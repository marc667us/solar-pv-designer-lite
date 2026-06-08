"""
tasks/ — Celery worker module.

Imports the Celery() instance + every @task definition so workers can boot
with: `celery -A tasks.celery_app worker --loglevel=info`.

Dormant until REDIS_URL is set. web_app.py does NOT import this yet — the
runtime app stays unchanged until Phase 4.2+ wires the queue calls
(Q-gate work-schedule 2026-06-06).

Closes Phase 4.1 scaffold portion: docker-compose.yml and
k8s/base/celery-deployment.yaml previously referenced `web_app.celery_app`
which does not exist — workers could not start. This module provides the
target they should reference: `tasks.celery_app`. See
docs/IMPLEMENTATION_LOG.md 2026-06-08 entry.
"""

from .celery_app import celery_app  # noqa: F401  — re-export for workers

# Import task modules so Celery auto-discovers them on worker boot.
# Each module registers its @celery_app.task functions at import time.
from . import email_tasks  # noqa: F401
from . import report_tasks  # noqa: F401
from . import ai_tasks  # noqa: F401

__all__ = ["celery_app"]
