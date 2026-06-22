#!/usr/bin/env python3
"""patch_marketplace_brands.py -- 2026-06-22.

Splice new_marketplace_brands.py into web_app.py and wire the brands list
into every Add Product handler so the brand <select> dropdown has data:
  - supplier_product_add        (was already showing categories from DB)
  - supplier_product_edit
  - admin_marketplace_product_edit
  - procurement_catalog

Plus call _seed_marketplace_brands() inside _ensure_marketplace_tables on
both SQLite and Postgres branches.
"""
from __future__ import annotations
import sys

PATH = "web_app.py"
NEW  = "new_marketplace_brands.py"
BEGIN = b"# === BEGIN: marketplace_brands splice ==="
END   = b"# === END: marketplace_brands splice ==="

def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    new_block = open(NEW, "rb").read().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    orig_len = len(data)
    log = []

    # ---- splice module ---------------------------------------------------
    if BEGIN in data and END in data:
        s = data.find(BEGIN)
        e = data.find(END, s) + len(END)
        data = data[:s] + new_block.rstrip(b"\r\n") + data[e:]
        log.append("(splice) marketplace_brands block replaced.")
    else:
        anchor = b"if __name__ == \"__main__\":"
        pos = data.rfind(anchor)
        if pos < 0:
            log.append("(splice) anchor `if __name__` not found -- aborting.")
            print("\n".join(log)); sys.exit(2)
        data = data[:pos] + new_block + b"\r\n\r\n" + data[pos:]
        log.append("(splice) marketplace_brands block spliced before __main__.")

    # ---- hook seed into _ensure_marketplace_tables (SQLite branch) -------
    n_sqlite_hook = (
        b"    # 2026-06-22: seed canonical Ghana-local suppliers + their price-sheet products.\r\n"
        b"    try: _seed_ghana_suppliers_products()\r\n"
        b"    except Exception: pass\r\n"
    )
    r_sqlite_hook = (
        b"    # 2026-06-22: seed canonical Ghana-local suppliers + their price-sheet products.\r\n"
        b"    try: _seed_ghana_suppliers_products()\r\n"
        b"    except Exception: pass\r\n"
        b"    # 2026-06-22 (session B): seed product_brands.\r\n"
        b"    try: _seed_marketplace_brands()\r\n"
        b"    except Exception: pass\r\n"
    )
    if n_sqlite_hook in data and b"# 2026-06-22 (session B): seed product_brands." not in data:
        data = data.replace(n_sqlite_hook, r_sqlite_hook, 1)
        log.append("(hook-sqlite) brands seed wired into SQLite branch.")
    elif b"# 2026-06-22 (session B): seed product_brands." in data:
        log.append("(hook-sqlite) already wired.")
    else:
        log.append("(hook-sqlite) anchor NOT FOUND.")

    # ---- hook seed into _ensure_marketplace_tables (Postgres branch) -----
    n_pg_hook = (
        b"        # 2026-06-22: also seed canonical Ghana suppliers + products on Postgres.\r\n"
        b"        try: _seed_ghana_suppliers_products()\r\n"
        b"        except Exception: pass\r\n"
        b"        return\r\n"
    )
    r_pg_hook = (
        b"        # 2026-06-22: also seed canonical Ghana suppliers + products on Postgres.\r\n"
        b"        try: _seed_ghana_suppliers_products()\r\n"
        b"        except Exception: pass\r\n"
        b"        # 2026-06-22 (session B): seed product_brands on Postgres too.\r\n"
        b"        try: _seed_marketplace_brands()\r\n"
        b"        except Exception: pass\r\n"
        b"        return\r\n"
    )
    if n_pg_hook in data and b"# 2026-06-22 (session B): seed product_brands on Postgres too." not in data:
        data = data.replace(n_pg_hook, r_pg_hook, 1)
        log.append("(hook-pg) brands seed wired into Postgres branch.")
    elif b"# 2026-06-22 (session B): seed product_brands on Postgres too." in data:
        log.append("(hook-pg) already wired.")
    else:
        log.append("(hook-pg) anchor NOT FOUND.")

    # ---- pass brands into supplier_product_add ---------------------------
    n_spa = (
        b"        _subs_m, _units_m, _specs_m = _merged_marketplace_taxonomy()\r\n"
        b"        return render_template(\r\n"
        b"            \"supplier_product_add.html\",\r\n"
        b"            user=current_user(),\r\n"
        b"            supplier=s,\r\n"
        b"            categories=categories,\r\n"
        b"            subcategories_by_code=_subs_m,\r\n"
        b"            default_unit_by_code=_units_m,\r\n"
        b"            spec_fields_by_code=_specs_m,\r\n"
        b"        )\r\n"
    )
    r_spa = (
        b"        _subs_m, _units_m, _specs_m = _merged_marketplace_taxonomy()\r\n"
        b"        brands = _get_active_brands()\r\n"
        b"        return render_template(\r\n"
        b"            \"supplier_product_add.html\",\r\n"
        b"            user=current_user(),\r\n"
        b"            supplier=s,\r\n"
        b"            categories=categories,\r\n"
        b"            brands=brands,\r\n"
        b"            subcategories_by_code=_subs_m,\r\n"
        b"            default_unit_by_code=_units_m,\r\n"
        b"            spec_fields_by_code=_specs_m,\r\n"
        b"        )\r\n"
    )
    if n_spa in data:
        data = data.replace(n_spa, r_spa, 1)
        log.append("(forms-spa) supplier_product_add now passes brands.")
    elif b"brands = _get_active_brands()" in data:
        log.append("(forms-spa) already wired.")
    else:
        log.append("(forms-spa) anchor NOT FOUND.")

    # ---- pass brands into supplier_product_edit --------------------------
    n_spe = (
        b"    if request.method == \"GET\":\r\n"
        b"        return render_template(\r\n"
        b"            \"supplier_product_edit.html\",\r\n"
        b"            user=current_user(),\r\n"
        b"            supplier=s,\r\n"
        b"            product=row,\r\n"
        b"            categories=categories,\r\n"
        b"        )\r\n"
    )
    r_spe = (
        b"    if request.method == \"GET\":\r\n"
        b"        return render_template(\r\n"
        b"            \"supplier_product_edit.html\",\r\n"
        b"            user=current_user(),\r\n"
        b"            supplier=s,\r\n"
        b"            product=row,\r\n"
        b"            categories=categories,\r\n"
        b"            brands=_get_active_brands(),\r\n"
        b"        )\r\n"
    )
    if n_spe in data:
        data = data.replace(n_spe, r_spe, 1)
        log.append("(forms-spe) supplier_product_edit now passes brands.")
    elif b"brands=_get_active_brands()," in data:
        log.append("(forms-spe) already wired.")
    else:
        log.append("(forms-spe) anchor NOT FOUND.")

    # ---- pass brands into admin_marketplace_product_edit -----------------
    n_ampe = (
        b"        _subs_m, _units_m, _specs_m = _merged_marketplace_taxonomy()\r\n"
        b"        return render_template(\r\n"
        b"            \"admin_marketplace_product_edit.html\",\r\n"
        b"            user=current_user(), product=p, categories=categories, suppliers=suppliers,\r\n"
        b"            subcategories_by_code=_subs_m,\r\n"
        b"            default_unit_by_code=_units_m,\r\n"
        b"            spec_fields_by_code=_specs_m,\r\n"
        b"        )\r\n"
    )
    r_ampe = (
        b"        _subs_m, _units_m, _specs_m = _merged_marketplace_taxonomy()\r\n"
        b"        return render_template(\r\n"
        b"            \"admin_marketplace_product_edit.html\",\r\n"
        b"            user=current_user(), product=p, categories=categories, suppliers=suppliers,\r\n"
        b"            brands=_get_active_brands(),\r\n"
        b"            subcategories_by_code=_subs_m,\r\n"
        b"            default_unit_by_code=_units_m,\r\n"
        b"            spec_fields_by_code=_specs_m,\r\n"
        b"        )\r\n"
    )
    if n_ampe in data:
        data = data.replace(n_ampe, r_ampe, 1)
        log.append("(forms-ampe) admin_marketplace_product_edit now passes brands.")
    elif b"brands=_get_active_brands(),\r\n            subcategories_by_code=_subs_m," in data:
        log.append("(forms-ampe) already wired.")
    else:
        log.append("(forms-ampe) anchor NOT FOUND.")

    # ---- pass brands into procurement_catalog ----------------------------
    n_pc = (
        b"    return render_template(\"procurement_catalog.html\", user=current_user(),\r\n"
        b"                           items=items, suppliers=suppliers, categories=categories)\r\n"
    )
    r_pc = (
        b"    return render_template(\"procurement_catalog.html\", user=current_user(),\r\n"
        b"                           items=items, suppliers=suppliers, categories=categories,\r\n"
        b"                           brands=_get_active_brands())\r\n"
    )
    if n_pc in data:
        data = data.replace(n_pc, r_pc, 1)
        log.append("(forms-pc) procurement_catalog now passes brands.")
    elif b"brands=_get_active_brands())\r\n" in data:
        log.append("(forms-pc) already wired.")
    else:
        log.append("(forms-pc) anchor NOT FOUND.")

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
