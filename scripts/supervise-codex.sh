#!/usr/bin/env bash
# Supervisor pass — audits Codex's review output and adds an independent pass.
# Writes to reviews/supervisor-*.md
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ./scripts/_codex-runner.sh

# Gather context once (repo state) and previously-written codex findings.
CONTEXT="$(gather_context)"
REVIEWS_DIR="$(pwd)/reviews"
PRIOR_REVIEWS=""
for f in "$REVIEWS_DIR"/codex-*.md; do
  [ -f "$f" ] || continue
  PRIOR_REVIEWS="${PRIOR_REVIEWS}

### $(basename "$f")
$(head -200 "$f")
"
done

# S1 — Audit Codex's prior findings
codex_run "supervisor-audit" \
"You are the Supervisor auditing Codex's prior review reports. For each finding, verify it's real by checking the cited file:line against the diff. Output a markdown table: review file | finding | file:line | verdict (REAL/HALLUCINATED/WRONG-FILE) | corrected severity | notes. Be skeptical — reviewers can be wrong.

${CONTEXT}

## Codex's prior findings
${PRIOR_REVIEWS}"

# S2 — Independent pass to find what Codex missed
codex_run "supervisor-missed-findings" \
"You are the Supervisor doing an INDEPENDENT review. DO NOT consult any prior Codex findings — the goal is to discover what Codex may have missed. Look for: tenant-owned queries without WHERE tenant_id; tables without ENABLE ROW LEVEL SECURITY; hidden routes without backend auth; logout paths without refresh-token revocation; heavy ops running synchronously; secrets in plaintext or in git; missing audit-log entries for sensitive actions. Output findings with severity, file:line, why it's a problem, recommended fix.

${CONTEXT}"

# S3 — Runtime verification plan (for the human / Claude to execute via /verify skill)
codex_run "supervisor-verification-plan" \
"You are the Supervisor producing a runtime verification plan for the latest feature. Read README.md, docs/IMPLEMENTATION_LOG.md (latest entry), and the diff. Produce a step-by-step plan that: (1) starts the app locally (use existing run command if documented, otherwise infer from package.json / Makefile / docker-compose.yml present in the tree), (2) exercises the golden path, (3) exercises at least one edge case, (4) checks for regressions in adjacent features. Plan must be runnable in under 10 minutes.

${CONTEXT}"

echo ""
echo "Supervisor pass complete. Files written:"
echo "  reviews/supervisor-audit.md"
echo "  reviews/supervisor-missed-findings.md"
echo "  reviews/supervisor-verification-plan.md"
echo ""
echo "Next steps:"
echo "  1. Read supervisor-audit.md — fix any HALLUCINATED markings on prior Codex findings"
echo "  2. Read supervisor-missed-findings.md — fix every critical/high finding"
echo "  3. Execute supervisor-verification-plan.md (use /verify skill in Claude Code)"
echo "  4. Run ./scripts/quality-gate.sh for final adjudication"
