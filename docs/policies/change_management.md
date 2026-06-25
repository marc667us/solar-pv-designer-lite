# Change Management Policy

Version: 1.0 · Effective: 2026-06-25 · Owner: Engineering Lead

## Purpose

Ensure changes to production systems are intentional, reviewed, and
reversible.

## Scope

Code changes that reach `master`; database schema migrations; Render env
var updates; Keycloak realm modifications; GitHub Actions workflow
edits; DNS / Cloudflare changes.

## Policy

1. **Source of truth** — production state is defined by `master` branch
   + Render env + Keycloak realm. Drift from `master` is a defect.

2. **Code change flow** — feature branch → PR → Codex review →
   Supervisor review → merge to `master` → Force Render Deploy →
   live smoke. Documented in `docs/architecture/cicd.md`.

3. **Migration flow** — every schema change ships as a numbered SQL
   file under `migrations/` AND a gated GitHub Actions workflow that
   defaults to dry-run. Apply token is migration-specific (e.g.
   `BOQ_RLS_APPLY` for migration 007).

4. **Env var changes** — only via the `Force Render Deploy` workflow's
   GET-merge-PUT pattern (with `?limit=100`). Direct Render console
   edits are audit-logged but discouraged.

5. **Keycloak realm changes** — major changes (new client, role,
   authentication flow) are documented in a proposal first (e.g.
   `docs/SECURITY_MFA_PROPOSAL_M12.md`) then applied via either the
   admin console (with screenshots in the proposal) or a workflow.

6. **Rollback path** — every change must have a documented rollback.
   Migrations include `pg_restore` from the most recent dump. Realm
   changes have an "if X breaks, revert to previous browser flow"
   playbook.

7. **No untracked changes in production** — every change has a commit,
   a PR, or a workflow run as its audit trail.

8. **Emergency changes** — owner can override the review gate for a
   P1/P2 hotfix, but the post-incident review MUST trace the override.

## Enforcement

- Direct push to `master` without review is an incident.
- Workflows that PUT env vars MUST honor the `?limit=100` rule.

## Review

Annual + after every cross-cutting infra change.
