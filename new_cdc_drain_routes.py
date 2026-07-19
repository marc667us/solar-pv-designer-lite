"""CDC slice 3 -- the FIRST CONSUMER of the change feed.

Slice 1 (migration 036) shipped the outbox mechanism dark. Slice 2 (migration 037) attached
the first capture triggers, to equipment_catalog only. Rows have been accumulating since, and
nothing has read them. This is the thing that reads them.

WHAT IT DOES: drains unconsumed `cdc_outbox` rows in batches and raises ONE aggregated admin
notification per pass -- "12 catalogue changes: 3 inserted, 8 updated, 1 deleted". That is the
"alerted" half of the owner's ask (2026-07-13: "make when database change everything else is
alerted and updated"). The "updated" half -- cache invalidation -- is NOT done here, and the
reason is in the `_mp_cache_invalidate` note at the bottom of this docstring.

WHY AN ALERT IS THE RIGHT FIRST CONSUMER
----------------------------------------
The delivery guarantee is AT-LEAST-ONCE, not exactly-once (migration 036 says so explicitly,
after Codex corrected an earlier claim). A drainer can perform its side effect and crash
before stamping `consumed_at`, and no outbox can prevent that -- exactly-once would require
the effect and the stamp to commit together, which is impossible when the effect leaves the
database.

So duplicates WILL eventually happen, and the first consumer must be one whose duplicate is
HARMLESS. A repeated admin notification is a cosmetic annoyance. A repeated customer email, a
repeated price sync, or a repeated payment would not be. Choosing the effect to match the
guarantee is the design, not a limitation of it.

Idempotency is nonetheless keyed on `cdc_outbox.id` as the design requires: the notification's
fingerprint is derived from the highest outbox id in the batch, so re-processing the SAME
batch dedupes inside `_admin_notify` rather than posting twice. A retry that picks up a
DIFFERENT batch (because new rows arrived meanwhile) correctly produces a new notification --
that is a different set of changes, not a duplicate.

THE CLAIM IS A REAL `FOR UPDATE SKIP LOCKED`, UNLIKE THE ENTERPRISE DRAIN
-------------------------------------------------------------------------
`/enterprise/jobs/drain` uses a plain unlocked `SELECT ... LIMIT 3` and relies on the GitHub
workflow's `concurrency.group` plus a unique index to stop double-processing. That is adequate
for at most three long-running jobs. It is NOT adequate here: this table takes a row per
catalogue write (equipment_catalog alone has ~90 write sites), batches are large, and a
retry-after-lease can legitimately overlap a slow pass. So this implements the locking claim
that migration 036 specified -- it is a mechanism to build, not one to reuse.

NOTHING IS EVER SILENTLY DROPPED
--------------------------------
A row that keeps failing is retried until `attempts` reaches _MAX_ATTEMPTS, then stops being
claimed -- but it is NOT consumed and NOT deleted. It stays in the table as evidence, where
the read-only `CDC Outbox Retention` workflow reports it as STUCK. This matches that
workflow's existing rule that unconsumed rows are never pruned at any age, because an old
unconsumed row is pending work, not garbage.

WHY THIS DOES NOT CALL `_mp_cache_invalidate()`
-----------------------------------------------
It would not work, and it would look like it did -- the worse of the two failures.

Each gunicorn worker holds its own `_MARKETPLACE_CACHE` dict. A drainer runs inside ONE
worker, so clearing the cache there leaves every other worker just as stale while making the
logs read as though invalidation happened. Migration 036 separates the two channels precisely
for this reason: durable side-effects go through the outbox and are claimed by one drainer;
cache invalidation is a BROADCAST and must travel over `pg_notify`, which every LISTENer
receives. Wiring that up is a later slice and needs a listener in each worker process.

`_mp_cache_invalidate()` is deliberately still callerless. It stays the designated entry point
for the broadcast half. The staleness it addresses is bounded to 60s by
`_MARKETPLACE_CACHE_TTL` and affects only anonymous `/marketplace` visitors, so leaving it for
a later slice costs at most a minute of staleness -- far less than shipping an invalidation
that silently covers one worker in N.
"""

import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from flask import abort, request

_log = logging.getLogger(__name__)

# How many outbox rows one pass will claim. Bounded because the cron has a finite HTTP budget
# (the workflow allows 280s) and because a claim holds row locks for the length of the
# transaction -- a giant batch would block catalogue writes waiting on the same rows.
_BATCH_LIMIT = 200

# A claimed row whose drainer never came back is re-claimable after this long. This is why
# `claimed_at` is a TIMESTAMP and not a boolean: a crashed pass must self-heal without an
# operator, and "claimed" with no expiry would strand the row forever.
_LEASE_MINUTES = 15

# After this many failed attempts a row stops being claimed. It is NOT consumed and NOT
# deleted -- see the module docstring. Retrying a poison row forever would starve the healthy
# ones behind it and turn one bad row into a permanent outage of the whole feed.
_MAX_ATTEMPTS = 5


def _is_postgres():
    """Backend detection, matching get_db() exactly.

    Deliberately identical to web_app._inbox_is_pg: a DATABASE_URL of `sqlite:///...` must NOT
    count as Postgres. cdc_outbox, the capture triggers and `FOR UPDATE SKIP LOCKED` are all
    Postgres-only, so on SQLite this endpoint has nothing to drain and says so loudly rather
    than pretending to succeed.
    """
    return (os.environ.get("DATABASE_URL") or "").startswith(
        ("postgres://", "postgresql://"))


def _summarise(rows):
    """Turn a claimed batch into (title, body, severity, max_id).

    Aggregated on purpose. One notification PER ROW would flood the admin inbox on any bulk
    catalogue sweep -- and bulk sweeps are exactly what this table sees. An alert nobody can
    read is not an alert.

    rows: sequence of (id, source_table, op, row_pk, payload)
    """
    max_id = 0
    per_table = {}          # source_table -> {op -> count}
    for r in rows:
        rid, table, op = int(r[0]), str(r[1]), str(r[2])
        if rid > max_id:
            max_id = rid
        per_table.setdefault(table, {})
        per_table[table][op] = per_table[table].get(op, 0) + 1

    total = len(rows)
    deletes = sum(ops.get("DELETE", 0) for ops in per_table.values())

    # A DELETE is the one op that destroys information, so it lifts the severity. Everything
    # else in a catalogue feed is routine.
    severity = "warning" if deletes else "info"

    parts = []
    for table in sorted(per_table):
        ops = per_table[table]
        detail = ", ".join(
            "%d %s" % (ops[op], op.lower())
            for op in ("INSERT", "UPDATE", "DELETE") if ops.get(op))
        parts.append("%s: %s" % (table, detail))

    title = "%d database change%s captured" % (total, "" if total == 1 else "s")
    body = "\n".join(parts)
    return title, body, severity, max_id


def register_cdc_drain(app, get_db=None, admin_notify=None):
    """Attach the CDC drain endpoint.

    Dependencies are injected rather than imported so this module never imports web_app --
    the same reason the enterprise and ops-support modules take theirs as arguments.
    """

    @app.route("/cdc/outbox/drain", methods=["POST"])
    def cdc_outbox_drain():
        """The CDC worker. Called by a scheduled GitHub Action, never by a browser.

        There is no worker PROCESS and there cannot be one -- Render's free tier caps this
        account at a single instance. So, exactly like /enterprise/jobs/drain, the queue is
        drained by an authenticated POST from a cron.

        AUTH IS COPIED VERBATIM FROM THE ENTERPRISE DRAIN, INCLUDING ITS THREE PROPERTIES:
        an unset secret is a 404 (a misconfiguration must never fail open), the comparison is
        hmac.compare_digest (a plain == leaks length and, given attempts, bytes), and both a
        malformed and a wrong token are 401. A cron has no session, so there is nothing for
        @login_required to check and nothing for CSRF to protect -- their absence is
        deliberate and this token is the only thing standing between a stranger and the feed.
        """
        secret = os.environ.get("CDC_DRAIN_TOKEN") or ""
        if not secret:
            abort(404)
        presented = request.headers.get("Authorization") or ""
        if not presented.startswith("Bearer "):
            abort(401)

        # COMPARE BYTES, NOT str. `hmac.compare_digest` RAISES TypeError
        # ("comparing strings with non-ASCII characters is not supported") when either str
        # argument is non-ASCII -- so a secret with one stray non-ASCII byte turns every
        # request into an unhandled 500 instead of an honest 401.
        #
        # That is not hypothetical: it is exactly what happened on the first live run,
        # 2026-07-19. `gh secret set` was fed the token over a PowerShell 5.1 pipe, which
        # prepended a UTF-8 BOM, so the stored secret began with U+FEFF and this line raised
        # on every call. Encoding both sides to UTF-8 bytes is still constant-time, never
        # raises, and makes a corrupted secret fail CLOSED and legibly (401, which the cron
        # already explains as "the GH secret and the Render env value disagree").
        #
        # Deliberately NOT stripping the BOM: silently repairing a malformed secret would
        # hide the misconfiguration instead of reporting it.
        if not hmac.compare_digest(presented[7:].encode("utf-8"), secret.encode("utf-8")):
            abort(401)

        # Loud, not silent. A cron quietly receiving 200/"skipped" forever would hide a
        # misconfigured environment for as long as nobody went looking.
        if not _is_postgres():
            return {"error": "cdc requires postgres; DATABASE_URL is not a postgres url"}, 503

        now = datetime.now(timezone.utc)
        lease_cutoff = now - timedelta(minutes=_LEASE_MINUTES)

        # ── 1. CLAIM ────────────────────────────────────────────────────────────────────
        # Its own transaction, committed before the side effect runs. Holding row locks
        # across an admin-notification write would block catalogue writes for no reason, and
        # if the pass then died the locks would only clear on connection teardown.
        claimed = []
        with get_db() as c:
            rows = c.execute(
                "SELECT id, source_table, op, row_pk, payload "
                "  FROM cdc_outbox "
                " WHERE consumed_at IS NULL "
                "   AND attempts < ? "
                "   AND (claimed_at IS NULL OR claimed_at < ?) "
                " ORDER BY changed_at "
                " LIMIT ? "
                "   FOR UPDATE SKIP LOCKED",
                (_MAX_ATTEMPTS, lease_cutoff, _BATCH_LIMIT),
            ).fetchall()

            claimed = [tuple(r) for r in rows]
            if claimed:
                ids = [int(r[0]) for r in claimed]
                # Parameterised IN-list: the ids come from the database, but building SQL by
                # concatenating them would still be the wrong habit to leave in the file.
                placeholders = ",".join("?" for _ in ids)
                c.execute(
                    "UPDATE cdc_outbox "
                    "   SET claimed_at = ?, attempts = attempts + 1 "
                    " WHERE id IN (%s)" % placeholders,
                    tuple([now] + ids),
                )

        if not claimed:
            return {"claimed": 0, "consumed": 0, "notified": False}, 200

        ids = [int(r[0]) for r in claimed]
        title, body, severity, max_id = _summarise(claimed)

        # ── 2. THE SIDE EFFECT ──────────────────────────────────────────────────────────
        # Outside any transaction we hold. If this raises, the rows stay claimed and
        # unconsumed and are retried after the lease expires -- at-least-once, by design.
        # `_admin_notify` DOES NOT RAISE ON FAILURE -- IT RETURNS None. (Codex HIGH,
        # 2026-07-19. The first draft of this function only handled the exception path and
        # would therefore have treated a failed write as success and consumed the rows,
        # losing those changes permanently -- the exact opposite of what this module's
        # docstring promises.) Its full contract, from web_app.py:
        #
        #     int > 0  -- the notification row was written
        #     0        -- deduped against an existing unread row: the alert is ALREADY
        #                 there, so this is SUCCESS, not failure. This is the idempotency
        #                 key doing its job on a replayed batch, and treating it as failure
        #                 would make a duplicate batch retry forever.
        #     None     -- the write failed and was swallowed internally
        #
        # So success is `result is not None`, and it is checked, not assumed. An exception
        # is still caught as well: "never raises" is a promise about today's implementation,
        # and this consumer must not be the thing that breaks when that changes.
        notify_error = None
        try:
            if admin_notify is None:
                notify_error = "no admin_notify was injected"
            else:
                result = admin_notify(
                    "cdc", severity, title, body,
                    ref_type="cdc_outbox", ref_id=max_id,
                    # THE IDEMPOTENCY KEY, and it is cdc_outbox.id as the design demands.
                    # Re-processing the same batch produces the same fingerprint, which
                    # _admin_notify dedupes (returning 0) instead of posting twice.
                    fingerprint="cdc_drain:%d" % max_id,
                    dedupe_minutes=1440,
                )
                if result is None:
                    notify_error = "admin_notify returned None (the write failed)"
        except Exception as e:            # noqa: BLE001 -- see the contract note above
            notify_error = "notify raised: " + str(e)

        if notify_error is not None:
            # An alert that was not delivered must NOT consume the rows: consuming them
            # would convert a delivery failure into permanent silence about those changes.
            # Record why and leave them for the next pass -- the lease makes them
            # re-claimable, and `attempts` bounds the retrying.
            _log.warning("cdc drain: notification failed: %s", notify_error)
            with get_db() as c:
                placeholders = ",".join("?" for _ in ids)
                c.execute(
                    "UPDATE cdc_outbox SET last_error = ? WHERE id IN (%s)" % placeholders,
                    tuple([("notify: " + notify_error)[:500]] + ids),
                )
            return {"claimed": len(ids), "consumed": 0, "notified": False,
                    "error": notify_error[:200]}, 500

        notified = True

        # ── 3. CONSUME ──────────────────────────────────────────────────────────────────
        # Only after the effect succeeded. The window between the effect and this stamp is
        # precisely where at-least-once lives: a crash here replays the batch, which is why
        # the effect above had to be one whose duplicate is harmless.
        with get_db() as c:
            placeholders = ",".join("?" for _ in ids)
            c.execute(
                "UPDATE cdc_outbox SET consumed_at = ?, last_error = '' "
                " WHERE id IN (%s)" % placeholders,
                tuple([datetime.now(timezone.utc)] + ids),
            )

        return {
            "claimed": len(ids),
            "consumed": len(ids),
            "notified": notified,
            "max_outbox_id": max_id,
            "summary": json.loads(json.dumps({"title": title, "body": body})),
        }, 200

    return app
