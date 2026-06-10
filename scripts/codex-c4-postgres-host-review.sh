#!/usr/bin/env bash
# One-off review: ask Codex CLI which Postgres host to use for the
# Session C smoke (local Docker container vs already-provisioned
# solarpro-postgres on Render). Output to reviews/codex-c4-postgres-host.md.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ./scripts/_codex-runner.sh

CONTEXT="$(gather_context)"

PROMPT="You are Codex acting as Independent Pair Programmer for the solar-pv-designer-lite repository.

DECISION TO REVIEW: which Postgres instance should host the Session C smoke tests (pytest tests/ + scripts/smoke_proposal_superset.py) against the new DATABASE_URL code path? Pick one and own it.

CONTEXT — what's already in place (Sessions A + B):
- migrations/001_mirror_sqlite.sql was authored and applied to solarpro-postgres on Render (workflow run 27308498772 success, 24/24 tables created).
- web_app.py:init_db() was just rewritten this turn so the SQLite-only DDL is gated behind 'if not os.environ.get(\"DATABASE_URL\")'. pytest against SQLite still 60/141 baseline. Commit b88008f6 already shipped to prod.
- db_adapter.py now has execute() + executemany() + executescript() + SQL translations for last_insert_rowid/datetime/PRAGMA/sqlite_master.
- No DATABASE_URL is set on the Render web service yet. Production app continues running on SQLite.

OPTIONS being weighed:
  A. **Use solarpro-postgres directly** via its external connection string. The DB is currently empty (just the mirror schema, no app rows). I'd pull the external URL through Render's API (RENDER_API_KEY is in GH Secrets), export DATABASE_URL locally, run pytest, then re-apply the mirror migration to clean test rows. Pros: zero local setup, fastest. Cons: hits an external host with test traffic; test failures could leave the DB in a half-state. The DB IS connected to no live web service so there's no traffic risk.
  B. **Local Docker Postgres**. Docker is installed (v29.4.3) but Docker Desktop daemon is not running. User would have to launch the GUI manually, ping back, then I docker run -d postgres:15, psql -f the migration, run pytest, docker rm at end. Pros: clean isolated environment, classic dev pattern. Cons: requires user manual action to start Docker Desktop, multi-minute wait.
  C. **Native Windows Postgres install via the EDB installer**. Heavyweight for a one-time smoke. Not recommended by me. Listed only for completeness.

POLICIES that apply (from CLAUDE.md and memory):
- feedback_solar_app_works_dont_break: do not modify the running solar app.
- feedback_no_dashboard_ask: do not ask the user to click through provider dashboards.
- feedback_no_provider_thrash: stay on Render + Postgres; do not migrate hosting.
- feedback_zero_cost_apis_only_pre_launch: free tier only, no paid Render Postgres.
- 'dont break anything' was the user's literal instruction at session start.

YOUR JOB:
  1. Read CLAUDE.md for the policy context. Read .github/workflows/migrate-and-cutover-postgres.yml to verify that re-running the mirror migration is idempotent (the DROP CASCADE prelude cleans any test rows in solarpro-postgres) — this matters for the rollback story of Option A.
  2. Check whether solarpro-postgres is genuinely disconnected from the live web service (read RENDER_SERVICE_ID env-vars OR confirm DATABASE_URL is not set anywhere on the service).
  3. For Option A: identify ANY way that pytest tests/ + the smoke proposal script could corrupt state on solarpro-postgres in a way the mirror re-apply does NOT clean up.
  4. For Option B: any blocker beyond 'user must start Docker Desktop'?
  5. Pick A, B, or C. Justify in 5-10 lines. Confidence (high/medium/low). Single biggest risk.

Be decisive. Do not enumerate every consideration — pick a path and own it.

${CONTEXT}"

codex_run "codex-c4-postgres-host" "$PROMPT"
