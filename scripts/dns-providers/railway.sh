#!/usr/bin/env bash
# Railway provider module for the DNS-edit skill.
#
# Railway exposes a GraphQL API for managing custom domains on services. Like
# Render, "custom domain on Railway" is one half of a complete plan — the other
# half is a CNAME at the DNS provider pointing to Railway's edge target.
#
# What this does:
#   - rw_list_services <project-id>           -> services in a project
#   - rw_list_domains <service-id> <env-id>   -> attached custom domains
#   - rw_attach_domain <svc> <env> <fqdn>     -> attach domain to service env
#   - rw_detach_domain <domain-id>            -> remove
#   - rw_apply <plan-json-path>
#
# Inputs:   RAILWAY_API_TOKEN env var (account-level token; project tokens are
#           env-scoped — see project_solar_pv memory for why account-level is
#           preferred for cross-env work)
#           Plan must carry provider_options.{project_id, service_id, environment_id}
# Outputs:  JSON to stdout; log lines to stderr

set -e

if ! type curl_json >/dev/null 2>&1; then
  . "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
fi

RW_API="https://backboard.railway.app/graphql/v2"

rw_auth_header() {
  require_env RAILWAY_API_TOKEN
  printf 'Authorization: Bearer %s' "$RAILWAY_API_TOKEN"
}

# _rw_gql QUERY VARS_JSON -- POST a GraphQL query, return data on stdout.
# Surfaces errors[] to stderr and returns non-zero on GraphQL errors.
_rw_gql() {
  local query="$1" vars="$2"
  printf '%s' "$query" | python - "$vars" <<'PY'
import json, sys
q = sys.stdin.read()
v = json.loads(sys.argv[1]) if sys.argv[1] else {}
print(json.dumps({'query': q, 'variables': v}))
PY
  return 0
} | curl_json POST "$RW_API" "$(rw_auth_header)" \
  | python - <<'PY'
import json, sys
data = json.load(sys.stdin)
if data.get('errors'):
    for e in data['errors']:
        print(f"Railway GQL error: {e.get('message')}", file=sys.stderr)
    sys.exit(1)
print(json.dumps(data.get('data', {}), indent=2))
PY

# Note: the function-body-with-pipe-after-{} pattern above relies on bash
# treating the whole pipeline as the function body. If your shell objects, the
# equivalent expansion is to wrap the body in a subshell ( ... ) and pipe.

# rw_list_services <project-id> -- ids+names of services in a project.
rw_list_services() {
  local pid="$1"
  _rw_gql '
    query($id: String!) {
      project(id: $id) {
        services { edges { node { id name } } }
      }
    }
  ' "{\"id\":\"$pid\"}"
}

# rw_list_domains <service-id> <env-id> -- custom domains for a service env.
rw_list_domains() {
  local svc="$1" env="$2"
  _rw_gql '
    query($svc: String!, $env: String!) {
      customDomains(serviceId: $svc, environmentId: $env) {
        customDomains { id domain status }
      }
    }
  ' "{\"svc\":\"$svc\",\"env\":\"$env\"}"
}

# rw_attach_domain <svc> <env> <fqdn> -- attach a custom domain.
rw_attach_domain() {
  local svc="$1" env="$2" fqdn="$3"
  _rw_gql '
    mutation($input: CustomDomainCreateInput!) {
      customDomainCreate(input: $input) {
        id domain status dnsRecords { hostlabel value }
      }
    }
  ' "{\"input\":{\"serviceId\":\"$svc\",\"environmentId\":\"$env\",\"domain\":\"$fqdn\"}}"
}

# rw_detach_domain <domain-id>.
rw_detach_domain() {
  local dom="$1"
  _rw_gql '
    mutation($id: String!) { customDomainDelete(id: $id) }
  ' "{\"id\":\"$dom\"}"
}

# rw_apply <plan-json-path> -- dispatcher.
rw_apply() {
  local plan="$1"
  local op zone fqdn leaf pid svc env dom

  op="$(json_get operation < "$plan")"
  zone="$(json_get zone < "$plan")"
  leaf="$(json_get record.name < "$plan")"

  if [ -z "$leaf" ] || [ "$leaf" = "@" ]; then fqdn="$zone"
  elif [[ "$leaf" == *".$zone" ]]; then fqdn="$leaf"
  else fqdn="$leaf.$zone"; fi

  pid="$(json_get provider_options.project_id < "$plan")"
  svc="$(json_get provider_options.service_id < "$plan")"
  env="$(json_get provider_options.environment_id < "$plan")"
  dom="$(json_get provider_options.domain_id < "$plan")"

  case "$op" in
    add_domain|add_subdomain)
      [ -n "$svc" ] && [ -n "$env" ] || { log ERROR "Railway attach needs provider_options.service_id and provider_options.environment_id"; return 1; }
      rw_attach_domain "$svc" "$env" "$fqdn"
      ;;
    delete_record)
      [ -n "$dom" ] || { log ERROR "Railway delete needs provider_options.domain_id"; return 1; }
      rw_detach_domain "$dom"
      ;;
    *)
      log ERROR "Railway provider does not support operation: $op (Railway attaches domains; DNS records belong to a DNS provider)"
      return 1
      ;;
  esac
}
