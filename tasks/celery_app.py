"""
Celery application factory.

Broker + result backend come from REDIS_URL. Routing/timeouts/retries set
per Q-gate 4.1 fix. Workers boot with:

    celery -A tasks.celery_app worker --loglevel=info \\
           --concurrency=2 --queues=default,heavy,ai_tasks,email,reports

Scheduled jobs (Celery Beat):

    celery -A tasks.celery_app beat --loglevel=info
"""

import os

from celery import Celery


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "solarpro",
    broker=REDIS_URL,
    backend=REDIS_URL,
    # Defer module loading until a task is actually called — keeps cold-start
    # fast and lets the workers boot even if optional integrations (Brevo,
    # Anthropic, etc.) are missing API keys.
    include=[
        "tasks.email_tasks",
        "tasks.report_tasks",
        "tasks.ai_tasks",
    ],
)


# --- Configuration ----------------------------------------------------------
# Per Q-gate work-schedule items 4.2/4.3/4.6:
# - Bound queues by purpose so a slow AI job can't starve a fast email job.
# - Set hard time limits so a hung subprocess can't block a worker forever.
# - Acks-late + reject-on-worker-lost = at-least-once delivery.
# - JSON-only serializer (no pickle) for safety.
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Routing — match queue names referenced in docker-compose.yml + k8s
    task_routes={
        "tasks.email_tasks.*":  {"queue": "email"},
        "tasks.report_tasks.*": {"queue": "reports"},
        "tasks.ai_tasks.*":     {"queue": "ai_tasks"},
        # Anything unmatched falls through to 'default'
    },
    task_default_queue="default",

    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,            # prevent fair scheduling skew
    task_soft_time_limit=300,                # 5 min soft (raises exception)
    task_time_limit=600,                     # 10 min hard (kills worker)
    broker_connection_retry_on_startup=True,

    # Result persistence — short-lived; we'll write result file IDs to
    # the `report_jobs` table separately when 4.3 lands.
    result_expires=3600,
)


# --- Health probe -----------------------------------------------------------
# /api/health/queue can ping this with `celery_app.control.ping(timeout=1)`
# once 4.1's web_app.py integration lands.
def healthcheck():
    """Return a small dict the health endpoint can serialize."""
    try:
        replies = celery_app.control.ping(timeout=1)
        return {"ok": True, "workers": len(replies or []), "details": replies}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}
