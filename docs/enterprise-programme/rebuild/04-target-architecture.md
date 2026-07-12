# Target Architecture

## Evidence Baseline

This target keeps the existing SolarPro application intact and adds an enterprise orchestration layer around existing engines. The standard project loader remains user-owned through `SELECT * FROM projects WHERE id=? AND user_id=?` (`web_app.py:1045`). The generation-station loader also resolves tenant context but still reads owned projects with `WHERE id=? AND user_id=?` (`new_capital_investment_routes.py:6312`, `new_capital_investment_routes.py:6314`, `new_capital_investment_routes.py:6325`). The current tenant UUID is not an organisation; it is generated from the user id by `md5('solarpro-tenant-v1:' || uid::text)::uuid` (`migrations/003_rls_tenant.sql:136`). Migration 001 confirms the historic base schema had no organisations table and drops `organizations` (`migrations/001_mirror_sqlite.sql:20`, `migrations/001_mirror_sqlite.sql:44`).

The old enterprise foundation creates eight dark tables and three dark flags (`migrations/024_enterprise_programme_foundation.sql:110`, `migrations/024_enterprise_programme_foundation.sql:125`, `migrations/024_enterprise_programme_foundation.sql:140`, `migrations/024_enterprise_programme_foundation.sql:164`, `migrations/024_enterprise_programme_foundation.sql:179`, `migrations/024_enterprise_programme_foundation.sql:208`, `migrations/024_enterprise_programme_foundation.sql:228`, `migrations/024_enterprise_programme_foundation.sql:250`, `migrations/024_enterprise_programme_foundation.sql:415`, `migrations/024_enterprise_programme_foundation.sql:416`, `migrations/024_enterprise_programme_foundation.sql:417`). It should be superseded in place, not destructively removed before migration.

## Repository Placement

New implementation files:

| Layer | Path |
|---|---|
| Blueprint registration seam | `enterprise_programme_routes.py` continues exporting `register_enterprise_programme(app, get_db, csrf)` because `wsgi.py` already imports and calls it (`wsgi.py:29`, `wsgi.py:32`) and C1 forbids editing `web_app.py`. |
| Domain constants | `app/enterprise_programme/constants.py` |
| Repository | `app/enterprise_programme/repository.py` |
| Tenancy service | `app/enterprise_programme/tenancy.py` |
| RBAC service | `app/enterprise_programme/rbac.py` |
| Workflow service | `app/enterprise_programme/workflows.py` |
| Gate predicates | `app/enterprise_programme/gates.py` |
| Template service | `app/enterprise_programme/templates.py` |
| Beneficiary/import service | `app/enterprise_programme/beneficiaries.py` |
| Project-generation adapters | `app/enterprise_programme/project_generation.py` |
| BOQ/procurement adapter | `app/enterprise_programme/procurement.py` |
| Funding adapter | `app/enterprise_programme/funding.py` |
| Reporting adapter | `app/enterprise_programme/reports.py` |
| AI recommendation adapter | `app/enterprise_programme/ai_recommendations.py` |
| Queue service | `app/enterprise_programme/jobs.py` |
| Observability helpers | `app/enterprise_programme/observability.py` |
| HTML templates | `templates/enterprise_programme/*.html` |
| Static assets | `static/enterprise_programme/*` |
| Migration | `migrations/025_enterprise_programme_rebuild.sql` and follow-on slice migrations |
| Tests | `tests/enterprise_programme/*` |

The implementation must not edit `web_app.py`, `api_manager.py`, or `start*.py`. Existing standard design behaviour is reused through adapters around current functions such as `_run_project_design` (`web_app.py:37906`) and calculation functions (`web_app.py:1264`, `web_app.py:1280`, `web_app.py:1298`, `web_app.py:1330`, `web_app.py:1775`). Existing generation-station behaviour is reused through adapters around `new_capital_investment_routes.py`, including `size_utility_pv` (`new_capital_investment_routes.py:388`), `_ci_yield_profile` (`new_capital_investment_routes.py:478`), and Step 9 BOQ creation (`new_capital_investment_routes.py:320`, `new_capital_investment_routes.py:2292`).

## Domain Model

All new enterprise tables carry `tenant_id uuid not null`, `created_at`, `updated_at`, `created_by_user_id`, and, where mutable, `updated_by_user_id`. Every table with tenant data gets `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, and policies based on enterprise membership plus `current_setting('app.current_tenant', true)`. Migration 024 proves RLS policy style already exists for enterprise tables (`migrations/024_enterprise_programme_foundation.sql:333`, `migrations/024_enterprise_programme_foundation.sql:350`, `migrations/024_enterprise_programme_foundation.sql:366`, `migrations/024_enterprise_programme_foundation.sql:396`).

### Tenancy and Organisation Tables

| Table | Columns | Keys and indexes |
|---|---|---|
| `enterprise_tenants` | `id uuid`, `legacy_user_id integer null`, `slug text`, `legal_name text`, `display_name text`, `organisation_type text`, `country text`, `default_currency text`, `default_timezone text`, `unit_system text`, `branding_json jsonb`, `status text`, timestamps | PK `id`; unique `slug`; unique `legacy_user_id` where not null; index `(status)` |
| `enterprise_departments` | `id bigserial`, `tenant_id uuid`, `parent_department_id bigint null`, `name text`, `department_type text`, `region_code text null`, `district_code text null`, `status text` | PK `id`; FK tenant; FK parent; unique `(tenant_id, name)`; indexes `(tenant_id, region_code)`, `(tenant_id, district_code)` |
| `enterprise_memberships` | extend/supersede migration-024 table: `id bigserial`, `tenant_id uuid`, `user_id integer`, `email text`, `status text`, `invited_by_user_id integer`, `joined_at timestamptz` | PK `id`; unique `(tenant_id, user_id)`; indexes `(user_id)`, `(tenant_id, status)` |
| `enterprise_role_assignments` | `id bigserial`, `tenant_id uuid`, `user_id integer`, `role_code text`, `scope_type text`, `scope_id bigint null`, `region_code text null`, `district_code text null`, `starts_at`, `ends_at` | PK; unique active `(tenant_id, user_id, role_code, scope_type, scope_id)`; indexes `(tenant_id, user_id)`, `(tenant_id, role_code)`, `(tenant_id, region_code, district_code)` |
| `enterprise_permission_overrides` | `id bigserial`, `tenant_id uuid`, `role_code text`, `permission_code text`, `effect text check in ('allow','deny')` | PK; unique `(tenant_id, role_code, permission_code)` |

### Programme Core Tables

| Table | Columns | Keys and indexes |
|---|---|---|
| `enterprise_programmes` | extend/supersede old table (`migrations/024_enterprise_programme_foundation.sql:140`): `id bigserial`, `tenant_id uuid`, `programme_code text`, `name text`, `programme_type_id bigint`, `description text`, `sponsor_membership_id bigint`, `owner_department_id bigint`, `managing_department_id bigint`, `countries text[]`, `start_date date`, `target_completion_date date`, `budget_amount numeric`, `currency text`, `delivery_model text`, `procurement_strategy text`, `contract_framework text`, `design_strategy text check in ('standard','generation_station','mixed')`, `risk_classification text`, `programme_status text`, `current_phase_code text`, `archive_status text`, `approved_sponsor_at timestamptz null` | PK; unique `(tenant_id, programme_code)`; indexes `(tenant_id, programme_status)`, `(tenant_id, current_phase_code)`, `(tenant_id, programme_type_id)`, GIN `(countries)` |
| `enterprise_programme_types` | `id bigserial`, `tenant_id uuid null`, `code text`, `name text`, `sector text`, `description text`, `active boolean` | PK; unique `(tenant_id, code)` with global rows where tenant null; indexes `(sector, active)` |
| `enterprise_programme_phases` | `id bigserial`, `tenant_id uuid`, `programme_id bigint`, `phase_code text`, `sequence_no int`, `name text`, `status text`, `planned_start`, `planned_finish`, `actual_start`, `actual_finish`, `gate_id bigint null` | PK; FK programme; unique `(tenant_id, programme_id, phase_code)`; indexes `(tenant_id, programme_id, sequence_no)`, `(tenant_id, status)` |
| `enterprise_geographic_areas` | `id bigserial`, `tenant_id uuid`, `programme_id bigint`, `parent_area_id bigint null`, `area_type text`, `country_code text`, `region_code text`, `district_code text`, `name text`, `geometry_json jsonb null` | PK; FK programme; indexes `(tenant_id, programme_id, area_type)`, `(tenant_id, region_code, district_code)` |
| `enterprise_sites` | `id bigserial`, `tenant_id uuid`, `programme_id bigint`, `geographic_area_id bigint`, `beneficiary_id bigint null`, `site_code text`, `name text`, `latitude numeric`, `longitude numeric`, `site_type text`, `grid_connection text`, `land_status text`, `status text` | PK; unique `(tenant_id, programme_id, site_code)`; indexes `(tenant_id, programme_id, status)`, `(tenant_id, latitude, longitude)` |

### Template and Standardisation Tables

| Table | Columns | Keys and indexes |
|---|---|---|
| `enterprise_programme_templates` | `id bigserial`, `tenant_id uuid`, `template_code text`, `name text`, `programme_type_id bigint`, `beneficiary_type text`, `design_strategy text`, `status text`, `current_version_id bigint null` | PK; unique `(tenant_id, template_code)`; indexes `(tenant_id, status)`, `(tenant_id, design_strategy)` |
| `enterprise_template_versions` | `id bigserial`, `tenant_id uuid`, `template_id bigint`, `version_no int`, `status text check in ('Draft','Review','Approved','Published','Superseded','Archived')`, `load_profile_json jsonb`, `pv_capacity_kw numeric`, `battery_capacity_kwh numeric`, `equipment_json jsonb`, `boq_snapshot_json jsonb`, `drawings_json jsonb`, `reports_json jsonb`, `approval_workflow_id bigint`, `approved_at timestamptz null`, `approved_by_user_id integer null` | PK; unique `(tenant_id, template_id, version_no)`; indexes `(tenant_id, template_id, status)`, `(tenant_id, approved_at)` |
| `enterprise_template_documents` | `id bigserial`, `tenant_id uuid`, `template_version_id bigint`, `document_type text`, `storage_ref text`, `required_for_gate text`, `status text` | PK; indexes `(tenant_id, template_version_id, document_type)` |
| `enterprise_template_equipment_options` | `id bigserial`, `tenant_id uuid`, `template_version_id bigint`, `catalog_item_id bigint null`, `equipment_category text`, `is_primary boolean`, `substitution_rule text`, `approval_status text` | PK; indexes `(tenant_id, template_version_id, equipment_category)`, `(catalog_item_id)` |

The project generator only accepts `enterprise_template_versions.status in ('Approved','Published')`. This enforces doc-3 Gate 6, which says only approved template versions may generate programme projects (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:400`).

### Beneficiary, Qualification, and Project Link Tables

| Table | Columns | Keys and indexes |
|---|---|---|
| `enterprise_beneficiaries` | extend/supersede old table (`migrations/024_enterprise_programme_foundation.sql:179`): `id bigserial`, `tenant_id uuid`, `programme_id bigint`, `beneficiary_code text`, `beneficiary_type text`, `name text`, `institution_type text`, `region_code text`, `district_code text`, `community text`, `latitude numeric`, `longitude numeric`, `electricity_consumption_kwh numeric`, `generator_fuel_liters numeric`, `roof_area_m2 numeric`, `land_area_m2 numeric`, `priority_rank int`, `funding_eligibility text`, `status text`, `qualification_status text`, `assigned_template_version_id bigint null` | PK; unique `(tenant_id, programme_id, beneficiary_code)`; indexes `(tenant_id, programme_id, status)`, `(tenant_id, qualification_status)`, `(tenant_id, region_code, district_code)`, `(tenant_id, assigned_template_version_id)` |
| `enterprise_beneficiary_imports` | `id bigserial`, `tenant_id uuid`, `programme_id bigint`, `source_type text`, `source_filename text`, `status text`, `row_count int`, `valid_count int`, `invalid_count int`, `idempotency_key text`, `created_by_user_id integer` | PK; unique `(tenant_id, programme_id, idempotency_key)`; indexes `(tenant_id, programme_id, status)` |
| `enterprise_beneficiary_import_rows` | `id bigserial`, `tenant_id uuid`, `import_id bigint`, `row_no int`, `raw_json jsonb`, `normalised_json jsonb`, `validation_status text`, `error_json jsonb`, `beneficiary_id bigint null` | PK; unique `(tenant_id, import_id, row_no)`; indexes `(tenant_id, import_id, validation_status)` |
| `enterprise_site_qualifications` | `id bigserial`, `tenant_id uuid`, `beneficiary_id bigint`, `site_id bigint null`, `status text`, `technical_score numeric`, `energy_need_score numeric`, `financial_score numeric`, `social_impact_score numeric`, `implementation_readiness_score numeric`, `security_risk_score numeric`, `environmental_risk_score numeric`, `funding_eligibility_score numeric`, `overall_priority_score numeric`, `approved_at timestamptz null`, `approved_by_user_id integer null` | PK; unique current `(tenant_id, beneficiary_id)`; indexes `(tenant_id, status)`, `(tenant_id, overall_priority_score desc)` |
| `enterprise_project_links` | extend/supersede old project links (`migrations/024_enterprise_programme_foundation.sql:208`): `id bigserial`, `tenant_id uuid`, `programme_id bigint`, `phase_id bigint`, `beneficiary_id bigint`, `template_version_id bigint`, `site_qualification_id bigint`, `source_project_kind text check in ('standard','generation_station')`, `source_project_id integer`, `source_project_user_id integer`, `source_project_tenant_id uuid null`, `project_status text`, `generation_job_id bigint null`, `traceability_hash text` | PK; unique `(tenant_id, programme_id, beneficiary_id, template_version_id)`; indexes `(tenant_id, programme_id, project_status)`, `(source_project_kind, source_project_id, source_project_user_id)`, `(tenant_id, template_version_id)` |

Existing source project ownership stays unchanged. Enterprise users do not get direct access to another user’s `projects` or `capital_investment_projects`; they access enterprise-visible programme links after RBAC and tenant checks. Drill-through to the native project page is allowed only when either the current user owns the source project or the programme grants a controlled enterprise project-access delegation recorded in `enterprise_project_access_grants`.

### Gate, Workflow, Approval, and Document Tables

| Table | Columns | Keys and indexes |
|---|---|---|
| `enterprise_workflow_definitions` | `id bigserial`, `tenant_id uuid null`, `workflow_code text`, `name text`, `version_no int`, `status text`, `definition_json jsonb` | PK; unique `(tenant_id, workflow_code, version_no)`; indexes `(workflow_code, status)` |
| `enterprise_workflow_instances` | `id bigserial`, `tenant_id uuid`, `workflow_definition_id bigint`, `subject_type text`, `subject_id bigint`, `current_state text`, `status text` | PK; unique active `(tenant_id, subject_type, subject_id, workflow_definition_id)`; indexes `(tenant_id, current_state)`, `(tenant_id, subject_type, subject_id)` |
| `enterprise_workflow_transitions` | `id bigserial`, `tenant_id uuid`, `workflow_instance_id bigint`, `from_state text`, `to_state text`, `transition_code text`, `requested_by_user_id integer`, `approved_by_user_id integer null`, `guard_result_json jsonb`, `created_at` | PK; indexes `(tenant_id, workflow_instance_id, created_at)`, `(tenant_id, transition_code)` |
| `enterprise_stage_gates` | `id bigserial`, `tenant_id uuid`, `programme_id bigint`, `gate_code text`, `phase_code text`, `name text`, `approving_authority text`, `status text`, `entry_conditions_json jsonb`, `exit_conditions_json jsonb`, `blocked_actions text[]`, `opened_at`, `approved_at`, `approved_by_user_id` | PK; unique `(tenant_id, programme_id, gate_code)`; indexes `(tenant_id, programme_id, status)`, `(tenant_id, gate_code, status)` |
| `enterprise_approvals` | `id bigserial`, `tenant_id uuid`, `subject_type text`, `subject_id bigint`, `approval_type text`, `required_role_code text`, `status text check in ('Pending','Approved','Rejected','Returned','Withdrawn')`, `decision_by_user_id integer null`, `decision_at timestamptz null`, `decision_comment text`, `ai_recommendation_id bigint null` | PK; indexes `(tenant_id, subject_type, subject_id, status)`, `(tenant_id, required_role_code, status)` |
| `enterprise_documents` | `id bigserial`, `tenant_id uuid`, `programme_id bigint`, `subject_type text`, `subject_id bigint`, `document_type text`, `title text`, `storage_ref text`, `status text`, `required_for_gate text null`, `uploaded_by_user_id integer` | PK; indexes `(tenant_id, programme_id, document_type)`, `(tenant_id, subject_type, subject_id)`, `(tenant_id, required_for_gate, status)` |

### Funding, Procurement, EPC, Contract, Logistics, Construction, Commissioning, O&M

| Table | Columns | Keys and indexes |
|---|---|---|
| `enterprise_funding_facilities` | `id bigserial`, `tenant_id uuid`, `programme_id bigint`, `source_type text`, `institution_id text null`, `amount numeric`, `currency text`, `status text`, `conditions_json jsonb` | PK; indexes `(tenant_id, programme_id, status)`, `(institution_id)` |
| `enterprise_funding_allocations` | `id bigserial`, `tenant_id uuid`, `facility_id bigint`, `programme_id bigint`, `phase_id bigint null`, `project_link_id bigint null`, `amount numeric`, `status text` | PK; indexes `(tenant_id, facility_id)`, `(tenant_id, project_link_id)` |
| `enterprise_boq_approvals` | `id bigserial`, `tenant_id uuid`, `project_link_id bigint`, `source_boq_kind text`, `source_boq_id bigint`, `source_snapshot_hash text`, `status text`, `approved_at`, `approved_by_user_id` | PK; unique approved `(tenant_id, project_link_id, source_snapshot_hash)`; indexes `(tenant_id, status)` |
| `enterprise_procurement_packages` | `id bigserial`, `tenant_id uuid`, `programme_id bigint`, `package_code text`, `package_type text`, `region_code text null`, `phase_id bigint null`, `status text`, `approved_boq_required boolean` | PK; unique `(tenant_id, programme_id, package_code)`; indexes `(tenant_id, programme_id, status)`, `(tenant_id, package_type)` |
| `enterprise_consolidated_boq_lines` | `id bigserial`, `tenant_id uuid`, `procurement_package_id bigint`, `catalog_item_id bigint null`, `description text`, `unit text`, `quantity numeric`, `estimated_rate numeric`, `estimated_amount numeric`, `approval_status text` | PK; indexes `(tenant_id, procurement_package_id)`, `(catalog_item_id)` |
| `enterprise_consolidated_boq_sources` | `id bigserial`, `tenant_id uuid`, `consolidated_line_id bigint`, `project_link_id bigint`, `source_boq_kind text`, `source_boq_line_id bigint`, `source_qty numeric` | PK; indexes `(tenant_id, consolidated_line_id)`, `(tenant_id, project_link_id)` |
| `enterprise_epc_packages` | `id bigserial`, `tenant_id uuid`, `programme_id bigint`, `procurement_package_id bigint null`, `package_code text`, `delivery_model text`, `contractor_membership_id bigint null`, `status text` | PK; unique `(tenant_id, programme_id, package_code)`; indexes `(tenant_id, status)` |
| `enterprise_contracts` | `id bigserial`, `tenant_id uuid`, `epc_package_id bigint`, `contract_code text`, `fidic_form text`, `contractor_name text`, `contract_value numeric`, `currency text`, `status text`, `executed_at`, `ntp_issued_at` | PK; unique `(tenant_id, contract_code)`; indexes `(tenant_id, epc_package_id, status)` |
| `enterprise_contract_events` | `id bigserial`, `tenant_id uuid`, `contract_id bigint`, `event_type text`, `event_status text`, `amount numeric null`, `notice_date date`, `payload_json jsonb` | PK; indexes `(tenant_id, contract_id, event_type)`, `(tenant_id, event_status)` |
| `enterprise_warehouses` | `id bigserial`, `tenant_id uuid`, `programme_id bigint`, `warehouse_code text`, `name text`, `region_code text`, `district_code text`, `status text` | PK; unique `(tenant_id, programme_id, warehouse_code)` |
| `enterprise_inventory_items` | `id bigserial`, `tenant_id uuid`, `warehouse_id bigint`, `catalog_item_id bigint null`, `serial_no text null`, `qr_code text null`, `quantity numeric`, `status text` | PK; indexes `(tenant_id, warehouse_id, status)`, `(tenant_id, serial_no)` |
| `enterprise_stock_movements` | `id bigserial`, `tenant_id uuid`, `inventory_item_id bigint`, `movement_type text`, `quantity numeric`, `from_warehouse_id bigint null`, `to_warehouse_id bigint null`, `project_link_id bigint null`, `status text` | PK; indexes `(tenant_id, inventory_item_id)`, `(tenant_id, project_link_id)` |
| `enterprise_construction_reports` | `id bigserial`, `tenant_id uuid`, `project_link_id bigint`, `report_date date`, `progress_pct numeric`, `quality_status text`, `safety_status text`, `weather_status text`, `status text` | PK; unique `(tenant_id, project_link_id, report_date)` |
| `enterprise_inspection_tests` | `id bigserial`, `tenant_id uuid`, `project_link_id bigint`, `test_type text`, `required boolean`, `result text`, `tested_at`, `tested_by_user_id`, `evidence_document_id bigint null` | PK; indexes `(tenant_id, project_link_id, test_type)`, `(tenant_id, result)` |
| `enterprise_commissioning_certificates` | `id bigserial`, `tenant_id uuid`, `project_link_id bigint`, `certificate_no text`, `status text`, `issued_at`, `issued_by_user_id` | PK; unique `(tenant_id, certificate_no)` |
| `enterprise_assets` | `id bigserial`, `tenant_id uuid`, `project_link_id bigint`, `asset_code text`, `asset_type text`, `catalog_item_id bigint null`, `serial_no text null`, `status text`, `handover_status text` | PK; unique `(tenant_id, asset_code)`; indexes `(tenant_id, project_link_id)`, `(tenant_id, asset_type, status)` |
| `enterprise_telemetry_sources` | `id bigserial`, `tenant_id uuid`, `asset_id bigint`, `source_type text`, `provider text`, `source_ref text`, `status text`, `last_seen_at` | PK; indexes `(tenant_id, asset_id, status)` |
| `enterprise_kpi_definitions` | `id bigserial`, `tenant_id uuid`, `programme_id bigint`, `kpi_code text`, `name text`, `source_type text`, `calculation_json jsonb`, `requires_data_source boolean`, `status text` | PK; unique `(tenant_id, programme_id, kpi_code)` |
| `enterprise_kpi_observations` | `id bigserial`, `tenant_id uuid`, `kpi_definition_id bigint`, `period_start date`, `period_end date`, `value numeric`, `data_source_id bigint null`, `status text` | PK; indexes `(tenant_id, kpi_definition_id, period_end)` |

## Enterprise Tenancy Resolution

C2 is CONFIRMED. The current application is single-user-owned for standard and generation-station projects (`web_app.py:1045`, `new_capital_investment_routes.py:6325`). The current tenant id is a deterministic user hash, not an organisation (`migrations/003_rls_tenant.sql:136`). Migration 001 dropped `organizations` and says there is no organisations table (`migrations/001_mirror_sqlite.sql:20`, `migrations/001_mirror_sqlite.sql:44`).

### Recommendation

Introduce true enterprise organisations for the enterprise module without changing existing project ownership. Existing projects remain owned by `user_id`. Enterprise tenancy becomes an overlay:

1. `enterprise_tenants.id` is the enterprise organisation tenant id.
2. Every existing user gets a default personal enterprise tenant during migration.
3. That default tenant id equals the existing `md5('solarpro-tenant-v1:' || user_id)::uuid`.
4. Existing user projects do not move, and their `WHERE id=? AND user_id=?` protections remain unchanged.
5. Multi-user organisations are created as additional `enterprise_tenants` rows with independent UUIDs.
6. Projects enter an enterprise programme only through `enterprise_project_links`, which records source owner, source project id, source tenant id, beneficiary, template version, and approval lineage.
7. Organisation users get programme access through `enterprise_memberships` and `enterprise_role_assignments`, not by changing `projects.user_id`.

### Exact Migration Path

1. Add `enterprise_tenants` and `enterprise_memberships_v2` columns in `migrations/025_enterprise_programme_rebuild.sql`.
2. For every existing user row, insert a personal tenant with:
   - `id = md5('solarpro-tenant-v1:' || users.id::text)::uuid`
   - `legacy_user_id = users.id`
   - `legal_name = COALESCE(users.name, users.email, 'Personal Workspace ' || users.id)`
   - `status = 'active'`
3. Backfill old `enterprise_organisations` rows from migration 024 into `enterprise_tenants`:
   - if the old organisation belongs to one user and matches the deterministic personal tenant, map it to that personal tenant;
   - otherwise create a new organisation tenant and preserve old row id in a migration mapping table.
4. Backfill old `enterprise_memberships` into the new membership shape, preserving `user_id`, role/status, and old organisation mapping.
5. Add `tenant_id` to old enterprise tables where needed and backfill from the mapping table.
6. Create `enterprise_project_links` from old `enterprise_programme_project_links`, preserving source project kind and source project id.
7. Do not update `projects.user_id` or `capital_investment_projects.user_id`.
8. Leave old deterministic personal tenant ids valid forever for backward compatibility.
9. New organisations use generated UUIDs and can contain many users.
10. A later cleanup migration may rename retired old tables only after live row counts and export validation.

What happens to `tenant_id = md5('solarpro-tenant-v1:'||user_id)`: it becomes the stable id of each user’s personal enterprise tenant. It is no longer treated as the only tenancy model, but it remains valid for legacy rows and personal workspaces.

## RBAC

The existing Keycloak/session decorator layer already provides JWT, role, scope, and tenant checks (`app/security/decorators.py:129`, `app/security/decorators.py:163`, `app/security/decorators.py:181`, `app/security/decorators.py:221`, `app/security/decorators.py:241`). The enterprise module must layer domain RBAC on top of that, not create a second authentication system.

Implementation:

1. Route entry remains protected by Flask login/session where the existing UI uses it and by existing Keycloak decorators for API endpoints.
2. `app/enterprise_programme/rbac.py::require_enterprise_permission(permission, subject)` runs after authentication.
3. The RBAC service resolves `current_user_id`, `tenant_id`, roles, region/district scope, programme scope, and denied overrides.
4. Permission checks are mandatory in services and not only decorators, so background jobs and API calls cannot bypass them.
5. Platform support access requires the existing platform role plus an auditable support reason. `platform_super_admin` bypass is already special-cased only for tenant match in the existing decorator (`app/security/decorators.py:256`), so enterprise support access must still write audit rows.

The master prompt section 11 source list contains 37 role labels (`docs/enterprise-programme/source/01-master-prompt.txt:481`, `docs/enterprise-programme/source/01-master-prompt.txt:485`). Doc 3’s approval chain adds `Finance Manager` (`docs/enterprise-programme/source/02-lifecycle-workflows.txt:1149`). The implementation should seed all 37 prompt roles plus the Finance Manager approval alias, for 38 operational roles.

Permission groups:

| Code | Meaning |
|---|---|
| `tenant.admin` | organisation profile, departments, invitations, branding |
| `programme.create` | create programme |
| `programme.edit` | edit programme setup |
| `programme.approve` | approve programme/gates |
| `template.manage` | create/edit templates |
| `template.approve` | approve/publish template versions |
| `beneficiary.import` | import beneficiaries |
| `beneficiary.approve` | approve beneficiaries and qualification |
| `design.generate` | request project/design generation |
| `engineering.approve` | approve designs and construction release |
| `funding.manage` | funding facilities and allocations |
| `procurement.manage` | BOQ consolidation, tender/procurement packages |
| `contract.manage` | EPC/FIDIC contract administration |
| `payment.certify` | payment certificates |
| `variation.approve` | contract variations/claims |
| `inspection.approve` | inspection approvals |
| `commissioning.approve` | commissioning/taking-over |
| `operations.manage` | O&M, telemetry, assets |
| `report.generate` | reports and exports |
| `audit.view` | audit trail |
| `cross_region.view` | all-region read |
| `cross_programme.view` | multi-programme read |
| `ai.recommend` | run AI recommendation jobs, never approve |

Role matrix:

| Role | Permission profile |
|---|---|
| Enterprise Owner | all tenant permissions except platform support internals |
| Organisation Administrator | `tenant.admin`, broad read, user/role management, not technical/financial approvals unless separately assigned |
| Programme Sponsor | `programme.approve`, gate 1/4/14 authority, executive reports |
| Programme Director | programme edit/approve, cross-region, gate authority, reports |
| Programme Manager | programme edit, workflow coordination, beneficiary/design/procurement read, reports |
| Technical Director | engineering approvals, template approval, technical gates |
| Programme Engineer | technical edits, qualification review, design package preparation |
| Design Engineer | template/design work, project generation preparation, no approval unless assigned |
| Regional Manager | region-scoped programme/project read/edit and regional approvals |
| District Coordinator | district-scoped beneficiary/site/construction coordination |
| Beneficiary Officer | beneficiary import, validation, duplicate handling, beneficiary review |
| Surveyor | site data, survey records, qualification inputs |
| GIS Specialist | GIS imports, map data, geographic areas |
| Funding Manager | funding facilities, allocations, funding gate recommendations |
| Finance Manager | funding approval workflow authority from doc 3 |
| Finance Officer | funding records, disbursement evidence, financial reports |
| Procurement Manager | BOQ consolidation, procurement packages, tender workflow |
| Contract Manager | contracts, notices, contract records |
| FIDIC Engineer | engineer instructions, variations, claims, certificates |
| EPC Contractor Administrator | contractor package administration for assigned packages only |
| EPC Project Manager | assigned package delivery, submittals, progress |
| Site Engineer | assigned site engineering and construction records |
| Site Supervisor | daily reports, readiness evidence, site progress |
| Warehouse Manager | warehouse and inventory |
| Logistics Officer | deliveries, dispatch, receipt |
| QA/QC Manager | quality records, NCRs, construction completion recommendation |
| Inspector | inspections and test evidence |
| Commissioning Engineer | commissioning tests and certificates |
| Operations Manager | O&M, asset operations, KPI review |
| Maintenance Engineer | maintenance records, fault closure |
| Monitoring Operator | telemetry monitoring and alarm triage |
| ESG and Carbon Officer | ESG/carbon KPI definitions and reports |
| Auditor | audit read, evidence read, no mutation except audit notes |
| Financier Viewer | scoped funding/programme read |
| Donor Viewer | scoped reports and programme KPI read |
| Executive Viewer | dashboard/report read |
| Beneficiary Representative | own beneficiary/project status and handover docs only |
| Platform Support Administrator | support-scoped cross-tenant read/write only with platform role, reason, and audit |

## Background Processing Under C3

C3 is CONFIRMED. Celery exists (`tasks/celery_app.py:17`; tasks in `tasks/report_tasks.py:21`, `tasks/ai_tasks.py:18`, `tasks/email_tasks.py:19`), but the old enterprise job module states Celery is not imported or dispatched for enterprise work and no worker process is deployed (`enterprise_programme_jobs.py:6`, `enterprise_programme_jobs.py:8`, `enterprise_programme_jobs.py:9`). Render runtime is a web command, not a durable worker. The Render best-practice workflow states the Procfile is ignored once a start command exists and sets one gthread worker with four threads (`.github/workflows/render-apply-best-practices.yml:3`, `.github/workflows/render-apply-best-practices.yml:18`, `.github/workflows/render-apply-best-practices.yml:53`). The old enterprise `tick` helper can fail claimed jobs because it is a placeholder (`enterprise_programme_jobs.py:185`, `enterprise_programme_jobs.py:189`).

### Mechanism

Use a Postgres durable queue in `enterprise_jobs` with explicit worker modes:

| Mode | Purpose |
|---|---|
| Web request | only creates jobs and shows status; never generates thousands of projects synchronously |
| Admin/manual worker route | guarded route claims one small batch for emergency/manual processing |
| Render worker service or Render cron | recommended production worker calling `python -m app.enterprise_programme.worker --once` or `--loop` |
| Celery future adapter | allowed only after a real worker deployment is verified |

Queue columns: `id`, `tenant_id`, `job_type`, `status`, `priority`, `payload_json`, `idempotency_key`, `progress_current`, `progress_total`, `attempt_count`, `max_attempts`, `locked_by`, `locked_at`, `last_error`, `dead_letter_at`, `cancel_requested_at`, timestamps.

Claim SQL uses `FOR UPDATE SKIP LOCKED` on Postgres. Each job runs in chunks and commits progress after each beneficiary/project/package batch. Idempotency keys prevent duplicate imports, duplicate project generation, duplicate BOQ aggregation, and duplicate report creation.

### Failure Modes and UI Text

| Failure mode | Handling | UI message |
|---|---|---|
| No worker configured | Job remains `queued`; dashboard shows queue age and worker status | “Queued. No enterprise worker is currently running, so this job will not start automatically. Ask an administrator to start the worker or run a manual batch.” |
| Worker crashes mid-batch | Lock expires; next worker retries remaining idempotent chunk | “Retry pending after worker interruption. Completed rows remain saved.” |
| Max attempts reached | Job becomes `failed` with `last_error` and retry action | “Failed after retries. Review errors, correct data, and retry.” |
| Validation errors in import | Job completes with partial invalid rows | “Import completed with row errors. Valid rows were staged; invalid rows need correction.” |
| User cancels | Worker checks `cancel_requested_at` between chunks | “Cancellation requested. Current chunk will finish, then processing stops.” |
| Duplicate job submit | Existing job returned by idempotency key | “A matching job already exists. Showing existing progress.” |

## API Surface

Use `enterprise_programme_routes.py` as the blueprint entry, with services in `app/enterprise_programme`. Existing old routes are simple HTML pages under `/enterprise` (`enterprise_programme_routes.py:102`, `enterprise_programme_routes.py:151`, `enterprise_programme_routes.py:213`, `enterprise_programme_routes.py:299`, `enterprise_programme_routes.py:385`, `enterprise_programme_routes.py:462`); replace their internals while preserving the route namespace.

API groups:

| Route group | Purpose |
|---|---|
| `GET /enterprise` | command dashboard |
| `GET/POST /enterprise/onboarding` | organisation setup and invitations |
| `GET/POST /enterprise/programmes` | programme registry |
| `GET/POST /enterprise/programmes/<id>/setup` | programme setup |
| `GET/POST /enterprise/programmes/<id>/lifecycle` | phases/gates/state |
| `POST /enterprise/programmes/<id>/transition` | guarded workflow transition |
| `GET/POST /enterprise/templates` | template library |
| `POST /enterprise/templates/<id>/versions/<vid>/submit-review` | template review |
| `POST /enterprise/templates/<id>/versions/<vid>/approve` | template approval |
| `GET/POST /enterprise/programmes/<id>/beneficiaries` | beneficiaries |
| `POST /enterprise/programmes/<id>/beneficiaries/import` | import job |
| `POST /enterprise/beneficiaries/<id>/qualify` | qualification |
| `POST /enterprise/beneficiaries/<id>/approve` | human approval |
| `POST /enterprise/programmes/<id>/generate-projects` | queue generation |
| `GET /enterprise/jobs/<id>` | job status |
| `POST /enterprise/programmes/<id>/boq/consolidate` | queue/perform BOQ aggregation |
| `POST /enterprise/programmes/<id>/procurement-packages` | procurement package creation with guards |
| `GET/POST /enterprise/programmes/<id>/funding` | funding facilities and allocations |
| `GET/POST /enterprise/programmes/<id>/epc` | EPC packages |
| `GET/POST /enterprise/contracts` | FIDIC contracts |
| `GET/POST /enterprise/construction` | construction records |
| `GET/POST /enterprise/commissioning` | test/certificate records |
| `GET /enterprise/programmes/<id>/operations` | operations centre |
| `GET /enterprise/programmes/<id>/gis` | portfolio map |
| `GET /enterprise/programmes/<id>/reports` | report list/export |
| `GET /enterprise/programmes/<id>/audit` | audit trail |

Every mutating route requires CSRF, permission check, tenant scoping, validation, idempotency where applicable, and audit logging.

## Frontend Surface

The old module uses seven templates (`enterprise_programme_routes.py:113`, `enterprise_programme_routes.py:119`, `enterprise_programme_routes.py:166`, `enterprise_programme_routes.py:199`, `enterprise_programme_routes.py:225`, `enterprise_programme_routes.py:319`, `enterprise_programme_routes.py:402`). Replace them with a command-centre experience under `templates/enterprise_programme/`:

| View | Template |
|---|---|
| Dashboard | `dashboard.html` |
| Onboarding | `onboarding.html` |
| Programme registry | `programmes_list.html` |
| Programme workspace shell | `programme_workspace.html` |
| Lifecycle and gates | `lifecycle.html` |
| Templates | `templates.html`, `template_version.html` |
| Beneficiaries/import | `beneficiaries.html`, `beneficiary_import.html` |
| Site qualification | `site_qualification.html` |
| Project generation | `project_generation.html` |
| Funding | `funding.html` |
| BOQ/procurement | `procurement.html` |
| EPC/FIDIC | `contracts.html` |
| Logistics | `logistics.html` |
| Construction | `construction.html` |
| Inspection/commissioning | `commissioning.html` |
| O&M/assets | `operations.html`, `assets.html` |
| GIS | `gis.html` |
| Reports | `reports.html` |
| Audit | `audit.html` |

Large tables use server-side pagination. Dropdowns come from seeded lifecycle/status/gate tables, `config/ghana_regions.py`, generation-station option constants (`new_capital_investment_routes.py:67`, `new_capital_investment_routes.py:78`, `new_capital_investment_routes.py:188`, `new_capital_investment_routes.py:253`), marketplace categories and equipment (`web_app.py:37367`, `web_app.py:37378`, `new_marketplace_procurement_center_routes.py:129`, `new_marketplace_procurement_center_routes.py:144`, `new_marketplace_procurement_center_routes.py:157`), and funding institutions (`new_capital_investment_routes.py:8629`, `new_capital_investment_routes.py:8708`).

## Observability

Use structured logs through `app/enterprise_programme/observability.py` with `tenant_id`, `programme_id`, `job_id`, `workflow_instance_id`, `gate_code`, and `request_id`. The existing audit chain supports tenant and hash-chain fields (`app/security/audit.py:233`, `app/security/audit.py:243`, `app/security/audit.py:299`, `app/security/audit.py:418`).

Metrics/events to capture:

| Event | Fields |
|---|---|
| API denial | tenant, user, permission, subject |
| Gate transition | tenant, programme, gate, from/to, guard result |
| Import row failures | tenant, programme, import id, error code |
| Project generation failure | tenant, beneficiary, template, source engine |
| Queue health | queue depth, oldest queued age, worker heartbeat |
| Dashboard latency | tenant, programme, query group, duration |
| Report generation | tenant, report type, duration, status |
| AI recommendation | tenant, recommendation type, token/cost metadata, approval status |
| RLS/IDOR violation | attempted subject, actor, tenant, route |

## Deployment on Render

Use the existing Render/GitHub workflow style. Render start command is controlled through workflows rather than Procfile (`.github/workflows/render-apply-best-practices.yml:3`, `.github/workflows/update-render-start-command.yml:3`). The web service command should remain the current gunicorn gthread command (`.github/workflows/render-apply-best-practices.yml:53`).

Deployment sequence:

1. Backup production database.
2. Apply migration dry run against staging.
3. Apply `migrations/025_enterprise_programme_rebuild.sql`.
4. Keep `enterprise_programme_enabled=0`.
5. Deploy app code.
6. Run tests and smoke checks.
7. Enable for pilot tenants only through entitlement.
8. Add Render worker/cron only before enabling imports/generation at scale.
9. Monitor queue depth, gate denials, and errors.
10. Broaden flag gradually.

Migration seed writes to `admin_settings` must set admin role inside the transaction, as migration 024 shows (`migrations/024_enterprise_programme_foundation.sql:412`, `migrations/024_enterprise_programme_foundation.sql:415`).

## Rollback

Preferred rollback is feature-flag rollback:

| Failure | Rollback |
|---|---|
| UI defect | set `enterprise_programme_enabled=0` |
| job defect | set `enterprise_programme_jobs_enabled=0`; queued jobs remain durable |
| AI defect | set `enterprise_programme_ai_enabled=0` |
| migration defect before data use | restore backup or run reverse migration |
| bad template | mark template version `Archived` or `Superseded`; existing generated links retain old version |
| bad import | mark import cancelled/void; staged rows remain traceable |
| bad project-generation batch | cancel job; generated project links remain marked failed/void, source projects are not deleted automatically |
| bad procurement consolidation | void package and regenerate from source approved BOQ lines |
| bad KPI calculation | invalidate observations and recalculate; approved programme baselines remain separate |
| release defect | redeploy previous app version and keep flags off |

No rollback deletes existing user projects because source projects remain protected by `user_id` ownership (`web_app.py:1045`, `new_capital_investment_routes.py:6325`).

## Security

### IDOR Prevention

All object loads use `tenant_id` plus subject id, then RBAC scope:

- `repository.get_programme(tenant_id, programme_id)`
- `repository.get_beneficiary(tenant_id, beneficiary_id)`
- `repository.get_template_version(tenant_id, template_version_id)`
- `repository.get_project_link(tenant_id, link_id)`
- `rbac.require_permission(user_id, tenant_id, permission, subject)`

Native project drill-through performs both enterprise-link checks and native owner checks. It never replaces `WHERE id=? AND user_id=?` in standard or generation-station loaders (`web_app.py:1045`, `new_capital_investment_routes.py:6325`).

### RLS Design

RLS policy shape:

1. `app.current_tenant` must be set per request/job.
2. User must be a member of that enterprise tenant.
3. Platform support can access only through explicit support role and audit reason.
4. Region-scoped access is enforced in service predicates, because Postgres cannot know all business scopes without complex policy joins.

SQL functions must be created after referenced tables because Postgres parses `LANGUAGE sql` bodies at create time; migration 024 documents this (`migrations/024_enterprise_programme_foundation.sql:101`, `migrations/024_enterprise_programme_foundation.sql:265`, `migrations/024_enterprise_programme_foundation.sql:274`).

### Audit

Every material action calls `write_audit_event` (`app/security/audit.py:233`) with `tenant_id`, actor, action, subject, before/after summary, request id, and guard result. Hash-chain verification is available through `verify_audit_chain` (`app/security/audit.py:418`). Module-local old audit rows should be migrated or mirrored into the unified audit chain; migration 024’s local enterprise audit table is not enough for the rebuild (`migrations/024_enterprise_programme_foundation.sql:250`).

### AI Safety

All LLM enrichment goes through `api_manager.py::_AIClient.chat()` (`api_manager.py:201`, `api_manager.py:224`, `api_manager.py:898`) and is stored as `enterprise_ai_recommendations` with status `Draft` or `Recommended`. AI cannot write approval rows with `status='Approved'`. Approval mutation requires a human `decision_by_user_id` and cannot use `ai_recommendation_id` as the actor.

