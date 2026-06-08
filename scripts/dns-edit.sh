#!/usr/bin/env bash
# DNS-edit skill entry point.
#
# The Claude + Codex + Supervisor team collaborates on DNS changes the same way
# we collaborate on code: someone has the intent, Codex drafts a plan, the
# Supervisor approves it, then the change is applied. The human only logs in
# (i.e. generates a provider API token once and pastes it into env).
#
# Sub-commands:
#   request "<intent>"        plan + supervise + (on PASS) apply.  One-shot.
#   plan    "<intent>"        produce reviews/dns/<id>.plan.json only
#   supervise <id>            run supervisor pass; emits verdict + sentinel
#   apply   <id> [--dry-run]  apply (requires supervisor PASS)
#   status  <id>              show artifacts for one plan
#   list                      list recent plans + their state
#   roles                     print the role contract (ai-coworkers/dns-edit-role.md)
#
# Exit codes: 0 success, 1 generic failure, 2 missing input, 3 unauthorized
# (no supervisor PASS), 4 provider problem.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/dns-providers/_lib.sh"
load_env

usage() {
  cat <<'TXT'
Usage:
  ./scripts/dns-edit.sh request "<intent>"
  ./scripts/dns-edit.sh plan    "<intent>"
  ./scripts/dns-edit.sh supervise <plan-id>
  ./scripts/dns-edit.sh apply <plan-id> [--dry-run]
  ./scripts/dns-edit.sh status <plan-id>
  ./scripts/dns-edit.sh list
  ./scripts/dns-edit.sh roles

Team:
  - Owner / Claude  -> writes the intent in plain English
  - Codex (planner) -> turns the intent into a plan.json
  - Supervisor      -> approves or refuses the plan
  - This script     -> applies an approved plan via the provider API

Human only needs to provide ONE thing: an API token per provider in .env or env.
See `./scripts/dns-edit.sh roles` for the full contract.
TXT
}

cmd="${1:-}"
shift || true

case "$cmd" in
  request)
    [ -n "${1:-}" ] || { usage; exit 2; }
    ID="$("$SCRIPT_DIR/dns-plan.sh" "$1" | tail -n 1)"
    [ -n "$ID" ] || { log ERROR "Planning failed — no id"; exit 1; }
    log INFO "Plan written: $ID"
    if "$SCRIPT_DIR/dns-supervise.sh" "$ID"; then
      log INFO "Supervisor PASS — proceeding to apply"
      "$SCRIPT_DIR/dns-apply.sh" "$ID"
    else
      log WARN "Supervisor FAIL — apply skipped. See reviews/dns/$ID.verdict.md"
      exit 1
    fi
    ;;
  plan)
    [ -n "${1:-}" ] || { usage; exit 2; }
    "$SCRIPT_DIR/dns-plan.sh" "$1"
    ;;
  supervise)
    [ -n "${1:-}" ] || { usage; exit 2; }
    "$SCRIPT_DIR/dns-supervise.sh" "$1"
    ;;
  apply)
    [ -n "${1:-}" ] || { usage; exit 2; }
    "$SCRIPT_DIR/dns-apply.sh" "$@"
    ;;
  status)
    [ -n "${1:-}" ] || { usage; exit 2; }
    ID="$1"
    R="$(reviews_dir)"
    echo "Plan        : $([ -f "$R/$ID.plan.json" ] && echo "yes" || echo "no")"
    echo "Verdict     : $([ -f "$R/$ID.verdict.md" ] && echo "yes" || echo "no")"
    if [ -f "$R/$ID.verdict.md" ]; then
      tail -n 1 "$R/$ID.verdict.md" | sed 's/^/   /'
    fi
    echo "Approved    : $([ -f "$R/$ID.approved" ] && echo "yes" || echo "no")"
    echo "Applied     : $([ -f "$R/$ID.applied.json" ] && echo "yes" || echo "no")"
    echo "Failed      : $([ -f "$R/$ID.failed.json" ] && echo "yes" || echo "no")"
    ;;
  list)
    R="$(reviews_dir)"
    # Build a one-line summary per plan id present.
    ls -1 "$R"/*.plan.json 2>/dev/null | while read -r f; do
      ID="$(basename "$f" .plan.json)"
      v="$(tail -n 1 "$R/$ID.verdict.md" 2>/dev/null || echo "-")"
      a="$([ -f "$R/$ID.approved" ] && echo "approved" || echo "—")"
      ap="$([ -f "$R/$ID.applied.json" ] && echo "applied" || echo "—")"
      printf '%-32s  %-30s  %-9s  %-7s\n' "$ID" "$v" "$a" "$ap"
    done
    ;;
  roles)
    DOC="$PROJECT_ROOT/ai-coworkers/dns-edit-role.md"
    if [ -f "$DOC" ]; then cat "$DOC"; else echo "(role doc missing at $DOC)"; fi
    ;;
  ''|-h|--help|help)
    usage
    ;;
  *)
    usage
    exit 2
    ;;
esac
