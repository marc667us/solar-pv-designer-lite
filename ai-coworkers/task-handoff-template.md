# Task Handoff Template

Use this when handing a Claude-implemented feature to Codex for review.

```
## Feature

<one-line description>

## Requirement source

<link to spec, issue, or roadmap entry>

## Files changed

<git diff --stat output, or list of paths>

## Database changes

<new tables / new columns / migrations / RLS policies added>

## API changes

<new/changed endpoints, with method + path + auth model>

## Frontend changes

<new/changed pages or components>

## Tests added

<unit / integration / security / RLS / logout tests>

## Self-review notes

<anything Claude is uncertain about — Codex should focus here>

## Codex review request

Please run:
- ./scripts/codex-review.sh
- ./scripts/codex-security-review.sh
- ./scripts/codex-db-review.sh         (if DB changed)
- ./scripts/codex-test-review.sh
- ./scripts/codex-performance-review.sh (if scale-sensitive)
- ./scripts/quality-gate.sh

Findings will land in ./reviews/. I will fix all critical/high before requesting final approval.
```
