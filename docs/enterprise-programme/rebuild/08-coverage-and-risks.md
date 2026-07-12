# Coverage And Risks

## Master Prompt Sections 9-45

| Section | Status | Follow-on task under section 47 |
|---|---|---|
| 9 Navigation | Full R1 | Expand existing flag-guarded nav under `/enterprise`; current guard at `templates/base.html:430`. |
| 10 Enterprise signup | Full R1 foundation | Validate exact billing/subscription fields with owner before migration 025. |
| 11 RBAC | Full R1 foundation | Seed 38 operational roles; test region and contractor scopes. |
| 12 Programme registration | Full R1 | Implement dropdown-heavy registration and cloning extension point. |
| 13 Template engine | Full R1 through approval/publish | R2 adds advanced drawings/report package automation. |
| 14 Design strategies | Full R1 adapters | Keep adapters around `_run_project_design` (`web_app.py:37906`) and generation station (`new_capital_investment_routes.py:388`). |
| 15 Beneficiary management | Full R1 except live GIS/API import | Follow-on: add external GIS/API import providers after credentials/source format are validated. |
| 16 Site qualification | Full R1 | Follow-on: add satellite/weather provider adapters after providers are chosen. |
| 17 Project generation | Full R1 with queue | Follow-on: enable at national scale only after Render worker/cron exists. |
| 18 Workflow engine | Full R1 spine | R2-R4 fill later phase-specific workflow records. |
| 19 Funding | Partial+extension point | R2 task: programme funding facilities and allocation workflow using existing funding module (`new_capital_investment_routes.py:5699`). |
| 20 EPC packaging | Partial+extension point | R2 task: EPC packages, contractor assignments, NTP guard. |
| 21 FIDIC contracts | Deferred+reason | R2 task: contract events, variations, claims, IPCs; no existing dedicated contract module found. |
| 22 Procurement | Partial+extension point | R1 approved BOQ guard; R2 tender/bid/award workflow. |
| 23 Logistics | Deferred+reason | R3 task: warehouses, inventory, deliveries; no existing warehouse module found. |
| 24 Construction | Deferred+reason | R3 task: daily reports, progress, safety, quality and claims. |
| 25 Inspection/commissioning | Partial+extension point | R3 task: reuse inspection report concept (`web_app.py:3433`) and add formal tests/certificates. |
| 26 Operations centre | Deferred+reason | R4 task: telemetry interface; live SCADA provider absent. |
| 27 GIS portfolio | Partial+extension point | R1 map fields; follow-on live GIS provider/import. |
| 28 Executive dashboard | Full R1 basic, partial advanced | R4 task: trend analysis, health score, benefits optimisation. |
| 29 AI orchestration | Partial+extension point | R5 task: recommendation registry using `_AIClient.chat()` only (`api_manager.py:201`). |
| 30 Scenario modelling | Deferred+reason | R5 task: scenario assumptions separate from approved baselines. |
| 31 ESG/carbon impact | Partial+extension point | R5 task: evidence-backed ESG indicators; do not claim standards without implementation. |
| 32 Reporting | Full R1 basic, partial catalogue | R1 core reports via markdown-pdf (`web_app.py:4533`); later add all report variants. |
| 33 Data model | Full staged | Migrations 025-036 create staged domain; cleanup 037 later. |
| 34 APIs | Full R1 for spine, partial later domains | R2-R4 add domain APIs as slices ship. |
| 35 Frontend | Full R1 for spine, partial later domains | R2-R4 add delivery/O&M workspaces. |
| 36 Background jobs | Partial+extension point | R1 durable queue; production worker/cron required before scale. |
| 37 Security | Full R1 foundation | Continue IDOR, upload, import and role-scope tests each slice. |
| 38 Migrations | Full staged | Use next free number 025 after 024. |
| 39 Testing | Full planned | Add tests per slice; do not report unrun tests as passed. |
| 40 Feature flags/release | Full | Reuse existing flags (`migrations/024_enterprise_programme_foundation.sql:415`). |
| 41 Deployment | Full planned | Render deploy and migration workflows; Render ignores Procfile per workflow evidence. |
| 42 Observability | Full R1 foundation | Add structured events for jobs/gates/imports/dashboard latency. |
| 43 Rollback | Full | Flag rollback first; forward corrective migrations after data use. |
| 44 Sample data | Full R1 fixtures | Add safe Ghana schools, hospitals, farms, 20 MW generation station. |
| 45 Acceptance criteria | Full staged | R1 satisfies spine through Gate 9; later releases satisfy remaining domains. |

## Doc-3 Lifecycle, Gates, Workflows, Controls

### Phases 1-16

| Phase | Status |
|---|---|
| 1 Concept | Full R1 |
| 2 Initiation | Full R1 |
| 3 Needs Assessment | Full R1 |
| 4 Feasibility/Business Case | Partial+extension point: R1 stores baseline/business case; R2 expands finance. |
| 5 Structuring/Master Planning | Full R1 |
| 6 Template/Standardisation | Full R1 |
| 7 Funding/Commercial | Partial R2 |
| 8 Procurement/EPC Packaging | Partial R1, full R2 |
| 9 Detailed Engineering/Project Generation | Full R1 |
| 10 Mobilisation | Deferred R3 |
| 11 Construction | Deferred R3 |
| 12 Inspection/Testing/Commissioning | Partial R3 |
| 13 Handover/Closeout | Deferred R3 |
| 14 O&M | Deferred R4 |
| 15 Monitoring/Evaluation/Optimisation | Partial R4 |
| 16 Expansion/Replication | Deferred R5 |

### Gates 1-14

| Gate | Status |
|---|---|
| Gate 1 Concept Approval | Full R1 |
| Gate 2 Initiation Approval | Full R1 |
| Gate 3 Needs Assessment Approval | Full R1 |
| Gate 4 Feasibility/Business Case Approval | Full R1 predicate, R2 richer evidence |
| Gate 5 Master Plan Approval | Full R1 |
| Gate 6 Standardisation Approval | Full R1 |
| Gate 7 Funding Approval | R2 |
| Gate 8 Contract Award/NTP | R2 |
| Gate 9 Design Approval/Construction Release | Full R1 |
| Gate 10 Mobilisation Approval | R3 |
| Gate 11 Construction Completion Approval | R3 |
| Gate 12 Commissioning/Taking-Over Approval | R3 |
| Gate 13 Handover/Closeout Approval | R3 |
| Gate 14 Benefits/Performance Review | R4 |

### Workflows

Doc 3 says 10 named workflows but includes Programme Approval Chain as an additional heading (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:924`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1149`). Treat approval chain as a shared sub-workflow.

| Workflow | Status |
|---|---|
| End-to-End Programme | Full R1 through Gate 9; later phases blocked until slices ship. |
| Beneficiary-to-Project | Full R1. |
| Standard Design | Full R1 adapter. |
| Generation-Station Design | Full R1 adapter. |
| Procurement | Partial R1; full R2. |
| EPC & FIDIC Contract | R2. |
| Funding | R2. |
| Construction | R3. |
| Inspection & Commissioning | R3. |
| Operations & Maintenance | R4. |
| Programme Approval Chain | Full R1 configurable approval foundation. |

### Controls 1-15

| Control | Enforced where |
|---|---|
| No programme proceeds without approved sponsor | `gates.require_approved_sponsor`, workflow transition. |
| No beneficiary becomes a project without qualification | `project_generation.queue_generation` and worker. |
| No project generated without approved template | `guards.require_approved_template_version`. |
| No design issued without engineering approval | Gate 9 construction release. |
| No procurement package without approved BOQ | `procurement.create_package`. |
| No contractor mobilises without contract approval | R2 mobilisation guard. |
| No installation begins without site readiness | R3 construction guard. |
| No system commissioned without tests | R3 commissioning guard. |
| No asset handed over without documentation | R3 handover guard. |
| No KPI without defined data source | R4 KPI service. |
| No AI recommendation becomes approval | `approvals.decide`; AI adapter uses `_AIClient.chat()` only. |
| Every material action auditable | Unified audit writer (`app/security/audit.py:233`). |
| Every programme record tenant-scoped | Repository + RLS; old RLS precedent at `migrations/024_enterprise_programme_foundation.sql:323`. |
| Every programme project traces to beneficiary/template | `enterprise_project_links`. |
| Every procurement quantity traces to source BOQ | `enterprise_consolidated_boq_sources`. |

## Follow-On Tasks For Partial/Deferred Items

| Item | Task |
|---|---|
| GIS/API import | Define provider interface, import schema, auth, sample files and tests. |
| Satellite/weather scoring | Add provider adapters with offline fallback and evidence fields. |
| Background worker scale | Add Render worker or cron service; prove queue progress and retry. |
| Funding | Extend project-centric funding tables into programme facilities and allocations. |
| FIDIC/contracts | Add contract entities, event workflows, IPCs, claims and variations. |
| Logistics | Build warehouse, inventory, delivery and reconciliation records. |
| Construction | Build site reports, quality/safety, progress, claims and completion checks. |
| Commissioning | Build test matrix, certificate, training and taking-over records. |
| O&M/live telemetry | Add telemetry provider registry; label simulated/manual data. |
| Scenario modelling | Store assumptions separately and compare baseline alternatives. |
| ESG/carbon | Add method registry, evidence uploads and verification status. |
| AI orchestration | Add recommendation registry, cost controls and approval separation tests. |
| Cleanup old module | Rename/drop old 024 objects only after export and compatibility release. |

## Risk Register

| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| Tenancy migration breaks existing user-owned projects | Medium | Critical | Backfill personal enterprise tenants; never mutate `projects.user_id` or generation-station ownership (`web_app.py:1045`, `new_capital_investment_routes.py:6325`). | Tech Lead |
| Live 024 data lost during teardown | Medium | High | Supersede in place; export/count old tables before cleanup. | DBA |
| No worker for bulk generation | High | High | R1 durable queue plus visible worker status; enable scale only after Render worker/cron. | Platform Lead |
| Gate checks implemented only in UI | Medium | Critical | Put predicates in services and worker; add bypass tests. | Backend Lead |
| Dropdown taxonomies drift from doc 3 | Medium | Medium | Seed from source lines and lock enum tests. | Product/QA |
| Marketplace/funding schemas are project-centric | High | Medium | Use adapters and programme allocation/link tables. | Backend Lead |
| Procurement quantities lose traceability | Medium | High | Require source join rows before package approval. | Procurement Lead |
| AI output accidentally treated as approval | Medium | High | Store AI as recommendation only; human actor required. | AI Lead |
| Report claims unsupported compliance | Medium | Medium | ESG reports require methodology/evidence; no standard claims without support. | ESG Lead |
| Render deploy command confusion | Medium | Medium | Use Render workflows; note Procfile is ignored by explicit start command. | DevOps |
| RLS policy order/function errors | Medium | High | Create tables before SQL functions; follow migration 024 warning. | DBA |
| Upload/import security gaps | Medium | High | File type/size validation, row staging, no direct activation. | Security Lead |
| Performance collapse on 10k beneficiaries | Medium | High | Server-side pagination, chunked jobs, indexes, load tests. | Performance Lead |
| Old module route compatibility issues | Medium | Medium | Keep route seam and compatibility shims for one release. | Backend Lead |
| Scope creep blocks Release 1 | High | High | Cut at complete Gate 9 lifecycle; defer delivery/O&M with blocked actions. | Programme Owner |

## Assumptions Requiring Validation Before Build

1. Confirm whether live Postgres has rows in all eight migration-024 enterprise tables.
2. Confirm exact enterprise role names and whether `Finance Manager` should be separate from `Funding Manager`.
3. Confirm supported first countries; Ghana registries exist, other countries use `GLOBAL_DATA` with less district depth.
4. Confirm initial pilot programmes and whether sample data should be shipped only in tests or staging seed.
5. Confirm Render worker/cron availability and cost.
6. Confirm acceptable import size limits for CSV/XLSX.
7. Confirm whether GIS import means shapefile, GeoJSON, KML, or spreadsheet coordinates for Release 1.
8. Confirm whether enterprise users may drill into native project pages when they are not the original `user_id` owner, or only view enterprise summaries.
9. Confirm funding institutions data quality in the existing funding workspace.
10. Confirm FIDIC forms and contract fields needed for the first market.
11. Confirm report formats beyond PDF; PDF path is markdown-pdf only.
12. Confirm branding and data residency requirements are contractual or descriptive for Release 1.
