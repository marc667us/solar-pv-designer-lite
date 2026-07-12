# Gap Analysis

## Classification Legend

- Full reuse: existing code can be used without structural change.
- Reuse with configuration: existing code works after seeded options/flags/config.
- Reuse with extension: existing code is usable but needs new enterprise fields, adapters, or tests.
- Adapter required: existing code should not be modified directly; wrap it.
- New model/service/UI: no adequate existing enterprise-grade implementation exists.
- Deferred integration: foundation now, provider/live integration later.
- Not feasible now: blocked by infrastructure or missing external system.

## Vision Requirements

| Source requirement | Evidence | Classification | Gap and action |
|---|---|---|---|
| Native enterprise module inside SolarPro navigation | Vision positions Enterprise in SolarPro (`docs/enterprise-programme/source/00-vision.txt:30`); old nav is flag guarded (`templates/base.html:430`, `templates/base.html:433`). | Reuse with extension | Keep `/enterprise` and flag; replace old pages with lifecycle-aware UI. |
| Manage national/regional/community/institutional programmes | Vision scope (`docs/enterprise-programme/source/00-vision.txt:11`, `docs/enterprise-programme/source/00-vision.txt:66`, `docs/enterprise-programme/source/00-vision.txt:1338`). | New model/service/UI | Old programme table is shallow (`enterprise_programme_repository.py:176`); add PBS, lifecycle, regions, districts, beneficiaries, packages, assets. |
| Programme templates | Vision template engine (`docs/enterprise-programme/source/00-vision.txt:164`). | New model/service/UI | Old module has no template table; add versioned template library and approval gates. |
| Beneficiary management with bulk/GIS import | Vision beneficiary/import (`docs/enterprise-programme/source/00-vision.txt:181`, `docs/enterprise-programme/source/00-vision.txt:198`). | New service/UI | Old module has manual beneficiary add/list only (`enterprise_programme_repository.py:582`, `enterprise_programme_repository.py:627`). |
| Standard design strategy | Vision design strategy (`docs/enterprise-programme/source/00-vision.txt:135`). | Adapter required | Use standard project design and calculation helpers (`web_app.py:37906`, `calculation/pv_sizing.py:7`, `calculation/boq_generator.py:6`). |
| Generation-station strategy | Vision design strategy (`docs/enterprise-programme/source/00-vision.txt:135`). | Adapter required | Use generation-station module (`new_capital_investment_routes.py:3`, `new_capital_investment_routes.py:388`, `new_capital_investment_routes.py:6291`). |
| Funding integration | Vision funding integration (`docs/enterprise-programme/source/00-vision.txt:200`). | Reuse with extension | Use funding tables/routes (`new_capital_investment_routes.py:5699`, `new_capital_investment_routes.py:7338`) and add programme-level allocations. |
| EPC/turnkey/FIDIC | Vision EPC/FIDIC (`docs/enterprise-programme/source/00-vision.txt:216`, `docs/enterprise-programme/source/00-vision.txt:230`). | New model/service/UI | No enterprise contract module found; add EPC packages, FIDIC contract entities, claims, variations, payment certificates. |
| Executive dashboard | Vision dashboard (`docs/enterprise-programme/source/00-vision.txt:251`). | Reuse with extension | Old dashboard counts rows only (`enterprise_programme_services.py:172`, `enterprise_programme_services.py:221`); add KPI source registry and aggregations. |
| GIS/portfolio view | Vision GIS (`docs/enterprise-programme/source/00-vision.txt:268`, `docs/enterprise-programme/source/00-vision.txt:1232`). | Deferred integration | Use GPS/location fields now; defer live GIS provider. |
| AI orchestration | Vision AI programme agents (`docs/enterprise-programme/source/00-vision.txt:284`). | Adapter required | Use deterministic services and `api_manager.py::_AIClient.chat()` only for recommendations (`api_manager.py:201`, `api_manager.py:224`). |
| Enterprise tenancy/RBAC | Vision enterprise features (`docs/enterprise-programme/source/00-vision.txt:342`, `docs/enterprise-programme/source/00-vision.txt:348`, `docs/enterprise-programme/source/00-vision.txt:1282`). | New model/service/UI | Current tenancy is user-derived (`migrations/003_rls_tenant.sql:136`); add true organisations, memberships, roles, region scopes. |

## Master Prompt Sections 9-45

| Section | Requirement | Existing evidence | Classification | Required bridge |
|---|---|---|---|---|
| 9 | Required module navigation (`docs/enterprise-programme/source/01-master-prompt.txt:400`) | Old `/enterprise` nav is one flag-guarded link (`templates/base.html:430`, `templates/base.html:436`). | Reuse with extension | Expand nav/sidebar inside enterprise module; guard by entitlement and RBAC. |
| 10 | Enterprise signup/onboarding (`docs/enterprise-programme/source/01-master-prompt.txt:434`) | Old bootstrap creates one organisation for a user (`enterprise_programme_repository.py:306`, `enterprise_programme_repository.py:334`). | New model/service/UI | Add legal org profile, departments, regions, contacts, branding, invitations. |
| 11 | RBAC (`docs/enterprise-programme/source/01-master-prompt.txt:481`, `docs/enterprise-programme/source/01-master-prompt.txt:485`) | Old membership has simple role/status (`enterprise_programme_repository.py:163`, `enterprise_programme_repository.py:282`). | New model/service/UI | Add granular permissions and role scopes; test tenant and regional isolation. |
| 12 | Programme registration (`docs/enterprise-programme/source/01-master-prompt.txt:554`, `docs/enterprise-programme/source/01-master-prompt.txt:556`) | Old programme CRUD has basic fields (`enterprise_programme_repository.py:385`, `enterprise_programme_repository.py:396`). | Reuse with extension | Extend fields and normalize countries, regions, districts, funding, KPI, standards, workflow. |
| 13 | Template engine (`docs/enterprise-programme/source/01-master-prompt.txt:601`) | No old template tables; only design_strategy string (`enterprise_programme_services.py:77`). | New model/service/UI | Add template/version/status/equipment/BOQ/drawing/report/workflow entities. |
| 14 | Design strategies (`docs/enterprise-programme/source/01-master-prompt.txt:650`, `docs/enterprise-programme/source/01-master-prompt.txt:652`) | Standard and generation-station engines exist (`web_app.py:37906`, `new_capital_investment_routes.py:388`). | Adapter required | Add strategy adapters and approval guards. |
| 15 | Beneficiary management (`docs/enterprise-programme/source/01-master-prompt.txt:755`) | Manual beneficiary CRUD only (`enterprise_programme_repository.py:582`, `enterprise_programme_repository.py:627`, `enterprise_programme_routes.py:299`). | New service/UI | Add imports, staging, duplicate detection, approvals, export, history. |
| 16 | Site qualification (`docs/enterprise-programme/source/01-master-prompt.txt:834`) | No enterprise scoring; generation-station has site/risk checks (`new_capital_investment_routes.py:3591`, `new_capital_investment_routes.py:3675`). | New service with reuse | Add qualification criteria/scores and adapters to existing engineering checks. |
| 17 | Automated project generation (`docs/enterprise-programme/source/01-master-prompt.txt:876`) | Old module only links existing projects (`enterprise_programme_repository.py:695`, `enterprise_programme_repository.py:731`). | New service | Add idempotent generator; require qualified beneficiary and approved template. |
| 18 | Workflow engine (`docs/enterprise-programme/source/01-master-prompt.txt:911`) | No configurable workflow engine; old status update is simple beneficiary status (`enterprise_programme_repository.py:646`). | New model/service/UI | Add workflow definitions, instances, transitions, guards, approvals. |
| 19 | Funding and finance (`docs/enterprise-programme/source/01-master-prompt.txt:960`) | Funding module exists (`new_capital_investment_routes.py:5699`, `new_capital_investment_routes.py:7338`). | Reuse with extension | Add programme funding facilities, phase/project allocations, conditions, audit. |
| 20 | EPC/EPCM/turnkey packaging (`docs/enterprise-programme/source/01-master-prompt.txt:1007`) | No enterprise EPC model; generation-station reports mention delivery (`new_capital_investment_routes.py:3429`). | New model/service/UI | Add delivery packages, contractors, assignments, NTP predicates. |
| 21 | FIDIC contract interface (`docs/enterprise-programme/source/01-master-prompt.txt:1056`) | No dedicated contract administration found. | New model/service/UI | Add contract forms, milestones, notices, variations, claims, IPCs. |
| 22 | Programme procurement (`docs/enterprise-programme/source/01-master-prompt.txt:1097`) | Marketplace/procurement center exists (`new_marketplace_procurement_center_routes.py:129`, `new_marketplace_procurement_center_routes.py:202`). | Reuse with extension | Add consolidated BOQ, package creation, tender workflow, source traceability. |
| 23 | Logistics and warehousing (`docs/enterprise-programme/source/01-master-prompt.txt:1137`) | No warehouse/inventory module found beyond procurement docs. | New model/service/UI | Add warehouse, inventory item, stock movement, delivery, QR/RFID fields. |
| 24 | Construction management (`docs/enterprise-programme/source/01-master-prompt.txt:1165`) | Limited project/report features; no enterprise construction state. | New model/service/UI | Add daily reports, progress, safety, quality, variations, claims. |
| 25 | Inspection/testing/commissioning (`docs/enterprise-programme/source/01-master-prompt.txt:1195`) | Inspection report route exists (`web_app.py:3433`, `web_app.py:3577`). | Reuse with extension | Add commissioning test records, certificates, gate predicates. |
| 26 | Operations centre (`docs/enterprise-programme/source/01-master-prompt.txt:1224`) | Digital twin/SCADA concepts exist but live ops provider absent (`new_capital_investment_routes.py:3211`, `new_capital_investment_routes.py:3233`). | Deferred integration | Add simulated/manual operational summaries now; provider adapter later. |
| 27 | GIS portfolio (`docs/enterprise-programme/source/01-master-prompt.txt:1252`) | Location bundle exists (`new_capital_investment_routes.py:5070`). | Deferred integration | Add map fields and server-side filters; live GIS import later. |
| 28 | Executive dashboard (`docs/enterprise-programme/source/01-master-prompt.txt:1280`) | Old dashboard has basic counts (`enterprise_programme_services.py:245`, `enterprise_programme_services.py:284`). | Reuse with extension | Add KPI source registry, health score, regional breakdowns, trends. |
| 29 | AI orchestration (`docs/enterprise-programme/source/01-master-prompt.txt:1330`, `docs/enterprise-programme/source/01-master-prompt.txt:1354`) | AI gateway exists (`api_manager.py:201`, `api_manager.py:224`) and rule-based agents exist (`new_capital_investment_routes.py:3512`). | Adapter required | Add programme AI recommendation service; no automatic approvals. |
| 30 | Scenario modelling (`docs/enterprise-programme/source/01-master-prompt.txt:1376`) | Financial engines exist (`new_capital_investment_routes.py:1424`, `bankability_optimizer.py:54`). | New service with reuse | Add scenario assumptions and comparisons separate from approved baseline. |
| 31 | Carbon/ESG/development impact (`docs/enterprise-programme/source/01-master-prompt.txt:1400`) | Existing reports include carbon/energy concepts (`web_app.py:4829`, `new_capital_investment_routes.py:2810`). | Reuse with extension | Add configurable KPI/ESG indicator registry and evidence. |
| 32 | Reporting (`docs/enterprise-programme/source/01-master-prompt.txt:1425`) | markdown-pdf reporting exists (`web_app.py:4533`, `new_capital_investment_routes.py:10672`). | Reuse with extension | Add programme markdown report builders and branded exports. |
| 33 | Data model (`docs/enterprise-programme/source/01-master-prompt.txt:1465`) | Old model covers only org/programme/phase/beneficiary/link/job/audit (`migrations/024_enterprise_programme_foundation.sql:110`, `migrations/024_enterprise_programme_foundation.sql:250`). | New model/service | Add lifecycle, gates, templates, approvals, packages, contracts, logistics, KPI, scenario. |
| 34 | APIs (`docs/enterprise-programme/source/01-master-prompt.txt:1526`, `docs/enterprise-programme/source/01-master-prompt.txt:1528`) | Old routes are mostly HTML (`enterprise_programme_routes.py:102`, `enterprise_programme_routes.py:151`). | New API/UI | Add JSON APIs with auth, tenant, validation, pagination, idempotency. |
| 35 | Frontend (`docs/enterprise-programme/source/01-master-prompt.txt:1569`) | Old templates are simple pages referenced by routes (`enterprise_programme_routes.py:113`, `enterprise_programme_routes.py:402`). | New UI | Build command-centre UI with pagination, filters, approvals, imports, dashboards. |
| 36 | Background jobs (`docs/enterprise-programme/source/01-master-prompt.txt:1599`, `docs/enterprise-programme/source/01-master-prompt.txt:1601`) | No usable worker (`enterprise_programme_jobs.py:6`, `enterprise_programme_jobs.py:8`, `.github/workflows/render-apply-best-practices.yml:53`). | New infra/service | Add real worker/cron or admin-triggered durable queue; no request-thread bulk generation. |
| 37 | Security (`docs/enterprise-programme/source/01-master-prompt.txt:1625`) | RLS exists for old tables (`migrations/024_enterprise_programme_foundation.sql:321`, `migrations/024_enterprise_programme_foundation.sql:396`); current tenant is user-derived (`migrations/003_rls_tenant.sql:136`). | New model/service/tests | Add true organisation tenancy, object permissions, upload validation, IDOR tests. |
| 38 | Migrations (`docs/enterprise-programme/source/01-master-prompt.txt:1653`) | Migration workflow and script exist (`.github/workflows/apply-migration-024-enterprise-programme.yml:1`, `scripts/apply_postgres_migrations.sh:2`). | Reuse with extension | Add forward migrations and rollback guidance. |
| 39 | Testing (`docs/enterprise-programme/source/01-master-prompt.txt:1670`) | Old foundation test exists (`tests/test_enterprise_programme_foundation.py:1`). | New tests | Replace with unit/integration/e2e/security/performance/tenant tests. |
| 40 | Feature flags/release (`docs/enterprise-programme/source/01-master-prompt.txt:1766`) | Flags exist and are seeded dark (`migrations/024_enterprise_programme_foundation.sql:415`). | Reuse with extension | Keep flag; add entitlement and per-slice rollout. |
| 41 | Deployment (`docs/enterprise-programme/source/01-master-prompt.txt:1810`) | Render deploy workflows exist (`.github/workflows/deploy-production.yml:125`, `.github/workflows/render-apply-best-practices.yml:41`). | Reuse with extension | Add migration dry run, smoke tests, worker deploy path. |
| 42 | Observability (`docs/enterprise-programme/source/01-master-prompt.txt:1837`) | Metrics module exists by repo inventory and SOC logs exist (`web_app.py:39593`, `web_app.py:39698`). | Reuse with extension | Add programme import/generation/gate/dashboard/job metrics. |
| 43 | Rollback (`docs/enterprise-programme/source/01-master-prompt.txt:1859`) | Feature flag and deployment workflows exist (`migrations/024_enterprise_programme_foundation.sql:415`, `.github/workflows/render-clear-deploy.yml` by inventory). | Reuse with extension | Prefer flag rollback; table rename/export for data rollback. |
| 44 | Sample data (`docs/enterprise-programme/source/01-master-prompt.txt:1876`) | No enterprise sample fixtures found. | New fixtures | Add safe Ghana school, hospital, agriculture, 20 MW generation-station fixtures. |
| 45 | Acceptance criteria (`docs/enterprise-programme/source/01-master-prompt.txt:1929`) | Old module fails most criteria. | New implementation | Tie each vertical slice to acceptance tests. |

## Doc 3: 16 Phases

| Phase | Source | Classification | Required implementation |
|---|---|---|---|
| 1 Programme Concept | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:26` | New model/UI | Concept record, sponsor draft, concept note, Gate 1. |
| 2 Programme Initiation | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:76` | New model/UI | Governance, roles, charter, document register, Gate 2. |
| 3 Needs Assessment | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:138` | New service/UI | Beneficiary import, validation, duplicate handling, scores, Gate 3. |
| 4 Feasibility/Business Case | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:205` | Reuse with extension | Use financial/design engines; add business-case approval, Gate 4. |
| 5 Structuring/Master Planning | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:266` | New model/UI | PBS, phases, lots, baselines, KPI framework, Gate 5. |
| 6 Template & Standardisation | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:337` | New model/service/UI | Template library, approved versions, standard BOQs, Gate 6. |
| 7 Funding & Commercial Structuring | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:404` | Reuse with extension | Reuse funding module; add funding facilities, allocations, Gate 7. |
| 8 Procurement & EPC Packaging | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:454` | Reuse with extension | Reuse BOQ/marketplace; add consolidated packages, Gate 8. |
| 9 Detailed Engineering & Project Generation | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:519` | Adapter + new service | Generate standard/generation-station projects idempotently, Gate 9. |
| 10 Mobilisation | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:576` | New model/UI | Readiness checklists, NTP, logistics, Gate 10. |
| 11 Construction | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:624` | New model/UI | Daily reports, progress, quality, safety, claims, Gate 11. |
| 12 Inspection/Testing/Commissioning | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:697` | Reuse with extension | Reuse inspection/reporting; add test records/certificates, Gate 12. |
| 13 Handover/Closeout | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:749` | New model/UI | Dossiers, as-builts, warranties, final account, Gate 13. |
| 14 O&M | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:797` | Deferred integration | Manual/simulated ops first; telemetry adapter later. |
| 15 Monitoring/Evaluation/Optimisation | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:843` | New service/UI | Benefits tracking, scorecards, corrective actions, Gate 14. |
| 16 Expansion/Replication | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:892` | New service/UI | Clone approved structures/templates into new regions/sectors. |

## Doc 3: 14 Gates

| Gate | Source | Classification | Guard predicate |
|---|---|---|---|
| Gate 1 Concept Approval | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:72` | New approval | Sponsor approval exists and concept note complete. |
| Gate 2 Initiation Approval | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:134` | New approval | Steering committee approval, governance and scope complete. |
| Gate 3 Needs Assessment Approval | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:201` | New approval | Beneficiary register validated and priority framework approved. |
| Gate 4 Feasibility/Business Case Approval | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:262` | New approval | Business case approved by sponsor/steering/funding stakeholders. |
| Gate 5 Master Plan Approval | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:333` | New approval | PBS, baselines, phasing, KPI framework approved. |
| Gate 6 Standardisation Approval | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:400` | New approval | Template version approved before project generation. |
| Gate 7 Financial Close/Funding Approval | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:450` | Reuse with extension | Funding secured/approved before major procurement. |
| Gate 8 Contract Award/NTP | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:515` | New approval | Contract executed and securities accepted before mobilisation. |
| Gate 9 Design Approval/Construction Release | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:572` | New approval | Construction documents approved or early-works exception approved. |
| Gate 10 Site Mobilisation Approval | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:620` | New approval | Site readiness checklist approved. |
| Gate 11 Construction Completion Approval | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:693` | New approval | Construction completion checks satisfied. |
| Gate 12 Commissioning/Taking-Over Approval | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:745` | Reuse with extension | Required tests and commissioning certificates complete. |
| Gate 13 Handover/Closeout Approval | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:793` | New approval | Complete handover dossier and closeout records. |
| Gate 14 Benefits/Performance Review | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:888` | New approval | Benefits review decision to continue, modify, expand, or close. |

## Doc 3: 10 Named Workflows

| Workflow | Source | Classification | Required bridge |
|---|---|---|---|
| End-to-End Programme | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:924` | New workflow | State machine across all phases and gates. |
| Beneficiary-to-Project | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:959` | New workflow + adapters | Import, qualify, assign template, approve, generate project, link asset. |
| Standard Design | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:983` | Adapter required | Call standard design engine after approval. |
| Generation-Station Design | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1001` | Adapter required | Call generation-station wizard/services after approval. |
| Procurement | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1029` | Reuse with extension | BOQ consolidation to marketplace procurement packages. |
| EPC & FIDIC Contract | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1052` | New model/service/UI | Contract administration workflow. |
| Funding | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1077` | Reuse with extension | Funding application/allocation/disbursement/audit. |
| Construction | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1098` | New model/UI | Site handover through commissioning request. |
| Inspection & Commissioning | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1116` | Reuse with extension | Inspection forms plus test/certificate records. |
| O&M | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1132` | Deferred integration | Maintenance tickets and telemetry adapter. |
| Programme Approval Chain | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1149` | New workflow | Configurable approver sequence and escalation. |

Note: doc 3 calls out “10 named workflows” but lists End-to-End, Beneficiary-to-Project, Standard Design, Generation-Station Design, Procurement, EPC & FIDIC, Funding, Construction, Inspection & Commissioning, Operations & Maintenance, and Programme Approval Chain. That is 11 headings in the source (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:924`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1149`). Treat Programme Approval Chain as the approval sub-workflow used by the other 10 rather than omitting it.

## Doc 3: Status Enums

| Enum | Source | Classification | Required implementation |
|---|---|---|---|
| Programme status values: Concept, Under Initiation, Under Assessment, Under Feasibility, Business Case Review, Approved, Funding Pending, Procurement Planning, Tendering, Contracted, Under Design, Under Construction, Under Commissioning, Operational, Suspended, On Hold, Closing, Closed, Cancelled, Archived | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1191`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1192`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1211` | New enum table/state machine | Seed verbatim, enforce transitions through workflow service, expose as dropdown not text. |
| Project status values: Beneficiary Registered, Qualification Pending, Qualified, Not Qualified, Template Assigned, Project Generated, Survey Pending, Under Design, Design Review, Design Approved, Procurement Pending, Contractor Assigned, Site Mobilised, Under Construction, Testing, Commissioning, Operational, Under Maintenance, Suspended, Closed | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1212`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1213`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1232` | New enum table/state machine | Seed verbatim, enforce beneficiary-to-project and delivery transitions. |

## Doc 3: 15 Controls

| Control | Source | Classification | Code enforcement needed |
|---|---|---|---|
| No programme proceeds without an approved sponsor. | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1176` | New guard | `can_transition(programme, next_phase)` checks sponsor approval. |
| No beneficiary becomes a project without qualification. | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1177` | New guard | Project-generation service requires qualification status. |
| No project is generated without an approved template. | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1178` | New guard | Generator requires approved template version ID. |
| No design is issued without engineering approval. | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1179` | New guard | Construction-release route checks engineering approval. |
| No procurement package is created without an approved BOQ. | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1180` | New guard | Procurement service requires approved BOQ snapshot. |
| No contractor mobilises without contract approval. | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1181` | New guard | Mobilisation transition checks executed contract and securities. |
| No installation begins without site-readiness approval. | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1182` | New guard | Construction start checks readiness checklist approval. |
| No system is commissioned without required tests. | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1183` | New guard | Commissioning approval checks required tests complete/pass. |
| No asset is handed over without complete documentation. | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1184` | New guard | Handover transition checks document dossier. |
| No operational KPI is reported without a defined data source. | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1185` | New guard | KPI service requires source definition and freshness. |
| No AI recommendation becomes an approval automatically. | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1186` | Adapter + guard | AI output creates recommendation/draft only; approval table requires human actor. |
| Every material action must be auditable. | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1187` | Reuse with extension | Use unified audit chain (`app/security/audit.py:233`, `app/security/audit.py:418`). |
| Every programme record must be tenant-scoped. | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1188` | New tenancy model | Add enterprise tenant ID and RLS/service checks. |
| Every programme project must retain traceability to beneficiary and template. | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1189` | New traceability model | Extend old project link concept (`enterprise_programme_repository.py:731`) with beneficiary/template version/source design IDs. |
| Every aggregated procurement quantity remains traceable to source project BOQ. | `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1190` | New traceability model | Add consolidated BOQ line source join table. |

## PBS And Governance

Doc 3 requires Programme -> Phase -> Region -> District -> Community/Institution -> Site -> Project -> Design Package -> Contract Package -> Construction Package -> Asset Package (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:306`). The old module only has programme, phase, beneficiary, and project link tables (`enterprise_programme_repository.py:176`, `enterprise_programme_repository.py:190`, `enterprise_programme_repository.py:199`, `enterprise_programme_repository.py:213`). Classification: new model/service/UI.

Doc 3 governance requires Sponsor -> Steering Committee -> Director -> PMO -> workstreams -> regional teams -> site teams -> O&M (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:107`). The old module only has `enterprise_memberships.role` (`enterprise_programme_repository.py:163`) and no approval authority matrix. Classification: new RBAC/workflow model.

## Biggest Architectural Gaps

1. True enterprise tenancy is missing. Current tenant ID is a deterministic hash of user ID (`migrations/003_rls_tenant.sql:136`), while source requirements demand institution signup and many users per organisation (`docs/enterprise-programme/source/01-master-prompt.txt:434`, `docs/enterprise-programme/source/01-master-prompt.txt:481`).
2. Lifecycle and gates are absent. Old code has no doc-3 phase/gate/workflow state machine (`enterprise_programme_repository.py:385`, `enterprise_programme_repository.py:646`; `docs/enterprise-programme/source/02-lifecycle-workflows.txt:26`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1172`).
3. Project generation is absent. Old code links existing projects only (`enterprise_programme_repository.py:695`, `enterprise_programme_repository.py:731`) while doc 3 requires generation from approved beneficiaries/templates (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:959`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1178`).
4. Background processing is not production-ready. Celery exists but is not deployed/used for enterprise jobs (`enterprise_programme_jobs.py:8`, `.github/workflows/render-apply-best-practices.yml:53`), while source requirements require batch imports and thousands of generated projects (`docs/enterprise-programme/source/01-master-prompt.txt:1599`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:519`).
5. Procurement/FIDIC/logistics/construction/O&M are mostly absent as enterprise domain models, though BOQ, marketplace, funding, finance, reporting, and digital twin can be reused (`new_boq_services_engine.py:2`, `new_marketplace_procurement_center_routes.py:129`, `new_capital_investment_routes.py:5699`, `new_capital_investment_routes.py:1424`, `web_app.py:4533`, `new_capital_investment_routes.py:10804`).

## Release Cut Recommendation

Release 1 should implement a complete shorter lifecycle rather than a hollow full lifecycle: enterprise tenancy foundation, programme registry, seeded phases/statuses/gates, template approval, beneficiary import/qualification, project generation adapters, traceability, audit, dashboard, and the first six controls through Gate 9. Funding/procurement can be read-only or limited to approved BOQ consolidation in Release 1 if the guard predicates are complete. EPC/FIDIC/logistics/construction/O&M/telemetry should follow in later slices because partial delivery controls are more dangerous than deferring those phases with explicit extension points.
