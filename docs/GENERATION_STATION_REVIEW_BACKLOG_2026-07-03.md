# Generation Station — owner review backlog (2026-07-03)

Captured live during the owner's QA pass of the Generation Station BOQ / cost
output. Ordered by dependency, not by when it was raised.

## The blocker that contaminates the rest

**B0 — BOQ generate crashes / truncates because the live worker timeout is 120s.**
Render ignores the `Procfile`; the service runs an explicit start command
`gunicorn … --workers 1 --timeout 120`. A heavy BOQ generate exceeds 120s, so
gunicorn SIGKILLs the sole free-tier worker mid-build. Symptoms the owner saw:
- "app crashed on generate boq" / "page cannot be reached" (worker died → 503).
- "sections of BOQ truncated or missing" (build didn't finish → partial rows).
- Possibly also odd/again item numbering (partial section fill).

**Fix (staged, needs owner authorization to run):** `Update Render Start Command`
workflow (`b80185c`) → PATCH startCommand to `--timeout 300 --graceful-timeout 30`
→ redeploy. See [[feedback-solar-render-procfile-ignored]].

> **Until B0 is applied, BOQ content review is unreliable** — a missing section or
> broken numbering may be a truncation artifact, not a real defect. Sequence:
> apply B0 → regenerate a clean BOQ → then judge B2/B3 for real.

## Content findings (validate AFTER B0 + a clean regenerate)

**B2 — Sections truncated / missing.** Confirm whether any section is genuinely
absent once a generate completes cleanly. Note the current design is a *lean
starter* (`_CI_MAX_ITEMS_PER_SECTION=1`, one representative line per section) +
the new large-campus floor cap (`_CI_MAX_AUTOBUILD_FLOORS=6`, over-cap facilities
linked-but-unpriced) — both are intentional and expand via BOQ "Build-all". If the
owner wants full pre-pricing, revisit those caps (needs the timeout headroom B0
buys).

**B3 — Item numbering within each BOQ section.** Verify numbering is per-section
(1,2,3… restarting each section) and contiguous with no gaps/dupes across
buildings/floors. Check the display template + the autobuild item write path.

## Feature requests

**F1 — BOQ breakdown modes.** Today the Generation-Station BOQ is organized *by
service* (electrical / ICT / security). Add options to view/generate **by
building (facility)**, **by external works**, and **by rooftop**, each **with its
sections**. Data already supports it: `boq_floor_items` carries `building_id`
(→ facility via `boq_buildings.purpose_subtype`), `floor_id`, `service`, `section`.

**F2 — Cost Plan Deck (new consolidated, exportable report).** One deck that:
- Cost breakdown viewable **by building OR by service**, all **with sections**.
- **Infographics** interpreting **cost distribution** (e.g. share by building,
  by service, by section; top cost drivers).
- **Cash flow** projection — currently missing; pull from Step 8 finance
  (CAPEX/OPEX/revenue over project life, cumulative cash flow, payback).
- **Export** as a report (PDF via markdown-pdf, matching the existing 13 reports;
  charts embedded as images).
- **Excel export split by service**: one worksheet per service (section) as tabs
  at the bottom of the workbook, so a large BOQ (a 2-building starter already has
  ~67 sections) stays manageable instead of one giant sheet. Plus a summary tab.
- Deck is derived from **the BOQ + the project** (owner: "must be based on the boq
  and the projects") — no parallel costing.
- Reuse: `_ci_cost_plan` (NEW shared aggregation engine, built + tested
  2026-07-03: pivots `boq_floor_items` by building / by service-section / floor
  with per-section itemised lines + cost distribution — `tmp/ci_cost_plan_engine_test_2026-07-03.py` 13/13),
  `_ci_boq_actuals` (per-facility totals), Step 8 `finance.computed`
  (NPV/IRR/cashflow), existing PDF + xlsx pipelines.

**F3 — 3D simulation: real + findable.** (a) Discoverability — the 3D Digital
Twin *works* but is a small button at the bottom of the overview; make it
prominent. (b) Owner: "the 3d must 100% real in 3d" — the twin must render as a
genuine, realistic 3D model (actual panel rows / inverters / buildings / terrain
in three.js), not a flat/placeholder view. Audit `build_scene_from_project` +
`digital_twin.html` and upgrade the geometry/materials/lighting as needed.

**F4 — Solar generation yield visualisation.** Owner: yield "by day, month and
annual over 10 years, years for the annual only". Charts:
- **Daily** — representative clear-day hourly generation curve.
- **Monthly** — 12-month distribution (latitude-aware).
- **Annual over 10 years** — annual yield with module degradation (the 10-year
  horizon applies to the annual series only).
Engine BUILT + tested 2026-07-03: `_ci_yield_profile(pv_cfg, gps_lat, years=10)`
derives all three from the Step-7 sizing (monthly via extraterrestrial clear-sky
model; annual series with degradation). Unit-verified: monthly sums to annual,
year-10 = 95.6% at 0.5%/yr, daily 24h midday-peaked. Feeds the Cost Plan Deck
(F2) and the Digital Twin (F3). Wire into charts next.

## Progress (local, tested, awaiting deploy)
- ✅ **B0** timeout fix — LIVE (`b80185c`).
- ✅ **Cost Plan Deck page** built (`/large-scale-solar/<pid>/cost-plan`): KPI strip +
  5 tabs (Overview / By Building / By Service / Yield / Cash Flow) with inline-SVG
  charts (cost distribution, daily/monthly/10yr yield, cash-flow + cumulative).
  Reuses `_ci_cost_plan` / `_ci_yield_profile` / `_ci_cashflow_plan` + `_svg_*`
  helpers. Linked from the project overview. Route test 12/12.
- ✅ **Calculation review** (Codex) — no critical/high; all refinements applied
  (PV dc_basis consistency, polar yield model, debt-ratio clamp, IRR boundary,
  MC percentile, degradation guards). Verified.
- ✅ **Check all / Uncheck all** on Facilities / Technology / Electrical, with
  sub-item cascade (buildings -> `sub_*`).
- ⏳ Remaining: PDF + per-service-sheet Excel export of the deck; real-3D twin
  upgrade; F1 explicit external/rooftop views; B2/B3 re-verify on live.

## Suggested execution order
1. **B0** — apply the timeout fix (owner OK) → stops crash + truncation.
2. **Regenerate** a clean BOQ → validate **B2**, **B3**.
3. **F1** BOQ breakdown modes (by building / external / rooftop).
4. **F2** Cost Plan Deck (breakdown + charts + cash flow + export).
5. **F3** 3D twin discoverability (quick).

All feature work goes through the four gates (Codex → Supervisor → Reviewer →
Scheduler) and deploys in batches, not silently.
