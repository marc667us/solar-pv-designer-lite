#!/usr/bin/env bash
# Test review — coverage gaps in unit, integration, security, RLS, logout, load, UI tests.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ./scripts/_codex-runner.sh

CONTEXT="$(gather_context)"

PROMPT="You are Codex acting as Independent QA Reviewer. Review the test coverage. Identify missing unit tests, integration tests, security tests, RLS tests, logout tests, load tests, and UI tests. For every protected resource, verify that the minimum 5 tests exist: (1) authorized user can access, (2) unauthorized user cannot access, (3) wrong tenant cannot access, (4) logged-out user cannot access, (5) expired token cannot access. List every protected resource that lacks one or more of these tests. Return findings with: severity, resource/endpoint, missing test type, suggested test outline.

${CONTEXT}"

codex_run "codex-test-review" "$PROMPT"
