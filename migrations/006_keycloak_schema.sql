-- Migration 006: Keycloak cohabitation schema on solarpro-postgres.
--
-- What it does:
--   * Creates the `keycloak` schema (where Keycloak 26 will create its
--     ~90 tables on first boot via Liquibase).
--   * Creates the `keycloak_app` role with login + a password supplied
--     by the caller via `psql -v kc_db_password='...'`.
--   * Grants keycloak_app full CRUD inside the keycloak schema only.
--   * Sets keycloak_app's default search_path so KC's unqualified
--     queries resolve to its own tables.
--   * REVOKEs the keycloak schema from PUBLIC so the solar app's role
--     (whoever DATABASE_URL connects as) cannot see KC tables. This is
--     the blast-radius isolation that lets us cohabit safely on the
--     same physical Postgres while still meeting the spirit of
--     plan §K (separate IdP database). End-state remains a fully
--     separate Postgres when paying users arrive.
--
-- Why cohabit at all:
--   Render free tier Postgres expires at 90 days; rotating a separate
--   free DB every 90 days carries a real risk of forgotten rotation =
--   total loss of the auth user table. solarpro-postgres is already
--   provisioned and persisted; cohabiting under a separate schema +
--   role is the cheapest configuration that meets the zero-cost rule
--   AND maintains schema-level isolation.
--
-- Idempotent: safe to re-run. CREATE SCHEMA IF NOT EXISTS handles
-- repeated apply; the role-creation DO block checks pg_roles first;
-- the password is ALTERed on every run so workflow re-runs effectively
-- rotate the password if a new value is supplied.
--
-- Apply:
--   psql "$DATABASE_URL" \
--     -v kc_db_password="$KC_DB_PASSWORD" \
--     -v ON_ERROR_STOP=1 \
--     -f migrations/006_keycloak_schema.sql
--
-- Verify:
--   psql "$DATABASE_URL" -A -t -c \
--     "SELECT nspname FROM pg_namespace WHERE nspname='keycloak'"
--   psql "$DATABASE_URL" -A -t -c \
--     "SELECT rolname FROM pg_roles WHERE rolname='keycloak_app'"

-- 1. Schema -------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS keycloak;

-- 2. Role ---------------------------------------------------------------
--    Created the first time; password rotated on every subsequent apply
--    so the workflow can be re-run with a fresh KC_DB_PASSWORD secret.
DO $do$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'keycloak_app') THEN
    EXECUTE format('CREATE ROLE keycloak_app WITH LOGIN PASSWORD %L', :'kc_db_password');
  ELSE
    EXECUTE format('ALTER ROLE keycloak_app WITH LOGIN PASSWORD %L', :'kc_db_password');
  END IF;
END
$do$;

-- 3. Grants -------------------------------------------------------------
--    keycloak_app is the only role allowed inside the keycloak schema.
--    USAGE lets it resolve schema; CREATE lets Liquibase build tables.
GRANT USAGE, CREATE ON SCHEMA keycloak TO keycloak_app;

--    Default privileges so every table/sequence Liquibase creates is
--    automatically owned and grant-flagged for keycloak_app without
--    needing follow-up grants.
ALTER DEFAULT PRIVILEGES FOR ROLE keycloak_app IN SCHEMA keycloak
  GRANT ALL ON TABLES TO keycloak_app;
ALTER DEFAULT PRIVILEGES FOR ROLE keycloak_app IN SCHEMA keycloak
  GRANT ALL ON SEQUENCES TO keycloak_app;

-- 4. Search path --------------------------------------------------------
--    KC's JDBC connections use SET SEARCH_PATH? No -- KC's Liquibase
--    expects unqualified table names. Setting role-level default
--    search_path means every login session as keycloak_app sees the
--    keycloak schema as the default.
ALTER ROLE keycloak_app SET search_path = keycloak, public;

-- 5. Blast-radius isolation --------------------------------------------
--    PUBLIC's implicit USAGE on every new schema is the default Postgres
--    behaviour that lets the solar app's role accidentally see KC
--    tables. REVOKEing PUBLIC and explicitly granting only keycloak_app
--    ensures a solar SQL injection cannot SELECT * FROM keycloak.users
--    (or any KC table). Keycloak itself uses bcrypt for password hashes
--    so even a hypothetical breach still requires cracking effort, but
--    this control prevents the read in the first place.
REVOKE ALL ON SCHEMA keycloak FROM PUBLIC;

-- 6. Sanity log ---------------------------------------------------------
--    Surfaces the schema + role in the psql output so the workflow log
--    confirms what landed.
SELECT 'keycloak schema present: ' || EXISTS(
  SELECT 1 FROM pg_namespace WHERE nspname='keycloak'
)::text AS step_1_schema;

SELECT 'keycloak_app role present: ' || EXISTS(
  SELECT 1 FROM pg_roles WHERE rolname='keycloak_app'
)::text AS step_2_role;
