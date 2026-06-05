# SolarPro Global — Session Context

**Last updated:** 2026-06-05 (end of session, switched to sales-campaign focus)
**Purpose:** capture in-flight state so any session can resume mid-task without re-discovery.

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
