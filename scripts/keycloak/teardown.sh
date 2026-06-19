#!/usr/bin/env bash
# Tear down the local Keycloak stack defined in docker-compose.keycloak.yml.
# By default leaves the Postgres volume in place so the realm survives
# the next bootstrap. Pass --wipe to also delete the volume (fresh
# realm import on next bootstrap).
#
# Usage:
#   bash scripts/keycloak/teardown.sh
#   bash scripts/keycloak/teardown.sh --wipe

set -euo pipefail

cd "$(dirname "$0")/../.."

COMPOSE_FILE="docker-compose.keycloak.yml"

WIPE=0
if [ "${1:-}" = "--wipe" ]; then
  WIPE=1
fi

echo "[1/2] stopping containers"
docker compose -f "$COMPOSE_FILE" down

if [ "$WIPE" -eq 1 ]; then
  echo "[2/2] removing Postgres volume (realm + users will be reset on next bootstrap)"
  docker volume rm solarpro-keycloak-db-data || true
else
  echo "[2/2] Postgres volume preserved -- realm state survives next bootstrap"
  echo "      (run 'bash scripts/keycloak/teardown.sh --wipe' to reset)"
fi
