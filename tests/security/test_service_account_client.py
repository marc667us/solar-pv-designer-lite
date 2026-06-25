"""
Unit tests for app.security.service_account_client.

Phase 3 deliverable per docs/SECURITY_MIGRATION_KEYCLOAK.md §19 task 18.

Mocks the Keycloak token endpoint via unittest.mock so no live Keycloak
is required. Covers:

- KEYCLOAK_ENABLED parallel-run short-circuit.
- Unknown client_id rejection.
- Missing-secret rejection.
- Missing-endpoint rejection.
- Happy-path fetch + cache population.
- Cache hit (no extra HTTP).
- Cache refresh inside leeway window.
- Cache refresh after explicit expiry.
- Token endpoint 4xx mapped to ServiceAccountError.
- Network failure mapped to ServiceAccountError.
- Non-JSON response mapped to ServiceAccountError.
- Response missing access_token mapped to ServiceAccountError.
- Token endpoint derived from KEYCLOAK_ISSUER.
- KEYCLOAK_TOKEN_ENDPOINT override wins.
- Missing/zero expires_in falls back to conservative 60s.
- _env_key_for derivation for all 5 SA clients.
- authorization_header convenience wrapper.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
import requests

from app.security import service_account_client as sac


# ── Fixtures ─────────────────────────────────────────────────────────────

CATALOGUE = "solarpro-catalogue-agent"
TENDER = "solarpro-tender-agent"


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """Each test starts with an empty cache, KEYCLOAK_ENABLED=true,
    a working issuer, and a client secret available for catalogue."""
    sac.clear_cache()
    monkeypatch.setenv("KEYCLOAK_ENABLED", "true")
    monkeypatch.setenv("KEYCLOAK_ISSUER", "http://kc.test/realms/solarpro")
    monkeypatch.delenv("KEYCLOAK_TOKEN_ENDPOINT", raising=False)
    monkeypatch.setenv("KC_SA_CATALOGUE_AGENT_CLIENT_SECRET", "cat-secret")
    yield
    sac.clear_cache()


def _ok_response(token: str = "ey.fake.token", expires_in: int = 300):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "access_token": token,
        "expires_in": expires_in,
        "token_type": "Bearer",
    }
    resp.text = '{"access_token":"…"}'
    return resp


# ── Feature flag retired (SOC 2 M1.1, 2026-06-25) ───────────────────────
# The "KEYCLOAK_ENABLED off -> return None" short-circuit is gone. The
# broker now always tries to fetch a token regardless of the env var.
# Coverage of the new contract is provided by test_happy_path_fetches_*.


def test_env_unset_still_fetches_token(monkeypatch):
    """SOC 2 M1.1: even with KEYCLOAK_ENABLED unset, the broker must
    obtain a real SA token (or raise) -- no anonymous fallback."""
    monkeypatch.delenv("KEYCLOAK_ENABLED", raising=False)
    with patch("app.security.service_account_client.requests.post",
               return_value=_ok_response(token="env-unset.tok")) as p:
        assert sac.get_service_account_token(CATALOGUE) == "env-unset.tok"
        p.assert_called_once()


# ── Input validation ─────────────────────────────────────────────────────

def test_unknown_client_id_raises():
    with pytest.raises(sac.ServiceAccountError, match="Unknown service-account"):
        sac.get_service_account_token("solarpro-rogue-agent")


def test_unknown_client_id_rejected_even_when_disabled(monkeypatch):
    """Typos should fail loud even in parallel-run mode."""
    monkeypatch.delenv("KEYCLOAK_ENABLED", raising=False)
    with pytest.raises(sac.ServiceAccountError, match="Unknown"):
        sac.get_service_account_token("typo-agent")


def test_missing_client_secret_raises(monkeypatch):
    monkeypatch.delenv("KC_SA_CATALOGUE_AGENT_CLIENT_SECRET", raising=False)
    with pytest.raises(sac.ServiceAccountError, match="KC_SA_CATALOGUE_AGENT_CLIENT_SECRET"):
        sac.get_service_account_token(CATALOGUE)


def test_blank_client_secret_raises(monkeypatch):
    monkeypatch.setenv("KC_SA_CATALOGUE_AGENT_CLIENT_SECRET", "   ")
    with pytest.raises(sac.ServiceAccountError, match="Missing client secret"):
        sac.get_service_account_token(CATALOGUE)


def test_missing_endpoint_and_issuer_raises(monkeypatch):
    monkeypatch.delenv("KEYCLOAK_ISSUER", raising=False)
    monkeypatch.delenv("KEYCLOAK_TOKEN_ENDPOINT", raising=False)
    with pytest.raises(sac.ServiceAccountError, match="KEYCLOAK_TOKEN_ENDPOINT"):
        sac.get_service_account_token(CATALOGUE)


# ── Happy path + cache ───────────────────────────────────────────────────

def test_happy_path_fetches_and_returns_token():
    with patch("app.security.service_account_client.requests.post",
               return_value=_ok_response(token="real.jwt.value")) as p:
        token = sac.get_service_account_token(CATALOGUE, _now=1_000_000.0)
    assert token == "real.jwt.value"
    p.assert_called_once()
    args, kwargs = p.call_args
    assert args[0] == "http://kc.test/realms/solarpro/protocol/openid-connect/token"
    assert kwargs["data"]["grant_type"] == "client_credentials"
    assert kwargs["data"]["client_id"] == CATALOGUE
    assert kwargs["data"]["client_secret"] == "cat-secret"


def test_cache_hit_skips_http():
    with patch("app.security.service_account_client.requests.post",
               return_value=_ok_response(expires_in=300)) as p:
        sac.get_service_account_token(CATALOGUE, _now=1_000_000.0)
        sac.get_service_account_token(CATALOGUE, _now=1_000_010.0)  # 10s later
    p.assert_called_once()  # second call served from cache


def test_cache_refreshes_within_expiry_leeway(monkeypatch):
    """When fewer than EXPIRY_LEEWAY_SECONDS remain we re-fetch even
    though the cached token is technically still valid."""
    responses = [_ok_response(token="t1", expires_in=300),
                 _ok_response(token="t2", expires_in=300)]
    with patch("app.security.service_account_client.requests.post",
               side_effect=responses) as p:
        assert sac.get_service_account_token(CATALOGUE, _now=1_000_000.0) == "t1"
        # 280s later -> 20s of life left -> inside the 30s leeway window.
        assert sac.get_service_account_token(CATALOGUE, _now=1_000_280.0) == "t2"
    assert p.call_count == 2


def test_cache_refreshes_after_explicit_expiry():
    responses = [_ok_response(token="t1", expires_in=60),
                 _ok_response(token="t2", expires_in=60)]
    with patch("app.security.service_account_client.requests.post",
               side_effect=responses) as p:
        assert sac.get_service_account_token(CATALOGUE, _now=1_000_000.0) == "t1"
        assert sac.get_service_account_token(CATALOGUE, _now=1_000_120.0) == "t2"  # 2x expiry later
    assert p.call_count == 2


def test_cache_is_per_client(monkeypatch):
    monkeypatch.setenv("KC_SA_TENDER_AGENT_CLIENT_SECRET", "tender-secret")
    responses = [_ok_response(token="cat.tok"), _ok_response(token="ten.tok")]
    with patch("app.security.service_account_client.requests.post",
               side_effect=responses) as p:
        assert sac.get_service_account_token(CATALOGUE, _now=1.0) == "cat.tok"
        assert sac.get_service_account_token(TENDER, _now=1.0) == "ten.tok"
    assert p.call_count == 2


# ── Error handling ───────────────────────────────────────────────────────

def test_4xx_response_raises():
    bad = MagicMock(status_code=401, text='{"error":"invalid_client"}')
    bad.json.return_value = {"error": "invalid_client"}
    with patch("app.security.service_account_client.requests.post", return_value=bad):
        with pytest.raises(sac.ServiceAccountError, match="401"):
            sac.get_service_account_token(CATALOGUE)


def test_network_failure_wrapped():
    with patch("app.security.service_account_client.requests.post",
               side_effect=requests.ConnectionError("no route")):
        with pytest.raises(sac.ServiceAccountError, match="Network error"):
            sac.get_service_account_token(CATALOGUE)


def test_non_json_response_wrapped():
    weird = MagicMock(status_code=200, text="<html>oops</html>")
    weird.json.side_effect = ValueError("not JSON")
    with patch("app.security.service_account_client.requests.post", return_value=weird):
        with pytest.raises(sac.ServiceAccountError, match="Non-JSON"):
            sac.get_service_account_token(CATALOGUE)


def test_response_missing_access_token_wrapped():
    incomplete = MagicMock(status_code=200, text='{"expires_in":300}')
    incomplete.json.return_value = {"expires_in": 300}
    with patch("app.security.service_account_client.requests.post", return_value=incomplete):
        with pytest.raises(sac.ServiceAccountError, match="missing access_token"):
            sac.get_service_account_token(CATALOGUE)


# ── Endpoint resolution ──────────────────────────────────────────────────

def test_endpoint_derived_from_issuer():
    with patch("app.security.service_account_client.requests.post",
               return_value=_ok_response()) as p:
        sac.get_service_account_token(CATALOGUE)
    assert p.call_args[0][0] == (
        "http://kc.test/realms/solarpro/protocol/openid-connect/token"
    )


def test_explicit_endpoint_overrides_issuer(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_TOKEN_ENDPOINT",
                       "https://auth.aiappinvent.com/realms/solarpro/protocol/openid-connect/token")
    with patch("app.security.service_account_client.requests.post",
               return_value=_ok_response()) as p:
        sac.get_service_account_token(CATALOGUE)
    assert p.call_args[0][0] == (
        "https://auth.aiappinvent.com/realms/solarpro/protocol/openid-connect/token"
    )


# ── expires_in defaults ──────────────────────────────────────────────────

def test_missing_expires_in_falls_back_to_60s():
    weird = MagicMock(status_code=200, text='ok')
    weird.json.return_value = {"access_token": "t"}
    with patch("app.security.service_account_client.requests.post", return_value=weird):
        sac.get_service_account_token(CATALOGUE, _now=1000.0)
    # Inside the 30s leeway -> not cached usefully; a call at t+31 must refetch.
    with patch("app.security.service_account_client.requests.post",
               return_value=_ok_response(token="next")) as p2:
        assert sac.get_service_account_token(CATALOGUE, _now=1031.0) == "next"
        assert p2.called


def test_zero_expires_in_falls_back_to_60s():
    weird = MagicMock(status_code=200, text='ok')
    weird.json.return_value = {"access_token": "t", "expires_in": 0}
    with patch("app.security.service_account_client.requests.post", return_value=weird):
        sac.get_service_account_token(CATALOGUE, _now=1000.0)
    with patch("app.security.service_account_client.requests.post",
               return_value=_ok_response(token="next")) as p2:
        sac.get_service_account_token(CATALOGUE, _now=1031.0)
        assert p2.called


# ── _env_key_for derivation ──────────────────────────────────────────────

@pytest.mark.parametrize("client_id, expected", [
    ("solarpro-catalogue-agent", "KC_SA_CATALOGUE_AGENT_CLIENT_SECRET"),
    ("solarpro-tender-agent",    "KC_SA_TENDER_AGENT_CLIENT_SECRET"),
    ("solarpro-report-agent",    "KC_SA_REPORT_AGENT_CLIENT_SECRET"),
    ("solarpro-email-agent",     "KC_SA_EMAIL_AGENT_CLIENT_SECRET"),
    ("solarpro-payment-agent",   "KC_SA_PAYMENT_AGENT_CLIENT_SECRET"),
])
def test_env_key_for_all_five_sa_clients(client_id, expected):
    assert sac._env_key_for(client_id) == expected


def test_env_key_for_non_solarpro_prefix():
    assert sac._env_key_for("custom-agent") == "KC_SA_CUSTOM_AGENT_CLIENT_SECRET"


# ── authorization_header convenience ─────────────────────────────────────

def test_authorization_header_happy_path():
    with patch("app.security.service_account_client.requests.post",
               return_value=_ok_response(token="abc")):
        assert sac.authorization_header(CATALOGUE) == {"Authorization": "Bearer abc"}


def test_authorization_header_env_unset_still_fetches(monkeypatch):
    """SOC 2 M1.1: helper must mint a Bearer even with env unset."""
    monkeypatch.delenv("KEYCLOAK_ENABLED", raising=False)
    with patch("app.security.service_account_client.requests.post",
               return_value=_ok_response(token="abc")):
        assert sac.authorization_header(CATALOGUE) == {"Authorization": "Bearer abc"}


# ── Allowlist completeness ───────────────────────────────────────────────

def test_allowed_set_matches_realm_export_count():
    """The realm export Phase 1 added the 5 SA clients. The allowlist
    here must stay in lockstep with realm-export.json."""
    assert sac.ALLOWED_CLIENT_IDS == frozenset({
        "solarpro-catalogue-agent",
        "solarpro-tender-agent",
        "solarpro-report-agent",
        "solarpro-email-agent",
        "solarpro-payment-agent",
    })
