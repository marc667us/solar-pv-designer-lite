# Lifecycle Gates And Workflows

## Evidence Baseline

Doc 3 is the operational spine. It defines lifecycle phases from Programme Concept through Programme Expansion and Replication (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:8`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:19`), 14 gates (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:72`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:888`), the Programme Breakdown Structure (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:306`), governance (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:107`), workflows (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:924`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1149`), status enums (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:1191`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1212`), and 15 controls (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:1172`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1190`).

Existing SolarPro engines are reused where they already exist: standard design through `_run_project_design` (`web_app.py:37906`), generation-station sizing and yield through `size_utility_pv` and `_ci_yield_profile` (`new_capital_investment_routes.py:388`, `new_capital_investment_routes.py:478`), BOQ through standard and formal BOQ functions (`web_app.py:1775`, `web_app.py:21323`, `web_app.py:35430`, `web_app.py:35566`), funding through generation-station/project funding tables and routes (`new_capital_investment_routes.py:5699`, `new_capital_investment_routes.py:6687`, `new_capital_investment_routes.py:6928`, `new_capital_investment_routes.py:7338`), PDF reports through markdown-pdf (`web_app.py:4533`, `new_capital_investment_routes.py:3499`), and audit through `app/security/audit.py` (`app/security/audit.py:233`, `app/security/audit.py:418`).

## The 16-Phase State Machine

State transitions are performed only by `app/enterprise_programme/workflows.py::transition_programme_phase()`. The function loads the programme by `(tenant_id, programme_id)`, checks `rbac.require_enterprise_permission()`, runs `gates.evaluate_gate()`, writes `enterprise_workflow_transitions`, updates `enterprise_programmes.current_phase_code`, and audits the action.

| Phase code | Phase | Programme status | Allowed next transitions | Required gate to leave |
|---|---|---|---|---|
| `P01_CONCEPT` | Programme Concept | Concept | `P02_INITIATION`, `CANCELLED`, `ON_HOLD` | Gate 1 |
| `P02_INITIATION` | Programme Initiation | Under Initiation | `P03_NEEDS_ASSESSMENT`, `P01_CONCEPT`, `CANCELLED`, `ON_HOLD` | Gate 2 |
| `P03_NEEDS_ASSESSMENT` | Needs Assessment | Under Assessment | `P04_FEASIBILITY`, `P02_INITIATION`, `ON_HOLD` | Gate 3 |
| `P04_FEASIBILITY` | Feasibility and Business Case | Under Feasibility or Business Case Review | `P05_STRUCTURING`, `P03_NEEDS_ASSESSMENT`, `CANCELLED`, `ON_HOLD` | Gate 4 |
| `P05_STRUCTURING` | Programme Structuring and Master Planning | Approved | `P06_TEMPLATE_STANDARDISATION`, `P04_FEASIBILITY`, `SUSPENDED` | Gate 5 |
| `P06_TEMPLATE_STANDARDISATION` | Programme Template and Standardisation Development | Approved | `P07_FUNDING`, `P09_DETAILED_ENGINEERING`, `P05_STRUCTURING` | Gate 6 |
| `P07_FUNDING` | Funding and Commercial Structuring | Funding Pending | `P08_PROCUREMENT`, `P06_TEMPLATE_STANDARDISATION`, `ON_HOLD` | Gate 7 |
| `P08_PROCUREMENT` | Procurement Strategy and EPC Packaging | Procurement Planning or Tendering or Contracted | `P09_DETAILED_ENGINEERING`, `P10_MOBILISATION`, `P07_FUNDING` | Gate 8 |
| `P09_DETAILED_ENGINEERING` | Detailed Engineering and Project Generation | Under Design | `P10_MOBILISATION`, `P08_PROCUREMENT`, `SUSPENDED` | Gate 9 |
| `P10_MOBILISATION` | Mobilisation and Implementation Readiness | Contracted | `P11_CONSTRUCTION`, `P09_DETAILED_ENGINEERING`, `SUSPENDED` | Gate 10 |
| `P11_CONSTRUCTION` | Construction, Installation and Delivery | Under Construction | `P12_COMMISSIONING`, `P10_MOBILISATION`, `SUSPENDED` | Gate 11 |
| `P12_COMMISSIONING` | Inspection, Testing and Commissioning | Under Commissioning | `P13_HANDOVER_CLOSEOUT`, `P11_CONSTRUCTION`, `SUSPENDED` | Gate 12 |
| `P13_HANDOVER_CLOSEOUT` | Handover and Programme Closeout | Closing | `P14_OPERATIONS`, `P15_EVALUATION`, `CLOSED` | Gate 13 |
| `P14_OPERATIONS` | Operations and Maintenance | Operational | `P15_EVALUATION`, `SUSPENDED`, `CLOSING` | no numbered gate; controlled by O&M permissions and KPI source guards |
| `P15_EVALUATION` | Monitoring, Evaluation and Programme Optimisation | Operational or Closing | `P16_EXPANSION`, `P14_OPERATIONS`, `CLOSED` | Gate 14 |
| `P16_EXPANSION` | Programme Expansion and Replication | Approved | `P01_CONCEPT` for cloned programme, `P05_STRUCTURING` for new phase, `CLOSED` | expansion approval record |

Terminal pseudo-states: `CANCELLED`, `CLOSED`, `ARCHIVED`, `SUSPENDED`, `ON_HOLD`. Returning from `SUSPENDED` or `ON_HOLD` requires an approval record and audit event.

## The 14 Stage Gates

Gate decisions are stored in `enterprise_stage_gates` and `enterprise_approvals`. A gate cannot be marked approved unless its predicate returns `passed=true`.

| Gate | Entry conditions | Exit conditions | Approving authority | Required documents | Blocked until passed |
|---|---|---|---|---|---|
| Gate 1: Programme Concept Approval | Programme idea, sponsor candidate, concept note draft | Sponsor approval exists; concept note complete; initial objectives, geography, risk and funding sources recorded | Programme Sponsor | Concept note, initial risk register, stakeholder list | Programme initiation, governance setup |
| Gate 2: Programme Initiation Approval | Programme created, sponsor assigned | Steering committee approval; director/manager assigned; governance, scope, charter and document register complete | Steering Committee | Programme charter, governance chart, RACI, communications plan, risk register | Needs assessment import, baseline approval |
| Gate 3: Needs Assessment Approval | Beneficiary categories defined and records imported/staged | Validated beneficiary register, duplicate handling complete, priority framework approved | Programme Management Team | Beneficiary register, site register, baseline report, priority framework | Feasibility approval and project qualification |
| Gate 4: Feasibility and Business Case Approval | Needs baseline approved | Business case approved by sponsor/steering/funding stakeholders; preferred option selected | Sponsor, Steering Committee, Funding Stakeholders | Technical feasibility, financial feasibility, environmental/social screening, business case | Master planning baseline |
| Gate 5: Programme Master Plan Approval | Approved business case | PBS, phases, lots, schedule, cost/capacity/beneficiary baselines and KPI framework approved | Steering Committee | Master plan, regional rollout plan, cost baseline, KPI framework, change-control plan | Standardisation as controlling baseline |
| Gate 6: Standardisation Approval | Template drafts and standard packages prepared | Approved template versions, standard BOQs, drawings, tests and O&M requirements published | Technical Director or Engineering Approval Board | Template version pack, standard drawings, standard BOQ, test manual, commissioning manual | Project generation from templates |
| Gate 7: Financial Close or Funding Approval | Funding strategy prepared | Funding secured/approved to required threshold; conditions precedent tracked | Sponsor, Finance Manager, Funding Stakeholders | Funding strategy, commitments, disbursement plan, financial model, financial risk register | Major procurement |
| Gate 8: Contract Award and Notice to Proceed | Approved BOQ/procurement package/tender evaluation | Contract executed; securities/insurance accepted; NTP authorised | Procurement Manager, Contract Manager, Programme Director | Procurement plan, bid evaluation, award recommendation, signed contract, securities | Contractor mobilisation |
| Gate 9: Design Approval and Construction Release | Generated projects and detailed designs prepared | Engineering approval and issued-for-construction documents complete, or controlled early-works exception approved | Technical Director / Engineering Approver | Approved design, drawings, calculations, project BOQ, IFC package | Site installation |
| Gate 10: Site Mobilisation Approval | Contract/NTP exists and site assigned | Readiness checklist approved: access, permits, method statements, safety/quality/logistics plans | Programme Manager, Site/Regional Authority | Site handover certificate, mobilisation plan, safety plan, quality plan, logistics plan | Construction start |
| Gate 11: Construction Completion Approval | Construction reports exist | Completion checks satisfied, NCRs/punch list classified, testing request accepted | QA/QC Manager / Engineer | Daily/progress reports, quality records, safety records, completion notice | Formal testing |
| Gate 12: Commissioning and Taking-Over Approval | Testing requested | Required tests passed or waived by authority, commissioning certificate issued, training recorded | Commissioning Engineer, Owner Representative | Test results, commissioning certificate, performance test, training record, utility approval where required | Asset activation/handover |
| Gate 13: Handover and Closeout Approval | Commissioned system/project/phase | Complete handover dossier, warranties, as-builts, final account and closeout report approved | Owner / Programme Director / O&M Manager | Handover dossier, as-builts, warranties, final account, lessons learned | Operations responsibility transfer |
| Gate 14: Benefits and Performance Review | Operational performance data available | Benefits review decision: continue, modify, expand, or close | Steering Committee | Performance report, benefits-realisation report, scorecards, corrective action plan | Expansion/replication or final closure |

## Status Enums

### Programme Status Values

Seed these verbatim from doc 3 (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:1191`):

| Value |
|---|
| Concept |
| Under Initiation |
| Under Assessment |
| Under Feasibility |
| Business Case Review |
| Approved |
| Funding Pending |
| Procurement Planning |
| Tendering |
| Contracted |
| Under Design |
| Under Construction |
| Under Commissioning |
| Operational |
| Suspended |
| On Hold |
| Closing |
| Closed |
| Cancelled |
| Archived |

### Project Status Values

Seed these verbatim from doc 3 (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:1212`):

| Value |
|---|
| Beneficiary Registered |
| Qualification Pending |
| Qualified |
| Not Qualified |
| Template Assigned |
| Project Generated |
| Survey Pending |
| Under Design |
| Design Review |
| Design Approved |
| Procurement Pending |
| Contractor Assigned |
| Site Mobilised |
| Under Construction |
| Testing |
| Commissioning |
| Operational |
| Under Maintenance |
| Suspended |
| Closed |

## Programme Breakdown Structure

The PBS is stored through `enterprise_programmes`, `enterprise_programme_phases`, `enterprise_geographic_areas`, `enterprise_sites`, `enterprise_project_links`, `enterprise_procurement_packages`, `enterprise_epc_packages`, `enterprise_construction_reports`, and `enterprise_assets`.

| PBS level | Table | Existing reuse |
|---|---|---|
| Programme | `enterprise_programmes` | supersedes old programme table (`migrations/024_enterprise_programme_foundation.sql:140`) |
| Phase | `enterprise_programme_phases` | supersedes old phase table (`migrations/024_enterprise_programme_foundation.sql:164`) |
| Region | `enterprise_geographic_areas` | uses region registries and generation-station location data (`new_capital_investment_routes.py:5070`) |
| District | `enterprise_geographic_areas` | same |
| Community or Institution | `enterprise_beneficiaries`, `enterprise_geographic_areas` | supersedes old beneficiary table (`migrations/024_enterprise_programme_foundation.sql:179`) |
| Site | `enterprise_sites` | new |
| Project | `enterprise_project_links` | supersedes old project-link table (`migrations/024_enterprise_programme_foundation.sql:208`) |
| Design Package | `enterprise_template_versions`, native design project | reuses `_run_project_design` and generation-station module (`web_app.py:37906`, `new_capital_investment_routes.py:388`) |
| Contract Package | `enterprise_epc_packages`, `enterprise_contracts` | new |
| Construction Package | `enterprise_construction_reports` and related package tables | new |
| Asset Package | `enterprise_assets`, `enterprise_telemetry_sources` | new; generation-station digital twin reused where applicable (`new_capital_investment_routes.py:10805`) |

## Governance Structure

| Governance level | Role/record | Enforcement |
|---|---|---|
| Programme Sponsor | `Programme Sponsor` role and sponsor approval | Gate 1, Gate 4, Gate 14 |
| Programme Steering Committee | approval group in `enterprise_approvals` | Gate 2, Gate 4, Gate 5, Gate 14 |
| Programme Director | role assignment | programme approval and escalation |
| Programme Management Office | `Programme Manager`, PMO department | workflow coordination |
| Technical Workstream | Technical Director, Programme Engineer, Design Engineer | templates, design, engineering gates |
| Finance Workstream | Funding Manager, Finance Manager, Finance Officer | funding gates and allocation |
| Procurement Workstream | Procurement Manager | BOQ consolidation and procurement |
| Contract Workstream | Contract Manager, FIDIC Engineer | contracts, variations, claims |
| Regional Implementation Teams | Regional Manager, District Coordinator | region/district scoped delivery |
| Site Delivery Teams | Site Engineer, Site Supervisor, EPC roles | mobilisation, construction |
| Operations and Maintenance Team | Operations Manager, Maintenance Engineer, Monitoring Operator | operations, maintenance, KPIs |

## Workflow Step Mapping

Doc 3 says “10 named workflows” but lists 11 headings including Programme Approval Chain (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:924`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1149`). Treat Programme Approval Chain as the reusable approval sub-workflow used by the other 10.

### 1. End-to-End Programme Workflow

| Step | Existing service/route or new |
|---|---|
| Programme Opportunity Identified | new `app/enterprise_programme/programmes.py` |
| Concept Registered | new route `POST /enterprise/programmes` |
| Concept Reviewed | new `app/enterprise_programme/gates.py::gate_1_concept_approval` |
| Programme Charter Created | new document records; PDF generation reuses markdown-pdf (`web_app.py:4533`) |
| Governance Established | new tenancy/RBAC tables; auth layers on decorators (`app/security/decorators.py:163`, `app/security/decorators.py:221`) |
| Beneficiaries Registered | new beneficiary service; supersedes old manual add (`enterprise_programme_repository.py:582`) |
| Baseline Data Collected | new qualification records |
| Sites Screened | new site qualification with optional generation-station checks (`new_capital_investment_routes.py:3591`, `new_capital_investment_routes.py:3675`) |
| Feasibility Completed | reuse standard/generation-station financial engines (`web_app.py:37906`, `new_capital_investment_routes.py:5244`) |
| Business Case Approved | new Gate 4 approval |
| Programme Master Plan Approved | new Gate 5 approval |
| Programme Templates Developed | new template service |
| Standard Designs Approved | new Gate 6, template approval |
| Funding Secured | reuse funding engine and extend programme allocations (`new_capital_investment_routes.py:5699`, `new_capital_investment_routes.py:7338`) |
| Procurement Packages Prepared | reuse BOQ/marketplace; new procurement package tables (`web_app.py:21323`, `new_marketplace_procurement_center_routes.py:129`) |
| Contractors Selected | new EPC/FIDIC service |
| Beneficiaries Qualified | new qualification approval |
| SolarPro Projects Generated | new project-generation adapter; standard engine `_run_project_design` (`web_app.py:37906`) or generation-station module |
| Detailed Designs Completed | existing design engines plus new approval records |
| Designs Approved | new Gate 9 |
| Sites Mobilised | new Gate 10 |
| Materials Delivered | new logistics service |
| Construction Completed | new construction service |
| Inspections Completed | reuse inspection reporting where possible (`web_app.py:3433`, `web_app.py:3577`) plus new records |
| Testing Completed | new test records |
| Systems Commissioned | new Gate 12 |
| Assets Handed Over | new Gate 13 |
| Systems Monitored | new telemetry source tables; generation-station digital twin reused (`new_capital_investment_routes.py:10805`) |
| Maintenance Performed | new O&M service |
| Programme Performance Evaluated | new KPI service |
| Programme Expanded or Closed | new clone/close workflow |

### 2. Beneficiary-to-Project Workflow

| Step | Existing service/route or new |
|---|---|
| Beneficiary Imported | new import job service |
| Data Validation | new validation service |
| Duplicate Check | new duplicate detector |
| Beneficiary Review | new approval route |
| Site Qualification | new scoring service |
| Priority Scoring | new scoring service |
| Funding Eligibility Check | reuse funding-readiness concepts (`new_capital_investment_routes.py:6114`) |
| Programme Template Assignment | new template assignment service |
| Standard or Generation-Station Strategy Selected | programme/template field; old strategy constants existed only as simple strings (`enterprise_programme_services.py:77`, `enterprise_programme_services.py:81`) |
| Human Approval | new approval chain |
| SolarPro Project Generated | new adapter |
| Design Inputs Created | standard project data JSON or generation-station payload |
| Engineering Design Completed | `_run_project_design` or generation-station services (`web_app.py:37906`, `new_capital_investment_routes.py:388`) |
| BOQ Generated | standard `calc_boq` or formal BOQ/generation station BOQ (`web_app.py:1775`, `new_capital_investment_routes.py:2292`) |
| Project Approved | new engineering approval |
| Procurement Package Assigned | new procurement package assignment |
| Contractor Assigned | new EPC package |
| Installation Completed | new construction |
| Commissioning Completed | new commissioning |
| Asset Registered | new asset table |
| Operations Monitoring Activated | new telemetry source |

### 3. Standard Design Workflow

| Step | Existing service/route or new |
|---|---|
| Select Programme | new enterprise UI |
| Select Beneficiary Type | seeded dropdown |
| Select Standard Design Package | new approved template version |
| Import Site and Load Data | new beneficiary/import service |
| Validate Site Conditions | new qualification service |
| Adjust Standard Parameters | new template parameter override with approval |
| Run Solar Design Engine | reuse `_run_project_design` (`web_app.py:37906`) |
| Run Energy Simulation | reuse existing result chain in `_run_project_design` (`web_app.py:37910`, `web_app.py:38009`) |
| Select Equipment | reuse marketplace/equipment catalogue (`new_marketplace_procurement_center_routes.py:129`, `web_app.py:37367`) |
| Generate BOQ | reuse `calc_boq` (`web_app.py:1775`) |
| Generate Drawings | reuse existing report/drawing route helpers where applicable |
| Generate Financial Model | reuse economics output from `_run_project_design` (`web_app.py:37977`, `web_app.py:38009`) |
| Engineering Review | new approval |
| Approval | Gate 9 |
| Issue for Construction | new controlled status transition |

### 4. Generation-Station Design Workflow

| Step | Existing service/route or new |
|---|---|
| Register Generation Site | new site record |
| Confirm Land and Grid Data | new qualification fields |
| Define Target Capacity | template/generation-station payload |
| Conduct Solar Resource Assessment | reuse `_ci_yield_profile` (`new_capital_investment_routes.py:478`) |
| Complete Site Layout | reuse digital-twin/site-layout routes (`new_capital_investment_routes.py:10805`) |
| Configure PV Array Blocks | reuse generation-station module |
| Configure Mounting or Trackers | reuse generation-station constants/config |
| Configure Inverters | reuse generation-station module |
| Configure DC Collection | reuse generation-station module |
| Configure AC Collection | reuse generation-station module |
| Configure MV Stations | reuse generation-station module |
| Configure Transformers | reuse generation-station module |
| Configure Substation | reuse generation-station module |
| Configure Protection | reuse generation-station module |
| Configure SCADA | reuse generation-station SCADA concepts (`new_capital_investment_routes.py:3211`, `new_capital_investment_routes.py:3233`) |
| Configure Battery Storage | reuse generation-station module |
| Configure Grid Interconnection | reuse generation-station module |
| Configure Roads and Drainage | reuse generation-station civil fields where present; extend if missing |
| Configure Security and Fencing | reuse generation-station BOQ/facility scope where present |
| Run Energy Simulation | reuse `_ci_yield_profile` |
| Run Financial Model | reuse generation-station financial config (`new_capital_investment_routes.py:5244`) |
| Generate BOQ | reuse Step 9 BOQ (`new_capital_investment_routes.py:320`, `new_capital_investment_routes.py:2292`) |
| Complete Technical Review | new approval |
| Obtain Approval | Gate 9 |
| Issue for Construction | new transition |

### 5. Procurement Workflow

| Step | Existing service/route or new |
|---|---|
| Approved Project BOQs | new `enterprise_boq_approvals` |
| BOQ Consolidation | new service using existing BOQ tables/functions (`web_app.py:21323`, `web_app.py:35430`) |
| Product Standardisation | reuse catalogue/category data (`web_app.py:37367`, `web_app.py:37378`) |
| Quantity Aggregation | new consolidated BOQ tables |
| Regional and Phase Breakdown | new package grouping |
| Procurement Package Creation | new guarded service |
| Technical Specification Preparation | reuse report/PDF output (`web_app.py:4533`) |
| Tender Issue | new procurement workflow |
| Bid Receipt | new procurement workflow |
| Technical Evaluation | new procurement workflow |
| Financial Evaluation | new procurement workflow |
| Approval | procurement approval |
| Contract Award | Gate 8 |
| Purchase Order | new procurement/logistics |
| Manufacturing | new logistics status |
| Delivery | new logistics |
| Warehouse Receipt | new warehouse/inventory |
| Site Dispatch | new stock movement |
| Installation | construction workflow |
| Quantity Reconciliation | new source traceability table |

### 6. EPC and FIDIC Contract Workflow

| Step | Existing service/route or new |
|---|---|
| EPC Package Created | new EPC package service |
| Procurement Approval | procurement workflow approval |
| Tender Process | new procurement |
| Contractor Selection | new procurement/EPC |
| Contract Execution | new contract table |
| Notice to Proceed | Gate 8 exit |
| Mobilisation | Gate 10 workflow |
| Submittals | new contract/document records |
| Design Review | engineering approval |
| Construction | construction workflow |
| Engineer’s Instructions | new contract event |
| Progress Measurement | construction report |
| Interim Payment Certificate | new contract event/payment certificate |
| Variation Management | new contract event |
| Claim Management | new contract event |
| Extension-of-Time Review | new contract event |
| Testing | commissioning workflow |
| Taking-Over Certificate | Gate 12 |
| Defects-Notification Period | contract event |
| Performance Certificate | contract event |
| Final Account | Gate 13 closeout |
| Contract Closeout | contract status transition |

### 7. Funding Workflow

| Step | Existing service/route or new |
|---|---|
| Funding Requirement Identified | new programme funding requirement |
| Funding Source Registered | reuse financial institution registration/admin (`new_capital_investment_routes.py:8629`, `new_capital_investment_routes.py:8708`) |
| Due Diligence | extend funding assessment (`new_capital_investment_routes.py:6114`) |
| Funding Application | reuse funding tables/routes where project-level (`new_capital_investment_routes.py:6687`, `new_capital_investment_routes.py:6928`) |
| Funding Approval | new programme approval plus funding workspace decision pattern (`new_capital_investment_routes.py:7514`) |
| Conditions Precedent | new facility conditions |
| Funding Agreement | new document/facility record |
| Programme Allocation | new allocation |
| Phase Allocation | new allocation |
| Project Allocation | new allocation |
| Disbursement Request | new funding workflow |
| Expenditure Verification | new funding workflow |
| Payment Approval | new approval |
| Disbursement | new funding workflow |
| Utilisation Tracking | new KPI/funding reports |
| Financial Reporting | reuse markdown-pdf reports (`web_app.py:4533`) |
| Audit | unified audit (`app/security/audit.py:233`) |
| Funding Closeout | new status transition |

### 8. Construction Workflow

| Step | Existing service/route or new |
|---|---|
| Site Assigned | new project/site assignment |
| Site Handover | Gate 10 document |
| Mobilisation Approval | Gate 10 |
| Method Statement Approval | Gate 10 document |
| Material Approval | logistics/procurement approval |
| Material Delivery | stock movement |
| Installation | construction report |
| Daily Reporting | construction report |
| Quality Inspection | QA/QC record |
| Safety Inspection | safety record |
| Progress Measurement | construction report |
| Defect Correction | NCR/punch list |
| Construction Completion | Gate 11 |
| Testing Request | commissioning workflow |
| Commissioning | Gate 12 |

### 9. Inspection and Commissioning Workflow

| Step | Existing service/route or new |
|---|---|
| Contractor Inspection Request | new commissioning request |
| Document Review | new document checklist |
| Physical Inspection | reuse inspection report concept (`web_app.py:3433`, `web_app.py:3577`) plus new record |
| Test Execution | new `enterprise_inspection_tests` |
| Defects or Non-Conformances Recorded | new NCR records |
| Corrective Action | new NCR workflow |
| Retest | new test record |
| Performance Test | new test record |
| Utility Approval Where Required | document/approval |
| Commissioning Certificate | `enterprise_commissioning_certificates` |
| Training | document record |
| Handover Approval | Gate 13 |
| Asset Activation | asset status transition |

### 10. Operations and Maintenance Workflow

| Step | Existing service/route or new |
|---|---|
| Asset Activated | new asset status |
| Monitoring Enabled | new telemetry source; generation-station digital twin reused where applicable (`new_capital_investment_routes.py:10805`) |
| Performance Baseline Established | KPI baseline |
| Scheduled Maintenance | new maintenance schedule |
| Alarm Detection | telemetry adapter; live provider deferred |
| Fault Ticket Created | new O&M ticket |
| Fault Diagnosis | new O&M |
| Technician Assignment | new O&M |
| Repair | new O&M |
| Testing | commissioning/test reuse |
| Service Closure | new O&M |
| Asset Record Updated | asset service |
| Performance Reassessment | KPI observation |
| Warranty Claim Where Applicable | contract/asset event |

### Approval Sub-Workflow

| Step | Existing service/route or new |
|---|---|
| Programme Officer | new approval step |
| Programme Manager | role approval |
| Technical Director | role approval |
| Finance Manager | role approval |
| Procurement Manager | role approval |
| Legal or Contract Manager | role approval |
| Programme Director | role approval |
| Steering Committee | group approval |
| Programme Sponsor | final approval |
| Ministry/Utility/Financier/Donor/Regulator/District/Environmental/Community/Board additions | configurable approval steps |

## The 15 Key Programme Management Controls

Each control is enforced in service code, not in templates alone. Tests live under `tests/enterprise_programme/`.

| Control | Guard predicate | Called from | Test |
|---|---|---|---|
| No programme proceeds without an approved sponsor. | `gates.require_approved_sponsor(tenant_id, programme_id)` | `workflows.transition_programme_phase()` for Gate 1 and phase advancement beyond concept | `test_gate_1_blocks_without_sponsor_approval` |
| No beneficiary becomes a project without qualification. | `guards.require_qualified_beneficiary(tenant_id, beneficiary_id)` | `project_generation.queue_generation()` and `project_generation.generate_one()` | `test_project_generation_rejects_unqualified_beneficiary` |
| No project is generated without an approved template. | `guards.require_approved_template_version(tenant_id, template_version_id)` | `project_generation.queue_generation()` and `project_generation.generate_one()` | `test_project_generation_rejects_draft_template` |
| No design is issued without engineering approval. | `guards.require_engineering_approval(tenant_id, project_link_id)` | `workflows.issue_for_construction()` and Gate 9 | `test_issue_for_construction_requires_engineering_approval` |
| No procurement package is created without an approved BOQ. | `guards.require_approved_boq_snapshot(tenant_id, project_link_ids)` | `procurement.create_package()` | `test_procurement_package_rejects_unapproved_boq` |
| No contractor mobilises without contract approval. | `guards.require_executed_contract_and_securities(tenant_id, epc_package_id)` | `workflows.approve_mobilisation()` and Gate 8/10 | `test_mobilisation_requires_executed_contract` |
| No installation begins without site-readiness approval. | `guards.require_site_readiness_approval(tenant_id, project_link_id)` | `construction.start_installation()` and Gate 10 | `test_installation_start_requires_site_readiness` |
| No system is commissioned without required tests. | `guards.require_required_tests_passed(tenant_id, project_link_id)` | `commissioning.issue_certificate()` and Gate 12 | `test_commissioning_requires_all_required_tests` |
| No asset is handed over without complete documentation. | `guards.require_handover_dossier_complete(tenant_id, project_link_id)` | `handover.approve_handover()` and Gate 13 | `test_handover_requires_document_dossier` |
| No operational KPI is reported without a defined data source. | `guards.require_kpi_data_source(tenant_id, kpi_definition_id)` | `kpi.record_observation()` and dashboard aggregation | `test_kpi_observation_requires_source` |
| No AI recommendation becomes an approval automatically. | `guards.require_human_approval_actor(decision_by_user_id, ai_recommendation_id)` | `approvals.decide()` | `test_ai_recommendation_cannot_set_approval_status` |
| Every material action must be auditable. | `guards.require_audit_written(action_result)` | service transaction wrapper | `test_material_action_rolls_back_when_audit_missing` |
| Every programme record must be tenant-scoped. | `guards.require_tenant_scope(row, tenant_id)` plus RLS | all repository writes and reads | `test_cross_tenant_programme_idor_denied` |
| Every programme project must retain traceability to originating beneficiary and programme template. | `guards.require_project_traceability(tenant_id, project_link_id)` | `project_generation.generate_one()` transaction commit | `test_generated_project_link_requires_beneficiary_and_template` |
| Every aggregated procurement quantity must remain traceable to source project BOQ. | `guards.require_procurement_source_lines(tenant_id, package_id)` | `procurement.approve_package()` | `test_consolidated_quantity_requires_source_boq_lines` |

## Concrete Non-Bypass Examples

### A. Impossible to Generate a Project From an Unapproved Template

Call path:

1. Route `POST /enterprise/programmes/<id>/generate-projects`.
2. `rbac.require_enterprise_permission('design.generate', programme)`.
3. `project_generation.queue_generation(tenant_id, programme_id, beneficiary_ids, template_version_id)`.
4. `guards.require_approved_template_version()` checks `enterprise_template_versions.status in ('Approved','Published')`.
5. `guards.require_qualified_beneficiary()` checks each beneficiary qualification.
6. Only then is an `enterprise_jobs` row inserted.

Worker path repeats the same guards inside `project_generation.generate_one()` before creating or linking a native project. This duplicate check prevents a malicious user from bypassing the route and inserting a queued job manually.

Proof test: `test_project_generation_rejects_draft_template` creates a draft template, approves a beneficiary, posts to the route, asserts HTTP 409/403, asserts no job row and no `enterprise_project_links` row.

### B. Impossible to Create a Procurement Package From an Unapproved BOQ

Call path:

1. Route `POST /enterprise/programmes/<id>/procurement-packages`.
2. `procurement.create_package()` loads requested source project links.
3. `guards.require_approved_boq_snapshot()` verifies each link has an approved `enterprise_boq_approvals` row.
4. `procurement.aggregate_boq_lines()` writes `enterprise_consolidated_boq_lines`.
5. `guards.require_procurement_source_lines()` verifies every consolidated line has at least one source row in `enterprise_consolidated_boq_sources`.
6. Package remains draft until final approval.

Proof test: `test_procurement_package_rejects_unapproved_boq` creates project BOQ rows through existing BOQ shape, omits `enterprise_boq_approvals`, calls package creation, asserts rejection and no package.

### C. Impossible for AI Recommendation to Auto-Approve Anything

Call path:

1. AI adapter calls only `api_manager.py::_AIClient.chat()` (`api_manager.py:201`, `api_manager.py:224`) and stores output as `enterprise_ai_recommendations.status='Recommended'`.
2. Approval route `POST /enterprise/approvals/<id>/decision` requires authenticated human user.
3. `approvals.decide()` rejects if `decision_by_user_id` is null, if actor is service account without explicit approval permission, or if request tries to set approval actor from `ai_recommendation_id`.
4. AI recommendation id may be attached as supporting evidence but cannot be the decision actor.

Proof test: `test_ai_recommendation_cannot_set_approval_status` inserts an AI recommendation, attempts to call `approvals.decide()` with no human actor/service actor, asserts rejection, and verifies approval remains `Pending`.

## Required Test Suite

| Test file | Scope |
|---|---|
| `tests/enterprise_programme/test_lifecycle_state_machine.py` | 16 phases, allowed transitions, terminal states |
| `tests/enterprise_programme/test_stage_gates.py` | 14 gates and required predicates |
| `tests/enterprise_programme/test_status_enums.py` | programme/project enum values verbatim |
| `tests/enterprise_programme/test_rbac_matrix.py` | 38 operational roles and permissions |
| `tests/enterprise_programme/test_tenant_isolation.py` | cross-tenant IDOR and region scope |
| `tests/enterprise_programme/test_template_generation_guards.py` | approved template and qualified beneficiary controls |
| `tests/enterprise_programme/test_boq_procurement_guards.py` | approved BOQ and source-line traceability |
| `tests/enterprise_programme/test_ai_approval_safety.py` | no AI auto-approval |
| `tests/enterprise_programme/test_audit_required.py` | material action audit |
| `tests/enterprise_programme/test_jobs_idempotency.py` | queued generation/import idempotency |
| `tests/enterprise_programme/test_workflow_mappings.py` | each doc-3 workflow maps to route/service |

## Release Spine

Release 1 must implement the lifecycle spine through Gate 9 completely: tenancy, RBAC, programme registry, phases/statuses, gates 1-9, templates, beneficiaries, qualification, project generation, traceability, audit, queue status, and dashboards. Procurement can begin only with the approved BOQ guard in place. EPC/FIDIC, logistics, construction, commissioning, O&M, and telemetry follow as later vertical slices, but their state/gate placeholders and blocked-action predicates must exist from Release 1 so the lifecycle cannot be bypassed.

