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
# Applies (in order):
#   001_postgresql_schema.sql  — initial schema, sequences, triggers
#   002_rls_policies.sql       — RLS helper functions + per-table policies
#   003_rls_hardening.sql      — FORCE RLS + plug PII/audit/uploaded_files loopholes (2026-06-07 Q-gate)
#   004_schema_hardening.sql   — tenant-aware composite FKs, NOT NULL, CHECKs, composite indexes (2026-06-07 Q-gate)
#
# Idempotent (uses CREATE … IF NOT EXISTS / ADD COLUMN IF NOT EXISTS where possible).
# The composite-FK ALTERs in 004 are NOT idempotent — re-running on an existing
# DB requires schema cleanup first; check `pg_constraint` for the new FK names.
#
# To skip a step pass `--skip 003 004` or similar.

set -euo pipefail

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

cd "$(dirname "$0")/../migrations"

SKIP=()
while [ $# -gt 0 ]; do
    case "$1" in
        --skip)
            shift
            while [ $# -gt 0 ] && ! [[ "$1" =~ ^-- ]]; do
                SKIP+=("$1")
                shift
            done
            ;;
        --help|-h)
            sed -n '2,18p' "$0"
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

apply() {
    local n="$1"
    local f="$2"
    if is_skipped "$n"; then
        echo "── ${n} ${f} SKIPPED ──"
        return 0
    fi
    if [ ! -f "$f" ]; then
        echo "ERROR: migration file ${f} not found in $(pwd)" >&2
        exit 3
    fi
    echo "── ${n} ${f} ──"
    psql "$DATABASE_URL" --single-transaction --set ON_ERROR_STOP=on -f "$f"
}

apply "001" "001_postgresql_schema.sql"
apply "002" "002_rls_policies.sql"
apply "003" "003_rls_hardening.sql"
apply "004" "004_schema_hardening.sql"

echo
echo "=== verify RLS coverage ==="
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
echo "✓ migrations applied. Next: configure the runtime to use DATABASE_URL"
echo "  (web_app.py currently reads DB_PATH for SQLite — see Q-gate 1.1)."
