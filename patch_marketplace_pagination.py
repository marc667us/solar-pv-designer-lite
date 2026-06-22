#!/usr/bin/env python3
"""patch_marketplace_pagination.py -- 2026-06-22.

(1) Splice new_marketplace_pagination.py into web_app.py.
(2) Swap the LIMIT 200 on marketplace_public to LIMIT ? OFFSET ?,
    compute total rows + total pages, pass to template.
(3) Same for procurement_center.
(4) procurement_center_add merges stored_ids[] (from sessionStorage)
    into product_ids[] so selections survive paginated navigation.
"""
from __future__ import annotations
import sys

PATH = "web_app.py"
NEW  = "new_marketplace_pagination.py"
BEGIN = b"# === BEGIN: marketplace_pagination splice ==="
END   = b"# === END: marketplace_pagination splice ==="

def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    new_block = open(NEW, "rb").read().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    orig_len = len(data)
    log = []

    # ---- splice module ----
    if BEGIN in data and END in data:
        s = data.find(BEGIN)
        e = data.find(END, s) + len(END)
        data = data[:s] + new_block.rstrip(b"\r\n") + data[e:]
        log.append("(splice) pagination block replaced.")
    else:
        anchor = b"if __name__ == \"__main__\":"
        pos = data.rfind(anchor)
        if pos < 0:
            log.append("(splice) anchor not found -- aborting.")
            print("\n".join(log)); sys.exit(2)
        data = data[:pos] + new_block + b"\r\n\r\n" + data[pos:]
        log.append("(splice) pagination block spliced before __main__.")

    # ---- (2) marketplace_public: pagination ----
    n_mp = (
        b"        sql += \"ORDER BY ec.created_at DESC LIMIT 200\"\r\n"
        b"        products = c.execute(sql, args).fetchall()\r\n"
        b"\r\n"
        b"        total_products = c.execute(\r\n"
    )
    r_mp = (
        b"        # 2026-06-22 (session B): admin-tunable pagination.\r\n"
        b"        _ppp = _products_per_page()\r\n"
        b"        try: _page = max(1, int(request.args.get(\"page\") or 1))\r\n"
        b"        except (TypeError, ValueError): _page = 1\r\n"
        b"        _offset = (_page - 1) * _ppp\r\n"
        b"        # Count rows that match THIS filter, not the global catalogue.\r\n"
        b"        _count_sql = sql.replace(\r\n"
        b"            \"SELECT ec.id, ec.name, ec.brand, ec.model, ec.spec, ec.unit,        ec.price_usd, ec.lead_time_days, ec.subcategory,        ec.literature_url, ec.datasheet_url,        ec.image_url, ec.category_id,        s.name AS supplier_name, s.country AS supplier_country,        s.rating AS supplier_rating,        pc.name AS category_name, pc.icon AS category_icon \", \"SELECT COUNT(*) \"\r\n"
        b"        )\r\n"
        b"        try:\r\n"
        b"            _filter_count = c.execute(_count_sql, args).fetchone()[0]\r\n"
        b"        except Exception:\r\n"
        b"            _filter_count = 0\r\n"
        b"        _total_pages = max(1, (int(_filter_count) + _ppp - 1) // _ppp)\r\n"
        b"        if _page > _total_pages:\r\n"
        b"            _page = _total_pages\r\n"
        b"            _offset = (_page - 1) * _ppp\r\n"
        b"        sql += \"ORDER BY ec.created_at DESC LIMIT ? OFFSET ?\"\r\n"
        b"        products = c.execute(sql, args + [_ppp, _offset]).fetchall()\r\n"
        b"\r\n"
        b"        total_products = c.execute(\r\n"
    )
    if n_mp in data:
        data = data.replace(n_mp, r_mp, 1)
        log.append("(2) marketplace_public paginated.")
    elif b"# 2026-06-22 (session B): admin-tunable pagination." in data:
        log.append("(2) marketplace_public already paginated.")
    else:
        log.append("(2) marketplace_public anchor NOT FOUND.")

    # marketplace_public render_template -- add page params
    n_mp_render = (
        b"        rates_as_of=_CURRENCY_RATES_AS_OF,\r\n"
        b"    )\r\n"
        b"\r\n"
        b"\r\n"
        b"@app.route(\"/marketplace/action/<string:action>\")\r\n"
    )
    r_mp_render = (
        b"        rates_as_of=_CURRENCY_RATES_AS_OF,\r\n"
        b"        page=_page, total_pages=_total_pages, products_per_page=_ppp,\r\n"
        b"        filter_count=_filter_count,\r\n"
        b"    )\r\n"
        b"\r\n"
        b"\r\n"
        b"@app.route(\"/marketplace/action/<string:action>\")\r\n"
    )
    if n_mp_render in data:
        data = data.replace(n_mp_render, r_mp_render, 1)
        log.append("(2b) marketplace_public renders page/total_pages.")
    elif b"page=_page, total_pages=_total_pages, products_per_page=_ppp," in data:
        log.append("(2b) marketplace_public render already wired.")
    else:
        log.append("(2b) marketplace_public render anchor NOT FOUND.")

    # ---- (3) procurement_center: pagination ----
    n_pc = (
        b"        sql += \"ORDER BY ec.created_at DESC LIMIT 200\"\r\n"
        b"        products = c.execute(sql, args).fetchall()\r\n"
        b"\r\n"
        b"    # Pre-compute per-product converted price for the template.\r\n"
    )
    r_pc = (
        b"        # 2026-06-22 (session B): admin-tunable pagination.\r\n"
        b"        _ppp = _products_per_page()\r\n"
        b"        try: _page = max(1, int(request.args.get(\"page\") or 1))\r\n"
        b"        except (TypeError, ValueError): _page = 1\r\n"
        b"        _offset = (_page - 1) * _ppp\r\n"
        b"        _count_sql = sql.replace(\r\n"
        b"            \"SELECT ec.id, ec.name, ec.brand, ec.model, ec.spec, ec.unit,        ec.price_usd, ec.lead_time_days, ec.category_id,        ec.literature_url, ec.datasheet_url,        s.name AS supplier_name, s.country AS supplier_country,        s.phone AS supplier_phone, s.email AS supplier_email,        pc.name AS category_name, pc.icon AS category_icon \", \"SELECT COUNT(*) \"\r\n"
        b"        )\r\n"
        b"        try:\r\n"
        b"            _filter_count = c.execute(_count_sql, args).fetchone()[0]\r\n"
        b"        except Exception:\r\n"
        b"            _filter_count = 0\r\n"
        b"        _total_pages = max(1, (int(_filter_count) + _ppp - 1) // _ppp)\r\n"
        b"        if _page > _total_pages:\r\n"
        b"            _page = _total_pages\r\n"
        b"            _offset = (_page - 1) * _ppp\r\n"
        b"        sql += \"ORDER BY ec.created_at DESC LIMIT ? OFFSET ?\"\r\n"
        b"        products = c.execute(sql, args + [_ppp, _offset]).fetchall()\r\n"
        b"\r\n"
        b"    # Pre-compute per-product converted price for the template.\r\n"
    )
    if n_pc in data:
        data = data.replace(n_pc, r_pc, 1)
        log.append("(3) procurement_center paginated.")
    elif b"        _ppp = _products_per_page()\r\n        try: _page = max(1, int(request.args.get(\"page\") or 1))" in data:
        log.append("(3) procurement_center already paginated.")
    else:
        log.append("(3) procurement_center anchor NOT FOUND.")

    # procurement_center render_template -- add page params
    # Box-drawing separator U+2500 in the source means we anchor without it.
    n_pc_render = (
        b"        rates_as_of=_CURRENCY_RATES_AS_OF,\r\n"
        b"    )\r\n"
        b"\r\n"
        b"\r\n"
        b"# "
        b"\xe2\x94\x80" * 24 + b" POST /procurement-center/add " + b"\xe2\x94\x80" * 18 + b"\r\n"
    )
    r_pc_render = (
        b"        rates_as_of=_CURRENCY_RATES_AS_OF,\r\n"
        b"        page=_page, total_pages=_total_pages, products_per_page=_ppp,\r\n"
        b"        filter_count=_filter_count,\r\n"
        b"    )\r\n"
        b"\r\n"
        b"\r\n"
        b"# "
        b"\xe2\x94\x80" * 24 + b" POST /procurement-center/add " + b"\xe2\x94\x80" * 18 + b"\r\n"
    )
    if n_pc_render in data:
        data = data.replace(n_pc_render, r_pc_render, 1)
        log.append("(3b) procurement_center renders page/total_pages.")
    elif b"page=_page, total_pages=_total_pages, products_per_page=_ppp,\r\n        filter_count=_filter_count," in data:
        log.append("(3b) procurement_center render already wired.")
    else:
        log.append("(3b) procurement_center render anchor NOT FOUND.")

    # ---- (4) procurement_center_add: merge stored_ids[] ----
    # Find the form-parse block. The function name + first lines:
    n_add = (
        b"def procurement_center_add():\r\n"
        b"    \"\"\"Take the checked product IDs from the form + the chosen doc type\r\n"
        b"    + currency, and create the new doc populated with those products.\"\"\"\r\n"
        b"    csrf_protect()\r\n"
    )
    r_add = (
        b"def procurement_center_add():\r\n"
        b"    \"\"\"Take the checked product IDs from the form + the chosen doc type\r\n"
        b"    + currency, and create the new doc populated with those products.\r\n"
        b"\r\n"
        b"    2026-06-22 (session B): also accept `stored_ids` (CSV from the\r\n"
        b"    sessionStorage layer) so paginated selections aren't lost when the\r\n"
        b"    user clicks Add on a later page.\r\n"
        b"    \"\"\"\r\n"
        b"    csrf_protect()\r\n"
        b"    # Merge form checkboxes + persisted sessionStorage IDs.\r\n"
        b"    try:\r\n"
        b"        _stored = (request.form.get(\"stored_ids\") or \"\").strip()\r\n"
        b"        _extra = [s for s in _stored.split(\",\") if s.strip().isdigit()]\r\n"
        b"        if _extra:\r\n"
        b"            _form_list = list(request.form.getlist(\"product_ids\"))\r\n"
        b"            _merged = list(dict.fromkeys(_form_list + _extra))  # de-dup, keep order\r\n"
        b"            # Inject into request.form's getlist by adding to a ImmutableMultiDict copy.\r\n"
        b"            try:\r\n"
        b"                from werkzeug.datastructures import ImmutableMultiDict\r\n"
        b"                pairs = list(request.form.items(multi=True))\r\n"
        b"                pairs = [(k, v) for k, v in pairs if k != \"product_ids\"]\r\n"
        b"                pairs += [(\"product_ids\", str(x)) for x in _merged]\r\n"
        b"                request.form = ImmutableMultiDict(pairs)\r\n"
        b"            except Exception:\r\n"
        b"                pass\r\n"
        b"    except Exception:\r\n"
        b"        pass\r\n"
    )
    if n_add in data:
        data = data.replace(n_add, r_add, 1)
        log.append("(4) procurement_center_add merges stored_ids.")
    elif b"2026-06-22 (session B): also accept `stored_ids`" in data:
        log.append("(4) procurement_center_add already merges stored_ids.")
    else:
        log.append("(4) procurement_center_add anchor NOT FOUND.")

    if len(data) == orig_len and data == open(PATH, "rb").read():
        log.append("\nNo changes -- already patched.")
        print("\n".join(log))
        return
    with open(PATH, "wb") as fh:
        fh.write(data)
    log.append(f"\nwrote {PATH} ({orig_len} -> {len(data)} bytes)")
    print("\n".join(log))

if __name__ == "__main__":
    main()
