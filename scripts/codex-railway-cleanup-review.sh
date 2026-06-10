#!/usr/bin/env bash
# One-off review: ask Codex CLI to recommend a cleanup strategy for the 6
# Railway-targeting end-to-end test scripts (web-production-744af URL is
# decommissioned; Railway tier removed). Output to reviews/codex-railway-cleanup.md.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ./scripts/_codex-runner.sh

CONTEXT="$(gather_context)"

PROMPT="You are Codex acting as Independent Pair Programmer for the solar-pv-designer-lite repository.

DECISION TO REVIEW: how to clean up six Python end-to-end test scripts at the repo root that target the now-decommissioned Railway URL https://web-production-744af.up.railway.app. The live deployment is https://solarpro.aiappinvent.com on Render. The six scripts are:

  1. test_admin_ops2.py        (162 lines)
  2. test_exports.py           (122 lines)
  3. test_panel_wp.py          (181 lines)
  4. test_referrals_live.py    (157 lines)
  5. test_sales_readiness.py   (246 lines)
  6. test_session_audit.py     (243 lines)

THREE OPTIONS being considered:
  A. Delete the 3 superseded scripts (admin_ops2, session_audit, sales_readiness) and migrate the 3 with unique coverage (exports, panel_wp, referrals_live) to point at solarpro.aiappinvent.com using the env-var pattern already applied to test_reports.py / test_render.py / test_admin_ops.py / test_email_debug.py / test_procurement.py (commits 8c96986 and 4e25555).
  B. Delete all 6 outright. Lose coverage for /project/{pid}/export/csv|docx, the panel_wp UI selection flow, and the referral program /r/<code>.
  C. Migrate all 6 — preserve everything but risk duplication with the live tests already covering admin ops.

CONTEXT — what each script does:
  - test_admin_ops2.py: 'Re-run admin ops test - all buttons including email. Revoke Sessions goes last.' Hits /admin/ops/* — fully covered by test_admin_ops.py which I just ran 23/25 PASS against prod (the 2 WARNs are expected REDIS_URL-not-configured on Render free tier).
  - test_exports.py: tests /project/{pid}/export/csv and /export/docx. CLAUDE.md and the current test_render.py / test_reports.py do not exercise these export routes.
  - test_panel_wp.py: tests panel_wp picker on the project wizard UI + KPI tile values rendered after results. test_render.py exercises the Design API JSON; not the wizard UI flow.
  - test_referrals_live.py: tests /r/<code> redirect, cookie capture, ?ref=CODE on landing. CLAUDE.md says 'Live tests: 10/10 PASS (test_referrals_live.py)' — this is the canonical referral test.
  - test_sales_readiness.py: tests /paystack/initialize. But CLAUDE.md is explicit: 'There is NO server-side /paystack/initialize route — the popup talks directly to Paystack.' So this script tests an endpoint that does not exist.
  - test_session_audit.py: 'Per-commit verification audit' — hits /admin/ops/email/status, /admin/operations, /api/ping. Heavily overlaps test_admin_ops.py.

POLICIES that apply (from CLAUDE.md):
  - Free / open-source first stack — keep build cheap and reversible.
  - 'A feature is not complete until tests pass' — losing real coverage is a regression.
  - 'No dashboard ask' / 'no provider thrash' — Railway thrash already happened, do not undo it.
  - The owner just ran the live test suite and explicitly asked to 'clean up the dead railway test'.

YOUR JOB:
  1. Open each of the 6 scripts and verify my characterization above (read first 40 lines + tail).
  2. For test_sales_readiness.py specifically: confirm whether /paystack/initialize really doesn't exist in web_app.py (grep for it).
  3. For test_referrals_live.py: confirm whether /r/<code> exists in web_app.py and whether test_render.py or any other live test already exercises it.
  4. Pick A, B, or C. Justify in 5-10 lines max. State your confidence level (high/medium/low) and the single biggest risk in your chosen option.

Be decisive. Do not enumerate every consideration — pick one and own it.

${CONTEXT}"

codex_run "codex-railway-cleanup" "$PROMPT"
