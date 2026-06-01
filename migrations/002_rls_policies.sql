-- SolarPro Global — PostgreSQL Row Level Security (RLS)
-- Migration: 002 - Enable RLS on all tenant-owned tables
-- Run AFTER migration 001.
-- Architecture: Zero Trust - every query inherits tenant context set at connection start.

-- ─── App context setters (called by backend on every request) ──────────────
-- The backend sets these at connection start:
--   SET app.current_tenant = 'uuid';
--   SET app.current_user   = 'uuid';
--   SET app.current_role   = 'engineer';   -- platform role

-- Helper functions to read app context
CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS UUID
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN current_setting('app.current_tenant', TRUE)::UUID;
EXCEPTION WHEN OTHERS THEN RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION current_user_id() RETURNS UUID
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN current_setting('app.current_user', TRUE)::UUID;
EXCEPTION WHEN OTHERS THEN RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION current_platform_role() RETURNS TEXT
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN COALESCE(current_setting('app.current_role', TRUE), 'customer');
EXCEPTION WHEN OTHERS THEN RETURN 'customer';
END;
$$;

CREATE OR REPLACE FUNCTION is_super_admin() RETURNS BOOLEAN
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN current_platform_role() IN ('super_admin', 'platform_admin');
EXCEPTION WHEN OTHERS THEN RETURN FALSE;
END;
$$;

-- ═══════════════════════════════════════════════════════════════════════════
-- ENABLE RLS ON ALL TENANT-OWNED TABLES
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE organizations             ENABLE ROW LEVEL SECURITY;
ALTER TABLE users                     ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_sessions             ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads                     ENABLE ROW LEVEL SECURITY;
ALTER TABLE assessment_requests       ENABLE ROW LEVEL SECURITY;
ALTER TABLE crm_opportunities         ENABLE ROW LEVEL SECURITY;
ALTER TABLE proposals                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE installers                ENABLE ROW LEVEL SECURITY;
ALTER TABLE procurement_packages      ENABLE ROW LEVEL SECURITY;
ALTER TABLE bidder_submissions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions             ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE tickets                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE ticket_replies            ENABLE ROW LEVEL SECURITY;
ALTER TABLE uploaded_files            ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_logs                ENABLE ROW LEVEL SECURITY;

-- ═══════════════════════════════════════════════════════════════════════════
-- RLS POLICIES — ORGANIZATIONS
-- ═══════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS org_tenant_policy ON organizations;
CREATE POLICY org_tenant_policy ON organizations FOR ALL
USING (
    is_super_admin()
    OR id = current_tenant_id()
);

-- ═══════════════════════════════════════════════════════════════════════════
-- RLS POLICIES — USERS
-- ═══════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS users_tenant_read ON users;
CREATE POLICY users_tenant_read ON users FOR SELECT
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
    OR id = current_user_id()      -- users can always read their own record
);

DROP POLICY IF EXISTS users_tenant_write ON users;
CREATE POLICY users_tenant_write ON users FOR INSERT
WITH CHECK (
    is_super_admin()
    OR organization_id = current_tenant_id()
);

DROP POLICY IF EXISTS users_tenant_update ON users;
CREATE POLICY users_tenant_update ON users FOR UPDATE
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
    OR id = current_user_id()      -- users can update own profile
);

-- ═══════════════════════════════════════════════════════════════════════════
-- RLS POLICIES — USER SESSIONS
-- ═══════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS sessions_policy ON user_sessions;
CREATE POLICY sessions_policy ON user_sessions FOR ALL
USING (
    is_super_admin()
    OR user_id = current_user_id()
    OR organization_id = current_tenant_id()
);

-- ═══════════════════════════════════════════════════════════════════════════
-- RLS POLICIES — PROJECTS
-- ═══════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS projects_read ON projects;
CREATE POLICY projects_read ON projects FOR SELECT
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
);

DROP POLICY IF EXISTS projects_write ON projects;
CREATE POLICY projects_write ON projects FOR INSERT
WITH CHECK (
    is_super_admin()
    OR organization_id = current_tenant_id()
);

DROP POLICY IF EXISTS projects_update ON projects;
CREATE POLICY projects_update ON projects FOR UPDATE
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
);

DROP POLICY IF EXISTS projects_delete ON projects;
CREATE POLICY projects_delete ON projects FOR DELETE
USING (
    is_super_admin()
    OR (organization_id = current_tenant_id()
        AND created_by_user_id = current_user_id())
);

-- ═══════════════════════════════════════════════════════════════════════════
-- RLS POLICIES — LEADS & CRM
-- ═══════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS leads_policy ON leads;
CREATE POLICY leads_policy ON leads FOR ALL
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
);

DROP POLICY IF EXISTS assessments_policy ON assessment_requests;
CREATE POLICY assessments_policy ON assessment_requests FOR ALL
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
    OR organization_id IS NULL   -- public submissions not yet assigned to org
);

DROP POLICY IF EXISTS opp_policy ON crm_opportunities;
CREATE POLICY opp_policy ON crm_opportunities FOR ALL
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
);

-- ═══════════════════════════════════════════════════════════════════════════
-- RLS POLICIES — PROPOSALS
-- ═══════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS proposals_read ON proposals;
CREATE POLICY proposals_read ON proposals FOR SELECT
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
);

DROP POLICY IF EXISTS proposals_write ON proposals;
CREATE POLICY proposals_write ON proposals FOR INSERT
WITH CHECK (
    is_super_admin()
    OR organization_id = current_tenant_id()
);

DROP POLICY IF EXISTS proposals_modify ON proposals;
CREATE POLICY proposals_modify ON proposals FOR UPDATE
USING (
    is_super_admin()
    OR (organization_id = current_tenant_id()
        AND created_by_user_id = current_user_id())
);

-- ═══════════════════════════════════════════════════════════════════════════
-- RLS POLICIES — PROCUREMENT
-- ═══════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS installers_policy ON installers;
CREATE POLICY installers_policy ON installers FOR ALL
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
    OR organization_id IS NULL   -- public installer registrations
);

DROP POLICY IF EXISTS packages_policy ON procurement_packages;
CREATE POLICY packages_policy ON procurement_packages FOR ALL
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
);

DROP POLICY IF EXISTS bids_policy ON bidder_submissions;
CREATE POLICY bids_policy ON bidder_submissions FOR ALL
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
);

-- ═══════════════════════════════════════════════════════════════════════════
-- RLS POLICIES — SUBSCRIPTIONS & PAYMENTS
-- ═══════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS subs_policy ON subscriptions;
CREATE POLICY subs_policy ON subscriptions FOR ALL
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
);

DROP POLICY IF EXISTS payments_policy ON payments;
CREATE POLICY payments_policy ON payments FOR ALL
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
);

-- ═══════════════════════════════════════════════════════════════════════════
-- RLS POLICIES — SUPPORT TICKETS
-- ═══════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS tickets_policy ON tickets;
CREATE POLICY tickets_policy ON tickets FOR ALL
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
    OR user_id = current_user_id()
);

DROP POLICY IF EXISTS replies_policy ON ticket_replies;
CREATE POLICY replies_policy ON ticket_replies FOR ALL
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
    OR user_id = current_user_id()
);

-- ═══════════════════════════════════════════════════════════════════════════
-- RLS POLICIES — FILES
-- ═══════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS files_policy ON uploaded_files;
CREATE POLICY files_policy ON uploaded_files FOR ALL
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
    OR (is_public = TRUE)
);

-- ═══════════════════════════════════════════════════════════════════════════
-- RLS POLICIES — AUDIT LOG
-- ═══════════════════════════════════════════════════════════════════════════

-- Super admin sees all; tenant owner/admin sees own org; others see nothing
DROP POLICY IF EXISTS audit_policy ON audit_log;
CREATE POLICY audit_policy ON audit_log FOR SELECT
USING (
    is_super_admin()
    OR (organization_id = current_tenant_id()
        AND current_platform_role() IN ('platform_admin','sales_manager','support_officer'))
);

DROP POLICY IF EXISTS audit_insert ON audit_log;
CREATE POLICY audit_insert ON audit_log FOR INSERT
WITH CHECK (TRUE);    -- backend can always write audit events

DROP POLICY IF EXISTS email_log_policy ON email_logs;
CREATE POLICY email_log_policy ON email_logs FOR ALL
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
);

-- ═══════════════════════════════════════════════════════════════════════════
-- FORCE ALL USERS TO USE RLS (prevents bypass)
-- ═══════════════════════════════════════════════════════════════════════════
-- Note: the DB superuser can always bypass. App uses a restricted role.
-- Create the app database role (run once by DBA):
-- CREATE ROLE solarpro_app LOGIN PASSWORD 'strong-password';
-- GRANT CONNECT ON DATABASE solarpro_db TO solarpro_app;
-- GRANT USAGE ON SCHEMA public TO solarpro_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO solarpro_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO solarpro_app;
-- The solarpro_app role does NOT have BYPASSRLS privilege.

\echo 'RLS migration 002 complete.'
\echo 'All tenant-owned tables are now protected by Row Level Security.'
