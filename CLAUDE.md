# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**SolarPro Global** — Intelligent Global PV Solar System Design Platform. Flask web SaaS for residential, commercial, and industrial solar PV design, financial engineering, and project management. Deployed live at **https://solarpro-global.onrender.com**.

Everything lives in a single file: `web_app.py` (~5 800 lines). SQLite database (`solar.db` locally, `/opt/render/project/src/solar.db` on Render).

---

## Running locally

**Quick start (Windows — opens Cloudflare tunnel automatically):**

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

`init_db()` also runs `ALTER TABLE … ADD COLUMN` migration stubs for columns added post-launch — safe to re-run on existing DBs.

All project engineering data is stored as a JSON blob in `projects.data_json`.

---

## Architecture

Single-file Flask app — no blueprints. Structure inside `web_app.py`:

| Section | What it does |
|---|---|
| Lines 1–168 | Imports, Flask config, rate limiter, CSRF, security headers |
| Lines 169–1153 | `init_db()`, `get_db()`, helper functions, calculation orchestration |
| Lines 1154–1828 | Core project routes (register/login/dashboard/project/results/reports) |
| Lines 1829–3173 | Export routes (Excel, CSV, PDF reports via `markdown-pdf`) |
| Lines 3174–3823 | Admin routes (users, tickets, appliances, codes, leads, news, newsletter, platform stats) |
| Lines 3824–4942 | Business routes (assess, installer register, procurement, email, upgrade/payments) |
| Lines 4943–5813 | AI Prospecting Agent (scraping, Claude API analysis, monitoring) |

Supporting modules (in project root):

- `calculation/ac_cable_sizing.py` — AC cable sizing calculations
- `config/global_solar_data.py` — country/region solar irradiance database
- `battery_sizing.py`, `pv_sizing.py`, `inverter_sizing.py`, `load_estimation.py` — legacy calculation modules (still imported by some code paths)
- `wsgi.py` — Render/Gunicorn entrypoint

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
| `/admin/agent/run` | Run the agent (Claude API — scrapes procurement portals, scores leads) |
| `/admin/agent/monitor/status` | Agent monitor SSE-like status polling |

---

## Payments

- **Stripe** — checkout via `stripe.checkout.Session.create`; webhook at `/stripe/webhook` with signature verification.
- **Paystack** — `POST /api.paystack.co/transaction/initialize`; callback at `/paystack/callback`; verify at `/paystack/verify`.
- **Upgrade codes** — admin-issued redemption codes at `/upgrade/redeem`.
- Plans: `free`, `professional`, `enterprise` (stored on `users.plan`).

---

## AI Prospecting Agent (`/admin/agent`)

Uses the **Anthropic SDK** (`anthropic` package). Route `POST /admin/agent/run` scrapes procurement/solar news sources with `ddgs` (DuckDuckGo Search), then calls Claude (`claude-opus-4-7` by default) to score and summarise leads. Results stored in `monitor_alerts` table. Status polling via `/admin/agent/monitor/status`.

---

## Environment variables (`.env`)

```
SECRET_KEY=...          # Flask session key — generated on first run if absent
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
3. GitHub Actions (`.github/workflows/`) syncs `ANTHROPIC_API_KEY` from GitHub Secrets → Render env vars via Render API.

Persistent disk mounted at `/opt/render/project/src` (1 GB) — this is where `solar.db` lives on Render.

---

## Engineering calculation flow

1. User enters project location → `/api/solar/<country>/<region>` returns irradiance data from `config/global_solar_data.py`.
2. User enters load schedule → saved as JSON in `projects.data_json`.
3. `/project/<pid>/results` triggers full calculation inline:
   - Load analysis (sum of daily Wh per appliance × quantity × hours)
   - PV array sizing (peak load / PSH / derating)
   - Battery bank sizing (autonomy days × daily Wh / DoD / voltage)
   - Inverter / charge controller sizing
   - AC cable sizing via `calculation/ac_cable_sizing.py`
   - Financial model (CAPEX, OPEX, savings, NPV, IRR, payback)
4. Results rendered to HTML; PDF/Excel exports regenerate from the same `data_json`.

---

## Notes

- No test suite. Test manually via the web UI or `python test_agent.py` for the agent endpoint.
- The legacy tkinter desktop app files (`ui.py`, `main.py`, `solar_pv_designer/`, `build/`, `dist*/`) are still present — ignore them; the web app (`web_app.py`) is the live product.
- `SPEC.md` contains the original functional spec — useful background but may lag the implementation.
- `assumptions.md` documents engineering calculation assumptions (derating factors, autonomy days, etc.).
