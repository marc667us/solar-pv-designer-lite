# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**SolarPro Global** — Intelligent Global PV Solar System Design Platform.
Flask web SaaS for residential, commercial, and industrial solar PV design, financial engineering, and project management.

- **Live URL**: https://solarpro.aiappinvent.com
- **GitHub**: marc667us/solar-pv-designer-lite (branch: `master`)
- **Render service**: `srv-d86gh237uimc73dib0f0`
- **Admin login**: `admin` / `SolarAdmin2026!` (enterprise plan)

Everything lives in a **single file**: `web_app.py` (~9 246 lines). SQLite database (`solar.db` locally, `/opt/render/project/src/solar.db` on Render).

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

**Render (production):**
```bash
gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

---

## CRITICAL — Editing `web_app.py`

**NEVER use the Edit tool directly on `web_app.py`.**

It has CRLF line endings + mojibake (UTF-8 dashes stored as Windows-1252). The Edit tool introduces Unicode curly quotes (`\xe2\x80\x9d`) that corrupt the file.

**Always use binary Python patch scripts:**
```python
data = open('web_app.py', 'rb').read()
data = data.replace(b'old bytes', b'new bytes')
open('web_app.py', 'wb').write(data)
```

Use `open('web_app.py', 'rb')` / `open('web_app.py', 'wb')` pattern in a PowerShell heredoc or temp .py file.

---

## Database

SQLite. Schema auto-created by `init_db()` (line ~170) on every cold start. Tables:

`users`, `projects`, `tickets`, `ticket_replies`, `appliances`, `payments`, `leads`, `newsletter_subscribers`, `news_posts`, `suppliers`, `equipment_catalog`, `email_logs`, `upgrade_codes`, `assessment_requests`, `installers`, `monitor_alerts`, `monitor_state`

`init_db()` runs `ALTER TABLE … ADD COLUMN` migration stubs — safe to re-run on existing DBs.

All project engineering data stored as JSON blob in `projects.data_json`.

**Key data pitfalls:**
- Login field is `username` (not `email`)
- CSRF field is `_csrf`
- Ghana region names: `Greater Accra`, `Ashanti`, `Northern`, `Volta`, `Western` (NOT plain "Accra")
- `mounting_type` values: `rooftop_pitched`, `rooftop_flat`, `rooftop_metal`, `rooftop_membrane`, `ground_fixed`, `ground_tracking`

---

## Architecture

Single-file Flask app — no blueprints. Structure inside `web_app.py`:

| Lines | What it does |
|---|---|
| 1–168 | Imports, Flask config, rate limiter, CSRF, security headers |
| 169–1153 | `init_db()`, `get_db()`, helpers, calculation orchestration |
| 1154–1828 | Core routes: register/login/dashboard/project/results/reports |
| 1829–3173 | Export routes: Excel, CSV, PDF (via `markdown-pdf`) |
| 3174–3823 | Admin routes: users, tickets, appliances, codes, leads, news, newsletter, stats |
| 3824–4942 | Business routes: assess, installer register, procurement, email, upgrade/payments |
| 4943–9246 | AI Prospecting Agent + Helpline AI + security + beta features |

Supporting modules:
- `calculation/ac_cable_sizing.py` — AC cable sizing
- `config/global_solar_data.py` — country/region solar irradiance database
- `wsgi.py` — Render/Gunicorn entrypoint
- `static/land-110m.json` — Bundled world atlas topojson (55KB, served to globe widget)
- `static/logo.svg` — App logo

Templates: `templates/` (58 HTML files). Base layout: `templates/base.html`.

---

## Key routes

| Route | Description |
|---|---|
| `/` | Landing page |
| `/register`, `/login`, `/logout` | Auth |
| `/dashboard` | User dashboard, projects list + KPIs |
| `/project/new` | Create project |
| `/project/<pid>/location` | **Step 1**: Country/region/solar data + globe widget |
| `/project/<pid>/loads` | **Step 2**: Load schedule entry |
| `/project/<pid>/results` | **Step 3**: Full engineering results |
| `/project/<pid>/report/pv` | PV array report |
| `/project/<pid>/report/boq` | Bill of quantities |
| `/project/<pid>/report/cable` | Cable sizing report |
| `/project/<pid>/report/economic` | Financial analysis |
| `/project/<pid>/report/installation` | Installation drawings (page 1) |
| `/project/<pid>/report/installation/drawings` | Installation drawings (page 2) — hardware details |
| `/project/<pid>/report/energy` | Energy analysis |
| `/project/<pid>/report/proposal` | Client proposal |
| `/project/<pid>/report/*/pdf` | PDF export via `markdown-pdf` |
| `/project/<pid>/export/excel` | Excel workbook export |
| `/assess` | Public lead form + AI scoring |
| `/upgrade` | Subscription plans |
| `/admin/*` | Admin panel (users, tickets, agent, stats…) |
| `/admin/agent/run` | POST — runs AI prospecting agent |
| `/api/assistant/chat` | POST — Helpline AI chat |
| `/static/land-110m.json` | World atlas topojson for globe widget |

---

## Globe Widget (`templates/location.html`)

D3.js v7 canvas-based rotating orthographic globe on the location step.

- **Land data**: fetched from `/static/land-110m.json` (same-origin, no CDN/CORS issues)
- **Red dot**: shows when no location is selected (default at lat=5, lon=15)
- **Green dot**: appears immediately when user selects any country + region; globe flies to those coordinates
- **`flyToLocation(lat, lon, label, saved)`**: always sets green marker
- D3 uses chained `.projection(proj).context(ctx)` API (not `d3.geoPath(proj, ctx)` shorthand)
- Canvas clipped to sphere circle to prevent back-hemisphere bleed
- Globe is in LEFT column, directly below country/region dropdowns (220px height)

**DO NOT** change the fetch URL away from `/static/land-110m.json` — CDN fetches fail silently in some browsers/networks and break the globe.

---

## AI Stack

### Helpline (floating chat widget, bottom-right of every logged-in page)
- Route: `POST /api/assistant/chat`
- Chain: Claude (`claude-opus-4-7`) → OpenRouter (free Llama/Gemma) → Ollama → GitHub Models (`gpt-4.1-mini`) → rule-based fallback
- CSRF passed via `X-CSRF-Token` header
- `_fetch_github_context()` — last 10 commits from public GitHub API, 5-min cache, appended to system prompt
- Escalation: `[ESCALATE]` tag → red banner → creates high-priority ticket

### Prospecting Agent (`/admin/agent`)
- Route: `POST /admin/agent/run`
- Chain: OpenRouter (4 free models: llama-3.1-8b, gemma-2-9b, mistral-7b, llama-3.3-70b) → Ollama → GitHub Models (`gpt-4.1-mini`) → Claude (last resort)
- Sequential `if raw is None` blocks — NOT `elif` (so each provider truly falls through)
- `_provider_errors` list surfaces per-provider errors in `ai_error` JSON field
- Results in `monitor_alerts` table; `urgency_score` field (1–10)
- DuckDuckGo search (`ddgs`) for procurement/RFP sources

**GitHub Models API**: endpoint `https://models.inference.ai.azure.com/chat/completions`, model ID is `gpt-4.1-mini` (NOT `openai/gpt-4.1-mini`).

**OpenRouter API**: requires `HTTP-Referer` and `X-Title` headers.

---

## Email Stack

- `_send_email(to, subject, html, ...)` — tries Resend first, falls back to SMTP
- SMTP: `mail.privateemail.com:465` (SSL), user `support@aiappinvent.com`, pass `/123456Me`
- Resend: API key `rnd_pGzmu0qNuy9wM2qEqAgLH3zmOgoU` — domain verify pending (Resend outage)
- Per-purpose senders: `EMAIL_SALES`, `EMAIL_SUPPORT`, `EMAIL_BILLING`, `EMAIL_HELLO`, `EMAIL_PROPOSALS` (all → `sales@` or `support@` or `billing@aiappinvent.com`)

---

## Payments

- **Paystack** — `POST /api.paystack.co/transaction/initialize`; callback `/paystack/callback`; verify `/paystack/verify`
- **Stripe** — `stripe.checkout.Session.create`; webhook `/stripe/webhook` with signature verification
- **Upgrade codes** — admin-issued at `/upgrade/redeem`
- Plans: `free` (1 project, 14 days), `professional` ($49/mo, 10 projects), `business` ($99/mo, unlimited), `enterprise` (custom, unlimited)

---

## Installation Reports — Ground Mount

`templates/report_installation.html` and `templates/report_installation_drawings.html` both check:
```jinja2
{% set mt = d.get('mounting_type','rooftop_pitched') %}
{% if mt in ['ground_fixed','ground_tracking'] %}
```

Ground mount shows: GROUND MOUNT ARRAY title, Ground Area Calculator card, Land Area Required in specs, STEEL POST / CONCRETE FOOTING / PURLIN BEAM / EARTH ROD hardware (instead of L-FOOT / T-RAIL).

---

## CI/CD

`.github/workflows/deploy.yml`:
1. Triggers Render deploy via `POST /v1/services/$RENDER_SERVICE_ID/deploys`
2. Syncs non-empty GitHub Secrets → Render env vars (handles both flat `[{key,value}]` AND nested `[{envVar:{key,value}}]` Render API response formats)

**Required GitHub Secrets**: `RENDER_API_KEY`, `RENDER_SERVICE_ID`
**Optional** (synced if set): `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `MISTRAL_API_KEY`, `OLLAMA_URL`, `OLLAMA_MODEL`, `SECRET_KEY`, `PAYSTACK_SECRET_KEY`, `RESEND_API_KEY`, `EMAIL_*`, `SMTP_*`

---

## Security (implemented)

- Brute-force lockout (5 failed logins → 15 min lockout)
- CSRF protection on all POST forms (`_csrf` field)
- Content Security Policy headers
- Paystack webhook signature verification
- Audit log table
- `robots.txt` (blocks crawlers from auth/admin routes)

**Pending security TODOs** (from `SECURITY.md`):
- Admin 2FA (`pyotp` TOTP)
- DMARC DNS record: `_dmarc.aiappinvent.com TXT "v=DMARC1; p=none; rua=mailto:marc667us@yahoo.com"`

---

## GitHub Secrets Status

| Secret | Status |
|--------|--------|
| `RENDER_API_KEY` | ✅ |
| `RENDER_SERVICE_ID` | ✅ |
| `ANTHROPIC_API_KEY` | ✅ |
| `OPENROUTER_API_KEY` | ✅ (synced to Render) |
| `RESEND_API_KEY` | ✅ |
| `OLLAMA_URL` | ✅ |
| `OLLAMA_MODEL` | ✅ |
| `SMTP_HOST` | ❌ not set |
| `SMTP_PORT` | ❌ not set |
| `SMTP_USER` | ❌ not set |
| `SMTP_PASS` | ❌ not set |
| `SMTP_FROM` | ❌ not set |
| `EMAIL_SALES` | ❌ not set |
| `EMAIL_SUPPORT` | ❌ not set |
| `EMAIL_BILLING` | ❌ not set |
| `EMAIL_HELLO` | ❌ not set |
| `EMAIL_PROPOSALS` | ❌ not set |

---

## Engineering Calculation Flow

1. Location step → `config/global_solar_data.py` returns PSH, temp, tariff, currency for country/region
2. Loads step (POST) → calculates and saves results to `projects.data_json`:
   - `calc_loads()` → daily kWh
   - `calc_pv()` → PV array kW, panel count, temp derating
   - `calc_battery()` → battery kWh, count, chemistry
   - `calc_inverter()` → inverter kW
   - `calc_mppt()` → MPPT current
   - `size_all_cables()` → AC/DC cable sizes
   - `calc_boq()` → Bill of Quantities with supply markup + install rate
   - `calc_economics()` → CAPEX, NPV, IRR, payback, savings
3. Results page renders from `data_json["results"]`; redirects to `/loads` if results not yet computed

---

## Testing

`test_render.py` — end-to-end test suite against live Render site.

```powershell
python test_render.py
```

---

## Recent Commit History (as of 2026-06-01)

| Commit | What |
|--------|------|
| `8f72342` | Bundle land-110m.json + red/green dot + fix canvas DPR scaling bug |
| `d41fae0` | Move globe to left column next to location selector |
| `51903dc` | Globe 3-D shading, chained D3 API, canvas sphere clip |
| `7f22f33` | Fix Render deploy workflow env-var sync (nested format) + GitHub Models model ID |
| `eadfce1` | Fix OpenRouter fallback chain + ground mount diagrams |
| `86eadc2` | Security: brute-force lockout, CSP, Paystack webhook, audit log, robots.txt |
| `15e50ed` | API manager — single secure source for all external API keys |
| `993477f` | Terms of Service, Privacy Policy, mandatory signup checkbox |
| `c666bc9` | Beta testing: waitlist signup, feedback widget, admin dashboards |
| `ce86caa` | Resend email + SMTP fallback + per-purpose email addresses |
| `0b3604e` | OpenRouter+Ollama Helpline AI; WhatsApp config; dynamic landing page |

---

## Notes

- Legacy tkinter desktop app files (`ui.py`, `main.py`, `solar_pv_designer/`, `build/`, `dist*/`) are present — ignore them
- `SPEC.md` — original functional spec, may lag implementation
- `assumptions.md` — engineering calculation assumptions (derating factors, autonomy days, etc.)
- `SECURITY.md` — security checklist and pending items
- PDF generation: `markdown-pdf` Python package (`MarkdownPdf` + `Section`) — pandoc/wkhtmltopdf/reportlab NOT installed
