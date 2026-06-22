#!/usr/bin/env python3
"""patch_admin_marketplace_categories_splice.py -- 2026-06-22 (session A).

Splice new_admin_marketplace_categories_routes.py into web_app.py and
re-wire the two product-form GET handlers to feed the merged taxonomy
(hardcoded registries + DB overrides + brand-new admin-added categories).
"""
from __future__ import annotations
import sys

PATH = "web_app.py"
NEW = "new_admin_marketplace_categories_routes.py"

BEGIN_MARK = b"# === BEGIN: admin_marketplace_categories splice ==="
END_MARK   = b"# === END: admin_marketplace_categories splice ==="

def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    new_block = open(NEW, "rb").read().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    orig_len = len(data)
    log = []

    # ---- 1. Splice / replace the routes block ------------------------------
    if BEGIN_MARK in data and END_MARK in data:
        start = data.find(BEGIN_MARK)
        end = data.find(END_MARK, start) + len(END_MARK)
        data = data[:start] + new_block.rstrip(b"\r\n") + data[end:]
        log.append("(1) admin_marketplace_categories block replaced.")
    else:
        anchor = b"if __name__ == \"__main__\":"
        pos = data.rfind(anchor)
        if pos < 0:
            log.append("(1) anchor `if __name__` not found -- aborting.")
            print("\n".join(log)); sys.exit(2)
        data = data[:pos] + new_block + b"\r\n\r\n" + data[pos:]
        log.append("(1) admin_marketplace_categories block spliced before __main__.")

    # ---- 2. Replace supplier_product_add() taxonomy wiring ------------------
    needle2 = (
        b"        return render_template(\r\n"
        b"            \"supplier_product_add.html\",\r\n"
        b"            user=current_user(),\r\n"
        b"            supplier=s,\r\n"
        b"            categories=categories,\r\n"
        b"            subcategories_by_code=_MARKETPLACE_SUBCATEGORIES,\r\n"
        b"            default_unit_by_code=_MARKETPLACE_DEFAULT_UNIT,\r\n"
        b"            spec_fields_by_code=_MARKETPLACE_SPEC_FIELDS,\r\n"
        b"        )\r\n"
    )
    repl2 = (
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
    if needle2 in data:
        data = data.replace(needle2, repl2, 1)
        log.append("(2) supplier_product_add now feeds merged taxonomy.")
    elif b"_subs_m, _units_m, _specs_m = _merged_marketplace_taxonomy()" in data:
        log.append("(2) supplier_product_add already feeds merged taxonomy.")
    else:
        log.append("(2) supplier_product_add taxonomy anchor NOT FOUND.")

    # ---- 3. Replace admin_marketplace_product_edit() taxonomy wiring -------
    #
    # We can't predict the exact form of the existing render_template call here
    # (admin templates differ between SQLite and Postgres branches), so search
    # for any render_template line that passes the three registries together
    # and rewrite it in-place. We do this with a coarse pattern then a
    # targeted replace on each occurrence.

    target_old = (
        b"subcategories_by_code=_MARKETPLACE_SUBCATEGORIES,\r\n"
        b"            default_unit_by_code=_MARKETPLACE_DEFAULT_UNIT,\r\n"
        b"            spec_fields_by_code=_MARKETPLACE_SPEC_FIELDS,\r\n"
    )
    target_new = (
        b"subcategories_by_code=_subs_m,\r\n"
        b"            default_unit_by_code=_units_m,\r\n"
        b"            spec_fields_by_code=_specs_m,\r\n"
    )
    count_remaining = data.count(target_old)
    if count_remaining:
        # Find every remaining match and add a single `_subs_m, _units_m, _specs_m`
        # initialisation just before each render_template call. Cheap + safe.
        idx = 0
        replaced = 0
        while True:
            pos = data.find(target_old, idx)
            if pos < 0:
                break
            # Find the start of the render_template(...) call (look upward
            # for "return render_template(" or "render_template(").
            # We just prefix a taxonomy resolution line right before it.
            rt_pos = data.rfind(b"return render_template(", 0, pos)
            if rt_pos < 0:
                # Fallback: leave this occurrence alone.
                idx = pos + len(target_old)
                continue
            indent_pos = data.rfind(b"\n", 0, rt_pos) + 1
            indent = data[indent_pos:rt_pos]
            inject = indent + b"_subs_m, _units_m, _specs_m = _merged_marketplace_taxonomy()\r\n"
            # Insert + apply the replace.
            data = data[:rt_pos] + inject + data[rt_pos:pos] + target_new + data[pos + len(target_old):]
            replaced += 1
            idx = rt_pos + len(inject) + (pos - rt_pos) + len(target_new)
        log.append(f"(3) replaced {replaced} more taxonomy callsite(s).")
    else:
        log.append("(3) no additional taxonomy callsites needed updating.")

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
