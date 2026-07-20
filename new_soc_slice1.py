# ─────────────────────────────────────────────────────────────────────────────
# AI-SOC — Slice 1: signal capture (detection only, ZERO actions)
# ─────────────────────────────────────────────────────────────────────────────
# Per docs/AI_SOC_IMPLEMENTATION_PLAN_2026-07-10.md Slice 1. Turns failures into
# append-only support_events rows (the "event bus" substitute). Nothing here acts,
# classifies, or remediates — that is Slice 2+. Detection rides the request path
# (an after_request 5xx catch) + a 5-min GitHub Actions health sweep; NO polling
# fleet, NO new daemon.
#
# Discipline (boot_state.py): the capture hook NEVER raises and NEVER blocks the
# request. A signal-write failure must not escalate the fault that triggered it.
#
# Gating: capture is gated on the soc_enabled() MASTER flag (default OFF) so the
# subsystem stays dark until an admin turns it on. The kill switch
# (soc_automation_enabled) governs ACTIONS — there are none in this slice.
#
# RLS-safe write: support_events is an admin-only table (migration 022). The
# signal fires inside a user's request context (app.current_role='user'), which
# RLS would reject once 022 is applied under Keycloak. So the writer opens its own
# transaction and elevates with set_config('app.current_role','admin',true) — the
# same idiom the platform-seed path uses. On SQLite this is a harmless no-op.
#
# Spliced into web_app.py by patch_soc_slice1.py (byte-level, CRLF-aware).

import hashlib as _soc_hashlib
import hmac as _soc_hmac
import threading as _soc_threading
from datetime import datetime as _soc_datetime


# The 5xx status codes that count as a backend failure signal. 501 (not
# implemented) is intentionally excluded — it is a routing/desig­n condition,
# not a fault.
_SOC_5XX_CAPTURE = (500, 502, 503, 504)


def _soc_hour_bucket():
    """UTC hour bucket 'YYYYMMDDHH' — the dedupe window per plan §6 Slice 1
    ((module, error_code, hour))."""
    try:
        return _soc_datetime.utcnow().strftime("%Y%m%d%H")
    except Exception:
        return "0"


def _soc_fingerprint(module, error_code):
    """Stable dedupe key over (module, error_code, hour). Encoding the hour into
    the fingerprint means the same fault in the same hour collapses to one row,
    while the next hour starts a fresh row — so one bad deploy writes O(hours)
    rows, not O(requests)."""
    raw = "%s|%s|%s" % (module or "", error_code or "", _soc_hour_bucket())
    return _soc_hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()


def soc_capture_signal(source, event_type, severity="P3", module=None,
                       error_code=None, payload=None, incident_id=None):
    """Append ONE support_events row for a detected signal, deduped by
    (module, error_code, hour). Detection only — writes no action, opens no
    incident (Slice 2 classifies these into incidents).

    Inputs:
      source      — 'backend' | 'cron' | 'security' | 'database' | 'api' ...
      event_type  — short machine tag, e.g. 'http_5xx', 'health_degraded'
      severity    — raw P1..P4 hint (the orchestrator reclassifies in Slice 2)
      module      — affected module / endpoint
      error_code  — status code or error identifier (part of the dedupe key)
      payload     — small str/dict of context (truncated); NEVER secrets
      incident_id — optional link if a caller already owns an incident

    Output: new row id, 0 if deduped this hour, or None if disabled/failed.
    NEVER raises.

    Dedupe is check-then-insert (not atomic). Two TRULY concurrent identical
    failures can therefore each pass the existence check and write a duplicate
    row — a rare, low-harm noise row, not a correctness fault. A global UNIQUE
    index on fingerprint is deliberately NOT used: it would over-constrain this
    append-only table for future non-deduped event types. The Slice 2
    orchestrator dedupes incidents from events, which absorbs the stray row."""
    try:
        if not soc_enabled():
            return None  # master switch off -> subsystem dark

        fp = _soc_fingerprint(module, error_code)
        sev = severity if severity in ("P1", "P2", "P3", "P4") else "P3"
        if payload is not None and not isinstance(payload, str):
            try:
                import json as _json
                payload = _json.dumps(payload, default=str)[:2000]
            except Exception:
                payload = str(payload)[:2000]
        elif isinstance(payload, str):
            payload = payload[:2000]

        is_pg = _inbox_is_pg()
        with get_db() as c:
            # RLS-safe elevation (no-op on SQLite). Transaction-local.
            if is_pg:
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            _ensure_soc_schema(c)
            dup = c.execute(
                "SELECT id FROM support_events WHERE fingerprint=? LIMIT 1", (fp,)
            ).fetchone()
            if dup:
                return 0  # already recorded this (module, error_code, hour)
            # lastrowid lives on the CURSOR returned by execute(), not the
            # connection (c). On Postgres db_adapter's _PgCursorWrap backfills it
            # via lastval(); on SQLite it is native.
            cur = c.execute(
                "INSERT INTO support_events "
                "(tenant_id, incident_id, source, event_type, severity, module, "
                " error_code, payload, fingerprint) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (None, incident_id, str(source)[:60], str(event_type)[:60], sev,
                 (str(module)[:120] if module is not None else None),
                 (str(error_code)[:60] if error_code is not None else None),
                 payload, fp))
            try:
                return int(getattr(cur, "lastrowid", 0) or 0)
            except Exception:
                return None
    except Exception:
        # Detection must never take down the request path.
        return None


def _soc_dispatch_async(**kwargs):
    """Fire-and-forget the signal write on a short-lived daemon thread so the
    response path is NEVER blocked by DB work (plan risk register: "the AI-SOC
    becomes the outage"). All request-scoped values are captured by the caller
    and passed in as plain kwargs — the thread has no request context, so it
    pushes its own app context. If the runtime can't spawn a thread
    (RuntimeError: can't start new thread — the boot_state.py failure mode),
    the signal is simply dropped: detection is best-effort, never load-bearing."""
    def _run():
        try:
            with app.app_context():
                eid = soc_capture_signal(**kwargs)
                # Slice 2 (if spliced): classify the new event into an incident,
                # still off the request path. globals()-guarded so Slice 1 runs
                # standalone if Slice 2 is absent.
                if eid and eid > 0:
                    _orch = globals().get("soc_orchestrate")
                    if _orch:
                        try:
                            _orch(eid)
                        except Exception:
                            pass
        except Exception:
            pass
    try:
        _soc_threading.Thread(target=_run, name="soc-signal", daemon=True).start()
    except Exception:
        pass


@app.after_request
def _soc_capture_5xx(response):
    """5xx capture. Fires after every response; when the status is a backend-
    failure code it dispatches ONE (deduped) support_events write to a background
    thread and returns the response immediately — no DB work on the hot path.
    Wrapped so nothing here can turn a served response into an error.

    On a normal 2xx/3xx/4xx response this does ONLY an integer membership test —
    zero DB access — so steady-state latency is unaffected."""
    try:
        code = getattr(response, "status_code", 200)
        if code in _SOC_5XX_CAPTURE:
            # Snapshot request-scoped values HERE (thread loses request context).
            try:
                module = request.endpoint or request.path
            except Exception:
                module = None
            try:
                method = getattr(request, "method", "?")
                path = getattr(request, "path", "?")
            except Exception:
                method, path = "?", "?"
            _soc_dispatch_async(
                source="backend", event_type="http_5xx", severity="P3",
                module=module, error_code=str(code),
                payload={"method": method, "path": path})
    except Exception:
        pass
    return response


# ── Cron ingest — the 5-min GitHub Actions health sweep posts here ─────────────

def _soc_ingest_authorized():
    """Bearer-gate the cron ingest with METRICS_BEARER (same secret that gates
    /metrics). Fail-CLOSED when the env is unset, so an unconfigured environment
    cannot be spammed with anonymous signal writes."""
    want = (os.environ.get("METRICS_BEARER") or "").strip()
    if not want:
        return False
    got = (request.headers.get("Authorization") or "").strip()
    if got.lower().startswith("bearer "):
        got = got[7:].strip()
    if not got:
        return False
    # constant-time compare — never leak length/prefix via early-exit timing.
    # COMPARE BYTES, NOT str: compare_digest RAISES TypeError on non-ASCII str,
    # and `got` is attacker-controlled (WSGI decodes headers latin-1, so any
    # byte 0x80-0xFF arrives as a non-ASCII char). Comparing str turns a
    # garbage Authorization header into an unhandled 500 instead of a 401.
    return _soc_hmac.compare_digest(got.encode("utf-8"), want.encode("utf-8"))


@app.route("/api/soc/ingest", methods=["POST"])
def api_soc_ingest():
    """Signal ingest for the health-sweep cron (and any external monitor). Bearer
    gated + fail-closed. Detection only: writes a support_events row via the same
    deduped, gated writer. Returns 202 on accept, 401 unauthorised, 403 when SOC
    disabled, 400 on bad input."""
    if not _soc_ingest_authorized():
        return jsonify({"error": "unauthorized"}), 401
    if not soc_enabled():
        return jsonify({"error": "soc_disabled", "captured": False}), 403
    data = request.get_json(silent=True) or {}
    source = data.get("source") or "cron"
    event_type = data.get("event_type")
    if not event_type:
        return jsonify({"error": "event_type required"}), 400
    rid = soc_capture_signal(
        source=source, event_type=event_type,
        severity=data.get("severity") or "P3",
        module=data.get("module"), error_code=data.get("error_code"),
        payload=data.get("payload"))
    # rid: int>0 new, 0 deduped, None failed/disabled.
    incident_id = None
    if rid and rid > 0:
        _orch = globals().get("soc_orchestrate")  # Slice 2, if spliced
        if _orch:
            try:
                incident_id = _orch(rid)
            except Exception:
                incident_id = None
    return jsonify({"captured": rid is not None, "deduped": rid == 0,
                    "event_id": rid if (rid and rid > 0) else None,
                    "incident_id": incident_id}), 202
