# === BEGIN: library_expansion splice ===
# 2026-06-22 (session C): bulk-expand supplier directory + product catalogue
# from pvsolar1/supplier and price/update liberary.txt (sections A-M).
#
# This module ADDS:
#   * 7 new Ghana suppliers (APT Ghana, Compass Engineering, Legrand Ghana,
#     Tricord Limited, JMG Offshore Ghana, Automation Ghana Group,
#     Electrical Supplies Ghana).
#   * ~85 new products covering: wiring + armoured cables, conduits, boxes,
#     wiring accessories, lighting, distribution boards, MCBs/MCCBs/RCBOs,
#     LED panels, surge protection, transformers, generators, UPS,
#     earthing + lightning protection, ICT cabling, network switches,
#     CCTV + access control, BMS + IoT, solar PV.
#   * ~32 new brand records (Marshall-Tufflex, Gewiss, Furse, DEHN, AN Wallis,
#     Adaptaflex, K2 Systems, Schletter, Clenergy, Felicity Solar,
#     Hikvision, Dahua, Axis, Uniview, Aruba, Yealink, Grandstream,
#     Yeastar, ZKTeco, HID, Suprema, Theben, Phoenix Contact, Socomec,
#     Janitza, Vertiv, Eaton MCB, Siemens MV, GoodWe, Solis, Sungrow,
#     Trina, Canadian Solar, Q CELLS).
#
# Prices use the midpoint of the GHS ranges given in the doc (e.g. for
# "8 - 12 GHS/m" the seed writes 10.00 GHS/m which converts to USD via
# _CURRENCY_RATES_FROM_USD['GHS'] at seed time).

_LIBRARY_EXPANSION_SUPPLIERS = [
    ("APT Ghana", "Ghana", "Sales",
     "+233 275 044444 / +233 247 887766",
     "sales@aptghana.com", "www.aptghana.com",
     "North Industrial Area, Dadeban, Accra, Ghana",
     "Schneider Electric, APC, PowerLogic, PrismaSeT, MCCB, MCB, DBs"),
    ("Compass Engineering Services", "Ghana", "Sales",
     "+233 263 201625",
     "sales@compass-ng.com", "www.compass-ng.com",
     "Plot 118/121 Spintex Road, Aramax Compound, Accra, Ghana",
     "Schneider Electric, EcoStruxure, APC, MV/LV equipment"),
    ("Legrand Ghana", "Ghana", "Sales",
     "+233 302 000 000",
     "info@legrand.com.gh", "www.legrand.com",
     "City Galleria Mall, Spintex Road, Accra, Ghana",
     "Legrand, BTicino, Arteor, Mallia, DLP Trunking, Plexo"),
    ("Tricord Limited", "Ghana", "Sales",
     "+233 302 226 600",
     "sales@tricordgh.com", "www.tricordgh.com",
     "Adabraka, Accra (with Takoradi branch), Ghana",
     "Legrand, Electrical Distribution Products, Cables, Switchgear"),
    ("JMG Offshore Ghana", "Ghana", "Sales",
     "+233 202 353713",
     "info@jmgoffshore.com", "www.jmgoffshore.com",
     "East Legon, Bissau Avenue, Accra, Ghana",
     "Legrand, UPS, Generators, Electrical Equipment"),
    ("Automation Ghana Group", "Ghana", "Sales",
     "+233 302 000 000",
     "info@automationghana.com", "www.automationghana.com",
     "Accra, Ghana",
     "Siemens, ABB, Schneider, Industrial Automation, PLC, VFD"),
    ("Electrical Supplies Ghana", "Ghana", "Sales",
     "+233 302 000 000",
     "info@electricalsupplies.gh", "",
     "Accra, Ghana",
     "Cables, Protection Devices, Enclosures, Industrial Components"),
]


# Field tuple: (supplier_name_lookup, category_code, name, brand, model, spec, unit, price_ghs, lead_days, subcategory)
# Prices from update liberary.txt midpoints (GHS); converted to USD at seed time.
_LIBRARY_EXPANSION_PRODUCTS_GHS = [
    # ---- SECTION B: Single-core PVC copper wires (Tricord / Electrical Supplies) ----
    ("Tricord Limited", "wires", "1.5mm² Cu PVC Cable (450/750V)",  "Nexans",       "PVC-1.5",   "1.5mm² Cu PVC, 450/750V, IEC 60227, lighting",      "m",   10.00, 14, "Single Core PVC"),
    ("Tricord Limited", "wires", "2.5mm² Cu PVC Cable (450/750V)",  "Nexans",       "PVC-2.5",   "2.5mm² Cu PVC, 450/750V, IEC 60227, socket wiring", "m",   16.00, 14, "Single Core PVC"),
    ("Tricord Limited", "wires", "4mm² Cu PVC Cable (450/750V)",    "Prysmian",     "PVC-4",     "4mm² Cu PVC, 450/750V, IEC 60227",                  "m",   25.00, 14, "Single Core PVC"),
    ("Tricord Limited", "wires", "6mm² Cu PVC Cable (450/750V)",    "Prysmian",     "PVC-6",     "6mm² Cu PVC, 450/750V, IEC 60227",                  "m",   40.00, 14, "Single Core PVC"),
    ("Tricord Limited", "wires", "10mm² Cu PVC Cable (450/750V)",   "Prysmian",     "PVC-10",    "10mm² Cu PVC, 450/750V, IEC 60227",                 "m",   62.00, 14, "Single Core PVC"),
    ("Tricord Limited", "wires", "16mm² Cu PVC Cable (450/750V)",   "Tropical Cable","PVC-16",   "16mm² Cu PVC, 450/750V, IEC 60227",                 "m",   95.00, 14, "Single Core PVC"),
    ("Tricord Limited", "wires", "Earth Cable 2.5mm² (Green/Yellow)","Nexans",      "CPC-2.5",   "2.5mm² Cu CPC, green/yellow PVC sheath",            "m",   18.00, 14, "Earth Wire"),
    ("Tricord Limited", "wires", "Earth Cable 10mm² (Green/Yellow)","Nexans",       "CPC-10",    "10mm² Cu CPC, green/yellow PVC sheath",             "m",   70.00, 14, "Earth Wire"),

    # ---- LV Armoured cables (XLPE/SWA/PVC, BS 5467) ----
    ("Tricord Limited", "lv_cables", "4C x 16mm² Cu XLPE/SWA/PVC", "Nexans",       "LV-4C-16",   "0.6/1kV 4-core 16mm² Cu XLPE/SWA/PVC, BS 5467",     "m",  150.00, 21, "4C Armoured"),
    ("Tricord Limited", "lv_cables", "4C x 35mm² Cu XLPE/SWA/PVC", "Nexans",       "LV-4C-35",   "0.6/1kV 4-core 35mm² Cu XLPE/SWA/PVC, BS 5467",     "m",  270.00, 21, "4C Armoured"),
    ("Tricord Limited", "lv_cables", "4C x 70mm² Cu XLPE/SWA/PVC", "Prysmian",     "LV-4C-70",   "0.6/1kV 4-core 70mm² Cu XLPE/SWA/PVC, BS 5467",     "m",  500.00, 21, "4C Armoured"),
    ("Tricord Limited", "lv_cables", "4C x 120mm² Cu XLPE/SWA/PVC","Prysmian",     "LV-4C-120",  "0.6/1kV 4-core 120mm² Cu XLPE/SWA/PVC, BS 5467",    "m",  825.00, 30, "4C Armoured"),
    ("Tricord Limited", "lv_cables", "4C x 240mm² Cu XLPE/SWA/PVC","Prysmian",     "LV-4C-240",  "0.6/1kV 4-core 240mm² Cu XLPE/SWA/PVC, BS 5467",    "m", 1675.00, 45, "4C Armoured"),
    ("Tricord Limited", "lv_cables", "1C x 240mm² Cu XLPE/SWA/PVC","Prysmian",     "LV-1C-240",  "0.6/1kV single-core 240mm² Cu XLPE/SWA/PVC",        "m",  800.00, 45, "1C Armoured"),
    ("Tricord Limited", "lv_cables", "1C x 400mm² Cu XLPE/SWA/PVC","Prysmian",     "LV-1C-400",  "0.6/1kV single-core 400mm² Cu XLPE/SWA/PVC",        "m", 1400.00, 45, "1C Armoured"),

    # ---- SECTION A: Conduits (Legrand Ghana / APT Ghana) ----
    ("Legrand Ghana", "conduit", "20mm Heavy-Duty PVC Conduit", "Marshall-Tufflex", "PVC-20HD",  "20mm dia heavy-gauge PVC conduit, BS EN 61386",     "m",   15.00, 7,  "PVC"),
    ("Legrand Ghana", "conduit", "25mm Heavy-Duty PVC Conduit", "Marshall-Tufflex", "PVC-25HD",  "25mm dia heavy-gauge PVC conduit, BS EN 61386",     "m",   21.00, 7,  "PVC"),
    ("Legrand Ghana", "conduit", "32mm Heavy-Duty PVC Conduit", "Marshall-Tufflex", "PVC-32HD",  "32mm dia heavy-gauge PVC conduit, BS EN 61386",     "m",   30.00, 7,  "PVC"),
    ("Legrand Ghana", "conduit", "50mm Heavy-Duty PVC Conduit", "Marshall-Tufflex", "PVC-50HD",  "50mm dia heavy-gauge PVC conduit, BS EN 61386",     "m",   55.00, 14, "PVC"),
    ("APT Ghana",     "conduit", "20mm GI Conduit (Class 4)",   "Legrand",          "GI-20-C4",  "20mm Class 4 galvanised steel conduit",             "m",   45.00, 14, "GI"),
    ("APT Ghana",     "conduit", "25mm GI Conduit (Class 4)",   "Legrand",          "GI-25-C4",  "25mm Class 4 galvanised steel conduit",             "m",   65.00, 14, "GI"),
    ("APT Ghana",     "conduit", "32mm GI Conduit (Class 4)",   "Legrand",          "GI-32-C4",  "32mm Class 4 galvanised steel conduit",             "m",   90.00, 14, "GI"),
    ("Legrand Ghana", "conduit", "Flexible Conduit 20mm (PVC-coated)","Adaptaflex", "FL-20",     "Flexible conduit for final equipment connection",   "m",   38.00, 14, "Flexible"),

    # ---- Steel boxes / circular boxes / trunking / trays ----
    ("Legrand Ghana", "steel_boxes",    "1-Gang Flush Box (35mm deep)",        "MK",       "FB-1G-35",   "Single-gang metal flush back box",          "No.",  22.00, 7,  "1 Gang"),
    ("Legrand Ghana", "steel_boxes",    "2-Gang Flush Box (35mm deep)",        "MK",       "FB-2G-35",   "Two-gang metal flush back box",             "No.",  30.00, 7,  "2 Gang"),
    ("Legrand Ghana", "steel_boxes",    "3-Gang Flush Box (35mm deep)",        "MK",       "FB-3G-35",   "Three-gang metal flush back box",           "No.",  42.00, 7,  "3 Gang"),
    ("Legrand Ghana", "circular_boxes", "Adaptable Box 100x100x50mm (PVC)",    "Gewiss",   "AB-100PVC",  "PVC adaptable box 100x100x50mm",            "No.",  50.00, 7,  "PVC Circular"),
    ("Legrand Ghana", "circular_boxes", "Adaptable Box 150x150x75mm (PVC)",    "Gewiss",   "AB-150PVC",  "PVC adaptable box 150x150x75mm",            "No.",  75.00, 7,  "PVC Circular"),
    ("Legrand Ghana", "circular_boxes", "GI Draw Box (heavy duty)",            "Legrand",  "DB-GI",      "Galvanised draw box for conduit wiring",    "No.", 130.00, 14, "Junction"),
    ("Legrand Ghana", "trunking",       "PVC Trunking 50x50mm",                "Marshall-Tufflex","TR-50PVC","PVC cable trunking 50x50mm",               "m",   42.00, 7,  "PVC"),
    ("Legrand Ghana", "trunking",       "PVC Trunking 100x50mm",               "Legrand",  "TR-100x50",  "PVC cable trunking 100x50mm (DLP-style)",   "m",   65.00, 14, "Cable Management"),
    ("Legrand Ghana", "cable_trays",    "GI Perforated Cable Tray 100mm",      "Legrand",  "CT-100PERF", "Galvanised perforated cable tray, 100mm",   "m",   95.00, 14, "Perforated"),
    ("Legrand Ghana", "cable_trays",    "GI Perforated Cable Tray 150mm",      "Legrand",  "CT-150PERF", "Galvanised perforated cable tray, 150mm",   "m",  140.00, 14, "Perforated"),
    ("Legrand Ghana", "cable_trays",    "GI Perforated Cable Tray 300mm",      "Legrand",  "CT-300PERF", "Galvanised perforated cable tray, 300mm",   "m",  240.00, 21, "Perforated"),

    # ---- SECTION C: Wiring accessories (MK / Crabtree / Schneider via Tricord / APT / Legrand) ----
    ("Tricord Limited", "sockets",        "13A Single Switched Socket",          "MK",        "K2747",     "13A switched single socket outlet, white",  "No.",  68.00, 7,  "Switched"),
    ("Tricord Limited", "sockets",        "13A Twin Switched Socket",            "MK",        "K2747D",    "13A switched twin socket outlet, white",    "No., ", 128.00, 7,  "Switched"),
    ("APT Ghana",       "sockets",        "13A Twin Socket with USB",            "Schneider", "USB-2X13A", "13A twin socket with USB-A + USB-C ports",  "No.",  315.00, 14, "USB"),
    ("APT Ghana",       "sockets",        "Weatherproof Socket IP66",            "MK Masterseal","WP-66",  "13A weatherproof socket outlet, IP66",      "No.",  425.00, 14, "Weatherproof"),
    ("Tricord Limited", "dp_switches",    "20A DP Switch with Neon",             "MK",        "DP20N",     "20A double-pole switch with neon indicator","No.",  85.00, 7,  "Air Conditioner"),
    ("Tricord Limited", "dp_switches",    "45A Cooker Control Unit",             "MK",        "CCU-45",    "45A cooker control unit with neon",         "No.", 245.00, 14, "Air Conditioner"),
    ("Tricord Limited", "dp_switches",    "45A Water Heater Switch",             "MK",        "WH-45",     "45A DP water heater switch with neon",      "No.", 185.00, 14, "Water Heater"),
    ("APT Ghana",       "isolators",      "20A AC Isolator Switch",              "Schneider", "ISO-20",    "20A AC isolator switch (rotary)",           "No.", 165.00, 14, "AC"),
    ("APT Ghana",       "isolators",      "32A AC Isolator Switch",              "Schneider", "ISO-32",    "32A AC isolator switch (rotary)",           "No.", 225.00, 14, "AC"),
    ("APT Ghana",       "isolators",      "63A AC Isolator Switch",              "Schneider", "ISO-63",    "63A AC isolator switch (rotary)",           "No.", 365.00, 14, "AC"),

    # ---- SECTION D: LED lighting (Tricord / APT Ghana) ----
    ("Tricord Limited", "ict_elv", "600x600 LED Panel 36W (3000K/4000K)", "Philips",  "PNL-600-36W", "600x600 recessed LED panel, 36W, daylight",   "No.",  315.00, 14, "Luminaires"),
    ("Tricord Limited", "ict_elv", "12W LED Downlight",                   "Opple",    "DL-12W",      "12W LED downlight recessed, 3000K/4000K",     "No.",   80.00, 7,  "Luminaires"),
    ("Tricord Limited", "ict_elv", "18W LED Downlight",                   "Philips",  "DL-18W",      "18W LED downlight recessed",                  "No.",  105.00, 7,  "Luminaires"),
    ("Tricord Limited", "ict_elv", "IP65 LED Bulkhead",                   "Ledvance", "BH-IP65",     "IP65 LED bulkhead, surface mount",            "No.",  235.00, 14, "Luminaires"),
    ("Tricord Limited", "ict_elv", "Emergency LED Bulkhead (3-hour)",     "Eaton",    "EM-LED-3H",   "Emergency LED bulkhead, 3-hour battery backup","No.", 575.00, 21, "Luminaires"),
    ("Tricord Limited", "ict_elv", "LED Exit Sign",                       "Eaton",    "EX-SIGN",     "LED exit sign, maintained/non-maintained",    "No.",  500.00, 14, "Luminaires"),
    ("Tricord Limited", "ict_elv", "100W LED Floodlight",                 "Philips",  "FL-100W",     "100W LED floodlight, IP65",                   "No.",  615.00, 21, "Luminaires"),
    ("Tricord Limited", "ict_elv", "200W LED Floodlight",                 "Philips",  "FL-200W",     "200W LED floodlight, IP65",                   "No.", 1125.00, 21, "Luminaires"),

    # ---- SECTION E: Distribution boards + breakers (APT Ghana / NESSTRA) ----
    ("APT Ghana", "distribution_boards", "6-way SPN Consumer Unit",  "Schneider", "DB-6SPN",  "6-way SPN DB, flush mounted, 63A RCD + MCBs",  "No.",   875.00, 14, "SPN"),
    ("APT Ghana", "distribution_boards", "12-way SPN DB",            "Schneider", "DB-12SPN", "12-way SPN DB, flush, 100A incomer",           "No.",  1450.00, 14, "SPN"),
    ("APT Ghana", "distribution_boards", "18-way SPN DB",            "Hager",     "DB-18SPN", "18-way SPN DB, flush, 100A incomer",           "No.",  2500.00, 21, "SPN"),
    ("APT Ghana", "distribution_boards", "24-way TPN DB",            "Schneider", "DB-24TPN", "24-way TPN DB, floor mounted, 250A incomer",   "No.",  8250.00, 30, "TPN"),
    ("APT Ghana", "distribution_boards", "36-way TPN DB",            "Schneider", "DB-36TPN", "36-way TPN DB, floor mounted, 400A incomer",   "No.", 16750.00, 45, "TPN"),
    ("APT Ghana", "fuse_switches", "6A MCB Single-Pole",      "Schneider", "MCB-6A-SP",   "6A SP MCB Type C, 6kA, Acti9",                 "No.",   122.00, 7,  "HRC"),
    ("APT Ghana", "fuse_switches", "10A MCB Single-Pole",     "Schneider", "MCB-10A-SP",  "10A SP MCB Type C, 6kA, Acti9",                "No.",   122.00, 7,  "HRC"),
    ("APT Ghana", "fuse_switches", "20A MCB Single-Pole",     "Schneider", "MCB-20A-SP",  "20A SP MCB Type C, 6kA, Acti9",                "No.",   122.00, 7,  "HRC"),
    ("APT Ghana", "fuse_switches", "32A MCB Single-Pole",     "Schneider", "MCB-32A-SP",  "32A SP MCB Type C, 6kA, Acti9",                "No.",   167.00, 7,  "HRC"),
    ("APT Ghana", "fuse_switches", "63A MCB Single-Pole",     "ABB",       "MCB-63A-SP",  "63A SP MCB Type C, 10kA",                      "No.",   285.00, 14, "HRC"),
    ("APT Ghana", "fuse_switches", "100A MCCB",               "Schneider", "MCCB-100",    "100A MCCB Compact NSX, 25kA",                  "No.",  1700.00, 21, "HRC"),
    ("APT Ghana", "fuse_switches", "250A MCCB",               "Schneider", "MCCB-250",    "250A MCCB Compact NSX, 36kA",                  "No.",  4500.00, 30, "HRC"),
    ("APT Ghana", "fuse_switches", "630A MCCB",               "ABB",       "MCCB-630",    "630A MCCB ABB Tmax, 50kA",                     "No.", 16500.00, 45, "HRC"),
    ("APT Ghana", "fuse_switches", "RCCB 30mA 4P",            "Schneider", "RCCB-30-4P",  "4-pole RCCB, 30mA, 63A trip-class A",          "No.",   485.00, 14, "Changeover"),
    ("APT Ghana", "fuse_switches", "RCBO 32A 30mA",           "Schneider", "RCBO-32",     "32A RCBO, 30mA, Acti9 iC60",                   "No.",   385.00, 14, "Changeover"),
    ("APT Ghana", "fuse_switches", "Surge Protection Device (Type 1+2)","DEHN", "SPD-T12","Type 1+2 SPD, 4-pole, 100kA",                  "No.",  1850.00, 21, "Changeover"),

    # ---- SECTION F: Transformers + Generators ----
    ("Automation Ghana Group", "transformers", "500 kVA Distribution Transformer", "ABB",     "T-500-ONAN", "500 kVA 11/0.415 kV ONAN distribution transformer", "No.",  200000.00, 75, "Distribution"),
    ("Automation Ghana Group", "transformers", "1000 kVA Distribution Transformer","ABB",     "T-1000-ONAN","1000 kVA 11/0.415 kV ONAN distribution transformer","No.",  450000.00, 90, "Distribution"),
    ("Automation Ghana Group", "transformers", "1500 kVA Distribution Transformer","Siemens", "T-1500-ONAN","1500 kVA 11/0.415 kV ONAN distribution transformer","No.",  685000.00, 90, "Distribution"),
    ("Automation Ghana Group", "transformers", "2000 kVA Distribution Transformer","Siemens", "T-2000-ONAN","2000 kVA 11/0.415 kV ONAN distribution transformer","No.", 1075000.00, 120,"Distribution"),
    ("Powertech Generators Ghana Limited", "generators", "100 kVA Diesel Generator (Silent)", "Perkins",  "GEN-100-S",  "100 kVA silent diesel generator with ATS panel",   "No.", 132500.00, 60, "Sound-proof Canopy"),
    ("Powertech Generators Ghana Limited", "generators", "250 kVA Diesel Generator (Silent)", "FG Wilson","GEN-250-S",  "250 kVA silent diesel generator with ATS panel",   "No.", 265000.00, 60, "Sound-proof Canopy"),
    ("Powertech Generators Ghana Limited", "generators", "500 kVA Diesel Generator (Silent)", "Cummins",  "GEN-500-S",  "500 kVA silent diesel generator with ATS panel",   "No.", 625000.00, 75, "Sound-proof Canopy"),
    ("Powertech Generators Ghana Limited", "generators", "1000 kVA Diesel Generator (Silent)","Caterpillar","GEN-1000-S","1000 kVA silent diesel generator with ATS panel", "No.",1700000.00, 90, "Sound-proof Canopy"),

    # ---- SECTION G: Earthing + Lightning protection (Tricord / APT) ----
    ("Tricord Limited", "earthing", "Copper-bonded Earth Rod 16mm x 3m", "Furse",     "ER-16-3M",  "Copper-bonded earth rod 16mm dia, 3m long",  "No.",   285.00, 14, "Earth Rods"),
    ("Tricord Limited", "earthing", "Earth Inspection Pit",              "Furse",     "EIP",       "Concrete earth inspection pit with cover",   "No.",   650.00, 14, "Inspection Pits"),
    ("Tricord Limited", "earthing", "Bare Copper Tape 25x3mm",           "Furse",     "BCT-25x3",  "Bare copper tape 25 x 3mm, hard-drawn",      "m",     105.00, 14, "Copper Tape"),
    ("Tricord Limited", "earthing", "Bare Copper Tape 50x6mm",           "Furse",     "BCT-50x6",  "Bare copper tape 50 x 6mm, hard-drawn",      "m",     245.00, 14, "Copper Tape"),
    ("Tricord Limited", "earthing", "Earth Clamp + Bonding Kit",         "Furse",     "ECB-KIT",   "Earth clamp and bonding accessories kit",    "No.",   165.00, 14, "Earth Clamps"),
    ("Tricord Limited", "earthing", "Lightning Air Terminal",            "DEHN",      "LAT-1M",    "1m copper lightning air terminal",           "No.",   485.00, 14, "Earth Rods"),
    ("Tricord Limited", "earthing", "Lightning Down Conductor (copper)", "DEHN",      "LDC-CU",    "Bare copper lightning down conductor",       "m",     105.00, 14, "Copper Tape"),
    ("Tricord Limited", "earthing", "Equipotential Bonding Bar",         "DEHN",      "EBB",       "Copper equipotential bonding bar, drilled", "No.",   525.00, 14, "Earth Bars"),

    # ---- SECTION I + J: ICT cabling + CCTV + access control ----
    ("Comsys Ghana Ltd.", "ict_elv", "CAT6 UTP Cable (305m box)",     "Commscope",  "CAT6-UTP",  "CAT6 UTP horizontal cable, 305m box, blue",  "Roll", 3500.00, 14, "Structured Cabling"),
    ("Comsys Ghana Ltd.", "ict_elv", "CAT6A UTP Cable (305m box)",    "Panduit",    "CAT6A-UTP", "CAT6A UTP horizontal cable, 305m box",       "Roll", 5650.00, 21, "Structured Cabling"),
    ("Comsys Ghana Ltd.", "ict_elv", "12-core Single-mode Fibre",     "Commscope",  "SM-12C",    "OS2 12-core single-mode fibre cable",         "m",      25.00, 14, "Structured Cabling"),
    ("Comsys Ghana Ltd.", "ict_elv", "24-core Single-mode Fibre",     "Commscope",  "SM-24C",    "OS2 24-core single-mode fibre cable",         "m",      36.00, 14, "Structured Cabling"),
    ("Comsys Ghana Ltd.", "ict_elv", "CAT6 RJ45 Outlet",              "Schneider",  "RJ45-CAT6", "CAT6 RJ45 keystone outlet, T568B",            "No.",    95.00, 14, "Data Outlets"),
    ("Comsys Ghana Ltd.", "ict_elv", "CAT6A RJ45 Outlet",             "Panduit",    "RJ45-CAT6A","CAT6A RJ45 keystone outlet, T568B",           "No.",   152.00, 21, "Data Outlets"),
    ("Comsys Ghana Ltd.", "ict_elv", "24-port CAT6 Patch Panel",      "Commscope",  "PP-24-C6",  "24-port CAT6 patch panel, 1U loaded",         "No.",   850.00, 21, "Structured Cabling"),
    ("Comsys Ghana Ltd.", "ict_elv", "48-port CAT6 Patch Panel",      "Panduit",    "PP-48-C6",  "48-port CAT6 patch panel, 2U loaded",         "No.",  1850.00, 21, "Structured Cabling"),
    ("Comsys Ghana Ltd.", "ict_elv", "42U Network Cabinet (free-standing)","APC",  "RACK-42U",  "42U network cabinet, 800x1000mm, glass door","No.",  8750.00, 30, "Network Switches"),
    ("Comsys Ghana Ltd.", "ict_elv", "12U Wall-mounted Cabinet",      "APC",        "RACK-12U",  "12U wall-mounted network cabinet",            "No.",  3250.00, 21, "Network Switches"),
    ("Compu-Ghana Ltd.",  "ict_elv", "24-port PoE+ Switch",           "Cisco",      "SW-24-PoE", "24-port managed PoE+ switch (370W budget)",  "No.",  8750.00, 30, "Network Switches"),
    ("Compu-Ghana Ltd.",  "ict_elv", "WiFi 6 Access Point",           "Aruba",      "AP-WiFi6",  "WiFi 6 indoor PoE access point",              "No.",  2450.00, 21, "Access Points"),
    ("Compu-Ghana Ltd.",  "ict_elv", "Outdoor Wireless AP",           "Ubiquiti",   "AP-OUTDOOR","Outdoor weatherproof PoE access point",       "No.",  2150.00, 21, "Access Points"),
    ("Compu-Ghana Ltd.",  "ict_elv", "IP PBX System",                 "Yeastar",    "PBX-IP",    "IP PBX system, up to 50 SIP users",           "No.",  6250.00, 30, "Telephones"),
    ("Compu-Ghana Ltd.",  "ict_elv", "IP Phone Handset",              "Yealink",    "PHONE-IP",  "Standard IP phone handset, PoE",              "No.",   525.00, 14, "Telephones"),
    ("Comsys Ghana Ltd.", "ict_elv", "Firewall Appliance",            "Fortinet",   "FW-100F",   "FortiGate 100F next-gen firewall",            "No.", 28500.00, 30, "Network Switches"),

    # CCTV + access control
    ("Comsys Ghana Ltd.", "ict_elv", "4MP IP Dome Camera (PoE)",     "Hikvision", "DOME-4MP",  "4MP IP dome camera, PoE, IK10, IR 30m",        "No.",  1175.00, 14, "CCTV"),
    ("Comsys Ghana Ltd.", "ict_elv", "4MP IP Bullet Camera (PoE)",   "Dahua",     "BULLET-4MP","4MP IP bullet camera, PoE, IP67, IR 50m",      "No.",  1325.00, 14, "CCTV"),
    ("Comsys Ghana Ltd.", "ict_elv", "PTZ Camera 25x Zoom",          "Axis",      "PTZ-25X",   "Outdoor PTZ camera 25x optical zoom",           "No.", 14750.00, 30, "CCTV"),
    ("Comsys Ghana Ltd.", "ict_elv", "32-channel NVR",               "Hikvision", "NVR-32CH",  "32-channel NVR + 4TB HDD, RAID-1",              "No.",  8750.00, 21, "CCTV"),
    ("Comsys Ghana Ltd.", "ict_elv", "8TB Surveillance HDD",         "Seagate",   "HDD-8TB",   "Seagate SkyHawk 8TB surveillance HDD",          "No.",  2350.00, 14, "CCTV"),
    ("Comsys Ghana Ltd.", "ict_elv", "Access Control Card Reader",   "ZKTeco",    "AC-READER", "Proximity card reader, weatherproof",           "No.",   650.00, 14, "Access Control"),
    ("Comsys Ghana Ltd.", "ict_elv", "Biometric Reader",             "Suprema",   "BIO-READ",  "Fingerprint + card biometric reader",           "No.",  1450.00, 21, "Access Control"),
    ("Comsys Ghana Ltd.", "ict_elv", "Magnetic Lock",                "ZKTeco",    "MAG-LOCK",  "Single-leaf magnetic door lock (600 lbs)",      "No.",   485.00, 14, "Access Control"),

    # ---- SECTION K + L: BMS + IoT sensors ----
    ("Automation Ghana Group", "power_system", "BMS DDC Controller",                "Schneider", "DDC-32IO", "BACnet/IP DDC controller, 32 UI / 16 UO",  "No.", 5650.00, 30, "Switchgear"),
    ("Automation Ghana Group", "power_system", "AHU Controller",                    "Siemens",   "AHU-CTRL", "Air handling unit controller, BACnet MSTP","No.", 4250.00, 30, "Switchgear"),
    ("Automation Ghana Group", "power_system", "BACnet/Modbus Gateway",             "Schneider", "GW-BMS",   "Multi-protocol BMS gateway",                "No.", 3850.00, 30, "Switchgear"),
    ("Automation Ghana Group", "ict_elv",      "Smart Energy Meter (Modbus)",       "Schneider", "PM-PWR",   "PowerLogic 3-phase smart energy meter",     "No.",  925.00, 14, "Network Switches"),
    ("Automation Ghana Group", "ict_elv",      "Temperature Sensor (Modbus)",       "Honeywell", "TEMP-MOD", "Duct temperature sensor (NTC10K)",          "No.",  145.00, 14, "Structured Cabling"),
    ("Automation Ghana Group", "ict_elv",      "CO2 Sensor (Modbus)",               "Siemens",   "CO2-MOD",  "Wall-mount CO2 sensor 0..2000 ppm",        "No.",  650.00, 14, "Structured Cabling"),
    ("Automation Ghana Group", "ict_elv",      "Occupancy / PIR Sensor",            "Steinel",   "PIR-OCC",  "Ceiling-mount PIR occupancy sensor",        "No.",  220.00, 14, "Structured Cabling"),
    ("Automation Ghana Group", "ict_elv",      "LoRaWAN Indoor Gateway",            "Milesight", "LORA-GW",  "Indoor LoRaWAN gateway, 8-channel",         "No.", 2750.00, 21, "Structured Cabling"),

    # ---- SECTION H: Solar PV equipment ----
    ("Tricord Limited", "solar_equipment", "550W Mono-PERC PV Module",       "JinkoSolar", "JKM-550",     "550W monocrystalline N-Type PV module",       "No.", 1150.00, 30, "PV Modules"),
    ("Tricord Limited", "solar_equipment", "620W Mono N-Type PV Module",     "JA Solar",   "JAM-620",     "620W monocrystalline N-type PV module",       "No.", 1425.00, 30, "PV Modules"),
    ("Tricord Limited", "solar_equipment", "5kW Hybrid Inverter (Single Ph)","Deye",       "SUN-5K-SP",   "5kW hybrid inverter, single phase",           "No.", 8250.00, 21, "Hybrid Inverters"),
    ("Tricord Limited", "solar_equipment", "10kW Hybrid Inverter (3-Phase)", "Deye",       "SUN-10K-3P",  "10kW hybrid inverter, three-phase",           "No.",17250.00, 21, "Hybrid Inverters"),
    ("Tricord Limited", "solar_equipment", "50kW String Inverter (3-Phase)", "Huawei",     "SUN2000-50K", "50kW string inverter, three-phase",           "No.",65000.00, 30, "String Inverters"),
    ("Tricord Limited", "solar_equipment", "100kW String Inverter (3-Phase)","Sungrow",    "SG-100K",     "100kW string inverter, three-phase",          "No.",127500.00,45, "String Inverters"),
    ("Tricord Limited", "solar_equipment", "5 kWh LiFePO4 Battery",          "BYD",        "BAT-5K",      "5 kWh LiFePO4 battery, 51.2V",                "No.",10750.00, 30, "Batteries"),
    ("Tricord Limited", "solar_equipment", "10 kWh LiFePO4 Battery",         "Pylontech",  "BAT-10K",     "10 kWh LiFePO4 battery, 48V",                 "No.",21000.00, 30, "Batteries"),
    ("Tricord Limited", "solar_equipment", "100 kWh Battery Rack",           "BYD",        "BAT-RACK-100","100 kWh LiFePO4 commercial battery rack",     "No.",250000.00,45, "Batteries"),
    ("Tricord Limited", "solar_equipment", "PV DC Cable 4mm²",               "Lapp",       "PV-4MM",      "Solar PV DC cable 4mm², UV-resistant",        "m",      28.00, 14, "Solar Cables"),
    ("Tricord Limited", "solar_equipment", "PV DC Cable 6mm²",               "Prysmian",   "PV-6MM",      "Solar PV DC cable 6mm², UV-resistant",        "m",      40.00, 14, "Solar Cables"),
    ("Tricord Limited", "solar_equipment", "MC4 Connector Pair",             "Staubli",    "MC4-PAIR",    "MC4 connector pair, Type II",                 "Pair",   85.00, 14, "MC4 Connectors"),
    ("Tricord Limited", "solar_equipment", "DC Combiner Box w/ Fuses + SPD", "Schneider",  "DCB-FUSE",    "DC combiner box with fuses and SPD",          "No.",  3250.00, 21, "Combiner Boxes"),
    ("Tricord Limited", "solar_equipment", "PV Mounting Rail (per metre)",   "K2 Systems", "RAIL-K2",     "Aluminium PV mounting rail",                  "m",     185.00, 21, "Mounting Systems"),
    ("Tricord Limited", "solar_equipment", "Solar Monitoring Gateway",       "Huawei",     "SMARTLOG-1000","Huawei SmartLogger solar monitoring gateway","No.",  8500.00, 21, "Monitoring Systems"),

    # ========================================================================
    # 2026-06-22 session C v2: extra +120 line items to push live count past 300.
    # Same midpoint-of-GHS-range pricing convention. Dedup at seed time on
    # (name, brand, supplier_id) -- so additive on every cold start.
    # ========================================================================

    # ---- additional single-core wires + flex (larger sizes) ----
    ("Tricord Limited", "wires", "25mm² Cu PVC Cable (450/750V)",   "Prysmian",     "PVC-25",    "25mm² Cu PVC, 450/750V, IEC 60227",                 "m",   145.00, 21, "Single Core PVC"),
    ("Tricord Limited", "wires", "35mm² Cu PVC Cable (450/750V)",   "Prysmian",     "PVC-35",    "35mm² Cu PVC, 450/750V, IEC 60227",                 "m",   210.00, 21, "Single Core PVC"),
    ("Tricord Limited", "wires", "50mm² Cu PVC Cable (450/750V)",   "Nexans",       "PVC-50",    "50mm² Cu PVC, 450/750V, IEC 60227",                 "m",   295.00, 21, "Single Core PVC"),
    ("Tricord Limited", "wires", "70mm² Cu PVC Cable (450/750V)",   "Nexans",       "PVC-70",    "70mm² Cu PVC, 450/750V, IEC 60227",                 "m",   410.00, 30, "Single Core PVC"),
    ("Tricord Limited", "wires", "95mm² Cu PVC Cable (450/750V)",   "Nexans",       "PVC-95",    "95mm² Cu PVC, 450/750V, IEC 60227",                 "m",   555.00, 30, "Single Core PVC"),
    ("Tricord Limited", "wires", "1.5mm² Flexible Cable (white)",   "Prysmian",     "FLX-1.5",   "1.5mm² flexible 3-core, white sheath",              "m",    18.00, 14, "Flexible"),
    ("Tricord Limited", "wires", "2.5mm² 3-Core Flexible Cable",    "Nexans",       "FLX-2.5-3C","2.5mm² 3-core flex for final equipment connection", "m",    28.00, 14, "Flexible"),
    ("Tricord Limited", "wires", "4mm² 3-Core Flexible Cable",      "Nexans",       "FLX-4-3C",  "4mm² 3-core flex",                                   "m",    45.00, 14, "Flexible"),
    ("Tricord Limited", "wires", "Fire-Resistant Cable 1.5mm² 2C (FP200)","Prysmian", "FR-1.5-2C","FP200 fire-resistant cable 1.5mm² 2C",             "m",    24.00, 14, "Fire-resistant"),
    ("Tricord Limited", "wires", "Earth Cable 4mm² (Green/Yellow)", "Nexans",       "CPC-4",     "4mm² Cu CPC, green/yellow PVC sheath",              "m",    32.00, 14, "Earth Wire"),
    ("Tricord Limited", "wires", "Earth Cable 16mm² (Green/Yellow)","Nexans",       "CPC-16",    "16mm² Cu CPC, green/yellow PVC sheath",             "m",   105.00, 21, "Earth Wire"),
    ("Tricord Limited", "wires", "Earth Cable 70mm² (Green/Yellow)","Prysmian",     "CPC-70",    "70mm² Cu CPC, green/yellow PVC sheath",             "m",   415.00, 30, "Earth Wire"),
    ("Tricord Limited", "wires", "Control Cable 7-Core 1.5mm²",     "Lapp",         "CTRL-7C-1.5","7-core 1.5mm² control cable",                       "m",    52.00, 21, "Control Wire"),
    ("Tricord Limited", "wires", "Control Cable 12-Core 1.5mm²",    "Lapp",         "CTRL-12C-1.5","12-core 1.5mm² control cable",                     "m",    88.00, 21, "Control Wire"),

    # ---- additional 3-core armoured (smaller sites) ----
    ("Tricord Limited", "lv_cables", "3C x 6mm² Cu XLPE/SWA/PVC",   "Nexans",       "LV-3C-6",   "0.6/1kV 3-core 6mm² Cu XLPE/SWA/PVC",               "m",    78.00, 21, "3C Armoured"),
    ("Tricord Limited", "lv_cables", "3C x 10mm² Cu XLPE/SWA/PVC",  "Nexans",       "LV-3C-10",  "0.6/1kV 3-core 10mm² Cu XLPE/SWA/PVC",              "m",   110.00, 21, "3C Armoured"),
    ("Tricord Limited", "lv_cables", "2C x 2.5mm² Cu XLPE/SWA/PVC", "Nexans",       "LV-2C-2.5", "0.6/1kV 2-core 2.5mm² Cu XLPE/SWA/PVC, control",    "m",    44.00, 21, "2C Armoured"),
    ("Tricord Limited", "lv_cables", "2C x 4mm² Cu XLPE/SWA/PVC",   "Nexans",       "LV-2C-4",   "0.6/1kV 2-core 4mm² Cu XLPE/SWA/PVC",               "m",    62.00, 21, "2C Armoured"),
    ("Tricord Limited", "lv_cables", "4C x 6mm² Cu XLPE/SWA/PVC",   "Nexans",       "LV-4C-6",   "0.6/1kV 4-core 6mm² Cu XLPE/SWA/PVC",               "m",    95.00, 21, "4C Armoured"),
    ("Tricord Limited", "lv_cables", "4C x 10mm² Cu XLPE/SWA/PVC",  "Nexans",       "LV-4C-10",  "0.6/1kV 4-core 10mm² Cu XLPE/SWA/PVC",              "m",   122.00, 21, "4C Armoured"),
    ("Tricord Limited", "lv_cables", "5C x 16mm² Cu XLPE/SWA/PVC",  "Prysmian",     "LV-5C-16",  "0.6/1kV 5-core 16mm² Cu XLPE/SWA/PVC, neutral+earth","m",   170.00, 30, "5C Armoured"),

    # ---- HV cables (Apinto / NESSTRA territory) ----
    ("NESSTRA Ghana Ltd", "hv_cables", "11 kV XLPE 3C x 70mm² Cu",  "Nexans",       "HV-11-3C70", "11 kV XLPE/SWA/PVC, 3 core 70mm² Cu",              "m",   485.00, 45, "3C HV Armoured"),
    ("NESSTRA Ghana Ltd", "hv_cables", "11 kV XLPE 3C x 95mm² Cu",  "Nexans",       "HV-11-3C95", "11 kV XLPE/SWA/PVC, 3 core 95mm² Cu",              "m",   615.00, 45, "3C HV Armoured"),
    ("NESSTRA Ghana Ltd", "hv_cables", "11 kV XLPE 3C x 120mm² Cu", "Prysmian",     "HV-11-3C120","11 kV XLPE/SWA/PVC, 3 core 120mm² Cu",             "m",   765.00, 60, "3C HV Armoured"),
    ("NESSTRA Ghana Ltd", "hv_cables", "11 kV XLPE 3C x 185mm² Cu", "Prysmian",     "HV-11-3C185","11 kV XLPE/SWA/PVC, 3 core 185mm² Cu",             "m",  1095.00, 60, "3C HV Armoured"),
    ("NESSTRA Ghana Ltd", "hv_cables", "11 kV XLPE 1C x 240mm² Al", "Nexans",       "HV-11-1C240","11 kV XLPE/SWA/PVC, single-core 240mm² Aluminium", "m",   485.00, 60, "Aluminium HV"),

    # ---- additional conduits + flex ----
    ("Legrand Ghana", "conduit", "16mm Heavy-Duty PVC Conduit",     "Marshall-Tufflex","PVC-16HD","16mm dia heavy-gauge PVC conduit, BS EN 61386",    "m",    10.00, 7,  "PVC"),
    ("Legrand Ghana", "conduit", "40mm Heavy-Duty PVC Conduit",     "Marshall-Tufflex","PVC-40HD","40mm dia heavy-gauge PVC conduit, BS EN 61386",    "m",    42.00, 14, "PVC"),
    ("APT Ghana",     "conduit", "40mm GI Conduit (Class 4)",       "Legrand",      "GI-40-C4",  "40mm Class 4 galvanised steel conduit",            "m",   135.00, 21, "GI"),
    ("APT Ghana",     "conduit", "50mm GI Conduit (Class 4)",       "Legrand",      "GI-50-C4",  "50mm Class 4 galvanised steel conduit",            "m",   195.00, 21, "GI"),
    ("Legrand Ghana", "conduit", "Flexible Conduit 25mm (PVC)",     "Adaptaflex",   "FL-25",     "Flexible conduit 25mm for final equipment",        "m",    55.00, 14, "Flexible"),
    ("Legrand Ghana", "conduit", "Flexible Conduit 32mm (PVC)",     "Adaptaflex",   "FL-32",     "Flexible conduit 32mm",                            "m",    78.00, 14, "Flexible"),

    # ---- additional boxes + trays + trunking ----
    ("Legrand Ghana", "steel_boxes",    "4-Gang Flush Box (35mm)",       "MK",       "FB-4G-35",  "Four-gang metal flush back box",            "No.",  58.00, 14, "4 Gang"),
    ("Legrand Ghana", "steel_boxes",    "1-Gang Surface Box",            "MK",       "SB-1G",     "Single-gang surface back box",              "No.",  28.00, 7,  "Surface"),
    ("Legrand Ghana", "steel_boxes",    "2-Gang Surface Box",            "MK",       "SB-2G",     "Two-gang surface back box",                 "No.",  38.00, 7,  "Surface"),
    ("Legrand Ghana", "circular_boxes", "Round Conduit Box 2-way",       "Legrand",  "CCB-2W",    "Circular conduit box, 2-way, PVC",          "No.",  18.00, 7,  "PVC Circular"),
    ("Legrand Ghana", "circular_boxes", "Round Conduit Box 4-way",       "Legrand",  "CCB-4W",    "Circular conduit box, 4-way, PVC",          "No.",  25.00, 7,  "PVC Circular"),
    ("Legrand Ghana", "circular_boxes", "Junction Box 80x80x40mm (IP65)","Gewiss",   "JB-IP65-80","Weatherproof junction box IP65 80x80x40mm", "No.",  85.00, 14, "Junction"),
    ("Legrand Ghana", "trunking",       "Mini Trunking 16x16mm",         "Legrand",  "MT-16x16",  "Mini PVC trunking 16x16mm",                 "m",    18.00, 7,  "Mini"),
    ("Legrand Ghana", "trunking",       "Mini Trunking 25x16mm",         "Legrand",  "MT-25x16",  "Mini PVC trunking 25x16mm",                 "m",    24.00, 7,  "Mini"),
    ("Legrand Ghana", "trunking",       "DLP Skirting Trunking",         "Legrand",  "DLP-SK",    "Legrand DLP skirting trunking 130x55mm",    "m",   145.00, 21, "Skirting"),
    ("Legrand Ghana", "cable_trays",    "GI Cable Ladder 300mm (LV main)","Legrand", "CL-300",    "Galvanised cable ladder 300mm wide, LV main feeders","m",325.00, 21, "Heavy Duty"),
    ("Legrand Ghana", "cable_trays",    "GI Cable Ladder 450mm",         "Legrand",  "CL-450",    "Galvanised cable ladder 450mm wide",        "m",   485.00, 30, "Heavy Duty"),
    ("Legrand Ghana", "cable_trays",    "Wire Mesh Cable Tray 100mm",    "Legrand",  "WM-100",    "Wire mesh cable tray 100mm wide",           "m",    68.00, 14, "Wire Mesh"),
    ("Legrand Ghana", "cable_trays",    "Wire Mesh Cable Tray 200mm",    "Legrand",  "WM-200",    "Wire mesh cable tray 200mm wide",           "m",   115.00, 14, "Wire Mesh"),

    # ---- additional accessories + outlets ----
    ("APT Ghana",       "sockets",        "13A Single Switched Socket (Schneider)",  "Schneider","SCKT-1G-S", "13A single switched socket, white", "No.",  72.00, 14, "Switched"),
    ("APT Ghana",       "sockets",        "13A Twin Switched Socket (Schneider)",    "Schneider","SCKT-2G-S", "13A twin switched socket, white",  "No.", 142.00, 14, "Switched"),
    ("APT Ghana",       "sockets",        "Schuko Socket Outlet (16A)",              "Schneider","SCKT-SCH",  "European Schuko 16A socket outlet", "No.", 168.00, 14, "Unswitched"),
    ("APT Ghana",       "sockets",        "Floor Socket Outlet (brass)",             "Schneider","SCKT-FLR",  "Brass floor socket outlet, hinged lid","No.", 525.00, 21, "Switched"),
    ("Legrand Ghana",   "sockets",        "13A Single Socket (Legrand Mallia)",      "Legrand",  "MAL-1G",    "Legrand Mallia 13A single socket",  "No.",  88.00, 14, "Switched"),
    ("Legrand Ghana",   "sockets",        "13A Twin Socket (Legrand Mallia)",        "Legrand",  "MAL-2G",    "Legrand Mallia 13A twin socket",    "No.", 165.00, 14, "Switched"),
    ("Legrand Ghana",   "light_switches", "1G 1W Switch (Legrand Arteor)",           "Legrand",  "ART-1G1W",  "Legrand Arteor 1G1W switch",        "No.",  92.00, 14, "1 Gang 1 Way"),
    ("Legrand Ghana",   "light_switches", "2G 2W Switch (Legrand Arteor)",           "Legrand",  "ART-2G2W",  "Legrand Arteor 2G2W switch",        "No.", 135.00, 14, "2 Gang 2 Way"),
    ("Legrand Ghana",   "light_switches", "Intermediate Switch (Schneider AvatarOn)","Schneider","AV-INT",    "Schneider AvatarOn intermediate switch","No.",185.00, 14, "Intermediate"),
    ("Legrand Ghana",   "light_switches", "Dimmer Switch 400W (Schneider)",          "Schneider","AV-DIM",    "AvatarOn dimmer switch 400W",       "No.", 365.00, 14, "Dimmer"),
    ("Legrand Ghana",   "light_switches", "Key Switch (hotel-style)",                "MK",       "KEY-SW",    "Keycard key switch (hotel/access)", "No.", 285.00, 21, "Key Switch"),
    ("Tricord Limited", "dp_switches",    "Fused Connection Unit 13A",               "MK",       "FCU-13A",   "13A fused connection unit, neon",   "No.", 145.00, 14, "Appliance"),
    ("Tricord Limited", "dp_switches",    "Shaver Socket Outlet (115V/230V)",        "MK",       "SHAV",      "Bathroom shaver socket 115V/230V",  "No.", 185.00, 21, "Appliance"),
    ("Tricord Limited", "dp_switches",    "Ceiling Rose + Pendant Set",              "MK",       "CR-PEND",   "Ceiling rose with pendant set",     "No.",  45.00, 7,  "Appliance"),
    ("Tricord Limited", "dp_switches",    "Blank Plate 1G (white)",                  "MK",       "BLANK-1G",  "1-gang blank plate, white",         "No.",  28.00, 7,  "Appliance"),
    ("Tricord Limited", "dp_switches",    "Blank Plate 2G (white)",                  "MK",       "BLANK-2G",  "2-gang blank plate, white",         "No.",  38.00, 7,  "Appliance"),

    # ---- additional lighting (LED tubes, panels, high bay, street) ----
    ("Tricord Limited", "ict_elv", "LED T8 Tube 18W 1.2m",                "Philips",  "T8-18W-12", "LED T8 tube 18W 1.2m, 4000K",        "No.",   95.00, 7,  "Luminaires"),
    ("Tricord Limited", "ict_elv", "LED T5 Tube 24W 1.45m",               "Philips",  "T5-24W",    "LED T5 tube 24W 1.45m, 4000K",       "No.",  135.00, 14, "Luminaires"),
    ("Tricord Limited", "ict_elv", "300x300 LED Panel 18W",               "Opple",    "PNL-300-18",  "300x300 LED panel 18W",            "No.",  185.00, 14, "Luminaires"),
    ("Tricord Limited", "ict_elv", "1200x300 LED Panel 36W",              "Opple",    "PNL-1200-36", "1200x300 LED panel 36W",           "No.",  385.00, 14, "Luminaires"),
    ("Tricord Limited", "ict_elv", "Linear LED Pendant 40W",              "Philips",  "LIN-40W",   "Linear LED pendant 40W, 1.2m, 4000K","No.",  525.00, 21, "Luminaires"),
    ("Tricord Limited", "ict_elv", "LED High Bay 150W (warehouse)",       "Philips",  "HB-150W",   "150W LED high bay, IP54, 5000K",     "No.",  925.00, 21, "Luminaires"),
    ("Tricord Limited", "ict_elv", "LED High Bay 200W",                   "Philips",  "HB-200W",   "200W LED high bay, IP54, 5000K",     "No.", 1325.00, 21, "Luminaires"),
    ("Tricord Limited", "ict_elv", "LED High Bay 300W",                   "Ledvance", "HB-300W",   "300W LED high bay, IP65, 5000K",     "No.", 1875.00, 21, "Luminaires"),
    ("Tricord Limited", "ict_elv", "Street Light LED 60W (pole-mounted)", "Philips",  "SL-60W",    "60W LED street light, IP66",         "No.",  925.00, 21, "Luminaires"),
    ("Tricord Limited", "ict_elv", "Street Light LED 100W",               "Philips",  "SL-100W",   "100W LED street light, IP66",        "No.", 1525.00, 21, "Luminaires"),
    ("Tricord Limited", "ict_elv", "Wall Pack LED 30W",                   "Ledvance", "WP-30W",    "Outdoor wall pack 30W LED, IP65",    "No.",  385.00, 14, "Luminaires"),
    ("Tricord Limited", "ict_elv", "Solar Street Light 60W (all-in-one)", "Felicity Solar","SSL-60","All-in-one solar street light 60W, integrated PV + LFP battery", "No.", 4250.00, 30, "Luminaires"),

    # ---- additional DBs (more SPN/TPN sizes) ----
    ("APT Ghana", "distribution_boards", "4-way SPN DB (flush)",        "Schneider", "DB-4SPN",   "4-way SPN consumer unit, 63A switch",      "No.",   525.00, 14, "SPN"),
    ("APT Ghana", "distribution_boards", "8-way SPN DB (flush)",        "Schneider", "DB-8SPN",   "8-way SPN consumer unit, 100A incomer",    "No.",  1150.00, 14, "SPN"),
    ("APT Ghana", "distribution_boards", "10-way SPN DB",               "Hager",     "DB-10SPN",  "10-way SPN DB, flush",                     "No.",  1325.00, 14, "SPN"),
    ("APT Ghana", "distribution_boards", "16-way SPN DB",               "Hager",     "DB-16SPN",  "16-way SPN DB, flush",                     "No.",  2250.00, 21, "SPN"),
    ("APT Ghana", "distribution_boards", "8-way TPN DB",                "Schneider", "DB-8TPN",   "8-way TPN DB, flush",                      "No.",  3250.00, 21, "TPN"),
    ("APT Ghana", "distribution_boards", "12-way TPN DB",               "Schneider", "DB-12TPN",  "12-way TPN DB, surface, 250A incomer",     "No.",  4850.00, 21, "TPN"),
    ("APT Ghana", "distribution_boards", "Main Panel 600A TPN (Form 3b)","Schneider","MP-600-3B", "Main TPN panel 600A, Form 3b, floor-mount","No.", 28500.00, 45, "Main Panel"),
    ("APT Ghana", "distribution_boards", "MCC Panel 400A Form 4 (Schneider)","Schneider","MCC-400","400A MCC panel, Form 4, motor starters", "No.", 35500.00, 45, "MCC Panel"),
    ("APT Ghana", "distribution_boards", "PFC Panel 100kVAr (auto)",    "Schneider", "PFC-100",   "Automatic power factor correction 100kVAr","No.", 24500.00, 45, "PFC Panel"),
    ("APT Ghana", "distribution_boards", "Synchronising Panel (2x250kVA)","NESSTRA", "SYN-250x2", "Auto-synch panel for 2x 250kVA gen sets",  "No.", 78500.00, 60, "Synchronising"),

    # ---- additional MCBs / RCBOs / RCCBs (full size range) ----
    ("APT Ghana", "fuse_switches", "16A MCB SP",            "Schneider","MCB-16A-SP",  "16A SP MCB Type C, 6kA, Acti9",         "No.", 122.00, 7,  "HRC"),
    ("APT Ghana", "fuse_switches", "25A MCB SP",            "Schneider","MCB-25A-SP",  "25A SP MCB Type C, 6kA, Acti9",         "No.", 122.00, 7,  "HRC"),
    ("APT Ghana", "fuse_switches", "40A MCB SP",            "Schneider","MCB-40A-SP",  "40A SP MCB Type C, 6kA, Acti9",         "No.", 195.00, 7,  "HRC"),
    ("APT Ghana", "fuse_switches", "50A MCB SP",            "Schneider","MCB-50A-SP",  "50A SP MCB Type C, 6kA, Acti9",         "No.", 225.00, 14, "HRC"),
    ("APT Ghana", "fuse_switches", "10A MCB DP",            "Schneider","MCB-10A-DP",  "10A DP MCB Type C, 6kA, Acti9",         "No.", 215.00, 14, "HRC"),
    ("APT Ghana", "fuse_switches", "32A MCB DP",            "Schneider","MCB-32A-DP",  "32A DP MCB Type C, 6kA, Acti9",         "No.", 285.00, 14, "HRC"),
    ("APT Ghana", "fuse_switches", "63A MCB DP",            "ABB",     "MCB-63A-DP",  "63A DP MCB Type C, 10kA",                "No.", 425.00, 14, "HRC"),
    ("APT Ghana", "fuse_switches", "32A MCB TP",            "Schneider","MCB-32A-TP", "32A TP MCB Type C, 6kA, Acti9",         "No.", 485.00, 14, "HRC"),
    ("APT Ghana", "fuse_switches", "63A MCB TP",            "ABB",     "MCB-63A-TP",  "63A TP MCB Type C, 10kA",                "No.", 685.00, 14, "HRC"),
    ("APT Ghana", "fuse_switches", "100A MCB TP",           "ABB",     "MCB-100A-TP", "100A TP MCB Type C, 10kA",               "No.",1450.00, 21, "HRC"),
    ("APT Ghana", "fuse_switches", "400A MCCB",             "Schneider","MCCB-400",   "400A MCCB Compact NSX, 50kA",            "No.",7250.00, 30, "HRC"),
    ("APT Ghana", "fuse_switches", "1000A MCCB",            "ABB",     "MCCB-1000",   "1000A MCCB ABB Tmax, 65kA",              "No.",24500.00,45, "HRC"),
    ("APT Ghana", "fuse_switches", "1600A MCCB",            "ABB",     "MCCB-1600",   "1600A MCCB ABB Tmax, 65kA",              "No.",58500.00,60, "HRC"),
    ("APT Ghana", "fuse_switches", "RCCB 100mA 4P",         "Schneider","RCCB-100-4P","4-pole RCCB, 100mA, 80A",                "No.", 685.00, 14, "Changeover"),
    ("APT Ghana", "fuse_switches", "RCCB 300mA 4P",         "Schneider","RCCB-300-4P","4-pole RCCB, 300mA, 100A (selective)",   "No.", 925.00, 14, "Changeover"),
    ("APT Ghana", "fuse_switches", "Time Switch (7-day digital)","Hager","TS-7D",     "7-day digital time switch, 1 channel",   "No.", 425.00, 14, "Changeover"),
    ("APT Ghana", "fuse_switches", "Photocell Control Unit","Theben",  "PC-32A",      "32A photocell dusk-to-dawn control",     "No.", 285.00, 14, "Changeover"),
    ("APT Ghana", "fuse_switches", "Contactor 25A (3-pole, 230V coil)","Schneider","CT-25A","25A 3-pole contactor, Acti9",      "No.", 285.00, 14, "Changeover"),
    ("APT Ghana", "fuse_switches", "Contactor 63A (3-pole, 230V coil)","ABB",      "CT-63A","63A 3-pole contactor",            "No.", 525.00, 14, "Changeover"),

    # ---- additional UPS sizes ----
    ("Grand Pacific Limited", "power_system", "1 kVA Online UPS (single-phase)",  "Safenergy",  "S1-1K",   "1 kVA online UPS, single-phase, 30min runtime", "No.",  4500.00, 14, "UPS"),
    ("Grand Pacific Limited", "power_system", "3 kVA Online UPS (single-phase)",  "Safenergy",  "S1-3K",   "3 kVA online UPS, single-phase",                 "No.", 11500.00, 14, "UPS"),
    ("Grand Pacific Limited", "power_system", "5 kVA Online UPS (single-phase)",  "Safenergy",  "S1-5K",   "5 kVA online UPS, single-phase",                 "No.", 18500.00, 14, "UPS"),
    ("Grand Pacific Limited", "power_system", "30 kVA Online UPS (three-phase)",  "Safenergy",  "S3-30K",  "30 kVA online UPS, three-phase",                 "No.",185000.00, 21, "UPS"),
    ("Grand Pacific Limited", "power_system", "60 kVA Online UPS (three-phase)",  "Safenergy",  "S3-60K",  "60 kVA online UPS, three-phase",                 "No.",295000.00, 30, "UPS"),
    ("Grand Pacific Limited", "power_system", "100 kVA Online UPS (three-phase)", "Safenergy",  "S3-100K", "100 kVA online UPS, three-phase",                "No.",425000.00, 45, "UPS"),
    ("Grand Pacific Limited", "power_system", "200 kVA Online UPS (three-phase)", "Safenergy",  "S3-200K", "200 kVA online UPS, three-phase",                "No.",750000.00, 60, "UPS"),

    # ---- additional generators ----
    ("Powertech Generators Ghana Limited", "generators", "60 kVA Diesel Generator (silent)",  "Perkins", "GEN-60-S",  "60 kVA silent diesel gen, ATS",       "No.",  82500.00, 45, "Sound-proof Canopy"),
    ("Powertech Generators Ghana Limited", "generators", "150 kVA Diesel Generator (silent)", "Cummins", "GEN-150-S", "150 kVA silent diesel gen, ATS",      "No.", 175000.00, 60, "Sound-proof Canopy"),
    ("Powertech Generators Ghana Limited", "generators", "200 kVA Diesel Generator (silent)", "Cummins", "GEN-200-S", "200 kVA silent diesel gen, ATS",      "No.", 225000.00, 60, "Sound-proof Canopy"),
    ("Powertech Generators Ghana Limited", "generators", "400 kVA Diesel Generator (silent)", "FG Wilson","GEN-400-S","400 kVA silent diesel gen, ATS",     "No.", 475000.00, 75, "Sound-proof Canopy"),
    ("Powertech Generators Ghana Limited", "generators", "750 kVA Diesel Generator (silent)", "Caterpillar","GEN-750-S","750 kVA silent diesel gen, ATS",   "No.",1125000.00, 90, "Sound-proof Canopy"),
    ("Powertech Generators Ghana Limited", "generators", "1500 kVA Diesel Generator (silent)","Caterpillar","GEN-1500-S","1500 kVA silent diesel gen, ATS","No.",2750000.00,120, "Sound-proof Canopy"),

    # ---- additional transformers (sizes 250 / 315 / 1250 / 2500 kVA) ----
    ("Automation Ghana Group", "transformers", "250 kVA Distribution Transformer", "ABB",     "T-250-ONAN",  "250 kVA 11/0.415 kV ONAN distribution transformer", "No.", 115000.00, 60, "Distribution"),
    ("Automation Ghana Group", "transformers", "315 kVA Distribution Transformer", "ABB",     "T-315-ONAN",  "315 kVA 11/0.415 kV ONAN distribution transformer", "No.", 145000.00, 75, "Distribution"),
    ("Automation Ghana Group", "transformers", "1250 kVA Distribution Transformer","Siemens", "T-1250-ONAN", "1250 kVA 11/0.415 kV ONAN distribution transformer","No.", 555000.00, 90, "Distribution"),
    ("Automation Ghana Group", "transformers", "2500 kVA Distribution Transformer","Siemens", "T-2500-ONAN", "2500 kVA 11/0.415 kV ONAN distribution transformer","No.",1325000.00, 120,"Distribution"),

    # ---- additional CCTV + access control ----
    ("Comsys Ghana Ltd.", "ict_elv", "6MP IP Dome Camera (PoE)",     "Hikvision", "DOME-6MP",  "6MP IP dome camera, PoE, IK10, IR 30m",         "No.",  1685.00, 14, "CCTV"),
    ("Comsys Ghana Ltd.", "ict_elv", "8MP IP Bullet Camera (PoE)",   "Hikvision", "BULLET-8MP","8MP IP bullet camera, PoE, IP67, IR 80m",       "No.",  2125.00, 21, "CCTV"),
    ("Comsys Ghana Ltd.", "ict_elv", "Fisheye 360 IP Camera",        "Axis",      "FISH-360",  "Fisheye 360-degree IP camera, indoor",          "No.",  4250.00, 21, "CCTV"),
    ("Comsys Ghana Ltd.", "ict_elv", "16-channel NVR + 4TB HDD",     "Dahua",     "NVR-16CH",  "16-channel NVR + 4TB HDD",                       "No.",  5650.00, 21, "CCTV"),
    ("Comsys Ghana Ltd.", "ict_elv", "64-channel NVR + 2x8TB HDD",   "Hikvision", "NVR-64CH",  "64-channel NVR + 2x8TB HDD, RAID-1",             "No.", 18750.00, 30, "CCTV"),
    ("Comsys Ghana Ltd.", "ict_elv", "4TB Surveillance HDD",         "WD",        "HDD-4TB",   "WD Purple 4TB surveillance HDD",                 "No.",  1325.00, 14, "CCTV"),
    ("Comsys Ghana Ltd.", "ict_elv", "23\" Monitor (security)",     "Dell",      "MON-23",    "23-inch full-HD monitor",                         "No.",  1850.00, 14, "CCTV"),
    ("Comsys Ghana Ltd.", "ict_elv", "Video Doorbell (IP)",          "Hikvision", "DOOR-IP",   "IP video doorbell with 2-way audio",             "No.",  1225.00, 14, "CCTV"),
    ("Comsys Ghana Ltd.", "ict_elv", "Door Controller (4-door)",     "ZKTeco",    "DC-4DOOR",  "4-door access controller, RS485",                "No.",  3850.00, 21, "Access Control"),
    ("Comsys Ghana Ltd.", "ict_elv", "Exit Push Button",             "ZKTeco",    "EX-BTN",    "Exit push button, NO/NC",                        "No.",   145.00, 7,  "Access Control"),
    ("Comsys Ghana Ltd.", "ict_elv", "Door Strike (electric)",       "ZKTeco",    "EL-STR",    "Electric door strike, fail-safe / fail-secure",  "No.",   485.00, 14, "Access Control"),
    ("Comsys Ghana Ltd.", "ict_elv", "Turnstile Tripod (manual)",    "ZKTeco",    "TRI-MAN",   "Manual tripod turnstile",                        "No.",  9250.00, 30, "Access Control"),

    # ---- additional PV solar inverters + batteries + panels ----
    ("Tricord Limited", "solar_equipment", "440W Mono PV Module (entry)",       "Trina",       "JKM-440",     "440W monocrystalline PV module (entry)",       "No.",   825.00, 30, "PV Modules"),
    ("Tricord Limited", "solar_equipment", "460W Mono PV Module",               "Canadian Solar","CS-460",    "460W monocrystalline PV module",              "No.",   895.00, 30, "PV Modules"),
    ("Tricord Limited", "solar_equipment", "480W Mono PERC Bifacial",           "JinkoSolar",  "JKM-480-B",   "480W mono PERC bifacial PV module",           "No.",   985.00, 30, "PV Modules"),
    ("Tricord Limited", "solar_equipment", "500W Mono PERC",                    "JA Solar",    "JAM-500",     "500W mono PERC PV module",                    "No.",  1025.00, 30, "PV Modules"),
    ("Tricord Limited", "solar_equipment", "660W Mono N-Type",                  "Trina",       "TRI-660",     "660W mono N-Type PV module",                  "No.",  1565.00, 45, "PV Modules"),
    ("Tricord Limited", "solar_equipment", "3kW Hybrid Inverter",               "GoodWe",      "ES-3K",       "3kW hybrid inverter, single phase",           "No.",  6250.00, 21, "Hybrid Inverters"),
    ("Tricord Limited", "solar_equipment", "7kW Hybrid Inverter",               "Deye",        "SUN-7K-SP",   "7kW hybrid inverter, single phase",           "No.", 12500.00, 21, "Hybrid Inverters"),
    ("Tricord Limited", "solar_equipment", "15kW Hybrid Inverter (3-Phase)",    "Deye",        "SUN-15K-3P",  "15kW hybrid inverter, three-phase",           "No.", 28500.00, 30, "Hybrid Inverters"),
    ("Tricord Limited", "solar_equipment", "20kW Hybrid Inverter (3-Phase)",    "Solis",       "SOL-20K-3P",  "20kW hybrid inverter, three-phase",           "No.", 36500.00, 30, "Hybrid Inverters"),
    ("Tricord Limited", "solar_equipment", "30kW Hybrid Inverter (3-Phase)",    "Sungrow",     "SUN30K-3P",   "30kW hybrid inverter, three-phase",           "No.", 49500.00, 30, "Hybrid Inverters"),
    ("Tricord Limited", "solar_equipment", "80kW String Inverter (3-Phase)",    "Huawei",      "SUN2000-80K", "80kW string inverter, three-phase",           "No.", 96500.00, 45, "String Inverters"),
    ("Tricord Limited", "solar_equipment", "200kW String Inverter (3-Phase)",   "Sungrow",     "SG-200K",     "200kW string inverter, three-phase",          "No.",225000.00, 60, "String Inverters"),
    ("Tricord Limited", "solar_equipment", "2.5 kWh LiFePO4 Battery",           "Pylontech",   "BAT-2.5K",    "2.5 kWh LiFePO4 battery, 48V",                "No.",  6850.00, 21, "Batteries"),
    ("Tricord Limited", "solar_equipment", "7 kWh LiFePO4 Battery",             "Dyness",      "BAT-7K",      "7 kWh LiFePO4 battery, 51.2V",                "No.", 14850.00, 30, "Batteries"),
    ("Tricord Limited", "solar_equipment", "15 kWh LiFePO4 Battery",            "BYD",         "BAT-15K",     "15 kWh LiFePO4 battery, 48V",                 "No.", 28500.00, 30, "Batteries"),
    ("Tricord Limited", "solar_equipment", "25 kWh LiFePO4 Battery Rack",       "BYD",         "BAT-25K-RACK","25 kWh LiFePO4 battery rack, indoor",         "No.", 47500.00, 45, "Batteries"),
    ("Tricord Limited", "solar_equipment", "MPPT Charge Controller 60A",        "Victron",     "MPPT-60A",    "60A MPPT solar charge controller, 12/24/48V", "No.",  3250.00, 21, "Charge Controllers"),
    ("Tricord Limited", "solar_equipment", "MPPT Charge Controller 100A",       "Victron",     "MPPT-100A",   "100A MPPT solar charge controller, 48V",      "No.",  6850.00, 21, "Charge Controllers"),
    ("Tricord Limited", "solar_equipment", "DC Isolator 1000V DC (PV string)",  "Schneider",   "ISO-DC-1000", "1000V DC isolator switch for PV string",      "No.",   485.00, 14, "DC Isolators"),
    ("Tricord Limited", "solar_equipment", "DC SPD Type 2 (PV string)",         "DEHN",        "SPD-DC-T2",   "Type 2 DC SPD for PV combiner box",           "No.",   985.00, 14, "DC SPD"),
    ("Tricord Limited", "solar_equipment", "AC Combiner Panel (small commercial)","Hager",     "ACP-3P",      "3-phase AC combiner panel for solar plant",   "No.",  4250.00, 30, "Combiner Boxes"),
    ("Tricord Limited", "solar_equipment", "Ground-mount PV Frame Kit",         "Schletter",   "GM-FRAME",    "Ground-mount PV frame kit (per module)",      "No.",   325.00, 21, "Mounting Systems"),
    ("Tricord Limited", "solar_equipment", "Roof Hook (tile roof)",             "K2 Systems",  "ROOF-HOOK",   "K2 roof hook for tile/clay roofs",            "No.",    95.00, 21, "Mounting Systems"),
    ("Tricord Limited", "solar_equipment", "End Clamp 35mm (anodised)",         "K2 Systems",  "END-35",      "K2 end clamp 35mm, anodised aluminium",       "No.",    35.00, 14, "Mounting Systems"),
    ("Tricord Limited", "solar_equipment", "Mid Clamp 35mm (anodised)",         "K2 Systems",  "MID-35",      "K2 mid clamp 35mm, anodised aluminium",       "No.",    32.00, 14, "Mounting Systems"),

    # ---- additional ICT cabling + active ----
    ("Comsys Ghana Ltd.", "ict_elv", "CAT5e UTP Cable (305m box)",   "Belden",    "CAT5E-UTP", "CAT5e UTP cable, 305m, grey",                "Roll", 2150.00, 14, "Structured Cabling"),
    ("Comsys Ghana Ltd.", "ict_elv", "Multi-mode 6-core Fibre (OM3)","Commscope","MM-OM3-6C", "OM3 6-core multi-mode fibre, indoor/outdoor",  "m",      18.00, 14, "Structured Cabling"),
    ("Comsys Ghana Ltd.", "ict_elv", "48-core Single-mode Fibre",    "Commscope", "SM-48C",    "OS2 48-core SM fibre, outdoor armoured",      "m",      62.00, 21, "Structured Cabling"),
    ("Comsys Ghana Ltd.", "ict_elv", "Fibre Patch Cord LC-LC OS2 3m","Commscope","FP-LC-3M",  "OS2 LC-LC fibre patch cord, 3m",              "No.",    85.00, 7,  "Structured Cabling"),
    ("Comsys Ghana Ltd.", "ict_elv", "Fibre Patch Cord SC-LC OS2 5m","Commscope","FP-SC-5M",  "OS2 SC-LC fibre patch cord, 5m",              "No.",   115.00, 14, "Structured Cabling"),
    ("Comsys Ghana Ltd.", "ict_elv", "Fibre ODF 24-port (LC)",       "Commscope", "ODF-24",    "24-port LC ODF, 1U rack-mount",               "No.",  2250.00, 21, "Structured Cabling"),
    ("Comsys Ghana Ltd.", "ict_elv", "Cable Manager 1U (horizontal)","APC",       "CM-1U",     "1U horizontal cable manager",                 "No.",   285.00, 14, "Network Switches"),
    ("Comsys Ghana Ltd.", "ict_elv", "Vertical Cable Manager 42U",   "APC",       "VCM-42U",   "Vertical cable manager for 42U cabinet",      "No.",  1850.00, 21, "Network Switches"),
    ("Compu-Ghana Ltd.",  "ict_elv", "48-port PoE+ Network Switch",  "Aruba",     "SW-48-PoE", "48-port managed PoE+ switch (740W)",          "No.", 14750.00, 30, "Network Switches"),
    ("Compu-Ghana Ltd.",  "ict_elv", "Stacking Switch (10G uplink)", "Cisco",     "STK-10G",   "Stackable core switch 48p 1G + 4p 10G",       "No.", 22500.00, 45, "Network Switches"),
    ("Compu-Ghana Ltd.",  "ict_elv", "WiFi 7 Access Point (indoor)", "Ubiquiti",  "AP-WIFI7",  "Ubiquiti U7 Pro WiFi 7 access point",         "No.",  3850.00, 21, "Access Points"),
    ("Compu-Ghana Ltd.",  "ict_elv", "Mesh WiFi Kit (3-pack)",       "TP-Link Omada","MESH-3P","WiFi mesh kit, 3-pack with controller",       "No.",  2250.00, 14, "Access Points"),
    ("Compu-Ghana Ltd.",  "ict_elv", "PoE+ Injector Single-port",    "TP-Link Omada","POE-INJ","Single-port PoE+ injector (30W)",            "No.",   285.00, 14, "Network Switches"),

    # ---- additional BMS + IoT + sensors ----
    ("Automation Ghana Group", "power_system", "VFD 5.5kW (3-phase)",           "Schneider", "VFD-5K5",     "5.5kW variable frequency drive, 3-phase",       "No.",  6850.00, 21, "Switchgear"),
    ("Automation Ghana Group", "power_system", "VFD 11kW (3-phase)",            "Schneider", "VFD-11K",     "11kW variable frequency drive, 3-phase",        "No.", 11500.00, 21, "Switchgear"),
    ("Automation Ghana Group", "power_system", "PLC Compact (24 I/O)",          "Siemens",   "PLC-24",      "Siemens S7-1200 compact PLC, 24 I/O",           "No.",  5850.00, 21, "Switchgear"),
    ("Automation Ghana Group", "ict_elv",      "Humidity Sensor (Modbus)",      "Honeywell", "HUM-MOD",     "Wall humidity sensor (Modbus, 0..100% RH)",     "No.",   185.00, 14, "Structured Cabling"),
    ("Automation Ghana Group", "ict_elv",      "Smart Water Meter (pulse)",     "Kamstrup",  "WM-PULSE",    "Smart water meter with pulse output",           "No.",  1250.00, 14, "Structured Cabling"),
    ("Automation Ghana Group", "ict_elv",      "Air Quality Sensor (PM2.5/CO2)","Airthings", "AQ-MULTI",    "Multi-gas air quality sensor",                  "No.",  2250.00, 21, "Structured Cabling"),
    ("Automation Ghana Group", "ict_elv",      "BLE Beacon (asset-tracking)",   "Kontakt.io","BLE-BEAC",    "BLE asset-tracking beacon, 5-yr battery",       "No.",   125.00, 14, "Structured Cabling"),
    ("Automation Ghana Group", "ict_elv",      "LoRaWAN End-Node Temperature",  "Milesight", "LORA-TEMP",   "LoRaWAN temperature end-node, IP65",            "No.",   485.00, 14, "Structured Cabling"),
    ("Automation Ghana Group", "ict_elv",      "BACnet/IP to MSTP Router",      "Schneider", "ROUT-BAC",    "BACnet/IP to BACnet/MSTP router",                "No.",  3250.00, 21, "Network Switches"),

    # ---- additional earthing / lightning protection ----
    ("Tricord Limited", "earthing", "Solid Copper Earth Rod 14mm x 1.8m","AN Wallis","CR-14-1.8","Solid copper earth rod 14mm dia x 1.8m",     "No.", 195.00, 14, "Earth Rods"),
    ("Tricord Limited", "earthing", "Earth Rod Coupler",              "Furse",     "ER-COUP",  "Earth rod coupler bolt",                        "No.",  85.00, 14, "Earth Rods"),
    ("Tricord Limited", "earthing", "Earth Rod Driving Stud",         "Furse",     "ER-STUD",  "Earth rod driving stud (rope-style)",           "No.",  68.00, 14, "Earth Rods"),
    ("Tricord Limited", "earthing", "Earth Bar (12-way drilled)",     "Furse",     "EB-12",    "12-way copper earth bar, drilled, insulated",   "No.", 1250.00, 21, "Earth Bars"),
    ("Tricord Limited", "earthing", "Exothermic Welding Kit (CAD)",   "Furse",     "EX-CAD",   "Exothermic welding kit, 25mm² to 70mm²",        "No.", 2850.00, 21, "Exothermic Kits"),
    ("Tricord Limited", "earthing", "Chemical Earthing Compound (25kg)","DEHN",    "CHEM-25",  "Conductive earthing compound, 25kg sack",       "No.",  385.00, 21, "Chemical Earthing"),
    ("Tricord Limited", "earthing", "Lightning Air Terminal 2m",      "DEHN",      "LAT-2M",   "2m copper lightning air terminal",              "No.",  725.00, 14, "Earth Rods"),
    ("Tricord Limited", "earthing", "ESE Lightning Air Terminal",     "LPI",       "ESE-LPI",  "Early Streamer Emission lightning air terminal","No.", 8500.00, 30, "Earth Rods"),

    # ---- additional miscellaneous ----
    ("APT Ghana", "panel_boards", "Meter Panel (single-phase, 1-meter)","Schneider","MP-1PH",  "Single-phase meter panel for utility metering","No.", 1250.00, 21, "Meter Panel"),
    ("APT Ghana", "panel_boards", "Meter Panel (3-phase, 4-meter)",     "Schneider","MP-3PH-4M","3-phase 4-meter housing panel",               "No.", 4250.00, 30, "Meter Panel"),
    ("APT Ghana", "panel_boards", "ATS Panel 250A",                     "Socomec",  "ATS-250",  "Automatic transfer switch panel 250A",         "No.",18500.00, 30, "ATS Panel"),
    ("APT Ghana", "panel_boards", "ATS Panel 630A",                     "Socomec",  "ATS-630",  "Automatic transfer switch panel 630A",         "No.",38500.00, 45, "ATS Panel"),

    # ======================================================================
    # 2026-06-22 session C v3: top-up AVR (was 1 product) + UPS (was 9).
    # Source: same indicative GHS midpoints + supplier mapping from
    # update liberary.txt. AVR sizes 3-1500kVA single + three phase, both
    # servo and static. UPS sizes 2-500kVA across Safenergy / APC /
    # Eaton / Vertiv / Huawei.
    # ======================================================================

    # ---- AVR: Single-phase Servo ----
    ("Grand Pacific Limited", "avr", "3 kVA Single-Phase Servo AVR",      "Safenergy", "AVR-3K-SP-S",   "3 kVA single-phase servo voltage stabilizer, ±15% input range, copper winding", "No.",   2850.00, 14, "Single-phase"),
    ("Grand Pacific Limited", "avr", "5 kVA Single-Phase Servo AVR",      "Safenergy", "AVR-5K-SP-S",   "5 kVA single-phase servo voltage stabilizer",                                    "No.",   4250.00, 14, "Single-phase"),
    ("Grand Pacific Limited", "avr", "10 kVA Single-Phase Servo AVR",     "Safenergy", "AVR-10K-SP-S",  "10 kVA single-phase servo voltage stabilizer, wall-mount",                       "No.",   7850.00, 14, "Single-phase"),
    ("Grand Pacific Limited", "avr", "15 kVA Single-Phase Servo AVR",     "Safenergy", "AVR-15K-SP-S",  "15 kVA single-phase servo voltage stabilizer, floor-mount",                      "No.",  11500.00, 14, "Single-phase"),
    ("Grand Pacific Limited", "avr", "30 kVA Single-Phase Servo AVR",     "Safenergy", "AVR-30K-SP-S",  "30 kVA single-phase servo voltage stabilizer, industrial",                       "No.",  22500.00, 21, "Single-phase"),

    # ---- AVR: Three-phase Servo ----
    ("Grand Pacific Limited", "avr", "15 kVA Three-Phase Servo AVR",      "Safenergy", "AVR-15K-3P-S",  "15 kVA three-phase servo voltage stabilizer, copper winding, ±25% range",        "No.",  18500.00, 21, "Three-phase"),
    ("Grand Pacific Limited", "avr", "30 kVA Three-Phase Servo AVR",      "Safenergy", "AVR-30K-3P-S",  "30 kVA three-phase servo voltage stabilizer",                                    "No.",  32500.00, 21, "Three-phase"),
    ("Grand Pacific Limited", "avr", "60 kVA Three-Phase Servo AVR",      "Safenergy", "AVR-60K-3P-S",  "60 kVA three-phase servo voltage stabilizer",                                    "No.",  56500.00, 21, "Three-phase"),
    ("Grand Pacific Limited", "avr", "100 kVA Three-Phase Servo AVR",     "Safenergy", "AVR-100K-3P-S", "100 kVA three-phase servo voltage stabilizer",                                   "No.",  88500.00, 30, "Three-phase"),
    ("Grand Pacific Limited", "avr", "150 kVA Three-Phase Servo AVR",     "Safenergy", "AVR-150K-3P-S", "150 kVA three-phase servo voltage stabilizer",                                   "No., ",128500.00, 30, "Three-phase"),
    ("Grand Pacific Limited", "avr", "200 kVA Three-Phase Servo AVR",     "Safenergy", "AVR-200K-3P-S", "200 kVA three-phase servo voltage stabilizer",                                   "No.", 168500.00, 45, "Three-phase"),
    ("Grand Pacific Limited", "avr", "300 kVA Three-Phase Servo AVR",     "Safenergy", "AVR-300K-3P-S", "300 kVA three-phase servo voltage stabilizer, industrial floor-mount",           "No.", 245000.00, 45, "Three-phase"),
    ("Grand Pacific Limited", "avr", "500 kVA Three-Phase Servo AVR",     "Safenergy", "AVR-500K-3P-S", "500 kVA three-phase servo voltage stabilizer",                                   "No.", 385000.00, 60, "Three-phase"),
    ("Grand Pacific Limited", "avr", "1000 kVA Three-Phase Servo AVR",    "Safenergy", "AVR-1000K-3P-S","1000 kVA three-phase servo voltage stabilizer, industrial",                     "No.", 725000.00, 75, "Three-phase"),
    ("Grand Pacific Limited", "avr", "1500 kVA Three-Phase Servo AVR",    "Safenergy", "AVR-1500K-3P-S","1500 kVA three-phase servo voltage stabilizer, industrial",                     "No.",1085000.00, 90, "Three-phase"),

    # ---- AVR: Static / Industrial alternates ----
    ("NESSTRA Ghana Ltd", "avr", "10 kVA Static AVR (single-phase)",      "Schneider", "AVR-10K-STC",   "Static AVR with bypass arrangement, 1-cycle response", "No.",  9850.00, 21, "Static"),
    ("NESSTRA Ghana Ltd", "avr", "50 kVA Static AVR (three-phase)",       "Schneider", "AVR-50K-STC-3P","Static AVR three-phase, fast electronic switching",    "No.", 38500.00, 30, "Static"),
    ("NESSTRA Ghana Ltd", "avr", "Industrial AVR 200 kVA (3P)",           "ABB",       "AVR-IND-200",   "Industrial three-phase AVR 200kVA",                    "No.",185000.00, 45, "Industrial"),

    # ---- UPS top-up: extra Safenergy three-phase sizes ----
    ("Grand Pacific Limited", "power_system", "2 kVA Online UPS (single-phase)",  "Safenergy",  "S1-2K",   "2 kVA online UPS, single-phase, 30min runtime",  "No.",   7250.00, 14, "UPS"),
    ("Grand Pacific Limited", "power_system", "6 kVA Online UPS (single-phase)",  "Safenergy",  "S1-6K",   "6 kVA online UPS, single-phase",                  "No.",  22500.00, 14, "UPS"),
    ("Grand Pacific Limited", "power_system", "15 kVA Online UPS (three-phase)",  "Safenergy",  "S3-15K",  "15 kVA online UPS, three-phase",                  "No.", 105000.00, 21, "UPS"),
    ("Grand Pacific Limited", "power_system", "40 kVA Online UPS (three-phase)",  "Safenergy",  "S3-40K",  "40 kVA online UPS, three-phase",                  "No.", 235000.00, 21, "UPS"),
    ("Grand Pacific Limited", "power_system", "50 kVA Online UPS (three-phase)",  "Safenergy",  "S3-50K",  "50 kVA online UPS, three-phase",                  "No.", 285000.00, 21, "UPS"),
    ("Grand Pacific Limited", "power_system", "120 kVA Online UPS (three-phase)", "Safenergy",  "S3-120K", "120 kVA online UPS, three-phase",                 "No.", 495000.00, 45, "UPS"),
    ("Grand Pacific Limited", "power_system", "160 kVA Online UPS (three-phase)", "Safenergy",  "S3-160K", "160 kVA online UPS, three-phase",                 "No.", 625000.00, 45, "UPS"),
    ("Grand Pacific Limited", "power_system", "300 kVA Online UPS (three-phase)", "Safenergy",  "S3-300K", "300 kVA online UPS, three-phase, industrial",     "No.",1125000.00, 60, "UPS"),
    ("Grand Pacific Limited", "power_system", "500 kVA Online UPS (three-phase)", "Safenergy",  "S3-500K", "500 kVA online UPS, three-phase, industrial",     "No.",1825000.00, 75, "UPS"),

    # ---- UPS top-up: alternate brands ----
    ("JMG Offshore Ghana", "power_system", "10 kVA APC Smart-UPS On-Line (3P)",    "APC",     "SRT10KXLI",   "APC Smart-UPS On-Line SRT 10kVA, three-phase",         "No.", 165000.00, 21, "UPS"),
    ("JMG Offshore Ghana", "power_system", "20 kVA APC Smart-UPS On-Line (3P)",    "APC",     "SRT20KXLI",   "APC Smart-UPS On-Line SRT 20kVA, three-phase",         "No.", 285000.00, 21, "UPS"),
    ("JMG Offshore Ghana", "power_system", "40 kVA Eaton 93PS UPS (3P)",            "Eaton",   "93PS-40",     "Eaton 93PS 40kVA three-phase UPS, modular",            "No.", 425000.00, 30, "UPS"),
    ("JMG Offshore Ghana", "power_system", "80 kVA Eaton 93PR UPS (3P)",            "Eaton",   "93PR-80",     "Eaton 93PR 80kVA three-phase UPS, fault-tolerant",     "No.", 685000.00, 45, "UPS"),
    ("JMG Offshore Ghana", "power_system", "100 kVA Vertiv Liebert UPS (3P)",       "Vertiv",  "LBT-100",     "Vertiv Liebert APM 100kVA three-phase UPS",            "No.", 825000.00, 45, "UPS"),
    ("JMG Offshore Ghana", "power_system", "200 kVA Vertiv Liebert UPS (3P)",       "Vertiv",  "LBT-200",     "Vertiv Liebert APM 200kVA three-phase UPS",            "No.",1485000.00, 60, "UPS"),
    ("JMG Offshore Ghana", "power_system", "100 kVA Huawei UPS5000-E (3P)",         "Huawei",  "UPS5000-100", "Huawei UPS5000-E 100kVA modular three-phase UPS",       "No.", 765000.00, 45, "UPS"),
    ("JMG Offshore Ghana", "power_system", "200 kVA Huawei UPS5000-E (3P)",         "Huawei",  "UPS5000-200", "Huawei UPS5000-E 200kVA modular three-phase UPS",       "No.",1325000.00, 60, "UPS"),

    # ---- UPS: line-interactive + rack-mount (data-centre + office) ----
    ("Comsys Ghana Ltd.", "power_system", "1 kVA Line-Interactive UPS (tower)",  "APC",     "SUA1000I",     "APC Smart-UPS 1000VA line-interactive tower UPS",         "No.",   3850.00, 7,  "UPS"),
    ("Comsys Ghana Ltd.", "power_system", "2 kVA Line-Interactive UPS (tower)",  "APC",     "SUA2200I",     "APC Smart-UPS 2200VA line-interactive tower UPS",         "No.",   8250.00, 7,  "UPS"),
    ("Comsys Ghana Ltd.", "power_system", "1.5 kVA Rack-Mount UPS (2U)",          "APC",     "SMT1500RMI",   "APC Smart-UPS 1500VA 2U rack-mount",                       "No.",   6250.00, 7,  "UPS"),
    ("Comsys Ghana Ltd.", "power_system", "3 kVA Rack-Mount UPS (2U)",            "APC",     "SMT3000RMI",   "APC Smart-UPS 3000VA 2U rack-mount",                       "No.",  11500.00, 14, "UPS"),
    ("Comsys Ghana Ltd.", "power_system", "10 kVA Rack-Mount UPS (6U)",           "Eaton",   "9PX10KIRT",    "Eaton 9PX 10kVA 6U rack/tower online UPS",                 "No.",  78500.00, 21, "UPS"),
    ("Comsys Ghana Ltd.", "power_system", "External Battery Cabinet (96V, 60Ah)", "APC",     "BATCAB-96V",   "External battery cabinet for extended runtime, 96V 60Ah",  "No.",  18500.00, 14, "UPS"),
    ("Comsys Ghana Ltd.", "power_system", "Maintenance Bypass Switch (40A)",      "APC",     "MBP-40A",      "Maintenance bypass switch 40A for UPS hot-swap servicing", "No.",   8750.00, 14, "UPS"),
]


# Additional brand names from the doc that aren't yet in _MARKETPLACE_BRANDS.
_LIBRARY_EXPANSION_BRANDS = [
    "Marshall-Tufflex", "Adaptaflex", "Gewiss", "Niedax", "Unistrut",
    "Furse", "DEHN", "AN Wallis", "LPI", "Schletter", "Clenergy", "K2 Systems",
    "Felicity Solar", "GoodWe", "Trina", "Canadian Solar", "Q CELLS",
    "Solis", "Sungrow", "Sungrow",  # alias-safe
    "Hikvision", "Dahua", "Axis", "Uniview", "Aruba", "TP-Link Omada",
    "Yealink", "Grandstream", "3CX", "Yeastar", "ZKTeco", "Suprema", "HID",
    "YLI", "Assa Abloy", "Honeywell", "Schneider EcoStruxure", "Siemens Desigo",
    "Johnson Controls", "Theben", "Phoenix Contact", "Socomec", "Janitza",
    "Lovato", "Vertiv", "Eaton", "Akuvox", "2N", "Seagate", "WD",
    "Steinel", "Kamstrup", "Sensus", "Advantech", "Teltonika", "Milesight",
    "Kerlink", "Dragino", "Kontakt.io", "Minew", "Estimote", "Airthings",
    "Aqara Pro", "Belden", "Lapp", "Staubli", "Amphenol", "Suntree",
    "Schreder", "Thorn", "Tropical Cable", "Prysmian", "Nexans",
]


def _seed_library_expansion():
    """Idempotent additive seed. Skip-if-exists at supplier + product level."""
    try:
        with get_db() as c:
            # ----- suppliers -----
            existing = {}
            try:
                for r in c.execute("SELECT id, LOWER(TRIM(name)) AS n FROM suppliers").fetchall():
                    existing[r["n"] if hasattr(r, "keys") else r[1]] = r["id"] if hasattr(r, "keys") else r[0]
            except Exception:
                pass
            for (name, country, contact, phone, email, website, address, categories) in _LIBRARY_EXPANSION_SUPPLIERS:
                if name.lower().strip() in existing:
                    continue
                try:
                    c.execute(
                        "INSERT INTO suppliers (name,country,contact_name,phone,email,website,address,"
                        "categories,lead_time_days,payment_terms,rating,user_id,is_verified,is_active) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (name, country, contact, phone, email, website, address,
                         categories, 30, "TT 30 days", 5, 0, 1, 1),
                    )
                except Exception:
                    pass

            # ----- brands -----
            is_pg = bool(os.environ.get("DATABASE_URL"))
            for brand in _LIBRARY_EXPANSION_BRANDS:
                try:
                    if is_pg:
                        c.execute(
                            "INSERT INTO product_brands (name, is_active) VALUES (?, 1) "
                            "ON CONFLICT (name) DO NOTHING",
                            (brand,),
                        )
                    else:
                        c.execute(
                            "INSERT OR IGNORE INTO product_brands (name, is_active) VALUES (?, 1)",
                            (brand,),
                        )
                except Exception:
                    pass

            # ----- products -----
            sup_index = {}
            try:
                for r in c.execute("SELECT id, name FROM suppliers WHERE is_active=1").fetchall():
                    sup_index[(r["name"] if hasattr(r, "keys") else r[1]).strip()] = (r["id"] if hasattr(r, "keys") else r[0])
            except Exception:
                pass
            cat_index = {}
            try:
                for r in c.execute("SELECT id, code FROM product_categories WHERE is_active=1").fetchall():
                    cat_index[r["code"] if hasattr(r, "keys") else r[1]] = r["id"] if hasattr(r, "keys") else r[0]
            except Exception:
                pass
            try:
                _ghs_per_usd = float(_CURRENCY_RATES_FROM_USD.get("GHS", 14.5) or 14.5)
            except Exception:
                _ghs_per_usd = 14.5

            for (sup_name, cat_code, name, brand, model, spec, unit, price_ghs, lead, subcategory) in _LIBRARY_EXPANSION_PRODUCTS_GHS:
                sid = sup_index.get(sup_name, 0)
                cid = cat_index.get(cat_code, 0)
                if not sid or not cid:
                    continue
                try:
                    dupe = c.execute(
                        "SELECT id FROM equipment_catalog "
                        "WHERE name=? AND COALESCE(brand,'')=? AND supplier_id=? AND is_active=1",
                        (name, brand or "", sid),
                    ).fetchone()
                    if dupe:
                        continue
                except Exception:
                    pass
                price_usd = round(float(price_ghs) / _ghs_per_usd, 2)
                try:
                    c.execute(
                        "INSERT INTO equipment_catalog "
                        "(category,category_id,subcategory,name,brand,model,spec,unit,price_usd,"
                        " supplier_id,lead_time_days,is_active,is_verified,is_public_visible) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (cat_code, cid, subcategory, name, brand, model, spec, unit, price_usd,
                         sid, lead, 1, 1, 1),
                    )
                except Exception:
                    pass
    except Exception as _e:
        try: app.logger.warning("_seed_library_expansion failed: %s", _e)
        except Exception: pass


@app.route("/admin/marketplace/reseed-library", methods=["POST"])
@admin_required
def admin_marketplace_reseed_library():
    """One-shot reseed of the expanded library (suppliers + products + brands)."""
    csrf_protect()
    _ensure_marketplace_tables()
    _seed_library_expansion()
    try: _log_marketplace_action("reseed_library_expansion", "system", 0,
                                 "manual re-fire of update liberary.txt seed")
    except Exception: pass
    flash("Library expansion re-seeded (idempotent).", "success")
    return redirect(url_for("admin_marketplace_dashboard"))


# === END: library_expansion splice ===
