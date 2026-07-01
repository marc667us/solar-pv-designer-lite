#!/usr/bin/env python
"""Add two new single-core 500mm² LV cable products to the marketplace:
    - 1C x 500mm2 Cu XLPE/PVC 600/1000V
    - 1C x 500mm2 Cu PVC/PVC  600/1000V

The source spec (pvsolar1/lv cable update11.txt) only ranged 70-400mm2, so
these two 500mm2 prices are engineering extrapolations from that series:

    1C XLPE/PVC ratio  400->500 (+25% conductor):
        source: 970 (300) -> 1290 (400), delta ~33% per size step.
        extrapolated 500mm2 -> 1620 GHS/m.

    1C PVC/PVC single-core: no source; new subcategory.
        Ratio PVC vs XLPE in the 4C series is ~0.93 (4650/5000 at 400mm2).
        For single-core PVC/PVC use ~0.90 factor:
        extrapolated 500mm2 -> 1460 GHS/m.

Owner should validate and override with live supplier quotations via
/supplier/products once quoted.

Patch:
  1. Add subcategory "1C PVC/PVC" to _MARKETPLACE_SUBCATEGORIES.lv_cables
  2. Insert two product tuples into _LV_PANEL_AVR_PRODUCTS_GHS
     -- in BOTH the seed source (new_lv_panel_avr_seed.py) and the copy
     spliced into web_app.py.

Idempotent: skips patches whose result is already present.
"""
from pathlib import Path

ROOT = Path(__file__).parent
WEB  = ROOT / "web_app.py"
SEED = ROOT / "new_lv_panel_avr_seed.py"

# ---------------------------------------------------------------------
# 1. Add "1C PVC/PVC" subcategory to _MARKETPLACE_SUBCATEGORIES.lv_cables
# ---------------------------------------------------------------------
web = WEB.read_bytes()
orig_web_len = len(web)

sub_old = (
    b'    "lv_cables": [\r\n'
    b'        "1C Armoured", "2C Armoured", "3C Armoured", "4C Armoured", "5C Armoured",\r\n'
    b'        "XLPE/SWA/PVC", "PVC/SWA/PVC", "Flexible Power",\r\n'
    b'        "1C XLPE/PVC",\r\n'
    b'    ],\r\n'
)
sub_new = (
    b'    "lv_cables": [\r\n'
    b'        "1C Armoured", "2C Armoured", "3C Armoured", "4C Armoured", "5C Armoured",\r\n'
    b'        "XLPE/SWA/PVC", "PVC/SWA/PVC", "Flexible Power",\r\n'
    b'        "1C XLPE/PVC", "1C PVC/PVC",\r\n'
    b'    ],\r\n'
)
if b'"1C PVC/PVC"' in web:
    print("[skip] '1C PVC/PVC' subcategory already present")
else:
    if sub_old in web:
        web = web.replace(sub_old, sub_new, 1)
        print("[ok] added '1C PVC/PVC' to lv_cables subcategories")
    else:
        print("[abort] lv_cables subcat block not found -- did the prior subcat patch run?")
        raise SystemExit(1)

# ---------------------------------------------------------------------
# 2. Product tuples to insert. Anchor is the last 1C XLPE/PVC entry
# (400mm2 line) which appears verbatim in both files.
# ---------------------------------------------------------------------
anchor = (
    b'    ("Grand Pacific", "lv_cables", "1C x 400mm2 Cu XLPE/PVC Cable 600/1000V",\r\n'
    b'     "Nexans / Tropical / Elsewedy", "LV-1C-400-XLPE",\r\n'
    b'     "Single-core 400mm2 copper XLPE insulated, PVC outer sheath, 600/1000V, unarmoured",\r\n'
    b'     "m", 1290.00, 21, "1C XLPE/PVC"),\r\n'
)

new_entries = (
    b'    ("Opera Market", "lv_cables", "1C x 500mm2 Cu XLPE/PVC Cable 600/1000V",\r\n'
    b'     "Nexans / Tropical / Elsewedy", "LV-1C-500-XLPE",\r\n'
    b'     "Single-core 500mm2 copper XLPE insulated, PVC outer sheath, 600/1000V, unarmoured",\r\n'
    b'     "m", 1620.00, 30, "1C XLPE/PVC"),\r\n'
    b'    ("Agenda Electricals", "lv_cables", "1C x 500mm2 Cu PVC/PVC Cable 600/1000V",\r\n'
    b'     "Nexans / Tropical / Elsewedy", "LV-1C-500-PVCPVC",\r\n'
    b'     "Single-core 500mm2 copper PVC insulated, PVC outer sheath, 600/1000V, unarmoured",\r\n'
    b'     "m", 1460.00, 30, "1C PVC/PVC"),\r\n'
)

marker_500_xlpe = b'"1C x 500mm2 Cu XLPE/PVC Cable 600/1000V"'
marker_500_pvc  = b'"1C x 500mm2 Cu PVC/PVC Cable 600/1000V"'

def _insert(buf: bytes, label: str) -> tuple[bytes, bool]:
    """Insert new_entries after the anchor. Returns (buf, changed)."""
    if marker_500_xlpe in buf and marker_500_pvc in buf:
        print(f"[skip] {label}: 500mm2 entries already present")
        return buf, False
    if anchor not in buf:
        print(f"[warn] {label}: anchor line NOT found -- skipping this file")
        return buf, False
    return buf.replace(anchor, anchor + new_entries, 1), True

# Patch web_app.py
web, w_changed = _insert(web, "web_app.py")
if len(web) != orig_web_len or w_changed:
    if len(web) != orig_web_len:
        backup = WEB.with_suffix(".py.bak-1c500-2026-07-01")
        if not backup.exists():
            backup.write_bytes(WEB.read_bytes())
            print(f"[backup] {backup.name}")
        WEB.write_bytes(web)
        print(f"[write] web_app.py updated ({orig_web_len} -> {len(web)} bytes)")

# Patch source seed file too so re-splice stays in sync
seed_src = SEED.read_bytes()
orig_seed_len = len(seed_src)
seed_src, s_changed = _insert(seed_src, "new_lv_panel_avr_seed.py")
if len(seed_src) != orig_seed_len:
    backup = SEED.with_suffix(".py.bak-1c500-2026-07-01")
    if not backup.exists():
        backup.write_bytes(SEED.read_bytes())
        print(f"[backup] {backup.name}")
    SEED.write_bytes(seed_src)
    print(f"[write] new_lv_panel_avr_seed.py updated ({orig_seed_len} -> {len(seed_src)} bytes)")

print("[done]")
