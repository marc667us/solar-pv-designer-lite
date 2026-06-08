"""
Email tasks — Brevo / Axigen / Resend / SMTP chain in background.

Replaces the synchronous `api_manager._send_email()` call inside request
handlers (Q-gate 4.3). Routes/handlers should call:

    from tasks.email_tasks import send_email
    send_email.delay(to=..., subject=..., html=..., tenant_id=..., user_id=...)

…and return 202 + a job_id. The web_app.py wiring lands in a separate
session (Phase 4.3 implementation).
"""

from celery import shared_task

from .celery_app import celery_app  # noqa: F401  — ensures app is loaded


@celery_app.task(name="tasks.email_tasks.send_email",
                 bind=True, max_retries=5, retry_backoff=True,
                 retry_backoff_max=600, retry_jitter=True)
def send_email(self, *, to, subject, html, tenant_id=None, user_id=None,
               text=None, reply_to=None):
    """
    Send a transactional email via the api_manager send chain.

    Records `tenant_id` + `user_id` in audit + email_logs (when the
    repository plumbing lands). Exponential backoff retries on transient
    delivery failures (Brevo 5xx, SMTP timeouts).
    """
    # Phase 4.3 wiring point: import api_manager._send_email and invoke it.
    # Until then this task is registered but doing nothing — call sites
    # are also not yet present, so it's truly dormant.
    raise NotImplementedError(
        "tasks.email_tasks.send_email body lands in Q-gate Phase 4.3 — "
        "callers should not invoke this until the api_manager.send_email "
        "import + DB-side job tracking are wired."
    )


@celery_app.task(name="tasks.email_tasks.send_referral_invite",
                 bind=True, max_retries=3)
def send_referral_invite(self, *, referrer_user_id, invitee_email, code,
                         tenant_id=None):
    """Specialized email — referral program invite."""
    raise NotImplementedError("Phase 4.3 — body TBD")


@celery_app.task(name="tasks.email_tasks.send_proposal",
                 bind=True, max_retries=3)
def send_proposal(self, *, project_id, recipient_email, pdf_storage_path,
                  tenant_id, user_id):
    """Attach a generated proposal PDF and send to the customer."""
    raise NotImplementedError("Phase 4.3 — body TBD")
