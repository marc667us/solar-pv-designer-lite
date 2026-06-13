-- 001_mirror_sqlite.sql
-- =====================================================================
-- Postgres schema that mirrors the 24 tables web_app.py:init_db() creates
-- on SQLite, with all the cumulative ALTER TABLE ADD COLUMN statements
-- baked into the CREATE statements.
--
-- Design choices:
--  * SERIAL PKs replace SQLite's INTEGER PRIMARY KEY AUTOINCREMENT.
--  * Boolean-ish columns (is_admin, is_active, is_published, is_new,
--    is_running, email_verified, used) stay INTEGER for byte compat
--    with the Python code (which writes 0/1, reads truthy).
--  * Timestamps stay TEXT (not TIMESTAMP) so application code that
--    reads/compares created_at as strings keeps working unchanged.
--    Default is now() formatted to SQLite's 'YYYY-MM-DD HH24:MI:SS'
--    layout so cross-engine comparisons stay lexicographically valid.
--  * data_json stays TEXT (not JSONB) — application code does its own
--    json.dumps/json.loads. JSONB would force psycopg to auto-parse.
--  * FOREIGN KEY constraints are declared. Postgres enforces them,
--    unlike SQLite default; init_db() seed order doesn't violate any.
--  * No RLS. No organizations table. No multi-tenant scoping. This is
--    a single-tenant app per memory project_solar_pv. Future RLS lives
--    in a separate hardening migration.
--
-- Safe to re-run: every CREATE TABLE uses IF NOT EXISTS; the DROP
-- prelude is guarded by IF EXISTS for the orphaned greenfield tables.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- Step 1: clean up orphaned tables from the archived greenfield
-- migrations (001..004 in migrations/archive/). They were applied to
-- solarpro-postgres in the prior session; they collide with this mirror
-- schema and the app cannot speak their schema. CASCADE because they
-- had FKs and RLS policies between them.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS bidder_submissions       CASCADE;
DROP TABLE IF EXISTS procurement_packages     CASCADE;
DROP TABLE IF EXISTS proposals                CASCADE;
DROP TABLE IF EXISTS crm_opportunities        CASCADE;
DROP TABLE IF EXISTS subscriptions            CASCADE;
DROP TABLE IF EXISTS uploaded_files           CASCADE;
DROP TABLE IF EXISTS user_sessions            CASCADE;
DROP TABLE IF EXISTS organizations            CASCADE;
DROP TABLE IF EXISTS audit_log                CASCADE;
-- Note: the greenfield migrations also created `users`, `projects`,
-- `tickets`, `ticket_replies`, `leads`, `assessment_requests`,
-- `installers`, `payments`, `newsletter_subscribers`, `email_logs`,
-- `equipment_catalog`. Those table names collide with the mirror
-- schema below. Drop them too — their column shapes are wrong for
-- the app.
DROP TABLE IF EXISTS payments                 CASCADE;
DROP TABLE IF EXISTS newsletter_subscribers   CASCADE;
DROP TABLE IF EXISTS email_logs               CASCADE;
DROP TABLE IF EXISTS equipment_catalog        CASCADE;
DROP TABLE IF EXISTS assessment_requests      CASCADE;
DROP TABLE IF EXISTS installers               CASCADE;
DROP TABLE IF EXISTS ticket_replies           CASCADE;
DROP TABLE IF EXISTS tickets                  CASCADE;
DROP TABLE IF EXISTS leads                    CASCADE;
DROP TABLE IF EXISTS projects                 CASCADE;
DROP TABLE IF EXISTS users                    CASCADE;
-- Drop the greenfield's helper function too (used by their UUID gen).
DROP FUNCTION IF EXISTS next_code(TEXT, TEXT) CASCADE;

-- Helper: SQLite-format timestamp string for column defaults. Replaces
-- SQLite's `TEXT DEFAULT CURRENT_TIMESTAMP` which would return a
-- timestamptz cast in Postgres rather than the YYYY-MM-DD HH:MM:SS form
-- the application code is written against.
CREATE OR REPLACE FUNCTION sqlite_ts() RETURNS TEXT AS $$
    SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
$$ LANGUAGE SQL VOLATILE;

-- ---------------------------------------------------------------------
-- Table 1 — users (with all cumulative ALTER columns baked in)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                 SERIAL PRIMARY KEY,
    username           TEXT UNIQUE NOT NULL,
    email              TEXT UNIQUE NOT NULL,
    password_hash      TEXT NOT NULL,
    name               TEXT DEFAULT '',
    company            TEXT DEFAULT '',
    country            TEXT DEFAULT '',
    plan               TEXT DEFAULT 'free',
    is_admin           INTEGER DEFAULT 0,
    created_at         TEXT DEFAULT sqlite_ts(),
    -- ALTER-added columns:
    stripe_customer_id TEXT DEFAULT '',
    subscription_end   TEXT DEFAULT '',
    role               TEXT DEFAULT 'customer',
    org_name           TEXT DEFAULT '',
    org_address        TEXT DEFAULT '',
    org_email          TEXT DEFAULT '',
    org_phone          TEXT DEFAULT '',
    org_website        TEXT DEFAULT '',
    timezone           TEXT DEFAULT 'UTC',
    org_whatsapp       TEXT DEFAULT '',
    date_format        TEXT DEFAULT 'DD/MM/YYYY',
    time_format        TEXT DEFAULT '24h',
    smtp_host          TEXT DEFAULT '',
    smtp_port          TEXT DEFAULT '587',
    smtp_user          TEXT DEFAULT '',
    smtp_pass          TEXT DEFAULT '',
    smtp_from          TEXT DEFAULT '',
    smtp_tls           TEXT DEFAULT 'starttls',
    resend_api_key     TEXT DEFAULT '',
    referral_code      TEXT,
    referred_by        INTEGER,
    email_verified     INTEGER DEFAULT 0,
    email_verify_token TEXT
);

-- ---------------------------------------------------------------------
-- Table 2 — referrals
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS referrals (
    id              SERIAL PRIMARY KEY,
    referrer_id     INTEGER NOT NULL,
    referee_id      INTEGER NOT NULL UNIQUE,
    signup_at       TEXT DEFAULT sqlite_ts(),
    upgraded_at     TEXT,
    plan_at_upgrade TEXT,
    reward_status   TEXT DEFAULT 'pending',
    FOREIGN KEY (referrer_id) REFERENCES users(id),
    FOREIGN KEY (referee_id)  REFERENCES users(id)
);

-- ---------------------------------------------------------------------
-- Table 3 — projects
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    name       TEXT NOT NULL,
    stage      TEXT DEFAULT 'new',
    folder     TEXT DEFAULT '',
    data_json  TEXT DEFAULT '{}',
    created_at TEXT DEFAULT sqlite_ts(),
    updated_at TEXT DEFAULT sqlite_ts(),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
-- ALTER for already-deployed Postgres instances where projects existed
-- before the folder column was introduced. ADD COLUMN IF NOT EXISTS is
-- Postgres 9.6+ and idempotent — re-applying this migration is safe.
ALTER TABLE projects ADD COLUMN IF NOT EXISTS folder TEXT DEFAULT '';

-- ---------------------------------------------------------------------
-- Table 4 — tickets
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tickets (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    subject    TEXT NOT NULL,
    message    TEXT NOT NULL,
    status     TEXT DEFAULT 'open',
    priority   TEXT DEFAULT 'normal',
    created_at TEXT DEFAULT sqlite_ts(),
    updated_at TEXT DEFAULT sqlite_ts(),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- ---------------------------------------------------------------------
-- Table 5 — ticket_replies
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ticket_replies (
    id         SERIAL PRIMARY KEY,
    ticket_id  INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    is_admin   INTEGER DEFAULT 0,
    message    TEXT NOT NULL,
    created_at TEXT DEFAULT sqlite_ts(),
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
);

-- ---------------------------------------------------------------------
-- Table 6 — appliances
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS appliances (
    id           SERIAL PRIMARY KEY,
    category     TEXT NOT NULL,
    name         TEXT NOT NULL,
    default_watt INTEGER NOT NULL,
    notes        TEXT DEFAULT ''
);

-- ---------------------------------------------------------------------
-- Table 7 — payments
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    gateway    TEXT NOT NULL DEFAULT 'manual',
    plan       TEXT NOT NULL DEFAULT 'free',
    amount_usd REAL DEFAULT 0,
    currency   TEXT DEFAULT 'USD',
    reference  TEXT DEFAULT '',
    status     TEXT DEFAULT 'success',
    created_at TEXT DEFAULT sqlite_ts(),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- ---------------------------------------------------------------------
-- Table 8 — leads (with all cumulative ALTER columns baked in)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS leads (
    id             SERIAL PRIMARY KEY,
    name           TEXT NOT NULL,
    email          TEXT NOT NULL,
    phone          TEXT DEFAULT '',
    company        TEXT DEFAULT '',
    country        TEXT DEFAULT '',
    interest       TEXT DEFAULT 'residential',
    message        TEXT DEFAULT '',
    source         TEXT DEFAULT 'website',
    status         TEXT DEFAULT 'new',
    notes          TEXT DEFAULT '',
    created_at     TEXT DEFAULT sqlite_ts(),
    -- ALTER-added columns:
    system_type    TEXT DEFAULT 'residential',
    system_size_kw REAL DEFAULT 0,
    budget_usd     TEXT DEFAULT '',
    ai_score       INTEGER DEFAULT 0,
    ai_grade       TEXT DEFAULT '',
    ai_notes       TEXT DEFAULT '',
    pipeline_stage TEXT DEFAULT 'new',
    follow_up_date TEXT DEFAULT ''
);

-- ---------------------------------------------------------------------
-- Table 9 — newsletter_subscribers
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS newsletter_subscribers (
    id         SERIAL PRIMARY KEY,
    email      TEXT UNIQUE NOT NULL,
    name       TEXT DEFAULT '',
    status     TEXT DEFAULT 'active',
    created_at TEXT DEFAULT sqlite_ts()
);

-- ---------------------------------------------------------------------
-- Table 10 — news_posts
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS news_posts (
    id           SERIAL PRIMARY KEY,
    title        TEXT NOT NULL,
    content      TEXT NOT NULL,
    category     TEXT DEFAULT 'industry',
    is_published INTEGER DEFAULT 1,
    created_at   TEXT DEFAULT sqlite_ts(),
    updated_at   TEXT DEFAULT sqlite_ts()
);

-- ---------------------------------------------------------------------
-- Table 11 — suppliers
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS suppliers (
    id             SERIAL PRIMARY KEY,
    name           TEXT NOT NULL,
    country        TEXT DEFAULT '',
    contact_name   TEXT DEFAULT '',
    phone          TEXT DEFAULT '',
    email          TEXT DEFAULT '',
    website        TEXT DEFAULT '',
    categories     TEXT DEFAULT '',
    lead_time_days INTEGER DEFAULT 30,
    payment_terms  TEXT DEFAULT 'TT 30 days',
    rating         INTEGER DEFAULT 5,
    notes          TEXT DEFAULT '',
    is_active      INTEGER DEFAULT 1,
    created_at     TEXT DEFAULT sqlite_ts()
);

-- ---------------------------------------------------------------------
-- Table 12 — equipment_catalog
-- (no FK on supplier_id: init_db's seed defaults to 0 when supplier
-- lookup misses, which would violate a real FK constraint)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS equipment_catalog (
    id             SERIAL PRIMARY KEY,
    category       TEXT NOT NULL,
    name           TEXT NOT NULL,
    brand          TEXT DEFAULT '',
    model          TEXT DEFAULT '',
    spec           TEXT DEFAULT '',
    unit           TEXT DEFAULT 'No.',
    price_usd      REAL DEFAULT 0,
    supplier_id    INTEGER DEFAULT 0,
    lead_time_days INTEGER DEFAULT 30,
    notes          TEXT DEFAULT '',
    is_active      INTEGER DEFAULT 1,
    created_at     TEXT DEFAULT sqlite_ts()
);

-- ---------------------------------------------------------------------
-- Table 13 — email_logs
-- (no FK on user_id/project_id — admin actions can log without a user)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS email_logs (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    project_id INTEGER DEFAULT 0,
    recipients TEXT DEFAULT '',
    subject    TEXT DEFAULT '',
    status     TEXT DEFAULT 'sent',
    error_msg  TEXT DEFAULT '',
    created_at TEXT DEFAULT sqlite_ts()
);

-- ---------------------------------------------------------------------
-- Table 14 — upgrade_codes
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS upgrade_codes (
    id            SERIAL PRIMARY KEY,
    code          TEXT UNIQUE NOT NULL,
    plan          TEXT NOT NULL DEFAULT 'professional',
    duration_days INTEGER DEFAULT 30,
    max_uses      INTEGER DEFAULT 1,
    uses          INTEGER DEFAULT 0,
    created_by    INTEGER DEFAULT 0,
    expires_at    TEXT DEFAULT '',
    created_at    TEXT DEFAULT sqlite_ts()
);

-- ---------------------------------------------------------------------
-- Table 15 — assessment_requests (with all cumulative ALTER columns)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS assessment_requests (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    email           TEXT NOT NULL,
    phone           TEXT DEFAULT '',
    company         TEXT DEFAULT '',
    country         TEXT DEFAULT '',
    system_type     TEXT DEFAULT 'off-grid',
    system_size_kw  REAL DEFAULT 0,
    budget_usd      TEXT DEFAULT '',
    location_desc   TEXT DEFAULT '',
    message         TEXT DEFAULT '',
    ai_score        INTEGER DEFAULT 0,
    ai_grade        TEXT DEFAULT '',
    ai_notes        TEXT DEFAULT '',
    pipeline_stage  TEXT DEFAULT 'assessment_submitted',
    assigned_to     TEXT DEFAULT '',
    follow_up_date  TEXT DEFAULT '',
    source          TEXT DEFAULT 'website',
    status          TEXT DEFAULT 'open',
    created_at      TEXT DEFAULT sqlite_ts(),
    updated_at      TEXT DEFAULT sqlite_ts(),
    -- ALTER-added columns:
    assessment_ref  TEXT DEFAULT '',
    building_desc   TEXT DEFAULT '',
    building_size   TEXT DEFAULT '',
    num_floors      INTEGER DEFAULT 0,
    building_type   TEXT DEFAULT '',
    region          TEXT DEFAULT ''
);

-- ---------------------------------------------------------------------
-- Table 16 — installers
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS installers (
    id             SERIAL PRIMARY KEY,
    company_name   TEXT NOT NULL,
    contact_name   TEXT NOT NULL,
    email          TEXT UNIQUE NOT NULL,
    phone          TEXT DEFAULT '',
    country        TEXT DEFAULT '',
    regions        TEXT DEFAULT '',
    years_exp      INTEGER DEFAULT 0,
    staff_count    INTEGER DEFAULT 0,
    certifications TEXT DEFAULT '',
    specialties    TEXT DEFAULT '',
    max_project_kw REAL DEFAULT 0,
    website        TEXT DEFAULT '',
    notes          TEXT DEFAULT '',
    status         TEXT DEFAULT 'pending',
    ai_grade       TEXT DEFAULT '',
    created_at     TEXT DEFAULT sqlite_ts()
);

-- ---------------------------------------------------------------------
-- Table 17 — monitor_alerts
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monitor_alerts (
    id          SERIAL PRIMARY KEY,
    url         TEXT UNIQUE NOT NULL,
    title       TEXT DEFAULT '',
    snippet     TEXT DEFAULT '',
    country     TEXT DEFAULT '',
    source_type TEXT DEFAULT '',
    is_new      INTEGER DEFAULT 1,
    found_at    TEXT DEFAULT sqlite_ts()
);

-- ---------------------------------------------------------------------
-- Table 18 — monitor_state (singleton row, id=1)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monitor_state (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    last_scan        TEXT DEFAULT '',
    last_count       INTEGER DEFAULT 0,
    is_running       INTEGER DEFAULT 0,
    scan_interval    INTEGER DEFAULT 120,
    notify_email     INTEGER DEFAULT 0,
    last_agent_run   TEXT DEFAULT '',
    agent_run_count  INTEGER DEFAULT 0
);
-- Seed the singleton row idempotently (Postgres ON CONFLICT,
-- replacing SQLite's `INSERT OR IGNORE`).
INSERT INTO monitor_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------
-- Table 19 — password_reset_tokens
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    token      TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    used       INTEGER DEFAULT 0,
    created_at TEXT DEFAULT sqlite_ts()
);

-- ---------------------------------------------------------------------
-- Table 20 — helpline_learned_kb
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS helpline_learned_kb (
    id         SERIAL PRIMARY KEY,
    agent      TEXT DEFAULT 'helpline',
    question   TEXT NOT NULL,
    answer     TEXT NOT NULL,
    use_count  INTEGER DEFAULT 0,
    created_at TEXT DEFAULT sqlite_ts()
);

-- ---------------------------------------------------------------------
-- Table 21 — beta_signups
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS beta_signups (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    email      TEXT UNIQUE NOT NULL,
    company    TEXT DEFAULT '',
    role       TEXT DEFAULT '',
    status     TEXT DEFAULT 'pending',
    invited_at TEXT DEFAULT '',
    notes      TEXT DEFAULT '',
    created_at TEXT DEFAULT sqlite_ts()
);

-- ---------------------------------------------------------------------
-- Table 22 — beta_feedback (with 3-axis rating columns added 2026-06-10)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS beta_feedback (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER DEFAULT NULL,
    username         TEXT DEFAULT '',
    email            TEXT DEFAULT '',
    type             TEXT DEFAULT 'general',
    message          TEXT NOT NULL,
    page             TEXT DEFAULT '',
    status           TEXT DEFAULT 'new',
    created_at       TEXT DEFAULT sqlite_ts(),
    -- Rating columns (1..5, NULL when the row is general feedback rather
    -- than a numeric rating). Server-side clamp at the /rate endpoint
    -- ensures values land in range.
    perf_score       INTEGER,
    creativity_score INTEGER,
    value_score      INTEGER
);

-- ---------------------------------------------------------------------
-- Table 23 — audit_logs (plural — matches both the INSERT writes at
-- web_app.py:1769/1780 AND the legacy SELECTs at 10202/10777 once
-- Session B renames those to plural)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER DEFAULT NULL,
    username   TEXT DEFAULT '',
    action     TEXT NOT NULL,
    ip_address TEXT DEFAULT '',
    details    TEXT DEFAULT '',
    created_at TEXT DEFAULT sqlite_ts()
);

-- ---------------------------------------------------------------------
-- Table 24 — login_failures
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS login_failures (
    id         SERIAL PRIMARY KEY,
    username   TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    created_at TEXT DEFAULT sqlite_ts()
);

COMMIT;

-- =====================================================================
-- Sanity: confirm we have all 24 tables. Run this manually after apply:
--   SELECT tablename FROM pg_tables WHERE schemaname='public'
--   ORDER BY tablename;
-- =====================================================================
