"""Task #5a: Working Paystack checkout end-to-end.

Fixes:
  1) Country -> Paystack currency map (GHS/NGN/KES/XOF/ZAR/USD). Adds
     XOF + ZMW to _CURRENCY_RATES_FROM_USD.
  2) upgrade() route computes paystack_currency + paystack_amount_subunit
     from user.country and passes them to the template.
  3) upgrade.html uses server-rendered currency + amount; adds user_id to
     PaystackPop metadata so the webhook can credit async payments.
  4) /paystack/verify route drops the bogus session.pop("paystack_plan")
     that JS never sets.
"""
import sys

path = "web_app.py"
data = open(path, "rb").read()
orig_len = len(data)

# === 1) Add XOF + ZMW to _CURRENCY_RATES_FROM_USD ===
old1 = (
    b'_CURRENCY_RATES_FROM_USD = {\r\n'
    b'    # Indicative rates -- overridable via FX_<CODE>_PER_USD env vars.\r\n'
    b'    # Customers see a disclaimer so they know to verify before quoting.\r\n'
    b'    "USD": 1.0,\r\n'
    b'    "EUR": _fx_rate("EUR", 0.93),\r\n'
    b'    "GBP": _fx_rate("GBP", 0.79),\r\n'
    b'    "GHS": _fx_rate("GHS", 14.5),\r\n'
    b'    "NGN": _fx_rate("NGN", 1550.0),\r\n'
    b'    "KES": _fx_rate("KES", 130.0),\r\n'
    b'    "ZAR": _fx_rate("ZAR", 18.5),\r\n'
    b'}\r\n'
)
# Read the existing block first (the comment text in source uses an em-dash that
# may be stored as a mojibake byte sequence -- match a smaller unique signature).
old1_short = b'    "USD": 1.0,\r\n    "EUR": _fx_rate("EUR", 0.93),\r\n    "GBP": _fx_rate("GBP", 0.79),\r\n    "GHS": _fx_rate("GHS", 14.5),\r\n    "NGN": _fx_rate("NGN", 1550.0),\r\n    "KES": _fx_rate("KES", 130.0),\r\n    "ZAR": _fx_rate("ZAR", 18.5),\r\n}'
new1_short = b'    "USD": 1.0,\r\n    "EUR": _fx_rate("EUR", 0.93),\r\n    "GBP": _fx_rate("GBP", 0.79),\r\n    "GHS": _fx_rate("GHS", 14.5),\r\n    "NGN": _fx_rate("NGN", 1550.0),\r\n    "KES": _fx_rate("KES", 130.0),\r\n    "ZAR": _fx_rate("ZAR", 18.5),\r\n    "XOF": _fx_rate("XOF", 610.0),\r\n    "ZMW": _fx_rate("ZMW", 24.0),\r\n}'
hits1 = data.count(old1_short)
if hits1 != 1:
    print(f"FAIL: expected 1 hit of currency table, got {hits1}")
    sys.exit(1)
data = data.replace(old1_short, new1_short)

# === 2) Add country->currency helpers above the /upgrade route ===
# Inject BEFORE the entire "# ___ Phase 4: ___" comment line.
# Anchor = "@app.route(\"/upgrade\")" on line 7085 (unique). Insert helpers
# before the @app.route decorator so they sit cleanly between the section
# heading comment and the route definition.
anchor = b'@app.route("/upgrade")\r\n@login_required\r\ndef upgrade():\r\n'
helpers = (
    b'# === Paystack country -> currency map (Task #5a) ===\r\n'
    b'_COUNTRY_TO_PAYSTACK_CURRENCY = {\r\n'
    b'    "Ghana": "GHS",\r\n'
    b'    "Nigeria": "NGN",\r\n'
    b'    "Kenya": "KES",\r\n'
    b'    "South Africa": "ZAR",\r\n'
    b'    "Mali": "XOF",\r\n'
    b'    "Burkina Faso": "XOF",\r\n'
    b'    "Cote d\'Ivoire": "XOF",\r\n'
    b'    "Ivory Coast": "XOF",\r\n'
    b'    "Senegal": "XOF",\r\n'
    b'    "Togo": "XOF",\r\n'
    b'    "Benin": "XOF",\r\n'
    b'    "Niger": "XOF",\r\n'
    b'    "Guinea-Bissau": "XOF",\r\n'
    b'    "Zambia": "USD",\r\n'
    b'}\r\n'
    b'_PAYSTACK_NO_SUBUNIT = {"XOF", "XAF"}\r\n'
    b'\r\n'
    b'def _paystack_currency_for_country(country):\r\n'
    b'    return _COUNTRY_TO_PAYSTACK_CURRENCY.get((country or "").strip(), "USD")\r\n'
    b'\r\n'
    b'def _paystack_subunit(amount_local, currency):\r\n'
    b'    if currency in _PAYSTACK_NO_SUBUNIT:\r\n'
    b'        return int(round(float(amount_local or 0)))\r\n'
    b'    return int(round(float(amount_local or 0) * 100))\r\n'
    b'\r\n'
    b'\r\n'
)
if data.count(anchor) != 1:
    print(f"FAIL: expected 1 hit of @app.route('/upgrade') anchor, got {data.count(anchor)}")
    sys.exit(1)
data = data.replace(anchor, helpers + anchor, 1)

# === 3) Patch upgrade() route to compute + pass paystack_currency + amount ===
old3 = (
    b'    return render_template("upgrade.html", user=user,\r\n'
    b'                           plan_prices=PLAN_PRICES,\r\n'
    b'                           current_plan=(user["plan"] or "free").lower(),\r\n'
    b'                           stripe_key=bool(STRIPE_SECRET),\r\n'
    b'                           paystack_key=bool(PAYSTACK_SECRET),\r\n'
    b'                           paystack_public_key=PAYSTACK_PUBLIC,\r\n'
    b'                           demo_mode=DEMO_MODE)\r\n'
)
new3 = (
    b'    _country = (user["country"] if user and "country" in (user.keys() if hasattr(user, "keys") else []) else "") or ""\r\n'
    b'    _ps_cur = _paystack_currency_for_country(_country)\r\n'
    b'    _ps_fx = _CURRENCY_RATES_FROM_USD.get(_ps_cur, 1.0)\r\n'
    b'    _ps_amounts = {\r\n'
    b'        _code: {\r\n'
    b'            "local": round(float(_p["usd"]) * float(_ps_fx), 2),\r\n'
    b'            "subunit": _paystack_subunit(float(_p["usd"]) * float(_ps_fx), _ps_cur),\r\n'
    b'        }\r\n'
    b'        for _code, _p in PLAN_PRICES.items()\r\n'
    b'    }\r\n'
    b'    return render_template("upgrade.html", user=user,\r\n'
    b'                           plan_prices=PLAN_PRICES,\r\n'
    b'                           current_plan=(user["plan"] or "free").lower(),\r\n'
    b'                           stripe_key=bool(STRIPE_SECRET),\r\n'
    b'                           paystack_key=bool(PAYSTACK_SECRET),\r\n'
    b'                           paystack_public_key=PAYSTACK_PUBLIC,\r\n'
    b'                           paystack_currency=_ps_cur,\r\n'
    b'                           paystack_amounts=_ps_amounts,\r\n'
    b'                           paystack_user_id=int(session.get("user_id", 0)),\r\n'
    b'                           demo_mode=DEMO_MODE)\r\n'
)
if data.count(old3) != 1:
    print(f"FAIL: expected 1 hit of upgrade() render block, got {data.count(old3)}")
    sys.exit(1)
data = data.replace(old3, new3)

# === 4) Clean up /paystack/verify: drop bogus session.pop and dead double-verify ===
old4 = (
    b'    _ps_ok, _ps_txn = _api.payment.verify(ref)\r\n'
    b'    if not _ps_ok:\r\n'
    b'        flash("Payment verification failed -- please contact billing@aiappinvent.com.", "danger")\r\n'
    b'        return redirect(url_for("upgrade"))\r\n'
    b'    plan = session.pop("paystack_plan", "")\r\n'
    b'    if not plan:\r\n'
    b'        plan = (_ps_txn.get("metadata") or {}).get("plan", "")\r\n'
)
# The em-dash above may not match -- match a shorter unique pattern around session.pop.
old4_short = b'    plan = session.pop("paystack_plan", "")\r\n    if not plan:\r\n        plan = (_ps_txn.get("metadata") or {}).get("plan", "")\r\n'
new4_short = b'    # Plan source: prefer form (set by PaystackPop callback) over metadata.\r\n    # session.pop("paystack_plan") used to be checked here but JS never set it.\r\n'
if data.count(old4_short) != 1:
    print(f"FAIL: expected 1 hit of paystack_verify session.pop, got {data.count(old4_short)}")
    sys.exit(1)
data = data.replace(old4_short, new4_short)

open(path, "wb").write(data)
print(f"OK: web_app.py {orig_len} -> {len(data)} bytes (+{len(data)-orig_len})")

# === 5) Add XOF + ZMW to procurement_center routes file ===
path2 = "new_marketplace_procurement_center_routes.py"
d2 = open(path2, "rb").read()
old5 = b'    "ZAR": _fx_rate("ZAR", 18.5),\n}'
new5 = b'    "ZAR": _fx_rate("ZAR", 18.5),\n    "XOF": _fx_rate("XOF", 610.0),\n    "ZMW": _fx_rate("ZMW", 24.0),\n}'
if d2.count(old5) != 1:
    # Try CRLF variant
    old5 = b'    "ZAR": _fx_rate("ZAR", 18.5),\r\n}'
    new5 = b'    "ZAR": _fx_rate("ZAR", 18.5),\r\n    "XOF": _fx_rate("XOF", 610.0),\r\n    "ZMW": _fx_rate("ZMW", 24.0),\r\n}'
    if d2.count(old5) != 1:
        print(f"FAIL: cannot find currency table in {path2}")
        sys.exit(1)
d2 = d2.replace(old5, new5)
open(path2, "wb").write(d2)
print(f"OK: {path2} updated (+XOF +ZMW)")
