"""
Phase A patch — update GHANA_PURC_TARIFFS dict in web_app.py to PURC Q2 2026
exact values (effective 2026-04-01). Run from project root:

    python _patch_bill_check_phase_a.py

Source: PURC "2026 Second Quarter Tariff Review Decision" (13-03-2026).
PDF: https://www.purc.com.gh/attachment/288818-20260313090334.pdf
GHp = Ghana pesewas; 100 GHp = GHS 1.
"""
from pathlib import Path

P = Path("web_app.py")
data = P.read_bytes()

# ─── Block A: replace whole GHANA_PURC_TARIFFS dict ──────────────────────────
# The old dict starts at the header comment and ends at the closing brace
# before "# ─── Demand Factors by load category". Replace by exact byte slice.

ANCHOR = b"GHANA_PURC_TARIFFS = {\r\n"
anchor_pos = data.find(ANCHOR)
if anchor_pos < 0:
    raise SystemExit("FAIL: could not locate GHANA_PURC_TARIFFS anchor")

# Walk backwards from anchor to the start of the header-comment block
# (delimited above by a blank line "\r\n\r\n").
header_break = data.rfind(b"\r\n\r\n", 0, anchor_pos)
if header_break < 0:
    raise SystemExit("FAIL: could not locate header break above dict")
start = header_break + len(b"\r\n\r\n")

# Find the closing brace of the dict (next line that is exactly "}\r\n" after start)
brace_close = data.find(b"\r\n}\r\n", start)
if brace_close < 0:
    raise SystemExit("FAIL: could not locate dict close")
end = brace_close + len(b"\r\n}\r\n")

# Verify our slice ends where we expect (the next non-blank line should be
# the DEMAND_FACTORS header comment).
tail = data[end:end + 200]
if b"Demand Factors" not in tail:
    raise SystemExit(f"FAIL: dict slice end mismatch. Tail begins:\n{tail!r}")

NEW = (
    "# ─── Ghana PURC Tariff Schedule (Q2 2026, effective April 1 2026) ─────\r\n"
    "# Source: PURC \"2026 Second Quarter Tariff Review Decision\", 13-03-2026.\r\n"
    "# PDF: https://www.purc.com.gh/attachment/288818-20260313090334.pdf\r\n"
    "# Rates in GHS/kWh; service charge in GHS/month. Lifeline is a *customer\r\n"
    "# class*, not a band: if monthly use ≤ 30 kWh the lifeline rate applies\r\n"
    "# to ALL units; if > 30 kWh the customer moves to the standard 0-300 and\r\n"
    "# 301+ bands and the lifeline rate no longer applies to any unit.\r\n"
    "GHANA_PURC_TARIFFS = {\r\n"
    "    \"Residential Lifeline (≤ 30 kWh/month)\": {\r\n"
    "        \"rate_ghc\":   0.8690,\r\n"
    "        \"fixed_ghc\":  2.13,\r\n"
    "        \"description\": \"Lifeline class — households whose TOTAL monthly use is 30 kWh or less.\",\r\n"
    "        \"bldg_hint\":  [\"low_income\", \"single_room\"],\r\n"
    "    },\r\n"
    "    \"Residential Standard (0-300 kWh/month)\": {\r\n"
    "        \"rate_ghc\":   1.9688,\r\n"
    "        \"fixed_ghc\":  10.7309,\r\n"
    "        \"description\": \"Non-lifeline residential, first 300 kWh band.\",\r\n"
    "        \"bldg_hint\":  [\"residential\", \"apartment\", \"bungalow\", \"villa\", \"duplex\"],\r\n"
    "    },\r\n"
    "    \"Residential High Use (>300 kWh/month)\": {\r\n"
    "        \"rate_ghc\":   2.6015,\r\n"
    "        \"fixed_ghc\":  10.7309,\r\n"
    "        \"description\": \"Non-lifeline residential, units above 300 kWh in a month.\",\r\n"
    "        \"bldg_hint\":  [\"mansion\", \"estate\"],\r\n"
    "    },\r\n"
    "    \"Non-Residential Standard (0-300 kWh/month)\": {\r\n"
    "        \"rate_ghc\":   1.7775,\r\n"
    "        \"fixed_ghc\":  12.4282,\r\n"
    "        \"description\": \"Small offices, shops, clinics — first 300 kWh band.\",\r\n"
    "        \"bldg_hint\":  [\"office\", \"retail\", \"shop\", \"clinic\", \"small_commercial\"],\r\n"
    "    },\r\n"
    "    \"Non-Residential High Use (>300 kWh/month)\": {\r\n"
    "        \"rate_ghc\":   2.1649,\r\n"
    "        \"fixed_ghc\":  12.4282,\r\n"
    "        \"description\": \"Larger commercial users (hotels, supermarkets) — units above 300.\",\r\n"
    "        \"bldg_hint\":  [\"commercial\", \"hotel\", \"supermarket\", \"restaurant\", \"church\"],\r\n"
    "    },\r\n"
    "    \"Special Load - LV (hospitals, schools)\": {\r\n"
    "        \"rate_ghc\":   2.3211,\r\n"
    "        \"fixed_ghc\":  500.00,\r\n"
    "        \"description\": \"SLT-LV — hospitals, schools, government buildings on low-voltage supply.\",\r\n"
    "        \"bldg_hint\":  [\"hospital\", \"school\", \"government\", \"institution\", \"university\"],\r\n"
    "    },\r\n"
    "    \"Special Load - MV (medium voltage)\": {\r\n"
    "        \"rate_ghc\":   2.0160,\r\n"
    "        \"fixed_ghc\":  500.00,\r\n"
    "        \"description\": \"SLT-MV — medium-voltage commercial / industrial supply.\",\r\n"
    "        \"bldg_hint\":  [\"medium_industry\", \"campus\"],\r\n"
    "    },\r\n"
    "    \"Special Load - MV-2 (medium voltage, large)\": {\r\n"
    "        \"rate_ghc\":   1.3204,\r\n"
    "        \"fixed_ghc\":  500.00,\r\n"
    "        \"description\": \"SLT-MV-2 — large medium-voltage users.\",\r\n"
    "        \"bldg_hint\":  [\"large_industry\"],\r\n"
    "    },\r\n"
    "    \"Special Load - HV (large facilities)\": {\r\n"
    "        \"rate_ghc\":   1.8212,\r\n"
    "        \"fixed_ghc\":  500.00,\r\n"
    "        \"description\": \"SLT-HV — large facilities on high-voltage supply.\",\r\n"
    "        \"bldg_hint\":  [],\r\n"
    "    },\r\n"
    "    \"Industrial - LV (factories, warehouses)\": {\r\n"
    "        \"rate_ghc\":   2.0160,\r\n"
    "        \"fixed_ghc\":  500.00,\r\n"
    "        \"description\": \"Industrial LV — billed under SLT-MV in PURC Q2 2026.\",\r\n"
    "        \"bldg_hint\":  [\"industrial\", \"factory\", \"warehouse\", \"manufacturing\"],\r\n"
    "    },\r\n"
    "    \"Industrial - HV (large industries)\": {\r\n"
    "        \"rate_ghc\":   1.8212,\r\n"
    "        \"fixed_ghc\":  500.00,\r\n"
    "        \"description\": \"Industrial HV — billed under SLT-HV in PURC Q2 2026.\",\r\n"
    "        \"bldg_hint\":  [],\r\n"
    "    },\r\n"
    "    \"EV Charging Station\": {\r\n"
    "        \"rate_ghc\":   2.0160,\r\n"
    "        \"fixed_ghc\":  500.00,\r\n"
    "        \"description\": \"Commercial EV charging station (new class in PURC Q2 2026).\",\r\n"
    "        \"bldg_hint\":  [\"ev_station\", \"petrol_station\"],\r\n"
    "    },\r\n"
    "}\r\n"
    "\r\n"
    "# Effective date + revision metadata for the dict above.\r\n"
    "GHANA_PURC_TARIFF_META = {\r\n"
    "    \"effective_from\":   \"2026-04-01\",\r\n"
    "    \"published_on\":     \"2026-03-13\",\r\n"
    "    \"quarter\":          \"Q2 2026\",\r\n"
    "    \"source_url\":       \"https://www.purc.com.gh/attachment/288818-20260313090334.pdf\",\r\n"
    "    \"source_title\":     \"PURC 2026 Second Quarter Tariff Review Decision\",\r\n"
    "    \"adjustment_note\": \"Residential -1.66% vs Q1 2026; SLT-LV -13.96%; HV -15.43%.\",\r\n"
    "}\r\n"
).encode("utf-8")

# splice
patched = data[:start] + NEW + data[end:]

# sanity: count of dict entries went from 10 -> 12
old_entry_count = data[start:end].count(b'"rate_ghc"')
new_entry_count = NEW.count(b'"rate_ghc"')
print(f"OLD entries: {old_entry_count}   NEW entries: {new_entry_count}")
assert old_entry_count == 10, f"unexpected OLD entry count {old_entry_count}"
assert new_entry_count == 12, f"unexpected NEW entry count {new_entry_count}"

P.write_bytes(patched)
print(f"OK wrote {len(patched)} bytes (was {len(data)}). Delta {len(patched) - len(data):+d}.")
