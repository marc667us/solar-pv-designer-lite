#!/usr/bin/env bash
# Requirement review — checks the latest implementation against the stated requirement.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ./scripts/_codex-runner.sh

CONTEXT="$(gather_context)"

PROMPT="You are Codex acting as Independent Pair Programmer for this repository. Review the latest implementation against the stated requirement in README.md and (if present) docs/IMPLEMENTATION_LOG.md. Identify anything Claude Code missed, misunderstood, or only partially implemented. Return a checklist of defects with: severity (critical/high/medium/low), file:line, what's wrong, recommended fix, why it matters.

${CONTEXT}"

codex_run "codex-review" "$PROMPT"
