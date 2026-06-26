"""SOC 2 hardening 2026-06-26 -- CSP + CORS + security headers tests.

Verifies the after_request hook + before_request preflight + the
/api/csp-report endpoint behave as documented in web_app.py:
  * CSP carries every hardened directive
  * HSTS / COOP / CORP / Permissions-Policy headers stamped on every response
  * /api/csp-report returns 204 and forwards through write_audit_event
  * CORS opt-in: no Access-Control-Allow-* unless Origin is in
    CORS_ALLOWED_ORIGINS env
  * CORS preflight: OPTIONS with a matching Origin returns 204 with the
    Allow-* headers stamped; OPTIONS with a non-matching Origin falls
    through to Flask's normal 405
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest


@pytest.fixture
def web_app_client(monkeypatch, tmp_path):
    """Boot web_app with a temp SQLite + audit sink; reload to pick up env."""
    # Use SQLite so we don't need Postgres for header tests.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "solar.db"))
    monkeypatch.setenv("SOLARPRO_ADMIN_PASSWORD", "test-admin")
    monkeypatch.setenv("SOLARPRO_OWNER_PASSWORD", "test-owner")
    monkeypatch.setenv("SECRET_KEY", "0" * 64)
    # CSP + CORS env knobs:
    monkeypatch.setenv("KEYCLOAK_ORIGIN", "https://auth.aiappinvent.com")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://obs.example.com,https://other.example.com")

    # Drop a cached module so the env-driven module-level constants reload.
    sys.modules.pop("web_app", None)
    sys.modules.pop("app.observability.metrics", None)

    import web_app  # noqa: WPS433
    importlib.reload(web_app)

    from app.security import audit as _audit
    _audit.set_test_sink([])
    yield web_app.app.test_client(), _audit._TEST_SINK  # noqa: SLF001
    _audit.set_test_sink(None)


# ── CSP ─────────────────────────────────────────────────────────────────

def test_csp_carries_all_hardened_directives(web_app_client):
    client, _sink = web_app_client
    r = client.get("/login")
    csp = r.headers.get("Content-Security-Policy", "")
    for needle in (
        "default-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self' https://auth.aiappinvent.com",
        "connect-src 'self' https://auth.aiappinvent.com",
        "object-src 'none'",
        "upgrade-insecure-requests",
        "report-uri /api/csp-report",
    ):
        assert needle in csp, f"CSP missing directive: {needle!r}\nGot: {csp}"


# ── Cross-cutting hardening headers ────────────────────────────────────

def test_security_hardening_headers_stamped(web_app_client):
    client, _sink = web_app_client
    r = client.get("/login")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("X-XSS-Protection") == "1; mode=block"
    assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "max-age=31536000" in r.headers.get("Strict-Transport-Security", "")
    assert "includeSubDomains" in r.headers.get("Strict-Transport-Security", "")
    assert "geolocation=()" in r.headers.get("Permissions-Policy", "")
    assert r.headers.get("Cross-Origin-Opener-Policy") == "same-origin"
    assert r.headers.get("Cross-Origin-Resource-Policy") == "same-origin"


def test_static_assets_skip_no_store_cache(web_app_client):
    """The hook intentionally leaves Cache-Control alone for /static/* so
    versioned assets can be cached. App responses still get no-store."""
    client, _sink = web_app_client
    r_app = client.get("/login")
    assert "no-store" in r_app.headers.get("Cache-Control", "")
    # /static/ paths are static-file served by Flask; even when the file
    # is absent (404), the after_request hook still runs -- check that we
    # did NOT stamp the no-store header on it.
    r_static = client.get("/static/missing.css")
    assert "no-store" not in r_static.headers.get("Cache-Control", "")


# ── CSP violation reporter ─────────────────────────────────────────────

def test_csp_report_returns_204_and_logs_audit(web_app_client):
    client, sink = web_app_client
    payload = {
        "csp-report": {
            "blocked-uri": "https://evil.example/inject.js",
            "document-uri": "https://solarpro.aiappinvent.com/dashboard",
            "violated-directive": "script-src",
            "effective-directive": "script-src",
            "source-file": "https://solarpro.aiappinvent.com/dashboard",
            "line-number": 42,
        }
    }
    r = client.post("/api/csp-report", json=payload)
    assert r.status_code == 204
    assert sink, "write_audit_event sink received nothing"
    row = sink[-1]
    assert row["action"] == "csp_violation"
    assert "evil.example" in row["details"]
    assert "script-src" in row["details"]


def test_csp_report_handles_garbage_body(web_app_client):
    """Malformed POSTs must still 204 -- never 4xx/5xx -- so the browser
    doesn't keep retrying."""
    client, _sink = web_app_client
    r = client.post(
        "/api/csp-report",
        data=b"not json",
        content_type="application/csp-report",
    )
    assert r.status_code == 204


# ── CORS (opt-in via env) ──────────────────────────────────────────────

def test_cors_no_headers_when_origin_not_allowed(web_app_client):
    client, _sink = web_app_client
    r = client.get("/login", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in r.headers
    assert "Access-Control-Allow-Credentials" not in r.headers


def test_cors_stamped_when_origin_in_allowlist(web_app_client):
    client, _sink = web_app_client
    r = client.get("/login", headers={"Origin": "https://obs.example.com"})
    assert r.headers.get("Access-Control-Allow-Origin") == "https://obs.example.com"
    assert r.headers.get("Access-Control-Allow-Credentials") == "true"
    assert "Origin" in r.headers.get("Vary", "")


def test_cors_preflight_204_for_allowed_origin(web_app_client):
    client, _sink = web_app_client
    r = client.options(
        "/login",
        headers={
            "Origin": "https://obs.example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert r.status_code == 204
    assert r.headers.get("Access-Control-Allow-Origin") == "https://obs.example.com"
    assert "GET" in r.headers.get("Access-Control-Allow-Methods", "")
    assert "Authorization" in r.headers.get("Access-Control-Allow-Headers", "")


def test_cors_preflight_falls_through_for_disallowed_origin(web_app_client):
    """OPTIONS without a matching allowlist origin must NOT short-circuit;
    Flask's normal routing handles it (which may 405 or 404). The point
    is no CORS headers leak."""
    client, _sink = web_app_client
    r = client.options(
        "/login",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "Access-Control-Allow-Origin" not in r.headers
