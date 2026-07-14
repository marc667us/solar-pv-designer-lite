-- Migration 031 -- BENEFICIARY APPLICATIONS and the three-level approval chain.
--
-- OWNER (2026-07-14):
--   "we don't need to do proving to any entity rather the beneficiaries must register for the
--    program and track progress from when they submit app to when their approved"
--   "the users of the beneficiary must register via their organisation platform and
--    applications must be submitted through the organisation. the first level of application
--    is the beneficiary organisation, the programme level approval and finally sponsor level
--    approval"
--   "all approvals must be set by the individual approving entities"
--   "check my bill must be run for each user automatically after their application"
--
-- THE THREE LEVELS ARE THREE DIFFERENT ORGANISATIONS.
-- ------------------------------------------------------------------------------------
-- That is why they are three sets of columns and not a generic `approvals` table with a
-- `level` discriminator: the authority for each is checked against a DIFFERENT entity, and
-- flattening them would make it far too easy for a later query to treat any approval row as
-- interchangeable with any other. They are not. A beneficiary organisation vouching for its
-- own household and a sponsor committing money are not two instances of one thing.
--
--   l1 -- the applicant's own BENEFICIARY ORGANISATION  (applicant_org_tenant_id)
--   l2 -- the PROGRAMME                                 (tenant_id)
--   l3 -- the SPONSOR                                   (a named financial_institution)
--
-- `l3_sponsor_id` records WHICH sponsor signed. A programme may name three; "the sponsor
-- approved" is not a fact until you can say which one.
--
-- WHY THE BILL CHECK IS A COLUMN AND NOT A GATE
-- ------------------------------------------------------------------------------------
-- `affordable` is 1 / 0 / NULL, and NULL means NOT COMPUTED -- which is the truth when the
-- engine is unavailable, rather than 0, which would be an accusation. Nothing keys off it.
-- An unaffordable bill today is very often exactly who a subsidised programme exists to
-- reach; the level-1 reviewer decides, and this column is what they read.
--
-- Idempotent. Safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS enterprise_applications (
    id                      bigserial PRIMARY KEY,
    -- The PROGRAMME's tenant. The application lives with the programme it is for.
    tenant_id               uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    programme_id            bigint NOT NULL,

    -- The applicant, and the organisation they belong to. `applicant_org_tenant_id` is what
    -- makes level 1 ANSWERABLE: it names which organisation must vouch for them. Without it
    -- an application has nobody who can give it a first approval.
    applicant_user_id       integer NOT NULL,
    applicant_org_tenant_id uuid NOT NULL REFERENCES enterprise_tenants(id),

    site_name               text NOT NULL,
    contact_email           text,
    contact_phone           text,
    country                 text,
    region                  text,

    monthly_bill            numeric,
    monthly_kwh             numeric,
    tariff_category         text,
    area_m2                 numeric,          -- "checks for area" (owner)

    bill_check_json         text,
    affordable              smallint,         -- 1 / 0 / NULL (NULL = not computed)

    status                  text NOT NULL DEFAULT 'Submitted',

    l1_decision             text,
    l1_by_user_id           integer,
    l1_at                   timestamptz,
    l1_note                 text,
    l2_decision             text,
    l2_by_user_id           integer,
    l2_at                   timestamptz,
    l2_note                 text,
    l3_decision             text,
    l3_by_user_id           integer,
    l3_at                   timestamptz,
    l3_note                 text,
    l3_sponsor_id           text,             -- WHICH sponsor signed

    created_at              timestamptz NOT NULL DEFAULT now(),

    FOREIGN KEY (tenant_id, programme_id)
        REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_ent_app_programme
    ON enterprise_applications (tenant_id, programme_id, status);
CREATE INDEX IF NOT EXISTS ix_ent_app_applicant
    ON enterprise_applications (applicant_user_id);
-- The beneficiary organisation's own inbox is read by org_tenant + "not yet decided".
CREATE INDEX IF NOT EXISTS ix_ent_app_org
    ON enterprise_applications (applicant_org_tenant_id, status);


-- WHO MAY SIGN FOR A SPONSOR.
-- The funding registry (financial_institutions, from the Project Funding module) holds
-- contact details, not logins. Level 3 says "the sponsor approves" -- this table is what
-- gives that sentence a subject. Without it, somebody else would have to approve on the
-- sponsor's behalf, which is precisely what the owner forbade.
--
-- NOT tenant-scoped: an institution is a platform-wide entity, exactly as it is in the
-- funding registry it comes from. The same bank may sponsor two ministries' programmes.
CREATE TABLE IF NOT EXISTS enterprise_sponsor_users (
    institution_id   text NOT NULL,
    user_id          integer NOT NULL,
    added_by_user_id integer,
    created_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (institution_id, user_id)
);


-- RLS on the application table. Every other tenant-owned table in this module carries it.
--
-- THE POLICY IS DELIBERATELY WIDER THAN `tenant_id`, because an application is legitimately
-- read by THREE DIFFERENT ORGANISATIONS -- that is the whole shape of the feature:
--
--   level 2, the PROGRAMME               -> tenant_id
--   level 1, the APPLICANT'S OWN ORG     -> applicant_org_tenant_id
--   level 3, the SPONSOR                 -> a user linked to an institution the programme NAMED
--
-- A policy keyed only on `tenant_id` would hide every application from the very organisation
-- that has to give it its FIRST approval, and level 1 would be unreachable. The sponsor is
-- worse still: they are not a member of the ministry's organisation at all, so their
-- `app.current_tenant` is their OWN, and no tenant-based clause can ever admit them. They are
-- admitted by IDENTITY instead -- `app.current_user_id`, the GUC migration 025's policies
-- already key on -- joined through the link table to the sponsor slots on the programme.
-- Without this clause level 3 works on SQLite (no RLS) and silently returns nothing on live.
ALTER TABLE enterprise_applications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS enterprise_applications_tenant_isolation ON enterprise_applications;
CREATE POLICY enterprise_applications_tenant_isolation ON enterprise_applications
    FOR ALL
    USING (
        tenant_id::text = current_setting('app.current_tenant', true)
        OR applicant_org_tenant_id::text = current_setting('app.current_tenant', true)
        OR EXISTS (
            SELECT 1
              FROM enterprise_programme_registry r
              JOIN enterprise_sponsor_users su
                ON su.institution_id IN (r.sponsor_1_id, r.sponsor_2_id, r.sponsor_3_id)
             WHERE r.tenant_id = enterprise_applications.tenant_id
               AND r.id        = enterprise_applications.programme_id
               AND su.user_id::text = current_setting('app.current_user_id', true)
        )
        OR current_setting('app.current_tenant', true) IS NULL
        OR current_setting('app.current_tenant', true) = ''
    );

COMMIT;
