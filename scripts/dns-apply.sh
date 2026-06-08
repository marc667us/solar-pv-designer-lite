#!/usr/bin/env bash
# Apply step for the DNS-edit skill — the only script that calls a provider API.
#
# What this does:
#   Reads reviews/dns/<id>.plan.json, refuses to run unless the Supervisor's
#   approval sentinel <id>.approved exists AND the signed checksum still matches
#   the plan on disk. On match, dispatches to the right provider module's
#   *_apply function. Persists the API response to <id>.applied.json on success
#   or <id>.failed.json on error.
#
# Inputs:
#   $1 -- plan id (or full path to plan.json)
#   --dry-run -- (optional) print what would run; touch nothing
#
# Outputs:
#   reviews/dns/<id>.applied.json  on success
#   reviews/dns/<id>.failed.json   on failure
#   Exit code: 0 on success, non-zero otherwise

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/dns-providers/_lib.sh"
load_env

DRY_RUN=0
ARG=""
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN=1 ;;
    -*) log ERROR "Unknown flag: $a"; exit 1 ;;
    *)  ARG="$a" ;;
  esac
done

if [ -z "$ARG" ]; then
  echo "Usage: $0 <plan-id-or-path> [--dry-run]" >&2
  exit 1
fi

REVIEWS="$(reviews_dir)"
if [ -f "$ARG" ]; then
  PLAN_PATH="$ARG"
  ID="$(basename "$ARG" .plan.json)"
else
  ID="$ARG"
  PLAN_PATH="$REVIEWS/$ID.plan.json"
fi
[ -f "$PLAN_PATH" ] || { log ERROR "No plan at $PLAN_PATH"; exit 2; }

APPROVED_PATH="$REVIEWS/$ID.approved"
SIG_PATH="$REVIEWS/$ID.approved.sha256"
APPLIED_PATH="$REVIEWS/$ID.applied.json"
FAILED_PATH="$REVIEWS/$ID.failed.json"

# Gate 1: approval sentinel must exist (supervisor PASS).
if [ ! -f "$APPROVED_PATH" ]; then
  log ERROR "No supervisor approval for $ID — refusing."
  log ERROR "Run: ./scripts/dns-supervise.sh $ID"
  exit 3
fi

# Gate 2: the checksum the supervisor signed must still match the plan on disk.
# Catches "edit plan after approval" attempts.
if [ ! -f "$SIG_PATH" ]; then
  log ERROR "Approval sentinel exists but no signature at $SIG_PATH — refusing."
  exit 3
fi
SIGNED_CHECKSUM="$(cat "$SIG_PATH")"
ACTUAL_CHECKSUM="$(checksum_plan "$PLAN_PATH")"
if [ "$SIGNED_CHECKSUM" != "$ACTUAL_CHECKSUM" ]; then
  log ERROR "Plan modified after approval — checksum drift."
  log ERROR "  signed: $SIGNED_CHECKSUM"
  log ERROR "  actual: $ACTUAL_CHECKSUM"
  log ERROR "Re-run dns-supervise.sh to re-approve the current plan."
  exit 3
fi

# Gate 3: provider module exists and is supported (Railway is disabled — dead infra).
PROVIDER="$(json_get provider < "$PLAN_PATH")"
case "$PROVIDER" in
  cloudflare|render|namecheap)
    PROVIDER_SH="$SCRIPT_DIR/dns-providers/$PROVIDER.sh"
    ;;
  railway)
    log ERROR "Railway provider is disabled in this project (dead infra). Re-plan with cloudflare or render."
    exit 4
    ;;
  *)
    log ERROR "Unknown provider in plan: $PROVIDER"
    exit 4
    ;;
esac
[ -f "$PROVIDER_SH" ] || { log ERROR "Provider module not found: $PROVIDER_SH"; exit 4; }

# Dispatch.
OPERATION="$(json_get operation < "$PLAN_PATH")"
ZONE="$(json_get zone < "$PLAN_PATH")"
log INFO "Applying $PROVIDER $OPERATION on $ZONE (plan=$ID)"

# Source the provider module so its *_apply function is in scope.
# shellcheck disable=SC1090
. "$PROVIDER_SH"

# Function name pattern: cf_apply | rd_apply | nc_apply (see provider modules).
case "$PROVIDER" in
  cloudflare) APPLY_FN=cf_apply ;;
  render)     APPLY_FN=rd_apply ;;
  namecheap)  APPLY_FN=nc_apply ;;
esac

if [ "$DRY_RUN" -eq 1 ]; then
  log INFO "[dry-run] would call: $APPLY_FN $PLAN_PATH"
  log INFO "[dry-run] plan body follows:"
  cat "$PLAN_PATH"
  exit 0
fi

# Run apply; capture stdout into applied.json on success or failed.json on
# non-zero exit. We do NOT `set +e` globally — the if-branch isolates the call.
TMP_OUT="$(mktemp)"
TMP_ERR="$(mktemp)"
if "$APPLY_FN" "$PLAN_PATH" >"$TMP_OUT" 2>"$TMP_ERR"; then
  mv "$TMP_OUT" "$APPLIED_PATH"
  log INFO "Apply OK — response at $APPLIED_PATH"
  # Echo a one-line success summary to stdout for callers.
  echo "OK $ID -> $APPLIED_PATH"
  rm -f "$TMP_ERR"
  # Run verification commands if the plan listed any (best effort — failures
  # don't roll back; they just get appended to applied.json so the operator
  # sees what verification said).
  python - "$PLAN_PATH" "$APPLIED_PATH" <<'PY' >/dev/null
import json, sys, subprocess
plan_path, applied_path = sys.argv[1], sys.argv[2]
with open(plan_path) as f: plan = json.load(f)
checks = plan.get('verification', []) or []
results = []
for cmd in checks:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
        results.append({'cmd': cmd, 'rc': r.returncode, 'stdout': r.stdout.strip()[:500]})
    except Exception as e:
        results.append({'cmd': cmd, 'error': str(e)})
with open(applied_path) as f: body = f.read()
out = {'provider_response': body, 'verification': results}
with open(applied_path, 'w') as f: f.write(json.dumps(out, indent=2))
PY
  exit 0
else
  rc=$?
  {
    echo "{"
    printf '  "plan_id": %s,\n' "\"$ID\""
    printf '  "provider": %s,\n' "\"$PROVIDER\""
    printf '  "exit_code": %d,\n' "$rc"
    printf '  "stderr": %s,\n' "$(python -c 'import json,sys; print(json.dumps(open(sys.argv[1]).read()))' "$TMP_ERR")"
    printf '  "stdout": %s\n' "$(python -c 'import json,sys; print(json.dumps(open(sys.argv[1]).read()))' "$TMP_OUT")"
    echo "}"
  } > "$FAILED_PATH"
  rm -f "$TMP_OUT" "$TMP_ERR"
  log ERROR "Apply failed — see $FAILED_PATH"
  exit "$rc"
fi
