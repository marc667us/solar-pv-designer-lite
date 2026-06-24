"""Honour the project rule: BOM editor (/boms/<id>) must NOT compute cost.

Replace `boms_view()`'s _bom_totals_with_rates call with a cost-free
grouping helper. The template only reads `totals.lines[].item` and
`totals.category_totals|length` so we hand it that shape with NO cost
fields populated.
"""
import sys

path = "web_app.py"
data = open(path, "rb").read()
orig_len = len(data)

old = (
    b'@app.route("/boms/<int:bom_id>")\r\n'
    b'@login_required\r\n'
    b'def boms_view(bom_id):\r\n'
    b'    _ensure_bom_tables()\r\n'
    b'    uid = session["user_id"]\r\n'
    b'    bom = _bom_owned_or_404(bom_id, uid)\r\n'
    b'    items = _bom_items_with_prices(bom_id)\r\n'
    b'    bom_rates = _bom_rates_for(bom_id)\r\n'
    b'    _bcur = (bom["currency"] if "currency" in bom.keys() and bom["currency"] else "GHS")\r\n'
    b'    _brate = _CURRENCY_RATES_FROM_USD.get(_bcur, 1.0)\r\n'
    b'    totals = _bom_totals_with_rates(items, bom_rates, fx_rate=_brate)\r\n'
    b'    return render_template(\r\n'
    b'        "bom_view.html",\r\n'
    b'        user=current_user(),\r\n'
    b'        bom=bom, items=items, totals=totals, bom_rates=bom_rates,\r\n'
    b'        currency=_bcur, fx_rate=_brate,\r\n'
    b'        currencies=list(_CURRENCY_RATES_FROM_USD.keys()),\r\n'
    b'        rates_as_of=_CURRENCY_RATES_AS_OF,\r\n'
    b'    )\r\n'
)
new = (
    b'@app.route("/boms/<int:bom_id>")\r\n'
    b'@login_required\r\n'
    b'def boms_view(bom_id):\r\n'
    b'    """BOM editor -- material list ONLY. Cost lives on /boms/<id>/boq\r\n'
    b'    (the Cost Estimate). The owner rule: BOM = quantities, Cost Estimate\r\n'
    b'    = the money. We DO NOT call _bom_totals_with_rates here so the cost\r\n'
    b'    chain never runs on this surface, period.\r\n'
    b'    """\r\n'
    b'    _ensure_bom_tables()\r\n'
    b'    uid = session["user_id"]\r\n'
    b'    bom = _bom_owned_or_404(bom_id, uid)\r\n'
    b'    items = _bom_items_with_prices(bom_id)\r\n'
    b'    bom_rates = _bom_rates_for(bom_id)\r\n'
    b'    _bcur = (bom["currency"] if "currency" in bom.keys() and bom["currency"] else "GHS")\r\n'
    b'    _brate = _CURRENCY_RATES_FROM_USD.get(_bcur, 1.0)\r\n'
    b'    # Cost-free totals shape: template only reads .lines[].item +\r\n'
    b'    # .category_totals|length. No basic_rate / overhead / profit / vat\r\n'
    b'    # / line_total / grand_total fields populated.\r\n'
    b'    _cat_seen = {}\r\n'
    b'    _lines = []\r\n'
    b'    for _it in items:\r\n'
    b'        try:\r\n'
    b'            _cat = (_it["category_name"] if "category_name" in _it.keys() else None) or "Uncategorised"\r\n'
    b'        except Exception:\r\n'
    b'            _cat = "Uncategorised"\r\n'
    b'        _cat_seen[_cat] = _cat_seen.get(_cat, 0) + 1\r\n'
    b'        _lines.append({"item": _it})\r\n'
    b'    totals = {"lines": _lines, "category_totals": _cat_seen, "grand_total": None}\r\n'
    b'    return render_template(\r\n'
    b'        "bom_view.html",\r\n'
    b'        user=current_user(),\r\n'
    b'        bom=bom, items=items, totals=totals, bom_rates=bom_rates,\r\n'
    b'        currency=_bcur, fx_rate=_brate,\r\n'
    b'        currencies=list(_CURRENCY_RATES_FROM_USD.keys()),\r\n'
    b'        rates_as_of=_CURRENCY_RATES_AS_OF,\r\n'
    b'    )\r\n'
)
if data.count(old) != 1:
    print(f"FAIL: boms_view block (got {data.count(old)})")
    sys.exit(1)
data = data.replace(old, new)

open(path, "wb").write(data)
print(f"OK: web_app.py {orig_len} -> {len(data)} bytes (+{len(data)-orig_len})")
