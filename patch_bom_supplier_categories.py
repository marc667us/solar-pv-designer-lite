#!/usr/bin/env python3
"""patch_bom_supplier_categories.py -- 2026-06-22 (session A).

Three byte-level patches against web_app.py, idempotent + CRLF-aware:

  (1) marketplace_bom_items gains description / specification / brand columns
      on BOTH SQLite and Postgres (ALTER TABLE IF NOT EXISTS / try-except).
  (2) supplier_register's INSERT INTO suppliers includes address (was being
      dropped on the floor even though the column has existed since 2026-06-19).
  (3) admin_marketplace_supplier_edit's UPDATE statement now writes address.
  (4) product_categories table gains default_unit / subcategories_csv /
      spec_fields_csv columns so the new admin Manage Categories page can
      persist the per-category taxonomy.

Patches are gated on marker text so re-running them is a no-op.
"""
from __future__ import annotations
import sys

PATH = "web_app.py"

def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    orig = data
    log = []

    # ---- 1. BOM items: extend _ensure_bom_tables() ALTER block -------------
    # Append three idempotent ALTERs next to the existing 'currency' ALTER.
    needle1 = (
        b"        try:\r\n"
        b"            with get_db() as _c:\r\n"
        b"                _c.execute(\"ALTER TABLE marketplace_boms ADD COLUMN currency TEXT DEFAULT 'GHS'\")\r\n"
        b"        except Exception:\r\n"
        b"            pass\r\n"
    )
    extra1 = (
        b"        # New 2026-06-22 (session A): description / specification / brand on BOM lines.\r\n"
        b"        # Idempotent for SQLite + Postgres (psycopg accepts ADD COLUMN IF NOT EXISTS).\r\n"
        b"        for _ddl in (\r\n"
        b"            \"ALTER TABLE marketplace_bom_items ADD COLUMN description TEXT DEFAULT ''\",\r\n"
        b"            \"ALTER TABLE marketplace_bom_items ADD COLUMN specification TEXT DEFAULT ''\",\r\n"
        b"            \"ALTER TABLE marketplace_bom_items ADD COLUMN brand TEXT DEFAULT ''\",\r\n"
        b"        ):\r\n"
        b"            try:\r\n"
        b"                with get_db() as _c:\r\n"
        b"                    _c.execute(_ddl)\r\n"
        b"            except Exception:\r\n"
        b"                pass\r\n"
    )
    if needle1 in data and extra1 not in data:
        data = data.replace(needle1, needle1 + extra1, 1)
        log.append("(1) BOM-item ALTERs spliced.")
    elif extra1 in data:
        log.append("(1) BOM-item ALTERs already present.")
    else:
        log.append("(1) BOM-item ALTER anchor NOT FOUND -- aborting before damaging file.")
        print("\n".join(log)); sys.exit(2)

    # ---- 2. supplier_register: include address in INSERT --------------------
    needle2 = (
        b"            c.execute(\r\n"
        b"                \"INSERT INTO suppliers (name,country,contact_name,phone,email,website,\"\r\n"
        b"                \"categories,lead_time_days,payment_terms,rating,user_id,is_verified,is_active) \"\r\n"
        b"                \"VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)\",\r\n"
        b"                (company, country, f.get(\"contact_name\", \"\"), f.get(\"phone\", \"\"),\r\n"
        b"                 email, f.get(\"website\", \"\"), f.get(\"categories\", \"\"),\r\n"
        b"                 _safe_int(f.get(\"lead_time_days\"), 30),\r\n"
        b"                 f.get(\"payment_terms\", \"TT 30 days\"), 5, uid, 0),\r\n"
        b"            )\r\n"
    )
    repl2 = (
        b"            c.execute(\r\n"
        b"                \"INSERT INTO suppliers (name,country,contact_name,phone,email,website,address,\"\r\n"
        b"                \"categories,lead_time_days,payment_terms,rating,user_id,is_verified,is_active) \"\r\n"
        b"                \"VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1)\",\r\n"
        b"                (company, country, f.get(\"contact_name\", \"\"), f.get(\"phone\", \"\"),\r\n"
        b"                 email, f.get(\"website\", \"\"), (f.get(\"address\") or \"\").strip(),\r\n"
        b"                 f.get(\"categories\", \"\"),\r\n"
        b"                 _safe_int(f.get(\"lead_time_days\"), 30),\r\n"
        b"                 f.get(\"payment_terms\", \"TT 30 days\"), 5, uid, 0),\r\n"
        b"            )\r\n"
    )
    if needle2 in data:
        data = data.replace(needle2, repl2, 1)
        log.append("(2) supplier_register INSERT now writes address.")
    elif b"INSERT INTO suppliers (name,country,contact_name,phone,email,website,address," in data:
        log.append("(2) supplier_register INSERT already writes address.")
    else:
        log.append("(2) supplier_register INSERT anchor NOT FOUND -- continuing (other patches).")

    # ---- 3. admin supplier edit: UPDATE includes address --------------------
    needle3 = (
        b"            \"UPDATE suppliers SET name=?, country=?, contact_name=?, phone=?, \"\r\n"
        b"            \"email=?, website=?, categories=?, lead_time_days=?, \"\r\n"
        b"            \"payment_terms=?, rating=?, is_verified=?, is_active=? \"\r\n"
        b"            \"WHERE id=?\",\r\n"
        b"            (\r\n"
        b"                (f.get(\"name\") or \"\").strip(),\r\n"
        b"                (f.get(\"country\") or \"\").strip(),\r\n"
        b"                (f.get(\"contact_name\") or \"\").strip(),\r\n"
        b"                (f.get(\"phone\") or \"\").strip(),\r\n"
        b"                (f.get(\"email\") or \"\").strip(),\r\n"
        b"                (f.get(\"website\") or \"\").strip(),\r\n"
        b"                (f.get(\"categories\") or \"\").strip(),\r\n"
        b"                _safe_int(f.get(\"lead_time_days\"), 30),\r\n"
        b"                (f.get(\"payment_terms\") or \"\").strip(),\r\n"
        b"                _safe_int(f.get(\"rating\"), 5),\r\n"
        b"                1 if f.get(\"is_verified\") else 0,\r\n"
        b"                1 if f.get(\"is_active\") else 0,\r\n"
        b"                sid,\r\n"
        b"            ),\r\n"
    )
    repl3 = (
        b"            \"UPDATE suppliers SET name=?, country=?, contact_name=?, phone=?, \"\r\n"
        b"            \"email=?, website=?, address=?, categories=?, lead_time_days=?, \"\r\n"
        b"            \"payment_terms=?, rating=?, is_verified=?, is_active=? \"\r\n"
        b"            \"WHERE id=?\",\r\n"
        b"            (\r\n"
        b"                (f.get(\"name\") or \"\").strip(),\r\n"
        b"                (f.get(\"country\") or \"\").strip(),\r\n"
        b"                (f.get(\"contact_name\") or \"\").strip(),\r\n"
        b"                (f.get(\"phone\") or \"\").strip(),\r\n"
        b"                (f.get(\"email\") or \"\").strip(),\r\n"
        b"                (f.get(\"website\") or \"\").strip(),\r\n"
        b"                (f.get(\"address\") or \"\").strip(),\r\n"
        b"                (f.get(\"categories\") or \"\").strip(),\r\n"
        b"                _safe_int(f.get(\"lead_time_days\"), 30),\r\n"
        b"                (f.get(\"payment_terms\") or \"\").strip(),\r\n"
        b"                _safe_int(f.get(\"rating\"), 5),\r\n"
        b"                1 if f.get(\"is_verified\") else 0,\r\n"
        b"                1 if f.get(\"is_active\") else 0,\r\n"
        b"                sid,\r\n"
        b"            ),\r\n"
    )
    if needle3 in data:
        data = data.replace(needle3, repl3, 1)
        log.append("(3) admin supplier edit UPDATE now writes address.")
    elif b"\"email=?, website=?, address=?, categories=?, lead_time_days=?, \"" in data:
        log.append("(3) admin supplier edit UPDATE already writes address.")
    else:
        log.append("(3) admin supplier edit UPDATE anchor NOT FOUND.")

    # ---- 4. _ensure_bom_tables extra: product_categories columns -----------
    # Splice 3 ALTERs onto product_categories so admin Manage Categories can
    # persist the default_unit / subcategories_csv / spec_fields_csv per row.
    needle4_anchor = extra1  # right after the BOM-item ALTERs we just inserted.
    extra4 = (
        b"        # 2026-06-22 (session A): per-category taxonomy storage for the\r\n"
        b"        # admin Manage Categories page. Idempotent on both engines.\r\n"
        b"        for _ddl in (\r\n"
        b"            \"ALTER TABLE product_categories ADD COLUMN default_unit TEXT DEFAULT 'No.'\",\r\n"
        b"            \"ALTER TABLE product_categories ADD COLUMN subcategories_csv TEXT DEFAULT ''\",\r\n"
        b"            \"ALTER TABLE product_categories ADD COLUMN spec_fields_csv TEXT DEFAULT ''\",\r\n"
        b"        ):\r\n"
        b"            try:\r\n"
        b"                with get_db() as _c:\r\n"
        b"                    _c.execute(_ddl)\r\n"
        b"            except Exception:\r\n"
        b"                pass\r\n"
    )
    if needle4_anchor in data and extra4 not in data:
        data = data.replace(needle4_anchor, needle4_anchor + extra4, 1)
        log.append("(4) product_categories ALTERs spliced.")
    elif extra4 in data:
        log.append("(4) product_categories ALTERs already present.")
    else:
        log.append("(4) product_categories ALTER anchor missing -- run (1) first.")

    if data == orig:
        log.append("\nNo changes -- everything already patched.")
        print("\n".join(log))
        return

    with open(PATH, "wb") as fh:
        fh.write(data)
    log.append(f"\nwrote {PATH} ({len(orig)} -> {len(data)} bytes)")
    print("\n".join(log))

if __name__ == "__main__":
    main()
