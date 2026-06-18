"""One-shot fix — converts `c.rowcount` to a cursor-based read inside the
injected admin_marketplace_bulk() function. SQLite3 Connection has no
rowcount; only Cursor does. The four call sites in the bulk handler are
patched by exact-string match (idempotent — re-running is safe).
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"

PATCHES = [
    (
        b"            c.execute(\r\n"
        b"                f\"UPDATE equipment_catalog SET is_verified=1, is_public_visible=1 \"\r\n"
        b"                f\"WHERE id IN ({placeholders}) \"\r\n"
        b"                f\"  AND supplier_id IN (SELECT id FROM suppliers WHERE is_verified=1)\",\r\n"
        b"                pids,\r\n"
        b"            )\r\n"
        b"            n = c.rowcount or 0\r\n",
        b"            cur = c.execute(\r\n"
        b"                f\"UPDATE equipment_catalog SET is_verified=1, is_public_visible=1 \"\r\n"
        b"                f\"WHERE id IN ({placeholders}) \"\r\n"
        b"                f\"  AND supplier_id IN (SELECT id FROM suppliers WHERE is_verified=1)\",\r\n"
        b"                pids,\r\n"
        b"            )\r\n"
        b"            n = cur.rowcount or 0\r\n",
    ),
    (
        b"            c.execute(\r\n"
        b"                f\"UPDATE equipment_catalog SET is_active=0, is_public_visible=0 \"\r\n"
        b"                f\"WHERE id IN ({placeholders})\",\r\n"
        b"                pids,\r\n"
        b"            )\r\n"
        b"            n = c.rowcount or 0\r\n",
        b"            cur = c.execute(\r\n"
        b"                f\"UPDATE equipment_catalog SET is_active=0, is_public_visible=0 \"\r\n"
        b"                f\"WHERE id IN ({placeholders})\",\r\n"
        b"                pids,\r\n"
        b"            )\r\n"
        b"            n = cur.rowcount or 0\r\n",
    ),
    (
        b"            c.execute(\r\n"
        b"                f\"UPDATE suppliers SET is_verified=1 WHERE id IN ({placeholders})\",\r\n"
        b"                sids,\r\n"
        b"            )\r\n"
        b"            n = c.rowcount or 0\r\n",
        b"            cur = c.execute(\r\n"
        b"                f\"UPDATE suppliers SET is_verified=1 WHERE id IN ({placeholders})\",\r\n"
        b"                sids,\r\n"
        b"            )\r\n"
        b"            n = cur.rowcount or 0\r\n",
    ),
    (
        b"            c.execute(\r\n"
        b"                f\"UPDATE suppliers SET is_active=0 WHERE id IN ({placeholders})\",\r\n"
        b"                sids,\r\n"
        b"            )\r\n"
        b"            n = c.rowcount or 0\r\n",
        b"            cur = c.execute(\r\n"
        b"                f\"UPDATE suppliers SET is_active=0 WHERE id IN ({placeholders})\",\r\n"
        b"                sids,\r\n"
        b"            )\r\n"
        b"            n = cur.rowcount or 0\r\n",
    ),
]


def patch() -> int:
    src = open(TARGET, "rb").read()
    if b"n = c.rowcount or 0" not in src:
        print("[skip] no `c.rowcount` left in target — already patched")
        return 0
    applied = 0
    for old, new in PATCHES:
        if old in src:
            src = src.replace(old, new)
            applied += 1
    if applied == 0:
        print("[fail] no patch site matched — line endings may have drifted")
        return 4
    open(TARGET, "wb").write(src)
    print(f"[ok] applied {applied}/{len(PATCHES)} rowcount fixes")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
