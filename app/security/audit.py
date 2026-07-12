"""
Audit-log writer for SolarPro Phase 6 audit unification.

Plan §19 task 31 + the audit-unification half of plan §4.7. Centralises
inserts into the existing `audit_logs` table so the Phase 2 decorators,
the Phase 5 OIDC callback, the Phase 6 Keycloak event webhook, and any
future code path can record an attributable, tenant-aware event with
one call.

Schema target (from web_app.py:init_db, mirrored on Postgres by
migration 001):

    CREATE TABLE audit_logs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER DEFAULT NULL,
        username    TEXT DEFAULT '',
        action      TEXT NOT NULL,
        ip_address  TEXT DEFAULT '',
        details     TEXT DEFAULT '',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    )

Phase 6 migration 004 adds `tenant_id UUID` and `agent_id TEXT` so
service-account actions can be distinguished from human actions and
tenant filters can apply.

Behavioural contract
--------------------

`write_audit_event` never raises. A failed audit write is logged
through the structured logger and silently dropped -- the calling
request still completes. This is the right trade-off because the
alternative (5xx on audit failure) would let a database problem brick
authn/authz, and Phase 7 cutover sees enough surface area without that
risk.

It IS still safe to call this from inside a request handler, from a
background worker, from a webhook receiver, or from a CLI. The writer
uses SolarPro's `get_db()` so the same dual-backend (SQLite/Postgres)
detection applies.

Parallel-run
------------

Nothing in this module reads `KEYCLOAK_ENABLED`. Audit writes happen
regardless of the migration flag -- the Phase 6 design is that audit
unification is one-way: even when Keycloak is off, denials and
sensitive admin actions still land in `audit_logs`.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
from typing import Any, Optional, Tuple


log = logging.getLogger(__name__)


GENESIS_HASH = "GENESIS"


def _canonical_audit_content(
    user_id: Optional[int],
    username: str,
    action: str,
    ip_address: str,
    details: str,
    created_at: str,
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> str:
    """Deterministic pipe-joined serialisation of a single audit_logs
    row, matched bit-for-bit by migrations/016_audit_log_hash_chain.sql.

    COALESCE-to-empty so NULL and '' hash identically (legacy rows have
    a mix of both for username / ip_address / details). The Python side
    and PG side MUST agree on this format -- if they diverge, the
    verifier flags every row as tampered.
    """
    return "|".join([
        str(user_id) if user_id is not None else "",
        username or "",
        action or "",
        ip_address or "",
        details or "",
        created_at or "",
        str(tenant_id) if tenant_id else "",
        agent_id or "",
    ])


def _sha256_chain_hash(prev_hash: Optional[str], content: str) -> str:
    """sha256((prev_hash or GENESIS) || '|' || content) as hex.

    Matches PG-side `_audit_row_hash(prev, content)`. Used both at
    INSERT (writer) and during chain verification."""
    seed = (prev_hash if prev_hash else GENESIS_HASH) + "|" + content
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


# Sentinel set in the test suite to capture writes without touching a
# real DB. When non-None, write_audit_event appends a dict to the list
# instead of calling get_db.
_TEST_SINK: Optional[list[dict]] = None


def set_test_sink(sink: Optional[list[dict]]) -> None:
    """Test-only hook. Pass a list to capture audit rows; pass None to
    restore the default DB-writing behaviour."""
    global _TEST_SINK
    _TEST_SINK = sink


def _stringify_details(details: Any) -> str:
    """Coerce arbitrary structured details into the TEXT details column.
    None -> empty string; dict/list -> JSON; bytes/str -> as-is."""
    if details is None:
        return ""
    if isinstance(details, (str, bytes)):
        return details if isinstance(details, str) else details.decode("utf-8", "replace")
    try:
        return json.dumps(details, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        return repr(details)


def _is_postgres() -> bool:
    """True when the app is running against Postgres rather than SQLite.

    Used to decide whether the hash-chain write needs an advisory lock.
    SQLite serialises writers itself via the database-file lock."""
    import os
    return str(os.environ.get("DATABASE_URL", "")).startswith(
        ("postgres://", "postgresql://")
    )


def _resolve_get_db():
    """Late import so this module can be imported before web_app.py
    has finished assembling the app. Returns the get_db callable."""
    try:
        import web_app  # type: ignore
        return web_app.get_db
    except Exception:
        return None


def _probe_audit_columns(conn) -> dict:
    """Probe audit_logs column presence; cached per process. Re-probed
    after `reset_schema_probe()` (called from migration apply paths)."""
    global _AUDIT_COLS
    if _AUDIT_COLS is not None:
        return _AUDIT_COLS
    cols: set[str] = set()
    try:
        cur = conn.execute("SELECT * FROM audit_logs WHERE 1=0")
        cols = {d[0].lower() for d in (cur.description or [])}
    except Exception:
        cols = set()
    _AUDIT_COLS = {
        "tenant_id": "tenant_id" in cols,
        "agent_id":  "agent_id" in cols,
        "prev_hash": "prev_hash" in cols,
        "row_hash":  "row_hash" in cols,
    }
    return _AUDIT_COLS


def _table_has_phase6_columns(conn) -> bool:
    """Back-compat alias retained for callers in the migration probe
    code path. New code should use _probe_audit_columns()."""
    probe = _probe_audit_columns(conn)
    return probe["tenant_id"] and probe["agent_id"]


_AUDIT_COLS: Optional[dict] = None


def reset_schema_probe() -> None:
    """Tests + migration runs call this after applying 004 / 016 so
    the column probe is recomputed."""
    global _AUDIT_COLS
    _AUDIT_COLS = None


def _now_audit_ts() -> str:
    """Return `YYYY-MM-DD HH:MM:SS` UTC string. Matches sqlite_ts() in
    migrations/001 so PG-side and app-side hash content agree."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _read_last_row_hash(conn) -> str:
    """SELECT the row_hash of the highest-id audit_logs row; returns
    GENESIS sentinel when the table is empty or the column doesn't
    exist yet. Wraps any read failure to GENESIS so an audit write is
    never blocked by a chain probe error."""
    try:
        cur = conn.execute(
            "SELECT row_hash FROM audit_logs "
            "WHERE row_hash IS NOT NULL "
            "ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row:
            value = row[0] if not hasattr(row, "keys") else row["row_hash"]
            if value:
                return value
    except Exception as e:
        log.debug("audit: chain head read failed (%s); using GENESIS.", e)
    return GENESIS_HASH


def _compute_chain_for_insert(
    conn,
    *,
    user_id: Optional[int],
    username: str,
    action: str,
    ip_address: str,
    details: str,
    tenant_id: Optional[str],
    agent_id: Optional[str],
) -> Tuple[str, str, str]:
    """Return (prev_hash, row_hash, created_at_iso) for a row about to
    be INSERTed. Reads the current chain head, computes the canonical
    content, returns both hashes plus the explicit created_at the
    caller must pass so PG-default-driven timestamps don't fork from
    the hash content.

    SERIALISED, because a hash chain that two writers can build at once
    is not a hash chain. Read-head-then-insert is a read-modify-write:
    request A reads head H100 and has not committed; request B cannot
    see A's row, reads H100 too, and commits. Now two rows both claim
    prev_hash=H100 and verify_audit_chain() -- which walks id ASC --
    reports a FORK. The evidence stops being evidence, which is the one
    thing an audit chain exists to prevent.

    The advisory lock is transaction-scoped, so it is released by the
    caller's COMMIT or ROLLBACK with no unlock call to forget. On SQLite
    no lock is needed: a write transaction already locks the database
    file, so writers are serialised by the engine.

    (Raised by the Codex slice-3 review. The race predates the `conn=`
    parameter -- any two concurrent audit writes could fork the chain --
    but `conn=` holds the transaction open for longer and widens it.)

    THE COST, AND THE RULE IT IMPOSES ON CALLERS. Being transaction-scoped
    cuts both ways: when `conn=` is passed, this lock is held until the
    CALLER commits, and every other audit write in the app -- logins, OIDC
    callbacks, admin actions -- queues behind it. That is acceptable only
    because an audited action writes its audit row LAST, so the window is
    a commit away. Callers passing `conn=` MUST keep it that way: do not
    do further work after the audit call and before the commit, or a slow
    tail (a report, a bulk generate) turns a local lock into an app-wide
    stall. The Supervisor raised this on slice 3; it is a constraint on
    callers, not a defect in the lock.
    """
    if _is_postgres():
        # Constant key: every audit writer contends on this one lock.
        conn.execute("SELECT pg_advisory_xact_lock(4242000000000001)")
    created_at = _now_audit_ts()
    prev_hash = _read_last_row_hash(conn)
    content = _canonical_audit_content(
        user_id=user_id, username=username, action=action,
        ip_address=ip_address, details=details, created_at=created_at,
        tenant_id=tenant_id, agent_id=agent_id,
    )
    row_hash = _sha256_chain_hash(prev_hash, content)
    return prev_hash, row_hash, created_at


def write_audit_event(
    action: str,
    *,
    user_id: Optional[int] = None,
    username: str = "",
    ip: str = "",
    details: Any = None,
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    conn: Any = None,
) -> bool:
    """Insert one row into audit_logs.

    Returns True if the row was persisted, False on any failure (the
    error is logged but never raised). The non-raising contract is
    deliberate: see module docstring.

    `conn` (optional): write on THIS connection instead of opening one.
    The row is then neither committed nor closed here -- it lands in the
    caller's transaction, so the audit row and the action it describes
    commit together or not at all. Callers that must not act without an
    audit trail (the enterprise module, control C12) pass their connection.
    Omit it and behaviour is exactly as before.
    """
    if not action:
        log.warning("write_audit_event called with empty action; dropping.")
        return False

    payload = {
        "action": action,
        "user_id": user_id,
        "username": username or "",
        "ip_address": ip or "",
        "details": _stringify_details(details),
        "tenant_id": tenant_id,
        "agent_id": agent_id,
    }

    if _TEST_SINK is not None:
        _TEST_SINK.append(payload)
        return True

    # A CALLER-SUPPLIED connection is used as-is, and neither committed nor closed here --
    # it belongs to the caller's transaction. This is what lets a caller make the audit row
    # ATOMIC with the action it describes: they commit both together, or neither.
    #
    # It also fixes a real deadlock. On SQLite the whole database file is locked by an open
    # write transaction, so a caller mid-write who triggers an audit on a SECOND connection
    # gets "database is locked" -- the audit is dropped, and any caller that treats a failed
    # audit as a failed action (as the enterprise module must, for control C12) rolls itself
    # back forever. Postgres never showed it; SQLite did, immediately.
    caller_conn = conn
    if caller_conn is None:
        get_db = _resolve_get_db()
        if get_db is None:
            log.warning("audit: get_db unavailable; %s dropped.", action)
            return False
        try:
            conn = get_db()
        except Exception as e:
            log.warning("audit: get_db() raised (%s); %s dropped.", e, action)
            return False

    try:
        # `with conn:` COMMITS on exit. That is right for a connection we opened, and wrong
        # for the caller's -- committing their transaction is not ours to do.
        with (contextlib.nullcontext() if caller_conn is not None else conn):
            probe = _probe_audit_columns(conn)
            has_phase6 = probe["tenant_id"] and probe["agent_id"]
            has_chain  = probe["prev_hash"] and probe["row_hash"]

            if has_chain:
                # SOC 2 M3.2: SHA-256 chain. Compute prev_hash from the
                # current chain head + canonical content (including a
                # Python-side created_at so PG's default doesn't fork
                # the hash content).
                prev_hash, row_hash, created_at = _compute_chain_for_insert(
                    conn,
                    user_id=payload["user_id"], username=payload["username"],
                    action=payload["action"], ip_address=payload["ip_address"],
                    details=payload["details"],
                    tenant_id=payload["tenant_id"] if has_phase6 else None,
                    agent_id=payload["agent_id"] if has_phase6 else None,
                )
                if has_phase6:
                    conn.execute(
                        "INSERT INTO audit_logs "
                        "(user_id, username, action, ip_address, details, "
                        " tenant_id, agent_id, created_at, prev_hash, row_hash) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (payload["user_id"], payload["username"], payload["action"],
                         payload["ip_address"], payload["details"],
                         payload["tenant_id"], payload["agent_id"],
                         created_at, prev_hash, row_hash),
                    )
                else:
                    merged = payload["details"]
                    if payload["tenant_id"] or payload["agent_id"]:
                        merged = _stringify_details({
                            "details": payload["details"],
                            "tenant_id": payload["tenant_id"],
                            "agent_id": payload["agent_id"],
                        })
                    conn.execute(
                        "INSERT INTO audit_logs "
                        "(user_id, username, action, ip_address, details, "
                        " created_at, prev_hash, row_hash) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (payload["user_id"], payload["username"], payload["action"],
                         payload["ip_address"], merged,
                         created_at, prev_hash, row_hash),
                    )
            elif has_phase6:
                conn.execute(
                    "INSERT INTO audit_logs "
                    "(user_id, username, action, ip_address, details, "
                    " tenant_id, agent_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (payload["user_id"], payload["username"], payload["action"],
                     payload["ip_address"], payload["details"],
                     payload["tenant_id"], payload["agent_id"]),
                )
            else:
                # Pre-migration schema -- shove tenant_id + agent_id
                # into details so we don't lose them.
                merged = payload["details"]
                if payload["tenant_id"] or payload["agent_id"]:
                    merged = _stringify_details({
                        "details": payload["details"],
                        "tenant_id": payload["tenant_id"],
                        "agent_id": payload["agent_id"],
                    })
                conn.execute(
                    "INSERT INTO audit_logs "
                    "(user_id, username, action, ip_address, details) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (payload["user_id"], payload["username"], payload["action"],
                     payload["ip_address"], merged),
                )
        # SOC 2 M3.4: bump the Prometheus counter so Grafana shows
        # the write rate (per action) without re-reading audit_logs.
        try:
            from app.observability import audit_writes_total
            audit_writes_total.labels(action=action).inc()
        except Exception:
            pass
        return True
    except Exception as e:
        log.warning("audit: INSERT failed (%s); %s dropped.", e, action)
        return False
    finally:
        # Close only what we opened. Closing the caller's connection would end their
        # transaction under them.
        if caller_conn is None:
            try:
                conn.close()
            except Exception:
                pass


# ── Convenience wrappers for common audit shapes ────────────────────────

def audit_login_success(user_id: int, username: str, ip: str,
                        tenant_id: Optional[str] = None) -> bool:
    return write_audit_event(
        "LOGIN_SUCCESS", user_id=user_id, username=username,
        ip=ip, tenant_id=tenant_id,
    )


def audit_login_failed(username: str, ip: str, reason: str = "") -> bool:
    return write_audit_event(
        "LOGIN_FAILED", username=username, ip=ip,
        details={"reason": reason} if reason else None,
    )


def audit_logout(user_id: int, username: str, ip: str,
                 tenant_id: Optional[str] = None) -> bool:
    return write_audit_event(
        "LOGOUT", user_id=user_id, username=username,
        ip=ip, tenant_id=tenant_id,
    )


def audit_permission_denied(
    action_path: str,
    *,
    reason: str,
    user_id: Optional[int] = None,
    ip: str = "",
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> bool:
    details = {"path": action_path, "reason": reason}
    if extra:
        details.update(extra)
    return write_audit_event(
        "PERMISSION_DENIED",
        user_id=user_id, ip=ip,
        details=details,
        tenant_id=tenant_id, agent_id=agent_id,
    )


# ── SOC 2 M3.2 -- chain verifier ────────────────────────────────────────

def verify_audit_chain(conn, *, limit: Optional[int] = None) -> dict:
    """Walk audit_logs in id ASC order, recompute each row_hash, and
    return a summary that the SOC 2 dashboard + admin route render.

    Returns:
      {
        "total":         int,           -- rows examined
        "verified":      int,           -- rows whose stored row_hash matched
        "unchained":     int,           -- rows with NULL row_hash (legacy)
        "first_break":   {              -- None if no break detected
            "id":           int,
            "reason":       str,
            "expected":     str,
            "stored":       str,
        } | None,
        "last_chained_id": int | None,  -- highest id that verified clean
      }

    Reasons emitted on a break:
      * 'tamper_row_hash_mismatch' -- stored row_hash != sha256(prev||content)
      * 'tamper_prev_hash_mismatch' -- row.prev_hash != prior row.row_hash
    """
    probe = _probe_audit_columns(conn)
    has_phase6 = probe["tenant_id"] and probe["agent_id"]
    has_chain  = probe["prev_hash"] and probe["row_hash"]
    if not has_chain:
        return {
            "total": 0, "verified": 0, "unchained": 0,
            "first_break": None, "last_chained_id": None,
            "error": "audit_logs missing prev_hash/row_hash columns "
                     "(migration 016 not applied)",
        }

    cols_select = ("id, user_id, username, action, ip_address, details, "
                   "created_at, prev_hash, row_hash")
    if has_phase6:
        cols_select += ", tenant_id, agent_id"

    sql = f"SELECT {cols_select} FROM audit_logs ORDER BY id ASC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur = conn.execute(sql)
    rows = cur.fetchall()

    total = len(rows)
    verified = 0
    unchained = 0
    prev_row_hash = GENESIS_HASH
    first_break = None
    last_chained_id = None

    for r in rows:
        try:
            row_id     = r["id"]
            stored_row = r["row_hash"]
            stored_prev = r["prev_hash"]
        except Exception:
            row_id = r[0]; stored_row = r[8]; stored_prev = r[7]

        if not stored_row:
            unchained += 1
            continue

        try:
            user_id    = r["user_id"]
            username   = r["username"] or ""
            action     = r["action"] or ""
            ip_address = r["ip_address"] or ""
            details    = r["details"] or ""
            created_at = r["created_at"] or ""
            tenant_id  = r["tenant_id"] if has_phase6 else None
            agent_id   = r["agent_id"]  if has_phase6 else None
        except Exception:
            user_id = r[1]; username = r[2] or ""; action = r[3] or ""
            ip_address = r[4] or ""; details = r[5] or ""; created_at = r[6] or ""
            tenant_id = r[9] if has_phase6 else None
            agent_id  = r[10] if has_phase6 else None

        content = _canonical_audit_content(
            user_id=user_id, username=username, action=action,
            ip_address=ip_address, details=details, created_at=created_at,
            tenant_id=tenant_id, agent_id=agent_id,
        )
        expected_row_hash = _sha256_chain_hash(stored_prev, content)

        if first_break is None and expected_row_hash != stored_row:
            first_break = {
                "id": row_id,
                "reason": "tamper_row_hash_mismatch",
                "expected": expected_row_hash,
                "stored": stored_row,
            }
            continue

        expected_prev = prev_row_hash if prev_row_hash else GENESIS_HASH
        stored_prev_compare = stored_prev if stored_prev else GENESIS_HASH
        if first_break is None and stored_prev_compare != expected_prev:
            first_break = {
                "id": row_id,
                "reason": "tamper_prev_hash_mismatch",
                "expected": expected_prev,
                "stored": stored_prev_compare,
            }
            continue

        if first_break is None:
            verified += 1
            last_chained_id = row_id
            prev_row_hash = stored_row

    return {
        "total": total,
        "verified": verified,
        "unchained": unchained,
        "first_break": first_break,
        "last_chained_id": last_chained_id,
    }


__all__ = [
    "GENESIS_HASH",
    "audit_login_failed",
    "audit_login_success",
    "audit_logout",
    "audit_permission_denied",
    "reset_schema_probe",
    "set_test_sink",
    "verify_audit_chain",
    "write_audit_event",
]
