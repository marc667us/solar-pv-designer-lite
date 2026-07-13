-- Migration 029 -- the PROGRAMME REFERENCE DESIGN (rebuild slice 7).
--
-- WHAT THE OWNER ASKED FOR, IN THEIR WORDS
--   "when you are in planning the programme must open into standard or generation station
--    design, as the output report the plans of the programme for the number of the
--    programme sites"
--   "the implementation must be built up from the design but must be scaled to all
--    programme sites"
--   "the BOQ and everything is the same for each site"
--
-- WHAT THAT MEANS, STRUCTURALLY
--   A programme does not hold N designs. It holds ONE -- the reference design -- and every
--   site is that design, instantiated. This table IS that "one". Without it, "the BOQ is
--   the same for each site" is a convention: something the code happens to do today and
--   that any future caller can quietly break by sizing a second site differently. With it,
--   the sameness has an address. There is a row that says what the BOQ is, one per
--   programme (the partial unique index below), and a site project that did not come from
--   it cannot claim to be part of the rollout.
--
-- WHY design_path LIVES ON THE TEMPLATE AND IS ONLY COPIED HERE
--   C03: no project is generated without an approved template. The design path decides
--   which engine runs against every site in the programme -- so it must be a thing somebody
--   approved. It is authored in enterprise_template_versions.parameters_json. The copy on
--   this row is a FROZEN one, taken at the moment the design was built: if the template is
--   later revised, the design that was actually issued still says what it actually was.
--
-- WHY THE SITE VARIANCE COLUMN EXISTS
--   The owner also said the field assessment and shading survey apply "at each location".
--   Those two things and "the BOQ is the same for each site" are only reconcilable one way:
--   the reference BOQ is what gets built, and a location whose survey disagrees with it is
--   a VARIANCE -- recorded, visible, and escalated to engineering. The alternative (let each
--   site's shading quietly re-size its own array) produces N different BOQs, which is the
--   exact thing the owner ruled out. So the variance is stored, and it is never applied
--   silently.
--
-- IDEMPOTENT. Safe to re-run. Adds nothing to any existing table's meaning.

BEGIN;

-- -----------------------------------------------------------------------------
-- PART 1 -- the reference design
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS enterprise_reference_designs (
    id                  bigserial PRIMARY KEY,
    tenant_id           uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    programme_id        bigint NOT NULL,
    -- C14. The immutable template version this design was built from. Composite FK, so it
    -- cannot name a version belonging to another tenant.
    template_version_id bigint NOT NULL,
    design_path         text NOT NULL,   -- standard | generation_station (frozen copy)

    -- The SolarPro-side project that holds the actual engineering. Deliberately NOT a
    -- foreign key, for the same reason enterprise_project_links is not: `projects` and
    -- `capital_investment_projects` are two different tables owned by the existing app, and
    -- this module must never constrain or cascade into a user's own project rows.
    project_kind        text NOT NULL,   -- standard | generation_station
    project_id          bigint NOT NULL,

    status              text NOT NULL DEFAULT 'Draft',

    -- The frozen outputs. boq_json is the one every site inherits verbatim -- it is the
    -- literal subject of "the BOQ is the same for each site", and it is snapshotted rather
    -- than read live from the project so that editing the reference project tomorrow cannot
    -- retroactively change what 400 sites were told they were getting.
    kwp                 numeric,
    boq_json            jsonb NOT NULL DEFAULT '{}'::jsonb,
    summary_json        jsonb NOT NULL DEFAULT '{}'::jsonb,

    -- C04: no design is issued without engineering approval. Rollout is gated on this
    -- being set; a Draft reference design generates nothing.
    approved_by_user_id integer,
    approved_at         timestamptz,
    created_by_user_id  integer,
    created_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT fk_refdesign_programme FOREIGN KEY (tenant_id, programme_id)
        REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_refdesign_template_version FOREIGN KEY (tenant_id, template_version_id)
        REFERENCES enterprise_template_versions (tenant_id, id),
    -- So enterprise_project_links can hold a tenant-scoped FK back to the design a site
    -- was built from. Without it, that column would be an integer nothing checks.
    CONSTRAINT uq_ent_refdesign_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT ck_ent_refdesign_path CHECK (design_path IN
        ('standard', 'generation_station')),
    CONSTRAINT ck_ent_refdesign_kind CHECK (project_kind IN
        ('standard', 'generation_station')),
    CONSTRAINT ck_ent_refdesign_status CHECK (status IN
        ('Draft', 'Engineering Approved', 'Superseded'))
);

-- ONE live reference design per programme, enforced by the database rather than by the
-- application being careful. Two live designs is not a tidiness problem: it is "which BOQ
-- is the one the sites get" having two answers, which is the failure this whole table
-- exists to prevent. Superseded rows are excluded so a revision can be issued.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_refdesign_current
    ON enterprise_reference_designs (tenant_id, programme_id)
    WHERE status <> 'Superseded';

CREATE INDEX IF NOT EXISTS ix_ent_refdesign_programme
    ON enterprise_reference_designs (tenant_id, programme_id, status);

-- -----------------------------------------------------------------------------
-- PART 2 -- close the traceability chain on the site projects
-- -----------------------------------------------------------------------------
-- enterprise_project_links (027) already records the beneficiary and the template version.
-- It could not record the design, because until now there was no design to record. Add it:
--   site project -> reference design -> template version -> programme
-- is now a chain the database can walk, which is what C14 actually asks for.
ALTER TABLE enterprise_project_links
    ADD COLUMN IF NOT EXISTS reference_design_id bigint;

-- The per-location survey result, held against the site and NOT applied to its BOQ.
-- See the header: this is the honest home for "field assessment at each location" in a
-- programme whose BOQ is the same everywhere.
ALTER TABLE enterprise_project_links
    ADD COLUMN IF NOT EXISTS site_variance_json jsonb NOT NULL DEFAULT '{}'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_link_reference_design'
    ) THEN
        ALTER TABLE enterprise_project_links
            ADD CONSTRAINT fk_link_reference_design
            FOREIGN KEY (tenant_id, reference_design_id)
            REFERENCES enterprise_reference_designs (tenant_id, id);
    END IF;
END $$;

-- -----------------------------------------------------------------------------
-- PART 3 -- one ACTIVE rollout per programme (Codex slice-7, MED)
-- -----------------------------------------------------------------------------
-- rollout.queue_rollout looks for an existing Queued/Running job before inserting one. That
-- look is a courtesy -- it produces a sentence a human can act on. It is NOT a control:
-- two operators clicking at the same moment each see no job and both insert, because a
-- check-then-insert is a race and "the application looked first" is a habit.
--
-- Two live jobs for one programme do not duplicate its projects (ux_ent_project_link_
-- beneficiary already forbids that), but they fight over the same rows, fail each other's
-- sites, and leave a job record that misreports what happened. This index makes the second
-- one impossible.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_job_active
    ON enterprise_jobs (tenant_id, programme_id, job_type)
    WHERE status IN ('Queued', 'Running');

-- -----------------------------------------------------------------------------
-- PART 4 -- RLS (after the table, per the rule in 026's header)
-- -----------------------------------------------------------------------------
-- NOTE, said plainly: these tables are ENABLE'd, not FORCE'd, exactly like 025-027. The
-- table owner bypasses a merely-ENABLE'd policy, and this app connects as the owner -- so
-- this policy is documentation until the outstanding FORCE migration lands. It is written
-- now so that FORCE, when it comes, has nothing left to add for this table.
ALTER TABLE enterprise_reference_designs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ent_refdesign_member ON enterprise_reference_designs;
CREATE POLICY ent_refdesign_member ON enterprise_reference_designs
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

COMMIT;
