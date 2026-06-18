"""
Switch the procurement-center default currency from USD -> GHS in the bytes
spliced into web_app.py. Idempotent: each rfind only fires if the old pattern
is still present.
"""
import sys

PATH = "web_app.py"

REPLACEMENTS = [
    # Postgres schema default
    (b"                currency      VARCHAR(3) DEFAULT 'USD',",
     b"                currency      VARCHAR(3) DEFAULT 'GHS',"),
    # SQLite schema default
    (b"                currency      TEXT DEFAULT 'USD',",
     b"                currency      TEXT DEFAULT 'GHS',"),
    # GET /procurement-center query-arg fallback + invalid-value fallback
    (b'    currency = (request.args.get("currency") or "USD").strip().upper()\r\n'
     b'    if currency not in _CURRENCY_RATES_FROM_USD:\r\n'
     b'        currency = "USD"',
     b'    currency = (request.args.get("currency") or "GHS").strip().upper()\r\n'
     b'    if currency not in _CURRENCY_RATES_FROM_USD:\r\n'
     b'        currency = "GHS"'),
    # POST /procurement-center/add form fallback + invalid-value fallback
    (b'    currency = (request.form.get("currency") or "USD").strip().upper()\r\n'
     b'    if currency not in _CURRENCY_RATES_FROM_USD:\r\n'
     b'        currency = "USD"',
     b'    currency = (request.form.get("currency") or "GHS").strip().upper()\r\n'
     b'    if currency not in _CURRENCY_RATES_FROM_USD:\r\n'
     b'        currency = "GHS"'),
]

data = open(PATH, "rb").read()
orig = data
hits = []
for old, new in REPLACEMENTS:
    if old in data:
        data = data.replace(old, new)
        hits.append(("hit ", old.split(b"\r\n")[0][:80]))
    elif new in data:
        hits.append(("skip", b"already GHS: " + new.split(b"\r\n")[0][:80]))
    else:
        hits.append(("MISS", old.split(b"\r\n")[0][:80]))

if data != orig:
    open(PATH, "wb").write(data)
    print(f"[patch] web_app.py updated ({len(data) - len(orig):+d} bytes)")
else:
    print("[patch] no change (already applied or all misses)")

for tag, line in hits:
    print(f"  [{tag}] {line.decode('utf-8', errors='replace')}")

sys.exit(0 if not any(t == "MISS" for t, _ in hits) else 1)
