#!/usr/bin/env python3
"""
patch_money_filter.py

Add a `money` Jinja filter that formats a number as an INTEGER with
thousands separators (no decimals). Used in the BOQ + marketplace +
BOM + cost-estimate templates for price / rate / amount columns so the
owner sees `1,234,567` instead of `1,234,567.89`. Quantities, ratios,
and percentages keep their decimals via the existing `fmt` filter.

Edit point: immediately after the existing `fmti` template filter
(web_app.py:4131). Pattern A byte patch, CRLF preserved.
"""

from pathlib import Path
P = Path("web_app.py")
data = P.read_bytes()

OLD = (
    b'@app.template_filter("fmti")\r\n'
    b'def fmti(v):\r\n'
    b'    try:\r\n'
    b'        return f"{int(v):,}"\r\n'
    b'    except Exception:\r\n'
    b'        return str(v)\r\n'
)
NEW = (
    b'@app.template_filter("fmti")\r\n'
    b'def fmti(v):\r\n'
    b'    try:\r\n'
    b'        return f"{int(v):,}"\r\n'
    b'    except Exception:\r\n'
    b'        return str(v)\r\n'
    b'\r\n'
    b'\r\n'
    b'@app.template_filter("money")\r\n'
    b'def money(v):\r\n'
    b'    """Integer-formatted money: 1,234,567 (no decimals).\r\n'
    b'\r\n'
    b'    Used for all price / rate / amount columns in BOQ + marketplace +\r\n'
    b'    BOM + cost-estimate templates per owner directive 2026-06-23:\r\n'
    b'    "round off prices remove the decimals". Rounds half-away-from-zero\r\n'
    b'    (Python\'s round() uses banker\'s rounding, so add a tiny epsilon\r\n'
    b'    to force standard arithmetic rounding for half-cents).\r\n'
    b'    """\r\n'
    b'    try:\r\n'
    b'        x = float(v)\r\n'
    b'        # Standard rounding (away from zero on .5) -- the +eps trick.\r\n'
    b'        if x >= 0:\r\n'
    b'            n = int(x + 0.5)\r\n'
    b'        else:\r\n'
    b'            n = -int(-x + 0.5)\r\n'
    b'        return f"{n:,}"\r\n'
    b'    except Exception:\r\n'
    b'        return str(v)\r\n'
)

if NEW in data:
    print("[skip] money filter already patched")
else:
    if data.count(OLD) != 1:
        raise SystemExit(f"[fail] expected 1 OLD match, found {data.count(OLD)}")
    data = data.replace(OLD, NEW, 1)
    P.write_bytes(data)
    print(f"[ok] money filter added; web_app.py +{len(NEW)-len(OLD)} bytes -> {P.stat().st_size} bytes")
