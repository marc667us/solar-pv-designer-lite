# Codex Review Prompt Templates

These are the prompts the `scripts/codex-*.sh` helpers feed to Codex CLI.

---

## PROMPT 1 — Requirement Review

> Codex, review the latest implementation against the stated requirement. Identify anything Claude Code missed, misunderstood, or only partially implemented. Return a checklist of defects and recommended fixes. For each defect: severity (critical/high/medium/low), file:line, what's wrong, recommended fix, why it matters.

## PROMPT 2 — Security Review

> Codex, review the latest code for authentication, authorization, tenant isolation, RLS, hidden-route protection, file access protection, token handling, and unsafe data exposure. Identify risks and fixes. For each finding: severity, file:line, attack scenario, recommended fix.

## PROMPT 3 — Database Review

> Codex, review the database schema, migrations, indexes, tenant_id usage, foreign keys, constraints, and RLS policies. Identify missing indexes, weak constraints, and tenant isolation risks. For each finding: severity, table/migration, issue, recommended SQL fix.

## PROMPT 4 — Test Review

> Codex, review the test coverage. Identify missing unit tests, integration tests, security tests, RLS tests, logout tests, load tests, and UI tests. For each gap: which protected resource lacks the minimum 5 tests (authorized/unauthorized/wrong-tenant/logged-out/expired-token).

## PROMPT 5 — Performance Review

> Codex, review the implementation for scaling. Check caching, queueing, database pooling, indexes, API response design, and long-running tasks. Assume 1000 concurrent users, multi-tenant load. For each finding: severity, location, scale risk, recommended fix.

## PROMPT 6 — Final Approval

> Codex, perform final review against the 18-item pair-review-checklist and 10-item quality-gates. Do not approve unless the implementation meets requirements, tests pass, security controls are present, and no critical issues remain. Output: PASS or FAIL with justification per gate.
