#!/usr/bin/env python3
"""patch_ghana_seed_postgres_hook.py -- 2026-06-22.

_ensure_marketplace_tables() returns early on Postgres after calling
_ensure_marketplace_schema_postgres(). The earlier patch wired
_seed_ghana_suppliers_products() into the SQLite branch only, so live
(Render Postgres) didn't get the Ghana suppliers seeded on cold start.

Fix: call _seed_ghana_suppliers_products() right after
_ensure_marketplace_schema_postgres() in the early-return branch too.
"""
from __future__ import annotations
import sys

PATH = "web_app.py"


def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    orig = data

    needle = (
        b"def _ensure_marketplace_tables():\r\n"
        b"    if bool(os.environ.get(\"DATABASE_URL\")):\r\n"
        b"        _ensure_marketplace_schema_postgres()\r\n"
        b"        return\r\n"
    )
    repl = (
        b"def _ensure_marketplace_tables():\r\n"
        b"    if bool(os.environ.get(\"DATABASE_URL\")):\r\n"
        b"        _ensure_marketplace_schema_postgres()\r\n"
        b"        # 2026-06-22: also seed canonical Ghana suppliers + products on Postgres.\r\n"
        b"        try: _seed_ghana_suppliers_products()\r\n"
        b"        except Exception: pass\r\n"
        b"        return\r\n"
    )
    if needle in data:
        data = data.replace(needle, repl, 1)
        print("(hook) Ghana seed wired into Postgres branch of _ensure_marketplace_tables.")
    elif b"# 2026-06-22: also seed canonical Ghana suppliers + products on Postgres." in data:
        print("(hook) Ghana seed Postgres hook already present.")
    else:
        print("(hook) anchor NOT FOUND -- aborting.")
        sys.exit(2)
    if data == orig:
        print("No changes.")
        return
    with open(PATH, "wb") as fh:
        fh.write(data)
    print(f"wrote {PATH}")


if __name__ == "__main__":
    main()
