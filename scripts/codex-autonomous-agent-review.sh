#!/usr/bin/env bash
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ./scripts/_codex-runner.sh

CONTEXT="$(gather_context)"

PROMPT="You are Codex acting as Independent Pair Programmer. Owner just said 'you must monitor all must be automated so human intervention is less' for the SolarPro Global beta (https://solarpro.aiappinvent.com, v0.9.0-beta.1).

ALREADY BUILT this session:
- .github/workflows/beta-monitor.yml — every 30 min logs in as admin, polls /admin/feedback + /admin/tickets + /admin/beta + /admin/ops/security/audit + /admin/ops/logs/audit + /admin/ops/security/sessions, diffs against data/response_state.json, emails alerts to sales@aiappinvent.com via Brevo.

PLANNED ADDITIONS — review the architecture:

  Tier 2+3 — Auto-triage + auto-respond:
    When a new feedback or ticket row appears, fetch its body text from the admin view, classify via OpenRouter free tier (per [[feedback-zero-cost-apis-only-pre-launch]]): { critical_bug, high_bug, feature_request, info, spam }. Send a personalised acknowledgement email to the submitter within 30 min via Brevo.

  Tier 4 — Auto-create GH Issue for critical/high:
    Classification >= high triggers a 'gh issue create' with the full evaluator body + classification + suggested next steps. Labels: beta, auto-triage, severity:{critical,high}.

  Tier 5 — Daily digest:
    9 AM UTC cron. Aggregates last 24h responses + classifications + security summary. Single email to owner.

  Tier 6 — Synthetic E2E health check every hour:
    Hits landing -> login as a synthetic user -> create project -> location step -> loads step -> view results -> proposal PDF download. Any 5xx or 4xx (other than expected 302) alerts the owner; multiple consecutive failures should escalate.

EXPLICIT SAFETY BOUNDARIES — DO NOT add unless reviewer blesses:
  * Auto IP-block (could lock real evaluators)
  * Auto-rollback of prod (high-blast-radius)
  * LLM-drafted full replies sent without owner review (could embarrass)

YOUR JOB:
  1. Read the current beta-monitor.yml + the response_state.json to understand the baseline.
  2. For each planned tier, identify the single biggest risk + a non-destructive mitigation.
  3. Specifically question: does auto-acknowledgement email risk a Brevo reputation hit if the LLM mis-classifies spam as a real response and replies? What about an LLM that classifies a legitimate report as spam (false-negative) and goes silent?
  4. Recommend ORDER of implementation. Pick one tier to ship FIRST.
  5. Pick GO / GO-WITH-MODS / STOP and justify in 5-10 lines. Confidence (high/medium/low).

Be decisive. Own one path.

${CONTEXT}"

codex_run "codex-autonomous-agent" "$PROMPT"
