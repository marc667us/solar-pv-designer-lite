#!/usr/bin/env bash
# Database review — schema, migrations, indexes, tenant_id, foreign keys, constraints, RLS policies.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ./scripts/_codex-runner.sh

CONTEXT="$(gather_context)"

PROMPT="You are Codex acting as Independent Database Reviewer. Review the database schema, recent migrations, indexes, tenant_id usage, foreign keys, constraints, and RLS policies. Identify: missing indexes (especially tenant_id and tenant_id+status), weak constraints (missing NOT NULL / CHECK / UNIQUE), tenant isolation risks (missing tenant_id column, missing tenant_id filter), missing RLS policies, missing audit columns (created_by_user_id, created_at, updated_at). Return findings with: severity, table or migration file, issue, recommended SQL fix.

${CONTEXT}"

codex_run "codex-database-review" "$PROMPT"
