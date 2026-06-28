"""Deepen helpline coverage on the 5 topics the owner flagged on 2026-06-28:
    1. Marketplace prices and products
    2. Shading
    3. Rate buildup + basic prices (the new v3 engine)
    4. BOM + Cost Estimate
    5. Project BOQ templates + section-by-section workflow

Two changes:
  A. Inject five new dedicated `=== TOPIC TRAINING ===` sections into
     _ASSISTANT_SYSTEM (just before COMMON ISSUES) so the LLM has the
     full vocabulary + values + URLs to answer naturally.
  B. Insert ten high-value KB entries into the rule-based fallback
     (_rule_reply / _KB) so even when the LLM chain is down, keyword
     matches still return useful answers.

Both changes are idempotent via SENTINELs.
"""
from __future__ import annotations
from pathlib import Path
import sys

TARGET = Path(__file__).parent / "web_app.py"

PROMPT_SENTINEL = b"# helpline-topic-training-2026-06-28"
KB_SENTINEL     = b"# kb-topic-training-2026-06-28"


# --- A. PROMPT INJECTION ----------------------------------------------------

PROMPT_ANCHOR = b'=== COMMON ISSUES ==='

PROMPT_NEW = (
    b'=== TOPIC TRAINING (2026-06-28) ===\r\n'
    b'\r\n'
    b'' + PROMPT_SENTINEL + b'\r\n'
    b'\r\n'
    b'-- TOPIC 1: MARKETPLACE PRICES & PRODUCTS --\r\n'
    b'\r\n'
    b'Prices on /marketplace are stored as price_usd (USD baseline) per product, then converted on the fly to the selected currency (USD/EUR/GBP/GHS/NGN/KES/ZAR/XOF/ZMW) using FX rates set in env (defaults shipped). Currencies render as ISO codes, never as symbols.\r\n'
    b'\r\n'
    b'Each product card shows: name, brand, category, unit (No./M/Set/m^2/etc), basic price in the picked currency, supplier name, supplier country, compliance badge for the picked country. Click a card to open the public product page with full spec.\r\n'
    b'\r\n'
    b'Adding a product (supplier role): /supplier/products/add. Required: name, category (21 fixed categories), brand, unit, basic price, voltage_v, frequency_hz, compliance_standards. Optional: datasheet URL, lit URL, spec text.\r\n'
    b'\r\n'
    b'BOQ side: when an item description has NO matching catalogue product, the BOQ section grid now has an inline "+ Add to catalogue" button on every row -- opens a modal, pick or type a new category + product name + brand + basic price + unit, save. The new price is auto-pushed into the BOQ row. POST /equipment-catalog/quick-add is the underlying endpoint.\r\n'
    b'\r\n'
    b'Recheck Prices: admins can hit /admin/marketplace/recheck to bulk-poll suppliers for current prices. Catalogue Price History at /admin/marketplace/products/<id>/history shows every supplier price change recorded for that product (equipment_catalog_price_history table).\r\n'
    b'\r\n'
    b'\r\n'
    b'-- TOPIC 2: SHADING (3D) --\r\n'
    b'\r\n'
    b'Where: /project/<pid>/report/shading. Interactive server-rendered SVG (NOT Three.js -- the old WebGL version was retired 2026-06-16 in favour of the SVG model). The SVG shows a proportional roof + sun arc + 16 compass directions for obstruction placement + a sky lerp that changes with time of day.\r\n'
    b'\r\n'
    b'Inputs feeding the simulation come from /project/<pid>/inspection -- roof type, tilt, azimuth, **building H/W/L**, mount type (ground vs rooftop), shading factor override, and per-direction obstructions (height + distance). The simulation reads roof_height_m, sim_time, mount_type so the sun arc + obstruction shadows are physically meaningful.\r\n'
    b'\r\n'
    b'Outputs: shading factor (0..1 multiplier on PV output), loss percentage, per-direction loss table, optional 25-yr energy delta with vs without shading. The engine multiplies designed kWp by the factor in the PV Design + Energy Production reports.\r\n'
    b'\r\n'
    b'Demo modes: ?demo=10/20/25/30 inject obstructions for sales demos. LIVE MODEL badge confirms the user is on the real simulation, not a static placeholder. The owner can override the computed factor with a slider on the report page -- the override is persisted and used by all downstream reports.\r\n'
    b'\r\n'
    b'\r\n'
    b'-- TOPIC 3: RATE BUILDUP + BASIC PRICES (v3 engine, 2026-06-28) --\r\n'
    b'\r\n'
    b'The BOQ rate engine uses this exact formula per line item:\r\n'
    b'  effective_vat    = 0 if vat_in_basic else vat_pct\r\n'
    b'  supply_amount    = basic_price * (1 + (supply_pct + effective_vat) / 100)\r\n'
    b'  install_amount   = basic_price * ((install_pct + overhead_pct + profit_pct) / 100)\r\n'
    b'  total_amount     = supply_amount + install_amount      (per unit)\r\n'
    b'  line_amount      = qty * total_amount                  (BOQ line total)\r\n'
    b'\r\n'
    b'Plain English: basic price is what the SUPPLIER charges per unit. Supply Amount marks up basic for supply-side costs (freight, handling, the supply-rate %). VAT is added INTO Supply if the supplier invoice did not already include it -- tick the "VAT already on supplier invoice?" checkbox to set vat_in_basic=true and skip the VAT addition. Install Amount is the LABOUR side: install_pct PLUS overhead_pct PLUS profit_pct, all multiplied with the basic. Overhead and profit ride on the install line, NOT supply. There is NO contingency (removed 2026-06-28 by owner directive).\r\n'
    b'\r\n'
    b'BOQ display columns are: Item | Description | Qty | Unit | Basic Price | Supply Amount | Install Amount | Total Amount | Line Amount. The percentage inputs (supply_pct, install_pct, overhead_pct, profit_pct, vat_pct) live in the rate-builder form per section or per row.\r\n'
    b'\r\n'
    b'Where to set them: /boq-projects/<pid>/buildings/<bid>/floors/<fid>/section/<bill>/<letter>/grid (section grid) -- top of the page has Overhead %, Profit %, VAT %, and the VAT-in-basic checkbox. Per-row: Supply % and Install % columns. The grid also recomputes Supply Amount + Install Amount + Total Amount in real time as the owner types.\r\n'
    b'\r\n'
    b'Recalculate rates: /boq-projects/<pid>/overview has a "Recalculate rates" button that re-runs the formula against every line in the project using the currently-stored percentages -- useful after a global tax rate change.\r\n'
    b'\r\n'
    b'\r\n'
    b'-- TOPIC 4: BOM vs COST ESTIMATE --\r\n'
    b'\r\n'
    b'BOM (Bill of Materials) and Cost Estimate are TWO views of the same marketplace document:\r\n'
    b'  /boms (list) and /boms/<id> (single) -- BOM view = raw material list with qty + unit. No markup. Used for material take-off and supplier order.\r\n'
    b'  Same document at /boms/<id>?as=cost_estimate -- Cost Estimate view = adds the supply / install / overhead / profit / VAT roll-up on top of the BOM lines so the owner sees a delivered + installed price.\r\n'
    b'\r\n'
    b'Create a BOM: /procurement-center -> tick products, choose currency, pick "BOM" doc type -> Add. The BOM lands in /boms.\r\n'
    b'\r\n'
    b'Cost Estimate gets a Labour cost line (10-30% slider), a Cost Estimate header branded "SolarPro Marketplace - Accra, Ghana", and Excel + PDF exports with A4 borders + per-row Update Price modal.\r\n'
    b'\r\n'
    b'BOM -> BOQ qty sync (since 2026-06-28): on the BOQ project overview, the "Sync from BOM" button opens a picker of the owner\'s BOMs. Pick one, click Sync -- the system matches each BOM line\'s `custom_name` to a BOQ item description (case-insensitive; exact first, then substring) and overwrites the BOQ qty with the BOM qty + recomputes total. Lines that already match the BOM qty are left alone.\r\n'
    b'\r\n'
    b'\r\n'
    b'-- TOPIC 5: PROJECT BOQ TEMPLATES + SECTIONS --\r\n'
    b'\r\n'
    b'14 templates ship in /boq-projects/wizard:\r\n'
    b'  Healthcare: hospital-floor-ground, hospital-floor-first, hospital-floor-second, iso-male-ward, morgue-building\r\n'
    b'  Residential: staff-housing-1bed, staff-housing-2bed\r\n'
    b'  Commercial: kitchen-building, it-room\r\n'
    b'  Industrial: energy-centre, maintenance-building, stores-building, external-service\r\n'
    b'  Multi-discipline: master-reference-library (13 bills, 124 items across containment, wiring, accessories, lighting, distribution, main equipment, earthing, solar PV, ICT, CCTV, BMS, IoT, testing)\r\n'
    b'\r\n'
    b'Topology of every BOQ template:\r\n'
    b'  Bill (e.g. "BILL No. 2 -- INTERNAL ELECTRICAL WIRING")\r\n'
    b'    Section (e.g. "A. SWITCH BOARDS AND DISTRIBUTION BOARDS")\r\n'
    b'      Sub-section (optional, e.g. "i. Light and fan points")\r\n'
    b'        Items (1, 2, 3 ... description / qty / unit / basic)\r\n'
    b'\r\n'
    b'Two ways to create a BOQ project from templates:\r\n'
    b'  A. Multi-building Wizard (recommended) -- /boq-projects/wizard. One screen: tick the building types + counts you need + global markup defaults + VAT-in-basic flag + project name + client + location. Submit creates the project + one building per (template x count) + one floor per building + every template line populated. Pricing in the sample templates is 0 by default; owner fills basic price after.\r\n'
    b'  B. Classic per-building flow -- /boq-projects/new -> create project -> add buildings one by one -> per floor -> "Start from template" or "Open one section". The classic flow shows the same 14 templates and lets the owner override per-line qty + basic.\r\n'
    b'\r\n'
    b'Section grid (the "by section" workflow): /boq-projects/<pid>/buildings/<bid>/floors/<fid>/bill/<bill>/section/<letter>/grid. Bulk-edit every line under a single section -- tick rows to include, edit qty / basic / supply% / install% per row, set section-wide Overhead/Profit/VAT/vat_in_basic at top, save. The grid shows Supply Amount + Install Amount + Total Amount + Line Amount live-computed.\r\n'
    b'\r\n'
    b'Learning layer: when the owner edits an item (description + unit + basic + qty + supply% + install%), the new values are recorded against the description as an override (table boq_user_item_overrides). The next time ANY template containing that same description is instantiated -- via the wizard or "Start from template" -- the override is overlaid on top of the static template defaults. The library effectively LEARNS the owner\'s preferred values across projects.\r\n'
    b'\r\n'
    b'Editable BOQ title + Instructions cell: on /boq-projects/<pid>/overview -- the top card has an editable title + free-text Instructions textarea. Save persists to boq_projects.project_name + .instructions. The instructions render above the BOQ table on Excel + PDF exports.\r\n'
    b'\r\n'
    b'\r\n'
)


def patch_prompt(src: bytes) -> tuple[bytes, str]:
    if PROMPT_SENTINEL in src:
        return src, "[skip] prompt sentinel already present"
    if PROMPT_ANCHOR not in src:
        return src, "[fail] prompt anchor not found"
    # Insert NEW block just BEFORE the COMMON ISSUES heading so the LLM
    # reads the topic-training sections in line with the rest of the
    # platform overview.
    new = src.replace(PROMPT_ANCHOR, PROMPT_NEW + PROMPT_ANCHOR, 1)
    return new, f"[ok] inserted topic-training sections (+{len(PROMPT_NEW)} bytes)"


# --- B. KB INJECTION --------------------------------------------------------

# Anchor: the same maintenance/alarm tuple used by the earlier kb patch.
KB_ANCHOR = (
    b'        # Monitoring/alarms before project (both mention "dashboard")\r\n'
    b'        (["maintenance","service","fault","alarm","monitoring","alert"],'
)

KB_NEW = (
    b'        ' + KB_SENTINEL + b'\r\n'
    b'        # --MARKETPLACE PRICES & PRODUCTS --\r\n'
    b'        (["price_usd","baseline price","fx rate","currency conversion","why is my price in usd"],\r\n'
    b'         "Marketplace prices are stored as **price_usd** (the USD baseline) on every product, then converted to your picked currency on the fly using FX rates configured in env. Currencies render as ISO codes (USD, GHS, NGN, ...) never as symbols. Pick currency at the top of /marketplace or on /procurement-center before adding to a document."),\r\n'
    b'        (["add product","supplier product","new product","catalogue product","quick add","add to catalogue","add to catalog"],\r\n'
    b'         "Two paths. **Supplier role**: /supplier/products/add -- fill name + category (21 fixed) + brand + basic price + unit + voltage_v + frequency_hz + compliance_standards. **Inline from BOQ**: open any section grid, click the gold **+ Add to catalogue** button on a row -- the modal lets you pick or type a NEW category + name + brand + basic price + unit, save, and the price is auto-pushed into the BOQ cell."),\r\n'
    b'        # --SHADING (3D) --\r\n'
    b'        (["shading","shade","obstruction","sun arc","sun path","3d shading","shading factor","shading report","shading simulation"],\r\n'
    b'         "**3D Shading** lives at /project/<pid>/report/shading. Interactive SVG (not WebGL) with proportional roof + sun arc + 16-compass obstruction placement + time-of-day sky lerp. Inputs come from /project/<pid>/inspection -- roof type, tilt, azimuth, building H/W/L, mount type, per-direction obstructions, optional manual shading factor. Output = factor (0..1) multiplied into PV output and the 25-yr energy report. Use ?demo=10/20/25/30 for sales demos."),\r\n'
    b'        # --RATE BUILDUP v3 --\r\n'
    b'        (["rate buildup","rate build-up","build up","basic price","supply amount","install amount","total amount","line amount","supply rate","install rate"],\r\n'
    b'         "**Rate engine v3** (2026-06-28): supply_amount = basic * (1 + (supply% + effective_vat)/100); install_amount = basic * ((install% + overhead% + profit%)/100); total_amount = supply + install (per unit); line_amount = qty * total_amount. effective_vat is 0 when the supplier invoice already included VAT (tick the **VAT already on supplier invoice?** box). NO contingency (removed). Set the percentages on the section grid top bar + per-row Supply%/Install% cells; values recompute live."),\r\n'
    b'        (["overhead","profit","vat","vat included","vat_in_basic","contingency"],\r\n'
    b'         "Overhead % and Profit % ride on the **install side** of the rate build-up (they get added to install_pct and applied to basic). VAT % goes on the **supply side** -- unless the supplier invoice already carries VAT, in which case tick the **VAT already on supplier invoice?** box and VAT contribution drops to 0. **Contingency is no longer applied** (removed 2026-06-28 by owner directive). Set all of these at /boq-projects/<pid>/buildings/.../section/.../grid top bar."),\r\n'
    b'        # --BOM + COST ESTIMATE --\r\n'
    b'        (["bom vs cost estimate","difference between bom","material list","cost estimate","take-off","material takeoff"],\r\n'
    b'         "**BOM** (Bill of Materials) is the raw material list with qty + unit -- no markup, used for take-off + supplier order. View at /boms/<id>. **Cost Estimate** is the SAME document with the supply / install / overhead / profit / VAT roll-up applied on top, branded \\"SolarPro Marketplace - Accra, Ghana\\" with a Labour cost line slider. View at /boms/<id>?as=cost_estimate. Create both from /procurement-center -- tick products, pick currency, pick \\"BOM\\" doc type, Add."),\r\n'
    b'        (["sync from bom","bom to boq","import bom","pull qty","update qty from bom"],\r\n'
    b'         "On the BOQ project overview, click **Sync from BOM** -- pick a saved BOM, click Sync. The system matches each BOM line\'s custom_name against BOQ item descriptions (case-insensitive; exact first, then substring) and overwrites the BOQ qty + recomputes the line total. Lines already matching the BOM qty are left alone. Audit log records updated / skipped counts."),\r\n'
    b'        # --BOQ TEMPLATES + SECTIONS + WIZARD --\r\n'
    b'        (["boq template","boq templates","building template","template library","what templates","wizard","multi-building","one click boq"],\r\n'
    b'         "14 BOQ templates ship in the **Multi-Building Wizard** at /boq-projects/wizard: healthcare (hospital floors ground/first/second, iso-male ward, morgue), residential (1-bed and 2-bed staff housing), commercial (kitchen, IT room), industrial (energy centre, maintenance, stores, external substation) plus the master-reference-library (13 bills, 124 items). One screen -> tick building types + counts -> Submit -> project + buildings + floors + every template line populated."),\r\n'
    b'        (["bill","section","sub-section","subsection","by section","section grid","section workflow","boq hierarchy"],\r\n'
    b'         "BOQ topology: **Bill** (e.g. BILL No. 2 -- INTERNAL ELECTRICAL WIRING) -> **Section** (e.g. A. SWITCH BOARDS) -> optional **Sub-section** (e.g. i. Light points) -> Items (qty, unit, basic). Edit any section\'s lines in bulk at /boq-projects/<pid>/buildings/<bid>/floors/<fid>/bill/<bill>/section/<letter>/grid -- tick rows, edit qty / basic / supply% / install% per row, save. Section-wide markup (Overhead/Profit/VAT/vat_in_basic) lives at the top of the grid."),\r\n'
    b'        (["boq title","boq instructions","project title","project instructions","edit boq name","note above table"],\r\n'
    b'         "On /boq-projects/<pid>/overview the top card has an editable **BOQ title** + a free-text **Instructions** textarea (max 4000 chars). Save persists to boq_projects.project_name + .instructions. The instructions render in italic gray above the BOQ table on Excel + PDF exports."),\r\n'
    b'        (["learning","learn from edits","library update","propagate","auto-fill template","template defaults"],\r\n'
    b'         "**Learning layer** (since 2026-06-28): every time the owner edits a BOQ item (description / unit / basic / qty / supply% / install%), the values are recorded as an override against the description (boq_user_item_overrides). The next time ANY template containing the same description is instantiated -- via the wizard or \\"Start from template\\" -- the override is overlaid on top of the static template defaults. The library effectively learns the owner\'s preferred values across projects."),\r\n'
    b'        ' + KB_ANCHOR
)


def patch_kb(src: bytes) -> tuple[bytes, str]:
    if KB_SENTINEL in src:
        return src, "[skip] KB sentinel already present"
    if KB_ANCHOR not in src:
        return src, "[fail] KB anchor not found"
    new = src.replace(KB_ANCHOR, KB_NEW, 1)
    added = KB_NEW.count(b'(["')
    return new, f"[ok] inserted {added} new KB entries (+{len(KB_NEW) - len(KB_ANCHOR)} bytes)"


def main() -> int:
    src = TARGET.read_bytes()
    src, msg1 = patch_prompt(src)
    print(msg1)
    if msg1.startswith("[fail]"):
        return 2
    src, msg2 = patch_kb(src)
    print(msg2)
    if msg2.startswith("[fail]"):
        return 3
    # compile-check before write
    try:
        compile(src, str(TARGET), "exec")
    except SyntaxError as e:
        print(f"[fail] SyntaxError at line {e.lineno}: {e.msg}")
        return 4
    TARGET.write_bytes(src)
    print(f"[ok] wrote {TARGET} ({len(src)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
