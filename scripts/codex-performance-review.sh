#!/usr/bin/env bash
# Performance review — caching, queues, DB pooling, indexes, API design, long tasks.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ./scripts/_codex-runner.sh

CONTEXT="$(gather_context)"

PROMPT="You are Codex acting as Independent Performance Reviewer. Review the implementation for scaling. Assume 1000 concurrent users, multi-tenant load, large file uploads, multiple AI jobs, multiple queues. Check: caching (Redis/Valkey, tenant-scoped keys), queueing (Celery/RQ/Dramatiq for PDF/DOCX/Excel/BOQ/reports/AI/email), database connection pooling (PgBouncer), indexes (tenant_id and common composites), API response design (pagination, projection, no N+1), long-running tasks (must be queued, not synchronous). Return findings with: severity, location, scale risk, recommended fix.

${CONTEXT}"

codex_run "codex-performance-review" "$PROMPT"
