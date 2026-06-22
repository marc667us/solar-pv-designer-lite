#!/usr/bin/env python3
"""patch_online_users_splice.py -- 2026-06-22.

Splice new_online_users.py into web_app.py and add the users.last_seen
ALTER into the schema-bootstrap path so the column exists on cold start.
"""
from __future__ import annotations
import sys

PATH = "web_app.py"
NEW  = "new_online_users.py"
BEGIN = b"# === BEGIN: online_users splice ==="
END   = b"# === END: online_users splice ==="

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
        log.append("(splice) online_users block replaced.")
    else:
        anchor = b"if __name__ == \"__main__\":"
        pos = data.rfind(anchor)
        if pos < 0:
            log.append("(splice) anchor `if __name__` not found -- aborting.")
            print("\n".join(log)); sys.exit(2)
        data = data[:pos] + new_block + b"\r\n\r\n" + data[pos:]
        log.append("(splice) online_users block spliced before __main__.")

    # Add ALTER into _ensure_supplier_schema (it always runs on first marketplace hit)
    needle_alter = (
        b"        if \"address\" not in scols:\r\n"
        b"            c.execute(\"ALTER TABLE suppliers ADD COLUMN address TEXT DEFAULT ''\")\r\n"
    )
    repl_alter = (
        b"        if \"address\" not in scols:\r\n"
        b"            c.execute(\"ALTER TABLE suppliers ADD COLUMN address TEXT DEFAULT ''\")\r\n"
        b"        # 2026-06-22 (session B): users.last_seen for online-tracking widget.\r\n"
        b"        try: _ensure_users_last_seen()\r\n"
        b"        except Exception: pass\r\n"
    )
    if needle_alter in data and b"# 2026-06-22 (session B): users.last_seen for online-tracking widget." not in data:
        data = data.replace(needle_alter, repl_alter, 1)
        log.append("(alter) users.last_seen wired into _ensure_supplier_schema.")
    elif b"# 2026-06-22 (session B): users.last_seen for online-tracking widget." in data:
        log.append("(alter) already wired.")
    else:
        log.append("(alter) anchor NOT FOUND.")

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
