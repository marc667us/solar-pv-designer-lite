# Dropdown And UX Spec

## Evidence And Option Sources

The owner requirement is to minimise typing. Existing option sources to reuse are: Ghana regions from `config/ghana_regions.py:12` and `config/ghana_regions.py:333`; global country/region solar data from `config/global_solar_data.py:31`, `config/global_solar_data.py:39`, `config/global_solar_data.py:406`, `config/global_solar_data.py:410`; generation-station project types, technologies and revenue models from `new_capital_investment_routes.py:57`, `new_capital_investment_routes.py:274`, `new_capital_investment_routes.py:608`; location cascading from `new_capital_investment_routes.py:5077`, `new_capital_investment_routes.py:5080`, `new_capital_investment_routes.py:5081`; marketplace categories, equipment and suppliers from `new_marketplace_procurement_center_routes.py:144`, `new_marketplace_procurement_center_routes.py:157`, `new_marketplace_procurement_center_routes.py:236`; BOQ service codes from `new_boq_services_engine.py:28`, `new_boq_services_engine.py:45`; funding institutions from `new_capital_investment_routes.py:8629`, `new_capital_investment_routes.py:8708`; lifecycle phases, gates, packaging options, programme statuses, project statuses and controls from `docs/enterprise-programme/source/02-lifecycle-workflows.txt:26`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:72`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:454`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1191`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1212`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1172`.

New configurable dropdowns must be seeded into `enterprise_taxonomy_options` in migration 025. This table holds programme types, organisation types, beneficiary types, delivery models, procurement strategies, contract frameworks, FIDIC forms, funding source types, risk classes, KPI categories, report types, document types, inspection test types, O&M event types, role codes and approval authorities. The old foundation has only shallow tables and flags (`migrations/024_enterprise_programme_foundation.sql:140`, `migrations/024_enterprise_programme_foundation.sql:179`, `migrations/024_enterprise_programme_foundation.sql:415`), so these taxonomies are new seeded data, not typed strings.

## Cascading And Defaults

| Cascade | Behaviour |
|---|---|
| Country -> region -> district -> community | Country select uses `GLOBAL_DATA` countries (`config/global_solar_data.py:31`); region select uses `get_regions(country)` (`config/global_solar_data.py:406`) or Ghana `REGION_LIST` (`config/ghana_regions.py:333`); district/community are seeded taxonomy rows scoped by country/region until a real district registry is added. Region can default to `DEFAULT_REGION` for Ghana (`config/ghana_regions.py:345`). |
| Category -> subcategory -> equipment | Product category select uses `product_categories` (`new_marketplace_procurement_center_routes.py:144`); equipment picker filters `equipment_catalog` joined to suppliers/categories (`new_marketplace_procurement_center_routes.py:157`). Subcategory is read from equipment rows and seeded where absent. |
| Programme type -> beneficiary type -> template -> standard package | Programme type and beneficiary type are seeded taxonomies from source examples (`docs/enterprise-programme/source/01-master-prompt.txt:554`, `docs/enterprise-programme/source/01-master-prompt.txt:755`); template picker filters approved/published versions; package picker filters template versions and seeded examples from `docs/enterprise-programme/source/02-lifecycle-workflows.txt:337`. |
| Design strategy -> project engine | `standard`, `generation_station`, `mixed` reuse old strategy vocabulary (`enterprise_programme_services.py:77`, `enterprise_programme_services.py:81`) but become seeded options. Standard routes through `_run_project_design` (`web_app.py:37906`); generation station routes through `new_capital_investment_routes.py:388`. |
| Programme phase -> gate -> approving role | Phase and gate options are seeded from doc 3 (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:26`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:72`). Approver defaults from governance/approval chain (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:107`, `docs/enterprise-programme/source/02-lifecycle-workflows.txt:1149`). |
| Funding source -> institution -> allocation rules | Source type seeded from doc 3 funding sources (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:404`); institution type and institution picker reuse funding workspace/admin (`new_capital_investment_routes.py:8629`, `new_capital_investment_routes.py:8708`). |

Defaults must prefer confirmation over typing: derive currency/timezone/unit system from organisation country; derive region lat/lon using location bundle (`new_capital_investment_routes.py:5077`, `new_capital_investment_routes.py:5081`); default programme status to `Concept`; default project status to `Beneficiary Registered`; default phase list to all 16 doc-3 phases; default stage gates to Gates 1-14; default template status to `Draft`; default import mapping from header synonyms; default report branding from organisation profile.

## Forms

### Organisation Onboarding

| Field | Control | Option source |
|---|---|---|
| Legal name | free text | Justified: legal name is institution-specific. |
| Display name | free text | Justified: branding-specific name. |
| Organisation type | select | `enterprise_taxonomy_options.organisation_type`, seeded from master prompt section 10 (`docs/enterprise-programme/source/01-master-prompt.txt:434`). |
| Country | select | `GLOBAL_DATA` countries (`config/global_solar_data.py:31`). |
| Region/business units | multiselect | Country-region cascade (`config/global_solar_data.py:406`, `config/ghana_regions.py:333`). |
| Registration number | free text | Justified: government/company registration formats vary. |
| Primary contact | typeahead | Existing users plus invited emails; old membership concept exists (`enterprise_programme_repository.py:163`). |
| Billing contact | typeahead | Existing users/invitations. |
| Technical contact | typeahead | Existing users/invitations. |
| Logo | picker | File upload with validation; no repo taxonomy. |
| Brand colours | picker | Colour picker. |
| Default currency | select | Generation-station currencies include GHS (`new_capital_investment_routes.py:100`) plus seeded ISO currency taxonomy. |
| Default timezone | select | `enterprise_taxonomy_options.timezone`. |
| Unit system | select | `enterprise_taxonomy_options.unit_system`. |
| Data residency | select | `enterprise_taxonomy_options.data_residency`. |
| Entitlement plan | select | `enterprise_taxonomy_options.entitlement_plan`; feature flags already exist (`migrations/024_enterprise_programme_foundation.sql:415`). |
| Initial admin | typeahead | Existing users/invite email. |

### Programme Registration

| Field | Control | Option source |
|---|---|---|
| Programme name | free text | Justified: unique programme title. |
| Programme code | free text with auto-suggest | Auto-generated from existing next-code pattern (`enterprise_programme_repository.py:494`); editable for official code. |
| Programme type | select | `enterprise_taxonomy_options.programme_type`, seeded from source examples (`docs/enterprise-programme/source/01-master-prompt.txt:45`). |
| Description | free text | Justified: narrative scope. |
| Sponsor | typeahead | Tenant memberships and role `Programme Sponsor` seeded from section 11 (`docs/enterprise-programme/source/01-master-prompt.txt:481`). |
| Owner/managing institution | picker | Enterprise departments. |
| Countries | multiselect | `GLOBAL_DATA` countries (`config/global_solar_data.py:31`). |
| Regions/districts/communities | cascading multiselect | Country-region-district-community cascade. |
| Dates | date | Date picker. |
| Objectives | free text | Justified: policy and programme-specific objectives. |
| Target beneficiaries/capacity/budget/carbon/jobs/local content | number | Numeric inputs with units. |
| Funding sources | multiselect | Doc-3 funding source taxonomy (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:404`). |
| Currency | select | Currency taxonomy plus GHS evidence (`new_capital_investment_routes.py:100`). |
| Delivery model | select | Doc-3 packaging/delivery terms (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:454`). |
| Procurement strategy | select | `enterprise_taxonomy_options.procurement_strategy`. |
| Contract framework | select | `enterprise_taxonomy_options.contract_framework`; FIDIC forms from source (`docs/enterprise-programme/source/00-vision.txt:230`). |
| Technical standards | multiselect | Generation-station standards list includes Ghana/IEC (`new_capital_investment_routes.py:92`). |
| Design strategy | select | `standard`, `generation_station`, `mixed` from old service vocabulary (`enterprise_programme_services.py:77`). |
| Reporting requirements/KPI framework/ESG requirements | multiselect plus free note | Taxonomy plus justified free note for programme-specific narrative. |
| Approval workflow | select | Seeded workflow definitions from doc-3 approval chain (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:1149`). |
| Risk classification | select | `enterprise_taxonomy_options.risk_classification`. |
| Programme status | select | Doc-3 programme status enum (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:1191`). |
| Archive status | toggle/select | Active/archived taxonomy. |

### Phase

| Field | Control | Option source |
|---|---|---|
| Phase | select | 16 doc-3 phases (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:26`). |
| Sequence | number | Default from phase seed order. |
| Region/district scope | cascading multiselect | Location cascade. |
| Planned/actual dates | date | Date picker. |
| Phase status | select | Programme status enum subset (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:1191`). |
| Gate | select | Gates 1-14 (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:72`). |
| Owner | typeahead | Tenant memberships/roles. |
| Notes | free text | Justified: schedule exceptions and management comments. |

### Template

| Field | Control | Option source |
|---|---|---|
| Template code/name | free text with auto-suggest | Justified official template naming. |
| Programme category | select | `enterprise_taxonomy_options.programme_type`. |
| Beneficiary type | select | `enterprise_taxonomy_options.beneficiary_type`, seeded from master prompt section 15 (`docs/enterprise-programme/source/01-master-prompt.txt:755`). |
| Design strategy | select | `standard`, `generation_station`, `mixed`. |
| Typical load profile | select | `enterprise_taxonomy_options.load_profile`. |
| PV capacity/battery capacity | number/select hybrid | Seeded standard package capacities from doc 3 (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:337`) plus numeric override. |
| Grid/off-grid/hybrid | select | `enterprise_taxonomy_options.energy_configuration`. |
| Generator/UPS integration | toggle | Boolean. |
| Equipment list/alternatives | typeahead/multiselect | `equipment_catalog`, `product_categories`, `suppliers` (`new_marketplace_procurement_center_routes.py:144`, `new_marketplace_procurement_center_routes.py:157`). |
| BOQ services | multiselect | `_BOQ_SERVICES` (`new_boq_services_engine.py:28`). |
| Drawings/reports/documents | picker | `enterprise_taxonomy_options.document_type` plus file picker. |
| Protection/testing/commissioning/O&M model | multiselect | Seeded taxonomy from doc-3 Phase 6 outputs (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:337`). |
| Funding/procurement/risk/schedule/KPI templates | select | Seeded template taxonomies. |
| Approval workflow | select | Workflow definition seed. |
| Version status | select | Master prompt template statuses (`docs/enterprise-programme/source/01-master-prompt.txt:601`). |

### Beneficiary Manual Entry

| Field | Control | Option source |
|---|---|---|
| Name | free text | Justified: beneficiary/institution-specific. |
| Beneficiary type | select | Seeded beneficiary taxonomy. |
| Institution type/building type | select | Seeded taxonomy. |
| Region/district/community | cascading select/typeahead | Location cascade; community typeahead from existing programme communities. |
| GPS coordinates | picker/number | Map picker plus lat/lon numeric. |
| Existing consumption/fuel/roof/land/priority | number | Numeric inputs. |
| Grid connection/transformer capacity/access/security/flood/environment risk | select/number | Site qualification taxonomy. |
| Funding eligibility | select | Funding eligibility taxonomy. |
| Assigned phase | select | Programme phase table. |
| Assigned template | select | Approved template versions. |
| Status/project status | select | Doc-3 project status enum (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:1212`). |
| Notes | free text | Justified: local site context not covered by taxonomy. |

### Beneficiary Import Mapping

| Field | Control | Option source |
|---|---|---|
| Source file | picker | CSV/XLSX/GIS file upload. |
| Source type | select | Spreadsheet, CSV, GIS, API, manual from doc 3 (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:138`). |
| Worksheet | select | Parsed workbook sheets. |
| Header row | number | Numeric. |
| Column mapping | select per target field | Target field list from beneficiary schema; auto-match common synonyms. |
| Duplicate key | multiselect | Name, region, district, GPS, registration id. |
| Default beneficiary type/template/phase | select | Cascading programme type -> beneficiary type -> approved template -> phase. |
| Validate only | toggle | Boolean. |
| Import comment | free text | Justified: operator batch note. |

Bulk path: upload CSV/XLSX, parse headers, auto-map columns by normalized names, preview first 50 rows, validate all rows into `enterprise_beneficiary_import_rows`, show row-level errors, allow downloadable error CSV, stage valid rows, require human approval before beneficiary activation. Old jobs are only a foundation (`enterprise_programme_jobs.py:57`, `enterprise_programme_jobs.py:185`), so the rebuild must use the new durable queue.

### Site Qualification

| Field | Control | Option source |
|---|---|---|
| Beneficiary/site | typeahead | Programme beneficiaries/sites. |
| Qualification criteria set | select | `enterprise_taxonomy_options.qualification_criteria_set`. |
| Scores | number sliders | Doc-3 score categories (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:138`). |
| Roof/land/grid/road/security/environment/communications | select/number | Site qualification taxonomy. |
| Recommended design strategy | select | Standard/generation-station/mixed. |
| Funding eligibility | select | Funding taxonomy. |
| Approver | typeahead | Users with beneficiary approval permission. |
| Decision | select | Qualified, Not Qualified, Returned. |
| Comments | free text | Justified: qualification rationale. |

### Project Generation

| Field | Control | Option source |
|---|---|---|
| Beneficiary set | multiselect/filter picker | Qualified beneficiaries only. |
| Template version | select | Approved/published template versions; enforced by Gate 6 (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:400`). |
| Standard package | select | Template package seed from doc 3 examples (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:337`). |
| Design engine | select | Standard/generation-station, routed to existing engines (`web_app.py:37906`, `new_capital_investment_routes.py:388`). |
| Generation mode | select | Draft links, generate design, generate and queue BOQ. |
| Batch size | number | Numeric. |
| Idempotency key | free text auto-generated | Justified only for operator-visible retry trace. |
| Human approval confirmation | toggle | Required before enqueue. |

### Funding Facility

| Field | Control | Option source |
|---|---|---|
| Funding source type | select | Doc-3 funding source taxonomy (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:404`). |
| Financial institution | typeahead | Existing funding institution workspace/admin (`new_capital_investment_routes.py:8629`, `new_capital_investment_routes.py:8708`). |
| Amount/currency | number/select | Currency taxonomy. |
| Conditions precedent | multiselect plus free text | Seeded conditions plus justified legal condition text. |
| Allocation level | select | Programme, phase, region, project. |
| Phase/project | picker | Enterprise phases/project links. |
| Status | select | Funding status taxonomy. |
| Documents | picker | Document type taxonomy. |

### EPC Package

| Field | Control | Option source |
|---|---|---|
| Package code/name | free text with auto-suggest | Justified official package identifier. |
| Package type | select | Doc-3 packaging options (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:454`). |
| Delivery model | select | EPC, EPCM, Design-Build, Turnkey, Framework from source (`docs/enterprise-programme/source/00-vision.txt:216`). |
| Region/phase/project scope | picker | Programme phase/geographic/project link records. |
| Contractor | typeahead | Supplier/contractor taxonomy and marketplace suppliers (`new_marketplace_procurement_center_routes.py:157`). |
| Procurement package | picker | Approved procurement packages. |
| Status | select | EPC status taxonomy. |
| Notes | free text | Justified: package-specific commercial notes. |

### Procurement Package

| Field | Control | Option source |
|---|---|---|
| Package type | select | Doc-3 packaging options (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:454`). |
| Source BOQs | multiselect | Approved BOQ snapshots only; BOQ services from `new_boq_services_engine.py:28`. |
| Product category/subcategory | cascading select | `product_categories` -> equipment subcategory (`new_marketplace_procurement_center_routes.py:144`, `new_marketplace_procurement_center_routes.py:157`). |
| Supplier panel | multiselect | `suppliers` joined through equipment catalogue (`new_marketplace_procurement_center_routes.py:157`). |
| Region/phase split | picker | Programme phase/geographic areas. |
| Tender status | select | Procurement workflow taxonomy. |
| Approval decision | select | Approval status taxonomy. |
| Procurement notes | free text | Justified: tender clarifications. |

### Contract

| Field | Control | Option source |
|---|---|---|
| Contract code/title | free text with auto-suggest | Justified official contract reference. |
| EPC package | picker | EPC packages. |
| FIDIC form | select | Red, Yellow, Silver, Green seeded from source (`docs/enterprise-programme/source/00-vision.txt:230`). |
| Contractor | typeahead | Suppliers/contractors. |
| Contract value/currency | number/select | Currency taxonomy. |
| Executed/NTP dates | date | Date picker. |
| Securities/insurance | multiselect | Contract requirement taxonomy. |
| Contract status | select | Contract status taxonomy. |
| Variation/claim/payment event type | select | Contract event taxonomy. |
| Notice text/comment | free text | Justified: legal notice wording. |

### Construction

| Field | Control | Option source |
|---|---|---|
| Project/site/package | picker | Enterprise project links/sites/EPC packages. |
| Work activity | select | Construction activity taxonomy from doc-3 Phase 11 (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:624`). |
| Progress percent | number | Numeric. |
| Materials used | typeahead | Equipment/catalog items. |
| Quality/safety/environment status | select | Construction status taxonomy. |
| Weather impact | select | Weather impact taxonomy. |
| Delay/claim/variation link | picker | Contract events. |
| Photos/evidence | picker | File upload. |
| Daily report note | free text | Justified: site narrative. |

### Inspection

| Field | Control | Option source |
|---|---|---|
| Inspection request | picker | Project/site. |
| Inspection type | select | Inspection taxonomy from doc-3 Phase 12 (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:697`). |
| Checklist | multiselect | Required test checklist taxonomy. |
| Inspector | typeahead | Users with Inspector role. |
| Result | select | Pass, fail, conditional pass, retest required. |
| NCR severity | select | NCR severity taxonomy. |
| Evidence | picker | File upload. |
| Findings | free text | Justified: inspection findings. |

### Commissioning

| Field | Control | Option source |
|---|---|---|
| Project/site | picker | Project links/sites. |
| Test type | select | Commissioning test taxonomy from doc-3 Phase 12 (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:697`). |
| Test result | select | Pass/fail/waived. |
| Utility approval required | toggle | Boolean. |
| Commissioning engineer | typeahead | Commissioning Engineer role. |
| Certificate date | date | Date picker. |
| Training completed | toggle | Boolean. |
| Certificate/evidence | picker | File upload. |
| Waiver/comment | free text | Justified: waiver and exception rationale. |

### O&M

| Field | Control | Option source |
|---|---|---|
| Asset/site/project | typeahead | Enterprise assets/project links. |
| Event type | select | O&M workflow taxonomy from doc-3 (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:1132`). |
| Maintenance type | select | Preventive/corrective/condition/predictive taxonomy. |
| Alarm/status | select | Telemetry status taxonomy. |
| Technician | typeahead | Maintenance Engineer role. |
| Warranty claim | toggle | Boolean. |
| KPI source | select | Defined KPI source records; required by control (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:1185`). |
| Reading/value | number | Numeric. |
| Work notes | free text | Justified: maintenance narrative. |

### Report Request

| Field | Control | Option source |
|---|---|---|
| Report type | select | Master prompt reporting list seeded into taxonomy (`docs/enterprise-programme/source/01-master-prompt.txt:1425`). |
| Programme/phase/region/project scope | picker | Enterprise records. |
| Period | date range | Date picker. |
| Format | select | PDF/spreadsheet/doc where supported; PDF must use markdown-pdf (`web_app.py:4533`, `new_capital_investment_routes.py:3499`). |
| Branding | select | Organisation brand profile. |
| Include appendices | multiselect | Report section taxonomy. |
| Narrative note | free text | Justified: report-specific cover note. |

### Settings

| Field | Control | Option source |
|---|---|---|
| Feature flags | toggle | Existing admin settings keys (`migrations/024_enterprise_programme_foundation.sql:415`, `migrations/024_enterprise_programme_foundation.sql:416`, `migrations/024_enterprise_programme_foundation.sql:417`). |
| Role assignments | multiselect/typeahead | Seeded role taxonomy from section 11 (`docs/enterprise-programme/source/01-master-prompt.txt:481`). |
| Approval workflow defaults | select | Workflow definitions. |
| Import limits | number | Numeric. |
| Worker mode | select | Web/manual/Render worker/cron taxonomy; no live worker confirmed (`enterprise_programme_jobs.py:8`, `.github/workflows/render-apply-best-practices.yml:53`). |
| AI recommendations enabled | toggle | Existing `enterprise_programme_ai_enabled` flag (`migrations/024_enterprise_programme_foundation.sql:417`). |
| Data retention | select | Retention taxonomy. |
| Support reason required | toggle | Boolean. |
