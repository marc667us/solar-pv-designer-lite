# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**SolarPro Global** â€” Intelligent Global PV Solar System Design Platform. Flask web SaaS for residential, commercial, and industrial solar PV design, financial engineering, and project management. Deployed live at **https://solarpro.aiappinvent.com**.

Everything lives in a single file: `web_app.py` (~5 800 lines). SQLite database (`solar.db` locally, `/opt/render/project/src/solar.db` on Render).

---

## Running locally

**Quick start (Windows â€” opens Cloudflare tunnel automatically):**

```
"START SERVER.bat"
```

or directly:

```powershell
cd "C:\Users\USER\Desktop\solar-pv-designer-lite"
python start.py
```

`start.py` starts Waitress on port 5000 then opens a Cloudflare tunnel. Prints the public URL when ready.
Default admin credentials printed at startup: `admin / SolarAdmin2026!`

**Flask dev server (hot-reload, no tunnel):**

```powershell
python web_app.py
```

App runs at http://localhost:5000.

**Render (production):**

```bash
gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

`wsgi.py` calls `init_db()` then serves `app`.

---

## Database

SQLite. Schema auto-created by `init_db()` in `web_app.py` (line ~170) on every cold start. Tables:

`users`, `projects`, `tickets`, `ticket_replies`, `appliances`, `payments`, `leads`, `newsletter_subscribers`, `news_posts`, `suppliers`, `equipment_catalog`, `email_logs`, `upgrade_codes`, `assessment_requests`, `installers`, `monitor_alerts`, `monitor_state`

`init_db()` also runs `ALTER TABLE â€¦ ADD COLUMN` migration stubs for columns added post-launch â€” safe to re-run on existing DBs.

All project engineering data is stored as a JSON blob in `projects.data_json`.

---

## Architecture

Single-file Flask app â€” no blueprints. Structure inside `web_app.py`:

| Section | What it does |
|---|---|
| Lines 1â€“168 | Imports, Flask config, rate limiter, CSRF, security headers |
| Lines 169â€“1153 | `init_db()`, `get_db()`, helper functions, calculation orchestration |
| Lines 1154â€“1828 | Core project routes (register/login/dashboard/project/results/reports) |
| Lines 1829â€“3173 | Export routes (Excel, CSV, PDF reports via `markdown-pdf`) |
| Lines 3174â€“3823 | Admin routes (users, tickets, appliances, codes, leads, news, newsletter, platform stats) |
| Lines 3824â€“4942 | Business routes (assess, installer register, procurement, email, upgrade/payments) |
| Lines 4943â€“5813 | AI Prospecting Agent (scraping, Claude API analysis, monitoring) |

Supporting modules (in project root):

- `calculation/ac_cable_sizing.py` â€” AC cable sizing calculations
- `config/global_solar_data.py` â€” country/region solar irradiance database
- `battery_sizing.py`, `pv_sizing.py`, `inverter_sizing.py`, `load_estimation.py` â€” legacy calculation modules (still imported by some code paths)
- `wsgi.py` â€” Render/Gunicorn entrypoint

Templates: all `.html` files in the project root (Flask `templates/` subdirectory is also present for base layouts).

---

## Key routes

| Route | Description |
|---|---|
| `/` | Landing page |
| `/register`, `/login`, `/logout` | Auth |
| `/dashboard` | User dashboard with projects list + KPIs |
| `/project/new` | Create project |
| `/project/<pid>/location` | Country/region/solar data input |
| `/project/<pid>/loads` | Load schedule entry form |
| `/project/<pid>/results` | Full engineering results (PV, battery, inverter, cable, financial) |
| `/project/<pid>/report/*` | Individual report pages (pv, boq, cable, economic, installation, energy, proposal) |
| `/project/<pid>/report/*/pdf` | PDF export via `markdown-pdf` |
| `/project/<pid>/export/excel` | Excel workbook export |
| `/project/<pid>/procurement` | Project-specific procurement plan |
| `/project/<pid>/email` | Send report by email |
| `/assess` | Public lead form + AI scoring |
| `/installer/register` | Installer network registration |
| `/upgrade` | Subscription plans (Free / Professional / Enterprise) |
| `/upgrade/checkout` | Stripe and Paystack checkout |
| `/stripe/webhook` | Stripe webhook receiver |
| `/admin/*` | Admin-only: users, tickets, appliances, codes, leads, news, assessments, installers, pipeline, sales, newsletter, platform stats, AI agent |
| `/admin/agent` | AI Prospecting Agent dashboard |
| `/admin/agent/run` | Run the agent (Claude API â€” scrapes procurement portals, scores leads) |
| `/admin/agent/monitor/status` | Agent monitor SSE-like status polling |

---

## Payments

- **Stripe** â€” checkout via `stripe.checkout.Session.create`; webhook at `/stripe/webhook` with signature verification.
- **Paystack** â€” `POST /api.paystack.co/transaction/initialize`; callback at `/paystack/callback`; verify at `/paystack/verify`.
- **Upgrade codes** â€” admin-issued redemption codes at `/upgrade/redeem`.
- Plans: `free`, `professional`, `enterprise` (stored on `users.plan`).

---

## AI Prospecting Agent (`/admin/agent`)

Uses the **Anthropic SDK** (`anthropic` package). Route `POST /admin/agent/run` scrapes procurement/solar news sources with `ddgs` (DuckDuckGo Search), then calls Claude (`claude-opus-4-7` by default) to score and summarise leads. Results stored in `monitor_alerts` table. Status polling via `/admin/agent/monitor/status`.

---

## Environment variables (`.env`)

```
SECRET_KEY=...          # Flask session key â€” generated on first run if absent
ANTHROPIC_API_KEY=...   # Required for AI agent; app runs without it (agent returns error)
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
PAYSTACK_SECRET_KEY=...
SMTP_HOST=...           # For report email delivery
SMTP_PORT=...
SMTP_USER=...
SMTP_PASS=...
DEMO_MODE=true          # Render: show demo banner, skip payment enforcement
```

---

## Deployment (Render)

Configured in `render.yaml`. Branch: `master`. On push to `master`:

1. `pip install -r requirements.txt`
2. `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
3. GitHub Actions (`.github/workflows/`) syncs `ANTHROPIC_API_KEY` from GitHub Secrets â†’ Render env vars via Render API.

Persistent disk mounted at `/opt/render/project/src` (1 GB) â€” this is where `solar.db` lives on Render.

---

## Engineering calculation flow

1. User enters project location â†’ `/api/solar/<country>/<region>` returns irradiance data from `config/global_solar_data.py`.
2. User enters load schedule â†’ saved as JSON in `projects.data_json`.
3. `/project/<pid>/results` triggers full calculation inline:
   - Load analysis (sum of daily Wh per appliance Ã— quantity Ã— hours)
   - PV array sizing (peak load / PSH / derating)
   - Battery bank sizing (autonomy days Ã— daily Wh / DoD / voltage)
   - Inverter / charge controller sizing
   - AC cable sizing via `calculation/ac_cable_sizing.py`
   - Financial model (CAPEX, OPEX, savings, NPV, IRR, payback)
4. Results rendered to HTML; PDF/Excel exports regenerate from the same `data_json`.

---

## Testing

`test_render.py` â€” 72-check end-to-end test suite against the live Render site. Requires admin account (enterprise plan). Run with:

```powershell
python test_render.py
```

To wait for a deploy to finish before testing (uses GitHub public API â€” no auth needed):

```bash
# Poll GitHub Actions for current HEAD commit, wait for success, then test
SHA=$(git rev-parse HEAD)
until curl -sf -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/marc667us/solar-pv-designer-lite/actions/runs?head_sha=$SHA&per_page=1" \
  | python3 -c "import sys,json; r=json.load(sys.stdin).get('workflow_runs',[]); exit(0 if r and r[0]['status']=='completed' and r[0]['conclusion']=='success' else 1)" 2>/dev/null
do sleep 10; done && sleep 40 && python test_render.py
```

---

## Helpline â€” AI Technical Assistant

Floating chat widget on every logged-in page (bottom-right, `#sp-asst-btn`). Powered by Claude `claude-opus-4-7`.

- **Routes**: `POST /api/assistant/chat` (no login required), `POST /api/assistant/escalate` (`@login_required`)
- **CSRF**: passed via `X-CSRF-Token` header (meta tag `name="csrf-token"` in base.html)
- **GitHub context**: `_fetch_github_context()` fetches last 10 commits from public GitHub API, 5-min cache (`_gh_ctx_cache`), appended to system prompt so Helpline knows recent fixes
- **Escalation**: AI includes `[ESCALATE]` tag â†’ red banner â†’ one-click creates high-priority ticket with chat transcript
- **ANTHROPIC_API_KEY**: must be set in Render dashboard (CI no longer overwrites it with empty value)

---

## CI/CD

`.github/workflows/deploy.yml`:
1. Triggers Render deploy via `POST /v1/services/$RENDER_SERVICE_ID/deploys`
2. Syncs non-empty GitHub Secrets to Render env vars (skips secrets not configured as GitHub Secrets â€” safe for keys set directly in Render dashboard)

Required GitHub Secrets: `RENDER_API_KEY`, `RENDER_SERVICE_ID`. Others optional (only synced if set).

---

## Notes

- The legacy tkinter desktop app files (`ui.py`, `main.py`, `solar_pv_designer/`, `build/`, `dist*/`) are still present â€” ignore them; the web app (`web_app.py`) is the live product.
- `SPEC.md` contains the original functional spec â€” useful background but may lag the implementation.
- `assumptions.md` documents engineering calculation assumptions (derating factors, autonomy days, etc.).
