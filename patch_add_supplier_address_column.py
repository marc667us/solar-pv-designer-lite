"""Add address column to suppliers + extend the postgres schema bootstrap.

Slice 9 (Procurement Center / Basic Price Sheet) needs supplier.address
to populate the price sheet's Address column. The suppliers table never
had address before — adding it now via idempotent ALTER.

Patches both code paths:
  1. _ensure_supplier_schema (SQLite path) — adds the ALTER call
  2. _ensure_marketplace_schema_postgres (Postgres path) — adds ALTER TABLE
     IF NOT EXISTS for suppliers.address

Idempotent — skips if the column is already present in both call sites.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"

# Patch 1: SQLite path inside _ensure_supplier_schema. Add the address
# ALTER right after the is_verified ALTER.
OLD_SQLITE = (
    b"        if \"is_verified\" not in scols:\r\n"
    b"            c.execute(\"ALTER TABLE suppliers ADD COLUMN is_verified INTEGER DEFAULT 0\")\r\n"
)
NEW_SQLITE = (
    b"        if \"is_verified\" not in scols:\r\n"
    b"            c.execute(\"ALTER TABLE suppliers ADD COLUMN is_verified INTEGER DEFAULT 0\")\r\n"
    b"        if \"address\" not in scols:\r\n"
    b"            c.execute(\"ALTER TABLE suppliers ADD COLUMN address TEXT DEFAULT ''\")\r\n"
)

# Patch 2: Postgres path inside _ensure_marketplace_schema_postgres.
# Add an ALTER TABLE IF NOT EXISTS for the address column.
OLD_PG = (
    b"        \"ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS user_id INTEGER DEFAULT 0\",\r\n"
    b"        \"ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS is_verified INTEGER DEFAULT 0\",\r\n"
)
NEW_PG = (
    b"        \"ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS user_id INTEGER DEFAULT 0\",\r\n"
    b"        \"ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS is_verified INTEGER DEFAULT 0\",\r\n"
    b"        \"ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS address TEXT DEFAULT ''\",\r\n"
)


def patch() -> int:
    src = open(TARGET, "rb").read()
    if (b"ALTER TABLE suppliers ADD COLUMN address" in src
            and b"ADD COLUMN IF NOT EXISTS address" in src):
        print("[skip] address column already present in both paths")
        return 0
    applied = 0
    if OLD_SQLITE in src and NEW_SQLITE not in src:
        src = src.replace(OLD_SQLITE, NEW_SQLITE)
        applied += 1
        print("[ok] SQLite path patched")
    if OLD_PG in src and NEW_PG not in src:
        src = src.replace(OLD_PG, NEW_PG)
        applied += 1
        print("[ok] Postgres path patched")
    if applied == 0:
        print("[fail] no patch sites matched")
        return 4
    open(TARGET, "wb").write(src)
    print(f"[ok] applied {applied}/2 address-column patches")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
