#!/usr/bin/env bash
# One-off review: ask Codex CLI to review the beta cutover plan
# (P2 Postgres cutover + v0.9.0-beta.1 versioning). Output to
# reviews/codex-beta-cutover.md.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ./scripts/_codex-runner.sh

CONTEXT="$(gather_context)"

PROMPT="You are Codex acting as Independent Pair Programmer for the solar-pv-designer-lite repository.

DECISION TO REVIEW: an end-to-end plan to go from the current Render free-tier SQLite deployment (which gets wiped on every deploy) to a Postgres-backed beta tagged v0.9.0-beta.1.

OWNER CONTEXT:
- 'We are going into beta so we need to get the app in usable mode and version it.'
- The biggest beta-blocker is data durability: Render free tier wipes /app/solar.db on every deploy. Beta evaluators would lose their projects mid-eval.
- Postgres migrations 001-004 were already applied to solarpro-postgres in the last session (workflow run 27296591166 success). DATABASE_URL is provisioned but not yet wired to the web service.
- The workflow scripts/.github/workflows/migrate-and-cutover-postgres.yml accepts a set_database_url=true input that does the env-flip and forces a Render redeploy.

STATE OF THE CODE (from the prior session's resume memo in memory):
- init_db() at web_app.py:226 runs SQLite-only 'CREATE TABLE ... INTEGER PRIMARY KEY AUTOINCREMENT' unconditionally on every cold start.
- Dozens of SQLite-only patterns scattered through routes: datetime('now'), INSERT OR REPLACE, last_insert_rowid(), PRAGMA table_info().
- db_adapter.py already translates ? -> %s parameterization but does NOT translate SQL syntax. Flipping DATABASE_URL today = 500 on first request.

PROPOSED PLAN (8 tasks):
  1. Audit SQLite-only patterns in web_app.py — quantify before touching.
  2. Surface migration plan to owner for OK — per feedback rule 'never silently modify web_app.py'.
  3. Gate init_db() on DATABASE_URL — early-return when set; migrations 001-004 own Postgres schema.
  4. Translate SQLite-only SQL to portable forms per pattern.
  5. Local Postgres smoke test of full app — pytest tests/ + smoke_proposal_superset + manual page-walk.
  6. Flip DATABASE_URL on Render via existing workflow with set_database_url=true.
  7. Add VERSION file + /api/version endpoint.
  8. Tag v0.9.0-beta.1 + GitHub Release with cumulative notes.

CURRENT TEST STATE (just verified live, this session):
- pytest tests/: 60 pass / 141 skipped / 0 fail
- Live suite vs solarpro.aiappinvent.com: test_render 104/104, test_admin_ops 23/25+2WARN, test_reports 20/20, test_procurement OK, test_email_debug 200, test_panel_wp PASS, test_exports 22/22, test_referrals_live 10/10+cleanup.
- All baselines green at commit ec6feb0.

POLICIES that apply (from CLAUDE.md):
- feedback_solar_app_works_dont_break: 'during sweeping fixes default to additive; never modify web_app.py silently — surface and ask.'
- feedback_verify_before_acting: 'read the actual logs/error message before proposing any fix.'
- feedback_no_provider_thrash: 'never propose switching providers as default response to failure.'
- feedback_no_dashboard_ask: 'use the provider's REST API + GitHub Actions workflows, never ask the user to click through dashboards.'
- feedback_reviewer_supervisor_lens: 'before any non-trivial action mentally run it past Codex + Supervisor.'
- 'A feature is NOT complete until Codex has reviewed it AND the supervisor has signed off.'

YOUR JOB — give a decisive review of this plan:
  1. Read web_app.py around the init_db() function and the migration files in migrations/.
  2. For each of the SQLite-only patterns (datetime('now'), INSERT OR REPLACE, last_insert_rowid(), PRAGMA table_info()): grep web_app.py, count occurrences, and rank by criticality (which patterns would cause an immediate 500 vs which are dormant).
  3. Question the plan order: is gating init_db() before or after the SQL translation? What's the cleanest sequence?
  4. Identify risks I haven't flagged. Specifically:
     - Will existing prod data (the seed admin + marc667us users) survive the cutover? They're created by _seed_pwd() at startup from env vars, but only if the rows don't already exist.
     - Is the existing /app/data disk for SQLite still mounted? If so, what happens to it?
     - Are there sessions / login_failures / audit_logs tables that exist in SQLite but were/weren't included in migrations 001-004?
  5. Pick: GO with the plan, GO with modifications (list them), or STOP and explain blockers.
  6. State confidence (high/medium/low) and single biggest risk.

Be decisive. Do not enumerate every consideration — pick a path and own it.

${CONTEXT}"

codex_run "codex-beta-cutover" "$PROMPT"
