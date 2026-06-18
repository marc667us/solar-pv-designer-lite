"""Apply Codex Slice 3 fixes to the already-injected web_app.py.

Codex high-severity finding: supplier approval flipped is_public_visible=1
on ALL active products, INCLUDING is_verified=0 ones. Combined with the
public /marketplace query lacking an is_verified=1 filter, unverified
products could leak public after supplier approval.

Two-pronged fix (belt + suspenders):
  1. Public query gains `AND is_verified=1` (defence in depth).
  2. Supplier-approval visibility flip restricted to `is_verified=1` rows.

Idempotent: skips quietly if already applied.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"


def patch() -> int:
    src = open(TARGET, "rb").read()
    applied = 0

    # 1. Public marketplace query — add `AND ec.is_verified=1`.
    old_a = b"               \"WHERE ec.is_active=1 AND ec.is_public_visible=1 \")\r\n"
    new_a = b"               \"WHERE ec.is_active=1 AND ec.is_public_visible=1 AND ec.is_verified=1 \")\r\n"
    if old_a in src:
        src = src.replace(old_a, new_a)
        applied += 1

    # 2. Public marketplace COUNT — add `AND is_verified=1`.
    old_b = (
        b"        total_products = c.execute(\r\n"
        b"            \"SELECT COUNT(*) FROM equipment_catalog \"\r\n"
        b"            \"WHERE is_active=1 AND is_public_visible=1\"\r\n"
        b"        ).fetchone()[0]\r\n"
    )
    new_b = (
        b"        total_products = c.execute(\r\n"
        b"            \"SELECT COUNT(*) FROM equipment_catalog \"\r\n"
        b"            \"WHERE is_active=1 AND is_public_visible=1 AND is_verified=1\"\r\n"
        b"        ).fetchone()[0]\r\n"
    )
    if old_b in src:
        src = src.replace(old_b, new_b)
        applied += 1

    # 3. Category product_count subquery.
    old_c = (
        b"            \"  (SELECT COUNT(*) FROM equipment_catalog ec \"\r\n"
        b"            \"   WHERE ec.category_id=pc.id AND ec.is_active=1 \"\r\n"
        b"            \"         AND ec.is_public_visible=1) AS product_count \"\r\n"
    )
    new_c = (
        b"            \"  (SELECT COUNT(*) FROM equipment_catalog ec \"\r\n"
        b"            \"   WHERE ec.category_id=pc.id AND ec.is_active=1 \"\r\n"
        b"            \"         AND ec.is_public_visible=1 AND ec.is_verified=1) AS product_count \"\r\n"
    )
    if old_c in src:
        src = src.replace(old_c, new_c)
        applied += 1

    # 4. Single supplier approval — only flip verified products.
    old_d = (
        b"        # Also mark this supplier's already-pending products as publicly visible\r\n"
        b"        # (each individual product still needs its own is_verified=1 flip below).\r\n"
        b"        c.execute(\r\n"
        b"            \"UPDATE equipment_catalog SET is_public_visible=1 \"\r\n"
        b"            \"WHERE supplier_id=? AND is_active=1\", (sid,),\r\n"
        b"        )\r\n"
    )
    new_d = (
        b"        # Surface ONLY the supplier's already-verified products. Unverified\r\n"
        b"        # products must continue to wait for product-level approval to avoid\r\n"
        b"        # leaking unreviewed listings on supplier approval (Codex finding).\r\n"
        b"        c.execute(\r\n"
        b"            \"UPDATE equipment_catalog SET is_public_visible=1 \"\r\n"
        b"            \"WHERE supplier_id=? AND is_active=1 AND is_verified=1\", (sid,),\r\n"
        b"        )\r\n"
    )
    if old_d in src:
        src = src.replace(old_d, new_d)
        applied += 1

    # 5. Bulk supplier approval — only flip verified products.
    old_e = (
        b"            c.execute(\r\n"
        b"                f\"UPDATE equipment_catalog SET is_public_visible=1 \"\r\n"
        b"                f\"WHERE supplier_id IN ({placeholders}) AND is_active=1\",\r\n"
        b"                sids,\r\n"
        b"            )\r\n"
    )
    new_e = (
        b"            # Only flip visibility for already-verified products of these\r\n"
        b"            # suppliers \xe2\x80\x94 unverified products must continue to wait for their\r\n"
        b"            # own approval (Codex finding).\r\n"
        b"            c.execute(\r\n"
        b"                f\"UPDATE equipment_catalog SET is_public_visible=1 \"\r\n"
        b"                f\"WHERE supplier_id IN ({placeholders}) AND is_active=1 AND is_verified=1\",\r\n"
        b"                sids,\r\n"
        b"            )\r\n"
    )
    if old_e in src:
        src = src.replace(old_e, new_e)
        applied += 1

    if applied == 0:
        print("[skip] no fix sites matched — likely already applied")
        return 0
    open(TARGET, "wb").write(src)
    print(f"[ok] applied {applied}/5 Codex Slice 3 fixes")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
