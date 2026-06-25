"""
Flask decorators for Keycloak-protected routes.

Phase 2 of docs/SECURITY_MIGRATION_KEYCLOAK.md. These decorators wrap
`app.security.keycloak_middleware.verify_jwt()` and stash the resulting
RequestContext on Flask's `g` so route handlers can read it via
`get_request_context()`.

The decorators are designed to compose:

    @app.route("/admin/marketplace")
    @require_role("marketplace_admin")
    @require_scope("supplier:approve")
    def admin_marketplace():
        ctx = get_request_context()
        ...

Each decorator implies @require_jwt (you don't need to add it
explicitly). They all short-circuit on the first failure with the
appropriate HTTP code:

    no token              -> 401 MISSING_BEARER
    bad JWT               -> 401 INVALID_JWT
    wrong role            -> 403 FORBIDDEN_ROLE
    wrong scope           -> 403 FORBIDDEN_SCOPE
    tenant mismatch       -> 403 TENANT_MISMATCH

KEYCLOAK_ENABLED env feature flag (RETIRED 2026-06-25 — SOC 2 M1.1):
    Keycloak is now the only authentication path. _keycloak_enabled()
    is hard-wired to True so every decorator enforces JWT + role + tenant
    on every request. The env var is ignored.
"""

from __future__ import annotations

import os
from functools import wraps
from typing import Iterable, Callable

from flask import request, jsonify, g, current_app

from .keycloak_middleware import (
    verify_jwt,
    extract_request_context,
    RequestContext,
    JWTError,
)


KEYCLOAK_ENABLED_ENV = "KEYCLOAK_ENABLED"  # retired flag, kept for back-compat imports


def _keycloak_enabled() -> bool:
    """Retired 2026-06-25 (SOC 2 M1.1). Keycloak is now mandatory; this
    helper always returns True so every decorator enforces auth on every
    request. The env var is no longer consulted."""
    return True


def get_request_context() -> RequestContext | None:
    """Return the RequestContext stashed by require_jwt, or None if the
    current request hasn't been authenticated via Keycloak. Route handlers
    should treat None as "fallback to old auth"."""
    return getattr(g, "kc_ctx", None)


def _audit_denial(reason: str, **extra) -> None:
    """Best-effort audit log of a permission denial.

    Phase 6 wires this into TWO sinks:
      1) structured logger (file + Loki) -- for live ops dashboards.
      2) audit_logs table via app.security.audit.write_audit_event --
         so the long-tail review surface (admin UI + compliance reports)
         sees denials alongside everything else.

    Either sink can fail without raising; the request is not blocked.
    """
    ctx = getattr(g, "kc_ctx", None)
    payload = {
        "action": "PERMISSION_DENIED",
        "reason": reason,
        "path": request.path,
        "method": request.method,
        "ip": request.remote_addr,
        "user_id": ctx and ctx.user_id,
        "tenant_id": ctx and ctx.tenant_id,
        "agent_id": ctx and ctx.azp,
        **extra,
    }
    try:
        from logging_config.structured_logger import audit  # type: ignore
        audit(**payload)
    except Exception:
        try:
            current_app.logger.warning("PERMISSION_DENIED %s", payload)
        except Exception:
            pass

    # Phase 6 audit unification -- write the denial to audit_logs so
    # it shows up alongside admin actions in the live ops dashboard.
    try:
        from app.security.audit import audit_permission_denied
        audit_permission_denied(
            payload["path"],
            reason=reason,
            user_id=None,  # JWT sub is a UUID, not the int user_id
            ip=payload["ip"] or "",
            tenant_id=payload["tenant_id"] or None,
            agent_id=payload["agent_id"] or None,
            extra={k: v for k, v in extra.items() if k != "path"} or None,
        )
    except Exception:
        # Audit writer is itself non-raising, but just in case import
        # ordering during very early startup throws.
        pass


def _extract_bearer(header_value: str) -> str | None:
    if not header_value:
        return None
    parts = header_value.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


# ── require_jwt ──────────────────────────────────────────────────────────

def require_jwt(view: Callable | None = None, *, audience: str | None = None):
    """Decorator: require a valid Keycloak JWT. Stashes the RequestContext
    on Flask's `g` as `g.kc_ctx`.

    Supports @require_jwt and @require_jwt(audience="...") forms.
    """
    def decorator(view: Callable):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not _keycloak_enabled():
                # Parallel-run: pass through so the old auth stack handles it.
                return view(*args, **kwargs)

            token = _extract_bearer(request.headers.get("Authorization", ""))
            if not token:
                _audit_denial("missing_bearer")
                return jsonify(error="MISSING_BEARER"), 401
            try:
                claims = verify_jwt(token, audience=audience)
            except JWTError as e:
                _audit_denial("invalid_jwt", detail=str(e))
                return jsonify(error="INVALID_JWT", reason=str(e)), 401

            g.kc_ctx = extract_request_context(claims)
            return view(*args, **kwargs)
        return wrapper

    if view is None:
        return decorator
    return decorator(view)


# ── require_role / require_any_role ──────────────────────────────────────

def require_role(role_name: str, *, audience: str | None = None):
    """Decorator: caller must have `role_name` in their realm roles.
    Implies @require_jwt."""
    def decorator(view: Callable):
        @require_jwt(audience=audience)
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not _keycloak_enabled():
                return view(*args, **kwargs)
            ctx: RequestContext = g.kc_ctx
            if not ctx.has_role(role_name):
                _audit_denial("forbidden_role", required=role_name, actual=list(ctx.roles))
                return jsonify(error="FORBIDDEN_ROLE", required=role_name), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator


def require_any_role(role_names: Iterable[str], *, audience: str | None = None):
    """Decorator: caller must have AT LEAST ONE of `role_names`. Useful for
    "platform_super_admin OR tenant_admin" style checks."""
    wanted = tuple(role_names)
    def decorator(view: Callable):
        @require_jwt(audience=audience)
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not _keycloak_enabled():
                return view(*args, **kwargs)
            ctx: RequestContext = g.kc_ctx
            if not ctx.has_any_role(wanted):
                _audit_denial("forbidden_role", required=list(wanted), actual=list(ctx.roles))
                return jsonify(error="FORBIDDEN_ROLE", required=list(wanted)), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator


def require_all_roles(role_names: Iterable[str], *, audience: str | None = None):
    """Decorator: caller must have ALL of `role_names`. Rare but useful for
    composite-role enforcement where the realm role is missing."""
    wanted = tuple(role_names)
    def decorator(view: Callable):
        @require_jwt(audience=audience)
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not _keycloak_enabled():
                return view(*args, **kwargs)
            ctx: RequestContext = g.kc_ctx
            if not ctx.has_all_roles(wanted):
                _audit_denial("forbidden_role", required=list(wanted), actual=list(ctx.roles))
                return jsonify(error="FORBIDDEN_ROLE", required=list(wanted)), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator


# ── require_scope ────────────────────────────────────────────────────────

def require_scope(scope_name: str, *, audience: str | None = None):
    """Decorator: caller's JWT scope must include `scope_name`. Per
    plan §7.4's 27 permission scopes."""
    def decorator(view: Callable):
        @require_jwt(audience=audience)
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not _keycloak_enabled():
                return view(*args, **kwargs)
            ctx: RequestContext = g.kc_ctx
            if not ctx.has_scope(scope_name):
                _audit_denial("forbidden_scope", required=scope_name, actual=list(ctx.scopes))
                return jsonify(error="FORBIDDEN_SCOPE", required=scope_name), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator


# ── require_tenant_match ─────────────────────────────────────────────────

def require_tenant_match(path_param: str, *, audience: str | None = None):
    """Decorator: the URL path param named `path_param` must equal the
    caller's JWT tenant_id claim. Critical for multi-tenant safety
    (per plan §10 step 7).

    Bypasses the check for platform_super_admin (their token can cross
    tenants by design).
    """
    def decorator(view: Callable):
        @require_jwt(audience=audience)
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not _keycloak_enabled():
                return view(*args, **kwargs)
            ctx: RequestContext = g.kc_ctx
            if ctx.has_role("platform_super_admin"):
                return view(*args, **kwargs)
            url_tenant = kwargs.get(path_param)
            if not ctx.tenant_id:
                _audit_denial("missing_tenant_context", path_param=path_param)
                return jsonify(error="MISSING_TENANT_CONTEXT"), 403
            if str(url_tenant) != str(ctx.tenant_id):
                _audit_denial(
                    "tenant_mismatch",
                    path_param=path_param,
                    url_tenant=str(url_tenant),
                    jwt_tenant=str(ctx.tenant_id),
                )
                return jsonify(error="TENANT_MISMATCH"), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator


# ── require_service_account ──────────────────────────────────────────────

def require_service_account(client_id: str | None = None, *, audience: str | None = None):
    """Decorator: caller must be an AI-agent service account (client
    credentials grant), optionally restricted to a specific client_id.
    Used by internal agent-only routes (e.g. POST /api/agents/internal/*).
    """
    def decorator(view: Callable):
        @require_jwt(audience=audience)
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not _keycloak_enabled():
                return view(*args, **kwargs)
            ctx: RequestContext = g.kc_ctx
            if not ctx.is_service_account:
                _audit_denial("not_service_account", azp=ctx.azp)
                return jsonify(error="NOT_SERVICE_ACCOUNT"), 403
            if client_id and ctx.azp != client_id:
                _audit_denial("wrong_service_account", required=client_id, actual=ctx.azp)
                return jsonify(error="WRONG_SERVICE_ACCOUNT", required=client_id), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator


__all__ = [
    "require_jwt",
    "require_role",
    "require_any_role",
    "require_all_roles",
    "require_scope",
    "require_tenant_match",
    "require_service_account",
    "get_request_context",
]
