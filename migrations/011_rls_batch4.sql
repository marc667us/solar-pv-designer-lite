-- 011_rls_batch4.sql
-- =====================================================================
-- SOC 2 M1.6 batch 4 -- RLS for 9 more tables (mixed ownership).
--
-- Owner directive 2026-06-25: total table coverage takes priority over
-- conceptual purity. Every batch-4 table gets tenant_id + RLS even if
-- its data model is global. This closes the audit-dashboard "table
-- without policy" count to (ideally) zero.
--
-- 4 user-owned tables (standard backfill):
--   tickets               <- user_id
--   ticket_replies        <- parent tickets.tenant_id (NOT reply author,
--                           so admin replies stay visible to ticket owner)
--   email_logs            <- user_id
--   shading_history       <- user_id
--
-- 5 global / tenant-agnostic tables (column added + RLS enabled, but
-- tenant_id stays NULL on every row -- parallel-run NULL escape keeps
-- them readable, exactly matching their "all tenants see this" intent):
--   assessment_requests   (anonymous webform leads, email-only)
--   installers            (public directory listing)
--   news_posts            (admin-published content for all tenants)
--   leads                 (anonymous lead pool, no user FK)
--   helpline_learned_kb   (cross-tenant AI knowledge base)
--
-- PHASE 7 FOLLOW-UP REQUIRED for the 5 global tables. The current
-- parallel-run policy admits NULL tenant_id. Phase 7 cutover removes
-- that NULL escape, at which point these 5 tables become invisible to
-- everyone. Options:
--   (a) Tag every row with a designated GLOBAL_TENANT_UUID and extend
--       the strict policy to admit that sentinel.
--   (b) Keep these 5 tables on a separate "global" policy that always
--       permits SELECT (and restricts INSERT/UPDATE/DELETE to admins).
--   (c) Add an admin-bypass GUC checked alongside tenant match.
--
-- Pick (a) or (b) before flipping Phase 7.
--
-- Mirrors 003 / 007 / 008 / 009 / 010 structure. Idempotent.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 -- Reuse helpers from 003.
-- ---------------------------------------------------------------------

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
        RETURN NULL;
    END;
END;
$$;

CREATE OR REPLACE FUNCTION _phase4_user_to_tenant(uid BIGINT) RETURNS UUID
    LANGUAGE sql IMMUTABLE AS $$
    SELECT md5('solarpro-tenant-v1:' || uid::text)::uuid
$$;


-- ---------------------------------------------------------------------
-- PART 2 -- tenant_id UUID column on all 9 batch-4 tables.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    batch4_tables TEXT[] := ARRAY[
        'tickets',
        'ticket_replies',
        'email_logs',
        'shading_history',
        'assessment_requests',
        'installers',
        'news_posts',
        'leads',
        'helpline_learned_kb'
    ];
BEGIN
    FOREACH t IN ARRAY batch4_tables LOOP
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
-- PART 3 -- Backfill the 4 user-owned tables. The 5 global tables
--          intentionally keep tenant_id IS NULL (see header).
-- ---------------------------------------------------------------------

DO $$
BEGIN
    -- 1. tickets -- from owning user_id (NOT NULL by schema)
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='tickets' AND column_name='user_id') THEN
        UPDATE tickets
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;

    -- 2. ticket_replies -- from parent ticket (NOT reply author).
    --    Reason: admin replies must remain visible to the ticket owner.
    --    The strict Phase 7 policy may want a (tenant_match OR admin)
    --    rule -- consider then.
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='ticket_replies' AND column_name='ticket_id') THEN
        UPDATE ticket_replies tr
           SET tenant_id = t.tenant_id
          FROM tickets t
         WHERE tr.ticket_id = t.id
           AND tr.tenant_id IS NULL
           AND t.tenant_id IS NOT NULL;
    END IF;

    -- 3. email_logs -- from owning user_id
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='email_logs' AND column_name='user_id') THEN
        UPDATE email_logs
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;

    -- 4. shading_history -- from owning user_id
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='shading_history' AND column_name='user_id') THEN
        UPDATE shading_history
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;

    -- 5-9. assessment_requests, installers, news_posts, leads,
    --      helpline_learned_kb -- intentionally NOT backfilled.
    --      tenant_id stays NULL; parallel-run policy permits reads.
END;
$$;


-- ---------------------------------------------------------------------
-- PART 4 -- RLS policies (parallel-run flavour, identical pattern).
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    pol_name TEXT;
    batch4_tables TEXT[] := ARRAY[
        'tickets',
        'ticket_replies',
        'email_logs',
        'shading_history',
        'assessment_requests',
        'installers',
        'news_posts',
        'leads',
        'helpline_learned_kb'
    ];
BEGIN
    FOREACH t IN ARRAY batch4_tables LOOP
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
-- All 9 must return a row:
--
--   SELECT table_name FROM information_schema.columns
--    WHERE column_name='tenant_id' AND table_schema='public'
--      AND table_name IN (
--        'tickets','ticket_replies','email_logs','shading_history',
--        'assessment_requests','installers','news_posts','leads',
--        'helpline_learned_kb');
--
--   SELECT tablename, policyname FROM pg_policies
--    WHERE policyname IN (
--      'tickets_tenant_isolation','ticket_replies_tenant_isolation',
--      'email_logs_tenant_isolation','shading_history_tenant_isolation',
--      'assessment_requests_tenant_isolation','installers_tenant_isolation',
--      'news_posts_tenant_isolation','leads_tenant_isolation',
--      'helpline_learned_kb_tenant_isolation');
--
-- Coverage (expect zero on the 4 user-owned tables; the 5 global
-- tables remain 100% NULL -- that's by design):
--
--   SELECT
--     (SELECT COUNT(*) FROM tickets         WHERE tenant_id IS NULL) AS unbackfilled_tickets,
--     (SELECT COUNT(*) FROM ticket_replies  WHERE tenant_id IS NULL) AS unbackfilled_replies,
--     (SELECT COUNT(*) FROM email_logs      WHERE tenant_id IS NULL) AS unbackfilled_email,
--     (SELECT COUNT(*) FROM shading_history WHERE tenant_id IS NULL) AS unbackfilled_shading;
-- =====================================================================
