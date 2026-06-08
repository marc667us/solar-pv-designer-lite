#!/usr/bin/env bash
# Plan generator for the DNS-edit skill.
#
# What this does:
#   Reads a natural-language intent (e.g., "Point solarpro.aiappinvent.com to
#   solarpro-global.onrender.com via Cloudflare CNAME") and produces a
#   reviews/dns/<id>.plan.json that fully specifies the change.
#
# Why a separate plan step:
#   The Supervisor reviews a structured plan, not the intent. Decoupling the
#   intent from the plan lets the Supervisor reason about exactly what will hit
#   the provider API — no surprises at apply time.
#
# Inputs:
#   $1 -- natural-language intent (required)
#   Optional env:
#     DNS_PLAN_BACKEND=codex|ollama   (default: codex)
#     DNS_PLAN_MODEL=llama3.2|mistral (only for ollama backend)
#
# Outputs:
#   reviews/dns/<id>.plan.json  -- the plan (schema in ai-coworkers/dns-edit-role.md)
#   reviews/dns/<id>.intent.txt -- verbatim intent (for the audit trail)
#   plan id is echoed to stdout (one line) for piping into supervise/apply.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/dns-providers/_lib.sh"
load_env

if [ -z "${1:-}" ]; then
  echo "Usage: $0 \"<natural-language intent>\"" >&2
  exit 1
fi

INTENT="$1"
ID="$(plan_id)"
REVIEWS="$(reviews_dir)"
PLAN_PATH="$REVIEWS/$ID.plan.json"
INTENT_PATH="$REVIEWS/$ID.intent.txt"

printf '%s\n' "$INTENT" > "$INTENT_PATH"

# Build the planner prompt. We give the reviewer the role contract, the schema,
# the provider list, the current env-var availability, and the intent.
PLANNER_BACKEND="${DNS_PLAN_BACKEND:-codex}"

# Detect which provider tokens are present so the planner doesn't suggest a
# provider the operator can't actually call. We don't print the token values.
PROVIDERS_AVAILABLE=""
[ -n "${CLOUDFLARE_API_TOKEN:-}" ] && PROVIDERS_AVAILABLE="$PROVIDERS_AVAILABLE cloudflare"
[ -n "${RENDER_API_KEY:-}" ]      && PROVIDERS_AVAILABLE="$PROVIDERS_AVAILABLE render"
[ -n "${RAILWAY_API_TOKEN:-}" ]   && PROVIDERS_AVAILABLE="$PROVIDERS_AVAILABLE railway"
if [ -n "${NAMECHEAP_API_KEY:-}" ] && [ -n "${NAMECHEAP_CLIENT_IP:-}" ]; then
  PROVIDERS_AVAILABLE="$PROVIDERS_AVAILABLE namecheap"
fi
PROVIDERS_AVAILABLE="$(echo "$PROVIDERS_AVAILABLE" | xargs)"   # trim
[ -z "$PROVIDERS_AVAILABLE" ] && PROVIDERS_AVAILABLE="(none — no provider env vars set; planner should refuse)"

# Read the role contract for the planner prompt so the model has the schema.
ROLE_DOC="$PROJECT_ROOT/ai-coworkers/dns-edit-role.md"
ROLE_BODY=""
[ -f "$ROLE_DOC" ] && ROLE_BODY="$(cat "$ROLE_DOC")"

PROMPT=$(cat <<EOF
You are the DNS planner in a Claude+Codex+Supervisor pair-coding workflow.

YOUR JOB: read the operator's intent, decide the SAFEST single provider+operation
that satisfies it, and emit a single JSON object matching the schema below.
Output ONLY the JSON — no markdown fences, no commentary.

PROVIDERS AVAILABLE (env tokens present in current shell): $PROVIDERS_AVAILABLE

SCHEMA:
{
  "id": "<must equal $ID>",
  "request": "<verbatim copy of the operator's intent>",
  "provider": "cloudflare | render | namecheap | railway",
  "operation": "add_domain | add_subdomain | create_record | update_record | delete_record",
  "zone": "<apex domain, e.g. aiappinvent.com>",
  "record": {
    "type": "A | AAAA | CNAME | TXT | MX",
    "name": "<leaf label, '@' for apex>",
    "value": "<target>",
    "ttl": 300,
    "proxied": false
  },
  "provider_options": { /* optional: render service_id, railway project/service/env, etc. */ },
  "rationale": "<one paragraph why this is the right change>",
  "rollback": "<concrete reversal — prior value for updates, delete-by-id for creates>",
  "risk": "low | medium | high",
  "production": false,
  "verification": [
    "<command 1, e.g. dig +short ...>",
    "<command 2, e.g. curl -sS -o /dev/null -w '%{http_code}\\\\n' ...>"
  ]
}

HARD RULES:
- If the intent mentions a provider you don't have an env token for, refuse: emit
  {"error": "..."} only.
- If the intent is ambiguous about the zone, pick the closest match and explain
  in rationale.
- For CNAME pointing a custom domain at a hosting provider, set ttl to 300 unless
  the intent says otherwise.
- Risk: "low" for non-production new records; "medium" for any update on a record
  in a known prod zone; "high" for wildcards or deletes.

ROLE CONTRACT (for context):
$ROLE_BODY

INTENT:
$INTENT
EOF
)

# Run the planner via either Codex CLI or Ollama, same call pattern as
# scripts/_codex-runner.sh. We need the raw JSON back, not markdown — the
# runners already pass prompts straight; we just capture stdout.
PLANNER_OUT="$REVIEWS/$ID.planner.raw"

run_planner() {
  case "$PLANNER_BACKEND" in
    codex)
      local codex_bin
      if command -v codex >/dev/null 2>&1; then codex_bin=codex
      elif [ -x "/c/Users/USER/nodejs/codex.cmd" ]; then codex_bin="/c/Users/USER/nodejs/codex.cmd"
      else log ERROR "codex CLI not found"; return 1
      fi
      "$codex_bin" exec --skip-git-repo-check -s workspace-write "$PROMPT"
      ;;
    ollama)
      python - "${DNS_PLAN_MODEL:-llama3.2}" "${OLLAMA_HOST:-http://localhost:11434}" "$PROMPT" <<'PY'
import json, sys, urllib.request
model, host, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
body = json.dumps({
    "model": model, "prompt": prompt, "stream": False,
    "options": {"num_predict": 1500, "num_ctx": 8192, "temperature": 0.1},
}).encode()
req = urllib.request.Request(f"{host}/api/generate", data=body,
                             headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=900) as r:
    print(json.loads(r.read()).get("response", ""))
PY
      ;;
    *)
      log ERROR "Unknown DNS_PLAN_BACKEND: $PLANNER_BACKEND (expected: codex | ollama)"
      return 1
      ;;
  esac
}

log INFO "Planning ($PLANNER_BACKEND) — id=$ID"
run_planner > "$PLANNER_OUT"

# Extract the JSON object from the planner output. Reviewers sometimes wrap in
# ```json ... ``` despite being told not to; strip those defensively.
python - "$PLANNER_OUT" "$PLAN_PATH" "$ID" "$INTENT" <<'PY'
import json, sys, re, pathlib, hashlib
raw = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8', errors='replace')
target = pathlib.Path(sys.argv[2])
plan_id = sys.argv[3]
intent  = sys.argv[4]

# Strip code fences if present.
m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.S)
candidate = m.group(1) if m else None
if not candidate:
    # Take the first balanced { ... } block.
    s = raw.find('{')
    if s < 0:
        print("Planner did not emit a JSON object", file=sys.stderr); sys.exit(2)
    depth, end = 0, -1
    for i, ch in enumerate(raw[s:], s):
        if ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0: end = i + 1; break
    if end < 0:
        print("Unbalanced JSON braces in planner output", file=sys.stderr); sys.exit(2)
    candidate = raw[s:end]

try:
    plan = json.loads(candidate)
except json.JSONDecodeError as e:
    print(f"Planner output is not valid JSON: {e}", file=sys.stderr); sys.exit(2)

if 'error' in plan:
    print(f"Planner refused: {plan['error']}", file=sys.stderr); sys.exit(3)

# Force the id + request to match what the operator actually provided. The
# planner sometimes drifts; the supervisor expects these to be authoritative.
plan['id'] = plan_id
plan['request'] = intent

# Minimal schema check before persisting.
required = ['provider', 'operation', 'zone', 'record', 'rationale', 'rollback', 'risk']
missing = [k for k in required if k not in plan]
if missing:
    print(f"Planner output missing required fields: {missing}", file=sys.stderr); sys.exit(2)

# Compute and embed the canonical checksum so the supervisor can sign it.
plan.pop('checksum', None)
canon = json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()
plan['checksum'] = hashlib.sha256(canon).hexdigest()

target.write_text(json.dumps(plan, indent=2) + "\n", encoding='utf-8')
print(f"Wrote {target}")
PY

# Emit the id so a calling script can chain: ID=$(dns-plan.sh "..."); dns-supervise.sh "$ID"
printf '%s\n' "$ID"
