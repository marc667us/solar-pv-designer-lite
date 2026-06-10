# Archived migrations 001–004

These four files were drafted in an earlier session as a **greenfield
multi-tenant SaaS-platform schema**: UUID primary keys, organizations
table, RLS, CRM/proposals/bidder tables, etc. They were applied to
`solarpro-postgres` (workflow run `27296591166` succeeded) but they
**do not describe the application that is actually deployed**.

The codex+supervisor review at `reviews/codex-beta-cutover.md` /
`reviews/supervisor-beta-cutover.md` documented 4 blocking gaps:

1. **Schema contract incompatible** — migration 001 uses
   `users.full_name`, `projects.created_by_user_id`, `tickets.body`;
   the application code uses `users.name`, `projects.user_id`,
   `tickets.message`.
2. **RLS forced but not wired** — migrations enable RLS, but
   `db_adapter.py` never sets `app.organization_id` / `app.current_tenant`
   / `app.current_user` before queries. Result: 0 rows or rejected writes.
3. **13 tables the app needs are absent**: `appliances`, `audit_logs`,
   `beta_feedback`, `beta_signups`, `helpline_learned_kb`,
   `login_failures`, `monitor_alerts`, `monitor_state`, `news_posts`,
   `password_reset_tokens`, `referrals`, `suppliers`, `upgrade_codes`.
4. **8 tables Postgres has but the app doesn't use**: `organizations`,
   `user_sessions`, `crm_opportunities`, `proposals`,
   `procurement_packages`, `bidder_submissions`, `subscriptions`,
   `uploaded_files`.

Flipping `DATABASE_URL` to point at the schema these migrations create
would have produced an immediate 500 cascade, not a working beta.

## What replaced them

`migrations/001_mirror_sqlite.sql` mirrors the 24-table schema that
`web_app.py:init_db()` creates on SQLite, translated to Postgres types.
No RLS, no org tables, no UUID — match what the deployed app speaks.

## Keep these archived files because…

They describe a viable long-term destination for the platform (proper
multi-tenancy + RLS + CRM-aligned schema). When the product evolves
toward that vision, the migrations here are the starting point for the
real schema redesign — at which point the application code, not the
schema files, will need to do the bulk of the moving.

## Do NOT re-apply

These files are kept for reference only. Re-applying them against
`solarpro-postgres` would re-create the unused tables and re-enable RLS,
breaking any reads even from the new `001_mirror_sqlite.sql` schema.
