#!/usr/bin/env python3
"""patch_boq_services_inline_alter.py -- 2026-06-22.

Drop an inline `ALTER TABLE boq_projects ADD COLUMN services_csv` next to
the call to _boq_ensure_schema() in boq_projects_new() so the column lands
even when _ensure_bom_tables() hasn't run yet (BOQ project routes never call
that). Idempotent.
"""
from __future__ import annotations
import sys

PATH = "web_app.py"

def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    needle = (
        b"def boq_projects_new():\r\n"
        b"    uid = session[\"user_id\"]\r\n"
        b"    _boq_ensure_schema()\r\n"
    )
    repl = (
        b"def boq_projects_new():\r\n"
        b"    uid = session[\"user_id\"]\r\n"
        b"    _boq_ensure_schema()\r\n"
        b"    # 2026-06-22 services: make sure services_csv column exists on every engine.\r\n"
        b"    for _ddl in (\r\n"
        b"        \"ALTER TABLE boq_projects ADD COLUMN services_csv TEXT DEFAULT ''\",\r\n"
        b"    ):\r\n"
        b"        try:\r\n"
        b"            with get_db() as _c:\r\n"
        b"                _c.execute(_ddl)\r\n"
        b"        except Exception:\r\n"
        b"            pass\r\n"
    )
    if needle not in data:
        if b"# 2026-06-22 services: make sure services_csv column exists on every engine." in data:
            print("already patched.")
            return
        print("anchor NOT FOUND -- aborting."); sys.exit(2)
    data = data.replace(needle, repl, 1)
    with open(PATH, "wb") as fh:
        fh.write(data)
    print(f"wrote {PATH}")

if __name__ == "__main__":
    main()
