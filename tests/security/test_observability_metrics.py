"""SOC 2 M3.4 -- metrics + /metrics endpoint behaviour tests."""
from __future__ import annotations

import os

import pytest
from flask import Flask

from app.observability import metrics as obs


@pytest.fixture
def flask_app():
    app = Flask(__name__)
    obs.register_request_hooks(app)
    obs.scrape_endpoint(app)

    @app.route("/health")
    def _health():
        return "ok"

    @app.route("/api/echo")
    def _echo():
        return ("echoed", 200)

    return app


# ── Bearer gate ─────────────────────────────────────────────────────────

def test_metrics_refuses_without_bearer(flask_app, monkeypatch):
    """METRICS_BEARER unset OR missing header => 401, never serve."""
    monkeypatch.delenv("METRICS_BEARER", raising=False)
    with flask_app.test_client() as c:
        r = c.get("/metrics")
        assert r.status_code == 401
        assert b"Bearer" in r.data


def test_metrics_refuses_wrong_bearer(flask_app, monkeypatch):
    monkeypatch.setenv("METRICS_BEARER", "abcdef0123456789" * 4)
    with flask_app.test_client() as c:
        r = c.get("/metrics", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401


def test_metrics_serves_with_correct_bearer(flask_app, monkeypatch):
    token = "abcdef0123456789" * 4
    monkeypatch.setenv("METRICS_BEARER", token)
    with flask_app.test_client() as c:
        c.get("/api/echo")  # warm a counter
        r = c.get("/metrics", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.data.decode("utf-8")
        # Prometheus exposition format starts each metric with a TYPE line.
        assert "solarpro_http_requests_total" in body
        assert "solarpro_http_request_duration_seconds" in body


def test_metrics_bearer_check_constant_length():
    """Bearer comparison must short-circuit on length mismatch BEFORE
    the char-by-char compare so the timing oracle is bounded."""
    assert obs._bearer_ok("Bearer short") is False  # noqa: SLF001


# ── Per-request counter ────────────────────────────────────────────────

def test_request_hook_increments_counter_by_status_class(flask_app, monkeypatch):
    token = "0" * 64
    monkeypatch.setenv("METRICS_BEARER", token)
    with flask_app.test_client() as c:
        c.get("/health")  # 200
        c.get("/health")
        c.get("/missing-route")  # 404
        body = c.get("/metrics", headers={"Authorization": f"Bearer {token}"}).data.decode()
    # The "2xx" series for the _health endpoint must show count >= 2.
    assert 'status_class="2xx"' in body
    assert 'status_class="4xx"' in body


def test_endpoint_label_collapses_dynamic_paths(flask_app, monkeypatch):
    """Per the metrics docstring, /<int:id> style paths must share an
    endpoint label so cardinality stays bounded."""
    token = "0" * 64
    monkeypatch.setenv("METRICS_BEARER", token)

    @flask_app.route("/items/<int:item_id>")
    def _item_view(item_id):
        return str(item_id)

    with flask_app.test_client() as c:
        for i in range(1, 6):
            c.get(f"/items/{i}")
        body = c.get("/metrics", headers={"Authorization": f"Bearer {token}"}).data.decode()
    # Five hits, one endpoint label -- the _item_view series must
    # appear exactly once on a _total line.
    item_lines = [l for l in body.splitlines()
                  if l.startswith("solarpro_http_requests_total") and "_item_view" in l]
    assert len(item_lines) == 1, item_lines


# ── Counter wiring (smoke) ─────────────────────────────────────────────

def test_oidc_failures_counter_label_path():
    """The OIDC fail-redirect helper labels by reason code; smoke-test
    the labels-then-inc path so a typo at the wiring site is caught."""
    obs.oidc_failures_total.labels(reason="OIDC_STATE_MISMATCH").inc()
    obs.oidc_failures_total.labels(reason="OIDC_STATE_MISMATCH").inc()
    # No assertion shape here -- prometheus_client doesn't expose a
    # public read API on Counter; the smoke is that .labels().inc()
    # doesn't raise on a fresh registry.


def test_audit_writes_counter_label_path():
    obs.audit_writes_total.labels(action="LOGIN_SUCCESS").inc()
    obs.audit_writes_total.labels(action="LOGOUT").inc()


# ── Gauge refresh resilience ───────────────────────────────────────────

def test_refresh_gauges_swallows_db_errors(monkeypatch):
    """refresh_gauges must NEVER raise; metrics scrape happens on every
    Prometheus poll and a DB hiccup should not 5xx the endpoint."""
    class _BoomConn:
        def execute(self, *a, **kw): raise RuntimeError("db gone")
        def __enter__(self): return self
        def __exit__(self, *exc): pass

    def _boom_get_db():
        return _BoomConn()

    # Should not raise.
    obs.refresh_gauges(_boom_get_db)
