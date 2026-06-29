# new_boq_hierarchy_schema.py
# Phase 1+2+3 schema migration for the Dynamic BOQ Library + Project Hierarchy.
#
# Relations declared:
#   boq_projects     1───┐
#                        ├── boq_buildings   N
#                        │       │
#                        │       └── boq_floors   N
#                        │                │
#                        │                └── boq_floor_items   N
#                        │                        │
#                        │                        ├── boq_floor_rate_buildup  1   (PII rates, internal-only)
#                        │                        └── equipment_catalog.id  (library item, nullable)
#                        │
#   marketplace_bom_items gains per-item build-up override columns (Phase 1)
#   equipment_catalog gains source_type + approval_status + submitter (Phase 2)
#
# Idempotent on SQLite (try/except per ALTER) and Postgres (IF NOT EXISTS).
# Called lazily by the BOQ-hierarchy + library routes on first hit.

from __future__ import annotations

import os
from typing import Iterable

_BOQ_SCHEMA_DONE = {"sqlite": False, "pg": False}


def _is_pg() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


# ─── SQLite DDL ───────────────────────────────────────────────────────────────
# SQLite FOREIGN KEYs are declared (documented) but enforced only when
# `PRAGMA foreign_keys = ON;` is set on the connection. On Render the live
# DB is Postgres so enforcement is real.

_SQLITE_CREATE = """
CREATE TABLE IF NOT EXISTS boq_projects (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                     INTEGER NOT NULL,
    project_name                TEXT NOT NULL,
    client_name                 TEXT DEFAULT '',
    location                    TEXT DEFAULT '',
    project_type                TEXT DEFAULT 'single_building',
    external_works_included     INTEGER DEFAULT 0,
    infrastructure_included     INTEGER DEFAULT 0,
    status                      TEXT DEFAULT 'draft',
    created_at                  TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at                  TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_boq_projects_user    ON boq_projects(user_id);
CREATE INDEX IF NOT EXISTS idx_boq_projects_status  ON boq_projects(user_id, status);

CREATE TABLE IF NOT EXISTS boq_buildings (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id                  INTEGER NOT NULL,
    building_name               TEXT NOT NULL,
    building_code               TEXT DEFAULT '',
    primary_purpose             TEXT NOT NULL,
    purpose_subtype             TEXT DEFAULT '',
    other_purpose_description   TEXT DEFAULT '',
    building_area               REAL DEFAULT 0,
    number_of_floors            INTEGER DEFAULT 1,
    basement_included           INTEGER DEFAULT 0,
    roof_level_included         INTEGER DEFAULT 0,
    external_area_included      INTEGER DEFAULT 0,
    status                      TEXT DEFAULT 'draft',
    created_at                  TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at                  TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES boq_projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_boq_buildings_project ON boq_buildings(project_id);

CREATE TABLE IF NOT EXISTS boq_floors (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    building_id                 INTEGER NOT NULL,
    project_id                  INTEGER NOT NULL,
    floor_name                  TEXT NOT NULL,
    floor_level                 INTEGER DEFAULT 0,
    floor_type                  TEXT DEFAULT 'ground',
    status                      TEXT DEFAULT 'draft',
    created_at                  TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at                  TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (building_id) REFERENCES boq_buildings(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id)  REFERENCES boq_projects(id)  ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_boq_floors_building ON boq_floors(building_id);
CREATE INDEX IF NOT EXISTS idx_boq_floors_project  ON boq_floors(project_id);

CREATE TABLE IF NOT EXISTS boq_floor_items (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    floor_id                    INTEGER NOT NULL,
    building_id                 INTEGER NOT NULL,
    project_id                  INTEGER NOT NULL,
    user_id                     INTEGER NOT NULL,
    section                     TEXT DEFAULT 'preliminaries',
    subsection                  TEXT DEFAULT '',
    library_item_id             INTEGER,
    supplier_id                 INTEGER,
    item_no                     TEXT DEFAULT '',
    description                 TEXT NOT NULL,
    specification               TEXT DEFAULT '',
    unit                        TEXT DEFAULT 'No.',
    qty                         REAL DEFAULT 1,
    final_built_up_rate         REAL DEFAULT 0,
    total_amount                REAL DEFAULT 0,
    remarks                     TEXT DEFAULT '',
    source_type                 TEXT DEFAULT 'master_library',
    approval_status             TEXT DEFAULT 'project_only',
    created_at                  TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at                  TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (floor_id)        REFERENCES boq_floors(id)         ON DELETE CASCADE,
    FOREIGN KEY (building_id)     REFERENCES boq_buildings(id)      ON DELETE CASCADE,
    FOREIGN KEY (project_id)      REFERENCES boq_projects(id)       ON DELETE CASCADE,
    FOREIGN KEY (library_item_id) REFERENCES equipment_catalog(id)  ON DELETE SET NULL,
    FOREIGN KEY (supplier_id)     REFERENCES suppliers(id)          ON DELETE SET NULL,
    FOREIGN KEY (user_id)         REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_boq_floor_items_floor    ON boq_floor_items(floor_id);
CREATE INDEX IF NOT EXISTS idx_boq_floor_items_building ON boq_floor_items(building_id);
CREATE INDEX IF NOT EXISTS idx_boq_floor_items_project  ON boq_floor_items(project_id);
CREATE INDEX IF NOT EXISTS idx_boq_floor_items_user     ON boq_floor_items(user_id);
CREATE INDEX IF NOT EXISTS idx_boq_floor_items_library  ON boq_floor_items(library_item_id);

CREATE TABLE IF NOT EXISTS boq_floor_rate_buildup (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    floor_item_id               INTEGER NOT NULL UNIQUE,
    project_id                  INTEGER NOT NULL,
    user_id                     INTEGER NOT NULL,
    basic_price                 REAL DEFAULT 0,
    supply_rate                 REAL DEFAULT 0,
    install_rate                REAL DEFAULT 0,
    overhead_pct                REAL DEFAULT 0,
    profit_pct                  REAL DEFAULT 0,
    contingency_pct             REAL DEFAULT 0,
    vat_pct                     REAL DEFAULT 0,
    final_built_up_rate         REAL DEFAULT 0,
    total_amount                REAL DEFAULT 0,
    notes                       TEXT DEFAULT '',
    created_at                  TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at                  TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (floor_item_id) REFERENCES boq_floor_items(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id)    REFERENCES boq_projects(id)    ON DELETE CASCADE,
    FOREIGN KEY (user_id)       REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_boq_rate_buildup_project ON boq_floor_rate_buildup(project_id);

CREATE TABLE IF NOT EXISTS boq_audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    action       TEXT NOT NULL,
    target_kind  TEXT NOT NULL,
    target_id    INTEGER NOT NULL,
    details      TEXT DEFAULT '',
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_boq_audit_user   ON boq_audit_log(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_boq_audit_target ON boq_audit_log(target_kind, target_id);
"""

# ALTERs are applied separately because SQLite < 3.35 won't IF NOT EXISTS them.
# Each ALTER is wrapped in its own try so partial earlier runs are tolerated.
_SQLITE_ALTERS_BOM_ITEMS = [
    "ALTER TABLE marketplace_bom_items ADD COLUMN basic_price REAL",
    "ALTER TABLE marketplace_bom_items ADD COLUMN supply_rate REAL",
    "ALTER TABLE marketplace_bom_items ADD COLUMN install_rate REAL",
    "ALTER TABLE marketplace_bom_items ADD COLUMN overhead_pct REAL",
    "ALTER TABLE marketplace_bom_items ADD COLUMN profit_pct REAL",
    "ALTER TABLE marketplace_bom_items ADD COLUMN contingency_pct REAL",
    "ALTER TABLE marketplace_bom_items ADD COLUMN vat_pct REAL",
    "ALTER TABLE marketplace_bom_items ADD COLUMN final_built_up_rate REAL",
    "ALTER TABLE marketplace_bom_items ADD COLUMN remarks TEXT DEFAULT ''",
    "ALTER TABLE marketplace_bom_items ADD COLUMN source_type TEXT DEFAULT 'master_library'",
    "ALTER TABLE marketplace_bom_items ADD COLUMN approval_status TEXT DEFAULT 'project_only'",
]

_SQLITE_ALTERS_CATALOG = [
    "ALTER TABLE equipment_catalog ADD COLUMN source_type TEXT DEFAULT 'master_library'",
    "ALTER TABLE equipment_catalog ADD COLUMN approval_status TEXT DEFAULT 'approved_library_item'",
    "ALTER TABLE equipment_catalog ADD COLUMN submitted_by_user_id INTEGER",
]

_SQLITE_ALTERS_BOM_RATES = [
    "ALTER TABLE marketplace_bom_rates ADD COLUMN contingency_pct REAL DEFAULT 0",
]

# 2026-06-21: real BOQ deliverables nest items under Bill -> Section ->
# Sub-section. Add the columns to the existing boq_floor_items + a
# per-floor contingency percentage (default 10 per the auditorium sample).
_SQLITE_ALTERS_FLOOR_BILLS = [
    "ALTER TABLE boq_floor_items ADD COLUMN bill_no INTEGER",
    "ALTER TABLE boq_floor_items ADD COLUMN bill_name TEXT DEFAULT ''",
    "ALTER TABLE boq_floor_items ADD COLUMN section_letter TEXT DEFAULT ''",
    "ALTER TABLE boq_floor_items ADD COLUMN subsection_label TEXT DEFAULT ''",
    "ALTER TABLE boq_floor_items ADD COLUMN item_no_display TEXT DEFAULT ''",
    "ALTER TABLE boq_floors      ADD COLUMN contingency_pct REAL DEFAULT 10",
]

# 2026-06-28 owner spec: rate engine v3. supply/install are now PERCENTAGES,
# contingency is dropped, and a vat_in_basic flag suppresses VAT on supply
# when the supplier invoice already included it. We keep supply_rate /
# install_rate columns (they now hold the COMPUTED amounts per unit) and
# add explicit input-side columns for the percentages + the new flag.
_SQLITE_ALTERS_RATE_V3 = [
    "ALTER TABLE boq_floor_rate_buildup ADD COLUMN supply_pct REAL DEFAULT 0",
    "ALTER TABLE boq_floor_rate_buildup ADD COLUMN install_pct REAL DEFAULT 0",
    "ALTER TABLE boq_floor_rate_buildup ADD COLUMN vat_in_basic INTEGER DEFAULT 0",
    # 2026-06-28: per-project free-text instructions surfaced on overview +
    # rendered above the BOQ table on Excel / PDF exports.
    "ALTER TABLE boq_projects ADD COLUMN instructions TEXT DEFAULT ''",
    # 2026-06-28 (3rd round): per-section editable heading + instructions.
    """CREATE TABLE IF NOT EXISTS boq_section_meta (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        floor_id        INTEGER NOT NULL,
        bill_no         INTEGER NOT NULL,
        section_letter  TEXT NOT NULL,
        custom_title    TEXT DEFAULT '',
        instructions    TEXT DEFAULT '',
        updated_at      TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(floor_id, bill_no, section_letter)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_boq_section_meta_floor ON boq_section_meta(floor_id, bill_no, section_letter)",
]


# 2026-06-29: Build by Template retired. The BOQ engine is unified to two
# modes only -- Section-by-Section + Complete BOQ. `build_mode` defaults to
# 'complete_boq' so any pre-refactor project lands on the new screen with all
# its existing sections shown together (silent auto-migration). Per
# projectboq build update1.txt lines 426-447, 679-697.
_SQLITE_ALTERS_BUILD_MODE = [
    "ALTER TABLE boq_projects ADD COLUMN build_mode TEXT DEFAULT 'complete_boq'",
    "ALTER TABLE boq_floor_items ADD COLUMN service_code TEXT DEFAULT ''",
]


# ─── Postgres DDL ─────────────────────────────────────────────────────────────

_PG_CREATE_TABLES = [
    """CREATE TABLE IF NOT EXISTS boq_projects (
        id                          SERIAL PRIMARY KEY,
        user_id                     INTEGER NOT NULL REFERENCES users(id),
        project_name                VARCHAR(300) NOT NULL,
        client_name                 VARCHAR(300) DEFAULT '',
        location                    VARCHAR(300) DEFAULT '',
        project_type                VARCHAR(40) DEFAULT 'single_building',
        external_works_included     INTEGER DEFAULT 0,
        infrastructure_included     INTEGER DEFAULT 0,
        status                      VARCHAR(40) DEFAULT 'draft',
        created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_boq_projects_user   ON boq_projects(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_boq_projects_status ON boq_projects(user_id, status)",

    """CREATE TABLE IF NOT EXISTS boq_buildings (
        id                          SERIAL PRIMARY KEY,
        project_id                  INTEGER NOT NULL REFERENCES boq_projects(id) ON DELETE CASCADE,
        building_name               VARCHAR(300) NOT NULL,
        building_code               VARCHAR(80) DEFAULT '',
        primary_purpose             VARCHAR(40) NOT NULL,
        purpose_subtype             VARCHAR(80) DEFAULT '',
        other_purpose_description   VARCHAR(300) DEFAULT '',
        building_area               REAL DEFAULT 0,
        number_of_floors            INTEGER DEFAULT 1,
        basement_included           INTEGER DEFAULT 0,
        roof_level_included         INTEGER DEFAULT 0,
        external_area_included      INTEGER DEFAULT 0,
        status                      VARCHAR(40) DEFAULT 'draft',
        created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_boq_buildings_project ON boq_buildings(project_id)",

    """CREATE TABLE IF NOT EXISTS boq_floors (
        id           SERIAL PRIMARY KEY,
        building_id  INTEGER NOT NULL REFERENCES boq_buildings(id) ON DELETE CASCADE,
        project_id   INTEGER NOT NULL REFERENCES boq_projects(id)  ON DELETE CASCADE,
        floor_name   VARCHAR(120) NOT NULL,
        floor_level  INTEGER DEFAULT 0,
        floor_type   VARCHAR(20) DEFAULT 'ground',
        status       VARCHAR(40) DEFAULT 'draft',
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_boq_floors_building ON boq_floors(building_id)",
    "CREATE INDEX IF NOT EXISTS idx_boq_floors_project  ON boq_floors(project_id)",

    """CREATE TABLE IF NOT EXISTS boq_floor_items (
        id                    SERIAL PRIMARY KEY,
        floor_id              INTEGER NOT NULL REFERENCES boq_floors(id)        ON DELETE CASCADE,
        building_id           INTEGER NOT NULL REFERENCES boq_buildings(id)     ON DELETE CASCADE,
        project_id            INTEGER NOT NULL REFERENCES boq_projects(id)      ON DELETE CASCADE,
        user_id               INTEGER NOT NULL REFERENCES users(id),
        section               VARCHAR(80) DEFAULT 'preliminaries',
        subsection            VARCHAR(120) DEFAULT '',
        library_item_id       INTEGER REFERENCES equipment_catalog(id) ON DELETE SET NULL,
        supplier_id           INTEGER REFERENCES suppliers(id)         ON DELETE SET NULL,
        item_no               VARCHAR(40) DEFAULT '',
        description           VARCHAR(500) NOT NULL,
        specification         TEXT DEFAULT '',
        unit                  VARCHAR(20) DEFAULT 'No.',
        qty                   REAL DEFAULT 1,
        final_built_up_rate   REAL DEFAULT 0,
        total_amount          REAL DEFAULT 0,
        remarks               TEXT DEFAULT '',
        source_type           VARCHAR(40) DEFAULT 'master_library',
        approval_status       VARCHAR(40) DEFAULT 'project_only',
        created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_boq_floor_items_floor    ON boq_floor_items(floor_id)",
    "CREATE INDEX IF NOT EXISTS idx_boq_floor_items_building ON boq_floor_items(building_id)",
    "CREATE INDEX IF NOT EXISTS idx_boq_floor_items_project  ON boq_floor_items(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_boq_floor_items_user     ON boq_floor_items(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_boq_floor_items_library  ON boq_floor_items(library_item_id)",

    """CREATE TABLE IF NOT EXISTS boq_floor_rate_buildup (
        id                    SERIAL PRIMARY KEY,
        floor_item_id         INTEGER NOT NULL UNIQUE REFERENCES boq_floor_items(id) ON DELETE CASCADE,
        project_id            INTEGER NOT NULL REFERENCES boq_projects(id) ON DELETE CASCADE,
        user_id               INTEGER NOT NULL REFERENCES users(id),
        basic_price           REAL DEFAULT 0,
        supply_rate           REAL DEFAULT 0,
        install_rate          REAL DEFAULT 0,
        overhead_pct          REAL DEFAULT 0,
        profit_pct            REAL DEFAULT 0,
        contingency_pct       REAL DEFAULT 0,
        vat_pct               REAL DEFAULT 0,
        final_built_up_rate   REAL DEFAULT 0,
        total_amount          REAL DEFAULT 0,
        notes                 TEXT DEFAULT '',
        created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_boq_rate_buildup_project ON boq_floor_rate_buildup(project_id)",

    """CREATE TABLE IF NOT EXISTS boq_audit_log (
        id           SERIAL PRIMARY KEY,
        user_id      INTEGER NOT NULL REFERENCES users(id),
        action       VARCHAR(80) NOT NULL,
        target_kind  VARCHAR(40) NOT NULL,
        target_id    INTEGER NOT NULL,
        details      TEXT DEFAULT '',
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_boq_audit_user   ON boq_audit_log(user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_boq_audit_target ON boq_audit_log(target_kind, target_id)",

    # Phase 1 ALTERs on marketplace_bom_items (per-item build-up overrides).
    "ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS basic_price REAL",
    "ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS supply_rate REAL",
    "ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS install_rate REAL",
    "ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS overhead_pct REAL",
    "ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS profit_pct REAL",
    "ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS contingency_pct REAL",
    "ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS vat_pct REAL",
    "ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS final_built_up_rate REAL",
    "ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS remarks TEXT DEFAULT ''",
    "ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS source_type VARCHAR(40) DEFAULT 'master_library'",
    "ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS approval_status VARCHAR(40) DEFAULT 'project_only'",

    # Phase 2 ALTERs on equipment_catalog (library item provenance).
    "ALTER TABLE equipment_catalog ADD COLUMN IF NOT EXISTS source_type VARCHAR(40) DEFAULT 'master_library'",
    "ALTER TABLE equipment_catalog ADD COLUMN IF NOT EXISTS approval_status VARCHAR(40) DEFAULT 'approved_library_item'",
    "ALTER TABLE equipment_catalog ADD COLUMN IF NOT EXISTS submitted_by_user_id INTEGER",

    # Phase 1 rate-table extension (spec adds contingency to the build-up).
    "ALTER TABLE marketplace_bom_rates ADD COLUMN IF NOT EXISTS contingency_pct REAL DEFAULT 0",

    # 2026-06-21 Bill -> Section -> Sub-section structure for floor items.
    "ALTER TABLE boq_floor_items ADD COLUMN IF NOT EXISTS bill_no INTEGER",
    "ALTER TABLE boq_floor_items ADD COLUMN IF NOT EXISTS bill_name VARCHAR(120) DEFAULT ''",
    "ALTER TABLE boq_floor_items ADD COLUMN IF NOT EXISTS section_letter VARCHAR(8) DEFAULT ''",
    "ALTER TABLE boq_floor_items ADD COLUMN IF NOT EXISTS subsection_label VARCHAR(20) DEFAULT ''",
    "ALTER TABLE boq_floor_items ADD COLUMN IF NOT EXISTS item_no_display VARCHAR(8) DEFAULT ''",
    "ALTER TABLE boq_floors      ADD COLUMN IF NOT EXISTS contingency_pct REAL DEFAULT 10",

    # 2026-06-25 SOC 2 M1.6 -- tenant_id columns. The dedicated migration
    # (migrations/007_rls_boq_hierarchy.sql) handles backfill + RLS policies
    # on Postgres; the ALTERs below cover fresh DBs that haven't run it yet.
    "ALTER TABLE boq_projects           ADD COLUMN IF NOT EXISTS tenant_id UUID",
    "ALTER TABLE boq_buildings          ADD COLUMN IF NOT EXISTS tenant_id UUID",
    "ALTER TABLE boq_floors             ADD COLUMN IF NOT EXISTS tenant_id UUID",
    "ALTER TABLE boq_floor_items        ADD COLUMN IF NOT EXISTS tenant_id UUID",
    "ALTER TABLE boq_floor_rate_buildup ADD COLUMN IF NOT EXISTS tenant_id UUID",
    "ALTER TABLE boq_audit_log          ADD COLUMN IF NOT EXISTS tenant_id UUID",
    "CREATE INDEX IF NOT EXISTS idx_boq_projects_tenant           ON boq_projects(tenant_id)",
    "CREATE INDEX IF NOT EXISTS idx_boq_buildings_tenant          ON boq_buildings(tenant_id)",
    "CREATE INDEX IF NOT EXISTS idx_boq_floors_tenant             ON boq_floors(tenant_id)",
    "CREATE INDEX IF NOT EXISTS idx_boq_floor_items_tenant        ON boq_floor_items(tenant_id)",
    "CREATE INDEX IF NOT EXISTS idx_boq_floor_rate_buildup_tenant ON boq_floor_rate_buildup(tenant_id)",
    "CREATE INDEX IF NOT EXISTS idx_boq_audit_log_tenant          ON boq_audit_log(tenant_id)",
]


# 2026-06-25 SOC 2 M1.6 -- SQLite mirror. SQLite stores UUIDs as TEXT.
_SQLITE_ALTERS_BOQ_TENANT = [
    "ALTER TABLE boq_projects           ADD COLUMN tenant_id TEXT",
    "ALTER TABLE boq_buildings          ADD COLUMN tenant_id TEXT",
    "ALTER TABLE boq_floors             ADD COLUMN tenant_id TEXT",
    "ALTER TABLE boq_floor_items        ADD COLUMN tenant_id TEXT",
    "ALTER TABLE boq_floor_rate_buildup ADD COLUMN tenant_id TEXT",
    "ALTER TABLE boq_audit_log          ADD COLUMN tenant_id TEXT",
]


_PG_ALTERS_RATE_V3 = [
    "ALTER TABLE boq_floor_rate_buildup ADD COLUMN IF NOT EXISTS supply_pct REAL DEFAULT 0",
    "ALTER TABLE boq_floor_rate_buildup ADD COLUMN IF NOT EXISTS install_pct REAL DEFAULT 0",
    "ALTER TABLE boq_floor_rate_buildup ADD COLUMN IF NOT EXISTS vat_in_basic INTEGER DEFAULT 0",
    "ALTER TABLE boq_projects ADD COLUMN IF NOT EXISTS instructions TEXT DEFAULT ''",
    # 2026-06-28 (3rd round): per-section editable heading + instructions.
    """CREATE TABLE IF NOT EXISTS boq_section_meta (
        id              SERIAL PRIMARY KEY,
        floor_id        INTEGER NOT NULL,
        bill_no         INTEGER NOT NULL,
        section_letter  VARCHAR(8) NOT NULL,
        custom_title    VARCHAR(300) DEFAULT '',
        instructions    TEXT DEFAULT '',
        updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(floor_id, bill_no, section_letter)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_boq_section_meta_floor ON boq_section_meta(floor_id, bill_no, section_letter)",
]


# 2026-06-29: Build by Template retired -- see _SQLITE_ALTERS_BUILD_MODE.
_PG_ALTERS_BUILD_MODE = [
    "ALTER TABLE boq_projects ADD COLUMN IF NOT EXISTS build_mode VARCHAR(40) DEFAULT 'complete_boq'",
    "ALTER TABLE boq_floor_items ADD COLUMN IF NOT EXISTS service_code VARCHAR(40) DEFAULT ''",
]


def _try_each(c, stmts: Iterable[str]) -> None:
    """Run each statement in its own try block so one failure (already exists,
    legacy schema mismatch) doesn't abort the rest."""
    for s in stmts:
        try:
            c.execute(s)
        except Exception:
            pass


def ensure_boq_hierarchy_schema(get_db_fn) -> None:
    """Idempotent schema bootstrap. Called by routes the first time they're
    hit. `get_db_fn` is web_app.get_db (a context-manager returning a
    cursor-like connection)."""
    if _is_pg():
        if _BOQ_SCHEMA_DONE["pg"]:
            return
        with get_db_fn() as c:
            _try_each(c, _PG_CREATE_TABLES)
            _try_each(c, _PG_ALTERS_RATE_V3)
            _try_each(c, _PG_ALTERS_BUILD_MODE)
        _BOQ_SCHEMA_DONE["pg"] = True
        return

    if _BOQ_SCHEMA_DONE["sqlite"]:
        return
    with get_db_fn() as c:
        try:
            c.executescript(_SQLITE_CREATE)
        except Exception:
            # Fall back to per-statement so one busted CREATE doesn't sink the rest.
            for stmt in _SQLITE_CREATE.split(";"):
                s = stmt.strip()
                if s:
                    try:
                        c.execute(s)
                    except Exception:
                        pass
        _try_each(c, _SQLITE_ALTERS_BOM_ITEMS)
        _try_each(c, _SQLITE_ALTERS_CATALOG)
        _try_each(c, _SQLITE_ALTERS_BOM_RATES)
        _try_each(c, _SQLITE_ALTERS_FLOOR_BILLS)
        _try_each(c, _SQLITE_ALTERS_RATE_V3)
        _try_each(c, _SQLITE_ALTERS_BUILD_MODE)
        _try_each(c, _SQLITE_ALTERS_BOQ_TENANT)
    _BOQ_SCHEMA_DONE["sqlite"] = True


def boq_audit(get_db_fn, user_id: int, action: str, target_kind: str,
              target_id: int, details: str = "") -> None:
    """Append a row to boq_audit_log. Non-raising — best-effort logging."""
    try:
        ensure_boq_hierarchy_schema(get_db_fn)
        with get_db_fn() as c:
            c.execute(
                "INSERT INTO boq_audit_log (user_id, action, target_kind, target_id, details) "
                "VALUES (?, ?, ?, ?, ?)",
                (int(user_id), str(action)[:80], str(target_kind)[:40],
                 int(target_id), str(details)[:1000]),
            )
    except Exception:
        pass
