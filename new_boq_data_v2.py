# new_boq_data_v2.py
# 2026-06-21 -- rewrites both the section grid catalogue and the project
# templates with three owner-driven changes:
#
#   1. Descriptions follow the auditorium sample format:
#         <instruction verb> <product description> as <brand> or approved equal
#      e.g. "Supply and install 6-way TPN MCCB Distribution Panel Board
#            c/w 400A Incomer as Memshield or approved equal"
#
#   2. Every template's Bill 2 (Internal Electrical Wiring) starts with
#      Switch Boards (Section A) and immediately follows with Subfeeder
#      Cables and Earth Leads (Section B). The owner specified this is
#      mandatory across all templates.
#
#   3. New "residence-typical" template for single-family residential
#      installations -- the missing residential primary-purpose template.
#
# This file is sourced after new_boq_section_grid_routes.py and
# new_boq_project_templates.py in the splice order, and overrides their
# data dicts at runtime.


# ===========================================================================
# SECTION GRID CATALOGUE -- pre-loaded dropdown items per section
# ===========================================================================

_BOQ_SECTION_ITEM_CATALOG = {

    # ----- Bill 2 ----------------------------------------------------------
    "SWITCH BOARDS AND DISTRIBUTION BOARDS": [
        ("Supply and install 6-way TPN MCCB Distribution Panel Board c/w 400A Incomer as Memshield or approved equal", "Nos.", 19800),
        ("Supply and install 6-way TPN MCB Distribution Board c/w 200A INT. switch as Memshield or approved equal",    "Nos.", 15500),
        ("Supply and install 6-way TPN MCB Distribution Board c/w 125A INT. switch as Memshield or approved equal",    "Nos.",  8500),
        ("Supply and install 6-way TPN MCB Distribution Board c/w 100A INT. switch as Memshield or approved equal",    "Nos.",  6800),
        ("Supply and install 6-way TPN MCB Distribution Board c/w 63A INT. switch as Memshield or approved equal",     "Nos.",  3308.81),
        ("Supply and install 6-way TPN MCB Distribution Board c/w 32A INT. switch as Memshield or approved equal",     "Nos.",  3309.81),
        ("Supply and install 4-way TPN MCB Distribution Board c/w 32A INT. switch as Memshield or approved equal",     "Nos.",  3200),
        ("Supply and install 8-way SPN MCB Distribution Board c/w 63A INT. switch as Memshield or approved equal",     "Nos.",  2800),
        ("Supply and install 12-way SPN MCB Distribution Board c/w 100A INT. switch as Memshield or approved equal",   "Nos.",  4200),
        ("Supply and install 400A TPN Fuse Switch as Memshield or approved equal",                                     "Nos.", 12160),
        ("Supply and install 200A TPN Fuse Switch as Memshield or approved equal",                                     "Nos.",  6700),
        ("Supply and install 125A TPN Fuse Switch as Memshield or approved equal",                                     "Nos.",  4600),
        ("Supply and install 100A TPN load Isolator as Memshield or approved equal",                                   "Nos.",  1470),
        ("Supply and install 63A TPN load Isolator as Memshield or approved equal",                                    "Nos.",   900),
        ("Supply and install 32A TPN load Isolator as Memshield or approved equal",                                    "Nos.",   650),
    ],

    "SUBFEEDER CABLES AND EARTHLEADS": [
        ("Supply, lay and connect 4c x 240mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal", "M", 3849),
        ("Supply, lay and connect 4c x 185mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal", "M", 2900),
        ("Supply, lay and connect 4c x 150mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal", "M", 2500),
        ("Supply, lay and connect 4c x 120mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal", "M", 2242.80),
        ("Supply, lay and connect 4c x 95mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",  "M", 1850),
        ("Supply, lay and connect 4c x 70mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",  "M", 1100),
        ("Supply, lay and connect 4c x 50mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",  "M",  651),
        ("Supply, lay and connect 4c x 35mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",  "M",  470),
        ("Supply, lay and connect 4c x 25mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",  "M",  290),
        ("Supply, lay and connect 4c x 16mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",  "M",  190),
        ("Supply, lay and connect 4c x 10mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",  "M",  125),
        ("Supply, lay and connect 1c x 240mm2 PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",     "M",  780),
        ("Supply, lay and connect 1c x 185mm2 PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",     "M",  560),
        ("Supply, lay and connect 1c x 120mm2 PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",     "M",  400),
        ("Supply, lay and connect 1c x 95mm2 PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",      "M",  350),
        ("Supply, lay and connect 1c x 70mm2 PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",      "M",  298),
        ("Supply, lay and connect 1c x 50mm2 PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",      "M",  170),
        ("Supply, lay and connect 1c x 35mm2 PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",      "M",  120),
        ("Supply, lay and connect 1c x 25mm2 PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",      "M",   65),
        ("Supply, lay and connect 1c x 16mm2 PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",      "M",   42),
        ("Supply, lay and connect 1c x 10mm2 PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",      "M",   27),
        ("Supply and install 1500mm copper earth rod, buried 1.5m below ground with soil treatment",                                    "Set",1200),
        ("Supply, lay and connect 1c x 240mm2 bare copper cable as earth jumper c/w accessories",                                       "M",  700),
    ],

    "WIRING OF POINTS": [
        ("Wire the following point in conduit / trunking using 1.5mm2 PVC insulated copper cable (Brown)",         "Coils", 391),
        ("Wire the following point in conduit / trunking using 1.5mm2 PVC insulated copper cable (Blue)",          "Coils", 391),
        ("Wire the following point in conduit / trunking using 1.5mm2 PVC insulated copper cable (Grey)",          "Coils", 391),
        ("Wire the following point in conduit / trunking using 1.5mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 391),
        ("Wire the following point in conduit / trunking using 2.5mm2 PVC insulated copper cable (Brown)",         "Coils", 653),
        ("Wire the following point in conduit / trunking using 2.5mm2 PVC insulated copper cable (Blue)",          "Coils", 653),
        ("Wire the following point in conduit / trunking using 2.5mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 653),
        ("Wire the following point in conduit / trunking using 4.0mm2 PVC insulated copper cable (Brown)",         "Coils", 1037),
        ("Wire the following point in conduit / trunking using 4.0mm2 PVC insulated copper cable (Blue)",          "Coils", 1037),
        ("Wire the following point in conduit / trunking using 4.0mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 1037),
        ("Wire the following point in conduit / trunking using 6.0mm2 PVC insulated copper cable (Brown)",         "Coils", 1500),
        ("Wire the following point in conduit / trunking using 6.0mm2 PVC insulated copper cable (Blue)",          "Coils", 1500),
        ("Wire the following point in conduit / trunking using 6.0mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 1500),
        ("Supply and install 20mm diameter PVC conduit pipe",                                                       "Nos.",   14.63),
        ("Supply and install 25mm diameter PVC conduit pipe",                                                       "Nos.",   19.50),
        ("Supply and install 32mm diameter PVC conduit pipe",                                                       "Nos.",   28.00),
        ("Supply and install 75mm x 75mm steel conduit boxes",                                                      "Nos.",   13),
        ("Supply and install 150mm x 75mm steel conduit boxes",                                                     "Nos.",   18),
        ("Supply and install circular boxes of various ways",                                                       "Nos.",    5),
        ("Supply and install junction boxes",                                                                       "Nos.",    8),
    ],

    "LUMINAIRES": [
        ("Supply and fix 35W Round Recessed downlighter as Philips or approved equal",                                          "Nos.",  550),
        ("Supply and fix 40W 230V 50Hz 600x600mm LED recessed FL light fitting c/w driver as Philips or approved equal",        "Nos.",  599),
        ("Supply and fix 36W 1200mm LED linear Panel light c/w enclosure as Philips or approved equal",                         "Nos.",  707.01),
        ("Supply and fix 36W 1200mm LED linear Panel light as Philips or approved equal",                                       "Nos.",  372),
        ("Supply and fix 36W Round surface panel light as Philips or approved equal",                                           "Nos.",  550),
        ("Supply and fix 18W LED round surface panel light as Philips or approved equal",                                       "Nos.",  305),
        ("Supply and fix 18W LED round recessed panel light as Philips or approved equal",                                      "Nos.",  310),
        ("Supply and fix 12W LED round surface panel light as Philips or approved equal",                                       "Nos.",  226),
        ("Supply and fix 87W LED round high bay 230V 50Hz light as Philips or approved equal",                                  "Nos.", 1100),
        ("Supply and fix LED Strip light as Philips or approved equal",                                                          "Coil",   35),
        ("Supply and fix Emergency exit luminaire c/w battery backup as Philips or approved equal",                              "Nos.",  480),
        ("Supply and fix Outdoor wall-mounted LED floodlight 50W IP65 as Philips or approved equal",                            "Nos.",  380),
    ],

    "ACCESSORIES": [
        ("Supply and fix 6A One Way One gang light switch as MK or approved equal",                                                 "Nos.",  20.73),
        ("Supply and fix 6A One Way two gang light switch as MK or approved equal",                                                 "Nos.",  34.13),
        ("Supply and fix 6A One Way three gang light switch as MK or approved equal",                                               "Nos.",  51.52),
        ("Supply and fix 6A two Way one gang light switch as MK or approved equal",                                                 "Nos.",  23.16),
        ("Supply and fix 6A two Way two gang light switch as MK or approved equal",                                                 "Nos.",  35),
        ("Supply and fix 6A two Way three gang light switch as MK or approved equal",                                               "Nos.",  55),
        ("Supply and fix 6 Compartment floor box c/w 2 double sockets + 2 double data outlet as MK or approved equal",              "Nos.", 2100),
        ("Supply and fix 1 x 13A unswitched Socket outlet as MK or approved equal",                                                 "Nos.",  40),
        ("Supply and fix 2 x 13A Switched Socket outlet as MK or approved equal",                                                   "Nos.",  60),
        ("Supply and fix 2 x 13A Switched Socket outlet with light + red colour as MK or approved equal",                           "Nos.",  74),
        ("Supply and fix 2 x 13A USB Socket outlet as MK or approved equal",                                                        "Nos.",  95),
        ("Supply and fix 20A DP switch with neon indicator as MK or approved equal",                                                "Nos.",  35),
        ("Supply and fix Plastic Automatic Hand Dryer",                                                                              "Nos.", 1250),
        ("Supply and fix Weatherproof IP65 socket outlet as MK or approved equal",                                                  "Nos.", 110),
    ],

    # ----- Bill 3 -- BONDING AND EARTHING -----------------------------------
    "BONDING AND EARTHING": [
        ("Supply and lay 70mm2 bare copper conductor to fully contact the earth and treat",                                "M",    289),
        ("Supply and vertically lay 50mm2 bare copper conductor as connecting electrode",                                  "M",    133),
        ("Supply and lay 35mm2 bare copper conductor",                                                                     "M",    120),
        ("Supply and fix holding rings made of galvanised steel",                                                          "Nos.",  20.30),
        ("Supply, fix and connect equalisation bar c/w 8 studs and connecting accessories",                                "Nos.", 548.55),
        ("Supply and install 6x6 IP65 grounding junction box 20cm above finished floor level",                             "Nos.",  36.57),
        ("Supply, fix and install 3x3 square box",                                                                         "Nos.",  13),
        ("Perform Arc welding as mechanical attaching taps",                                                               "Pts.", 135),
        ("Perform Exothermic welding",                                                                                     "Nos.", 750),
        ("Supply and install 600mm x 600mm copper earth mat c/w 1500mm copper earth rod",                                  "Nos.", 1700),
        ("Supply and install warning tape (yellow/green)",                                                                 "Nos.",  150),
        ("Supply and install standard 1.5M high graded copper earth rod",                                                  "Nos.", 1200),
        ("Test the installation using scripts from the electrical engineer",                                               "Lot",  5000),
        ("Supply and install concrete inspection chamber with cover",                                                      "Nos.",  457.13),
        ("Supply and lay stranded 35mm2 copper bare cable",                                                                "M",    120),
    ],

    "EARTH ELECTRODE NETWORK": [
        ("Supply and install 1500mm copper earth rod, buried 1.5m below ground with soil treatment",                       "Set",  1200),
        ("Supply and install prefabricated earth inspection chamber with lid",                                             "No.",   457.13),
        ("Supply, lay and connect 1c x 240mm2 bare copper cable as earth jumper c/w accessories",                          "M",     700),
        ("Supply and install 6x6 IP65 junction box",                                                                       "M",      36.57),
        ("Supply and install earth tape clamp",                                                                            "Nos.",   45),
    ],

    # ----- Bill 4 -- FIRE ALARM ---------------------------------------------
    "WIRING OF FIRE POINTS": [
        ("Supply, lay and connect 3c x 2.5mm2 red fire-resistant network detection cable drawn and looped",                "M",   30),
        ("Supply and install 20mm diameter self-extinguishing thermoplastic conduit pipe",                                 "Nos.",14.63),
        ("Supply and install 75mm x 75mm steel conduit boxes",                                                             "Nos.",13),
        ("Supply and install circular boxes of various ways",                                                              "Nos.", 5),
    ],

    "FIRE PANEL AND ACCESSORIES": [
        ("Supply, install, connect and commission Addressable optical Smoke detector as Hochiki or approved equal",                                    "Nos.",  532),
        ("Supply, install, connect and commission Addressable heat detector as Hochiki or approved equal",                                             "Nos.",  580),
        ("Supply, install, connect and commission Break glass call point as Hochiki or approved equal",                                                "Nos.",  600),
        ("Supply, install, connect and commission Fire Alarm Beacon/Sounder indoor with strobe as Hochiki or approved equal",                          "Nos.",  980),
        ("Supply, install, connect and commission Outdoor Weatherproof siren c/w strobe as Hochiki or approved equal",                                 "Nos.",  980),
        ("Supply and install Fire Alarm Junction Box",                                                                                                 "Nos.",  250),
        ("Supply, install, connect and commission 8 Zone Addressable Fire Alarm Control Panel inc LCD module and Control Keys as Hochiki or approved equal", "Nos.", 53640),
        ("Supply, install, connect and commission 4 Zone Conventional Fire Alarm Control Panel as Hochiki or approved equal",                          "Nos.", 8500),
        ("Supply and install Fire Exit Sign",                                                                                                          "Nos.",  120),
        ("Supply and install Emergency Fire Bell",                                                                                                     "Nos.",  450),
    ],

    # ----- Bill 5 -- DATA & VOICE -------------------------------------------
    "DATA EQUIPMENT AND ACCESSORIES": [
        ("Supply, lay and connect Cat 6e UTP Data cable",                                                                       "Coils",1650),
        ("Supply and install 48 Port CAT 6 patch panel",                                                                        "Nos.", 1500),
        ("Supply, install and commission 48 port CAT 6 Switch w/ 1GB fibre optic uplink as Cisco / Juniper or approved equal",  "Nos.", 2300),
        ("Supply, install and commission 24 port CAT 6 Switch w/ 1GB fibre optic uplink as Cisco / Juniper or approved equal",  "Nos.", 1800),
        ("Supply and install Fibre patch",                                                                                       "Nos.",  850),
        ("Supply and install 12U Data network cabinet",                                                                          "Nos.", 1600),
        ("Supply, lay and connect OM3 Laser-Optimized Multimode Aqua fibre optic cable",                                         "M",      52),
        ("Supply and install RJ45 double data outlet c/w faceplate, insert and mounting screws as MK or approved equal",         "Nos.",  104),
        ("Supply and install Power strip",                                                                                       "Nos.",  150),
        ("Supply Patch cord 1m CAT 6",                                                                                           "Nos.",   45),
        ("Supply Patch cord 2m CAT 6",                                                                                           "Nos.",   65),
    ],

    "VOICE EQUIPMENT AND ACCESSORIES": [
        ("Supply, install and commission IP desk phone",                 "Nos.",  650),
        ("Supply, install and commission Wireless DECT base + handset",  "Nos.", 1200),
        ("Supply, lay and connect voice cabling (Cat 6e)",               "Coils",1650),
        ("Supply and install voice patch panel 24-port",                 "Nos.", 1100),
    ],

    # ----- Bill 6 -- SIGNAL COMMS -------------------------------------------
    "EQUIPMENT AND ACCESSORIES": [
        ("Supply, install and commission IP Cam dome 100m, 180-degree view with night vision and motion detection as Panasonic or approved equal","Nos.",  865),
        ("Supply, install and commission IP Cam bullet IR 30m, outdoor IP67 as Panasonic or approved equal",                                       "Nos.", 1050),
        ("Supply, install and connect circular ceiling recessed audio speakers as Panasonic or approved equal",                                    "Nos.",  260),
        ("Supply, install and connect wall mounted audio speakers as Panasonic or approved equal",                                                 "Nos.",  400),
        ("Supply and install Power strip",                                                                                                          "Nos.",  150),
        ("Supply, install and commission Building/Zonal IP audio amplifier as Panasonic or approved equal",                                        "M",   4900),
        ("Supply, lay and connect 20m AV cables -- building MIC to zonal amp",                                                                     "M",     19),
        ("Supply, lay and connect audio speaker cables (pair)",                                                                                     "M",      3),
        ("Supply, install and commission Network video recorder (NVR) 8-channel as Hikvision or approved equal",                                   "Nos.", 5500),
        ("Supply, install and commission Network video recorder (NVR) 16-channel as Hikvision or approved equal",                                  "Nos.", 8800),
        ("Supply, install and commission Access control reader as HID or approved equal",                                                          "Nos.", 1850),
        ("Supply, install and commission Electromagnetic door lock",                                                                                "Nos.", 1200),
    ],

    # ----- Bill 1 -- PRELIMINARIES ------------------------------------------
    "PRELIMINARY ITEMS": [
        ("Allow for site mobilisation and setup",                            "Lot", 25000),
        ("Allow for site insurance",                                         "Lot", 15000),
        ("Allow for project manager presence on site",                       "Mth",  8500),
        ("Allow for site engineer presence on site",                         "Mth",  7000),
        ("Allow for health & safety provisions",                             "Lot",  6500),
        ("Allow for site office accommodation",                              "Mth",  3500),
        ("Allow for tools and small plant",                                  "Lot",  4500),
        ("Allow for final commissioning and handover",                       "Lot",  8000),
    ],
}


def _boq_catalog_for_section(section_title: str) -> list:
    if not section_title:
        return []
    s = section_title.strip()
    if s in _BOQ_SECTION_ITEM_CATALOG:
        return list(_BOQ_SECTION_ITEM_CATALOG[s])
    if s.upper() in _BOQ_SECTION_ITEM_CATALOG:
        return list(_BOQ_SECTION_ITEM_CATALOG[s.upper()])
    s_up = s.upper()
    for key, items in _BOQ_SECTION_ITEM_CATALOG.items():
        if s_up.startswith(key) or key.startswith(s_up):
            return list(items)
    return []


# ===========================================================================
# WHOLE-FLOOR PROJECT TEMPLATES
# Each template's Bill 2 starts: A. Switch Boards -> B. Subfeeder Cables
# (mandatory ordering per owner directive).
# Descriptions follow <verb> <product> as <brand> or approved equal.
# ===========================================================================

def _it(desc, unit, qty, basic, spec=""):
    return {"desc": desc, "unit": unit, "qty": qty, "basic": basic, "spec": spec}


# Common section helpers used across templates
_COMMON_SUBFEEDER = [
    _it("Supply, lay and connect 4c x 16mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal", "M",  60,   190),
    _it("Supply, lay and connect 4c x 10mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal", "M",  40,   125),
    _it("Supply, lay and connect 1c x 16mm2 PVC Insulated copper cable as earth lead",                                                  "M",  40,    42),
    _it("Supply, lay and connect 1c x 10mm2 PVC Insulated copper cable as earth lead",                                                  "M",  40,    27),
]

_BOQ_PROJECT_TEMPLATES = {

    # ============== AUDITORIUM (1UGLS reference) ============================
    "auditorium-1ugls": {
        "name":        "Auditorium -- full reference (1UGLS-style)",
        "purpose":     "commercial",
        "subtype":     "Auditorium",
        "description": "Mirrors the 1UGLS Auditorium electrical BOQ -- 6 bills, ~95 items. Use as a starting point for any auditorium / school hall / lecture-theatre project.",
        "bills": [
            {"no": 1, "name": "PRELIMINARIES", "sections": [
                {"letter": "A", "title": "PRELIMINARY ITEMS", "subsection": "", "items": [
                    _it("Allow for site mobilisation and setup",         "Lot",  1, 25000),
                    _it("Allow for site insurance",                      "Lot",  1, 15000),
                    _it("Allow for project manager presence on site",    "Mth",  4,  8500),
                    _it("Allow for site engineer presence on site",      "Mth",  4,  7000),
                    _it("Allow for health & safety provisions",          "Lot",  1,  6500),
                    _it("Allow for site office accommodation",           "Mth",  4,  3500),
                    _it("Allow for tools and small plant",               "Lot",  1,  4500),
                    _it("Allow for final commissioning and handover",    "Lot",  1,  8000),
                ]},
            ]},
            {"no": 2, "name": "INTERNAL ELECTRICAL WIRING", "sections": [
                {"letter": "A", "title": "SWITCH BOARDS AND DISTRIBUTION BOARDS", "subsection": "", "items": [
                    _it("Supply and install 6-way TPN MCCB Distribution Panel Board c/w 400A Incomer as Memshield or approved equal", "Nos.", 1, 19800),
                    _it("Supply and install 6-way TPN MCB Distribution Board c/w 200A INT. switch as Memshield or approved equal",    "Nos.", 1, 15500),
                    _it("Supply and install 6-way TPN MCB Distribution Board c/w 63A INT. switch as Memshield or approved equal",     "Nos.", 1,  3308.81),
                    _it("Supply and install 6-way TPN MCB Distribution Board c/w 32A INT. switch as Memshield or approved equal",     "Nos.", 1,  3309.81),
                    _it("Supply and install 4-way TPN MCB Distribution Board c/w 32A INT. switch as Memshield or approved equal",     "Nos.", 1,  3200),
                    _it("Supply and install 200A TPN Fuse Switch as Memshield or approved equal",                                     "Nos.", 1,  6700),
                    _it("Supply and install 400A TPN Fuse Switch as Memshield or approved equal",                                     "Nos.", 1, 12160),
                    _it("Supply and install 125A TPN Fuse Switch as Memshield or approved equal",                                     "Nos.", 1,  4600),
                    _it("Supply and install 100A TPN load Isolator as Memshield or approved equal",                                   "Nos.", 3,  1470),
                    _it("Supply and install 63A TPN load Isolator as Memshield or approved equal",                                    "Nos.", 3,   900),
                ]},
                {"letter": "B", "title": "SUBFEEDER CABLES AND EARTHLEADS", "subsection": "", "items": [
                    _it("Supply, lay and connect 4c x 240mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal", "M", 120, 3849),
                    _it("Supply, lay and connect 1c x 120mm2 PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",     "M",  10,  400),
                    _it("Supply, lay and connect 4c x 120mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal", "M", 120, 2242.80),
                    _it("Supply, lay and connect 1c x 70mm2 PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",      "M",  10,  298),
                    _it("Supply, lay and connect 4c x 50mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",  "M", 120,  651),
                    _it("Supply, lay and connect 1c x 25mm2 PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",      "M",  10,   65),
                    _it("Supply, lay and connect 1c x 16mm2 PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",      "M",  70,   42),
                    _it("Supply, lay and connect 4c x 16mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",  "M", 145,  190),
                    _it("Supply, lay and connect 4c x 10mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",  "M",  20,  125),
                    _it("Supply, lay and connect 1c x 10mm2 PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",      "M",  20,   27),
                    _it("Supply, lay and connect 4c x 25mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal",  "M", 135,  290),
                ]},
                {"letter": "C", "title": "WIRING OF POINTS", "subsection": "I. Light and fan points", "items": [
                    _it("Wire light/fan points using 1.5mm2 PVC insulated copper cable (Brown)", "Coils", 30, 391),
                    _it("Wire light/fan points using 1.5mm2 PVC insulated copper cable (Blue)",  "Coils", 35, 391),
                    _it("Wire light/fan points using 1.5mm2 PVC insulated copper cable (Grey)",  "Coils", 33, 391),
                    _it("Supply and install 20mm diameter PVC conduit pipe",                     "Nos.", 578, 14.63),
                    _it("Supply and install 75mm x 75mm steel conduit boxes",                    "Nos.", 467, 13),
                    _it("Supply and install circular boxes of various ways",                     "Nos.",  50,  5),
                ]},
                {"letter": "C", "title": "WIRING OF POINTS", "subsection": "II. 13A socket points and hand dryer", "items": [
                    _it("Wire 13A socket points using 2.5mm2 PVC insulated copper cable (Brown)",         "Coils",  5, 653),
                    _it("Wire 13A socket points using 2.5mm2 PVC insulated copper cable (Blue)",          "Coils",  5, 653),
                    _it("Wire 13A socket points using 2.5mm2 PVC insulated copper cable (Yellow/Green)",  "Coils",  5, 653),
                    _it("Supply and install 20mm diameter PVC conduit pipe",                              "Nos.", 156, 14.63),
                    _it("Supply and install 150mm x 75mm steel conduit boxes",                            "Nos.",  20, 18),
                ]},
                {"letter": "D", "title": "LUMINAIRES", "subsection": "", "items": [
                    _it("Supply and fix 35W Round Recessed downlighter as Philips or approved equal",                          "Nos.", 53,  550),
                    _it("Supply and fix 36W 1200mm LED linear Panel light c/w enclosure as Philips or approved equal",         "Nos.", 10,  707.01),
                    _it("Supply and fix 36W 1200mm LED linear Panel light as Philips or approved equal",                       "Nos.",  4,  372),
                    _it("Supply and fix 18W LED round surface panel light as Philips or approved equal",                       "Nos.", 17,  305),
                    _it("Supply and fix 12W LED round surface panel light as Philips or approved equal",                       "Nos.", 20,  226),
                    _it("Supply and fix LED Strip light as Philips or approved equal",                                          "Coil",  1,   35),
                ]},
                {"letter": "E", "title": "ACCESSORIES", "subsection": "", "items": [
                    _it("Supply and fix 6A One Way One gang light switch as MK or approved equal",                                                  "Nos.", 22, 20.73),
                    _it("Supply and fix 6A One Way two gang light switch as MK or approved equal",                                                  "Nos.",  4, 34.13),
                    _it("Supply and fix 6A two Way one gang light switch as MK or approved equal",                                                  "Nos.", 12, 23.16),
                    _it("Supply and fix 6A two Way two gang light switch as MK or approved equal",                                                  "Nos.",  1, 35),
                    _it("Supply and fix 6 Compartment floor box c/w 2 double sockets + 2 double data outlet as MK or approved equal",               "Nos.", 29, 2100),
                    _it("Supply and fix 1 x 13A unswitched Socket outlet as MK or approved equal",                                                  "Nos.",  5, 40),
                    _it("Supply and fix 2 x 13A Switched Socket outlet as MK or approved equal",                                                    "Nos.",  6, 60),
                    _it("Supply and fix Plastic Automatic Hand Dryer",                                                                              "Nos.",  2, 1250),
                ]},
            ]},
            {"no": 3, "name": "BONDING AND EARTHING", "sections": [
                {"letter": "A", "title": "BONDING AND EARTHING", "subsection": "", "items": [
                    _it("Supply and lay 70mm2 bare copper conductor to fully contact the earth and treat",          "M",    138,  289),
                    _it("Supply and vertically lay 50mm2 bare copper conductor as connecting electrode",            "M",     35,  133),
                    _it("Supply and fix holding rings made of galvanised steel",                                    "Nos.",   7,   20.30),
                    _it("Supply, fix and connect equalisation bar c/w 8 studs and connecting accessories",          "Nos.",   3,  548.55),
                    _it("Supply and install 6x6 IP65 grounding junction box 20cm above finished floor level",       "Nos.",   3,   36.57),
                    _it("Supply and install 3x3 square box",                                                        "Nos.",   3,   13),
                    _it("Perform Arc welding as mechanical attaching taps",                                         "Pts.",  80,  135),
                    _it("Perform Exothermic welding",                                                               "Nos.",  20,  750),
                    _it("Supply and install 600mm x 600mm copper earth mat c/w 1500mm copper earth rod",            "Nos.",   7, 1700),
                    _it("Supply and install warning tape (yellow/green)",                                           "Nos.",   3,  150),
                    _it("Supply and install standard 1.5M high graded copper earth rod",                            "Nos.",   7, 1200),
                    _it("Test the installation using scripts from the electrical engineer",                         "Lot",    1, 5000),
                    _it("Supply and install concrete inspection chamber with cover",                                "Nos.",   1,  457.13),
                    _it("Supply and lay stranded 35mm2 copper bare cable",                                          "M",      2,  120),
                ]},
            ]},
            {"no": 4, "name": "FIRE ALARM SYSTEM", "sections": [
                {"letter": "A", "title": "WIRING OF FIRE POINTS", "subsection": "", "items": [
                    _it("Supply, lay and connect 3c x 2.5mm2 red fire-resistant network detection cable drawn and looped", "M",   500,  30),
                    _it("Supply and install 20mm diameter self-extinguishing thermoplastic conduit",                       "Nos.",120,  14.63),
                    _it("Supply and install 75mm x 75mm steel conduit boxes",                                              "Nos.", 10,  13),
                    _it("Supply and install circular boxes of various ways",                                               "Nos.", 50,   5),
                ]},
                {"letter": "B", "title": "FIRE PANEL AND ACCESSORIES", "subsection": "", "items": [
                    _it("Supply, install, connect and commission Addressable optical Smoke detector as Hochiki or approved equal", "Nos.", 13,  532),
                    _it("Supply, install, connect and commission Break glass call point as Hochiki or approved equal",             "Nos.",  4,  600),
                    _it("Supply, install, connect and commission Fire Alarm Beacon/Sounder indoor with strobe",                    "Nos.",  4,  980),
                    _it("Supply and install Fire Alarm Junction Box",                                                              "Nos.",  1,  250),
                    _it("Supply, install, connect and commission Outdoor Weatherproof siren c/w strobe",                           "Nos.",  1,  980),
                    _it("Supply, install, connect and commission 8 Zone Addressable Fire Alarm Control Panel",                     "Nos.",  1, 53640),
                    _it("Supply and install Fire Exit Sign",                                                                       "Nos.",  3,  120),
                ]},
            ]},
            {"no": 5, "name": "DATA AND VOICE COMMUNICATIONS", "sections": [
                {"letter": "A", "title": "WIRING OF POINTS", "subsection": "Telephone and Data points", "items": [
                    _it("Supply and install 20mm diameter PVC conduit pipe", "Nos.",  95, 14.63),
                    _it("Supply and install 75mmx75mm square box",            "Nos.",  25, 13),
                    _it("Supply, lay and connect Cat 6e UTP Data cable",     "Coils",  3, 1650),
                ]},
                {"letter": "B", "title": "DATA EQUIPMENT AND ACCESSORIES", "subsection": "", "items": [
                    _it("Supply and install 48 Port CAT 6 patch panel",                                                                 "Nos.", 3,   1500),
                    _it("Supply, install and commission 48 port CAT 6 Switch w/ 1GB fibre optic uplink as Cisco or approved equal",     "Nos.", 3,   2300),
                    _it("Supply and install Fibre patch",                                                                                "Nos.", 2,    850),
                    _it("Supply and install 12U Data network cabinet",                                                                   "Nos.", 1,   1600),
                    _it("Supply, lay and connect OM3 Laser-Optimized Multimode Aqua fibre optic cable",                                 "M",  150,     52),
                    _it("Supply and install RJ45 double data outlet c/w faceplate, insert and mounting screws as MK or approved equal", "Nos.", 13,    104),
                    _it("Supply and install Power strip",                                                                                "Nos.", 2,    150),
                ]},
            ]},
            {"no": 6, "name": "SIGNAL COMMUNICATION SYSTEMS", "sections": [
                {"letter": "A", "title": "SMALL SIGNAL IP NETWORK", "subsection": "", "items": [
                    _it("Supply and install 20mm diameter PVC conduit pipe",                                  "Nos.",  50, 14.63),
                    _it("Supply and install 75mmx75mm square box",                                             "Nos.",  15, 13),
                    _it("Supply, lay and connect Cat 6e UTP Data cable",                                       "Coils",  2, 1650),
                    _it("Supply, install and commission Building/Zonal IP audio amplifier",                    "M",      1, 4900),
                    _it("Supply, lay and connect 20m AV cables -- building MIC to zonal amp",                  "M",     20,   19),
                    _it("Supply, lay and connect audio speaker cables (pair)",                                  "M",    100,    3),
                ]},
                {"letter": "B", "title": "EQUIPMENT AND ACCESSORIES", "subsection": "", "items": [
                    _it("Supply, install and commission IP Cam dome 100m, 180-degree view with night vision",  "Nos.",  3,  865),
                    _it("Supply, install and connect circular ceiling recessed audio speakers",                "Nos.", 10,  260),
                    _it("Supply, install and connect wall mounted audio speakers",                              "Nos.",  3,  400),
                    _it("Supply and install Power strip",                                                       "Nos.",  1,  150),
                ]},
            ]},
        ],
    },

    # ============== OFFICE ==================================================
    "office-typical": {
        "name":        "Typical Commercial Office floor",
        "purpose":     "commercial",
        "subtype":     "Office",
        "description": "Lean office-floor BOQ: switch boards + subfeeders + lighting + sockets + data, basic earthing. Good starter for SME / co-working / banking-hall projects.",
        "bills": [
            {"no": 1, "name": "PRELIMINARIES", "sections": [
                {"letter": "A", "title": "PRELIMINARY ITEMS", "subsection": "", "items": [
                    _it("Allow for site mobilisation and setup",     "Lot", 1, 12000),
                    _it("Allow for project manager presence on site","Mth", 2,  8500),
                    _it("Allow for health & safety provisions",      "Lot", 1,  4500),
                    _it("Allow for tools and small plant",            "Lot", 1,  3000),
                    _it("Allow for final commissioning and handover","Lot", 1,  5000),
                ]},
            ]},
            {"no": 2, "name": "INTERNAL ELECTRICAL WIRING", "sections": [
                {"letter": "A", "title": "SWITCH BOARDS AND DISTRIBUTION BOARDS", "subsection": "", "items": [
                    _it("Supply and install 12-way SPN MCB Distribution Board c/w 100A INT. switch as Memshield or approved equal", "Nos.", 1, 4200),
                    _it("Supply and install 8-way SPN MCB Distribution Board c/w 63A INT. switch as Memshield or approved equal",   "Nos.", 1, 2800),
                    _it("Supply and install 100A TPN load Isolator as Memshield or approved equal",                                 "Nos.", 1, 1470),
                ]},
                {"letter": "B", "title": "SUBFEEDER CABLES AND EARTHLEADS", "subsection": "", "items": _COMMON_SUBFEEDER},
                {"letter": "C", "title": "WIRING OF POINTS", "subsection": "Light points", "items": [
                    _it("Wire light points using 1.5mm2 PVC insulated copper cable (Brown)", "Coils",  8, 391),
                    _it("Wire light points using 1.5mm2 PVC insulated copper cable (Blue)",  "Coils",  8, 391),
                    _it("Supply and install 20mm diameter PVC conduit pipe",                  "Nos.", 120, 14.63),
                    _it("Supply and install 75mm x 75mm steel conduit boxes",                 "Nos.",  80, 13),
                ]},
                {"letter": "C", "title": "WIRING OF POINTS", "subsection": "Socket points", "items": [
                    _it("Wire socket points using 2.5mm2 PVC insulated copper cable (Brown)", "Coils", 3, 653),
                    _it("Wire socket points using 2.5mm2 PVC insulated copper cable (Blue)",  "Coils", 3, 653),
                ]},
                {"letter": "D", "title": "LUMINAIRES", "subsection": "", "items": [
                    _it("Supply and fix 40W 600x600mm LED recessed panel light c/w driver as Philips or approved equal", "Nos.", 18,  599),
                    _it("Supply and fix 18W LED round surface panel light as Philips or approved equal",                 "Nos.",  8,  305),
                    _it("Supply and fix Emergency exit luminaire c/w battery backup",                                     "Nos.",  4,  480),
                ]},
                {"letter": "E", "title": "ACCESSORIES", "subsection": "", "items": [
                    _it("Supply and fix 6A One Way two gang light switch as MK or approved equal",      "Nos.", 12,  34.13),
                    _it("Supply and fix 2 x 13A Switched Socket outlet as MK or approved equal",        "Nos.", 24,  60),
                    _it("Supply and fix 2 x 13A USB Socket outlet as MK or approved equal",             "Nos.",  8,  95),
                    _it("Supply and fix 6 Compartment floor box c/w 2 double sockets as MK or approved equal", "Nos.",  6, 2100),
                ]},
            ]},
            {"no": 5, "name": "DATA AND VOICE COMMUNICATIONS", "sections": [
                {"letter": "A", "title": "DATA EQUIPMENT AND ACCESSORIES", "subsection": "", "items": [
                    _it("Supply, lay and connect Cat 6e UTP Data cable",                                                            "Coils", 4, 1650),
                    _it("Supply, install and commission 24 port CAT 6 Switch w/ 1GB fibre optic uplink as Cisco or approved equal", "Nos.",  1, 1800),
                    _it("Supply and install 12U Data network cabinet",                                                              "Nos.",  1, 1600),
                    _it("Supply and install RJ45 double data outlet c/w faceplate as MK or approved equal",                         "Nos.", 12,  104),
                ]},
            ]},
        ],
    },

    # ============== HOSPITAL ================================================
    "hospital-ward": {
        "name":        "Hospital Ward floor",
        "purpose":     "commercial",
        "subtype":     "Hospital",
        "description": "Hospital-ward template with essential power split (normal + emergency), nurse call wiring, medical-grade sockets.",
        "bills": [
            {"no": 1, "name": "PRELIMINARIES", "sections": [
                {"letter": "A", "title": "PRELIMINARY ITEMS", "subsection": "", "items": [
                    _it("Allow for site mobilisation and setup",        "Lot", 1, 18000),
                    _it("Allow for project manager presence on site",   "Mth", 3,  8500),
                    _it("Allow for site engineer presence on site",     "Mth", 3,  7000),
                    _it("Allow for health & safety / infection control","Lot", 1,  8500),
                    _it("Allow for final commissioning and handover",   "Lot", 1,  6500),
                ]},
            ]},
            {"no": 2, "name": "INTERNAL ELECTRICAL WIRING", "sections": [
                {"letter": "A", "title": "SWITCH BOARDS AND DISTRIBUTION BOARDS", "subsection": "", "items": [
                    _it("Supply and install 12-way TPN MCB DB c/w 200A INT. switch (Normal Power) as Memshield or approved equal",    "Nos.", 1, 16500),
                    _it("Supply and install 8-way TPN MCB DB c/w 100A INT. switch (Essential Power) as Memshield or approved equal",  "Nos.", 1,  8200),
                    _it("Supply and install 6-way TPN MCB DB c/w 63A INT. switch (UPS Power) as Memshield or approved equal",         "Nos.", 1,  3308.81),
                    _it("Supply, install and commission ATS Panel 200A c/w controller",                                                "Nos.", 1, 22000),
                ]},
                {"letter": "B", "title": "SUBFEEDER CABLES AND EARTHLEADS", "subsection": "", "items": [
                    _it("Supply, lay and connect 4c x 50mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal", "M",  60,  651),
                    _it("Supply, lay and connect 4c x 25mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal", "M",  80,  290),
                    _it("Supply, lay and connect 4c x 16mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal", "M", 100,  190),
                    _it("Supply, lay and connect 4c x 10mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal", "M",  60,  125),
                    _it("Supply, lay and connect 1c x 25mm2 PVC Insulated copper cable as earth lead",                                                "M",  50,   65),
                    _it("Supply, lay and connect 1c x 16mm2 PVC Insulated copper cable as earth lead",                                                "M",  50,   42),
                ]},
                {"letter": "C", "title": "WIRING OF POINTS", "subsection": "Light points", "items": [
                    _it("Wire light points using 1.5mm2 PVC insulated copper cable (Brown)", "Coils", 18, 391),
                    _it("Wire light points using 1.5mm2 PVC insulated copper cable (Blue)",  "Coils", 18, 391),
                    _it("Supply and install 20mm diameter PVC conduit pipe",                  "Nos.",300, 14.63),
                ]},
                {"letter": "C", "title": "WIRING OF POINTS", "subsection": "Medical-grade socket points", "items": [
                    _it("Wire medical-grade socket points using 4.0mm2 PVC insulated copper cable (Brown)", "Coils", 6, 1037),
                    _it("Wire medical-grade socket points using 4.0mm2 PVC insulated copper cable (Blue)",  "Coils", 6, 1037),
                ]},
                {"letter": "D", "title": "LUMINAIRES", "subsection": "", "items": [
                    _it("Supply and fix 40W 600x600mm LED recessed panel light c/w driver as Philips or approved equal", "Nos.", 22, 599),
                    _it("Supply and fix Emergency LED exam-room luminaire as Philips or approved equal",                  "Nos.",  6, 850),
                    _it("Supply and fix Emergency exit luminaire c/w battery backup",                                     "Nos.",  6, 480),
                ]},
                {"letter": "E", "title": "ACCESSORIES", "subsection": "", "items": [
                    _it("Supply and fix Medical-grade twin socket outlet (red, essential) as MK or approved equal",  "Nos.", 18, 220),
                    _it("Supply and fix Medical-grade twin socket outlet (white, normal) as MK or approved equal",   "Nos.", 24, 180),
                    _it("Supply and fix 6A One Way two gang light switch as MK or approved equal",                   "Nos.", 18,  34.13),
                ]},
            ]},
            {"no": 4, "name": "FIRE ALARM SYSTEM", "sections": [
                {"letter": "A", "title": "WIRING OF FIRE POINTS", "subsection": "", "items": [
                    _it("Supply, lay and connect 3c x 2.5mm2 red fire-resistant detection cable", "M",    350,  30),
                    _it("Supply and install 20mm diameter thermoplastic fire conduit",            "Nos.",  80,  14.63),
                ]},
                {"letter": "B", "title": "FIRE PANEL AND ACCESSORIES", "subsection": "", "items": [
                    _it("Supply, install, connect and commission Addressable optical Smoke detector as Hochiki or approved equal", "Nos.", 18,    532),
                    _it("Supply, install, connect and commission Break glass call point as Hochiki or approved equal",             "Nos.",  6,    600),
                    _it("Supply, install, connect and commission 8 Zone Addressable Fire Panel as Hochiki or approved equal",      "Nos.",  1, 53640),
                ]},
            ]},
            {"no": 6, "name": "SIGNAL COMMUNICATION SYSTEMS", "sections": [
                {"letter": "A", "title": "NURSE CALL SYSTEM", "subsection": "", "items": [
                    _it("Supply, install and commission Nurse call patient bedhead unit",       "Nos.", 12, 1600),
                    _it("Supply, install and commission Nurse call corridor display",          "Nos.",  2, 2200),
                    _it("Supply, install and commission Nurse call master station",            "Nos.",  1, 6800),
                    _it("Supply, lay and connect Nurse call wiring 4c x 0.5mm2 shielded",      "M",   400,   18),
                ]},
            ]},
        ],
    },

    # ============== HOSTEL ==================================================
    "hostel-typical": {
        "name":        "Hostel / Student Residence floor",
        "purpose":     "residential",
        "subtype":     "Hostel",
        "description": "Hostel-floor BOQ for student or staff accommodation -- per-room DBs, basic lighting + sockets, communal areas.",
        "bills": [
            {"no": 1, "name": "PRELIMINARIES", "sections": [
                {"letter": "A", "title": "PRELIMINARY ITEMS", "subsection": "", "items": [
                    _it("Allow for site mobilisation and setup",        "Lot", 1,  8000),
                    _it("Allow for project manager presence on site",   "Mth", 2,  6500),
                    _it("Allow for final commissioning and handover",   "Lot", 1,  3500),
                ]},
            ]},
            {"no": 2, "name": "INTERNAL ELECTRICAL WIRING", "sections": [
                {"letter": "A", "title": "SWITCH BOARDS AND DISTRIBUTION BOARDS", "subsection": "", "items": [
                    _it("Supply and install 12-way SPN Consumer Unit c/w 100A switch (floor) as Memshield or approved equal", "Nos.", 1, 3800),
                    _it("Supply and install 6-way SPN room consumer unit as Memshield or approved equal",                     "Nos.", 8,  850),
                ]},
                {"letter": "B", "title": "SUBFEEDER CABLES AND EARTHLEADS", "subsection": "", "items": _COMMON_SUBFEEDER},
                {"letter": "C", "title": "WIRING OF POINTS", "subsection": "Light points (per room)", "items": [
                    _it("Wire light points using 1.5mm2 PVC insulated copper cable (Brown)", "Coils", 12, 391),
                    _it("Wire light points using 1.5mm2 PVC insulated copper cable (Blue)",  "Coils", 12, 391),
                    _it("Supply and install 20mm diameter PVC conduit pipe",                  "Nos.",180, 14.63),
                    _it("Supply and install 75mm x 75mm steel conduit boxes",                 "Nos.",150, 13),
                ]},
                {"letter": "C", "title": "WIRING OF POINTS", "subsection": "Socket points (per room)", "items": [
                    _it("Wire socket points using 2.5mm2 PVC insulated copper cable (Brown)", "Coils", 5, 653),
                    _it("Wire socket points using 2.5mm2 PVC insulated copper cable (Blue)",  "Coils", 5, 653),
                ]},
                {"letter": "D", "title": "LUMINAIRES", "subsection": "", "items": [
                    _it("Supply and fix 18W LED ceiling round panel light as Philips or approved equal",  "Nos.", 16, 226),
                    _it("Supply and fix LED bathroom waterproof fitting as Philips or approved equal",     "Nos.",  8, 380),
                ]},
                {"letter": "E", "title": "ACCESSORIES", "subsection": "", "items": [
                    _it("Supply and fix 6A One Way One gang light switch as MK or approved equal",                   "Nos.", 16, 20.73),
                    _it("Supply and fix 2 x 13A Switched Socket outlet as MK or approved equal",                     "Nos.", 24, 60),
                    _it("Supply and fix 1 x 13A unswitched Socket outlet as MK or approved equal",                   "Nos.",  8, 40),
                    _it("Supply and fix 20A DP switch with neon indicator (water heater) as MK or approved equal",   "Nos.",  8, 35),
                ]},
            ]},
        ],
    },

    # ============== RESIDENCE (single-family) -- NEW ========================
    "residence-typical": {
        "name":        "Single-Family Residence (3-bed)",
        "purpose":     "residential",
        "subtype":     "Single Family House",
        "description": "3-bedroom residential electrical BOQ. Main consumer unit + subfeeder cables + per-room wiring, lighting, sockets, water-heater, AC and security outlets. Aimed at electricians doing residential installations.",
        "bills": [
            {"no": 1, "name": "PRELIMINARIES", "sections": [
                {"letter": "A", "title": "PRELIMINARY ITEMS", "subsection": "", "items": [
                    _it("Allow for site mobilisation and setup",         "Lot", 1, 4500),
                    _it("Allow for tools and small plant",                "Lot", 1, 2500),
                    _it("Allow for final commissioning and handover",    "Lot", 1, 2500),
                ]},
            ]},
            {"no": 2, "name": "INTERNAL ELECTRICAL WIRING", "sections": [
                {"letter": "A", "title": "SWITCH BOARDS AND DISTRIBUTION BOARDS", "subsection": "", "items": [
                    _it("Supply and install 12-way SPN Consumer Unit c/w 100A main switch as Memshield or approved equal", "Nos.", 1, 3800),
                    _it("Supply and install 8-way SPN sub-consumer unit (kitchen/utility) as Memshield or approved equal",  "Nos.", 1, 1500),
                    _it("Supply and install 63A TPN load Isolator as Memshield or approved equal",                          "Nos.", 1,  900),
                ]},
                {"letter": "B", "title": "SUBFEEDER CABLES AND EARTHLEADS", "subsection": "", "items": [
                    _it("Supply, lay and connect 4c x 25mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal", "M",  30,  290),
                    _it("Supply, lay and connect 4c x 16mm2 PVC/PVC Insulated copper cable c/w connecting accessories as Tropical or approved equal", "M",  40,  190),
                    _it("Supply, lay and connect 1c x 16mm2 PVC Insulated copper cable as earth lead",                                                 "M",  35,   42),
                    _it("Supply and install 1500mm copper earth rod, buried 1.5m below ground with soil treatment",                                    "Set", 1, 1200),
                ]},
                {"letter": "C", "title": "WIRING OF POINTS", "subsection": "Light points (whole house)", "items": [
                    _it("Wire light points using 1.5mm2 PVC insulated copper cable (Brown)",            "Coils",  6, 391),
                    _it("Wire light points using 1.5mm2 PVC insulated copper cable (Blue)",             "Coils",  6, 391),
                    _it("Wire light points using 1.5mm2 PVC insulated copper cable (Yellow/Green)",     "Coils",  4, 391),
                    _it("Supply and install 20mm diameter PVC conduit pipe",                            "Nos.", 250, 14.63),
                    _it("Supply and install 75mm x 75mm steel conduit boxes",                           "Nos.", 200, 13),
                    _it("Supply and install circular boxes of various ways",                            "Nos.",  60,  5),
                ]},
                {"letter": "C", "title": "WIRING OF POINTS", "subsection": "13A socket points", "items": [
                    _it("Wire socket points using 2.5mm2 PVC insulated copper cable (Brown)",           "Coils",  4, 653),
                    _it("Wire socket points using 2.5mm2 PVC insulated copper cable (Blue)",            "Coils",  4, 653),
                    _it("Wire socket points using 2.5mm2 PVC insulated copper cable (Yellow/Green)",    "Coils",  3, 653),
                ]},
                {"letter": "C", "title": "WIRING OF POINTS", "subsection": "Water heater + AC points", "items": [
                    _it("Wire water heater / AC points using 4.0mm2 PVC insulated copper cable (Brown)",         "Coils", 2, 1037),
                    _it("Wire water heater / AC points using 4.0mm2 PVC insulated copper cable (Blue)",          "Coils", 2, 1037),
                    _it("Wire water heater / AC points using 4.0mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 2, 1037),
                ]},
                {"letter": "D", "title": "LUMINAIRES", "subsection": "", "items": [
                    _it("Supply and fix 18W LED round surface panel light (rooms) as Philips or approved equal",        "Nos.", 16, 305),
                    _it("Supply and fix 12W LED round surface panel light (corridor/utility) as Philips or approved equal","Nos.", 6, 226),
                    _it("Supply and fix LED bathroom waterproof fitting IP44 as Philips or approved equal",              "Nos.",  4, 380),
                    _it("Supply and fix Outdoor wall-mounted LED floodlight 50W IP65 (security)",                         "Nos.",  3, 380),
                ]},
                {"letter": "E", "title": "ACCESSORIES", "subsection": "", "items": [
                    _it("Supply and fix 6A One Way One gang light switch as MK or approved equal",                                       "Nos.", 16, 20.73),
                    _it("Supply and fix 6A One Way two gang light switch as MK or approved equal",                                       "Nos.",  6, 34.13),
                    _it("Supply and fix 6A two Way one gang light switch as MK or approved equal (staircase / corridor)",                "Nos.",  4, 23.16),
                    _it("Supply and fix 2 x 13A Switched Socket outlet as MK or approved equal",                                         "Nos.", 22, 60),
                    _it("Supply and fix 1 x 13A unswitched Socket outlet as MK or approved equal (kitchen appliance)",                   "Nos.",  6, 40),
                    _it("Supply and fix 20A DP switch with neon indicator (water heater) as MK or approved equal",                       "Nos.",  4, 35),
                    _it("Supply and fix 20A DP switch with neon indicator (AC outdoor unit) as MK or approved equal",                    "Nos.",  3, 35),
                    _it("Supply and fix Weatherproof IP65 socket outlet (outdoor) as MK or approved equal",                              "Nos.",  2, 110),
                ]},
            ]},
            {"no": 3, "name": "BONDING AND EARTHING", "sections": [
                {"letter": "A", "title": "BONDING AND EARTHING", "subsection": "", "items": [
                    _it("Supply and lay 35mm2 bare copper conductor to fully contact the earth and treat",     "M",   25, 120),
                    _it("Supply and install standard 1.5M high graded copper earth rod",                       "Nos.", 1, 1200),
                    _it("Perform Exothermic welding",                                                          "Nos.", 2,  750),
                    _it("Supply and install concrete inspection chamber with cover",                           "Nos.", 1,  457.13),
                    _it("Test the installation using scripts from the electrical engineer",                    "Lot",  1, 2500),
                ]},
            ]},
        ],
    },
}


# ===========================================================================
# Public helpers (replace the originals in _BOQ_PROJECT_TEMPLATES_v1)
# ===========================================================================

def _boq_template_list(purpose: str = "") -> list:
    out = []
    for slug, t in _BOQ_PROJECT_TEMPLATES.items():
        if purpose and t.get("purpose") != purpose:
            continue
        out.append({
            "slug": slug,
            "name": t["name"],
            "purpose": t["purpose"],
            "subtype": t["subtype"],
            "description": t["description"],
            "n_bills": len(t["bills"]),
            "n_lines": sum(len(s["items"]) for b in t["bills"] for s in b["sections"]),
        })
    return out


def _boq_template_get(slug: str) -> dict:
    return _BOQ_PROJECT_TEMPLATES.get(slug)


def _boq_template_iter_lines(template: dict):
    idx = 0
    for b in template["bills"]:
        bill_no = b["no"]
        bill_name = b["name"]
        for s in b["sections"]:
            section_letter = s["letter"]
            section_title = s["title"]
            subsec = s.get("subsection", "")
            for it in s["items"]:
                yield (bill_no, bill_name, section_letter, section_title, subsec,
                       idx, it["desc"], it.get("unit", "No."),
                       float(it.get("qty", 1)), float(it.get("basic", 0)),
                       it.get("spec", ""))
                idx += 1
