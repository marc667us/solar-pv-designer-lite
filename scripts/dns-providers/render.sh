#!/usr/bin/env bash
# Render provider module for the DNS-edit skill.
#
# What this does:
#   - Wraps Render's REST API for custom-domain operations the skill needs:
#       rd_list_services                       -> list services on the account
#       rd_get_service_id <name>               -> id by service name
#       rd_list_domains <service-id>           -> custom domains attached
#       rd_attach_domain <service-id> <fqdn>   -> attach + return verification CNAME
#       rd_verify_domain <service-id> <dom-id> -> trigger Render-side verify
#       rd_detach_domain <service-id> <dom-id> -> remove
#       rd_apply <plan-json-path>              -> dispatch on operation
#
# Why this module exists alongside the DNS providers (Cloudflare/Namecheap):
#   "Custom domain" on Render is two halves —
#     (1) attach the domain at Render (this module), and
#     (2) point the DNS record at Render's target (Cloudflare/Namecheap module).
#   A complete plan often needs both halves; the supervisor's "cert path
#   coherence" check makes sure neither is missing.
#
# Inputs:   RENDER_API_KEY env var (already set in this project's CI secrets)
#           Optional: RENDER_SERVICE_ID env var (skip the by-name lookup)
# Outputs:  JSON to stdout; log lines to stderr; non-zero exit on API errors

set -e

if ! type curl_json >/dev/null 2>&1; then
  . "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
fi

RD_API="https://api.render.com/v1"

# rd_auth_header -- echo bearer header.
rd_auth_header() {
  require_env RENDER_API_KEY
  printf 'Authorization: Bearer %s' "$RENDER_API_KEY"
}

# rd_list_services -- GET /services.
# Render wraps each item in {service: {...}, cursor: "..."}; we unwrap to a plain
# array of services for easier downstream processing.
rd_list_services() {
  curl_json GET "$RD_API/services?limit=50" "$(rd_auth_header)" </dev/null \
    | python - <<'PY'
import json, sys
data = json.load(sys.stdin)
out = [item.get('service', item) for item in (data if isinstance(data, list) else [])]
print(json.dumps(out, indent=2))
PY
}

# rd_get_service_id <name> -- match by service name; empty if absent.
rd_get_service_id() {
  local name="$1"
  rd_list_services | python - "$name" <<'PY'
import json, sys
name = sys.argv[1]
svcs = json.load(sys.stdin) or []
for s in svcs:
    if s.get('name') == name:
        print(s.get('id', ''))
        break
PY
}

# rd_list_domains <service-id> -- GET /services/{id}/custom-domains.
rd_list_domains() {
  local svc="$1"
  curl_json GET "$RD_API/services/$svc/custom-domains" "$(rd_auth_header)" </dev/null \
    | python - <<'PY'
import json, sys
data = json.load(sys.stdin)
out = [item.get('customDomain', item) for item in (data if isinstance(data, list) else [])]
print(json.dumps(out, indent=2))
PY
}

# rd_attach_domain <service-id> <fqdn> -- POST /services/{id}/custom-domains.
# Render auto-creates a Let's Encrypt cert once the DNS CNAME points at the
# service's *.onrender.com URL. The response includes the verification target.
rd_attach_domain() {
  local svc="$1" fqdn="$2"
  printf '{"name":"%s"}' "$fqdn" \
    | curl_json POST "$RD_API/services/$svc/custom-domains" "$(rd_auth_header)"
}

# rd_verify_domain <service-id> <domain-id> -- POST verify.
# Idempotent on Render's side; safe to retry.
rd_verify_domain() {
  local svc="$1" dom="$2"
  printf '' \
    | curl_json POST "$RD_API/services/$svc/custom-domains/$dom/verify" "$(rd_auth_header)"
}

# rd_detach_domain <service-id> <domain-id> -- DELETE.
rd_detach_domain() {
  local svc="$1" dom="$2"
  curl_json DELETE "$RD_API/services/$svc/custom-domains/$dom" "$(rd_auth_header)" </dev/null
}

# rd_apply <plan-json-path> -- dispatcher used by dns-apply.sh.
# For Render we treat 'add_domain' / 'add_subdomain' as "attach to a service"
# and 'delete_record' as detach. 'create_record' / 'update_record' are NOT
# meaningful on Render — those belong to a DNS-hosting provider, so we refuse.
rd_apply() {
  local plan="$1"
  local op zone fqdn svc_id svc_name dom_id

  op="$(json_get operation < "$plan")"
  zone="$(json_get zone < "$plan")"

  case "$op" in
    add_domain|add_subdomain)
      # Compose FQDN from zone + record.name (leaf), same convention as Cloudflare.
      local leaf
      leaf="$(json_get record.name < "$plan")"
      if [ -z "$leaf" ] || [ "$leaf" = "@" ]; then fqdn="$zone"
      elif [[ "$leaf" == *".$zone" ]]; then fqdn="$leaf"
      else fqdn="$leaf.$zone"; fi

      # Service can be named in the plan under provider_options.service_name
      # or via RENDER_SERVICE_ID env. Prefer plan over env so a single .env can
      # serve multiple plans.
      svc_name="$(json_get provider_options.service_name < "$plan")"
      svc_id="$(json_get provider_options.service_id < "$plan")"
      [ -z "$svc_id" ] && svc_id="${RENDER_SERVICE_ID:-}"
      if [ -z "$svc_id" ] && [ -n "$svc_name" ]; then
        svc_id="$(rd_get_service_id "$svc_name")"
      fi
      [ -n "$svc_id" ] || { log ERROR "Render service id not found (set provider_options.service_id or RENDER_SERVICE_ID, or provider_options.service_name)"; return 1; }
      rd_attach_domain "$svc_id" "$fqdn"
      ;;
    delete_record)
      svc_id="$(json_get provider_options.service_id < "$plan")"
      [ -z "$svc_id" ] && svc_id="${RENDER_SERVICE_ID:-}"
      dom_id="$(json_get provider_options.domain_id < "$plan")"
      [ -n "$svc_id" ] && [ -n "$dom_id" ] || { log ERROR "delete_record on Render needs provider_options.service_id + provider_options.domain_id"; return 1; }
      rd_detach_domain "$svc_id" "$dom_id"
      ;;
    *)
      log ERROR "Render provider does not support operation: $op (Render attaches domains; DNS records belong to a DNS provider)"
      return 1
      ;;
  esac
}
