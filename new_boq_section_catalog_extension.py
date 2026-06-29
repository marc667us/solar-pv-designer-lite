# new_boq_section_catalog_extension.py
# 2026-06-29: extend _BOQ_SECTION_ITEM_CATALOG with the 80+ section titles
# the v2/v3/v4 catalogs missed -- everything that Complete BOQ Generate
# pulls from for non-Internal-Electrical services (Fire Alarm, Lightning,
# Equipotential, LV/Power, LAN, IT Server Room, VoIP, PA, IP CCTV, TV,
# IP Clock, Nurse Call, Medical Equipment, BMS, plus the missing
# Internal Electrical sections: Preliminaries, T&C, Documentation).
#
# Pattern: mutate the existing dict in place after it has been built.
# Mirrors how data_v3 and data_v4 work.
#
# Prices are in Ghana Cedis (GHS) -- the platform's primary currency.
# Owner overrides them per project via the per-row Basic Price input.


_NEW_CATALOG_ENTRIES = {

    # ===================================================================
    # INTERNAL ELECTRICAL -- missing sections
    # ===================================================================
    "PRELIMINARIES": [
        ("Site mobilisation and demobilisation",                              "Lot",   25000),
        ("Site supervision and project management (per month)",               "Mth",    8500),
        ("Site engineer presence on site (per month)",                        "Mth",    7000),
        ("Site insurance and bonds",                                           "Lot",   15000),
        ("Health and safety provisions + PPE allowance",                       "Lot",    6500),
        ("Site office accommodation (per month)",                              "Mth",    3500),
        ("Tools and small plant allowance",                                    "Lot",    4500),
        ("Permits, certificates and statutory notices",                        "Item",   3500),
        ("Testing instruments allowance",                                      "Lot",    5500),
        ("Final commissioning and handover",                                   "Lot",    8000),
    ],

    "SUB-FEEDER CABLES AND EARTH LEADS": [
        ("4c x 50mm² Cu/XLPE/SWA/PVC sub-feeder cable",                       "M",       651),
        ("4c x 35mm² Cu/XLPE/SWA/PVC sub-feeder cable",                       "M",       470),
        ("4c x 25mm² Cu/XLPE/SWA/PVC sub-feeder cable",                       "M",       290),
        ("4c x 16mm² Cu/XLPE/SWA/PVC sub-feeder cable",                       "M",       190),
        ("4c x 10mm² Cu/XLPE/SWA/PVC sub-feeder cable",                       "M",       125),
        ("1c x 25mm² PVC copper earth lead",                                  "M",        65),
        ("1c x 16mm² PVC copper earth lead",                                  "M",        42),
        ("1c x 10mm² PVC copper earth lead",                                  "M",        27),
        ("Cable gland and lug kit (per cable size)",                          "Set",     180),
        ("Cable cleat (per metre)",                                            "M",        45),
    ],

    "TESTING AND COMMISSIONING": [
        ("Insulation resistance test (per circuit)",                          "Item",     85),
        ("Earth loop impedance test",                                          "Item",     85),
        ("RCD operation test",                                                 "Item",     85),
        ("Phase rotation + continuity test",                                   "Item",    120),
        ("Polarity verification",                                              "Item",     65),
        ("Final functional test sweep",                                        "Item",    250),
        ("Test certificates + Schedule of Test Results (BS 7671)",             "Set",     650),
        ("Witnessed energisation",                                             "Item",    850),
    ],

    "DOCUMENTATION AND HANDOVER": [
        ("As-built drawings (PDF + DWG)",                                      "Set",    2500),
        ("Operation and Maintenance (O&M) manual",                             "Set",    1800),
        ("Test certificates pack",                                              "Set",     650),
        ("Training to client maintenance staff (per day)",                     "Day",    1500),
        ("Spares list and recommended spares",                                  "Item",    450),
        ("Asset register + barcoding",                                          "Lot",    1500),
    ],

    # ===================================================================
    # FIRE ALARM SYSTEM
    # ===================================================================
    "FIRE DETECTION AND ALARM SYSTEM": [
        ("Addressable Fire Alarm Control Panel (2-loop, EN 54-2/4)",          "No.",   25000),
        ("Addressable Fire Alarm Control Panel (4-loop)",                      "No.",   38000),
        ("Optical smoke detector (addressable, EN 54-7)",                      "No.",     320),
        ("Heat detector A2S (addressable, EN 54-5)",                           "No.",     280),
        ("Multi-sensor detector (heat + smoke)",                                "No.",     420),
        ("Manual Call Point break-glass (addressable, EN 54-11)",              "No.",     250),
        ("Sounder + strobe wall-mount (100dB, EN 54-3/23)",                    "No.",     480),
        ("Voice alarm sounder (EN 54-24)",                                      "No.",     580),
        ("Door retainer 24Vdc (EN 1155)",                                       "No.",     320),
        ("Interface module (addressable input/output)",                         "No.",     650),
    ],

    "FIRE ALARM CABLING": [
        ("Fire-resistant cable 1.5mm² 2C (FP200, BS EN 50200 PH120)",         "M",        18),
        ("Fire-resistant cable 2.5mm² 2C (FP200) for sounder circuits",       "M",        24),
        ("Fire-resistant containment (LSF tray + clips, red colour-coded)",   "M",        45),
        ("Red colour-coded conduit 20mm (LSF, fire-rated)",                   "M",        22),
        ("Junction box for fire-alarm circuit (red, surface)",                 "No.",      85),
        ("Fire-rated cable gland (per size)",                                  "No.",      35),
    ],

    "FIRE ALARM ACCESSORIES": [
        ("Battery backup 24Vdc sealed lead-acid (24hr standby + 30min alarm)", "Set",    2800),
        ("Magnetic door retainer (24Vdc)",                                      "No.",     320),
        ("Door release button (manual + auto)",                                 "No.",     180),
        ("Beacon + strobe (visual-only)",                                       "No.",     250),
        ("Remote indicator LED",                                                "No.",      85),
        ("FACP printer + paper roll",                                            "Set",    2500),
    ],

    # ===================================================================
    # EQUIPOTENTIAL BONDING SYSTEM
    # ===================================================================
    "EQUIPOTENTIAL BONDING": [
        ("Bonding to incoming water service (clamp + 10mm² conductor)",        "No.",     220),
        ("Bonding to incoming gas service (clamp + 10mm² conductor)",          "No.",     220),
        ("Bonding to structural steel (16mm² conductor + lug)",                "No.",     180),
        ("Supplementary bonding wet area (per IEE 415.2)",                     "Lot",    1200),
        ("Bonding to cable tray (16mm² jumper)",                                "No.",      85),
        ("Bonding to lift / hoist motor frame",                                 "No.",     150),
    ],

    "EARTH BARS AND EARTH LEADS": [
        ("Sub-earth bar (drilled copper, 6-way, wall-mounted)",                "No.",     680),
        ("Main earth bar (drilled copper, 12-way, lockable enclosure)",        "No.",    1450),
        ("70mm² PVC earth conductor (green/yellow)",                            "M",        95),
        ("50mm² PVC earth conductor (green/yellow)",                            "M",        70),
        ("35mm² PVC earth conductor (green/yellow)",                            "M",        48),
        ("16mm² PVC earth conductor (green/yellow)",                            "M",        25),
        ("Compression cable lug (per size)",                                    "No.",      18),
    ],

    # ===================================================================
    # LIGHTNING PROTECTION SYSTEM
    # ===================================================================
    "LIGHTNING PROTECTION": [
        ("Risk assessment per IEC 62305-2",                                     "Item",   2500),
        ("Rolling sphere design package + drawing pack",                         "Set",    3500),
        ("Witness inspection + LPS certificate",                                 "Item",   1800),
    ],

    "AIR TERMINALS": [
        ("Copper air-terminal rod 1m x 16mm dia (BS EN 62305)",                "No.",     450),
        ("Copper air-terminal rod 1.5m x 16mm dia",                            "No.",     580),
        ("Air-terminal base + insulating pad",                                  "No.",     220),
        ("Roof saddle / mounting bracket",                                       "No.",     180),
    ],

    "DOWN CONDUCTORS": [
        ("25 x 3mm hard-drawn copper tape (BS EN 50164-2)",                    "M",        42),
        ("20 x 3mm copper tape",                                                 "M",        35),
        ("Round 8mm copper down conductor",                                      "M",        28),
        ("Roof + wall tape clip (per type)",                                     "No.",      12),
        ("DC tape connector",                                                    "No.",      55),
    ],

    "TEST CLAMPS": [
        ("Test clamp (bolted disconnect, brass) accessible at 2.0m AGL",       "No.",     180),
        ("Inspection cover for test clamp",                                     "No.",      85),
    ],

    "EARTH ELECTRODES": [
        ("Copper-bonded earth rod 1.5m x 16mm dia (BS 7430)",                  "No.",     280),
        ("Copper-bonded earth rod 2.4m x 16mm dia",                             "No.",     420),
        ("Inspection pit + lid + clamp",                                         "No.",     650),
        ("Bentonite earth-enhancing compound (25kg bag)",                       "Bag",     320),
        ("Exothermic-weld kit (per joint)",                                      "Item",    250),
    ],

    # ===================================================================
    # POWER SUPPLY, LV DISTRIBUTION AND EXTERNAL LIGHTING
    # ===================================================================
    "TRANSFORMERS": [
        ("Distribution transformer 250kVA, 11kV/415V, oil-immersed ONAN",      "No.",  185000),
        ("Distribution transformer 500kVA, 11kV/415V, oil-immersed ONAN",      "No.",  285000),
        ("Distribution transformer 1000kVA, 11kV/415V, oil-immersed ONAN",     "No.",  450000),
        ("Transformer civil plinth + bund wall",                                "Item",  18500),
        ("Transformer oil + electrical tests (BDV/DGA/IR)",                    "Item",   4500),
    ],

    "RMU": [
        ("11kV Ring Main Unit (2-way + Tee-off, SF6, IEC 62271)",              "No.",  185000),
        ("11kV Ring Main Unit (3-way switch + 1 fuse)",                         "No.",  220000),
        ("RMU foundation + cable trench",                                        "Item",  12500),
    ],

    "AVR": [
        ("AVR (servo-motor type, 415V, 100kVA)",                                "No.",   25000),
        ("AVR (servo-motor type, 415V, 200kVA)",                                "No.",   42000),
        ("AVR (servo-motor type, 415V, 400kVA)",                                "No.",   72000),
    ],

    "MAIN LV SWITCHBOARDS": [
        ("Main LV switchboard (form 4b, IP54, ACB incomer)",                   "No.",   85000),
        ("Capacitor bank PFC automatic (50kVAr)",                               "No.",   28000),
        ("Capacitor bank PFC automatic (100kVAr)",                              "No.",   45000),
        ("MCCB 400A, 4P, 50kA",                                                  "No.",    4500),
        ("MCCB 250A, 4P, 36kA",                                                  "No.",    2800),
        ("MCCB 100A, 4P, 25kA",                                                  "No.",    1200),
    ],

    "PANEL BOARDS": [
        ("Sub-main panel board TPN 250A, MCCB outgoing",                        "No.",   12500),
        ("Sub-main panel board TPN 400A, MCCB outgoing",                        "No.",   18500),
        ("Floor-level panel board, MCB outgoing, 18 way",                       "No.",    4500),
    ],

    "EXTERNAL LIGHTING": [
        ("9m steel street-light pole (hot-dip galvanised) + LED head 60W",     "No.",    3200),
        ("9m steel street-light pole + LED head 100W",                          "No.",    3800),
        ("6m steel pole + LED head 40W",                                        "No.",    2200),
        ("Bollard light LED 12W (IK10, vandal-resistant)",                     "No.",     450),
        ("LED floodlight 100W (IP66)",                                          "No.",     680),
        ("LED floodlight 200W (IP66)",                                          "No.",    1200),
        ("Photocell + contactor control panel (32A, dusk-to-dawn)",            "No.",    1850),
        ("Pole junction box (IP66)",                                            "No.",     220),
        ("Underground feed cable to poles (4C x 6mm² Cu/XLPE/SWA)",            "M",        65),
    ],

    "EARTHING GRID": [
        ("Bare copper earth tape 25 x 3mm (buried, exothermic-welded)",        "M",        45),
        ("Bare copper earth tape 20 x 3mm",                                     "M",        38),
        ("Copper-bonded earth electrode 2.4m x 16mm",                           "No.",     420),
        ("Earth electrode 1.5m x 16mm",                                          "No.",     280),
        ("Exothermic-weld joint kit",                                            "Item",    250),
        ("Inspection pit + concrete chamber",                                    "No.",     680),
    ],

    "CABLE TRENCHES": [
        ("Excavation + backfill cable trench 450 x 800mm (sand bed + tile)",   "M",       180),
        ("Excavation + backfill cable trench 600 x 1000mm",                    "M",       240),
        ("Concrete cable duct uPVC 100mm (Class 1)",                            "M",        85),
        ("Concrete cable duct uPVC 150mm",                                       "M",       120),
        ("Cable warning tape (yellow)",                                          "M",         8),
        ("Pulling rope + draw cord per duct",                                    "M",        12),
    ],

    # ===================================================================
    # LAN / WLAN
    # ===================================================================
    "DATA AND VOICE COMMUNICATION": [
        ("Cat6 RJ45 voice/data outlet, single-gang (T568B)",                   "No.",      45),
        ("Cat6 RJ45 voice/data outlet, double-gang (T568B)",                   "No.",      75),
        ("RJ11 voice-only outlet",                                              "No.",      28),
        ("Cat6A shielded outlet",                                                "No.",      85),
        ("Faceplate single-gang white moulded",                                  "No.",      18),
    ],

    "STRUCTURED CABLING": [
        ("Cat6 UTP horizontal cable 305m roll (blue)",                          "Roll",   1200),
        ("Cat6 UTP horizontal cable 305m roll (yellow)",                        "Roll",   1200),
        ("Cat6A F/UTP shielded cable 305m roll",                                "Roll",   2200),
        ("Cat6 patch panel 24-port (1U loaded)",                                "No.",     650),
        ("Cat6 patch panel 48-port (2U loaded)",                                "No.",    1200),
        ("Cat6 patch lead 1m (snagless)",                                        "No.",      18),
        ("Cat6 patch lead 2m (snagless)",                                        "No.",      28),
        ("Cat6 patch lead 3m (snagless)",                                        "No.",      35),
        ("Fibre patch cord LC-LC duplex OM3 (3m)",                              "No.",      85),
    ],

    "NETWORK CABINETS": [
        ("24U floor-standing data cabinet 600x800 (glass front, lockable)",    "No.",    6500),
        ("42U floor-standing server cabinet 600x1000 (perforated doors)",      "No.",    8500),
        ("12U wall-mounted data cabinet 600x500",                                "No.",    2800),
        ("9U wall-mounted data cabinet 600x450",                                 "No.",    2200),
        ("Vertical cable manager (per rack)",                                    "No.",     450),
        ("Horizontal cable manager 1U",                                          "No.",     180),
        ("Cabinet cooling fan kit (4-fan)",                                      "Set",     650),
        ("PDU 8-way IEC + UK (rack-mount)",                                      "No.",     480),
    ],

    "WIRELESS ACCESS POINTS": [
        ("WiFi 6 Access Point PoE+ (2x2 MIMO, 802.11ax indoor)",               "No.",    2200),
        ("WiFi 6 Access Point PoE+ (4x4 MIMO, indoor)",                         "No.",    3800),
        ("WiFi 6 Access Point outdoor IP67 PoE+ (mesh-capable)",                "No.",    4500),
        ("Wireless controller (cloud-managed)",                                  "No.",    5500),
        ("AP mounting bracket + ceiling fixings",                                "No.",     180),
    ],

    "TESTING AND CERTIFICATION": [
        ("Cat6 channel certification (per outlet, Fluke / Wirexpert)",          "No.",      45),
        ("Cat6A channel certification",                                          "No.",      65),
        ("Fibre OTDR test (per link)",                                            "No.",     180),
        ("Wireless site survey + heatmap report",                                "Item",   3500),
        ("Network commissioning + handover documentation",                       "Item",   2500),
    ],

    # ===================================================================
    # IT SERVER ROOM
    # ===================================================================
    "IT SERVER ROOM POWER": [
        ("Server-room sub-DB TPN 63A 12-way",                                   "No.",    5800),
        ("Server-room sub-DB TPN 100A 18-way",                                  "No.",    8500),
        ("Critical-load distribution feed from essential bus",                  "Item",   4500),
        ("Single-phase isolator 32A (per rack)",                                "No.",     280),
        ("Three-phase isolator 63A",                                             "No.",     580),
    ],

    "UPS": [
        ("Online double-conversion UPS 6kVA (rack-mount, 30min runtime)",       "No.",   28000),
        ("Online double-conversion UPS 10kVA",                                   "No.",   42000),
        ("Online double-conversion UPS 20kVA",                                   "No.",   68000),
        ("Extended battery cabinet (sealed VRLA, hot-swap)",                    "No.",   18500),
        ("Maintenance bypass switch (manual, make-before-break)",                "No.",    8500),
        ("UPS commissioning + load + autonomy test",                            "Item",   4500),
    ],

    "SERVER RACKS": [
        ("42U server rack 600x1000 (perforated doors, baying kit)",             "No.",    8500),
        ("47U server rack 800x1100",                                             "No.",   12500),
        ("Vertical cable manager + 0U PDU (switched, monitored)",               "Set",    3800),
        ("Heavy-duty shelf (deep, lockable)",                                    "No.",     680),
        ("Cable tray + ladder above rack row",                                    "M",       450),
    ],

    "DATA CABINETS": [
        ("24U data cabinet (network row, glass front, lockable)",                "No.",    6800),
        ("Fibre patch panel LC duplex 24-port (OS2 single-mode)",                "No.",    1850),
        ("MPO patch panel 12-port (MPO to LC breakout)",                         "No.",    2800),
        ("Patch cord guide (per cabinet)",                                       "No.",     220),
    ],

    "EARTHING AND BONDING": [
        ("Computer-room earth grid mesh (TIA-942)",                              "Lot",   12500),
        ("Rack-bonding kit per cabinet (16mm² conductor + lug)",                "No.",     280),
        ("Equipotential bonding bar (clean earth)",                              "No.",     680),
        ("16mm² PVC earth conductor (green/yellow)",                              "M",        25),
    ],

    "ENVIRONMENTAL MONITORING": [
        ("Temperature + humidity sensor (SNMP, email / SMS alerting)",          "No.",    1850),
        ("Leak-detection rope sensor (under raised floor, per metre)",          "M",        85),
        ("Smoke + heat early-warning detection (VESDA aspirating)",             "No.",   18500),
        ("Door-open contact (rack security)",                                    "No.",     180),
        ("UPS SNMP card / network monitoring",                                   "No.",    1200),
    ],

    # ===================================================================
    # VOIP SYSTEM
    # ===================================================================
    "VOIP SYSTEM": [
        ("IP-PBX server appliance (50 extension licence pack)",                 "No.",   38000),
        ("IP-PBX server appliance (100 extension licence pack)",                "No.",   58000),
        ("SIP trunk licence (per concurrent channel, annual)",                  "Channel", 850),
        ("IVR / auto-attendant module",                                          "Item",   3500),
        ("Voicemail server module",                                              "Item",   4500),
    ],

    "IP PHONES": [
        ("IP desk phone entry, monochrome, PoE, HD voice",                       "No.",     580),
        ("IP desk phone executive, colour, Gigabit, PoE, BLF keys",              "No.",    1850),
        ("IP conference phone (omnidirectional, PoE)",                           "No.",    2500),
        ("DECT base station (multi-cell)",                                       "No.",    2800),
        ("DECT handset",                                                          "No.",     680),
    ],

    "VOICE GATEWAY": [
        ("Analog-to-VoIP gateway FXS (8-port, for fax / analog lines)",         "No.",    2800),
        ("Analog-to-VoIP gateway FXO (8-port, for legacy PSTN)",                "No.",    3200),
        ("E1 / PRI gateway (30-channel)",                                        "No.",    9500),
        ("SBC session border controller (entry)",                                 "No.",   12500),
    ],

    "NETWORK SWITCHES": [
        ("24-port PoE+ access switch Gigabit (L2, 370W PoE budget)",            "No.",    8500),
        ("48-port PoE+ access switch Gigabit (L2, 740W PoE budget)",            "No.",   18500),
        ("24-port non-PoE Gigabit access switch",                                 "No.",    3200),
        ("10G core switch 24-port SFP+ (L3)",                                     "No.",   28000),
        ("10G uplink module SFP+ (multimode)",                                    "No.",    1850),
        ("1G uplink module SFP (single-mode)",                                    "No.",    1200),
    ],

    "DATA OUTLETS": [
        ("Cat6 RJ45 voice outlet single-gang (T568B)",                          "No.",      45),
        ("Cat6 RJ45 voice outlet double-gang",                                   "No.",      75),
        ("Floor box with Cat6 + power outlets",                                  "No.",    1850),
    ],

    # ===================================================================
    # PUBLIC ADDRESS SYSTEM
    # ===================================================================
    "PUBLIC ADDRESS SYSTEM": [
        ("PA controller + zone-paging server (EN 54-16)",                       "No.",   28000),
        ("PA digital matrix (8 zones)",                                          "No.",   18500),
        ("PA emergency evacuation system (VA, EN 54-16/24)",                    "No.",   45000),
    ],

    "AMPLIFIERS": [
        ("PA amplifier 120W (100V line, zone-output, EN 54-16)",                "No.",    4500),
        ("PA amplifier 240W (100V line, EN 54-16)",                              "No.",    7500),
        ("PA amplifier 480W (100V line)",                                        "No.",   12500),
        ("Standby / hot-swap amplifier (redundancy)",                            "No.",    4500),
    ],

    "SPEAKERS": [
        ("Ceiling speaker 6W (100V, fire-rated dome)",                          "No.",     180),
        ("Ceiling speaker 12W (100V)",                                           "No.",     250),
        ("Wall-mount cabinet speaker 10W (100V, EN 54-24)",                     "No.",     320),
        ("Wall-mount cabinet speaker 20W (100V)",                                "No.",     480),
        ("Horn speaker 30W (100V, outdoor IP66, EN 54-24)",                     "No.",     850),
        ("Column speaker 60W (100V)",                                            "No.",    1450),
    ],

    "MICROPHONE POINTS": [
        ("Desktop paging microphone PTT (zone-select keypad)",                  "No.",    1450),
        ("Emergency / all-call microphone (lockable, EN 54-16)",                "No.",    2800),
        ("Wall-mount paging point",                                              "No.",     680),
    ],

    "PA CABLING": [
        ("100V line speaker cable 1.5mm² 2C (fire-rated for EVAC)",             "M",        18),
        ("100V line speaker cable 2.5mm² 2C",                                    "M",        28),
        ("PA containment LSF tray + clips",                                       "M",        45),
        ("Junction box for PA speakers (IP54)",                                  "No.",      85),
    ],

    # ===================================================================
    # IP CCTV NETWORK
    # ===================================================================
    "IP CCTV SYSTEM": [
        ("VMS server (32-camera licence)",                                      "No.",   28000),
        ("VMS server (64-camera licence)",                                       "No.",   45000),
        ("Operator workstation (dual 27\" screen)",                              "No.",    8500),
        ("Video wall display 55\" 4K",                                            "No.",   12500),
    ],

    "CAMERAS": [
        ("5MP IP dome camera (PoE, indoor, H.265, IR 30m)",                     "No.",    1450),
        ("5MP IP bullet camera (PoE, outdoor IP67, H.265, IR 50m)",             "No.",    1850),
        ("8MP PTZ camera (PoE+, 30x zoom, IP67, IR 200m)",                      "No.",   18500),
        ("4K IP turret camera (PoE+, IK10)",                                     "No.",    3200),
        ("Thermal camera (perimeter)",                                            "No.",   45000),
        ("Camera weatherproof housing",                                          "No.",     680),
    ],

    "NVR": [
        ("32-channel NVR + 4TB storage (RAID-5)",                                "No.",   18500),
        ("64-channel NVR + 8TB storage (RAID-5)",                                "No.",   38000),
        ("Storage expansion module 8TB (per 30 days retention)",                "No.",    8500),
        ("NVR commissioning + retention test",                                   "Item",   2500),
    ],

    "POE SWITCHES": [
        ("24-port PoE+ switch Gigabit, 370W (camera-only VLAN)",                "No.",    8500),
        ("16-port PoE+ switch Gigabit, 240W",                                    "No.",    6500),
        ("Industrial PoE+ switch (DIN-rail, outdoor IP30, -40 to 75C)",        "No.",   12500),
    ],

    "CCTV CABLING": [
        ("Cat6 outdoor UV-resistant cable, gel-filled (black jacket)",          "M",        18),
        ("Cat6 indoor cable for camera VLAN (white)",                            "M",        12),
        ("Fibre OM3 multimode patch (long runs > 90m)",                          "M",        35),
        ("Camera junction box (IP66)",                                           "No.",     220),
    ],

    "CAMERA POLES / MOUNTS": [
        ("6m camera pole (hot-dip galvanised, with bracket + power feed)",      "No.",    4500),
        ("4m wall-bracket camera pole",                                           "No.",    1800),
        ("Wall-mount bracket (IP66 junction)",                                   "No.",     320),
        ("Corner mount bracket",                                                  "No.",     280),
    ],

    # ===================================================================
    # TV SYSTEM
    # ===================================================================
    "TV SYSTEM": [
        ("TV head-end controller + IPTV server",                                 "No.",   28000),
        ("STB / set-top box per TV outlet (HD, HDMI out)",                       "No.",     680),
        ("4K STB",                                                                "No.",    1450),
    ],

    "TV OUTLETS": [
        ("F-type TV wall plate single (screened, BS 41003)",                    "No.",      85),
        ("Combined TV + data outlet (1-gang plate)",                            "No.",     150),
        ("Sat F outlet",                                                          "No.",      85),
    ],

    "COAXIAL CABLING": [
        ("RG6 coaxial cable quad-shield (75Ω, BS EN 50117)",                    "M",        18),
        ("RG11 trunk coaxial cable",                                              "M",        32),
        ("F-type compression connector",                                          "No.",      15),
        ("Coax wall plate + faceplate",                                          "No.",      45),
    ],

    "SPLITTERS": [
        ("2-way TV splitter (5-2400 MHz, screened)",                            "No.",      85),
        ("4-way TV splitter (screened)",                                         "No.",     180),
        ("8-way TV splitter (screened)",                                         "No.",     320),
        ("16-way TV splitter (screened, rack-mount)",                            "No.",     680),
    ],

    "ANTENNA / DISH": [
        ("UHF / VHF terrestrial antenna (mast-mounted)",                         "No.",     850),
        ("Satellite dish 1.2m + LNB (Ku-band)",                                  "No.",    1850),
        ("Antenna mast + lightning protection",                                   "Item",   2500),
        ("Roof penetration kit (waterproof)",                                    "No.",     320),
    ],

    # ===================================================================
    # IP CLOCK SYSTEM
    # ===================================================================
    "IP CLOCK SYSTEM": [
        ("NTP time-server (rack-mount, GPS-disciplined, Stratum-1)",            "No.",   12500),
        ("Clock management software (annual licence)",                           "Lot",    3500),
    ],

    "MASTER CLOCK": [
        ("Master clock with PoE output (redundant)",                             "No.",    4500),
        ("GPS antenna + outdoor mount (roof-mounted)",                           "Set",    1850),
    ],

    "IP CLOCKS": [
        ("IP digital wall clock 24cm (PoE, 12/24hr)",                            "No.",    1450),
        ("IP digital wall clock 35cm",                                            "No.",    1850),
        ("IP analogue wall clock (PoE)",                                          "No.",    1850),
        ("IP double-sided clock (corridor)",                                      "No.",    2800),
    ],

    "NETWORK CABLING": [
        ("Cat6 horizontal drop per clock (PoE)",                                  "M",        12),
        ("Surface back-box + bracket",                                            "No.",      85),
    ],

    # ===================================================================
    # NURSE CALL SYSTEM
    # ===================================================================
    "NURSE CALL SYSTEM": [
        ("Nurse call master station + server (BS HTM 08-03 compliant)",         "No.",   28000),
        ("Reporting + audit software (annual licence)",                          "Lot",    4500),
    ],

    "BEDHEAD UNITS": [
        ("Bedhead trunking + nurse-call socket (aluminium, hygiene-rated)",     "M",       850),
        ("Pull-cord call point (en-suite, IP65)",                                "No.",     380),
        ("Bed locator beacon",                                                    "No.",     280),
    ],

    "CALL POINTS": [
        ("Patient handset call point (reassurance LED + reset)",                 "No.",     480),
        ("Staff assist call point (yellow, staff-only)",                         "No.",     420),
        ("Emergency call point cardiac arrest (red, lockable reset)",            "No.",     520),
    ],

    "CORRIDOR INDICATORS": [
        ("Over-door indicator (multi-colour LED) per bay",                      "No.",     480),
        ("Buzzer + audible repeater",                                             "No.",     280),
        ("Zone alarm panel",                                                     "No.",    1200),
    ],

    "STAFF STATION DISPLAY": [
        ("Staff station LCD display (touch panel)",                              "No.",    3500),
        ("DECT pager / mobile handset per staff member",                         "No.",    1850),
        ("Staff station + duty rota integration",                                "Item",   2800),
    ],

    "NURSE CALL CABLING": [
        ("Nurse-call bus cable (manufacturer-approved)",                          "M",        28),
        ("Cat5e cable for IP nurse call",                                          "M",        12),
        ("Containment + back-boxes (per linear metre)",                          "M",        45),
    ],

    # ===================================================================
    # MEDICAL EQUIPMENT ELECTRICAL
    # ===================================================================
    "MEDICAL EQUIPMENT POWER": [
        ("Theatre / ICU sub-DB (medical, IP2X, BS HTM 06-01)",                  "No.",   18500),
        ("Medical-grade socket outlet (clean-power, red colour-coded)",         "No.",     280),
        ("Medical-grade socket outlet (essential, green colour-coded)",          "No.",     280),
        ("Theatre control panel with patient isolation",                          "No.",   28000),
    ],

    "UPS POWER WIRING": [
        ("Centralised medical UPS feed (sized per clinical demand)",            "Item",   8500),
        ("Local UPS feed (per imaging suite)",                                   "Item",   4500),
        ("Critical-load isolator (lockable, per equipment)",                    "No.",     680),
    ],

    "ESSENTIAL POWER WIRING": [
        ("Generator-backed essential-bus feed (ATS-fed)",                       "Item",   4500),
        ("Essential-bus distribution wiring",                                    "Lot",    8500),
        ("Critical-load monitoring point",                                       "No.",     280),
    ],

    "ISOLATED POWER SUPPLY": [
        ("Isolating transformer 5 kVA (BS HTM 06-01 / IEC 61558-2-15)",         "No.",   18500),
        ("Isolating transformer 8 kVA",                                           "No.",   24000),
        ("Isolating transformer 10 kVA",                                          "No.",   28000),
        ("Line isolation monitor LIM (audible + visual alarm)",                 "No.",    8500),
        ("Equipotential bus bar (clean earth)",                                  "No.",     850),
    ],

    "MEDICAL EQUIPMENT FINAL CONNECTIONS": [
        ("Final connection to MRI (per OEM spec)",                              "Lot",   12500),
        ("Final connection to CT scanner",                                       "Lot",    8500),
        ("Final connection to surgical luminaire",                              "No.",    1850),
        ("Final connection to dialysis station",                                "No.",    1450),
        ("Final connection to ICU monitor pendant",                             "No.",    2800),
    ],

    # ===================================================================
    # BUILDING MANAGEMENT SYSTEM (BMS)
    # ===================================================================
    "BMS HEAD-END PROCESSORS AND CENTRAL SERVERS": [
        ("BMS application server (rack-mount, hot-spare ready)",                "No.",   28000),
        ("BMS database server + storage (RAID)",                                "No.",   25000),
        ("BMS point-licence pack (per 100 points)",                              "Lot",   12500),
        ("BMS server software annual maintenance",                               "Lot",    8500),
    ],

    "AI / ANALYTICS CONTROLLERS": [
        ("AI / analytics edge gateway (FDD + energy optimisation)",             "No.",   18500),
        ("Predictive-maintenance module annual licence",                         "Lot",    8500),
        ("Energy-management software pack (kWh dashboards + alerts)",           "Lot",   12500),
        ("ML model deployment + tuning service",                                 "Item",   8500),
    ],

    "FIELD CONTROLLERS AND I/O MODULES": [
        ("BACnet/IP DDC controller (32 UI / 16 UO, programmable)",              "No.",    8500),
        ("BACnet MS/TP I/O module 8AI + 8DI + 8DO",                              "No.",    2800),
        ("Application-specific controller VAV (pre-loaded VAV app)",            "No.",    1850),
        ("Application-specific controller FCU",                                  "No.",    1450),
        ("Programmable web-server controller",                                   "No.",    5800),
    ],

    "SENSORS": [
        ("Duct temperature sensor (NTC10K)",                                    "No.",     180),
        ("Room temperature + setpoint sensor (BACnet MS/TP)",                   "No.",     480),
        ("Combined CO2 + temperature + humidity sensor (NDIR CO2)",             "No.",    1850),
        ("Differential pressure sensor (air, 0-500 Pa)",                        "No.",     680),
        ("PIR occupancy sensor (BMS-linked)",                                   "No.",     320),
        ("Water flow meter (DN50 turbine, pulse output)",                        "No.",    1450),
        ("Outdoor weather station (T/H/wind/light)",                             "No.",    4500),
    ],

    "ACTUATORS": [
        ("Motorised damper actuator 24V 5Nm (modulating, spring-return)",       "No.",     850),
        ("Motorised damper actuator 24V 10Nm",                                   "No.",    1200),
        ("2-port motorised valve DN50 modulating 0-10V",                         "No.",    1850),
        ("3-port motorised valve DN50 modulating",                              "No.",    2200),
        ("VAV box damper actuator (Belimo or approved equal)",                  "No.",    2200),
        ("Variable speed drive (VSD) interface card for BMS",                   "No.",    1200),
    ],

    "FIELD WIRING AND TERMINAL BLOCKS": [
        ("Belden 18 AWG shielded BMS bus cable (BACnet MS/TP)",                 "M",        22),
        ("Multi-core control cable 2 pair shielded",                            "M",        18),
        ("Multi-core control cable 4 pair shielded",                            "M",        32),
        ("Wago / Phoenix terminal block kit (spring-cage, DIN-rail)",          "Lot",     680),
        ("Field control panel IP55 lockable (per floor)",                       "No.",    2800),
        ("DIN-rail (per metre)",                                                 "M",        45),
    ],

    "BMS POWER SYSTEMS": [
        ("24Vdc power supply DIN-rail 240W (backup-ready)",                     "No.",    1450),
        ("BMS UPS rack-mount 1kVA (30 min runtime)",                            "No.",    5500),
        ("Dedicated BMS sub-DB feed",                                           "Item",   3500),
        ("Surge protection device for BMS bus",                                 "No.",     680),
    ],

    "BMS NETWORK CABLING AND SWITCHES": [
        ("BMS VLAN PoE switch 16-port (L2 managed)",                            "No.",    5500),
        ("Cat6 horizontal drop per BMS controller",                              "M",        12),
        ("Fibre uplink multimode (per metre)",                                   "M",        35),
        ("Network commissioning + BMS-VLAN setup",                               "Item",   2800),
    ],

    "OPERATOR WORKSTATIONS AND SOFTWARE LICENCES": [
        ("BMS operator workstation (dual-screen, i7, 16GB, SSD)",                "No.",    8500),
        ("Operator graphics + dashboard licence",                                "Lot",    8500),
        ("Mobile / web client licence",                                          "Lot",    4500),
        ("BMS reporting + scheduling licence",                                   "Lot",    3500),
    ],

    "INTEGRATION WITH HVAC, LIGHTING, FIRE ALARM, ACCESS CONTROL": [
        ("BACnet / Modbus integration to HVAC plant (per chiller / AHU)",       "Item",   4500),
        ("DALI / KNX integration to lighting control",                          "Item",   3500),
        ("Fire-alarm interface (volt-free contacts + BACnet)",                  "Item",   2800),
        ("Access-control / CCTV interface",                                     "Item",   3500),
        ("Lift / escalator status integration",                                  "Item",   2500),
    ],
}


# ---------------------------------------------------------------------------
# Splice: mutate _BOQ_SECTION_ITEM_CATALOG in place.
# Runs after data_v2 / v3 / v4 so this catalog extension lands LAST and
# fills the gaps. Section keys we ADD do not overwrite anything because
# only this file knows them; if a future version of the catalog adds the
# same key, the existing entry wins (we keep the first definition).
# ---------------------------------------------------------------------------
try:
    _cat = _BOQ_SECTION_ITEM_CATALOG  # type: ignore[name-defined]
except NameError:
    _cat = None

if _cat is not None:
    for _key, _items in _NEW_CATALOG_ENTRIES.items():
        # Don't clobber existing entries (data_v2 wins if there's a conflict).
        if _key not in _cat:
            _cat[_key] = list(_items)
