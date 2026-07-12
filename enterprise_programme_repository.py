"""Enterprise Solar Programme Management -- data access layer (Phase 1).

Raw SQL only (this repo has no ORM). SQLite-style `?` placeholders throughout;
db_adapter translates them to `%s` for Postgres.

SECURITY MODEL -- read before changing anything here.
-----------------------------------------------------
Phase 1's PRIMARY tenant boundary is in THIS FILE, not in the database.
Postgres RLS (migration 024) is ENABLE, not FORCE, so it is defence in depth
only. Every function that touches an enterprise table therefore:

  1. resolves the caller's active membership from session `users.id`, and
  2. scopes EVERY query by that membership's `organisation_id` in the WHERE
     clause -- never by an id taken from the URL.

An id from the URL is treated as hostile input. `programme_id` alone never
identifies a row; `(id, organisation_id)` does.

The one exception that must never regress: linking a project. A programme may
only link a project the CALLER ALREADY OWNS, proven against the existing
ownership predicate of the project's own table (`WHERE id=? AND user_id=?`).
Enterprise never becomes a back door to someone else's project.

GUC NOTE
--------
The app's existing `app.current_user` GUC carries the Keycloak *sub*, not the
integer users.id (app/security/tenant_context.py:191), and is '' on the legacy
session path. Migration 024's policies therefore key on `app.current_user_id`,
which nothing else in the app publishes -- so this module publishes it itself,
on the connection it already holds, via apply_enterprise_guc(). No change to
web_app.py::get_db() is required.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any


# --- flags -----------------------------------------------------------------

FLAG_ENABLED = "enterprise_programme_enabled"
FLAG_JOBS = "enterprise_programme_jobs_enabled"
FLAG_AI = "enterprise_programme_ai_enabled"


def _is_postgres() -> bool:
    """True when the app is running against Postgres (vs local SQLite)."""
    return str(os.environ.get("DATABASE_URL", "")).startswith(
        ("postgres://", "postgresql://")
    )


def apply_enterprise_guc(c, user_id: int | None) -> None:
    """Publish the caller's integer users.id as `app.current_user_id`.

    Input:  an open DB connection, and the session user id (or None).
    Output: none. No-op on SQLite (no RLS there) and when user_id is falsy.

    Migration 024's RLS policies read this GUC. Nothing else in the app sets
    it -- `app.current_user` holds the Keycloak sub, which is a different
    identity and is empty for session-authenticated users.
    """
    if not _is_postgres() or not user_id:
        return
    try:
        c.execute(
            "SELECT set_config('app.current_user_id', ?, true)", (str(int(user_id)),)
        )
    except Exception:
        # RLS is defence-in-depth in Phase 1; the app-layer checks below are
        # the real boundary. A GUC failure must not 500 the request.
        pass


def read_flag(get_db, key: str, default: str = "0") -> str:
    """Read one enterprise feature flag from admin_settings.

    Input:  the injected get_db factory, the flag key, a default.
    Output: the flag's string value, or `default`.

    WHY THIS IS NOT JUST A SELECT: admin_settings is RLS-protected AND
    FORCE-enabled and admin-only (012_rls_batch5:172, 015_global_table_policies:230,
    018_force_rls_globals:104), and 017 dropped its parallel-run escape. A plain
    SELECT on a NORMAL user's request therefore matches no policy and returns
    zero rows -- the flag would read as `default` forever and the module would
    be permanently dark with nothing in the logs to explain it.

    So we set `app.current_role='admin'` transaction-locally for this one read
    and clear it immediately afterwards. The GUC is is_local=true, so it dies
    with the transaction even if the reset is skipped; the explicit reset keeps
    the connection safe if it is reused later in the same request.
    """
    try:
        with get_db() as c:
            if _is_postgres():
                c.execute("SELECT set_config('app.current_role', 'admin', true)")
            row = c.execute(
                "SELECT value FROM admin_settings WHERE key=?", (key,)
            ).fetchone()
            if _is_postgres():
                c.execute("SELECT set_config('app.current_role', '', true)")
        if row:
            return row["value"] if hasattr(row, "keys") else row[0]
    except Exception:
        pass
    return default


# Process-local cache for the module flag. The context processor consults it on
# EVERY template render, including anonymous public pages, so an uncached read
# would add a fresh Postgres connection to every page load on a 1-worker free
# tier -- a real regression even while the module is dark (Codex, gate 1 MEDIUM).
# 60s is short enough that flipping the flag takes effect within a minute.
_FLAG_TTL_SECONDS = 60.0
_flag_cache: dict[str, tuple[float, bool]] = {}


def module_enabled(get_db) -> bool:
    """True when the enterprise module is switched on. Dark by default.

    Cached for _FLAG_TTL_SECONDS per process. Fails CLOSED: any error reading the
    flag leaves the module dark rather than accidentally exposing it.
    """
    now = time.monotonic()
    hit = _flag_cache.get(FLAG_ENABLED)
    if hit and (now - hit[0]) < _FLAG_TTL_SECONDS:
        return hit[1]

    try:
        value = str(read_flag(get_db, FLAG_ENABLED, "0")).strip().lower()
        enabled = value in ("1", "true", "on", "yes")
    except Exception:
        enabled = False          # fail closed

    _flag_cache[FLAG_ENABLED] = (now, enabled)
    return enabled


def invalidate_flag_cache() -> None:
    """Drop the cached flag (used by tests, and after an admin flips it)."""
    _flag_cache.clear()


# --- schema (SQLite / local dev only) --------------------------------------

# Production schema is migration 024 (Postgres, with RLS). SQLite has no RLS, so
# this is a dev/test-only mirror of the same tables -- same columns, same names,
# no policies. Idempotent: safe to call on every boot.
_SQLITE_DDL = [
    """CREATE TABLE IF NOT EXISTS enterprise_organisations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id TEXT, legal_name TEXT NOT NULL,
        organisation_type TEXT NOT NULL DEFAULT 'corporate_enterprise',
        country TEXT DEFAULT '', default_currency TEXT DEFAULT 'USD',
        timezone TEXT DEFAULT 'UTC', brand_json TEXT DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'active',
        created_by_user_id INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS enterprise_memberships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organisation_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        keycloak_sub TEXT DEFAULT '', role TEXT NOT NULL DEFAULT 'enterprise_owner',
        permissions_json TEXT DEFAULT '{}', region_scope_json TEXT DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'active', invited_by_user_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(organisation_id, user_id))""",
    # One active organisation per user (see migration 024). SQLite supports
    # partial unique indexes, so the same guarantee holds in dev/tests.
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_ep_members_one_active_org_per_user
        ON enterprise_memberships (user_id) WHERE status = 'active'""",
    """CREATE TABLE IF NOT EXISTS enterprise_programmes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organisation_id INTEGER NOT NULL, programme_code TEXT NOT NULL,
        name TEXT NOT NULL, programme_type TEXT NOT NULL DEFAULT 'residential',
        description TEXT DEFAULT '', countries_json TEXT DEFAULT '[]',
        regions_json TEXT DEFAULT '[]', target_beneficiaries INTEGER DEFAULT 0,
        target_capacity_kwp REAL DEFAULT 0, target_battery_kwh REAL DEFAULT 0,
        budget_amount REAL DEFAULT 0, currency TEXT DEFAULT 'USD',
        delivery_model TEXT DEFAULT '', procurement_strategy TEXT DEFAULT '',
        design_strategy TEXT NOT NULL DEFAULT 'standard',
        status TEXT NOT NULL DEFAULT 'draft', created_by_user_id INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(organisation_id, programme_code))""",
    """CREATE TABLE IF NOT EXISTS enterprise_programme_phases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organisation_id INTEGER NOT NULL, programme_id INTEGER NOT NULL,
        name TEXT NOT NULL, sequence_no INTEGER NOT NULL DEFAULT 1,
        start_date TEXT DEFAULT '', target_completion_date TEXT DEFAULT '',
        target_beneficiaries INTEGER DEFAULT 0, target_capacity_kwp REAL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'planned',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS enterprise_beneficiaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organisation_id INTEGER NOT NULL, programme_id INTEGER NOT NULL,
        phase_id INTEGER, beneficiary_type TEXT NOT NULL DEFAULT 'household',
        name TEXT NOT NULL, region TEXT DEFAULT '', district TEXT DEFAULT '',
        community TEXT DEFAULT '', address TEXT DEFAULT '',
        latitude REAL, longitude REAL, contact_name TEXT DEFAULT '',
        contact_email TEXT DEFAULT '', contact_phone TEXT DEFAULT '',
        load_kwh_day REAL DEFAULT 0, target_capacity_kwp REAL DEFAULT 0,
        priority_score INTEGER DEFAULT 0,
        qualification_status TEXT NOT NULL DEFAULT 'draft',
        metadata_json TEXT DEFAULT '{}', created_by_user_id INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS enterprise_programme_project_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organisation_id INTEGER NOT NULL, programme_id INTEGER NOT NULL,
        beneficiary_id INTEGER, project_kind TEXT NOT NULL,
        project_id INTEGER NOT NULL, source_user_id INTEGER NOT NULL,
        linked_by_user_id INTEGER NOT NULL,
        design_strategy TEXT NOT NULL DEFAULT 'standard',
        status TEXT NOT NULL DEFAULT 'linked',
        linked_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(programme_id, project_kind, project_id))""",
    """CREATE TABLE IF NOT EXISTS enterprise_programme_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organisation_id INTEGER NOT NULL, programme_id INTEGER,
        job_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
        idempotency_key TEXT NOT NULL, payload_json TEXT DEFAULT '{}',
        cursor_json TEXT DEFAULT '{}', progress_current INTEGER DEFAULT 0,
        progress_total INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0,
        max_attempts INTEGER DEFAULT 3, locked_by TEXT DEFAULT '',
        locked_until TEXT DEFAULT '', last_error TEXT DEFAULT '',
        created_by_user_id INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(organisation_id, idempotency_key))""",
    """CREATE TABLE IF NOT EXISTS enterprise_programme_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organisation_id INTEGER NOT NULL, programme_id INTEGER,
        actor_user_id INTEGER, action TEXT NOT NULL, target_kind TEXT DEFAULT '',
        target_id INTEGER, details TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
]


def ensure_enterprise_schema(get_db) -> None:
    """Create the enterprise tables on SQLite (local dev + tests).

    No-op on Postgres -- there the schema is migration 024, applied deliberately
    through the gated workflow, because it also carries the RLS policies.
    """
    if _is_postgres():
        return
    try:
        with get_db() as c:
            for ddl in _SQLITE_DDL:
                c.execute(ddl)
    except Exception:
        pass


# --- inserts ---------------------------------------------------------------


def _insert_returning_id(c, sql: str, params: tuple) -> int:
    """INSERT and return the new row id.

    Postgres: uses `INSERT ... RETURNING id` (the `cur.lastrowid` shim in
    db_adapter is a `SELECT lastval()` emulation and is fragile -- new tables
    must not depend on it). SQLite: falls back to cur.lastrowid, which is native.
    """
    if _is_postgres():
        cur = c.execute(sql + " RETURNING id", params)
        row = cur.fetchone()
        return int(row["id"] if hasattr(row, "keys") else row[0])
    cur = c.execute(sql, params)
    return int(cur.lastrowid)


# --- membership (the primary tenant boundary) ------------------------------


def get_active_membership(get_db, user_id: int) -> dict[str, Any] | None:
    """The caller's active enterprise membership, or None.

    Input:  session users.id.
    Output: dict with organisation_id / role / legal_name, or None if the user
            belongs to no organisation (i.e. they must bootstrap one first).

    Every other function in this module takes the organisation_id THIS returns
    -- never one supplied by the client.
    """
    with get_db() as c:
        apply_enterprise_guc(c, user_id)
        row = c.execute(
            "SELECT m.id, m.organisation_id, m.role, m.status, o.legal_name, "
            "       o.default_currency, o.country "
            "FROM enterprise_memberships m "
            "JOIN enterprise_organisations o ON o.id = m.organisation_id "
            "WHERE m.user_id=? AND m.status='active' "
            "ORDER BY m.id LIMIT 1",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def bootstrap_organisation(
    get_db, user_id: int, legal_name: str, org_type: str = "corporate_enterprise",
    country: str = "", currency: str = "USD", keycloak_sub: str = "",
) -> int:
    """Create an organisation + owner membership for a user who has none.

    Input:  session users.id, the organisation's legal name, optional profile.
    Output: the organisation_id (existing one if the user already has a
            membership -- this is IDEMPOTENT and will not create a second org).
    """
    existing = get_active_membership(get_db, user_id)
    if existing:
        return int(existing["organisation_id"])

    try:
        with get_db() as c:
            apply_enterprise_guc(c, user_id)
            org_id = _insert_returning_id(
                c,
                "INSERT INTO enterprise_organisations "
                "(legal_name, organisation_type, country, default_currency, created_by_user_id) "
                "VALUES (?,?,?,?,?)",
                (legal_name.strip()[:200], org_type, country, currency, user_id),
            )
            # uq_ep_members_one_active_org_per_user makes this INSERT fail if a
            # concurrent request already bootstrapped this user.
            c.execute(
                "INSERT INTO enterprise_memberships "
                "(organisation_id, user_id, keycloak_sub, role, status) "
                "VALUES (?,?,?,'enterprise_owner','active')",
                (org_id, user_id, keycloak_sub or ""),
            )
            _audit(c, org_id, None, user_id, "organisation.bootstrap", "organisation",
                   org_id, legal_name.strip()[:200])
        return org_id
    except Exception:
        # We lost the race (or the unique index rejected us). The other request
        # created the organisation -- adopt it rather than 500 at the user.
        winner = get_active_membership(get_db, user_id)
        if winner:
            return int(winner["organisation_id"])
        raise


# --- audit -----------------------------------------------------------------


def _audit(c, org_id: int, programme_id: int | None, actor_user_id: int,
           action: str, target_kind: str = "", target_id: int | None = None,
           details: str = "") -> None:
    """Append an enterprise audit row. Called inside the caller's transaction."""
    try:
        c.execute(
            "INSERT INTO enterprise_programme_audit "
            "(organisation_id, programme_id, actor_user_id, action, target_kind, target_id, details) "
            "VALUES (?,?,?,?,?,?,?)",
            (org_id, programme_id, actor_user_id, action, target_kind, target_id,
             str(details)[:500]),
        )
    except Exception:
        # Never let an audit write failure lose the user's actual work.
        pass


def list_audit(get_db, org_id: int, user_id: int, limit: int = 50) -> list[dict]:
    """Recent audit events for the caller's organisation."""
    with get_db() as c:
        apply_enterprise_guc(c, user_id)
        rows = c.execute(
            "SELECT * FROM enterprise_programme_audit WHERE organisation_id=? "
            "ORDER BY id DESC LIMIT ?",
            (org_id, int(limit)),
        ).fetchall()
    return [dict(r) for r in rows]


# --- programmes ------------------------------------------------------------


def create_programme(get_db, org_id: int, user_id: int, data: dict) -> int:
    """Create a programme inside the caller's organisation.

    Input:  org_id (from membership, NOT from the client), users.id, form data.
    Output: the new programme id.
    """
    with get_db() as c:
        apply_enterprise_guc(c, user_id)
        pid = _insert_returning_id(
            c,
            "INSERT INTO enterprise_programmes "
            "(organisation_id, programme_code, name, programme_type, description, "
            " countries_json, regions_json, target_beneficiaries, target_capacity_kwp, "
            " target_battery_kwh, budget_amount, currency, delivery_model, "
            " procurement_strategy, design_strategy, status, created_by_user_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                org_id,
                data["programme_code"],
                data["name"],
                data.get("programme_type", "residential"),
                data.get("description", ""),
                json.dumps(data.get("countries", [])),
                json.dumps(data.get("regions", [])),
                int(data.get("target_beneficiaries") or 0),
                float(data.get("target_capacity_kwp") or 0),
                float(data.get("target_battery_kwh") or 0),
                float(data.get("budget_amount") or 0),
                data.get("currency", "USD"),
                data.get("delivery_model", ""),
                data.get("procurement_strategy", ""),
                data.get("design_strategy", "standard"),
                data.get("status", "draft"),
                user_id,
            ),
        )
        _audit(c, org_id, pid, user_id, "programme.create", "programme", pid,
               data.get("name", ""))
    return pid


def get_programme(get_db, org_id: int, user_id: int, programme_id: int) -> dict | None:
    """One programme, scoped to the caller's organisation.

    `programme_id` comes from the URL and is therefore untrusted: the
    organisation_id in the WHERE clause is what makes this safe.
    """
    with get_db() as c:
        apply_enterprise_guc(c, user_id)
        row = c.execute(
            "SELECT * FROM enterprise_programmes WHERE id=? AND organisation_id=?",
            (programme_id, org_id),
        ).fetchone()
    return dict(row) if row else None


def list_programmes(get_db, org_id: int, user_id: int, limit: int = 25,
                    offset: int = 0) -> tuple[list[dict], int]:
    """Paginated programme registry for the caller's organisation.

    Output: (rows, total). Paginated because the spec forbids rendering an
    unbounded portfolio (File B §5.7 / §35).
    """
    with get_db() as c:
        apply_enterprise_guc(c, user_id)
        rows = c.execute(
            "SELECT * FROM enterprise_programmes WHERE organisation_id=? "
            "ORDER BY id DESC LIMIT ? OFFSET ?",
            (org_id, int(limit), int(offset)),
        ).fetchall()
        trow = c.execute(
            "SELECT COUNT(*) AS n FROM enterprise_programmes WHERE organisation_id=?",
            (org_id,),
        ).fetchone()
    total = int(trow["n"] if hasattr(trow, "keys") else trow[0])
    return [dict(r) for r in rows], total


def update_programme(get_db, org_id: int, user_id: int, programme_id: int,
                     data: dict) -> bool:
    """Update a programme. Returns False if it is not the caller's."""
    if not get_programme(get_db, org_id, user_id, programme_id):
        return False
    with get_db() as c:
        apply_enterprise_guc(c, user_id)
        c.execute(
            "UPDATE enterprise_programmes SET name=?, programme_type=?, description=?, "
            "target_beneficiaries=?, target_capacity_kwp=?, budget_amount=?, currency=?, "
            "design_strategy=?, status=?, updated_at=CURRENT_TIMESTAMP "
            "WHERE id=? AND organisation_id=?",
            (
                data["name"],
                data.get("programme_type", "residential"),
                data.get("description", ""),
                int(data.get("target_beneficiaries") or 0),
                float(data.get("target_capacity_kwp") or 0),
                float(data.get("budget_amount") or 0),
                data.get("currency", "USD"),
                data.get("design_strategy", "standard"),
                data.get("status", "draft"),
                programme_id,
                org_id,
            ),
        )
        _audit(c, org_id, programme_id, user_id, "programme.update", "programme",
               programme_id, data.get("name", ""))
    return True


def next_programme_code(get_db, org_id: int, user_id: int) -> str:
    """Suggest the next programme code (PRG-001, PRG-002, ...) for this org."""
    with get_db() as c:
        apply_enterprise_guc(c, user_id)
        row = c.execute(
            "SELECT COUNT(*) AS n FROM enterprise_programmes WHERE organisation_id=?",
            (org_id,),
        ).fetchone()
    n = int(row["n"] if hasattr(row, "keys") else row[0])
    return f"PRG-{n + 1:03d}"


# --- phases ----------------------------------------------------------------


def add_phase(get_db, org_id: int, user_id: int, programme_id: int, data: dict) -> int | None:
    """Add a phase to a programme the caller owns. None if not theirs."""
    if not get_programme(get_db, org_id, user_id, programme_id):
        return None
    with get_db() as c:
        apply_enterprise_guc(c, user_id)
        pid = _insert_returning_id(
            c,
            "INSERT INTO enterprise_programme_phases "
            "(organisation_id, programme_id, name, sequence_no, start_date, "
            " target_completion_date, target_beneficiaries, target_capacity_kwp, status) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                org_id, programme_id, data["name"],
                int(data.get("sequence_no") or 1),
                data.get("start_date", ""),
                data.get("target_completion_date", ""),
                int(data.get("target_beneficiaries") or 0),
                float(data.get("target_capacity_kwp") or 0),
                data.get("status", "planned"),
            ),
        )
        _audit(c, org_id, programme_id, user_id, "phase.create", "phase", pid,
               data.get("name", ""))
    return pid


def list_phases(get_db, org_id: int, user_id: int, programme_id: int) -> list[dict]:
    """Phases of a programme, ordered. Empty list if the programme is not the caller's."""
    with get_db() as c:
        apply_enterprise_guc(c, user_id)
        rows = c.execute(
            "SELECT * FROM enterprise_programme_phases "
            "WHERE programme_id=? AND organisation_id=? ORDER BY sequence_no, id",
            (programme_id, org_id),
        ).fetchall()
    return [dict(r) for r in rows]


# --- beneficiaries ---------------------------------------------------------


def phase_belongs_to(get_db, org_id: int, programme_id: int, phase_id: int) -> bool:
    """Is this phase really part of THIS programme in THIS organisation?

    A foreign key only proves the id EXISTS -- not that it is ours. Without this,
    a crafted form could attach our beneficiary to another organisation's phase
    (Codex gate 1, HIGH). Every optional cross-reference must be re-scoped.
    """
    with get_db() as c:
        row = c.execute(
            "SELECT 1 AS ok FROM enterprise_programme_phases "
            "WHERE id=? AND programme_id=? AND organisation_id=?",
            (phase_id, programme_id, org_id),
        ).fetchone()
    return bool(row)


def beneficiary_belongs_to(get_db, org_id: int, programme_id: int,
                           beneficiary_id: int) -> bool:
    """Is this beneficiary really part of THIS programme in THIS organisation?

    Same reasoning as phase_belongs_to -- the FK is not a tenancy check.
    """
    with get_db() as c:
        row = c.execute(
            "SELECT 1 AS ok FROM enterprise_beneficiaries "
            "WHERE id=? AND programme_id=? AND organisation_id=?",
            (beneficiary_id, programme_id, org_id),
        ).fetchone()
    return bool(row)


def add_beneficiary(get_db, org_id: int, user_id: int, programme_id: int,
                    data: dict) -> int | None:
    """Register one beneficiary against a programme the caller owns."""
    if not get_programme(get_db, org_id, user_id, programme_id):
        return None

    # A supplied phase_id is untrusted input: prove it is OURS before storing it.
    phase_id = int(data["phase_id"]) if data.get("phase_id") else None
    if phase_id is not None and not phase_belongs_to(get_db, org_id, programme_id,
                                                     phase_id):
        return None

    with get_db() as c:
        apply_enterprise_guc(c, user_id)
        bid = _insert_returning_id(
            c,
            "INSERT INTO enterprise_beneficiaries "
            "(organisation_id, programme_id, phase_id, beneficiary_type, name, region, "
            " district, community, address, latitude, longitude, contact_name, "
            " contact_email, contact_phone, load_kwh_day, target_capacity_kwp, "
            " priority_score, qualification_status, created_by_user_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                org_id, programme_id,
                phase_id,
                data.get("beneficiary_type", "household"),
                data["name"],
                data.get("region", ""), data.get("district", ""),
                data.get("community", ""), data.get("address", ""),
                float(data["latitude"]) if data.get("latitude") else None,
                float(data["longitude"]) if data.get("longitude") else None,
                data.get("contact_name", ""), data.get("contact_email", ""),
                data.get("contact_phone", ""),
                float(data.get("load_kwh_day") or 0),
                float(data.get("target_capacity_kwp") or 0),
                int(data.get("priority_score") or 0),
                data.get("qualification_status", "draft"),
                user_id,
            ),
        )
        _audit(c, org_id, programme_id, user_id, "beneficiary.create", "beneficiary",
               bid, data.get("name", ""))
    return bid


def list_beneficiaries(get_db, org_id: int, user_id: int, programme_id: int,
                       limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    """Paginated beneficiary register for one programme. (rows, total)."""
    with get_db() as c:
        apply_enterprise_guc(c, user_id)
        rows = c.execute(
            "SELECT * FROM enterprise_beneficiaries "
            "WHERE programme_id=? AND organisation_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (programme_id, org_id, int(limit), int(offset)),
        ).fetchall()
        trow = c.execute(
            "SELECT COUNT(*) AS n FROM enterprise_beneficiaries "
            "WHERE programme_id=? AND organisation_id=?",
            (programme_id, org_id),
        ).fetchone()
    total = int(trow["n"] if hasattr(trow, "keys") else trow[0])
    return [dict(r) for r in rows], total


def set_beneficiary_status(get_db, org_id: int, user_id: int, programme_id: int,
                           beneficiary_id: int, status: str) -> bool:
    """Approve / reject / archive one beneficiary. Org-scoped."""
    if status not in ("draft", "approved", "rejected", "archived"):
        return False
    with get_db() as c:
        apply_enterprise_guc(c, user_id)
        cur = c.execute(
            "UPDATE enterprise_beneficiaries SET qualification_status=?, "
            "updated_at=CURRENT_TIMESTAMP "
            "WHERE id=? AND programme_id=? AND organisation_id=?",
            (status, beneficiary_id, programme_id, org_id),
        )
        changed = (cur.rowcount or 0) > 0
        if changed:
            _audit(c, org_id, programme_id, user_id, f"beneficiary.{status}",
                   "beneficiary", beneficiary_id, status)
    return changed


# --- project links (the backward-compatibility keystone) -------------------


def user_owns_project(get_db, user_id: int, kind: str, project_id: int) -> bool:
    """Does THIS user own this project, per the project's own ownership rule?

    Input:  session users.id, 'standard' | 'generation_station', project id.
    Output: True only if the existing ownership predicate matches.

    This reuses the app's existing ownership contract verbatim
    (`WHERE id=? AND user_id=?` -- web_app.py:1043 get_project, and
    new_capital_investment_routes.py:6320 _load_project). It is the gate that
    stops the enterprise module becoming an IDOR back door into another user's
    project by guessing an integer. Do not relax it.
    """
    table = {
        "standard": "projects",
        "generation_station": "capital_investment_projects",
    }.get(kind)
    if not table:
        return False
    with get_db() as c:
        row = c.execute(
            f"SELECT 1 AS ok FROM {table} WHERE id=? AND user_id=?",
            (project_id, user_id),
        ).fetchone()
    return bool(row)


def link_project(get_db, org_id: int, user_id: int, programme_id: int, kind: str,
                 project_id: int, beneficiary_id: int | None = None) -> tuple[bool, str]:
    """Link an EXISTING, CALLER-OWNED project into a programme.

    Output: (ok, message). Refuses when the programme is not the caller's org's,
    or when the caller does not own the project.

    The link never mutates the project itself -- `projects.user_id` /
    `capital_investment_projects.user_id` remain untouched, so an existing user's
    project keeps working exactly as before even after being linked.
    """
    if not get_programme(get_db, org_id, user_id, programme_id):
        return False, "Programme not found."
    if kind not in ("standard", "generation_station"):
        return False, "Unknown project type."
    if not user_owns_project(get_db, user_id, kind, project_id):
        return False, "You can only link a project you own."
    # The optional beneficiary_id is untrusted too -- a crafted form must not be
    # able to attach the link to ANOTHER organisation's beneficiary
    # (Codex gate 1, HIGH).
    if beneficiary_id is not None and not beneficiary_belongs_to(
        get_db, org_id, programme_id, beneficiary_id
    ):
        return False, "Unknown beneficiary for this programme."

    with get_db() as c:
        apply_enterprise_guc(c, user_id)
        dup = c.execute(
            "SELECT 1 AS ok FROM enterprise_programme_project_links "
            "WHERE programme_id=? AND project_kind=? AND project_id=?",
            (programme_id, kind, project_id),
        ).fetchone()
        if dup:
            return False, "That project is already linked to this programme."
        link_id = _insert_returning_id(
            c,
            "INSERT INTO enterprise_programme_project_links "
            "(organisation_id, programme_id, beneficiary_id, project_kind, project_id, "
            " source_user_id, linked_by_user_id, design_strategy, status) "
            "VALUES (?,?,?,?,?,?,?,?,'linked')",
            (org_id, programme_id, beneficiary_id, kind, project_id, user_id, user_id,
             "generation_station" if kind == "generation_station" else "standard"),
        )
        _audit(c, org_id, programme_id, user_id, "project.link", kind, project_id,
               f"link={link_id}")
    return True, "Project linked."


def unlink_project(get_db, org_id: int, user_id: int, programme_id: int,
                   link_id: int) -> bool:
    """Remove a project link. Deletes only the LINK, never the project."""
    with get_db() as c:
        apply_enterprise_guc(c, user_id)
        cur = c.execute(
            "DELETE FROM enterprise_programme_project_links "
            "WHERE id=? AND programme_id=? AND organisation_id=?",
            (link_id, programme_id, org_id),
        )
        ok = (cur.rowcount or 0) > 0
        if ok:
            _audit(c, org_id, programme_id, user_id, "project.unlink", "link", link_id, "")
    return ok


def list_links(get_db, org_id: int, user_id: int, programme_id: int) -> list[dict]:
    """Projects linked into a programme."""
    with get_db() as c:
        apply_enterprise_guc(c, user_id)
        rows = c.execute(
            "SELECT * FROM enterprise_programme_project_links "
            "WHERE programme_id=? AND organisation_id=? ORDER BY id DESC",
            (programme_id, org_id),
        ).fetchall()
    return [dict(r) for r in rows]


def list_linkable_projects(get_db, user_id: int) -> dict[str, list[dict]]:
    """The caller's OWN projects, offered as link candidates.

    Only ever lists projects owned by this user -- the picker cannot show, and
    therefore cannot leak, another user's project.
    """
    out: dict[str, list[dict]] = {"standard": [], "generation_station": []}
    with get_db() as c:
        try:
            rows = c.execute(
                "SELECT id, name FROM projects WHERE user_id=? ORDER BY id DESC LIMIT 200",
                (user_id,),
            ).fetchall()
            out["standard"] = [dict(r) for r in rows]
        except Exception:
            pass
        try:
            rows = c.execute(
                "SELECT id, name FROM capital_investment_projects WHERE user_id=? "
                "ORDER BY id DESC LIMIT 200",
                (user_id,),
            ).fetchall()
            out["generation_station"] = [dict(r) for r in rows]
        except Exception:
            pass
    return out
