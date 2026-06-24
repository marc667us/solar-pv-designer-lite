"""Staged workflow per owner rule:
  Stage 1: /boms/<id>            -- BOM (material list, NO cost)
  Stage 2: /boms/<id>/basic-prices -- NEW Basic Price Schedule (catalog price only,
                                    NO OH/profit/contingency/VAT)
  Stage 3: /boms/<id>/boq        -- Full Cost Estimate (BOQ chain with all mark-ups)

This patch adds Stage 2: route + template helper. Template lives in
templates/bom_basic_prices.html (created separately, NOT in this patch).
"""
import sys

path = "web_app.py"
data = open(path, "rb").read()
orig_len = len(data)

# Inject NEW route just AFTER the boms_view route (before items/add route).
anchor = (
    b'# \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80 BOM item add / update / delete \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\r\n'
)
# Use a shorter unique anchor (the rest of the comment is unicode boxes -- avoid)
anchor_short = b'# Backwards-compatible alias: many earlier templates link directly to'
# Actually let me just find the @app.route line for items/add and inject above it.
# Even simpler: anchor on the bytes "# BOM item add / update / delete" text only.
anchor_text = b'BOM item add / update / delete'
if data.count(anchor_text) != 1:
    print(f"FAIL: anchor 'BOM item add / update / delete' (got {data.count(anchor_text)})")
    sys.exit(1)

new_route = (
    b'# === Stage 2: Basic Price Schedule (Task #10, 2026-06-24) ===\r\n'
    b'# Per owner rule, BOM (Stage 1) carries NO cost; user clicks\r\n'
    b'# "Get Basic Price Schedule" to land here, where catalog basic price\r\n'
    b'# (supply rate only, no mark-ups) appears next to each line, then\r\n'
    b'# "Get Full Cost Estimate" advances to /boms/<id>/boq for the BOQ\r\n'
    b'# chain with OH/profit/contingency/VAT.\r\n'
    b'@app.route("/boms/<int:bom_id>/basic-prices")\r\n'
    b'@login_required\r\n'
    b'def boms_basic_prices(bom_id):\r\n'
    b'    """Stage 2 view: per-item catalog basic price (no mark-ups).\r\n'
    b'\r\n'
    b'    Computes only:\r\n'
    b'      basic_price_local = catalog_price_usd * fx_rate\r\n'
    b'      subtotal_local    = basic_price_local * qty\r\n'
    b'      grand_basic_local = sum(subtotal_local)\r\n'
    b'    No labour, no overhead, no profit, no contingency, no VAT.\r\n'
    b'    That chain runs in /boms/<bom_id>/boq (Stage 3).\r\n'
    b'    """\r\n'
    b'    _ensure_bom_tables()\r\n'
    b'    uid = session["user_id"]\r\n'
    b'    bom = _bom_owned_or_404(bom_id, uid)\r\n'
    b'    items = _bom_items_with_prices(bom_id)\r\n'
    b'    _bcur = (bom["currency"] if "currency" in bom.keys() and bom["currency"] else "GHS")\r\n'
    b'    _brate = float(_CURRENCY_RATES_FROM_USD.get(_bcur, 1.0) or 1.0)\r\n'
    b'    lines = []\r\n'
    b'    grand_basic = 0.0\r\n'
    b'    cat_totals = {}\r\n'
    b'    for it in items:\r\n'
    b'        try:\r\n'
    b'            cat = (it["category_name"] if "category_name" in it.keys() else None) or "Uncategorised"\r\n'
    b'        except Exception:\r\n'
    b'            cat = "Uncategorised"\r\n'
    b'        basic_usd = float(\r\n'
    b'            (it["unit_price_override"] if it["unit_price_override"] is not None\r\n'
    b'             else (it["catalog_price"] or 0)) or 0\r\n'
    b'        )\r\n'
    b'        basic_local = basic_usd * _brate\r\n'
    b'        qty = float(it["qty"] or 0)\r\n'
    b'        subtotal = basic_local * qty\r\n'
    b'        grand_basic += subtotal\r\n'
    b'        cat_totals[cat] = cat_totals.get(cat, 0.0) + subtotal\r\n'
    b'        lines.append({\r\n'
    b'            "item": it,\r\n'
    b'            "category": cat,\r\n'
    b'            "basic_price": basic_local,\r\n'
    b'            "qty": qty,\r\n'
    b'            "subtotal": subtotal,\r\n'
    b'        })\r\n'
    b'    return render_template(\r\n'
    b'        "bom_basic_prices.html",\r\n'
    b'        user=current_user(),\r\n'
    b'        bom=bom, lines=lines,\r\n'
    b'        grand_basic=grand_basic, cat_totals=cat_totals,\r\n'
    b'        currency=_bcur, fx_rate=_brate,\r\n'
    b'        rates_as_of=_CURRENCY_RATES_AS_OF,\r\n'
    b'    )\r\n'
    b'\r\n'
    b'\r\n'
)
# Inject the new route BEFORE the "BOM item add / update / delete" comment line.
# Find the position of the comment, then back up to the start of its line.
pos = data.find(anchor_text)
# Step back to find the start of the line containing this anchor.
line_start = data.rfind(b'\r\n', 0, pos) + 2  # after the previous \r\n
data = data[:line_start] + new_route + data[line_start:]

open(path, "wb").write(data)
print(f"OK: web_app.py {orig_len} -> {len(data)} bytes (+{len(data)-orig_len})")
