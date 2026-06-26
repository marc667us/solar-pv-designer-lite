# SOC 2 M3.4 — Observability Stack

Self-hosted Prometheus + Loki + Grafana (the LGP stack), provisioned
as code per the Solar Project Execution Directive's FOSS Stack Rule.

## What's in the box

| Service | Purpose | Port |
|---|---|---|
| `prometheus` | Scrapes `solarpro.aiappinvent.com/metrics` (bearer-gated) | 9090 |
| `loki` | Stores structured JSON logs (30-day retention) | 3100 |
| `promtail` | Tails `/var/log/solarpro/*.log` and ships to Loki | — |
| `grafana` | Dashboards + alerts | 3000 |

All four start with `docker compose up -d` and the **SolarPro SOC 2**
dashboard appears in Grafana pre-provisioned.

## Bring-up checklist (operator side)

1. Set `METRICS_BEARER` on the Render Solar service env (32-byte hex):

   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

   Push it through the Render dashboard or via `gh workflow run` if you
   wire a sync workflow.

2. Pick an observability host (a small Hetzner / DigitalOcean VPS is
   fine) and copy this directory to it:

   ```bash
   rsync -av infra/observability/ ops@OBS_HOST:/srv/solarpro-obs/
   ```

3. On the host:

   ```bash
   cd /srv/solarpro-obs
   cp .env.example .env
   ${EDITOR} .env   # fill SOLARPRO_METRICS_BEARER + GRAFANA_ADMIN_PASSWORD
   mkdir -p secrets && echo -n "$SOLARPRO_METRICS_BEARER" > secrets/metrics-bearer
   docker compose up -d
   ```

4. Open `http://OBS_HOST:3000`, log in as `admin` with the password
   from `.env`, navigate to "Dashboards → Browse → SolarPro SOC 2".

5. The first scrape happens within 30s; the dashboard's "HTTP request
   rate" and "Audit chain status" panels should populate immediately.

## Log shipping from Render

Render doesn't expose log files directly. Two FOSS-aligned options:

**Option A — Render Log Streams to Vector → file.** Configure a
Render Log Stream to push to a Vector instance on `OBS_HOST` whose
sink writes `/var/log/solarpro/*.log` in JSON Lines. Promtail picks
those up via the bind-mount in `docker-compose.yml`.

**Option B — Render Log Drain (HTTP) to a Loki push endpoint.**
Promtail listens on port 9080; if you front it with a small reverse
proxy that maps the Render Log Drain HTTPS POST onto Promtail's
`/loki/api/v1/raw` shape, the file step is avoided entirely.

The structured logger in `logging_config/structured_logger.py` already
emits one JSON line per event with `ts`, `level`, `action`, `tenant_id`,
`module` and the per-call payload; both options use the same pipeline
stage in `promtail-config.yml`.

## What the dashboard shows

- **HTTP request rate** broken down by 2xx / 3xx / 4xx / 5xx
- **Latency p50 / p95 / p99** computed from the histogram
- **Audit chain status** — green stat when `first_break_id = -1`,
  red with the offending row id otherwise (SOC 2 M3.2)
- **Audit chain coverage** — unchained vs total rows
- **RLS-enforced tables** — current count, watch for regressions
- **Error logs last 24h** — green ≤ 10, yellow 10–50, red > 50
- **OIDC callback failure rate by reason** — spike on bad config or
  a brute-force attempt
- **Audit writes rate by action** — confirms the writer pipeline is
  alive (M3.1 dashboard check)
- **Live structured logs (Loki)** — LogQL search panel scoped to
  `{service="solarpro"} | json`

## Alerts (next session)

The dashboard ships without alert rules; the natural next step is to
wire Grafana Alerting to a Discord or Telegram webhook for:

- `solarpro_audit_chain_first_break_id > -1` → tamper detected
- `solarpro_oidc_failures_total{reason="OIDC_STATE_MISMATCH"}` rate
  > 0.1/s over 5m → brute-force or stale-session storm
- `histogram_quantile(0.95, ...) > 2` → p95 latency degraded
- `solarpro_error_logs_recent_total > 50` → 5xx storm

These are tracked under **M3.6** (Slack + email alerts) in the SOC 2
implementation plan; this directory is M3.4 only.

## Cost

A 2 CPU / 2 GB VPS handles all four services with retention room for
about 100 MB/day of logs. Hetzner CX22 (€3.79/mo) is a working baseline.
