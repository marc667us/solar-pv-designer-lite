#!/usr/bin/env python3
"""patch_categories_pg_alters_and_pagination.py -- 2026-06-22 session B.

Two fixes:

(A) /admin/marketplace/categories returned 0 rows live because the SELECT
    includes default_unit/subcategories_csv/spec_fields_csv columns that
    only got ALTERed on the SQLite branch of _ensure_bom_tables. Add the
    same ALTERs to the Postgres branch of _ensure_marketplace_tables so
    the columns exist on Render too.

(B) Paginate /procurement/suppliers and /procurement/catalog with the
    same _products_per_page() knob the marketplace + procurement-center
    use. Render Prev/Next controls in templates.
"""
from __future__ import annotations
import sys

PATH = "web_app.py"


def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    orig_len = len(data)
    log = []

    # ---- (A) Add 3 ALTERs to Postgres branch of _ensure_marketplace_tables.
    n_pg_branch = (
        b"def _ensure_marketplace_tables():\r\n"
        b"    if bool(os.environ.get(\"DATABASE_URL\")):\r\n"
        b"        _ensure_marketplace_schema_postgres()\r\n"
        b"        # 2026-06-22: also seed canonical Ghana suppliers + products on Postgres.\r\n"
        b"        try: _seed_ghana_suppliers_products()\r\n"
        b"        except Exception: pass\r\n"
        b"        # 2026-06-22 (session B): seed product_brands on Postgres too.\r\n"
        b"        try: _seed_marketplace_brands()\r\n"
        b"        except Exception: pass\r\n"
        b"        return\r\n"
    )
    r_pg_branch = (
        b"def _ensure_marketplace_tables():\r\n"
        b"    if bool(os.environ.get(\"DATABASE_URL\")):\r\n"
        b"        _ensure_marketplace_schema_postgres()\r\n"
        b"        # 2026-06-22 (session B): extra columns on product_categories so the\r\n"
        b"        # admin Manage Categories page can SELECT them on Postgres too.\r\n"
        b"        for _ddl in (\r\n"
        b"            \"ALTER TABLE product_categories ADD COLUMN IF NOT EXISTS default_unit VARCHAR(20) DEFAULT 'No.'\",\r\n"
        b"            \"ALTER TABLE product_categories ADD COLUMN IF NOT EXISTS subcategories_csv TEXT DEFAULT ''\",\r\n"
        b"            \"ALTER TABLE product_categories ADD COLUMN IF NOT EXISTS spec_fields_csv TEXT DEFAULT ''\",\r\n"
        b"            \"ALTER TABLE boq_projects ADD COLUMN IF NOT EXISTS services_csv TEXT DEFAULT ''\",\r\n"
        b"            \"ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS description TEXT DEFAULT ''\",\r\n"
        b"            \"ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS specification TEXT DEFAULT ''\",\r\n"
        b"            \"ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT ''\",\r\n"
        b"        ):\r\n"
        b"            try:\r\n"
        b"                with get_db() as _c:\r\n"
        b"                    _c.execute(_ddl)\r\n"
        b"            except Exception:\r\n"
        b"                pass\r\n"
        b"        # 2026-06-22: also seed canonical Ghana suppliers + products on Postgres.\r\n"
        b"        try: _seed_ghana_suppliers_products()\r\n"
        b"        except Exception: pass\r\n"
        b"        # 2026-06-22 (session B): seed product_brands on Postgres too.\r\n"
        b"        try: _seed_marketplace_brands()\r\n"
        b"        except Exception: pass\r\n"
        b"        return\r\n"
    )
    if n_pg_branch in data:
        data = data.replace(n_pg_branch, r_pg_branch, 1)
        log.append("(A) Postgres ALTERs spliced into _ensure_marketplace_tables.")
    elif b"ALTER TABLE product_categories ADD COLUMN IF NOT EXISTS default_unit" in data:
        log.append("(A) Postgres ALTERs already present.")
    else:
        log.append("(A) Postgres ALTER anchor NOT FOUND.")

    # ---- (B1) Paginate /procurement/suppliers.
    n_sup = (
        b"    with get_db() as c:\r\n"
        b"        rows = c.execute(\"SELECT * FROM suppliers ORDER BY name\").fetchall()\r\n"
        b"    return render_template(\"procurement_suppliers.html\", user=current_user(), suppliers=rows)\r\n"
    )
    r_sup = (
        b"    # 2026-06-22 (session B): pagination + count.\r\n"
        b"    try: _ppp = _products_per_page()\r\n"
        b"    except Exception: _ppp = 24\r\n"
        b"    try: _page = max(1, int(request.args.get(\"page\") or 1))\r\n"
        b"    except (TypeError, ValueError): _page = 1\r\n"
        b"    with get_db() as c:\r\n"
        b"        _total = int(c.execute(\"SELECT COUNT(*) FROM suppliers\").fetchone()[0] or 0)\r\n"
        b"        _total_pages = max(1, (_total + _ppp - 1) // _ppp)\r\n"
        b"        if _page > _total_pages: _page = _total_pages\r\n"
        b"        _offset = (_page - 1) * _ppp\r\n"
        b"        rows = c.execute(\r\n"
        b"            \"SELECT * FROM suppliers ORDER BY name LIMIT ? OFFSET ?\",\r\n"
        b"            (_ppp, _offset),\r\n"
        b"        ).fetchall()\r\n"
        b"    return render_template(\r\n"
        b"        \"procurement_suppliers.html\", user=current_user(), suppliers=rows,\r\n"
        b"        page=_page, total_pages=_total_pages, products_per_page=_ppp,\r\n"
        b"        filter_count=_total,\r\n"
        b"    )\r\n"
    )
    if n_sup in data:
        data = data.replace(n_sup, r_sup, 1)
        log.append("(B1) /procurement/suppliers paginated.")
    elif b"# 2026-06-22 (session B): pagination + count.\r\n    try: _ppp = _products_per_page()" in data:
        log.append("(B1) /procurement/suppliers already paginated.")
    else:
        log.append("(B1) /procurement/suppliers anchor NOT FOUND.")

    # ---- (B2) Paginate /procurement/catalog.
    n_cat = (
        b"    with get_db() as c:\r\n"
        b"        items = c.execute(\r\n"
        b"            \"SELECT e.*, s.name as sup_name, pc.name AS pc_name FROM equipment_catalog e \"\r\n"
        b"            \"LEFT JOIN suppliers s ON e.supplier_id=s.id \"\r\n"
        b"            \"LEFT JOIN product_categories pc ON pc.id=e.category_id \"\r\n"
        b"            \"WHERE e.is_active=1 ORDER BY COALESCE(pc.display_order, 999), pc.name, e.name\").fetchall()\r\n"
    )
    r_cat = (
        b"    # 2026-06-22 (session B): pagination on the catalogue.\r\n"
        b"    try: _ppp_cat = _products_per_page()\r\n"
        b"    except Exception: _ppp_cat = 24\r\n"
        b"    try: _page_cat = max(1, int(request.args.get(\"page\") or 1))\r\n"
        b"    except (TypeError, ValueError): _page_cat = 1\r\n"
        b"    with get_db() as c:\r\n"
        b"        _total_cat = int(c.execute(\"SELECT COUNT(*) FROM equipment_catalog WHERE is_active=1\").fetchone()[0] or 0)\r\n"
        b"        _total_pages_cat = max(1, (_total_cat + _ppp_cat - 1) // _ppp_cat)\r\n"
        b"        if _page_cat > _total_pages_cat: _page_cat = _total_pages_cat\r\n"
        b"        _offset_cat = (_page_cat - 1) * _ppp_cat\r\n"
        b"        items = c.execute(\r\n"
        b"            \"SELECT e.*, s.name as sup_name, pc.name AS pc_name FROM equipment_catalog e \"\r\n"
        b"            \"LEFT JOIN suppliers s ON e.supplier_id=s.id \"\r\n"
        b"            \"LEFT JOIN product_categories pc ON pc.id=e.category_id \"\r\n"
        b"            \"WHERE e.is_active=1 ORDER BY COALESCE(pc.display_order, 999), pc.name, e.name \"\r\n"
        b"            \"LIMIT ? OFFSET ?\", (_ppp_cat, _offset_cat)).fetchall()\r\n"
    )
    if n_cat in data:
        data = data.replace(n_cat, r_cat, 1)
        log.append("(B2) /procurement/catalog SELECT paginated.")
    elif b"# 2026-06-22 (session B): pagination on the catalogue." in data:
        log.append("(B2) /procurement/catalog already paginated.")
    else:
        log.append("(B2) /procurement/catalog anchor NOT FOUND.")

    # Add pagination params to procurement_catalog render
    n_cat_render = (
        b"    return render_template(\"procurement_catalog.html\", user=current_user(),\r\n"
        b"                           items=items, suppliers=suppliers, categories=categories,\r\n"
        b"                           brands=_get_active_brands())\r\n"
    )
    r_cat_render = (
        b"    return render_template(\"procurement_catalog.html\", user=current_user(),\r\n"
        b"                           items=items, suppliers=suppliers, categories=categories,\r\n"
        b"                           brands=_get_active_brands(),\r\n"
        b"                           page=_page_cat, total_pages=_total_pages_cat,\r\n"
        b"                           products_per_page=_ppp_cat, filter_count=_total_cat)\r\n"
    )
    if n_cat_render in data:
        data = data.replace(n_cat_render, r_cat_render, 1)
        log.append("(B2b) /procurement/catalog render carries page params.")
    elif b"page=_page_cat, total_pages=_total_pages_cat," in data:
        log.append("(B2b) /procurement/catalog render already wired.")
    else:
        log.append("(B2b) /procurement/catalog render anchor NOT FOUND.")

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
