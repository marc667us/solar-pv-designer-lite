#!/usr/bin/env python3
"""patch_boms_add_item_fields.py -- 2026-06-22 (session A).

Make /boms/<id>/items/add capture description / specification / brand from
the BOM editor's Add form (qty stays required at the HTML layer; this patch
backs that up server-side).
"""
from __future__ import annotations
import sys

PATH = "web_app.py"

def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    orig = data

    needle = (
        b"    with get_db() as c:\r\n"
        b"        c.execute(\r\n"
        b"            \"INSERT INTO marketplace_bom_items \"\r\n"
        b"            \"(bom_id, product_id, custom_name, qty, unit, unit_price_override, notes) \"\r\n"
        b"            \"VALUES (?,?,?,?,?,?,?)\",\r\n"
        b"            (bom_id, pid, name, qty,\r\n"
        b"             (f.get(\"unit\") or \"No.\").strip(),\r\n"
        b"             override,\r\n"
        b"             (f.get(\"notes\") or \"\").strip()),\r\n"
        b"        )\r\n"
    )
    repl = (
        b"    # 2026-06-22 (session A): description / specification / brand from BOM editor.\r\n"
        b"    description    = (f.get(\"description\") or \"\").strip()[:500]\r\n"
        b"    specification  = (f.get(\"specification\") or \"\").strip()[:500]\r\n"
        b"    brand          = (f.get(\"brand\") or \"\").strip()[:120]\r\n"
        b"    with get_db() as c:\r\n"
        b"        try:\r\n"
        b"            c.execute(\r\n"
        b"                \"INSERT INTO marketplace_bom_items \"\r\n"
        b"                \"(bom_id, product_id, custom_name, qty, unit, unit_price_override, notes, description, specification, brand) \"\r\n"
        b"                \"VALUES (?,?,?,?,?,?,?,?,?,?)\",\r\n"
        b"                (bom_id, pid, name, qty,\r\n"
        b"                 (f.get(\"unit\") or \"No.\").strip(),\r\n"
        b"                 override,\r\n"
        b"                 (f.get(\"notes\") or \"\").strip(),\r\n"
        b"                 description, specification, brand),\r\n"
        b"            )\r\n"
        b"        except Exception:\r\n"
        b"            # Schema not yet migrated -- fall back to legacy 7-col INSERT.\r\n"
        b"            c.execute(\r\n"
        b"                \"INSERT INTO marketplace_bom_items \"\r\n"
        b"                \"(bom_id, product_id, custom_name, qty, unit, unit_price_override, notes) \"\r\n"
        b"                \"VALUES (?,?,?,?,?,?,?)\",\r\n"
        b"                (bom_id, pid, name, qty,\r\n"
        b"                 (f.get(\"unit\") or \"No.\").strip(),\r\n"
        b"                 override,\r\n"
        b"                 (f.get(\"notes\") or \"\").strip()),\r\n"
        b"            )\r\n"
    )
    if needle in data:
        data = data.replace(needle, repl, 1)
        print("(1) boms_add_item INSERT extended with description/specification/brand.")
    elif b"# 2026-06-22 (session A): description / specification / brand from BOM editor." in data:
        print("(1) boms_add_item already patched.")
    else:
        print("(1) boms_add_item anchor NOT FOUND -- aborting.")
        sys.exit(2)

    if data == orig:
        print("No changes.")
        return
    with open(PATH, "wb") as fh:
        fh.write(data)
    print(f"wrote {PATH} ({len(orig)} -> {len(data)} bytes)")

if __name__ == "__main__":
    main()
