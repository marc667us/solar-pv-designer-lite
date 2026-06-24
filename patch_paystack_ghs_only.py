"""Paystack merchant account is GHS-only (per Diag Paystack Merchant Config
run 28113596791 on 2026-06-24). NGN/KES/USD/ZAR/XOF all return 403 from the
API. Until the owner enables more currencies on the Paystack account, route
every user to GHS so the popup actually opens.

Implementation: add _PAYSTACK_SUPPORTED_CURRENCIES env-driven constant.
_paystack_currency_for_country() now picks the logical currency from the map
BUT clamps to the supported set, falling back to GHS as the safe default.

Owner action to expand: set env `PAYSTACK_SUPPORTED_CURRENCIES=GHS,NGN,KES`
on Render AFTER enabling NGN/KES on the merchant account.
"""
import sys

path = "web_app.py"
data = open(path, "rb").read()
orig_len = len(data)

old = (
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
)
new = (
    b'_COUNTRY_TO_PAYSTACK_CURRENCY = {\r\n'
    b'    # Logical map: which currency BEST fits each target country. Reality\r\n'
    b'    # is clamped to _PAYSTACK_SUPPORTED_CURRENCIES (the merchant account\r\n'
    b'    # only enables a subset). Per Diag Paystack Merchant Config run on\r\n'
    b'    # 2026-06-24, the account supports GHS only -- everything else gets\r\n'
    b'    # clamped down to GHS so the popup opens. Expand the env var as the\r\n'
    b'    # owner enables more currencies on Paystack.\r\n'
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
    b'# Currencies the merchant account actually accepts. Override at deploy\r\n'
    b'# time with env PAYSTACK_SUPPORTED_CURRENCIES=GHS,NGN,KES (comma-separated).\r\n'
    b'# When None or empty, defaults to GHS only (the conservative safe value\r\n'
    b'# proven by the 2026-06-24 diag).\r\n'
    b'def _paystack_supported_currencies():\r\n'
    b'    raw = (os.environ.get("PAYSTACK_SUPPORTED_CURRENCIES") or "GHS").strip()\r\n'
    b'    return {c.strip().upper() for c in raw.split(",") if c.strip()}\r\n'
    b'\r\n'
    b'def _paystack_currency_for_country(country):\r\n'
    b'    """Return the Paystack currency for the user\'s country, clamped to\r\n'
    b'    what the merchant account actually accepts."""\r\n'
    b'    logical = _COUNTRY_TO_PAYSTACK_CURRENCY.get((country or "").strip(), "USD")\r\n'
    b'    supported = _paystack_supported_currencies()\r\n'
    b'    if logical in supported:\r\n'
    b'        return logical\r\n'
    b'    # Fallback priority: GHS (primary market) > first supported alphabetic.\r\n'
    b'    if "GHS" in supported:\r\n'
    b'        return "GHS"\r\n'
    b'    return sorted(supported)[0] if supported else "GHS"\r\n'
)
if data.count(old) != 1:
    print(f"FAIL: anchor (got {data.count(old)})")
    sys.exit(1)
data = data.replace(old, new)

open(path, "wb").write(data)
print(f"OK: web_app.py {orig_len} -> {len(data)} bytes (+{len(data)-orig_len})")
