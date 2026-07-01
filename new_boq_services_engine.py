# === BEGIN: boq_services_engine splice ===
# 2026-06-29 refactor (projectboq build update1.txt). The BOQ engine is unified:
#   - Build by Template is RETIRED. There is no template picker, no wizard.
#   - Two build modes share the same engine: Section-by-Section (one section
#     at a time) and Complete BOQ (all selected services' sections in one
#     editable page).
#   - Service Configuration is the SOLE driver of which sections load.
#
# Source spec sections of relevance:
#   - lines 469-477  : 14 engineering services
#   - lines 502-608  : verbatim service -> section mapping
#   - lines 633-641  : important rules
#   - lines 679-697  : acceptance criteria
#
# The 15th service (BMS) is preserved at the owner's direction (2026-06-29)
# with sections modelled after the other 14 (processors, AI/analytics
# controllers, sensors, actuators, field wiring & terminal blocks, power
# systems, network cabling, workstations, integrations, T&C).
#
# Codes are STABLE -- they persist in boq_projects.services_csv. The legacy
# map below carries pre-refactor projects forward (silent auto-migrate).


# ---------------------------------------------------------------------------
# 1. Service registry (15 services, spec order, BMS last)
# ---------------------------------------------------------------------------

_BOQ_SERVICES = [
    ("internal_electrical",   "Internal Electrical Installation",                              "bi-plug-fill"),
    ("fire_alarm",            "Fire Alarm System Installation",                                "bi-fire"),
    ("earthing_bonding",      "Equipotential Bonding System Installation",                     "bi-arrow-down-square"),
    ("lightning_protection",  "Lightning Protection System Installation",                      "bi-cloud-lightning-rain"),
    ("power_supply_lv",       "Power Supply, LV Distribution and External Lighting Systems",   "bi-lightning-charge"),
    ("lan_wlan",              "Local Area Network and Wireless Area Network",                  "bi-hdd-network"),
    ("it_server_room",        "IT Server Room Infrastructure",                                 "bi-server"),
    ("voip",                  "VoIP System Installation",                                      "bi-telephone-inbound"),
    ("ip_pa",                 "Public Address System Installation",                            "bi-megaphone"),
    ("ip_cctv",               "IP CCTV Network Installation",                                  "bi-camera-video"),
    ("tv_system",             "TV System Installation",                                        "bi-tv"),
    ("ip_clock",              "IP Clock System Installation",                                  "bi-clock-history"),
    ("nurse_call",            "Nurse Call System Installation",                                "bi-bell-fill"),
    ("medical_equip",         "Medical Equipment Electrical Installation",                     "bi-heart-pulse"),
    ("bms",                   "Building Management System (BMS)",                              "bi-cpu"),
]
_BOQ_SERVICE_CODES = [c for c, _, _ in _BOQ_SERVICES]
_BOQ_SERVICE_LABEL = {c: l for c, l, _ in _BOQ_SERVICES}
_BOQ_SERVICE_ICON  = {c: ic for c, _, ic in _BOQ_SERVICES}


# ---------------------------------------------------------------------------
# 2. Legacy code -> new code map (silent migration on first read)
# ---------------------------------------------------------------------------
# A legacy code may expand to multiple new codes (it_network -> lan_wlan +
# it_server_room because the spec splits them).

_BOQ_SERVICE_LEGACY_MAP = {
    "power_supply_lighting": ["power_supply_lv"],
    "it_network":            ["lan_wlan", "it_server_room"],
    # All other pre-refactor codes (internal_electrical, fire_alarm,
    # earthing_bonding, lightning_protection, ip_cctv, nurse_call, ip_pa,
    # bms) match the new set 1:1 so they need no entry here.
}


# ---------------------------------------------------------------------------
# 3. Bill-name -> services map (infers services_csv from existing bill rows
#    when a legacy project has services_csv NULL).
# ---------------------------------------------------------------------------

_BOQ_BILL_TO_SERVICES = [
    ("PRELIMINARIES",                 []),   # spans services
    ("INTERNAL ELECTRICAL",           ["internal_electrical"]),
    ("SWITCH BOARDS",                 ["internal_electrical"]),
    ("DISTRIBUTION BOARDS",           ["internal_electrical"]),
    ("WIRING OF POINTS",              ["internal_electrical"]),
    ("LUMINAIRES",                    ["internal_electrical"]),
    ("EXTERNAL LIGHTING",             ["power_supply_lv"]),
    ("POWER SUPPLY",                  ["power_supply_lv"]),
    ("LV DISTRIBUTION",               ["power_supply_lv"]),
    ("TRANSFORMER",                   ["power_supply_lv"]),
    ("BONDING AND EARTHING",          ["earthing_bonding"]),
    ("EQUIPOTENTIAL",                 ["earthing_bonding"]),
    ("LIGHTNING PROTECTION",          ["lightning_protection"]),
    ("FIRE ALARM",                    ["fire_alarm"]),
    ("FIRE DETECTION",                ["fire_alarm"]),
    ("STRUCTURED CABLING",            ["lan_wlan"]),
    ("DATA AND VOICE",                ["lan_wlan"]),
    ("WIRELESS",                      ["lan_wlan"]),
    ("LAN AND",                       ["lan_wlan"]),
    ("NETWORK CABINET",               ["lan_wlan"]),
    ("IT SERVER ROOM",                ["it_server_room"]),
    ("SERVER ROOM",                   ["it_server_room"]),
    ("UPS",                           ["it_server_room"]),
    ("VOIP",                          ["voip"]),
    ("IP PHONE",                      ["voip"]),
    ("VOICE GATEWAY",                 ["voip"]),
    ("PUBLIC ADDRESS",                ["ip_pa"]),
    ("PA SYSTEM",                     ["ip_pa"]),
    ("CCTV",                          ["ip_cctv"]),
    ("TV SYSTEM",                     ["tv_system"]),
    ("IP CLOCK",                      ["ip_clock"]),
    ("MASTER CLOCK",                  ["ip_clock"]),
    ("NURSE CALL",                    ["nurse_call"]),
    ("MEDICAL EQUIPMENT",             ["medical_equip"]),
    ("ISOLATED POWER SUPPLY",         ["medical_equip"]),
    ("BUILDING MANAGEMENT",           ["bms"]),
    ("BMS",                           ["bms"]),
    # Legacy aggregate names (pre-2026-06-29) -- still resolve.
    ("SIGNAL COMMUNICATION",          ["ip_pa", "ip_cctv"]),
    ("IT AND NETWORK",                ["lan_wlan"]),
]


# ---------------------------------------------------------------------------
# 4. Per-service section skeleton.
#    Each service = one Bill on the floor. The Bill's `sections` is the
#    verbatim list from the spec; each section has 3-5 representative items
#    so the BOQ feels real out-of-the-box. qty=0 + basic=0 by owner directive
#    (2026-06-28) -- owner fills in per project.
# ---------------------------------------------------------------------------

_BOQ_SERVICE_BILL_SKELETON = {

    # ------------ 1. Internal Electrical Installation -----------------
    "internal_electrical": {
        "name": "INTERNAL ELECTRICAL INSTALLATION",
        "sections": [
            {"letter": "A", "title": "PRELIMINARIES", "subsection": "", "items": [
                {"desc": "Site supervision and project management",                "unit": "Item", "qty": 0, "basic": 0, "spec": "Per contract programme"},
                {"desc": "Mobilisation and demobilisation",                        "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Testing instruments and PPE allowance",                  "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Permits, certificates and notices",                      "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "B", "title": "SWITCH BOARDS AND DISTRIBUTION BOARDS", "subsection": "", "items": [
                {"desc": "Main Distribution Board (MDB)",                          "unit": "No.", "qty": 0, "basic": 0, "spec": "TPN, MCCB incomer + outgoing breakers"},
                {"desc": "Sub Distribution Board (SDB)",                           "unit": "No.", "qty": 0, "basic": 0, "spec": "TPN, 12-way, 100A"},
                {"desc": "Final Distribution Board (FDB)",                         "unit": "No.", "qty": 0, "basic": 0, "spec": "SPN, 8-way, 63A with MCBs"},
                {"desc": "Surge protection device (Type 1+2)",                     "unit": "No.", "qty": 0, "basic": 0, "spec": "IEC 61643"},
            ]},
            {"letter": "C", "title": "SUB-FEEDER CABLES AND EARTH LEADS", "subsection": "", "items": [
                {"desc": "4C x 16mm² Cu/XLPE/SWA/PVC sub-feeder cable",            "unit": "m",   "qty": 0, "basic": 0, "spec": "BS 5467"},
                {"desc": "4C x 25mm² Cu/XLPE/SWA/PVC sub-feeder cable",            "unit": "m",   "qty": 0, "basic": 0, "spec": "BS 5467"},
                {"desc": "1C x 10mm² PVC earth lead",                              "unit": "m",   "qty": 0, "basic": 0, "spec": "Green/yellow"},
                {"desc": "Cable gland and lug kit (per cable size)",               "unit": "Set", "qty": 0, "basic": 0, "spec": "Brass, BS 6121"},
            ]},
            {"letter": "D", "title": "WIRING OF POINTS", "subsection": "Lighting + socket circuits", "items": [
                {"desc": "1.5mm² PVC single copper conductor",                     "unit": "Roll", "qty": 0, "basic": 0, "spec": "BS 6004, R/B/Y/G&Y per phase colour"},
                {"desc": "2.5mm² PVC single copper conductor",                     "unit": "Roll", "qty": 0, "basic": 0, "spec": "BS 6004"},
                {"desc": "4.0mm² PVC single copper conductor",                     "unit": "Roll", "qty": 0, "basic": 0, "spec": "BS 6004"},
                {"desc": "20mm PVC conduit + boxes (Heavy gauge)",                 "unit": "Lot", "qty": 0, "basic": 0, "spec": "BS 6099"},
            ]},
            {"letter": "E", "title": "LUMINAIRES", "subsection": "", "items": [
                {"desc": "LED panel light 600x600 (40W, 4000K)",                   "unit": "No.", "qty": 0, "basic": 0, "spec": "UGR<19, recessed"},
                {"desc": "LED downlight 18W (4000K)",                              "unit": "No.", "qty": 0, "basic": 0, "spec": "Recessed, IP44 bathroom-rated"},
                {"desc": "LED batten 4ft (36W)",                                   "unit": "No.", "qty": 0, "basic": 0, "spec": "Surface, BS EN 60598"},
                {"desc": "Emergency exit luminaire (3hr maintained)",              "unit": "No.", "qty": 0, "basic": 0, "spec": "Self-test, BS EN 60598-2-22"},
            ]},
            {"letter": "F", "title": "ACCESSORIES", "subsection": "", "items": [
                {"desc": "13A switched socket outlet (single)",                    "unit": "No.", "qty": 0, "basic": 0, "spec": "White moulded, BS 1363"},
                {"desc": "13A switched socket outlet (double)",                    "unit": "No.", "qty": 0, "basic": 0, "spec": "White moulded, BS 1363"},
                {"desc": "1-gang 1-way wall switch (10A)",                         "unit": "No.", "qty": 0, "basic": 0, "spec": "White moulded, BS 3676"},
                {"desc": "2-gang 2-way wall switch (10A)",                         "unit": "No.", "qty": 0, "basic": 0, "spec": "White moulded"},
                {"desc": "Ceiling rose with hook",                                 "unit": "No.", "qty": 0, "basic": 0, "spec": "BS 67"},
            ]},
            {"letter": "G", "title": "BONDING AND EARTHING", "subsection": "", "items": [
                {"desc": "Main earth bar (drilled copper)",                        "unit": "No.", "qty": 0, "basic": 0, "spec": "Insulated, lockable enclosure"},
                {"desc": "16mm² PVC earth conductor",                              "unit": "m",   "qty": 0, "basic": 0, "spec": "Green/yellow"},
                {"desc": "Earth rod 1.5m + clamp + inspection pit",                "unit": "Set", "qty": 0, "basic": 0, "spec": "Copper-bonded, BS 7430"},
            ]},
            {"letter": "H", "title": "TESTING AND COMMISSIONING", "subsection": "", "items": [
                {"desc": "Insulation resistance test (per circuit)",               "unit": "Item", "qty": 0, "basic": 0, "spec": "500V Megger, BS 7671"},
                {"desc": "Earth loop impedance test",                              "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "RCD operation test",                                     "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Phase rotation test",                                    "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "I", "title": "DOCUMENTATION AND HANDOVER", "subsection": "", "items": [
                {"desc": "As-built drawings (PDF + DWG)",                          "unit": "Set", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Operation and Maintenance manual",                       "unit": "Set", "qty": 0, "basic": 0, "spec": "Printed + USB"},
                {"desc": "Test certificates (electrical)",                         "unit": "Set", "qty": 0, "basic": 0, "spec": "BS 7671 Schedule of Test Results"},
                {"desc": "Training to client maintenance staff",                   "unit": "Day", "qty": 0, "basic": 0, "spec": ""},
            ]},
        ],
    },

    # ------------ 2. Fire Alarm System Installation -------------------
    "fire_alarm": {
        "name": "FIRE ALARM SYSTEM INSTALLATION",
        "sections": [
            {"letter": "A", "title": "FIRE DETECTION AND ALARM SYSTEM", "subsection": "", "items": [
                {"desc": "Addressable Fire Alarm Control Panel (FACP)",            "unit": "No.", "qty": 0, "basic": 0, "spec": "2-loop, EN 54-2/4"},
                {"desc": "Optical smoke detector (addressable)",                   "unit": "No.", "qty": 0, "basic": 0, "spec": "EN 54-7"},
                {"desc": "Heat detector (addressable, A2S)",                       "unit": "No.", "qty": 0, "basic": 0, "spec": "EN 54-5"},
                {"desc": "Manual Call Point (break-glass)",                        "unit": "No.", "qty": 0, "basic": 0, "spec": "EN 54-11"},
                {"desc": "Sounder + strobe (wall-mount, 100dB)",                   "unit": "No.", "qty": 0, "basic": 0, "spec": "EN 54-3/23"},
            ]},
            {"letter": "B", "title": "FIRE ALARM CABLING", "subsection": "", "items": [
                {"desc": "Fire-resistant cable 1.5mm² 2C (FP200)",                 "unit": "m",   "qty": 0, "basic": 0, "spec": "BS EN 50200 PH120"},
                {"desc": "Fire-resistant cable 2.5mm² 2C (FP200)",                 "unit": "m",   "qty": 0, "basic": 0, "spec": "For sounder circuits"},
                {"desc": "Containment for FA cabling (LSF tray + clips)",          "unit": "m",   "qty": 0, "basic": 0, "spec": "Red colour-coded"},
            ]},
            {"letter": "C", "title": "FIRE ALARM ACCESSORIES", "subsection": "", "items": [
                {"desc": "Door retainer (24Vdc, magnetic)",                        "unit": "No.", "qty": 0, "basic": 0, "spec": "EN 1155"},
                {"desc": "Interface module (input/output)",                        "unit": "No.", "qty": 0, "basic": 0, "spec": "Addressable, BMS-linked"},
                {"desc": "Battery backup (24Vdc, sealed lead-acid)",               "unit": "Set", "qty": 0, "basic": 0, "spec": "24hrs standby + 30min alarm"},
            ]},
            {"letter": "D", "title": "TESTING AND COMMISSIONING", "subsection": "", "items": [
                {"desc": "100% device sweep test (smoke + heat + MCP)",            "unit": "Item", "qty": 0, "basic": 0, "spec": "BS 5839-1"},
                {"desc": "Sounder audibility test (per zone)",                     "unit": "Item", "qty": 0, "basic": 0, "spec": "65dBA above ambient"},
                {"desc": "Cause-and-effect commissioning",                         "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
            ]},
        ],
    },

    # ------------ 3. Equipotential Bonding System Installation --------
    "earthing_bonding": {
        "name": "EQUIPOTENTIAL BONDING SYSTEM INSTALLATION",
        "sections": [
            {"letter": "A", "title": "BONDING AND EARTHING", "subsection": "", "items": [
                {"desc": "Main earthing terminal (MET) copper bar",                "unit": "No.", "qty": 0, "basic": 0, "spec": "Insulated, lockable"},
                {"desc": "70mm² PVC earth conductor",                              "unit": "m",   "qty": 0, "basic": 0, "spec": "Green/yellow"},
                {"desc": "35mm² PVC earth conductor",                              "unit": "m",   "qty": 0, "basic": 0, "spec": "Green/yellow"},
            ]},
            {"letter": "B", "title": "EQUIPOTENTIAL BONDING", "subsection": "", "items": [
                {"desc": "Bonding to incoming water service",                      "unit": "No.", "qty": 0, "basic": 0, "spec": "Earth clamp + 10mm² conductor"},
                {"desc": "Bonding to incoming gas service",                        "unit": "No.", "qty": 0, "basic": 0, "spec": "Earth clamp + 10mm² conductor"},
                {"desc": "Bonding to structural steel",                            "unit": "No.", "qty": 0, "basic": 0, "spec": "16mm² conductor + lug"},
                {"desc": "Supplementary bonding (wet areas)",                      "unit": "Lot", "qty": 0, "basic": 0, "spec": "Per IEE wiring regs 415.2"},
            ]},
            {"letter": "C", "title": "EARTH BARS AND EARTH LEADS", "subsection": "", "items": [
                {"desc": "Sub-earth bar (drilled copper, 6 ways)",                 "unit": "No.", "qty": 0, "basic": 0, "spec": "Wall-mounted enclosure"},
                {"desc": "Cable lug (per conductor size)",                         "unit": "No.", "qty": 0, "basic": 0, "spec": "Compression type, tinned"},
            ]},
            {"letter": "D", "title": "TESTING AND COMMISSIONING", "subsection": "", "items": [
                {"desc": "Earth resistance measurement",                           "unit": "Item", "qty": 0, "basic": 0, "spec": "Fall-of-potential method"},
                {"desc": "Continuity test of bonding conductors",                  "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Test certificate (earthing)",                            "unit": "Set", "qty": 0, "basic": 0, "spec": "BS 7430"},
            ]},
        ],
    },

    # ------------ 4. Lightning Protection System Installation ---------
    "lightning_protection": {
        "name": "LIGHTNING PROTECTION SYSTEM INSTALLATION",
        "sections": [
            {"letter": "A", "title": "LIGHTNING PROTECTION", "subsection": "Risk assessment + design", "items": [
                {"desc": "Risk assessment per IEC 62305-2",                        "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Rolling sphere design + drawing pack",                   "unit": "Set", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "B", "title": "AIR TERMINALS", "subsection": "", "items": [
                {"desc": "Copper air-terminal rod 1m x 16mm dia",                  "unit": "No.", "qty": 0, "basic": 0, "spec": "BS EN 62305"},
                {"desc": "Air-terminal base + insulating pad",                     "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "C", "title": "DOWN CONDUCTORS", "subsection": "", "items": [
                {"desc": "25 x 3mm hard-drawn copper tape",                        "unit": "m",   "qty": 0, "basic": 0, "spec": "BS EN 50164-2"},
                {"desc": "Roof + wall tape clips (per type)",                      "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "D", "title": "TEST CLAMPS", "subsection": "", "items": [
                {"desc": "Test clamp (bolted disconnect, brass)",                  "unit": "No.", "qty": 0, "basic": 0, "spec": "Accessible at 2.0m AGL"},
            ]},
            {"letter": "E", "title": "EARTH ELECTRODES", "subsection": "", "items": [
                {"desc": "Copper-bonded earth rod 1.5m x 16mm dia",                "unit": "No.", "qty": 0, "basic": 0, "spec": "BS 7430"},
                {"desc": "Inspection pit + lid + clamp",                           "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Bentonite earth-enhancing compound",                     "unit": "Bag", "qty": 0, "basic": 0, "spec": "25kg"},
            ]},
            {"letter": "F", "title": "TESTING AND COMMISSIONING", "subsection": "", "items": [
                {"desc": "Earth resistance measurement (LPS)",                     "unit": "Item", "qty": 0, "basic": 0, "spec": "Target <10 ohms"},
                {"desc": "Continuity sweep (down conductors)",                     "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "LPS test certificate",                                   "unit": "Set", "qty": 0, "basic": 0, "spec": "IEC 62305"},
            ]},
        ],
    },

    # ------------ 5. Power Supply, LV Distribution and External Lighting Systems
    "power_supply_lv": {
        "name": "POWER SUPPLY, LV DISTRIBUTION AND EXTERNAL LIGHTING SYSTEMS",
        "sections": [
            {"letter": "A", "title": "TRANSFORMERS", "subsection": "", "items": [
                {"desc": "Distribution transformer (oil-immersed, ONAN)",          "unit": "No.", "qty": 0, "basic": 0, "spec": "11kV/415V, rated per demand"},
                {"desc": "Transformer civil plinth + bund wall",                   "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "B", "title": "RMU", "subsection": "Ring main unit", "items": [
                {"desc": "11kV Ring Main Unit (2-way + Tee-off)",                  "unit": "No.", "qty": 0, "basic": 0, "spec": "SF6 insulated, IEC 62271"},
            ]},
            {"letter": "C", "title": "AVR", "subsection": "Automatic voltage regulator", "items": [
                {"desc": "AVR (servo-motor type)",                                 "unit": "No.", "qty": 0, "basic": 0, "spec": "415V, sized per total load"},
            ]},
            {"letter": "D", "title": "MAIN LV SWITCHBOARDS", "subsection": "", "items": [
                {"desc": "Main LV switchboard (form 4b, IP54)",                    "unit": "No.", "qty": 0, "basic": 0, "spec": "Air circuit breaker incomer + MCCB outgoers"},
                {"desc": "Capacitor bank (PFC, automatic)",                        "unit": "No.", "qty": 0, "basic": 0, "spec": "Target 0.95 lagging"},
            ]},
            {"letter": "E", "title": "PANEL BOARDS", "subsection": "", "items": [
                {"desc": "Sub-main panel board (TPN, MCCB)",                       "unit": "No.", "qty": 0, "basic": 0, "spec": "Floor or building level"},
            ]},
            {"letter": "F", "title": "DISTRIBUTION BOARDS", "subsection": "", "items": [
                {"desc": "Final distribution board (TPN, MCB)",                    "unit": "No.", "qty": 0, "basic": 0, "spec": "12 / 18 / 24 way"},
            ]},
            {"letter": "G", "title": "SUB-FEEDER CABLES", "subsection": "", "items": [
                {"desc": "4C x 70mm² Cu/XLPE/SWA/PVC sub-feeder",                  "unit": "m",   "qty": 0, "basic": 0, "spec": "BS 5467"},
                {"desc": "4C x 50mm² Cu/XLPE/SWA/PVC sub-feeder",                  "unit": "m",   "qty": 0, "basic": 0, "spec": "BS 5467"},
                {"desc": "Cable tray (galv. perforated, 300mm)",                   "unit": "m",   "qty": 0, "basic": 0, "spec": "Hot-dip galvanised"},
            ]},
            {"letter": "H", "title": "EXTERNAL LIGHTING", "subsection": "", "items": [
                {"desc": "9m steel street-light pole + LED head (60W)",            "unit": "No.", "qty": 0, "basic": 0, "spec": "IP66, 4000K"},
                {"desc": "Bollard light (LED, 12W)",                               "unit": "No.", "qty": 0, "basic": 0, "spec": "IK10, vandal-resistant"},
                {"desc": "Photocell + contactor control panel",                    "unit": "No.", "qty": 0, "basic": 0, "spec": "Dusk-to-dawn + override"},
            ]},
            {"letter": "I", "title": "EARTHING GRID", "subsection": "", "items": [
                {"desc": "Bare copper earth tape (25 x 3mm)",                      "unit": "m",   "qty": 0, "basic": 0, "spec": "Buried, exothermic-welded"},
                {"desc": "Earth electrode (copper-bonded, 2.4m)",                  "unit": "No.", "qty": 0, "basic": 0, "spec": "BS 7430"},
            ]},
            {"letter": "J", "title": "CABLE TRENCHES", "subsection": "", "items": [
                {"desc": "Excavation + backfill cable trench (450 x 800mm)",       "unit": "m",   "qty": 0, "basic": 0, "spec": "Including sand bed + tile cover"},
                {"desc": "Concrete cable duct (uPVC, 100mm)",                      "unit": "m",   "qty": 0, "basic": 0, "spec": "Class 1"},
            ]},
            {"letter": "K", "title": "TESTING AND COMMISSIONING", "subsection": "", "items": [
                {"desc": "Switchgear commissioning + functional test",             "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Transformer oil + electrical tests",                     "unit": "Item", "qty": 0, "basic": 0, "spec": "BDV / DGA / IR"},
                {"desc": "Lighting control + photocell commissioning",             "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
            ]},
        ],
    },

    # ------------ 6. Local Area Network and Wireless Area Network -----
    "lan_wlan": {
        "name": "LOCAL AREA NETWORK AND WIRELESS AREA NETWORK",
        "sections": [
            {"letter": "A", "title": "DATA AND VOICE COMMUNICATION", "subsection": "", "items": [
                {"desc": "Cat6 RJ45 voice/data outlet (single-gang)",              "unit": "No.", "qty": 0, "basic": 0, "spec": "T568B punch-down"},
                {"desc": "Cat6 RJ45 voice/data outlet (double-gang)",              "unit": "No.", "qty": 0, "basic": 0, "spec": "T568B punch-down"},
            ]},
            {"letter": "B", "title": "STRUCTURED CABLING", "subsection": "", "items": [
                {"desc": "Cat6 UTP horizontal cable (305m roll)",                  "unit": "Roll", "qty": 0, "basic": 0, "spec": "Blue jacket"},
                {"desc": "24-port Cat6 patch panel (1U)",                          "unit": "No.", "qty": 0, "basic": 0, "spec": "Loaded"},
                {"desc": "Cat6 patch lead (1m)",                                   "unit": "No.", "qty": 0, "basic": 0, "spec": "Snagless"},
                {"desc": "Cat6 patch lead (2m)",                                   "unit": "No.", "qty": 0, "basic": 0, "spec": "Snagless"},
            ]},
            {"letter": "C", "title": "NETWORK CABINETS", "subsection": "", "items": [
                {"desc": "24U floor-standing data cabinet (600x800)",              "unit": "No.", "qty": 0, "basic": 0, "spec": "Glass front, locking"},
                {"desc": "12U wall-mounted data cabinet (600x500)",                "unit": "No.", "qty": 0, "basic": 0, "spec": "Glass front, locking"},
                {"desc": "Cable manager + PDU + cooling fan",                      "unit": "Set", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "D", "title": "WIRELESS ACCESS POINTS", "subsection": "", "items": [
                {"desc": "WiFi 6 Access Point (PoE+)",                             "unit": "No.", "qty": 0, "basic": 0, "spec": "2x2 MIMO, IEEE 802.11ax"},
                {"desc": "WiFi 6 Access Point (outdoor, IP67)",                    "unit": "No.", "qty": 0, "basic": 0, "spec": "PoE+, mesh-capable"},
                {"desc": "Wireless controller (cloud-managed)",                    "unit": "No.", "qty": 0, "basic": 0, "spec": "Per architecture"},
            ]},
            {"letter": "E", "title": "TESTING AND CERTIFICATION", "subsection": "", "items": [
                {"desc": "Cat6 channel certification (per outlet)",                "unit": "No.", "qty": 0, "basic": 0, "spec": "Fluke / Wirexpert report"},
                {"desc": "Wireless site survey + heatmap",                         "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Network commissioning + handover",                       "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
            ]},
        ],
    },

    # ------------ 7. IT Server Room Infrastructure --------------------
    "it_server_room": {
        "name": "IT SERVER ROOM INFRASTRUCTURE",
        "sections": [
            {"letter": "A", "title": "IT SERVER ROOM POWER", "subsection": "", "items": [
                {"desc": "Server room sub-DB (TPN, 12-way)",                       "unit": "No.", "qty": 0, "basic": 0, "spec": "63A incomer + MCBs"},
                {"desc": "Critical-load distribution feed",                        "unit": "Item", "qty": 0, "basic": 0, "spec": "From essential bus"},
                {"desc": "Single-phase isolators (per rack)",                      "unit": "No.", "qty": 0, "basic": 0, "spec": "32A"},
            ]},
            {"letter": "B", "title": "UPS", "subsection": "Uninterruptible power supply", "items": [
                {"desc": "Online double-conversion UPS (rack-mount)",              "unit": "No.", "qty": 0, "basic": 0, "spec": "Sized per critical load + 30min runtime"},
                {"desc": "Extended battery cabinet",                               "unit": "No.", "qty": 0, "basic": 0, "spec": "Sealed VRLA, hot-swap"},
                {"desc": "Maintenance bypass switch",                              "unit": "No.", "qty": 0, "basic": 0, "spec": "Manual, make-before-break"},
            ]},
            {"letter": "C", "title": "SERVER RACKS", "subsection": "", "items": [
                {"desc": "42U server rack (600x1000)",                             "unit": "No.", "qty": 0, "basic": 0, "spec": "Perforated doors, baying kit"},
                {"desc": "Vertical cable manager + 0U PDU",                        "unit": "Set", "qty": 0, "basic": 0, "spec": "Switched, monitored"},
            ]},
            {"letter": "D", "title": "DATA CABINETS", "subsection": "", "items": [
                {"desc": "24U data cabinet (network row)",                         "unit": "No.", "qty": 0, "basic": 0, "spec": "600x800, glass front"},
                {"desc": "Fibre patch panel (LC duplex, 24-port)",                 "unit": "No.", "qty": 0, "basic": 0, "spec": "OS2 single-mode"},
            ]},
            {"letter": "E", "title": "EARTHING AND BONDING", "subsection": "", "items": [
                {"desc": "Computer-room earth grid (mesh)",                        "unit": "Lot", "qty": 0, "basic": 0, "spec": "TIA-942"},
                {"desc": "Rack-bonding kit (per cabinet)",                         "unit": "No.", "qty": 0, "basic": 0, "spec": "16mm² conductor + lug"},
            ]},
            {"letter": "F", "title": "ENVIRONMENTAL MONITORING", "subsection": "", "items": [
                {"desc": "Temperature + humidity sensor (SNMP)",                   "unit": "No.", "qty": 0, "basic": 0, "spec": "Email/SMS alerting"},
                {"desc": "Leak-detection rope sensor",                             "unit": "m",   "qty": 0, "basic": 0, "spec": "Under raised floor"},
                {"desc": "Smoke + heat early-warning detection (VESDA)",           "unit": "No.", "qty": 0, "basic": 0, "spec": "Aspirating"},
            ]},
            {"letter": "G", "title": "TESTING AND COMMISSIONING", "subsection": "", "items": [
                {"desc": "UPS load + autonomy test",                               "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Environmental monitoring commissioning",                 "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Tier-rating compliance check (per design)",              "unit": "Item", "qty": 0, "basic": 0, "spec": "TIA-942 / Uptime"},
            ]},
        ],
    },

    # ------------ 8. VoIP System Installation -------------------------
    "voip": {
        "name": "VOIP SYSTEM INSTALLATION",
        "sections": [
            {"letter": "A", "title": "VOIP SYSTEM", "subsection": "", "items": [
                {"desc": "IP-PBX server (appliance + license pack)",               "unit": "No.", "qty": 0, "basic": 0, "spec": "Sized per total extensions"},
                {"desc": "SIP trunk licence (annual)",                             "unit": "Channel", "qty": 0, "basic": 0, "spec": "Per concurrent call"},
            ]},
            {"letter": "B", "title": "IP PHONES", "subsection": "", "items": [
                {"desc": "IP desk phone (entry, monochrome)",                      "unit": "No.", "qty": 0, "basic": 0, "spec": "PoE, HD voice"},
                {"desc": "IP desk phone (executive, colour, Gigabit)",             "unit": "No.", "qty": 0, "basic": 0, "spec": "PoE, BLF keys"},
                {"desc": "IP conference phone",                                    "unit": "No.", "qty": 0, "basic": 0, "spec": "Omnidirectional, PoE"},
            ]},
            {"letter": "C", "title": "VOICE GATEWAY", "subsection": "", "items": [
                {"desc": "Analog-to-VoIP gateway (FXS / FXO)",                     "unit": "No.", "qty": 0, "basic": 0, "spec": "For legacy fax / analog lines"},
                {"desc": "E1 / PRI gateway",                                       "unit": "No.", "qty": 0, "basic": 0, "spec": "If TDM trunks retained"},
            ]},
            {"letter": "D", "title": "NETWORK SWITCHES", "subsection": "", "items": [
                {"desc": "24-port PoE+ access switch (Gigabit)",                   "unit": "No.", "qty": 0, "basic": 0, "spec": "L2, 370W PoE budget"},
                {"desc": "10G uplink module (SFP+)",                               "unit": "No.", "qty": 0, "basic": 0, "spec": "Multimode"},
            ]},
            {"letter": "E", "title": "DATA OUTLETS", "subsection": "", "items": [
                {"desc": "Cat6 RJ45 voice outlet (single-gang)",                   "unit": "No.", "qty": 0, "basic": 0, "spec": "T568B"},
            ]},
            {"letter": "F", "title": "TESTING AND COMMISSIONING", "subsection": "", "items": [
                {"desc": "Call-quality testing (per extension)",                   "unit": "Item", "qty": 0, "basic": 0, "spec": "MOS > 4.0"},
                {"desc": "Failover + redundancy test",                             "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "User training (admin + user)",                           "unit": "Day", "qty": 0, "basic": 0, "spec": ""},
            ]},
        ],
    },

    # ------------ 9. Public Address System Installation ---------------
    "ip_pa": {
        "name": "PUBLIC ADDRESS SYSTEM INSTALLATION",
        "sections": [
            {"letter": "A", "title": "PUBLIC ADDRESS SYSTEM", "subsection": "", "items": [
                {"desc": "PA controller + zone-paging server",                     "unit": "No.", "qty": 0, "basic": 0, "spec": "Per zone count, EN 54-16"},
            ]},
            {"letter": "B", "title": "AMPLIFIERS", "subsection": "", "items": [
                {"desc": "PA amplifier 120W (100V line)",                          "unit": "No.", "qty": 0, "basic": 0, "spec": "Zone-output, EN 54-16"},
                {"desc": "PA amplifier 240W (100V line)",                          "unit": "No.", "qty": 0, "basic": 0, "spec": "EN 54-16"},
                {"desc": "Standby / hot-swap amplifier",                           "unit": "No.", "qty": 0, "basic": 0, "spec": "Redundancy"},
            ]},
            {"letter": "C", "title": "SPEAKERS", "subsection": "", "items": [
                {"desc": "Ceiling speaker 6W (100V)",                              "unit": "No.", "qty": 0, "basic": 0, "spec": "Fire-rated dome"},
                {"desc": "Wall-mount cabinet speaker 10W (100V)",                  "unit": "No.", "qty": 0, "basic": 0, "spec": "EN 54-24"},
                {"desc": "Horn speaker 30W (100V, outdoor IP66)",                  "unit": "No.", "qty": 0, "basic": 0, "spec": "EN 54-24"},
            ]},
            {"letter": "D", "title": "MICROPHONE POINTS", "subsection": "", "items": [
                {"desc": "Desktop paging microphone (PTT)",                        "unit": "No.", "qty": 0, "basic": 0, "spec": "Zone-select keypad"},
                {"desc": "Emergency / all-call microphone",                        "unit": "No.", "qty": 0, "basic": 0, "spec": "Lockable, EN 54-16"},
            ]},
            {"letter": "E", "title": "PA CABLING", "subsection": "", "items": [
                {"desc": "100V line speaker cable (1.5mm² 2C)",                    "unit": "m",   "qty": 0, "basic": 0, "spec": "Fire-rated for EVAC"},
                {"desc": "PA containment (LSF tray + clips)",                      "unit": "m",   "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "F", "title": "TESTING AND COMMISSIONING", "subsection": "", "items": [
                {"desc": "Sound-pressure measurement (per zone)",                  "unit": "Item", "qty": 0, "basic": 0, "spec": "65dBA above ambient"},
                {"desc": "Speech intelligibility (STI) test",                      "unit": "Item", "qty": 0, "basic": 0, "spec": "STI > 0.50"},
                {"desc": "Zone-paging functional test",                            "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
            ]},
        ],
    },

    # ------------ 10. IP CCTV Network Installation --------------------
    "ip_cctv": {
        "name": "IP CCTV NETWORK INSTALLATION",
        "sections": [
            {"letter": "A", "title": "IP CCTV SYSTEM", "subsection": "", "items": [
                {"desc": "VMS server + licence pack",                              "unit": "No.", "qty": 0, "basic": 0, "spec": "Per camera count"},
                {"desc": "Operator workstation (dual-screen)",                     "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "B", "title": "CAMERAS", "subsection": "", "items": [
                {"desc": "5MP IP dome camera (PoE, indoor)",                       "unit": "No.", "qty": 0, "basic": 0, "spec": "H.265, IR 30m"},
                {"desc": "5MP IP bullet camera (PoE, outdoor IP67)",               "unit": "No.", "qty": 0, "basic": 0, "spec": "H.265, IR 50m"},
                {"desc": "8MP PTZ camera (PoE+, 30x zoom)",                        "unit": "No.", "qty": 0, "basic": 0, "spec": "IP67, IR 200m"},
            ]},
            {"letter": "C", "title": "NVR", "subsection": "Network video recorder", "items": [
                {"desc": "32-channel NVR + storage (RAID-5)",                      "unit": "No.", "qty": 0, "basic": 0, "spec": "Days retention per spec"},
                {"desc": "Storage expansion module",                               "unit": "No.", "qty": 0, "basic": 0, "spec": "If retention > 30 days"},
            ]},
            {"letter": "D", "title": "POE SWITCHES", "subsection": "", "items": [
                {"desc": "24-port PoE+ switch (Gigabit, 370W)",                    "unit": "No.", "qty": 0, "basic": 0, "spec": "Camera-only VLAN"},
                {"desc": "Industrial PoE+ switch (DIN-rail, outdoor)",             "unit": "No.", "qty": 0, "basic": 0, "spec": "IP30, -40 to 75C"},
            ]},
            {"letter": "E", "title": "CCTV CABLING", "subsection": "", "items": [
                {"desc": "Cat6 outdoor UV-resistant cable",                        "unit": "m",   "qty": 0, "basic": 0, "spec": "Black jacket, gel-filled"},
                {"desc": "Fibre patch (multi-mode OM3, LC-LC)",                    "unit": "m",   "qty": 0, "basic": 0, "spec": "For long runs > 90m"},
            ]},
            {"letter": "F", "title": "CAMERA POLES / MOUNTS", "subsection": "", "items": [
                {"desc": "6m camera pole (hot-dip galvanised)",                    "unit": "No.", "qty": 0, "basic": 0, "spec": "Bracket + power feed"},
                {"desc": "Wall-mount bracket (IP66 junction)",                     "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "G", "title": "TESTING AND COMMISSIONING", "subsection": "", "items": [
                {"desc": "Per-camera image-quality test",                          "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Storage retention verification",                         "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "VMS + analytics commissioning",                          "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
            ]},
        ],
    },

    # ------------ 11. TV System Installation --------------------------
    "tv_system": {
        "name": "TV SYSTEM INSTALLATION",
        "sections": [
            {"letter": "A", "title": "TV SYSTEM", "subsection": "", "items": [
                {"desc": "TV head-end controller + IPTV server",                   "unit": "No.", "qty": 0, "basic": 0, "spec": "Per channel count"},
                {"desc": "STB / set-top box (per TV outlet)",                      "unit": "No.", "qty": 0, "basic": 0, "spec": "HD, HDMI out"},
            ]},
            {"letter": "B", "title": "TV OUTLETS", "subsection": "", "items": [
                {"desc": "F-type TV wall plate (single)",                          "unit": "No.", "qty": 0, "basic": 0, "spec": "Screened, BS 41003"},
                {"desc": "Combined TV + data outlet",                              "unit": "No.", "qty": 0, "basic": 0, "spec": "1-gang plate"},
            ]},
            {"letter": "C", "title": "COAXIAL CABLING", "subsection": "", "items": [
                {"desc": "RG6 coaxial cable (1.0/4.6 quad-shield)",                "unit": "m",   "qty": 0, "basic": 0, "spec": "75Ω, BS EN 50117"},
                {"desc": "F-type connector (compression)",                         "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "D", "title": "SPLITTERS", "subsection": "", "items": [
                {"desc": "2-way TV splitter (5-2400 MHz)",                         "unit": "No.", "qty": 0, "basic": 0, "spec": "Screened housing"},
                {"desc": "4-way TV splitter",                                      "unit": "No.", "qty": 0, "basic": 0, "spec": "Screened housing"},
                {"desc": "8-way TV splitter",                                      "unit": "No.", "qty": 0, "basic": 0, "spec": "Screened housing"},
            ]},
            {"letter": "E", "title": "AMPLIFIERS", "subsection": "", "items": [
                {"desc": "TV distribution amplifier (40 dB)",                      "unit": "No.", "qty": 0, "basic": 0, "spec": "Rack or wall-mount"},
                {"desc": "Channel processor / modulator",                          "unit": "No.", "qty": 0, "basic": 0, "spec": "Per channel"},
            ]},
            {"letter": "F", "title": "ANTENNA / DISH", "subsection": "", "items": [
                {"desc": "UHF / VHF terrestrial antenna",                          "unit": "No.", "qty": 0, "basic": 0, "spec": "Mast-mounted"},
                {"desc": "Satellite dish + LNB (1.2m)",                            "unit": "No.", "qty": 0, "basic": 0, "spec": "Wall or ground mount"},
                {"desc": "Antenna mast + lightning protection",                    "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "G", "title": "TESTING AND COMMISSIONING", "subsection": "", "items": [
                {"desc": "Per-outlet signal-level test",                           "unit": "No.", "qty": 0, "basic": 0, "spec": "65-75 dBμV"},
                {"desc": "Channel scan + program guide",                           "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
            ]},
        ],
    },

    # ------------ 12. IP Clock System Installation --------------------
    "ip_clock": {
        "name": "IP CLOCK SYSTEM INSTALLATION",
        "sections": [
            {"letter": "A", "title": "IP CLOCK SYSTEM", "subsection": "", "items": [
                {"desc": "NTP time-server (rack-mount, GPS-disciplined)",          "unit": "No.", "qty": 0, "basic": 0, "spec": "Stratum-1"},
                {"desc": "Clock management software (annual)",                     "unit": "Lot", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "B", "title": "MASTER CLOCK", "subsection": "", "items": [
                {"desc": "Master clock with PoE output",                           "unit": "No.", "qty": 0, "basic": 0, "spec": "Redundant"},
                {"desc": "GPS antenna + outdoor mount",                            "unit": "Set", "qty": 0, "basic": 0, "spec": "Roof-mounted"},
            ]},
            {"letter": "C", "title": "IP CLOCKS", "subsection": "", "items": [
                {"desc": "IP digital wall clock (PoE)",                            "unit": "No.", "qty": 0, "basic": 0, "spec": "12 / 24 hr"},
                {"desc": "IP analogue wall clock (PoE)",                           "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "IP double-sided clock (corridor)",                       "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "D", "title": "POE SWITCHES", "subsection": "", "items": [
                {"desc": "8-port PoE+ switch (clock VLAN)",                        "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "E", "title": "NETWORK CABLING", "subsection": "", "items": [
                {"desc": "Cat6 horizontal drop (per clock)",                       "unit": "m",   "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Surface back-box + bracket",                             "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "F", "title": "TESTING AND COMMISSIONING", "subsection": "", "items": [
                {"desc": "NTP synchronisation test (per clock)",                   "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "GPS lock verification",                                  "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
            ]},
        ],
    },

    # ------------ 13. Nurse Call System Installation ------------------
    "nurse_call": {
        "name": "NURSE CALL SYSTEM INSTALLATION",
        "sections": [
            {"letter": "A", "title": "NURSE CALL SYSTEM", "subsection": "", "items": [
                {"desc": "Nurse call master station + server",                     "unit": "No.", "qty": 0, "basic": 0, "spec": "BS HTM 08-03 compliant"},
                {"desc": "Reporting + audit software (annual)",                    "unit": "Lot", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "B", "title": "BEDHEAD UNITS", "subsection": "", "items": [
                {"desc": "Bedhead trunking + nurse-call socket",                   "unit": "No.", "qty": 0, "basic": 0, "spec": "Aluminium, hygiene-rated"},
                {"desc": "Pull-cord call point (en-suite)",                        "unit": "No.", "qty": 0, "basic": 0, "spec": "IP65"},
            ]},
            {"letter": "C", "title": "CALL POINTS", "subsection": "", "items": [
                {"desc": "Patient handset call point",                             "unit": "No.", "qty": 0, "basic": 0, "spec": "Reassurance LED + reset"},
                {"desc": "Staff assist call point",                                "unit": "No.", "qty": 0, "basic": 0, "spec": "Yellow, staff-only"},
                {"desc": "Emergency call point (cardiac arrest)",                  "unit": "No.", "qty": 0, "basic": 0, "spec": "Red, lockable reset"},
            ]},
            {"letter": "D", "title": "CORRIDOR INDICATORS", "subsection": "", "items": [
                {"desc": "Over-door indicator (multi-colour LED)",                 "unit": "No.", "qty": 0, "basic": 0, "spec": "Per bay"},
                {"desc": "Buzzer + audible repeater",                              "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "E", "title": "STAFF STATION DISPLAY", "subsection": "", "items": [
                {"desc": "Staff station LCD display",                              "unit": "No.", "qty": 0, "basic": 0, "spec": "Touch panel"},
                {"desc": "DECT pager / mobile handset",                            "unit": "No.", "qty": 0, "basic": 0, "spec": "Per staff member"},
            ]},
            {"letter": "F", "title": "NURSE CALL CABLING", "subsection": "", "items": [
                {"desc": "Nurse-call bus cable (per system spec)",                 "unit": "m",   "qty": 0, "basic": 0, "spec": "Manufacturer-approved"},
                {"desc": "Containment + back-boxes",                               "unit": "m",   "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "G", "title": "TESTING AND COMMISSIONING", "subsection": "", "items": [
                {"desc": "Per-bed call-flow test",                                 "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Cardiac-arrest escalation test",                         "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Staff training (clinical + facilities)",                 "unit": "Day", "qty": 0, "basic": 0, "spec": ""},
            ]},
        ],
    },

    # ------------ 14. Medical Equipment Electrical Installation -------
    "medical_equip": {
        "name": "MEDICAL EQUIPMENT ELECTRICAL INSTALLATION",
        "sections": [
            {"letter": "A", "title": "MEDICAL EQUIPMENT POWER", "subsection": "", "items": [
                {"desc": "Theatre / ICU sub-DB (medical, IP2X)",                   "unit": "No.", "qty": 0, "basic": 0, "spec": "BS HTM 06-01"},
                {"desc": "Medical-grade socket outlet (clean-power)",              "unit": "No.", "qty": 0, "basic": 0, "spec": "Red/Green colour-coded"},
            ]},
            {"letter": "B", "title": "UPS POWER WIRING", "subsection": "", "items": [
                {"desc": "Centralised medical UPS feed",                           "unit": "Item", "qty": 0, "basic": 0, "spec": "Sized per clinical demand"},
                {"desc": "Local UPS feed (per imaging suite)",                     "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "C", "title": "ESSENTIAL POWER WIRING", "subsection": "", "items": [
                {"desc": "Generator-backed essential-bus feed",                    "unit": "Item", "qty": 0, "basic": 0, "spec": "ATS-fed"},
                {"desc": "Critical-load isolator (per equipment)",                 "unit": "No.", "qty": 0, "basic": 0, "spec": "Lockable"},
            ]},
            {"letter": "D", "title": "ISOLATED POWER SUPPLY", "subsection": "Where applicable (Group 2 medical locations)", "items": [
                {"desc": "Isolating transformer (5/8/10 kVA)",                     "unit": "No.", "qty": 0, "basic": 0, "spec": "BS HTM 06-01 / IEC 61558-2-15"},
                {"desc": "Line isolation monitor (LIM)",                           "unit": "No.", "qty": 0, "basic": 0, "spec": "Audible + visual alarm"},
                {"desc": "Equipotential bus bar (clean earth)",                    "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "E", "title": "EQUIPOTENTIAL BONDING", "subsection": "", "items": [
                {"desc": "Equipotential bonding to all metallic parts",            "unit": "Lot", "qty": 0, "basic": 0, "spec": "BS HTM 06-01"},
                {"desc": "Bonding test point (clinical area)",                     "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "F", "title": "MEDICAL EQUIPMENT FINAL CONNECTIONS", "subsection": "", "items": [
                {"desc": "Final connection to MRI / CT (per OEM)",                 "unit": "Lot", "qty": 0, "basic": 0, "spec": "Per imaging OEM spec"},
                {"desc": "Final connection to surgical luminaire",                 "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Final connection to dialysis station",                   "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "G", "title": "TESTING AND COMMISSIONING", "subsection": "", "items": [
                {"desc": "LIM functional + alarm test",                            "unit": "Item", "qty": 0, "basic": 0, "spec": "Group 2 areas"},
                {"desc": "Equipotential resistance test (per outlet)",             "unit": "No.", "qty": 0, "basic": 0, "spec": "BS HTM 06-01"},
                {"desc": "Witness test with clinical engineering",                 "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
            ]},
        ],
    },

    # ------------ 15. Building Management System (BMS) ----------------
    # (15th service kept at owner's direction 2026-06-29 -- modelled after the
    # 14 spec services. Sections: head-end processors, AI/analytics, field
    # controllers, sensors, actuators, field wiring & terminals, BMS power,
    # network cabling & switches, workstations & licences, integrations, T&C.)
    "bms": {
        "name": "BUILDING MANAGEMENT SYSTEM (BMS)",
        "sections": [
            {"letter": "A", "title": "BMS HEAD-END PROCESSORS AND CENTRAL SERVERS", "subsection": "", "items": [
                {"desc": "BMS application server (rack-mount)",                    "unit": "No.", "qty": 0, "basic": 0, "spec": "Hot-spare / redundant"},
                {"desc": "BMS database server + storage",                          "unit": "No.", "qty": 0, "basic": 0, "spec": "RAID"},
                {"desc": "BMS point-licence pack (per 100 points)",                "unit": "Lot", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "B", "title": "AI / ANALYTICS CONTROLLERS", "subsection": "", "items": [
                {"desc": "AI/analytics edge gateway (fault detection + diagnostics)", "unit": "No.", "qty": 0, "basic": 0, "spec": "Energy optimisation"},
                {"desc": "Predictive-maintenance module (annual licence)",         "unit": "Lot", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Energy-management software pack",                        "unit": "Lot", "qty": 0, "basic": 0, "spec": "kWh dashboards + alerts"},
            ]},
            {"letter": "C", "title": "FIELD CONTROLLERS AND I/O MODULES", "subsection": "DDC", "items": [
                {"desc": "BACnet/IP DDC controller (32 UI / 16 UO)",               "unit": "No.", "qty": 0, "basic": 0, "spec": "Programmable"},
                {"desc": "BACnet MS/TP I/O module (8AI / 8DI / 8DO)",              "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Application-specific controller (VAV / FCU)",            "unit": "No.", "qty": 0, "basic": 0, "spec": "Pre-loaded VAV / FCU app"},
            ]},
            {"letter": "D", "title": "SENSORS", "subsection": "Temperature / humidity / CO2 / pressure / occupancy / air-quality", "items": [
                {"desc": "Duct temperature sensor (NTC10K)",                       "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Room temperature + setpoint sensor",                     "unit": "No.", "qty": 0, "basic": 0, "spec": "BACnet MS/TP"},
                {"desc": "Combined CO2 + temperature + humidity sensor",           "unit": "No.", "qty": 0, "basic": 0, "spec": "NDIR CO2"},
                {"desc": "Differential pressure sensor (air)",                     "unit": "No.", "qty": 0, "basic": 0, "spec": "0-500 Pa"},
                {"desc": "PIR occupancy sensor (BMS-linked)",                      "unit": "No.", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "E", "title": "ACTUATORS", "subsection": "Valves / dampers / VAV", "items": [
                {"desc": "Motorised damper actuator (24V, 5 Nm)",                  "unit": "No.", "qty": 0, "basic": 0, "spec": "Modulating, spring-return"},
                {"desc": "2-port motorised valve (DN50, modulating)",              "unit": "No.", "qty": 0, "basic": 0, "spec": "0-10 V"},
                {"desc": "VAV box damper actuator",                                "unit": "No.", "qty": 0, "basic": 0, "spec": "Belimo or equivalent"},
            ]},
            {"letter": "F", "title": "FIELD WIRING AND TERMINAL BLOCKS", "subsection": "", "items": [
                {"desc": "Belden 18 AWG shielded BMS bus cable",                   "unit": "m",   "qty": 0, "basic": 0, "spec": "BACnet MS/TP"},
                {"desc": "Multi-core control cable (per spec)",                    "unit": "m",   "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Wago / Phoenix terminal block kit",                      "unit": "Lot", "qty": 0, "basic": 0, "spec": "Spring-cage, DIN-rail"},
                {"desc": "Field control panel (IP55, lockable)",                   "unit": "No.", "qty": 0, "basic": 0, "spec": "Per floor"},
            ]},
            {"letter": "G", "title": "BMS POWER SYSTEMS", "subsection": "", "items": [
                {"desc": "24Vdc power supply (DIN-rail, 240W)",                    "unit": "No.", "qty": 0, "basic": 0, "spec": "Backup-ready"},
                {"desc": "BMS UPS (rack-mount, 1kVA)",                             "unit": "No.", "qty": 0, "basic": 0, "spec": "30 min runtime"},
                {"desc": "Dedicated BMS sub-DB feed",                              "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "H", "title": "BMS NETWORK CABLING AND SWITCHES", "subsection": "", "items": [
                {"desc": "BMS VLAN PoE switch (16-port)",                          "unit": "No.", "qty": 0, "basic": 0, "spec": "L2 managed"},
                {"desc": "Cat6 horizontal drop (BMS controller)",                  "unit": "m",   "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Fibre uplink (multimode)",                               "unit": "m",   "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "I", "title": "OPERATOR WORKSTATIONS AND SOFTWARE LICENCES", "subsection": "", "items": [
                {"desc": "BMS operator workstation (dual-screen)",                 "unit": "No.", "qty": 0, "basic": 0, "spec": "i7, 16GB, SSD"},
                {"desc": "Operator graphics + dashboards (licence)",               "unit": "Lot", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Mobile / web client licence",                            "unit": "Lot", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "J", "title": "INTEGRATION WITH HVAC, LIGHTING, FIRE ALARM, ACCESS CONTROL", "subsection": "", "items": [
                {"desc": "BACnet / Modbus integration to HVAC plant",              "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "DALI / KNX integration to lighting control",             "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Fire-alarm interface (volt-free contacts + BACnet)",     "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Access-control / CCTV interface",                        "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
            ]},
            {"letter": "K", "title": "TESTING AND COMMISSIONING", "subsection": "", "items": [
                {"desc": "Point-to-point I/O verification",                        "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Control-loop tuning + commissioning",                    "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Witness test with M&E commissioning team",               "unit": "Item", "qty": 0, "basic": 0, "spec": ""},
                {"desc": "Operator training + handover",                           "unit": "Day", "qty": 0, "basic": 0, "spec": ""},
            ]},
        ],
    },

}


# ---------------------------------------------------------------------------
# 5. Helpers
# ---------------------------------------------------------------------------

def _services_csv_to_list(csv: str) -> list:
    """Split boq_projects.services_csv into a clean list of KNOWN codes.

    Applies the legacy migration map (e.g. ``it_network`` -> ``lan_wlan`` +
    ``it_server_room``). Unknown codes are silently dropped. Order is
    preserved; duplicates removed.
    """
    if not csv:
        return []
    out, seen = [], set()
    for tok in (csv or "").split(","):
        t = tok.strip()
        if not t:
            continue
        # Apply legacy expansion first.
        new_codes = _BOQ_SERVICE_LEGACY_MAP.get(t, [t])
        for c in new_codes:
            if c in _BOQ_SERVICE_LABEL and c not in seen:
                seen.add(c)
                out.append(c)
    return out


def _services_label_list(codes: list) -> list:
    """Map a list of service codes to their human labels (order preserved)."""
    return [_BOQ_SERVICE_LABEL[c] for c in codes if c in _BOQ_SERVICE_LABEL]


def _services_loaded_sections(codes: list) -> list:
    """Return the flat 'Loaded BOQ Sections:' preview for the UI panel.

    Each entry is a dict::

        {"bill_no", "bill_name", "section_letter", "section_title", "subsection"}

    Bill numbers are assigned 1..N in the order codes were selected so the
    preview matches what will be inserted into ``boq_floor_items``.
    """
    out = []
    for bill_no, code in enumerate((c for c in codes if c in _BOQ_SERVICE_BILL_SKELETON), start=1):
        skel = _BOQ_SERVICE_BILL_SKELETON[code]
        for sec in skel["sections"]:
            out.append({
                "bill_no":        bill_no,
                "bill_name":      skel["name"],
                "section_letter": sec["letter"],
                "section_title":  sec["title"],
                "subsection":     sec.get("subsection", ""),
                "service_code":   code,
            })
    return out


def _services_section_rows(codes: list) -> list:
    """Return the list of rows to insert into ``boq_floor_items`` for the
    selected services. Each row carries ``bill_no``, ``bill_name``,
    ``section_letter``, ``section_title``, ``subsection_label`` plus the
    item fields (``desc``, ``unit``, ``qty``, ``basic``, ``spec``)."""
    out = []
    for bill_no, code in enumerate((c for c in codes if c in _BOQ_SERVICE_BILL_SKELETON), start=1):
        skel = _BOQ_SERVICE_BILL_SKELETON[code]
        for sec in skel["sections"]:
            for item in sec.get("items", []):
                out.append({
                    "bill_no":          bill_no,
                    "bill_name":        skel["name"],
                    "section_letter":   sec["letter"],
                    "section_title":    sec["title"],
                    "subsection_label": sec.get("subsection", ""),
                    "service_code":     code,
                    "desc":             item["desc"],
                    "unit":             item["unit"],
                    "qty":              item["qty"],
                    "basic":            item["basic"],
                    "spec":             item.get("spec", ""),
                })
    return out


def _infer_services_from_bill_names(bill_names: list) -> list:
    """Infer service codes from a list of existing bill names (used to
    auto-populate ``services_csv`` for pre-refactor projects on first read).

    Order preserved, duplicates removed. Returns ``[]`` if no bill matched.
    """
    out, seen = [], set()
    for name in bill_names or []:
        up = (name or "").upper()
        for needle, svc_list in _BOQ_BILL_TO_SERVICES:
            if needle in up:
                for s in svc_list:
                    if s in _BOQ_SERVICE_LABEL and s not in seen:
                        seen.add(s)
                        out.append(s)
    return out


def _ensure_project_migrated_to_v3(c, project_id: int) -> tuple:
    """Silent auto-migration of a single ``boq_projects`` row to the unified
    BOQ engine (2026-06-29 refactor). Called at the top of every project-read
    route. Idempotent.

    Steps:
      1. SELECT services_csv, build_mode FROM boq_projects.
      2. If services_csv contains LEGACY codes, expand via _services_csv_to_list.
      3. If services_csv is empty, infer from DISTINCT bill_name across the
         project's existing boq_floor_items rows.
      4. If build_mode is NULL/empty, set to 'complete_boq'.
      5. UPDATE the row if anything changed; return (services_list, build_mode).

    No-op if the project is already on the new schema with a non-legacy
    services_csv. Returns the final (services_list, build_mode) either way.
    """
    try:
        c.execute(
            "SELECT services_csv, build_mode FROM boq_projects WHERE id = ?",
            (project_id,),
        )
        row = c.fetchone()
    except Exception:
        return ([], "complete_boq")
    if not row:
        return ([], "complete_boq")

    raw_csv = (row[0] or "") if not hasattr(row, "keys") else (row["services_csv"] or "")
    raw_mode = (row[1] or "") if not hasattr(row, "keys") else (row["build_mode"] or "")
    # Normalise via the legacy expander.
    services = _services_csv_to_list(raw_csv)

    # If still empty, infer from existing bill names on this project.
    if not services:
        try:
            c.execute(
                "SELECT DISTINCT bill_name FROM boq_floor_items WHERE project_id = ?",
                (project_id,),
            )
            bill_names = [r[0] if not hasattr(r, "keys") else r["bill_name"] for r in c.fetchall()]
        except Exception:
            bill_names = []
        services = _infer_services_from_bill_names(bill_names)

    build_mode = raw_mode.strip().lower() or "complete_boq"
    if build_mode not in ("section_by_section", "complete_boq"):
        build_mode = "complete_boq"

    new_csv = ",".join(services)
    if new_csv != raw_csv or build_mode != raw_mode:
        try:
            c.execute(
                "UPDATE boq_projects SET services_csv = ?, build_mode = ? WHERE id = ?",
                (new_csv, build_mode, project_id),
            )
        except Exception:
            pass

    return (services, build_mode)


# === END: boq_services_engine splice ===
