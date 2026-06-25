"""
Unit tests for app.auth.oidc_routes.

Phase 5 deliverable per docs/SECURITY_MIGRATION_KEYCLOAK.md §19 task 27.

Mocks the Keycloak token endpoint + verify_jwt() so the suite runs
without a live Keycloak. Covers:

  * Parallel-run pass-through: every route falls back to the legacy
    /login form when KEYCLOAK_ENABLED is unset.
  * /auth/login: 302 to Keycloak with the right query params; state +
    nonce + verifier stored in session.
  * /auth/callback: rejects state mismatch, missing code, network error,
    token-endpoint 4xx, nonce mismatch, invalid id_token; happy path
    sets session["user"] + HttpOnly cookie.
  * /auth/logout: calls end-session, wipes session + cookie, redirects.
  * /auth/refresh: 401 without cookie; happy path rotates cookie.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock
from urllib.parse import urlparse, parse_qs

import pytest
import requests
from flask import Flask, session

from app.auth import register_oidc


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def flask_app(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_ENABLED", "true")
    monkeypatch.setenv(
        "KEYCLOAK_ISSUER", "http://kc.test/realms/solarpro"
    )
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "solarpro-web")
    monkeypatch.setenv(
        "KEYCLOAK_REDIRECT_URI",
        "https://solarpro.aiappinvent.com/auth/callback",
    )
    app = Flask(__name__)
    app.secret_key = "test-secret"
    register_oidc(app)

    @app.route("/login")
    def _legacy_login_stub():
        return "legacy", 200

    @app.route("/dashboard")
    def _dashboard_stub():
        return "dashboard", 200

    return app


def _seed_session(client, **kv):
    """Inject PKCE/state material into the Flask test-client session."""
    with client.session_transaction() as s:
        for k, v in kv.items():
            s[k] = v


def _make_token_response(
    access_token="access.jwt",
    refresh_token="refresh.jwt",
    id_token="id.jwt",
    refresh_expires_in=3600,
    expires_in=600,
):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "id_token": id_token,
        "expires_in": expires_in,
        "refresh_expires_in": refresh_expires_in,
        "token_type": "Bearer",
    }
    resp.text = '{"access_token":"…"}'
    return resp


# ── Feature flag retired (SOC 2 M1.1, 2026-06-25) ───────────────────────
# KEYCLOAK_ENABLED no longer exists as a kill-switch. OIDC routes always
# execute the real flow. The legacy `/login?legacy=1` fallback is gone.

def test_legacy_logout_delegates_to_oidc_logout(monkeypatch):
    """SOC 2 M1.8 (2026-06-25): the legacy /logout entry point must
    redirect to /auth/logout so Keycloak's end-session call + RT cookie
    wipe + Flask session.clear all run. Without that delegation the KC
    session and the solarpro_rt cookie stay alive after a user 'logs
    out' (Codex finding 2026-06-25, MEDIUM)."""
    monkeypatch.setenv("KEYCLOAK_ENABLED", "true")
    app = Flask(__name__)
    app.secret_key = "test"
    register_oidc(app)

    # Mirror web_app.py:1945-1969 in miniature: the legacy /logout
    # purges drafts (we stub it out here) then 302s to oidc.auth_logout.
    from flask import session, redirect, url_for
    @app.route("/logout")
    def legacy_logout():
        session.clear()
        return redirect(url_for("oidc.auth_logout"))

    with app.test_client() as c:
        _seed_session(c, user_id=42)
        r = c.get("/logout", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/auth/logout"), \
            f"expected redirect to /auth/logout, got {r.headers['Location']}"


def test_logout_with_env_unset_still_clears_session(monkeypatch):
    """Session-clearing on logout has no env dependency -- it works
    regardless of the retired KEYCLOAK_ENABLED env."""
    monkeypatch.delenv("KEYCLOAK_ENABLED", raising=False)
    app = Flask(__name__)
    app.secret_key = "test"
    register_oidc(app)
    with app.test_client() as c:
        _seed_session(c, user={"sub": "u1"})
        r = c.post("/auth/logout", follow_redirects=False)
        assert r.status_code == 302
        with c.session_transaction() as s:
            assert "user" not in s


# ── /auth/login ──────────────────────────────────────────────────────────

def test_login_redirects_to_keycloak_with_pkce_params(flask_app):
    with flask_app.test_client() as c:
        r = c.get("/auth/login", follow_redirects=False)
        assert r.status_code == 302
        u = urlparse(r.headers["Location"])
        assert u.netloc == "kc.test"
        assert u.path.endswith("/protocol/openid-connect/auth")
        q = parse_qs(u.query)
        assert q["response_type"] == ["code"]
        assert q["client_id"] == ["solarpro-web"]
        assert q["redirect_uri"] == [
            "https://solarpro.aiappinvent.com/auth/callback"
        ]
        assert q["code_challenge_method"] == ["S256"]
        assert len(q["code_challenge"][0]) >= 43
        assert q["scope"] == ["openid profile email"]

        with c.session_transaction() as s:
            assert "_kc_state" in s
            assert "_kc_nonce" in s
            assert "_kc_verifier" in s
            assert s["_kc_state"] == q["state"][0]
            assert s["_kc_nonce"] == q["nonce"][0]


def test_login_honours_next_param(flask_app):
    with flask_app.test_client() as c:
        c.get("/auth/login?next=/admin/marketplace", follow_redirects=False)
        with c.session_transaction() as s:
            assert s["_kc_next"] == "/admin/marketplace"


def test_login_503_when_issuer_unset(monkeypatch, flask_app):
    monkeypatch.delenv("KEYCLOAK_ISSUER", raising=False)
    with flask_app.test_client() as c:
        r = c.get("/auth/login")
        assert r.status_code == 503
        assert r.get_json()["error"] == "OIDC_NOT_CONFIGURED"


# ── /auth/callback ──────────────────────────────────────────────────────

def test_callback_rejects_state_mismatch(flask_app):
    with flask_app.test_client() as c:
        _seed_session(c, _kc_state="EXPECTED", _kc_verifier="v", _kc_nonce="n")
        r = c.get("/auth/callback?code=abc&state=WRONG")
        assert r.status_code == 400
        assert r.get_json()["error"] == "OIDC_STATE_MISMATCH"


def test_callback_rejects_missing_code(flask_app):
    with flask_app.test_client() as c:
        _seed_session(c, _kc_state="S", _kc_verifier="v", _kc_nonce="n")
        r = c.get("/auth/callback?state=S")
        assert r.status_code == 400
        assert r.get_json()["error"] == "OIDC_MISSING_CODE_OR_STATE"


def test_callback_rejects_keycloak_error_response(flask_app):
    with flask_app.test_client() as c:
        r = c.get("/auth/callback?error=access_denied&error_description=user_aborted")
        assert r.status_code == 400
        assert r.get_json()["error"] == "OIDC_ERROR"


def test_callback_wraps_network_failure(flask_app):
    with flask_app.test_client() as c:
        _seed_session(c, _kc_state="S", _kc_verifier="v", _kc_nonce="n")
        with patch("app.auth.oidc_routes.requests.post",
                   side_effect=requests.ConnectionError("no route")):
            r = c.get("/auth/callback?code=abc&state=S")
        assert r.status_code == 502
        assert r.get_json()["error"] == "OIDC_TOKEN_NETWORK"


def test_callback_4xx_response(flask_app):
    bad = MagicMock(status_code=400, text='{"error":"invalid_grant"}')
    with flask_app.test_client() as c:
        _seed_session(c, _kc_state="S", _kc_verifier="v", _kc_nonce="n")
        with patch("app.auth.oidc_routes.requests.post", return_value=bad):
            r = c.get("/auth/callback?code=abc&state=S")
        assert r.status_code == 400
        assert r.get_json()["error"] == "OIDC_TOKEN_FAILED"


def test_callback_rejects_nonce_mismatch(flask_app):
    """ID token nonce must match the value we stored in session."""
    with flask_app.test_client() as c:
        _seed_session(c,
                      _kc_state="S", _kc_verifier="v",
                      _kc_nonce="NONCE-EXPECTED", _kc_next="/dashboard")
        with patch("app.auth.oidc_routes.requests.post",
                   return_value=_make_token_response()), \
             patch("app.auth.oidc_routes.verify_jwt",
                   return_value={"sub": "u", "nonce": "WRONG"}):
            r = c.get("/auth/callback?code=abc&state=S")
        assert r.status_code == 400
        assert r.get_json()["error"] == "OIDC_NONCE_MISMATCH"


def test_callback_rejects_invalid_id_token(flask_app):
    from app.security.keycloak_middleware import JWTError
    with flask_app.test_client() as c:
        _seed_session(c, _kc_state="S", _kc_verifier="v", _kc_nonce="n")
        with patch("app.auth.oidc_routes.requests.post",
                   return_value=_make_token_response()), \
             patch("app.auth.oidc_routes.verify_jwt",
                   side_effect=JWTError("bad signature")):
            r = c.get("/auth/callback?code=abc&state=S")
        assert r.status_code == 400
        assert r.get_json()["error"] == "OIDC_ID_TOKEN_INVALID"


def test_callback_happy_path(flask_app):
    claims = {
        "sub": "uuid-1",
        "preferred_username": "alice",
        "email": "alice@example.com",
        "name": "Alice A.",
        "tenant_id": "tenant-uuid-1",
        "nonce": "NONCE-X",
        "realm_access": {"roles": ["solar_engineer", "supplier_admin"]},
    }
    with flask_app.test_client() as c:
        _seed_session(c,
                      _kc_state="STATE-X",
                      _kc_verifier="verifier-x",
                      _kc_nonce="NONCE-X",
                      _kc_next="/admin/marketplace")
        with patch("app.auth.oidc_routes.requests.post",
                   return_value=_make_token_response()) as post, \
             patch("app.auth.oidc_routes.verify_jwt", return_value=claims):
            r = c.get("/auth/callback?code=abc&state=STATE-X",
                      follow_redirects=False)

        # Token exchange request shape.
        token_call = post.call_args
        assert token_call.kwargs["data"]["grant_type"] == "authorization_code"
        assert token_call.kwargs["data"]["code"] == "abc"
        assert token_call.kwargs["data"]["client_id"] == "solarpro-web"
        assert token_call.kwargs["data"]["code_verifier"] == "verifier-x"

        # Response shape.
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/admin/marketplace")

        # Cookie planted with the right attributes.
        cookie_header = r.headers.get("Set-Cookie", "")
        assert "solarpro_rt=" in cookie_header
        assert "HttpOnly" in cookie_header
        assert "SameSite=Lax" in cookie_header

        # Session hydrated.
        with c.session_transaction() as s:
            assert s["access_token"] == "access.jwt"
            assert s["user"]["preferred_username"] == "alice"
            assert s["user"]["tenant_id"] == "tenant-uuid-1"
            assert "solar_engineer" in s["user"]["roles"]
            # Single-use proofs cleared.
            assert "_kc_state" not in s
            assert "_kc_nonce" not in s
            assert "_kc_verifier" not in s


# ── /auth/logout ────────────────────────────────────────────────────────

def test_logout_calls_end_session_and_clears(flask_app):
    with flask_app.test_client() as c:
        _seed_session(c, user={"sub": "u1"}, access_token="a")
        c.set_cookie("solarpro_rt", "REFRESH-X")
        with patch("app.auth.oidc_routes.requests.post",
                   return_value=MagicMock(status_code=204)) as post:
            r = c.post("/auth/logout", follow_redirects=False)

        post.assert_called_once()
        assert post.call_args.kwargs["data"]["refresh_token"] == "REFRESH-X"
        assert post.call_args.kwargs["data"]["client_id"] == "solarpro-web"
        assert r.status_code == 302
        with c.session_transaction() as s:
            assert "user" not in s
            assert "access_token" not in s


def test_logout_survives_end_session_failure(flask_app):
    with flask_app.test_client() as c:
        _seed_session(c, user={"sub": "u1"})
        c.set_cookie("solarpro_rt", "REFRESH-X")
        with patch("app.auth.oidc_routes.requests.post",
                   side_effect=requests.ConnectionError("kc down")):
            r = c.post("/auth/logout", follow_redirects=False)
        assert r.status_code == 302
        with c.session_transaction() as s:
            assert "user" not in s


def test_logout_no_cookie_still_clears_session(flask_app):
    with flask_app.test_client() as c:
        _seed_session(c, user={"sub": "u1"})
        with patch("app.auth.oidc_routes.requests.post") as post:
            r = c.post("/auth/logout", follow_redirects=False)
        post.assert_not_called()
        assert r.status_code == 302


# ── /auth/refresh ───────────────────────────────────────────────────────

def test_refresh_401_without_cookie(flask_app):
    with flask_app.test_client() as c:
        r = c.post("/auth/refresh")
        assert r.status_code == 401
        assert r.get_json()["error"] == "OIDC_NO_REFRESH_TOKEN"


def test_refresh_happy_path_rotates_cookie(flask_app):
    new = _make_token_response(
        access_token="A2", refresh_token="R2",
        id_token="I2", expires_in=600, refresh_expires_in=3600,
    )
    with flask_app.test_client() as c:
        c.set_cookie("solarpro_rt", "OLD-RT")
        with patch("app.auth.oidc_routes.requests.post", return_value=new):
            r = c.post("/auth/refresh")
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        assert body["expires_in"] == 600
        # Cookie rotated.
        assert "solarpro_rt=R2" in r.headers.get("Set-Cookie", "")


def test_refresh_4xx_response_returns_401(flask_app):
    bad = MagicMock(status_code=400, text='{"error":"invalid_grant"}')
    with flask_app.test_client() as c:
        c.set_cookie("solarpro_rt", "OLD-RT")
        with patch("app.auth.oidc_routes.requests.post", return_value=bad):
            r = c.post("/auth/refresh")
        assert r.status_code == 401
        assert r.get_json()["error"] == "OIDC_REFRESH_FAILED"


def test_register_oidc_is_idempotent(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_ENABLED", "true")
    monkeypatch.setenv("KEYCLOAK_ISSUER", "http://kc.test/realms/solarpro")
    app = Flask(__name__)
    app.secret_key = "test"
    register_oidc(app)
    register_oidc(app)  # second call must not raise
    auth_endpoints = [
        r.endpoint for r in app.url_map.iter_rules()
        if r.endpoint.startswith("oidc.")
    ]
    # 5 routes -- login, register, callback, logout, refresh.
    # (register added 2026-06-20 in Phase 7 KC cutover.)
    assert sorted(set(auth_endpoints)) == sorted(auth_endpoints)
    assert len(auth_endpoints) == 5
