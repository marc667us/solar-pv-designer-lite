"""
Keycloak JWT middleware for SolarPro.

Phase 2 of docs/SECURITY_MIGRATION_KEYCLOAK.md. This module provides the
verification primitives the decorators in `app.security.decorators` use:

- `verify_jwt(token)` -> dict of validated claims, or raises JWTError.
- `extract_request_context(claims)` -> typed RequestContext with
  user_id, tenant_id, roles, scopes, etc.

JWT verification is done locally against Keycloak's JWKS endpoint
(cached + rotated on `kid` mismatch). NO per-request introspection
round-trip -- that scales badly.

Environment variables consumed:

  KEYCLOAK_ISSUER   e.g. https://auth.aiappinvent.com/realms/solarpro
                    (locally: http://localhost:8080/realms/solarpro)
  KEYCLOAK_AUDIENCE default "solarpro-api" -- the JWT `aud` claim that
                    the SolarPro backend resource server expects.
  KEYCLOAK_JWKS_TTL default 300 (5 min). JWKS cache lifetime.

If KEYCLOAK_ISSUER is unset, every verification is a hard FAIL --
matches the Project Directive's "no token = no access" rule, and
prevents accidental auth bypass when the env wasn't set.

NB: this module does NOT import Flask. It's a pure verification layer
the decorator module wraps. That keeps it unit-testable without a
running Flask app.
"""

from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass, field
from typing import Iterable

import requests
from jose import jwt, JWTError, jwk
from jose.exceptions import ExpiredSignatureError, JWTClaimsError

log = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────────

class KeycloakConfig:
    """Resolves Keycloak settings from env at construction time. Re-instantiate
    per process; do not cache across forks."""

    def __init__(
        self,
        issuer: str | None = None,
        audience: str | None = None,
        jwks_ttl_seconds: int | None = None,
    ):
        self.issuer = issuer or os.environ.get("KEYCLOAK_ISSUER", "")
        self.audience = audience or os.environ.get("KEYCLOAK_AUDIENCE", "solarpro-api")
        self.jwks_ttl_seconds = jwks_ttl_seconds or int(
            os.environ.get("KEYCLOAK_JWKS_TTL", "300")
        )
        if not self.issuer:
            log.warning(
                "KeycloakConfig: KEYCLOAK_ISSUER is not set. Every verify_jwt() call "
                "will fail until it is. This is intentional -- prevents accidental "
                "auth bypass when the env wasn't configured."
            )

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/certs"

    @property
    def configured(self) -> bool:
        return bool(self.issuer)


# Module-level singleton -- cheap, picked up at first call.
_config: KeycloakConfig | None = None


def get_config() -> KeycloakConfig:
    global _config
    if _config is None:
        _config = KeycloakConfig()
    return _config


def set_config(config: KeycloakConfig) -> None:
    """Override the module-level config (tests + multi-realm callers)."""
    global _config
    _config = config


# ── JWKS cache ───────────────────────────────────────────────────────────

class _JWKSCache:
    """Caches Keycloak's JSON Web Key Set with a TTL. Refreshes on TTL
    expiry OR when verify_jwt is asked for a `kid` the cache doesn't know
    about (handles key rotation without waiting for the TTL)."""

    def __init__(self, config: KeycloakConfig):
        self._config = config
        self._keys: dict[str, dict] = {}
        self._fetched_at: float = 0.0

    def _fetch(self) -> None:
        url = self._config.jwks_url
        if not url or not self._config.configured:
            raise JWTError("KEYCLOAK_ISSUER not configured")
        log.info("fetching JWKS from %s", url)
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        body = resp.json()
        self._keys = {k["kid"]: k for k in body.get("keys", [])}
        self._fetched_at = time.time()

    def get_key(self, kid: str) -> dict:
        ttl_expired = (time.time() - self._fetched_at) > self._config.jwks_ttl_seconds
        if ttl_expired or kid not in self._keys:
            self._fetch()
        if kid not in self._keys:
            # forced refresh didn't find it -- the token's kid is genuinely unknown.
            raise JWTError(f"unknown kid: {kid}")
        return self._keys[kid]

    def reset(self) -> None:
        """Tests + the migration's blue-green key rotation."""
        self._keys = {}
        self._fetched_at = 0.0


_jwks_cache: _JWKSCache | None = None


def get_jwks_cache() -> _JWKSCache:
    global _jwks_cache
    if _jwks_cache is None:
        _jwks_cache = _JWKSCache(get_config())
    return _jwks_cache


def reset_jwks_cache() -> None:
    """For tests + explicit cache invalidation after key rotation."""
    if _jwks_cache is not None:
        _jwks_cache.reset()


# ── Verification ─────────────────────────────────────────────────────────

def verify_jwt(token: str, audience: str | None = None,
               access_token: str | None = None) -> dict:
    """Validate a Keycloak-issued JWT.

    Returns the claims dict on success. Raises JWTError on any failure:
    bad signature, expired token, wrong issuer, wrong audience, missing
    `kid`. The caller (decorator layer) is responsible for translating
    JWTError into the appropriate HTTP response.

    Defence in depth -- python-jose's decode() validates:
      - signature (against the JWKS key we hand it)
      - exp / nbf (default option)
      - iss (issuer)
      - aud (audience)
    We additionally require a non-empty `sub` claim so a malformed
    token can't pass with everything but the subject set.

    `audience` overrides the configured default -- useful when a single
    SolarPro service handles tokens minted for multiple audiences (rare).
    """
    config = get_config()
    if not config.configured:
        raise JWTError("KEYCLOAK_ISSUER not configured")

    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise JWTError(f"malformed JWT header: {e}") from e

    kid = unverified_header.get("kid")
    if not kid:
        raise JWTError("JWT header missing kid")

    try:
        key = get_jwks_cache().get_key(kid)
    except requests.RequestException as e:
        raise JWTError(f"JWKS fetch failed: {e}") from e

    try:
        # access_token is forwarded so python-jose can validate the
        # `at_hash` claim that KC includes in id_tokens by default.
        # Without it, jwt.decode raises JWTClaimsError("No access_token
        # provided to compare against at_hash claim.") and OIDC callback
        # rejects perfectly valid sign-ins (regression caught after
        # Phase 7 cutover with KC 26).
        claims = jwt.decode(
            token,
            key,
            algorithms=[key.get("alg", "RS256")],
            audience=audience or config.audience,
            issuer=config.issuer,
            access_token=access_token,
            options={
                "verify_signature": True,
                "verify_aud": True,
                "verify_iss": True,
                "verify_exp": True,
                "verify_nbf": True,
                "require_exp": True,
                "require_iat": True,
                "require_sub": True,
            },
        )
    except ExpiredSignatureError as e:
        raise JWTError(f"token expired: {e}") from e
    except JWTClaimsError as e:
        raise JWTError(f"claim validation failed: {e}") from e
    except JWTError as e:
        raise JWTError(f"signature verification failed: {e}") from e

    if not claims.get("sub"):
        raise JWTError("missing sub claim")

    return claims


# ── Request context ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class RequestContext:
    """Strongly-typed view of the JWT claims that SolarPro routes need.

    Built once per request by `extract_request_context(claims)`. The
    decorator layer stashes this into Flask's `g` object so route
    handlers can read it without re-parsing the JWT.

    `is_service_account=True` indicates the token came from a
    client-credentials grant (no human user behind it); in that case
    `user_id` is the client's UUID, not a person's sub.
    """

    user_id: str
    tenant_id: str | None
    tenant_name: str | None
    user_type: str | None
    roles: tuple[str, ...]
    scopes: tuple[str, ...]
    supplier_id: str | None
    engineering_company_id: str | None
    marketplace_scope: tuple[str, ...]
    subscription_plan: str | None
    country: str | None
    region: str | None
    is_service_account: bool
    preferred_username: str | None
    email: str | None
    azp: str | None  # authorised party = client id; helps audit
    raw_claims: dict = field(repr=False, compare=False)

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_any_role(self, roles: Iterable[str]) -> bool:
        wanted = set(roles)
        return bool(wanted.intersection(self.roles))

    def has_all_roles(self, roles: Iterable[str]) -> bool:
        return set(roles).issubset(self.roles)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def extract_request_context(claims: dict) -> RequestContext:
    """Turn the raw JWT claims dict into a RequestContext."""
    realm_access = claims.get("realm_access") or {}
    roles = tuple(realm_access.get("roles") or [])
    scope_str = claims.get("scope") or ""
    scopes = tuple(s for s in scope_str.split() if s)

    marketplace_scope_raw = claims.get("marketplace_scope") or ""
    marketplace_scope = tuple(
        s.strip() for s in marketplace_scope_raw.split(",") if s.strip()
    )

    # Client-credentials grants carry typ=Bearer + a synthetic sub equal
    # to the service-account user id. Keycloak sets azp to the client id.
    is_service_account = (
        claims.get("azp", "").startswith("solarpro-")
        and not claims.get("preferred_username", "").startswith(
            ("engineer_", "supplier_", "marketplace_", "tenant_", "platform_",
             "procurement_", "catalogue_", "finance_", "support_", "customer_",
             "senior_", "electrician_")
        )
        and "service-account-" in (claims.get("preferred_username") or "")
    )

    return RequestContext(
        user_id=str(claims["sub"]),
        tenant_id=claims.get("tenant_id"),
        tenant_name=claims.get("tenant_name"),
        user_type=claims.get("user_type"),
        roles=roles,
        scopes=scopes,
        supplier_id=claims.get("supplier_id"),
        engineering_company_id=claims.get("engineering_company_id"),
        marketplace_scope=marketplace_scope,
        subscription_plan=claims.get("subscription_plan"),
        country=claims.get("country"),
        region=claims.get("region"),
        is_service_account=is_service_account,
        preferred_username=claims.get("preferred_username"),
        email=claims.get("email"),
        azp=claims.get("azp"),
        raw_claims=claims,
    )


__all__ = [
    "KeycloakConfig",
    "get_config",
    "set_config",
    "reset_jwks_cache",
    "verify_jwt",
    "RequestContext",
    "extract_request_context",
    "JWTError",  # re-export for callers
]
