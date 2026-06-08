#!/usr/bin/env bash
# Apply all PostgreSQL migrations to the database pointed at by $DATABASE_URL.
#
# Usage:
#   export DATABASE_URL='postgres://USER:PASS@HOST:PORT/DBNAME?sslmode=require'
#   ./scripts/apply_postgres_migrations.sh
#
# Or one-shot:
#   DATABASE_URL='postgres://...' ./scripts/apply_postgres_migrations.sh
#
# Applies (in order, each tracked in public.schema_migrations so re-runs skip applied ones):
#   001_postgresql_schema.sql  — initial schema, sequences, triggers
#   002_rls_policies.sql       — RLS helper functions + per-table policies
#   003_rls_hardening.sql      — FORCE RLS + plug PII/audit/uploaded_files loopholes (2026-06-07 Q-gate)
#   004_schema_hardening.sql   — tenant-aware composite FKs, NOT NULL, CHECKs, composite indexes (2026-06-07 Q-gate)
#
# Migration ledger (added 2026-06-08, Phase 2.5 of SolarPro_Schedule_2026-06-08.md):
#   On first run, creates public.schema_migrations(name TEXT PK, applied_at TIMESTAMPTZ).
#   Each migration is wrapped in a single transaction with the ledger insert,
#   so a failure rolls BOTH back. Re-runs check the ledger and skip applied
#   migrations, even if their CREATE/ALTER statements are not idempotent.
#
# After all migrations apply, verifies tenant-table RLS coverage with hard
# assertions (exits non-zero if any required table is missing forced RLS or
# has zero policies).
#
# To force-skip a migration (e.g. for development) pass `--skip 003 004`.
# To restart from scratch (DROPs ledger), pass `--reset-ledger` — DANGEROUS.

set -euo pipefail

# Resolve absolute script path BEFORE any `cd` so --help still works (Phase 2.5 finding).
SCRIPT_ABS_PATH="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MIGRATIONS_DIR="$REPO_ROOT/migrations"

if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERROR: DATABASE_URL is not set." >&2
    echo "  export DATABASE_URL='postgres://user:pass@host:port/db?sslmode=require'" >&2
    exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
    echo "ERROR: psql not found on PATH." >&2
    echo "  Install PostgreSQL client: apt install postgresql-client / brew install postgresql / choco install postgresql" >&2
    exit 1
fi

SKIP=()
RESET_LEDGER=0
while [ $# -gt 0 ]; do
    case "$1" in
        --skip)
            shift
            while [ $# -gt 0 ] && ! [[ "$1" =~ ^-- ]]; do
                SKIP+=("$1")
                shift
            done
            ;;
        --reset-ledger)
            RESET_LEDGER=1
            shift
            ;;
        --help|-h)
            sed -n '2,30p' "$SCRIPT_ABS_PATH"
            exit 0
            ;;
        *)
            echo "Unknown arg: $1" >&2
            exit 2
            ;;
    esac
done

is_skipped() {
    local n="$1"
    for s in "${SKIP[@]:-}"; do
        [ "$s" = "$n" ] && return 0
    done
    return 1
}

# --- Ledger setup ------------------------------------------------------------

if [ "$RESET_LEDGER" = "1" ]; then
    echo "── --reset-ledger: DROPping public.schema_migrations ──"
    psql "$DATABASE_URL" -v ON_ERROR_STOP=on -c "DROP TABLE IF EXISTS public.schema_migrations;"
fi

psql "$DATABASE_URL" -v ON_ERROR_STOP=on -c "
    CREATE TABLE IF NOT EXISTS public.schema_migrations (
        name        TEXT PRIMARY KEY,
        applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );"

is_applied() {
    # Returns 0 (true) if migration name is already in the ledger.
    local name="$1"
    local count
    count=$(psql "$DATABASE_URL" -tA -c "SELECT count(*) FROM public.schema_migrations WHERE name = '$name';")
    [ "$count" -gt 0 ]
}

apply() {
    local n="$1"
    local f="$2"
    local fpath="$MIGRATIONS_DIR/$f"

    if is_skipped "$n"; then
        echo "── ${n} ${f} SKIPPED via --skip ──"
        return 0
    fi
    if is_applied "$f"; then
        echo "── ${n} ${f} already applied (ledger) ──"
        return 0
    fi
    if [ ! -f "$fpath" ]; then
        echo "ERROR: migration file ${fpath} not found." >&2
        exit 3
    fi
    echo "── ${n} ${f} ──"
    # Wrap the migration AND the ledger insert in one transaction so a failure
    # rolls both back; otherwise a partially-applied migration would not be
    # in the ledger and the next run would re-fail on non-idempotent DDL.
    psql "$DATABASE_URL" --single-transaction --set ON_ERROR_STOP=on <<SQL
\\set ON_ERROR_STOP on
BEGIN;
\\i $fpath
INSERT INTO public.schema_migrations (name) VALUES ('$f');
COMMIT;
SQL
}

apply "001" "001_postgresql_schema.sql"
apply "002" "002_rls_policies.sql"
apply "003" "003_rls_hardening.sql"
apply "004" "004_schema_hardening.sql"

# --- Verification (hard assertions) ------------------------------------------

echo
echo "=== verify RLS coverage (asserts; exits non-zero on failure) ==="

# DO-block: error out if any required tenant table is missing forced RLS or has
# zero policies. Returns one row of details per failing table, then raises.
psql "$DATABASE_URL" -v ON_ERROR_STOP=on <<'SQL'
DO $$
DECLARE
    bad RECORD;
    failures INT := 0;
BEGIN
    FOR bad IN
        SELECT t.tablename, c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced,
               (SELECT count(*) FROM pg_policies p WHERE p.tablename = t.tablename) AS policy_count
        FROM pg_tables t
        JOIN pg_class c ON c.relname = t.tablename AND c.relkind = 'r'
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
        WHERE t.tablename IN (
            'organizations','users','user_sessions','projects','leads',
            'assessment_requests','crm_opportunities','proposals','installers',
            'procurement_packages','bidder_submissions','subscriptions',
            'payments','tickets','ticket_replies','uploaded_files',
            'audit_log','email_logs'
        )
        AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity OR
             (SELECT count(*) FROM pg_policies p WHERE p.tablename = t.tablename) = 0)
    LOOP
        failures := failures + 1;
        RAISE NOTICE 'FAILED %: rls_enabled=% rls_forced=% policy_count=%',
            bad.tablename, bad.rls_enabled, bad.rls_forced, bad.policy_count;
    END LOOP;
    IF failures > 0 THEN
        RAISE EXCEPTION 'RLS verification failed: % tables missing forced RLS or policies', failures;
    END IF;
    RAISE NOTICE 'OK: every required tenant table has forced RLS and >=1 policy.';
END $$;
SQL

# Human-readable summary for the operator.
psql "$DATABASE_URL" -c "
    SELECT tablename,
           rowsecurity AS rls_enabled,
           CASE WHEN forcerowsecurity THEN 'FORCED' ELSE 'NOT forced' END AS rls_force,
           (SELECT count(*) FROM pg_policies p WHERE p.tablename = c.relname) AS policy_count
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_tables t ON t.tablename = c.relname
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND c.relname IN ('organizations','users','user_sessions','projects','leads',
                        'assessment_requests','crm_opportunities','proposals','installers',
                        'procurement_packages','bidder_submissions','subscriptions',
                        'payments','tickets','ticket_replies','uploaded_files',
                        'audit_log','email_logs')
    ORDER BY c.relname;
"

echo
echo "✓ migrations applied + RLS coverage verified."
echo "  Next: configure the runtime to use DATABASE_URL"
echo "  (web_app.py currently reads DB_PATH for SQLite — see Q-gate 1.1)."
