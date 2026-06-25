# Tenant inventory — 2026-06-25

Source-grep snapshot of CREATE TABLE statements across `web_app.py`, `new_*.py`, and `migrations/*.sql`. Action column maps each gap to the SOC 2 plan milestone (`docs/SOC2_IMPLEMENTATION_PLAN.md`).

## Summary

- **Tables found**: 49
- **With tenant_id column**: 1 (2.0%)
- **With RLS policy in migrations/**: 1 (2.0%)
- **Gap to close in M1.6**: 48 tables need an RLS policy (excluding the intentionally-global rows below).

## Per-table action list

| Table | tenant_id col | RLS in migrations/ | Source | Action |
|---|---|---|---|---|
| `admin_settings` | no | no | `web_app.py:26551` | M3.1 -- add tenant_id column + M1.6 RLS |
| `appliances` | no | no | `web_app.py:329` | M3.1 -- add tenant_id column + M1.6 RLS |
| `assessment_requests` | no | no | `web_app.py:430` | M3.1 -- add tenant_id column + M1.6 RLS |
| `audit_logs` | no | yes | `web_app.py:531` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `beta_feedback` | no | no | `web_app.py:520` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `beta_signups` | no | no | `web_app.py:509` | M3.1 -- add tenant_id column + M1.6 RLS |
| `boq_audit_log` | no | no | `new_boq_hierarchy_schema.py:150` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `boq_buildings` | no | no | `new_boq_hierarchy_schema.py:56` | M3.1 -- add tenant_id column + M1.6 RLS |
| `boq_floor_items` | no | no | `new_boq_hierarchy_schema.py:92` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `boq_floor_rate_buildup` | no | no | `new_boq_hierarchy_schema.py:127` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `boq_floors` | no | no | `new_boq_hierarchy_schema.py:76` | M3.1 -- add tenant_id column + M1.6 RLS |
| `boq_projects` | no | no | `new_boq_hierarchy_schema.py:39` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `boq_user_item_overrides` | no | no | `web_app.py:23074` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `email_logs` | no | no | `web_app.py:409` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `equipment_catalog` | no | no | `web_app.py:394` | OK -- intentionally global |
| `equipment_catalog_price_history` | no | no | `new_catalogue_pricing_routes.py:61` | M3.1 -- add tenant_id column + M1.6 RLS |
| `equipment_catalog_quotes` | no | no | `new_catalogue_pricing_routes.py:31` | M3.1 -- add tenant_id column + M1.6 RLS |
| `error_logs` | yes | no | `web_app.py:27853` | OK -- intentionally global |
| `helpline_learned_kb` | no | no | `web_app.py:501` | M3.1 -- add tenant_id column + M1.6 RLS |
| `installers` | no | no | `web_app.py:453` | M3.1 -- add tenant_id column + M1.6 RLS |
| `leads` | no | no | `web_app.py:348` | M3.1 -- add tenant_id column + M1.6 RLS |
| `login_failures` | no | no | `web_app.py:540` | M3.1 -- add tenant_id column + M1.6 RLS |
| `marketplace_audit_log` | no | no | `web_app.py:15323` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `marketplace_bom_items` | no | no | `web_app.py:16250` | M3.1 -- add tenant_id column + M1.6 RLS |
| `marketplace_bom_rates` | no | no | `web_app.py:18422` | M3.1 -- add tenant_id column + M1.6 RLS |
| `marketplace_boms` | no | no | `web_app.py:16236` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `marketplace_price_sheet_items` | no | no | `web_app.py:19027` | M3.1 -- add tenant_id column + M1.6 RLS |
| `marketplace_price_sheets` | no | no | `web_app.py:19018` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `monitor_alerts` | no | no | `web_app.py:472` | M3.1 -- add tenant_id column + M1.6 RLS |
| `monitor_state` | no | no | `web_app.py:482` | M3.1 -- add tenant_id column + M1.6 RLS |
| `news_posts` | no | no | `web_app.py:369` | M3.1 -- add tenant_id column + M1.6 RLS |
| `newsletter_subscribers` | no | no | `web_app.py:362` | M3.1 -- add tenant_id column + M1.6 RLS |
| `password_reset_tokens` | no | no | `web_app.py:493` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `payments` | no | no | `web_app.py:336` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `product_brands` | no | no | `web_app.py:26064` | M3.1 -- add tenant_id column + M1.6 RLS |
| `product_categories` | no | no | `web_app.py:14302` | M3.1 -- add tenant_id column + M1.6 RLS |
| `projects` | no | no | `web_app.py:299` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `referrals` | no | no | `web_app.py:288` | M3.1 -- add tenant_id column + M1.6 RLS |
| `rfq_items` | no | no | `web_app.py:15678` | M3.1 -- add tenant_id column + M1.6 RLS |
| `rfq_response_items` | no | no | `web_app.py:15716` | M3.1 -- add tenant_id column + M1.6 RLS |
| `rfq_responses` | no | no | `web_app.py:15702` | M3.1 -- add tenant_id column + M1.6 RLS |
| `rfq_supplier_targets` | no | no | `web_app.py:15690` | M3.1 -- add tenant_id column + M1.6 RLS |
| `rfqs` | no | no | `web_app.py:15662` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `shading_history` | no | no | `web_app.py:550` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `suppliers` | no | no | `web_app.py:378` | M3.1 -- add tenant_id column + M1.6 RLS |
| `ticket_replies` | no | no | `web_app.py:320` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `tickets` | no | no | `web_app.py:309` | M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, backfill from owning user's tenant, then M1.6 RLS. |
| `upgrade_codes` | no | no | `web_app.py:419` | M3.1 -- add tenant_id column + M1.6 RLS |
| `users` | no | no | `web_app.py:275` | OK -- intentionally global |

## How the action column maps to milestones

- **M1.6** — extend `migrations/003_rls_tenant.sql` (or land `migrations/006_rls_full.sql`) so every tenant-owned table has `ENABLE ROW LEVEL SECURITY` + a `<table>_tenant_isolation` policy.
- **M3.1** — when a table lacks `tenant_id`, the schema change comes first (Alembic migration adds the column, backfills from owning user / project / parent, then `NOT NULL` + index).

## Limitations

- **CREATE TABLE only.** This walks the CREATE TABLE statements in source -- it does NOT see `ALTER TABLE ADD COLUMN tenant_id` (which `migrations/003_rls_tenant.sql` ran to add 14 columns to live Postgres). So a table that shows `tenant_id col: no` here may already carry the column at runtime. Confirm against Postgres before doing M3.1 work on it.
- Source-grep -- a CREATE TABLE that has been since dropped or renamed without removing the source line still shows up.
- Doesn't yet enumerate every `SELECT ... FROM <table>` callsite to flag missing `WHERE tenant_id=?` predicates -- that's the Phase 2 follow-up (M3.1 task list driver).
