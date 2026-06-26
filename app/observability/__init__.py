"""SOC 2 M3.4 observability stack -- Prometheus + Loki + Grafana.

Module exports:
  * metrics            -- the Prometheus collectors (counters, gauges,
                          histograms) used across the app.
  * register_request_hooks(app)
                       -- wires Flask before/after_request hooks that
                          record per-request latency + status counts.
  * scrape_endpoint(app)
                       -- registers the bearer-gated /metrics route
                          that Prometheus scrapes.
  * refresh_gauges(get_db_fn)
                       -- pulls live DB-driven numbers (audit chain
                          status, RLS coverage, error count) into the
                          Gauges. Called from /metrics on every scrape
                          AND from the SOC 2 audit dashboard.

The structured JSON logger in logging_config/ already feeds Loki
naturally (Loki accepts any line-oriented log; the JSON layout means
LogQL can filter on `action="LOGIN_FAILED"` directly). No code change
needed there beyond the infra/observability/promtail-config.yml that
ships log shipping rules.
"""

from app.observability.metrics import (  # noqa: F401
    METRICS,
    audit_chain_first_break_id,
    audit_chain_total_rows,
    audit_chain_unchained_rows,
    audit_writes_total,
    error_logs_recent_total,
    http_request_duration_seconds,
    http_requests_total,
    login_total,
    oidc_failures_total,
    refresh_gauges,
    register_request_hooks,
    rls_tables_count,
    scrape_endpoint,
)
