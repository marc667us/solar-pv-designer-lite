"""
Tenant + user context bridge from Keycloak JWT to Postgres GUCs.

Phase 4 of docs/SECURITY_MIGRATION_KEYCLOAK.md. This module is the
middle layer that lets RLS work without sprinkling raw GUC writes
across the codebase.

It does two jobs:

1. **Read** the tenant_id + user sub off the validated JWT (which Phase 2
   already stashed in Flask's `g.kc_ctx`). Routes call
   `current_tenant_id()` and `current_user_sub()` instead of reading
   `g.kc_ctx` directly so the codebase has one chokepoint to change
   when the claim names move.

2. **Write** those values to the per-request Postgres connection as
   `app.current_tenant` and `app.current_user` GUCs. The RLS policies
   in `migrations/003_rls_tenant.sql` read those GUCs via the
   `current_tenant_id()` SQL helper.

Defence in depth (per plan §8.3):
    - JWT middleware refuses bad tokens.
    - Application code filters `WHERE tenant_id = ...`.
    - Postgres RLS refuses rows whose `tenant_id` does not match the GUC.
    - Even if the developer forgets the WHERE, the DB refuses.

Parallel-run safety
-------------------

The whole module is a graceful no-op when:

  * `KEYCLOAK_ENABLED` env is unset / false — the legacy `user_id`
    filter still runs and nothing changes.
  * The connection is SQLite — RLS doesn't exist there; we silently
    skip the GUC writes.
  * No JWT has been verified yet — `g.kc_ctx` is absent.

This lets us deploy the module before flipping the flag, exactly the
pattern used in Phase 2 and Phase 3.

Connection model
----------------

SolarPro opens a fresh DB connection per `get_db()` context (see
`db_adapter._PgConnAdapter`). That makes session-scoped GUCs safe in
principle, but we still use `SELECT set_config(..., is_local=true)` so
the GUC dies with the implicit transaction. If pooling is added later
the local-scope keeps us correct.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from flask import g, request, jsonify, has_request_context

from .keycloak_middleware import RequestContext


log = logging.getLogger(__name__)


KEYCLOAK_ENABLED_ENV = "KEYCLOAK_ENABLED"  # retired flag, kept for back-compat imports


def _keycloak_enabled() -> bool:
    """Retired 2026-06-25 (SOC 2 M1.1). Always True — Keycloak is the
    only auth path. RLS GUCs are set on every request that carries a
    verified JWT context."""
    return True


# ── Public read helpers (route handlers + repositories use these) ───────

def get_request_context() -> Optional[RequestContext]:
    """Return the RequestContext that the Phase 2 decorators stashed,
    or None if the current request was not authenticated via Keycloak.

    Safe to call outside a Flask request context (returns None) -- so
    background jobs and startup hooks that may use the same DB helpers
    don't crash on `g` access."""
    if not has_request_context():
        return None
    return getattr(g, "kc_ctx", None)


def current_tenant_id() -> Optional[str]:
    """Return the validated tenant_id from the JWT, or None if absent.

    Routes that MUST have a tenant should call `require_tenant_context()`
    instead — that one returns a 403 to the caller on absence.
    """
    ctx = get_request_context()
    return ctx.tenant_id if ctx else None


def current_user_sub() -> Optional[str]:
    """Return the JWT `sub` claim of the caller, or None.

    For service accounts this is the SA's internal user id (Keycloak
    auto-creates a `service-account-<client_id>` user behind every
    confidential client with `serviceAccountsEnabled=true`)."""
    ctx = get_request_context()
    return ctx.user_id if ctx else None


def current_user_is_service_account() -> bool:
    ctx = get_request_context()
    return bool(ctx and ctx.is_service_account)


# ── Hard gate: routes that must have a tenant context ───────────────────

class MissingTenantContextError(RuntimeError):
    """Raised when a tenant-scoped resource is requested but no
    tenant_id claim is on the JWT. The Flask error handler turns this
    into a 403 MISSING_TENANT_CONTEXT response (matches plan §8.4)."""


def require_tenant_context() -> str:
    """For routes that absolutely require a tenant claim on the JWT.

    Returns the tenant_id (so callers can use it inline). Raises
    MissingTenantContextError when:
      - Keycloak is on and the JWT has no tenant_id claim, OR
      - Keycloak is on and there's no JWT at all (the decorator layer
        should have caught this earlier — belt-and-braces here).

    Returns "" silently when Keycloak is OFF — the legacy auth still
    enforces user_id-based isolation in that case.
    """
    if not _keycloak_enabled():
        return ""
    tid = current_tenant_id()
    if not tid:
        raise MissingTenantContextError(
            "No tenant_id claim on the JWT for this request."
        )
    return tid


# ── Postgres GUC bridge ─────────────────────────────────────────────────

def _is_postgres_connection(conn) -> bool:
    """True iff the conn is SolarPro's psycopg2 wrapper.

    SQLite connections are sqlite3.Connection; their type name is
    `Connection` and they are NOT in the db_adapter module. The
    wrapper class is `_PgConnAdapter` in db_adapter.py."""
    try:
        return type(conn).__name__ == "_PgConnAdapter"
    except Exception:
        return False


def apply_tenant_guc(conn) -> bool:
    """Set `app.current_tenant` + `app.current_user` GUCs on `conn`
    for the duration of the current Postgres transaction.

    No-ops cleanly when:
      - the connection is SQLite (RLS doesn't exist there),
      - Keycloak is disabled (parallel-run),
      - or there's no JWT context (anonymous routes).

    Returns True if the GUCs were actually written, False otherwise.
    Use the return value if you need to know whether RLS will be
    enforced for the rest of this transaction.

    The third arg to `set_config` is `is_local` — true means the value
    is scoped to the current transaction, which is safer than session
    scope under connection pooling.
    """
    if not _keycloak_enabled():
        return False
    if not _is_postgres_connection(conn):
        return False
    if not has_request_context():
        # init_db, background jobs, CLI scripts -- no request, no
        # tenant. RLS policy's parallel-run NULL escape covers reads.
        return False

    tenant_id = current_tenant_id()
    user_sub = current_user_sub()

    # Empty string is a valid GUC value — Postgres treats it as "unset"
    # and `current_tenant_id()` in SQL returns NULL, so RLS denies.
    tenant_value = tenant_id or ""
    user_value = user_sub or ""

    try:
        # set_config returns the value set; we don't read it back.
        conn.execute(
            "SELECT set_config('app.current_tenant', ?, true)",
            (tenant_value,),
        )
        conn.execute(
            "SELECT set_config('app.current_user', ?, true)",
            (user_value,),
        )
    except Exception as e:
        # GUC write failure is a hard error — without it RLS won't know
        # who's calling. Log loud and propagate so the request 500s
        # rather than silently bypassing isolation.
        log.error("Failed to apply tenant GUC: %s", e)
        raise

    return True


def clear_tenant_guc(conn) -> None:
    """Reset the GUCs on `conn`. Useful for connection pools — call in
    teardown_request when the connection will be returned to a pool.

    Today's db_adapter opens fresh connections per request so this is
    a no-op in practice, but a forward-compatibility hook is cheap."""
    if not _is_postgres_connection(conn):
        return
    try:
        conn.execute("SELECT set_config('app.current_tenant', '', true)")
        conn.execute("SELECT set_config('app.current_user', '', true)")
    except Exception as e:
        log.warning("Failed to clear tenant GUC (non-fatal): %s", e)


# ── Flask error handler ─────────────────────────────────────────────────

def register_error_handler(app) -> None:
    """Wire MissingTenantContextError to a 403 JSON response.

    Idempotent: calling twice on the same Flask app just re-registers
    the same handler.
    """
    @app.errorhandler(MissingTenantContextError)
    def _handle_missing_tenant(e):  # pragma: no cover (Flask wires this)
        log.warning(
            "MISSING_TENANT_CONTEXT on %s %s from %s",
            request.method, request.path, request.remote_addr,
        )
        return jsonify(error="MISSING_TENANT_CONTEXT", reason=str(e)), 403


__all__ = [
    "MissingTenantContextError",
    "apply_tenant_guc",
    "clear_tenant_guc",
    "current_tenant_id",
    "current_user_is_service_account",
    "current_user_sub",
    "get_request_context",
    "register_error_handler",
    "require_tenant_context",
]
