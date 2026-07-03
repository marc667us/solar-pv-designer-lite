# Generation Station rebuild — review brief & follow-ups (2026-07-03)

Prepared for the owner's review + Codex session. Nothing here has been deployed
beyond the rebuild itself; the items below are **decisions/cleanup for you to
weigh**, not applied changes.

## 1. What shipped (live)

Clean-room REBUILD of the `/large-scale-solar` "Generation Station" module,
replacing the old implementation. Live tip **`cdfe4a6`** (deployed via *Force
Render Deploy* run 28671512922; `/api/version` confirms `cdfe4a6c006e`).

- Same `register_capital_investment` entrypoint → **web_app.py unchanged**.
- Full 14-step wizard + Regulatory bolt-on + 3D Digital Twin + 13 report PDFs +
  15 rule-based AI agents.
- Reuse discipline held: BOQ auto-build via `web_app._ci_autobuild_floor_items`,
  CRM mirror via `_capture_pipeline_lead` (opportunities also hit
  `/admin/pipeline`), reconciliation via `_ci_boq_actuals`, PDFs via
  `markdown-pdf`. No platform engine was reimplemented.
- Postgres-safe: every id-needing INSERT uses `RETURNING id`; schema helpers run
  per-statement on PG.
- Source of truth is `new_capital_investment_routes.py` (the swap copied v2 into
  it). Pre-swap backup: `new_capital_investment_routes_pre_v2swap_20260703.py`.
  Working copy kept as `new_capital_investment_routes_v2.py`.

**Gate status:** Codex reviewed v2 → **APPROVE** (after fixing its two findings:
persist `tenant_id` on the opportunity INSERT; scope agent-run reads by
`user_id`). Local swap-harness: **132/132** checks. Live E2E suite (KC PKCE login
as owner): **login + Steps 1–8 = 21/21**, **Step 9 + Steps 10–14 + DT + regulatory
= 19/19** — all 13 report PDFs valid, agents score, twin JSON serves, Ghana
framework renders.

Re-runnable live suites:
- `tmp/live_generation_station_suite_2026-07-03.py` (login → create → all steps)
- `tmp/live_gs_resume_tail_2026-07-03.py` (`RESUME_PID=<id>` → steps 9–14 + DT + reg)
- Local: `tmp/ci_rebuild_swap_phases_2to10_2026-07-03.py` (in-process swap, 132 checks)

> **Keycloak warm-up:** KC (`auth.aiappinvent.com`, Render free) spins down after
> ~15 min idle. Before any live login test, loop
> `curl .../realms/solarpro/.well-known/openid-configuration` until `200`
> (cold start can take >90 s). Log in with the **email**, not the short username.

## 2. FINDING — Step 9 BOQ auto-build vs. the free-tier worker timeout — ✅ RESOLVED (A + C shipped)

> **Update 2026-07-03:** Mitigations **A + C** are now implemented, Codex-approved
> (VERDICT: APPROVE, one LOW operational-tradeoff note on the raised timeout), and
> deployed. Details:
> - **A** — `Procfile` now `--workers 1 --timeout 300 --graceful-timeout 30`
>   (was `--timeout 120`). A normal generate completes instead of being killed.
> - **C** — `new_capital_investment_routes.py` step 9 caps synchronous
>   pre-pricing at `_CI_MAX_AUTOBUILD_FLOORS` (default **6**, env override
>   `CI_MAX_AUTOBUILD_FLOORS`). Floors beyond the cap stay **fully linked**
>   (buildings + floors + `capital_investment_boq_links`) but unpriced; a flash
>   tells the user to finish them with BOQ *Build-all*. So even a 10+ facility
>   campus can never hang the sole worker.
> - Verified: 132/132 swap harness (unchanged) + focused cap test
>   (`tmp/ci_step9_autobuild_cap_test_2026-07-03.py`, `CI_MAX_AUTOBUILD_FLOORS=1`,
>   2 facilities → both floors/links kept, exactly one priced, correct flash).
> - **B** (`--workers 2`) intentionally NOT taken on the free tier (OOM risk).
>   **D** (background the autobuild) remains available if a future campus routinely
>   exceeds 6 facilities and the deferred-floor UX proves annoying.
>
> Original analysis retained below for context.



**Observed:** generating the BOQ for a 3-building project on live momentarily
**503s the whole site**. Root cause: `Procfile` runs `gunicorn --workers 1
--timeout 120`; the synchronous per-building × per-section item inserts (already
lean at `_CI_MAX_ITEMS_PER_SECTION = 1`) exceed 120 s of free-tier PG round-trips,
so gunicorn kills the sole worker → follow-on requests 503 until it restarts.

**Not a correctness bug:** the `boq_project_id` is claimed atomically *before* the
autobuild loop, so the BOQ **does link** even when the worker dies mid-build — the
user can open it and finish with *Build-all*. The problems are (a) a 503 blip for
concurrent users and (b) some floors miss their pre-priced starter rows.

**Mitigation options (pick in the Codex session):**

| # | Option | Effort | Risk | Notes |
|---|---|---|---|---|
| A | Raise `Procfile` gunicorn `--timeout` to 300 | 1 line | Low | Stops the worker-kill; but a slow request still monopolises the single worker (others wait, don't 503). Cheapest safety net. |
| B | `--workers 2` on the free tier | 1 line | **Med (OOM)** | 512 MB may not hold two Python workers + the app; would need memory headroom check. Best paired with a paid tier. |
| C | Cap synchronous autobuild to the first N floors; link the rest and prompt *Build-all* | ~30 min in v2 step9 | Low | Keeps every request fast; slight UX change (not all floors pre-priced). Pure v2 change, no web_app edit. |
| D | Background the autobuild (thread/queue) and redirect immediately | ~1–2 h | Med | Cleanest UX; free tier has no Celery, so a thread + status poll. More moving parts. |

**Recommendation:** ship **A** now (trivial safety net) and design **C** as the
real fix (fast request + explicit Build-all for large campuses). Avoid B on free
tier. A + C together fully remove the 503 window without infra spend.

## 3. Housekeeping — dead flat templates (safe cleanup, verified)

Phase 0 of the rebuild **copied** (not moved) the 20 old flat
`templates/capital_investment_*.html` into `templates/_retired_capital_investment_20260703/`.
v2 uses the new `templates/capital_investment/` subdirectory. Verified **0 active
`render_template` references** to the flat files anywhere in the live code paths.

Safe cleanup when you're ready (not done yet — left for your review):
```bash
git rm templates/capital_investment_*.html
# optionally also drop the _retired_ archive + the *_legacy_/*_pre_v2swap_ backups
```

## 4. Test data left on live

The live E2E suite created real projects named
**"LIVE SMOKE TEST - Generation Station (delete me)"** (e.g. pid 16). There is no
delete route in v2, so they persist. Purge when a delete/admin path exists, or add
a small owner-only delete route (candidate v2 follow-up).

## 5. Backlog status (unchanged — mostly owner-gated)

From `outstanding_work_schedule` memory — none newly actionable without you:
- **2026-07-03 FK VALIDATE mig 021** and **Phase B mig 005** — owner-run DDL on
  live PG (`gh workflow run ...` with the `confirm=` field). Not run.
- Owner blockers #1–5 (LLM chain / `.env` sync / RLS close-out / observability VPS
  / paid Gemini key) — all need owner action.
- Item **G** (bulk back-fill `voltage_v`/`frequency_hz` on 437+ marketplace
  products) is the one non-blocked engineering task; it writes live product data,
  so best run as a reviewed GH Action, not silently.

## 6. Rollback (if the rebuild ever needs reverting)

1. `cp new_capital_investment_routes_pre_v2swap_20260703.py new_capital_investment_routes.py`
2. `git commit` + `git push` + `gh workflow run "Force Render Deploy"`
   (or `git revert cdfe4a6` then deploy).
   web_app.py import is unchanged either way.
