"""
Unit tests for app.security.keycloak_middleware.

Phase 2 deliverable per docs/SECURITY_MIGRATION_KEYCLOAK.md §19 task 12.

These tests synthesise their own JWTs via python-jose (no running
Keycloak required). The test fixture generates an RSA key pair, signs
a token with it, and primes the module's JWKS cache with the
corresponding public key so verify_jwt() can validate the signature.

Covers:
- Happy path: valid JWT -> claims extracted.
- Expired token rejected.
- Wrong issuer rejected.
- Wrong audience rejected.
- Missing kid rejected.
- Unknown kid rejected.
- RequestContext extraction from a realistic claims payload.
- has_role / has_scope / has_any_role / has_all_roles.
- Service-account detection.
"""

from __future__ import annotations

import json
import time
import pytest

from jose import jwt as jose_jwt
from jose.utils import long_to_base64

from app.security.keycloak_middleware import (
    KeycloakConfig,
    extract_request_context,
    get_jwks_cache,
    reset_jwks_cache,
    set_config,
    verify_jwt,
    JWTError,
)


ISSUER = "http://localhost:8080/realms/solarpro"
AUDIENCE = "solarpro-api"


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def rsa_key():
    """Generate an RSA-2048 key pair for signing test JWTs."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private.public_key().public_numbers()

    # Convert to JWK shape Keycloak emits.
    jwk = {
        "kty": "RSA",
        "kid": "test-kid-1",
        "alg": "RS256",
        "use": "sig",
        "n": long_to_base64(public_numbers.n).decode(),
        "e": long_to_base64(public_numbers.e).decode(),
    }
    # python-jose accepts PEM for signing.
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return {"jwk": jwk, "private_pem": private_pem}


@pytest.fixture(autouse=True)
def configured_module(rsa_key, monkeypatch):
    """Prime the module-level config + JWKS cache for each test."""
    set_config(KeycloakConfig(issuer=ISSUER, audience=AUDIENCE, jwks_ttl_seconds=300))
    reset_jwks_cache()

    cache = get_jwks_cache()
    # Bypass the network fetch by seeding the cache directly.
    cache._keys = {rsa_key["jwk"]["kid"]: rsa_key["jwk"]}
    cache._fetched_at = time.time()
    yield


def _make_token(rsa_key, claims_override=None, kid_override=None):
    """Build a Keycloak-style JWT with sensible defaults."""
    now = int(time.time())
    base_claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": now + 600,
        "iat": now,
        "nbf": now,
        "sub": "user-uuid-engineer",
        "typ": "Bearer",
        "azp": "solarpro-web",
        "scope": "openid profile email project:view design:create",
        "preferred_username": "engineer_test",
        "email": "engineer@test.solarpro.local",
        "realm_access": {"roles": ["solar_engineer", "default-roles-solarpro"]},
        "tenant_id": "00000000-0000-0000-0000-000000000010",
        "tenant_name": "Demo Engineering Firm",
        "user_type": "engineer",
        "country": "GH",
        "region": "Greater Accra",
        "subscription_plan": "pro",
        "engineering_company_id": "00000000-0000-0000-0000-000000000010",
    }
    if claims_override:
        base_claims.update(claims_override)

    headers = {"alg": "RS256", "kid": kid_override or rsa_key["jwk"]["kid"], "typ": "JWT"}
    return jose_jwt.encode(base_claims, rsa_key["private_pem"], algorithm="RS256", headers=headers)


# ── Happy path ───────────────────────────────────────────────────────────

def test_verify_valid_token(rsa_key):
    token = _make_token(rsa_key)
    claims = verify_jwt(token)
    assert claims["sub"] == "user-uuid-engineer"
    assert claims["tenant_id"] == "00000000-0000-0000-0000-000000000010"
    assert "solar_engineer" in claims["realm_access"]["roles"]


def test_extract_request_context(rsa_key):
    token = _make_token(rsa_key)
    claims = verify_jwt(token)
    ctx = extract_request_context(claims)

    assert ctx.user_id == "user-uuid-engineer"
    assert ctx.tenant_id == "00000000-0000-0000-0000-000000000010"
    assert ctx.tenant_name == "Demo Engineering Firm"
    assert ctx.user_type == "engineer"
    assert "solar_engineer" in ctx.roles
    assert "project:view" in ctx.scopes
    assert "design:create" in ctx.scopes
    assert ctx.country == "GH"
    assert ctx.region == "Greater Accra"
    assert ctx.subscription_plan == "pro"
    assert ctx.engineering_company_id == "00000000-0000-0000-0000-000000000010"
    assert ctx.is_service_account is False
    assert ctx.preferred_username == "engineer_test"
    assert ctx.email == "engineer@test.solarpro.local"
    assert ctx.azp == "solarpro-web"


# ── Failure modes ────────────────────────────────────────────────────────

def test_reject_expired(rsa_key):
    token = _make_token(rsa_key, {"exp": int(time.time()) - 1})
    with pytest.raises(JWTError, match="expired"):
        verify_jwt(token)


def test_reject_wrong_issuer(rsa_key):
    token = _make_token(rsa_key, {"iss": "https://attacker.example/realms/evil"})
    with pytest.raises(JWTError):
        verify_jwt(token)


def test_reject_wrong_audience(rsa_key):
    token = _make_token(rsa_key, {"aud": "wrong-audience"})
    with pytest.raises(JWTError):
        verify_jwt(token)


def test_reject_missing_kid(rsa_key):
    token = _make_token(rsa_key, kid_override=None)
    # When kid_override is None we use the default kid; force-strip the header.
    # python-jose enforces a header, so build it without kid:
    headers = {"alg": "RS256", "typ": "JWT"}
    now = int(time.time())
    raw_token = jose_jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "exp": now + 600, "iat": now, "sub": "x"},
        rsa_key["private_pem"],
        algorithm="RS256",
        headers=headers,
    )
    with pytest.raises(JWTError, match="missing kid"):
        verify_jwt(raw_token)


def test_reject_unknown_kid(rsa_key):
    token = _make_token(rsa_key, kid_override="unknown-kid")
    with pytest.raises(JWTError):
        verify_jwt(token)


def test_reject_missing_sub(rsa_key):
    token = _make_token(rsa_key, {"sub": ""})
    with pytest.raises(JWTError):
        verify_jwt(token)


def test_reject_when_issuer_not_configured(rsa_key, monkeypatch):
    set_config(KeycloakConfig(issuer="", audience=AUDIENCE))
    token = _make_token(rsa_key)
    with pytest.raises(JWTError, match="not configured"):
        verify_jwt(token)


# ── RequestContext helpers ───────────────────────────────────────────────

def test_has_role_helpers(rsa_key):
    token = _make_token(rsa_key, {
        "realm_access": {"roles": ["solar_engineer", "estimator"]},
    })
    ctx = extract_request_context(verify_jwt(token))

    assert ctx.has_role("solar_engineer") is True
    assert ctx.has_role("platform_super_admin") is False
    assert ctx.has_any_role(["solar_engineer", "tenant_admin"]) is True
    assert ctx.has_any_role(["tenant_admin", "customer"]) is False
    assert ctx.has_all_roles(["solar_engineer", "estimator"]) is True
    assert ctx.has_all_roles(["solar_engineer", "senior_engineer"]) is False


def test_has_scope(rsa_key):
    token = _make_token(rsa_key, {"scope": "openid project:view boq:create"})
    ctx = extract_request_context(verify_jwt(token))

    assert ctx.has_scope("project:view") is True
    assert ctx.has_scope("project:approve") is False


def test_service_account_detection(rsa_key):
    """Client credentials grants have a synthetic preferred_username
    starting with `service-account-`, and azp matching the client_id."""
    token = _make_token(rsa_key, {
        "azp": "solarpro-catalogue-agent",
        "preferred_username": "service-account-solarpro-catalogue-agent",
        "realm_access": {"roles": ["api_service_account"]},
        "scope": "openid",
    })
    ctx = extract_request_context(verify_jwt(token))
    assert ctx.is_service_account is True
    assert ctx.azp == "solarpro-catalogue-agent"


def test_human_user_is_not_service_account(rsa_key):
    """Human users have a real preferred_username -- not flagged as SA."""
    token = _make_token(rsa_key, {
        "azp": "solarpro-web",
        "preferred_username": "marketplace_admin_test",
        "realm_access": {"roles": ["marketplace_admin"]},
    })
    ctx = extract_request_context(verify_jwt(token))
    assert ctx.is_service_account is False


def test_marketplace_scope_parsed_as_tuple(rsa_key):
    token = _make_token(rsa_key, {
        "realm_access": {"roles": ["marketplace_admin"]},
        "marketplace_scope": "transformers,hv_cables,lv_cables",
    })
    ctx = extract_request_context(verify_jwt(token))
    assert ctx.marketplace_scope == ("transformers", "hv_cables", "lv_cables")
