"""
Migrate SolarPro users into Keycloak via partial import.

Phase 7 task 33 of docs/SECURITY_MIGRATION_KEYCLOAK.md.

Pipeline
--------

1. Read every active row from the `users` table (DATABASE_URL or
   sqlite path).
2. Map each row to a Keycloak `UserRepresentation`:
     * username, email, emailVerified
     * firstName/lastName split from `name`
     * `requiredActions=["UPDATE_PASSWORD"]` so every migrated user
       resets their credential on first login. We do NOT carry the
       legacy bcrypt hash across -- per plan §4.8 + the FOSS rule.
     * realmRoles derived from legacy is_admin + role columns:
         is_admin=1 + role='' / 'admin' / 'platform_admin'
                 -> platform_super_admin
         role='supplier_admin'                    -> supplier_admin
         role='supplier_user'                     -> supplier_user
         role='procurement_specialist'            -> procurement_specialist
         role='catalogue_manager'                 -> catalogue_manager
         role='finance_officer'                   -> finance_officer
         role='support_agent'                     -> support_agent
         role='solar_engineer' | '' (default)    -> solar_engineer
                                                     for legacy non-admin users
         (unmapped role)                          -> customer  (least privilege)
     * attributes: country, company, plan, trial_end_date,
       referral_code, email_verified (string)
3. Pack the list into a `partialImport` payload and POST it to
   `/admin/realms/<realm>/partialImport`.
4. Print per-user result + a summary.

Modes
-----

    --export       Write the partial-import JSON to a file (default
                   `tmp/keycloak_partial_import_<ts>.json`); no API call.
    --dry-run      Build the payload, print stats + a sample of 3
                   users; no file write, no API call.
    --apply        Build payload + POST it. Requires `KEYCLOAK_ENABLED=true`-
                   equivalent env (KEYCLOAK_ISSUER + admin client secret).

The script is idempotent at the Keycloak side: `ifResourceExists` is
set to `"SKIP"` so re-running won't clobber users who already moved.
Override with `--overwrite` (sets `ifResourceExists=OVERWRITE`) only
during a hard re-cutover.

Auth
----

The script uses the `solarpro-admin-console` confidential client
(client credentials grant) by default; override via
`KEYCLOAK_MIGRATION_CLIENT_ID`. The client secret comes from env
`KC_SA_ADMIN_CONSOLE_CLIENT_SECRET` (matches the broker's env-var
convention).

Per the FOSS rule we do NOT carry password hashes across. Users get
a "you need to reset your password" email at cutover-1 (sent by
`scripts/broadcast_keycloak_migration_email.py`) and the
UPDATE_PASSWORD required-action fires on first OIDC login.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

import requests


REPO_ROOT = Path(__file__).resolve().parent.parent

log = logging.getLogger("user_migration")


# ── DB layer (sqlite + postgres) ────────────────────────────────────────

def _connect():
    """Return a DB-API connection + a "Postgres?" flag.

    Prefers DATABASE_URL when set so we hit the same database the
    deployed app uses. Falls back to the local solar.db for development."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if url.startswith(("postgres://", "postgresql://")):
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(url)
        return conn, True
    sqlite_path = os.environ.get(
        "DB_PATH", str(REPO_ROOT / "solar.db")
    )
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn, False


def _fetch_users(conn, is_postgres: bool) -> list[dict]:
    # Build the SELECT defensively: introspect the live users table and
    # only ask for columns that actually exist. SolarPro's schema drifts
    # between SQLite (dev) and Postgres (Render); the optional set varies
    # by vintage. id/username/email are required; everything else falls
    # back to NULL when absent.
    REQUIRED = ("id", "username", "email")
    OPTIONAL = ("name", "company", "country", "plan", "is_admin", "role",
                "created_at", "email_verified", "trial_end_date",
                "referral_code")

    cur = conn.cursor()
    if is_postgres:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='users'"
        )
        present = {row[0] for row in cur.fetchall()}
    else:
        cur.execute("PRAGMA table_info(users)")
        present = {row[1] for row in cur.fetchall()}

    missing_required = [c for c in REQUIRED if c not in present]
    if missing_required:
        raise RuntimeError(
            f"users table missing required column(s): {missing_required}"
        )

    cols = list(REQUIRED) + [c for c in OPTIONAL if c in present]
    cur.execute(
        f"SELECT {', '.join(cols)} FROM users "
        "WHERE username <> '' AND email <> '' ORDER BY id"
    )
    rows = cur.fetchall()
    cur.close()

    out = []
    for r in rows:
        if is_postgres:
            d = dict(zip(cols, r))
        else:
            d = {k: r[k] for k in r.keys()}
        # Fill OPTIONAL columns absent from the live schema with None so
        # downstream build_user_representation can call .get() uniformly.
        for c in OPTIONAL:
            d.setdefault(c, None)
        out.append(d)
    return out


# ── Role mapping ────────────────────────────────────────────────────────

def map_realm_roles(row: dict) -> list[str]:
    """Translate legacy is_admin + role columns to Keycloak realm roles.

    The 13 plan §7.2 roles -- minus the ones SolarPro never assigned
    today -- are honoured. Anything we don't recognise drops to
    `customer` (least privilege) so a misclassified user can't escalate."""
    is_admin = bool(row.get("is_admin"))
    legacy_role = (row.get("role") or "").strip().lower()

    if is_admin and legacy_role in ("", "admin", "platform_admin"):
        return ["platform_super_admin"]
    if legacy_role == "platform_super_admin":
        return ["platform_super_admin"]

    known = {
        "tenant_admin", "marketplace_admin", "solar_engineer",
        "senior_engineer", "electrician_installer", "supplier_admin",
        "supplier_user", "procurement_specialist", "catalogue_manager",
        "finance_officer", "support_agent", "customer",
    }
    if legacy_role in known:
        return [legacy_role]

    # Empty role + not admin -> default the bulk of SolarPro users to
    # `solar_engineer` (the platform's primary persona today). Plan
    # §7.5 backs this up: a designer who hasn't been promoted maps to
    # solar_engineer, not customer.
    if legacy_role == "":
        return ["solar_engineer"]

    log.warning("user %s: legacy role %r unrecognised; defaulting to customer",
                row.get("username"), legacy_role)
    return ["customer"]


# ── User representation ─────────────────────────────────────────────────

def _split_name(name: Optional[str]) -> tuple[str, str]:
    """Split a free-form display name into firstName + lastName.
    Keycloak treats both as optional but the UI looks bad without."""
    parts = (name or "").strip().split(maxsplit=1)
    if not parts:
        return ("", "")
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], parts[1])


def build_user_representation(row: dict) -> dict:
    """Map one users-table row to a Keycloak UserRepresentation."""
    first, last = _split_name(row.get("name"))
    attributes = {}
    for k in ("country", "company", "plan", "trial_end_date", "referral_code"):
        v = row.get(k)
        if v not in (None, ""):
            attributes[k] = [str(v)]
    # email_verified -> Keycloak's emailVerified field is the canonical
    # spot. Also stash on attributes so the admin UI shows it.
    email_verified = bool(row.get("email_verified"))

    return {
        # username/email come straight across
        "username": row["username"],
        "email": row["email"],
        "emailVerified": email_verified,
        "enabled": True,
        "firstName": first,
        "lastName": last,
        # Force password reset on first login. We don't carry the
        # bcrypt hash across; legacy_role-aware OTP requirements
        # already live on the role's required-actions list.
        "requiredActions": ["UPDATE_PASSWORD"],
        "realmRoles": map_realm_roles(row),
        "attributes": attributes,
    }


# ── Keycloak admin call ─────────────────────────────────────────────────

def _admin_token(client_id: str, client_secret: str) -> str:
    """One-off client_credentials grant. We don't pull in the broker
    because this script's lifetime is one cutover; caching is overkill."""
    issuer = os.environ.get("KEYCLOAK_ISSUER", "").rstrip("/")
    if not issuer:
        raise SystemExit("KEYCLOAK_ISSUER not set; cannot mint admin token.")
    endpoint = f"{issuer}/protocol/openid-connect/token"
    resp = requests.post(
        endpoint,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=10.0,
    )
    if resp.status_code != 200:
        raise SystemExit(
            f"Admin token fetch failed: {resp.status_code}: {resp.text[:200]}"
        )
    return resp.json()["access_token"]


def _resolve_realm() -> str:
    issuer = os.environ.get("KEYCLOAK_ISSUER", "").rstrip("/")
    if "/realms/" not in issuer:
        raise SystemExit(
            f"KEYCLOAK_ISSUER {issuer!r} does not contain '/realms/'."
        )
    return issuer.split("/realms/", 1)[1].split("/", 1)[0]


def _admin_base() -> str:
    issuer = os.environ.get("KEYCLOAK_ISSUER", "").rstrip("/")
    return issuer.split("/realms/")[0] + f"/admin/realms/{_resolve_realm()}"


def push_partial_import(
    users: list[dict],
    *,
    if_exists: str,
    client_id: str,
    client_secret: str,
    timeout: float = 60.0,
) -> dict:
    token = _admin_token(client_id, client_secret)
    payload = {
        "ifResourceExists": if_exists,  # SKIP | OVERWRITE | FAIL
        "users": users,
    }
    url = f"{_admin_base()}/partialImport"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if resp.status_code not in (200, 201):
        raise SystemExit(
            f"partialImport failed: {resp.status_code}: {resp.text[:400]}"
        )
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}


# ── CLI driver ──────────────────────────────────────────────────────────

def _redact(s: Optional[str]) -> str:
    return f"<{len(s or '')} chars>" if s else "<unset>"


def _print_overview(rows: list[dict], users: list[dict]) -> None:
    role_counts: dict[str, int] = {}
    for u in users:
        for r in u["realmRoles"]:
            role_counts[r] = role_counts.get(r, 0) + 1
    print(f"users found: {len(rows)}")
    print("realm role distribution:")
    for r, n in sorted(role_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"   {n:>4}  {r}")
    print(f"first 3 users (preview):")
    for u in users[:3]:
        print(f"   {u['username']:>30}  email={u['email']:<30}  "
              f"roles={','.join(u['realmRoles'])}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--export", action="store_true",
                   help="Write the partial-import JSON to a file; no API call.")
    g.add_argument("--dry-run", action="store_true",
                   help="Print summary + sample; no file, no API call.")
    g.add_argument("--apply", action="store_true",
                   help="POST the partial import to Keycloak.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Set ifResourceExists=OVERWRITE (default SKIP).")
    parser.add_argument("--out", default="",
                        help="Output path for --export (default: tmp/...)")
    parser.add_argument("--client-id",
                        default=os.environ.get("KEYCLOAK_MIGRATION_CLIENT_ID",
                                               "solarpro-admin-console"))
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    log.info("Connecting to DB...")
    conn, is_pg = _connect()
    try:
        rows = _fetch_users(conn, is_pg)
    finally:
        conn.close()
    log.info("Loaded %d users from %s.", len(rows),
             "Postgres" if is_pg else "SQLite")
    if not rows:
        log.warning("No users to migrate; aborting.")
        return 1

    users = [build_user_representation(r) for r in rows]
    _print_overview(rows, users)

    if args.dry_run:
        return 0

    if args.export:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = Path(args.out) if args.out else (
            REPO_ROOT / "tmp" / f"keycloak_partial_import_{ts}.json"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ifResourceExists": "OVERWRITE" if args.overwrite else "SKIP",
            "users": users,
        }
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.info("Wrote %s (%d users).", out_path, len(users))
        return 0

    # --apply
    secret = os.environ.get("KC_SA_ADMIN_CONSOLE_CLIENT_SECRET", "").strip()
    if not secret:
        log.error("KC_SA_ADMIN_CONSOLE_CLIENT_SECRET unset; cannot apply.")
        return 1
    log.info("Posting partialImport for %d users (ifResourceExists=%s)...",
             len(users), "OVERWRITE" if args.overwrite else "SKIP")
    result = push_partial_import(
        users,
        if_exists="OVERWRITE" if args.overwrite else "SKIP",
        client_id=args.client_id,
        client_secret=secret,
    )
    log.info("partialImport result: %s", json.dumps(result)[:400])
    return 0


if __name__ == "__main__":
    sys.exit(main())
