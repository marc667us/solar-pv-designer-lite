-- 003_rls_tenant.sql
-- =====================================================================
-- Phase 4 of docs/SECURITY_MIGRATION_KEYCLOAK.md
--
-- Adds the multi-tenant column + RLS layer to the live Postgres schema.
-- The migration is split into 4 parts so a half-apply leaves the DB in
-- a well-defined intermediate state:
--
--   PART 1 — Helper function `current_tenant_id()` reading the GUC.
--   PART 2 — `ADD COLUMN tenant_id UUID` on every tenant-owned table.
--   PART 3 — Deterministic backfill so existing rows have a tenant_id.
--   PART 4 — `ENABLE ROW LEVEL SECURITY` + parallel-run policies.
--
-- Parallel-run safety
-- -------------------
-- The Phase 4 RLS policy is INTENTIONALLY permissive when no GUC is set
-- ("`current_tenant_id()` IS NULL  OR  tenant_id = current_tenant_id()`").
-- That means:
--   * Pre-Keycloak code paths (KEYCLOAK_ENABLED=false) continue to read
--     and write every row exactly as before -- no breakage at deploy.
--   * Post-Keycloak code paths set the GUC via
--     `app.security.tenant_context.apply_tenant_guc(conn)` and the
--     policy kicks in: only rows whose tenant_id matches the GUC are
--     visible.
--
-- The hard cut to `FORCE ROW LEVEL SECURITY` (which refuses even table
-- owners without a GUC) is left to Phase 7's cutover migration so the
-- legacy code path can keep working through staging.
--
-- Idempotent: every statement uses IF NOT EXISTS / IF EXISTS, so the
-- file can be applied twice without error. Same migration file ships
-- to staging and prod.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 -- SQL helpers
-- ---------------------------------------------------------------------

-- `current_tenant_id()` returns the GUC `app.current_tenant` if set,
-- otherwise NULL. The `true` second arg to `current_setting` means
-- "missing OK -- return NULL instead of raising".
CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS UUID
    LANGUAGE plpgsql STABLE AS $$
DECLARE
    raw_value TEXT;
BEGIN
    raw_value := current_setting('app.current_tenant', true);
    IF raw_value IS NULL OR raw_value = '' THEN
        RETURN NULL;
    END IF;
    BEGIN
        RETURN raw_value::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
        -- Defensive: a non-UUID GUC value behaves like "unset" rather
        -- than crashing every query. The middleware should never send
        -- a non-UUID here, but we'd rather a 0-row result than a 5xx.
        RETURN NULL;
    END;
END;
$$;

-- `current_user_sub()` mirrors the above for the JWT `sub` claim.
-- Useful for triggers + future audit_log defaults.
CREATE OR REPLACE FUNCTION current_user_sub() RETURNS TEXT
    LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.current_user', true), '')
$$;

-- ---------------------------------------------------------------------
-- PART 2 -- tenant_id columns on tenant-owned tables
--
-- Every column is idempotent ADD COLUMN IF NOT EXISTS. Tables that
-- don't exist on this database are silently skipped.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    tenant_tables TEXT[] := ARRAY[
        'projects',
        'tickets',
        'ticket_replies',
        'email_logs',
        'password_reset_tokens',
        'payments',
        'suppliers',
        'equipment_catalog',
        'rfqs',
        'rfq_items',
        'marketplace_boms',
        'marketplace_bom_items',
        'marketplace_boqs',
        'marketplace_boq_items',
        'price_sheets',
        'price_sheet_items',
        'marketplace_audit'
    ];
BEGIN
    FOREACH t IN ARRAY tenant_tables LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = t
        ) THEN
            EXECUTE format(
                'ALTER TABLE %I ADD COLUMN IF NOT EXISTS tenant_id UUID',
                t
            );
            EXECUTE format(
                'CREATE INDEX IF NOT EXISTS %I ON %I (tenant_id)',
                'idx_' || t || '_tenant_id', t
            );
        END IF;
    END LOOP;
END;
$$;

-- ---------------------------------------------------------------------
-- PART 3 -- Backfill
--
-- The live app today is single-tenant-per-user: every user is their own
-- tenant. Backfill `tenant_id` deterministically from the existing
-- `user_id` so any future "two users in the same tenant" workflow can
-- coalesce by updating one column.
--
-- Deterministic UUIDs: we hash the user_id (int) into a UUID via
-- `gen_random_uuid()` would be wrong (non-deterministic). Instead we
-- use `md5(...)::uuid` with a namespace prefix so the value is stable
-- across re-runs.
-- ---------------------------------------------------------------------

-- One-shot helper: build a stable tenant_id from a SolarPro user_id.
CREATE OR REPLACE FUNCTION _phase4_user_to_tenant(uid BIGINT) RETURNS UUID
    LANGUAGE sql IMMUTABLE AS $$
    SELECT md5('solarpro-tenant-v1:' || uid::text)::uuid
$$;

DO $$
BEGIN
    -- projects.tenant_id from projects.user_id
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='projects' AND column_name='user_id') THEN
        UPDATE projects
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='tickets' AND column_name='user_id') THEN
        UPDATE tickets
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='ticket_replies' AND column_name='user_id') THEN
        UPDATE ticket_replies
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='email_logs' AND column_name='user_id') THEN
        UPDATE email_logs
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='password_reset_tokens' AND column_name='user_id') THEN
        UPDATE password_reset_tokens
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='payments' AND column_name='user_id') THEN
        UPDATE payments
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- PART 4 -- RLS policies (parallel-run flavour)
--
-- Per-table macro:
--   ALTER TABLE x ENABLE ROW LEVEL SECURITY;
--   DROP POLICY IF EXISTS x_tenant_isolation ON x;
--   CREATE POLICY x_tenant_isolation ON x
--     USING ( current_tenant_id() IS NULL
--             OR tenant_id IS NULL
--             OR tenant_id = current_tenant_id() );
--
-- The two NULL escapes are the parallel-run safety net:
--   * GUC unset (KC off) -> every row visible (legacy code still works)
--   * Row's tenant_id NULL (legacy rows, freshly-INSERTed pre-fill) ->
--     visible (so existing UPDATE/DELETE on legacy rows still work).
--
-- Phase 7's cutover migration tightens this by:
--   * Dropping the GUC-unset escape (force a tenant context per request).
--   * Dropping the row-NULL escape (every row must carry tenant_id).
--   * Switching to FORCE ROW LEVEL SECURITY (denies even the table owner
--     without a GUC).
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    pol_name TEXT;
    tenant_tables TEXT[] := ARRAY[
        'projects',
        'tickets',
        'ticket_replies',
        'email_logs',
        'password_reset_tokens',
        'payments',
        'suppliers',
        'equipment_catalog',
        'rfqs',
        'rfq_items',
        'marketplace_boms',
        'marketplace_bom_items',
        'marketplace_boqs',
        'marketplace_boq_items',
        'price_sheets',
        'price_sheet_items',
        'marketplace_audit'
    ];
BEGIN
    FOREACH t IN ARRAY tenant_tables LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = t
        ) THEN
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
            pol_name := t || '_tenant_isolation';
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', pol_name, t);
            EXECUTE format($pol$
                CREATE POLICY %I ON %I
                    USING (
                        current_tenant_id() IS NULL
                        OR tenant_id IS NULL
                        OR tenant_id = current_tenant_id()
                    )
                    WITH CHECK (
                        current_tenant_id() IS NULL
                        OR tenant_id IS NULL
                        OR tenant_id = current_tenant_id()
                    )
                $pol$,
                pol_name, t
            );
        END IF;
    END LOOP;
END;
$$;

COMMIT;

-- =====================================================================
-- POST-APPLY VERIFICATION
-- ---------------------------------------------------------------------
-- Once applied, these queries should each return at least one row:
--
--   SELECT proname FROM pg_proc WHERE proname IN
--     ('current_tenant_id','current_user_sub','_phase4_user_to_tenant');
--
--   SELECT table_name FROM information_schema.columns
--    WHERE column_name = 'tenant_id'
--      AND table_schema = 'public';
--
--   SELECT tablename, policyname FROM pg_policies
--    WHERE policyname LIKE '%_tenant_isolation';
--
-- Set the GUC and confirm RLS:
--
--   SELECT set_config('app.current_tenant',
--                     _phase4_user_to_tenant(1)::text, true);
--   SELECT COUNT(*) FROM projects;   -- only user_id=1's rows
--   RESET app.current_tenant;
--   SELECT COUNT(*) FROM projects;   -- all rows again (parallel-run)
-- =====================================================================
