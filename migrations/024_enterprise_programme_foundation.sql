-- 024_enterprise_programme_foundation.sql
-- =====================================================================
-- Enterprise Solar Programme Management Module -- PHASE 1 FOUNDATION.
--
-- Adds the organisation/membership bridge that turns SolarPro from a
-- single-user-owned app into one that can also host many users under one
-- enterprise organisation -- WITHOUT changing how existing projects are
-- owned. Existing `projects` / `capital_investment_projects` rows keep
-- `WHERE id=? AND user_id=?` as their ONLY ownership predicate. Programmes
-- LINK to those projects (enterprise_programme_project_links); they never
-- take ownership of them. That is what makes this migration backward
-- compatible: an existing user who never touches /enterprise is unaffected.
--
-- Tables (all new, all additive):
--   enterprise_organisations           -- the tenant entity that never existed
--   enterprise_memberships             -- many users per organisation
--   enterprise_programmes              -- the principal domain object
--   enterprise_programme_phases
--   enterprise_beneficiaries
--   enterprise_programme_project_links -- programme <-> EXISTING SolarPro project
--   enterprise_programme_jobs          -- durable job queue (foundation only)
--   enterprise_programme_audit
--
-- ---------------------------------------------------------------------
-- RLS DESIGN -- READ THIS BEFORE CHANGING ANY POLICY BELOW
-- ---------------------------------------------------------------------
-- The app's existing `app.current_user` GUC carries the KEYCLOAK SUB
-- (app/security/tenant_context.py:191 -- `user_value = user_sub or ""`),
-- NOT the integer users.id, and it is '' for users on the legacy Flask
-- session path. A policy keyed on `user_id::text = current_user_sub()`
-- can therefore NEVER match. This module publishes its own GUC instead:
-- `app.current_user_id` (integer users.id), set by
-- enterprise_programme_repository.apply_enterprise_guc() on the connection
-- it already holds -- no change to web_app.py::get_db() required.
--
-- enterprise_memberships is the BASE policy and deliberately queries NO
-- other enterprise table. Every child table keys off
-- `organisation_id = ANY(current_enterprise_org_ids())`. This avoids a
-- policy that subqueries another RLS-protected table, which would either
-- recurse or silently return zero rows.
--
-- ENABLE, **NOT FORCE** (matches 015/022/023). RLS here is DEFENCE IN
-- DEPTH. The PRIMARY enforcement in Phase 1 is the app-layer membership
-- check keyed on session["user_id"] in enterprise_programme_repository.py.
-- This is NOT DB-enforced isolation and must not be described as such
-- until a later slice applies FORCE with the GUC path proven live.
--
-- Parallel-run escape: when NO enterprise identity context is set at all
-- (current_user_id_int() IS NULL AND current_user_sub() IS NULL), access is
-- admitted -- identical intent to 022/023, so applying this migration
-- cannot lock the app (or a migration runner) out before cutover.
--
-- Depends on: current_user_is_admin() (015), current_user_sub() (003),
-- sqlite_ts() (001). All re-declared CREATE OR REPLACE so this file
-- applies standalone.
--
-- Idempotent: IF NOT EXISTS throughout; DROP POLICY IF EXISTS before CREATE.
--
-- Apply deliberately via the gated workflow (dry-run first), NEVER auto.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 -- helper functions (idempotent re-declarations)
-- ---------------------------------------------------------------------

-- sqlite_ts(): the repo's TEXT timestamp default (from 001_mirror_sqlite.sql).
CREATE OR REPLACE FUNCTION sqlite_ts() RETURNS TEXT
    LANGUAGE sql STABLE AS $$
    SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
$$;

-- Considered admin iff the app.current_role GUC is exactly 'admin'.
CREATE OR REPLACE FUNCTION current_user_is_admin() RETURNS BOOLEAN
    LANGUAGE sql STABLE AS $$
    SELECT COALESCE(NULLIF(current_setting('app.current_role', true), ''), '') = 'admin'
$$;

-- The JWT `sub` claim, or NULL when unset.
CREATE OR REPLACE FUNCTION current_user_sub() RETURNS TEXT
    LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.current_user', true), '')
$$;

-- NEW: the integer users.id of the caller, published by the enterprise
-- module itself. NULL when unset (e.g. a non-enterprise request).
CREATE OR REPLACE FUNCTION current_user_id_int() RETURNS INTEGER
    LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.current_user_id', true), '')::INTEGER
$$;

-- TRUE when the request carries no enterprise identity at all. Used as the
-- parallel-run escape so this migration cannot lock anyone out pre-cutover.
CREATE OR REPLACE FUNCTION enterprise_no_identity() RETURNS BOOLEAN
    LANGUAGE sql STABLE AS $$
    SELECT current_user_id_int() IS NULL AND current_user_sub() IS NULL
$$;

-- The organisation ids the caller is an active member of.
-- Queries ONLY enterprise_memberships (the base policy table) -- never a
-- child table -- so no policy on a child table can recurse through this.
CREATE OR REPLACE FUNCTION current_enterprise_org_ids() RETURNS INTEGER[]
    LANGUAGE sql STABLE AS $$
    SELECT COALESCE(array_agg(m.organisation_id), ARRAY[]::INTEGER[])
    FROM enterprise_memberships m
    WHERE m.status = 'active'
      AND (
            (current_user_id_int() IS NOT NULL AND m.user_id = current_user_id_int())
         OR (current_user_sub()   IS NOT NULL AND m.keycloak_sub = current_user_sub())
      )
$$;

-- ---------------------------------------------------------------------
-- PART 2 -- tables
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS enterprise_organisations (
    id                 SERIAL PRIMARY KEY,
    tenant_id          UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    legal_name         TEXT NOT NULL,
    organisation_type  TEXT NOT NULL DEFAULT 'corporate_enterprise',
    country            TEXT DEFAULT '',
    default_currency   TEXT DEFAULT 'USD',
    timezone           TEXT DEFAULT 'UTC',
    brand_json         TEXT DEFAULT '{}',
    status             TEXT NOT NULL DEFAULT 'active',
    created_by_user_id INTEGER NOT NULL,
    created_at         TEXT DEFAULT sqlite_ts(),
    updated_at         TEXT DEFAULT sqlite_ts()
);

CREATE TABLE IF NOT EXISTS enterprise_memberships (
    id                 SERIAL PRIMARY KEY,
    organisation_id    INTEGER NOT NULL REFERENCES enterprise_organisations(id) ON DELETE CASCADE,
    user_id            INTEGER NOT NULL,
    keycloak_sub       TEXT DEFAULT '',
    role               TEXT NOT NULL DEFAULT 'enterprise_owner',
    permissions_json   TEXT DEFAULT '{}',
    region_scope_json  TEXT DEFAULT '[]',
    status             TEXT NOT NULL DEFAULT 'active',
    invited_by_user_id INTEGER,
    created_at         TEXT DEFAULT sqlite_ts(),
    updated_at         TEXT DEFAULT sqlite_ts(),
    UNIQUE (organisation_id, user_id)
);

CREATE TABLE IF NOT EXISTS enterprise_programmes (
    id                   SERIAL PRIMARY KEY,
    organisation_id      INTEGER NOT NULL REFERENCES enterprise_organisations(id) ON DELETE CASCADE,
    programme_code       TEXT NOT NULL,
    name                 TEXT NOT NULL,
    programme_type       TEXT NOT NULL DEFAULT 'residential',
    description          TEXT DEFAULT '',
    countries_json       TEXT DEFAULT '[]',
    regions_json         TEXT DEFAULT '[]',
    target_beneficiaries INTEGER DEFAULT 0,
    target_capacity_kwp  REAL DEFAULT 0,
    target_battery_kwh   REAL DEFAULT 0,
    budget_amount        REAL DEFAULT 0,
    currency             TEXT DEFAULT 'USD',
    delivery_model       TEXT DEFAULT '',
    procurement_strategy TEXT DEFAULT '',
    design_strategy      TEXT NOT NULL DEFAULT 'standard',
    status               TEXT NOT NULL DEFAULT 'draft',
    created_by_user_id   INTEGER NOT NULL,
    created_at           TEXT DEFAULT sqlite_ts(),
    updated_at           TEXT DEFAULT sqlite_ts(),
    UNIQUE (organisation_id, programme_code)
);

CREATE TABLE IF NOT EXISTS enterprise_programme_phases (
    id                     SERIAL PRIMARY KEY,
    organisation_id        INTEGER NOT NULL REFERENCES enterprise_organisations(id) ON DELETE CASCADE,
    programme_id           INTEGER NOT NULL REFERENCES enterprise_programmes(id) ON DELETE CASCADE,
    name                   TEXT NOT NULL,
    sequence_no            INTEGER NOT NULL DEFAULT 1,
    start_date             TEXT DEFAULT '',
    target_completion_date TEXT DEFAULT '',
    target_beneficiaries   INTEGER DEFAULT 0,
    target_capacity_kwp    REAL DEFAULT 0,
    status                 TEXT NOT NULL DEFAULT 'planned',
    created_at             TEXT DEFAULT sqlite_ts(),
    updated_at             TEXT DEFAULT sqlite_ts()
);

CREATE TABLE IF NOT EXISTS enterprise_beneficiaries (
    id                   SERIAL PRIMARY KEY,
    organisation_id      INTEGER NOT NULL REFERENCES enterprise_organisations(id) ON DELETE CASCADE,
    programme_id         INTEGER NOT NULL REFERENCES enterprise_programmes(id) ON DELETE CASCADE,
    phase_id             INTEGER REFERENCES enterprise_programme_phases(id) ON DELETE SET NULL,
    beneficiary_type     TEXT NOT NULL DEFAULT 'household',
    name                 TEXT NOT NULL,
    region               TEXT DEFAULT '',
    district             TEXT DEFAULT '',
    community            TEXT DEFAULT '',
    address              TEXT DEFAULT '',
    latitude             REAL,
    longitude            REAL,
    contact_name         TEXT DEFAULT '',
    contact_email        TEXT DEFAULT '',
    contact_phone        TEXT DEFAULT '',
    load_kwh_day         REAL DEFAULT 0,
    target_capacity_kwp  REAL DEFAULT 0,
    priority_score       INTEGER DEFAULT 0,
    qualification_status TEXT NOT NULL DEFAULT 'draft',
    metadata_json        TEXT DEFAULT '{}',
    created_by_user_id   INTEGER NOT NULL,
    created_at           TEXT DEFAULT sqlite_ts(),
    updated_at           TEXT DEFAULT sqlite_ts()
);

-- The backward-compatibility keystone: a programme LINKS an existing
-- SolarPro project. It does not own it. `project_kind` says which table
-- `project_id` points into. `source_user_id` records who owns it there.
CREATE TABLE IF NOT EXISTS enterprise_programme_project_links (
    id               SERIAL PRIMARY KEY,
    organisation_id  INTEGER NOT NULL REFERENCES enterprise_organisations(id) ON DELETE CASCADE,
    programme_id     INTEGER NOT NULL REFERENCES enterprise_programmes(id) ON DELETE CASCADE,
    beneficiary_id   INTEGER REFERENCES enterprise_beneficiaries(id) ON DELETE SET NULL,
    project_kind     TEXT NOT NULL CHECK (project_kind IN ('standard', 'generation_station')),
    project_id       INTEGER NOT NULL,
    source_user_id   INTEGER NOT NULL,
    linked_by_user_id INTEGER NOT NULL,
    design_strategy  TEXT NOT NULL DEFAULT 'standard',
    status           TEXT NOT NULL DEFAULT 'linked',
    linked_at        TEXT DEFAULT sqlite_ts(),
    UNIQUE (programme_id, project_kind, project_id)
);

-- Durable job queue. FOUNDATION ONLY in Phase 1 -- no bulk generation runs
-- yet. Exists because there is no Celery worker in production (Render free
-- tier, 1 gunicorn process) and the spec forbids synchronous bulk work.
-- Chunks must be idempotent and sized to finish well inside the request
-- timeout; `cursor_json` makes a job resumable across restarts.
CREATE TABLE IF NOT EXISTS enterprise_programme_jobs (
    id                 SERIAL PRIMARY KEY,
    organisation_id    INTEGER NOT NULL REFERENCES enterprise_organisations(id) ON DELETE CASCADE,
    programme_id       INTEGER REFERENCES enterprise_programmes(id) ON DELETE CASCADE,
    job_type           TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'queued',
    idempotency_key    TEXT NOT NULL,
    payload_json       TEXT DEFAULT '{}',
    cursor_json        TEXT DEFAULT '{}',
    progress_current   INTEGER DEFAULT 0,
    progress_total     INTEGER DEFAULT 0,
    attempts           INTEGER DEFAULT 0,
    max_attempts       INTEGER DEFAULT 3,
    locked_by          TEXT DEFAULT '',
    locked_until       TEXT DEFAULT '',
    last_error         TEXT DEFAULT '',
    created_by_user_id INTEGER NOT NULL,
    created_at         TEXT DEFAULT sqlite_ts(),
    updated_at         TEXT DEFAULT sqlite_ts(),
    UNIQUE (organisation_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS enterprise_programme_audit (
    id              SERIAL PRIMARY KEY,
    organisation_id INTEGER NOT NULL REFERENCES enterprise_organisations(id) ON DELETE CASCADE,
    programme_id    INTEGER,
    actor_user_id   INTEGER,
    action          TEXT NOT NULL,
    target_kind     TEXT DEFAULT '',
    target_id       INTEGER,
    details         TEXT DEFAULT '',
    created_at      TEXT DEFAULT sqlite_ts()
);

-- ---------------------------------------------------------------------
-- PART 3 -- indexes (portfolio queries are org/programme-scoped + paginated)
-- ---------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_ep_members_user
    ON enterprise_memberships (user_id, status);

-- Phase 1 allows exactly ONE active organisation per user. This is a DB-level
-- constraint, not an app-level check, because bootstrap is otherwise racy: two
-- concurrent POSTs can both observe "no membership" and both create an
-- organisation (Codex gate 1, LOW). A partial unique index makes the second
-- INSERT fail, and bootstrap_organisation() then re-reads the winner.
-- Lifting the one-org-per-user rule later means dropping this index.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ep_members_one_active_org_per_user
    ON enterprise_memberships (user_id)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_ep_members_org
    ON enterprise_memberships (organisation_id, status);
CREATE INDEX IF NOT EXISTS idx_ep_programmes_org_status
    ON enterprise_programmes (organisation_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ep_phases_programme
    ON enterprise_programme_phases (programme_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_ep_beneficiaries_programme
    ON enterprise_beneficiaries (programme_id, qualification_status, id);
CREATE INDEX IF NOT EXISTS idx_ep_beneficiaries_org
    ON enterprise_beneficiaries (organisation_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_ep_links_programme
    ON enterprise_programme_project_links (programme_id, project_kind);
CREATE INDEX IF NOT EXISTS idx_ep_jobs_claim
    ON enterprise_programme_jobs (status, locked_until, id);
CREATE INDEX IF NOT EXISTS idx_ep_audit_org_recent
    ON enterprise_programme_audit (organisation_id, created_at DESC);

-- ---------------------------------------------------------------------
-- PART 4 -- RLS: ENABLE (not FORCE). Defence in depth only -- see header.
-- ---------------------------------------------------------------------

ALTER TABLE enterprise_organisations           ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_memberships             ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_programmes              ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_programme_phases        ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_beneficiaries           ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_programme_project_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_programme_jobs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_programme_audit         ENABLE ROW LEVEL SECURITY;

-- BASE POLICY. Queries no other enterprise table -- this is what stops the
-- child policies below from recursing back through RLS.
DROP POLICY IF EXISTS enterprise_memberships_self_access ON enterprise_memberships;
CREATE POLICY enterprise_memberships_self_access
    ON enterprise_memberships
    FOR ALL
    USING (
        enterprise_no_identity()
        OR current_user_is_admin()
        OR (current_user_id_int() IS NOT NULL AND user_id = current_user_id_int())
        OR (current_user_sub()   IS NOT NULL AND keycloak_sub = current_user_sub())
    )
    WITH CHECK (
        enterprise_no_identity()
        OR current_user_is_admin()
        OR (current_user_id_int() IS NOT NULL AND user_id = current_user_id_int())
        OR (current_user_sub()   IS NOT NULL AND keycloak_sub = current_user_sub())
    );

DROP POLICY IF EXISTS enterprise_organisations_member_access ON enterprise_organisations;
CREATE POLICY enterprise_organisations_member_access
    ON enterprise_organisations
    FOR ALL
    USING (
        enterprise_no_identity()
        OR current_user_is_admin()
        OR id = ANY (current_enterprise_org_ids())
    )
    WITH CHECK (
        enterprise_no_identity()
        OR current_user_is_admin()
        OR id = ANY (current_enterprise_org_ids())
    );

-- Child tables: all keyed on organisation_id. Same shape for each.
DROP POLICY IF EXISTS enterprise_programmes_member_access ON enterprise_programmes;
CREATE POLICY enterprise_programmes_member_access
    ON enterprise_programmes FOR ALL
    USING      (enterprise_no_identity() OR current_user_is_admin() OR organisation_id = ANY (current_enterprise_org_ids()))
    WITH CHECK (enterprise_no_identity() OR current_user_is_admin() OR organisation_id = ANY (current_enterprise_org_ids()));

DROP POLICY IF EXISTS enterprise_programme_phases_member_access ON enterprise_programme_phases;
CREATE POLICY enterprise_programme_phases_member_access
    ON enterprise_programme_phases FOR ALL
    USING      (enterprise_no_identity() OR current_user_is_admin() OR organisation_id = ANY (current_enterprise_org_ids()))
    WITH CHECK (enterprise_no_identity() OR current_user_is_admin() OR organisation_id = ANY (current_enterprise_org_ids()));

DROP POLICY IF EXISTS enterprise_beneficiaries_member_access ON enterprise_beneficiaries;
CREATE POLICY enterprise_beneficiaries_member_access
    ON enterprise_beneficiaries FOR ALL
    USING      (enterprise_no_identity() OR current_user_is_admin() OR organisation_id = ANY (current_enterprise_org_ids()))
    WITH CHECK (enterprise_no_identity() OR current_user_is_admin() OR organisation_id = ANY (current_enterprise_org_ids()));

DROP POLICY IF EXISTS enterprise_programme_project_links_member_access ON enterprise_programme_project_links;
CREATE POLICY enterprise_programme_project_links_member_access
    ON enterprise_programme_project_links FOR ALL
    USING      (enterprise_no_identity() OR current_user_is_admin() OR organisation_id = ANY (current_enterprise_org_ids()))
    WITH CHECK (enterprise_no_identity() OR current_user_is_admin() OR organisation_id = ANY (current_enterprise_org_ids()));

DROP POLICY IF EXISTS enterprise_programme_jobs_member_access ON enterprise_programme_jobs;
CREATE POLICY enterprise_programme_jobs_member_access
    ON enterprise_programme_jobs FOR ALL
    USING      (enterprise_no_identity() OR current_user_is_admin() OR organisation_id = ANY (current_enterprise_org_ids()))
    WITH CHECK (enterprise_no_identity() OR current_user_is_admin() OR organisation_id = ANY (current_enterprise_org_ids()));

DROP POLICY IF EXISTS enterprise_programme_audit_member_access ON enterprise_programme_audit;
CREATE POLICY enterprise_programme_audit_member_access
    ON enterprise_programme_audit FOR ALL
    USING      (enterprise_no_identity() OR current_user_is_admin() OR organisation_id = ANY (current_enterprise_org_ids()))
    WITH CHECK (enterprise_no_identity() OR current_user_is_admin() OR organisation_id = ANY (current_enterprise_org_ids()));

-- ---------------------------------------------------------------------
-- PART 5 -- feature flags, seeded DARK.
--
-- CRITICAL: admin_settings is RLS-protected AND FORCE-enabled and is
-- admin-only (012_rls_batch5.sql:172, 015_global_table_policies.sql:230,
-- 018_force_rls_globals.sql:104 -- which even asserts the table is
-- invisible without app.current_role='admin'). A plain INSERT here would
-- match no policy and be SILENTLY DISCARDED, shipping the module with no
-- flags at all. The GUC below is what makes this write land.
-- ---------------------------------------------------------------------

SELECT set_config('app.current_role', 'admin', true);

INSERT INTO admin_settings (key, value, updated_at) VALUES
    ('enterprise_programme_enabled',      '0', CURRENT_TIMESTAMP),
    ('enterprise_programme_jobs_enabled', '0', CURRENT_TIMESTAMP),
    ('enterprise_programme_ai_enabled',   '0', CURRENT_TIMESTAMP)
ON CONFLICT (key) DO NOTHING;

COMMIT;
