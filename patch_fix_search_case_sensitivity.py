"""Apply case-insensitive search fix to the already-injected web_app.py.

Live deploy d409fca: /marketplace?q=transformer returned 0 results even
though there are 2 transformer products. Root cause: Postgres LIKE is
case-sensitive; SQLite LIKE is case-insensitive. The query had
`ec.name LIKE ?` which behaved differently on the two backends.

Fix: wrap both sides in LOWER() so behaviour is identical:
  LOWER(ec.name) LIKE LOWER(?)

Same fix applies to /admin/marketplace/pending search.

Idempotent — skips if LOWER( is already present.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"

PATCHES = [
    # Public /marketplace search
    (
        b"        if q:\r\n"
        b"            sql += (\"AND (ec.name LIKE ? OR ec.brand LIKE ? OR ec.model LIKE ? \"\r\n"
        b"                    \"     OR ec.spec LIKE ?) \")\r\n"
        b"            like = f\"%{q}%\"\r\n"
        b"            args.extend([like, like, like, like])\r\n",
        b"        if q:\r\n"
        b"            # LOWER() on both sides so search is case-insensitive on Postgres\r\n"
        b"            # (LIKE is case-sensitive there; SQLite is case-insensitive for\r\n"
        b"            # ASCII, so this keeps both backends behaving the same).\r\n"
        b"            sql += (\"AND (LOWER(ec.name) LIKE ? OR LOWER(ec.brand) LIKE ? \"\r\n"
        b"                    \"     OR LOWER(ec.model) LIKE ? OR LOWER(ec.spec) LIKE ?) \")\r\n"
        b"            like = f\"%{q.lower()}%\"\r\n"
        b"            args.extend([like, like, like, like])\r\n",
    ),
    # Admin /admin/marketplace/pending search
    (
        b"            sql += (\"AND (ec.name LIKE ? OR ec.brand LIKE ? OR ec.model LIKE ? \"\r\n"
        b"                    \"     OR s.name LIKE ?) \")\r\n"
        b"            like = f\"%{q}%\"\r\n"
        b"            args.extend([like, like, like, like])\r\n",
        b"            # LOWER() on both sides for cross-dialect case-insensitive search\r\n"
        b"            # (matches the same pattern used on the public /marketplace).\r\n"
        b"            sql += (\"AND (LOWER(ec.name) LIKE ? OR LOWER(ec.brand) LIKE ? \"\r\n"
        b"                    \"     OR LOWER(ec.model) LIKE ? OR LOWER(s.name) LIKE ?) \")\r\n"
        b"            like = f\"%{q.lower()}%\"\r\n"
        b"            args.extend([like, like, like, like])\r\n",
    ),
]


def patch() -> int:
    src = open(TARGET, "rb").read()
    if b"LOWER(ec.name) LIKE ?" in src:
        print("[skip] LOWER() already present")
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
    print(f"[ok] applied {applied}/{len(PATCHES)} case-insensitive search fixes")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
