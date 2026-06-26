"""SOC 2 M3.4 -- Prometheus metrics for the Solar app.

Design notes
============

prometheus_client uses a process-global default registry. We attach
our collectors to a *new* CollectorRegistry instance so:

  1. Tests can reset cleanly without nuking the library's defaults.
  2. The /metrics endpoint serves only OUR collectors, not Python
     interpreter defaults (gc, process info) which leak details.

Naming follows Prometheus convention: `solarpro_<subsystem>_<unit>`
with `_total` suffix on counters, `_seconds` on histograms, no suffix
on gauges.

Label cardinality is bounded by `_safe_route_label()` which collapses
high-cardinality route paths (e.g. /boq-projects/123) onto their
endpoint name (e.g. boq_project_view). Without this every URL would
spawn a unique series and OOM Prometheus.

Bearer gate
-----------

/metrics is gated by METRICS_BEARER env. Set it to a 32-byte hex
secret; configure your Prometheus scrape job with the matching
bearer_token. With METRICS_BEARER unset, the endpoint refuses every
request (403) -- fail-closed because metrics carry sensitive telemetry
(login failure rates, audit chain status, error counts).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable, Optional

from flask import Flask, Response, g, request

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)


log = logging.getLogger(__name__)


# ── Registry + collectors ───────────────────────────────────────────────

METRICS = CollectorRegistry(auto_describe=True)


http_requests_total = Counter(
    "solarpro_http_requests_total",
    "Total HTTP requests handled, labelled by endpoint, method, status_class.",
    labelnames=("endpoint", "method", "status_class"),
    registry=METRICS,
)


http_request_duration_seconds = Histogram(
    "solarpro_http_request_duration_seconds",
    "End-to-end request duration in seconds, by endpoint + method.",
    labelnames=("endpoint", "method"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=METRICS,
)


audit_writes_total = Counter(
    "solarpro_audit_writes_total",
    "Audit log writes via write_audit_event, labelled by action.",
    labelnames=("action",),
    registry=METRICS,
)


oidc_failures_total = Counter(
    "solarpro_oidc_failures_total",
    "OIDC callback failure redirects, labelled by failure reason.",
    labelnames=("reason",),
    registry=METRICS,
)


login_total = Counter(
    "solarpro_login_total",
    "Login attempts labelled by outcome (success/failed).",
    labelnames=("outcome",),
    registry=METRICS,
)


# ── Live-state gauges (refreshed on every /metrics scrape) ─────────────

audit_chain_total_rows = Gauge(
    "solarpro_audit_chain_total_rows",
    "Total rows in audit_logs (M3.1 + M3.2).",
    registry=METRICS,
)

audit_chain_unchained_rows = Gauge(
    "solarpro_audit_chain_unchained_rows",
    "Rows in audit_logs with NULL row_hash (legacy / unchained writers).",
    registry=METRICS,
)

audit_chain_first_break_id = Gauge(
    "solarpro_audit_chain_first_break_id",
    "ID of the first audit_logs row whose chain doesn't verify. -1 when clean.",
    registry=METRICS,
)

rls_tables_count = Gauge(
    "solarpro_rls_tables_count",
    "Number of tables with an active RLS policy (M1.6 + M3.3 batches).",
    registry=METRICS,
)

error_logs_recent_total = Gauge(
    "solarpro_error_logs_recent_total",
    "Rows in error_logs in the last 24h (M3.5).",
    registry=METRICS,
)


# ── Hook utilities ──────────────────────────────────────────────────────

def _safe_route_label(req) -> str:
    """Collapse high-cardinality paths onto Flask endpoint names so
    label cardinality stays bounded. /boq-projects/<int:pid> renders
    a million possible paths but only one endpoint label."""
    try:
        if req.url_rule and req.url_rule.endpoint:
            return req.url_rule.endpoint
    except Exception:
        pass
    return "unknown"


def _status_class(status_code: int) -> str:
    """Bucket status codes into 2xx/3xx/4xx/5xx so per-status series
    don't explode."""
    try:
        return f"{int(status_code) // 100}xx"
    except Exception:
        return "0xx"


def register_request_hooks(app: Flask) -> None:
    """Wire before/after_request hooks that record per-request latency
    + status counters. Idempotent: a second call is a no-op."""
    if getattr(app, "_observability_hooks_registered", False):
        return
    app._observability_hooks_registered = True

    @app.before_request
    def _start_timer():
        g._observability_t0 = time.monotonic()

    @app.after_request
    def _record_metrics(response):
        try:
            endpoint = _safe_route_label(request)
            method = request.method or "GET"
            sc = _status_class(getattr(response, "status_code", 0) or 0)
            http_requests_total.labels(
                endpoint=endpoint, method=method, status_class=sc,
            ).inc()
            t0 = getattr(g, "_observability_t0", None)
            if t0 is not None:
                http_request_duration_seconds.labels(
                    endpoint=endpoint, method=method,
                ).observe(max(0.0, time.monotonic() - t0))
        except Exception as e:
            log.debug("metrics after_request hook swallowed: %s", e)
        return response


# ── Gauge refresh ──────────────────────────────────────────────────────

def refresh_gauges(get_db_fn: Optional[Callable] = None) -> None:
    """Pull live numbers into the four DB-driven gauges. Designed to
    run on every /metrics scrape so Grafana panels see fresh data
    without a background worker. Each query is wrapped so a single
    failure can't poison the whole scrape."""
    if get_db_fn is None:
        try:
            import web_app  # type: ignore
            get_db_fn = web_app.get_db
        except Exception:
            return

    # 1. Audit chain status -- reuses verify_audit_chain so the count
    #    matches the SOC 2 dashboard exactly.
    try:
        from app.security.audit import verify_audit_chain, reset_schema_probe
        reset_schema_probe()
        with get_db_fn() as c:
            result = verify_audit_chain(c)
        audit_chain_total_rows.set(result.get("total", 0))
        audit_chain_unchained_rows.set(result.get("unchained", 0))
        fb = result.get("first_break")
        audit_chain_first_break_id.set(fb["id"] if fb else -1)
    except Exception as e:
        log.debug("refresh_gauges audit chain: %s", e)

    # 2. RLS policy count.
    try:
        with get_db_fn() as c:
            row = c.execute(
                "SELECT COUNT(DISTINCT tablename) FROM pg_policies "
                "WHERE schemaname='public'"
            ).fetchone()
            n = row[0] if row else 0
        rls_tables_count.set(n or 0)
    except Exception as e:
        log.debug("refresh_gauges rls count: %s", e)
        # SQLite local will fail this -- not a real signal.

    # 3. error_logs last 24h.
    try:
        with get_db_fn() as c:
            row = c.execute(
                "SELECT COUNT(*) FROM error_logs "
                "WHERE created_at > (NOW() - INTERVAL '24 hours')"
            ).fetchone()
            n = row[0] if row else 0
        error_logs_recent_total.set(n or 0)
    except Exception as e:
        log.debug("refresh_gauges error_logs: %s", e)


# ── /metrics endpoint ──────────────────────────────────────────────────

def _bearer_ok(auth_header: str) -> bool:
    """Constant-time-ish compare against METRICS_BEARER env. Returns
    False when the env is unset (fail-closed: metrics carry sensitive
    counters)."""
    expected = (os.environ.get("METRICS_BEARER") or "").strip()
    if not expected:
        return False
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return False
    sent = auth_header[7:].strip()
    # length-equal check then char-by-char to thwart timing oracle
    if len(sent) != len(expected):
        return False
    diff = 0
    for a, b in zip(sent, expected):
        diff |= ord(a) ^ ord(b)
    return diff == 0


def scrape_endpoint(app: Flask) -> None:
    """Register GET /metrics. Bearer-gated. Refreshes gauges then
    serves Prometheus exposition format."""

    @app.route("/metrics", methods=["GET"])
    def _metrics():
        if not _bearer_ok(request.headers.get("Authorization", "")):
            return Response(
                "401 metrics scrape requires Bearer token\n",
                status=401,
                mimetype="text/plain",
            )
        try:
            refresh_gauges()
        except Exception as e:
            log.warning("refresh_gauges raised on scrape: %s", e)
        payload = generate_latest(METRICS)
        return Response(payload, mimetype=CONTENT_TYPE_LATEST)
