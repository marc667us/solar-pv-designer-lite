# Loom Shell #2 — Cost Estimate in 60 seconds

**Audience:** electrical contractor / solar installer comparing SolarPro to Excel-based cost-estimating.
**Goal:** prove they can produce a full cost estimate with overhead/profit/VAT buildup in under a minute.
**Duration:** 60 s ± 5 s.
**Asset path:** record via Loom; export as MP4; commit to `docs/SolarPro_CostEstimate_60s.mp4`; surface via slug `cost-estimate-60s`.

---

## Shot list & voiceover

| # | Time | Screen action | Voiceover (spoken) | On-screen text overlay |
|---|---|---|---|---|
| 1 | 0:00–0:05 | On `/dashboard`. Click **BOMs / Cost Estimates** in the nav dropdown. | "Cost estimates with full overhead, profit, and VAT buildup — sixty seconds." | `Cost estimate in 60 seconds` |
| 2 | 0:05–0:12 | On `/boms`. Click any existing BOM (e.g. "Accra Office Block - 50 kW PV"). | "Open the BOM you built from the marketplace." | — |
| 3 | 0:12–0:22 | Inside the BOM. Click **Go to Cost Estimate** (or **View BOQ**). Land on the cost-estimate grid showing every line with direct rate + built-up rate. | "Every line carries a direct rate from the marketplace and a built-up rate with your mark-ups." | — |
| 4 | 0:22–0:35 | Click **Edit rates / mark-up**. Set: Labour 10% · Overhead 30% · Profit 10% · Contingency 5% · VAT 12.5%. Click **Recalculate rates**. | "Set your labour, overhead, profit, contingency, VAT. One click recalculates every line — direct rate compounded by each mark-up." | `Direct × (1+OH+P) × (1+C) × (1+VAT)` |
| 5 | 0:35–0:48 | Scroll: show the bill-level subtotal, the section-level subtotal, the grand total in GHS. Highlight a row with `[would]` next to a missing-spec compliance warning. | "Bill subtotal. Section subtotal. Grand total in your local currency. Compliance review flags missing specs in red." | `Bill · Section · Grand · Compliance` |
| 6 | 0:48–0:55 | Click **Excel** at the top → download triggers. Then **PDF** → download. | "Excel and PDF exports — A4, bordered, ready to print." | — |
| 7 | 0:55–1:00 | Logo + URL card. | "solarpro.aiappinvent.com. Start free." | `solarpro.aiappinvent.com · Start free` |

## Production notes

- Pre-seed the demo account with one BOM that has at least 8 line items spanning panels, inverters, batteries, cable, mounting, labour, freight, contingency.
- Use a **screen size = 1080p** so Loom's compression doesn't muddle the numeric columns.
- The compliance-review red box ([[project-solar-pv-session-2026-06-19-catalogue]]'s `_boq_compliance_check`) is a strong differentiator — make sure it's visible in shot #5.
- Loom URL goes in: `support.html` card, BOM list empty-state, the BOM detail view ("Watch how").

## Source-truth handoff

Same six-step pattern as Loom #1.
