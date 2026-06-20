"""
Provision or update the `solarpro-keycloak` web service on Render via
the Render REST API. Designed to be run from
.github/workflows/deploy-keycloak.yml -- not for interactive use.

What it does:
  1. Resolves the Render owner ID (the account that owns the API key).
  2. Searches for an existing service named "solarpro-keycloak".
     * If absent: POST /v1/services to create it (Dockerfile build,
       free plan, oregon region, mounted at /, env vars from the env
       block below).
     * If present: PATCH each env var entry to match the env block
       (rotated KC_DB_PASSWORD or updated KC_DB_URL will land here).
  3. Triggers a deploy via POST /v1/services/{id}/deploys.
  4. Writes the service's live URL to /tmp/kc_service_url.txt so the
     calling workflow can pick it up.

Required env vars (workflow injects):
  RENDER_API_KEY               Render personal API key with create+deploy scope.
  GITHUB_REPOSITORY            owner/repo, e.g. marc667us/solar-pv-designer-lite.
  KC_DB_URL                    JDBC URL pointing at solarpro-postgres ?currentSchema=keycloak.
  KC_DB_PASSWORD               password for the keycloak_app role.
  KC_BOOTSTRAP_ADMIN_PASSWORD  master-realm root admin password (optional;
                               falls back to a generated value if unset).

Output: prints actions to stdout; writes service URL to /tmp/kc_service_url.txt.
Exit:   non-zero on any unrecoverable API failure.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
from typing import Optional

import requests

API = "https://api.render.com/v1"
SERVICE_NAME = "solarpro-keycloak"
DOCKERFILE_PATH = "./keycloak/render/Dockerfile"
DOCKER_CONTEXT = "."
BRANCH = "master"
# Render checks healthCheckPath against the routed port (=main HTTP).
# /health and /metrics live on the management port (9000) which Render
# does NOT expose externally, so we use a main-port endpoint that exists
# from boot: master realm's OIDC discovery doc (created automatically by
# KC's first-boot bootstrap).
HEALTH_PATH = "/realms/master/.well-known/openid-configuration"


def _hdrs() -> dict:
    """Bearer auth header used for every Render API call."""
    key = os.environ["RENDER_API_KEY"]
    return {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _get(path: str, **params) -> requests.Response:
    """GET helper that raises on >=400."""
    r = requests.get(f"{API}{path}", headers=_hdrs(), params=params, timeout=30)
    if r.status_code >= 400:
        sys.stderr.write(f"GET {path} -> {r.status_code}: {r.text[:500]}\n")
        r.raise_for_status()
    return r


def _post(path: str, body: dict) -> requests.Response:
    """POST helper that raises on >=400 (except idempotent 4xx we expect)."""
    r = requests.post(f"{API}{path}", headers=_hdrs(),
                      data=json.dumps(body), timeout=60)
    if r.status_code >= 400:
        sys.stderr.write(f"POST {path} -> {r.status_code}: {r.text[:1500]}\n")
        r.raise_for_status()
    return r


def _put(path: str, body: list) -> requests.Response:
    """PUT helper for the env-vars bulk endpoint."""
    r = requests.put(f"{API}{path}", headers=_hdrs(),
                     data=json.dumps(body), timeout=60)
    if r.status_code >= 400:
        sys.stderr.write(f"PUT {path} -> {r.status_code}: {r.text[:1500]}\n")
        r.raise_for_status()
    return r


def resolve_owner_id() -> str:
    """Find the owner that the API key has access to. The first one is
    used; an API key only belongs to one account in Render's model."""
    r = _get("/owners", limit=20)
    items = r.json()
    if not isinstance(items, list) or not items:
        raise RuntimeError("no owners found for this API key")
    owner = items[0].get("owner", items[0])
    owner_id = owner.get("id")
    if not owner_id:
        raise RuntimeError(f"owner without id: {owner!r}")
    print(f"owner: {owner.get('name', '?')!r} ({owner_id})")
    return owner_id


def find_service() -> Optional[dict]:
    """Return the service dict if a service named SERVICE_NAME exists,
    else None. Render's /v1/services accepts a name filter."""
    r = _get("/services", name=SERVICE_NAME, limit=20)
    for item in r.json():
        svc = item.get("service", item)
        if svc.get("name") == SERVICE_NAME:
            return svc
    return None


def env_block() -> list:
    """The list of env vars the service should run with. Sensitive values
    come from the workflow env; non-sensitive are hardcoded here."""
    return [
        # ── Database ──
        {"key": "KC_DB", "value": "postgres"},
        {"key": "KC_DB_URL", "value": os.environ["KC_DB_URL"]},
        {"key": "KC_DB_USERNAME", "value": "keycloak_app"},
        {"key": "KC_DB_PASSWORD", "value": os.environ["KC_DB_PASSWORD"]},
        # ── Master-realm bootstrap admin ──
        {"key": "KC_BOOTSTRAP_ADMIN_USERNAME", "value": "admin"},
        {"key": "KC_BOOTSTRAP_ADMIN_PASSWORD",
         "value": os.environ.get("KC_BOOTSTRAP_ADMIN_PASSWORD")
                  or secrets.token_urlsafe(32)},
        # ── Hostname / proxy (Render terminates TLS) ──
        # KC_HOSTNAME accepts a full URL in KC 26; passing the scheme
        # forces issuer URLs to be https:// even though the container
        # itself speaks HTTP (Render's load balancer terminates TLS).
        # When DNS for auth.aiappinvent.com is set up, swap this URL to
        # the custom domain and re-run the deploy workflow.
        {"key": "KC_HOSTNAME",
         "value": os.environ.get("KC_HOSTNAME_URL",
                                 "https://solarpro-keycloak.onrender.com")},
        {"key": "KC_HOSTNAME_STRICT", "value": "false"},
        # KC_PROXY=edge is the legacy flag; KC_PROXY_HEADERS=xforwarded
        # is the KC 26 way of telling KC to trust X-Forwarded-* from the
        # Render load balancer.
        {"key": "KC_PROXY_HEADERS", "value": "xforwarded"},
        # ── Observability ──
        {"key": "KC_METRICS_ENABLED", "value": "true"},
        {"key": "KC_HEALTH_ENABLED", "value": "true"},
        {"key": "KC_LOG", "value": "console"},
        {"key": "KC_LOG_LEVEL", "value": "INFO"},
    ]


def create_service(owner_id: str) -> dict:
    """POST /v1/services to create the Docker web service from scratch."""
    repo_full = os.environ["GITHUB_REPOSITORY"]
    repo_url = f"https://github.com/{repo_full}"

    body = {
        "type": "web_service",
        "name": SERVICE_NAME,
        "ownerId": owner_id,
        "repo": repo_url,
        "branch": BRANCH,
        "rootDir": "",
        "autoDeploy": "no",       # deploys via the workflow
        "serviceDetails": {
            "env": "docker",
            "envSpecificDetails": {
                "dockerfilePath": DOCKERFILE_PATH,
                "dockerContext": DOCKER_CONTEXT,
            },
            "plan": "free",
            "region": "oregon",
            "healthCheckPath": HEALTH_PATH,
            "numInstances": 1,
        },
        "envVars": env_block(),
    }
    print(f"creating service {SERVICE_NAME!r} ...")
    r = _post("/services", body)
    payload = r.json()
    # Response wraps {"service": {...}, "deployId": "..."}
    svc = payload.get("service", payload)
    print(f"created service id: {svc.get('id')}")
    return svc


def update_env_vars(service_id: str) -> None:
    """Render's bulk env-var endpoint: PUT replaces the whole list."""
    print("updating env vars (PUT /services/{id}/env-vars) ...")
    _put(f"/services/{service_id}/env-vars", env_block())


def update_service_config(service_id: str) -> None:
    """PATCH service-level config (healthCheckPath etc.). Needed when
    the initial service create used a stale value; subsequent runs
    bring the service back into sync without re-creating."""
    print("updating service config (PATCH /services/{id}) ...")
    body = {
        "serviceDetails": {
            "healthCheckPath": HEALTH_PATH,
        }
    }
    r = requests.patch(f"{API}/services/{service_id}",
                       headers=_hdrs(),
                       data=json.dumps(body), timeout=60)
    if r.status_code >= 400:
        # PATCH may 422 if the body shape is wrong; surface but don't
        # block deploy since healthCheckPath is non-critical.
        sys.stderr.write(f"PATCH /services/{service_id} -> "
                         f"{r.status_code}: {r.text[:500]}\n")
        print("  (continuing despite PATCH failure -- healthCheckPath"
              " stays at previous value)")


def trigger_deploy(service_id: str) -> dict:
    """POST a fresh deploy. clearCache=do_not_clear so the realm import
    is preserved; we want incremental KC restarts.

    Render's POST /deploys sometimes returns 202 with an empty body
    (e.g. when a deploy is already in progress from the create call).
    We tolerate empty bodies and return {} so the caller can keep going."""
    print("triggering deploy ...")
    r = _post(f"/services/{service_id}/deploys",
              {"clearCache": "do_not_clear"})
    if not r.text.strip():
        print("  (empty 2xx body -- treating as queued)")
        return {"id": None, "status": "queued"}
    try:
        return r.json()
    except ValueError:
        print(f"  (non-JSON 2xx body: {r.text[:120]!r}) -- treating as queued")
        return {"id": None, "status": "queued"}


def main() -> int:
    owner_id = resolve_owner_id()
    svc = find_service()
    if svc is None:
        svc = create_service(owner_id)
    else:
        print(f"existing service id: {svc.get('id')}")
        update_env_vars(svc["id"])
        update_service_config(svc["id"])

    deploy = trigger_deploy(svc["id"])
    print(f"deploy queued: {deploy.get('id') or deploy}")

    # Capture the live URL. Render returns serviceDetails.url on the
    # service object once published (.onrender.com hostname).
    url = svc.get("serviceDetails", {}).get("url") or ""
    if not url:
        # Newly created services may not have the URL yet; poll briefly.
        for _ in range(20):
            time.sleep(3)
            r = _get(f"/services/{svc['id']}")
            current = r.json().get("service", r.json())
            url = current.get("serviceDetails", {}).get("url") or ""
            if url:
                svc = current
                break
    if not url:
        raise RuntimeError("service URL not available after 60s")

    print(f"service URL: {url}")
    with open("/tmp/kc_service_url.txt", "w", encoding="utf-8") as fh:
        fh.write(url + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
