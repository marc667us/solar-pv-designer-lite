-- =============================================================================
-- 027 -- Enterprise Solar Programme: beneficiaries, import staging, jobs
--
-- THE LAST MIGRATION OF RELEASE 1. The Supervisor's correction R2 caps Release 1 at three
-- live migrations (025 tenancy+RBAC, 026 lifecycle+templates, 027 this one), because the
-- free-tier Postgres has already had one near-miss: migration 024's first apply died
-- mid-way on SQL-function parse order. Every remaining Release-1 table therefore lands
-- here -- including tables that slices 6 to 9 will fill and that nothing reads yet.
--
-- An empty table that a later slice fills is cheap. A fourth apply against a production
-- database that has already failed once is not.
--
-- RULES THIS FILE FOLLOWS (learned the hard way -- see migrations 024 and 026):
--   1. Table names must not collide with anything already ON LIVE. Migration 024 owns
--      `enterprise_programmes` and `enterprise_programme_phases`; CREATE TABLE IF NOT
--      EXISTS would SILENTLY SKIP a colliding table, leave the old shape in place, and
--      kill the apply at the first foreign key that expects the new one.
--   2. A SQL function definition comes AFTER the tables it reads. 024 died on this.
--   3. Every reference to a tenant-owned row is a TENANT-SCOPED COMPOSITE foreign key.
--      With a bare `programme_id` FK, tenant A could point a row at tenant B's programme:
--      ids are globally unique, so Postgres would accept it, and B deleting that
--      programme would cascade into A's data -- cross-tenant corruption through a foreign
--      key, with neither tenant ever seeing the other's rows.
--   4. RLS on every table. Defence in depth: the app is the primary tenant boundary
--      (every query is scoped by the caller's RESOLVED tenant id, never by an id from the
--      URL), and the database is the last line.
--
-- NOT APPLIED TO LIVE. The module is dark (`enterprise_rebuild_enabled`='0').
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- PART 1 -- the beneficiary register
-- -----------------------------------------------------------------------------
-- WHAT A BENEFICIARY IS: the school, clinic or farm the programme exists to serve. It is
-- the unit that BECOMES a project (slice 7), which is why its status column speaks doc 3's
-- PROJECT_STATUSES vocabulary rather than a parallel one of its own -- doc 3 starts that
-- list at "Beneficiary Registered" for exactly this reason.
--
-- The 22 attribute columns are the same 22 keys a template may declare in its
-- `required_beneficiary_fields` (constants.BENEFICIARY_FIELD_SPEC). Explicit columns, not
-- a JSON blob: these are queried, filtered, scored (slice 6) and fed to the design engine
-- (slice 7), and a blob would mean every one of those reaches into JSON for a value the
-- database could have typed and indexed.
CREATE TABLE IF NOT EXISTS enterprise_beneficiaries (
    id                     bigserial PRIMARY KEY,
    tenant_id              uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    programme_id           bigint NOT NULL,
    area_id                bigint,
    code                   text NOT NULL,
    beneficiary_type       text NOT NULL,
    status                 text NOT NULL DEFAULT 'Beneficiary Registered',

    -- the 22 fields of constants.BENEFICIARY_FIELD_SPEC
    name                   text NOT NULL,
    region                 text,
    district               text,
    community              text,
    address                text,
    gps_coordinates        text,
    latitude               numeric,          -- parsed out of gps_coordinates on write, so
    longitude              numeric,          -- a map query never has to parse a string
    contact_person         text,
    contact_details        text,
    ownership              text,
    building_type          text,
    occupancy              numeric,
    existing_energy_source text,
    electricity_consumption numeric,
    tariff                 numeric,
    generator_details      text,
    roof_area              numeric,
    land_availability      numeric,
    critical_loads         text,
    priority_loads         text,
    funding_eligibility    text,
    social_impact_class    text,
    priority_ranking       numeric,

    -- provenance. C14 (traceability) needs to answer "where did this project come from"
    -- for every generated project, and the answer starts here.
    import_batch_id        bigint,
    approved_by_user_id    integer,
    approved_at            timestamptz,
    created_by_user_id     integer,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT fk_beneficiary_programme FOREIGN KEY (tenant_id, programme_id)
        REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_beneficiary_area FOREIGN KEY (tenant_id, area_id)
        REFERENCES enterprise_geographic_areas (tenant_id, id),
    CONSTRAINT uq_ent_beneficiary_tenant_id UNIQUE (tenant_id, id),
    -- PROGRAMME-scoped unique key, so that enterprise_project_links below can hold a foreign
    -- key proving its beneficiary belongs to the SAME programme it claims to serve. With only
    -- (tenant_id, id) to point at, a link row in programme P1 could reference a beneficiary
    -- from P2 in the same tenant, and control C14's traceability chain would quietly lie.
    CONSTRAINT uq_ent_beneficiary_programme_id UNIQUE (tenant_id, programme_id, id),
    CONSTRAINT ck_ent_beneficiary_status CHECK (status IN (
        'Beneficiary Registered', 'Qualification Pending', 'Qualified', 'Not Qualified',
        'Template Assigned', 'Project Generated', 'Rejected', 'Archived'))
);

-- The register's identity key. A duplicate import of the same spreadsheet must not double
-- every school in the programme -- and "did I already import this?" is a question the
-- database can answer definitively, where a fuzzy name match cannot.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_beneficiary_code
    ON enterprise_beneficiaries (tenant_id, programme_id, code);

CREATE INDEX IF NOT EXISTS ix_ent_beneficiary_status
    ON enterprise_beneficiaries (tenant_id, programme_id, status);
CREATE INDEX IF NOT EXISTS ix_ent_beneficiary_area
    ON enterprise_beneficiaries (tenant_id, area_id);
-- The duplicate-detection probe (slice 5) matches on name within a community; without
-- this, every imported row costs a sequential scan of the whole register.
CREATE INDEX IF NOT EXISTS ix_ent_beneficiary_dup_probe
    ON enterprise_beneficiaries (tenant_id, programme_id, community, name);

-- -----------------------------------------------------------------------------
-- PART 2 -- import staging
-- -----------------------------------------------------------------------------
-- An import is STAGED, never applied straight to the register. A 4000-row spreadsheet with
-- 12 bad rows must not be a choice between importing nothing and importing 12 broken
-- records -- so every row is parsed, mapped, validated and shown back BEFORE a single
-- beneficiary exists, and the operator commits the good ones.
--
-- The raw row is kept verbatim alongside the mapped one. When somebody asks in six months
-- why a school's roof area is 40 rather than 400, the answer is in this table.
CREATE TABLE IF NOT EXISTS enterprise_import_batches (
    id                 bigserial PRIMARY KEY,
    tenant_id          uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    programme_id       bigint NOT NULL,
    filename           text,
    status             text NOT NULL DEFAULT 'Staged',
    column_mapping     jsonb NOT NULL DEFAULT '{}'::jsonb,  -- spreadsheet header -> field key
    -- The fallback beneficiary type chosen at upload. Persisted, not just passed once:
    -- a re-map has to replay the ORIGINAL choices or rows that were valid become invalid
    -- for a reason the operator never touched (Codex slice-5 round 2).
    default_type       text NOT NULL DEFAULT '',
    total_rows         integer NOT NULL DEFAULT 0,
    valid_rows         integer NOT NULL DEFAULT 0,
    error_rows         integer NOT NULL DEFAULT 0,
    duplicate_rows     integer NOT NULL DEFAULT 0,
    imported_rows      integer NOT NULL DEFAULT 0,
    created_by_user_id integer,
    created_at         timestamptz NOT NULL DEFAULT now(),
    committed_at       timestamptz,
    CONSTRAINT fk_import_batch_programme FOREIGN KEY (tenant_id, programme_id)
        REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT uq_ent_import_batch_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT ck_ent_import_batch_status CHECK (status IN
        ('Staged', 'Committed', 'Cancelled'))
);

CREATE INDEX IF NOT EXISTS ix_ent_import_batch_programme
    ON enterprise_import_batches (tenant_id, programme_id, status);

CREATE TABLE IF NOT EXISTS enterprise_import_rows (
    id              bigserial PRIMARY KEY,
    tenant_id       uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    batch_id        bigint NOT NULL,
    row_no          integer NOT NULL,          -- the line in the user's spreadsheet
    raw_json        jsonb NOT NULL DEFAULT '{}'::jsonb,   -- exactly what was in the file
    mapped_json     jsonb NOT NULL DEFAULT '{}'::jsonb,   -- after mapping + coercion
    status          text NOT NULL DEFAULT 'Valid',
    errors_json     jsonb NOT NULL DEFAULT '[]'::jsonb,   -- why, per field
    beneficiary_id  bigint,                    -- set on commit; the row's provenance link
    CONSTRAINT fk_import_row_batch FOREIGN KEY (tenant_id, batch_id)
        REFERENCES enterprise_import_batches (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_import_row_beneficiary FOREIGN KEY (tenant_id, beneficiary_id)
        REFERENCES enterprise_beneficiaries (tenant_id, id) ON DELETE SET NULL,
    CONSTRAINT ck_ent_import_row_status CHECK (status IN
        ('Valid', 'Error', 'Duplicate', 'Imported', 'Skipped'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_import_row
    ON enterprise_import_rows (tenant_id, batch_id, row_no);
CREATE INDEX IF NOT EXISTS ix_ent_import_row_status
    ON enterprise_import_rows (tenant_id, batch_id, status);

-- -----------------------------------------------------------------------------
-- PART 3 -- site qualification (slice 6 fills this; created here per R2)
-- -----------------------------------------------------------------------------
-- Control C02: no beneficiary becomes a project without qualification. The SCORE is kept,
-- not just the verdict -- "why was Kpando SHS rejected" is the question an appeal asks, and
-- a bare Not-Qualified flag cannot answer it.
CREATE TABLE IF NOT EXISTS enterprise_site_qualifications (
    id                  bigserial PRIMARY KEY,
    tenant_id           uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    beneficiary_id      bigint NOT NULL,
    scores_json         jsonb NOT NULL DEFAULT '{}'::jsonb,  -- category -> score
    total_score         numeric,
    decision            text,                  -- Qualified | Not Qualified
    notes               text,
    scored_by_user_id   integer,
    scored_at           timestamptz,
    decided_by_user_id  integer,
    decided_at          timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_qualification_beneficiary FOREIGN KEY (tenant_id, beneficiary_id)
        REFERENCES enterprise_beneficiaries (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT uq_ent_qualification_tenant_id UNIQUE (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS ix_ent_qualification_beneficiary
    ON enterprise_site_qualifications (tenant_id, beneficiary_id);

-- -----------------------------------------------------------------------------
-- PART 4 -- generated project links (slice 7 fills this; created here per R2)
-- -----------------------------------------------------------------------------
-- Control C14: every programme project must retain traceability to its originating
-- beneficiary AND the programme template version it was built from. That is what this
-- table IS -- the join between a programme's intent and SolarPro's existing project
-- tables, which this module never writes to (see the tenancy overlay decision in slice 1).
--
-- `template_version_id` is the IMMUTABLE unit from slice 4, not the template: the whole
-- point of freezing a version is that this row can still say what the project was
-- specified to be, years later, after the standard has moved on three versions.
CREATE TABLE IF NOT EXISTS enterprise_project_links (
    id                  bigserial PRIMARY KEY,
    tenant_id           uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    programme_id        bigint NOT NULL,
    beneficiary_id      bigint NOT NULL,
    template_version_id bigint NOT NULL,
    -- The SolarPro-side project. Deliberately NOT a foreign key: `projects` and
    -- `capital_investment_projects` are two different tables owned by the existing app,
    -- and this module must never constrain, cascade into, or otherwise take ownership of
    -- a user's own project rows.
    project_kind        text NOT NULL,         -- standard | generation_station
    project_id          bigint NOT NULL,
    status              text NOT NULL DEFAULT 'Project Generated',
    engineering_approved_by_user_id integer,
    engineering_approved_at timestamptz,
    generated_by_user_id integer,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_link_programme FOREIGN KEY (tenant_id, programme_id)
        REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE,
    -- PROGRAMME-scoped, not merely tenant-scoped. C14 says a generated project must retain
    -- traceability to its originating beneficiary; a link that could name a beneficiary from
    -- a DIFFERENT programme in the same tenant retains a traceability that is false, which is
    -- worse than none -- a report would follow it and produce a confident wrong answer.
    CONSTRAINT fk_link_beneficiary FOREIGN KEY (tenant_id, programme_id, beneficiary_id)
        REFERENCES enterprise_beneficiaries (tenant_id, programme_id, id) ON DELETE CASCADE,
    -- The OTHER half of C14: the immutable template version this project was built from.
    -- Without this FK it is an integer that nothing checks -- it could name a version in
    -- another tenant, or one that never existed, and the provenance would still "resolve".
    CONSTRAINT fk_link_template_version FOREIGN KEY (tenant_id, template_version_id)
        REFERENCES enterprise_template_versions (tenant_id, id),
    CONSTRAINT uq_ent_project_link_tenant_id UNIQUE (tenant_id, id)
);

-- One project per beneficiary. Generation must be IDEMPOTENT: the worker (a GitHub-Actions
-- cron hitting a drain endpoint -- Supervisor correction R1, because Render's free tier
-- caps the account at one instance) can and will retry, and a retry that builds a second
-- project for the same school is a duplicate that somebody has to find and delete by hand.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_project_link_beneficiary
    ON enterprise_project_links (tenant_id, beneficiary_id);
CREATE INDEX IF NOT EXISTS ix_ent_project_link_programme
    ON enterprise_project_links (tenant_id, programme_id, status);

-- -----------------------------------------------------------------------------
-- PART 5 -- the durable job queue (slice 7 fills this; created here per R2)
-- -----------------------------------------------------------------------------
-- Supervisor correction R1: there is NO worker process and there cannot be one. Render's
-- free tier caps the account at a single instance -- a second service was already BLOCKED
-- on 2026-07-10. So bulk work is a DURABLE JOB TABLE drained by a GitHub-Actions cron
-- calling an authenticated admin endpoint, chunked and idempotent, with every guard
-- re-checked on the worker path (a guard that lives in a route is a guard the drainer
-- skips).
--
-- GitHub's free cron is best-effort and DROPS fires. Nothing in the UI may present this
-- queue as real-time.
CREATE TABLE IF NOT EXISTS enterprise_jobs (
    id                 bigserial PRIMARY KEY,
    tenant_id          uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    programme_id       bigint,
    job_type           text NOT NULL,          -- generate_projects | ...
    status             text NOT NULL DEFAULT 'Queued',
    payload_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    total_items        integer NOT NULL DEFAULT 0,
    done_items         integer NOT NULL DEFAULT 0,
    failed_items       integer NOT NULL DEFAULT 0,
    last_error         text,
    attempts           integer NOT NULL DEFAULT 0,
    created_by_user_id integer,
    created_at         timestamptz NOT NULL DEFAULT now(),
    started_at         timestamptz,
    finished_at        timestamptz,
    CONSTRAINT fk_job_programme FOREIGN KEY (tenant_id, programme_id)
        REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT ck_ent_job_status CHECK (status IN
        ('Queued', 'Running', 'Completed', 'Failed', 'Cancelled'))
);

CREATE INDEX IF NOT EXISTS ix_ent_job_drain
    ON enterprise_jobs (status, created_at);
CREATE INDEX IF NOT EXISTS ix_ent_job_programme
    ON enterprise_jobs (tenant_id, programme_id, status);

-- -----------------------------------------------------------------------------
-- PART 6 -- RLS (AFTER the tables -- see rule 2 in the header)
-- -----------------------------------------------------------------------------
-- current_enterprise_tenant_ids() was created by migration 025; it reads only
-- enterprise_tenant_memberships, so none of the policies below can recurse.
ALTER TABLE enterprise_beneficiaries        ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_import_batches       ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_import_rows          ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_site_qualifications  ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_project_links        ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_jobs                 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ent_beneficiaries_member ON enterprise_beneficiaries;
CREATE POLICY ent_beneficiaries_member ON enterprise_beneficiaries
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

DROP POLICY IF EXISTS ent_import_batches_member ON enterprise_import_batches;
CREATE POLICY ent_import_batches_member ON enterprise_import_batches
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

DROP POLICY IF EXISTS ent_import_rows_member ON enterprise_import_rows;
CREATE POLICY ent_import_rows_member ON enterprise_import_rows
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

DROP POLICY IF EXISTS ent_qualifications_member ON enterprise_site_qualifications;
CREATE POLICY ent_qualifications_member ON enterprise_site_qualifications
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

DROP POLICY IF EXISTS ent_project_links_member ON enterprise_project_links;
CREATE POLICY ent_project_links_member ON enterprise_project_links
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

DROP POLICY IF EXISTS ent_jobs_member ON enterprise_jobs;
CREATE POLICY ent_jobs_member ON enterprise_jobs
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

COMMIT;

-- =============================================================================
-- ROLLBACK (manual; prefer flag-off over dropping anything)
--   UPDATE admin_settings SET value='0' WHERE key='enterprise_rebuild_enabled';
-- Only if the schema itself must go (this DESTROYS enterprise data -- back up first):
--   DROP TABLE IF EXISTS enterprise_jobs, enterprise_project_links,
--                        enterprise_site_qualifications, enterprise_import_rows,
--                        enterprise_import_batches, enterprise_beneficiaries CASCADE;
-- Dropping these does NOT affect any user's projects -- by design, this migration never
-- wrote to them. enterprise_project_links REFERENCES a project id without a foreign key
-- precisely so that dropping it cannot cascade into anybody's work.
-- =============================================================================
