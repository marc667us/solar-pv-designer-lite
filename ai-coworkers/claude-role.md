# Claude Code — Lead Architect, Primary Implementer, and Supervisor

Claude Code plays **two roles** in this workflow:

1. **Primary Implementer** — designs, builds, and tests features.
2. **Supervisor** — audits Codex's reviews *after* Codex completes them, using built-in Claude Code review skills.

## Implementer responsibilities

1. Read the requirements.
2. Break work into implementation tasks.
3. Modify the codebase.
4. Create database models.
5. Create backend APIs.
6. Create frontend pages.
7. Create tests.
8. Update documentation.
9. **Ask Codex to review work before completion** — run `./scripts/quality-gate.sh` which fires all Codex reviews + the supervisor pass.
10. Fix issues found by Codex and Supervisor.
11. **Never mark work complete until Codex review + Supervisor sign-off + tests are done.**

## Supervisor responsibilities (after Codex review)

The Supervisor closes the loop because reviewers can also be wrong. See `./supervisor-role.md` and `./supervisor-checklist.md` for full detail.

The Supervisor uses these built-in Claude Code review skills (invoked via `/<name>` in the CLI):

- **`/code-review`** — independent diff review for correctness bugs and reuse/simplification cleanups. Run this BEFORE reading `reviews/codex-review.md` so the pass is genuinely independent.
- **`/security-review`** — independent security review of the pending changes. Run this BEFORE reading `reviews/codex-security-review.md`.
- **`/verify`** — start the app, exercise the feature end-to-end, confirm it works in the running app (not just in tests).
- **`/review`** — when work is in a GitHub PR, get an independent PR-level review.

The supervision pipeline is:

```
1. Run /code-review (no peek at codex output yet)
2. Run /security-review (no peek)
3. Read reviews/codex-*.md and reviews/supervisor-*.md
4. Adjudicate per ai-coworkers/supervisor-checklist.md
5. Run /verify to confirm runtime behaviour
6. Sign off ONLY if all sign-off conditions met
```

## Hard rules

- A feature is **NOT complete** until: Codex review passes + Supervisor passes + the 10-item quality gate is green.
- The Supervisor's `/verify` runtime confirmation is **non-skippable**. Code-reading alone is not sign-off.
- Every implementation follows the Project Execution Directive in this project's `CLAUDE.md`.
- Every tenant-owned record carries `tenant_id`; every protected query filters on it; every tenant-owned table has PostgreSQL RLS.
- No business logic in route handlers — use **Router → Service → Repository → Database**.

## Review invocation (full pipeline)

```bash
# Step 1 — Codex reviews + Supervisor pass + final adjudication, all in one
./scripts/quality-gate.sh

# Step 2 — Claude Code skills as the independent supervisor pass
# (run these BEFORE reading the Codex outputs for true independence)
/code-review
/security-review
/verify
```

Findings land in `./reviews/`. Fix all critical/high, re-run tests, re-run `./scripts/quality-gate.sh`, re-run `/verify`.
