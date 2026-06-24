"""Split Generators into its own top-level category.

Was: subcategory "Generators" under category "power_system".
Now: dedicated category code "generators" with its own subcategories
(Diesel / Petrol / Gas / Standby / Prime Power / Open-set / Sound-
proof Canopy / Containerized), default unit, and spec fields.

Code-side changes (web_app.py byte patches):
  1. Add "generators" entry to _MARKETPLACE_CATEGORIES (display_order 215).
  2. Add "generators" key to _MARKETPLACE_SUBCATEGORIES.
  3. Remove "Generators" from _MARKETPLACE_SUBCATEGORIES["power_system"].
  4. Add "generators" key to _MARKETPLACE_DEFAULT_UNIT.
  5. Add "generators" key to _MARKETPLACE_SPEC_FIELDS.
  6. Move Cummins Genset seed row (2 callsites) from power_system to generators.
  7. Add 4 more generator products to the SQLite seed (sized + fuel variety).
  8. Add 4 more generator products to the Postgres seed (parallel update).
  9. Update CSV-template example dict so "generators" maps to a Cummins Genset
     and "power_system" maps to a different example (RMU).

Live DB migration is in .github/workflows/migrate-generators-category.yml
(dry-run gated per feedback_workflow_dry_run_gate).
"""
import sys

path = "web_app.py"
data = open(path, "rb").read()
orig_len = len(data)

# === 1) _MARKETPLACE_CATEGORIES: insert generators after power_system ===
old1 = b'    ("power_system",      "Power System Equipment",           "bi-cpu",              210),\r\n]'
new1 = (
    b'    ("power_system",      "Power System Equipment",           "bi-cpu",              210),\r\n'
    b'    ("generators",        "Generators",                       "bi-lightning-charge-fill", 215),\r\n'
    b']'
)
if data.count(old1) != 1:
    print(f"FAIL: _MARKETPLACE_CATEGORIES anchor (got {data.count(old1)})")
    sys.exit(1)
data = data.replace(old1, new1)

# === 2) _MARKETPLACE_SUBCATEGORIES: add generators ===
# Inject between "power_system" entry and "ict_elv" entry.
old2 = (
    b'    "power_system": [\r\n'
    b'        "RMU", "Generators", "UPS", "Static Transfer Switches",\r\n'
    b'        "Capacitor Banks", "Busduct Systems", "Switchgear",\r\n'
    b'        "Protection Relays",\r\n'
    b'    ],\r\n'
    b'    "ict_elv": [\r\n'
)
new2 = (
    b'    "power_system": [\r\n'
    b'        "RMU", "UPS", "Static Transfer Switches",\r\n'
    b'        "Capacitor Banks", "Busduct Systems", "Switchgear",\r\n'
    b'        "Protection Relays",\r\n'
    b'    ],\r\n'
    b'    "generators": [\r\n'
    b'        "Diesel", "Petrol", "Gas", "Standby", "Prime Power",\r\n'
    b'        "Open-set", "Sound-proof Canopy", "Containerized",\r\n'
    b'        "Portable",\r\n'
    b'    ],\r\n'
    b'    "ict_elv": [\r\n'
)
if data.count(old2) != 1:
    print(f"FAIL: _MARKETPLACE_SUBCATEGORIES anchor (got {data.count(old2)})")
    sys.exit(1)
data = data.replace(old2, new2)

# === 3) _MARKETPLACE_DEFAULT_UNIT: add generators ===
old3 = (
    b'    "power_system":        "No.",\r\n'
    b'    "ict_elv":             "No.",\r\n'
)
new3 = (
    b'    "power_system":        "No.",\r\n'
    b'    "generators":          "No.",\r\n'
    b'    "ict_elv":             "No.",\r\n'
)
if data.count(old3) != 1:
    print(f"FAIL: _MARKETPLACE_DEFAULT_UNIT anchor (got {data.count(old3)})")
    sys.exit(1)
data = data.replace(old3, new3)

# === 4) _MARKETPLACE_SPEC_FIELDS: add generators ===
old4 = (
    b'    "power_system": [\r\n'
    b'        "Rated power", "Voltage", "Current rating", "Phase",\r\n'
    b'        "Frequency", "Protection class", "Cooling / fuel type",\r\n'
    b'    ],\r\n'
    b'    "ict_elv": [\r\n'
)
new4 = (
    b'    "power_system": [\r\n'
    b'        "Rated power", "Voltage", "Current rating", "Phase",\r\n'
    b'        "Frequency", "Protection class", "Cooling / fuel type",\r\n'
    b'    ],\r\n'
    b'    "generators": [\r\n'
    b'        "kVA rating", "Fuel type", "Phase", "Cooling",\r\n'
    b'        "Engine make", "Alternator make", "Speed (rpm)",\r\n'
    b'        "Frequency", "Enclosure", "Control panel", "Fuel tank capacity",\r\n'
    b'    ],\r\n'
    b'    "ict_elv": [\r\n'
)
if data.count(old4) != 1:
    print(f"FAIL: _MARKETPLACE_SPEC_FIELDS anchor (got {data.count(old4)})")
    sys.exit(1)
data = data.replace(old4, new4)

# === 5) SQLite seed: move 250 kVA Cummins from power_system to generators
# AND add 4 more generator products. ===
old5 = b'("power_system",       "250 kVA Cummins Genset",               "Cummins",   "C250D5",     "250 kVA, 3PH, diesel, open-set, 1500 rpm",           "No.", 28500, rs,        45, "Generators"),'
new5 = (
    b'("generators",         "100 kVA Cummins Diesel Genset",        "Cummins",   "C100D5",     "100 kVA, 3PH, diesel, open-set, 1500 rpm",           "No.", 14500, rs,        30, "Open-set"),\r\n'
    b'        ("generators",         "250 kVA Cummins Diesel Genset",        "Cummins",   "C250D5",     "250 kVA, 3PH, diesel, open-set, 1500 rpm",           "No.", 28500, rs,        45, "Open-set"),\r\n'
    b'        ("generators",         "500 kVA Cummins Sound-Proof Canopy",   "Cummins",   "C500D5-CN", "500 kVA, 3PH, diesel, sound-attenuated canopy <75 dBA","No.", 52000, rs,        60, "Sound-proof Canopy"),\r\n'
    b'        ("generators",         "50 kVA Honda Petrol Standby",          "Honda",     "EG5000C",    "50 kVA, 3PH, petrol, recoil + electric start",       "No.",  7800, rs,        21, "Petrol"),\r\n'
    b'        ("generators",         "1000 kVA Containerized Genset",        "Cummins",   "C1000D5-CT","1000 kVA, 3PH, 40-ft container, AMF, redundant",   "No.",110000, rs,        90, "Containerized"),'
)
if data.count(old5) != 1:
    print(f"FAIL: SQLite seed Cummins row (got {data.count(old5)})")
    sys.exit(1)
data = data.replace(old5, new5)

# === 6) Postgres seed: same move + same 4 extra rows ===
old6 = b'("power_system",       "250 kVA Cummins Genset",               "Cummins",   "C250D5",     "250 kVA, 3PH, diesel, open-set, 1500 rpm",           "No.", 28500, sup.get("Cummins", generic), 45, "Generators"),'
new6 = (
    b'("generators",         "100 kVA Cummins Diesel Genset",        "Cummins",   "C100D5",     "100 kVA, 3PH, diesel, open-set, 1500 rpm",           "No.", 14500, sup.get("Cummins", generic), 30, "Open-set"),\r\n'
    b'        ("generators",         "250 kVA Cummins Diesel Genset",        "Cummins",   "C250D5",     "250 kVA, 3PH, diesel, open-set, 1500 rpm",           "No.", 28500, sup.get("Cummins", generic), 45, "Open-set"),\r\n'
    b'        ("generators",         "500 kVA Cummins Sound-Proof Canopy",   "Cummins",   "C500D5-CN", "500 kVA, 3PH, diesel, sound-attenuated canopy <75 dBA","No.", 52000, sup.get("Cummins", generic), 60, "Sound-proof Canopy"),\r\n'
    b'        ("generators",         "50 kVA Honda Petrol Standby",          "Honda",     "EG5000C",    "50 kVA, 3PH, petrol, recoil + electric start",       "No.",  7800, sup.get("Honda", generic), 21, "Petrol"),\r\n'
    b'        ("generators",         "1000 kVA Containerized Genset",        "Cummins",   "C1000D5-CT","1000 kVA, 3PH, 40-ft container, AMF, redundant",   "No.",110000, sup.get("Cummins", generic), 90, "Containerized"),'
)
if data.count(old6) != 1:
    print(f"FAIL: Postgres seed Cummins row (got {data.count(old6)})")
    sys.exit(1)
data = data.replace(old6, new6)

# === 7) CSV-template example: split power_system + generators ===
old7 = b'        "power_system":        ("250 kVA Cummins Genset",               28500, "Cummins",   "C250D5",     "250 kVA, 3PH, diesel, open-set, 1500 rpm", 45),'
new7 = (
    b'        "power_system":        ("11 kV RMU 2-Way Compact",              11500, "ABB",       "SafeRing-2W","11 kV, 2-way ring main unit, SF6, 630A, 21kA",       75),\r\n'
    b'        "generators":          ("250 kVA Cummins Diesel Genset",        28500, "Cummins",   "C250D5",     "250 kVA, 3PH, diesel, open-set, 1500 rpm", 45),'
)
if data.count(old7) != 1:
    print(f"FAIL: CSV example dict anchor (got {data.count(old7)})")
    sys.exit(1)
data = data.replace(old7, new7)

open(path, "wb").write(data)
print(f"OK: web_app.py {orig_len} -> {len(data)} bytes (+{len(data)-orig_len})")
