# Implementation Plan

## Non-Negotiables

Do not edit `web_app.py`, `api_manager.py`, or any `start*.py`. The standard project loader is user-owned (`web_app.py:1043`, `web_app.py:1045`), the generation-station loader is user-owned (`new_capital_investment_routes.py:6314`, `new_capital_investment_routes.py:6325`), and `api_manager.py::_AIClient.chat()` is the only allowed LLM gateway (`api_manager.py:201`, `api_manager.py:224`). Keep the existing `/enterprise` registration seam because `wsgi.py` imports and calls `register_enterprise_programme` (`wsgi.py:29`, `wsgi.py:32`). Render runtime is controlled by Render workflows, not the Procfile (`.github/workflows/render-apply-best-practices.yml:3`, `.github/workflows/render-apply-best-practices.yml:53`), while the Procfile remains only a fallback (`Procfile:1`).

## Release Cut

Release 1 implements a complete shorter lifecycle through Gate 9: tenancy, RBAC, programme registry, phases/statuses/gates, template approval, beneficiary import, site qualification, project generation, traceability, audit, queue visibility, dashboard, approved BOQ guard and procurement extension point. This matches the earlier verdict because a lifecycle with holes in the middle is worse than a shorter lifecycle that cannot be bypassed. EPC/FIDIC, logistics, construction, commissioning, O&M, telemetry, scenario modelling and advanced ESG are later releases, with blocked actions and extension tables present from Release 1.

## File-By-File Change Map

New files:
| Path | Purpose |
|---|---|
| `app/enterprise_programme/__init__.py` | Package export. |
| `app/enterprise_programme/constants.py` | Seed keys for doc-3 phases, gates, statuses, controls and dropdown taxonomies. |
| `app/enterprise_programme/repository.py` | Tenant-scoped data access. |
| `app/enterprise_programme/tenancy.py` | Enterprise tenants, memberships, invitations, personal-tenant backfill. |
| `app/enterprise_programme/rbac.py` | Role/permission/scope checks. |
| `app/enterprise_programme/workflows.py` | Phase/status workflow transitions. |
| `app/enterprise_programme/gates.py` | Gate predicates and blocked action checks. |
| `app/enterprise_programme/templates.py` | Versioned template service. |
| `app/enterprise_programme/beneficiaries.py` | Manual entry, import staging, validation, duplicate handling. |
| `app/enterprise_programme/site_qualification.py` | Score criteria and approval. |
| `app/enterprise_programme/project_generation.py` | Adapters to standard and generation-station engines. |
| `app/enterprise_programme/procurement.py` | Approved BOQ snapshots and consolidation extension point. |
| `app/enterprise_programme/funding.py` | Programme funding facilities and allocations. |
| `app/enterprise_programme/jobs.py` | Postgres durable queue with idempotency and worker status. |
| `app/enterprise_programme/reports.py` | Programme markdown report builders using markdown-pdf. |
| `app/enterprise_programme/ai_recommendations.py` | Labelled recommendations only via `_AIClient.chat()`. |
| `app/enterprise_programme/observability.py` | Structured logs/metrics wrappers. |
| `app/enterprise_programme/worker.py` | Render worker/cron entrypoint. |
| `templates/enterprise_programme/*.html` | New command-centre pages replacing old shallow templates. |
| `static/enterprise_programme/*` | Module JS/CSS for dropdowns, import preview, tables. |
| `tests/enterprise_programme/*` | Unit/integration/security tests for the rebuild. |
| `migrations/025_enterprise_programme_rebuild_foundation.sql` onward | Forward migrations after 024. |
| `.github/workflows/apply-enterprise-programme-rebuild-migrations.yml` | Migration workflow based on existing migration style (`scripts/apply_postgres_migrations.sh:2`, `scripts/apply_postgres_migrations.sh:125`). |

Modified files:
| Path | Change |
|---|---|
| `enterprise_programme_routes.py` | Keep `register_enterprise_programme`; replace old route internals. Existing old routes are at `enterprise_programme_routes.py:102`, `enterprise_programme_routes.py:151`, `enterprise_programme_routes.py:213`, `enterprise_programme_routes.py:299`, `enterprise_programme_routes.py:385`, `enterprise_programme_routes.py:462`. |
| `enterprise_programme_repository.py` | Compatibility shim only, delegating to new package during transition. |
| `enterprise_programme_services.py` | Compatibility shim only, then retire after Release 1. |
| `enterprise_programme_jobs.py` | Compatibility shim to new queue; old `tick` fails jobs by design (`enterprise_programme_jobs.py:185`, `enterprise_programme_jobs.py:189`). |
| `templates/base.html` | Only expand existing feature-flagged Enterprise nav when safe; current guard exists at `templates/base.html:430`, `templates/base.html:433`, `templates/base.html:436`. |
| `tests/test_enterprise_programme_foundation.py` | Replace old foundation assertions; it imports old modules at `tests/test_enterprise_programme_foundation.py:17`, `tests/test_enterprise_programme_foundation.py:18`, `tests/test_enterprise_programme_foundation.py:19`. |
| `.github/workflows/set-enterprise-programme-flag.yml` | Keep rollback flag workflow; it already uses admin `set_config` at `.github/workflows/set-enterprise-programme-flag.yml:119`, `.github/workflows/set-enterprise-programme-flag.yml:131`. |

Do not modify: `web_app.py`, `api_manager.py`, `start.py`, `start_render.py`, `START SERVER.bat`.

## Migration Order

| Migration | Release | Purpose |
|---|---|---|
| 025 | R1 | Create `enterprise_tenants`, true memberships, RBAC, taxonomy table, backfill personal tenants from deterministic user tenant. |
| 026 | R1 | Create programme core, phases, geographic areas, sites, statuses, gates, workflow definitions, approvals, documents. |
| 027 | R1 | Create templates, template versions, template equipment, required documents, template approval seed. |
| 028 | R1 | Create beneficiary import, import rows, site qualification, project links, generation jobs. |
| 029 | R1 | Create BOQ approvals, procurement package shell, consolidated source traceability tables. |
| 030 | R1 | Create audit/event mirrors, KPI source definitions, report request table, sample fixtures. |
| 031 | R2 | Funding facility extension, EPC packages, contract shell. |
| 032 | R2 | Procurement tender/bid/award, contract events, payment certificates, variations/claims. |
| 033 | R3 | Logistics, warehouses, inventory, deliveries. |
| 034 | R3 | Construction, inspection, commissioning, handover, assets. |
| 035 | R4 | O&M, telemetry provider interface, maintenance, KPI observations. |
| 036 | R5 | Scenario modelling, ESG/carbon evidence, AI recommendation registry expansion. |
| 037 | Cleanup | Rename/drop retired old 024 objects only after export and compatibility release. |

Postgres SQL functions must come after referenced tables because migration 024 documents SQL body parse order (`migrations/024_enterprise_programme_foundation.sql:101`, `migrations/024_enterprise_programme_foundation.sql:265`). Any `admin_settings` seed/update must call `set_config('app.current_role','admin',true)` inside the transaction as shown in migration 024 (`migrations/024_enterprise_programme_foundation.sql:404`, `migrations/024_enterprise_programme_foundation.sql:412`, `migrations/024_enterprise_programme_foundation.sql:414`).

## Vertical Slices

### Slice 1 - R1 Foundation, tenancy, flags

Goal: introduce true enterprise tenants without breaking user-owned projects.
Files: `app/enterprise_programme/tenancy.py`, `repository.py`, `rbac.py`, `constants.py`, migration 025, route bootstrap.
DB migration: 025.
Dropdown sources: organisation type, role codes, countries, regions.
Reused components: old flag keys (`migrations/024_enterprise_programme_foundation.sql:415`), existing auth decorators (`app/security/decorators.py:163`, `app/security/decorators.py:221`), deterministic tenant evidence (`migrations/003_rls_tenant.sql:136`).
Acceptance: every existing user has a personal enterprise tenant; no `projects.user_id` or `capital_investment_projects.user_id` changes; module remains dark.
Tests: tenant backfill, membership, IDOR, flag-off render.
Doc-3 gates/controls: control 13 tenant scope.

### Slice 2 - R1 Lifecycle seed and workflow spine

Goal: seed 16 phases, 14 gates, programme/project status enums, controls and workflow transitions.
Files: `workflows.py`, `gates.py`, route lifecycle pages, `templates/enterprise_programme/lifecycle.html`, migration 026.
DB migration: 026.
Dropdown sources: doc-3 phases, gates, statuses (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:26`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:72`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1191`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1212`).
Reused components: unified audit (`app/security/audit.py:233`, `app/security/audit.py:418`).
Acceptance: invalid phase transitions fail; Gate 1 cannot pass without sponsor approval; audit is written.
Tests: lifecycle state machine, stage gates, audit required.
Doc-3 gates/controls: Gates 1-14 seeded; controls 1, 11, 12, 13.

### Slice 3 - R1 Programme registry and onboarding UI

Goal: organisation onboarding and programme registration with dropdown-heavy forms.
Files: routes, `programmes.py`, onboarding/dashboard templates, static dropdown JS.
DB migration: 026.
Dropdown sources: location registries (`config/global_solar_data.py:406`, `config/ghana_regions.py:333`), seeded programme taxonomies.
Reused components: old `/enterprise` seam (`wsgi.py:29`, `wsgi.py:32`), old nav flag (`templates/base.html:430`).
Acceptance: admin creates organisation and programme; phase/gate rows auto-created; status defaults to Concept.
Tests: programme create/edit, dropdown sources, tenant isolation.
Doc-3 gates/controls: Phases 1-2, Gates 1-2, control 1.

### Slice 4 - R1 Templates and standardisation

Goal: versioned template engine with approval/publish.
Files: `templates.py`, template routes/templates, migration 027.
DB migration: 027.
Dropdown sources: beneficiary types, design strategy, equipment catalogue (`new_marketplace_procurement_center_routes.py:157`), BOQ services (`new_boq_services_engine.py:28`).
Reused components: marketplace, BOQ, standard package source examples.
Acceptance: draft template cannot generate projects; approved/published version is immutable for generated links.
Tests: template versioning, approval guard, equipment picker.
Doc-3 phase/gate/control: Phase 6, Gate 6, control 3.

### Slice 5 - R1 Beneficiaries and import

Goal: manual entry plus CSV/XLSX import staging, auto-mapping, row errors.
Files: `beneficiaries.py`, `jobs.py`, beneficiary templates, migration 028.
DB migration: 028.
Dropdown sources: beneficiary taxonomy, location cascade, project status enum.
Reused components: old beneficiary concept (`enterprise_programme_repository.py:582`), durable job concept (`enterprise_programme_jobs.py:57`).
Acceptance: import preview, row-level validation, duplicate detection, approval/rejection, no project generation before qualification.
Tests: import mapping, row errors, duplicate detection, approval.
Doc-3 phase/gate/control: Phase 3, Gate 3, controls 2, 12, 13.

### Slice 6 - R1 Site qualification

Goal: score and approve sites.
Files: `site_qualification.py`, qualification templates, migration 028.
DB migration: 028.
Dropdown sources: doc-3 score categories (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:138`), design strategy taxonomy.
Reused components: generation-station site/risk checks where applicable (`new_capital_investment_routes.py:3591`, `new_capital_investment_routes.py:3675`).
Acceptance: qualification status drives project eligibility; scoring records are auditable.
Tests: scoring, qualification gate, unqualified generation rejection.
Doc-3 phase/gate/control: Phase 3, Gate 3, control 2.

### Slice 7 - R1 Project generation adapters

Goal: generate or link standard/generation-station projects from approved beneficiaries and templates.
Files: `project_generation.py`, `worker.py`, project generation templates, migration 028.
DB migration: 028.
Dropdown sources: approved templates, standard packages, generation-station project types (`new_capital_investment_routes.py:57`).
Reused components: `_run_project_design` (`web_app.py:37906`), generation station sizing (`new_capital_investment_routes.py:388`), yield profile (`new_capital_investment_routes.py:478`).
Acceptance: queued generation repeats guards in worker; traceability to beneficiary/template exists; no request-thread mass generation.
Tests: draft template blocked, unqualified beneficiary blocked, idempotency, traceability.
Doc-3 phase/gate/control: Phase 9, Gate 9, controls 2, 3, 14.

### Slice 8 - R1 BOQ approval and procurement extension point

Goal: approved BOQ snapshots and traceable procurement shell.
Files: `procurement.py`, procurement templates, migration 029.
DB migration: 029.
Dropdown sources: BOQ services (`new_boq_services_engine.py:28`), product categories/equipment/suppliers (`new_marketplace_procurement_center_routes.py:144`, `new_marketplace_procurement_center_routes.py:157`), packaging options (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:454`).
Reused components: formal BOQ routes/functions (`web_app.py:35430`, `web_app.py:35566`) and marketplace procurement centre.
Acceptance: package creation fails without approved BOQ; every consolidated quantity has source line references.
Tests: approved BOQ guard, source-line traceability.
Doc-3 phase/gate/control: Phase 8 extension, control 5, control 15.

### Slice 9 - R1 Dashboard, reports, sample data, pilot flag

Goal: end-to-end pilot dashboard and reports for the complete R1 lifecycle.
Files: `reports.py`, `observability.py`, dashboard/reports templates, migration 030.
DB migration: 030.
Dropdown sources: report types from master prompt section 32 (`docs/enterprise-programme/source/01-master-prompt.txt:1425`).
Reused components: markdown-pdf (`web_app.py:4533`, `new_capital_investment_routes.py:3499`), audit (`app/security/audit.py:233`), tutorial engine (`static/tutorial/tutorial-engine.js:3`).
Acceptance: sample programmes created; dashboard counts from real rows; PDF report generated; flag can enable pilot tenant.
Tests: dashboard aggregation, report request, sample fixtures, smoke flow.
Doc-3 phase/gate/control: R1 workflow through Gate 9; controls 10, 12.

### Slice 10 - R2 Funding, EPC, contracts

Goal: programme funding facilities, EPC packages, FIDIC contract shell.
Files: `funding.py`, `contracts.py`, migration 031/032.
Dropdown sources: funding source taxonomy, funding institutions (`new_capital_investment_routes.py:8629`), FIDIC forms.
Reused components: funding module (`new_capital_investment_routes.py:5699`, `new_capital_investment_routes.py:7338`).
Acceptance: funding approval before major procurement; contractor cannot mobilise without executed contract.
Tests: funding allocation, Gate 7, Gate 8, mobilisation guard.
Doc-3 phases/gates/controls: Phases 7-8, Gates 7-8, control 6.

### Slice 11 - R3 Logistics, construction, inspection, commissioning, handover

Goal: delivery execution with gates 10-13.
Files: logistics/construction/commissioning modules and templates, migrations 033/034.
Dropdown sources: construction/inspection/commissioning taxonomies seeded from doc-3 phases 10-13.
Reused components: inspection report concept (`web_app.py:3433`, `web_app.py:3577`), markdown-pdf.
Acceptance: installation requires readiness, commissioning requires tests, handover requires dossier.
Tests: Gates 10-13 and controls 7-9.
Doc-3 phases/gates/controls: Phases 10-13, Gates 10-13, controls 7, 8, 9.

### Slice 12 - R4 O&M, telemetry, KPI, evaluation

Goal: operations centre, KPI source guards and benefits review.
Files: operations/kpi/telemetry modules, migration 035.
Dropdown sources: O&M taxonomy, KPI source definitions.
Reused components: digital twin (`new_capital_investment_routes.py:10804`), SCADA concepts (`new_capital_investment_routes.py:3211`).
Acceptance: no KPI without source; live telemetry clearly marked unavailable unless provider configured.
Tests: KPI source guard, O&M workflow, Gate 14.
Doc-3 phases/gates/controls: Phases 14-15, Gate 14, control 10.

### Slice 13 - R5 AI, scenarios, ESG, expansion

Goal: recommendation, scenario and replication capabilities.
Files: `ai_recommendations.py`, scenario/esg modules, migration 036.
Dropdown sources: scenario variables and ESG indicator taxonomy.
Reused components: `_AIClient.chat()` (`api_manager.py:201`, `api_manager.py:224`), AI budget (`ai_budget.py:85`), financial engines.
Acceptance: AI cannot approve; scenarios separate from approved baseline; programme clone works.
Tests: AI approval safety, scenario comparison, replication.
Doc-3 phases/controls: Phase 16, control 11.

## Feature Flags

Keep `enterprise_programme_enabled`, `enterprise_programme_jobs_enabled`, `enterprise_programme_ai_enabled` seeded dark (`migrations/024_enterprise_programme_foundation.sql:415`, `migrations/024_enterprise_programme_foundation.sql:416`, `migrations/024_enterprise_programme_foundation.sql:417`). Add tenant entitlement rows in migration 025. Enable in this order: UI read-only for pilot tenant, mutating R1 flow, jobs, then AI recommendations. Rollback is flag-off through `.github/workflows/set-enterprise-programme-flag.yml`, which documents it is also the rollback (`.github/workflows/set-enterprise-programme-flag.yml:4`).

## Test Commands

Run targeted tests first:
`python -m pytest tests/enterprise_programme -q`
`python -m pytest tests/security/test_enterprise_programme_tenant_isolation.py -q`
`python -m pytest tests/test_enterprise_programme_foundation.py -q`

Run integration reuse checks:
`python -m pytest test_funding_module.py test_marketplace_procurement_center.py test_marketplace_rfq.py tests/test_app.py -q`

Run broader checks before deployment:
`python -m pytest -q`
`bash scripts/quality-gate.sh` where available (`scripts/quality-gate.sh` exists by repo inventory).

## Deploy Commands

Apply migrations through a new workflow patterned on the existing runner. Existing migration script path is `scripts/apply_postgres_migrations.sh:2` and applies files with psql at `scripts/apply_postgres_migrations.sh:125`.

Suggested commands:
`gh workflow run apply-enterprise-programme-rebuild-migrations.yml -f migration=025`
`gh workflow run "Force Render Deploy"` using existing Render deploy workflow (`.github/workflows/render-deploy-now.yml:1`).
`gh workflow run set-enterprise-programme-flag.yml -f key=enterprise_programme_enabled -f value=1 -f confirm=APPLY`

Render ignores the Procfile once explicit start command exists (`.github/workflows/render-apply-best-practices.yml:3`). Do not change `Procfile` for worker rollout; add a Render worker service or cron that runs `python -m app.enterprise_programme.worker --loop` or `--once`.

## Rollback Commands

Flag rollback:
`gh workflow run set-enterprise-programme-flag.yml -f key=enterprise_programme_enabled -f value=0 -f confirm=APPLY`
`gh workflow run set-enterprise-programme-flag.yml -f key=enterprise_programme_jobs_enabled -f value=0 -f confirm=APPLY`
`gh workflow run set-enterprise-programme-flag.yml -f key=enterprise_programme_ai_enabled -f value=0 -f confirm=APPLY`

Render rollback:
Use previous deploy through Render dashboard/API or existing deploy workflow. Existing production workflow has Kubernetes rollback and Render fallback (`.github/workflows/deploy-production.yml:122`, `.github/workflows/deploy-production.yml:125`, `.github/workflows/deploy-production.yml:132`).

Database rollback:
Before tenant pilot, restore backup or run reverse migration. After tenant pilot, prefer forward rollback: flags off, mark bad template/import/job/package void, create corrective migration. Do not delete source projects because native ownership remains in `projects.user_id` and generation-station project ownership (`web_app.py:1045`, `new_capital_investment_routes.py:6325`).

## Old Module Teardown Sequence

1. Keep old flags dark during schema build (`migrations/024_enterprise_programme_foundation.sql:415`).
2. Export/count old eight tables from migration 024 before destructive work (`migrations/024_enterprise_programme_foundation.sql:110`, `migrations/024_enterprise_programme_foundation.sql:250`).
3. Migrate useful rows into new tenant/programme/beneficiary/project-link/audit tables.
4. Replace old route internals behind same `register_enterprise_programme` seam.
5. Replace seven templates referenced by old routes.
6. Replace old job helper with new queue; do not use `tick` as a worker (`enterprise_programme_jobs.py:185`).
7. Replace tests.
8. Keep `.github/workflows/apply-migration-024-enterprise-programme.yml` until every environment has either applied 024 or migrated past it (`.github/workflows/apply-migration-024-enterprise-programme.yml:1`).
9. In cleanup migration 037, rename old tables to retired names for one release, then drop only after validation.
