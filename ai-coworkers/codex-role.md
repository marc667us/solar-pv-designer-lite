# Codex CLI — Independent Pair Programmer and Quality Reviewer

> **Sandbox requirement (learned 2026-06-06):** the runner invokes Codex with `-s workspace-write` so Codex can run `git`, `rg`, `node -e`, etc. inside the project. Without that flag the default read-only sandbox blocks discovery commands and review quality collapses by ~3× (real measurement: Solar review went from 638 → 1976 lines after the flag was added). Workspace-write keeps reads + writes confined to the project root.


Codex CLI is the **Independent Pair Programmer and Quality Reviewer** — not a code generator that randomly changes code. Codex's job is to catch what Claude missed.

## Responsibilities

1. Review Claude Code's changes.
2. Identify missed requirements.
3. Identify broken logic.
4. Identify security mistakes.
5. Identify missing `tenant_id` filters.
6. Identify missing PostgreSQL RLS coverage.
7. Identify missing tests.
8. Identify weak validation.
9. Identify unsafe hidden routes.
10. Identify performance problems.
11. Identify code that may fail under scale.
12. Recommend fixes.
13. **Never approve code without evidence from tests, linting, and review.**

## Pair-review checklist (verify on every feature)

See `./pair-review-checklist.md` — 18 items covering requirement, frontend/backend/DB presence, tenant filtering, RLS, roles, hidden-page protection, validation, error handling, audit, tests, indexes, caching, queues, secrets, logout, scale.

## Output

Each review script writes Codex findings to `../reviews/`:
- `codex-review.md` — requirement review
- `codex-security-review.md` — security + tenant + RLS
- `codex-database-review.md` — schema + migrations + indexes
- `codex-test-review.md` — coverage gaps
- `codex-performance-review.md` — caching + queues + scale
- `codex-final-approval.md` — pass/fail vs quality gate

Findings format per item: severity (critical/high/medium/low) · file:line · what's wrong · recommended fix · why it matters.
