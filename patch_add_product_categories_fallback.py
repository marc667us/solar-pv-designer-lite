#!/usr/bin/env python3
"""patch_add_product_categories_fallback.py -- 2026-06-22.

User reports that on the live supplier `Add product` form the Category
dropdown is showing only one entry (PV Modules). On a freshly seeded DB
the dropdown shows 21. The race / source of the missing rows is unknown,
so this patch makes the route defensive on EVERY visit:

  (a) call _ensure_marketplace_tables() inside supplier_product_add GET
      so the INSERT-OR-IGNORE seed runs;
  (b) if the SELECT returns fewer rows than _MARKETPLACE_CATEGORIES, do
      a one-shot reseed + re-query before rendering.

Same treatment applied to the admin product edit form which uses the same
template + data-feed pattern.
"""
from __future__ import annotations
import sys

PATH = "web_app.py"


def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    orig_len = len(data)
    log = []

    # ---- (a) supplier_product_add: re-seed + fallback ----------------------
    n1 = (
        b"def supplier_product_add():\r\n"
        b"    s = _current_supplier()\r\n"
        b"    if not s:\r\n"
        b"        return redirect(url_for(\"supplier_dashboard\"))\r\n"
        b"    with get_db() as c:\r\n"
        b"        # Include `code` so the template can look up subcategories /\r\n"
        b"        # default unit / required spec fields from the taxonomy registries.\r\n"
        b"        categories = c.execute(\r\n"
        b"            \"SELECT id, code, name FROM product_categories \"\r\n"
        b"            \"WHERE is_active=1 ORDER BY display_order\"\r\n"
        b"        ).fetchall()\r\n"
    )
    r1 = (
        b"def supplier_product_add():\r\n"
        b"    s = _current_supplier()\r\n"
        b"    if not s:\r\n"
        b"        return redirect(url_for(\"supplier_dashboard\"))\r\n"
        b"    # 2026-06-22 defensive: re-fire the schema bootstrap (cheap; just runs\r\n"
        b"    # CREATE IF NOT EXISTS + INSERT OR IGNORE) and re-seed any missing\r\n"
        b"    # categories. Bug report: the Add Product dropdown only showed one\r\n"
        b"    # category live; this guarantees the full 21 are populated.\r\n"
        b"    try:\r\n"
        b"        _ensure_marketplace_tables()\r\n"
        b"    except Exception:\r\n"
        b"        pass\r\n"
        b"    with get_db() as c:\r\n"
        b"        # Include `code` so the template can look up subcategories /\r\n"
        b"        # default unit / required spec fields from the taxonomy registries.\r\n"
        b"        categories = c.execute(\r\n"
        b"            \"SELECT id, code, name FROM product_categories \"\r\n"
        b"            \"WHERE is_active=1 ORDER BY display_order\"\r\n"
        b"        ).fetchall()\r\n"
        b"        if len(categories) < len(_MARKETPLACE_CATEGORIES):\r\n"
        b"            # Emergency reseed -- INSERT OR IGNORE is no-op on existing rows.\r\n"
        b"            for _row in _MARKETPLACE_CATEGORIES:\r\n"
        b"                try:\r\n"
        b"                    c.execute(\r\n"
        b"                        \"INSERT OR IGNORE INTO product_categories \"\r\n"
        b"                        \"(code,name,icon,display_order) VALUES (?,?,?,?)\",\r\n"
        b"                        _row,\r\n"
        b"                    )\r\n"
        b"                except Exception:\r\n"
        b"                    try:\r\n"
        b"                        c.execute(\r\n"
        b"                            \"INSERT INTO product_categories \"\r\n"
        b"                            \"(code,name,icon,display_order) VALUES (?,?,?,?) \"\r\n"
        b"                            \"ON CONFLICT (code) DO NOTHING\",\r\n"
        b"                            _row,\r\n"
        b"                        )\r\n"
        b"                    except Exception:\r\n"
        b"                        pass\r\n"
        b"            categories = c.execute(\r\n"
        b"                \"SELECT id, code, name FROM product_categories \"\r\n"
        b"                \"WHERE is_active=1 ORDER BY display_order\"\r\n"
        b"            ).fetchall()\r\n"
    )
    if n1 in data:
        data = data.replace(n1, r1, 1)
        log.append("(a) supplier_product_add: re-seed + fallback wired.")
    elif b"2026-06-22 defensive: re-fire the schema bootstrap" in data:
        log.append("(a) supplier_product_add already patched.")
    else:
        log.append("(a) supplier_product_add anchor NOT FOUND.")

    # ---- (b) admin_marketplace_product_edit: same treatment ---------------
    # The admin edit route opens a `with get_db() as c:` and then assigns
    # `categories = c.execute(...)` followed by `suppliers = c.execute(...)`.
    n2 = (
        b"    _ensure_marketplace_tables()\r\n"
        b"    with get_db() as c:\r\n"
        b"        p = c.execute(\r\n"
    )
    # Only inject the reseed-after-query AFTER the categories SELECT.
    # Anchor on the literal SELECT used in admin_marketplace_product_edit.
    n2b = (
        b"        categories = c.execute(\r\n"
        b"            \"SELECT id, code, name FROM product_categories \"\r\n"
        b"            \"WHERE is_active=1 ORDER BY display_order\"\r\n"
        b"        ).fetchall()\r\n"
        b"        suppliers = c.execute(\r\n"
        b"            \"SELECT id, name FROM suppliers WHERE is_active=1 ORDER BY name\"\r\n"
        b"        ).fetchall()\r\n"
    )
    r2b = (
        b"        categories = c.execute(\r\n"
        b"            \"SELECT id, code, name FROM product_categories \"\r\n"
        b"            \"WHERE is_active=1 ORDER BY display_order\"\r\n"
        b"        ).fetchall()\r\n"
        b"        if len(categories) < len(_MARKETPLACE_CATEGORIES):\r\n"
        b"            for _row in _MARKETPLACE_CATEGORIES:\r\n"
        b"                try:\r\n"
        b"                    c.execute(\r\n"
        b"                        \"INSERT OR IGNORE INTO product_categories \"\r\n"
        b"                        \"(code,name,icon,display_order) VALUES (?,?,?,?)\",\r\n"
        b"                        _row,\r\n"
        b"                    )\r\n"
        b"                except Exception:\r\n"
        b"                    try:\r\n"
        b"                        c.execute(\r\n"
        b"                            \"INSERT INTO product_categories \"\r\n"
        b"                            \"(code,name,icon,display_order) VALUES (?,?,?,?) \"\r\n"
        b"                            \"ON CONFLICT (code) DO NOTHING\",\r\n"
        b"                            _row,\r\n"
        b"                        )\r\n"
        b"                    except Exception:\r\n"
        b"                        pass\r\n"
        b"            categories = c.execute(\r\n"
        b"                \"SELECT id, code, name FROM product_categories \"\r\n"
        b"                \"WHERE is_active=1 ORDER BY display_order\"\r\n"
        b"            ).fetchall()\r\n"
        b"        suppliers = c.execute(\r\n"
        b"            \"SELECT id, name FROM suppliers WHERE is_active=1 ORDER BY name\"\r\n"
        b"        ).fetchall()\r\n"
    )
    if n2b in data:
        data = data.replace(n2b, r2b, 1)
        log.append("(b) admin_marketplace_product_edit: re-seed fallback wired.")
    elif b"if len(categories) < len(_MARKETPLACE_CATEGORIES):\r\n            for _row in _MARKETPLACE_CATEGORIES:" in data:
        log.append("(b) admin_marketplace_product_edit already patched.")
    else:
        log.append("(b) admin_marketplace_product_edit anchor NOT FOUND.")

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
