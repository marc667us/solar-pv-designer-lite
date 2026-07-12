-- =============================================================================
-- 025 -- Enterprise Programme rebuild, slice 1: true enterprise tenancy + RBAC
-- =============================================================================
--
-- WHAT THIS DOES
--   Introduces many-users-per-organisation tenancy for the enterprise module
--   WITHOUT touching how any existing project is owned.
--
-- THE LOAD-BEARING DECISION (do not undo -- see
-- docs/enterprise-programme/rebuild/04-target-architecture.md)
--   SolarPro is single-user-owned today. Both project loaders enforce
--   `WHERE id=? AND user_id=?` (web_app.py:1043, new_capital_investment_routes.py:6325)
--   and `tenant_id` is md5('solarpro-tenant-v1:'||user_id) -- a pure function of the
--   user (003_rls_tenant.sql:136). Migration 001 DROPped `organizations` outright.
--
--   Rather than rewrite ownership (which would put every existing user's projects at
--   risk), enterprise tenancy is an OVERLAY:
--     * every existing user is backfilled a PERSONAL tenant whose id is exactly the
--       deterministic hash they already have, so nothing they own moves or changes;
--     * real multi-user organisations are NEW rows with fresh UUIDs;
--     * projects join a programme only through link rows (slice 3), never by
--       rewriting projects.user_id.
--   This migration therefore performs ZERO writes to `projects` or
--   `capital_investment_projects`. That is the safety property. Keep it.
--
-- MIGRATION RULES LEARNED THE HARD WAY (024 failed its first apply on the 2nd one)
--   1. Whole file is one transaction with ON_ERROR_STOP -- a partial apply is worse
--      than no apply.
--   2. Postgres parses a `LANGUAGE sql` function body at CREATE time, so every SQL
--      function is declared AFTER the tables it references. See PART 4.
--   3. `admin_settings` is FORCE-RLS admin-only: any write to it needs
--      set_config('app.current_role','admin',true) INSIDE this transaction or it
--      silently rolls back. See PART 5.
--
-- IDEMPOTENT: safe to re-run.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- PART 1 -- tenants
-- -----------------------------------------------------------------------------
-- `legacy_user_id` is set ONLY on backfilled personal tenants and is what makes the
-- backfill idempotent (partial unique index below). Real organisations leave it NULL.
CREATE TABLE IF NOT EXISTS enterprise_tenants (
    id                 uuid PRIMARY KEY,
    legacy_user_id     integer,
    slug               text NOT NULL,
    legal_name         text NOT NULL,
    display_name       text,
    organisation_type  text NOT NULL DEFAULT 'personal',
    country            text,
    default_currency   text NOT NULL DEFAULT 'GHS',
    default_timezone   text NOT NULL DEFAULT 'Africa/Accra',
    unit_system        text NOT NULL DEFAULT 'metric',
    branding_json      jsonb NOT NULL DEFAULT '{}'::jsonb,
    status             text NOT NULL DEFAULT 'active',
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_tenants_slug
    ON enterprise_tenants (slug);
-- one personal tenant per user, enforced by the DB rather than by app logic
CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_tenants_legacy_user
    ON enterprise_tenants (legacy_user_id) WHERE legacy_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_ent_tenants_status
    ON enterprise_tenants (status);

-- -----------------------------------------------------------------------------
-- PART 2 -- memberships and role assignments
-- -----------------------------------------------------------------------------
-- NOTE ON NAMING: migration 024 already created a table called
-- `enterprise_memberships` bound to the old `enterprise_organisations`. This
-- rebuild does NOT reuse that name -- colliding with a live table mid-rebuild is
-- how you lose data. The old table stays untouched and dark until the cleanup
-- migration retires it.
CREATE TABLE IF NOT EXISTS enterprise_tenant_memberships (
    id                 bigserial PRIMARY KEY,
    tenant_id          uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    user_id            integer NOT NULL,
    email              text,
    status             text NOT NULL DEFAULT 'active',
    invited_by_user_id integer,
    joined_at          timestamptz NOT NULL DEFAULT now(),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_membership_tenant_user
    ON enterprise_tenant_memberships (tenant_id, user_id);
CREATE INDEX IF NOT EXISTS ix_ent_membership_user
    ON enterprise_tenant_memberships (user_id);
CREATE INDEX IF NOT EXISTS ix_ent_membership_tenant_status
    ON enterprise_tenant_memberships (tenant_id, status);

-- A role is always granted WITHIN a tenant, and optionally narrowed to a scope
-- (a programme, a region, a district). `scope_type='tenant'` means tenant-wide.
-- The master prompt is explicit that roles must NOT be globally powerful by
-- default -- power comes from the permission map in constants.py, not from here.
CREATE TABLE IF NOT EXISTS enterprise_role_assignments (
    id            bigserial PRIMARY KEY,
    tenant_id     uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    user_id       integer NOT NULL,
    role_code     text NOT NULL,
    scope_type    text NOT NULL DEFAULT 'tenant',   -- tenant | programme | region | district
    scope_id      bigint,                            -- programme id when scope_type='programme'
    region_code   text,
    district_code text,
    starts_at     timestamptz,
    ends_at       timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    created_by_user_id integer
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_role_assignment
    ON enterprise_role_assignments
       (tenant_id, user_id, role_code, scope_type,
        COALESCE(scope_id, -1), COALESCE(region_code, ''), COALESCE(district_code, ''));
CREATE INDEX IF NOT EXISTS ix_ent_role_tenant_user
    ON enterprise_role_assignments (tenant_id, user_id);
CREATE INDEX IF NOT EXISTS ix_ent_role_tenant_role
    ON enterprise_role_assignments (tenant_id, role_code);

-- -----------------------------------------------------------------------------
-- PART 3 -- taxonomy (the dropdown source of truth)
-- -----------------------------------------------------------------------------
-- The owner's hard requirement is: minimise typing, use dropdowns everywhere.
-- Every selectable vocabulary in the module resolves to a row here. tenant_id NULL
-- == a global option shipped with the platform; a tenant may add its own options
-- without affecting anyone else. Seeded from app/enterprise_programme/constants.py.
CREATE TABLE IF NOT EXISTS enterprise_taxonomy_options (
    id            bigserial PRIMARY KEY,
    tenant_id     uuid REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    taxonomy      text NOT NULL,   -- e.g. 'programme_status', 'gate', 'role', 'funding_source'
    code          text NOT NULL,
    label         text NOT NULL,
    parent_code   text,            -- drives cascading dropdowns (e.g. gate -> phase)
    sort_order    integer NOT NULL DEFAULT 0,
    extra_json    jsonb NOT NULL DEFAULT '{}'::jsonb,
    active        boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_taxonomy_global
    ON enterprise_taxonomy_options (taxonomy, code) WHERE tenant_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_taxonomy_tenant
    ON enterprise_taxonomy_options (tenant_id, taxonomy, code) WHERE tenant_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_ent_taxonomy_lookup
    ON enterprise_taxonomy_options (taxonomy, active, sort_order);

-- -----------------------------------------------------------------------------
-- PART 4 -- helper function (AFTER its tables -- see header rule 2)
-- -----------------------------------------------------------------------------
-- Returns the tenant ids the current user is an active member of. Used by the RLS
-- policies below. Declaring this in PART 1 would fail at CREATE time because
-- Postgres parses the body immediately and the table would not yet exist -- this is
-- exactly how migration 024's first apply died.
CREATE OR REPLACE FUNCTION current_enterprise_tenant_ids()
RETURNS SETOF uuid
LANGUAGE sql STABLE AS $$
    SELECT m.tenant_id
      FROM enterprise_tenant_memberships m
     WHERE m.status = 'active'
       AND m.user_id = NULLIF(current_setting('app.current_user_id', true), '')::integer
$$;

-- -----------------------------------------------------------------------------
-- PART 5 -- RLS
-- -----------------------------------------------------------------------------
-- Defence in depth ONLY. The app layer remains the primary tenant boundary (every
-- query is scoped by the caller's resolved tenant_id, never by an id from the URL).
-- Do NOT describe this as DB-enforced isolation until FORCE is on and the GUC path
-- is proven on live.
--
-- The membership table is the BASE policy and deliberately queries no other
-- enterprise table -- that is what stops RLS policy recursion.
ALTER TABLE enterprise_tenants              ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_tenant_memberships   ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_role_assignments     ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_taxonomy_options     ENABLE ROW LEVEL SECURITY;

-- BASE POLICY -- must not call current_enterprise_tenant_ids(), because that
-- function READS THIS TABLE. A policy on a table whose USING clause queries the same
-- table recurses (and under FORCE RLS it will actually bite). So the base policy is
-- expressed purely on the row's own column: you can see your own membership rows.
-- Every other enterprise policy is free to use the helper, because none of those
-- tables is read by the helper.
DROP POLICY IF EXISTS ent_membership_self ON enterprise_tenant_memberships;
CREATE POLICY ent_membership_self ON enterprise_tenant_memberships
    FOR ALL USING (
        user_id = NULLIF(current_setting('app.current_user_id', true), '')::integer
    );

DROP POLICY IF EXISTS ent_tenants_member ON enterprise_tenants;
CREATE POLICY ent_tenants_member ON enterprise_tenants
    FOR ALL USING (id IN (SELECT current_enterprise_tenant_ids()));

DROP POLICY IF EXISTS ent_roles_member ON enterprise_role_assignments;
CREATE POLICY ent_roles_member ON enterprise_role_assignments
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

-- Global taxonomy rows (tenant_id IS NULL) are readable by everyone; tenant-owned
-- options are visible only to that tenant's members.
DROP POLICY IF EXISTS ent_taxonomy_member ON enterprise_taxonomy_options;
CREATE POLICY ent_taxonomy_member ON enterprise_taxonomy_options
    FOR ALL USING (
        tenant_id IS NULL
        OR tenant_id IN (SELECT current_enterprise_tenant_ids())
    );

-- -----------------------------------------------------------------------------
-- PART 6 -- backfill personal tenants
-- -----------------------------------------------------------------------------
-- Every existing user gets a personal tenant whose id is EXACTLY the deterministic
-- tenant hash they already carry (003_rls_tenant.sql:136). This is what makes the
-- overlay non-breaking: nothing they own has to move.
--
-- Writes ONLY to enterprise_* tables. `projects` and `capital_investment_projects`
-- are not touched. ON CONFLICT makes re-running a no-op.
INSERT INTO enterprise_tenants (
    id, legacy_user_id, slug, legal_name, display_name, organisation_type, status
)
SELECT
    md5('solarpro-tenant-v1:' || u.id::text)::uuid,
    u.id,
    'personal-' || u.id::text,
    COALESCE(NULLIF(TRIM(u.username), ''), 'user-' || u.id::text),
    COALESCE(NULLIF(TRIM(u.username), ''), 'user-' || u.id::text),
    'personal',
    'active'
FROM users u
ON CONFLICT (id) DO NOTHING;

-- Each user is an active member of their own personal tenant, and its owner.
INSERT INTO enterprise_tenant_memberships (tenant_id, user_id, email, status)
SELECT t.id, t.legacy_user_id, u.email, 'active'
FROM enterprise_tenants t
JOIN users u ON u.id = t.legacy_user_id
WHERE t.legacy_user_id IS NOT NULL
ON CONFLICT (tenant_id, user_id) DO NOTHING;

INSERT INTO enterprise_role_assignments (tenant_id, user_id, role_code, scope_type)
SELECT t.id, t.legacy_user_id, 'enterprise_owner', 'tenant'
FROM enterprise_tenants t
WHERE t.legacy_user_id IS NOT NULL
ON CONFLICT DO NOTHING;

-- -----------------------------------------------------------------------------
-- PART 7 -- flags
-- -----------------------------------------------------------------------------
-- admin_settings is FORCE-RLS and admin-only. Without this set_config the INSERT
-- below silently rolls back and the flags never appear. This is not optional.
SELECT set_config('app.current_role', 'admin', true);

INSERT INTO admin_settings (key, value)
VALUES ('enterprise_rebuild_enabled', '0')
ON CONFLICT (key) DO NOTHING;

COMMIT;

-- =============================================================================
-- ROLLBACK (manual; prefer flag-off over dropping anything)
--   UPDATE admin_settings SET value='0' WHERE key='enterprise_rebuild_enabled';
-- Only if the schema itself must go (this DESTROYS enterprise data -- back up first):
--   DROP TABLE IF EXISTS enterprise_taxonomy_options, enterprise_role_assignments,
--                        enterprise_tenant_memberships, enterprise_tenants CASCADE;
--   DROP FUNCTION IF EXISTS current_enterprise_tenant_ids();
-- Note: dropping these does NOT affect any user's projects -- by design, this
-- migration never wrote to them.
-- =============================================================================
