#!/usr/bin/env python
"""Idempotent byte-splice: add 3 new subcategories to _MARKETPLACE_SUBCATEGORIES
in web_app.py to support the LV Cable + Panel Board + AVR seed.

Additions:
  - lv_cables:    "1C XLPE/PVC"                        (Single-Core XLPE/PVC cables)
  - panel_boards: "SPN Distribution", "TPN Distribution" (5/8/etc. Way SPN/TPN DBs)

AVR (Single-phase / Three-phase) subcats already exist in the taxonomy.

CRLF preserved. Skips silently on re-run.
"""
from pathlib import Path

ROOT = Path(__file__).parent
target = ROOT / "web_app.py"
data = target.read_bytes()
orig_len = len(data)

# --- Patch 1: lv_cables -- add "1C XLPE/PVC" as final entry ------------
old_lv = (
    b'    "lv_cables": [\r\n'
    b'        "1C Armoured", "2C Armoured", "3C Armoured", "4C Armoured", "5C Armoured",\r\n'
    b'        "XLPE/SWA/PVC", "PVC/SWA/PVC", "Flexible Power",\r\n'
    b'    ],\r\n'
)
new_lv = (
    b'    "lv_cables": [\r\n'
    b'        "1C Armoured", "2C Armoured", "3C Armoured", "4C Armoured", "5C Armoured",\r\n'
    b'        "XLPE/SWA/PVC", "PVC/SWA/PVC", "Flexible Power",\r\n'
    b'        "1C XLPE/PVC",\r\n'
    b'    ],\r\n'
)
if b'"1C XLPE/PVC"' in data:
    print("[skip] lv_cables already has '1C XLPE/PVC'")
else:
    if old_lv in data:
        data = data.replace(old_lv, new_lv, 1)
        print("[ok] lv_cables: added '1C XLPE/PVC'")
    else:
        print("[warn] lv_cables literal block NOT FOUND -- aborting (safe: file unchanged)")
        raise SystemExit(1)

# --- Patch 2: panel_boards -- add "SPN Distribution" + "TPN Distribution"
old_pb = (
    b'    "panel_boards": [\r\n'
    b'        "Main Panel", "Sub-main Panel", "Meter Panel", "ATS Panel",\r\n'
    b'        "Synchronising", "MCC Panel", "PFC Panel", "Custom Control",\r\n'
    b'    ],\r\n'
)
new_pb = (
    b'    "panel_boards": [\r\n'
    b'        "Main Panel", "Sub-main Panel", "Meter Panel", "ATS Panel",\r\n'
    b'        "Synchronising", "MCC Panel", "PFC Panel", "Custom Control",\r\n'
    b'        "SPN Distribution", "TPN Distribution",\r\n'
    b'    ],\r\n'
)
if b'"SPN Distribution"' in data and b'"TPN Distribution"' in data:
    print("[skip] panel_boards already has 'SPN Distribution' + 'TPN Distribution'")
else:
    if old_pb in data:
        data = data.replace(old_pb, new_pb, 1)
        print("[ok] panel_boards: added 'SPN Distribution' + 'TPN Distribution'")
    else:
        print("[warn] panel_boards literal block NOT FOUND -- aborting (safe: file unchanged)")
        raise SystemExit(1)

if len(data) != orig_len:
    target.write_bytes(data)
    print(f"[write] web_app.py updated ({orig_len} -> {len(data)} bytes)")
else:
    print("[noop] web_app.py unchanged")
