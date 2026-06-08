#!/usr/bin/env bash
# Supervisor pass for the DNS-edit skill.
#
# What this does:
#   Reads reviews/dns/<id>.plan.json, runs hard safety checks in shell, then
#   asks the supervisor model to audit the plan against the role contract.
#   Writes a verdict markdown that ENDS with one of:
#       SUPERVISOR VERDICT: PASS
#       SUPERVISOR VERDICT: FAIL
#   On PASS, drops a zero-byte sentinel file <id>.approved alongside a
#   signature file <id>.approved.sha256 capturing the plan's checksum at
#   approval time. dns-apply.sh refuses to run without both.
#
# Inputs:
#   $1 -- plan id (e.g., dns-2026-06-08T15-22-03Z) OR full path to plan.json
#   Optional env:
#     DNS_SUPERVISOR_BACKEND=codex|ollama  (default: codex)
#
# Outputs:
#   reviews/dns/<id>.verdict.md
#   reviews/dns/<id>.approved          (only if PASS)
#   reviews/dns/<id>.approved.sha256   (only if PASS — signs the plan checksum)
#   Exit code: 0 on PASS, 1 on FAIL, 2 on hard-check failure (no model call)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/dns-providers/_lib.sh"
load_env

if [ -z "${1:-}" ]; then
  echo "Usage: $0 <plan-id-or-path>" >&2
  exit 1
fi

ARG="$1"
REVIEWS="$(reviews_dir)"
if [ -f "$ARG" ]; then
  PLAN_PATH="$ARG"
  ID="$(basename "$ARG" .plan.json)"
else
  ID="$ARG"
  PLAN_PATH="$REVIEWS/$ID.plan.json"
fi
[ -f "$PLAN_PATH" ] || { log ERROR "No plan at $PLAN_PATH"; exit 2; }

VERDICT_PATH="$REVIEWS/$ID.verdict.md"
APPROVED_PATH="$REVIEWS/$ID.approved"
SIG_PATH="$REVIEWS/$ID.approved.sha256"

# Hard checks — these run BEFORE the model call. If any fails, we FAIL fast
# without spending Codex/Ollama time. The supervisor still gets to refuse on
# softer grounds, but these are non-negotiable.
HARD_FINDINGS=""
hard_fail() { HARD_FINDINGS="${HARD_FINDINGS}- ${1}"$'\n'; }

PROVIDER="$(json_get provider < "$PLAN_PATH")"
OPERATION="$(json_get operation < "$PLAN_PATH")"
ZONE="$(json_get zone < "$PLAN_PATH")"
REC_TYPE="$(json_get record.type < "$PLAN_PATH")"
REC_NAME="$(json_get record.name < "$PLAN_PATH")"
REC_VALUE="$(json_get record.value < "$PLAN_PATH")"
REC_TTL="$(json_get record.ttl < "$PLAN_PATH")"
RISK="$(json_get risk < "$PLAN_PATH")"
ROLLBACK="$(json_get rollback < "$PLAN_PATH")"
PRODUCTION="$(json_get production < "$PLAN_PATH")"
PLAN_CHECKSUM="$(json_get checksum < "$PLAN_PATH")"

# Hard check 1: provider supported + token present
case "$PROVIDER" in
  cloudflare) [ -n "${CLOUDFLARE_API_TOKEN:-}" ] || hard_fail "CLOUDFLARE_API_TOKEN missing — Cloudflare API will fail at apply time." ;;
  render)     [ -n "${RENDER_API_KEY:-}" ]      || hard_fail "RENDER_API_KEY missing — Render API will fail at apply time." ;;
  namecheap)
    { [ -n "${NAMECHEAP_API_KEY:-}" ] && [ -n "${NAMECHEAP_API_USER:-}" ] && [ -n "${NAMECHEAP_USERNAME:-}" ] && [ -n "${NAMECHEAP_CLIENT_IP:-}" ]; } \
      || hard_fail "Namecheap env vars incomplete (need API_USER, API_KEY, USERNAME, CLIENT_IP)."
    ;;
  railway)    hard_fail "Railway provider is disabled in this project (dead infra). Switch provider." ;;
  *)          hard_fail "Unknown provider '$PROVIDER' — must be one of: cloudflare | render | namecheap." ;;
esac

# Hard check 2: TTL within sane bounds (or 1/'auto')
if [ -n "$REC_TTL" ] && [ "$REC_TTL" != "auto" ] && [ "$REC_TTL" != "1" ]; then
  if ! [[ "$REC_TTL" =~ ^[0-9]+$ ]] || [ "$REC_TTL" -lt 60 ] || [ "$REC_TTL" -gt 86400 ]; then
    hard_fail "TTL $REC_TTL outside allowed range (60–86400, or 'auto'/1)."
  fi
fi

# Hard check 3: wildcards require explicit high risk
case "$REC_NAME" in
  '*'|'*.'*)
    [ "$RISK" = "high" ] || hard_fail "Wildcard record '$REC_NAME' requires risk='high' (got '$RISK')."
    ;;
esac

# Hard check 4: blast radius — updates must include a rollback value
if [ "$OPERATION" = "update_record" ] || [ "$OPERATION" = "delete_record" ]; then
  [ -n "$ROLLBACK" ] && [ "$ROLLBACK" != "null" ] || hard_fail "$OPERATION requires a non-empty 'rollback' field describing reversal."
fi

# Hard check 5: target reachability for CNAME/A — don't point live hosts at dead origins.
# We do a HEAD with a short timeout. For CNAME we also resolve the target.
case "$REC_TYPE" in
  CNAME|A|AAAA)
    if [ -n "$REC_VALUE" ]; then
      # Try resolution first (CNAMEs point to names).
      if [ "$REC_TYPE" = "CNAME" ]; then
        if ! getent hosts "$REC_VALUE" >/dev/null 2>&1 && ! python -c "import socket,sys; socket.gethostbyname(sys.argv[1])" "$REC_VALUE" >/dev/null 2>&1; then
          hard_fail "Target '$REC_VALUE' does not resolve — this is the dead-origin bug. Refuse pointing at it."
        fi
      fi
      # HTTPS HEAD probe (best effort; 000 == no response).
      probe="$(curl -sS -o /dev/null --max-time 8 -w '%{http_code}' "https://$REC_VALUE/" 2>/dev/null || echo "000")"
      if [ "$probe" = "000" ]; then
        # Soft warning — some valid targets don't speak HTTPS (e.g., MX hosts).
        # We do NOT hard-fail; we surface in the supervisor prompt.
        SOFT_PROBE_WARN="Target '$REC_VALUE' did not respond to HTTPS HEAD (could be normal for non-HTTP targets)."
      fi
    fi
    ;;
esac

# Hard check 6: production-domain protection
PROD_ALLOWLIST="$SCRIPT_DIR/dns-providers/dns-edit.config"
if [ -f "$PROD_ALLOWLIST" ]; then
  if grep -Fxq "$ZONE" "$PROD_ALLOWLIST"; then
    if [ "$PRODUCTION" != "true" ]; then
      hard_fail "Zone '$ZONE' is in the production allowlist but plan production:false."
    fi
  fi
fi

# Recompute the plan's checksum from disk to confirm the file hasn't been
# tampered with since planning. The plan-side checksum was written by dns-plan.sh.
ACTUAL_CHECKSUM="$(checksum_plan "$PLAN_PATH")"
if [ "$PLAN_CHECKSUM" != "$ACTUAL_CHECKSUM" ]; then
  hard_fail "Plan checksum mismatch — file edited after planning (plan: $PLAN_CHECKSUM, actual: $ACTUAL_CHECKSUM)."
fi

# Build the supervisor prompt. The model gets the plan + the role contract +
# any soft warnings, and is asked to verify the soft items (zone authority,
# cert path coherence, etc.) the shell didn't enforce.
ROLE_DOC="$PROJECT_ROOT/ai-coworkers/dns-edit-role.md"
ROLE_BODY=""
[ -f "$ROLE_DOC" ] && ROLE_BODY="$(cat "$ROLE_DOC")"
PLAN_BODY="$(cat "$PLAN_PATH")"

SUPERVISOR_PROMPT=$(cat <<EOF
You are the Supervisor in a Claude+Codex+Supervisor pair-coding workflow,
auditing a DNS-change plan before it touches a provider API.

Refuse loudly if you have any doubt — the cost of a wrong DNS change is hours
of downtime. The cost of a false FAIL is one re-plan.

Hard checks already PASSED in shell (assume these are correct):
- provider env tokens present
- TTL in range
- wildcards have risk=high
- updates/deletes carry rollback text
- plan checksum matches file on disk

Your job — verify the soft checks the shell can't:
1. ZONE AUTHORITY: based on the provider field, does the zone make sense for
   that provider's account? (e.g., is "aiappinvent.com" actually delegated to
   Cloudflare?) If you have doubt, FAIL and ask the operator to confirm.
2. CERT PATH COHERENCE: if the plan attaches a custom domain at a hosting
   provider (Render), is there a matching DNS record planned or already in
   place at the DNS provider? Vice versa: if the plan creates a CNAME pointing
   at a hosting target, is the hosting side already attached? Mismatches keep
   certs from issuing — this exact gap kept solarpro.aiappinvent.com dark for
   a month.
3. SCOPE CREEP: does the plan do exactly one thing? Refuse multi-record plans;
   they belong as separate plans.
4. RATIONALE QUALITY: is the rationale specific enough that a future reader
   understands the change without re-asking the operator?

Soft warning from shell probe (may or may not be a real issue):
${SOFT_PROBE_WARN:-(none)}

Output format:
- A markdown report under headings ### Zone authority, ### Cert path coherence,
  ### Scope, ### Rationale, ### Other concerns.
- For each, state "PASS" or "FAIL" with a one-line reason.
- End the file with EXACTLY one of these two lines on its own line:
    SUPERVISOR VERDICT: PASS
    SUPERVISOR VERDICT: FAIL

ROLE CONTRACT:
$ROLE_BODY

PLAN TO REVIEW:
\`\`\`json
$PLAN_BODY
\`\`\`
EOF
)

SUPERVISOR_BACKEND="${DNS_SUPERVISOR_BACKEND:-codex}"

run_supervisor() {
  case "$SUPERVISOR_BACKEND" in
    codex)
      local codex_bin
      if command -v codex >/dev/null 2>&1; then codex_bin=codex
      elif [ -x "/c/Users/USER/nodejs/codex.cmd" ]; then codex_bin="/c/Users/USER/nodejs/codex.cmd"
      else log ERROR "codex CLI not found"; return 1
      fi
      "$codex_bin" exec --skip-git-repo-check -s workspace-write "$SUPERVISOR_PROMPT"
      ;;
    ollama)
      python - "${DNS_SUPERVISOR_MODEL:-mistral}" "${OLLAMA_HOST:-http://localhost:11434}" "$SUPERVISOR_PROMPT" <<'PY'
import json, sys, urllib.request
model, host, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
body = json.dumps({
    "model": model, "prompt": prompt, "stream": False,
    "options": {"num_predict": 1200, "num_ctx": 8192, "temperature": 0.1},
}).encode()
req = urllib.request.Request(f"{host}/api/generate", data=body,
                             headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=1200) as r:
    print(json.loads(r.read()).get("response", ""))
PY
      ;;
    *)
      log ERROR "Unknown DNS_SUPERVISOR_BACKEND: $SUPERVISOR_BACKEND"
      return 1
      ;;
  esac
}

# Write verdict header + hard findings + (if no hard failure) the model's audit.
{
  echo "# DNS Plan Verdict — $ID"
  echo ""
  echo "_Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ) · supervisor: ${SUPERVISOR_BACKEND}_"
  echo ""
  echo "## Plan summary"
  echo ""
  echo "- provider: $PROVIDER"
  echo "- operation: $OPERATION"
  echo "- zone: $ZONE"
  echo "- record: $REC_TYPE $REC_NAME -> $REC_VALUE (ttl=$REC_TTL)"
  echo "- risk: $RISK   production: $PRODUCTION"
  echo ""
  echo "## Hard checks"
  echo ""
  if [ -n "$HARD_FINDINGS" ]; then
    echo "FAILED:"
    echo ""
    printf '%s' "$HARD_FINDINGS"
  else
    echo "All hard checks passed."
  fi
  echo ""
} > "$VERDICT_PATH"

if [ -n "$HARD_FINDINGS" ]; then
  echo "" >> "$VERDICT_PATH"
  echo "SUPERVISOR VERDICT: FAIL" >> "$VERDICT_PATH"
  log WARN "Hard checks failed — supervisor FAIL written to $VERDICT_PATH"
  exit 1
fi

log INFO "Hard checks passed — running supervisor model ($SUPERVISOR_BACKEND)"
echo "## Supervisor audit" >> "$VERDICT_PATH"
echo "" >> "$VERDICT_PATH"
run_supervisor >> "$VERDICT_PATH" 2>>"$VERDICT_PATH" || true

# Determine verdict: look for the canonical line at the END of the file. If the
# model emitted "PASS" then we drop the approval sentinel + signature.
TAIL_LINE="$(grep -E '^SUPERVISOR VERDICT: (PASS|FAIL)\s*$' "$VERDICT_PATH" | tail -n 1 || true)"
if [ "$TAIL_LINE" = "SUPERVISOR VERDICT: PASS" ]; then
  : > "$APPROVED_PATH"
  printf '%s' "$ACTUAL_CHECKSUM" > "$SIG_PATH"
  log INFO "PASS — approval sentinel + signature written"
  exit 0
elif [ "$TAIL_LINE" = "SUPERVISOR VERDICT: FAIL" ]; then
  log WARN "FAIL — no sentinel written"
  exit 1
else
  # Defensive: if the model didn't emit a final verdict line, treat as FAIL.
  echo "" >> "$VERDICT_PATH"
  echo "SUPERVISOR VERDICT: FAIL" >> "$VERDICT_PATH"
  log WARN "No verdict line in model output — defaulting to FAIL"
  exit 1
fi
