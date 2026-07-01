#!/usr/bin/env python
"""Splice public news + newsfeed routes into web_app.py, add nav link in
base.html, and add 'Read all news' + newsfeed links to landing.html,
landing_page2.html, marketplace.html, and bill_check_landing.html.

Idempotent: skips whichever pieces are already present.
"""
from pathlib import Path

ROOT = Path(__file__).parent
WEB  = ROOT / "web_app.py"
SRC  = ROOT / "new_public_news_routes.py"

data = WEB.read_bytes()
orig = len(data)

BEGIN = b"# === BEGIN: public_news_routes splice ==="

# ---------------------------------------------------------------------
# 1. Splice the module before `if __name__ == "__main__":`
# ---------------------------------------------------------------------
if BEGIN in data:
    print("[skip] public_news_routes splice already present")
else:
    new_code = SRC.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    MAIN = b'if __name__ == "__main__":'
    pos = data.rfind(MAIN)
    if pos < 0:
        print("[abort] __main__ guard not found")
        raise SystemExit(1)
    data = data[:pos] + new_code + b"\r\n\r\n" + data[pos:]
    print(f"[ok] spliced {len(new_code)} bytes of public_news_routes")

if len(data) != orig:
    backup = WEB.with_suffix(".py.bak-news-2026-07-01")
    if not backup.exists():
        backup.write_bytes(WEB.read_bytes())
        print(f"[backup] {backup.name}")
    WEB.write_bytes(data)
    print(f"[write] web_app.py {orig} -> {len(data)} bytes")
print("[done] web_app.py splice")
