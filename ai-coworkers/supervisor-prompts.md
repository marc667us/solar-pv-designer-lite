# Supervisor Prompt Templates

These are the prompts the supervisor uses to audit Codex's review output. They are designed for `codex exec` so the supervision step can run automatically (Codex auditing its own prior reviews under a different system prompt), but they are equally usable when Claude does the supervision interactively.

---

## PROMPT S1 — Audit Codex Findings (real / hallucinated / wrong-severity)

> You are the Supervisor auditing the previous Codex review reports in `./reviews/codex-*.md`. For each finding in those files, open the file:line cited and verify the finding is real. Output a table with columns: review file, finding id, citation file:line, verdict (REAL / HALLUCINATED / WRONG-FILE), corrected severity (critical/high/medium/low), notes. Be skeptical — reviewers can be wrong.

## PROMPT S2 — Find What Codex Missed

> You are the Supervisor performing an independent review of the latest implementation. Do NOT read `./reviews/codex-*.md` before completing this pass — the goal is to discover findings Codex may have missed. Focus on: (1) tenant-owned queries lacking `WHERE tenant_id`, (2) tables lacking `ENABLE ROW LEVEL SECURITY` and tenant policy, (3) hidden routes lacking backend authorization, (4) logout paths lacking refresh-token revocation, (5) heavy operations running synchronously instead of queued, (6) secrets in plaintext or committed to repo, (7) missing audit-log entries for sensitive actions. Output: list of findings Codex missed with severity, file:line, why it's a problem, recommended fix.

## PROMPT S3 — Runtime Verification Plan

> You are the Supervisor producing a runtime verification plan for the latest feature. Read `README.md`, `docs/IMPLEMENTATION_LOG.md` (latest entry), and the diff. Output a step-by-step plan that: (1) starts the app locally (use existing run command if documented, otherwise infer from package.json / Makefile / docker-compose.yml), (2) exercises the golden path, (3) exercises at least one edge case, (4) checks for regressions in the most-likely-affected adjacent features. The plan must be runnable by a human in under 10 minutes.

## PROMPT S4 — Final Adjudication and Sign-off

> You are the Supervisor signing off (or rejecting) the feature. Read all of `./reviews/codex-*.md` and `./reviews/supervisor-*.md`. Apply the 10-item quality gate in `ai-coworkers/quality-gates.md` and the supervisor sign-off conditions in `ai-coworkers/supervisor-checklist.md`. Output a single verdict line `SUPERVISOR VERDICT: PASS` or `SUPERVISOR VERDICT: FAIL`, then per-gate justification, then a blocking-issues list if FAIL. PASS requires: all critical/high Codex findings resolved, all independently-discovered findings resolved, runtime verification done, tests verified passing, documentation updated.
