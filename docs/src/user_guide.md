# SolarPro Global — User Guide
## End-to-end workflow for pv solar designers in Ghana

**Version:** 2026-06-05 (beta)
**Audience:** Solar engineers, designers, project leads — at installer and supplier companies.
**Production URL:** https://web-production-744af.up.railway.app
**Custom domain (provisioning):** https://solarpro.aiappinvent.com

> Screens are referenced as `[SCREEN: page-name]`. Live screenshots are attached at the end of this document. If a screen has changed since this PDF was issued, the live app is always the source of truth.

---

## 1. What SolarPro Global does for you

SolarPro Global takes you from blank page → bankable proposal in a single web workflow.

| Step | What it does | Time |
|---|---|---|
| 1. Site assessment | Pulls solar irradiance, ECG tariff, currency, weather profile for the prospect's region | 30 s |
| 2. Loads | You enter what the customer wants to power. We calculate daily Wh demand. | 2 min |
| 3. PV sizing | Computes array size, panel count, string layout, MPPT match | auto |
| 4. Battery + inverter | Sizes battery autonomy + inverter rating against your loads | auto |
| 5. Cable design | Sizes AC + DC cables per BS 7671 and IEC 60364 | auto |
| 6. BOQ | Generates a full bill of quantities — panels, structures, fittings, cabling | auto |
| 7. Economic analysis | Payback, IRR, NPV, lifetime savings in Cedis | auto |
| 8. Reports | 7 bankable reports as one branded PDF | 30 s |

Total: a project that used to take 4–6 hours in Excel now takes 20–30 minutes in SolarPro.

---

## 2. Getting started

### 2.1 Create your account

1. Open https://web-production-744af.up.railway.app
2. Click **Get Started** (top right).
3. Fill the registration form:
   - Username (you'll log in with this — not your email)
   - Email
   - Password (8+ chars)
   - Company name
   - Country = Ghana
4. Click **Create Account**.
5. Check your email for the welcome message (sender: `sales@aiappinvent.com`). It contains your trial expiry and quick-start tips.

`[SCREEN: register-form]`

### 2.2 Free trial

Every new account starts a 14-day free trial of the Professional plan. You can:
- Create unlimited projects
- Generate all 7 reports per project
- Export PDF + JSON

No credit card. At the end of 14 days you choose a paid plan or downgrade to free (which keeps your account but limits you to 1 active project).

### 2.3 Log in

- Field is **Username**, not email — easy to forget.
- If you get locked out (5 wrong passwords = 15-minute lockout) wait it out; do not reset unless you actually forgot.

`[SCREEN: login]`

---

## 3. The dashboard

After login you land on your dashboard.

`[SCREEN: dashboard]`

What you see:
- **My Projects** — every project you've created, newest first. Click a row to open it.
- **+ New Project** button — top right.
- **Trial countdown** — how many days left of the 14-day Professional trial.
- **Recent reports** — quick-open links to your last 5 generated PDFs.
- **Support** — bottom-right floating chat icon → AI assistant (rule-based + Claude/Llama fallback).

---

## 4. Creating a project (3 minutes)

### 4.1 Project basics

Click **+ New Project** and fill:

| Field | Example | Notes |
|---|---|---|
| Project name | "Kasoa Residential — 5 kW" | Any text |
| Client name | "Mr. Mensah" | Shown on the proposal cover |
| Site type | Residential / Commercial / Industrial | Drives default parameters |
| Country | Ghana | Locks in ECG tariff + Cedi |
| Currency | GHS (auto) | You can override |

`[SCREEN: project-new]`

Click **Create** — you go straight to the Location step.

### 4.2 Location

This is where the engineering starts. You set the site latitude and longitude. Two ways:

**Globe pick** — the rotating 3D globe shows Ghana. Click your region — a green dot appears. The system reads:
- Peak Sun Hours (PSH)
- Mean ambient temperature
- ECG tariff zone
- Currency

`[SCREEN: location-globe]`

**Address search** — type "Madina Accra" or "Kasoa" and pick from the dropdown. Same data populates.

**Valid Ghana regions:** Greater Accra, Ashanti, Northern, Volta, Western. Pick the closest one — region picks the irradiance profile.

Click **Save & Continue.**

---

## 5. Loads — telling the system what to size for

This is the most important step. Garbage in = wrong system out.

### 5.1 Two ways to enter loads

`[SCREEN: loads-input]`

**Method A — Appliance picker** (recommended for residential):
- A list of common Ghanaian household appliances: fridge, fan, TV, LED bulb, water heater, AC, water pump.
- Click an appliance → enter quantity + daily usage hours.
- The system fills wattage from a standard catalogue (you can override).

**Method B — Direct entry** (recommended for commercial/industrial):
- Paste rows from Excel: `Load name | Wattage (W) | Quantity | Hours/day | Days/week`
- One row per load. Up to 200 loads per project.

### 5.2 What the system computes from loads

- **Connected load (kW)** = Σ(W × Qty) ÷ 1000
- **Daily energy demand (kWh)** = Σ(W × Qty × Hours ÷ 1000) × Days/week ÷ 7
- **Peak load (kW)** = largest simultaneous load (used to size inverter)
- **Surge load (kW)** = peak × 3 (motor-start margin; configurable)

These four numbers drive every downstream calculation.

### 5.3 Mounting type

Pick before continuing — it changes the BOQ and the installation drawings.

| Value | When to pick |
|---|---|
| `rooftop_pitched` | Most Ghanaian residential — IBR / tiled roofs |
| `rooftop_flat` | Concrete slab roofs (Accra commercial) |
| `rooftop_metal` | Aluzinc warehouse roofs |
| `rooftop_membrane` | Modern commercial flat membrane |
| `ground_fixed` | Land available, no tracking — most cost-effective utility |
| `ground_tracking` | Land + budget for single-axis tracking |

Ground-mount selections add steel post, concrete footing, purlin beam, and earth rod to the BOQ.

Click **Calculate Sizing**.

---

## 6. PV sizing — what the engine returns

`[SCREEN: results-pv]`

Inside 30 seconds you get:

| Output | Example | Sizing basis |
|---|---|---|
| Required PV array | 6.0 kWp | Daily demand ÷ (PSH × system efficiency) |
| Panel selection | 12 × 500 Wp mono | Closest standard size; you can change to 110/250/330/400/450/500/550 Wp |
| String layout | 2 × strings of 6 panels in series | Matches inverter MPPT voltage window |
| Battery autonomy | 10 kWh, 1 day autonomy | Daily demand × autonomy × depth-of-discharge factor |
| Inverter rating | 5 kW hybrid | Peak load × oversize factor |
| MPPT match | OK / Warning | Vmp string × 1.25 ≤ Inverter Vmax |
| AC cable | 4 mm² × 25 m | BS 7671 derating per ambient temp |
| DC cable | 6 mm² × 30 m | IEC 62548 voltage drop ≤ 1.5% |

Click **Edit Parameters** to override any value (e.g. force 330 Wp panels if that's what your supplier stocks).

Click **Continue to BOQ** when satisfied.

---

## 7. Bill of Quantities (BOQ)

`[SCREEN: boq]`

The BOQ lists every part needed to build the system. Sections:

- Panels — make, model, Wp, qty, unit cost, total
- Inverter(s) — model, rating, qty
- Batteries — type (lithium/gel/AGM), kWh, qty
- Mounting hardware — rails, end clamps, mid clamps, MLPE if any
- Cabling — AC + DC, by gauge and run length
- Protective devices — MC4 connectors, fuses, surge arrestors, isolators, combiner box
- Earthing — rods, conductors, bonding clamps
- Mounting (ground) — steel post, concrete footing, purlin beam (only if ground mount)

You can:
- **Override prices** — click any unit cost, type your supplier's price.
- **Add line items** — for items not auto-generated (gravel, transport, labour).
- **Save as template** — re-use this BOQ structure for similar projects.

The total flows into the economic analysis automatically.

---

## 8. Economic analysis

`[SCREEN: economics]`

Inputs are pre-filled from the project; you can override:

| Input | Default | Override when |
|---|---|---|
| Tariff (GHS/kWh) | ECG residential rate for the region | Customer is on commercial tariff |
| Tariff escalation (%/year) | 6% | You have a more conservative number |
| Discount rate (%) | 12% | Customer's actual cost of capital differs |
| Project lifetime (years) | 25 | Customer requires a shorter horizon |

Outputs:
- **Simple payback (years)**
- **IRR (%)**
- **NPV at year 25 (GHS)**
- **Lifetime savings (GHS)**
- **First-year energy yield (kWh)**
- **CO₂ avoided (tonnes/year)**

Graph: annual cumulative cash flow — payback point clearly marked.

---

## 9. Installation report + drawings

`[SCREEN: installation-drawings]`

This report is for the install crew. It includes:

1. **Method statement** — step-by-step install sequence
2. **Mounting drawings** — top-down layout, side elevation
3. **Single-line diagram** — DC + AC + battery + grid
4. **Earthing diagram**
5. **Cable schedule** — every run, gauge, length, route
6. **Risk assessment** — working at height, electrical isolation, fall arrest
7. **Tools and materials checklist**

For ground mount, additional drawings show steel post depth, footing dimensions, and purlin beam spacing.

---

## 10. Generating the proposal PDF

`[SCREEN: proposal]`

From the project header, click **Generate Proposal**.

The proposal PDF includes:
1. Cover page (your logo, client name, project name, date)
2. Executive summary (system size, cost, payback)
3. Site assessment + irradiance map
4. Sizing summary
5. BOQ
6. Economic analysis with chart
7. Installation method + drawings
8. Terms & conditions (editable template)

PDF generates in ~30 seconds. Sender on the email-the-PDF flow: `sales@aiappinvent.com` (you can change to your own SMTP in **Settings → Email**).

---

## 11. Tips that save time

| Tip | Why |
|---|---|
| **Save common appliance lists as templates** | A typical Ghanaian 3-bed home uses the same 12 loads — set it up once. |
| **Override panel size to match what you stock** | Avoids quoting a panel the customer will ask you to swap. |
| **Use the AI helpline (floating chat)** | It can pre-fill standard cable runs, suggest mounting layouts, and explain any error. |
| **Export JSON before deleting a project** | One JSON file = whole project. Future restore is one upload. |
| **Bookmark the dashboard** | Direct URL skips the landing redirect. |

---

## 12. Support

- **In-app:** click the chat icon (bottom-right) — answers in 2 seconds.
- **Email:** support@aiappinvent.com (24-hour SLA during beta).
- **Phone (beta only):** see the email signature on your welcome mail.
- **Status page:** `/admin/operations` shows live system health if you have admin rights at your company.

---

## 13. Account settings worth knowing

| Setting | Where | What it changes |
|---|---|---|
| Company logo | Settings → Profile | Appears on every proposal PDF |
| Default tariff escalation | Settings → Defaults | Saves re-typing on each project |
| Default panel make/model | Settings → BOQ | Pre-fills BOQ from your supplier |
| API key for procurement integration | Settings → Procurement | Pulls Nocheski / Ozo live pricing into BOQ |

---

## 14. Frequently asked

**Can my customer log in and see their proposal?**
Yes — under Project → Sharing, click "Create client link". Read-only, expires in 30 days unless you renew.

**Can I have multiple users at my company?**
Yes — on Professional plan or higher. Settings → Team → Invite. Each user has their own login but you share projects.

**Does it work on mobile?**
The dashboard and proposal viewing work well on phone. Sizing input is easier on a tablet or laptop because of the side-by-side panels.

**What if my customer is outside Ghana?**
Switch country at project creation. The tool covers 40+ countries — but BOQ pricing and ECG tariffs only Ghana for now. Other markets coming Q3 2026.

**Where is my data stored?**
EU-region encrypted database. Per-tenant row-level isolation. Daily backups.

---

## 15. What's new (June 17, 2026)

Workflow-relevant changes shipped today. None of them changes the order of steps; they all sharpen what you see at the shading step and at the Installation Drawings report.

### 15.1 Shading dashboard — three new right-rail cards

After saving your inspection / obstruction form, open **Shading**. The right rail now opens with three cards:

1. **Obstruction Details** — name, type, height, distance, direction of the primary obstruction. An amber **MODERATE**, orange **HIGH** or red **SEVERE** chip carries the impact assessment at a glance.
2. **Shading Summary** — total shading hours per day, average shading index (the saved factor), peak shading hour, energy loss percentage.
3. **Shading Impact (PV Modules)** — a five-step legend bar (None → Low → Med → High → Severe) and a 4 × 7 module grid (28 cells in a typical residential array) coloured per cell. Cells in the NE-facing wedge carry the high / severe colours; cells unaffected stay deep blue. This is the "where will the shadow actually hit?" view a client wants to see before signing.

The sun-path arc in the central viewport now displays five visible time markers along the curve — 07:00, 09:30, 12:00, 14:30, 17:00. Scrub the timeline slider; the moving sun disk passes through each marker exactly.

### 15.2 Manual factor override — what you save is what you see

If you disagree with the agent's chosen factor (you have site knowledge the form can't capture), click one of the gold pill buttons under the SHADING_FACTORS table and hit Save. The factor you picked now drives every visible number on the page — top stat strip, big banner, summary card, the AGENT PICK row highlight in the table. The label is suffixed `· MANUAL` so the source is obvious.

Before today, the page would silently keep showing the engine's number while the system actually saved (and applied downstream) yours. The bug was cosmetic — your save was always honoured by the loads / sizing step — but the visible mismatch was confusing. Fixed.

### 15.3 Sunlight beams onto panels AND obstructions

The shading viewport's rays are now broad cones of light, not stick-thin lines. Each illuminated target — the PV array first, then every obstruction in your project — gets its own three-layer beam: a wide warm-yellow outer cone for soft glow, a brighter cream-yellow inner cone for the hot core, and a fan of sharper ray accents drawn on top. As you scrub the time slider, every beam rotates with the sun in lock-step. The shadow on the ground continues to fall directly opposite each beam, so the customer can see the full geometric chain: sun → beam → obstruction → shadow. Use this when explaining at the kitchen table why their north-east tree matters for an afternoon shading event.

### 15.4 Video walkthroughs in Resources & Tutorials

The Support page now serves MP4 video walkthroughs instead of audio-only MP3s. Each "Watch (MP4)" button plays a 1280×720 video pairing the narration with a relevant screenshot, so reps and operators can show a client what the platform looks like while the voice-over explains it. Both walkthroughs are also mirrored to the Desktop for offline use.

### 15.5 Installation Drawings — mount-specific routing diagram

Open Results → **Installation Diagrams** → Page 2. Between Drawing 1 (PV panel internal wiring) and Drawing 2 (battery bank), you now have **Drawing 1B — String Cable Routing & Combiner**. It draws your actual project's strings (colour-coded per string) running into the combiner box and out to the inverter, with the cable management appropriate to your project's mount:

- **Sloped roof** — cables under aluminium rails, EPDM-flashed roof penetration, IP65 conduit drop to indoor inverter wall.
- **Flat roof** — galvanised cable tray clipped to ballast stands, parapet transition to UV-rated rigid conduit, plant-room drop.
- **Ground** — IP67 armoured conduit buried at least 600 mm with draw pits every 20 m, combiner mounted on the equipment shelter.

The notes panel below the diagram references the right derating standard (BS 7671 Table 4D4A for buried, IEC 60364-5-52 for tray, Method B + 0.85 factor for through-insulation), so your installer's electrical sign-off has a defensible citation.

---

## 16. Screenshots index

When this guide is updated, screenshots will be referenced here:

- `[SCREEN: register-form]` — page `/register`
- `[SCREEN: login]` — page `/login`
- `[SCREEN: dashboard]` — page `/dashboard`
- `[SCREEN: project-new]` — page `/project/new`
- `[SCREEN: location-globe]` — page `/project/<id>/location`
- `[SCREEN: loads-input]` — page `/project/<id>/loads`
- `[SCREEN: results-pv]` — page `/project/<id>/report/pv`
- `[SCREEN: boq]` — page `/project/<id>/report/boq`
- `[SCREEN: economics]` — page `/project/<id>/report/economic`
- `[SCREEN: installation-drawings]` — page `/project/<id>/report/installation`
- `[SCREEN: proposal]` — page `/project/<id>/report/proposal`

To insert screenshots: capture the relevant page from the live app, save as `docs/screens/<slug>.png`, and re-run the PDF build script. The script auto-embeds any PNG whose filename matches a `[SCREEN: …]` token.
