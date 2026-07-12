-- =============================================================================
-- 026 -- Enterprise Programme rebuild, slice 2: the lifecycle spine
-- =============================================================================
--
-- WHAT THIS DOES
--   Creates the Programme Breakdown Structure and the operational spine from doc 3:
--   programmes, their 16 phase rows, their 14 stage-gate rows, the transition ledger,
--   the approval ledger, the document register, the geography tree, sites, and the
--   template tables the standardisation slice will fill.
--
-- WHY THIS MIGRATION IS BIGGER THAN THE PLAN SAID
--   The Codex plan (docs/enterprise-programme/rebuild/07-implementation-plan.md) cut
--   Release 1 into SIX live migrations (025-030). The Supervisor's required correction
--   R2 (docs/.../09-supervisor-adjudication.md) caps Release 1 at THREE: the free-tier
--   Postgres has already had one near-miss, when migration 024's first apply died on
--   SQL-function parse order, and every additional apply against live is another chance
--   to half-land. So the plan's 026 (programme core) and 027 (templates) are merged
--   here, and 028-030 will merge into 027. Release 1 = 025 + 026 + 027. Nothing is
--   dropped -- the tables are the same, the number of live applies is not.
--
-- WHY THE TABLES ARE NOT CALLED `enterprise_programmes` (this one nearly broke live)
--   Migration 024 IS APPLIED TO LIVE, and it already owns tables named
--   `enterprise_programmes` and `enterprise_programme_phases`. `CREATE TABLE IF NOT
--   EXISTS` would have SILENTLY SKIPPED them -- leaving 024's old shape in place, with no
--   `UNIQUE (tenant_id, id)` -- and the very first composite FK below would then have
--   failed, killing this migration half-way through, exactly as 024's own first apply
--   died. Owner decision D1 forbids dropping 024's tables (they hold the pilot rows,
--   audit and links), so the rebuild takes NEW names instead:
--       enterprise_programmes        ->  enterprise_programme_registry
--       enterprise_programme_phases  ->  enterprise_programme_phase_states
--   This is the same call slice 1 made when it chose `enterprise_tenant_memberships` over
--   colliding with 024's `enterprise_memberships`. 024's tables are left untouched and
--   dark; the cleanup migration retires them once the owner says so.
--   (Caught by the Codex slice-2 review. Nothing in this file touches a 024 table.)
--
-- WHAT THIS DOES *NOT* DO (the safety property from 025, still holding)
--   ZERO writes to `projects` or `capital_investment_projects`. A programme LINKS to
--   an existing project through a link row; it never takes ownership of one. The app is
--   single-user-owned at the database level and this rebuild does not change that.
--
-- TENANT-SCOPED FOREIGN KEYS (why the child FKs look unusual)
--   Every child table carries BOTH `tenant_id` and `programme_id`. If the FK pointed only
--   at `enterprise_programme_registry(id)`, Postgres would happily accept a row with tenant A's
--   `tenant_id` and tenant B's `programme_id` -- a cross-tenant child that RLS would then
--   show to tenant A, because RLS filters on the child's own tenant_id. The service layer
--   never builds such a row (every write goes through _load_programme, control C13), but
--   "the app is careful" is not a database constraint.
--   So the parents carry UNIQUE (tenant_id, id) and every child declares
--   FOREIGN KEY (tenant_id, programme_id) REFERENCES enterprise_programme_registry (tenant_id, id).
--   A cross-tenant child row is now rejected by Postgres itself.
--   (Raised by the Codex slice-2 review.) EVERY cross-row reference in this migration is
--   tenant-scoped, including geographic_areas.parent_id and sites.area_id -- a bare FK
--   there would let one tenant's DELETE cascade into another tenant's rows, which is
--   corruption neither tenant could even see coming.
--
-- MIGRATION RULES (the same three that 024 taught us the hard way)
--   1. One transaction, ON_ERROR_STOP. A partial apply is worse than no apply.
--   2. Postgres parses a `LANGUAGE sql` body at CREATE time, so every SQL function is
--      declared AFTER the tables it reads. See PART 8.
--   3. Any admin_settings write needs set_config('app.current_role','admin',true)
--      INSIDE the transaction or it silently rolls back. See PART 9.
--
-- IDEMPOTENT: safe to re-run.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- PART 1 -- programmes
-- -----------------------------------------------------------------------------
-- `current_phase_code` and `status` are TWO VIEWS OF ONE TRUTH: status is derived from
-- the phase (app/enterprise_programme/constants.py::PHASE_STATUS) and is never typed by
-- a user. They are both stored because the dashboard filters on status and the state
-- machine moves on phase -- but only workflows.py writes either, and it always writes
-- both together.
--
-- `held_from_phase_code` is what makes a hold reversible: a SUSPENDED programme
-- remembers the phase it was suspended from and resumes exactly there.
CREATE TABLE IF NOT EXISTS enterprise_programme_registry (
    id                   bigserial PRIMARY KEY,
    tenant_id            uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    code                 text NOT NULL,
    name                 text NOT NULL,
    description          text,
    organisation_type    text,
    design_strategy      text NOT NULL DEFAULT 'standard',
    country              text,
    sponsor_user_id      integer,
    director_user_id     integer,
    manager_user_id      integer,
    current_phase_code   text NOT NULL DEFAULT 'P01_CONCEPT',
    status               text NOT NULL DEFAULT 'Concept',
    held_from_phase_code text,
    target_capacity_kwp  numeric,
    target_beneficiaries integer,
    created_by_user_id   integer,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    -- The FK target for every child table. `id` alone is already unique (it is the PK);
    -- this composite key is what lets a child declare (tenant_id, programme_id) as a
    -- FOREIGN KEY, which is what makes a cross-tenant child row impossible in the
    -- DATABASE rather than only in the service layer. See PART 11.
    CONSTRAINT uq_ent_programme_tenant_id UNIQUE (tenant_id, id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_programme_code
    ON enterprise_programme_registry (tenant_id, code);
CREATE INDEX IF NOT EXISTS ix_ent_programme_tenant_status
    ON enterprise_programme_registry (tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_ent_programme_tenant_created
    ON enterprise_programme_registry (tenant_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- PART 2 -- the 16 phase rows per programme
-- -----------------------------------------------------------------------------
-- Seeded in full at programme creation, not lazily. The whole road (including the gates
-- that will block it) is visible from day one, and there is no "the gate row was simply
-- missing so the check never ran" failure mode.
CREATE TABLE IF NOT EXISTS enterprise_programme_phase_states (
    id            bigserial PRIMARY KEY,
    tenant_id     uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    programme_id  bigint NOT NULL,
    phase_code    text NOT NULL,
    sequence_no   integer NOT NULL,
    status        text NOT NULL DEFAULT 'Not Started',
    started_at    timestamptz,
    completed_at  timestamptz,
    CONSTRAINT fk_phase_programme FOREIGN KEY (tenant_id, programme_id)
        REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_phase
    ON enterprise_programme_phase_states (tenant_id, programme_id, phase_code);

-- -----------------------------------------------------------------------------
-- PART 3 -- the 14 stage gates per programme
-- -----------------------------------------------------------------------------
-- `approving_role` is copied onto the row at seed time from constants.GATES. It is the
-- role that ALONE may approve this gate (doc 3 names an authority per gate). Storing it
-- per-row rather than looking it up means an audit of a 2029 approval can still see
-- which authority was required in 2026, even if the constant later changes.
CREATE TABLE IF NOT EXISTS enterprise_stage_gates (
    id                 bigserial PRIMARY KEY,
    tenant_id          uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    programme_id       bigint NOT NULL,
    gate_code          text NOT NULL,
    phase_code         text NOT NULL,
    status             text NOT NULL DEFAULT 'Pending',   -- Pending|Approved|Rejected|Waived
    approving_role     text NOT NULL,
    decided_by_user_id integer,
    decided_at         timestamptz,
    comment            text,
    CONSTRAINT fk_gate_programme FOREIGN KEY (tenant_id, programme_id)
        REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_gate
    ON enterprise_stage_gates (tenant_id, programme_id, gate_code);
CREATE INDEX IF NOT EXISTS ix_ent_gate_status
    ON enterprise_stage_gates (tenant_id, programme_id, status);

-- -----------------------------------------------------------------------------
-- PART 4 -- the transition ledger (append-only)
-- -----------------------------------------------------------------------------
-- Every phase move, hold, resume and termination lands here. Nothing UPDATEs or DELETEs
-- this table: "who sent this back to Feasibility, and when" is exactly the question a
-- steering committee asks six months later.
CREATE TABLE IF NOT EXISTS enterprise_workflow_transitions (
    id              bigserial PRIMARY KEY,
    tenant_id       uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    programme_id    bigint NOT NULL,
    from_phase_code text,
    to_phase_code   text NOT NULL,
    gate_code       text,
    actor_user_id   integer NOT NULL,
    note            text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_transition_programme FOREIGN KEY (tenant_id, programme_id)
        REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_ent_transition_programme
    ON enterprise_workflow_transitions (tenant_id, programme_id, id DESC);

-- -----------------------------------------------------------------------------
-- PART 5 -- the approval ledger
-- -----------------------------------------------------------------------------
-- `ai_recommendation_id` is EVIDENCE, never authority (control C11). An AI
-- recommendation may be attached to an approval; `decided_by_user_id` must still be a
-- human. There is deliberately no service-account or "system" actor that can decide.
CREATE TABLE IF NOT EXISTS enterprise_approvals (
    id                   bigserial PRIMARY KEY,
    tenant_id            uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    -- NULLABLE, deliberately. Not every approval belongs to a programme: a programme
    -- TEMPLATE may be tenant-wide (one "School 50 kW" standard, reused across every
    -- programme a ministry runs), and its approval is an organisation-level act. Forcing a
    -- programme here would either lose the approval record for exactly the templates that
    -- matter most, or force a duplicate template per programme -- which is the drift the
    -- template engine exists to prevent. The composite FK still fires whenever it IS set.
    programme_id         bigint,
    subject_type         text NOT NULL,      -- gate | programme | template_version | ...
    subject_id           text,
    approval_type        text NOT NULL,      -- stage_gate | resume_from_hold | ...
    decision             text NOT NULL,      -- Approved | Rejected | Pending
    decided_by_user_id   integer,
    decided_by_role      text,
    ai_recommendation_id bigint,
    comment              text,
    created_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_approval_programme FOREIGN KEY (tenant_id, programme_id)
        REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_ent_approval_programme
    ON enterprise_approvals (tenant_id, programme_id, approval_type);

-- -----------------------------------------------------------------------------
-- PART 6 -- the document register
-- -----------------------------------------------------------------------------
-- Doc 3 lists required documents per gate. The gate predicate checks a document of the
-- right type is REGISTERED; judging its contents is the named authority's job, which is
-- exactly why a specific human role has to sign rather than the system auto-passing.
CREATE TABLE IF NOT EXISTS enterprise_documents (
    id                  bigserial PRIMARY KEY,
    tenant_id           uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    programme_id        bigint NOT NULL,
    doc_type            text NOT NULL,
    title               text NOT NULL,
    uri                 text,
    uploaded_by_user_id integer,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_document_programme FOREIGN KEY (tenant_id, programme_id)
        REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_ent_document_programme
    ON enterprise_documents (tenant_id, programme_id, doc_type);

-- -----------------------------------------------------------------------------
-- PART 7 -- geography and sites (PBS levels: region / district / community / site)
-- -----------------------------------------------------------------------------
-- Self-referencing tree so one table serves region, district and community rather than
-- three near-identical tables with three near-identical queries.
CREATE TABLE IF NOT EXISTS enterprise_geographic_areas (
    id            bigserial PRIMARY KEY,
    tenant_id     uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    programme_id  bigint,
    parent_id     bigint,
    level         text NOT NULL,          -- region | district | community
    code          text NOT NULL,
    name          text NOT NULL,
    country       text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_geo_programme FOREIGN KEY (tenant_id, programme_id)
        REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE,
    -- Tenant-scoped self-reference. With a bare parent_id FK, tenant A could parent its
    -- district under tenant B's region: Postgres would accept it (ids are globally
    -- unique), and although RLS would hide B's row from A, B DELETING that region would
    -- cascade into A's data. Cross-tenant corruption via a foreign key, without either
    -- tenant ever seeing the other's rows.
    CONSTRAINT fk_geo_parent FOREIGN KEY (tenant_id, parent_id)
        REFERENCES enterprise_geographic_areas (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT uq_ent_geo_tenant_id UNIQUE (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS ix_ent_geo_programme
    ON enterprise_geographic_areas (tenant_id, programme_id, level);

CREATE TABLE IF NOT EXISTS enterprise_sites (
    id             bigserial PRIMARY KEY,
    tenant_id      uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    programme_id   bigint NOT NULL,
    area_id        bigint,
    code           text NOT NULL,
    name           text NOT NULL,
    latitude       numeric,
    longitude      numeric,
    status         text NOT NULL DEFAULT 'Registered',
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_site_programme FOREIGN KEY (tenant_id, programme_id)
        REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_site_area FOREIGN KEY (tenant_id, area_id)
        REFERENCES enterprise_geographic_areas (tenant_id, id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_site_code
    ON enterprise_sites (tenant_id, programme_id, code);

-- -----------------------------------------------------------------------------
-- PART 8 -- programme templates (slice 4 fills these; created here per R2)
-- -----------------------------------------------------------------------------
-- Control C03: only an Approved or Published VERSION may generate a project. The
-- version is the immutable unit -- once a project is generated from version 3, editing
-- the template must not retroactively change what that project was built from. Hence
-- template/version split rather than a status column on the template itself.
CREATE TABLE IF NOT EXISTS enterprise_programme_templates (
    id                 bigserial PRIMARY KEY,
    tenant_id          uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    programme_id       bigint,
    code               text NOT NULL,
    name               text NOT NULL,
    beneficiary_type   text,
    design_strategy    text NOT NULL DEFAULT 'standard',
    created_by_user_id integer,
    created_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_template_programme FOREIGN KEY (tenant_id, programme_id)
        REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE
    ,
    CONSTRAINT uq_ent_template_tenant_id UNIQUE (tenant_id, id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_template_code
    ON enterprise_programme_templates (tenant_id, code);

CREATE TABLE IF NOT EXISTS enterprise_template_versions (
    id                 bigserial PRIMARY KEY,
    tenant_id          uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    template_id        bigint NOT NULL,
    version_no         integer NOT NULL,
    status             text NOT NULL DEFAULT 'Draft',
    parameters_json    jsonb NOT NULL DEFAULT '{}'::jsonb,
    approved_by_user_id integer,
    approved_at        timestamptz,
    created_by_user_id integer,
    created_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_template_version_template FOREIGN KEY (tenant_id, template_id)
        REFERENCES enterprise_programme_templates (tenant_id, id) ON DELETE CASCADE,
    -- The status vocabulary is a state machine, not a suggestion. Without this CHECK, one
    -- typo in one UPDATE somewhere puts a version into a status nothing in the code knows
    -- how to reason about -- and the safest of those, from the database's point of view,
    -- would look exactly like an approved one.
    CONSTRAINT ck_ent_template_version_status CHECK (status IN
        ('Draft','Review','Approved','Published','Superseded','Archived'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_template_version
    ON enterprise_template_versions (tenant_id, template_id, version_no);
CREATE INDEX IF NOT EXISTS ix_ent_template_version_status
    ON enterprise_template_versions (tenant_id, status);

-- ONE Published and ONE Draft per template, enforced by the database.
--
-- The application already serialises both (templates.py locks the template row before
-- publishing and before opening a draft), but "the application is careful" is not a
-- constraint -- it is a habit, and it holds only for as long as every future caller keeps
-- it. Two concurrent publishes on Postgres each supersede an incumbent the other cannot
-- see yet, and both land Published; after that "which version does this build from" has
-- two answers. These indexes make that state unrepresentable.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_template_one_published
    ON enterprise_template_versions (tenant_id, template_id) WHERE status = 'Published';
CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_template_one_draft
    ON enterprise_template_versions (tenant_id, template_id) WHERE status = 'Draft';

-- -----------------------------------------------------------------------------
-- PART 8b -- template immutability, enforced by the DATABASE
-- -----------------------------------------------------------------------------
-- The master prompt: "Projects created from templates must retain the template version
-- used. Later template changes must not silently overwrite completed or approved project
-- designs."
--
-- templates.py enforces that. This makes it TRUE. The application guard protects the app's
-- own write paths; it does nothing about a migration, a fix-up script, an admin console, a
-- future slice, or a bug -- any of which can reach this table with a plain UPDATE. And the
-- damage is the quietest kind there is: a school is built to version 3, version 3 is later
-- edited, and now the record and the building disagree with no event anywhere saying which
-- one moved. The guard belongs where the data is.
--
-- Same doctrine as RLS in this codebase: the app is the first line of defence, the database
-- is the last, and both are required (CLAUDE.md, Directive s7).
-- ONE function for all three operations. An UPDATE guard alone is not immutability: the
-- reviewer's own follow-up was that DELETE-then-reinsert forges a version just as well, and
-- a bare INSERT can conjure a Published one that no Technical Director ever saw.
--
-- WHY THIS DOES NOT BREAK BACKUP/RESTORE: new_admin_backup_routes.py restores by
-- DELETE-then-INSERT per table, which is exactly what this forbids -- but it first issues
-- `SET session_replication_role = 'replica'` (new_admin_backup_routes.py:172), and in
-- replica mode Postgres does not fire ordinary user triggers. A restore therefore passes
-- straight through, as it must. That switch is also why these guards are Postgres-only:
-- SQLite has no equivalent, so its schema (workflows.py) carries the UPDATE triggers alone
-- and its restore keeps working. Production is Postgres, which is where the guarantee has
-- to be real.
CREATE OR REPLACE FUNCTION enterprise_template_version_is_frozen()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- A version is BORN a Draft. Anything else was not approved by anybody.
        IF NEW.status <> 'Draft' THEN
            RAISE EXCEPTION
                'a template version must be created as a Draft (got %): an approved '
                'version has to be approved, not inserted.',
                NEW.status
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        -- Deleting a frozen version and reinserting a replacement is a rewrite with extra
        -- steps. Blocked -- UNLESS the parent template is itself going away, which is how
        -- a template or tenant deletion cascades: Postgres removes the parent row first,
        -- so by the time this fires for the cascade the parent is already gone and the
        -- EXISTS is false. A DIRECT delete of one version leaves the parent in place and
        -- is refused.
        IF OLD.status <> 'Draft' AND EXISTS (
            SELECT 1 FROM enterprise_programme_templates t
             WHERE t.tenant_id = OLD.tenant_id AND t.id = OLD.template_id
        ) THEN
            RAISE EXCEPTION
                'template version % is % and cannot be deleted: something may already '
                'have been generated from it. Archive it instead.',
                OLD.version_no, OLD.status
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN OLD;
    END IF;

    -- UPDATE.
    IF OLD.status <> 'Draft'
       AND NEW.parameters_json IS DISTINCT FROM OLD.parameters_json THEN
        RAISE EXCEPTION
            'template version % is % and is frozen: its parameters cannot be changed. '
            'Create a new version instead.',
            OLD.version_no, OLD.status
            USING ERRCODE = 'check_violation';
    END IF;

    -- Rejection (Review -> Draft) is the ONE legal way back to editable, and only before
    -- anything has been generated. Nothing may return to Draft once it has been approved.
    IF NEW.status = 'Draft' AND OLD.status NOT IN ('Draft', 'Review') THEN
        RAISE EXCEPTION
            'template version % cannot return to Draft from %: something may already have '
            'been generated from it.',
            OLD.version_no, OLD.status
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ent_template_version_is_frozen
    ON enterprise_template_versions;
CREATE TRIGGER trg_ent_template_version_is_frozen
    BEFORE INSERT OR UPDATE OR DELETE ON enterprise_template_versions
    FOR EACH ROW EXECUTE FUNCTION enterprise_template_version_is_frozen();

-- -----------------------------------------------------------------------------
-- PART 9 -- RLS (AFTER the tables -- see header rule 2)
-- -----------------------------------------------------------------------------
-- Defence in depth ONLY. The app layer remains the primary tenant boundary: every query
-- is scoped by the caller's RESOLVED tenant id, never by an id taken from the URL.
-- current_enterprise_tenant_ids() was created by migration 025; it reads only
-- enterprise_tenant_memberships, so none of the policies below can recurse.
ALTER TABLE enterprise_programme_registry             ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_programme_phase_states       ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_stage_gates            ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_workflow_transitions   ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_approvals              ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_documents              ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_geographic_areas       ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_sites                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_programme_templates    ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_template_versions      ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ent_programmes_member ON enterprise_programme_registry;
CREATE POLICY ent_programmes_member ON enterprise_programme_registry
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

DROP POLICY IF EXISTS ent_phases_member ON enterprise_programme_phase_states;
CREATE POLICY ent_phases_member ON enterprise_programme_phase_states
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

DROP POLICY IF EXISTS ent_gates_member ON enterprise_stage_gates;
CREATE POLICY ent_gates_member ON enterprise_stage_gates
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

DROP POLICY IF EXISTS ent_transitions_member ON enterprise_workflow_transitions;
CREATE POLICY ent_transitions_member ON enterprise_workflow_transitions
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

DROP POLICY IF EXISTS ent_approvals_member ON enterprise_approvals;
CREATE POLICY ent_approvals_member ON enterprise_approvals
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

DROP POLICY IF EXISTS ent_documents_member ON enterprise_documents;
CREATE POLICY ent_documents_member ON enterprise_documents
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

DROP POLICY IF EXISTS ent_geo_member ON enterprise_geographic_areas;
CREATE POLICY ent_geo_member ON enterprise_geographic_areas
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

DROP POLICY IF EXISTS ent_sites_member ON enterprise_sites;
CREATE POLICY ent_sites_member ON enterprise_sites
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

DROP POLICY IF EXISTS ent_templates_member ON enterprise_programme_templates;
CREATE POLICY ent_templates_member ON enterprise_programme_templates
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

DROP POLICY IF EXISTS ent_template_versions_member ON enterprise_template_versions;
CREATE POLICY ent_template_versions_member ON enterprise_template_versions
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

-- -----------------------------------------------------------------------------
-- PART 10 -- flags
-- -----------------------------------------------------------------------------
-- admin_settings is FORCE-RLS and admin-only: without this set_config the INSERT below
-- silently rolls back and the flag never appears. Not optional.
SELECT set_config('app.current_role', 'admin', true);

INSERT INTO admin_settings (key, value)
VALUES ('enterprise_rebuild_enabled', '0')
ON CONFLICT (key) DO NOTHING;

COMMIT;

-- =============================================================================
-- ROLLBACK (manual; prefer flag-off over dropping anything)
--   UPDATE admin_settings SET value='0' WHERE key='enterprise_rebuild_enabled';
-- Only if the schema itself must go (this DESTROYS enterprise data -- back up first):
--   DROP TABLE IF EXISTS enterprise_template_versions, enterprise_programme_templates,
--                        enterprise_sites, enterprise_geographic_areas,
--                        enterprise_documents, enterprise_approvals,
--                        enterprise_workflow_transitions, enterprise_stage_gates,
--                        enterprise_programme_phase_states, enterprise_programme_registry CASCADE;
-- Dropping these does NOT affect any user's projects -- by design, this migration never
-- wrote to them.
-- =============================================================================
