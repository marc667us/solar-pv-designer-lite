"""
Inter-service HTTP helper for SolarPro AI agents.

Phase 3 tasks 16 + 17 of docs/SECURITY_MIGRATION_KEYCLOAK.md. When an
agent needs to call back into the SolarPro API (e.g. the catalogue
agent updating a product, the report agent writing to a job queue),
this is the ONLY supported channel. It guarantees:

  * Outbound requests carry a fresh service-account JWT in the
    `Authorization: Bearer` header (no shared API keys, no static
    secrets in agent code).
  * Tokens come from `app.security.service_account_client` which
    handles per-client caching + 30 s expiry leeway.
  * The agent's identity is auditable downstream because `azp` on the
    JWT names the SA client (per Phase 3 `_audit_denial` + the
    heartbeat route's audit row).
  * Parallel-run safe: when `KEYCLOAK_ENABLED` is unset the helper
    falls back to issuing the request without an Authorization header
    so the legacy code path keeps working.

Today no agent calls SolarPro internally -- the marketplace agents
only talk to OpenRouter / Ollama (external LLM providers, distinct
auth surface). This module is the forward-compat channel: any future
agent-to-SolarPro call MUST go through `agent_request()` / `agent_get`
/ `agent_post` so the SA broker is the single chokepoint.

Per the Project Execution Directive §14 the human-in-the-loop checks
(approval for email send, payment, delete, etc.) still apply on the
**server side** of the SolarPro API; this helper just makes sure the
caller can be identified.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests

from app.security.service_account_client import (
    authorization_header,
    ServiceAccountError,
)


log = logging.getLogger(__name__)


DEFAULT_TIMEOUT = 10.0


def _keycloak_enabled() -> bool:
    return os.environ.get("KEYCLOAK_ENABLED", "").lower() in (
        "1", "true", "yes", "on",
    )


def agent_request(
    method: str,
    client_id: str,
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    **kwargs,
) -> requests.Response:
    """Issue an HTTP request signed with the given SA's JWT.

    Args:
        method: 'GET' / 'POST' / 'PUT' / 'DELETE' etc.
        client_id: one of the 5 SA clients in ALLOWED_CLIENT_IDS.
        url: absolute or relative URL to the SolarPro API.
        timeout: connect+read seconds; defaults to 10.

    Other kwargs (json, data, params, headers, ...) are forwarded to
    `requests.request`. If the caller already passes `headers`, the
    Authorization entry is added without disturbing the rest.

    Behaviour
    ---------

    - `KEYCLOAK_ENABLED` off: the call goes through WITHOUT an
      Authorization header. SolarPro's parallel-run middleware accepts
      this (the @require_jwt etc. decorators are pass-throughs). This
      keeps the legacy code path working unchanged.
    - `KEYCLOAK_ENABLED` on: a fresh SA JWT is fetched via the broker
      and attached. ServiceAccountError propagates so the caller knows
      auth failed BEFORE the network call.
    """
    headers = dict(kwargs.pop("headers", {}) or {})

    if _keycloak_enabled():
        try:
            auth = authorization_header(client_id, timeout=timeout)
        except ServiceAccountError:
            # Re-raise so callers don't silently issue an unauthenticated
            # request from an agent that requires SA auth.
            raise
        if auth:
            headers.update(auth)

    return requests.request(method, url, headers=headers, timeout=timeout, **kwargs)


def agent_get(client_id: str, url: str, **kwargs) -> requests.Response:
    return agent_request("GET", client_id, url, **kwargs)


def agent_post(client_id: str, url: str, **kwargs) -> requests.Response:
    return agent_request("POST", client_id, url, **kwargs)


__all__ = ["agent_get", "agent_post", "agent_request"]
