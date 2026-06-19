# Patch I: extend the supplier CSV upload template -- one example row
# per category drawn from the taxonomy registries, instead of just one
# Transformers row. Surfaces every valid category name + default unit +
# representative subcategory in a single downloadable file.

from pathlib import Path
TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

SENTINEL = b'examples = {\r\n        "transformers":        ("ABB 500'
if SENTINEL in data:
    print("Already patched. No changes written.")
    raise SystemExit(0)

# Anchor copied verbatim from `python3 -c "print(repr(...))"` of the actual bytes.
OLD = b'def supplier_upload_template():\r\n    """Download a starter CSV template with the canonical columns + one example row."""\r\n    import io as _io\r\n    buf = _io.StringIO()\r\n    buf.write(",".join(_UPLOAD_REQUIRED_COLS + _UPLOAD_OPTIONAL_COLS) + "\\n")\r\n    buf.write(\r\n        \'"ABB 500 kVA Distribution Transformer","Transformers",9800,\'\r\n        \'"ABB","TRF-500-DT","500 kVA, 11/0.433 kV, Dyn11","No.",60,"Distribution"\\n\'\r\n    )'

NEW = (
    b'def supplier_upload_template():\r\n'
    b'    """Download a starter CSV template -- header row + one example row\r\n'
    b'    per category so suppliers see every valid category name + the\r\n'
    b'    default unit + a representative subcategory in one file."""\r\n'
    b'    import io as _io\r\n'
    b'    buf = _io.StringIO()\r\n'
    b'    buf.write(",".join(_UPLOAD_REQUIRED_COLS + _UPLOAD_OPTIONAL_COLS) + "\\n")\r\n'
    b'    # One example row per category, drawn from the taxonomy registries.\r\n'
    b'    # Format follows _UPLOAD_REQUIRED_COLS + _UPLOAD_OPTIONAL_COLS:\r\n'
    b'    #   name, category, price_usd, brand, model, spec, unit, lead_time_days, subcategory\r\n'
    b'    examples = {\r\n'
    b'        "transformers":        ("ABB 500 kVA Distribution Transformer", 9800, "ABB",       "TRF-500-DT", "500 kVA, 11/0.433 kV, Dyn11, ONAN", 60),\r\n'
    b'        "avr":                 ("Servo AVR 30 kVA 3-Phase",              1450, "Generic",   "SAVR-30K",   "30 kVA, 3PH, Servo, +/-15% input range", 21),\r\n'
    b'        "hv_cables":           ("11 kV XLPE 3C 70mm2 Cu Armoured",         52, "Nexans",    "HV-11-3C70", "11 kV, Cu, XLPE/SWA/PVC, 3C, 70mm2", 45),\r\n'
    b'        "lv_cables":           ("LV 4C 25mm2 Cu XLPE/SWA/PVC",             22, "Nexans",    "LV-4C-25",   "0.6/1 kV, Cu, 4C, 25mm2, XLPE/SWA/PVC", 21),\r\n'
    b'        "wires":               ("Single Core 2.5mm2 PVC Red (100m)",       28, "Generic",   "SC-2.5-R",   "2.5mm2 Cu, 450/750 V, PVC, red", 7),\r\n'
    b'        "panel_boards":        ("400A MCC Panel",                        3800, "Schneider", "MCC-400",    "400A TPN MCC, Form 3b, 50kA, IP54", 45),\r\n'
    b'        "distribution_boards": ("18-way TPN Distribution Board",          285, "Schneider", "DB-18TPN",   "18-way TPN, 100A incomer, 10kA, IP43", 21),\r\n'
    b'        "isolators":           ("63A 4-Pole Isolator",                     58, "Schneider", "ISO-63-4P",  "63A 4P AC isolator, IP65", 14),\r\n'
    b'        "fuse_switches":       ("100A Switch Fuse with HRC Fuses",        145, "Schneider", "SF-100-HRC", "100A switch fuse, IP30, HRC fuses included", 21),\r\n'
    b'        "conduit":             ("PVC Conduit 25mm Heavy Gauge (3m)",        1, "Generic",   "PVC-25-HG",  "25mm dia heavy-gauge PVC conduit, 3m", 7),\r\n'
    b'        "steel_boxes":         ("1 Gang Deep Steel Box",                    3, "Generic",   "SB-1G-D",    "1 gang deep flush steel back box, 50mm deep", 7),\r\n'
    b'        "circular_boxes":      ("Ceiling Circular Box 65mm",                2, "Generic",   "CB-65",      "65mm dia ceiling box with knockouts", 7),\r\n'
    b'        "cable_trays":         ("Perforated Cable Tray 300mm (3m)",        18, "Generic",   "CT-300P",    "300mm perforated cable tray, HDG, 3m", 21),\r\n'
    b'        "trunking":            ("PVC Mini Trunking 38x16mm (2m)",           4, "Generic",   "MT-38-16",   "PVC mini trunking, 38x16mm, white, 2m", 7),\r\n'
    b'        "earthing":            ("Copper Earth Bar 600mm",                  52, "Generic",   "EB-600",     "600mm Cu earth bar, 25mm x 6mm, 10 holes", 14),\r\n'
    b'        "sockets":             ("MK 13A Twin Switched Socket",             14, "MK",        "K2747WHI",   "13A twin switched socket, white, flush", 7),\r\n'
    b'        "dp_switches":         ("20A DP Water Heater Switch",              11, "MK",        "K5403WHI",   "20A DP switch with neon, flush, white", 7),\r\n'
    b'        "light_switches":      ("1 Gang 2 Way Switch",                      6, "MK",        "K4871WHI",   "1 gang 2 way switch, 10A, white", 7),\r\n'
    b'        "solar_equipment":     ("JA Solar 550W Mono PV Module",           180, "JA Solar",  "JAM72S30-550", "550W, mono-PERC, 72-cell, 21.3% eff.", 21),\r\n'
    b'        "power_system":        ("250 kVA Cummins Genset",               28500, "Cummins",   "C250D5",     "250 kVA, 3PH, diesel, open-set, 1500 rpm", 45),\r\n'
    b'        "ict_elv":             ("24-port Gigabit PoE+ Switch",            620, "Cisco",     "CBS250-24P", "24-port Gigabit + 4 SFP, PoE+ 195W, managed", 21),\r\n'
    b'    }\r\n'
    b'    code_to_label = {row[0]: row[1] for row in _MARKETPLACE_CATEGORIES}\r\n'
    b'    for code, _label, _icon, _order in _MARKETPLACE_CATEGORIES:\r\n'
    b'        ex = examples.get(code)\r\n'
    b'        if not ex:\r\n'
    b'            continue\r\n'
    b'        name, price, brand, model, spec, lead = ex\r\n'
    b'        unit = _MARKETPLACE_DEFAULT_UNIT.get(code, "No.")\r\n'
    b'        subcats = _MARKETPLACE_SUBCATEGORIES.get(code, [])\r\n'
    b'        sub = subcats[0] if subcats else ""\r\n'
    b'        buf.write(\r\n'
    b'            f\'"{name}","{code_to_label[code]}",{price},\'\r\n'
    b'            f\'"{brand}","{model}","{spec}","{unit}",{lead},"{sub}"\\n\'\r\n'
    b'        )'
)

assert data.count(OLD) == 1, f"I anchor not unique (count={data.count(OLD)})"
data = data.replace(OLD, NEW)
TARGET.write_bytes(data)
print(f"OK -- patch I applied, size {TARGET.stat().st_size:,}")
