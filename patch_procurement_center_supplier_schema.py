"""Make procurement_center routes call _ensure_supplier_schema() so the
address column is added on first hit (the schema helper otherwise only
fires inside /supplier/* routes)."""
from __future__ import annotations
import sys

TARGET = "web_app.py"

PATCHES = [
    (
        b"def procurement_center():\r\n"
        b"    _ensure_marketplace_tables()\r\n"
        b"    _ensure_price_sheet_tables()\r\n",
        b"def procurement_center():\r\n"
        b"    _ensure_marketplace_tables()\r\n"
        b"    _ensure_supplier_schema()\r\n"
        b"    _ensure_price_sheet_tables()\r\n",
    ),
    (
        b"    csrf_protect()\r\n"
        b"    _ensure_marketplace_tables()\r\n"
        b"    _ensure_bom_tables()\r\n"
        b"    _ensure_price_sheet_tables()\r\n",
        b"    csrf_protect()\r\n"
        b"    _ensure_marketplace_tables()\r\n"
        b"    _ensure_supplier_schema()\r\n"
        b"    _ensure_bom_tables()\r\n"
        b"    _ensure_price_sheet_tables()\r\n",
    ),
]


def patch() -> int:
    src = open(TARGET, "rb").read()
    if b"def procurement_center():\r\n    _ensure_marketplace_tables()\r\n    _ensure_supplier_schema()" in src:
        print("[skip] already present")
        return 0
    applied = 0
    for old, new in PATCHES:
        if old in src:
            src = src.replace(old, new)
            applied += 1
    if applied == 0:
        print("[fail] no patch site matched")
        return 4
    open(TARGET, "wb").write(src)
    print(f"[ok] applied {applied}/2 patches")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
