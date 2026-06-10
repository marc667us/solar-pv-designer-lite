-- SolarPro Global — Schema hardening
-- Migration: 004 - Schema fixes identified in 2026-06-06 quality-gate review
-- Run AFTER 001, 002, 003.
--
-- Addresses work-schedule items 1.9 (tenant-aware composite FKs),
-- 1.10 (NOT NULL organization_id), 1.11 (composite tenant+status indexes),
-- 1.12 (missing tenant+FK indexes), 1.13 (domain CHECK constraints),
-- 1.14 (created_by_user_id + updated_at audit columns),
-- 1.15 (workload composite indexes).
--
-- Source: C:\Users\USER\Desktop\SolarPro_QualityGate_WorkSchedule_2026-06-06.md

-- ═══════════════════════════════════════════════════════════════════════════
-- 1.10 NOT NULL on organization_id where tenants must always be set
-- Null org_id rows are unreachable through normal RLS → orphan data
-- ═══════════════════════════════════════════════════════════════════════════

-- Existing rows with NULL must be quarantined or assigned to a system tenant
-- before this migration runs. Wrap in a DO block to fail loudly otherwise.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM user_sessions WHERE organization_id IS NULL) THEN
        RAISE EXCEPTION 'Cannot set NOT NULL: user_sessions has NULL organization_id rows';
    END IF;
    IF EXISTS (SELECT 1 FROM payments WHERE organization_id IS NULL) THEN
        RAISE EXCEPTION 'Cannot set NOT NULL: payments has NULL organization_id rows';
    END IF;
    IF EXISTS (SELECT 1 FROM tickets WHERE organization_id IS NULL) THEN
        RAISE EXCEPTION 'Cannot set NOT NULL: tickets has NULL organization_id rows';
    END IF;
    IF EXISTS (SELECT 1 FROM ticket_replies WHERE organization_id IS NULL) THEN
        RAISE EXCEPTION 'Cannot set NOT NULL: ticket_replies has NULL organization_id rows';
    END IF;
    IF EXISTS (SELECT 1 FROM audit_log WHERE organization_id IS NULL) THEN
        RAISE EXCEPTION 'Cannot set NOT NULL: audit_log has NULL organization_id rows';
    END IF;
    IF EXISTS (SELECT 1 FROM email_logs WHERE organization_id IS NULL) THEN
        RAISE EXCEPTION 'Cannot set NOT NULL: email_logs has NULL organization_id rows';
    END IF;
END;
$$;

ALTER TABLE user_sessions  ALTER COLUMN organization_id SET NOT NULL;
ALTER TABLE payments       ALTER COLUMN organization_id SET NOT NULL;
ALTER TABLE tickets        ALTER COLUMN organization_id SET NOT NULL;
ALTER TABLE ticket_replies ALTER COLUMN organization_id SET NOT NULL;
ALTER TABLE audit_log      ALTER COLUMN organization_id SET NOT NULL;
ALTER TABLE email_logs     ALTER COLUMN organization_id SET NOT NULL;

-- assessment_requests + installers keep organization_id nullable for public
-- submissions but those rows are only writable via the public-INSERT RLS
-- policies added in migration 003.

-- ═══════════════════════════════════════════════════════════════════════════
-- 1.14 Audit columns (created_by_user_id + updated_at) on remaining tables
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE ticket_replies
    ADD COLUMN IF NOT EXISTS created_by_user_id UUID REFERENCES users(id),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

ALTER TABLE email_logs
    ADD COLUMN IF NOT EXISTS created_by_user_id UUID REFERENCES users(id),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- Tighten projects.created_at + updated_at NOT NULL (already DEFAULT NOW but
-- nothing prevents an explicit NULL insert today).
ALTER TABLE projects
    ALTER COLUMN created_at SET NOT NULL,
    ALTER COLUMN updated_at SET NOT NULL;

-- Same for the audit_log + email_logs base columns
ALTER TABLE audit_log
    ALTER COLUMN created_at SET NOT NULL;

-- updated_at trigger for ticket_replies + email_logs (they now have the col)
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['ticket_replies','email_logs'] LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trg_%s_updated ON %I; '
            'CREATE TRIGGER trg_%s_updated BEFORE UPDATE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION update_updated_at()',
            t, t, t, t
        );
    END LOOP;
END;
$$;

-- ═══════════════════════════════════════════════════════════════════════════
-- 1.9 Tenant-aware composite foreign keys
-- Existing FKs reference only parent.id, letting a child row carry tenant A
-- while parent belongs to tenant B. Add UNIQUE(id, org_id) on parents, then
-- composite FK from children.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE projects ADD CONSTRAINT projects_id_org_uk UNIQUE (id, organization_id);
ALTER TABLE users    ADD CONSTRAINT users_id_org_uk    UNIQUE (id, organization_id);

-- proposals → projects + creator
ALTER TABLE proposals
    DROP CONSTRAINT IF EXISTS proposals_project_id_fkey,
    DROP CONSTRAINT IF EXISTS proposals_created_by_user_id_fkey,
    ADD  CONSTRAINT proposals_project_tenant_fk
         FOREIGN KEY (project_id, organization_id)
         REFERENCES projects(id, organization_id),
    ADD  CONSTRAINT proposals_creator_tenant_fk
         FOREIGN KEY (created_by_user_id, organization_id)
         REFERENCES users(id, organization_id);

-- crm_opportunities → leads(optional) + projects(optional) + creator
ALTER TABLE crm_opportunities
    DROP CONSTRAINT IF EXISTS crm_opportunities_project_id_fkey,
    DROP CONSTRAINT IF EXISTS crm_opportunities_created_by_user_id_fkey,
    ADD  CONSTRAINT opp_project_tenant_fk
         FOREIGN KEY (project_id, organization_id)
         REFERENCES projects(id, organization_id),
    ADD  CONSTRAINT opp_creator_tenant_fk
         FOREIGN KEY (created_by_user_id, organization_id)
         REFERENCES users(id, organization_id);

-- procurement_packages → projects + creator
ALTER TABLE procurement_packages
    DROP CONSTRAINT IF EXISTS procurement_packages_project_id_fkey,
    DROP CONSTRAINT IF EXISTS procurement_packages_created_by_user_id_fkey,
    ADD  CONSTRAINT pkg_project_tenant_fk
         FOREIGN KEY (project_id, organization_id)
         REFERENCES projects(id, organization_id),
    ADD  CONSTRAINT pkg_creator_tenant_fk
         FOREIGN KEY (created_by_user_id, organization_id)
         REFERENCES users(id, organization_id);

-- bidder_submissions → procurement_packages composite
ALTER TABLE procurement_packages ADD CONSTRAINT pkg_id_org_uk UNIQUE (id, organization_id);
ALTER TABLE bidder_submissions
    DROP CONSTRAINT IF EXISTS bidder_submissions_package_id_fkey,
    ADD  CONSTRAINT bid_pkg_tenant_fk
         FOREIGN KEY (package_id, organization_id)
         REFERENCES procurement_packages(id, organization_id);

-- subscriptions → users
ALTER TABLE subscriptions
    DROP CONSTRAINT IF EXISTS subscriptions_user_id_fkey,
    ADD  CONSTRAINT sub_user_tenant_fk
         FOREIGN KEY (user_id, organization_id)
         REFERENCES users(id, organization_id);

-- payments → users + subscriptions
ALTER TABLE subscriptions ADD CONSTRAINT sub_id_org_uk UNIQUE (id, organization_id);
ALTER TABLE payments
    DROP CONSTRAINT IF EXISTS payments_user_id_fkey,
    DROP CONSTRAINT IF EXISTS payments_subscription_id_fkey,
    ADD  CONSTRAINT pay_user_tenant_fk
         FOREIGN KEY (user_id, organization_id)
         REFERENCES users(id, organization_id),
    ADD  CONSTRAINT pay_sub_tenant_fk
         FOREIGN KEY (subscription_id, organization_id)
         REFERENCES subscriptions(id, organization_id);

-- tickets → user + assignee
ALTER TABLE tickets
    DROP CONSTRAINT IF EXISTS tickets_user_id_fkey,
    DROP CONSTRAINT IF EXISTS tickets_assigned_to_fkey,
    ADD  CONSTRAINT tkt_user_tenant_fk
         FOREIGN KEY (user_id, organization_id)
         REFERENCES users(id, organization_id),
    ADD  CONSTRAINT tkt_assignee_tenant_fk
         FOREIGN KEY (assigned_to, organization_id)
         REFERENCES users(id, organization_id);

-- ticket_replies → tickets + user
ALTER TABLE tickets ADD CONSTRAINT tickets_id_org_uk UNIQUE (id, organization_id);
ALTER TABLE ticket_replies
    DROP CONSTRAINT IF EXISTS ticket_replies_ticket_id_fkey,
    DROP CONSTRAINT IF EXISTS ticket_replies_user_id_fkey,
    ADD  CONSTRAINT reply_ticket_tenant_fk
         FOREIGN KEY (ticket_id, organization_id)
         REFERENCES tickets(id, organization_id) ON DELETE CASCADE,
    ADD  CONSTRAINT reply_user_tenant_fk
         FOREIGN KEY (user_id, organization_id)
         REFERENCES users(id, organization_id);

-- uploaded_files → projects + creator
ALTER TABLE uploaded_files
    DROP CONSTRAINT IF EXISTS uploaded_files_project_id_fkey,
    DROP CONSTRAINT IF EXISTS uploaded_files_created_by_user_id_fkey,
    ADD  CONSTRAINT file_project_tenant_fk
         FOREIGN KEY (project_id, organization_id)
         REFERENCES projects(id, organization_id),
    ADD  CONSTRAINT file_creator_tenant_fk
         FOREIGN KEY (created_by_user_id, organization_id)
         REFERENCES users(id, organization_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- 1.13 Domain CHECK constraints
-- DB-level guards against bad-status / negative-money / probability>100 bugs
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE crm_opportunities
    ADD CONSTRAINT opp_prob_range_ck      CHECK (probability BETWEEN 0 AND 100),
    ADD CONSTRAINT opp_value_nonneg_ck    CHECK (value_usd IS NULL OR value_usd >= 0),
    ADD CONSTRAINT opp_stage_enum_ck      CHECK (stage IN ('prospect','qualified','proposal','negotiation','won','lost'));

ALTER TABLE bidder_submissions
    ADD CONSTRAINT bid_amount_nonneg_ck   CHECK (bid_amount_usd IS NULL OR bid_amount_usd >= 0),
    ADD CONSTRAINT bid_tech_range_ck      CHECK (technical_score IS NULL OR technical_score BETWEEN 0 AND 100),
    ADD CONSTRAINT bid_comm_range_ck      CHECK (commercial_score IS NULL OR commercial_score BETWEEN 0 AND 100),
    ADD CONSTRAINT bid_status_enum_ck     CHECK (status IN ('submitted','reviewing','shortlisted','awarded','rejected'));

ALTER TABLE subscriptions
    ADD CONSTRAINT sub_amount_nonneg_ck   CHECK (amount_usd IS NULL OR amount_usd >= 0),
    ADD CONSTRAINT sub_interval_enum_ck   CHECK (interval IN ('monthly','quarterly','yearly')),
    ADD CONSTRAINT sub_status_enum_ck     CHECK (status IN ('active','trialing','past_due','cancelled','expired'));

ALTER TABLE payments
    ADD CONSTRAINT pay_amount_nonneg_ck   CHECK (amount_usd >= 0);

ALTER TABLE assessment_requests
    ADD CONSTRAINT asm_load_nonneg_ck     CHECK (load_kwh IS NULL OR load_kwh >= 0),
    ADD CONSTRAINT asm_budget_nonneg_ck   CHECK (budget_usd IS NULL OR budget_usd >= 0),
    ADD CONSTRAINT asm_status_enum_ck     CHECK (status IN ('new','reviewing','contacted','quoted','closed'));

ALTER TABLE installers
    ADD CONSTRAINT ins_status_enum_ck     CHECK (status IN ('pending','approved','suspended','rejected'));

ALTER TABLE procurement_packages
    ADD CONSTRAINT pkg_status_enum_ck     CHECK (status IN ('open','reviewing','awarded','closed','cancelled'));

ALTER TABLE audit_log
    ADD CONSTRAINT audit_status_enum_ck   CHECK (status IN ('success','failure','denied','error'));

ALTER TABLE email_logs
    ADD CONSTRAINT email_status_enum_ck   CHECK (status IN ('sent','queued','failed','bounced','spam'));

-- ═══════════════════════════════════════════════════════════════════════════
-- 1.11 Composite tenant + status indexes — dashboard/workflow queries
-- ═══════════════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_projects_org_status ON projects(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_leads_org_status    ON leads(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_proposals_org_status ON proposals(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_packages_org_status ON procurement_packages(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_bids_org_status     ON bidder_submissions(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_subs_org_status     ON subscriptions(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_payments_org_status ON payments(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_tickets_org_status  ON tickets(organization_id, status);

-- ═══════════════════════════════════════════════════════════════════════════
-- 1.12 Missing tenant + FK indexes — admin views + RLS lookups
-- ═══════════════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_assessments_org       ON assessment_requests(organization_id);
CREATE INDEX IF NOT EXISTS idx_installers_org        ON installers(organization_id);
CREATE INDEX IF NOT EXISTS idx_replies_org_ticket    ON ticket_replies(organization_id, ticket_id);
CREATE INDEX IF NOT EXISTS idx_email_logs_org_created ON email_logs(organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_org_revoked  ON user_sessions(organization_id, is_revoked);
CREATE INDEX IF NOT EXISTS idx_bids_package          ON bidder_submissions(package_id);
CREATE INDEX IF NOT EXISTS idx_payments_subscription ON payments(subscription_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- 1.15 Workload composite indexes — recency-sorted tenant queries
-- ═══════════════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_projects_org_status_created
    ON projects(organization_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_org_updated
    ON projects(organization_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_proposals_org_project
    ON proposals(organization_id, project_id);
CREATE INDEX IF NOT EXISTS idx_files_org_project
    ON uploaded_files(organization_id, project_id);
CREATE INDEX IF NOT EXISTS idx_leads_org_updated
    ON leads(organization_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_opp_org_stage_close
    ON crm_opportunities(organization_id, stage, close_date);
CREATE INDEX IF NOT EXISTS idx_audit_org_created
    ON audit_log(organization_id, created_at DESC);

\echo 'Schema hardening migration 004 complete.'
\echo 'Validate with EXPLAIN ANALYZE against representative tenant-filtered queries.'
