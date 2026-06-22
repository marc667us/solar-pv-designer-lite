#!/usr/bin/env python3
"""patch_library_expansion_splice.py -- 2026-06-22 session C.

(1) Splice new_library_expansion.py into web_app.py.
(2) Wire _seed_library_expansion() into both Postgres and SQLite branches
    of _ensure_marketplace_tables() so cold start lands the new rows.
"""
from __future__ import annotations
import sys

PATH = "web_app.py"
NEW  = "new_library_expansion.py"
BEGIN = b"# === BEGIN: library_expansion splice ==="
END   = b"# === END: library_expansion splice ==="

def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    new_block = open(NEW, "rb").read().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    orig_len = len(data)
    log = []

    if BEGIN in data and END in data:
        s = data.find(BEGIN); e = data.find(END, s) + len(END)
        data = data[:s] + new_block.rstrip(b"\r\n") + data[e:]
        log.append("(splice) library_expansion block replaced.")
    else:
        anchor = b"if __name__ == \"__main__\":"
        pos = data.rfind(anchor)
        if pos < 0:
            log.append("(splice) anchor not found.")
            print("\n".join(log)); sys.exit(2)
        data = data[:pos] + new_block + b"\r\n\r\n" + data[pos:]
        log.append("(splice) library_expansion block spliced before __main__.")

    # Hook into SQLite branch
    n_sql = (
        b"    # 2026-06-22 (session B): seed product_brands.\r\n"
        b"    try: _seed_marketplace_brands()\r\n"
        b"    except Exception: pass\r\n"
    )
    r_sql = (
        b"    # 2026-06-22 (session B): seed product_brands.\r\n"
        b"    try: _seed_marketplace_brands()\r\n"
        b"    except Exception: pass\r\n"
        b"    # 2026-06-22 (session C): library expansion seed.\r\n"
        b"    try: _seed_library_expansion()\r\n"
        b"    except Exception: pass\r\n"
    )
    if n_sql in data and b"# 2026-06-22 (session C): library expansion seed." not in data:
        data = data.replace(n_sql, r_sql, 1)
        log.append("(hook-sqlite) library expansion wired.")
    elif b"# 2026-06-22 (session C): library expansion seed." in data:
        log.append("(hook-sqlite) already wired.")
    else:
        log.append("(hook-sqlite) anchor NOT FOUND.")

    # Hook into Postgres branch
    n_pg = (
        b"        # 2026-06-22 (session B): seed product_brands on Postgres too.\r\n"
        b"        try: _seed_marketplace_brands()\r\n"
        b"        except Exception: pass\r\n"
        b"        return\r\n"
    )
    r_pg = (
        b"        # 2026-06-22 (session B): seed product_brands on Postgres too.\r\n"
        b"        try: _seed_marketplace_brands()\r\n"
        b"        except Exception: pass\r\n"
        b"        # 2026-06-22 (session C): library expansion on Postgres too.\r\n"
        b"        try: _seed_library_expansion()\r\n"
        b"        except Exception: pass\r\n"
        b"        return\r\n"
    )
    if n_pg in data and b"# 2026-06-22 (session C): library expansion on Postgres too." not in data:
        data = data.replace(n_pg, r_pg, 1)
        log.append("(hook-pg) library expansion wired on Postgres.")
    elif b"# 2026-06-22 (session C): library expansion on Postgres too." in data:
        log.append("(hook-pg) already wired.")
    else:
        log.append("(hook-pg) anchor NOT FOUND.")

    if len(data) == orig_len and data == open(PATH, "rb").read():
        log.append("\nNo changes.")
        print("\n".join(log))
        return
    with open(PATH, "wb") as fh:
        fh.write(data)
    log.append(f"\nwrote {PATH} ({orig_len} -> {len(data)} bytes)")
    print("\n".join(log))


if __name__ == "__main__":
    main()
