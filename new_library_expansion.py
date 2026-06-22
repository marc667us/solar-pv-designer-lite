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
    ("Powertech Generators Ghana Limited", "power_system", "100 kVA Diesel Generator (Silent)", "Perkins",  "GEN-100-S",  "100 kVA silent diesel generator with ATS panel",   "No.", 132500.00, 60, "Generators"),
    ("Powertech Generators Ghana Limited", "power_system", "250 kVA Diesel Generator (Silent)", "FG Wilson","GEN-250-S",  "250 kVA silent diesel generator with ATS panel",   "No.", 265000.00, 60, "Generators"),
    ("Powertech Generators Ghana Limited", "power_system", "500 kVA Diesel Generator (Silent)", "Cummins",  "GEN-500-S",  "500 kVA silent diesel generator with ATS panel",   "No.", 625000.00, 75, "Generators"),
    ("Powertech Generators Ghana Limited", "power_system", "1000 kVA Diesel Generator (Silent)","Caterpillar","GEN-1000-S","1000 kVA silent diesel generator with ATS panel", "No.",1700000.00, 90, "Generators"),

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
