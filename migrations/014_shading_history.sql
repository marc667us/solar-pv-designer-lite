-- 014_shading_history.sql
-- =====================================================================
-- SOC 2 M1.6 batch 4 RECOVERY -- create shading_history on Postgres,
-- then add tenant_id + RLS so it matches batch 4's coverage intent.
--
-- Background: shading_history was originally defined in web_app.py's
-- init_db() SQLite-only branch (line ~557, inside `if not _is_postgres`)
-- and was NEVER added to migrations/001_mirror_sqlite.sql. On live PG
-- the table has never existed; every INSERT (web_app.py:13167) silently
-- fails inside its try/except wrapper.
--
-- Migration 011 (batch 4) tried to ADD COLUMN tenant_id + RLS on this
-- table but the IF EXISTS guard short-circuited (table absent). The
-- batch-4 verify workflow was relaxed to tolerate 8 columns instead of
-- 9 (commit d283f8e) -- this migration closes that gap.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS + ADD COLUMN IF NOT EXISTS +
-- DROP POLICY IF EXISTS + CREATE POLICY. Safe to re-run.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 -- Reuse helpers from 001 (sqlite_ts) + 003/011 (tenant_id).
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
-- PART 2 -- Create the table (mirrors web_app.py:557 SQLite DDL).
--           Column types translated to Postgres equivalents per the
--           sqlite_ts() / SERIAL conventions in migrations/001.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS shading_history (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL,
    username        TEXT DEFAULT '',
    project_id      INTEGER NOT NULL,
    project_name    TEXT DEFAULT '',
    location        TEXT DEFAULT '',
    mount_type      TEXT DEFAULT '',
    factor          REAL DEFAULT 1.0,
    label           TEXT DEFAULT '',
    loss_pct        REAL DEFAULT 0,
    agent_narrative TEXT DEFAULT '',
    agent_version   TEXT DEFAULT '',
    obstructions_n  INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT sqlite_ts()
);

CREATE INDEX IF NOT EXISTS idx_shading_history_user
    ON shading_history (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shading_history_project
    ON shading_history (project_id, created_at DESC);


-- ---------------------------------------------------------------------
-- PART 3 -- tenant_id UUID column + index.
-- ---------------------------------------------------------------------

ALTER TABLE shading_history ADD COLUMN IF NOT EXISTS tenant_id UUID;
CREATE INDEX IF NOT EXISTS idx_shading_history_tenant_id
    ON shading_history (tenant_id);


-- ---------------------------------------------------------------------
-- PART 4 -- Backfill tenant_id from user_id (NOT NULL by schema).
-- ---------------------------------------------------------------------

UPDATE shading_history
   SET tenant_id = _phase4_user_to_tenant(user_id)
 WHERE tenant_id IS NULL AND user_id IS NOT NULL;


-- ---------------------------------------------------------------------
-- PART 5 -- RLS policy (parallel-run flavour, identical to batch 4).
-- ---------------------------------------------------------------------

ALTER TABLE shading_history ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS shading_history_tenant_isolation ON shading_history;
CREATE POLICY shading_history_tenant_isolation ON shading_history
    USING (
        current_tenant_id() IS NULL
        OR tenant_id IS NULL
        OR tenant_id = current_tenant_id()
    )
    WITH CHECK (
        current_tenant_id() IS NULL
        OR tenant_id IS NULL
        OR tenant_id = current_tenant_id()
    );

COMMIT;

-- =====================================================================
-- POST-APPLY VERIFICATION
-- ---------------------------------------------------------------------
--   SELECT column_name FROM information_schema.columns
--    WHERE table_name='shading_history' AND table_schema='public'
--      AND column_name IN ('id','user_id','tenant_id','created_at');
--   -- expect 4 rows
--
--   SELECT policyname FROM pg_policies
--    WHERE tablename='shading_history';
--   -- expect 1 row: shading_history_tenant_isolation
--
--   SELECT COUNT(*) FILTER (WHERE tenant_id IS NULL)  AS unbackfilled,
--          COUNT(*) FILTER (WHERE tenant_id IS NOT NULL) AS tagged,
--          COUNT(*) AS total
--     FROM shading_history;
--   -- expect unbackfilled=0 (or close to 0) since user_id is NOT NULL.
-- =====================================================================
