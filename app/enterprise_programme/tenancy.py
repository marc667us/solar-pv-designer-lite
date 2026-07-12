"""Enterprise Solar Programme -- tenancy service (rebuild, slice 1).

WHAT THIS IS
------------
The overlay that gives the enterprise module many-users-per-organisation tenancy on
top of an app that is, at the database level, single-user-owned.

THE SAFETY PROPERTY (read before changing anything here)
--------------------------------------------------------
Nothing in this file writes to `projects` or `capital_investment_projects`. Ever.
Existing project ownership (`WHERE id=? AND user_id=?`) is left exactly as it is.
A user's PERSONAL tenant id is deliberately the same deterministic hash the app
already derives for them -- md5('solarpro-tenant-v1:'||user_id) -- so the overlay
lines up with existing rows instead of fighting them.

Real organisations (many users) are separate tenants with generated UUIDs. A user
can belong to several tenants; the "active" one is resolved per request.

Raw SQL with `?` placeholders throughout -- db_adapter rewrites them to `%s` for
Postgres. No ORM in this repo.
"""

from __future__ import annotations

import hashlib
import os
import uuid

from .constants import ORGANISATION_TYPES

_ORG_TYPE_CODES = frozenset(c for c, _ in ORGANISATION_TYPES)


def _is_postgres() -> bool:
    """True when running against Postgres rather than local SQLite."""
    return str(os.environ.get("DATABASE_URL", "")).startswith(
        ("postgres://", "postgresql://")
    )


def personal_tenant_id(user_id: int) -> str:
    """The deterministic tenant UUID this app already derives for a user.

    Input:  integer users.id
    Output: UUID string, identical to Postgres
            `md5('solarpro-tenant-v1:'||user_id)::uuid` (003_rls_tenant.sql:136).

    This MUST stay byte-for-byte compatible with the SQL, because migration 025's
    backfill and this function have to agree on the same id or a user would end up
    with two personal tenants.
    """
    digest = hashlib.md5(f"solarpro-tenant-v1:{user_id}".encode()).hexdigest()
    return str(uuid.UUID(digest))


def apply_enterprise_guc(c, user_id: int | None) -> None:
    """Publish the caller's integer users.id as the `app.current_user_id` GUC.

    Input:  open DB connection, session user id (or None).
    Output: none.

    Why this exists: the app's existing `app.current_user` GUC carries the Keycloak
    *sub*, not users.id, and is '' on the legacy session path. Migration 025's RLS
    policies key on `app.current_user_id`, which nothing else publishes -- so we set
    it ourselves on the connection we already hold. No change to web_app.py needed.
    No-op on SQLite (no RLS there).
    """
    if not user_id or not _is_postgres():
        return
    c.execute("SELECT set_config('app.current_user_id', ?, true)", (str(user_id),))


# --- SQLite fallback schema -------------------------------------------------
# Local dev runs on SQLite, where the .sql migrations never run. This mirrors 025.
# It creates tables only when ABSENT -- it must never widen or alter an existing
# column, because CREATE-IF-NOT-EXISTS silently does nothing against a live table
# whose shape has drifted, and you get a confusing failure far from the cause.

_SQLITE_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS enterprise_tenants (
        id                TEXT PRIMARY KEY,
        legacy_user_id    INTEGER,
        slug              TEXT NOT NULL,
        legal_name        TEXT NOT NULL,
        display_name      TEXT,
        organisation_type TEXT NOT NULL DEFAULT 'personal',
        country           TEXT,
        default_currency  TEXT NOT NULL DEFAULT 'GHS',
        default_timezone  TEXT NOT NULL DEFAULT 'Africa/Accra',
        unit_system       TEXT NOT NULL DEFAULT 'metric',
        branding_json     TEXT NOT NULL DEFAULT '{}',
        status            TEXT NOT NULL DEFAULT 'active',
        created_at        TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at        TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_tenants_slug ON enterprise_tenants(slug)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_tenants_legacy_user "
    "ON enterprise_tenants(legacy_user_id) WHERE legacy_user_id IS NOT NULL",
    """
    CREATE TABLE IF NOT EXISTS enterprise_tenant_memberships (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id          TEXT NOT NULL,
        user_id            INTEGER NOT NULL,
        email              TEXT,
        status             TEXT NOT NULL DEFAULT 'active',
        invited_by_user_id INTEGER,
        joined_at          TEXT DEFAULT CURRENT_TIMESTAMP,
        created_at         TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at         TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_membership_tenant_user "
    "ON enterprise_tenant_memberships(tenant_id, user_id)",
    """
    CREATE TABLE IF NOT EXISTS enterprise_role_assignments (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id          TEXT NOT NULL,
        user_id            INTEGER NOT NULL,
        role_code          TEXT NOT NULL,
        scope_type         TEXT NOT NULL DEFAULT 'tenant',
        scope_id           INTEGER,
        region_code        TEXT,
        district_code      TEXT,
        starts_at          TEXT,
        ends_at            TEXT,
        created_at         TEXT DEFAULT CURRENT_TIMESTAMP,
        created_by_user_id INTEGER
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_role_assignment "
    "ON enterprise_role_assignments(tenant_id, user_id, role_code, scope_type, "
    "COALESCE(scope_id,-1), COALESCE(region_code,''), COALESCE(district_code,''))",
    """
    CREATE TABLE IF NOT EXISTS enterprise_taxonomy_options (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id   TEXT,
        taxonomy    TEXT NOT NULL,
        code        TEXT NOT NULL,
        label       TEXT NOT NULL,
        parent_code TEXT,
        sort_order  INTEGER NOT NULL DEFAULT 0,
        extra_json  TEXT NOT NULL DEFAULT '{}',
        active      INTEGER NOT NULL DEFAULT 1,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_taxonomy_global "
    "ON enterprise_taxonomy_options(taxonomy, code) WHERE tenant_id IS NULL",
    # Mirrors migration 025's ux_ent_taxonomy_tenant. Without it, SQLite would accept
    # duplicate tenant-scoped options that live Postgres rejects -- a schema drift that
    # only shows up as a production-only failure.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_taxonomy_tenant "
    "ON enterprise_taxonomy_options(tenant_id, taxonomy, code) WHERE tenant_id IS NOT NULL",
]


def ensure_schema(c) -> None:
    """Create the slice-1 tables on SQLite. No-op on Postgres (migration 025 owns it).

    Input:  open DB connection.
    Output: none.
    """
    if _is_postgres():
        return
    for stmt in _SQLITE_SCHEMA:
        c.execute(stmt)


# --- tenant resolution ------------------------------------------------------

def get_or_create_personal_tenant(c, user_id: int, username: str = "",
                                  email: str = "") -> str:
    """Return the caller's personal tenant id, creating it if this is their first visit.

    Input:  connection, users.id, and optionally username/email for the display name.
    Output: tenant id (UUID string).

    Idempotent: the unique index on legacy_user_id means a concurrent double-call
    cannot produce two personal tenants. On Postgres the row normally already exists
    (migration 025 backfilled every user); this path covers SQLite and users created
    after the migration ran.
    """
    tid = personal_tenant_id(user_id)
    name = (username or "").strip() or f"user-{user_id}"

    c.execute(
        "INSERT INTO enterprise_tenants "
        "(id, legacy_user_id, slug, legal_name, display_name, organisation_type, status) "
        "VALUES (?,?,?,?,?,?,?) ON CONFLICT (id) DO NOTHING",
        (tid, user_id, f"personal-{user_id}", name, name, "personal", "active"),
    )
    c.execute(
        "INSERT INTO enterprise_tenant_memberships (tenant_id, user_id, email, status) "
        "VALUES (?,?,?,?) ON CONFLICT (tenant_id, user_id) DO NOTHING",
        (tid, user_id, email or None, "active"),
    )
    c.execute(
        "INSERT INTO enterprise_role_assignments (tenant_id, user_id, role_code, scope_type) "
        "VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
        (tid, user_id, "enterprise_owner", "tenant"),
    )
    return tid


def list_tenants_for_user(c, user_id: int) -> list[dict]:
    """Every tenant the user is an ACTIVE member of, personal one first.

    Input:  connection, users.id.
    Output: list of dicts (id, legal_name, organisation_type, status).

    This is the source for the tenant-switcher dropdown. A user with no organisation
    still gets exactly one row back: their personal workspace.
    """
    rows = c.execute(
        "SELECT t.id, t.legal_name, t.organisation_type, t.status, t.legacy_user_id "
        "  FROM enterprise_tenants t "
        "  JOIN enterprise_tenant_memberships m ON m.tenant_id = t.id "
        " WHERE m.user_id = ? AND m.status = 'active' AND t.status = 'active' "
        " ORDER BY CASE WHEN t.legacy_user_id IS NULL THEN 1 ELSE 0 END, t.legal_name",
        (user_id,),
    ).fetchall()
    return [
        {
            "id": r[0],
            "legal_name": r[1],
            "organisation_type": r[2],
            "status": r[3],
            "is_personal": r[4] is not None,
        }
        for r in rows
    ]


def resolve_active_tenant(c, user_id: int, requested_tenant_id: str | None = None) -> str | None:
    """Resolve which tenant this request acts in, verifying membership.

    Input:  connection, users.id, optionally a tenant id from the session/URL.
    Output: the tenant id to use, or None if the user has no tenant at all.

    SECURITY: a tenant id arriving from the client is HOSTILE INPUT. It is honoured
    only after proving the caller holds an active membership in it. Anything else
    falls back to the personal tenant. This is the check that stops a crafted
    tenant id from reading another organisation's programmes.
    """
    if requested_tenant_id:
        row = c.execute(
            "SELECT 1 FROM enterprise_tenant_memberships "
            " WHERE tenant_id = ? AND user_id = ? AND status = 'active'",
            (requested_tenant_id, user_id),
        ).fetchone()
        if row:
            return requested_tenant_id
        # Not a member -> do NOT honour it, and do not leak whether it exists.

    tenants = list_tenants_for_user(c, user_id)
    return tenants[0]["id"] if tenants else None


# --- organisations ----------------------------------------------------------

def create_organisation(c, user_id: int, legal_name: str, organisation_type: str,
                        country: str = "", currency: str = "GHS") -> str:
    """Create a real multi-user organisation tenant, with the creator as its owner.

    Input:  connection, creating users.id, legal name, organisation type code
            (must be one of constants.ORGANISATION_TYPES), country, currency.
    Output: the new tenant id (UUID string).
    Raises: ValueError on a blank name or an unknown organisation type.

    The creator becomes an active member and `enterprise_owner`. Unlike a personal
    tenant this row has legacy_user_id = NULL, which is what marks it as a real
    organisation that other users can be invited into.
    """
    name = (legal_name or "").strip()
    if not name:
        raise ValueError("Organisation legal name is required.")
    if organisation_type not in _ORG_TYPE_CODES:
        raise ValueError(f"Unknown organisation type: {organisation_type!r}")

    tid = str(uuid.uuid4())
    slug = f"org-{tid[:8]}"
    c.execute(
        "INSERT INTO enterprise_tenants "
        "(id, legacy_user_id, slug, legal_name, display_name, organisation_type, "
        " country, default_currency, status) "
        "VALUES (?, NULL, ?,?,?,?,?,?,?)",
        (tid, slug, name, name, organisation_type, country or None, currency, "active"),
    )
    c.execute(
        "INSERT INTO enterprise_tenant_memberships (tenant_id, user_id, status) "
        "VALUES (?,?,?)",
        (tid, user_id, "active"),
    )
    c.execute(
        "INSERT INTO enterprise_role_assignments (tenant_id, user_id, role_code, scope_type, "
        " created_by_user_id) VALUES (?,?,?,?,?)",
        (tid, user_id, "enterprise_owner", "tenant", user_id),
    )
    return tid


def add_member(c, tenant_id: str, user_id: int, role_code: str,
               invited_by_user_id: int, email: str = "") -> None:
    """Add a user to an organisation with a role.

    Input:  connection, tenant id, the user being added, their role code, the
            inviter's users.id, optional email.
    Output: none.

    The CALLER is responsible for proving the inviter holds `tenant.admin` in this
    tenant -- see rbac.require_permission. This function does not re-check that,
    because it is also used by the personal-tenant bootstrap where there is no
    inviter to check.
    """
    c.execute(
        "INSERT INTO enterprise_tenant_memberships "
        "(tenant_id, user_id, email, status, invited_by_user_id) VALUES (?,?,?,?,?) "
        "ON CONFLICT (tenant_id, user_id) DO NOTHING",
        (tenant_id, user_id, email or None, "active", invited_by_user_id),
    )
    c.execute(
        "INSERT INTO enterprise_role_assignments "
        "(tenant_id, user_id, role_code, scope_type, created_by_user_id) "
        "VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
        (tenant_id, user_id, role_code, "tenant", invited_by_user_id),
    )
