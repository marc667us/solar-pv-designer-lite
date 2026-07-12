# Enterprise Programme Reuse Matrix

| Capability | Existing Module / Entry Point | Classification | Reuse / Change |
|---|---|---:|---|
| Flask app shell | `web_app.py`; production via `wsgi.py` | reuse-with-extension | Register enterprise routes from `wsgi.py`; do not edit `web_app.py`. |
| Dependency-injected module pattern | `web_app.py:1034` calls `register_capital_investment(...)` | reuse-as-pattern | Build `register_enterprise_programme(app, *, get_db, login_required, csrf_protect, current_user)`. |
| Keycloak login | `app/auth/oidc_routes.py:86`, `:632` | reuse-as-is | No second auth system. |
| JWT verification | `app/security/keycloak_middleware.py` `verify_jwt`, `extract_request_context` | reuse-as-is | Enterprise API routes may use decorators where appropriate. |
| Role constants | `app/security/roles.py` `ALL_ROLES` | reuse-with-extension | Map enterprise roles to existing roles first; add constants only if necessary later. |
| Role decorators | `app/security/decorators.py` `require_role`, `require_any_role`, `require_scope` | reuse-with-extension | Use for API/admin routes; browser views can combine existing `login_required` with membership checks. |
| Tenant GUC bridge | `app/security/tenant_context.py:apply_tenant_guc` | reuse-with-extension | Use as defence-in-depth; do not rely on it alone because tenant claim may be missing. |
| DB adapter | `db_adapter.py:229` execute translation, `:142` `_PgCursorWrap` | reuse-with-config | Continue raw SQL `?` style; for new Postgres inserts use `RETURNING id` helper. |
| Feature flags | `new_marketplace_pagination.py:6`, `:28`, `:43`; same helpers in `web_app.py:28876` | reuse-with-extension | Use `admin_settings` keys: `enterprise_programme_enabled`, `enterprise_programme_jobs_enabled`, `enterprise_programme_ai_enabled`. |
| Standard project ownership | `web_app.py:1043` `get_project(pid)` | reuse-as-is | Phase 1 links only projects owned by current user. |
| Standard design sizing | `web_app.py:1264` `calc_loads`; `:1280` `calc_pv`; `:1298` `calc_battery`; `:1330` `calc_inverter`; `:1342` `calc_economics`; `:1775` `calc_boq` | needs-adapter | Phase 2 adapter generates standard project data from templates/beneficiaries. |
| Simple BOQ document | `calculation/boq_generator.py:6` `generate_boq` | reuse-with-extension | Use for standard project reports; consolidate later. |
| Generation station sizing | `new_capital_investment_routes.py:388` `size_utility_pv(...)` | needs-adapter | Phase 2 generation-station programme adapter. |
| Generation station routes | `new_capital_investment_routes.py:6291` `register_capital_investment`; routes from `:6350` | reuse-as-is | Programme links/drill-down into existing `/large-scale-solar/<pid>` routes. |
| Generation project loader | `new_capital_investment_routes.py:6320` `_load_project(pid)` | reuse-as-is | Do not weaken owner filter; enterprise linking validates owner first. |
| Capital project table | `new_capital_investment_routes.py:5328` `capital_investment_projects` schema | reuse-with-extension | Link by ID; do not add enterprise columns in Phase 1. |
| Reports catalogue | `new_capital_investment_routes.py:2732` `REPORT_TYPES` | reuse-with-extension | Programme reports should follow existing report key/title pattern. |
| PDF renderer | `new_capital_investment_routes.py:3499` `_render_pdf_bytes` | reuse-with-extension | Phase 5 programme PDFs; can import or extract later. |
| Funding schema | `new_capital_investment_routes.py:5699` `_ensure_ci_funding_schema` | reuse-with-extension | Programme funding should allocate/link to existing project funding records. |
| Funding assessment | `new_capital_investment_routes.py:6114` `_ci_funding_assessment` | reuse-with-extension | Reuse for project-level readiness; programme rollup service aggregates. |
| Regular project funding | `new_capital_investment_routes.py:6928` `/project/<pid>/funding` | reuse-as-is | Programme page links to existing funding view. |
| Generation funding | `new_capital_investment_routes.py:6687` `/large-scale-solar/<pid>/funding` | reuse-as-is | Programme page links to existing funding view. |
| Marketplace product catalogue | `web_app.py:544` `equipment_catalog` | reuse-as-is | No second catalogue. |
| Marketplace public browse | `new_marketplace_routes.py` and spliced routes in `web_app.py` | reuse-as-is | Programme procurement links to existing marketplace. |
| Procurement center | `new_marketplace_procurement_center_routes.py:129` `/procurement-center` | reuse-as-is | Later consolidated procurement opens existing picker/price sheets. |
| Marketplace BOM | `new_marketplace_bom_routes.py:7`, `:103`, `:327` | reuse-with-extension | Phase 3 consolidated BOM/BOQ can create marketplace BOM rows. |
| Marketplace RFQ | `new_marketplace_rfq_routes.py:11`, `:108`, `:126`, `:292` | reuse-with-extension | Phase 3 creates RFQ from consolidated BOQ. |
| Supplier portal | `new_marketplace_supplier_routes.py:58`, `:132`, `:160` | reuse-as-is | EPC/supplier assignment references existing suppliers where appropriate. |
| BOQ hierarchy schema | `new_boq_hierarchy_schema.py:513` `ensure_boq_hierarchy_schema` | reuse-with-extension | Programme BOQ consolidation should read/link hierarchy projects. |
| BOQ audit | `new_boq_hierarchy_schema.py:555` `boq_audit` | reuse-with-extension | Reuse for BOQ-affecting programme actions. |
| BOQ hierarchy routes | `new_boq_hierarchy_routes.py:180` `/boq-projects` | reuse-as-is | Link/drill-down only; no duplicate BOQ UI. |
| BOQ rates | `boq_rate_v3.py:27` `boq_rate_v3` | reuse-as-is | Programme BOQ uses same rate calculation. |
| Audit log writer | `app/security/audit.py:233` `write_audit_event` | reuse-with-extension | All enterprise mutations should call it. |
| Structured audit logs | `logging_config/structured_logger.py:133` `log_audit` | reuse-with-extension | Use for operational logs where DB audit may fail. |
| AI gateway | `api_manager.py:224` `_AIClient.chat` | reuse-with-config | Optional narrative enrichment only; deterministic services first. |
| AI budget | `ai_budget.py` | reuse-as-is | Enterprise AI calls must pass user/admin context and cap usage. |
| AI-SOC dark flag precedent | `new_soc_slice0.py:30`, `:36`, `:45`, `:270` | reuse-as-pattern | Enterprise module ships dark by default. |
| Digital twin static assets | `static/capital_investment/dt/*` | reuse-as-is | Programme links generation-station digital twin; no duplicate 3D engine. |
| Capital digital twin route | `new_capital_investment_routes.py:10804` | reuse-as-is | Link from programme project rows. |
| Admin settings table | `web_app.py:28876` `_ensure_admin_settings_table`; `:28897` `_admin_setting`; `:28912` `_admin_setting_set` | reuse-with-extension | Use existing table; if helpers unavailable from enterprise module, query table directly. |
| Navigation shell | `templates/base.html:348` nav; enterprise insertion near `:713` side menu | reuse-with-extension | Add hidden-by-flag Enterprise link; do not touch `templates/location.html`. |
| CI workflows | `.github/workflows/ci.yml` | reuse-with-extension | Add enterprise tests to existing pytest flow. |
| Render deploy | `.github/workflows/render-deploy-now.yml` | reuse-as-is | Use “Force Render Deploy” after merge. |
| GitHub cron ticker | `.github/workflows/soc-health-sweep.yml:16` pattern | needs-new-service | Optional `enterprise-job-tick.yml` calls internal job tick endpoint. |
| Celery | `tasks/celery_app.py`, `tasks/report_tasks.py`, etc. | deferred | Do not depend on Celery in production until worker exists. |
| Workflow engine | none found | needs-new-service | Implement simple configurable statuses/stages first. |
| Digital signatures | none found | not-feasible now | Audited approvals substitute. |
| GIS provider | none found beyond location/globe UI | needs-new-UI/deferred | Simple coordinate map/list first; provider adapter later. |
| SCADA/telemetry | static digital twin only | not-feasible now | Manual/mock telemetry summary, labelled. |
| ERP/API integrations | none found | deferred | Provider interfaces after foundation. |
