# Claude Code Implementation Handoff: Phase 1 Only

## Phase 1 Boundary

Implement only the Enterprise Programme Foundation vertical slice:

- Feature flag dark by default.
- Enterprise organisation bootstrap for current logged-in user.
- Programme registry.
- Programme detail dashboard.
- Programme phases.
- Manual beneficiary registry.
- Link existing user-owned standard projects and generation-station projects.
- Durable job table foundation, but no bulk project generation.
- RLS policies for new tables.
- Tests and live smoke verification.

Stop after Phase 1 and owner review. Do not implement Phase 2 generation, imports, procurement, contracts, AI, ESG, SCADA, or workflow engine.

## Non-Negotiable Constraints

- Do not edit `web_app.py`.
- Do not touch `templates/location.html`, the D3 globe, or `static/land-110m.json`.
- Do not create a second auth system.
- Do not duplicate BOQ, marketplace, funding, report, project, or AI engines.
- Everything additive.
- Feature flag dark by default.
- Use Render free-tier constraints.
- No synchronous bulk operations.
- Use raw SQL, not ORM.
- Prefer `INSERT ... RETURNING id` for new Postgres tables.
- Existing users/projects must continue working.

## Files To Add

- `enterprise_programme_routes.py`
- `enterprise_programme_repository.py`
- `enterprise_programme_services.py`
- `enterprise_programme_jobs.py`
- `migrations/024_enterprise_programme_foundation.sql`
- `templates/enterprise_programme/dashboard.html`
- `templates/enterprise_programme/programmes_list.html`
- `templates/enterprise_programme/programme_form.html`
- `templates/enterprise_programme/programme_detail.html`
- `templates/enterprise_programme/beneficiaries.html`
- `templates/enterprise_programme/beneficiary_form.html`
- `templates/enterprise_programme/phases.html`
- `templates/enterprise_programme/project_links.html`
- `tests/test_enterprise_programme_foundation.py`
- `tests/security/test_enterprise_programme_tenant_isolation.py`
- Optional: `.github/workflows/enterprise-job-tick.yml` only if owner approves a cron ticker in Phase 1.

## Files To Modify

- `wsgi.py`
  - Import and register the enterprise module after importing `web_app.app`.
  - Keep `boot_state.attach(app, init_db)`.
- `templates/base.html`
  - Add Enterprise link in logged-in nav/side menu only when `enterprise_programme_enabled` is true.
  - If passing flag to all templates is hard from a separate module, use a context processor registered by `enterprise_programme_routes.py`.
- `docs/ARCHITECTURE_DECISIONS.md`
  - Add ADR exemption: Enterprise Programme AI will use deterministic Python services plus optional existing `api_manager.py` gateway; no Google ADK/LangChain/CrewAI/AutoGen for this owner-approved module.
- `docs/IMPLEMENTATION_LOG.md`
  - Record Phase 1 implementation steps and validation.

## Feature Flag Keys

Use existing `admin_settings` table.

- `enterprise_programme_enabled`: default `0`
- `enterprise_programme_jobs_enabled`: default `0`
- `enterprise_programme_ai_enabled`: default `0`

Dark-by-default behavior:

- If `enterprise_programme_enabled != "1"`, `/enterprise*` returns 404 or a feature-disabled response for non-admin users.
- Nav link hidden.
- No background/tick processing.

## Route List

Use `register_enterprise_programme(app, *, get_db, login_required, csrf_protect, current_user)`.

Browser routes:

- `GET /enterprise`
  - Dashboard/bootstrap.
- `POST /enterprise/bootstrap`
  - Create organisation + owner membership for current user.
- `GET /enterprise/programmes`
  - Paginated registry.
- `GET /enterprise/programmes/new`
  - New programme form.
- `POST /enterprise/programmes/new`
  - Create programme.
- `GET /enterprise/programmes/<int:programme_id>`
  - Programme dashboard.
- `GET /enterprise/programmes/<int:programme_id>/edit`
  - Edit programme form.
- `POST /enterprise/programmes/<int:programme_id>/edit`
  - Update programme.
- `GET /enterprise/programmes/<int:programme_id>/phases`
  - Phase list.
- `POST /enterprise/programmes/<int:programme_id>/phases`
  - Add phase.
- `GET /enterprise/programmes/<int:programme_id>/beneficiaries`
  - Paginated beneficiaries.
- `GET /enterprise/programmes/<int:programme_id>/beneficiaries/new`
  - Beneficiary form.
- `POST /enterprise/programmes/<int:programme_id>/beneficiaries/new`
  - Create beneficiary.
- `POST /enterprise/programmes/<int:programme_id>/beneficiaries/<int:beneficiary_id>/status`
  - Approve/reject/archive.
- `GET /enterprise/programmes/<int:programme_id>/projects`
  - Existing project-link screen.
- `POST /enterprise/programmes/<int:programme_id>/projects/link`
  - Link one current-user-owned project.
- `POST /enterprise/programmes/<int:programme_id>/projects/<int:link_id>/unlink`
  - Remove link.

API/status routes:

- `GET /enterprise/jobs`
  - List current org jobs.
- `GET /enterprise/jobs/<int:job_id>`
  - Poll status.
- `POST /enterprise/jobs/tick`
  - Disabled unless `enterprise_programme_jobs_enabled=1`; service account/admin only.

## Migration

Create `migrations/024_enterprise_programme_foundation.sql`.

Order:

1. Helper functions if needed.
2. Organisation/membership tables.
3. Programme and phase tables.
4. Beneficiary table.
5. Project-link table.
6. Job table.
7. Audit table.
8. Indexes.
9. RLS enable + policies.
10. Feature flags seeded to `0`.

### DDL Sketch

Use Postgres-compatible DDL. If the app still supports SQLite locally, repository `_ensure_enterprise_schema()` may create SQLite-compatible equivalents for dev, but production migration is Postgres.

```sql
CREATE TABLE IF NOT EXISTS enterprise_organisations (
    id SERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    legal_name TEXT NOT NULL,
    organisation_type TEXT NOT NULL DEFAULT 'corporate_enterprise',
    country TEXT DEFAULT '',
    default_currency TEXT DEFAULT 'USD',
    timezone TEXT DEFAULT 'UTC',
    brand_json TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    created_by_user_id INTEGER NOT NULL,
    created_at TEXT DEFAULT sqlite_ts(),
    updated_at TEXT DEFAULT sqlite_ts()
);

CREATE TABLE IF NOT EXISTS enterprise_memberships (
    id SERIAL PRIMARY KEY,
    organisation_id INTEGER NOT NULL REFERENCES enterprise_organisations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    keycloak_sub TEXT DEFAULT '',
    role TEXT NOT NULL DEFAULT 'enterprise_owner',
    permissions_json TEXT DEFAULT '{}',
    region_scope_json TEXT DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    invited_by_user_id INTEGER,
    created_at TEXT DEFAULT sqlite_ts(),
    updated_at TEXT DEFAULT sqlite_ts(),
    UNIQUE(organisation_id, user_id)
);

CREATE TABLE IF NOT EXISTS enterprise_programmes (
    id SERIAL PRIMARY KEY,
    organisation_id INTEGER NOT NULL REFERENCES enterprise_organisations(id) ON DELETE CASCADE,
    programme_code TEXT NOT NULL,
    name TEXT NOT NULL,
    programme_type TEXT NOT NULL,
    description TEXT DEFAULT '',
    countries_json TEXT DEFAULT '[]',
    regions_json TEXT DEFAULT '[]',
    target_beneficiaries INTEGER DEFAULT 0,
    target_capacity_kwp REAL DEFAULT 0,
    target_battery_kwh REAL DEFAULT 0,
    budget_amount REAL DEFAULT 0,
    currency TEXT DEFAULT 'USD',
    delivery_model TEXT DEFAULT '',
    procurement_strategy TEXT DEFAULT '',
    design_strategy TEXT NOT NULL DEFAULT 'standard',
    status TEXT NOT NULL DEFAULT 'draft',
    created_by_user_id INTEGER NOT NULL,
    created_at TEXT DEFAULT sqlite_ts(),
    updated_at TEXT DEFAULT sqlite_ts(),
    UNIQUE(organisation_id, programme_code)
);

CREATE TABLE IF NOT EXISTS enterprise_programme_phases (
    id SERIAL PRIMARY KEY,
    organisation_id INTEGER NOT NULL REFERENCES enterprise_organisations(id) ON DELETE CASCADE,
    programme_id INTEGER NOT NULL REFERENCES enterprise_programmes(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    sequence_no INTEGER NOT NULL DEFAULT 1,
    start_date TEXT DEFAULT '',
    target_completion_date TEXT DEFAULT '',
    target_beneficiaries INTEGER DEFAULT 0,
    target_capacity_kwp REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'planned',
    created_at TEXT DEFAULT sqlite_ts(),
    updated_at TEXT DEFAULT sqlite_ts()
);

CREATE TABLE IF NOT EXISTS enterprise_beneficiaries (
    id SERIAL PRIMARY KEY,
    organisation_id INTEGER NOT NULL REFERENCES enterprise_organisations(id) ON DELETE CASCADE,
    programme_id INTEGER NOT NULL REFERENCES enterprise_programmes(id) ON DELETE CASCADE,
    phase_id INTEGER REFERENCES enterprise_programme_phases(id) ON DELETE SET NULL,
    beneficiary_type TEXT NOT NULL,
    name TEXT NOT NULL,
    region TEXT DEFAULT '',
    district TEXT DEFAULT '',
    community TEXT DEFAULT '',
    address TEXT DEFAULT '',
    latitude REAL,
    longitude REAL,
    contact_name TEXT DEFAULT '',
    contact_email TEXT DEFAULT '',
    contact_phone TEXT DEFAULT '',
    load_kwh_day REAL DEFAULT 0,
    target_capacity_kwp REAL DEFAULT 0,
    priority_score INTEGER DEFAULT 0,
    qualification_status TEXT NOT NULL DEFAULT 'draft',
    metadata_json TEXT DEFAULT '{}',
    created_by_user_id INTEGER NOT NULL,
    created_at TEXT DEFAULT sqlite_ts(),
    updated_at TEXT DEFAULT sqlite_ts()
);

CREATE TABLE IF NOT EXISTS enterprise_programme_project_links (
    id SERIAL PRIMARY KEY,
    organisation_id INTEGER NOT NULL REFERENCES enterprise_organisations(id) ON DELETE CASCADE,
    programme_id INTEGER NOT NULL REFERENCES enterprise_programmes(id) ON DELETE CASCADE,
    beneficiary_id INTEGER REFERENCES enterprise_beneficiaries(id) ON DELETE SET NULL,
    project_kind TEXT NOT NULL CHECK (project_kind IN ('standard','generation_station')),
    project_id INTEGER NOT NULL,
    source_user_id INTEGER NOT NULL REFERENCES users(id),
    linked_by_user_id INTEGER NOT NULL REFERENCES users(id),
    design_strategy TEXT NOT NULL DEFAULT 'standard',
    status TEXT NOT NULL DEFAULT 'linked',
    linked_at TEXT DEFAULT sqlite_ts(),
    UNIQUE(programme_id, project_kind, project_id)
);

CREATE TABLE IF NOT EXISTS enterprise_programme_jobs (
    id SERIAL PRIMARY KEY,
    organisation_id INTEGER NOT NULL REFERENCES enterprise_organisations(id) ON DELETE CASCADE,
    programme_id INTEGER REFERENCES enterprise_programmes(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    idempotency_key TEXT NOT NULL,
    payload_json TEXT DEFAULT '{}',
    cursor_json TEXT DEFAULT '{}',
    progress_current INTEGER DEFAULT 0,
    progress_total INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    locked_by TEXT DEFAULT '',
    locked_until TEXT DEFAULT '',
    last_error TEXT DEFAULT '',
    created_by_user_id INTEGER NOT NULL,
    created_at TEXT DEFAULT sqlite_ts(),
    updated_at TEXT DEFAULT sqlite_ts(),
    UNIQUE(organisation_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS enterprise_programme_audit (
    id SERIAL PRIMARY KEY,
    organisation_id INTEGER NOT NULL REFERENCES enterprise_organisations(id) ON DELETE CASCADE,
    programme_id INTEGER,
    actor_user_id INTEGER,
    action TEXT NOT NULL,
    target_kind TEXT DEFAULT '',
    target_id INTEGER,
    details TEXT DEFAULT '',
    created_at TEXT DEFAULT sqlite_ts()
);
```

Indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_ep_members_user ON enterprise_memberships(user_id, status);
CREATE INDEX IF NOT EXISTS idx_ep_programmes_org_status ON enterprise_programmes(organisation_id, status, updated_at);
CREATE INDEX IF NOT EXISTS idx_ep_phases_programme ON enterprise_programme_phases(programme_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_ep_beneficiaries_programme ON enterprise_beneficiaries(programme_id, qualification_status, id);
CREATE INDEX IF NOT EXISTS idx_ep_links_programme ON enterprise_programme_project_links(programme_id, project_kind);
CREATE INDEX IF NOT EXISTS idx_ep_jobs_claim ON enterprise_programme_jobs(status, locked_until, id);
CREATE INDEX IF NOT EXISTS idx_ep_audit_org_recent ON enterprise_programme_audit(organisation_id, created_at);
```

RLS policy pattern:

```sql
ALTER TABLE enterprise_organisations ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_programmes ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_programme_phases ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_beneficiaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_programme_project_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_programme_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_programme_audit ENABLE ROW LEVEL SECURITY;

CREATE POLICY enterprise_organisations_member_access
ON enterprise_organisations
USING (
    current_user_is_admin()
    OR EXISTS (
        SELECT 1 FROM enterprise_memberships m
        WHERE m.organisation_id = enterprise_organisations.id
          AND m.status = 'active'
          AND (
              m.keycloak_sub = current_user_sub()
              OR m.user_id::text = current_user_sub()
          )
    )
);

-- Repeat child policies by joining to enterprise_memberships through organisation_id.
```

Important: because current Keycloak `sub` is not the integer `users.id`, repository code must also enforce membership by current session user id from `current_user()`. RLS is defence-in-depth until the user/sub mapping is complete.

Seed flags:

```sql
INSERT INTO admin_settings (key, value, updated_at)
VALUES
('enterprise_programme_enabled','0',CURRENT_TIMESTAMP),
('enterprise_programme_jobs_enabled','0',CURRENT_TIMESTAMP),
('enterprise_programme_ai_enabled','0',CURRENT_TIMESTAMP)
ON CONFLICT (key) DO NOTHING;
```

If `admin_settings.key` lacks a unique constraint on current DB, use the existing upsert pattern from `new_marketplace_pagination.py`.

## Repository/Service Rules

Repository functions must always accept `organisation_id` and current `user_id`.

Required checks:

- `get_active_membership(user_id)` returns membership or none.
- Programme fetch must join/filter by membership organisation.
- Beneficiary fetch must filter by programme and organisation.
- Project link validation:
  - For `standard`: query `projects WHERE id=? AND user_id=?`.
  - For `generation_station`: query `capital_investment_projects WHERE id=? AND user_id=?`.
- Never expose arbitrary project IDs through enterprise routes.

## Exact Implementation Sequence

1. Re-read `CLAUDE.md`, `context.MD`, `wsgi.py`, `templates/base.html`, `app/security/*`, and migration 003/020.
2. Create migration `024_enterprise_programme_foundation.sql`.
3. Create repository module with schema helpers and query functions.
4. Create service module with validation, dashboard rollups, programme code generation, and audit calls.
5. Create route registration module with feature-flag check.
6. Register from `wsgi.py`.
7. Add templates.
8. Add dark-flagged nav/context processor.
9. Add tests for feature flag, bootstrap, CRUD, project-link authorization, and non-member denial.
10. Add RLS tests or SQL verification tests using existing security test patterns.
11. Update ADR and implementation log.
12. Run targeted tests.
13. Run broader smoke tests.
14. Deploy via existing Render workflow after owner/developer approval process.
15. Live smoke Phase 1 only.
16. Stop for owner review.

## Test Commands

Targeted:

```bash
python -m pytest tests/test_enterprise_programme_foundation.py -q
python -m pytest tests/security/test_enterprise_programme_tenant_isolation.py -q
```

Regression around reused systems:

```bash
python -m pytest tests/security/test_decorators.py tests/security/test_tenant_isolation.py -q
python -m pytest test_marketplace_bom.py test_marketplace_rfq.py test_funding_module.py -q
python -m pytest tests/test_app.py tests/test_csrf.py -q
```

Static/security where available:

```bash
python -m compileall enterprise_programme_routes.py enterprise_programme_repository.py enterprise_programme_services.py enterprise_programme_jobs.py
python -m pip check
```

Existing quality gate if present and usable:

```bash
./scripts/quality-gate.sh
```

## Deployment Commands

Use existing deployment method documented in `CLAUDE.md` and workflows:

```bash
git status
git add enterprise_programme_routes.py enterprise_programme_repository.py enterprise_programme_services.py enterprise_programme_jobs.py migrations/024_enterprise_programme_foundation.sql templates/enterprise_programme tests docs wsgi.py templates/base.html
git commit -m "feat(enterprise): add programme foundation behind flag"
git push origin master
gh workflow run "Force Render Deploy"
```

Migration application should follow the repo’s gated migration workflow pattern. If no generic migration workflow exists for 024, create/apply a dedicated safe workflow or run through the established Render Postgres migration process used by prior `apply-migration-*` workflows.

## Rollback Commands

Fast rollback:

```sql
UPDATE admin_settings SET value='0', updated_at=CURRENT_TIMESTAMP
WHERE key='enterprise_programme_enabled';
UPDATE admin_settings SET value='0', updated_at=CURRENT_TIMESTAMP
WHERE key='enterprise_programme_jobs_enabled';
```

Application rollback:

```bash
git revert <enterprise_phase1_commit>
git push origin master
gh workflow run "Force Render Deploy"
```

Database rollback guidance:

- Prefer feature-flag disable over dropping tables.
- Do not drop enterprise tables unless owner confirms no Phase 1 data must be retained.
- If necessary, create a numbered rollback migration that:
  - disables enterprise flags,
  - revokes route use,
  - leaves tables in place for forensic/export purposes.

## Live Acceptance Test

1. Confirm `/api/ping` returns healthy.
2. Confirm `/enterprise` is hidden/disabled while `enterprise_programme_enabled=0`.
3. Enable flag in `admin_settings`.
4. Login through Keycloak as an existing user.
5. Visit `/enterprise`.
6. Bootstrap enterprise organisation.
7. Create programme:
   - Name: Ghana National Secondary School Solar Independence Programme
   - Type: school
   - Target beneficiaries: 420
   - Target capacity: 250000 kWp
   - Currency: GHS
8. Add phases:
   - Phase 1 Greater Accra Pilot
   - Phase 2 Regional Rollout
   - Phase 3 National Completion
9. Add three beneficiaries.
10. Link one existing owned project.
11. Confirm dashboard counts:
   - programmes >= 1
   - phases = 3
   - beneficiaries = 3
   - linked projects = 1
12. Confirm linked project drill-down opens existing SolarPro route.
13. Login as another non-member user or simulate non-member in test; direct URL must deny.
14. Disable flag and confirm nav/route are hidden again.

## Definition Of Done

- `web_app.py` unchanged.
- New enterprise routes registered from `wsgi.py`.
- Feature flag dark by default.
- Phase 1 workflow works end-to-end on live site after enabling flag.
- Existing standard project, generation station, marketplace, funding, and BOQ tests still pass.
- New migration is additive and idempotent.
- New enterprise tables have RLS policies.
- App-layer membership checks are present on every enterprise route.
- Project linking cannot link another user’s project.
- Audit events written for bootstrap, programme create/update, beneficiary create/status, project link/unlink.
- No synchronous bulk operation implemented.
- Owner review stop point reached after Phase 1.

## Unresolved Risks

- Keycloak `tenant_id` claim may still be absent. Mitigation: membership checks by session user id in application code.
- `wsgi.py` registration means `python web_app.py` local dev path will not include enterprise routes. Acceptable for Phase 1 live verification; document it.
- RLS policies depending on `current_user_sub()` need confirmed mapping between Keycloak sub and `users.id`. Do not rely on RLS alone.
- `admin_settings` uniqueness may vary; use existing helper/upsert pattern.
- Render free tier may sleep; job ticker must tolerate missed intervals.
