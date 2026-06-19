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

import json
import logging
from typing import Any, Optional


log = logging.getLogger(__name__)


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


def _resolve_get_db():
    """Late import so this module can be imported before web_app.py
    has finished assembling the app. Returns the get_db callable."""
    try:
        import web_app  # type: ignore
        return web_app.get_db
    except Exception:
        return None


def _table_has_phase6_columns(conn) -> bool:
    """Probe whether audit_logs has the Phase 6 tenant_id + agent_id
    columns. The probe runs once per process via a module cache."""
    global _PHASE6_COLS
    if _PHASE6_COLS is not None:
        return _PHASE6_COLS
    try:
        cur = conn.execute(
            "SELECT * FROM audit_logs WHERE 1=0"
        )
        cols = {d[0].lower() for d in (cur.description or [])}
        _PHASE6_COLS = ("tenant_id" in cols) and ("agent_id" in cols)
    except Exception:
        _PHASE6_COLS = False
    return _PHASE6_COLS


_PHASE6_COLS: Optional[bool] = None


def reset_schema_probe() -> None:
    """Tests + migration runs call this after applying 004 so the
    column probe is recomputed."""
    global _PHASE6_COLS
    _PHASE6_COLS = None


def write_audit_event(
    action: str,
    *,
    user_id: Optional[int] = None,
    username: str = "",
    ip: str = "",
    details: Any = None,
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> bool:
    """Insert one row into audit_logs.

    Returns True if the row was persisted, False on any failure (the
    error is logged but never raised). The non-raising contract is
    deliberate: see module docstring.
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
        with conn:
            if _table_has_phase6_columns(conn):
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
        return True
    except Exception as e:
        log.warning("audit: INSERT failed (%s); %s dropped.", e, action)
        return False
    finally:
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


__all__ = [
    "audit_login_failed",
    "audit_login_success",
    "audit_logout",
    "audit_permission_denied",
    "reset_schema_probe",
    "set_test_sink",
    "write_audit_event",
]
