"""/api/health/ai must report the provider setup the AI chain ACTUALLY uses.

WHY THIS FILE EXISTS
--------------------
The route hand-rolled its own os.environ check and it had drifted from the code it describes:

    "github_models": "configured" if os.environ.get("GITHUB_MODELS_TOKEN") else ...

api_manager reads GITHUB_TOKEN. Nothing anywhere sets GITHUB_MODELS_TOKEN. So the provider
would have reported "not_configured" no matter how correctly it was configured -- on the one
endpoint used to diagnose this feature. A health check that reports the opposite of the truth
is worse than none, because it is believed.

Run: python -m pytest test_health_ai_single_source.py -q
"""
import os
import pytest

import web_app


@pytest.fixture
def client():
    web_app.app.config["TESTING"] = True
    with web_app.app.test_client() as c:
        yield c


def _body(client):
    r = client.get("/api/health/ai")
    assert r.status_code == 200
    return r.get_json()


def test_the_endpoint_still_answers_with_its_documented_shape(client):
    """beta-monitor and the smoke tests parse `services` -- do not break its shape."""
    b = _body(client)
    assert set(b["services"]) == {"anthropic", "openrouter", "ollama", "github_models"}
    for v in b["services"].values():
        assert v in ("configured", "not_configured")
    assert b["status"] in ("ok", "degraded")


def test_it_reports_health_not_merely_presence(client):
    """The whole point: distinguish 'a key exists' from 'it actually answers'."""
    b = _body(client)
    assert set(b["health"]) == set(b["services"])
    for v in b["health"].values():
        assert v in ("not_configured", "untried", "failing",
                     "degraded", "working", "unknown")


def test_github_models_tracks_GITHUB_TOKEN_not_the_phantom_variable(client, monkeypatch):
    """THE REGRESSION. The route read GITHUB_MODELS_TOKEN; the chain reads GITHUB_TOKEN."""
    import api_manager

    monkeypatch.setenv("GITHUB_TOKEN", "tok-abc123")
    monkeypatch.delenv("GITHUB_MODELS_TOKEN", raising=False)
    api_manager.api.ai.reload()
    try:
        assert _body(client)["services"]["github_models"] == "configured", (
            "setting the variable the chain actually reads must show as configured")
    finally:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        api_manager.api.ai.reload()


def test_the_phantom_variable_alone_does_not_fake_configured(client, monkeypatch):
    """Setting only the variable the OLD route read must NOT report configured.

    It configures nothing -- the chain would still have no token.
    """
    import api_manager

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_MODELS_TOKEN", "tok-phantom")
    api_manager.api.ai.reload()
    try:
        assert _body(client)["services"]["github_models"] == "not_configured"
    finally:
        monkeypatch.delenv("GITHUB_MODELS_TOKEN", raising=False)
        api_manager.api.ai.reload()


def test_endpoint_survives_the_ai_client_blowing_up(client, monkeypatch):
    """A health check must not 500 -- that would turn a report into an outage of its own."""
    import api_manager

    def _boom():
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(api_manager.api, "status", _boom)
    b = _body(client)
    assert b["status"] == "degraded"
    # Codex LOW: a failure to READ the provider state must not be reported as the providers
    # being absent -- that sends ops to fix configuration when the health check is what broke.
    assert b.get("health_error") == "api_status_unavailable"


def test_no_health_error_key_when_nothing_is_wrong(client):
    """The diagnostic must be absent on the happy path, not present-and-empty."""
    assert "health_error" not in _body(client)
