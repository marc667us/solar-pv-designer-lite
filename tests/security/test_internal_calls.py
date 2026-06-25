"""
Unit tests for app.auth.internal_calls.

Phase 3 tasks 16 + 17 deliverable -- the only supported channel for an
AI agent to call back into the SolarPro API.

Covers:
  * KC off: request issued WITHOUT Authorization header (parallel-run).
  * KC on:  request issued WITH Bearer header sourced from the SA broker.
  * Caller-supplied headers preserved.
  * ServiceAccountError propagates instead of degrading to unauthenticated.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from app.auth import internal_calls as ic
from app.security import service_account_client as sac


CATALOGUE = "solarpro-catalogue-agent"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    sac.clear_cache()
    monkeypatch.setenv("KEYCLOAK_ENABLED", "true")
    monkeypatch.setenv("KEYCLOAK_ISSUER", "http://kc.test/realms/solarpro")
    monkeypatch.setenv("KC_SA_CATALOGUE_AGENT_CLIENT_SECRET", "secret-x")
    yield
    sac.clear_cache()


def _ok_token():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"access_token": "ey.cat.tok", "expires_in": 300}
    resp.text = "ok"
    return resp


def test_env_unset_still_attaches_bearer(monkeypatch):
    """SOC 2 M1.1 (2026-06-25): KEYCLOAK_ENABLED is retired. Even when
    the env var is absent, internal calls must obtain and attach a SA
    token -- there is no anonymous fall-through any more."""
    monkeypatch.delenv("KEYCLOAK_ENABLED", raising=False)
    with patch("app.security.service_account_client.requests.post",
               return_value=_ok_token()), \
         patch("app.auth.internal_calls.requests.request") as req:
        req.return_value = MagicMock(status_code=200)
        ic.agent_get(CATALOGUE, "http://localhost/api/x")
        sent_headers = req.call_args.kwargs.get("headers", {})
        assert sent_headers["Authorization"].startswith("Bearer ")


def test_kc_on_attaches_bearer():
    with patch("app.security.service_account_client.requests.post",
               return_value=_ok_token()), \
         patch("app.auth.internal_calls.requests.request") as req:
        req.return_value = MagicMock(status_code=200)
        ic.agent_post(CATALOGUE, "http://localhost/api/x",
                      json={"hello": 1})
        sent_headers = req.call_args.kwargs["headers"]
        assert sent_headers["Authorization"] == "Bearer ey.cat.tok"


def test_caller_headers_preserved():
    with patch("app.security.service_account_client.requests.post",
               return_value=_ok_token()), \
         patch("app.auth.internal_calls.requests.request") as req:
        req.return_value = MagicMock(status_code=200)
        ic.agent_post(
            CATALOGUE,
            "http://localhost/api/x",
            headers={"X-Trace-Id": "tr-1"},
        )
        h = req.call_args.kwargs["headers"]
        assert h["X-Trace-Id"] == "tr-1"
        assert h["Authorization"].startswith("Bearer ")


def test_service_account_error_propagates(monkeypatch):
    """Missing client secret must NOT be papered over -- the agent
    needs to know its identity is unavailable rather than silently
    issuing an anonymous internal call."""
    monkeypatch.delenv("KC_SA_CATALOGUE_AGENT_CLIENT_SECRET", raising=False)
    with patch("app.auth.internal_calls.requests.request") as req:
        with pytest.raises(sac.ServiceAccountError):
            ic.agent_get(CATALOGUE, "http://localhost/api/x")
        req.assert_not_called()


def test_unknown_client_id_propagates():
    with patch("app.auth.internal_calls.requests.request") as req:
        with pytest.raises(sac.ServiceAccountError, match="Unknown"):
            ic.agent_get("solarpro-rogue-agent", "http://x")
        req.assert_not_called()


def test_method_param_forwarded():
    with patch("app.security.service_account_client.requests.post",
               return_value=_ok_token()), \
         patch("app.auth.internal_calls.requests.request") as req:
        req.return_value = MagicMock(status_code=204)
        ic.agent_request("DELETE", CATALOGUE, "http://x/y")
    assert req.call_args.args[0] == "DELETE"


def test_default_timeout_passed():
    with patch("app.security.service_account_client.requests.post",
               return_value=_ok_token()), \
         patch("app.auth.internal_calls.requests.request") as req:
        req.return_value = MagicMock(status_code=200)
        ic.agent_get(CATALOGUE, "http://x/y")
    assert req.call_args.kwargs["timeout"] == ic.DEFAULT_TIMEOUT
