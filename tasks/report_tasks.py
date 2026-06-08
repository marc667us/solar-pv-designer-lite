"""
Report tasks — PDF / DOCX / Excel / BOQ generation in background.

Replaces the in-request PDF rendering at web_app.py:3284, 3775, 7405, 7516
that Codex flagged as scale risk (Q-gate 4.3). Each task writes its result
artifact to object storage (MinIO when 4.4 lands; SQLite blob temporarily)
and records the file_id in a `report_jobs` table.

Callers (after Phase 4.3 wires this in):

    from tasks.report_tasks import generate_proposal_pdf
    job = generate_proposal_pdf.delay(project_id=..., tenant_id=..., user_id=...)
    return jsonify(job_id=job.id, status_url=...), 202
"""

from celery import shared_task

from .celery_app import celery_app  # noqa: F401


@celery_app.task(name="tasks.report_tasks.generate_proposal_pdf",
                 bind=True, max_retries=2, time_limit=600)
def generate_proposal_pdf(self, *, project_id, tenant_id, user_id):
    """Render the proposal PDF for a project; write to storage; return file_id."""
    raise NotImplementedError("Phase 4.3 — body TBD")


@celery_app.task(name="tasks.report_tasks.generate_boq",
                 bind=True, max_retries=2, time_limit=600)
def generate_boq(self, *, project_id, tenant_id, user_id, format="pdf"):
    """Bill of Quantities — supports format=pdf|docx|excel."""
    raise NotImplementedError("Phase 4.3 — body TBD")


@celery_app.task(name="tasks.report_tasks.generate_cable_report",
                 bind=True, max_retries=2)
def generate_cable_report(self, *, project_id, tenant_id, user_id, format="pdf"):
    raise NotImplementedError("Phase 4.3 — body TBD")


@celery_app.task(name="tasks.report_tasks.generate_economic_report",
                 bind=True, max_retries=2)
def generate_economic_report(self, *, project_id, tenant_id, user_id, format="pdf"):
    raise NotImplementedError("Phase 4.3 — body TBD")


@celery_app.task(name="tasks.report_tasks.generate_installation_drawings",
                 bind=True, max_retries=2)
def generate_installation_drawings(self, *, project_id, tenant_id, user_id):
    """The heaviest report — installation drawings + ground-mount diagrams."""
    raise NotImplementedError("Phase 4.3 — body TBD")
