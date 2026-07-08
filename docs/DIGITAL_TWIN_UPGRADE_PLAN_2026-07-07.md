# 3D Solar Farm Digital Twin — Upgrade Plan (2026-07-07)

> Source brief: owner reference docs `farm 3D 5.txt` (primary — engineering digital-twin replacement), `farm 3d updated.txt` (feature checklist), `farm 3d interface updated.png` (visual reference). Plan authored by Codex CLI (gpt-5.5, read-only) against the live code. Target module: Generation Station 3D Digital Twin at `/large-scale-solar/<pid>/digital-twin` (`new_capital_investment_routes_v2.py` + `templates/capital_investment/digital_twin.html`). **Additive only — no rebuild of web_app.py, design/BOQ/finance/marketplace engines, or navigation.**

## Current-State Assessment

### Reusable Server-Side Assets (`new_capital_investment_routes_v2.py`)
- `DT_LAYER_PALETTE` / `DT_LAYER_GROUPS` — layer codes for terrain, fence, roads, buildings, PV rows, inverters, transformers, ICT, lighting, earthing, safety.
- `build_scene_from_project(proj)` — emits a metres-based scene graph, origin at site centre, +X=East, +Z=South, from `pv_config`/`facility_config`/`site_config`/`electrical_config`/`technology_config`.
- `_ci_normalize_proj_for_agents()` mirrors v2 `technologies/services` into `selected`.
- Routes already exist and are login + paid-gated: `/digital-twin`, `/dt/scene.json`, `/dt/sun.json`. Tenant/user scoping via `_load_project(pid)`.

### Reusable Client-Side Assets (`digital_twin.html`)
- Three-pane layout (layer nav / viewport / property panel / bottom timeline).
- Vendored Three.js **r147 UMD** (`/static/vendor/three-r147-umd/…`) — no build step.
- Terrain plane, box buildings/PV rows/inverters, mast cylinders, fence segments, roads; layer toggles; raycast click selection; sun timeline; bird's-eye + perspective cameras; electrical-flow pulse; PNG screenshot.

### Gaps vs Owner Spec
- PV field is row-level only; modules/tables aren't independent logical objects; no instancing/LOD.
- No stable object schema for behaviour/editability/links/simulation/quantities/dependencies.
- Parameter changes don't round-trip into project engines without page refresh.
- `_sun_position` is simplified **and duplicated twice** in the file; no longitude/timezone/refraction/sunrise/sunset.
- Shadows are visual-only — no affected-row/module attribution or loss model.
- Selection is click-only (no hover/context-menu/lock/hide/delete/duplicate/drag/snap).
- Simulation modes don't change camera/layers/labels/analytics; no object-library abstraction; all logic inline.
- No graphics tiers / perf budget / 100MW stress handling; no client state model; no digital-twin tests.

## Target Architecture

### Additive file structure (no `web_app.py` edits)
Primary: `new_capital_investment_routes_v2.py`, `templates/capital_investment/digital_twin.html`.
New client modules under `static/capital_investment/dt/`: `dt-state.js`, `dt-scene-builder.js`, `dt-materials.js`, `dt-selection.js`, `dt-sun.js`, `dt-cameras.js`, `dt-simulation-modes.js`, `dt-exports.js` (+ later `dt-ai-actions.js`, `dt-shadow-analysis.js`, `dt-parameter-panel.js`). New routes go **inside** `register_capital_investment()` (no route splice needed).

### Scene graph contract — version it now (`schema_version: "dt_scene_v2"`)
Top-level: `site`, `camera`, `layers`, `materials`, `objects[]`, `collections`, `links`, `simulation`, `performance`. Each object: `id`, `type`, `layer`, `label`, `kind`, `transform`, `dimensions`, `render` (material/lod/instanced/shadows), `engineering` (editable/locked/quantity/capacity/dependencies), `links` (boq/financial/marketplace/maintenance/datasheet), `simulation` (shadow_loss/irradiance/warnings), `meta`. Legacy arrays (`pv.rows`, `buildings`, …) preserved during migration.

### Client state model
Single `DTState` object (projectId, sceneData, selection/hover, hiddenLayers, lockedObjects, simulationMode, sun, graphicsTier, dirtyParams, objectIndex, three refs) — no scattered globals.

### Server round-trip strategy
- **Client-preview** (no server): camera, layer visibility, labels, time slider, hover/select, AI highlights, drag preview.
- **Server-authoritative**: PV capacity, module W, row spacing, tilt, azimuth, inverter count/type, transformer location, battery size, facility toggles → via new `POST /dt/parameters`, `POST /dt/object-action`, `GET /dt/links/<id>`, `GET /dt/shadow-analysis.json`. All inherit `_gate(CI_LEVEL_FULL)` + `_load_project(pid)` + user scoping.

## Phased Delivery (each independently shippable + Codex-reviewable)

| Phase | Title | Effort | Core deliverable |
|---|---|---|---|
| **1** | Scene Graph v2, vendored-loader cleanup, instanced PV rows | **M** | Stable `dt_scene_v2` object schema; extract inline JS → `dt-state/scene-builder/materials.js`; instanced/merged PV geometry; `tests/test_digital_twin_scene_graph.py`. Preserves all current behaviour. |
| **2** | Engineering selection, details panel, object links | M | Hover + selection outline; right-panel identity/dimensions/quantities/warnings/links; right-click context menu; BOQ→step9, finance→step8, marketplace→`/marketplace?cat=…` (existing routes only). |
| **3** | Live parameter panel + server-authoritative refresh | **L** | Left "Design Parameters" panel; `POST /dt/parameters` updates project JSON via existing storage, returns fresh scene+summary; tenant-isolation security test. |
| **4** | Camera presets, simulation modes, timeline UX | M | 14 camera presets + 9 sim modes (change layers/labels/lighting/analytics, not just labels); VR cards move camera; consolidate the two `_sun_position` defs; additively extend sun payload (declination/hour-angle/sunrise/sunset/solar-noon/tz). |
| **5** | Shadow severity + loss attribution | **L** | `GET /dt/shadow-analysis.json`; bounding-box shadow projection → per-row severity (none/light/moderate/heavy) + loss% + caused-by; heatmap panel. Row-level first (never 181k module objects). |
| **6** | Object actions, drag preview, AI recommendation hooks | **L** | `POST /dt/object-action` (move_transformer / increase_row_spacing / hide / lock / …); AI recs block with "Apply" → server rebuild; drag persists only on confirm; `boq_dirty`/`finance_dirty` flags. |
| **7** | Rendering quality, object library, graphics tiers | M/L | Material library + PBR (`MeshStandardMaterial`); Low/Medium/High tiers; object-library factories; distance-culled labels. Data-driven, no per-module meshes. |
| **8** | Engineering exports + report hooks | M | Keep PNG; add scene-JSON, BOQ-linked object schedule, shadow-analysis export; technical report links to existing **Step 13** (no parallel report engine). |

## Performance Plan (target 100MW ≈ 181k modules)
Never one-mesh-per-module. LOD: site→rows/table blocks, medium→instanced tables, close→instanced module detail near camera only. `InstancedMesh` for repeated PV tables/poles/posts; raycast against proxy meshes; layer-group visibility toggles; frustum culling; distance-based labels; debounce slider ops; rebuild only changed groups; cache geom/materials by type; pixel ratio capped `min(dpr, 1.5)`. Tiers — Low: row-level, no shadows, dpr 1, 45–60 FPS · Medium (default): instanced tables, shadows on majors, dpr 1.5, 30–60 FPS · High: enhanced materials + labels + higher shadow map, 30 FPS. Server: keep `build_scene_from_project()` deterministic; memoize layout helpers; shadow analysis row-level; return aggregate instance batches for large scenes.

## Risk Register
| Risk | Sev | Mitigation |
|---|---|---|
| Three.js load reliability on Render | High | Vendored JS only; keep UMD fallback; smoke-test script availability. |
| 181k-module performance | High | Row/table instancing, proxy picking, LOD, tiers; never per-module meshes by default. |
| Corrupting `web_app.py` | High | Do not edit it — all route work in `new_capital_investment_routes_v2.py`; CRLF byte-patch only if a separate module is unavoidable. |
| Duplicate BOQ/finance engines | High | Link/call existing Step 8/9/10/13 only; mark summaries dirty where recompute unsafe. |
| Schema migration breaking current page | Medium | Preserve legacy arrays while adding `objects`; migrate renderer gradually. |
| Sun/shadow accuracy expectations | Medium | Extend `_sun_position` additively; label Phase 5 loss as engineering estimate until validated. |
| Client edits mistaken as persisted | Medium | Separate preview vs server-authoritative state; explicit apply/save. |
| Tenant/auth regression on new endpoints | High | Every route inside `register_capital_investment()` using `_gate()`+`_load_project()`; security tests. |

## Explicit Non-Goals
Do not rebuild web_app.py / design engine / BOQ-BOM / marketplace / financial modelling / CRM / AI agents / payments / auth / navigation / project wizard. No paid engines/assets/commercial APIs/unreliable CDNs. No static-image viewport. No hardcoded dashboard numbers. No "bankable PVsyst-grade shading" claim before validation.

## Recommended First Phase
**Start with Phase 1.** It is additive, low-risk, preserves existing behaviour, and creates the stable object schema + modular renderer + scalable PV rendering that every later phase (selection, parameters, sim modes, shadow attribution, AI actions, exports) depends on.
