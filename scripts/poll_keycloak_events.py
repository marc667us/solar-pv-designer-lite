"""
Keycloak event poller -- SPI-less fallback for Phase 6 audit unification.

Plan §19 task 29 alt-path. The plan's preferred delivery channel is a
custom event-listener JAR that POSTs events to /api/keycloak/events.
On hosts where installing an SPI is impossible (Render free tier, no
sudo on the Keycloak container, etc.) this script polls Keycloak's
admin REST endpoints on a cron and writes the events to SolarPro's
`audit_logs` via the same `process_event` path.

Endpoints polled
----------------

  GET /admin/realms/<realm>/events?first=<n>&max=<m>          -- user events
  GET /admin/realms/<realm>/admin-events?first=<n>&max=<m>    -- admin events

Auth
----

Uses the `solarpro-admin-console` client (or a dedicated `solarpro-event-poller`
client if provisioned) with a service-account JWT obtained via the
existing Phase 3 broker.

Resumption
----------

`tmp/keycloak_event_checkpoint.json` carries the last seen `time` per
endpoint. On restart we resume where we stopped. First run pulls only
events newer than `--initial-window` (default 30 minutes) so we don't
flood the table with weeks of backlog.

Usage
-----

    # one-shot poll (intended for cron / Render scheduled job)
    KEYCLOAK_ENABLED=true \
    KEYCLOAK_ISSUER=https://auth.aiappinvent.com/realms/solarpro \
    KC_SA_ADMIN_CONSOLE_CLIENT_SECRET=... \
    python scripts/poll_keycloak_events.py --once

    # continuous loop (sleep 30s between polls)
    python scripts/poll_keycloak_events.py --interval 30

    # dry-run -- print what would be processed, no writes
    python scripts/poll_keycloak_events.py --once --dry-run

Exit codes
    0  poll completed
    1  configuration error
    2  Keycloak unreachable
    3  audit writer failed for >= 50% of events (cron should alert)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests


REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT = REPO_ROOT / "tmp" / "keycloak_event_checkpoint.json"

# We borrow the admin-console SA client; in production the realm
# export can add a dedicated `solarpro-event-poller` confidential
# client with view-events scope. The lookup table maps the env-var
# convention from app.security.service_account_client.
POLLER_CLIENT_ID = os.environ.get(
    "KEYCLOAK_POLLER_CLIENT_ID", "solarpro-admin-console"
)


log = logging.getLogger("kc_poller")


def _resolve_realm() -> str:
    """Pull the realm name out of KEYCLOAK_ISSUER."""
    issuer = os.environ.get("KEYCLOAK_ISSUER", "").rstrip("/")
    if "/realms/" not in issuer:
        return ""
    return issuer.split("/realms/", 1)[1].split("/", 1)[0]


def _admin_base() -> str:
    issuer = os.environ.get("KEYCLOAK_ISSUER", "").rstrip("/")
    if not issuer:
        return ""
    return issuer.split("/realms/")[0] + f"/admin/realms/{_resolve_realm()}"


def _load_checkpoint() -> dict:
    try:
        return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_checkpoint(state: dict) -> None:
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _get_token() -> Optional[str]:
    """Lazy import so this script can be invoked without the full
    SolarPro environment loaded."""
    sys.path.insert(0, str(REPO_ROOT))
    from app.security.service_account_client import (
        get_service_account_token, ServiceAccountError,
    )
    try:
        return get_service_account_token(POLLER_CLIENT_ID)
    except ServiceAccountError as e:
        log.error("token fetch failed: %s", e)
        return None


def _fetch(endpoint: str, token: str, params: dict,
           timeout: float = 10.0) -> Optional[list]:
    try:
        r = requests.get(
            endpoint,
            params=params,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=timeout,
        )
    except requests.RequestException as e:
        log.error("GET %s failed: %s", endpoint, e)
        return None
    if r.status_code != 200:
        log.error("GET %s -> %s: %s", endpoint, r.status_code, r.text[:200])
        return None
    try:
        return r.json()
    except ValueError:
        log.error("Non-JSON response from %s", endpoint)
        return None


def _process(events: list, *, dry_run: bool) -> tuple[int, int]:
    """Pipe each event through app.security.keycloak_events.process_event.

    Returns (stored, dropped)."""
    sys.path.insert(0, str(REPO_ROOT))
    from app.security.keycloak_events import process_event

    stored = dropped = 0
    for evt in events:
        if dry_run:
            print(json.dumps(evt)[:200])
            stored += 1
            continue
        result = process_event(evt)
        if result == "stored":
            stored += 1
        elif result == "duplicate":
            continue
        else:
            dropped += 1
            log.warning("event %s: %s", evt.get("id"), result)
    return stored, dropped


def _epoch_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def poll_once(*, initial_window_minutes: int, dry_run: bool) -> int:
    """One sweep of both endpoints. Returns exit code."""
    realm = _resolve_realm()
    if not realm:
        log.error("KEYCLOAK_ISSUER not set or malformed; cannot resolve realm.")
        return 1

    admin_base = _admin_base()
    token = _get_token()
    if token is None:
        return 1

    checkpoint = _load_checkpoint()
    default_floor = _epoch_ms(
        datetime.now(timezone.utc) - timedelta(minutes=initial_window_minutes)
    )

    grand_stored = grand_dropped = 0
    for kind, path in [("user", "events"), ("admin", "admin-events")]:
        from_ts = int(checkpoint.get(f"{kind}_from") or default_floor)
        url = f"{admin_base}/{path}"
        events = _fetch(url, token, {"dateFrom": from_ts, "max": 100})
        if events is None:
            return 2
        # Sort oldest-first so we update the checkpoint to the newest
        # `time` value seen.
        events.sort(key=lambda e: e.get("time") or 0)
        stored, dropped = _process(events, dry_run=dry_run)
        if events:
            checkpoint[f"{kind}_from"] = int(events[-1].get("time") or from_ts) + 1
        log.info("%s events: stored=%d dropped=%d", kind, stored, dropped)
        grand_stored += stored
        grand_dropped += dropped

    if not dry_run:
        _save_checkpoint(checkpoint)

    total = grand_stored + grand_dropped
    if total and grand_dropped / total >= 0.5:
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--once", action="store_true", help="One poll, then exit.")
    parser.add_argument("--interval", type=int, default=30,
                        help="Sleep seconds between polls (continuous mode).")
    parser.add_argument("--initial-window", type=int, default=30,
                        help="On first run, pull events from this many minutes ago.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print events without writing to audit_logs.")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    level = logging.WARNING if args.quiet else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")

    if args.once:
        return poll_once(
            initial_window_minutes=args.initial_window, dry_run=args.dry_run,
        )

    while True:
        rc = poll_once(
            initial_window_minutes=args.initial_window, dry_run=args.dry_run,
        )
        if rc != 0:
            log.warning("poll returned %s; will retry in %ss", rc, args.interval)
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
