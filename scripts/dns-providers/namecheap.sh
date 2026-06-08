#!/usr/bin/env bash
# Namecheap provider module for the DNS-edit skill.
#
# Heads-up: Namecheap's API is *not* available on every plan tier and requires
# a whitelisted client IP. When unavailable, this module fails fast with a clear
# message instead of hanging. The solar-pv-designer-lite owner's current plan
# does NOT have API access — this module is here for completeness and for the
# day the plan is upgraded; until then, use the Cloudflare module.
#
# What this does:
#   - nc_get_hosts <domain>   -> current host records (XML -> JSON)
#   - nc_set_hosts <domain> <plan-json-path>
#                              -> REPLACE entire host record set for a domain.
#                                 Namecheap's setHosts is whole-domain, not
#                                 single-record; we read current set, splice the
#                                 plan's record in/out, then write back.
#   - nc_apply <plan-json-path>
#
# Inputs:   NAMECHEAP_API_USER, NAMECHEAP_API_KEY, NAMECHEAP_USERNAME,
#           NAMECHEAP_CLIENT_IP  (all required)
# Outputs:  JSON to stdout; log lines to stderr
#
# Syntax notes:
#   - Namecheap returns XML. We use python's xml.etree to convert to JSON before
#     handing off to downstream tools — keeps the rest of the skill XML-free.

set -e

if ! type curl_json >/dev/null 2>&1; then
  . "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
fi

NC_API="https://api.namecheap.com/xml.response"
# Production endpoint. The sandbox at api.sandbox.namecheap.com behaves
# identically but requires a separate sandbox account; not used here.

# nc_require -- enforce env preconditions with a friendly error pointing at the
# Namecheap settings page so the owner knows where to fix it.
nc_require() {
  require_env NAMECHEAP_API_USER NAMECHEAP_API_KEY NAMECHEAP_USERNAME NAMECHEAP_CLIENT_IP || {
    log ERROR "Namecheap API needs four vars. Configure at:"
    log ERROR "  https://ap.www.namecheap.com/settings/tools/apiaccess/"
    log ERROR "Also whitelist your client IP (NAMECHEAP_CLIENT_IP) on the same page."
    log ERROR "Note: API access requires a qualifying plan tier; if you cannot"
    log ERROR "enable API in the dashboard, use the Cloudflare provider instead."
    return 1
  }
}

# _nc_split_domain <fqdn-or-apex> -- echo "SLD\nTLD" on two lines.
# Namecheap's API takes SLD (second-level) and TLD separately: "aiappinvent"
# and "com" for aiappinvent.com.
_nc_split_domain() {
  python - "$1" <<'PY'
import sys
d = sys.argv[1]
parts = d.split('.')
# Reduce subdomain to apex by taking last two labels (works for .com, .org;
# multi-label TLDs like .co.uk would need PSL — out of scope for v1).
if len(parts) < 2:
    sys.exit(2)
apex = parts[-2:] if len(parts) > 2 else parts
print(apex[0])
print(apex[1])
PY
}

# nc_get_hosts <domain> -- call namecheap.domains.dns.getHosts and return the
# host records as a JSON array on stdout.
nc_get_hosts() {
  local domain="$1"
  nc_require
  local sld tld
  IFS=$'\n' read -r sld tld < <(_nc_split_domain "$domain")
  # GET request; no body. We use --get with -d for clean URL encoding.
  local resp
  resp="$(curl -sS --get \
    --data-urlencode "ApiUser=$NAMECHEAP_API_USER" \
    --data-urlencode "ApiKey=$NAMECHEAP_API_KEY" \
    --data-urlencode "UserName=$NAMECHEAP_USERNAME" \
    --data-urlencode "ClientIp=$NAMECHEAP_CLIENT_IP" \
    --data-urlencode "Command=namecheap.domains.dns.getHosts" \
    --data-urlencode "SLD=$sld" \
    --data-urlencode "TLD=$tld" \
    "$NC_API")"
  printf '%s' "$resp" | _nc_xml_hosts_to_json
}

# _nc_xml_hosts_to_json -- read Namecheap XML on stdin, emit JSON array of
# {Name, Type, Address, TTL, MXPref} on stdout. Also surfaces API errors.
_nc_xml_hosts_to_json() {
  python - <<'PY'
import sys, json
import xml.etree.ElementTree as ET
ns = {'nc': 'http://api.namecheap.com/xml.response'}
try:
    root = ET.fromstring(sys.stdin.read())
except ET.ParseError as e:
    print(json.dumps({'error': f'XML parse: {e}'}), file=sys.stderr)
    sys.exit(2)
status = root.attrib.get('Status', '')
if status != 'OK':
    errs = [e.text for e in root.findall('.//nc:Errors/nc:Error', ns)]
    print(json.dumps({'error': 'Namecheap API error', 'details': errs}), file=sys.stderr)
    sys.exit(1)
hosts = []
for h in root.findall('.//nc:host', ns):
    hosts.append({k: v for k, v in h.attrib.items()})
print(json.dumps(hosts, indent=2))
PY
}

# nc_set_hosts <domain> <plan-json-path> -- replace the entire host record set
# for the domain after splicing the plan's change (create/update/delete) into
# the current set. This is the only mutating call Namecheap exposes; it is
# atomic at the API level.
nc_set_hosts() {
  local domain="$1" plan="$2"
  nc_require
  local sld tld
  IFS=$'\n' read -r sld tld < <(_nc_split_domain "$domain")

  # Pull current records, splice plan change in.
  local merged
  merged="$(nc_get_hosts "$domain" \
    | python - "$plan" "$domain" <<'PY'
import json, sys, os
plan_path, domain = sys.argv[1], sys.argv[2]
current = json.load(sys.stdin)
with open(plan_path) as f:
    plan = json.load(f)
op = plan['operation']
rec = plan['record']
# Namecheap's leaf name "@" means apex; we use that directly.
leaf = rec.get('name', '@') or '@'
if leaf.endswith('.' + domain):
    leaf = leaf[: -(len(domain) + 1)]
if leaf == domain:
    leaf = '@'
# Match current records by (Type, Name) for update/delete.
def matches(h):
    return h.get('Type') == rec['type'] and h.get('Name') == leaf
if op in ('create_record', 'add_subdomain'):
    current = [h for h in current if not matches(h)]
    current.append({'Name': leaf, 'Type': rec['type'], 'Address': rec['value'],
                    'TTL': str(rec.get('ttl', 1800)), 'MXPref': str(rec.get('mxpref', 10))})
elif op == 'update_record':
    found = False
    for h in current:
        if matches(h):
            h['Address'] = rec['value']
            h['TTL'] = str(rec.get('ttl', h.get('TTL', 1800)))
            found = True
    if not found:
        print(f"No existing {rec['type']} record for '{leaf}' to update", file=sys.stderr)
        sys.exit(1)
elif op == 'delete_record':
    before = len(current)
    current = [h for h in current if not matches(h)]
    if len(current) == before:
        print(f"No {rec['type']} record for '{leaf}' to delete", file=sys.stderr)
        sys.exit(1)
else:
    print(f"namecheap setHosts does not support operation: {op}", file=sys.stderr)
    sys.exit(2)
print(json.dumps(current))
PY
  )"

  # Build the setHosts query string. Namecheap indexes records starting at 1.
  local args=()
  args+=(--data-urlencode "ApiUser=$NAMECHEAP_API_USER")
  args+=(--data-urlencode "ApiKey=$NAMECHEAP_API_KEY")
  args+=(--data-urlencode "UserName=$NAMECHEAP_USERNAME")
  args+=(--data-urlencode "ClientIp=$NAMECHEAP_CLIENT_IP")
  args+=(--data-urlencode "Command=namecheap.domains.dns.setHosts")
  args+=(--data-urlencode "SLD=$sld")
  args+=(--data-urlencode "TLD=$tld")

  # Python emits the index/parameter pairs for curl to consume.
  while IFS= read -r kv; do
    args+=(--data-urlencode "$kv")
  done < <(printf '%s' "$merged" | python - <<'PY'
import json, sys
hosts = json.load(sys.stdin)
for i, h in enumerate(hosts, 1):
    print(f"HostName{i}={h.get('Name', '@')}")
    print(f"RecordType{i}={h.get('Type')}")
    print(f"Address{i}={h.get('Address')}")
    print(f"TTL{i}={h.get('TTL', '1800')}")
    if h.get('Type') == 'MX':
        print(f"MXPref{i}={h.get('MXPref', '10')}")
PY
  )

  local resp
  resp="$(curl -sS --get "${args[@]}" "$NC_API")"
  # setHosts returns a Status="OK" element on success; surface body so the
  # apply step can write it to applied.json.
  printf '%s' "$resp" | python - <<'PY'
import sys, json
import xml.etree.ElementTree as ET
ns = {'nc': 'http://api.namecheap.com/xml.response'}
root = ET.fromstring(sys.stdin.read())
status = root.attrib.get('Status', '')
result = root.find('.//nc:DomainDNSSetHostsResult', ns)
ok = result is not None and result.attrib.get('IsSuccess') == 'true'
out = {'status': status, 'isSuccess': ok}
if not ok:
    out['errors'] = [e.text for e in root.findall('.//nc:Errors/nc:Error', ns)]
print(json.dumps(out, indent=2))
if not ok:
    sys.exit(1)
PY
}

# nc_apply <plan-json-path> -- dispatcher.
# Namecheap supports record CRUD on existing domains; adding a domain is a
# purchase operation we deliberately do NOT automate.
nc_apply() {
  local plan="$1"
  local op zone
  op="$(json_get operation < "$plan")"
  zone="$(json_get zone < "$plan")"
  case "$op" in
    create_record|add_subdomain|update_record|delete_record)
      nc_set_hosts "$zone" "$plan"
      ;;
    add_domain)
      log ERROR "Namecheap add_domain is a domain purchase — not automated. Register the domain manually then re-run as create_record."
      return 1
      ;;
    *)
      log ERROR "Namecheap provider does not support operation: $op"
      return 1
      ;;
  esac
}
