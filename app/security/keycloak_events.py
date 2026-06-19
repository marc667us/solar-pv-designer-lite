"""
Keycloak admin/user event ingestion for SolarPro.

Plan §19 tasks 29 + 30 of docs/SECURITY_MIGRATION_KEYCLOAK.md.

Keycloak emits two kinds of events:

  * **User events** -- LOGIN, LOGIN_ERROR, LOGOUT, REGISTER,
    REFRESH_TOKEN, UPDATE_PASSWORD, REVOKE_GRANT, ...
  * **Admin events** -- CREATE/UPDATE/DELETE of users/roles/clients/groups.

The realm export ships with the built-in "jboss-logging" and "email"
listeners. To get the events into SolarPro's `audit_logs` table we
have two delivery paths and this module supports both:

  (a) **Webhook** -- an SPI listener JAR posts each event to
      `POST /api/keycloak/events` with an HMAC-SHA256 signature in
      `X-Keycloak-Event-Signature`. SolarPro verifies the signature
      using `KEYCLOAK_WEBHOOK_SECRET` and writes one audit_log row.
  (b) **Poller** -- `scripts/poll_keycloak_events.py` calls Keycloak's
      admin REST endpoint `/admin/realms/<realm>/events` +
      `/admin/realms/<realm>/admin-events` on a cron and pipes the
      results through `process_event()` below. Required when the
      operator cannot install a custom SPI JAR (Render free tier,
      etc.).

Both paths converge on `process_event(payload)`, which deduplicates,
normalises the action name, and calls `app.security.audit.write_audit_event`.

Configuration
-------------

    KEYCLOAK_WEBHOOK_SECRET    Required for the webhook path. Used by
                               both Keycloak (to sign) and SolarPro
                               (to verify). Generated via
                               `openssl rand -hex 32`.
    KEYCLOAK_EVENT_DEDUPE_TTL  Seconds. Default 300. The webhook
                               receiver tracks recently-seen event IDs
                               to drop duplicates within this window
                               (Keycloak retries on 5xx).

This module is pure-Python; the SPI listener implementation lives in
Java/Kotlin and is out of scope for SolarPro's repo. The deployment
README at `docs/keycloak/event-listener-deploy.md` (Phase 6 deliverable)
documents the JAR build + install steps for whichever environment hosts
Keycloak.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import threading
import time
from typing import Optional

from app.security.audit import write_audit_event


log = logging.getLogger(__name__)


# ── HMAC verification ───────────────────────────────────────────────────

def _webhook_secret() -> str:
    return os.environ.get("KEYCLOAK_WEBHOOK_SECRET", "").strip()


def verify_signature(raw_body: bytes, provided: str) -> bool:
    """Constant-time HMAC-SHA256 verify of the raw request body.

    `provided` is the value of the `X-Keycloak-Event-Signature`
    header. Format: `sha256=<hex>` (matches Stripe / GitHub style so
    the SPI listener stays familiar).

    Returns False on any failure mode -- missing secret, missing
    prefix, length mismatch, computed mismatch.
    """
    secret = _webhook_secret()
    if not secret:
        log.warning("KEYCLOAK_WEBHOOK_SECRET not set; rejecting all webhook calls.")
        return False
    if not provided:
        return False
    if provided.startswith("sha256="):
        provided = provided[len("sha256="):]
    expected = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    try:
        return hmac.compare_digest(expected, provided)
    except Exception:
        return False


# ── Dedupe cache ────────────────────────────────────────────────────────

_DEFAULT_TTL = 300
_dedupe: dict[str, float] = {}
_dedupe_lock = threading.Lock()


def _dedupe_ttl() -> int:
    try:
        return int(os.environ.get("KEYCLOAK_EVENT_DEDUPE_TTL",
                                  str(_DEFAULT_TTL)))
    except ValueError:
        return _DEFAULT_TTL


def _is_duplicate(event_id: str, now: float) -> bool:
    if not event_id:
        return False
    ttl = _dedupe_ttl()
    cutoff = now - ttl
    with _dedupe_lock:
        # Opportunistic cleanup of stale ids so the dict can't grow
        # without bound under sustained webhook traffic.
        stale = [k for k, ts in _dedupe.items() if ts < cutoff]
        for k in stale:
            _dedupe.pop(k, None)
        if event_id in _dedupe and _dedupe[event_id] >= cutoff:
            return True
        _dedupe[event_id] = now
        return False


def clear_dedupe_cache() -> None:
    """Test-only helper. Drops the dedupe state so tests don't leak
    state into each other."""
    with _dedupe_lock:
        _dedupe.clear()


# ── Event normalisation ─────────────────────────────────────────────────

# Map raw Keycloak event types -> SolarPro audit_log action names.
# Anything not listed here gets a `KC_` prefix so the downstream UI
# can still group unknowns sensibly.
_USER_EVENT_MAP = {
    "LOGIN":              "LOGIN_SUCCESS",
    "LOGIN_ERROR":        "LOGIN_FAILED",
    "LOGOUT":             "LOGOUT",
    "LOGOUT_ERROR":       "LOGOUT_FAILED",
    "REGISTER":           "USER_REGISTERED",
    "REGISTER_ERROR":     "USER_REGISTER_FAILED",
    "REFRESH_TOKEN":      "TOKEN_REFRESHED",
    "REFRESH_TOKEN_ERROR": "TOKEN_REFRESH_FAILED",
    "REVOKE_GRANT":       "GRANT_REVOKED",
    "UPDATE_PASSWORD":    "PASSWORD_UPDATED",
    "UPDATE_TOTP":        "TOTP_UPDATED",
    "REMOVE_TOTP":        "TOTP_REMOVED",
    "CODE_TO_TOKEN":      "OIDC_CODE_EXCHANGE",
    "CODE_TO_TOKEN_ERROR": "OIDC_CODE_EXCHANGE_FAILED",
    "CLIENT_LOGIN":       "SA_LOGIN_SUCCESS",
    "CLIENT_LOGIN_ERROR": "SA_LOGIN_FAILED",
}


def _map_event_type(raw_type: str, is_admin: bool) -> str:
    if not raw_type:
        return "KC_UNKNOWN"
    if is_admin:
        return f"KC_ADMIN_{raw_type}"
    return _USER_EVENT_MAP.get(raw_type, f"KC_{raw_type}")


# ── Public entry point ──────────────────────────────────────────────────

def process_event(payload: dict, *, now: Optional[float] = None) -> str:
    """Persist one Keycloak event to `audit_logs`.

    Returns one of:
      * "stored"     -- row inserted
      * "duplicate"  -- event id already seen within TTL
      * "invalid"    -- payload couldn't be normalised
      * "dropped"    -- audit writer returned False (DB hiccup)

    The function never raises; both delivery paths trust the return
    value to decide whether to retry / log / alert.
    """
    if not isinstance(payload, dict):
        return "invalid"

    now = now if now is not None else time.time()
    event_id = str(payload.get("id") or payload.get("uniqueId") or "")
    if event_id and _is_duplicate(event_id, now):
        return "duplicate"

    raw_type = str(payload.get("type") or payload.get("operationType") or "")
    is_admin = "operationType" in payload or payload.get("realmId") and payload.get("resourceType")
    action = _map_event_type(raw_type, bool(is_admin))

    # Realm-level event payloads carry userId (UUID) but NOT the
    # SolarPro int id; record only what we have so the cutover script
    # can join later.
    user_sub = str(payload.get("userId") or payload.get("authDetails", {}).get("userId") or "")
    username = ""
    details = payload.get("details") if isinstance(payload.get("details"), dict) else None
    ip = str(payload.get("ipAddress") or payload.get("authDetails", {}).get("ipAddress") or "")
    realm = str(payload.get("realmId") or "")

    merged_details = {
        "kc_event_id": event_id or None,
        "kc_realm": realm or None,
        "kc_event_type": raw_type or None,
        "kc_details": details,
        "kc_resource_type": payload.get("resourceType"),
        "kc_resource_path": payload.get("resourcePath"),
        "kc_error": payload.get("error"),
    }

    ok = write_audit_event(
        action,
        username=username,
        ip=ip,
        details=merged_details,
        agent_id=user_sub or None,
    )
    return "stored" if ok else "dropped"


__all__ = [
    "clear_dedupe_cache",
    "process_event",
    "verify_signature",
]
