#!/usr/bin/env python3
"""Splice the Recheck Prices routes from new_recheck_prices_routes.py
into web_app.py via the register-by-closure pattern. Idempotent: skips if
the marker line is already present.
"""
from pathlib import Path

P = Path("web_app.py")
data = P.read_bytes()

MARKER = b"# RECHECK_PRICES_ROUTES_v1 -- do not remove"

if MARKER in data:
    print("[skip] Recheck Prices routes already wired")
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
    b"    from new_recheck_prices_routes import register_recheck_prices_routes\r\n"
    b"    register_recheck_prices_routes(\r\n"
    b"        app, login_required, session, request, redirect, url_for, flash,\r\n"
    b"        render_template, current_user, get_db, _bom_owned_or_404,\r\n"
    b"        _bom_items_with_prices, _CURRENCY_RATES_FROM_USD, csrf_protect,\r\n"
    b"    )\r\n"
    b"except Exception as _e_rcp:\r\n"
    b"    try:\r\n"
    b"        app.logger.warning('recheck-prices routes failed to register: %s', _e_rcp)\r\n"
    b"    except Exception:\r\n"
    b"        pass\r\n"
    b"\r\n"
)

data2 = data[:pos] + insert + data[pos:]
P.write_bytes(data2)
print(f"[ok] inserted {len(insert)} bytes before module main guard")
