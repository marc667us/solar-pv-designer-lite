#!/usr/bin/env python3
"""patch_procurement_catalog_categories.py -- 2026-06-22.

The admin Product Catalogue page (/procurement/catalog) has its own Add
Product modal whose Category dropdown was hardcoded to 10 solar-only labels
(PV Modules, Inverters, Batteries, MPPT, Cables, Protection, Earthing,
Mounting, Testing, Sundries). Owner wants the full 21 marketplace
categories (transformers / panel boards / sockets / power_system / etc.)
to be selectable there too.

Patches:
  (1) Replace the hardcoded `cats` list with a DB query against
      product_categories (active rows, display_order sort).
  (2) Add the same re-seed fallback we shipped for supplier_product_add so
      the dropdown is robust even on a partially-seeded DB.
  (3) Make the POST 'add' branch read category_id from the form, look up
      the matching product_categories row, and write BOTH the FK
      (category_id) AND the free-text 'category' column so legacy queries
      that still hit the free-text column keep working.
  (4) Same for the 'edit' branch.
"""
from __future__ import annotations
import sys

PATH = "web_app.py"


def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    orig_len = len(data)
    log = []

    # ---- (1)+(2) Replace hardcoded cats with DB-driven categories ----------
    n_cats = (
        b"    with get_db() as c:\r\n"
        b"        items = c.execute(\r\n"
        b"            \"SELECT e.*, s.name as sup_name FROM equipment_catalog e \"\r\n"
        b"            \"LEFT JOIN suppliers s ON e.supplier_id=s.id ORDER BY e.category, e.name\").fetchall()\r\n"
        b"        suppliers = c.execute(\"SELECT id,name FROM suppliers WHERE is_active=1\").fetchall()\r\n"
        b"    cats = [\"PV Modules\",\"Inverters\",\"Batteries\",\"MPPT\",\"Cables\",\r\n"
        b"            \"Protection\",\"Earthing\",\"Mounting\",\"Testing\",\"Sundries\"]\r\n"
        b"    return render_template(\"procurement_catalog.html\", user=current_user(),\r\n"
        b"                           items=items, suppliers=suppliers, categories=cats)\r\n"
    )
    r_cats = (
        b"    # 2026-06-22 defensive: fire the marketplace ensure so product_categories exists\r\n"
        b"    # and the 21-entry taxonomy is seeded (was previously solar-only hardcoded list).\r\n"
        b"    try:\r\n"
        b"        _ensure_marketplace_tables()\r\n"
        b"    except Exception:\r\n"
        b"        pass\r\n"
        b"    with get_db() as c:\r\n"
        b"        items = c.execute(\r\n"
        b"            \"SELECT e.*, s.name as sup_name, pc.name AS pc_name FROM equipment_catalog e \"\r\n"
        b"            \"LEFT JOIN suppliers s ON e.supplier_id=s.id \"\r\n"
        b"            \"LEFT JOIN product_categories pc ON pc.id=e.category_id \"\r\n"
        b"            \"WHERE e.is_active=1 ORDER BY COALESCE(pc.display_order, 999), pc.name, e.name\").fetchall()\r\n"
        b"        suppliers = c.execute(\"SELECT id,name FROM suppliers WHERE is_active=1\").fetchall()\r\n"
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
        b"    return render_template(\"procurement_catalog.html\", user=current_user(),\r\n"
        b"                           items=items, suppliers=suppliers, categories=categories)\r\n"
    )
    if n_cats in data:
        data = data.replace(n_cats, r_cats, 1)
        log.append("(1+2) procurement_catalog: DB-driven categories + re-seed wired.")
    elif b"# 2026-06-22 defensive: fire the marketplace ensure so product_categories" in data:
        log.append("(1+2) procurement_catalog already patched.")
    else:
        log.append("(1+2) procurement_catalog anchor NOT FOUND.")

    # ---- (3) POST 'add' branch: write category_id + free-text name --------
    n_add = (
        b"            if action == \"add\":\r\n"
        b"                c.execute(\r\n"
        b"                    \"INSERT INTO equipment_catalog (category,name,brand,model,spec,unit,\"\r\n"
        b"                    \"price_usd,supplier_id,lead_time_days,notes) VALUES (?,?,?,?,?,?,?,?,?,?)\",\r\n"
        b"                    (f[\"category\"], f[\"name\"], f.get(\"brand\",\"\"), f.get(\"model\",\"\"),\r\n"
        b"                     f.get(\"spec\",\"\"), f.get(\"unit\",\"No.\"), float(f.get(\"price_usd\",0)),\r\n"
        b"                     int(f.get(\"supplier_id\",0)), int(f.get(\"lead_time_days\",30)),\r\n"
        b"                     f.get(\"notes\",\"\")))\r\n"
        b"                flash(\"Equipment added.\", \"success\")\r\n"
    )
    r_add = (
        b"            if action == \"add\":\r\n"
        b"                # 2026-06-22: accept either category_id (FK, new) or category (legacy free-text).\r\n"
        b"                _cat_id = 0\r\n"
        b"                try: _cat_id = int(f.get(\"category_id\") or 0)\r\n"
        b"                except (TypeError, ValueError): _cat_id = 0\r\n"
        b"                _cat_label = (f.get(\"category\") or \"\").strip()\r\n"
        b"                if _cat_id and not _cat_label:\r\n"
        b"                    _r = c.execute(\"SELECT name FROM product_categories WHERE id=?\", (_cat_id,)).fetchone()\r\n"
        b"                    if _r: _cat_label = _r[\"name\"] if hasattr(_r, \"keys\") else _r[0]\r\n"
        b"                c.execute(\r\n"
        b"                    \"INSERT INTO equipment_catalog (category,category_id,name,brand,model,spec,unit,\"\r\n"
        b"                    \"price_usd,supplier_id,lead_time_days,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)\",\r\n"
        b"                    (_cat_label, _cat_id, f[\"name\"], f.get(\"brand\",\"\"), f.get(\"model\",\"\"),\r\n"
        b"                     f.get(\"spec\",\"\"), f.get(\"unit\",\"No.\"), float(f.get(\"price_usd\",0)),\r\n"
        b"                     int(f.get(\"supplier_id\",0)), int(f.get(\"lead_time_days\",30)),\r\n"
        b"                     f.get(\"notes\",\"\")))\r\n"
        b"                flash(f\"Product added under '{_cat_label or 'Uncategorised'}'.\", \"success\")\r\n"
    )
    if n_add in data:
        data = data.replace(n_add, r_add, 1)
        log.append("(3) POST add branch now writes category_id + category name.")
    elif b"# 2026-06-22: accept either category_id (FK, new) or category (legacy free-text)." in data:
        log.append("(3) POST add already patched.")
    else:
        log.append("(3) POST add anchor NOT FOUND.")

    # ---- (4) POST 'edit' branch --------------------------------------------
    n_edit = (
        b"            elif action == \"edit\":\r\n"
        b"                eid = f.get(\"eid\", type=int)\r\n"
        b"                c.execute(\r\n"
        b"                    \"UPDATE equipment_catalog SET category=?,name=?,brand=?,model=?,spec=?,\"\r\n"
        b"                    \"unit=?,price_usd=?,supplier_id=?,lead_time_days=?,notes=? WHERE id=?\",\r\n"
        b"                    (f[\"category\"], f[\"name\"], f.get(\"brand\",\"\"), f.get(\"model\",\"\"),\r\n"
        b"                     f.get(\"spec\",\"\"), f.get(\"unit\",\"No.\"), float(f.get(\"price_usd\",0)),\r\n"
        b"                     int(f.get(\"supplier_id\",0)), int(f.get(\"lead_time_days\",30)),\r\n"
        b"                     f.get(\"notes\",\"\"), eid))\r\n"
        b"                flash(\"Equipment updated.\", \"success\")\r\n"
    )
    r_edit = (
        b"            elif action == \"edit\":\r\n"
        b"                eid = f.get(\"eid\", type=int)\r\n"
        b"                _cat_id = 0\r\n"
        b"                try: _cat_id = int(f.get(\"category_id\") or 0)\r\n"
        b"                except (TypeError, ValueError): _cat_id = 0\r\n"
        b"                _cat_label = (f.get(\"category\") or \"\").strip()\r\n"
        b"                if _cat_id and not _cat_label:\r\n"
        b"                    _r = c.execute(\"SELECT name FROM product_categories WHERE id=?\", (_cat_id,)).fetchone()\r\n"
        b"                    if _r: _cat_label = _r[\"name\"] if hasattr(_r, \"keys\") else _r[0]\r\n"
        b"                c.execute(\r\n"
        b"                    \"UPDATE equipment_catalog SET category=?,category_id=?,name=?,brand=?,model=?,spec=?,\"\r\n"
        b"                    \"unit=?,price_usd=?,supplier_id=?,lead_time_days=?,notes=? WHERE id=?\",\r\n"
        b"                    (_cat_label, _cat_id, f[\"name\"], f.get(\"brand\",\"\"), f.get(\"model\",\"\"),\r\n"
        b"                     f.get(\"spec\",\"\"), f.get(\"unit\",\"No.\"), float(f.get(\"price_usd\",0)),\r\n"
        b"                     int(f.get(\"supplier_id\",0)), int(f.get(\"lead_time_days\",30)),\r\n"
        b"                     f.get(\"notes\",\"\"), eid))\r\n"
        b"                flash(\"Product updated.\", \"success\")\r\n"
    )
    if n_edit in data:
        data = data.replace(n_edit, r_edit, 1)
        log.append("(4) POST edit branch now writes category_id + category name.")
    elif b"\"UPDATE equipment_catalog SET category=?,category_id=?,name=?,brand=?,model=?,spec=?,\"" in data:
        log.append("(4) POST edit already patched.")
    else:
        log.append("(4) POST edit anchor NOT FOUND.")

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
