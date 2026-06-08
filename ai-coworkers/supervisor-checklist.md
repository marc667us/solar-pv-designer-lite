# Supervisor Checklist — Reviewing Codex's Work

Use this when auditing each of Codex's review outputs.

## Important interpretation note (learned 2026-06-06)

An **empty `supervisor-missed-findings.md` is a GOOD sign** — it means Codex was thorough. Do NOT treat it as a supervisor failure. The supervisor's value in that case is its other two outputs: `supervisor-audit.md` (confirming Codex's findings are REAL, not hallucinated) and `supervisor-verification-plan.md` (the runtime test plan for `/verify`). Sign-off can still proceed.

## Per Codex finding

For every item in `reviews/codex-*.md`:

- [ ] **Real?** Open the cited file:line. Does the issue actually exist?
- [ ] **Severity correct?** Is critical truly critical (security/data loss/scale-blocker) vs medium (best-practice violation)? Down/up-grade as needed.
- [ ] **Fix recommendation sound?** Is Codex's recommended fix correct, or would it introduce a different problem?
- [ ] **Same finding repeated?** Codex sometimes lists the same issue under multiple reviews — dedupe.
- [ ] **Resolved?** If Claude already fixed it, mark resolved with the commit/file evidence.

## Missed findings (independent pass)

Run these independently — **do not read Codex's findings first**:

- [ ] `/code-review` — does the supervisor's review find anything Codex missed?
- [ ] `/security-review` — same, for security.
- [ ] Grep the diff for the high-risk patterns the directive cares about:
  - tenant-owned query without `WHERE tenant_id = ...`
  - new table without `ENABLE ROW LEVEL SECURITY` + tenant policy
  - new hidden route without backend authorization check
  - new logout path without refresh-token revocation
  - new background-eligible task running synchronously
  - secrets in plaintext / committed to repo

Findings the supervisor caught independently are added to `reviews/supervisor-adjudication.md` and **must** be fixed before sign-off (treated as critical).

## Runtime verification

- [ ] `/verify` — start the app, exercise the changed feature, observe behavior end-to-end. Cover the golden path + at least one edge case. Watch for regressions in adjacent features.
- [ ] Tests pass (don't trust Codex's claim that they pass — re-run).
- [ ] No console errors / no 500s / no silent failures.

## Sign-off conditions

The supervisor signs PASS only when:

- [ ] All critical and high Codex findings → confirmed real and fixed (or marked hallucinated with evidence).
- [ ] All independently-discovered findings → fixed.
- [ ] Runtime verification → PASS.
- [ ] Tests → PASS (verified, not claimed).
- [ ] Documentation → updated (impl log, roadmap, ADRs).
- [ ] 10-item quality gate → all green.
