# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**SolarPro Global** — Intelligent Global PV Solar System Design Platform.
Flask web SaaS for residential, commercial, and industrial solar PV design, financial engineering, and project management.

- **Live URL (Render — primary as of 2026-06-05)**: https://solarpro-global.onrender.com — Railway deploy stuck so backend moved to Render. Render service ID lives in GitHub Secrets.
- **Old Railway URL (still up but stale)**: https://web-production-744af.up.railway.app
- **Custom domain**: https://solarpro.aiappinvent.com — Railway cert stuck; CF flip never completed
- **GitHub**: marc667us/solar-pv-designer-lite
- **Branch model**: `master` = production / `develop` = active feature work / `staging` = pre-prod (planned)
- **Hosting**:
  - **Render (primary)** — free tier. Deploy via `gh workflow run "Force Render Deploy"`. API key + service ID in repo secrets. Render mounts disk at `/app/data` if attached (NOT yet — Render disk REST API returned 404).
  - **Railway (legacy)** — free tier. Project ID `310ad3cf-...`, service ID `b9889adc-...`. Auto-deploy on push is broken; redeploy via `gh workflow run "Railway Sync and Deploy"` still doesn't pick up new source.
- **SolarPro admin login**: `admin` — password sourced from env `SOLARPRO_ADMIN_PASSWORD` (rotated 2026-06-08; see secret in Render env + GitHub Secrets). Owner account `marc667us` uses `SOLARPRO_OWNER_PASSWORD` (same rotation date). The seed in `web_app.py` reads both from env and raises `RuntimeError` if unset.
- **Campaign portal**: torn down in commit `95e07c9` on 2026-06-07. Any references to `/api/campaign/*` or `campaign_api.py` in older docs are historical.

Most of the app lives in **`web_app.py`** (~494KB, ~10 000 lines). SQLite database (`solar.db` locally, `/app/solar.db` on Railway / `/app/data/solar.db` on Render once disk is attached). Set `DB_PATH` env var to override.

---

## Running locally

```powershell
cd "C:\Users\USER\Desktop\solar-pv-designer-lite"
python start.py
```

`start.py` starts Waitress on port 5000 then opens a Cloudflare tunnel (`C:\Users\USER\cloudflared.exe`). Prints the public URL when ready.

**Flask dev server (hot-reload, no tunnel):**
```powershell
python web_app.py
```

**Railway (production):**
```bash
gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

---

## CRITICAL — Editing `web_app.py`

**NEVER use the Edit tool directly on `web_app.py`.**

It has CRLF line endings + mojibake (UTF-8 dashes stored as Windows-1252). The Edit tool introduces Unicode curly quotes (`\xe2\x80\x9d`) that corrupt the file.

### Pattern A — small byte replacements
```python
data = open('web_app.py', 'rb').read()
data = data.replace(b'old bytes', b'new bytes')
open('web_app.py', 'wb').write(data)
```

### Pattern B — inserting large blocks (preferred for new routes)
1. Write route code to a **separate file** e.g. `new_xxx_routes.py`
2. Write a patch script that reads both files:
```python
data = open('web_app.py', 'rb').read()
new_code = open('new_xxx_routes.py', 'rb').read()
new_code_crlf = new_code.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
TARGET = b'if __name__ == "__main__":'
pos = data.rfind(TARGET)
data = data[:pos] + new_code_crlf + b'\r\n' + data[pos:]
open('web_app.py', 'wb').write(data)
```
3. **Never use `b'''...'''` bytes literals** that contain triple-quoted Python code — use the file-read approach instead.

---

## Database

SQLite. Schema auto-created by `init_db()` on every cold start. All project engineering data stored as JSON blob in `projects.data_json`.

**Key pitfalls:**
- Login field is `username` (not `email`)
- CSRF field is `_csrf`
- Ghana region names: `Greater Accra`, `Ashanti`, `Northern`, `Volta`, `Western`
- `mounting_type` values: `rooftop_pitched`, `rooftop_flat`, `rooftop_metal`, `rooftop_membrane`, `ground_fixed`, `ground_tracking`

---

## Architecture

Single-file Flask app — no blueprints. Route namespaces:

| Namespace | What |
|---|---|
| `/` | Landing, auth, dashboard, project wizard |
| `/project/<pid>/report/*` | Engineering reports (PV, BOQ, cable, economic, installation, energy, proposal) |
| `/admin/*` | Admin panel (users, tickets, news, agent, stats) |
| `/admin/operations` | Admin Ops Center (NOC/SOC dashboard) |
| `/admin/logs` | JSON log viewer |
| `/admin/ops/*` | Ops action endpoints (see section below) |
| `/api/health*` | Health check endpoints |
| `/api/ping`, `/metrics` | Liveness + Prometheus metrics |
| `/api/assistant/chat` | Helpline AI chat |
| `/assess`, `/upgrade`, `/paystack/*`, `/stripe/*` | Public forms + payments |

Supporting modules:
- `calculation/ac_cable_sizing.py` — AC cable sizing
- `config/global_solar_data.py` — country/region solar irradiance database
- `logging_config/structured_logger.py` — JSON structured logging (app/error/audit/security/ai/queue)
- `wsgi.py` — Render/Gunicorn entrypoint
- `static/land-110m.json` — Bundled world atlas topojson (55KB, globe widget)

Templates: `templates/` (58+ HTML files). Base layout: `templates/base.html`.
Admin panel: `templates/admin.html`, `templates/admin_operations.html`, `templates/admin_logs.html`.

---

## Health Check Endpoints

All added in session 2026-06-02 (commit `598b071`):

| Endpoint | Returns |
|---|---|
| `GET /api/ping` | `{"pong": true}` — note: no `"status"` key |
| `GET /api/health` | Overall health summary |
| `GET /api/health/database` | SQLite read/write test |
| `GET /api/health/redis` | Redis ping (WARN on Render free tier — no Redis) |
| `GET /api/health/queue` | Celery queue depth (WARN on Render free tier — no Celery) |
| `GET /api/health/storage` | Disk space check |
| `GET /api/health/ai` | AI provider connectivity |
| `GET /metrics` | Prometheus text format metrics |

---

## Admin Ops Center Endpoints (`/admin/ops/*`)

All require `@admin_required`. POST endpoints require CSRF token.

### Pings
| Endpoint | Method | Notes |
|---|---|---|
| `/admin/ops/ping/frontend` | GET | Latency to live URL |
| `/admin/ops/ping/backend` | GET | Internal `/api/ping` |
| `/admin/ops/ping/redis` | GET | Redis PING (WARN on free tier) |
| `/admin/ops/ping/database` | GET | SQLite write test |

### Security
| Endpoint | Method | Notes |
|---|---|---|
| `/admin/ops/db/rls-check` | GET | Row-level security verification |
| `/admin/ops/security/tenant-isolation` | GET | Tenant data isolation check |
| `/admin/ops/security/audit` | GET | Security audit summary |
| `/admin/ops/security/sessions` | GET | Lists recent users from DB (PRAGMA-safe) |
| `/admin/ops/security/revoke-all-sessions` | POST | Clears Flask session store |

### System Tools
| Endpoint | Method | Notes |
|---|---|---|
| `/admin/ops/system/pip-audit` | GET | Runs `pip-audit` for CVEs |
| `/admin/ops/system/load-test` | POST | 5 threads × 10 requests against `/api/ping` |
| `/admin/ops/email/status` | GET | Shows current email config (masked) |
| `/admin/ops/email/test` | POST | Sends test email (Resend first, SMTP fallback) |

### Cache / Queue
| Endpoint | Method | Notes |
|---|---|---|
| `/admin/ops/cache/clear` | POST | Clears Flask cache |
| `/admin/ops/queue/restart` | POST | Restarts Celery workers (WARN on free tier) |

### Database
| Endpoint | Method | Notes |
|---|---|---|
| `/admin/ops/db/vacuum` | POST | VACUUM SQLite |

### Backup / Logs
| Endpoint | Method | Notes |
|---|---|---|
| `/admin/ops/backup/run` | POST | Creates backup of solar.db |
| `/admin/ops/backup/download` | GET | Downloads latest backup |
| `/admin/ops/logs/view` | GET | Returns recent app log lines |
| `/admin/ops/logs/audit` | GET | Returns audit log entries |
| `/admin/ops/logs/export` | GET | Downloads logs as ZIP |

**Live test results (2026-06-02):** 26/29 PASS. Redis ping = WARN (no Redis on free tier), Restart Queue = WARN (no Celery), Send Test Email = FAIL (Render blocks SMTP + Resend domain unverified).

---

## Structured Logging

`logging_config/structured_logger.py` — JSON RotatingFileHandlers.

```python
from logging_config.structured_logger import log_app, log_audit, log_security, log_ai, log_queue
log_audit("user_login", user_id=uid, org_id=org)
log_security("brute_force", ip=ip, attempts=n)
```

Log files: `logs/app.log`, `logs/error.log`, `logs/audit.log`, `logs/security.log`, `logs/ai.log`, `logs/queue.log`.

---

## K8s Infrastructure (`k8s/`)

Full Kubernetes manifests with Kustomize overlays (commit `598b071`):

```
k8s/
  base/           namespace, configmap, secret-template, backend-deployment (HPA min3/max20),
                  service, redis+PVC, celery, nginx ingress (TLS + security headers),
                  network-policy, PodDisruptionBudget
  dev/            1 replica, DEBUG=true
  staging/        2 replicas
  production/     3 replicas, 4 gunicorn workers, manual approval gate
  geo-routing/    Cloudflare GeoDNS: 4 pools (AF/EU/US/ME), WAF rules, edge Workers
```

Deployment probes use `/api/health`. Non-root uid 1000. topologySpreadConstraints for zone spread.

**No cluster provisioned yet** — manifests exist but no GKE/EKS/DO cluster is set up.

---

## Docker

`Dockerfile` — multi-stage: `builder` + lean `python:3.12-slim`, non-root uid 1000, HEALTHCHECK at `/api/health`.

`docker-compose.yml` — backend + redis + celery.

`docker-compose.monitoring.yml` — Prometheus + Grafana + Loki + Promtail + Uptime Kuma + Flower.

---

## Monitoring (`monitoring/`)

- `prometheus/alerts.yml` — Alerts: HighErrorRate (>5%), SlowResponseTime (p95>3s), BruteForce (>20/5min), TenantIsolationViolation, CeleryQueueBacklog (>100)
- `grafana/` — auto-provisioned datasources + dashboard loader
- `loki/` — 30-day retention; Promtail JSON pipeline for log labels

---

## CI/CD

`.github/workflows/`:
- `deploy.yml` — Railway auto-deploys on push to master (GitHub integration in Railway dashboard). No API trigger needed. Set env vars once in Railway dashboard → Variables tab.
- `ci.yml` — flake8/black lint, pip-audit, Semgrep SAST, Trivy image scan, smoke test
- `deploy-dev.yml` — push-to-dev → kustomize apply (needs K8s cluster secrets)
- `deploy-production.yml` — semver tag → manual approval → deploy → rollback on fail

---

## Database Migrations (`migrations/`)

PostgreSQL-ready (not yet deployed — current stack is SQLite):
- `001_postgresql_schema.sql` — Full schema, UUID PKs, human-readable codes (USR-/ORG-/PRJ-/PAY-)
- `002_rls_policies.sql` — RLS on 18 tenant tables, `current_tenant_id()` / `is_super_admin()` helpers
- `database-sharding.md` — 3-phase strategy: SQLite → single Neon → read replicas → geo sharding

---

## Globe Widget (`templates/location.html`)

D3.js v7 canvas-based rotating orthographic globe.

- **Land data**: `/static/land-110m.json` (same-origin — do NOT change to CDN)
- Red dot = no location selected; Green dot = location selected
- `flyToLocation(lat, lon, label, saved)` always sets green marker
- D3 uses chained `.projection(proj).context(ctx)` API

---

## AI Stack

### Helpline (floating chat, `/api/assistant/chat`)
Chain: Claude `claude-opus-4-7` → OpenRouter (free Llama/Gemma) → Ollama → GitHub Models `gpt-4.1-mini` → rule-based fallback.
CSRF via `X-CSRF-Token` header. `[ESCALATE]` tag → high-priority ticket.

### Prospecting Agent (`/admin/agent/run`)
Chain: OpenRouter (4 free models) → Ollama → GitHub Models → Claude (last resort).
Sequential `if raw is None` blocks (NOT `elif`).

**GitHub Models endpoint**: `https://models.inference.ai.azure.com/chat/completions`, model `gpt-4.1-mini` (NOT `openai/gpt-4.1-mini`).

---

## Email Stack

- `_send_email()` send chain (api_manager.py): **Brevo → Axigen → Resend → SMTP**
- **Brevo (primary, HTTPS, free 300/day):** `BREVO_API_KEY` (`xkeysib-...`). Domain `aiappinvent.com` is **authenticated** (4 DNS records on Namecheap: 2 DKIM CNAMEs, 1 brevo-code TXT, 1 DMARC TXT) so we can send from any `@aiappinvent.com` address. Verified senders in production: `sales@`, `support@`, `billing@`, plus auto-verified `marc667us@yahoo.com`.
- **Axigen (secondary, scaffolded only):** `AXIGEN_SERVER_URL`/`AXIGEN_USER`/`AXIGEN_PASSWORD` — vars exist + integration code lives in api_manager._send_axigen(); no actual server provisioned yet
- **Resend (fallback, currently broken):** `RESEND_API_KEY` value is a Render-generated placeholder `rnd_pGzm…`, not a real Resend key. To re-enable: generate at https://resend.com/api-keys, `gh secret set RESEND_API_KEY -b "re_xxx"`, redeploy.
- **SMTP (last resort):** Namecheap Private Email — `mail.privateemail.com:587` STARTTLS. **Render blocks outbound SMTP; Railway free tier also blocks it.** SMTP only works on paid hosting or self-host.

---

## Payments

- **Paystack — client-side via PaystackPop.js** on `templates/upgrade.html`. Server-side routes: `/paystack/verify` (POST, called by JS callback) + `/paystack/webhook` (POST, async confirmation). There is NO server-side `/paystack/initialize` route — the popup talks directly to Paystack.
- **Stripe** — `stripe.checkout.Session.create`; webhook `/stripe/webhook`
- Plans: `free` (14-day trial), `professional` ($49/mo), `business` ($99/mo), `enterprise` (custom)

---

## Referral Program (commit `16b7ba3`)

- Schema: `users.referral_code` (unique 8-char per user, auto-generated on signup), `users.referred_by` (FK), `referrals` table logs conversions
- Routes: `GET /r/<code>` → sets `ref_code` cookie + 302s to landing; `GET /referrals` → user dashboard
- `base.html` injects `REF_COOKIE_CAPTURE_v1` JS that reads `?ref=CODE` from URL and stores the same cookie
- `register()` reads cookie, looks up referrer, sets `referred_by`, logs to `referrals` table
- Reward language (template only, manually applied): 20% credit per paid referral + 20% off first paid month for referee
- Live tests: 10/10 PASS (`test_referrals_live.py`)

---

## 14-Day Free-Trial Model (on `develop` branch only, NOT in production)

- Source spec: `C:\Users\USER\Documents\pvsolar1\kubernates\basicprice.txt`
- Commit: `163a936` on `develop`
- Schema: `users.trial_end_date` (TEXT ISO 8601, set to now+14d on signup)
- `_paid_only()` admits free-plan users while `now <= trial_end_date`; otherwise redirect to `/upgrade`
- `_trial_days_left()` helper exposed via Jinja `context_processor` for countdown widgets
- Out of scope (future sessions): 50k+ public product catalog (electrical, IT), AI Product Intelligence Agent, automated day 7/10/13/15 reminders, CRM tables (public_visitors, product_views, supplier_views)

---

## Installation Reports — Ground Mount

Both `templates/report_installation.html` and `templates/report_installation_drawings.html` check:
```jinja2
{% set mt = d.get('mounting_type','rooftop_pitched') %}
{% if mt in ['ground_fixed','ground_tracking'] %}
```
Ground mount shows STEEL POST / CONCRETE FOOTING / PURLIN BEAM / EARTH ROD hardware.

---

## Railway Variables (set in Railway dashboard → Variables tab)

| Variable | Status |
|----------|--------|
| `ANTHROPIC_API_KEY` | **leave empty** — zero-cost policy; chain falls through to OpenRouter |
| `OPENROUTER_API_KEY` | copy from GitHub Secrets (free Llama/Gemma models) |
| `BREVO_API_KEY` | copy from GitHub Secrets — current primary email provider |
| `AXIGEN_SERVER_URL` / `AXIGEN_USER` / `AXIGEN_PASSWORD` | empty until VPS provisioned |
| `RESEND_API_KEY` | held but invalid placeholder `rnd_pGzm…`; not used |
| `PAYSTACK_SECRET_KEY` | copy from GitHub Secrets |
| `SECRET_KEY` | copy from GitHub Secrets |
| `OLLAMA_URL` | copy from GitHub Secrets |
| `OLLAMA_MODEL` | copy from GitHub Secrets |
| `SMTP_HOST` | mail.privateemail.com |
| `SMTP_PORT` | 587 |
| `SMTP_USER` | support@aiappinvent.com |
| `SMTP_PASS` | copy from GitHub Secrets |
| `SMTP_FROM` | sales@aiappinvent.com |
| `SMTP_TLS` | true |
| `EMAIL_SALES` | sales@aiappinvent.com |
| `EMAIL_SUPPORT` | support@aiappinvent.com |
| `EMAIL_BILLING` | billing@aiappinvent.com |
| `EMAIL_HELLO` | ❌ not set |
| `EMAIL_PROPOSALS` | ❌ not set |

---

## Security (implemented)

- Brute-force lockout (5 failed → 15 min lockout)
- CSRF on all POST forms (`_csrf` field)
- Content Security Policy headers
- Paystack webhook signature verification
- Audit log table + structured JSON security log
- `robots.txt` (blocks crawlers)
- Zero Trust architecture, RBAC (9 roles) — documented in `SECURITY.md`
- RLS on 18 tenant tables (PostgreSQL migrations ready)

**Pending:**
- Admin 2FA (`pyotp` TOTP)
- DMARC DNS: `_dmarc.aiappinvent.com TXT "v=DMARC1; p=none; rua=mailto:marc667us@yahoo.com"`

---

## Engineering Calculation Flow

1. Location step → `config/global_solar_data.py` returns PSH, temp, tariff, currency
2. Loads step (POST) → `calc_loads()` → `calc_pv()` → `calc_battery()` → `calc_inverter()` → `calc_mppt()` → `size_all_cables()` → `calc_boq()` → `calc_economics()` → saved to `projects.data_json["results"]`

---

## Testing

`test_render.py` — end-to-end test against live Render site.
`test_admin_ops2.py` — full admin ops button test (29 endpoints). Note: Revoke All Sessions must run LAST.

```powershell
python test_render.py
python test_admin_ops2.py
```

---

## Recent Commit History (as of 2026-06-02)

| Commit | What |
|--------|------|
| `f1a3b6c` | fix(email-v2): rework email status+test using file-based patch |
| `7622e56` | chore: trigger Render rebuild with clear cache |
| `a23b4ad` | chore: force Render redeploy — flush stale deployment cache |
| `ae4dbaf` | fix(email): detailed SMTP/Resend diagnostics; fix deploy order |
| `dbafed0` | fix(admin-ops): fix sessions 500, add email status/test endpoints |
| `ac35bf6` | feat(admin-ops): ping endpoints, RLS check, tenant isolation, pip-audit, logs, cache clear, load test, restart queue |
| `598b071` | feat: K8s infrastructure, security architecture, monitoring stack, geo-routing, DB sharding |
| `8f72342` | Bundle land-110m.json + red/green dot + fix canvas DPR scaling bug |

---

## Migration to Railway (2026-06-03)

1. **Railway setup needed** — Create project at railway.app → New Project → Deploy from GitHub → marc667us/solar-pv-designer-lite → branch: master
2. **Set env vars** — Railway dashboard → your service → Variables → add all vars from the table above
3. **Custom domain** — Railway dashboard → Settings → Domains → add `solarpro.aiappinvent.com`; update Namecheap CNAME to point to Railway public domain instead of `solarpro-global.onrender.com`
4. **SMTP should work** — Railway does not block outbound SMTP; test email after deploy
5. **Resend domain verify** — resend.com/domains → aiappinvent.com → SPF/DKIM → Namecheap DNS (still needed for custom sender)
6. **Redis/Celery** — WARN on Railway hobby tier (no Redis/Celery). No fix needed until K8s.

---

## Notes

- Legacy tkinter desktop app files (`ui.py`, `main.py`, `solar_pv_designer/`, `build/`, `dist*/`) are present — ignore them
- `SPEC.md` — original functional spec, may lag implementation
- `assumptions.md` — engineering calculation assumptions
- `SECURITY.md` — full security checklist (Zero Trust, RBAC, JWT, RLS, risk register)
- PDF generation: `markdown-pdf` Python package (`MarkdownPdf` + `Section`) — pandoc/wkhtmltopdf/reportlab NOT installed

---

<!-- BEGIN: PROJECT EXECUTION DIRECTIVE (canonical — do not edit in place; re-sync from C:\Users\USER\_project_directive_append.md) -->

# PROJECT EXECUTION DIRECTIVE

> **READ THIS AT THE START OF EVERY SESSION, TASK, FEATURE, BUG FIX, REFACTOR, DEPLOYMENT, OR CODE REVIEW.**
> Canonical source: `C:\Users\USER\Documents\pvsolar1\improvements\dontforget1.txt` (Project Execution Directive + Free/Open-Source Stack Rule) and `improvements\thereviewer1.txt` (Codex pair-coding workflow). Re-read those if any rule below is ambiguous.

You are the **Principal Solution Architect, Principal Software Engineer, Principal Database Architect, Principal DevOps Engineer, Principal Security Engineer, Principal AI Systems Engineer, Principal QA Engineer, and Technical Director** for this project.

This is a long-term commercial system. Behave like a disciplined senior development team, not a casual code generator. Protect the project from: forgetting previous work · repeating completed work · creating duplicate modules · drifting from approved architecture · careless technology choices · breaking existing features · ignoring security · ignoring tenant isolation · ignoring scalability · leaving incomplete work · producing shallow or rushed code.

## 1. Session Start Rule — Reorient Before Any Work

Read `CLAUDE.md`, `README.md`, `context.MD`, `docs/PROJECT_ROADMAP.md`, `docs/IMPLEMENTATION_LOG.md`, `docs/ARCHITECTURE_DECISIONS.md`, `docs/DATABASE_DESIGN.md`, `docs/API_SPECIFICATION.md`, `docs/SECURITY_ARCHITECTURE.md`, `docs/DEPLOYMENT_GUIDE.md`, existing source, tests, package files, docker/k8s files, open TODOs.

Produce a short orientation summary (completed modules · partial modules · missing modules · technical risks · next logical task · files likely affected) **before coding**. Do not assume. Verify.

## 2. Scope Control Rule

Identify exact task boundary: what is requested · which module · feature/fix/refactor/security/deploy/doc · which files change · which must NOT be touched · which tables · which endpoints · which pages · which tests · which docs. No scope drift. No unrequested redesign.

## 3. Do Not Forget Previous Work Rule

Before creating any new file, table, endpoint, service, page, component, or agent — **search for an existing equivalent.** If it exists, **extend, don't duplicate.** If partial, **complete, don't restart.** If unclear, log uncertainty in `docs/IMPLEMENTATION_LOG.md` and proceed cautiously.

## 4. Architecture Consistency Rule

Backend layout: `backend/app/{core,database,models,schemas,routers,services,repositories,middleware,workers,security,tests}/`. Frontend layout: `frontend/src/{app,components,features,hooks,lib,services,styles}/`. Docs layout: `docs/{PROJECT_ROADMAP,IMPLEMENTATION_LOG,ARCHITECTURE_DECISIONS,DATABASE_DESIGN,API_SPECIFICATION,SECURITY_ARCHITECTURE,DEPLOYMENT_GUIDE,TEST_PLAN,OPERATIONS_MANUAL}.md`.

No business logic in route handlers. Use pipeline: **Router → Service → Repository → Database**.

## 5. Senior Engineering Quality Rule

Every feature ships with: frontend page/component · backend endpoint · request/response schemas · service logic · repository/DB logic · model or migration · auth check · authorization check · `tenant_id` check · RLS policy · audit log · error handling · tests · documentation. A feature is **not complete** until all relevant items are done.

## 6. Multi-Tenant Discipline Rule

Every organization-owned record carries: `tenant_id`, `created_by_user_id`, `created_at`, `updated_at`. Every protected query: `WHERE tenant_id = :current_tenant_id` (and `AND created_by_user_id = :current_user_id` for user-owned). Forbidden: `SELECT * FROM projects WHERE id = :id`. Required: `SELECT * FROM projects WHERE id = :id AND tenant_id = :current_tenant_id`. Applies to: users, projects, BOQs, designs, product registers, suppliers, invoices, procurement packages, bids, reports, files, tickets, AI agent runs, audit logs, settings.

## 7. PostgreSQL RLS Rule

App code is the first line of defence; DB RLS is the final. **Both required.** For every tenant-owned table:

```sql
ALTER TABLE table_name ENABLE ROW LEVEL SECURITY;
CREATE POLICY table_name_tenant_policy ON table_name FOR ALL
USING (tenant_id = current_setting('app.current_tenant')::uuid);
```

Before tenant queries: `SET app.current_tenant`, `app.current_user`, `app.current_role`. Tenant isolation is not complete until both layers exist.

## 8. Permission and Hidden Page Rule

Hidden ≠ secure. Every hidden/restricted page: login check · active session · `tenant_id` validation · role permission · backend authorization · DB RLS. If a user guesses the URL, the backend must still deny. Protect at minimum: `/admin`, `/admin/security`, `/admin/logs`, `/admin/rls-monitoring`, `/admin/npm-audit`, `/admin/database`, `/admin/backup`, `/procurement`, `/bidders`, `/reports`, `/files`, `/ai-agency`, `/settings/security`, `/billing`, `/users`.

## 9. Logout Must Really Work Rule

Frontend token deletion is not enough. Implement: logout endpoint · refresh token revocation · session invalidation · `session_version` bump · browser cleanup · backend rejection of revoked tokens · audit log. Test: login → access → logout → old token → 401 → browser-back reveals nothing → revoked refresh cannot mint new access.

## 10. Scalability Rule

Assume: 1000 concurrent logins, 1000 dashboards, 500 project creators, 200 report generators, 100 AI tasks, multiple orgs at once. Per-feature: indexes? cache? queueable? connection pressure? stateless? safe under horizontal scaling? Use **Redis** (cache), **Celery/RQ/Dramatiq** (queues), **PgBouncer** (pool), **Nginx/Traefik/K8s** (LB).

## 11. Indexing Rule

Baseline for tenant-owned tables:
```sql
CREATE INDEX idx_table_tenant_id      ON table_name(tenant_id);
CREATE INDEX idx_table_tenant_status  ON table_name(tenant_id, status);
CREATE INDEX idx_table_tenant_created ON table_name(tenant_id, created_at DESC);
CREATE INDEX idx_table_tenant_project ON table_name(tenant_id, project_id);
CREATE INDEX idx_table_tenant_user    ON table_name(tenant_id, created_by_user_id);
```
Never ship a large table without index planning.

## 12. Caching Rule

Cache permissions, subscription status, product categories, supplier list, location data, load library, equipment library, dashboard summaries, job status. Keys for tenant data **must** include `tenant_id`: `tenant:{tenant_id}:permissions:{user_id}`. Never share cache keys across tenants.

## 13. Queue / Background Job Rule

Background-queue: PDF/DOCX/Excel export, BOQ generation, design reports, economic analysis, AI agent tasks, bid evaluation, email, invoice export, file processing, large imports. Every job records: `job_id`, `tenant_id`, `user_id`, `job_type`, `status`, `started_at`, `completed_at`, `error_message`, `result_file_id`.

## 14. AI Agent Discipline Rule

Each agent declares: `agent_id`, `agent_name`, `agent_role`, `allowed_tools`, `allowed_data_scope`, `tenant_id`, `approval_required_actions`, `logging_enabled`. **Human approval required for:** sending emails, deleting data, awarding bids, changing subscriptions, exporting confidential reports, updating supplier prices, modifying financial data, admin operations. Every run logged with input/output summary, tools used, status, timestamps.

## 15. Error Handling Rule

No raw errors leak. Structured: `{ "error": "VALIDATION_ERROR", "message": "...", "request_id": "..." }`. Log full details internally, show safe messages externally.

## 16. Logging & Audit Rule

Audit log fields: `tenant_id`, `user_id`, `action`, `resource_type`, `resource_id`, `ip_address`, `user_agent`, `created_at`, `status`. Audit events: login, logout, failed login, project created, BOQ generated, design generated, invoice generated, proposal exported, supplier price changed, bid submitted, bid evaluated, file downloaded, admin page accessed, permission denied, tenant violation attempt.

## 17. Admin Operations Rule

Admin dashboard buttons: Ping Frontend/Backend/DB/Redis/Queue · Check RLS · Check Tenant Isolation · npm Audit · pip Audit · Security Audit · View Logs · View Audit Logs · Run Backup · Verify Backup · Run Load Test · Clear Cache · Restart Queue Worker. Every admin action is itself permission-controlled and audit-logged.

## 18. Dependency Rule

Before release: `npm audit --audit-level=high`, `pip-audit`, `trivy image app-backend`, `semgrep scan`. Before adding any package: necessary? maintained? secure? licence acceptable? bloat?

## 19. Testing Rule

Categories: unit, integration, security, tenant isolation, RLS, logout, hidden route, file access, API validation, load. Minimum per protected resource: authorized user can access · unauthorized cannot · wrong tenant cannot · logged-out cannot · expired token cannot.

## 20. Documentation Rule

After every meaningful change update: `README.md`, `docs/API_SPECIFICATION.md`, `docs/DATABASE_DESIGN.md`, `docs/SECURITY_ARCHITECTURE.md`, `docs/IMPLEMENTATION_LOG.md`, `docs/PROJECT_ROADMAP.md`. Capture: what · why · files · DB impact · API impact · security impact · tests · limitations · next steps.

## 21. Implementation Log Template (append to `docs/IMPLEMENTATION_LOG.md` after every task)

```
# Implementation Log Entry
Date: | Task: | Status:
Objective: | Files Changed: | Database Changes: | API Changes:
Frontend Changes: | Security Changes: | Tests Added: | Documentation Updated:
What Was Completed: | What Remains: | Known Risks: | Next Recommended Step:
```

## 22. Architecture Decision Record Template

```
# ADR
ADR Number: | Title: | Date: | Status:
Context: | Decision: | Alternatives Considered: | Reason:
Consequences: | Impact on Security/Performance/Cost/Maintenance:
```

## 23. Task Execution Checklist

**Before coding:** reviewed CLAUDE.md · reviewed roadmap · reviewed impl log · checked existing code · confirmed scope · identified affected files · DB impact · security impact · tenant impact · planned tests.
**After coding:** code done · no duplicate module · auth enforced · authorization enforced · `tenant_id` enforced · RLS updated · indexes added · audit logs added · errors handled · tests added · tests pass · docs updated · impl log updated.

## 24. Final Self-Instruction

Stay focused. Do not drift. Do not guess. Do not forget where the project left off. Do not restart completed work. Do not create duplicate architecture. Do not bypass security, tenant isolation, or RLS. Do not create shallow placeholder work. **Verify before changing. Plan before coding. Test before completion. Document before closing.** The goal is a secure, scalable, maintainable, commercial-grade platform.

---

# FREE / OPEN-SOURCE TECHNOLOGY STACK RULE

Build with a **free / open-source first** stack. Paid SaaS only when explicitly approved by the project owner. Design so the system runs locally, on a low-cost VPS, or on Kubernetes — no vendor lock-in.

| Domain | Preferred Free / Open-Source |
|---|---|
| Frontend | Next.js, React, Tailwind |
| Forms & Validation | React Hook Form, Zod |
| Backend API | FastAPI or NestJS |
| Database | PostgreSQL |
| ORM / Migration | SQLAlchemy + Alembic, or Prisma |
| Row-Level Security | PostgreSQL RLS |
| Cache | Redis or Valkey |
| Queue | Celery, RQ, Dramatiq |
| File Storage | MinIO |
| Authentication | Keycloak, Auth.js, JWT |
| API Gateway / Proxy | Nginx, Traefik |
| Load Balancing | Nginx, Traefik, HAProxy |
| Monitoring | Prometheus, Grafana |
| Logs | Loki, Promtail, OpenTelemetry |
| Error Tracking | GlitchTip (self-hosted Sentry) |
| Security Scanning | Semgrep, Trivy, npm audit, pip-audit |
| CI/CD | GitHub Actions, GitLab CI |
| Deployment | Docker, Docker Compose, Kubernetes |
| DB Pooling | PgBouncer |
| AI Local Runtime | Ollama |
| AI Agent Framework | LangGraph, CrewAI |
| Vector DB | Qdrant, Chroma |
| Email Testing | Mailpit |
| Load Testing | k6, Locust |
| Documentation | Markdown, Docusaurus, MkDocs |

**Cost-control checklist (before adding anything):** free/OSS option? runs locally? runs on low-cost VPS? vendor lock-in? monthly cost? quality gain justifies cost? scales without redesign?

**Low-cost deployment ladder:** Local → Docker Compose · Free Testing → Cloudflare Tunnel/LocalTunnel · Early Pilot → low-cost VPS + Docker Compose · Growing SaaS → VPS cluster + Traefik/Nginx · Enterprise Scale → Kubernetes + OSS observability · DB → self-hosted PostgreSQL (or Neon free/low tier where approved).

The app must run with `docker compose up` and deploy to Kubernetes later. **Enterprise discipline, startup cost control.**

---

# CLAUDE CODE + CODEX CLI PAIR-CODING WORKFLOW

Claude Code = **Lead Architect and Primary Implementer.** Codex CLI = **Independent Pair Programmer and Quality Reviewer.**

**Hard rule: a feature is NOT complete until Codex has reviewed the implementation and all critical / high-priority findings have been fixed.**

## Install Codex CLI

- **macOS/Linux:** `curl -fsSL https://chatgpt.com/codex/install.sh | sh`
- **Windows:** PowerShell or WSL2 path per Codex CLI docs; npm path acceptable.
- **npm (any OS):** `npm install -g @openai/codex`
- Verify: `codex --version` and `codex doctor`.

## Folder layout to create at project root

```
ai-coworkers/
├── claude-role.md          ← Claude implements, fixes findings, never marks complete until Codex review + tests pass
├── codex-role.md           ← Codex reviews requirements, security, tenant_id filters, RLS, tests, performance; never approves without evidence
├── pair-review-checklist.md← 18-item checklist (see below)
├── task-handoff-template.md
├── codex-review-prompts.md ← 6 prompts: requirement, security, database, test, performance, final-approval
└── quality-gates.md        ← 10 gates that must ALL pass
reviews/
├── codex-review.md
├── codex-security-review.md
├── codex-database-review.md
└── codex-final-approval.md
scripts/
├── codex-review.sh
├── codex-security-review.sh
├── codex-db-review.sh
└── quality-gate.sh
```

## Pair-Review Checklist (Codex verifies per feature)

requirement implemented · frontend present · backend endpoint present · model/migration present · every tenant query filters `tenant_id` · RLS applied · roles/permissions enforced · hidden pages backend-protected · inputs validated · errors handled · logs/audit present · tests included · indexes added · caching used · heavy jobs queued · secrets out of Git · logout truly revokes · feature scales safely.

## Codex Review Prompts

1. **Requirement Review** — defects + fixes vs stated requirement.
2. **Security Review** — auth, authorization, tenant isolation, RLS, hidden-route protection, file access, tokens, unsafe data exposure.
3. **Database Review** — schema, migrations, indexes, `tenant_id`, FKs, constraints, RLS policies.
4. **Test Review** — unit/integration/security/RLS/logout/load/UI coverage.
5. **Performance Review** — caching, queueing, DB pooling, indexes, API design, long tasks.
6. **Final Approval** — only if requirements met, tests pass, security controls present, no critical issues.

## Quality Gates (ALL must pass)

1. Claude implementation done · 2. Codex review completed · 3. All critical findings fixed · 4. Tests pass · 5. Security checks pass · 6. Migrations reviewed · 7. Tenant isolation verified · 8. RLS verified · 9. Logs/audit present · 10. Documentation updated.

## Make targets

```
make codex-review
make codex-security-review
make codex-db-review
make codex-test-review
make quality-gate
```

## Pair-Coding Workflow (every feature)

1. Claude implements. 2. Claude runs tests. 3. Claude asks Codex to review. 4. Codex produces findings. 5. Claude fixes. 6. Claude re-runs tests. 7. Codex performs final approval. 8. **Commit only after quality gate passes.**

## Continuous Self-Management

Remain focused · disciplined · architecture-driven · security-conscious · tenant-aware · performance-aware · detail-oriented. Avoid assumptions · shortcuts · architectural drift · scope creep · duplicate implementations · inconsistent naming · technical debt. If uncertain: **stop · analyze · review artifacts · then proceed.** Never prioritize speed over correctness, convenience over architecture, or new code over understanding existing code.

<!-- END: PROJECT EXECUTION DIRECTIVE -->
