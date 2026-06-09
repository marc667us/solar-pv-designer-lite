# ai-coworkers — Claude + Codex Pair-Coding Setup

This folder lives at the root of every app I'm building. It operationalizes the **Claude + Codex CLI pair-coding workflow** described in the project's `CLAUDE.md` (Project Execution Directive).

## Folders

```
ai-coworkers/   role files + checklist + prompts + quality gates
reviews/        Codex review outputs (generated)
scripts/        review-runner shell scripts (one per review type + quality gate)
```

## Usage

After Claude finishes implementing a feature and tests pass:

```bash
./scripts/codex-review.sh              # requirement review
./scripts/codex-security-review.sh     # security + tenant + RLS
./scripts/codex-db-review.sh           # schema + indexes + migrations
./scripts/codex-test-review.sh         # coverage gaps
./scripts/codex-performance-review.sh  # caching + queues + scale
./scripts/quality-gate.sh              # runs all + final PASS/FAIL
```

Findings land in `reviews/codex-*.md`. Claude fixes critical/high findings, re-runs tests, then runs `quality-gate.sh` for final approval.

## Auth

Codex CLI needs one of:
- `OPENAI_API_KEY` environment variable (pay-as-you-go API), OR
- `codex login` — interactive ChatGPT Plus/Pro authentication

If neither is set, the review scripts capture Codex's auth error into the review markdown so the failure mode is visible.

## Idempotency

The roll-out script at `C:\Users\USER\_ai-coworkers-template\install.sh` copies these files into a target project root. It skips files that already exist so per-project customizations are preserved.
