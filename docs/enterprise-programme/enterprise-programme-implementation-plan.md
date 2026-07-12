# Enterprise Programme Implementation Plan

## Executive Summary

SolarPro can support an Enterprise Solar Programme Management Module, but only if the implementation is staged around two hard facts found in the repository:

1. SolarPro is currently single-user-owned. Existing projects are owned by `projects.user_id` and protected in code by `WHERE id=? AND user_id=?`, for example `web_app.py:1043` `get_project(pid)` and `new_capital_investment_routes.py:6320` `_load_project(pid)`. The current RLS tenant is not an organisation; `migrations/003_rls_tenant.sql:122-137` derives `tenant_id` from `md5('solarpro-tenant-v1:' || user_id)`. `migrations/001_mirror_sqlite.sql:44` explicitly drops `organizations`. Enterprise tenancy therefore requires a new organisation/membership bridge without breaking existing personal ownership.

2. There is no production background worker. Celery exists under `tasks/`, but production is `Procfile:1` with a single web dyno/process: `gunicorn wsgi:app --workers 1 --timeout 300`. Docker Compose has Celery worker/beat, but Render production does not. File B forbids synchronous bulk generation. The module needs a durable database-backed job table and chunked processing driven by UI polling and/or GitHub Actions cron.

Phase 1 must be a small but useful vertical slice: enterprise organisation bootstrap, programme registry, phases, beneficiary registry, dashboard KPIs, project linking to existing user-owned projects, audit, RLS, and dark feature flag. No bulk project generation in Phase 1. No edits to `web_app.py`.

## Current-State Architecture Found In Code

### Application Shape

- Flask monolith: `web_app.py`.
- Render/Gunicorn entrypoint: `wsgi.py`.
- Production start command: `Procfile:1`, one worker, 300s timeout.
- Raw SQL with SQLite `?` placeholders translated to Postgres by `db_adapter.py`.
- `db_adapter.py:142` `_PgCursorWrap` emulates `lastrowid` via `SELECT lastval()`, but this is fragile; new tables must use `INSERT ... RETURNING id` on Postgres where possible.

### Registration Patterns

Two route extension patterns exist:

- Byte-splice into `web_app.py` via many `patch_*.py` scripts. This is explicitly risky because `CLAUDE.md` warns never to edit `web_app.py` directly.
- Clean dependency-injected registration. `web_app.py:44` imports `register_capital_investment`; `web_app.py:1034` calls `register_capital_investment(app, get_db=get_db, login_required=..., csrf_protect=..., current_user=...)`. This is the pattern to reuse.

Because File B and the owner forbid editing `web_app.py`, Phase 1 should register the enterprise module from `wsgi.py` after importing `web_app.app`. This preserves production behavior and avoids corrupting the monolith. Local `python web_app.py` will not include the module unless Claude later adds an equivalent safe import path outside `web_app.py`; for live verification, Render uses `wsgi:app`.

### Authentication And Authorization

- Keycloak OIDC is active. `app/auth/oidc_routes.py:86` defines `oidc_bp`; `app/auth/oidc_routes.py:632` registers it.
- Role constants live in `app/security/roles.py`; `ALL_ROLES` currently contains 20 roles.
- Decorators exist in `app/security/decorators.py`: `require_jwt`, `require_role`, `require_any_role`, `require_scope`, `require_tenant_match`, `require_service_account`.
- Tenant GUC bridge exists in `app/security/tenant_context.py`; `apply_tenant_guc(conn)` writes `app.current_tenant`, `app.current_user`, and `app.current_role`.
- `web_app.py:383` `get_db()` calls `db_adapter.open_postgres()` when `DATABASE_URL` is set and applies `_kc_apply_tenant_guc(conn)` around `web_app.py:399`.

Do not design a second auth system. Enterprise roles should map onto existing realm roles first, then add granular app-level permissions in enterprise tables.

### Existing Reusable Engines

- Generation Station / Capital Investment:
  - `new_capital_investment_routes.py:388` `size_utility_pv(...)`
  - `new_capital_investment_routes.py:6291` `register_capital_investment(...)`
  - `new_capital_investment_routes.py:6320` `_load_project(pid)`
  - Routes start at `new_capital_investment_routes.py:6350`.
- Standard residential sizing:
  - `web_app.py:1264` `calc_loads`
  - `web_app.py:1280` `calc_pv`
  - `web_app.py:1298` `calc_battery`
  - `web_app.py:1330` `calc_inverter`
  - `web_app.py:1342` `calc_economics`
  - `web_app.py:1775` `calc_boq`
- Simple BOQ report:
  - `calculation/boq_generator.py:6` `generate_boq(...)`
- BOQ hierarchy/rate engine:
  - `new_boq_hierarchy_schema.py:513` `ensure_boq_hierarchy_schema(get_db_fn)`
  - `new_boq_hierarchy_schema.py:555` `boq_audit(...)`
  - `new_boq_hierarchy_routes.py:102` `_boq_project_owned_or_404(...)`
  - `new_boq_hierarchy_routes.py:180` `/boq-projects`
  - `boq_rate_v3.py:27` `boq_rate_v3(...)`
- Marketplace:
  - `web_app.py:544` creates `equipment_catalog`
  - `new_marketplace_bom_routes.py:7` `_ensure_bom_tables`
  - `new_marketplace_bom_routes.py:103` `/boms`
  - `new_marketplace_rfq_routes.py:11` `_ensure_rfq_tables`
  - `new_marketplace_rfq_routes.py:108` `/rfqs`
  - `new_marketplace_procurement_center_routes.py:129` `/procurement-center`
- Funding:
  - `new_capital_investment_routes.py:5699` `_ensure_ci_funding_schema`
  - `new_capital_investment_routes.py:6114` `_ci_funding_assessment`
  - `new_capital_investment_routes.py:6687` `/large-scale-solar/<pid>/funding`
  - `new_capital_investment_routes.py:6928` `/project/<pid>/funding`
- Reports:
  - `new_capital_investment_routes.py:2732` `REPORT_TYPES`
  - `new_capital_investment_routes.py:3499` `_render_pdf_bytes(markdown_text, doc_title)`
- AI:
  - `api_manager.py:201` `_AIClient`
  - `api_manager.py:224` `_AIClient.chat(...)`
  - Budget gating at `api_manager.py:237` using `ai_budget.py`.
- Digital twin:
  - `static/capital_investment/dt/*`
  - Capital routes such as `new_capital_investment_routes.py:10804` `/large-scale-solar/<pid>/digital-twin`.
- Audit:
  - `app/security/audit.py:233` `write_audit_event(...)`
  - `logging_config/structured_logger.py:133` `log_audit(...)`
  - BOQ audit at `new_boq_hierarchy_schema.py:555`.

## Target Architecture

Add an additive enterprise module:

- `enterprise_programme_routes.py`: Flask blueprint/route registration through `register_enterprise_programme(...)`.
- `enterprise_programme_services.py`: deterministic services for programme CRUD, dashboard rollups, beneficiary validation, project-linking, template snapshots, and job chunking.
- `enterprise_programme_repository.py`: raw SQL repository, tenant/org scoped, no ORM.
- `enterprise_programme_jobs.py`: durable job claim/process functions.
- `templates/enterprise_programme/*.html`: registry, dashboard, setup, beneficiaries, links, settings.
- `migrations/024_enterprise_programme_foundation.sql`: organisation bridge, programme registry, beneficiaries, links, audit, jobs, RLS.
- Tests:
  - `tests/test_enterprise_programme_foundation.py`
  - `tests/security/test_enterprise_programme_tenant_isolation.py`

Registration in Phase 1 should be from `wsgi.py`, not `web_app.py`:

- Import `web_app.app`, `web_app.get_db`, `web_app.login_required`, `web_app.csrf_protect`, `web_app.current_user`.
- Import and call `register_enterprise_programme(...)`.
- Preserve `boot_state.attach(app, init_db)`.

This keeps the monolith untouched and the feature dark by default.

## Tenancy Bridge Design

### Problem

Existing SolarPro identity/data model:

- `users` table has flat organisation-stamping fields (`org_name`, `org_address`, etc.) only for reports.
- No actual organisation entity.
- Existing projects are individually owned by `projects.user_id`.
- RLS `tenant_id` is currently a pure function of user id, not a shared organisation.
- Real Keycloak users may not have `tenant_id` claims, so RLS can be inert due to NULL escapes in migrations such as `003_rls_tenant.sql`.

Enterprise needs:

- Many users in one organisation.
- Programme-level and role-level permissions.
- Organisation-level project visibility without exposing unrelated personal projects.
- Backward compatibility with existing personal projects.

### Staged Model

#### Stage 1: Add Enterprise Organisations Without Rewriting Existing Users

Create new tables:

- `enterprise_organisations`
- `enterprise_memberships`
- `enterprise_programmes`
- `enterprise_programme_phases`
- `enterprise_beneficiaries`
- `enterprise_programme_project_links`
- `enterprise_programme_jobs`
- `enterprise_programme_audit`

Each enterprise organisation has its own UUID `tenant_id`. Membership maps existing `users.id` and optional Keycloak `sub` to an organisation.

Existing users remain valid without enterprise membership. Existing projects remain personal and are not automatically shared.

#### Stage 2: Bootstrap Membership

When a user first opens `/enterprise` with the feature flag enabled:

- If no membership exists, create one organisation from `users.org_name` or `users.company` or fallback `"SolarPro Enterprise Workspace"`.
- Insert membership as `enterprise_owner`.
- Store `created_by_user_id`.
- Audit the bootstrap.

This is additive and reversible by disabling the feature flag.

#### Stage 3: Link Existing Projects Explicitly

Enterprise programmes do not take ownership of existing `projects` rows. They link them:

`enterprise_programme_project_links` contains:

- `programme_id`
- `project_kind`: `standard` or `generation_station`
- `project_id`
- `source_user_id`
- `linked_by_user_id`
- `template_version_id` nullable
- `design_strategy`

Phase 1 only allows linking projects the current user already owns, preserving `WHERE id=? AND user_id=?`. Multi-user project visibility is introduced later through membership-controlled enterprise views that resolve links, not by weakening existing project loaders.

#### Stage 4: Organisation Tenant Claim

Later, Keycloak should receive `tenant_id=<enterprise_organisations.tenant_id>` for enterprise users. Until that claim is guaranteed, enterprise routes must enforce organisation membership in SQL and app code:

- Every enterprise query filters by `organisation_id`.
- Membership is checked at route entry.
- RLS is defence-in-depth, not sole enforcement.

#### Stage 5: Backfill Existing RLS Tenant IDs Carefully

Do not bulk-update existing `projects.tenant_id` from user-derived tenant to organisation tenant in Phase 1. That would break assumptions and possibly expose data.

Later migration strategy:

1. Add `enterprise_owned_project_access` or strengthen `enterprise_programme_project_links`.
2. For linked projects only, add explicit enterprise access rows.
3. Keep `projects.user_id` ownership as canonical for legacy views.
4. Enterprise views query through links and membership.
5. Only after Keycloak tenant claims are reliable should optional org tenant IDs be applied to new enterprise-created projects.

## Job/Queue Design

### Existing Reality

- `tasks/celery_app.py` defines Celery.
- `tasks/report_tasks.py`, `tasks/email_tasks.py`, and `tasks/ai_tasks.py` define Celery tasks.
- `docker-compose.yml` defines worker/beat services.
- Production `Procfile:1` is web-only.
- GitHub Actions cron exists, e.g. `.github/workflows/soc-health-sweep.yml:16`, `.github/workflows/synthetic-health.yml:31`, `.github/workflows/backup-postgres.yml:45`.

Therefore Celery cannot be the production mechanism for enterprise bulk operations on Render free tier.

### Proposed Durable Table Queue

Add `enterprise_programme_jobs`:

- `id`
- `organisation_id`
- `programme_id`
- `job_type`
- `status`: queued, running, succeeded, failed, cancelled
- `idempotency_key`
- `payload_json`
- `progress_current`
- `progress_total`
- `cursor_json`
- `attempts`
- `max_attempts`
- `locked_by`
- `locked_until`
- `last_error`
- timestamps

Processing model:

- Jobs are created by UI actions with an idempotency key.
- A route like `POST /enterprise/jobs/tick` claims one job with `FOR UPDATE SKIP LOCKED` on Postgres.
- UI polling can process a small chunk per request, e.g. 25 beneficiaries or 5 project generations, staying below timeout.
- A GitHub Actions cron can call the same route every 5-15 minutes with a service token when owner configures it.
- Each chunk commits progress.
- Jobs are resumable after Render restart.
- No synchronous bulk design generation in request handlers.

Phase 1 creates the queue table and uses it for future imports/generation, but Phase 1 visible scope should be manual beneficiary entry and small project linking. Bulk CSV import can be preview-only or queued as a no-generation import job.

## AI Layer

Owner decision: do not use Google ADK for this module. Gemini key is exhausted. No LangChain, CrewAI, AutoGen, or new agent framework.

Plan:

- Implement deterministic Python services first:
  - Programme readiness score.
  - Beneficiary validation/qualification score.
  - Funding readiness summary using existing funding logic.
  - Risk flags.
  - Dashboard recommendations.
- Optional LLM enrichment only through existing `api_manager.py:224` `_AIClient.chat(...)`, governed by `ai_budget.py`.
- All AI output must be labelled recommendation/draft pending human approval.
- Add ADR exemption in `docs/ARCHITECTURE_DECISIONS.md` during implementation: “Enterprise Programme AI uses deterministic services with optional existing LLM gateway enrichment; ADK not used for this module by owner decision.”

## Requirement Classification

| Requirement | Classification | Plan |
|---|---:|---|
| Native SolarPro navigation | reuse-with-extension | Add dark-flagged nav link in `templates/base.html`; no `location.html` changes. |
| Enterprise signup/onboarding | needs-new-table + needs-new-UI | New enterprise org/membership bridge. Use existing Keycloak login. |
| Many users per organisation | needs-new-table | `enterprise_memberships`; Keycloak tenant claim follow-up. |
| RBAC | reuse-with-extension | Use `app/security/roles.py` + membership permissions. |
| Programme registry | needs-new-table + needs-new-UI | Phase 1 core. |
| Programme templates | needs-new-table | Phase 1 seed minimal template catalogue, versioned. |
| Programme phases | needs-new-table + needs-new-UI | Phase 1. |
| Beneficiary management manual | needs-new-table + needs-new-UI | Phase 1. |
| Bulk import | needs-new-service | Phase 2 queued import; Phase 1 table/job foundation. |
| Standard design strategy | needs-adapter | Reuse `web_app.py` sizing chain in Phase 2. |
| Generation station strategy | needs-adapter | Reuse `new_capital_investment_routes.py:388` and existing routes in Phase 2. |
| Automated project generation | needs-new-service | Phase 2 via durable jobs, no synchronous bulk. |
| BOQ consolidation | reuse-with-extension | Reuse BOQ hierarchy and marketplace BOM tables in Phase 3. |
| Marketplace procurement | reuse-with-extension | Use `equipment_catalog`, BOM/RFQ/procurement center. |
| Funding | reuse-with-extension | Use capital funding tables/functions; programme-level allocation table later. |
| EPC packaging | needs-new-table + needs-new-UI | Phase 3. |
| FIDIC contracts | needs-new-table + needs-new-UI | Phase 3/4; no digital signatures initially. |
| Logistics/warehouse/RFID | deferred | Free-tier substitute: manual status + CSV inventory. |
| GIS map | needs-new-UI | Phase 2 simple coordinate map; no GIS provider dependency. |
| Live SCADA/telemetry | not-feasible now | Free-tier substitute: manual/simulated telemetry summaries labelled as such. |
| Digital twin | reuse-with-extension | Link generation station projects to existing digital twin. |
| Workflow engine | needs-new-service | Configurable stage/status tables; not a full external workflow engine. |
| Digital signatures | not-feasible now | Substitute: typed approvals + audit chain; provider interface later. |
| AI programme agents | needs-new-service | Deterministic services + optional existing LLM gateway. |
| Scenario modelling | needs-new-service | Phase 5 deterministic assumptions table. |
| ESG/carbon | needs-new-table + service | Phase 5 configurable indicators; no false standard compliance claims. |
| Reporting | reuse-with-extension | Reuse `_render_pdf_bytes` and `REPORT_TYPES` patterns. |
| Audit trail | reuse-with-extension | Use `app/security/audit.py` and `boq_audit` where relevant. |
| Background jobs | needs-new-table + service | Durable DB queue, net-new. |
| Tenant isolation | needs-new-table + RLS | Enterprise org tenant UUID + membership checks. |
| Performance pagination | needs-new-UI + SQL indexes | Server-side pagination for beneficiaries/projects. |

## Phase Breakdown

### Phase 1: Enterprise Foundation And Registry

Size: M

Deliver visible value:

- Feature flag dark by default.
- Enterprise dashboard appears when flag is enabled.
- Current user can bootstrap an enterprise organisation.
- User can create programme, phases, and beneficiaries.
- User can link existing personal standard/generation projects to a programme.
- Dashboard shows real programme counts and capacity targets.
- Audit log records create/update/link actions.
- RLS policies protect new enterprise tables.

Live acceptance test:

1. Enable `enterprise_programme_enabled=1` in `admin_settings`.
2. Login as an existing Keycloak user.
3. Visit `/enterprise`.
4. Create organisation bootstrap if needed.
5. Create programme “Ghana National Secondary School Solar Independence Programme”.
6. Add three phases and at least three beneficiaries.
7. Link one existing standard project or one generation-station project owned by that user.
8. Confirm `/enterprise/programmes/<id>` shows counts, targets, beneficiaries, linked projects.
9. Confirm another non-member user cannot access the programme URL.
10. Disable flag and confirm `/enterprise` returns 404 or feature-disabled page and nav disappears.

### Phase 2: Design Strategy And Queued Project Generation

Size: L

- Add programme templates/versioning UI.
- Add site qualification scoring.
- Add CSV import preview + queued import.
- Add queued standard-project generation adapter.
- Add queued generation-station project generation adapter.
- Add GIS portfolio view from coordinates.
- Add links into existing project and capital routes.

Live acceptance test:

- Import 100 beneficiaries.
- Approve 10.
- Queue project generation.
- Observe progress polling.
- Confirm generated/linked projects exist and are traceable.

### Phase 3: Finance, BOQ Consolidation, Procurement, EPC Packaging

Size: L

- Programme funding facilities.
- Programme-level BOQ consolidation from linked projects.
- Procurement package generation.
- RFQ handoff to existing marketplace.
- EPC package assignment.

Live acceptance test:

- For a programme with linked projects, generate consolidated BOQ and create an RFQ package from it.

### Phase 4: Construction, Inspections, Contracts, Operations

Size: L

- Configurable workflow stages.
- FIDIC-style contract records.
- Variations, claims, milestones, payment certificates.
- Inspection/commissioning records.
- Programme assets rollup.
- Operations summaries with manual/mock telemetry.

Live acceptance test:

- Move one beneficiary/project through installation, inspection, commissioning, and operations status.

### Phase 5: Intelligence, Scenario Modelling, ESG

Size: M/L

- Deterministic programme recommendations.
- Optional LLM narrative via existing AI gateway.
- Scenario assumptions and comparisons.
- Carbon/ESG configurable indicators.
- Executive PDF reports.

Live acceptance test:

- Create a scenario with changed equipment cost and funding delay; generate a draft executive recommendation clearly labelled as draft.

## Commercially Attractive But Unrealistic On Free Tier

| Vision Item | Reality | Strongest Feasible Substitute |
|---|---|---|
| National live SCADA control centre | No SCADA provider, no persistent worker, free Render | Manual/simulated telemetry summaries with provider interface. |
| Satellite imagery scoring | No imagery provider/API budget | Manual GPS/roof/land fields and deterministic score; future provider interface. |
| Drone inspections | No drone media pipeline | Upload photo/document evidence; future media adapter. |
| Digital signatures | No signature provider | Audited approval records with hash-chain audit; future e-sign provider interface. |
| RFID/vehicle tracking | No IoT/logistics integration | Manual delivery status and CSV import/export. |
| ERP/GIS/utility API integrations | No credentials or providers | API adapter interfaces and import/export endpoints. |
| 10,000-project synchronous generation | Forbidden and infeasible | Durable chunked DB jobs with polling/cron ticker. |
| Full workflow engine | Not present | Configurable status/stage tables; workflow engine deferred. |
| External carbon standard compliance | No verified methodology/evidence workflow yet | Configurable carbon indicators; no compliance claims. |

## Key Risks

- `web_app.py` fragility: avoid editing it. Register from `wsgi.py`.
- RLS NULL escapes: enterprise app-layer membership checks are mandatory.
- Missing Keycloak tenant claim: do not rely on JWT tenant alone until verified.
- Job processing is net-new: must be conservative and idempotent.
- `lastrowid` fragility: use Postgres `RETURNING id` for new inserts.
- Feature flag: dark by default to protect live revenue app.
- Navigation: update `templates/base.html` only behind flag; do not touch `templates/location.html`, D3 globe, or `static/land-110m.json`.
