#!/usr/bin/env python3
"""Splice the catalogue pricing routes from new_catalogue_pricing_routes.py
into web_app.py via the register-by-closure pattern. Idempotent.
"""
from pathlib import Path

P = Path("web_app.py")
data = P.read_bytes()

MARKER = b"# CATALOGUE_PRICING_ROUTES_v1 -- do not remove"

if MARKER in data:
    print("[skip] catalogue pricing routes already wired")
    raise SystemExit(0)

TARGET = b'if __name__ == "__main__":'
pos = data.rfind(TARGET)
if pos < 0:
    raise SystemExit("[fail] could not find module main guard")

insert = (
    b"\r\n"
    + MARKER
    + b"\r\n"
    b"try:\r\n"
    b"    from new_catalogue_pricing_routes import register_catalogue_pricing_routes\r\n"
    b"    register_catalogue_pricing_routes(\r\n"
    b"        app, admin_required, session, request, redirect, url_for, flash,\r\n"
    b"        render_template, current_user, get_db, csrf_protect,\r\n"
    b"        _CURRENCY_RATES_FROM_USD,\r\n"
    b"    )\r\n"
    b"except Exception as _e_cpr:\r\n"
    b"    try:\r\n"
    b"        app.logger.warning('catalogue-pricing routes failed to register: %s', _e_cpr)\r\n"
    b"    except Exception:\r\n"
    b"        pass\r\n"
    b"\r\n"
)

data2 = data[:pos] + insert + data[pos:]
P.write_bytes(data2)
print(f"[ok] inserted {len(insert)} bytes before module main guard")
