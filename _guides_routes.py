# ─── Guides — Quick / Full user / Full technical ─────────────────────────────
# 2026-06-27: replaced legacy /support/user-guide with 3 audience-targeted guides.
# Each guide:
#   - HTML view (templates/guide.html shared template)
#   - PDF download via _render_pdf (markdown-pdf, already in toolchain)
#   - Listen button on the HTML view uses the browser SpeechSynthesis API
#     (zero-cost, no TTS bill, no storage). Auto-plays when ?listen=1.
#   - Optional embedded video — owner pastes a YouTube/Loom URL into the
#     <slug>_VIDEO_URL env var when they record one.

_GUIDE_QUICK_MD = """# Quick Start — 3 minutes

Welcome to SolarPro Global. This is the bare minimum you need to get a usable solar design out of the platform.

## 1. Register or log in

Click **Register** on the homepage (top-right) and use your real email — the design + PDF report will land in your inbox. Login goes through Keycloak; if it looks unfamiliar, just enter your email and the password you set at registration.

## 2. Create a project

From the Dashboard, click **+ New Project**. Give it a meaningful name (e.g. "Accra Office 50 kW"). You'll land on the Location step.

## 3. Pick country + region

Choose the country, then the region. The form picks up local solar irradiance (peak sun hours) and tariff data automatically.

## 4. Enter your loads

Click **Loads** in the sidebar. For each appliance you want to power, pick from the dropdown (60 common appliances pre-loaded), set Watts / Quantity / Hours-per-day / Demand Factor. The Daily Energy and Peak Load tally live at the bottom.

## 5. View Results

Click **Calculate My Solar System**. The engine sizes:
- PV array (kWp + panel count)
- Battery bank (kWh)
- Inverter (kW)
- AC + DC cabling (BS 7671 / IEC 60364)
- 25-year economics (NPV, IRR, payback)

## 6. Export

From any report page click **PDF** to download. From the Results page click the gold **Share** button to generate a public share card with QR code.

That's it. The Full User Guide goes deeper on every step; the Technical Guide explains the engine math.
"""


_GUIDE_FULL_USER_MD = """# Full User Guide

This guide covers every feature an end user (designer, sales engineer, project manager) will touch.

## 1. Accounts and plans

| Plan | Projects | Reports | Price |
|---|---|---|---|
| Free Trial | 1 | Inspection only | 14 days |
| Professional | 10 | All 9 reports | $49/mo |
| Business | unlimited | + white-label PDFs + RFQ | $99/mo |
| Enterprise | unlimited | + multi-tenant + SLA | Contact us |

Upgrade at **Settings → Upgrade**. Mobile Money + card both supported via Paystack.

## 2. The design flow

Every project goes through these steps:

**Location** → country, region, system type (off-grid / grid-tied / hybrid), tariff. Pulls peak sun hours from `config/global_solar_data.py`.

**Inspection** (optional) → roof type, tilt, azimuth, obstructions placed on a 16-compass dial. Feeds the shading factor.

**Loads** → appliances + watts + quantity + hours/day + demand factor. The Appliance dropdown has 60 common entries with typical wattage that auto-fill the Watts column.

**Results** → engine sizes PV / battery / inverter / cable. 25-year economics.

**Reports** → 9 PDF reports (PV Design, BOQ, Cable Sizing, Economic, Installation Plan, Installation Drawings, Energy Production, Proposal, Shading 3D).

## 3. Check My Bill — the conversion magnet

`/bill-check` is a free, anonymous, ~60-second tool that audits an ECG bill against the **PURC Q2 2026 tariff** (12 customer categories). Visitors enter their bill in GHS, pick a category, and see what a 5-year solar loan would cost vs. their current bill. Outputs: PDF, email-yourself, invite-friends, copy-share-link. Share any /bill-check link to get prefill-loaded leads.

## 4. Marketplace

`/marketplace` is free to browse (no signup). 21 categories, 437+ products across 140+ brands. Filter by category / subcategory / country (compliance badge) / currency.

- **Country compliance badge** — green = compliant, amber = checks needed, red = blocked, violet = notes. Hover the badge for findings.
- **Currency picker** — USD / EUR / GBP / GHS / NGN / KES / ZAR / XOF / ZMW.
- **Procurement Center** at `/procurement-center` — checkbox-grid picker, build a Basic Price Sheet, BOM (Cost Estimate), or BOQ (tender submission).
- **RFQs** at `/rfqs/new` — invite suppliers, track responses at `/rfqs/<id>`.

## 5. Sharing (Growth Layer)

Two surfaces:

**Per-project Share** — Results page → gold **Share** button → composer at `/share/<project_id>`. Seven card types: Solar Savings, Energy Score, BOQ Summary, Proposal Preview, **Installer Achievement**, **Supplier Product**, **Roof Before-After**. Each generates a PNG/PDF + share URL + QR code. WhatsApp / Facebook / LinkedIn / X buttons built in.

**Platform Share** — navbar megaphone → modal with WhatsApp / Facebook / LinkedIn / X / Email / QR. Logged-in users get their referral code baked into every link.

## 6. Referrals

Every account has an 8-character referral code. Share `/r/<code>` — visitors get a 30-day cookie, signups credit you in the `referrals` table. **20% credit per paid referral, 20% off the new user's first paid month.** Dashboard at `/referrals`.

## 7. Free Site Assessment

The homepage **Free Solar Site Assessment** modal collects a lead's name + phone + country + region + building type/size. It writes to `assessment_requests` and shows on `/admin/sales`. Sales operators click **Open Design Card** to convert any submission into a project pre-filled with the lead's details, then run the full design flow.

## 8. Helpline AI

Floating chat (bottom-right) — ask anything about features, sizing, or the design flow. Trained on every feature in this guide. Says `[ESCALATE]` when it genuinely needs human escalation (payment disputes, data corruption).

## 9. Common gotchas

- Login bounces to `auth.aiappinvent.com` — that's Keycloak, expected. Use email-as-username.
- Marketplace shows wrong currency? Pick your currency on the form before clicking Filter.
- Share card numbers all show 0? You need to run Loads → Results first; share cards read the computed values.
- Lost your password? Click "Forgot password" on the Keycloak login form.
"""


_GUIDE_FULL_TECHNICAL_MD = """# Full Technical Guide

For engineers, integrators, and admins who need to understand or extend the platform.

## 1. Architecture overview

Single-file Flask app (`web_app.py`, ~10k lines). SQLite locally / Postgres on Render production. Templates in `templates/`. Calculation modules in `calculation/`. Solar/weather data in `config/`. CI/CD via GitHub Actions; deploy to Render via the **Diag Render recent deploys** workflow (auto-deploy on push is flaky).

Auth: Keycloak OIDC (since 2026-06-19). Login route redirects to `auth.aiappinvent.com` and back via `/auth/callback`.

Database: 47 RLS tables enforced via Postgres row-level security. Tenant context set per request via `app.current_tenant` GUC.

## 2. The sizing engine

`calc_loads → calc_pv → calc_battery → calc_inverter → calc_mppt → size_all_cables → calc_boq → calc_economics`. Each function reads from and writes back to `projects.data_json` (the canonical project state blob).

Key inputs to the engine:
- `loads[]` — list of {name, watts, qty, hours, demand_factor}.
- `psh` (peak sun hours) and `temp` from `config/global_solar_data.py`.
- `shading_factor` from the Inspection step.
- `target_pct` (solar fraction goal) and `loan_years/loan_rate` for economics.

Key outputs in `results`:
- `pv_kw`, `num_panels`, `bat_kwh`, `inv_kw`, `daily_kwh`.
- `economics.annual_sav`, `economics.payback`, `economics.total_local`.
- `boq_rows[]` — full bill of quantities.

## 3. Marketplace schema

`equipment_catalog` is the source of truth. Key columns:
- `category_id` → `product_categories` (21 categories, code + display_order).
- `subcategory` (free text, sourced from `_MARKETPLACE_SUBCATEGORIES`).
- `unit` (default per category from `_MARKETPLACE_DEFAULT_UNIT`).
- `spec` (free text, parsed for grid-compatibility back-fill).
- `voltage_v`, `frequency_hz`, `compliance_standards` (declared by supplier on add/edit).
- `is_verified` (admin approval gate; auto-drops to 0 on supplier edit).
- `is_public_visible` (marketplace gate).

The country compliance check (`country_compliance.compliance_findings_for_product`) reads from `COUNTRY_GRID_PROFILES` (24 countries) and produces high/med/low findings tagged per product.

## 4. Growth layer

`growth_share_assets` table holds every share card. Public access via `/s/<slug>`. Owner can revoke (status → 410). Events tracked in `growth_share_events` (created / viewed / shared by channel / converted).

Supported asset types: `solar_savings_card`, `energy_score_card`, `boq_summary_card`, `proposal_preview`, `installer_achievement_card`, `supplier_product_card`, `roof_before_after_card`. The payload for each is generated by `_safe_card_payload(project_row, asset_type)` — explicitly strips internal prices, supplier private prices, admin notes, rate buildups.

## 5. AI stack

| Surface | Chain | Models |
|---|---|---|
| Helpline (`/api/assistant/chat`) | Claude → OpenRouter → Ollama → GitHub Models → rule-based fallback | claude-opus-4-7 / free-tier OR models / mistral / gpt-4.1-mini |
| Prospecting agent (`/admin/agent/run`) | OpenRouter free → Ollama → GitHub Models → template extraction | nvidia nemotron / llama 3.3 70b / qwen 72b / llama 3.1 8b / gemma 2 9b / mistral 7b / llama 3.2 3b |

**Diagnostic**: `GET /admin/agent/ping-providers` (admin only). Pings every provider with a tiny 'OK' prompt and reports per-provider ok/reply/error.

**Owner directive**: no Anthropic in the prospecting chain. Helpline still allows Claude but only when explicitly authorised.

## 6. Email stack

`api_manager._send_email` chain: **Brevo → Axigen → Resend → SMTP**. Brevo primary (300/day free, domain authenticated). SMTP often fails on Render free (outbound 587 blocked). Resend key is currently a placeholder.

## 7. Security

- Brute-force lockout: 5 failed logins → 15-minute lockout.
- CSRF on every POST form (`_csrf` field).
- CSP headers; HSTS preload on the production domain.
- Audit log (`audit_logs`) with SHA-256 hash chain (every row signed against the previous).
- RLS on 47 tables; `FORCE ROW LEVEL SECURITY` on tenant tables.
- Paystack webhook signature verification.
- Zero Trust + RBAC documented in `SECURITY.md`.

## 8. Admin surfaces

- `/admin` — hub (users, tickets, news, agent, stats).
- `/admin/operations` — NOC/SOC dashboard.
- `/admin/logs` — JSON log viewer.
- `/admin/sales` — sales dashboard + recent landing-page assessments inline.
- `/admin/marketplace` + `/admin/marketplace/pending` — verification queue.
- `/admin/agent` + `/admin/agent/ping-providers` — prospecting + diagnostic.
- `/admin/opportunities` — Google News RSS feed + Save-all-to-CRM.
- `/admin/users` — last-seen-online per row.

## 9. Deployment

- `git push origin master` — does NOT reliably trigger a Render deploy on this repo.
- After every push: `gh workflow run "Diag Render recent deploys"`.
- Schema bootstrap: `_ensure_marketplace_schema_postgres` runs on cold start.
- For schema changes that need to predate cold start, use a dry-run-gated workflow (e.g. `Back-fill Marketplace Grid Fields`).

## 10. Where things live

| Path | Purpose |
|---|---|
| `web_app.py` | Routes, business logic |
| `calculation/` | Engine modules |
| `config/global_solar_data.py` | Country / region / PSH / tariff |
| `templates/` | Jinja2 |
| `country_compliance.py` | Grid profiles for 24 countries |
| `api_manager.py` | AI + Email + Payment + Search facade |
| `app/security/*` | Keycloak middleware + decorators |
| `migrations/` | SQL files (run via per-migration GH workflow) |
| `.github/workflows/` | CI / deploy / diag / backfill |
"""


def _guide_lookup(slug):
    return {
        "quick":     ("Quick Start", _GUIDE_QUICK_MD),
        "full-user": ("Full User Guide", _GUIDE_FULL_USER_MD),
        "technical": ("Full Technical Guide", _GUIDE_FULL_TECHNICAL_MD),
    }.get(slug)


@app.route("/guides/<slug>")
def guides_view(slug):
    g = _guide_lookup(slug)
    if not g:
        abort(404)
    title, md = g
    # Owner-supplied YouTube/Loom URL per guide (paste into env when recorded).
    video_url = os.environ.get(f"GUIDE_VIDEO_URL_{slug.upper().replace('-', '_')}", "")
    return render_template(
        "guide.html",
        user=current_user(),
        slug=slug,
        title=title,
        markdown=md,
        video_url=video_url,
        listen_autoplay=(request.args.get("listen") == "1"),
    )


@app.route("/guides/<slug>/pdf")
def guides_pdf(slug):
    g = _guide_lookup(slug)
    if not g:
        abort(404)
    title, md = g
    safe = slug.replace("-", "_")
    return _render_pdf(f"SolarPro — {title}", md, f"SolarPro_Guide_{safe}.pdf")


# Legacy URL redirects so existing email links / bookmarks don't 404.
@app.route("/support/user-guide")
def _legacy_user_guide_redirect():
    return redirect(url_for("guides_view", slug="full-user"), code=301)


@app.route("/support/user-guide/pdf")
def _legacy_user_guide_pdf_redirect():
    return redirect(url_for("guides_pdf", slug="full-user"), code=301)
