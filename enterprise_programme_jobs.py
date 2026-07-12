"""Enterprise Solar Programme Management -- durable job queue (Phase 1: foundation).

WHY THIS EXISTS
---------------
The spec forbids generating thousands of projects inside a web request
(File B §17). This app has NO usable worker to hand that work to:

  * Celery IS defined under tasks/ but is never imported and never dispatched,
    and no worker process is deployed.
  * Production runs ONE gunicorn process (gthread, 1 worker, 4 threads, 300s
    timeout -- set through the Render API by
    .github/workflows/render-apply-best-practices.yml; the Procfile is ignored).
  * `threading.Thread` is used elsewhere in the app but is not durable: work in
    flight is lost on the frequent free-tier restarts.

So bulk work becomes a DATABASE-BACKED, CHUNKED, RESUMABLE job:

  claim_job()  -> take one queued job under a lock (FOR UPDATE SKIP LOCKED on PG)
  <run one small chunk of it, well inside the request timeout>
  save_progress() -> persist the cursor and release
  ...repeat until done. A restart mid-job loses at most one chunk.

Chunks must be IDEMPOTENT (File B §5.8): re-running a chunk after a crash must
not double-create rows. The `idempotency_key` on the job, plus per-item natural
keys, are what make a retry safe.

PHASE 1 SCOPE: the table and these helpers only. NOTHING is enqueued yet and no
bulk generation runs. Phase 2 puts beneficiary import and project generation on
top of this. The tick endpoint stays behind its own flag
(`enterprise_programme_jobs_enabled`, dark by default).
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import enterprise_programme_repository as repo

# A chunk must finish comfortably inside the 300s request timeout, with room for
# a cold start. Sized for ~60-90s of real work, not for the theoretical maximum.
DEFAULT_CHUNK = 25

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_SUCCEEDED = "succeeded"
JOB_FAILED = "failed"
JOB_CANCELLED = "cancelled"


def _is_postgres() -> bool:
    return repo._is_postgres()


def enqueue(get_db, org_id: int, user_id: int, job_type: str,
            programme_id: int | None = None, payload: dict | None = None,
            idempotency_key: str | None = None, total: int = 0) -> int | None:
    """Queue a job. Returns the job id, or the EXISTING id if the key repeats.

    Input:  org_id (from membership), users.id, a job_type, optional payload.
    Output: job id. Idempotent on (organisation_id, idempotency_key) -- a
            double-submitted form cannot create two jobs.
    """
    key = idempotency_key or str(uuid.uuid4())
    with get_db() as c:
        repo.apply_enterprise_guc(c, user_id)
        existing = c.execute(
            "SELECT id FROM enterprise_programme_jobs "
            "WHERE organisation_id=? AND idempotency_key=?",
            (org_id, key),
        ).fetchone()
        if existing:
            return int(existing["id"] if hasattr(existing, "keys") else existing[0])

        return repo._insert_returning_id(
            c,
            "INSERT INTO enterprise_programme_jobs "
            "(organisation_id, programme_id, job_type, status, idempotency_key, "
            " payload_json, progress_total, created_by_user_id) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (org_id, programme_id, job_type, JOB_QUEUED, key,
             json.dumps(payload or {}), int(total), user_id),
        )


def claim_job(get_db, org_id: int, user_id: int, worker_id: str = "") -> dict | None:
    """Claim the next queued job for this organisation, or None.

    On Postgres the claim uses FOR UPDATE SKIP LOCKED so two concurrent ticks
    cannot grab the same job. SQLite (local dev) has no such clause and is
    single-writer anyway, so it takes the simple path.
    """
    worker = worker_id or f"web-{os.getpid()}"
    with get_db() as c:
        repo.apply_enterprise_guc(c, user_id)
        if _is_postgres():
            row = c.execute(
                "SELECT * FROM enterprise_programme_jobs "
                "WHERE organisation_id=? AND status=? "
                "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED",
                (org_id, JOB_QUEUED),
            ).fetchone()
        else:
            row = c.execute(
                "SELECT * FROM enterprise_programme_jobs "
                "WHERE organisation_id=? AND status=? ORDER BY id LIMIT 1",
                (org_id, JOB_QUEUED),
            ).fetchone()
        if not row:
            return None

        job = dict(row)
        c.execute(
            "UPDATE enterprise_programme_jobs "
            "SET status=?, locked_by=?, attempts=attempts+1, "
            "    updated_at=CURRENT_TIMESTAMP "
            "WHERE id=? AND organisation_id=?",
            (JOB_RUNNING, worker, job["id"], org_id),
        )
        job["status"] = JOB_RUNNING
    return job


def save_progress(get_db, org_id: int, user_id: int, job_id: int, *,
                  current: int, cursor: dict | None = None,
                  done: bool = False, error: str = "") -> None:
    """Persist one chunk's progress, and release or finish the job.

    `cursor` is whatever the job needs to resume where it stopped (e.g. the last
    row id processed). Persisting it after every chunk is what makes the job
    survive a restart.
    """
    status = JOB_SUCCEEDED if done else JOB_QUEUED
    if error:
        status = JOB_FAILED
    with get_db() as c:
        repo.apply_enterprise_guc(c, user_id)
        c.execute(
            "UPDATE enterprise_programme_jobs "
            "SET status=?, progress_current=?, cursor_json=?, last_error=?, "
            "    locked_by='', updated_at=CURRENT_TIMESTAMP "
            "WHERE id=? AND organisation_id=?",
            (status, int(current), json.dumps(cursor or {}), str(error)[:500],
             job_id, org_id),
        )


def get_job(get_db, org_id: int, user_id: int, job_id: int) -> dict | None:
    """One job, scoped to the caller's organisation (for UI polling)."""
    with get_db() as c:
        repo.apply_enterprise_guc(c, user_id)
        row = c.execute(
            "SELECT * FROM enterprise_programme_jobs WHERE id=? AND organisation_id=?",
            (job_id, org_id),
        ).fetchone()
    return dict(row) if row else None


def list_jobs(get_db, org_id: int, user_id: int, limit: int = 25) -> list[dict]:
    """Recent jobs for the caller's organisation."""
    with get_db() as c:
        repo.apply_enterprise_guc(c, user_id)
        rows = c.execute(
            "SELECT * FROM enterprise_programme_jobs WHERE organisation_id=? "
            "ORDER BY id DESC LIMIT ?",
            (org_id, int(limit)),
        ).fetchall()
    return [dict(r) for r in rows]


def cancel_job(get_db, org_id: int, user_id: int, job_id: int) -> bool:
    """Cancel a job that has not finished. Safe: only queued jobs are cancelled."""
    with get_db() as c:
        repo.apply_enterprise_guc(c, user_id)
        cur = c.execute(
            "UPDATE enterprise_programme_jobs SET status=?, updated_at=CURRENT_TIMESTAMP "
            "WHERE id=? AND organisation_id=? AND status IN (?, ?)",
            (JOB_CANCELLED, job_id, org_id, JOB_QUEUED, JOB_RUNNING),
        )
    return (cur.rowcount or 0) > 0


def tick(get_db, org_id: int, user_id: int) -> dict[str, Any]:
    """Process ONE chunk of ONE job. Phase 1: no job types are registered yet.

    Phase 2 registers handlers here (beneficiary import, project generation).
    Until then this claims a job and immediately marks it failed with a clear
    reason rather than silently swallowing it -- an unhandled job type is a bug,
    not a no-op.
    """
    job = claim_job(get_db, org_id, user_id)
    if not job:
        return {"claimed": False, "message": "No queued jobs."}

    handler = _HANDLERS.get(job["job_type"])
    if handler is None:
        save_progress(get_db, org_id, user_id, job["id"], current=0,
                      error=f"No handler registered for job_type={job['job_type']!r}")
        return {"claimed": True, "job_id": job["id"], "ok": False,
                "message": f"No handler for {job['job_type']!r} (Phase 2)."}

    return handler(get_db, org_id, user_id, job)


# Phase 2 populates this: {"beneficiary_import": fn, "project_generation": fn}.
# Each fn processes at most DEFAULT_CHUNK items, then calls save_progress().
_HANDLERS: dict[str, Any] = {}
