#!/usr/bin/env python3
"""patch_marketplace_cache_setter.py -- second half of the cache patch.

Wrap marketplace_public's `return render_template(...)` so the rendered
HTML is stored in _MARKETPLACE_CACHE on the way out. Anonymous-only;
logged-in users skip the set too.
"""
from pathlib import Path
P = Path("web_app.py")
data = P.read_bytes()

OLD = (
    b'    return render_template(\r\n'
    b'        "marketplace.html",\r\n'
    b'        user=current_user(),\r\n'
    b'        categories=categories,\r\n'
    b'        products=products_view,\r\n'
    b'        products_by_category=products_by_category,\r\n'
    b'        subcategories_for_selected=subcategories_for_selected,\r\n'
    b'        selected_subcategory=sub,\r\n'
    b'        total_products=total_products,\r\n'
    b'        total_suppliers=total_suppliers,\r\n'
    b'        total_countries=countries,\r\n'
    b'        selected_category=selected_category,\r\n'
    b'        q=q,\r\n'
    b'        currency=currency,\r\n'
    b'        currencies=list(_CURRENCY_RATES_FROM_USD.keys()),\r\n'
    b'        rates_as_of=_CURRENCY_RATES_AS_OF,\r\n'
    b'        page=_page, total_pages=_total_pages, products_per_page=_ppp,\r\n'
    b'        filter_count=_filter_count,\r\n'
    b'    )\r\n'
)
NEW = (
    b'    _rendered = render_template(\r\n'
    b'        "marketplace.html",\r\n'
    b'        user=current_user(),\r\n'
    b'        categories=categories,\r\n'
    b'        products=products_view,\r\n'
    b'        products_by_category=products_by_category,\r\n'
    b'        subcategories_for_selected=subcategories_for_selected,\r\n'
    b'        selected_subcategory=sub,\r\n'
    b'        total_products=total_products,\r\n'
    b'        total_suppliers=total_suppliers,\r\n'
    b'        total_countries=countries,\r\n'
    b'        selected_category=selected_category,\r\n'
    b'        q=q,\r\n'
    b'        currency=currency,\r\n'
    b'        currencies=list(_CURRENCY_RATES_FROM_USD.keys()),\r\n'
    b'        rates_as_of=_CURRENCY_RATES_AS_OF,\r\n'
    b'        page=_page, total_pages=_total_pages, products_per_page=_ppp,\r\n'
    b'        filter_count=_filter_count,\r\n'
    b'    )\r\n'
    b'    # Populate the 60-s anonymous response cache on the way out.\r\n'
    b'    if "user_id" not in session:\r\n'
    b'        _ck = "anon:" + (request.query_string.decode("utf-8","replace") or "_")\r\n'
    b'        _mp_cache_set(_ck, _rendered)\r\n'
    b'    resp = make_response(_rendered)\r\n'
    b'    resp.headers["X-Cache"] = "MISS"\r\n'
    b'    if "user_id" not in session:\r\n'
    b'        resp.headers["Cache-Control"] = "public, max-age=30"\r\n'
    b'    return resp\r\n'
)

if NEW in data:
    print("[skip] cache-setter already patched")
elif data.count(OLD) != 1:
    raise SystemExit(f"[fail] expected 1 OLD match, found {data.count(OLD)}")
else:
    data = data.replace(OLD, NEW, 1)
    P.write_bytes(data)
    print(f"[ok] cache-setter added; web_app.py +{len(NEW)-len(OLD)} bytes -> {P.stat().st_size}")
