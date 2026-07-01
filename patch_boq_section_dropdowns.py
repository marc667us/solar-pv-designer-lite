#!/usr/bin/env python
"""Update the inline copy of new_boq_section_catalog_extension.py inside
web_app.py so the Build-all BOQ dropdown lists for LV cables, panel
boards, and AVRs include the products seeded 2026-07-01.

Prior state:
  * The extension was spliced into web_app.py (~L33827) NOT imported,
    so source-file edits didn't affect the running code.
  * Merge logic was "skip if key exists in primary" which meant new
    items couldn't be appended to primary-catalog sections.

Fix (byte replacements on web_app.py):
  1. Replace merge logic so it APPENDS with case-insensitive dedup
     instead of skipping when the key exists.
  2. Extend AVR section with 19 seeded AVRs.
  3. Extend MAIN LV SWITCHBOARDS with 5 Main LV + 4 PFC + 4 MCC + 6 ATS.
  4. Extend PANEL BOARDS with 5 SPN + 5 TPN + 5 Sub-Main.
  5. Extend SUB-FEEDER CABLES AND EARTH LEADS with 24 LV cables + 2 500mm2.
  6. Insert new sections SUBFEEDER CABLES AND EARTHLEADS + SWITCH BOARDS
     AND DISTRIBUTION BOARDS in _NEW_CATALOG_ENTRIES so the new merge
     logic can append their items to the primary catalog too.
"""
from pathlib import Path

ROOT = Path(__file__).parent
WEB = ROOT / "web_app.py"

data = WEB.read_bytes()
orig = len(data)

# ---------------------------------------------------------------------
# 1. Merge logic (skip → append with dedup)
# ---------------------------------------------------------------------
old_merge = (
    b"if _cat is not None:\r\n"
    b"    for _key, _items in _NEW_CATALOG_ENTRIES.items():\r\n"
    b"        # Don't clobber existing entries (data_v2 wins if there's a conflict).\r\n"
    b"        if _key not in _cat:\r\n"
    b"            _cat[_key] = list(_items)\r\n"
)
new_merge = (
    b"if _cat is not None:\r\n"
    b"    for _key, _items in _NEW_CATALOG_ENTRIES.items():\r\n"
    b"        # 2026-07-01: append with case-insensitive description dedup so\r\n"
    b"        # we can extend existing primary-catalog sections with newly\r\n"
    b"        # seeded items instead of silently dropping them.\r\n"
    b"        if _key in _cat:\r\n"
    b"            _existing = {t[0].lower() for t in _cat[_key]}\r\n"
    b"            for _tup in _items:\r\n"
    b"                if _tup and _tup[0].lower() not in _existing:\r\n"
    b"                    _cat[_key].append(_tup)\r\n"
    b"                    _existing.add(_tup[0].lower())\r\n"
    b"        else:\r\n"
    b"            _cat[_key] = list(_items)\r\n"
)

if b"append with case-insensitive description dedup" in data:
    print("[skip] merge logic already updated")
elif old_merge in data:
    data = data.replace(old_merge, new_merge, 1)
    print("[ok] merge logic switched to append")
else:
    print("[abort] merge logic block not found byte-for-byte")
    raise SystemExit(1)

# ---------------------------------------------------------------------
# 2. Extend AVR (add 19 seeded)
# ---------------------------------------------------------------------
old_avr = (
    b'    "AVR": [\r\n'
    b'        ("AVR (servo-motor type, 415V, 100kVA)",                                "No.",   25000),\r\n'
    b'        ("AVR (servo-motor type, 415V, 200kVA)",                                "No.",   42000),\r\n'
    b'        ("AVR (servo-motor type, 415V, 400kVA)",                                "No.",   72000),\r\n'
    b'    ],\r\n'
)
new_avr = (
    b'    "AVR": [\r\n'
    b'        ("AVR (servo-motor type, 415V, 100kVA)",                                "No.",   25000),\r\n'
    b'        ("AVR (servo-motor type, 415V, 200kVA)",                                "No.",   42000),\r\n'
    b'        ("AVR (servo-motor type, 415V, 400kVA)",                                "No.",   72000),\r\n'
    b'        ("1 kVA Single Phase Automatic Voltage Regulator",                      "No.",     850),\r\n'
    b'        ("2 kVA Single Phase Automatic Voltage Regulator",                      "No.",    1250),\r\n'
    b'        ("3 kVA Single Phase Automatic Voltage Regulator",                      "No.",    1850),\r\n'
    b'        ("5 kVA Single Phase Automatic Voltage Regulator",                      "No.",    2850),\r\n'
    b'        ("7.5 kVA Single Phase Automatic Voltage Regulator",                    "No.",    4500),\r\n'
    b'        ("10 kVA Single Phase Automatic Voltage Regulator",                     "No.",    5800),\r\n'
    b'        ("15 kVA Single Phase Automatic Voltage Regulator",                     "No.",    8200),\r\n'
    b'        ("20 kVA Single Phase Automatic Voltage Regulator",                     "No.",   10800),\r\n'
    b'        ("10 kVA Three Phase Automatic Voltage Regulator",                      "No.",   12500),\r\n'
    b'        ("15 kVA Three Phase Automatic Voltage Regulator",                      "No.",   15500),\r\n'
    b'        ("20 kVA Three Phase Automatic Voltage Regulator",                      "No.",   18500),\r\n'
    b'        ("30 kVA Three Phase Automatic Voltage Regulator",                      "No.",   24000),\r\n'
    b'        ("50 kVA Three Phase Automatic Voltage Regulator",                      "No.",   36000),\r\n'
    b'        ("75 kVA Three Phase Automatic Voltage Regulator",                      "No.",   52000),\r\n'
    b'        ("100 kVA Three Phase Automatic Voltage Regulator",                     "No.",   68000),\r\n'
    b'        ("150 kVA Three Phase Automatic Voltage Regulator",                     "No.",   98000),\r\n'
    b'        ("200 kVA Three Phase Automatic Voltage Regulator",                     "No.",  128000),\r\n'
    b'        ("300 kVA Three Phase Automatic Voltage Regulator",                     "No.",  185000),\r\n'
    b'        ("500 kVA Three Phase Automatic Voltage Regulator",                     "No.",  295000),\r\n'
    b'    ],\r\n'
)
if b'"500 kVA Three Phase Automatic Voltage Regulator"' in data:
    print("[skip] AVR already extended")
elif old_avr in data:
    data = data.replace(old_avr, new_avr, 1)
    print("[ok] AVR extended (+19 items)")
else:
    print("[warn] AVR block not found -- skipped")

# ---------------------------------------------------------------------
# 3. Extend MAIN LV SWITCHBOARDS (add 5+4+4+6 = 19 seeded items)
# ---------------------------------------------------------------------
old_mlv = (
    b'    "MAIN LV SWITCHBOARDS": [\r\n'
    b'        ("Main LV switchboard (form 4b, IP54, ACB incomer)",                   "No.",   85000),\r\n'
    b'        ("Capacitor bank PFC automatic (50kVAr)",                               "No.",   28000),\r\n'
    b'        ("Capacitor bank PFC automatic (100kVAr)",                              "No.",   45000),\r\n'
    b'        ("MCCB 400A, 4P, 50kA",                                                  "No.",    4500),\r\n'
    b'        ("MCCB 250A, 4P, 36kA",                                                  "No.",    2800),\r\n'
    b'        ("MCCB 100A, 4P, 25kA",                                                  "No.",    1200),\r\n'
    b'    ],\r\n'
)
new_mlv = old_mlv[:-len(b'    ],\r\n')] + (
    b'        ("800A Main LV Panel Board, ACB incomer, MCCB feeders, metering, SPD, busbars",   "No.",   95000),\r\n'
    b'        ("1000A Main LV Panel Board, ACB incomer, MCCB feeders, metering, SPD, busbars",  "No.",  125000),\r\n'
    b'        ("1250A Main LV Panel Board, ACB incomer, MCCB feeders, metering, SPD, busbars",  "No.",  160000),\r\n'
    b'        ("1600A Main LV Panel Board, ACB incomer, MCCB feeders, metering, SPD, busbars",  "No.",  220000),\r\n'
    b'        ("2000A Main LV Panel Board, ACB incomer, MCCB feeders, metering, SPD, busbars",  "No.",  310000),\r\n'
    b'        ("50 kVAr Automatic PFC Panel, capacitors, contactors, controller, enclosure",    "No.",   20000),\r\n'
    b'        ("100 kVAr Automatic PFC Panel, capacitors, contactors, controller, enclosure",   "No.",   34000),\r\n'
    b'        ("150 kVAr Automatic PFC Panel, capacitors, contactors, controller, enclosure",   "No.",   48000),\r\n'
    b'        ("200 kVAr Automatic PFC Panel, capacitors, contactors, controller, enclosure",   "No.",   62000),\r\n'
    b'        ("4 Feeder MCC Panel, motor starters, overloads, control wiring, enclosure",      "No.",   28000),\r\n'
    b'        ("6 Feeder MCC Panel, motor starters, overloads, control wiring, enclosure",      "No.",   38000),\r\n'
    b'        ("8 Feeder MCC Panel, motor starters, overloads, control wiring, enclosure",      "No.",   50000),\r\n'
    b'        ("12 Feeder MCC Panel, motor starters, overloads, control wiring, enclosure",     "No.",   72000),\r\n'
    b'        ("100A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure",  "No.",   12000),\r\n'
    b'        ("160A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure",  "No.",   16000),\r\n'
    b'        ("250A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure",  "No.",   24000),\r\n'
    b'        ("400A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure",  "No.",   38000),\r\n'
    b'        ("630A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure",  "No.",   65000),\r\n'
    b'        ("1000A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure", "No.",  110000),\r\n'
    b'    ],\r\n'
)
if b'"2000A Main LV Panel Board' in data:
    print("[skip] MAIN LV SWITCHBOARDS already extended")
elif old_mlv in data:
    data = data.replace(old_mlv, new_mlv, 1)
    print("[ok] MAIN LV SWITCHBOARDS extended (+19 items)")
else:
    print("[warn] MAIN LV SWITCHBOARDS block not found -- skipped")

# ---------------------------------------------------------------------
# 4. Extend PANEL BOARDS (add SPN 5 + TPN 5 + Sub-main 5 = 15 items)
# ---------------------------------------------------------------------
old_pb = (
    b'    "PANEL BOARDS": [\r\n'
    b'        ("Sub-main panel board TPN 250A, MCCB outgoing",                        "No.",   12500),\r\n'
    b'        ("Sub-main panel board TPN 400A, MCCB outgoing",                        "No.",   18500),\r\n'
    b'        ("Floor-level panel board, MCB outgoing, 18 way",                       "No.",    4500),\r\n'
    b'    ],\r\n'
)
new_pb = old_pb[:-len(b'    ],\r\n')] + (
    b'        ("4 Way SPN Distribution Board, 63A incomer, MCB outgoing ways, metal enclosure",   "No.",     850),\r\n'
    b'        ("6 Way SPN Distribution Board, 63A incomer, MCB outgoing ways, metal enclosure",   "No.",    1050),\r\n'
    b'        ("8 Way SPN Distribution Board, 63A incomer, MCB outgoing ways, metal enclosure",   "No.",    1250),\r\n'
    b'        ("12 Way SPN Distribution Board, 80A incomer, MCB outgoing ways, metal enclosure",  "No.",    1650),\r\n'
    b'        ("16 Way SPN Distribution Board, 100A incomer, MCB outgoing ways, metal enclosure", "No.",    2200),\r\n'
    b'        ("4 Way TPN Distribution Board, 100A TP incomer, MCB outgoing ways",                "No.",    3500),\r\n'
    b'        ("6 Way TPN Distribution Board, 100A TP incomer, MCB outgoing ways",                "No.",    4200),\r\n'
    b'        ("8 Way TPN Distribution Board, 125A TP incomer, MCB outgoing ways",                "No.",    5200),\r\n'
    b'        ("12 Way TPN Distribution Board, 160A TP incomer, MCB outgoing ways",               "No.",    6800),\r\n'
    b'        ("16 Way TPN Distribution Board, 200A TP incomer, MCB outgoing ways",               "No.",    8500),\r\n'
    b'        ("125A TP&N Sub-Main Panel Board, MCCB incomer, outgoing MCCBs, metering, SPD",     "No.",   12500),\r\n'
    b'        ("160A TP&N Sub-Main Panel Board, MCCB incomer, outgoing MCCBs, metering, SPD",     "No.",   15000),\r\n'
    b'        ("250A TP&N Sub-Main Panel Board, MCCB incomer, outgoing MCCBs, metering, SPD",     "No.",   22000),\r\n'
    b'        ("400A TP&N Sub-Main Panel Board, MCCB incomer, outgoing MCCBs, metering, SPD",     "No.",   34000),\r\n'
    b'        ("630A TP&N Sub-Main Panel Board, MCCB incomer, outgoing MCCBs, metering, SPD",     "No.",   55000),\r\n'
    b'    ],\r\n'
)
if b'"16 Way SPN Distribution Board' in data:
    print("[skip] PANEL BOARDS already extended")
elif old_pb in data:
    data = data.replace(old_pb, new_pb, 1)
    print("[ok] PANEL BOARDS extended (+15 items)")
else:
    print("[warn] PANEL BOARDS block not found -- skipped")

# ---------------------------------------------------------------------
# 5. Extend SUB-FEEDER CABLES AND EARTH LEADS (add 26 seeded)
# ---------------------------------------------------------------------
old_sfe = (
    b'    "SUB-FEEDER CABLES AND EARTH LEADS": [\r\n'
    b'        ("4c x 50mm\xc2\xb2 Cu/XLPE/SWA/PVC sub-feeder cable",                       "M",       651),\r\n'
    b'        ("4c x 35mm\xc2\xb2 Cu/XLPE/SWA/PVC sub-feeder cable",                       "M",       470),\r\n'
    b'        ("4c x 25mm\xc2\xb2 Cu/XLPE/SWA/PVC sub-feeder cable",                       "M",       290),\r\n'
    b'        ("4c x 16mm\xc2\xb2 Cu/XLPE/SWA/PVC sub-feeder cable",                       "M",       190),\r\n'
    b'        ("4c x 10mm\xc2\xb2 Cu/XLPE/SWA/PVC sub-feeder cable",                       "M",       125),\r\n'
    b'        ("1c x 25mm\xc2\xb2 PVC copper earth lead",                                  "M",        65),\r\n'
    b'        ("1c x 16mm\xc2\xb2 PVC copper earth lead",                                  "M",        42),\r\n'
    b'        ("1c x 10mm\xc2\xb2 PVC copper earth lead",                                  "M",        27),\r\n'
    b'        ("Cable gland and lug kit (per cable size)",                          "Set",     180),\r\n'
    b'        ("Cable cleat (per metre)",                                            "M",        45),\r\n'
    b'    ],\r\n'
)

# The mm² character may be mojibake in web_app.py (Windows-1252). Try both.
CABLE_ITEMS = (
    b'        ("4C x 70mm2 Cu XLPE/SWA/PVC Armoured Cable 600/1000V",               "M",       900),\r\n'
    b'        ("4C x 95mm2 Cu XLPE/SWA/PVC Armoured Cable 600/1000V",               "M",      1190),\r\n'
    b'        ("4C x 120mm2 Cu XLPE/SWA/PVC Armoured Cable 600/1000V",              "M",      1500),\r\n'
    b'        ("4C x 150mm2 Cu XLPE/SWA/PVC Armoured Cable 600/1000V",              "M",      1850),\r\n'
    b'        ("4C x 185mm2 Cu XLPE/SWA/PVC Armoured Cable 600/1000V",              "M",      2300),\r\n'
    b'        ("4C x 240mm2 Cu XLPE/SWA/PVC Armoured Cable 600/1000V",              "M",      3000),\r\n'
    b'        ("4C x 300mm2 Cu XLPE/SWA/PVC Armoured Cable 600/1000V",              "M",      3750),\r\n'
    b'        ("4C x 400mm2 Cu XLPE/SWA/PVC Armoured Cable 600/1000V",              "M",      5000),\r\n'
    b'        ("4C x 70mm2 Cu PVC/SWA/PVC Armoured Cable 600/1000V",                "M",       840),\r\n'
    b'        ("4C x 95mm2 Cu PVC/SWA/PVC Armoured Cable 600/1000V",                "M",      1110),\r\n'
    b'        ("4C x 120mm2 Cu PVC/SWA/PVC Armoured Cable 600/1000V",               "M",      1400),\r\n'
    b'        ("4C x 150mm2 Cu PVC/SWA/PVC Armoured Cable 600/1000V",               "M",      1730),\r\n'
    b'        ("4C x 185mm2 Cu PVC/SWA/PVC Armoured Cable 600/1000V",               "M",      2150),\r\n'
    b'        ("4C x 240mm2 Cu PVC/SWA/PVC Armoured Cable 600/1000V",               "M",      2800),\r\n'
    b'        ("4C x 300mm2 Cu PVC/SWA/PVC Armoured Cable 600/1000V",               "M",      3500),\r\n'
    b'        ("4C x 400mm2 Cu PVC/SWA/PVC Armoured Cable 600/1000V",               "M",      4650),\r\n'
    b'        ("1C x 70mm2 Cu XLPE/PVC Cable 600/1000V",                            "M",       230),\r\n'
    b'        ("1C x 95mm2 Cu XLPE/PVC Cable 600/1000V",                            "M",       310),\r\n'
    b'        ("1C x 120mm2 Cu XLPE/PVC Cable 600/1000V",                           "M",       390),\r\n'
    b'        ("1C x 150mm2 Cu XLPE/PVC Cable 600/1000V",                           "M",       485),\r\n'
    b'        ("1C x 185mm2 Cu XLPE/PVC Cable 600/1000V",                           "M",       600),\r\n'
    b'        ("1C x 240mm2 Cu XLPE/PVC Cable 600/1000V",                           "M",       775),\r\n'
    b'        ("1C x 300mm2 Cu XLPE/PVC Cable 600/1000V",                           "M",       970),\r\n'
    b'        ("1C x 400mm2 Cu XLPE/PVC Cable 600/1000V",                           "M",      1290),\r\n'
    b'        ("1C x 500mm2 Cu XLPE/PVC Cable 600/1000V",                           "M",      1620),\r\n'
    b'        ("1C x 500mm2 Cu PVC/PVC Cable 600/1000V",                            "M",      1460),\r\n'
)
new_sfe = old_sfe[:-len(b'    ],\r\n')] + CABLE_ITEMS + b'    ],\r\n'

if b'"1C x 500mm2 Cu PVC/PVC Cable 600/1000V"' in data:
    print("[skip] SUB-FEEDER CABLES AND EARTH LEADS already extended")
elif old_sfe in data:
    data = data.replace(old_sfe, new_sfe, 1)
    print("[ok] SUB-FEEDER CABLES AND EARTH LEADS extended (+26 items)")
else:
    print("[warn] SUB-FEEDER CABLES block not found (encoding mismatch?) -- skipped")

# ---------------------------------------------------------------------
# 6. Insert NEW sections into _NEW_CATALOG_ENTRIES so the append-merge
#    catches primary-catalog spellings "SUBFEEDER CABLES AND EARTHLEADS"
#    and "SWITCH BOARDS AND DISTRIBUTION BOARDS".
# ---------------------------------------------------------------------
# Anchor: the closing `}\r\n\r\n` of _NEW_CATALOG_ENTRIES right before the
# splice code. Find the "Integration with HVAC" block that closes the dict.
anchor = (
    b'    "INTEGRATION WITH HVAC, LIGHTING, FIRE ALARM, ACCESS CONTROL": [\r\n'
    b'        ("BACnet / Modbus integration to HVAC plant (per chiller / AHU)",       "Item",   4500),\r\n'
    b'        ("DALI / KNX integration to lighting control",                          "Item",   3500),\r\n'
    b'        ("Fire-alarm interface (volt-free contacts + BACnet)",                  "Item",   2800),\r\n'
    b'        ("Access-control / CCTV interface",                                     "Item",   3500),\r\n'
    b'        ("Lift / escalator status integration",                                  "Item",   2500),\r\n'
    b'    ],\r\n'
    b'}\r\n'
)
new_sections = (
    b'    "INTEGRATION WITH HVAC, LIGHTING, FIRE ALARM, ACCESS CONTROL": [\r\n'
    b'        ("BACnet / Modbus integration to HVAC plant (per chiller / AHU)",       "Item",   4500),\r\n'
    b'        ("DALI / KNX integration to lighting control",                          "Item",   3500),\r\n'
    b'        ("Fire-alarm interface (volt-free contacts + BACnet)",                  "Item",   2800),\r\n'
    b'        ("Access-control / CCTV interface",                                     "Item",   3500),\r\n'
    b'        ("Lift / escalator status integration",                                  "Item",   2500),\r\n'
    b'    ],\r\n'
    b'\r\n'
    b'    "SUBFEEDER CABLES AND EARTHLEADS": [\r\n'
    + CABLE_ITEMS +
    b'    ],\r\n'
    b'\r\n'
    b'    "SWITCH BOARDS AND DISTRIBUTION BOARDS": [\r\n'
    b'        ("4 Way SPN Distribution Board, 63A incomer, MCB outgoing ways, metal enclosure",   "No.",     850),\r\n'
    b'        ("6 Way SPN Distribution Board, 63A incomer, MCB outgoing ways, metal enclosure",   "No.",    1050),\r\n'
    b'        ("8 Way SPN Distribution Board, 63A incomer, MCB outgoing ways, metal enclosure",   "No.",    1250),\r\n'
    b'        ("12 Way SPN Distribution Board, 80A incomer, MCB outgoing ways, metal enclosure",  "No.",    1650),\r\n'
    b'        ("16 Way SPN Distribution Board, 100A incomer, MCB outgoing ways, metal enclosure", "No.",    2200),\r\n'
    b'        ("4 Way TPN Distribution Board, 100A TP incomer, MCB outgoing ways",                "No.",    3500),\r\n'
    b'        ("6 Way TPN Distribution Board, 100A TP incomer, MCB outgoing ways",                "No.",    4200),\r\n'
    b'        ("8 Way TPN Distribution Board, 125A TP incomer, MCB outgoing ways",                "No.",    5200),\r\n'
    b'        ("12 Way TPN Distribution Board, 160A TP incomer, MCB outgoing ways",               "No.",    6800),\r\n'
    b'        ("16 Way TPN Distribution Board, 200A TP incomer, MCB outgoing ways",               "No.",    8500),\r\n'
    b'        ("125A TP&N Sub-Main Panel Board, MCCB incomer, outgoing MCCBs, metering, SPD",     "No.",   12500),\r\n'
    b'        ("160A TP&N Sub-Main Panel Board, MCCB incomer, outgoing MCCBs, metering, SPD",     "No.",   15000),\r\n'
    b'        ("250A TP&N Sub-Main Panel Board, MCCB incomer, outgoing MCCBs, metering, SPD",     "No.",   22000),\r\n'
    b'        ("400A TP&N Sub-Main Panel Board, MCCB incomer, outgoing MCCBs, metering, SPD",     "No.",   34000),\r\n'
    b'        ("630A TP&N Sub-Main Panel Board, MCCB incomer, outgoing MCCBs, metering, SPD",     "No.",   55000),\r\n'
    b'        ("800A Main LV Panel Board, ACB incomer, MCCB feeders, metering, SPD, busbars",     "No.",   95000),\r\n'
    b'        ("1000A Main LV Panel Board, ACB incomer, MCCB feeders, metering, SPD, busbars",    "No.",  125000),\r\n'
    b'        ("1250A Main LV Panel Board, ACB incomer, MCCB feeders, metering, SPD, busbars",    "No.",  160000),\r\n'
    b'        ("1600A Main LV Panel Board, ACB incomer, MCCB feeders, metering, SPD, busbars",    "No.",  220000),\r\n'
    b'        ("2000A Main LV Panel Board, ACB incomer, MCCB feeders, metering, SPD, busbars",    "No.",  310000),\r\n'
    b'        ("100A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure",  "No.",   12000),\r\n'
    b'        ("160A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure",  "No.",   16000),\r\n'
    b'        ("250A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure",  "No.",   24000),\r\n'
    b'        ("400A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure",  "No.",   38000),\r\n'
    b'        ("630A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure",  "No.",   65000),\r\n'
    b'        ("1000A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure", "No.",  110000),\r\n'
    b'        ("4 Feeder MCC Panel, motor starters, overloads, control wiring, enclosure",      "No.",   28000),\r\n'
    b'        ("6 Feeder MCC Panel, motor starters, overloads, control wiring, enclosure",      "No.",   38000),\r\n'
    b'        ("8 Feeder MCC Panel, motor starters, overloads, control wiring, enclosure",      "No.",   50000),\r\n'
    b'        ("12 Feeder MCC Panel, motor starters, overloads, control wiring, enclosure",     "No.",   72000),\r\n'
    b'        ("50 kVAr Automatic PFC Panel, capacitors, contactors, controller, enclosure",    "No.",   20000),\r\n'
    b'        ("100 kVAr Automatic PFC Panel, capacitors, contactors, controller, enclosure",   "No.",   34000),\r\n'
    b'        ("150 kVAr Automatic PFC Panel, capacitors, contactors, controller, enclosure",   "No.",   48000),\r\n'
    b'        ("200 kVAr Automatic PFC Panel, capacitors, contactors, controller, enclosure",   "No.",   62000),\r\n'
    b'    ],\r\n'
    b'}\r\n'
)
if b'"SWITCH BOARDS AND DISTRIBUTION BOARDS": [\r\n        ("4 Way SPN Distribution Board' in data:
    print("[skip] new SUBFEEDER/SWITCH sections already inserted")
elif anchor in data:
    data = data.replace(anchor, new_sections, 1)
    print("[ok] inserted new sections into _NEW_CATALOG_ENTRIES")
else:
    print("[warn] anchor for new sections not found -- skipped")

if len(data) != orig:
    backup = WEB.with_suffix(".py.bak-boqdropdowns-2026-07-01")
    if not backup.exists():
        backup.write_bytes(WEB.read_bytes())
        print(f"[backup] {backup.name}")
    WEB.write_bytes(data)
    print(f"[write] web_app.py {orig} -> {len(data)} bytes")
