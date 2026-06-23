#!/usr/bin/env python3
"""
patch_money_filter_template_sweep.py

Sweep BOQ + marketplace + BOM + report templates and replace `|fmt`
with `|money` on lines that clearly reference a price / rate / amount
column. Quantities and percentages are intentionally left alone.

Money field-name heuristic (case-insensitive) -- the line must include
ONE of these tokens AS AN IDENTIFIER:
    basic_price, supply_rate, install_rate, final_built_up_rate,
    total_amount, subtotal, grand, unit_price, lump_sum, line_total,
    bill_total, section_total, floor_total, building_total, item_total,
    amount, cost, total, price, rate, fee

Tokens that flag the line as NOT MONEY (skip even if money-token also
appears -- e.g. "rate_pct" "qty_per_panel"):
    pct, percent, qty, count, days, hours, kwh, kwp, kw_ac, panels,
    months, years, lat, lon, hsp, psh, irradiance, tilt, azimuth

The patcher loads each template, walks lines, applies the replacement
where appropriate, and writes back. Idempotent.
"""

from pathlib import Path
import re

TEMPLATES_DIR = Path("templates")

# Files to touch. Exclude any template where ALL `|fmt` usages are for
# scientific / engineering fields, not money.
TARGET_FILES = [
    "boq_project_boq.html",          # already partly done; re-running is no-op
    "boq_project_summary.html",
    "boq_project_overview.html",
    "boq_building_view.html",
    "boq_floor_view.html",
    "boq_floor_summary.html",
    "boq_floor_section_grid.html",
    "boq_floor_section_loop.html",
    "boq_projects_list.html",
    "bom_boq.html",
    "price_sheet_view.html",
    "marketplace.html",
    "marketplace_product.html",
    "procurement_center.html",
    "supplier_products.html",
    "supplier_dashboard.html",
    "admin_marketplace_products.html",
    "admin_marketplace_pending.html",
    "admin_library_pending.html",
    "report_boq.html",
    "report_proposal.html",
    "report_economic.html",
]

MONEY_TOKENS = (
    "basic_price", "supply_rate", "install_rate", "final_built_up_rate",
    "total_amount", "subtotal", "grand", "unit_price", "lump_sum",
    "line_total", "bill_total", "section_total", "floor_total",
    "building_total", "item_total",
    # Suffix matches -- looser; protected by NOT-MONEY filter below
    "_amount", "_cost", "_total", "_price", "_rate", "_fee",
    ".amount", ".cost", ".total", ".price", ".rate", ".fee",
    " amount ", " cost ", " total ", " price ", " rate ", " fee ",
    "(amount", "(cost", "(total", "(price", "(rate", "(fee",
)

NOT_MONEY_TOKENS = (
    "_pct", "pct ", "pct}", "pct|", "pct,", "_percent", "_qty",
    ".qty", "(qty", "_count", "_days", "_hours", "_kwh", "_kwp",
    "kw_ac", "panels", "_months", "_years", "lat", "lon",
    "_hsp", "_psh", "irradiance", "tilt", "azimuth", "elevation",
    "savings_pct", "loss_pct", "efficiency",
    # specific to engineering reports
    "voltage", "current", "ampere", "watt_per", "lumen",
)

def is_money_line(line: str) -> bool:
    low = line.lower()
    if any(tok in low for tok in NOT_MONEY_TOKENS):
        return False
    return any(tok in low for tok in MONEY_TOKENS)

# Pattern: replace `|fmt}}` or `|fmt }}` or `|fmt|` (chained) with `|money`
# Keep arguments like `|fmt(1)%` intact.
FMT_BARE = re.compile(r'\|fmt(?=[\s}|+])')

touched_total = 0
files_changed = 0
for fname in TARGET_FILES:
    p = TEMPLATES_DIR / fname
    if not p.exists():
        print(f"  [skip] {fname} not found")
        continue
    src = p.read_text(encoding="utf-8")
    out_lines = []
    touched = 0
    for ln in src.splitlines(keepends=True):
        if "|fmt" in ln and is_money_line(ln) and FMT_BARE.search(ln):
            new_ln = FMT_BARE.sub("|money", ln)
            if new_ln != ln:
                out_lines.append(new_ln)
                touched += 1
                continue
        out_lines.append(ln)
    if touched:
        p.write_text("".join(out_lines), encoding="utf-8")
        print(f"  [ok]   {fname:40s}  {touched} line(s) money-formatted")
        touched_total += touched
        files_changed += 1
    else:
        print(f"  [noop] {fname:40s}  nothing to change")

print()
print(f"Total: {files_changed} file(s) changed, {touched_total} line(s) swapped fmt -> money.")
