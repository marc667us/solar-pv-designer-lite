# SolarPro Global — Technical Guide
## Engineering basis, standards, and integration reference

**Version:** 2026-06-05 (beta)
**Audience:** Senior engineers, technical leads, and procurement/IT staff at Ghana installer and supplier companies; internal engineering team.
**Companion to:** User Guide (workflow) and Sales Pitch (positioning).

> This document explains **how** SolarPro computes its outputs and **which standards** it follows, so an external engineer can defend any value the platform produces to a client or to a financing bank.

---

## 1. Engineering principles in one page

SolarPro is built on three rules:

1. **Every output is derivable from the inputs.** No "magic" multipliers — every coefficient is listed in this guide or in `assumptions.md`.
2. **Every output is overridable.** Defaults are conservative; the engineer can replace any value with their own.
3. **Every output is traceable.** The proposal PDF shows the calculation path so a reviewing engineer can validate without re-running the tool.

---

## 2. Standards applied

| Standard | Where it's applied | Notes |
|---|---|---|
| **BS 7671 (18th Edition, +A2)** | AC cable sizing, derating, protective device coordination | UK origin; default standard for Ghana commercial/industrial wiring |
| **IEC 62548** | DC string design, MPPT voltage windows, isolation | International PV-array standard |
| **IEC 60364-7-712** | PV-specific installation requirements | Used for protective bonding, isolation |
| **IEC 61730** | Module safety classification | Determines Class II isolation requirements |
| **NEC Article 690** | Fallback for US-style installations | Triggered only when site country = USA |
| **Ghana Energy Commission — Solar PV Code of Practice (2019)** | Permitting checklist on the installation report | Drives the EC-certification section |
| **IEC 61724** | Performance ratio & yield calculation | Drives the economic analysis |

Standards are cited inline in every report so the bank's engineer can verify.

---

## 3. Site assessment

### 3.1 Irradiance

Source: `config/global_solar_data.py` — region-level peak sun hours (PSH) lookup.

For Ghana:

| Region | PSH (kWh/m²/day) | Ambient (°C) |
|---|---|---|
| Greater Accra | 5.2 | 28 |
| Ashanti | 5.0 | 26 |
| Northern | 5.6 | 30 |
| Volta | 5.1 | 27 |
| Western | 4.8 | 26 |

Source data: NASA POWER + Ghana Meteorological Agency monthly means, averaged 2018–2023.

### 3.2 ECG tariff

Region-tagged residential and commercial tariffs sourced from Public Utilities Regulatory Commission (PURC) quarterly publications. Escalation default = 6%/year (BoG inflation forecast).

The engineer can override tariff and escalation in the economic step.

---

## 4. Load analysis

```
Daily energy demand (Wh/day) = Σ(P_i × n_i × h_i × d_i / 7)
```

Where:
- `P_i` = nameplate power of load `i` (W)
- `n_i` = quantity
- `h_i` = hours per day
- `d_i` = days per week (default 7)

A diversity factor is applied to the **peak** load (not the daily energy):

```
Peak (kW) = Σ(P_i × n_i) × DF
```

Where `DF` = 0.65 for residential, 0.85 for commercial, 1.0 for industrial. The engineer can change `DF` per project.

Surge load = peak × 3 (motor start; configurable 2–5×).

---

## 5. PV array sizing

### 5.1 Required peak power

```
P_pv (kWp) = E_daily / (PSH × η_system × δ_temp)
```

Where:
- `E_daily` = daily energy demand (kWh)
- `PSH` = peak sun hours from §3.1
- `η_system` = 0.80 (default) — combined inverter + wiring + soiling
- `δ_temp` = 1 − γ × (T_cell − 25) — temperature derate

Cell temperature: `T_cell = T_amb + 25 °C` (NOCT approximation; configurable).
γ (power temperature coefficient) = −0.0034 K⁻¹ (Tier-1 mono panel default).

### 5.2 Module count

```
N_modules = ceil(P_pv × 1000 / W_module)
```

Where `W_module` ∈ {110, 250, 330, 400, 450, 500, 550} Wp (commit `27b2492`).

### 5.3 String design

For each candidate inverter MPPT range `[V_min, V_max]`:

```
N_series_min = ceil(V_min / (V_mp × δ_T_hot))
N_series_max = floor(V_max / (V_oc × δ_T_cold))
```

Temperature corrections:
- `δ_T_hot = 1 + β_voc × (T_cell_hot − 25)` ≈ 0.88 (Vmp shrinks when panel is hot)
- `δ_T_cold = 1 + β_voc × (T_cold − 25)` ≈ 1.10 (Voc grows when panel is cold)

`β_voc` = −0.0029 K⁻¹ default.

If `N_series_min > N_series_max`, the MPPT panel is incompatible → engine flags WARNING and suggests a smaller-Vmp module or a different inverter.

### 5.4 Mounting derate

| Mounting type | Soiling factor | Temperature uplift (°C) |
|---|---|---|
| `rooftop_pitched` | 0.95 | +5 |
| `rooftop_flat` | 0.90 | +10 |
| `rooftop_metal` | 0.95 | +12 |
| `rooftop_membrane` | 0.95 | +8 |
| `ground_fixed` | 0.92 | +3 |
| `ground_tracking` | 0.95 | +3 |

These factors fold into `η_system` and `T_cell` automatically.

---

## 6. Battery sizing

```
C_battery (Wh) = E_daily × N_autonomy / (DoD × η_inv × η_batt)
```

Defaults:
- `N_autonomy` = 1 day (residential), 0.5 day (grid-tied), 2 days (off-grid critical)
- `DoD` = 0.80 (lithium), 0.50 (gel/AGM)
- `η_inv` = 0.95
- `η_batt` = 0.95 (lithium), 0.85 (lead-acid)

The battery type (lithium / gel / AGM) drives DoD and η_batt. The engineer chooses; the engine reflects the math.

Output is rounded up to the nearest stocked battery module size (5 kWh, 10 kWh, 15 kWh, 20 kWh by default — configurable in Settings → BOQ).

---

## 7. Inverter sizing

```
P_inv (kW) = max(Peak_kW × 1.25, P_pv × 0.85)
```

Two-sided constraint:
- Must handle peak load with 25% margin
- Must absorb at least 85% of PV array output (Ghana standard avoids over-clipping under low PSH)

A hybrid inverter is selected by default for off-grid + battery; grid-tied selects a string inverter.

---

## 8. Cable sizing

### 8.1 DC cable (panel → combiner → inverter)

Voltage drop method (IEC 62548):

```
A (mm²) = (2 × L × I × ρ) / ΔV_max
```

Where:
- `L` = one-way length (m)
- `I` = string current at STC
- `ρ` = 0.0175 Ω·mm²/m (Cu @ 20 °C)
- `ΔV_max` = 1.5% × V_array

Round up to the next standard size (4, 6, 10, 16, 25 mm²).
Verify the result against ampacity at 70 °C ambient — bump up one size if borderline.

### 8.2 AC cable (inverter → DB → load)

Per BS 7671 §523, Table 4D5 (PVC SWA):

| Cable | Current carrying capacity (A) @ 30 °C ambient |
|---|---|
| 2.5 mm² | 24 A |
| 4 mm² | 32 A |
| 6 mm² | 41 A |
| 10 mm² | 57 A |
| 16 mm² | 76 A |
| 25 mm² | 101 A |

Derating applied:
- Ambient temperature factor (BS 7671 Table 4B1) — Ghana ambient 32–35 °C → 0.94
- Grouping factor (Table 4C1) — if more than one cable shares conduit
- Installation method factor (clipped direct vs. conduit)

Final: smallest size whose derated capacity ≥ design current × 1.25.

Voltage drop check: ≤ 3% for final circuits, ≤ 5% combined (per BS 7671 Appendix 12).

### 8.3 Earthing

Earth conductor sized per BS 7671 §544 — half the phase conductor's cross-section, minimum 4 mm² Cu.

Earth rod: 1.2 m × 16 mm Cu — measured resistance ≤ 10 Ω per IEC 60364-7-712.

---

## 9. Bill of Quantities — how it's built

`calc_boq()` traverses the sized system and emits one line per material category:

| Category | Quantity logic |
|---|---|
| Modules | `N_modules` from §5.2 |
| Mounting rails | `ceil(N_modules × 1.05 m / 4.2 m)` — 4.2 m standard rail |
| End clamps | `4 × N_strings` |
| Mid clamps | `2 × (N_modules − N_strings)` |
| MC4 connectors | `2 × N_strings` |
| DC cable | length from §8.1 with 10% wastage |
| AC cable | length from §8.2 with 10% wastage |
| Inverter | `N_inv` |
| Battery modules | `ceil(C_battery / W_battery_unit)` |
| Earth rod | 1 per system |
| Earth conductor | length matches AC cable |
| Surge arrestor (DC) | 1 per MPPT input |
| Surge arrestor (AC) | 1 per phase |
| Isolators (DC) | 1 per string |
| Combiner box | 1 per inverter |
| **Ground mount only** | steel post (1 per 4 modules), concrete footing (1 per post), purlin beam (4.2 m per row), earth rod (1 per 20 modules) |

Pricing:
- Default: blank — engineer types unit cost.
- With supplier integration enabled: pulls live pricing via the supplier's API. Currently scaffolded for Nocheski and Ozo (target Q3 2026).

---

## 10. Economic analysis

### 10.1 Energy yield (per IEC 61724)

```
E_year (kWh) = P_pv × PSH × 365 × PR
```

`PR` (performance ratio) defaults:
- Rooftop residential: 0.75
- Rooftop commercial: 0.80
- Ground mount fixed: 0.82
- Ground mount tracking: 0.86

### 10.2 Cash flow

For year `y` ∈ [1, lifetime]:

```
Savings_y = E_year × (1 − δ_y) × Tariff × (1 + escalation)^(y − 1)
OPEX_y    = OPEX_0 × (1 + 0.03)^(y − 1)
Net_y     = Savings_y − OPEX_y
NPV_y     = Net_y / (1 + discount)^y
```

Where:
- `δ_y` = degradation per year (default 0.5%, lithium battery system; 0.7% pure PV)
- `OPEX_0` = annual maintenance estimate (default 1% of CAPEX)

### 10.3 Headline metrics

- **Payback (years)** — interpolated to the year where cumulative cashflow ≥ 0
- **IRR (%)** — Newton-Raphson on the cashflow vector, tolerance 1e-6
- **NPV (GHS)** — sum of `NPV_y` over lifetime
- **LCOE (GHS/kWh)** — `Σ Costs / Σ Energy`

---

## 11. Reports

Every project produces seven PDF reports, all rendered from the same JSON state:

1. **PV Sizing Report** — array, strings, MPPT match, temperature checks
2. **BOQ** — full materials list with prices
3. **Cable Schedule** — every run with gauge, length, derating, voltage drop
4. **Economic Analysis** — charts + IRR/NPV table
5. **Installation Method Statement** — step-by-step, with safety
6. **Energy Yield Report** — month-by-month projection
7. **Bankable Proposal** — combined cover-page + executive summary + sized excerpts of 1–6

Reports embed the assumptions used (PSH, system efficiency, derating factors) so a third-party engineer can validate without re-running the tool.

---

## 12. Data model (for IT staff)

### 12.1 Storage

Each project's full engineering state lives in a single JSON blob: `projects.data_json`. Schema (abbreviated):

```json
{
  "site": { "country": "Ghana", "region": "Greater Accra", "psh": 5.2, "ambient_c": 28, "tariff_kwh": 1.45 },
  "loads": [ { "name": "Fridge", "watts": 250, "qty": 1, "hours": 12, "days_per_week": 7 } ],
  "totals": { "daily_kwh": 18.3, "peak_kw": 4.1, "surge_kw": 12.3 },
  "results": {
    "pv":     { "p_kwp": 6.0, "n_modules": 12, "w_module": 500, "strings": [...] },
    "battery":{ "kwh": 10, "type": "lithium" },
    "inverter":{ "kw": 5.0, "type": "hybrid" },
    "cable":  { "dc_mm2": 6, "ac_mm2": 4 },
    "boq":    [...],
    "economics":{ "payback_y": 4.2, "irr": 0.27, "npv_25y": 86_200 }
  }
}
```

### 12.2 Export

- **PDF** — `Generate Proposal` button on the project page.
- **JSON** — `GET /api/project/<id>/export.json` (authenticated; returns the schema above).
- **CSV** — `GET /api/project/<id>/boq.csv` (BOQ only).

### 12.3 Re-import

POST a previously exported JSON to `/api/project/import` — recreates the project. Useful for restoring from backup or moving a project between accounts.

---

## 13. Integration points

For supplier and installer companies, three integration surfaces are available during beta:

### 13.1 Pricing API (suppliers)

If you sell panels / inverters / batteries / cables, we'll wire your stock into the BOQ procurement screen. Required from you:
- A REST or GraphQL endpoint returning JSON with `{ sku, name, category, unit_price_ghs, in_stock, lead_time_days }`
- Optional webhook for stock updates

We pull on a 6-hour cadence (configurable). Live unit costs replace blank cells in the BOQ.

### 13.2 Project handoff (installers)

After a designer signs off a project, a `/installer/handoff` webhook fires to your endpoint with the full JSON state. Your project management system picks it up and creates a work order.

### 13.3 Single sign-on (SSO)

If your company uses Google Workspace, Microsoft 365, or any OIDC provider — we support SSO on Business+ plans. Required: client ID + client secret + issuer URL.

---

## 14. Security & compliance

| Control | Implementation |
|---|---|
| Authentication | Username + password; 5-failed-attempt lockout 15 min |
| Session management | HttpOnly Lax cookie; CSRF (`_csrf`) on every POST |
| Database isolation | Per-tenant row-level filters on all user data tables |
| Encryption at rest | Hosting platform-managed (currently AES-256) |
| Encryption in transit | TLS 1.2+ end-to-end |
| Audit log | `audit.log` (JSON-line) — login, project edits, exports |
| Security headers | CSP, X-Content-Type-Options, Referrer-Policy, Frame-Ancestors |
| Data export | Self-serve from Settings → Export (per GDPR Art. 20) |
| Data deletion | Self-serve from Settings → Delete Account |
| Backups | Daily snapshot, 30-day retention |

Reference: `SECURITY.md` in the repo for the full Zero-Trust architecture + RBAC matrix.

---

## 15. Performance & SLA targets (beta)

| Metric | Target | Notes |
|---|---|---|
| Sizing calculation latency | < 30 s | p95 |
| Proposal PDF generation | < 60 s | p95 |
| Uptime | 99.0% | Free Railway tier; will rise to 99.9% on K8s |
| Support response (in-app chat) | < 60 s | Rule-based; AI fallback to Claude/Llama |
| Support response (email) | < 24 h | Business hours |

---

## 16. Where to look in the code (internal staff)

| Concern | File |
|---|---|
| Loads → sizing pipeline | `web_app.py` → `calc_loads` / `calc_pv` / `calc_battery` |
| AC cable sizing | `calculation/ac_cable_sizing.py` |
| DC cable sizing | `web_app.py` → `size_dc_cable` |
| BOQ generation | `web_app.py` → `calc_boq` |
| Economic engine | `web_app.py` → `calc_economics` |
| Global irradiance data | `config/global_solar_data.py` |
| AI helpline | `web_app.py` → `/api/assistant/chat` + `api_manager.py` |
| Email send chain | `api_manager.py` → `_send_email` |
| Structured logging | `logging_config/structured_logger.py` |
| Health endpoints | `web_app.py` → `/api/health*` |

---

## 17. Roadmap (next 90 days)

| Month | Theme | Highlights |
|---|---|---|
| **June 2026** | Beta hardening | Custom domain SSL, multi-tenant edge isolation, screenshots in user guide |
| **July 2026** | Procurement | Nocheski + Ozo pricing live in BOQ, supplier directory page |
| **August 2026** | Energy reporting | Month-by-month yield, Excel export of BOQ, mobile-optimised dashboard |

Feature requests during beta: send to `support@aiappinvent.com` or via in-app chat. Top-3 by demand each fortnight ships on the next sprint.

---

## 18. Engineering changelog (June 17, 2026)

Four mechanical changes shipped to master today. The first three concern the shading dashboard's mathematical contract; the fourth introduces a mount-aware electrical drawing.

### 18.1 Sun-position Bézier — single source of truth

The shading dashboard's central viewport draws a dashed yellow sun-path arc as the SVG path

```
M 60 460 Q 500 -340 940 460
```

a quadratic Bézier with horizon endpoints (60, 460) and (940, 460) and control point (500, −340) so the noon peak sits at (500, 60). The same Bézier coefficients now drive the JS animation:

```js
function sunXY(hour) {
  var t = (hour - 6) / 12;
  var x = (1 - t) * (1 - t) * 60  + 2 * (1 - t) * t * 500 + t * t * 940;
  var y = (1 - t) * (1 - t) * 460 + 2 * (1 - t) * t * (-340) + t * t * 460;
  return { x: x, y: y };
}
```

with `BASE_X = 700, BASE_Y = 70` matching the server-rendered `_sun_x` / `_sun_y` defaults, so the disk's transform `translate(p.x − BASE_X, p.y − BASE_Y)` puts it at `(p.x, p.y)` for every hour. Five visible marker circles sit on the curve at t = 1/12, 3.5/12, 6/12, 8.5/12, 11/12 (07:00, 09:30, 12:00, 14:30, 17:00) — pre-computed Jinja constants so they never drift.

Net: the visible curve and the moving disk are guaranteed to share a single mathematical formula. Any client asking "is your simulation accurate?" can be shown both the SVG path string and the JS coefficients side by side.

### 18.2 Shading-factor precedence chain

The dashboard now reads `_factor` / `_label` / `_loss` from a single ordered precedence:

1. **`shading.factor`** (the saved value written by `_apply_shading_factor`)
2. **`_eng.bucket_factor`** (cached engine block, used only when no save exists)
3. **`1.00`** / `''` / `0` (no-data defaults)

`_apply_shading_factor` (in `web_app.py`) runs the deterministic geometry engine first, falls back to the heuristic agent `_compute_shading_factor` when project context is incomplete, and yields to a manual operator override when the gold-pill Save handler fires. All three write the same `data["shading"]["factor"]` field, so the dashboard now displays the actually-applied value regardless of which source produced it.

When `factor_source == "manual"`, a `· MANUAL` suffix is appended to the displayed label, and the AGENT PICK row highlight in the SHADING_FACTORS table tracks the saved factor rather than the cached engine bucket. The engine block remains in `data["shading"]["engine"]` so the 3D scene still has geometry to render against.

### 18.3 Engine ↔ heuristic snapping parity

Both `engine.shading_engine.SHADING_BUCKETS` and `web_app.SHADING_FACTORS` are the same eight rows (No shading → Very severe shading, 0% → 40% loss, 1.00 → 0.60 factor) with the same conservative snap rule: pick the highest row whose loss% is ≤ the computed loss%. When either path runs alone its output is one of those eight rows, so the visible factor on the dashboard is one of eight discrete values — never a continuous figure. Downstream code (loads / sizing / BOQ) reads only the snapped row.

### 18.4 Directed sun-rays — wide-beam cone-of-light rendering

The shading viewport's sun-rays used to live inside `#svgSunGroup` and translate with the disk, which made them look frozen relative to the array. They have been moved into a sibling `<g id="svgDirectedRays">` group OUTSIDE the sun group, and a new `paintDirectedRays(hour)` is wired into the `paintSun` wrapper chain. Per slider tick the group's `innerHTML` is replaced with a fresh build.

Per illuminated target the renderer stacks three layers in z-order:

1. An OUTER cone polygon `<polygon fill="#fde68a" opacity="0.18">` — apex at the current sun emit point `(p.x, p.y + 22)`, base on the target's plane with half-width 90 px for the PV array and a per-obstruction clamped `Math.max(22, Math.min(bw * 0.55, 60))` for each obstruction.
2. An INNER hot-core polygon `<polygon fill="#fef3c7" opacity="0.22">` at 45 % of the outer half-width.
3. A fan of ray accents `<line stroke="#fbbf24">` on top — 9 lines across the array at ±90 / ±67 / ±45 / ±22 / 0 px (centre 1.8 px @ 0.65 opacity, outer 1.0 px @ 0.38 opacity) and 5 lines per obstruction at relative offsets −1.0 / −0.5 / 0 / +0.5 / +1.0 × that target's beam half-width.

Obstruction geometry is read live from each `[id^="shadow-"]` polygon's `data-base-x` / `data-base-w` / `data-h` attributes, so beams stay in sync with whatever obstruction set the project carries. The group is cleared (`innerHTML = ''`) when `hour < 5 || hour > 19` to mirror the existing `paintShadows` night cutoff. Implementation lives in `templates/shading.html`, function `paintDirectedRays`, immediately above the `paintSun` wrapper.

### 18.5 Installation drawings — mount-aware string routing (Drawing 1B)

The Installation Drawings report (`/project/<pid>/report/installation/drawings`) carries a new Drawing 1B between the existing PV-panel internal-wiring diagram and the battery-bank diagram. One SVG with three Jinja branches keyed on the project's stored `mounting_type`:

| Mount class | Topology rendered | Standards cited |
|---|---|---|
| `rooftop_sloped` (default — pitched, hip, gable, metal, rooftop_pitched, rooftop_metal) | Cables clipped to under-rail tray, EPDM-flashed pitched penetration, IP65 rigid conduit to indoor inverter wall | BS 7671 Method B + 0.85 thermal-insulation factor; §712 PV bonding |
| `rooftop_flat` (flat, membrane, concrete, rooftop_flat, rooftop_membrane) | Galvanised cable tray on ballast stands, parapet transition to UV-rated rigid conduit, drop to plant room | IEC 60364-5-52 tray fill ≤ 40 %, 70 °C PVC; FM 4474 ballast wind-load |
| `ground_*` (ground_fixed, ground_tracking) | IP67 armoured conduit buried ≥ 600 mm, cable draw-pits every 20 m, combiner on equipment shelter | BS 7671 Tab 4D4A buried-cable derating; BS 7430 array-frame bonding |

The diagram is sized from the project's actual `pps` (panels per string) × `num_strings`, colours each string from an 8-step palette (red → orange → yellow → green → blue → violet → magenta → cyan), and draws DC+ red / DC− blue cable paths from the array to the combiner box (fuse + DC isolator per string, IP65 housing, "{N}-in / 1-out") and out to the inverter (MPPT input ceiling annotated). The notes panel adds string-balance, derating, and combiner-termination guidance with BS 7671 §537 lockout requirement.

Implementation: see `templates/report_installation_drawings.html` block "DRAWING 1B" (≈ 150 LOC SVG + 3-column notes panel). All `mt` branches are derived from the lower-cased `mounting_type` string, so any new raw mount value the form might add ("ground_pole", "rooftop_carport", etc.) defaults to the closest-class topology rather than 500'ing.

---

## 19. Screenshots index

The technical guide references the same screens as the user guide:

- `[SCREEN: location-globe]` — for §3 site assessment
- `[SCREEN: loads-input]` — for §4 load analysis
- `[SCREEN: results-pv]` — for §5 PV sizing
- `[SCREEN: boq]` — for §9 BOQ
- `[SCREEN: economics]` — for §10 economics
- `[SCREEN: installation-drawings]` — for §6.4 mounting derate consequences

Capture from the live app, save under `docs/screens/<slug>.png`, rerun the PDF build to embed.
