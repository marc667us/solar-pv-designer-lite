#!/usr/bin/env bash
# Cloudflare provider module for the DNS-edit skill.
#
# What this does:
#   - Provides functions for Cloudflare API v4 operations the skill needs:
#       cf_list_zones                              -> array of {id, name}
#       cf_get_zone_id <domain>                    -> zone id or empty
#       cf_list_records <zone-id>                  -> array of records
#       cf_find_record <zone-id> <type> <name>     -> record object or empty
#       cf_create_record <zone-id> <plan-json>     -> created record
#       cf_update_record <zone-id> <rec-id> <plan> -> updated record
#       cf_delete_record <zone-id> <rec-id>        -> deletion confirmation
#       cf_add_zone <domain>                       -> created zone (incl. NS)
#       cf_apply <plan-json-path>                  -> dispatch on operation
#
# Inputs:   CLOUDFLARE_API_TOKEN env var (scopes: Zone:Edit, Zone:DNS:Edit, Zone:SSL:Edit)
# Outputs:  JSON to stdout per function; log lines to stderr; non-zero exit on API errors
# Syntax notes:
#   - All API calls go through curl_json (defined in _lib.sh) which sets
#     DNS_LAST_HTTP_CODE for response-code checks.
#   - Cloudflare v4 wraps everything in {success, errors, result}; we unwrap to
#     just .result on success and surface .errors on failure.
#   - Record name in CF API is the full FQDN ("solarpro.aiappinvent.com"), not
#     a leaf — plan.json carries the leaf, we join with zone here.

set -e

# Source the shared lib if not already loaded.
if ! type curl_json >/dev/null 2>&1; then
  . "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
fi

CF_API="https://api.cloudflare.com/client/v4"

# cf_auth_header -- echo the bearer header. Used in every call.
# Why a function: makes it easy to swap to a key/email pair later without
# rewriting each caller.
cf_auth_header() {
  require_env CLOUDFLARE_API_TOKEN
  printf 'Authorization: Bearer %s' "$CLOUDFLARE_API_TOKEN"
}

# cf_check_success -- read CF API response on stdin; if success=false, print
# errors to stderr and return 1. Otherwise print .result to stdout.
cf_check_success() {
  python - <<'PY'
import json, sys
try:
    data = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print(f"Cloudflare returned non-JSON: {e}", file=sys.stderr)
    sys.exit(2)
if not data.get('success', False):
    errs = data.get('errors', [])
    for e in errs:
        print(f"CF error {e.get('code')}: {e.get('message')}", file=sys.stderr)
    sys.exit(1)
print(json.dumps(data.get('result'), indent=2))
PY
}

# cf_list_zones -- GET /zones, return array of {id, name, status, nameservers}.
cf_list_zones() {
  curl_json GET "$CF_API/zones?per_page=50" "$(cf_auth_header)" </dev/null \
    | cf_check_success
}

# cf_get_zone_id <domain> -- look up zone id by zone name.
# Cloudflare zones are registered by apex domain (e.g., aiappinvent.com),
# not by subdomain. We accept either and strip down to the apex if needed.
cf_get_zone_id() {
  local domain="$1"
  # Reduce a subdomain to the registered apex by walking from right to left
  # until we find a registered zone. CF doesn't expose a "get apex" call so
  # we list and match.
  cf_list_zones | python - "$domain" <<'PY'
import json, sys
domain = sys.argv[1]
zones = json.load(sys.stdin) or []
# Try exact match first, then progressively-trimmed left labels.
candidates = [domain]
parts = domain.split('.')
for i in range(1, len(parts) - 1):
    candidates.append('.'.join(parts[i:]))
by_name = {z['name']: z['id'] for z in zones}
for c in candidates:
    if c in by_name:
        print(by_name[c])
        sys.exit(0)
# No match — exit silently with empty stdout.
PY
}

# cf_list_records <zone-id> [type] [name] -- list DNS records in a zone.
# Optional type+name filter for finding a specific record before update/delete.
cf_list_records() {
  local zone_id="$1" type="${2:-}" name="${3:-}"
  local q="per_page=100"
  [ -n "$type" ] && q="$q&type=$type"
  [ -n "$name" ] && q="$q&name=$name"
  curl_json GET "$CF_API/zones/$zone_id/dns_records?$q" "$(cf_auth_header)" </dev/null \
    | cf_check_success
}

# cf_find_record <zone-id> <type> <name-fqdn> -- return the matching record
# object or empty string. Used by update/delete to look up id from plan fields.
cf_find_record() {
  local zone_id="$1" type="$2" name="$3"
  cf_list_records "$zone_id" "$type" "$name" | python - <<'PY'
import json, sys
recs = json.load(sys.stdin) or []
if recs:
    print(json.dumps(recs[0], indent=2))
PY
}

# _cf_record_body PLAN_JSON ZONE_NAME -- read a plan.json on stdin and emit
# the request body Cloudflare expects: {type, name, content, ttl, proxied}.
# Joins the plan's leaf record.name with the zone to form the FQDN.
_cf_record_body() {
  local zone_name="$1"
  python - "$zone_name" <<'PY'
import json, sys
zone = sys.argv[1]
plan = json.load(sys.stdin)
rec = plan['record']
leaf = rec.get('name', '@')
# '@' means apex; otherwise join leaf.zone unless leaf is already FQDN.
if leaf in ('@', '', zone):
    fqdn = zone
elif leaf.endswith('.' + zone):
    fqdn = leaf
else:
    fqdn = f"{leaf}.{zone}"
body = {
    'type': rec['type'],
    'name': fqdn,
    'content': rec['value'],
    'ttl': rec.get('ttl', 1),  # 1 == "auto"
    'proxied': bool(rec.get('proxied', False)),
}
print(json.dumps(body))
PY
}

# cf_create_record <zone-id> <zone-name> <plan-json-path> -- POST a new record.
cf_create_record() {
  local zone_id="$1" zone_name="$2" plan="$3"
  local body
  body="$(_cf_record_body "$zone_name" < "$plan")"
  printf '%s' "$body" \
    | curl_json POST "$CF_API/zones/$zone_id/dns_records" "$(cf_auth_header)" \
    | cf_check_success
}

# cf_update_record <zone-id> <zone-name> <rec-id> <plan-json-path>.
cf_update_record() {
  local zone_id="$1" zone_name="$2" rec_id="$3" plan="$4"
  local body
  body="$(_cf_record_body "$zone_name" < "$plan")"
  printf '%s' "$body" \
    | curl_json PUT "$CF_API/zones/$zone_id/dns_records/$rec_id" "$(cf_auth_header)" \
    | cf_check_success
}

# cf_delete_record <zone-id> <rec-id>.
cf_delete_record() {
  local zone_id="$1" rec_id="$2"
  curl_json DELETE "$CF_API/zones/$zone_id/dns_records/$rec_id" "$(cf_auth_header)" </dev/null \
    | cf_check_success
}

# cf_add_zone <apex-domain> -- POST a new zone (registers domain with CF).
# CF returns assigned nameservers in result.name_servers — owner pastes these at
# the registrar (Namecheap) to delegate. Type=full means full DNS hosting.
cf_add_zone() {
  local domain="$1"
  printf '{"name":"%s","type":"full"}' "$domain" \
    | curl_json POST "$CF_API/zones" "$(cf_auth_header)" \
    | cf_check_success
}

# cf_apply <plan-json-path> -- dispatcher used by dns-apply.sh.
# Reads operation + provider-specific fields from the plan and routes to the
# right verb. Writes the API response to stdout for the caller to persist.
cf_apply() {
  local plan="$1"
  local op zone
  op="$(json_get operation < "$plan")"
  zone="$(json_get zone < "$plan")"

  case "$op" in
    add_domain)
      cf_add_zone "$zone"
      ;;
    create_record|add_subdomain)
      local zone_id
      zone_id="$(cf_get_zone_id "$zone")"
      [ -n "$zone_id" ] || { log ERROR "Zone $zone not found in Cloudflare account"; return 1; }
      cf_create_record "$zone_id" "$zone" "$plan"
      ;;
    update_record)
      local zone_id type leaf fqdn rec_id
      zone_id="$(cf_get_zone_id "$zone")"
      [ -n "$zone_id" ] || { log ERROR "Zone $zone not found in Cloudflare account"; return 1; }
      type="$(json_get record.type < "$plan")"
      leaf="$(json_get record.name < "$plan")"
      if [ "$leaf" = "@" ] || [ -z "$leaf" ]; then fqdn="$zone"
      elif [[ "$leaf" == *".$zone" ]]; then fqdn="$leaf"
      else fqdn="$leaf.$zone"; fi
      rec_id="$(cf_find_record "$zone_id" "$type" "$fqdn" | json_get id)"
      [ -n "$rec_id" ] || { log ERROR "Existing $type record for $fqdn not found"; return 1; }
      cf_update_record "$zone_id" "$zone" "$rec_id" "$plan"
      ;;
    delete_record)
      local zone_id type leaf fqdn rec_id
      zone_id="$(cf_get_zone_id "$zone")"
      [ -n "$zone_id" ] || { log ERROR "Zone $zone not found"; return 1; }
      type="$(json_get record.type < "$plan")"
      leaf="$(json_get record.name < "$plan")"
      if [ "$leaf" = "@" ] || [ -z "$leaf" ]; then fqdn="$zone"
      elif [[ "$leaf" == *".$zone" ]]; then fqdn="$leaf"
      else fqdn="$leaf.$zone"; fi
      rec_id="$(cf_find_record "$zone_id" "$type" "$fqdn" | json_get id)"
      [ -n "$rec_id" ] || { log ERROR "Record $type $fqdn not found (already deleted?)"; return 1; }
      cf_delete_record "$zone_id" "$rec_id"
      ;;
    *)
      log ERROR "Cloudflare provider does not support operation: $op"
      return 1
      ;;
  esac
}
