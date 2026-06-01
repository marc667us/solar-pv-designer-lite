# -*- coding: utf-8 -*-
"""
SolarPro Global — Structured JSON Logging
==========================================
Provides tenant-aware, structured JSON logging for all platform services.

Log types:
  - app       : General application events
  - audit     : User actions (login, logout, project view, BOQ, proposal, etc.)
  - security  : Auth failures, tenant violations, permission denied
  - engineering: PV design, BOQ, cable sizing events
  - economic  : Financial analysis, funding report events
  - ai        : AI agent execution events
  - queue     : Background job events (Celery)
  - error     : Application errors

Usage:
    from logging_config.structured_logger import (
        log_audit, log_security, log_app, log_error,
        log_engineering, log_economic, log_ai, log_queue
    )

    log_audit(action="login", user_id=123, tenant_id="t1", status="success")
    log_security(event_type="failed_login", ip_address="1.2.3.4", username="bob")
    log_app(module="pv_design", action="calc_pv", project_id="p1", status="success")
"""

import os
import json
import uuid
import logging
import logging.handlers
from datetime import datetime, timezone


# ─── Log directory ────────────────────────────────────────────────────────────

LOG_DIR = os.environ.get("LOG_DIR", os.path.join(os.path.dirname(__file__), "..", "logs"))

_dirs = {
    "backend":  os.path.join(LOG_DIR, "backend"),
    "audit":    os.path.join(LOG_DIR, "audit"),
    "security": os.path.join(LOG_DIR, "security"),
    "ai":       os.path.join(LOG_DIR, "ai-agents"),
    "queue":    os.path.join(LOG_DIR, "queue"),
}

for _d in _dirs.values():
    os.makedirs(_d, exist_ok=True)


# ─── JSON Formatter ───────────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """Emits each log record as a single-line JSON object."""

    def format(self, record):
        log_obj = {
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "level":       record.levelname,
            "logger":      record.name,
            "message":     record.getMessage(),
        }
        # Merge any extra fields set on the record
        for key, val in vars(record).items():
            if key not in (
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName",
                "exc_info", "exc_text"
            ):
                log_obj[key] = val
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, default=str)


def _make_logger(name: str, filepath: str, level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(f"solarpro.{name}")
    if logger.handlers:
        return logger
    logger.setLevel(level)
    logger.propagate = False

    # Rotating file handler: 10 MB per file, keep 10 files
    fh = logging.handlers.RotatingFileHandler(
        filepath, maxBytes=10 * 1024 * 1024, backupCount=10, encoding="utf-8"
    )
    fh.setFormatter(JSONFormatter())
    logger.addHandler(fh)

    # Also stream to stdout in non-production or when DEBUG
    if os.environ.get("LOG_LEVEL", "INFO").upper() == "DEBUG":
        sh = logging.StreamHandler()
        sh.setFormatter(JSONFormatter())
        logger.addHandler(sh)

    return logger


# ─── Loggers ──────────────────────────────────────────────────────────────────

_app_logger       = _make_logger("app",      os.path.join(_dirs["backend"],  "app.log"))
_error_logger     = _make_logger("error",    os.path.join(_dirs["backend"],  "error.log"), logging.ERROR)
_audit_logger     = _make_logger("audit",    os.path.join(_dirs["audit"],    "audit.log"))
_security_logger  = _make_logger("security", os.path.join(_dirs["security"], "security.log"))
_ai_logger        = _make_logger("ai",       os.path.join(_dirs["ai"],       "agent.log"))
_queue_logger     = _make_logger("queue",    os.path.join(_dirs["queue"],    "worker.log"))


# ─── Public logging helpers ───────────────────────────────────────────────────

def _build_record(**kwargs) -> dict:
    """Add a request_id to every log record if not provided."""
    if "request_id" not in kwargs:
        kwargs["request_id"] = str(uuid.uuid4())[:8]
    return kwargs


def log_app(module: str, action: str, status: str = "success", **kwargs):
    """General application event."""
    extra = _build_record(module=module, action=action, status=status, **kwargs)
    _app_logger.info(action, extra=extra)


def log_error(module: str, action: str, error: str, **kwargs):
    """Application error (exception context)."""
    extra = _build_record(module=module, action=action, status="error", error=error, **kwargs)
    _error_logger.error(action, extra=extra)


def log_audit(action: str, user_id=None, tenant_id: str = None,
              resource: str = None, status: str = "success", **kwargs):
    """
    Audit log — records every sensitive user action.

    Tracked actions:
      login, logout, failed_login, token_refresh, token_revoked
      admin_page_access, hidden_page_attempt, unauthorized_access
      tenant_isolation_violation, project_viewed, boq_generated,
      proposal_downloaded, procurement_package_created, bid_submitted,
      bid_evaluated, file_downloaded, permission_denied
    """
    extra = _build_record(
        action=action, user_id=user_id, tenant_id=tenant_id,
        resource=resource, status=status, **kwargs
    )
    _audit_logger.info(action, extra=extra)


def log_security(event_type: str, ip_address: str = None, user_id=None,
                 username: str = None, **kwargs):
    """
    Security event log.

    event_types:
      failed_login, brute_force_blocked, tenant_isolation_violation,
      unauthorized_page_access, hidden_page_probe,
      permission_denied, token_expired, invalid_csrf
    """
    extra = _build_record(
        event_type=event_type, ip_address=ip_address,
        user_id=user_id, username=username, **kwargs
    )
    _security_logger.warning(event_type, extra=extra)


def log_engineering(action: str, project_id=None, user_id=None,
                    tenant_id: str = None, **kwargs):
    """Engineering event: PV design generated, BOQ created, cable sizing done."""
    extra = _build_record(
        module="engineering", action=action,
        project_id=project_id, user_id=user_id, tenant_id=tenant_id, **kwargs
    )
    _app_logger.info(action, extra=extra)


def log_economic(action: str, project_id=None, user_id=None,
                 tenant_id: str = None, **kwargs):
    """Economic analysis event: NPV/IRR run, funding report generated."""
    extra = _build_record(
        module="economic_analysis", action=action,
        project_id=project_id, user_id=user_id, tenant_id=tenant_id, **kwargs
    )
    _app_logger.info(action, extra=extra)


def log_ai(agent: str, action: str, status: str = "success",
           tenant_id: str = None, **kwargs):
    """AI agent event: agent started, completed, failed."""
    extra = _build_record(
        agent=agent, action=action, status=status, tenant_id=tenant_id, **kwargs
    )
    _ai_logger.info(action, extra=extra)


def log_queue(task_name: str, task_id: str = None, status: str = "started",
              tenant_id: str = None, **kwargs):
    """Celery queue event: task started, completed, failed, retried."""
    extra = _build_record(
        task_name=task_name, task_id=task_id,
        status=status, tenant_id=tenant_id, **kwargs
    )
    _queue_logger.info(task_name, extra=extra)
