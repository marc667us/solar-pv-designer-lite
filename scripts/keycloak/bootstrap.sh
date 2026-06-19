#!/usr/bin/env bash
# Bring up the local Keycloak stack defined in docker-compose.keycloak.yml,
# wait for it to come ready, then verify the solarpro realm imported
# cleanly by fetching a JWT for one of the test users.
#
# Usage:
#   bash scripts/keycloak/bootstrap.sh
#
# Requires:
#   - docker + docker-compose plugin
#   - curl
#   - jq (optional -- nicer JWT inspection)

set -euo pipefail

cd "$(dirname "$0")/../.."

COMPOSE_FILE="docker-compose.keycloak.yml"
REALM="solarpro"
TEST_USER="engineer_test"
TEST_PASSWORD="Test1234!Test"
TEST_CLIENT="solarpro-web"
KC_BASE="http://localhost:8080"
TOKEN_URL="${KC_BASE}/realms/${REALM}/protocol/openid-connect/token"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found. Install Docker Desktop (Windows) or docker.io (Linux) first."
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose plugin not found. Install docker-compose-v2 first."
  exit 1
fi

echo "[1/4] docker compose up -d (Keycloak + Postgres)"
docker compose -f "$COMPOSE_FILE" up -d

echo "[2/4] waiting for Keycloak readiness (up to ~3 minutes for first boot)"
deadline=$(( $(date +%s) + 240 ))
while ! curl -fSs "${KC_BASE}/realms/${REALM}/.well-known/openid-configuration" >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "  ! Keycloak did not become ready within 240s. Tail the logs:"
    echo "    docker compose -f $COMPOSE_FILE logs --tail=100 keycloak"
    exit 1
  fi
  printf "."
  sleep 5
done
echo
echo "  ready: ${KC_BASE}/realms/${REALM}"

echo "[3/4] fetching JWT for ${TEST_USER} via password grant"
RESP=$(curl -fSs -X POST "$TOKEN_URL" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=${TEST_CLIENT}" \
  -d "grant_type=password" \
  -d "username=${TEST_USER}" \
  -d "password=${TEST_PASSWORD}" 2>&1 || true)

if echo "$RESP" | grep -q "access_token"; then
  if command -v jq >/dev/null 2>&1; then
    echo "  access token (claims):"
    echo "$RESP" | jq -r '.access_token' | awk -F. '{print $2}' | base64 -d 2>/dev/null | jq '.' || true
  else
    echo "  got an access_token (install jq to decode the claims)"
  fi
else
  echo "  ! token fetch failed:"
  echo "$RESP"
  echo
  echo "  Common causes:"
  echo "  - solarpro-web isn't configured to allow direct-access grants in"
  echo "    realm-export.json (we INTENTIONALLY disable it for security)."
  echo "    The bootstrap test below uses the admin-cli flow instead."
fi

# Confirm the realm imported even if direct-access grant is off.
ADMIN_TOKEN=$(curl -fSs -X POST \
  "${KC_BASE}/realms/master/protocol/openid-connect/token" \
  -d "client_id=admin-cli" \
  -d "grant_type=password" \
  -d "username=${KC_BOOTSTRAP_ADMIN_USERNAME:-admin}" \
  -d "password=${KC_BOOTSTRAP_ADMIN_PASSWORD:-StrongAdminPassword!Replace}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

ROLES_COUNT=$(curl -fSs -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  "${KC_BASE}/admin/realms/${REALM}/roles" \
  | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')

CLIENTS_COUNT=$(curl -fSs -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  "${KC_BASE}/admin/realms/${REALM}/clients" \
  | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')

USERS_COUNT=$(curl -fSs -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  "${KC_BASE}/admin/realms/${REALM}/users?max=100" \
  | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')

echo "[4/4] realm health"
echo "  realm:   ${REALM}"
echo "  roles:   ${ROLES_COUNT} (expected: 17 SolarPro + a handful of Keycloak defaults)"
echo "  clients: ${CLIENTS_COUNT} (expected: 10 SolarPro + a handful of Keycloak defaults)"
echo "  users:   ${USERS_COUNT} (expected: 13 SolarPro test fixtures)"
echo
echo "  Admin console:  ${KC_BASE}/admin/"
echo "  Master realm:   admin / \${KC_BOOTSTRAP_ADMIN_PASSWORD}"
echo "  SolarPro realm: select 'solarpro' in the realm dropdown"
echo
echo "  Next step: Phase 2 -- write app/security/keycloak_middleware.py"
