"""SolarPro Global — Structured Logging package."""
from .structured_logger import (
    log_app, log_error, log_audit, log_security,
    log_engineering, log_economic, log_ai, log_queue
)

__all__ = [
    "log_app", "log_error", "log_audit", "log_security",
    "log_engineering", "log_economic", "log_ai", "log_queue",
]
