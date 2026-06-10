#!/usr/bin/env bash
# Final approval — runs Codex reviews, then Supervisor pass, then asks Codex for PASS/FAIL.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ./scripts/_codex-runner.sh

echo "=== Stage 1: Codex review pipeline ==="
./scripts/codex-review.sh
./scripts/codex-security-review.sh
./scripts/codex-db-review.sh
./scripts/codex-test-review.sh
./scripts/codex-performance-review.sh

echo ""
echo "=== Stage 2: Supervisor pass (audits Codex's output) ==="
./scripts/supervise-codex.sh

echo ""
echo "=== Stage 3: Final adjudication ==="

PROMPT="You are the Supervisor signing off (or rejecting) the feature. Read ALL of ./reviews/codex-*.md AND ./reviews/supervisor-*.md. Apply the 10-item quality gate in ai-coworkers/quality-gates.md and the supervisor sign-off conditions in ai-coworkers/supervisor-checklist.md. PASS requires: (1) all critical/high Codex findings resolved or marked hallucinated with evidence, (2) all independently-discovered findings from supervisor-missed-findings.md resolved, (3) runtime verification plan executed (assume yes if the human has run /verify and tests pass), (4) tests verified passing, (5) documentation updated. Output FIRST line: 'SUPERVISOR VERDICT: PASS' or 'SUPERVISOR VERDICT: FAIL'. Then per-gate justification (gates 1..10). Then blocking-issues list if FAIL."

codex_run "codex-final-approval" "$PROMPT"

echo ""
echo "=== Final verdict ==="
# Parse verdict and EXIT NON-ZERO on FAIL / missing — CI must not pass a failed gate.
VERDICT_LINE=$(grep -E "^SUPERVISOR VERDICT:" reviews/codex-final-approval.md || true)
if [ -z "$VERDICT_LINE" ]; then
  echo "(verdict line not found - read reviews/codex-final-approval.md)"
  echo ""
  echo "Reminder: a PASS verdict from this script is advisory. The human/Claude (acting as Supervisor)"
  echo "must still confirm runtime behaviour via /verify before treating the gate as closed."
  exit 2
fi
echo "$VERDICT_LINE"
echo ""
echo "Reminder: a PASS verdict from this script is advisory. The human/Claude (acting as Supervisor)"
echo "must still confirm runtime behaviour via /verify before treating the gate as closed."
# Non-zero exit on FAIL so the calling CI step (or the human) cannot miss it.
case "$VERDICT_LINE" in
  *FAIL*) exit 1 ;;
  *PASS*) exit 0 ;;
  *)      exit 2 ;;
esac
