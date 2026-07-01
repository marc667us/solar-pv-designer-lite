#!/usr/bin/env python
"""Splice /sitemap.xml route into web_app.py."""
from pathlib import Path

ROOT = Path(__file__).parent
WEB = ROOT / "web_app.py"
SRC = ROOT / "new_sitemap_route.py"

data = WEB.read_bytes()
orig = len(data)

BEGIN = b"# === BEGIN: sitemap_route splice ==="

if BEGIN in data:
    print("[skip] sitemap_route already spliced")
else:
    new_code = SRC.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    MAIN = b'if __name__ == "__main__":'
    pos = data.rfind(MAIN)
    data = data[:pos] + new_code + b"\r\n\r\n" + data[pos:]
    print(f"[ok] spliced {len(new_code)} bytes")

if len(data) != orig:
    backup = WEB.with_suffix(".py.bak-sitemap-2026-07-01")
    if not backup.exists():
        backup.write_bytes(WEB.read_bytes())
        print(f"[backup] {backup.name}")
    WEB.write_bytes(data)
    print(f"[write] web_app.py {orig} -> {len(data)} bytes")
