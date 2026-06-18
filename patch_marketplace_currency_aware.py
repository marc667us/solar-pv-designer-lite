"""
Make /marketplace currency-aware (default GHS) + make FX rates env-configurable.

Three byte-level edits inside web_app.py:
  1. Replace the hard-coded _CURRENCY_RATES_FROM_USD dict with an env-driven
     version + _fx_rate helper.
  2. Make _CURRENCY_RATES_AS_OF env-overrideable.
  3. Extend marketplace_public()'s render_template call with currency,
     currencies, rates_as_of + a per-product price_in_currency list.

Idempotent: each rfind only fires if the old pattern is still present.
"""
import sys

PATH = "web_app.py"
data = open(PATH, "rb").read()
orig = data

# ── 1. FX dict + helper ───────────────────────────────────────────────────────
OLD_FX = (
    b"_CURRENCY_RATES_FROM_USD = {\r\n"
    b"    # Indicative rates \xe2\x80\x94 refreshed periodically. Customers see a disclaimer\r\n"
    b"    # so they know to verify before quoting.\r\n"
    b"    \"USD\": 1.0,\r\n"
    b"    \"EUR\": 0.93,\r\n"
    b"    \"GBP\": 0.79,\r\n"
    b"    \"GHS\": 14.5,\r\n"
    b"    \"NGN\": 1550.0,\r\n"
    b"    \"KES\": 130.0,\r\n"
    b"    \"ZAR\": 18.5,\r\n"
    b"}\r\n"
    b"_CURRENCY_RATES_AS_OF = \"2026-06-18\""
)
NEW_FX = (
    b"def _fx_rate(code, default):\r\n"
    b"    \"\"\"Read an indicative FX rate from env FX_<CODE>_PER_USD; fall back\r\n"
    b"    to the bundled default. Lets ops override the rate without a code push.\"\"\"\r\n"
    b"    try:\r\n"
    b"        return float(os.environ.get(f\"FX_{code}_PER_USD\", default))\r\n"
    b"    except (TypeError, ValueError):\r\n"
    b"        return float(default)\r\n"
    b"\r\n"
    b"\r\n"
    b"_CURRENCY_RATES_FROM_USD = {\r\n"
    b"    # Indicative rates \xe2\x80\x94 overridable via FX_<CODE>_PER_USD env vars.\r\n"
    b"    # Customers see a disclaimer so they know to verify before quoting.\r\n"
    b"    \"USD\": 1.0,\r\n"
    b"    \"EUR\": _fx_rate(\"EUR\", 0.93),\r\n"
    b"    \"GBP\": _fx_rate(\"GBP\", 0.79),\r\n"
    b"    \"GHS\": _fx_rate(\"GHS\", 14.5),\r\n"
    b"    \"NGN\": _fx_rate(\"NGN\", 1550.0),\r\n"
    b"    \"KES\": _fx_rate(\"KES\", 130.0),\r\n"
    b"    \"ZAR\": _fx_rate(\"ZAR\", 18.5),\r\n"
    b"}\r\n"
    b"_CURRENCY_RATES_AS_OF = os.environ.get(\"FX_RATES_AS_OF\", \"2026-06-18\")"
)
if OLD_FX in data:
    data = data.replace(OLD_FX, NEW_FX, 1)
    print("[1/2] FX dict + _fx_rate helper installed")
elif b"def _fx_rate(" in data:
    print("[1/2] FX dict already env-aware (skip)")
else:
    print("[1/2] MISS — could not find FX dict to replace")
    sys.exit(1)

# ── 2. marketplace_public() — make currency-aware ─────────────────────────────
OLD_MP = (
    b"    return render_template(\r\n"
    b"        \"marketplace.html\",\r\n"
    b"        user=current_user(),\r\n"
    b"        categories=categories,\r\n"
    b"        products=products,\r\n"
    b"        total_products=total_products,\r\n"
    b"        total_suppliers=total_suppliers,\r\n"
    b"        total_countries=countries,\r\n"
    b"        selected_category=selected_category,\r\n"
    b"        q=q,\r\n"
    b"    )"
)
NEW_MP = (
    b"    # Currency selection \xe2\x80\x94 same indicative FX rates as the procurement center.\r\n"
    b"    currency = (request.args.get(\"currency\") or \"GHS\").strip().upper()\r\n"
    b"    if currency not in _CURRENCY_RATES_FROM_USD:\r\n"
    b"        currency = \"GHS\"\r\n"
    b"    rate = _CURRENCY_RATES_FROM_USD.get(currency, 1.0)\r\n"
    b"    products_view = []\r\n"
    b"    for p in products:\r\n"
    b"        d = dict(p)\r\n"
    b"        d[\"price_in_currency\"] = float(d.get(\"price_usd\") or 0) * float(rate)\r\n"
    b"        products_view.append(d)\r\n"
    b"\r\n"
    b"    return render_template(\r\n"
    b"        \"marketplace.html\",\r\n"
    b"        user=current_user(),\r\n"
    b"        categories=categories,\r\n"
    b"        products=products_view,\r\n"
    b"        total_products=total_products,\r\n"
    b"        total_suppliers=total_suppliers,\r\n"
    b"        total_countries=countries,\r\n"
    b"        selected_category=selected_category,\r\n"
    b"        q=q,\r\n"
    b"        currency=currency,\r\n"
    b"        currencies=list(_CURRENCY_RATES_FROM_USD.keys()),\r\n"
    b"        rates_as_of=_CURRENCY_RATES_AS_OF,\r\n"
    b"    )"
)
if OLD_MP in data:
    data = data.replace(OLD_MP, NEW_MP, 1)
    print("[2/2] marketplace_public() now currency-aware")
elif b"products_view = []" in data and b"d[\"price_in_currency\"]" in data:
    print("[2/2] marketplace_public() already currency-aware (skip)")
else:
    print("[2/2] MISS — could not find marketplace_public render_template to extend")
    sys.exit(1)

if data != orig:
    open(PATH, "wb").write(data)
    print(f"[done] web_app.py {len(data)-len(orig):+d} bytes")
else:
    print("[done] no change")
