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

from .constants import (
    ONBOARDING_OWNER_ROLES,
    ORGANISATION_TYPES,
    ROLE_CODES,
    ROLE_PERMISSIONS,
)

_ORG_TYPE_CODES = frozenset(c for c, _ in ORGANISATION_TYPES)

# The roles that can administer a tenant -- DERIVED from the permission map, never typed
# out by hand. If a future role is given `tenant.admin`, the last-administrator guard in
# revoke_role/remove_member must know about it, and a hand-maintained list is exactly the
# kind of thing that silently falls out of date and turns a guard into decoration.
_TENANT_ADMIN_ROLES = frozenset(
    role for role, perms in ROLE_PERMISSIONS.items() if "tenant.admin" in perms
)
# Inlined into SQL. Safe because every element is a key of ROLE_PERMISSIONS -- a Python
# literal in this repo's own source, never user input. Sorted so the SQL is stable.
_TENANT_ADMIN_ROLES_SQL = ", ".join(f"'{r}'" for r in sorted(_TENANT_ADMIN_ROLES))


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

    The creator becomes an active member and is granted ONBOARDING_OWNER_ROLES. Unlike a
    personal tenant this row has legacy_user_id = NULL, which is what marks it as a real
    organisation that other users can be invited into.

    WHY THE CREATOR GETS A BUNDLE OF ROLES, NOT JUST `enterprise_owner`
    ------------------------------------------------------------------
    Because `enterprise_owner` alone made the module unusable, and the live suite proved
    it: the owner could register a programme and then not import a beneficiary, not author
    a template, and not sign Gate 2 -- the gates demand a NAMED ROLE, not a permission, so
    no permission-map change could have reached them. See constants.ONBOARDING_OWNER_ROLES
    for the full reasoning.

    They are the organisation's first and (at this instant) only member, so they are every
    authority in it. That is not a privilege escalation -- it is the plain truth about a
    one-person organisation, now written down where the audit trail can see it. Each role
    is a separate, revocable row: when the ministry hires a real Technical Director, the
    owner hands `technical_director` over on the members screen and stops holding it.
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
    for role_code in ONBOARDING_OWNER_ROLES:
        c.execute(
            "INSERT INTO enterprise_role_assignments (tenant_id, user_id, role_code, "
            " scope_type, created_by_user_id) VALUES (?,?,?,?,?)",
            (tid, user_id, role_code, "tenant", user_id),
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


# --- membership administration (slice 6.5) ----------------------------------
#
# WHY THIS EXISTS
# ---------------
# Slice 3 shipped role CHECKING with no way to GRANT a role, and onboarding hands the
# creator `enterprise_owner`, which carried no operational permissions. The live suite
# proved the consequence: the person who onboards an organisation could create a
# programme and then do nothing with it -- import 403, no template form, empty priority
# list -- and had no UI to grant themselves anything. 231 unit tests missed it because
# every fixture hand-grants roles. These functions are the missing half.


def is_personal_tenant(c, tenant_id: str) -> bool:
    """True when this tenant is a user's PRIVATE workspace, not a real organisation.

    Input:  connection, tenant id.
    Output: True if the tenant carries a legacy_user_id.

    A personal tenant's id IS the md5 hash the app already derives for that user, so it
    lines up with their existing project rows. Admitting a second person into it would
    silently turn one user's private workspace into a shared one -- so member management
    refuses to touch a personal tenant. Organisations are for sharing; personal tenants
    are not.
    """
    row = c.execute(
        "SELECT legacy_user_id FROM enterprise_tenants WHERE id = ?", (tenant_id,)
    ).fetchone()
    return bool(row and row[0] is not None)


def active_member_count(c, tenant_id: str) -> int:
    """How many people are actually IN this tenant right now.

    Input:  connection, tenant id.
    Output: count of memberships with status 'active'.

    Revoked members do not count -- offboarding must actually reduce the headcount, or
    a tenant would look shared forever after its second member left.
    """
    row = c.execute(
        "SELECT COUNT(*) FROM enterprise_tenant_memberships "
        " WHERE tenant_id = ? AND status = 'active'",
        (tenant_id,),
    ).fetchone()
    return int(row[0]) if row else 0


def is_solo_tenant(c, tenant_id: str) -> bool:
    """True when exactly one active person is in this tenant.

    Input:  connection, tenant id.
    Output: True if the active membership count is 1.

    THIS IS A SECURITY-RELEVANT PREDICATE. It is the ONLY condition under which the
    separation-of-duties rules relax (see site_qualification.decide and
    templates.approve_version). The reasoning, stated plainly so nobody has to infer it:

      Separation of duties needs TWO PEOPLE to mean anything. "The person who surveys a
      site is not the person who commits the programme to serving it" is a real control
      when there are two people; with one person in the tenant it is not a control at
      all, it is a deadlock -- nothing can ever be approved, and the module is unusable
      for the solo operator who is its actual first user.

    So a one-member tenant may self-approve, and the audit row SAYS SO explicitly. The
    moment a second member joins, this returns False and SoD binds again, with no
    migration and no flag to remember. The relaxation cannot outlive the condition that
    justifies it -- which is the whole reason it is computed from live membership rather
    than stored as a tenant setting.
    """
    return active_member_count(c, tenant_id) == 1


def find_user(c, identifier: str) -> dict | None:
    """Resolve a username or email address to an app user.

    Input:  connection, a username or email (case-insensitive, whitespace-trimmed).
    Output: {"id", "username", "email"} or None if no such user.

    Matched case-insensitively on BOTH columns because an admin inviting a colleague
    types whichever one they remember, and Postgres -- unlike SQLite -- compares text
    case-sensitively by default. `Marc@Example.com` must find `marc@example.com`.
    """
    ident = (identifier or "").strip()
    if not ident:
        return None
    row = c.execute(
        "SELECT id, username, email FROM users "
        " WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)",
        (ident, ident),
    ).fetchone()
    if not row:
        return None
    return {"id": int(row[0]), "username": row[1], "email": row[2]}


def list_members(c, tenant_id: str) -> list[dict]:
    """Every ACTIVE member of a tenant, each with the roles they hold.

    Input:  connection, tenant id.
    Output: list of {"user_id", "username", "email", "joined_at", "roles": [codes]},
            ordered by username.

    TWO queries, never N+1 (the Supervisor caught a ~30-query detail render in slice 3;
    this is the same shape and would have grown with the member list). One query for the
    people, one for every tenant-scoped role in the tenant, then stitched in memory.

    Only tenant-scoped roles are listed. Programme-scoped grants belong on the programme
    page next to the programme they apply to -- showing them here, stripped of the
    programme they are bounded by, would read as tenant-wide authority the holder does
    not have.
    """
    rows = c.execute(
        "SELECT m.user_id, u.username, u.email, m.joined_at "
        "  FROM enterprise_tenant_memberships m "
        "  JOIN users u ON u.id = m.user_id "
        " WHERE m.tenant_id = ? AND m.status = 'active' "
        " ORDER BY LOWER(u.username)",
        (tenant_id,),
    ).fetchall()

    role_rows = c.execute(
        "SELECT ra.user_id, ra.role_code "
        "  FROM enterprise_role_assignments ra "
        "  JOIN enterprise_tenant_memberships m "
        "    ON m.tenant_id = ra.tenant_id AND m.user_id = ra.user_id "
        " WHERE ra.tenant_id = ? AND ra.scope_type = 'tenant' "
        "   AND m.status = 'active' "
        "   AND (ra.starts_at IS NULL OR ra.starts_at <= CURRENT_TIMESTAMP) "
        "   AND (ra.ends_at   IS NULL OR ra.ends_at   >  CURRENT_TIMESTAMP)",
        (tenant_id,),
    ).fetchall()

    by_user: dict[int, list[str]] = {}
    for uid, role_code in role_rows:
        by_user.setdefault(int(uid), []).append(role_code)

    return [
        {
            "user_id": int(r[0]),
            "username": r[1],
            "email": r[2],
            "joined_at": r[3],
            "roles": sorted(by_user.get(int(r[0]), [])),
        }
        for r in rows
    ]


def grant_role(c, tenant_id: str, user_id: int, role_code: str,
               granted_by_user_id: int) -> None:
    """Grant a tenant-wide role to an EXISTING active member.

    Input:  connection, tenant id, the member's users.id, role code, the granter's id.
    Output: none.
    Raises: ValueError on an unknown role, or if the target is not an active member.

    The CALLER proves the granter holds `tenant.admin` (rbac.require_permission).

    Membership is checked HERE and not left to the caller because a role row for a
    non-member is a live landmine: `roles_for_user` joins membership, so the grant looks
    inert -- until that person is later added to the tenant for some unrelated reason and
    silently inherits an authority nobody remembers granting them.
    """
    if role_code not in ROLE_CODES:
        raise ValueError(f"Unknown role: {role_code!r}")

    row = c.execute(
        "SELECT 1 FROM enterprise_tenant_memberships "
        " WHERE tenant_id = ? AND user_id = ? AND status = 'active'",
        (tenant_id, user_id),
    ).fetchone()
    if not row:
        raise ValueError("That user is not an active member of this organisation.")

    c.execute(
        "INSERT INTO enterprise_role_assignments "
        "(tenant_id, user_id, role_code, scope_type, created_by_user_id) "
        "VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
        (tenant_id, user_id, role_code, "tenant", granted_by_user_id),
    )


def revoke_role(c, tenant_id: str, user_id: int, role_code: str) -> None:
    """Remove a tenant-wide role from a member.

    Input:  connection, tenant id, the member's users.id, role code.
    Output: none.
    Raises: ValueError if this would strip the tenant's LAST enterprise_owner.

    The CALLER proves the revoker holds `tenant.admin`.

    THE LAST-OWNER GUARD: `tenant.admin` is the only permission that can grant roles, and
    `enterprise_owner`/`org_admin` are the only roles that carry it. Revoking the last one
    leaves an organisation that NOBODY can administer -- not the person who created it,
    not support, nobody -- and there is no recovery path short of a database edit. An
    admin may hand the keys to someone else and step back; they may not lock the door and
    throw the key away.
    """
    if role_code in _TENANT_ADMIN_ROLES:
        others = c.execute(
            "SELECT COUNT(*) FROM enterprise_role_assignments ra "
            "  JOIN enterprise_tenant_memberships m "
            "    ON m.tenant_id = ra.tenant_id AND m.user_id = ra.user_id "
            " WHERE ra.tenant_id = ? AND ra.scope_type = 'tenant' "
            "   AND m.status = 'active' "
            f"   AND ra.role_code IN ({_TENANT_ADMIN_ROLES_SQL}) "
            "   AND NOT (ra.user_id = ? AND ra.role_code = ?)",
            (tenant_id, user_id, role_code),
        ).fetchone()
        if not others or int(others[0]) == 0:
            raise ValueError(
                "This is the organisation's last administrator role. Grant "
                "administrator to somebody else first -- otherwise nobody could ever "
                "manage this organisation again."
            )

    c.execute(
        "DELETE FROM enterprise_role_assignments "
        " WHERE tenant_id = ? AND user_id = ? AND role_code = ? AND scope_type = 'tenant'",
        (tenant_id, user_id, role_code),
    )


def remove_member(c, tenant_id: str, user_id: int) -> None:
    """Offboard a member: revoke the membership, leaving their role rows in place.

    Input:  connection, tenant id, the member's users.id.
    Output: none.
    Raises: ValueError if this would remove the tenant's last administrator.

    The CALLER proves the remover holds `tenant.admin`.

    The membership is marked 'revoked', NOT deleted. `roles_for_user` joins membership and
    requires status='active', so a revoked member holds nothing the moment this commits --
    that JOIN is exactly the slice-1 fix for offboarding being a silent no-op. Keeping the
    row means the audit trail can still answer "who was in this organisation in March",
    which a DELETE would erase.
    """
    row = c.execute(
        "SELECT 1 FROM enterprise_tenant_memberships "
        " WHERE tenant_id = ? AND user_id = ? AND status = 'active'",
        (tenant_id, user_id),
    ).fetchone()
    if not row:
        raise ValueError("That user is not an active member of this organisation.")

    # Same guard as revoke_role, for the same reason: removing the last admin outright is
    # just a faster way to lock everyone out.
    others = c.execute(
        "SELECT COUNT(*) FROM enterprise_role_assignments ra "
        "  JOIN enterprise_tenant_memberships m "
        "    ON m.tenant_id = ra.tenant_id AND m.user_id = ra.user_id "
        " WHERE ra.tenant_id = ? AND ra.scope_type = 'tenant' "
        "   AND m.status = 'active' AND ra.user_id <> ? "
        f"   AND ra.role_code IN ({_TENANT_ADMIN_ROLES_SQL})",
        (tenant_id, user_id),
    ).fetchone()
    if not others or int(others[0]) == 0:
        raise ValueError(
            "This is the organisation's last administrator. Grant administrator to "
            "somebody else before removing them."
        )

    c.execute(
        "UPDATE enterprise_tenant_memberships "
        "   SET status = 'revoked', updated_at = CURRENT_TIMESTAMP "
        " WHERE tenant_id = ? AND user_id = ? AND status = 'active'",
        (tenant_id, user_id),
    )
