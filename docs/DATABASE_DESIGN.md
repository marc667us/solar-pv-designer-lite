# Database Design — SolarPro Global

**Runtime today:** SQLite (`solar.db` locally, `/app/solar.db` on Render).
**Target:** PostgreSQL (Neon free or low-cost), schema in `migrations/001_postgresql_schema.sql`, RLS in `migrations/002_rls_policies.sql`, hardenings in `migrations/003_rls_hardening.sql` + `migrations/004_schema_hardening.sql`. Migrations NOT yet applied.

---

## Tables (target Postgres schema)

| Domain | Tables |
|---|---|
| Tenancy | `organizations`, `users`, `user_sessions` |
| Solar engineering | `projects` (with `data_json` JSON blob for the full calculation), `proposals`, `equipment_catalog` |
| Sales + CRM | `leads`, `assessment_requests`, `crm_opportunities` |
| Procurement | `installers`, `procurement_packages`, `bidder_submissions` |
| Billing | `subscriptions`, `payments` |
| Support | `tickets`, `ticket_replies` |
| Compliance | `audit_log`, `email_logs`, `uploaded_files`, `newsletter_subscribers` |

## Conventions

- PK: `id UUID DEFAULT uuid_generate_v4()`.
- Human code: `<entity>_code TEXT UNIQUE DEFAULT next_code('<PREFIX>-', '<seq>_seq')` (e.g. `USR-000001`, `PRJ-000007`).
- Tenant column: `organization_id UUID REFERENCES organizations(id)`. After migration 004, NOT NULL on tables where every row must carry a tenant (sessions, payments, tickets, replies, audit, email_logs).
- Audit columns: `created_by_user_id UUID REFERENCES users(id)`, `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`. Update trigger `update_updated_at()` is attached.
- Composite FK pattern (added in 004): parent has `UNIQUE (id, organization_id)`; child has `FOREIGN KEY (parent_id, organization_id) REFERENCES parent(id, organization_id)` — prevents cross-tenant references.

## Row Level Security

Every tenant-owned table:
1. `ENABLE ROW LEVEL SECURITY` (migration 002).
2. `FORCE ROW LEVEL SECURITY` so the table owner can't bypass (migration 003).
3. Per-table policy keyed on `current_setting('app.current_tenant')::uuid` via the `current_tenant_id()` helper. `is_super_admin()` short-circuits.

Special cases:
- `assessment_requests`, `installers` — public anonymous INSERT is allowed (`organization_id IS NULL`), but **reads/updates/deletes are tenant-only**. Migration 003 split the old `FOR ALL ... IS NULL` policies that previously exposed unassigned rows to every tenant.
- `uploaded_files` — `is_public = TRUE` is SELECT-only. Writes still require tenant match.
- `users` — column-level GRANT restricts the app role to non-privileged columns. Role / `is_admin` / `organization_id` / `status` / `mfa_secret` / `plan` only via a `SECURITY DEFINER` function (TBD).
- `audit_log` — INSERT WITH CHECK requires `organization_id = current_tenant_id() AND user_id = current_user_id()` (replaces the previous `WITH CHECK (TRUE)` forgery hole).

## Connection model (target)

- App role: `solarpro_app` (LOGIN, NO BYPASSRLS).
- Per request: `SET LOCAL app.current_tenant = '<org_id>'`, `SET LOCAL app.current_user = '<user_id>'`, `SET LOCAL app.current_role = '<role>'`.
- Pool: SQLAlchemy `pool_size=10, max_overflow=20`, routed through PgBouncer in transaction mode at scale.

## Indexes (post-004)

- Baseline per tenant table: `idx_<t>_org`.
- Workload composites for dashboard queries: `(organization_id, status)`, `(organization_id, status, created_at DESC)`, `(organization_id, updated_at DESC)`, `(organization_id, project_id)` — added in 004 for projects, leads, proposals, packages, bids, subs, payments, tickets.

## Open gaps

- Postgres not provisioned yet. Migrations 001–004 are aspirational.
- `SECURITY DEFINER` admin-column-update function (1.7 follow-up) not yet written.
- `user_sessions` is currently a schema-only table — actual server-side session tracking + revocation (`is_revoked`, `session_version`) needs the runtime auth rewrite (Q-gate 2.1).
- Sharding strategy lives in `migrations/database-sharding.md` — applies post-1000-tenant scale.
