"""Wire the existing /boms/<id> route (boms_view) to load rates + pass them
to the template under the `bom_rates` and `totals_rated` keys, AND wire
/boms/<id>/boq similarly so the printable view can use total-rate columns.

Without this patch the new rates panel + export routes work, but the
existing BOM view template would render with the default rates only
(since the view route doesn't yet load the rates row).
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"


PATCHES = [
    # boms_view: existing body ends with render_template("bom_view.html", ...).
    # We need to load rates + recompute totals before the render.
    (
        b"    items = _bom_items_with_prices(bom_id)\r\n"
        b"    totals = _bom_totals(items)\r\n"
        b"    return render_template(\r\n"
        b"        \"bom_view.html\",\r\n"
        b"        user=current_user(),\r\n"
        b"        bom=bom, items=items, totals=totals,\r\n"
        b"    )\r\n"
        b"\r\n"
        b"\r\n"
        b"# \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80 BOM item add / update / delete \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80",
        b"    items = _bom_items_with_prices(bom_id)\r\n"
        b"    bom_rates = _bom_rates_for(bom_id)\r\n"
        b"    totals = _bom_totals_with_rates(items, bom_rates)\r\n"
        b"    return render_template(\r\n"
        b"        \"bom_view.html\",\r\n"
        b"        user=current_user(),\r\n"
        b"        bom=bom, items=items, totals=totals, bom_rates=bom_rates,\r\n"
        b"    )\r\n"
        b"\r\n"
        b"\r\n"
        b"# \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80 BOM item add / update / delete \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80",
    ),
    # boms_boq: same idea — recompute totals using the saved rates so the
    # printable view shows the rated grand total instead of basic-only.
    (
        b"    items = _bom_items_with_prices(bom_id)\r\n"
        b"    totals = _bom_totals(items)\r\n"
        b"    return render_template(\r\n"
        b"        \"bom_boq.html\",\r\n"
        b"        user=current_user(),\r\n"
        b"        bom=bom, items=items, totals=totals,\r\n"
        b"    )\r\n",
        b"    items = _bom_items_with_prices(bom_id)\r\n"
        b"    bom_rates = _bom_rates_for(bom_id)\r\n"
        b"    totals = _bom_totals_with_rates(items, bom_rates)\r\n"
        b"    return render_template(\r\n"
        b"        \"bom_boq.html\",\r\n"
        b"        user=current_user(),\r\n"
        b"        bom=bom, items=items, totals=totals, bom_rates=bom_rates,\r\n"
        b"    )\r\n",
    ),
]


def patch() -> int:
    src = open(TARGET, "rb").read()
    if b"bom_rates = _bom_rates_for(bom_id)" in src:
        print("[skip] bom_rates wiring already present")
        return 0
    applied = 0
    for old, new in PATCHES:
        if old in src:
            src = src.replace(old, new)
            applied += 1
    if applied == 0:
        print("[fail] no patch site matched")
        return 4
    open(TARGET, "wb").write(src)
    print(f"[ok] wired {applied}/{len(PATCHES)} BOM view routes to load rates")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
