-- SolarPro Global — PostgreSQL Schema
-- Migration: 001 - Initial schema with UUID PKs, human IDs, and tenant isolation
-- Target: Neon PostgreSQL (pooled connection)
-- Run: psql $DATABASE_URL -f 001_postgresql_schema.sql

-- ─── Extensions ────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── Sequences for human-readable IDs ──────────────────────────────────────
CREATE SEQUENCE IF NOT EXISTS user_seq START 1;
CREATE SEQUENCE IF NOT EXISTS org_seq START 1;
CREATE SEQUENCE IF NOT EXISTS project_seq START 1;
CREATE SEQUENCE IF NOT EXISTS opp_seq START 1;
CREATE SEQUENCE IF NOT EXISTS assessment_seq START 1;
CREATE SEQUENCE IF NOT EXISTS proposal_seq START 1;
CREATE SEQUENCE IF NOT EXISTS ticket_seq START 1;
CREATE SEQUENCE IF NOT EXISTS subscription_seq START 1;
CREATE SEQUENCE IF NOT EXISTS payment_seq START 1;
CREATE SEQUENCE IF NOT EXISTS installer_seq START 1;
CREATE SEQUENCE IF NOT EXISTS bid_seq START 1;

-- ─── Helper function for human-readable IDs ────────────────────────────────
CREATE OR REPLACE FUNCTION next_code(prefix TEXT, seq_name TEXT)
RETURNS TEXT LANGUAGE plpgsql AS $$
BEGIN
    RETURN prefix || LPAD(nextval(seq_name)::TEXT, 6, '0');
END;
$$;

-- ═══════════════════════════════════════════════════════════════════════════
-- TENANT / ORGANIZATION
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS organizations (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    organization_code   TEXT UNIQUE DEFAULT next_code('ORG-', 'org_seq'),
    name                TEXT NOT NULL,
    slug                TEXT UNIQUE,                  -- url-friendly name
    type                TEXT DEFAULT 'company'        -- company | individual | installer | consultant
                        CHECK (type IN ('company','individual','installer','consultant','supplier','epc')),
    country             TEXT,
    region              TEXT,
    phone               TEXT,
    website             TEXT,
    subscription_plan   TEXT DEFAULT 'free'
                        CHECK (subscription_plan IN ('free','starter','professional','business','enterprise')),
    subscription_status TEXT DEFAULT 'active'
                        CHECK (subscription_status IN ('active','trialing','expired','cancelled','suspended')),
    subscription_ends_at TIMESTAMPTZ,
    trial_ends_at       TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '14 days'),
    project_limit       INT DEFAULT 1,
    status              TEXT DEFAULT 'active'
                        CHECK (status IN ('active','suspended','deleted')),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_organizations_status ON organizations(status);

-- ═══════════════════════════════════════════════════════════════════════════
-- USERS
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS users (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_code           TEXT UNIQUE DEFAULT next_code('USR-', 'user_seq'),
    organization_id     UUID REFERENCES organizations(id) ON DELETE SET NULL,
    username            TEXT UNIQUE NOT NULL,
    email               TEXT UNIQUE NOT NULL,
    phone               TEXT,
    password_hash       TEXT NOT NULL,               -- bcrypt/argon2
    full_name           TEXT,
    role                TEXT DEFAULT 'customer'
                        CHECK (role IN ('super_admin','platform_admin','sales_manager',
                                        'engineer','proposal_officer','support_officer',
                                        'installer_user','consultant_user','supplier_user','customer')),
    is_admin            BOOLEAN DEFAULT FALSE,        -- platform super-admin flag
    plan                TEXT DEFAULT 'free',          -- kept for backwards compat
    status              TEXT DEFAULT 'active'
                        CHECK (status IN ('active','suspended','disabled','deleted')),
    email_verified      BOOLEAN DEFAULT FALSE,
    last_login          TIMESTAMPTZ,
    login_attempts      INT DEFAULT 0,
    locked_until        TIMESTAMPTZ,
    mfa_enabled         BOOLEAN DEFAULT FALSE,
    mfa_secret          TEXT,                         -- TOTP secret (encrypted)
    avatar_url          TEXT,
    timezone            TEXT DEFAULT 'UTC',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_users_org ON users(organization_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_status ON users(status);

-- ═══════════════════════════════════════════════════════════════════════════
-- SESSIONS (server-side session tracking)
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS user_sessions (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id     UUID REFERENCES organizations(id),
    session_token       TEXT UNIQUE NOT NULL,
    refresh_token       TEXT UNIQUE,
    device              TEXT,
    ip_address          TEXT,
    user_agent          TEXT,
    is_revoked          BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    expires_at          TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '8 hours'),
    last_activity       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_sessions_user ON user_sessions(user_id);
CREATE INDEX idx_sessions_token ON user_sessions(session_token);

-- ═══════════════════════════════════════════════════════════════════════════
-- PROJECTS (solar engineering)
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS projects (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    project_code        TEXT UNIQUE DEFAULT next_code('PRJ-', 'project_seq'),
    organization_id     UUID NOT NULL REFERENCES organizations(id),
    created_by_user_id  UUID NOT NULL REFERENCES users(id),
    name                TEXT NOT NULL,
    description         TEXT,
    country             TEXT,
    region              TEXT,
    site_address        TEXT,
    latitude            NUMERIC(10,6),
    longitude           NUMERIC(10,6),
    mounting_type       TEXT DEFAULT 'rooftop_pitched'
                        CHECK (mounting_type IN ('rooftop_pitched','rooftop_flat','rooftop_metal',
                                                  'rooftop_membrane','ground_fixed','ground_tracking')),
    system_type         TEXT DEFAULT 'hybrid',
    status              TEXT DEFAULT 'draft'
                        CHECK (status IN ('draft','in_progress','completed','archived')),
    data_json           TEXT,                         -- full engineering calculation blob
    psh                 NUMERIC(6,2),
    tariff_usd          NUMERIC(8,4),
    currency            TEXT DEFAULT 'USD',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_projects_org ON projects(organization_id);
CREATE INDEX idx_projects_user ON projects(created_by_user_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- LEADS / CRM
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS leads (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    organization_id     UUID NOT NULL REFERENCES organizations(id),
    created_by_user_id  UUID REFERENCES users(id),
    name                TEXT NOT NULL,
    email               TEXT,
    phone               TEXT,
    company             TEXT,
    country             TEXT,
    region              TEXT,
    source              TEXT,                         -- web | referral | agent | manual
    status              TEXT DEFAULT 'new'
                        CHECK (status IN ('new','contacted','qualified','proposal_sent',
                                          'negotiating','won','lost','dead')),
    urgency_score       INT CHECK (urgency_score BETWEEN 1 AND 10),
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_leads_org ON leads(organization_id);

-- ─── Assessment Requests ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS assessment_requests (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    assessment_code     TEXT UNIQUE DEFAULT next_code('ASM-', 'assessment_seq'),
    organization_id     UUID REFERENCES organizations(id),
    lead_id             UUID REFERENCES leads(id),
    name                TEXT NOT NULL,
    email               TEXT NOT NULL,
    phone               TEXT,
    country             TEXT,
    region              TEXT,
    system_type         TEXT,
    load_kwh            NUMERIC(8,2),
    budget_usd          NUMERIC(12,2),
    ai_score            INT,
    ai_analysis         TEXT,
    status              TEXT DEFAULT 'new',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ─── CRM Opportunities ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crm_opportunities (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    opp_code            TEXT UNIQUE DEFAULT next_code('OPP-', 'opp_seq'),
    organization_id     UUID NOT NULL REFERENCES organizations(id),
    created_by_user_id  UUID REFERENCES users(id),
    lead_id             UUID REFERENCES leads(id),
    project_id          UUID REFERENCES projects(id),
    title               TEXT NOT NULL,
    value_usd           NUMERIC(14,2),
    stage               TEXT DEFAULT 'prospect',
    probability         INT DEFAULT 20,
    close_date          DATE,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_opp_org ON crm_opportunities(organization_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- PROPOSALS
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS proposals (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    proposal_code       TEXT UNIQUE DEFAULT next_code('PRP-', 'proposal_seq'),
    organization_id     UUID NOT NULL REFERENCES organizations(id),
    created_by_user_id  UUID NOT NULL REFERENCES users(id),
    project_id          UUID NOT NULL REFERENCES projects(id),
    title               TEXT NOT NULL,
    client_name         TEXT,
    status              TEXT DEFAULT 'draft'
                        CHECK (status IN ('draft','sent','accepted','rejected','expired')),
    version             INT DEFAULT 1,
    valid_until         DATE,
    total_cost_usd      NUMERIC(14,2),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_proposals_org ON proposals(organization_id);
CREATE INDEX idx_proposals_project ON proposals(project_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- PROCUREMENT
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS installers (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    installer_code      TEXT UNIQUE DEFAULT next_code('INS-', 'installer_seq'),
    organization_id     UUID REFERENCES organizations(id),
    company_name        TEXT NOT NULL,
    contact_name        TEXT,
    email               TEXT NOT NULL,
    phone               TEXT,
    country             TEXT,
    region              TEXT,
    license_number      TEXT,
    verified            BOOLEAN DEFAULT FALSE,
    status              TEXT DEFAULT 'pending',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS procurement_packages (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    organization_id     UUID NOT NULL REFERENCES organizations(id),
    project_id          UUID REFERENCES projects(id),
    created_by_user_id  UUID REFERENCES users(id),
    title               TEXT NOT NULL,
    description         TEXT,
    status              TEXT DEFAULT 'open',
    deadline            TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_proc_org ON procurement_packages(organization_id);

CREATE TABLE IF NOT EXISTS bidder_submissions (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    bid_code            TEXT UNIQUE DEFAULT next_code('BID-', 'bid_seq'),
    organization_id     UUID NOT NULL REFERENCES organizations(id),
    package_id          UUID NOT NULL REFERENCES procurement_packages(id),
    installer_id        UUID REFERENCES installers(id),
    bid_amount_usd      NUMERIC(14,2),
    technical_score     INT,
    commercial_score    INT,
    ai_recommendation   TEXT,
    status              TEXT DEFAULT 'submitted',
    submitted_at        TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_bids_org ON bidder_submissions(organization_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- SUBSCRIPTIONS & PAYMENTS
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS subscriptions (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    subscription_code   TEXT UNIQUE DEFAULT next_code('SUB-', 'subscription_seq'),
    organization_id     UUID NOT NULL REFERENCES organizations(id),
    user_id             UUID REFERENCES users(id),
    plan                TEXT NOT NULL,
    status              TEXT DEFAULT 'active',
    amount_usd          NUMERIC(10,2),
    currency            TEXT DEFAULT 'USD',
    interval            TEXT DEFAULT 'monthly',
    provider            TEXT,                         -- paystack | stripe | code
    provider_sub_id     TEXT,
    starts_at           TIMESTAMPTZ DEFAULT NOW(),
    ends_at             TIMESTAMPTZ,
    trial_ends_at       TIMESTAMPTZ,
    cancelled_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_subs_org ON subscriptions(organization_id);

CREATE TABLE IF NOT EXISTS payments (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    payment_code        TEXT UNIQUE DEFAULT next_code('PAY-', 'payment_seq'),
    organization_id     UUID REFERENCES organizations(id),
    user_id             UUID REFERENCES users(id),
    subscription_id     UUID REFERENCES subscriptions(id),
    amount_usd          NUMERIC(10,2) NOT NULL,
    currency            TEXT DEFAULT 'USD',
    status              TEXT DEFAULT 'pending'
                        CHECK (status IN ('pending','success','failed','refunded')),
    provider            TEXT,
    provider_ref        TEXT UNIQUE,                  -- Paystack/Stripe reference
    webhook_verified    BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_payments_org ON payments(organization_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- SUPPORT TICKETS
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS tickets (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    ticket_code         TEXT UNIQUE DEFAULT next_code('TKT-', 'ticket_seq'),
    organization_id     UUID REFERENCES organizations(id),
    user_id             UUID REFERENCES users(id),
    subject             TEXT NOT NULL,
    body                TEXT,
    priority            TEXT DEFAULT 'medium'
                        CHECK (priority IN ('low','medium','high','urgent')),
    status              TEXT DEFAULT 'open'
                        CHECK (status IN ('open','in_progress','resolved','closed')),
    assigned_to         UUID REFERENCES users(id),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_tickets_org ON tickets(organization_id);

CREATE TABLE IF NOT EXISTS ticket_replies (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    ticket_id           UUID NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    organization_id     UUID REFERENCES organizations(id),
    user_id             UUID REFERENCES users(id),
    body                TEXT NOT NULL,
    is_staff_reply      BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════════
-- AUDIT LOGS
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS audit_log (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    organization_id     UUID REFERENCES organizations(id),
    user_id             UUID REFERENCES users(id),
    action              TEXT NOT NULL,
    resource_type       TEXT,
    resource_id         TEXT,
    ip_address          TEXT,
    user_agent          TEXT,
    status              TEXT DEFAULT 'success',
    metadata            JSONB,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_audit_org ON audit_log(organization_id);
CREATE INDEX idx_audit_user ON audit_log(user_id);
CREATE INDEX idx_audit_action ON audit_log(action);
CREATE INDEX idx_audit_created ON audit_log(created_at);

-- ═══════════════════════════════════════════════════════════════════════════
-- FILES / UPLOADED DOCUMENTS
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS uploaded_files (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    organization_id     UUID NOT NULL REFERENCES organizations(id),
    created_by_user_id  UUID REFERENCES users(id),
    project_id          UUID REFERENCES projects(id),
    filename            TEXT NOT NULL,
    storage_path        TEXT NOT NULL,               -- MinIO/S3 object key
    mime_type           TEXT,
    size_bytes          BIGINT,
    file_type           TEXT,                         -- proposal | boq | drawing | report
    is_public           BOOLEAN DEFAULT FALSE,
    download_token      TEXT UNIQUE,                  -- signed download link token
    expires_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_files_org ON uploaded_files(organization_id);
CREATE INDEX idx_files_project ON uploaded_files(project_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- NEWSLETTER / EMAIL
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS newsletter_subscribers (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    email               TEXT UNIQUE NOT NULL,
    name                TEXT,
    status              TEXT DEFAULT 'active',
    source              TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS email_logs (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    organization_id     UUID REFERENCES organizations(id),
    recipient           TEXT,
    subject             TEXT,
    provider            TEXT,
    status              TEXT DEFAULT 'sent',
    error_message       TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════════
-- EQUIPMENT CATALOG
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS equipment_catalog (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    category            TEXT NOT NULL,
    name                TEXT NOT NULL,
    brand               TEXT,
    model               TEXT,
    specs               JSONB,
    unit_price_usd      NUMERIC(10,2),
    currency            TEXT DEFAULT 'USD',
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Update timestamp trigger ───────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'organizations','users','projects','leads','assessment_requests',
        'crm_opportunities','proposals','installers','procurement_packages',
        'bidder_submissions','subscriptions','payments','tickets',
        'equipment_catalog'
    ] LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trg_%s_updated ON %I; '
            'CREATE TRIGGER trg_%s_updated BEFORE UPDATE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION update_updated_at()',
            t, t, t, t
        );
    END LOOP;
END;
$$;

\echo 'Schema migration 001 complete.'
