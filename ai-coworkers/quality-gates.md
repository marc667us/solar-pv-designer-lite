# Quality Gates

No feature is complete unless **ALL 10 gates pass** — and the **Supervisor signs off** independently.

## The 10 gates

1. Claude Code implementation is done.
2. Codex review is completed.
3. All critical Codex findings are fixed (or marked HALLUCINATED with evidence by the Supervisor).
4. Tests pass.
5. Security checks pass (auth, authorization, tenant isolation, RLS, hidden-route protection).
6. Database migrations are reviewed.
7. Tenant isolation is verified (every owned query filters `tenant_id`).
8. RLS is verified (every owned table has a tenant policy).
9. Logs and audit events are present.
10. Documentation is updated (`README.md`, `docs/IMPLEMENTATION_LOG.md`, roadmap if scope changed).

## Plus: Supervisor sign-off (non-skippable)

The Supervisor (Claude Code acting as auditor) must independently:

- Confirm Codex's findings are REAL via `reviews/supervisor-audit.md`.
- Find anything Codex missed via `reviews/supervisor-missed-findings.md` and ensure those are fixed.
- Run `/verify` (Claude Code skill) to confirm the feature works in the running app — code-reading alone is **not** sufficient.
- Run `/code-review` and `/security-review` skills as independent passes (BEFORE reading Codex's output) and reconcile findings.
- Produce `reviews/codex-final-approval.md` containing a `SUPERVISOR VERDICT: PASS` line.

## Pipeline

```
./scripts/quality-gate.sh   # runs all Codex reviews + supervise-codex.sh + final adjudication
/code-review                # independent pass (do BEFORE reading reviews/)
/security-review            # independent pass (do BEFORE reading reviews/)
/verify                     # runtime verification (mandatory)
```

A failing gate, a missing supervisor sign-off, or a failed `/verify` blocks the commit.
