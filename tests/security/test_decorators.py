"""
Unit tests for app.security.decorators.

Phase 2 deliverable per docs/SECURITY_MIGRATION_KEYCLOAK.md §19 task 12.

Uses a minimal Flask app + mocked verify_jwt to exercise each decorator
without needing a running Keycloak. Covers:

- KEYCLOAK_ENABLED feature-flag pass-through.
- require_jwt: missing token, invalid token, valid token.
- require_role: forbidden, allowed.
- require_any_role: any-of semantics.
- require_all_roles: all-of semantics.
- require_scope: forbidden, allowed.
- require_tenant_match: mismatch denied; platform_super_admin bypass; missing context.
- require_service_account: human denied; correct SA allowed; wrong SA denied.
"""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import pytest
from flask import Flask, jsonify

from app.security import decorators as deco
from app.security.keycloak_middleware import RequestContext


# ── Test-app builder ─────────────────────────────────────────────────────

def _make_app() -> Flask:
    app = Flask(__name__)

    @app.route("/protected/jwt")
    @deco.require_jwt
    def protected_jwt():
        ctx = deco.get_request_context()
        return jsonify(sub=ctx.user_id, tenant=ctx.tenant_id)

    @app.route("/protected/role")
    @deco.require_role("marketplace_admin")
    def protected_role():
        return jsonify(ok=True)

    @app.route("/protected/any-role")
    @deco.require_any_role(["marketplace_admin", "tenant_admin"])
    def protected_any_role():
        return jsonify(ok=True)

    @app.route("/protected/all-roles")
    @deco.require_all_roles(["solar_engineer", "estimator"])
    def protected_all_roles():
        return jsonify(ok=True)

    @app.route("/protected/scope")
    @deco.require_scope("supplier:approve")
    def protected_scope():
        return jsonify(ok=True)

    @app.route("/tenants/<tenant_id>/projects")
    @deco.require_tenant_match("tenant_id")
    def protected_tenant(tenant_id):
        return jsonify(tenant=tenant_id)

    @app.route("/internal/agent")
    @deco.require_service_account("solarpro-catalogue-agent")
    def protected_service_account():
        return jsonify(ok=True)

    return app


def _ctx(**overrides) -> RequestContext:
    """Build a RequestContext for tests, with defaults for an engineer
    user that can be overridden per case."""
    defaults = dict(
        user_id="user-uuid-engineer",
        tenant_id="tenant-a",
        tenant_name="Demo Engineering Firm",
        user_type="engineer",
        roles=("solar_engineer",),
        scopes=("project:view", "design:create"),
        supplier_id=None,
        engineering_company_id="tenant-a",
        marketplace_scope=tuple(),
        subscription_plan="pro",
        country="GH",
        region="Greater Accra",
        is_service_account=False,
        preferred_username="engineer_test",
        email="engineer@test.solarpro.local",
        azp="solarpro-web",
        raw_claims={},
    )
    defaults.update(overrides)
    return RequestContext(**defaults)


@pytest.fixture
def app():
    return _make_app()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def enable_keycloak(monkeypatch):
    """Flip the KEYCLOAK_ENABLED feature flag on for the test."""
    monkeypatch.setenv("KEYCLOAK_ENABLED", "true")


def _stub_verify(monkeypatch, claims: dict):
    """Replace verify_jwt with a stub that returns `claims`."""
    monkeypatch.setattr(
        "app.security.decorators.verify_jwt",
        lambda token, audience=None: claims,
    )


# ── Feature-flag pass-through (the parallel-run model) ───────────────────

def test_feature_flag_off_passes_through(client):
    """With KEYCLOAK_ENABLED unset, decorators don't reject -- they let
    the old @login_required / @admin_required stack handle it."""
    resp = client.get("/protected/role")  # no Authorization header
    assert resp.status_code == 200  # the view ran -- pass-through


# ── require_jwt ──────────────────────────────────────────────────────────

def test_require_jwt_missing_bearer(client, enable_keycloak):
    resp = client.get("/protected/jwt")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "MISSING_BEARER"


def test_require_jwt_invalid_token(client, enable_keycloak, monkeypatch):
    from jose import JWTError
    monkeypatch.setattr(
        "app.security.decorators.verify_jwt",
        lambda token, audience=None: (_ for _ in ()).throw(JWTError("bad sig")),
    )
    resp = client.get("/protected/jwt", headers={"Authorization": "Bearer bad-token"})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "INVALID_JWT"


def test_require_jwt_happy_path(client, enable_keycloak, monkeypatch):
    _stub_verify(monkeypatch, {
        "sub": "user-uuid-engineer", "tenant_id": "tenant-a",
        "realm_access": {"roles": ["solar_engineer"]},
        "scope": "project:view", "azp": "solarpro-web",
        "preferred_username": "engineer_test",
    })
    resp = client.get("/protected/jwt", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["sub"] == "user-uuid-engineer"
    assert body["tenant"] == "tenant-a"


# ── require_role ─────────────────────────────────────────────────────────

def test_require_role_forbidden(client, enable_keycloak, monkeypatch):
    _stub_verify(monkeypatch, {
        "sub": "u", "tenant_id": "tenant-a",
        "realm_access": {"roles": ["solar_engineer"]},  # NOT marketplace_admin
        "scope": "", "azp": "solarpro-web",
    })
    resp = client.get("/protected/role", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN_ROLE"
    assert resp.get_json()["required"] == "marketplace_admin"


def test_require_role_allowed(client, enable_keycloak, monkeypatch):
    _stub_verify(monkeypatch, {
        "sub": "u", "tenant_id": "tenant-a",
        "realm_access": {"roles": ["marketplace_admin"]},
        "scope": "", "azp": "solarpro-web",
    })
    resp = client.get("/protected/role", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200


# ── require_any_role / require_all_roles ─────────────────────────────────

def test_require_any_role_allows_intersection(client, enable_keycloak, monkeypatch):
    _stub_verify(monkeypatch, {
        "sub": "u", "tenant_id": "tenant-a",
        "realm_access": {"roles": ["tenant_admin"]},
        "scope": "", "azp": "solarpro-web",
    })
    resp = client.get("/protected/any-role", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200


def test_require_any_role_denies_when_empty(client, enable_keycloak, monkeypatch):
    _stub_verify(monkeypatch, {
        "sub": "u", "tenant_id": "tenant-a",
        "realm_access": {"roles": ["customer"]},
        "scope": "", "azp": "solarpro-web",
    })
    resp = client.get("/protected/any-role", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 403


def test_require_all_roles_requires_intersection(client, enable_keycloak, monkeypatch):
    _stub_verify(monkeypatch, {
        "sub": "u", "tenant_id": "tenant-a",
        "realm_access": {"roles": ["solar_engineer"]},  # missing estimator
        "scope": "", "azp": "solarpro-web",
    })
    resp = client.get("/protected/all-roles", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 403


def test_require_all_roles_happy_path(client, enable_keycloak, monkeypatch):
    _stub_verify(monkeypatch, {
        "sub": "u", "tenant_id": "tenant-a",
        "realm_access": {"roles": ["solar_engineer", "estimator"]},
        "scope": "", "azp": "solarpro-web",
    })
    resp = client.get("/protected/all-roles", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200


# ── require_scope ────────────────────────────────────────────────────────

def test_require_scope_forbidden(client, enable_keycloak, monkeypatch):
    _stub_verify(monkeypatch, {
        "sub": "u", "tenant_id": "tenant-a",
        "realm_access": {"roles": ["supplier_admin"]},
        "scope": "supplier:view",  # NOT supplier:approve
        "azp": "solarpro-web",
    })
    resp = client.get("/protected/scope", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN_SCOPE"


def test_require_scope_allowed(client, enable_keycloak, monkeypatch):
    _stub_verify(monkeypatch, {
        "sub": "u", "tenant_id": "tenant-a",
        "realm_access": {"roles": ["marketplace_admin"]},
        "scope": "supplier:approve supplier:suspend",
        "azp": "solarpro-web",
    })
    resp = client.get("/protected/scope", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200


# ── require_tenant_match ─────────────────────────────────────────────────

def test_tenant_mismatch_denied(client, enable_keycloak, monkeypatch):
    _stub_verify(monkeypatch, {
        "sub": "u", "tenant_id": "tenant-a",
        "realm_access": {"roles": ["solar_engineer"]},
        "scope": "", "azp": "solarpro-web",
    })
    resp = client.get("/tenants/tenant-b/projects",
                      headers={"Authorization": "Bearer x"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "TENANT_MISMATCH"


def test_tenant_match_allowed(client, enable_keycloak, monkeypatch):
    _stub_verify(monkeypatch, {
        "sub": "u", "tenant_id": "tenant-a",
        "realm_access": {"roles": ["solar_engineer"]},
        "scope": "", "azp": "solarpro-web",
    })
    resp = client.get("/tenants/tenant-a/projects",
                      headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200


def test_platform_super_admin_bypasses_tenant(client, enable_keycloak, monkeypatch):
    _stub_verify(monkeypatch, {
        "sub": "u", "tenant_id": "tenant-platform",
        "realm_access": {"roles": ["platform_super_admin"]},
        "scope": "", "azp": "solarpro-web",
    })
    resp = client.get("/tenants/any-other-tenant/projects",
                      headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200


def test_missing_tenant_claim_denied(client, enable_keycloak, monkeypatch):
    _stub_verify(monkeypatch, {
        "sub": "u",  # no tenant_id at all
        "realm_access": {"roles": ["solar_engineer"]},
        "scope": "", "azp": "solarpro-web",
    })
    resp = client.get("/tenants/anywhere/projects",
                      headers={"Authorization": "Bearer x"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "MISSING_TENANT_CONTEXT"


# ── require_service_account ──────────────────────────────────────────────

def test_human_denied_on_service_account_route(client, enable_keycloak, monkeypatch):
    _stub_verify(monkeypatch, {
        "sub": "u", "tenant_id": "tenant-a",
        "realm_access": {"roles": ["solar_engineer"]},
        "scope": "", "azp": "solarpro-web",
        "preferred_username": "engineer_test",
    })
    resp = client.get("/internal/agent", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "NOT_SERVICE_ACCOUNT"


def test_correct_service_account_allowed(client, enable_keycloak, monkeypatch):
    _stub_verify(monkeypatch, {
        "sub": "u", "tenant_id": "tenant-a",
        "realm_access": {"roles": ["api_service_account"]},
        "scope": "", "azp": "solarpro-catalogue-agent",
        "preferred_username": "service-account-solarpro-catalogue-agent",
    })
    resp = client.get("/internal/agent", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200


def test_wrong_service_account_denied(client, enable_keycloak, monkeypatch):
    _stub_verify(monkeypatch, {
        "sub": "u", "tenant_id": "tenant-a",
        "realm_access": {"roles": ["api_service_account"]},
        "scope": "", "azp": "solarpro-payment-agent",
        "preferred_username": "service-account-solarpro-payment-agent",
    })
    resp = client.get("/internal/agent", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "WRONG_SERVICE_ACCOUNT"
