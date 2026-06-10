#!/usr/bin/env bash
# Time-pressure beta review: 60-min window to ship beta. Earlier supervisor
# verdict (reviews/supervisor-beta-cutover.md) picked Path X (full Postgres
# cutover, 1-2 days). That timeline is now broken. Pick a 60-min-fit path.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ./scripts/_codex-runner.sh

CONTEXT="$(gather_context)"

PROMPT="You are Codex acting as Independent Pair Programmer. The constraint changed: owner just said 'we need start beta testing in an hour'. The original Postgres-cutover Path X is decomposed across 4 working sessions (A through D, ~8 hours combined) and would not fit. Sessions A and B already shipped to master (mirror schema applied to solarpro-postgres + db_adapter SQL portability + init_db gated). Session C (local Postgres smoke) is in progress; Session D (production flip + tag) hasn't started.

What's already true at this moment:
- web_app.py:init_db() gates SQLite DDL on DATABASE_URL (commit just before this turn; pytest tests/ 60/141 baseline holds).
- db_adapter.py has execute/executemany/executescript + SQL translations for last_insert_rowid/datetime/PRAGMA/sqlite_master.
- migrations/001_mirror_sqlite.sql applied to solarpro-postgres; 24 tables present.
- Production app on Render is still serving from SQLite. /api/ping returns 200 ~600ms.
- DATABASE_URL is NOT set on the Render web service.
- Full live test suite is green against the SQLite-backed prod (test_render 104/104, test_reports 20/20, test_admin_ops 23/25+2WARN, test_panel_wp PASS, test_exports 22/22, test_referrals_live 10/10).

THREE 60-min-fit options to weigh:

  F1. **Postgres cutover compressed** (~45-50 min if first try works).
      - Skip local Docker. Fetch solarpro-postgres external URL via Render API + GH Secrets.
      - Run pytest tests/ against solarpro-postgres locally. Target: 60/141.
      - If green: trigger migrate workflow with set_database_url=true. Smoke /api/ping and create+keep one project across a forced redeploy.
      - Tag v0.9.0-beta.1, push, announce.
      - Risk: any pytest failure on Postgres burns the budget; might miss the hour. The half-applied mirror schema cleans up via re-running the migration (idempotent CASCADE prelude), so rollback is cheap.

  F2. **Beta on SQLite + 'data may reset' banner** (~25 min).
      - Add a beta banner to base.html: 'Beta build — data may be reset between deploys; please keep a backup of your projects.'
      - Add VERSION file + /api/version endpoint.
      - Tag v0.9.0-beta.1. Push. Announce.
      - DATABASE_URL stays unset. Production runs SQLite as today.
      - Risk: the data-loss-on-deploy issue the original supervisor verdict called 'semantically incoherent with beta' is shipped as a known limitation.

  F3. **Soft beta — invite-only on SQLite, no banner** (~25 min).
      - Same as F2 but no banner; restrict signup with an admin-issued invite code or close /register temporarily. Existing /admin/users delete is the cleanup tool. Set a clear 1-week beta window after which everyone migrates to the Postgres-backed v0.9.1.
      - Tag v0.9.0-beta.1. Push. Announce only to the invited list.
      - Risk: still on SQLite, still loses data on deploy; mitigated by tight tester list and a known short window.

POLICIES that apply (from CLAUDE.md and memory):
- feedback_solar_app_works_dont_break: do not break the running app. F1 risks this if pytest catches a Postgres bug at the last minute.
- feedback_commit_to_one_path: pick a path, don't propose alternatives while it's still in progress.
- The Project Execution Directive rule 5 ('Senior Engineering Quality') says a feature isn't complete until data durability is in place — F2 and F3 ship without it.
- The previous supervisor verdict (reviews/supervisor-beta-cutover.md §S4) rejected F2-style options because 'beta with a data may vanish banner is semantically incoherent.' But that was before the 60-min constraint.

YOUR JOB:
  1. Read reviews/supervisor-beta-cutover.md to understand the prior verdict and the precise reasons it rejected SQLite-based betas.
  2. Decide whether the 60-min time constraint legitimately overrides the prior verdict, or whether it's a moment to STOP and renegotiate the deadline with the owner.
  3. If proceeding: pick F1, F2, or F3.
  4. Justify in 5-10 lines. Confidence (high/medium/low). Single biggest risk in your chosen path.

Be decisive. Do not enumerate every consideration. Own one path.

${CONTEXT}"

codex_run "codex-beta-60min" "$PROMPT"
