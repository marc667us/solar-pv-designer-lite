# Secure Development Policy

Version: 1.0 · Effective: 2026-06-25 · Owner: Engineering Lead

## Purpose

Embed security into every step of the SolarPro development lifecycle.

## Scope

All code that ends up in production — `web_app.py`, `app/`, `new_*.py`,
migrations, GitHub Actions workflows, Dockerfile, deployment scripts.

## Policy

1. **Secure design** — every new feature MUST address: AuthN, AuthZ,
   tenant isolation, input validation, output filtering, audit logging,
   error handling, and rate limiting. The Project Execution Directive
   (`CLAUDE.md` §5) is the master checklist.

2. **Code review** — every PR goes through Codex CLI review (`scripts/
   codex-*-review.sh`). Critical and High findings must be fixed before
   merge. The Supervisor (`/code-review` + `/security-review`) is the
   second gate.

3. **Tests** — security-affecting code MUST land with tests. The
   `tests/security/` suite is the regression net (179 tests as of
   2026-06-25, must stay green).

4. **No secrets in source** — gitleaks scans every push (`security.yml`).
   Secrets live in Render env or GitHub Secrets only. `.env.example`
   files document expected variables without values.

5. **Dependency hygiene** — `pip-audit` runs in CI on every push +
   weekly. Outdated or vulnerable libraries are upgraded the same week.

6. **Static analysis** — semgrep + bandit on every push (`security.yml`).
   OWASP Top 10, flask, and secrets rulesets enabled.

7. **Branch model** — `master` = production. Feature work on a branch,
   PR'd into master. Force-push to master is forbidden.

8. **Pre-commit hooks** — recommended but not yet mandatory. When
   `.pre-commit-config.yaml` lands, ruff + black + gitleaks + bandit run
   locally before the developer pushes.

9. **CSRF protection** — every state-changing POST must call
   `csrf_protect()`. Tested by `tests/test_csrf.py`.

10. **SQL injection** — only parameterised queries (psycopg2 / sqlite3
    placeholder substitution). String concatenation into SQL is a
    review-blocker.

## Enforcement

CI fails on any High security finding. Codex review is required for
substantive changes. Direct master push without review is an incident.

## Review

Annual, or whenever the toolchain materially changes.
