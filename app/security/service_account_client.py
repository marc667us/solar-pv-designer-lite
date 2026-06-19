"""
Keycloak service-account token broker for SolarPro AI agents.

Phase 3 of docs/SECURITY_MIGRATION_KEYCLOAK.md. When an AI agent calls
back into the SolarPro backend (or any other SolarPro-aware service),
it must present a service-account JWT — NOT share a human user's
session, NOT use the global OpenRouter API key, NOT pass a static
bearer secret around.

This module gives every agent a single function call to get a fresh
token via Keycloak's `client_credentials` grant. Tokens are cached
per-client until ~30s before expiry, so a hot agent loop doesn't melt
Keycloak.

Five service-account clients are declared in
`docs/keycloak/realm-export.json` (Phase 1):

    solarpro-catalogue-agent   — read supplier catalogue, write
                                 extraction queue, suggest product update
    solarpro-tender-agent      — read tender feed, write tender draft
    solarpro-report-agent      — read project + design, write report
    solarpro-email-agent       — read user email, send transactional
    solarpro-payment-agent     — read payment event, write invoice status

Environment variables consumed
------------------------------

  KEYCLOAK_TOKEN_ENDPOINT  Optional explicit override. Default is
                           derived from KEYCLOAK_ISSUER (used by the
                           Phase 2 middleware) as
                           `{issuer}/protocol/openid-connect/token`.
  KEYCLOAK_ISSUER          Same env the middleware reads. Falls back here
                           if KEYCLOAK_TOKEN_ENDPOINT is unset.
  KEYCLOAK_ENABLED         Master parallel-run switch. When unset/false
                           every call returns None so callers degrade
                           gracefully to the pre-Keycloak path.
  KC_SA_<NAME>_CLIENT_SECRET
                           Per-client secret. NAME is the client_id with
                           the `solarpro-` prefix stripped, hyphens
                           replaced with underscores, uppercased.
                           e.g. `solarpro-catalogue-agent` ->
                                `KC_SA_CATALOGUE_AGENT_CLIENT_SECRET`.

The 90-day rotation of those secrets is owned by the Vault broker
described in `[[project-solar-pv-secrets-engine-proposal-v3]]` — this
module just reads whatever is in env at the moment.

Thread safety
-------------

The cache uses a module-level threading.Lock. Flask runs requests on
multiple threads under Waitress / Gunicorn so the lock is mandatory.
Cache entries are immutable tuples; concurrent reads after the lock is
released are safe.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

import requests


log = logging.getLogger(__name__)


KEYCLOAK_ENABLED_ENV = "KEYCLOAK_ENABLED"


# The exhaustive list of allowed service-account client IDs. Anything
# outside this set is a programming error — fail loudly so a typo in an
# agent loader doesn't silently degrade to "no token".
ALLOWED_CLIENT_IDS = frozenset({
    "solarpro-catalogue-agent",
    "solarpro-tender-agent",
    "solarpro-report-agent",
    "solarpro-email-agent",
    "solarpro-payment-agent",
})


# Refresh tokens this many seconds before their stated expiry, so we
# never hand out a token that expires mid-flight on a slow backend call.
EXPIRY_LEEWAY_SECONDS = 30

# HTTP timeout for the token endpoint. Keycloak should respond in
# milliseconds; a slow call is a misconfiguration we want to surface.
DEFAULT_HTTP_TIMEOUT = 5.0


class ServiceAccountError(RuntimeError):
    """Hard failure fetching a service-account token.

    Callers who can fall back to a deterministic path (e.g. the
    marketplace LLM agents) should catch this and continue. Callers
    that *must* have a JWT (e.g. an outbound webhook signed by the
    agent's identity) should propagate it as a 5xx."""


@dataclass(frozen=True)
class _CacheEntry:
    token: str
    expires_at: float  # epoch seconds


def _keycloak_enabled() -> bool:
    """Parallel-run master switch. When false the broker hands back
    None and callers stay on the legacy auth path."""
    return os.environ.get(KEYCLOAK_ENABLED_ENV, "").lower() in (
        "1", "true", "yes", "on",
    )


def _env_key_for(client_id: str) -> str:
    """Map a service-account client_id to its env-var name.

        solarpro-catalogue-agent  ->  KC_SA_CATALOGUE_AGENT_CLIENT_SECRET
        solarpro-tender-agent     ->  KC_SA_TENDER_AGENT_CLIENT_SECRET
    """
    suffix = client_id[len("solarpro-"):] if client_id.startswith("solarpro-") else client_id
    suffix = suffix.replace("-", "_").upper()
    return f"KC_SA_{suffix}_CLIENT_SECRET"


def _resolve_token_endpoint() -> str:
    """Prefer the explicit endpoint env. Fall back to the middleware's
    KEYCLOAK_ISSUER. Raise if neither is set."""
    explicit = os.environ.get("KEYCLOAK_TOKEN_ENDPOINT", "").strip()
    if explicit:
        return explicit
    issuer = os.environ.get("KEYCLOAK_ISSUER", "").strip()
    if not issuer:
        raise ServiceAccountError(
            "Neither KEYCLOAK_TOKEN_ENDPOINT nor KEYCLOAK_ISSUER is set; "
            "cannot fetch service-account token."
        )
    return f"{issuer.rstrip('/')}/protocol/openid-connect/token"


# ── Cache ────────────────────────────────────────────────────────────────

_cache: dict[str, _CacheEntry] = {}
_cache_lock = threading.Lock()


def clear_cache() -> None:
    """Drop every cached token. Tests call this; production callers
    should not need to."""
    with _cache_lock:
        _cache.clear()


def _cached_token(client_id: str, *, now: float) -> Optional[str]:
    with _cache_lock:
        entry = _cache.get(client_id)
    if entry is None:
        return None
    if entry.expires_at - now <= EXPIRY_LEEWAY_SECONDS:
        return None
    return entry.token


def _store_token(client_id: str, token: str, expires_in: int, *, now: float) -> None:
    entry = _CacheEntry(token=token, expires_at=now + max(0, int(expires_in)))
    with _cache_lock:
        _cache[client_id] = entry


# ── Public API ───────────────────────────────────────────────────────────

def get_service_account_token(
    client_id: str,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    _now: Optional[float] = None,
) -> Optional[str]:
    """Return a valid service-account JWT for `client_id`, or None
    when Keycloak is disabled (parallel-run mode).

    Raises ServiceAccountError if Keycloak is enabled but the client_id
    is unknown, the secret env var is missing, or the token endpoint
    responds with an error.

    The `_now` kwarg lets tests freeze time without monkey-patching
    `time.time()` globally.
    """
    if client_id not in ALLOWED_CLIENT_IDS:
        raise ServiceAccountError(
            f"Unknown service-account client_id: {client_id!r}. "
            f"Allowed: {sorted(ALLOWED_CLIENT_IDS)}"
        )

    if not _keycloak_enabled():
        # Parallel-run: legacy auth path still works; don't try to
        # contact Keycloak (it may not even be running yet).
        return None

    now = time.time() if _now is None else _now

    cached = _cached_token(client_id, now=now)
    if cached is not None:
        return cached

    secret_env = _env_key_for(client_id)
    secret = os.environ.get(secret_env, "").strip()
    if not secret:
        raise ServiceAccountError(
            f"Missing client secret env var {secret_env} for {client_id}. "
            "Set it from the Vault broker or .env before invoking the agent."
        )

    endpoint = _resolve_token_endpoint()

    try:
        resp = requests.post(
            endpoint,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": secret,
            },
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise ServiceAccountError(
            f"Network error fetching token for {client_id} from {endpoint}: {e}"
        ) from e

    if resp.status_code != 200:
        # Keycloak echoes the OAuth2 error in JSON when available.
        snippet = (resp.text or "")[:300]
        raise ServiceAccountError(
            f"Token endpoint returned {resp.status_code} for {client_id}: {snippet}"
        )

    try:
        payload = resp.json()
    except ValueError as e:
        raise ServiceAccountError(
            f"Non-JSON response from token endpoint for {client_id}: {e}"
        ) from e

    token = payload.get("access_token")
    expires_in = payload.get("expires_in")
    if not isinstance(token, str) or not token:
        raise ServiceAccountError(
            f"Token endpoint response missing access_token for {client_id}: {payload!r}"
        )
    if not isinstance(expires_in, int) or expires_in <= 0:
        # Conservative default — Keycloak's standard is 300s for SA tokens.
        # If the server omits it, refresh aggressively rather than risk a
        # stale-cached token getting handed to a long-running agent.
        expires_in = 60
        log.warning(
            "Token endpoint omitted expires_in for %s; using conservative 60s.",
            client_id,
        )

    _store_token(client_id, token, expires_in, now=now)
    return token


def authorization_header(
    client_id: str,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
) -> Optional[dict]:
    """Convenience for agents: returns a dict ready to merge into a
    requests / urllib call's headers, or None when Keycloak is off.

        headers = {**default_headers, **(authorization_header(cid) or {})}
    """
    token = get_service_account_token(client_id, timeout=timeout)
    if token is None:
        return None
    return {"Authorization": f"Bearer {token}"}


__all__ = [
    "ALLOWED_CLIENT_IDS",
    "EXPIRY_LEEWAY_SECONDS",
    "ServiceAccountError",
    "authorization_header",
    "clear_cache",
    "get_service_account_token",
]
