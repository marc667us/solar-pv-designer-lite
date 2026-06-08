#!/usr/bin/env bash
# Shared helpers for the DNS-edit skill.
# Sourced by dns-plan.sh, dns-supervise.sh, dns-apply.sh, and every provider module.
#
# What this provides:
#   - load_env            : reads .env at project root into the shell (safe parser)
#   - json_get KEY        : extracts a key from a JSON blob on stdin (no jq dependency)
#   - json_set KEY VALUE  : sets a key in a JSON blob on stdin
#   - canonical_json      : sorts keys + strips whitespace (for checksums)
#   - sha256              : sha256 over stdin -> hex
#   - plan_id             : generates dns-<UTC-ISO-with-dashes> id
#   - reviews_dir         : echoes the absolute reviews/dns directory (and mkdir -p's it)
#   - require_env VAR     : fails with a clear message if VAR is unset
#   - log INFO|WARN|ERROR : timestamped stderr log
#
# Inputs:   sourced; functions read args + stdin per their signatures above
# Outputs:  stdout/stderr per function; exit codes follow shell conventions
# Syntax notes:
#   - "set -e" is NOT applied here so callers can choose. Callers should set -e.
#   - We use python for all JSON handling. Same pattern as scripts/_codex-runner.sh.
#   - Heredocs use 'PY' (quoted) so $vars are NOT expanded by the shell — python
#     handles its own quoting via sys.argv.

# Find project root: this file is in scripts/dns-providers/, so two dirs up.
DNS_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$DNS_LIB_DIR/../.." && pwd)"

# load_env: read .env at project root into current shell.
# Skips comment lines and blank lines. Does NOT eval — splits on first '=' only.
# This keeps secrets out of the shell history and avoids the classic
# `eval $(cat .env)` injection footgun.
load_env() {
  local envfile="$PROJECT_ROOT/.env"
  [ -f "$envfile" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ''|'#'*) continue ;;          # blank or comment
      *=*)
        local key="${line%%=*}"
        local val="${line#*=}"
        # Strip surrounding double or single quotes if present
        val="${val%\"}"; val="${val#\"}"
        val="${val%\'}"; val="${val#\'}"
        export "$key=$val"
        ;;
    esac
  done < "$envfile"
}

# require_env VAR [VAR ...]: fails fast if any var is unset/empty.
# Used by provider modules so a missing token surfaces a clear message instead
# of a curl 401 deep in the call chain.
require_env() {
  local missing=()
  for v in "$@"; do
    if [ -z "${!v}" ]; then
      missing+=("$v")
    fi
  done
  if [ ${#missing[@]} -gt 0 ]; then
    log ERROR "Missing required env var(s): ${missing[*]}"
    log ERROR "Set in shell or in $PROJECT_ROOT/.env then re-run."
    return 1
  fi
}

# log LEVEL MESSAGE...: timestamped log to stderr so command stdout stays clean.
# Levels are conventional — no color, no ANSI, since logs are tee'd to files.
log() {
  local level="$1"; shift
  printf '[%s] [%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$level" "$*" >&2
}

# json_get KEY  -- read key from JSON on stdin, print value to stdout.
# Supports dotted keys: json_get "record.value"
# Prints nothing + exits 0 if key is missing (callers check empty string).
# Syntax note: `python - <<'PY'` consumes stdin for the SCRIPT body, so we
# capture the upstream pipeline's stdin into argv first via $(cat). Same
# pattern is used by json_set, canonical_json, sha256, checksum_plan below.
json_get() {
  local key="$1"
  local input
  input="$(cat)"
  python - "$key" "$input" <<'PY'
import json, sys
key, raw = sys.argv[1], sys.argv[2]
if not raw.strip():
    sys.exit(0)
data = json.loads(raw)
for part in key.split('.'):
    if isinstance(data, dict) and part in data:
        data = data[part]
    else:
        sys.exit(0)
if isinstance(data, (dict, list)):
    print(json.dumps(data))
elif isinstance(data, bool):
    print('true' if data else 'false')
elif data is None:
    print('')
else:
    print(data)
PY
}

# json_set KEY VALUE -- read JSON on stdin, set key, print new JSON to stdout.
# VALUE is parsed as JSON if it looks like JSON; otherwise treated as a string.
# Supports dotted keys (creates intermediate objects).
json_set() {
  local key="$1" value="$2"
  local input
  input="$(cat)"
  python - "$key" "$value" "$input" <<'PY'
import json, sys
key, raw_val, raw_in = sys.argv[1], sys.argv[2], sys.argv[3]
data = json.loads(raw_in) if raw_in.strip() else {}
try:
    val = json.loads(raw_val)
except (json.JSONDecodeError, ValueError):
    val = raw_val
parts = key.split('.')
cur = data
for part in parts[:-1]:
    if part not in cur or not isinstance(cur[part], dict):
        cur[part] = {}
    cur = cur[part]
cur[parts[-1]] = val
print(json.dumps(data, indent=2, sort_keys=False))
PY
}

# canonical_json -- read JSON on stdin, print stable canonical form (sorted keys,
# no whitespace) to stdout. Used as the checksum input so cosmetic re-saves
# don't invalidate the supervisor's signature.
canonical_json() {
  local input
  input="$(cat)"
  python - "$input" <<'PY'
import json, sys
raw = sys.argv[1]
data = json.loads(raw)
print(json.dumps(data, sort_keys=True, separators=(',', ':')))
PY
}

# sha256 -- read text on stdin, print hex digest to stdout. We keep this as
# text-only since every caller hashes JSON or a checksum string.
sha256() {
  local input
  input="$(cat)"
  python - "$input" <<'PY'
import hashlib, sys
print(hashlib.sha256(sys.argv[1].encode('utf-8')).hexdigest())
PY
}

# plan_id -- emit a sortable plan id: dns-YYYY-MM-DDTHH-MM-SSZ
# Colons in ISO timestamps break Windows filenames so we replace them.
plan_id() {
  date -u +'dns-%Y-%m-%dT%H-%M-%SZ'
}

# reviews_dir -- echo absolute path to reviews/dns, creating it if missing.
reviews_dir() {
  local d="$PROJECT_ROOT/reviews/dns"
  mkdir -p "$d"
  printf '%s\n' "$d"
}

# checksum_plan PATH -- canonicalize the plan body (excluding the checksum field
# itself) and emit its sha256. Used at sign time and verify time.
checksum_plan() {
  local path="$1"
  python - "$path" <<'PY'
import json, sys, hashlib
path = sys.argv[1]
with open(path, 'rb') as f:
    data = json.load(f)
# Exclude the 'checksum' field from the canonical form so it can be written into
# the same file afterwards without changing the digest.
data.pop('checksum', None)
canon = json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')
print(hashlib.sha256(canon).hexdigest())
PY
}

# curl_json METHOD URL [HEADER ...] -- wraps curl for JSON API calls.
# Stdin is sent as the request body (use </dev/null for GET/DELETE).
# Stdout is the response body. Sets DNS_LAST_HTTP_CODE for the caller to check.
# Why: every provider does the same auth-header dance; centralizing avoids drift.
curl_json() {
  local method="$1" url="$2"; shift 2
  local hdrs=()
  for h in "$@"; do hdrs+=(-H "$h"); done
  # -sS: silent but show errors; -w: append HTTP code on its own line so we can
  # split it from the body. --data-binary @- streams stdin as the body.
  local tmp
  tmp="$(mktemp)"
  local code
  code="$(curl -sS -X "$method" "${hdrs[@]}" -H 'Accept: application/json' \
    -H 'Content-Type: application/json' --data-binary @- \
    -o "$tmp" -w '%{http_code}' "$url")"
  DNS_LAST_HTTP_CODE="$code"
  cat "$tmp"
  rm -f "$tmp"
}
