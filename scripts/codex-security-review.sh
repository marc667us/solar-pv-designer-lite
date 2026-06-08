#!/usr/bin/env bash
# Security review — auth, authorization, tenant isolation, RLS, hidden routes, file access, tokens.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ./scripts/_codex-runner.sh

CONTEXT="$(gather_context)"

PROMPT="You are Codex acting as Independent Security Reviewer. Review the latest code for authentication, authorization, tenant isolation, PostgreSQL RLS coverage, hidden-route protection, file access protection, token handling, and unsafe data exposure. Pay special attention to: (1) every query on a tenant-owned table must filter by tenant_id; (2) every tenant-owned table must have an RLS policy ENABLE ROW LEVEL SECURITY + tenant policy; (3) hidden admin routes must be backend-protected even if a user guesses the URL; (4) logout must revoke refresh tokens, not just clear browser storage. Return findings with: severity, file:line, attack scenario, recommended fix.

${CONTEXT}"

codex_run "codex-security-review" "$PROMPT"
