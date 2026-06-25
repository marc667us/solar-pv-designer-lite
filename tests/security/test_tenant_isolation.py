"""
Unit tests for app.security.tenant_context.

Phase 4 deliverable per docs/SECURITY_MIGRATION_KEYCLOAK.md §19 task 22.

These tests cover the tenant_context module's behaviour in isolation:
  * Reading tenant_id / user_sub off the JWT (via g.kc_ctx).
  * Parallel-run short-circuit when KEYCLOAK_ENABLED is unset.
  * MissingTenantContextError raised for routes that require a tenant.
  * Postgres GUC writes via a stubbed _PgConnAdapter.
  * No-op on SQLite-shaped connections.

The full DB-RLS acceptance cases from plan §8.4 (cross-tenant 404 over
the wire, cross-FK 404, SA without tenant_id 403, immutable attribute
403) require a running Postgres with `migrations/003_rls_tenant.sql`
applied. Those are exercised by the integration suite that runs after
`bash scripts/keycloak/bootstrap.sh` -- see the comment at the bottom
of this file for the runbook.
"""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from flask import Flask, g

from app.security import tenant_context as tc
from app.security.keycloak_middleware import RequestContext


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_ctx(
    *,
    tenant_id: str | None = "11111111-1111-1111-1111-111111111111",
    user_id: str = "user-sub-1",
    is_service_account: bool = False,
    azp: str | None = None,
) -> RequestContext:
    """Build a synthetic RequestContext for the test app's `g.kc_ctx`."""
    return RequestContext(
        user_id=user_id,
        tenant_id=tenant_id,
        tenant_name=None,
        user_type=None,
        roles=(),
        scopes=(),
        supplier_id=None,
        engineering_company_id=None,
        marketplace_scope=(),
        subscription_plan=None,
        country=None,
        region=None,
        is_service_account=is_service_account,
        preferred_username=None,
        email=None,
        azp=azp,
        raw_claims={},
    )


@pytest.fixture
def flask_app():
    app = Flask(__name__)
    tc.register_error_handler(app)

    @app.route("/needs-tenant")
    def needs_tenant():
        tid = tc.require_tenant_context()
        return {"tenant_id": tid}

    @app.route("/peek")
    def peek():
        return {
            "tenant_id": tc.current_tenant_id(),
            "user_sub": tc.current_user_sub(),
            "is_sa": tc.current_user_is_service_account(),
        }
    return app


# ── Read helpers (no GUC, no Postgres) ───────────────────────────────────

def test_current_tenant_id_returns_none_without_ctx(flask_app):
    with flask_app.test_request_context("/peek"):
        assert tc.current_tenant_id() is None
        assert tc.current_user_sub() is None
        assert tc.current_user_is_service_account() is False


def test_current_tenant_id_reads_from_kc_ctx(flask_app):
    with flask_app.test_request_context("/peek"):
        g.kc_ctx = _make_ctx(tenant_id="abc-1", user_id="bob")
        assert tc.current_tenant_id() == "abc-1"
        assert tc.current_user_sub() == "bob"


def test_current_user_is_service_account_reads_ctx(flask_app):
    with flask_app.test_request_context("/peek"):
        g.kc_ctx = _make_ctx(is_service_account=True,
                             azp="solarpro-catalogue-agent")
        assert tc.current_user_is_service_account() is True


# ── require_tenant_context: parallel-run short-circuit ──────────────────

def test_require_tenant_enforces_even_with_env_unset(monkeypatch, flask_app):
    """SOC 2 M1.1 (2026-06-25): KEYCLOAK_ENABLED is retired. Tenant
    isolation must be enforced regardless of the env var -- the
    legacy "returns empty string when KC off" path is gone."""
    monkeypatch.delenv("KEYCLOAK_ENABLED", raising=False)
    with flask_app.test_request_context("/needs-tenant"):
        with pytest.raises(tc.MissingTenantContextError):
            tc.require_tenant_context()


def test_require_tenant_returns_id_when_present(monkeypatch, flask_app):
    monkeypatch.setenv("KEYCLOAK_ENABLED", "true")
    with flask_app.test_request_context("/needs-tenant"):
        g.kc_ctx = _make_ctx(tenant_id="tid-1")
        assert tc.require_tenant_context() == "tid-1"


def test_require_tenant_raises_when_kc_enabled_and_missing(monkeypatch, flask_app):
    monkeypatch.setenv("KEYCLOAK_ENABLED", "true")
    with flask_app.test_request_context("/needs-tenant"):
        g.kc_ctx = _make_ctx(tenant_id=None)
        with pytest.raises(tc.MissingTenantContextError):
            tc.require_tenant_context()


def test_require_tenant_raises_when_kc_enabled_and_no_ctx(monkeypatch, flask_app):
    monkeypatch.setenv("KEYCLOAK_ENABLED", "true")
    with flask_app.test_request_context("/needs-tenant"):
        with pytest.raises(tc.MissingTenantContextError):
            tc.require_tenant_context()


# ── Flask error-handler: route returns 403 MISSING_TENANT_CONTEXT ──────

def test_missing_tenant_error_handler_returns_403(monkeypatch, flask_app):
    monkeypatch.setenv("KEYCLOAK_ENABLED", "true")

    @flask_app.before_request
    def _no_ctx():
        # Simulate require_jwt having let a tokenless / claim-less
        # request through (e.g. service-account JWT without tenant_id).
        pass

    with flask_app.test_client() as c:
        r = c.get("/needs-tenant")
        assert r.status_code == 403
        body = r.get_json()
        assert body["error"] == "MISSING_TENANT_CONTEXT"


def test_route_returns_tenant_id_when_present(monkeypatch, flask_app):
    monkeypatch.setenv("KEYCLOAK_ENABLED", "true")

    @flask_app.before_request
    def _seed_ctx():
        g.kc_ctx = _make_ctx(tenant_id="abcde")

    with flask_app.test_client() as c:
        r = c.get("/needs-tenant")
        assert r.status_code == 200
        assert r.get_json()["tenant_id"] == "abcde"


# ── Postgres GUC bridge ─────────────────────────────────────────────────

class _FakePgConn:
    """Mimics db_adapter._PgConnAdapter just enough for apply_tenant_guc.

    The real adapter exposes .execute(sql, params); we record every call
    so the test can assert the right `set_config(...)` payloads were
    issued, in the right order.
    """
    __name__ = "_PgConnAdapter"  # only used for the type-name check
    def __init__(self):
        self.calls = []
    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return MagicMock()


# Match the class name detection in apply_tenant_guc.
_FakePgConn.__qualname__ = "_PgConnAdapter"
_FakePgConn.__name__ = "_PgConnAdapter"


def test_apply_tenant_guc_writes_two_set_configs(monkeypatch, flask_app):
    monkeypatch.setenv("KEYCLOAK_ENABLED", "true")
    conn = _FakePgConn()
    with flask_app.test_request_context("/peek"):
        g.kc_ctx = _make_ctx(tenant_id="t-99", user_id="u-99")
        assert tc.apply_tenant_guc(conn) is True
    assert len(conn.calls) == 2
    assert "app.current_tenant" in conn.calls[0][0]
    assert conn.calls[0][1] == ("t-99",)
    assert "app.current_user" in conn.calls[1][0]
    assert conn.calls[1][1] == ("u-99",)


def test_apply_tenant_guc_runs_even_with_env_unset(monkeypatch, flask_app):
    """SOC 2 M1.1 (2026-06-25): with the env flag retired, apply_tenant_guc
    must still set the GUCs whenever a request ctx carries a tenant_id."""
    monkeypatch.delenv("KEYCLOAK_ENABLED", raising=False)
    conn = _FakePgConn()
    with flask_app.test_request_context("/peek"):
        g.kc_ctx = _make_ctx(tenant_id="t-99", user_id="u-99")
        assert tc.apply_tenant_guc(conn) is True
    assert len(conn.calls) == 2


# ── SOC 2 M1.7 -- request-hook observability ────────────────────────────

def test_is_tenant_scoped_path_classifier():
    """The path-prefix classifier must pull /admin, /api/admin, etc. into
    the tenant-scoped bucket and leave public paths out."""
    assert tc.is_tenant_scoped_path("/admin/users") is True
    assert tc.is_tenant_scoped_path("/admin") is True
    assert tc.is_tenant_scoped_path("/api/admin/foo") is True
    assert tc.is_tenant_scoped_path("/api/errors/recent") is True
    assert tc.is_tenant_scoped_path("/boq-projects/123") is True
    assert tc.is_tenant_scoped_path("/dashboard") is True
    # Public surfaces:
    assert tc.is_tenant_scoped_path("/") is False
    assert tc.is_tenant_scoped_path("/api/ping") is False
    assert tc.is_tenant_scoped_path("/marketplace") is False
    assert tc.is_tenant_scoped_path("/login") is False
    # Documented exception:
    assert tc.is_tenant_scoped_path("/api/admin/health") is False


def test_register_tenant_request_hooks_tags_g():
    """Hook must populate g.tenant_scoped + g.tenant_ctx_present on every
    request without raising, and remain idempotent on double-registration."""
    from flask import Flask, g, jsonify
    app = Flask(__name__)
    app.secret_key = "test"
    tc.register_tenant_request_hooks(app)
    # Idempotency
    tc.register_tenant_request_hooks(app)

    @app.route("/admin/anything")
    def _stub():
        return jsonify(
            tenant_scoped=g.tenant_scoped,
            tenant_ctx_present=g.tenant_ctx_present,
        )

    @app.route("/api/ping")
    def _public():
        return jsonify(
            tenant_scoped=g.tenant_scoped,
            tenant_ctx_present=g.tenant_ctx_present,
        )

    with app.test_client() as c:
        r = c.get("/admin/anything")
        assert r.status_code == 200
        body = r.get_json()
        assert body["tenant_scoped"] is True
        assert body["tenant_ctx_present"] is False

        r2 = c.get("/api/ping")
        body2 = r2.get_json()
        assert body2["tenant_scoped"] is False
        assert body2["tenant_ctx_present"] is False


def test_apply_tenant_guc_noop_on_sqlite_shaped_conn(monkeypatch, flask_app):
    monkeypatch.setenv("KEYCLOAK_ENABLED", "true")
    sqlite_like = MagicMock()
    type(sqlite_like).__name__ = "Connection"  # sqlite3 style
    with flask_app.test_request_context("/peek"):
        g.kc_ctx = _make_ctx(tenant_id="t-99")
        assert tc.apply_tenant_guc(sqlite_like) is False
    sqlite_like.execute.assert_not_called()


def test_apply_tenant_guc_sends_empty_string_when_tenant_missing(monkeypatch, flask_app):
    """Service accounts may legitimately have no tenant_id; the GUC is
    written as empty string so RLS denies cross-tenant access without
    crashing the request."""
    monkeypatch.setenv("KEYCLOAK_ENABLED", "true")
    conn = _FakePgConn()
    with flask_app.test_request_context("/peek"):
        g.kc_ctx = _make_ctx(tenant_id=None, user_id="u-9")
        tc.apply_tenant_guc(conn)
    assert conn.calls[0][1] == ("",)        # tenant_id missing -> ''
    assert conn.calls[1][1] == ("u-9",)


def test_apply_tenant_guc_propagates_db_error(monkeypatch, flask_app):
    """If Postgres refuses set_config we want a hard 5xx, not a silent
    bypass of RLS for the rest of the request."""
    monkeypatch.setenv("KEYCLOAK_ENABLED", "true")
    class _Boom(_FakePgConn):
        def execute(self, sql, params=()):
            raise RuntimeError("connection reset")
    # Subclasses don't inherit the patched __name__; apply_tenant_guc
    # uses type(conn).__name__ to detect Postgres, so the boom conn
    # needs the same name for the test to exercise the error path.
    _Boom.__name__ = "_PgConnAdapter"
    with flask_app.test_request_context("/peek"):
        g.kc_ctx = _make_ctx(tenant_id="t-99")
        with pytest.raises(RuntimeError):
            tc.apply_tenant_guc(_Boom())


def test_clear_tenant_guc_resets_both(monkeypatch, flask_app):
    monkeypatch.setenv("KEYCLOAK_ENABLED", "true")
    conn = _FakePgConn()
    with flask_app.test_request_context("/peek"):
        tc.clear_tenant_guc(conn)
    assert len(conn.calls) == 2
    assert conn.calls[0][0].endswith("set_config('app.current_tenant', '', true)")
    assert conn.calls[1][0].endswith("set_config('app.current_user', '', true)")


def test_clear_tenant_guc_noop_on_sqlite():
    """Clear is a forward-compat hook; on SQLite it must not raise."""
    sqlite_like = MagicMock()
    type(sqlite_like).__name__ = "Connection"
    tc.clear_tenant_guc(sqlite_like)
    sqlite_like.execute.assert_not_called()


def test_get_request_context_returns_g_value(flask_app):
    with flask_app.test_request_context("/peek"):
        assert tc.get_request_context() is None
        ctx = _make_ctx(tenant_id="seed")
        g.kc_ctx = ctx
        assert tc.get_request_context() is ctx


# ── Documentation: full DB-RLS acceptance tests ─────────────────────────

# The four plan §8.4 acceptance cases require a running Postgres with
# migrations/003_rls_tenant.sql applied. Runbook (once Phase 1 bootstrap
# is up locally):
#
#   1. bash scripts/keycloak/bootstrap.sh
#   2. psql $DATABASE_URL -f migrations/003_rls_tenant.sql
#   3. Set KEYCLOAK_ENABLED=true and seed two tenants' worth of data.
#   4. From a token-A session, GET /projects/<row_owned_by_B>
#         -> expect 404 (RLS hides the row).
#   5. From a token-A session, GET /projects/<A_row>/reports/<B_report>
#         -> expect 404 (cross-FK leak prevented).
#   6. From an SA token with no tenant_id claim, GET /projects
#         -> expect 403 MISSING_TENANT_CONTEXT.
#   7. From a non-super-admin user, PATCH /me {"tenant_id": "..."}
#         -> expect 403 IMMUTABLE_ATTRIBUTE (Phase 5 route; Phase 4
#         leaves the test as a placeholder).
#
# When the bootstrap runs in CI, those four assertions land in
# `tests/security/test_tenant_isolation_live.py` so they only execute
# when a `PG_TEST_URL` env var is present.
