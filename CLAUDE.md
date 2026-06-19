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

## Marketplace / Procurement Center (added 2026-06-17→18)

Procurement module bolted into `web_app.py` as the user-acquisition magnet for solar. Anyone can browse pricing at `/marketplace`; signup unlocks RFQ / BOM / BOQ / Procurement Center.

| Namespace | Slice | What |
|---|---|---|
| `/marketplace`, `/marketplace/product/<id>` | 1 | Public catalog browse |
| `/supplier/register`, `/supplier/dashboard`, `/supplier/products[/add]` | 2 | Supplier self-service portal (role `supplier_admin`) |
| `/admin/marketplace`, `/admin/marketplace/pending` | 3 | Verification queue (audit log written to `logs/audit/audit.log` — no UI route) |
| `/rfqs/*` | 4 | RFQ workflow (10 routes) |
| `/boms/*` | 5 + 8 | BOM/BOQ builder; BOQ is nested at `/boms/<id>/boq` with Excel/PDF export at `/boms/<id>/boq.xlsx` and `/boms/<id>/boq.pdf` |
| `engine/agents/marketplace/_llm.py` | 6 | Zero-cost LLM tie-break classifier (`:free` allowlist required) |
| `/staff/*`, `/me/*` | 7 | Procurement-specialist role + CRUD + dashboards |
| `/procurement-center`, `/procurement-center/add`, `/price-sheets/*` | 9 | Checkbox-grid product picker + Basic Price Sheet (qty=1; 10 cols: item#/desc/qty/unit/price/supplier/brand/phone/email/address) |

**Where the routes live:**
- 11 × `new_marketplace_*_routes.py` (Slice 1-9 + Postgres init + Procurement Center)
- 14 × `patch_*.py` to splice them into `web_app.py` (byte-level, CRLF-aware)
- 10 × `test_marketplace_*.py` (104+ tests)
- 26 × `templates/` for marketplace/supplier/admin/rfq/bom/boq/me/procurement-center

**Currency model:** ISO codes only (USD/EUR/GBP/GHS/NGN/KES/ZAR), never symbols. Static rates in `_CURRENCY_RATES_FROM_USD` inside `new_marketplace_procurement_center_routes.py`.

**Zero-cost LLM guardrail:** `_is_free_openrouter_model()` rejects any model that doesn't end in `:free` or appear in the allowlist. Chain: OpenRouter free Nemotron → Ollama → None. NEVER paid Anthropic.

**Email injection defence:** `_safe_email_text()` html.escape body; `_safe_email_subject()` strips CR/LF. Used for RFQ notify, procurement-specialist invite, verification approval.

**Postgres parity:** `_ensure_marketplace_schema_postgres()` runs on cold start, translates `INTEGER PRIMARY KEY AUTOINCREMENT` → `SERIAL`, uses `ADD COLUMN IF NOT EXISTS` idempotently, backfills `category_id`. Case-insensitive search via `LOWER(ec.name) LIKE ?` since Postgres LIKE is case-sensitive but SQLite isn't.

**Soft-launch artefacts (commit `e7c2d6a`):** `scripts/send_marketplace_launch.py` (Brevo, dry-run default, 33 invitees) + `scripts/build_marketplace_flyer.py` (Pillow 1080×1080 + 1200×628) + 4-channel copy + `patch_solar_email_marketplace_footer.py` (PS injected on all transactional emails).

**Last shipped:** Slice 9 = `dd22a92` (Procurement Center + Basic Price Sheet). Slice 9 has NOT been through a Codex round-1 review yet — earlier slices had 8 rounds with 7 HIGH-SEV fixes (state-mutating GET, unverified product leak, paid LLM model, HTML/SMTP injection, zero-target RFQ, missing supplier.address column, supplier-schema not firing in procurement routes).

### Marketplace catalogue rebuild — 2026-06-19 (`8261289`..`86130a5` live; tip `a1732a4`)

Drove `pvsolar1/price master/price prompt.txt` (Electrical Costing, BOM, BOQ & Supplier Marketplace brief).

**21-category taxonomy in `_MARKETPLACE_CATEGORIES`** (was 20; added `power_system` for RMU/Generators/UPS/Switchgear/...). Three central registries co-located with it:

- `_MARKETPLACE_SUBCATEGORIES`   — code → list of subcategory display names (~140 entries across 21 categories). Drives the supplier upload form's subcategory dropdown + the public `/marketplace?cat=&sub=` drilldown chips.
- `_MARKETPLACE_DEFAULT_UNIT`    — code → UoM (m / Roll / No.). Auto-fills the supplier form's unit field on category change.
- `_MARKETPLACE_SPEC_FIELDS`     — code → list of required technical spec fields. Shows as "Required: …" hint on the supplier form AND drives the BOQ Compliance Review.

**Seed discipline:** category seed is `INSERT OR IGNORE` (SQLite) / `ON CONFLICT (code) DO NOTHING` (Postgres) so adding a new entry to `_MARKETPLACE_CATEGORIES` lands in existing DBs. Sample seed expanded 27→77 rows; new categories get topped up via `_backfill_marketplace_samples_for_empty_categories` (SQLite) and the Postgres twin. Both helpers use a `_FilteredConn` proxy that filters by `cat_id` (param tuple index 9) so existing populated categories are never disturbed.

**BOQ Compliance Review** at `/boms/<id>/boq` — `_boq_compliance_check(items, lines)` returns severity-ranked findings: missing spec fields (substring-match against `ec.spec`), missing unit price (high), no supplier (low), wrong unit vs category default (low), duplicate item names (medium). No-print red panel on screen, hidden on the printed client deliverable.

**Public subcategory drilldown:** `/marketplace?cat=<id>&sub=<name>` filters via `LOWER(ec.subcategory)=?`; subcategory chips render below the category chip row.

**Category-grouped grid:** both `/marketplace` and `/procurement-center` render `products_by_category` (list of {category, products}) ordered by display_order; each category gets a gold uppercase section header (icon + name + count badge) above its card / checkbox grid. Uncategorised fallback so nothing is silently dropped.

**Product Catalogue rename** (owner directive): 10 user-visible "Equipment Catalog"/"Add Equipment" strings → "Product Catalogue"/"Add Product" across nav menu, `/procurement/catalog`, `/procurement`, `/upgrade`, `price_sheet_view.html`, web_app.py admin help. British "Catalogue" spelling. `equipment_catalog` table identifier untouched.

**Three Postgres-specific live fixes** uncovered by the smoke test:

1. **`db_adapter.py` lastrowid proxy.** psycopg2 does NOT populate `cursor.lastrowid` for plain INSERTs. Nine `cur = c.execute("INSERT …"); pid = cur.lastrowid` callsites silently redirected to `/boms/None` → 404. New `_PgCursorWrap` proxy class wraps the psycopg2 cursor and computes `lastrowid` lazily via `SELECT lastval()` on first access (cached). All cursor methods (fetchone/fetchall/rowcount/iter/...) delegate to the underlying cursor.
2. **`db_adapter.py` literal `%` escape.** SolarPro's marketplace SQL has `NOT LIKE 'BulkProd-%'` etc. psycopg2 read those `%` chars as format-string specs whenever params were supplied → `IndexError: list index out of range` on every `/marketplace?cat=<n>`. Fixed by doubling `%`→`%%` BEFORE substituting `?`→`%s`.
3. **Postgres init missing `marketplace_boms.currency`.** Previous session added the column via SQLite ALTER in `_ensure_bom_tables` but `_ensure_bom_tables` short-circuits to `_ensure_marketplace_schema_postgres` BEFORE the ALTER runs. Added the idempotent `ALTER TABLE marketplace_boms ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT 'GHS'` to the Postgres init list.

**Re-runnable live smoke test** at `tmp/live_smoke_test_2026-06-19.py` (25 checks across 4 sections: anonymous public, logged-in nav, marketplace→BOM/RFQ/procurement flows, taxonomy verification). Update the `startswith` commit-hash check before re-running.

**Render auto-deploy gotcha:** Render does NOT auto-deploy on `git push` for this repo. Use `gh workflow run "Force Render Deploy"` after each push. The "Deploy to Railway" workflows on every push are for the legacy Railway host (decommissioned) — they pass but don't touch Render.

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

---


---

<!-- BEGIN: AGENTIC ADK EXTENSION (canonical — do not edit in place; re-sync from C:\Users\USER\_agentic_adk_append.md) -->

# AGENTIC DEVELOPMENT EXTENSION — Google ADK + Claude Code + Governance Agents

> **READ ALONGSIDE THE PROJECT EXECUTION DIRECTIVE.** This extension adds the agentic-architecture layer that every app under this account must follow. It does not replace the directive — it extends it.
> Canonical sources:
> - `C:\Users\USER\Documents\agentic proper2\agenticadk1.txt` — master Enterprise AI Agent Factory prompt (architecture spec + 24-section blueprint + Section 26 governance agents)
> - `C:\Users\USER\_agentic_adk_append.md` — this template (CLAUDE.md content)
> - `C:\Users\USER\_agentic_adk_context_append.md` — companion context.MD append
> - `C:\Users\USER\_agentic_adk_mcp.md` — companion MCP.md per-app file

## 0. Why this exists

Every app in this account — past, present, and future — is part of a single agentic platform. The split is:

- **Claude Code** is the **Software Engineering Agent**. It writes code, fixes bugs, creates APIs, databases, Dockerfiles, CI/CD pipelines, tests, and deployment scripts. It does NOT orchestrate business workflows.
- **Google ADK (Agent Development Kit)** is the **Agent Operating System AND the agent framework**. It coordinates business agents (executive, engineering, construction, procurement, finance, healthcare, legal, research, sales, support, technology) across workflows, tools, memory, and execution. **It is also the only framework used to design and implement any agent in any app under this account** — see §0.1 below.
- **Codex CLI + Supervisor** is the **Pair-Coding Review Lane**. It reviews Claude Code's diffs; the Supervisor adjudicates. See the existing pair-coding skeleton at `ai-coworkers/`, `reviews/`, `scripts/`.
- **Governance Agents (Work Reviewer, Development Supervisor, Work Scheduler)** are the **Quality + Planning Lane** running inside ADK. They run for every project deliverable, not just code.

> A feature is NOT done until: code is written → Codex reviews → Supervisor signs off → Work Reviewer Agent approves → Work Scheduler Agent marks the task `approved`. All four gates are mandatory.

## 0.1 HARD RULE — Google ADK Is the Only Agent Framework

**Every agent — in every app, in every department, current and future — must be designed and implemented in Google ADK.** No exceptions without explicit owner approval logged in `docs/IMPLEMENTATION_LOG.md` and an ADR in `docs/ARCHITECTURE_DECISIONS.md`.

This applies to:

- Agent class definitions (always subclass / compose ADK primitives — `Agent`, `LlmAgent`, `SequentialAgent`, `ParallelAgent`, `LoopAgent`, etc.)
- Tool definitions (always ADK `Tool` / `FunctionTool` / `AgentTool` — never bare function dispatchers or competing tool-call schemas).
- Memory and session state (always ADK session services + the memory layer in §6).
- Agent-to-agent handoffs (always ADK transfer / sub-agent invocation — never direct LLM-to-LLM hand-rolled loops).
- Orchestration (always ADK workflows — never custom while-loops, custom orchestrators, or shell-driven agent chains).

**Forbidden without an approved ADR:**

- LangChain agents, LangGraph, AutoGen, CrewAI, Smolagents, Letta/MemGPT, OpenAI Assistants API agents, Microsoft Semantic Kernel — or any other competing agent framework.
- Hand-rolled "while-LLM-says-not-done" loops.
- Direct provider SDK calls (`anthropic.messages.create`, `openai.chat.completions.create`, `vertexai.GenerativeModel.generate_content`) **inside an agent's reasoning loop**. Direct SDK calls are fine for one-shot utility prompts (e.g., a deterministic summariser inside a tool); they are NOT fine as a substitute for an agent.
- Storing agent prompts, tools, or graph topology outside of ADK definitions (e.g. as YAML interpreted by a custom runner).

**Why this matters:**

- A single framework means observability, evals, memory, and governance schemas all converge — the Work Reviewer / Development Supervisor / Work Scheduler agents can introspect any agent's run because every agent shares the same lifecycle.
- ADK is the bridge to Vertex AI for production hosting; non-ADK agents cannot ride that deployment path.
- The four-gate quality bar depends on uniform run records; bespoke agents break those records.

**How Claude Code applies this rule when implementing:**

1. Before writing any agent code, confirm the ADK class to subclass / compose. If unsure, read `agenticadk1.txt` §2–§13 for the canonical agent role list.
2. Tools go in `app/tools/<department>/` as ADK tools — even if the underlying logic is a pure function, wrap it in `FunctionTool` (or equivalent ADK primitive).
3. Multi-agent flows go in `app/workflows/` using ADK `SequentialAgent` / `ParallelAgent` / `LoopAgent` — never a custom Python orchestrator.
4. If the user asks for "just a quick agent", default to a minimal `LlmAgent` with one tool, NOT a script with a `while` loop around `client.messages.create()`.
5. If a request seems to require a non-ADK framework, **stop** and surface the conflict — propose an ADR rather than silently introducing the competing library.

## 0.2 HARD RULE — Always Start From Orchestration; Branch Into Conductors When Needed

**Every agent system in every app MUST start from an orchestration agent at the top.** No request enters the platform by going directly to a specialist agent or a tool. The shape is:

```
                ┌───────────────────────────────────┐
   User /  ───▶ │  ROOT ORCHESTRATOR (ADK)          │  ← always present
   API          │  e.g. ChiefExecutiveOrchestrator  │     (LlmAgent / SequentialAgent)
                └────────────┬──────────────────────┘
                             │ classifies request, routes
                  ┌──────────┴──────────┐
                  │                     │
                  ▼                     ▼
            CONDUCTOR A             CONDUCTOR B          ← branch here only WHEN
        (sub-orchestrator       (sub-orchestrator           the sub-workflow needs
         e.g. ConstructionDept   e.g. FinanceDept           its own coordination
         Conductor)               Conductor)                of multiple specialists
                  │                     │
        ┌─────────┼─────────┐     ┌─────┴────┐
        ▼         ▼         ▼     ▼          ▼
    Specialist Specialist Tool  Specialist  Tool         ← leaves
       Agent     Agent    call    Agent     call
```

**Definitions:**

- **Root Orchestrator** — the single ADK entry agent for the app. It owns request classification, top-level routing, and the §3 control sequence (Work Scheduler → assignments → Work Reviewer → executive report). It is always an ADK agent — typically `LlmAgent` with sub-agents, or `SequentialAgent` wrapping the §3 pipeline.
- **Conductor** — a sub-orchestrator agent. Use one when a branch needs to coordinate **more than one specialist agent** OR **a non-trivial workflow** (sequencing, retries, parallel fan-out, conditional routing). A conductor IS an ADK orchestrator agent (`SequentialAgent`, `ParallelAgent`, `LoopAgent`, or an `LlmAgent` with its own `sub_agents`) — it is NOT a specialist with tool calls.
- **Specialist** — a leaf agent (one department role: Electrical Design Agent, BOQ Agent, Lead Generation Agent, etc.) that does the actual work via its tools.

**Branching rules — when to introduce a conductor vs. keep it flat:**

| Situation | Pattern |
|---|---|
| Single specialist needed for the request | Root Orchestrator → Specialist (no conductor) |
| Two or three specialists in strict sequence | Root Orchestrator → `SequentialAgent` Conductor → Specialists |
| Several specialists running in parallel | Root Orchestrator → `ParallelAgent` Conductor → Specialists |
| Iterative refinement (e.g. design → review → revise) | Root Orchestrator → `LoopAgent` Conductor → Specialists |
| Whole department's work for this request | Root Orchestrator → Department Conductor (`LlmAgent` w/ sub-agents) → Specialists |
| Cross-department workflow (engineering + finance + procurement) | Root Orchestrator → one Conductor per department → Specialists; Root composes their outputs |

**Forbidden shapes:**

- Calling a specialist agent directly from an API handler without going through the Root Orchestrator.
- A Root Orchestrator that contains all 50+ specialists as direct sub-agents — flatten this into department conductors.
- A "conductor" that is actually a tool function dispatching to other tools — that is not a conductor, that is a misnamed helper. Conductors are ADK agents with sub-agents.
- Mixing orchestration logic into a specialist (a specialist may NOT spawn or hand off to other agents — only conductors do that).

**Mandatory files when this rule is implemented in an app:**

```
app/agents/
├── orchestrators/
│   └── root_orchestrator.py          ← REQUIRED — the single entry agent
├── conductors/
│   ├── executive_conductor.py        ← coordinates Chief* agents + governance
│   ├── technology_conductor.py       ← coordinates Dev Supervisor + Claude Code + ...
│   ├── engineering_conductor.py      ← coordinates engineering specialists
│   ├── construction_conductor.py
│   ├── procurement_conductor.py
│   ├── finance_conductor.py
│   ├── healthcare_conductor.py
│   ├── legal_conductor.py
│   ├── research_conductor.py
│   ├── sales_conductor.py
│   └── support_conductor.py
└── {executive,technology,engineering,...}/   ← specialists live here, NOT in conductors/
```

Department conductors are stubbed (just a `SequentialAgent` with no sub-agents yet) until that department's first specialist exists. Stubs are required so the orchestration topology is always visible.

**The §3 control sequence runs INSIDE the Root Orchestrator.** Concretely:

1. Root Orchestrator receives the request and asks the Chief Executive Agent (a sub-agent) to classify.
2. Root Orchestrator hands the schedule task to the Work Scheduler Agent (sub-agent).
3. Root Orchestrator routes scheduled tasks to the relevant Conductor(s).
4. Each Conductor coordinates its specialists and returns the department's output.
5. Root Orchestrator hands collected outputs to the Work Reviewer Agent.
6. Root Orchestrator returns the final report.

**How Claude Code applies this rule when implementing:**

1. If the app has no `app/agents/orchestrators/root_orchestrator.py`, create it as the first agent file, even before any specialist. Wire `/api/agents/execute` and `/api/demo/run` through it.
2. Never add an API route that calls a specialist or tool directly. The route calls the Root Orchestrator; the Root Orchestrator decides.
3. When asked for a multi-step workflow, the first design question is "which conductor owns this?" — not "which specialist runs it?"
4. If a conductor would have a single specialist underneath it, do NOT create the conductor — call the specialist from the Root Orchestrator directly. Conductors exist to coordinate ≥2 agents or non-trivial control flow.
5. Document the orchestrator/conductor tree in `docs/ARCHITECTURE_DECISIONS.md` whenever a new conductor is added.

## 0.3 HARD RULE — Agents and Code Must Be Reusable Across Apps

**Every agent, conductor, tool, schema, and utility in every app MUST be importable from another app's codebase, unchanged.** The factory only works if a Solar Design Agent built for `solar-pv-designer-lite` can be imported and used by `pvsolar1` or `ai-app-invent-sales-platform` without copying source. No exceptions.

**Concrete requirements:**

1. **Each app is a pip-installable Python package.** Every app root has:
   - `pyproject.toml` declaring `name`, `version`, and a `packages = ["app"]` (or `setuptools.find_packages`) so `pip install -e /path/to/app` makes everything under `app/` importable.
   - A top-level `app/__init__.py` and an `__init__.py` in every subpackage (`agents/`, `agents/executive/`, `agents/conductors/`, `tools/`, `schemas/`, `workflows/`, `memory/`, ...).
   - A `py.typed` marker for type-checker support.

2. **Public API is explicit.** Each package's `__init__.py` re-exports the agents/tools/schemas other apps may consume:
   ```python
   # app/agents/engineering/__init__.py
   from .solar_design_agent import SolarDesignAgent
   from .electrical_design_agent import ElectricalDesignAgent
   __all__ = ["SolarDesignAgent", "ElectricalDesignAgent"]
   ```
   If it isn't in `__all__`, it is not part of the public contract. Other apps should not import it.

3. **No app-local hardcoded paths inside agent/tool/schema code.** All paths come from config (`pydantic-settings`, `os.getenv`, or a `Settings` object injected at construction). Anything that reads `C:\Users\USER\...` or this-app-only relative paths inside business logic is a defect. Hardcoded paths belong in `app/main.py` or the deployment layer only.

4. **Dependency injection over globals.** Agents and tools accept their dependencies — DB session factory, LLM client, MCP client, settings — via constructor or factory function. No module-level singletons that another app would have to monkey-patch. ADK already encourages this pattern; follow it.

5. **No business logic in route handlers.** (Restates Directive §4 — Router → Service → Repository → DB.) The Service and Repository layers must be the importable units; the Router is the only piece that is allowed to be app-specific.

6. **Cross-app installation patterns:**
   - **Direct pip install** (development):
     `pip install -e "C:/Users/USER/Desktop/solar-pv-designer-lite"`
     then `from app.agents.engineering import SolarDesignAgent`.
   - **MCP mesh** (production / cross-runtime): the producing app exposes the agent's tool surface as an MCP server (see MCP.md §5.2); the consuming app declares it in MCP.md §5.1 and calls it via the MCP client. Use this when the consumer is in another language or another runtime.
   - **Wheel / private index** (releases): when an app reaches a stable version, publish a wheel to a private index (GitHub Packages, internal PyPI) so other apps can pin a version rather than `-e` to a working tree.

7. **Stable import paths.** Once an agent or tool is published under `app.agents.<dept>.<name>`, that import path is a contract. Rename only with a deprecation alias for at least one minor version:
   ```python
   # app/agents/engineering/__init__.py
   from .pv_design_agent import PvDesignAgent
   SolarDesignAgent = PvDesignAgent  # deprecated alias, remove in v2
   ```

8. **No circular dependencies between departments.** A Sales agent may NOT import an Engineering specialist directly to do calculations — it asks the Root Orchestrator to route to Engineering, OR it calls the Engineering app's MCP surface. Department-to-department coupling at the import layer breaks reusability.

9. **Tests travel with the code.** When another app installs this package and runs its own test suite, the imported package's invariants should still hold. That means tests live in `tests/` at app root AND every public agent/tool ships with at least one example test that can be re-run by consumers.

10. **Schemas are the contract surface.** `app/schemas/` defines Pydantic models used at every public boundary. Other apps import schemas — they do NOT inspect agent internals. If the schemas change shape, that is a breaking change requiring a version bump.

**Forbidden:**

- Copy-pasting an agent from one app into another. If you find yourself doing this, stop, install the source app as a package instead, and add the missing export to its `__all__`.
- `sys.path.append("../other-app")` hacks. Use `pip install -e` or the MCP mesh.
- App-local `from .config import THIS_APP_ONLY_FLAG` reads inside an agent. Configuration is injected.
- Database models reaching across apps. If two apps need the same table, the table belongs in a shared package, not duplicated.

**Mandatory files for the reusability contract:**

```
<app-root>/
├── pyproject.toml             ← REQUIRED — name, version, packages
├── app/
│   ├── __init__.py            ← REQUIRED — re-exports the public API
│   ├── py.typed               ← REQUIRED — empty marker file
│   ├── agents/__init__.py     ← lists the top-level orchestrator + conductors
│   ├── agents/<dept>/__init__.py   ← lists that department's agents
│   ├── tools/__init__.py
│   ├── tools/<area>/__init__.py
│   ├── schemas/__init__.py    ← lists the public schemas
│   └── workflows/__init__.py
└── docs/REUSABILITY.md        ← REQUIRED — lists what is publicly exported
                                  and which other apps currently consume it
```

**How Claude Code applies this rule when implementing:**

1. Before creating a new agent or tool, check whether an equivalent already exists in this app OR in any sibling app (`C:\Users\USER\Documents\*` and `C:\Users\USER\Desktop\*`). If it does, **install the sibling app as a package and import from it**. Do not duplicate. (Restates and tightens Directive §3.)
2. When adding a new agent/tool, place it under the correct package path AND add it to the parent package's `__init__.py` `__all__`. An agent that isn't exported is not finished.
3. When `pyproject.toml` is missing, scaffold a minimal one before any other code: `[project] name="<app-slug>"`, `version="0.1.0"`, `[tool.setuptools.packages.find] where=["."]`.
4. If a new feature needs a value that today is hardcoded in this app, move it to `app/core/config.py` (or equivalent `Settings` class) and inject it. Do not propagate the hardcoding into a new module.
5. Update `docs/REUSABILITY.md` whenever the public `__all__` of any package changes, listing the new export, its schema, and any consumer app that will need updating.

## 1. The Platform Hierarchy Every App Inherits

Even when an app only builds part of this hierarchy, the structure is the canonical mental model. Departments live under `app/agents/`. Tools live under `app/tools/`. Workflows live under `app/workflows/`.

```
Enterprise Agent Hierarchy
│
├── Executive Department          (app/agents/executive/)
│   ├── Chief Executive Agent
│   ├── Chief Operating Agent
│   ├── Chief Financial Agent
│   ├── Chief Technology Agent
│   ├── Chief Engineering Agent
│   ├── Chief Construction Agent
│   ├── Chief Procurement Agent
│   ├── Chief Legal Agent
│   ├── Chief Research Agent
│   ├── Chief Sales Agent
│   ├── Chief Support Agent
│   ├── Work Reviewer Agent       ← GOVERNANCE
│   └── Work Scheduler Agent      ← GOVERNANCE
│
├── Technology Department         (app/agents/technology/)
│   ├── Chief Technology Agent
│   ├── Development Supervisor Agent  ← GOVERNANCE
│   ├── Claude Code Agent             ← THIS IS ME
│   ├── Codex Agent
│   ├── Software Architect Agent
│   ├── DevOps Agent
│   ├── Security Agent
│   ├── Testing Agent
│   ├── Deployment Agent
│   ├── API Agent
│   ├── Database Agent
│   └── Monitoring Agent
│
├── Engineering Department        (app/agents/engineering/)
├── Construction Department       (app/agents/construction/)
├── Procurement Department        (app/agents/procurement/)
├── Finance Department            (app/agents/finance/)
├── Healthcare Department         (app/agents/healthcare/)
├── Legal Department              (app/agents/legal/)
├── Research Department           (app/agents/research/)
├── Sales Department              (app/agents/sales/)
└── Support Department            (app/agents/support/)
```

Specialist agents and tools per department are enumerated in `agenticadk1.txt` sections 5–13. Implement only the agents the current app actually needs — but **always create the directory** with an `__init__.py` so the hierarchy is recognisable.

## 2. Governance Agents — Mandatory in Every App

These three agents are non-skippable, no matter how small the app. They are the project's quality gates inside the ADK layer.

### 2.1 Work Reviewer Agent (`app/agents/executive/work_reviewer_agent.py`)

**Role:** Review every agent's output before it leaves the platform.

**Reviews:** engineering calculations · BOQs · project plans · proposals · reports · code outputs · risk registers · schedules · client-facing documents.

**Checks:** technical correctness · completeness · formatting · compliance with project requirements · calculation logic · document quality · client-readiness.

**Returns (schema: `app/schemas/review_schema.py`):**

```python
class WorkReview(BaseModel):
    review_status: Literal["approved", "corrections_required", "rejected"]
    quality_score: int  # 0–100
    missing_items: list[str]
    technical_errors: list[str]
    compliance_issues: list[str]
    correction_instructions: list[str]
    approval_comment: str | None
```

**Output statuses (every reviewable artifact carries one):**
`draft` → `under_review` → `corrections_required` → `approved` → `rejected`.

### 2.2 Development Supervisor Agent (`app/agents/technology/development_supervisor_agent.py`)

**Role:** Supervise all software-engineering tasks executed by Claude Code Agent, Codex Agent, DevOps Agent, Testing Agent, Security Agent, and Deployment Agent.

**Responsibilities:** break dev work into tasks · assign coding tasks to Claude Code · assign testing tasks to Testing Agent · assign security review to Security Agent · assign deployment tasks to DevOps Agent · review PR-style summaries · track development progress · enforce coding standards · keep architecture consistent · keep documentation up to date · escalate blockers to Chief Technology Agent.

**Returns (schema: `app/schemas/development_supervision_schema.py`):**

```python
class DevelopmentSupervisionReport(BaseModel):
    development_tasks: list[DevTask]
    assigned_coding_agent: str
    architecture_notes: list[str]
    testing_requirements: list[str]
    security_requirements: list[str]
    deployment_requirements: list[str]
    blocked_items: list[str]
    next_actions: list[str]
```

### 2.3 Work Scheduler Agent (`app/agents/executive/work_scheduler_agent.py`)

**Role:** Convert project goals into work breakdowns, schedules, milestones, and deadlines.

**Responsibilities:** create WBS · build task dependencies · produce Gantt-style schedules · set milestones · assign responsible agents · track task status · detect delays · re-plan delayed activities · emit weekly + daily work plans · emit progress summaries.

**Returns (schema: `app/schemas/schedule_schema.py`):**

```python
class WorkSchedule(BaseModel):
    work_breakdown_structure: list[WBSNode]
    milestones: list[Milestone]
    task_dependencies: list[Dependency]
    responsible_agents: dict[str, str]   # task_id → agent_name
    planned_start_dates: dict[str, date]
    planned_finish_dates: dict[str, date]
    critical_tasks: list[str]
    progress_status: dict[str, TaskStatus]
```

**Task statuses (every scheduled task carries one):**
`not_started` → `assigned` → `in_progress` → `blocked` → `under_review` → `completed` → `approved`.

## 3. The Mandatory Control Sequence

Every project request — no matter how small — flows through this sequence. Short-circuit it only with explicit owner approval logged in `docs/IMPLEMENTATION_LOG.md`.

1. **User submits project request** → API or chat or admin dashboard.
2. **Chief Executive Agent classifies the project** → maps to one or more departments.
3. **Work Scheduler Agent** creates WBS + schedule + milestones + dependencies.
4. **Chief Operating Agent** assigns departments to schedule entries.
5. **Specialist agents** execute their work (engineering, construction, finance, etc.).
6. **Development Supervisor Agent** supervises any software-related work in parallel.
7. **Work Reviewer Agent** reviews every agent output against the schemas in §2.
8. **Rejected work** routes back to the responsible agent with `correction_instructions`.
9. **Work Reviewer Agent** approves the final corrected output.
10. **Chief Executive Agent** issues the final executive report to the user.

## 4. Required Files Per App (when the agentic layer is built)

Implement these as the app grows. Stub the file with a docstring + `pass` until the agent is actually wired — but the path must exist so the hierarchy is discoverable.

```
app/
├── agents/
│   ├── executive/
│   │   ├── chief_executive_agent.py
│   │   ├── chief_operating_agent.py
│   │   ├── work_reviewer_agent.py          ← MANDATORY
│   │   └── work_scheduler_agent.py         ← MANDATORY
│   ├── technology/
│   │   ├── chief_technology_agent.py
│   │   ├── development_supervisor_agent.py ← MANDATORY
│   │   ├── claude_code_agent.py
│   │   ├── codex_agent.py
│   │   ├── software_architect_agent.py
│   │   ├── devops_agent.py
│   │   ├── security_agent.py
│   │   ├── testing_agent.py
│   │   ├── deployment_agent.py
│   │   ├── api_agent.py
│   │   ├── database_agent.py
│   │   └── monitoring_agent.py
│   └── {engineering,construction,procurement,finance,healthcare,legal,research,sales,support}/
├── tools/
│   ├── governance/
│   │   ├── review_tool.py
│   │   └── quality_check_tool.py
│   ├── scheduling/
│   │   ├── work_breakdown_tool.py
│   │   ├── gantt_tool.py
│   │   └── dependency_tool.py
│   └── technology/
│       └── development_task_tool.py
├── schemas/
│   ├── review_schema.py
│   ├── schedule_schema.py
│   └── development_supervision_schema.py
├── workflows/
│   └── governance_pipeline.py     ← runs the §3 control sequence
└── memory/
    ├── session_memory.py          ← short-term
    ├── project_memory.py          ← long-term
    ├── organization_memory.py
    ├── user_memory.py
    └── vector_memory.py           ← Qdrant or ChromaDB
```

## 5. Required APIs (FastAPI)

Even apps that don't expose every endpoint to end users should register these for ADK orchestration:

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/agents/execute` | Run an agent by name with a task payload |
| POST | `/api/projects` | Create a project record |
| POST | `/api/tasks` | Create a task (assigned by Work Scheduler) |
| POST | `/api/documents/upload` | Upload to the Document Intelligence layer |
| POST | `/api/workflows/execute` | Execute a named workflow |
| POST | `/api/reports` | Generate a report |
| POST | `/api/review/work` | Submit work to the Work Reviewer Agent |
| POST | `/api/schedule/project` | Submit a project to the Work Scheduler Agent |
| POST | `/api/technology/supervise-development` | Submit dev work to the Development Supervisor Agent |
| GET | `/api/dashboard/metrics` | Admin dashboard counters |

All endpoints enforce `tenant_id`, RBAC, and audit logging per the Project Execution Directive §6–§9.

## 6. Memory & Knowledge Layer

| Layer | Store | Used for |
|---|---|---|
| Short-term session memory | Redis | Conversation context within a single agent run |
| Long-term project memory | PostgreSQL | Project history, decisions, deliverables |
| Organization memory | PostgreSQL | Tenant-wide policies, standards, suppliers |
| User memory | PostgreSQL | Per-user preferences and history |
| Vector memory | Qdrant or ChromaDB | Semantic search over documents + past outputs |

PostgreSQL is the structured-data baseline (see Directive §6, §7, §11 for tenant + RLS + indexing rules). All four governance schemas above persist to PostgreSQL.

## 7. Multi-Tenant Discipline (extends Directive §6)

Every governance-related table inherits the same tenant discipline as business tables:

- `work_reviews`, `work_schedules`, `development_supervisions`, `agent_runs`, `tool_invocations`, `workflow_executions`, `audit_logs` — all carry `tenant_id`, `organization_id`, `created_by`, `created_at`, `updated_at`.
- All queries filter by `tenant_id`.
- RLS policies on every governance table.

## 8. Security Requirements (extends Directive §17)

For the agentic layer specifically:

- **Agent execution authorization:** verify the calling user has the role required to invoke that agent.
- **Tool sandboxing:** tools that touch the filesystem or shell must validate inputs and run inside the project's allowlist.
- **Prompt-injection defence:** strip / quarantine user-supplied content that re-instructs an agent ("ignore prior instructions", role-spoofing, etc.).
- **Secrets:** never hard-code API keys for ADK / Vertex AI / Claude API / Codex / Qdrant — read from env, document in `.env.example`.
- **Audit:** every agent run logs `(tenant_id, user_id, agent_name, input_hash, output_hash, started_at, finished_at, status)`.

## 9. Deployment

The ADK runtime ships as part of the app's container. Reference deploy targets (in order of preference for low cost): Render free tier → Railway → VPS → Google Cloud Run (Vertex AI region) → Kubernetes. Vertex AI is the canonical home for ADK in production, but starter scaffolds may run ADK locally with the Python SDK only.

`Dockerfile`, `docker-compose.yml`, `.env.example`, `requirements.txt` (or `pyproject.toml`), GitHub Actions workflow, and `README.md` are mandatory per Directive §19.

## 10. Testing

Add these test groups in `tests/`:

- `test_agent_initialization.py` — every agent constructs cleanly.
- `test_tool_execution.py` — every tool runs with sample inputs.
- `test_governance_flow.py` — Work Scheduler → Specialist → Development Supervisor → Work Reviewer → approved.
- `test_review_statuses.py` — all five review statuses transition correctly.
- `test_task_statuses.py` — all seven task statuses transition correctly.
- `test_tenant_isolation.py` — cross-tenant access denied at app + DB layer.
- `test_api_endpoints.py` — every endpoint from §5.

## 11. How Claude Code Should Behave Inside This Hierarchy

When working in any app under this account, Claude Code is acting **as the Claude Code Agent inside the Technology Department**. Concretely:

1. **Before writing code,** read CLAUDE.md, context.MD, MCP.md, and the Directive's §1 session-start files. Produce the orientation summary.
2. **For ANY agent-shaped work, design and implement it in Google ADK** — see §0.1. If the requested feature involves an agent, a tool an agent will use, a multi-agent workflow, memory shared between agents, or an orchestration step, the implementation goes through ADK primitives. No exceptions without an approved ADR.
3. **Take instructions from the Development Supervisor Agent.** If no Development Supervisor exists in this repo yet, behave as if its instructions are the user's instructions, but record what a Supervisor would have asked for in `docs/IMPLEMENTATION_LOG.md`.
4. **Hand off completed code to Codex CLI** via `scripts/quality-gate.sh` (existing pair-coding skeleton).
5. **After Codex signs off, hand off to the Supervisor** (`/code-review`, `/security-review`, `/verify`).
6. **After Supervisor signs off, hand off to the Work Reviewer Agent** — even for code, because the Work Reviewer checks completeness and client-readiness (READMEs, ADRs, deployment guides, tests).
7. **Update the Work Scheduler Agent's task status** when an assigned task moves through `in_progress` → `under_review` → `completed` → `approved`.

If any of these governance agents are not yet implemented in the current app, Claude Code's job is to scaffold their stubs **in ADK** first, before doing the requested feature work. Stubs are cheap; missing governance is not.

## 12. Demo Workflow (every app gets one)

Wire a `POST /api/demo/run` endpoint or a CLI command that takes a single prompt — e.g. `"Create a project plan for a 10-storey commercial building."` — and produces:

1. Classification (Chief Executive Agent).
2. Work breakdown + schedule (Work Scheduler Agent).
3. Department assignments (Chief Operating Agent).
4. Specialist outputs (construction, engineering, finance, procurement, legal agents — whichever are implemented).
5. Development supervision report (if any software work was triggered).
6. Review report (Work Reviewer Agent).
7. Executive summary (Chief Executive Agent).

This demo doubles as the smoke test for the governance pipeline.

## 13. Free / Open-Source Stack Preference

This extension does NOT override the FOSS Stack Rule in the Project Execution Directive. Default reviewer is **Codex CLI signed in with ChatGPT Plus** (no per-call cost). Default LLM for ADK agents is whatever the FOSS rule allows for this app — Ollama / OpenRouter free / GitHub Models — before any paid Claude/Vertex usage. Paid AI usage requires explicit owner approval, logged in `docs/IMPLEMENTATION_LOG.md`.

## 14. The Four Gates — Restated

Nothing ships until all four pass. In order:

| Gate | Owned by | Mechanism |
|---|---|---|
| 1. Code review | Codex CLI | `./scripts/quality-gate.sh` |
| 2. Supervisor sign-off | Claude Code skills | `/code-review`, `/security-review`, `/verify` |
| 3. Work Reviewer Agent | ADK governance | `POST /api/review/work` → status `approved` |
| 4. Work Scheduler Agent | ADK governance | task status flipped to `approved` |

If any gate is blocked, escalate per §3 step 8 — back to the responsible agent with `correction_instructions`. Do not bypass.

<!-- END: AGENTIC ADK EXTENSION -->
