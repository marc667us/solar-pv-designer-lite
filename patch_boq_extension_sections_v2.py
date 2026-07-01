#!/usr/bin/env python
"""Follow-up to patch_boq_section_dropdowns.py.

Previous patch's guards matched strings elsewhere in web_app.py (the LV
panel AVR seed splice at ~L35324), so it skipped extending AVR / MAIN
LV SWITCHBOARDS / PANEL BOARDS / SUB-FEEDER CABLES AND EARTH LEADS.

This patch uses precise byte-anchors that only match inside the inline
copy of new_boq_section_catalog_extension.py in web_app.py.
"""
from pathlib import Path

ROOT = Path(__file__).parent
WEB = ROOT / "web_app.py"

data = WEB.read_bytes()
orig = len(data)

# Guard by looking for a byte pattern that only exists in the extension
# inline copy: the extension's placeholder AVR entries.
INLINE_MARKER = b'("AVR (servo-motor type, 415V, 100kVA)"'
assert INLINE_MARKER in data, "extension inline copy not found"

# AVR ---------------------------------------------------------------
old_avr = (
    b'    "AVR": [\r\n'
    b'        ("AVR (servo-motor type, 415V, 100kVA)",                                "No.",   25000),\r\n'
    b'        ("AVR (servo-motor type, 415V, 200kVA)",                                "No.",   42000),\r\n'
    b'        ("AVR (servo-motor type, 415V, 400kVA)",                                "No.",   72000),\r\n'
    b'    ],\r\n'
)
new_avr = old_avr[:-len(b'    ],\r\n')] + (
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
if old_avr in data:
    data = data.replace(old_avr, new_avr, 1)
    print("[ok] AVR extended in-place")

# MAIN LV SWITCHBOARDS ----------------------------------------------
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
if old_mlv in data:
    data = data.replace(old_mlv, new_mlv, 1)
    print("[ok] MAIN LV SWITCHBOARDS extended in-place")

# PANEL BOARDS ------------------------------------------------------
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
if old_pb in data:
    data = data.replace(old_pb, new_pb, 1)
    print("[ok] PANEL BOARDS extended in-place")

# SUB-FEEDER CABLES AND EARTH LEADS (mm² byte encoding is UTF-8)
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
if old_sfe in data:
    data = data.replace(old_sfe, new_sfe, 1)
    print("[ok] SUB-FEEDER CABLES AND EARTH LEADS extended in-place (mm² utf-8)")
else:
    # Fallback: try Windows-1252 mojibake (\xb2 alone)
    old_sfe_ms = old_sfe.replace(b'\xc2\xb2', b'\xb2')
    if old_sfe_ms in data:
        new_sfe_ms = old_sfe_ms[:-len(b'    ],\r\n')] + CABLE_ITEMS + b'    ],\r\n'
        data = data.replace(old_sfe_ms, new_sfe_ms, 1)
        print("[ok] SUB-FEEDER CABLES extended (mojibake \\xb2 path)")
    else:
        print("[warn] SUB-FEEDER CABLES block not found in either encoding")

if len(data) != orig:
    backup = WEB.with_suffix(".py.bak-boqdropdowns2-2026-07-01")
    if not backup.exists():
        backup.write_bytes(WEB.read_bytes())
        print(f"[backup] {backup.name}")
    WEB.write_bytes(data)
    print(f"[write] web_app.py {orig} -> {len(data)} bytes")
