#!/usr/bin/env python
"""Splice new_lv_panel_avr_seed.py into web_app.py, and wire the seed
function into the two existing cold-start hooks that already call
_seed_ghana_suppliers_products().

Insertion point: immediately before the `if __name__ == "__main__":` block
at the end of web_app.py (same pattern used by ghana_suppliers_seed).

Cold-start hooks patched (both call sites of _seed_ghana_suppliers_products):
  - the Postgres path in _ensure_marketplace_tables (~line 14986)
  - the SQLite fallthrough at ~line 15061

Idempotent: BEGIN marker in web_app.py -> skip splice; second marker check
before adding each cold-start call.
"""
from pathlib import Path

ROOT = Path(__file__).parent
target = ROOT / "web_app.py"
source = ROOT / "new_lv_panel_avr_seed.py"

data = target.read_bytes()
orig_len = len(data)

BEGIN = b"# === BEGIN: lv_panel_avr_seed splice ==="
END   = b"# === END: lv_panel_avr_seed splice ==="

# ---------------------------------------------------------------------
# Step 1: splice the seed module in before the __main__ guard.
# ---------------------------------------------------------------------
if BEGIN in data:
    print("[skip] lv_panel_avr_seed splice already present in web_app.py")
else:
    new_code = source.read_bytes()
    # Normalise to CRLF to match web_app.py line endings.
    new_code = new_code.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')

    MAIN = b'if __name__ == "__main__":'
    pos = data.rfind(MAIN)
    if pos < 0:
        print("[abort] `if __name__ == \"__main__\":` marker not found in web_app.py")
        raise SystemExit(1)

    data = data[:pos] + new_code + b'\r\n\r\n' + data[pos:]
    print(f"[ok] spliced {len(new_code)} bytes of lv_panel_avr_seed before __main__")

# ---------------------------------------------------------------------
# Step 2: wire _seed_lv_panel_avr_products() into both existing cold-start
# hooks alongside _seed_ghana_suppliers_products().
# ---------------------------------------------------------------------

# Callsite 1: Postgres-path block (session B/C hooks)
old_pg = (
    b"        # 2026-06-22: also seed canonical Ghana suppliers + products on Postgres.\r\n"
    b"        try: _seed_ghana_suppliers_products()\r\n"
    b"        except Exception: pass\r\n"
)
new_pg = (
    b"        # 2026-06-22: also seed canonical Ghana suppliers + products on Postgres.\r\n"
    b"        try: _seed_ghana_suppliers_products()\r\n"
    b"        except Exception: pass\r\n"
    b"        # 2026-07-01: seed LV Cables + Panel Boards + AVRs on Postgres.\r\n"
    b"        try: _seed_lv_panel_avr_products()\r\n"
    b"        except Exception: pass\r\n"
)
if b"_seed_lv_panel_avr_products()" in data.split(b"# === BEGIN: lv_panel_avr_seed splice ===")[0]:
    print("[skip] Postgres cold-start hook already wired")
else:
    if old_pg in data:
        data = data.replace(old_pg, new_pg, 1)
        print("[ok] wired _seed_lv_panel_avr_products() into Postgres cold-start hook")
    else:
        print("[warn] Postgres cold-start hook literal NOT FOUND -- wiring skipped (splice still applied)")

# Callsite 2: SQLite/fall-through block
old_sq = (
    b"    # 2026-06-22: seed canonical Ghana-local suppliers + their price-sheet products.\r\n"
    b"    try: _seed_ghana_suppliers_products()\r\n"
    b"    except Exception: pass\r\n"
)
new_sq = (
    b"    # 2026-06-22: seed canonical Ghana-local suppliers + their price-sheet products.\r\n"
    b"    try: _seed_ghana_suppliers_products()\r\n"
    b"    except Exception: pass\r\n"
    b"    # 2026-07-01: seed LV Cables + Panel Boards + AVRs.\r\n"
    b"    try: _seed_lv_panel_avr_products()\r\n"
    b"    except Exception: pass\r\n"
)
# Only wire the SQLite call if it isn't already present between the two seed markers.
pre_splice = data.split(b"# === BEGIN: lv_panel_avr_seed splice ===")[0]
if pre_splice.count(b"_seed_lv_panel_avr_products()") >= 2:
    print("[skip] SQLite cold-start hook already wired")
else:
    if old_sq in data:
        data = data.replace(old_sq, new_sq, 1)
        print("[ok] wired _seed_lv_panel_avr_products() into SQLite cold-start hook")
    else:
        print("[warn] SQLite cold-start hook literal NOT FOUND -- wiring skipped (splice still applied)")

if len(data) != orig_len:
    # Back up the previous byte-image before writing.
    backup = target.with_suffix(".py.bak-lvpanelavr-2026-07-01")
    if not backup.exists():
        backup.write_bytes(target.read_bytes())
        print(f"[backup] {backup.name}")
    target.write_bytes(data)
    print(f"[write] web_app.py updated ({orig_len} -> {len(data)} bytes, +{len(data) - orig_len})")
else:
    print("[noop] web_app.py unchanged")
