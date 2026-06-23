# Render-deployable Keycloak 26 image for the SolarPro IdP.
#
# What it does:
#   * Starts from the official Keycloak 26 image (Apache 2.0; FOSS-rule
#     compliant per ADR-0007).
#   * Bakes in the production realm definition (test users stripped by
#     build_realm_prod.py at image-build time -- see render.yaml
#     buildCommand).
#   * Runs `kc.sh build` so the production-optimised distribution is
#     ready at container start (skips the build step on every boot ->
#     ~3-5s startup instead of ~30s).
#
# Inputs (env vars supplied by render.yaml):
#   KC_DB                  -- "postgres"
#   KC_DB_URL              -- jdbc:postgresql://...?currentSchema=keycloak
#   KC_DB_USERNAME         -- keycloak_app (created by migration 006)
#   KC_DB_PASSWORD         -- supplied by Render secret env
#   KC_HOSTNAME            -- auth.aiappinvent.com (or onrender.com URL)
#   KC_BOOTSTRAP_ADMIN_USERNAME / _PASSWORD -- master-realm root admin
#   KEYCLOAK_ENABLED       -- "true" once the app side cuts over
#
# Output:
#   * /opt/keycloak/data/import/realm-prod.json with realm `solarpro`
#     ready for first-boot import.
#   * `start --optimized --import-realm` as the container's CMD.
#
# Why pin 26.0:
#   Plan §K technical decisions name Keycloak 26.0 pinned -- breaking
#   that pin without an ADR amendment is out of scope.

FROM quay.io/keycloak/keycloak:26.0 AS builder

# Build-time optimisations. The official image's `kc.sh build` step bakes
# the database vendor + features into the distribution, removing the
# per-boot rebuild cost. Setting these env vars here means `kc.sh build`
# picks them up; they do NOT carry over to the runtime stage (we set
# them again in render.yaml).
ENV KC_DB=postgres \
    KC_HEALTH_ENABLED=true \
    KC_METRICS_ENABLED=true \
    KC_FEATURES=token-exchange,admin-fine-grained-authz \
    KC_HTTP_RELATIVE_PATH=/

RUN /opt/keycloak/bin/kc.sh build

# ── Runtime stage ─────────────────────────────────────────────────────
FROM quay.io/keycloak/keycloak:26.0

# Copy the pre-built distribution from the builder stage so the
# container can `kc.sh start --optimized` (no rebuild on boot).
COPY --from=builder /opt/keycloak/ /opt/keycloak/

# Copy the production realm JSON into the import directory. Keycloak's
# --import-realm flag reads any *.json in this dir on first boot only
# (subsequent boots see the realm already exists in the DB and skip).
# Renaming to realm-prod.json keeps it distinct from the local-dev file.
COPY keycloak/render/realm-prod.json /opt/keycloak/data/import/realm-prod.json

# Bake the SolarPro login theme into the KC distribution. The realm's
# loginTheme="solarpro" property selects this theme; KC reads themes
# from /opt/keycloak/themes/<name>/ at request time so no rebuild is
# required to update CSS (just redeploy the image after editing).
# Theme inherits keycloak.v2 (PatternFly 5) and overrides login.css to
# match the SolarPro web app palette (templates/base.html).
COPY keycloak/render/themes/solarpro/ /opt/keycloak/themes/solarpro/

# Render terminates TLS at its load balancer and forwards plain HTTP to
# the container. KC_PROXY=edge tells Keycloak to trust the X-Forwarded-*
# headers so SSL-required checks pass; KC_HOSTNAME_STRICT_HTTPS=false
# is required because the container itself speaks HTTP.
ENV KC_PROXY=edge \
    KC_HOSTNAME_STRICT_HTTPS=false \
    KC_HTTP_ENABLED=true

# Render-friendly: bind KC's MAIN HTTP listener to Render's $PORT (10000
# by default). The management interface stays on a separate port (9000)
# but is NOT externally reachable through Render -- Render only routes
# external traffic to the $PORT binding. That means /realms/* + /admin
# work externally, and /health + /metrics stay internal (we don't need
# them externally because Render's healthCheckPath uses /realms/master).
#
# Why a shell-form CMD: Docker's JSON-form CMD doesn't expand $PORT, so
# we wrap with sh -c to do the substitution at container start. The
# trailing exec replaces the shell with the kc.sh process so signals
# (SIGTERM on redeploy) propagate correctly.
EXPOSE 10000

ENTRYPOINT []
CMD ["sh", "-c", "exec /opt/keycloak/bin/kc.sh start --optimized --import-realm --http-port=${PORT:-10000}"]
