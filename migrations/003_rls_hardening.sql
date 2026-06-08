-- SolarPro Global — RLS hardening
-- Migration: 003 - Fix RLS loopholes identified in 2026-06-06 quality-gate review
-- Run AFTER 001 and 002.
--
-- Addresses work-schedule items 1.3 (FORCE RLS), 1.4 (assessment_requests),
-- 1.5 (installers), 1.6 (uploaded_files), 1.7 (users self-update column lock),
-- 1.8 (audit_log WITH CHECK TRUE).
--
-- Source: C:\Users\USER\Desktop\SolarPro_QualityGate_WorkSchedule_2026-06-06.md

-- ═══════════════════════════════════════════════════════════════════════════
-- 1.3 FORCE ROW LEVEL SECURITY on every tenant-owned table
-- Without FORCE, the table owner role bypasses every RLS policy.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE organizations        FORCE ROW LEVEL SECURITY;
ALTER TABLE users                FORCE ROW LEVEL SECURITY;
ALTER TABLE user_sessions        FORCE ROW LEVEL SECURITY;
ALTER TABLE projects             FORCE ROW LEVEL SECURITY;
ALTER TABLE leads                FORCE ROW LEVEL SECURITY;
ALTER TABLE assessment_requests  FORCE ROW LEVEL SECURITY;
ALTER TABLE crm_opportunities    FORCE ROW LEVEL SECURITY;
ALTER TABLE proposals            FORCE ROW LEVEL SECURITY;
ALTER TABLE installers           FORCE ROW LEVEL SECURITY;
ALTER TABLE procurement_packages FORCE ROW LEVEL SECURITY;
ALTER TABLE bidder_submissions   FORCE ROW LEVEL SECURITY;
ALTER TABLE subscriptions        FORCE ROW LEVEL SECURITY;
ALTER TABLE payments             FORCE ROW LEVEL SECURITY;
ALTER TABLE tickets              FORCE ROW LEVEL SECURITY;
ALTER TABLE ticket_replies       FORCE ROW LEVEL SECURITY;
ALTER TABLE uploaded_files       FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_log            FORCE ROW LEVEL SECURITY;
ALTER TABLE email_logs           FORCE ROW LEVEL SECURITY;

-- ═══════════════════════════════════════════════════════════════════════════
-- 1.4 assessment_requests — close cross-tenant PII leak
-- Old policy let every tenant read, modify, or delete every
-- organization_id IS NULL row (which holds customer PII for public
-- assessment submissions). Split into tenant-rw + public-insert-only.
-- ═══════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS assessments_policy ON assessment_requests;

CREATE POLICY assessments_tenant_rw ON assessment_requests FOR ALL
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
)
WITH CHECK (
    is_super_admin()
    OR organization_id = current_tenant_id()
);

CREATE POLICY assessments_public_insert ON assessment_requests FOR INSERT
WITH CHECK (organization_id IS NULL);

-- ═══════════════════════════════════════════════════════════════════════════
-- 1.5 installers — same FOR ALL ... IS NULL defect; same fix
-- ═══════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS installers_policy ON installers;

CREATE POLICY installers_tenant_rw ON installers FOR ALL
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
)
WITH CHECK (
    is_super_admin()
    OR organization_id = current_tenant_id()
);

CREATE POLICY installers_public_insert ON installers FOR INSERT
WITH CHECK (organization_id IS NULL);

-- ═══════════════════════════════════════════════════════════════════════════
-- 1.6 uploaded_files — is_public must be SELECT-only, not FOR ALL
-- Old policy let any tenant UPDATE/DELETE another tenant's public file.
-- ═══════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS files_policy ON uploaded_files;

CREATE POLICY files_read ON uploaded_files FOR SELECT
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
    OR is_public = TRUE
);

CREATE POLICY files_write ON uploaded_files FOR ALL
USING (
    is_super_admin()
    OR organization_id = current_tenant_id()
)
WITH CHECK (
    is_super_admin()
    OR organization_id = current_tenant_id()
);

-- ═══════════════════════════════════════════════════════════════════════════
-- 1.7 users — block self-update of privileged columns
-- RLS policy stays (users may still UPDATE their own row), but column-level
-- GRANT restricts the app role to non-privileged columns only.
-- Privileged columns (role, is_admin, organization_id, status, mfa_secret,
-- plan) can only be changed via a SECURITY DEFINER function invoked by
-- admin endpoints — to be added in a later migration.
-- ═══════════════════════════════════════════════════════════════════════════

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'solarpro_app') THEN
        REVOKE UPDATE ON users FROM solarpro_app;
        GRANT  UPDATE (full_name, phone, avatar_url, timezone, email_verified, last_login, login_attempts)
               ON users TO solarpro_app;
    END IF;
END;
$$;

-- ═══════════════════════════════════════════════════════════════════════════
-- 1.8 audit_log — replace WITH CHECK (TRUE) with tenant-bound check
-- Old policy let the app role forge audit entries for any tenant. Real
-- super-admin bypass still possible via is_super_admin().
-- ═══════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS audit_insert ON audit_log;

CREATE POLICY audit_insert ON audit_log FOR INSERT
WITH CHECK (
    is_super_admin()
    OR (
        organization_id = current_tenant_id()
        AND user_id = current_user_id()
    )
);

\echo 'RLS hardening migration 003 complete.'
\echo 'Closed: FORCE-bypass · assessments PII leak · installers PII leak · uploaded_files writable-public · users self-priv-escalation · audit_log forgery.'
