"""
AI tasks — prospect agent, helpline, assessment scoring (Q-gate 4.2).

Replaces the synchronous AI calls at web_app.py:8094 / 8184 / 8240 / 8446
that Codex flagged as worker-starvation risk (up to 12 web fetches +
multi-second LLM calls inside one Gunicorn request).

The per-tenant concurrency cap + daily quota land in Phase 4.2 via a
Redis semaphore (`tenant:{id}:ai_runs:in_flight`). Until then the tasks
are registered as no-ops.
"""

from celery import shared_task

from .celery_app import celery_app  # noqa: F401


@celery_app.task(name="tasks.ai_tasks.run_prospect_agent",
                 bind=True, max_retries=1, time_limit=900)
def run_prospect_agent(self, *, tenant_id, user_id, country, regions=None,
                       industry_filters=None):
    """
    Run the prospecting agent — searches tender portals, fetches up to N
    pages, summarizes with Claude/OpenRouter/Ollama, stores leads.

    Per-tenant concurrency: 1 (semaphore enforced before this task is
    scheduled; if a tenant already has one in-flight the API returns 429).
    """
    raise NotImplementedError(
        "Phase 4.2 — body wraps web_app.admin_agent_run() logic with proper "
        "tenant + quota + audit-log integration."
    )


@celery_app.task(name="tasks.ai_tasks.score_assessment",
                 bind=True, max_retries=2)
def score_assessment(self, *, assessment_request_id, tenant_id=None):
    """
    Score a public assessment request using the helpline AI chain.
    Tenant-less when the assessment is anonymous (organization_id IS NULL).
    """
    raise NotImplementedError("Phase 4.2 — body TBD")


@celery_app.task(name="tasks.ai_tasks.helpline_chat",
                 bind=True, max_retries=0, time_limit=60)
def helpline_chat(self, *, user_id, tenant_id, message, conversation_id=None):
    """
    Server-side helpline call — alternative to the synchronous
    /api/assistant/chat. Returns AI reply + escalate flag.
    For the current low-volume case the synchronous route is fine; this
    task is the path forward when concurrency increases.
    """
    raise NotImplementedError("Phase 4.2 — body TBD")
