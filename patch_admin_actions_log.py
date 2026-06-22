#!/usr/bin/env python3
"""patch_admin_actions_log.py -- 2026-06-22.

(1) Splice new_admin_actions_log.py.
(2) Wire _log_marketplace_action() into 4 routes that don't log yet:
    - procurement_catalog (add / edit / delete branches)
    - procurement_suppliers (add / edit / delete branches)
    - admin_marketplace_settings POST
    - admin_marketplace_reseed_ghana POST
"""
from __future__ import annotations
import sys

PATH = "web_app.py"
NEW  = "new_admin_actions_log.py"
BEGIN = b"# === BEGIN: admin_actions_log splice ==="
END   = b"# === END: admin_actions_log splice ==="

def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    new_block = open(NEW, "rb").read().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    orig_len = len(data)
    log = []

    # ---- (1) Splice module ----
    if BEGIN in data and END in data:
        s = data.find(BEGIN)
        e = data.find(END, s) + len(END)
        data = data[:s] + new_block.rstrip(b"\r\n") + data[e:]
        log.append("(splice) admin_actions_log replaced.")
    else:
        anchor = b"if __name__ == \"__main__\":"
        pos = data.rfind(anchor)
        if pos < 0:
            log.append("(splice) anchor not found -- abort.")
            print("\n".join(log)); sys.exit(2)
        data = data[:pos] + new_block + b"\r\n\r\n" + data[pos:]
        log.append("(splice) admin_actions_log spliced before __main__.")

    # ---- (2a) procurement_suppliers add ----
    n_sup_add = (
        b"                     f.get(\"notes\",\"\")))\r\n"
        b"                flash(\"Supplier added.\", \"success\")\r\n"
    )
    r_sup_add = (
        b"                     f.get(\"notes\",\"\")))\r\n"
        b"                try: _log_marketplace_action(\"add_supplier_legacy\", \"supplier\", 0, f.get(\"name\",\"\"))\r\n"
        b"                except Exception: pass\r\n"
        b"                flash(\"Supplier added.\", \"success\")\r\n"
    )
    if n_sup_add in data:
        data = data.replace(n_sup_add, r_sup_add, 1)
        log.append("(2a) procurement_suppliers add logged.")
    else:
        log.append("(2a) procurement_suppliers add anchor NOT FOUND.")

    # ---- (2b) procurement_suppliers edit ----
    n_sup_edit = (
        b"                     f.get(\"notes\",\"\"), sid))\r\n"
        b"                flash(\"Supplier updated.\", \"success\")\r\n"
    )
    r_sup_edit = (
        b"                     f.get(\"notes\",\"\"), sid))\r\n"
        b"                try: _log_marketplace_action(\"edit_supplier_legacy\", \"supplier\", int(sid or 0), f.get(\"name\",\"\"))\r\n"
        b"                except Exception: pass\r\n"
        b"                flash(\"Supplier updated.\", \"success\")\r\n"
    )
    if n_sup_edit in data:
        data = data.replace(n_sup_edit, r_sup_edit, 1)
        log.append("(2b) procurement_suppliers edit logged.")
    else:
        log.append("(2b) procurement_suppliers edit anchor NOT FOUND.")

    # ---- (2c) procurement_suppliers delete ----
    n_sup_del = (
        b"            elif action == \"delete\":\r\n"
        b"                c.execute(\"UPDATE suppliers SET is_active=0 WHERE id=?\",\r\n"
        b"                          (f.get(\"sid\", type=int),))\r\n"
        b"                flash(\"Supplier deactivated.\", \"info\")\r\n"
    )
    r_sup_del = (
        b"            elif action == \"delete\":\r\n"
        b"                _sid = f.get(\"sid\", type=int)\r\n"
        b"                c.execute(\"UPDATE suppliers SET is_active=0 WHERE id=?\", (_sid,))\r\n"
        b"                try: _log_marketplace_action(\"delete_supplier_legacy\", \"supplier\", int(_sid or 0), \"soft-delete\")\r\n"
        b"                except Exception: pass\r\n"
        b"                flash(\"Supplier deactivated.\", \"info\")\r\n"
    )
    if n_sup_del in data:
        data = data.replace(n_sup_del, r_sup_del, 1)
        log.append("(2c) procurement_suppliers delete logged.")
    else:
        log.append("(2c) procurement_suppliers delete anchor NOT FOUND.")

    # ---- (2d) procurement_catalog add ----
    n_cat_add = (
        b"                flash(f\"Product added under '{_cat_label or 'Uncategorised'}'.\", \"success\")\r\n"
    )
    r_cat_add = (
        b"                try: _log_marketplace_action(\"add_product_catalog\", \"product\", 0, f\"{f.get('name','')} / {_cat_label or 'Uncategorised'}\")\r\n"
        b"                except Exception: pass\r\n"
        b"                flash(f\"Product added under '{_cat_label or 'Uncategorised'}'.\", \"success\")\r\n"
    )
    if n_cat_add in data:
        data = data.replace(n_cat_add, r_cat_add, 1)
        log.append("(2d) procurement_catalog add logged.")
    else:
        log.append("(2d) procurement_catalog add anchor NOT FOUND.")

    # ---- (2e) procurement_catalog edit ----
    n_cat_edit = (
        b"                flash(\"Product updated.\", \"success\")\r\n"
    )
    r_cat_edit = (
        b"                try: _log_marketplace_action(\"edit_product_catalog\", \"product\", int(eid or 0), f.get(\"name\",\"\"))\r\n"
        b"                except Exception: pass\r\n"
        b"                flash(\"Product updated.\", \"success\")\r\n"
    )
    if n_cat_edit in data:
        data = data.replace(n_cat_edit, r_cat_edit, 1)
        log.append("(2e) procurement_catalog edit logged.")
    else:
        log.append("(2e) procurement_catalog edit anchor NOT FOUND.")

    # ---- (2f) procurement_catalog delete ----
    n_cat_del = (
        b"            elif action == \"delete\":\r\n"
        b"                c.execute(\"UPDATE equipment_catalog SET is_active=0 WHERE id=?\",\r\n"
        b"                          (f.get(\"eid\", type=int),))\r\n"
        b"                flash(\"Item deactivated.\", \"info\")\r\n"
    )
    r_cat_del = (
        b"            elif action == \"delete\":\r\n"
        b"                _eid = f.get(\"eid\", type=int)\r\n"
        b"                c.execute(\"UPDATE equipment_catalog SET is_active=0 WHERE id=?\", (_eid,))\r\n"
        b"                try: _log_marketplace_action(\"delete_product_catalog\", \"product\", int(_eid or 0), \"soft-delete\")\r\n"
        b"                except Exception: pass\r\n"
        b"                flash(\"Item deactivated.\", \"info\")\r\n"
    )
    if n_cat_del in data:
        data = data.replace(n_cat_del, r_cat_del, 1)
        log.append("(2f) procurement_catalog delete logged.")
    else:
        log.append("(2f) procurement_catalog delete anchor NOT FOUND.")

    # ---- (2g) admin_marketplace_settings POST ----
    n_set = (
        b"        _admin_setting_set(\"products_per_page\", ppp)\r\n"
        b"        flash(f\"Saved: products per page = {ppp}.\", \"success\")\r\n"
    )
    r_set = (
        b"        _admin_setting_set(\"products_per_page\", ppp)\r\n"
        b"        try: _log_marketplace_action(\"settings_save\", \"admin_settings\", 0, f\"products_per_page={ppp}\")\r\n"
        b"        except Exception: pass\r\n"
        b"        flash(f\"Saved: products per page = {ppp}.\", \"success\")\r\n"
    )
    if n_set in data:
        data = data.replace(n_set, r_set, 1)
        log.append("(2g) admin_marketplace_settings POST logged.")
    else:
        log.append("(2g) admin_marketplace_settings anchor NOT FOUND.")

    # ---- (2h) admin_marketplace_reseed_ghana ----
    n_re = (
        b"    _ensure_marketplace_tables()\r\n"
        b"    _seed_ghana_suppliers_products()\r\n"
        b"    flash(\"Ghana suppliers + price-sheet products re-seeded (idempotent).\", \"success\")\r\n"
    )
    r_re = (
        b"    _ensure_marketplace_tables()\r\n"
        b"    _seed_ghana_suppliers_products()\r\n"
        b"    try: _log_marketplace_action(\"reseed_ghana\", \"system\", 0, \"manual re-fire of canonical Ghana seed\")\r\n"
        b"    except Exception: pass\r\n"
        b"    flash(\"Ghana suppliers + price-sheet products re-seeded (idempotent).\", \"success\")\r\n"
    )
    if n_re in data:
        data = data.replace(n_re, r_re, 1)
        log.append("(2h) reseed_ghana logged.")
    else:
        log.append("(2h) reseed_ghana anchor NOT FOUND.")

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
