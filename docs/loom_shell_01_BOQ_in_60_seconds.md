# Loom Shell #1 — BOQ in 60 seconds

**Audience:** electrical contractor evaluating SolarPro for the first time.
**Goal:** prove they can build a Ghana-priced, client-deliverable BOQ in under a minute.
**Duration:** 60 s ± 5 s.
**Asset path:** record via Loom; export as MP4; commit to `docs/SolarPro_BOQ_60s.mp4`; surface via a new `_SUPPORT_ASSETS` slug `boq-60s`.

---

## Shot list & voiceover

| # | Time | Screen action | Voiceover (spoken) | On-screen text overlay |
|---|---|---|---|---|
| 1 | 0:00–0:05 | Cursor on dashboard with one project visible. Click **BOMs / Cost Estimates** in the nav dropdown. | "Building a BOQ in SolarPro takes one minute. Watch." | `BOQ in 60 seconds` (top) |
| 2 | 0:05–0:12 | Land on `/boms`. Click **New BOM** (top right). | "Click New BOM. Name it after the project." | — |
| 3 | 0:12–0:20 | Type `Accra Office Block - 50 kW PV` in the title field. Click **Create**. | "One field — title. Hit Create." | — |
| 4 | 0:20–0:32 | Lands on the BOM detail. Click **Pick from Marketplace**. Filter to `solar` category. Tick 5 items (panels, inverter, batteries, MC4 connectors, cable). Set quantities. Click **Add to BOM**. | "Pick from the marketplace. Live Ghana prices. Tick what you need, set quantities, add." | `Ghana-priced. Live updated.` |
| 5 | 0:32–0:42 | Click **Edit rates / mark-up**. Set Overhead 30%, Profit 10%, VAT 12.5%. Click **Recalculate rates**. | "Set your overhead, profit, and VAT. Recalculate runs in two seconds." | `OH 30% · P 10% · VAT 12.5%` |
| 6 | 0:42–0:52 | Scroll to bottom. Click **Excel** then **PDF** then **Email**. Show the Email modal opening. | "Excel, PDF, or email straight to your client. Done." | — |
| 7 | 0:52–0:58 | Back to the BOM list. Show "Accra Office Block - 50 kW PV" with grand total in GHS. | "One BOM. Ready to send." | — |
| 8 | 0:58–1:00 | Card with the SolarPro logo + URL `solarpro.aiappinvent.com` + CTA `Start free`. | "Start free at solarpro.aiappinvent.com." | `solarpro.aiappinvent.com · Start free` |

## Production notes

- Use **incognito** so the navbar doesn't show admin/test data.
- Seed the demo account beforehand: 1 project (Accra), 0 BOMs, ≥10 marketplace items already in the relevant categories.
- Record at **1920×1080** so it survives compression on WhatsApp + LinkedIn.
- Trim aggressively in Loom — no "uh", no waiting for page loads (use Loom's cut tool).
- Loom URL goes in: `support.html` "Watch BOQ tutorial" card, dashboard empty-state secondary link, marketing emails.

## Source-truth handoff

After recording, do all six steps so this file stays the source of truth:

1. Export MP4 from Loom (Settings → Download MP4).
2. `cp ~/Downloads/SolarPro_BOQ_60s.mp4 docs/SolarPro_BOQ_60s.mp4`
3. Add slug to `_SUPPORT_ASSETS` in `web_app.py`: `"boq-60s": ("SolarPro_BOQ_60s.mp4", "video/mp4")`.
4. Add a "Watch BOQ tutorial" card to `templates/support.html` linking to `{{ url_for('support_asset', slug='boq-60s') }}`.
5. Add a link from the BOM list empty-state in `boms_list.html`.
6. `git add docs/SolarPro_BOQ_60s.mp4 web_app.py templates/support.html templates/boms_list.html && git commit -m "docs(loom): BOQ-in-60-seconds walkthrough"`.
