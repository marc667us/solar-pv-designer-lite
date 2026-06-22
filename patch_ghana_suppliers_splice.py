#!/usr/bin/env python3
"""patch_ghana_suppliers_splice.py -- 2026-06-22.

Splice new_ghana_suppliers_seed.py into web_app.py and wire the seed
helper into _ensure_marketplace_tables() so it runs on every cold start.
Also exposes POST /admin/marketplace/reseed-ghana for manual re-fire.
"""
from __future__ import annotations
import sys

PATH = "web_app.py"
NEW  = "new_ghana_suppliers_seed.py"
BEGIN = b"# === BEGIN: ghana_suppliers_seed splice ==="
END   = b"# === END: ghana_suppliers_seed splice ==="

def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    new_block = open(NEW, "rb").read().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    orig_len = len(data)
    log = []

    if BEGIN in data and END in data:
        s = data.find(BEGIN)
        e = data.find(END, s) + len(END)
        data = data[:s] + new_block.rstrip(b"\r\n") + data[e:]
        log.append("(splice) ghana_suppliers_seed block replaced.")
    else:
        anchor = b"if __name__ == \"__main__\":"
        pos = data.rfind(anchor)
        if pos < 0:
            log.append("(splice) anchor `if __name__` not found -- aborting.")
            print("\n".join(log)); sys.exit(2)
        data = data[:pos] + new_block + b"\r\n\r\n" + data[pos:]
        log.append("(splice) ghana_suppliers_seed block spliced before __main__.")

    # Wire _seed_ghana_suppliers_products() into _ensure_marketplace_tables.
    # Anchor on the existing _backfill_marketplace_samples_for_empty_categories
    # call which is the LAST thing _ensure_marketplace_tables does today.
    hook_needle = (
        b"            _backfill_marketplace_samples_for_empty_categories(c)\r\n"
        b"    try: _ensure_product_link_columns()\r\n"
        b"    except Exception: pass\r\n"
    )
    hook_repl = (
        b"            _backfill_marketplace_samples_for_empty_categories(c)\r\n"
        b"    try: _ensure_product_link_columns()\r\n"
        b"    except Exception: pass\r\n"
        b"    # 2026-06-22: seed canonical Ghana-local suppliers + their price-sheet products.\r\n"
        b"    try: _seed_ghana_suppliers_products()\r\n"
        b"    except Exception: pass\r\n"
    )
    if hook_needle in data and b"_seed_ghana_suppliers_products()" not in data[:hook_needle and data.find(hook_needle) or 0:].split(b"_seed_ghana_suppliers_products()", 1)[0]:
        if b"# 2026-06-22: seed canonical Ghana-local suppliers" not in data:
            data = data.replace(hook_needle, hook_repl, 1)
            log.append("(hook) _seed_ghana_suppliers_products() wired into _ensure_marketplace_tables.")
        else:
            log.append("(hook) hook already present.")
    elif b"# 2026-06-22: seed canonical Ghana-local suppliers" in data:
        log.append("(hook) hook already present.")
    else:
        log.append("(hook) anchor NOT FOUND -- seed will still run via the route, but not on cold start.")

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
