# Supervisor — Reviewer of the Reviewer

The Supervisor is the **third coworker** in the workflow. Claude implements, Codex reviews, **Supervisor audits Codex's review.**

The Supervisor exists because reviewers can also be wrong: Codex may miss findings, raise false positives, or hallucinate issues. Without supervision, a clean Codex report could falsely greenlight broken code.

## Who plays the Supervisor

In day-to-day work the Supervisor is **Claude Code**, but operating in a different mode — not as the implementer, as an auditor of Codex's output. Claude uses the built-in Claude Code review skills to do this:

- `/code-review` — review the current diff for correctness bugs and reuse/simplification cleanups
- `/security-review` — complete a security review of the pending changes
- `/verify` — verify that a code change actually does what it's supposed to do (run the app, observe behavior)
- `/review` — review a pull request (when work is in a PR)

These skills run independently from Codex and produce findings Claude can compare to Codex's findings.

## Responsibilities

1. **Re-read Codex's reviews** in `./reviews/codex-*.md` before accepting them.
2. **Spot-check Codex's findings** by reading the files Codex flagged. Are the findings real? Are they in the right file/line?
3. **Identify missed findings** by independently running the project's built-in review skills (`/code-review`, `/security-review`) and comparing.
4. **Verify behavior** with `/verify` — does the feature actually work end-to-end in a running instance? Codex only reads code; the supervisor confirms runtime behavior.
5. **Adjudicate severity** — Codex may overrate or underrate; the supervisor sets the final severity per finding.
6. **Flag hallucinations** — if Codex cites a file:line that doesn't exist, mark it as hallucinated and discard.
7. **Sign off the quality gate** — only after supervision passes does the 10-item quality gate close.

## Hard rules

- **No quality gate without supervision.** A green Codex report is **not** sufficient to mark a feature complete. The supervisor must independently sign off.
- **No supervisor sign-off without runtime verification.** `/verify` (or an equivalent run-the-app step) must succeed. Reading code alone is not enough.
- **No supervisor sign-off if Codex's findings are partially fixed.** All critical and high-severity findings must be resolved; medium findings either fixed or explicitly deferred with a recorded reason.

## Output

The supervisor writes a final adjudication file:

```
reviews/supervisor-adjudication.md
```

Containing: per-Codex-finding verdict (confirmed / hallucinated / wrong-severity / resolved), missed findings the supervisor caught independently, runtime verification result, final PASS/FAIL recommendation to the quality gate.
