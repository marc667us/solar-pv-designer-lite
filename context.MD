# SolarPro Global — Session Context

**Last updated:** 2026-06-19 (Marketplace catalogue rebuild + Postgres bug fixes + Product Catalogue rename — live deploy verified 25/25)
**Purpose:** capture in-flight state so any session can resume mid-task without re-discovery.

## Session close — 2026-06-19 evening

Repo HEAD: `6ded729`. Live HEAD: `86130a5` (catalogue + UI rename; Keycloak commits are docs + new modules, no runtime change).

This session shipped two distinct workstreams:

1. **Marketplace catalogue rebuild** (11 commits `8261289`..`86130a5`) — live verified 25/25 smoke test. Detail below.
2. **Keycloak migration plan + Phases 0-2** (4 commits `e61fb23`..`6ded729`) — spec + auth inventory + local Keycloak stack + Flask middleware + 33 passing unit tests. `web_app.py` NOT modified; `KEYCLOAK_ENABLED` defaults off so production is unaffected. Full plan at `docs/SECURITY_MIGRATION_KEYCLOAK.md`.

Marketplace carry-over items (BOQ printable PDF compliance, CSV parser spec validation, Procurement Center subcategory drilldown, Codex round-1 on Slice 9, smoke-test extension, Render auto-deploy hook) deferred to memory `project_solar_pv_deferred_marketplace_work` — pick up AFTER Keycloak Phase 2 task 11 lands.

**Resume next session at:** Phase 2 task 11 — byte-patch `web_app.py:14746` to add `@require_role("marketplace_admin")` above the existing `@admin_required` on `admin_marketplace_dashboard`. See `docs/IMPLEMENTATION_LOG.md` "Session Close" marker for the exact resume point + steps.

---

## 2026-06-19 (catalogue session — 11 commits, live verified)

**Source prompt:** `pvsolar1/price master/price prompt.txt` (Electrical Costing, BOM, BOQ & Supplier Marketplace brief).

**Final live state** (HEAD `86130a5` on `solarpro.aiappinvent.com`, repo tip `a1732a4`):

- **21-category product taxonomy** in `_MARKETPLACE_CATEGORIES`. New 21st category `power_system` (RMU, Generators, UPS, Switchgear, etc.) closed the prompt's "Power System Equipment" gap.
- **Three central registries** sitting next to `_MARKETPLACE_CATEGORIES`:
  - `_MARKETPLACE_SUBCATEGORIES` (~140 entries) — drives the supplier upload form's subcategory dropdown + the `/marketplace?sub=` drilldown chips.
  - `_MARKETPLACE_DEFAULT_UNIT` — auto-fills the unit field on category change.
  - `_MARKETPLACE_SPEC_FIELDS` — surfaces as "Required: …" hint on the supplier form AND drives the BOQ Compliance Review.
- **Seed discipline:** category seed converted to `INSERT OR IGNORE` (SQLite) / `ON CONFLICT (code) DO NOTHING` (Postgres) so new categories actually land in existing DBs. Sample seed expanded 27→77 rows. New helpers `_backfill_marketplace_samples_for_empty_categories` (SQLite) + Postgres twin top up empty categories without touching populated ones.
- **14 new brand suppliers** added to the Postgres seed: Eaton, Hager, Legrand, Siemens, Polycab, RR Kabel, JA Solar, Victron, Pylontech, Cummins, APC, Cisco, Hikvision, Honeywell.
- **Forms wired to registries:** supplier add form, admin product-edit form, and CSV upload template (22 example rows, one per category). Admin form preserves legacy free-text values as "(legacy)" options.
- **Public subcategory drilldown:** `/marketplace?cat=&sub=` filters via LOWER() exact match.
- **Category-grouped grid** on both `/marketplace` and `/procurement-center` — gold section headers with icon + count badge above each category's card / checkbox grid.
- **BOQ Compliance Review panel** at `/boms/<id>/boq` — HIGH/MED/LOW findings driven off `_MARKETPLACE_SPEC_FIELDS` + `_MARKETPLACE_DEFAULT_UNIT`. No-print so it stays off the client PDF.
- **"Equipment Catalog" → "Product Catalogue" UI rename** (10 strings across 7 templates + web_app.py admin help) after the owner flagged the first equipment→product pass had missed the literal phrase. British spelling.

**Three live Postgres-only bug fixes uncovered by today's smoke test:**

| Commit | Bug | Fix |
|---|---|---|
| `ad5261f` | `cur.lastrowid` is `None` on psycopg2 INSERTs → 9 callsites redirect to `/boms/None` → 404 | `_PgCursorWrap` proxy in db_adapter.py adds lazy `SELECT lastval()` |
| `acbbc03` | Literal `%` in SQL (`NOT LIKE 'BulkProd-%'`) → `IndexError` when params supplied | Double `%`→`%%` before `?`→`%s` translation |
| `859f6af` | `marketplace_boms.currency` column never added on Postgres → `/procurement-center/add doc_type=bom` 500'd with UndefinedColumn | Add idempotent ALTER + Postgres per-category backfill helper |

**Live verification:** `tmp/live_smoke_test_2026-06-19.py` re-runnable. 25/25 PASS. Update the `startswith` commit-hash check at the top before re-running after future changes.

**Render deploy gotcha:** Render auto-deploy does NOT fire on `git push` for this repo. Use `gh workflow run "Force Render Deploy"` after each push. The "Deploy to Railway" workflow on every push is for the decommissioned legacy host.

**Commit list:**

```
a1732a4 test(live): add re-runnable live smoke test for the 2026-06-19 catalogue work
86130a5 feat(marketplace): rename Equipment Catalog -> Product Catalogue in UI
859f6af fix(pg): add marketplace_boms.currency + per-category sample backfill
acbbc03 fix(db): escape literal % in SQL before psycopg2 parameter binding
e7a469e feat(boq): Compliance Review panel driven by marketplace spec registry
14e33d6 feat(marketplace): group products by category + rename equipment->product
ad5261f fix(db): expose lastrowid on Postgres -- /boms/None + /rfqs/None bug
ab01e38 feat(marketplace): public subcategory drilldown -- ?sub=<name> filter
cb0bedc feat(marketplace): wire admin product-edit form to taxonomy registries
9a8540a feat(marketplace): wire supplier form + CSV template to new taxonomy
8261289 feat(marketplace): expand product taxonomy per electrical marketplace brief
```

### Carry-over for next session

- BOQ generator section mapping not yet using `_MARKETPLACE_SPEC_FIELDS` for the printable client PDF (compliance is in the no-print review only).
- CSV upload parser doesn't yet enforce required spec fields on import.
- Procurement Center subcategory drilldown not yet wired — only `/marketplace` got the `?sub=` chips this session.
- Slice 9 + 9b still have not been through a Codex round-1 review (now further extended by this session's catalogue work). Run `./scripts/quality-gate.sh` before declaring this work formally complete.

---

## 2026-06-08 (this session)

- **Phase 0.1 credential rotation:** byte-patched `web_app.py:559-560` to source `admin` + `marc667us` seed passwords from `SOLARPRO_ADMIN_PASSWORD` and `SOLARPRO_OWNER_PASSWORD` env vars. Old plaintext `SolarAdmin2026!` and `"marc667us"` literals removed; helper `_seed_pwd()` raises `RuntimeError` if env var unset. New passwords generated; pushing to Render via API workflow. Old hash will be replaced on next redeploy (Render has no persistent disk so a fresh seed runs).
- **Phase 0.2 doc creds:** removed `ChangeMe2026!` and `SolarAdmin2026!` references from `CLAUDE.md`. Removed orphaned campaign-portal section. Deleted `.github/workflows/test-admin-entities.yml` (targeted torn-down blueprint).
- **Schedule:** `Desktop\SolarPro_Schedule_2026-06-08.md` is the live work plan. Prior 46-item plan from 2026-06-06 superseded; closure delta tracked at top of new schedule.

---

## 1. Where the app is running RIGHT NOW

| Tier | URL | State | Branch |
|------|-----|-------|--------|
| **Primary host (Render)** | https://solarpro-global.onrender.com | ✅ Live — deploys auto-trigger on push to `master`. Fresh DB on each redeploy (no persistent disk yet). | `master` @ `2ff1481` |
| Legacy host (Railway) | https://web-production-744af.up.railway.app | ⚠️ Stale — Railway auto-deploy stopped picking up new commits. Last successfully deployed: `5aa9761`. | (frozen) |
| Custom domain | https://solarpro.aiappinvent.com | ❌ Railway cert never issued. Not pointed at Render yet. | — |

**Why the host change:** at midday 2026-06-05 Railway's GitHub integration stopped picking up new pushes from `master` for unknown reasons (no logs visible without dashboard access). The campaign-portal backend (`campaign_api.py`) was already shipped to master and needed live execution; we redeployed the same code on the existing Render service via `gh workflow run "Force Render Deploy"`. Render is now the primary host. Railway service is left running but stale.

---

## 2. Today's net change (campaign portal backend added in this repo)

A separate **aiappinvent Sales Campaign Portal** got built today. Its FRONTEND lives in a different repo (`marc667us/campaign-portal`, GitHub Pages). Its BACKEND lives here as a Flask blueprint:

- `campaign_api.py` — REST API mounted at `/api/campaign/*` (admin auth, invite-only signup, per-entity assignments, audit tracking, CORS for the portal origin)
- `patch_campaign_api_registration.py` — binary patch that wires the blueprint into `web_app.py` (preserves CRLF + mojibake per the editing rule)
- `.github/workflows/render-attach-campaign-disk.yml` — disk-attach attempt (failed, Render disk API returned 404)
- `.github/workflows/render-fix-db-path.yml` — set DB_PATH=/app/solar.db (also wrong — `/app` doesn't exist on Render)
- `.github/workflows/render-remove-db-path.yml` — removed DB_PATH so the code default kicks in
- `.github/workflows/test-campaign-login.yml` — login smoke test from a clean runner IP

The campaign portal is documented separately in `memory/project_campaign_portal.md` and `campaign-portal/context.MD`. Treat it as an independent project that just happens to share this Render service.

---

## 3. Active blockers

1. **Namecheap CNAME for `solarpro.aiappinvent.com`** — still pointing at Railway, where the cert never issued. Move it to Render (CNAME → service URL or alias) when next picking up SolarPro work. Same CNAME problem also blocks `campaign.aiappinvent.com` for the campaign portal.
2. **Railway service is dead but billed** — should be paused or deleted to stop any free-tier resource ticking.
3. **Persistent disk on Render** — currently the DB resets on every redeploy. Render disk REST API returned 404 on both PUT and POST to `/v1/services/{id}/disk`. Either find the correct endpoint, switch to a render.yaml IaC definition, or move to Turso/SQLite Cloud (free).
4. **Workflow secret leak** — `render-attach-campaign-disk.yml` accidentally dumps all env values (including `OPENROUTER_API_KEY`, `PAYSTACK_SECRET_KEY`, `SECRET_KEY`) into GitHub Actions logs when it builds the env-vars merge. Rewrite the merge to not echo values.

---

## 4. Things that ARE working

- All existing SolarPro routes (landing, register, login, project wizard, BOQ, reports, admin) — untouched today
- New campaign portal endpoints (`/api/campaign/*`) — verified end-to-end via test workflow
- Auto-deploy on `git push origin master` to Render
- `Force Render Deploy` workflow as a manual re-trigger
- 26/29 admin ops tests (per earlier session state — not re-verified today)
- All 7 panel wattages, 22/22 reports — per memory, not retested today

---

## 5. Latest commits on master (most recent first)

| Commit | What |
|---|---|
| `2ff1481` | (campaign-portal repo) PDF restyle + bigger Open buttons on tabs |
| `dd30c14` | `chore(campaign-api): add /_debug endpoint` |
| `bc5a689` + `ec4726f` + `b95bd1e` | iteration on fix attempts for the Render DB-path issue |
| `b029bf5` | feat(campaign-api): invite-based onboarding + admin approval |
| `33a8ec8` | feat(campaign-api): SaaS auth — email+password login, user mgmt, sessions |
| `7c980f3` | feat(campaign-api): cloud-backed REST API for the GitHub Pages campaign portal |
| `37c432a` | revert(campaign): unbundle campaign portal from SolarPro (initial mistake) |

Pre-today commits (the actual SolarPro work) are unchanged from the prior session — see `memory/project_solar_pv.md` for the prior baseline.

---

## 6. Resume here (next time you work on the SolarPro app)

1. **Re-point `solarpro.aiappinvent.com`** at Render. Add Render's recommended target as CNAME at Namecheap, add the custom domain via Render API workflow.
2. **Decide what to do with the Railway service.** Either re-enable auto-deploy by reconnecting GitHub integration via Railway dashboard, or delete it.
3. **Attach a persistent disk on Render.** Without this, every Render redeploy wipes solar.db — the campaign portal admin must be re-bootstrapped each time. (For the actual SolarPro app, the same disk would persist user accounts, projects, and BOQs.)
4. **Resume the original SolarPro 14-day trial work** on `develop` branch (`163a936`) — deploy to a Render preview environment when you're ready.

---

## 7. What we did NOT touch in SolarPro today

- `web_app.py` — only the 2-line registration injection for the campaign blueprint was added at the top, via binary patch. No SolarPro routes, no shared config changed.
- `solar.db` schema (for SolarPro tables) — only added campaign-prefixed tables alongside
- Any template, static, or `calculation/` file
- Any payment / email config

This means SolarPro behavior is exactly the same as it was at the start of session 2026-06-05.

---

<!-- BEGIN: PROJECT OS CONTEXT (canonical — do not edit in place; re-sync from C:\Users\USER\_project_context_append.md) -->

# Project OS — Context Addendum

This project operates under the **Project Execution Directive** appended to this app's `CLAUDE.md`. See that file for:

- **Session-start rule** (read CLAUDE.md, README.md, this context.MD, all `docs/*.md`, code, tests, infra files BEFORE coding; produce an orientation summary).
- **24 numbered discipline rules** covering scope control · reuse-before-create · architecture pipeline (Router → Service → Repository → DB) · multi-tenant `tenant_id` discipline · PostgreSQL RLS · hidden-page protection · logout-must-really-work · scalability · indexing · caching · queues · AI agent discipline · error handling · audit logging · admin operations · dependency audits · testing · documentation · ADR + implementation-log templates · pre/post-coding checklists.
- **Free / Open-Source Stack Rule** with the full FOSS technology table, cost-control checklist, and low-cost deployment ladder. Paid SaaS only when explicitly approved by the project owner.
- **Codex CLI Pair-Coding Workflow** — Claude implements, Codex reviews; a feature is NOT complete until Codex review passes the 10-item quality gate.

## Canonical Sources

- `C:\Users\USER\Documents\pvsolar1\improvements\dontforget1.txt` — original Project Execution Directive + FOSS Stack Rule
- `C:\Users\USER\Documents\pvsolar1\improvements\thereviewer1.txt` — original Codex pair-coding workflow

If this app's `CLAUDE.md` directive drifts from those source files, re-read them and reconcile.

## Per-Session Orientation Summary (update every session)

Append the latest snapshot here so the next session inherits accurate state. The template:

```
Date:
Current project status:
- Completed modules:
- Partially completed modules:
- Missing modules:
- Current technical risks:
- Next logical task:
- Files likely to be affected:
```

Granular per-task changes go to `docs/IMPLEMENTATION_LOG.md` per the directive's §21.

<!-- END: PROJECT OS CONTEXT -->

---


---

<!-- BEGIN: AGENTIC ADK CONTEXT (canonical — do not edit in place; re-sync from C:\Users\USER\_agentic_adk_context_append.md) -->

# Agentic Development Context Addendum

This project operates under the **Agentic Development Extension** appended to this app's `CLAUDE.md` and elaborated in this app's `MCP.md`. Together they define the three-layer agentic platform every app under this account belongs to.

## What This Extension Adds

- **Google ADK** is the Agent Operating System — it orchestrates business agents (executive, engineering, construction, procurement, finance, healthcare, legal, research, sales, support, technology) across workflows, tools, and memory.
- **HARD RULE — Google ADK is the only agent framework** for every agent in every app. All agent classes, tools, memory, handoffs, and orchestration use ADK primitives. No LangChain / LangGraph / AutoGen / CrewAI / Semantic Kernel / hand-rolled while-loops without an approved ADR. See CLAUDE.md §0.1 for the full rule.
- **HARD RULE — Always start from orchestration; branch into conductors when needed.** Every request enters via a single Root Orchestrator agent (`app/agents/orchestrators/root_orchestrator.py`). The Root Orchestrator routes to department Conductors (`app/agents/conductors/<dept>_conductor.py`) when a branch needs to coordinate ≥2 specialists or non-trivial flow; otherwise it calls a specialist directly. Specialists never call other agents. See CLAUDE.md §0.2 for full branching rules + topology diagram.
- **HARD RULE — Agents and code must be reusable across apps.** Every app is a pip-installable package (`pyproject.toml` at root, `app/` package, `__init__.py` everywhere, `__all__` declaring the public API). Other apps consume agents/tools/schemas either by `pip install -e ../this-app` and importing, or via the MCP mesh (this-app's MCP server registered in the consumer's MCP.md). No copy-paste between apps; no hardcoded paths inside business logic; no cross-department imports between specialists; no business logic in route handlers. Each app maintains `docs/REUSABILITY.md` listing its public exports + consumers. See CLAUDE.md §0.3 for full rules.
- **Claude Code** is the **Software Engineering Agent** living inside the Technology Department. It writes code; it does NOT orchestrate business workflows.
- **Codex CLI + Supervisor** is the pair-coding review lane (existing — see `ai-coworkers/`, `reviews/`, `scripts/`).
- **Governance Agents** — Work Reviewer, Development Supervisor, Work Scheduler — are mandatory in every app and themselves implemented in ADK. They are the project's quality and planning gates.
- **MCP.md** in the app root enumerates the Model Context Protocol servers and how Claude Code connects to ADK for this app specifically.

## The Four Mandatory Quality Gates

Nothing ships until all four pass, in order:

1. **Codex CLI** review via `./scripts/quality-gate.sh`.
2. **Supervisor** sign-off via `/code-review`, `/security-review`, `/verify`.
3. **Work Reviewer Agent** approval (`POST /api/review/work` → status `approved`).
4. **Work Scheduler Agent** marks the task `approved`.

## Canonical Sources

- `C:\Users\USER\Documents\agentic proper2\agenticadk1.txt` — Enterprise AI Agent Factory master prompt
- `C:\Users\USER\_agentic_adk_append.md` — CLAUDE.md template (this extension's full text)
- `C:\Users\USER\_agentic_adk_mcp.md` — MCP.md template
- `C:\Users\USER\_agentic_adk_context_append.md` — this file
- `C:\Users\USER\Documents\pvsolar1\improvements\dontforget1.txt` — original Project Execution Directive + FOSS Stack Rule
- `C:\Users\USER\Documents\pvsolar1\improvements\thereviewer1.txt` — Codex pair-coding workflow

If this app's `CLAUDE.md` extension drifts from those source files, re-read them and reconcile.

## Per-Session Orientation Summary (update every session)

Append the latest snapshot below so the next session inherits accurate state. The template:

```
Date:
Agentic layer status:
- ADK installed:                  yes | no | partial
- Executive Department agents:    list of implemented agents
- Technology Department agents:   list of implemented agents
- Governance agents (Reviewer/Supervisor/Scheduler):  status of each
- Other departments stubbed:      list
- Active MCP servers (see MCP.md): list
- Last governance pipeline run:   pass | fail | not run | path to report
- Next agentic task:
```

Granular per-task changes go to `docs/IMPLEMENTATION_LOG.md` per the Project Execution Directive §21.

<!-- END: AGENTIC ADK CONTEXT -->
