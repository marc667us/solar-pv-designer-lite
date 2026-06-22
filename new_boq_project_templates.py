# new_boq_project_templates.py
# Whole-floor BOQ templates -- owner-pickable, rendered with a checkbox
# per line so the user just ticks what applies, edits qtys, and Generate.
#
# Structure:
#   _BOQ_PROJECT_TEMPLATES[slug] = {
#     "name", "purpose", "subtype", "description",
#     "bills": [
#        { "no", "name", "sections": [
#             { "letter", "title", "subsection",  # subsection optional
#               "items": [{"desc","unit","qty","basic","spec"}, ...] }
#          ...
#        ] }
#     ]
#   }
#
# Owner can:
#   - Tick / untick any line  (default = ticked)
#   - Edit qty  (default from template)
#   - Edit basic rate  (default from template; markup applied at save time)
#   - Add ad-hoc lines via "Open new section" (existing grid flow)
#
# Save POST: bulk-insert every ticked line under (bill_no, section_letter)
# tuples into boq_floor_items + boq_floor_rate_buildup.


_BOQ_PROJECT_TEMPLATES = {

    # ─── Schools, Offices and Auditorium (formerly auditorium-1ugls) ──────
    # Slug kept stable so saved-project references don't break; display name
    # updated 2026-06-22 to reflect the broader scope (school / office /
    # auditorium / lecture-hall) the template actually covers.
    "auditorium-1ugls": {
        "name":        "Schools, Offices and Auditorium",
        "purpose":     "commercial",
        "subtype":     "Schools / Offices / Auditorium",
        "description": "Reference electrical + ICT BOQ for schools, offices, and auditoria -- 6 bills, ~95 items, covers preliminaries, switchboards, internal wiring, fire alarm, data / voice, signal comms.",
        "bills": [
            {"no": 1, "name": "PRELIMINARIES", "sections": [
                {"letter": "A", "title": "PRELIMINARY ITEMS", "subsection": "", "items": [
                    {"desc": "Site mobilisation and setup",          "unit": "Lot",  "qty": 1, "basic": 25000, "spec": ""},
                    {"desc": "Site insurance",                       "unit": "Lot",  "qty": 1, "basic": 15000, "spec": ""},
                    {"desc": "Project manager allowance",            "unit": "Mth",  "qty": 4, "basic":  8500, "spec": ""},
                    {"desc": "Site engineer allowance",              "unit": "Mth",  "qty": 4, "basic":  7000, "spec": ""},
                    {"desc": "Health & safety provisions",           "unit": "Lot",  "qty": 1, "basic":  6500, "spec": ""},
                    {"desc": "Site office accommodation",            "unit": "Mth",  "qty": 4, "basic":  3500, "spec": ""},
                    {"desc": "Tools and small plant",                "unit": "Lot",  "qty": 1, "basic":  4500, "spec": ""},
                    {"desc": "Final commissioning and handover",     "unit": "Lot",  "qty": 1, "basic":  8000, "spec": ""},
                ]},
            ]},

            {"no": 2, "name": "INTERNAL ELECTRICAL WIRING", "sections": [
                {"letter": "A", "title": "SWITCH BOARDS AND DISTRIBUTION BOARDS", "subsection": "", "items": [
                    {"desc": "6-way TPN Memshield MCCB Distribution Panel Board c/w 400A Incomer", "unit": "Nos.", "qty": 1, "basic": 19800,  "spec": ""},
                    {"desc": "6-way TPN Memshield MCB Distribution Board c/w 200A INT. switch",    "unit": "Nos.", "qty": 1, "basic": 15500,  "spec": ""},
                    {"desc": "6-way TPN Memshield MCB Distribution Board c/w 63A INT. switch",     "unit": "Nos.", "qty": 1, "basic":  3308.81,"spec": ""},
                    {"desc": "6-way TPN Memshield MCB Distribution Board c/w 32A INT. switch",     "unit": "Nos.", "qty": 1, "basic":  3309.81,"spec": ""},
                    {"desc": "4-way TPN Memshield MCB Distribution Board c/w 32A INT. switch",     "unit": "Nos.", "qty": 1, "basic":  3200,   "spec": ""},
                    {"desc": "200A TPN Fuse Switch",                                                "unit": "Nos.", "qty": 1, "basic":  6700,   "spec": ""},
                    {"desc": "400A TPN Fuse Switch",                                                "unit": "Nos.", "qty": 1, "basic": 12160,   "spec": ""},
                    {"desc": "125A TPN Fuse Switch",                                                "unit": "Nos.", "qty": 1, "basic":  4600,   "spec": ""},
                    {"desc": "100A TPN load Isolator",                                              "unit": "Nos.", "qty": 3, "basic":  1470,   "spec": ""},
                    {"desc": "63A TPN load Isolator",                                               "unit": "Nos.", "qty": 3, "basic":   900,   "spec": ""},
                ]},
                {"letter": "B", "title": "SUBFEEDER CABLES AND EARTHLEADS", "subsection": "", "items": [
                    {"desc": "4c x 240mm2 PVC/PVC Insulated copper cable c/w connecting accessories","unit": "M",   "qty": 120, "basic": 3849,    "spec": ""},
                    {"desc": "1c x 120mm2 PVC Insulated copper cable c/w connecting accessories",   "unit": "M",   "qty":  10, "basic":  400,    "spec": ""},
                    {"desc": "4c x 120mm2 PVC/PVC Insulated copper cable c/w connecting accessories","unit": "M",   "qty": 120, "basic": 2242.80, "spec": ""},
                    {"desc": "1c x 70mm2 PVC Insulated copper cable c/w connecting accessories",    "unit": "M",   "qty":  10, "basic":  298,    "spec": ""},
                    {"desc": "4c x 50mm2 PVC/PVC Insulated copper cable c/w connecting accessories", "unit": "M",   "qty": 120, "basic":  651,    "spec": ""},
                    {"desc": "1c x 25mm2 PVC Insulated copper cable c/w connecting accessories",    "unit": "M",   "qty":  10, "basic":   65,    "spec": ""},
                    {"desc": "1c x 16mm2 PVC Insulated copper cable c/w connecting accessories",    "unit": "M",   "qty":  70, "basic":   42,    "spec": ""},
                    {"desc": "4c x 16mm2 PVC/PVC Insulated copper cable c/w connecting accessories", "unit": "M",   "qty": 145, "basic":  190,    "spec": ""},
                    {"desc": "4c x 10mm2 PVC/PVC Insulated copper cable c/w connecting accessories", "unit": "M",   "qty":  20, "basic":  125,    "spec": ""},
                    {"desc": "1c x 10mm2 PVC Insulated copper cable c/w connecting accessories",    "unit": "M",   "qty":  20, "basic":   27,    "spec": ""},
                    {"desc": "4c x 25mm2 PVC/PVC Insulated copper cable c/w connecting accessories", "unit": "M",   "qty": 135, "basic":  290,    "spec": ""},
                ]},
                {"letter": "C", "title": "WIRING OF POINTS", "subsection": "I. Light and fan points", "items": [
                    {"desc": "1.5mm2 PVC insulated copper cable (Brown)", "unit": "Coils", "qty": 30, "basic": 391, "spec": ""},
                    {"desc": "1.5mm2 PVC insulated copper cable (Blue)",  "unit": "Coils", "qty": 35, "basic": 391, "spec": ""},
                    {"desc": "1.5mm2 PVC insulated copper cable (Grey)",  "unit": "Coils", "qty": 33, "basic": 391, "spec": ""},
                    {"desc": "20mm diameter PVC conduit pipe",            "unit": "Nos.",  "qty": 578, "basic": 14.63, "spec": ""},
                    {"desc": "75mm x 75mm steel conduit boxes",           "unit": "Nos.",  "qty": 467, "basic": 13, "spec": ""},
                    {"desc": "Circular boxes of various ways",             "unit": "Nos.",  "qty":  50, "basic":  5, "spec": ""},
                ]},
                {"letter": "C", "title": "WIRING OF POINTS", "subsection": "II. 13A socket points and hand dryer", "items": [
                    {"desc": "2.5mm2 PVC insulated copper cable (Brown)",         "unit": "Coils", "qty":  5, "basic": 653, "spec": ""},
                    {"desc": "2.5mm2 PVC insulated copper cable (Blue)",          "unit": "Coils", "qty":  5, "basic": 653, "spec": ""},
                    {"desc": "2.5mm2 PVC insulated copper cable (Yellow/Green)",  "unit": "Coils", "qty":  5, "basic": 653, "spec": ""},
                    {"desc": "20mm diameter PVC conduit pipe",                    "unit": "Nos.",  "qty": 156, "basic": 14.63, "spec": ""},
                    {"desc": "150mm x 75mm steel conduit boxes",                  "unit": "Nos.",  "qty":  20, "basic": 18, "spec": ""},
                ]},
                {"letter": "D", "title": "LUMINAIRES", "subsection": "", "items": [
                    {"desc": "35W Round Recessed downlighter",                              "unit": "Nos.", "qty": 53, "basic": 550,    "spec": ""},
                    {"desc": "36W 1200mm LED linear Panel light c/w enclosure",             "unit": "Nos.", "qty": 10, "basic": 707.01, "spec": ""},
                    {"desc": "36W 1200mm LED linear Panel light",                           "unit": "Nos.", "qty":  4, "basic": 372,    "spec": ""},
                    {"desc": "18W LED round surface panel light",                           "unit": "Nos.", "qty": 17, "basic": 305,    "spec": ""},
                    {"desc": "12W LED round surface panel light",                           "unit": "Nos.", "qty": 20, "basic": 226,    "spec": ""},
                    {"desc": "LED Strip light",                                             "unit": "Coil", "qty":  1, "basic":  35,    "spec": ""},
                ]},
                {"letter": "E", "title": "ACCESSORIES", "subsection": "", "items": [
                    {"desc": "6A One Way One gang light switch (MK)",                       "unit": "Nos.", "qty": 22, "basic": 20.73, "spec": ""},
                    {"desc": "6A One Way two gang light switch (MK)",                       "unit": "Nos.", "qty":  4, "basic": 34.13, "spec": ""},
                    {"desc": "6A two Way one gang light switch (MK)",                       "unit": "Nos.", "qty": 12, "basic": 23.16, "spec": ""},
                    {"desc": "6A two Way two gang light switch (MK)",                       "unit": "Nos.", "qty":  1, "basic": 35,    "spec": ""},
                    {"desc": "6 Compartment floor box c/w 2 double sockets + 2 double data outlet","unit": "Nos.", "qty": 29, "basic": 2100, "spec": ""},
                    {"desc": "1 x 13A unswitched Socket outlet (MK)",                       "unit": "Nos.", "qty":  5, "basic": 40,    "spec": ""},
                    {"desc": "2 x 13A Switched Socket outlet (MK)",                         "unit": "Nos.", "qty":  6, "basic": 60,    "spec": ""},
                    {"desc": "Plastic Automatic Hand Dryer",                                "unit": "Nos.", "qty":  2, "basic": 1250, "spec": ""},
                ]},
            ]},

            {"no": 3, "name": "BONDING AND EARTHING", "sections": [
                {"letter": "A", "title": "BONDING AND EARTHING", "subsection": "", "items": [
                    {"desc": "70mm2 bare copper conductor",                                  "unit": "M",    "qty": 138, "basic":  289,   "spec": ""},
                    {"desc": "50mm2 bare copper conductor",                                  "unit": "M",    "qty":  35, "basic":  133,   "spec": ""},
                    {"desc": "Galvanised steel holding rings",                               "unit": "Nos.", "qty":   7, "basic":   20.30,"spec": ""},
                    {"desc": "Equalisation bar c/w 8 studs and connecting accessories",      "unit": "Nos.", "qty":   3, "basic":  548.55,"spec": ""},
                    {"desc": "6x6 IP65 grounding junction box 20cm above FFL",               "unit": "Nos.", "qty":   3, "basic":   36.57,"spec": ""},
                    {"desc": "3x3 square box",                                               "unit": "Nos.", "qty":   3, "basic":   13,   "spec": ""},
                    {"desc": "Arc welding -- mechanical attaching taps",                     "unit": "Pts.", "qty":  80, "basic":  135,   "spec": ""},
                    {"desc": "Exothermic welding",                                           "unit": "Nos.", "qty":  20, "basic":  750,   "spec": ""},
                    {"desc": "600mm x 600mm copper earth mat c/w 1500mm copper earth rod",   "unit": "Nos.", "qty":   7, "basic": 1700,   "spec": ""},
                    {"desc": "Roll of warning tape (yellow/green)",                          "unit": "Nos.", "qty":   3, "basic":  150,   "spec": ""},
                    {"desc": "Standard 1.5M high graded copper earth rod",                   "unit": "Nos.", "qty":   7, "basic": 1200,   "spec": ""},
                    {"desc": "Test the installation -- electrical engineer's scripts",       "unit": "Lot",  "qty":   1, "basic": 5000,   "spec": ""},
                    {"desc": "Concrete inspection chamber with cover",                       "unit": "Nos.", "qty":   1, "basic":  457.13,"spec": ""},
                    {"desc": "Stranded 35mm2 copper bare cable",                             "unit": "M",    "qty":   2, "basic":  120,   "spec": ""},
                ]},
            ]},

            {"no": 4, "name": "FIRE ALARM SYSTEM", "sections": [
                {"letter": "A", "title": "WIRING OF FIRE POINTS", "subsection": "", "items": [
                    {"desc": "3c x 2.5mm2 red fire-resistant network detection cable", "unit": "M",    "qty": 500, "basic": 30,   "spec": ""},
                    {"desc": "20mm diameter self-extinguishing thermoplastic conduit", "unit": "Nos.", "qty": 120, "basic": 14.63,"spec": ""},
                    {"desc": "75mm x 75mm steel conduit boxes",                        "unit": "Nos.", "qty":  10, "basic": 13,   "spec": ""},
                    {"desc": "Circular boxes of various ways",                          "unit": "Nos.", "qty":  50, "basic":  5,   "spec": ""},
                ]},
                {"letter": "B", "title": "FIRE PANEL AND ACCESSORIES", "subsection": "", "items": [
                    {"desc": "Addressable optical Smoke detector",                                          "unit": "Nos.", "qty": 13, "basic":   532, "spec": ""},
                    {"desc": "Break glass call point",                                                      "unit": "Nos.", "qty":  4, "basic":   600, "spec": ""},
                    {"desc": "Fire Alarm Beacon/Sounder indoor with strobe",                                "unit": "Nos.", "qty":  4, "basic":   980, "spec": ""},
                    {"desc": "Fire Alarm Junction Box",                                                     "unit": "Nos.", "qty":  1, "basic":   250, "spec": ""},
                    {"desc": "Outdoor Weatherproof siren c/w strobe",                                       "unit": "Nos.", "qty":  1, "basic":   980, "spec": ""},
                    {"desc": "8 Zone Addressable Fire Alarm Control Panel inc LCD module and Control Keys", "unit": "Nos.", "qty":  1, "basic": 53640, "spec": ""},
                    {"desc": "Fire Exit Sign",                                                              "unit": "Nos.", "qty":  3, "basic":   120, "spec": ""},
                ]},
            ]},

            {"no": 5, "name": "DATA AND VOICE COMMUNICATIONS", "sections": [
                {"letter": "A", "title": "WIRING OF POINTS", "subsection": "Telephone and Data points", "items": [
                    {"desc": "20mm diameter PVC conduit pipe", "unit": "Nos.",  "qty": 95, "basic": 14.63, "spec": ""},
                    {"desc": "75mmx75mm square box",            "unit": "Nos.",  "qty": 25, "basic": 13,    "spec": ""},
                    {"desc": "Cat 6e UTP Data cable",           "unit": "Coils", "qty":  3, "basic": 1650,  "spec": ""},
                ]},
                {"letter": "B", "title": "DATA EQUIPMENT AND ACCESSORIES", "subsection": "", "items": [
                    {"desc": "48 Port CAT 6 patch panel",                                       "unit": "Nos.", "qty": 3,   "basic": 1500, "spec": ""},
                    {"desc": "48 port CAT 6 Switch w/ 1GB fibre optic uplink",                  "unit": "Nos.", "qty": 3,   "basic": 2300, "spec": ""},
                    {"desc": "Fibre patch",                                                     "unit": "Nos.", "qty": 2,   "basic":  850, "spec": ""},
                    {"desc": "12U Data network cabinet",                                        "unit": "Nos.", "qty": 1,   "basic": 1600, "spec": ""},
                    {"desc": "OM3 Laser-Optimized Multimode Aqua fibre optic cable",            "unit": "M",    "qty": 150, "basic":   52, "spec": ""},
                    {"desc": "RJ45 double data outlet c/w faceplate, insert and mounting screws","unit": "Nos.", "qty": 13,  "basic":  104, "spec": ""},
                    {"desc": "Power strip",                                                     "unit": "Nos.", "qty": 2,   "basic":  150, "spec": ""},
                ]},
            ]},

            {"no": 6, "name": "SIGNAL COMMUNICATION SYSTEMS", "sections": [
                {"letter": "A", "title": "SMALL SIGNAL IP NETWORK", "subsection": "", "items": [
                    {"desc": "20mm diameter PVC conduit pipe",                    "unit": "Nos.",  "qty":  50, "basic": 14.63, "spec": ""},
                    {"desc": "75mmx75mm square box",                              "unit": "Nos.",  "qty":  15, "basic": 13,    "spec": ""},
                    {"desc": "Cat 6e UTP Data cable",                             "unit": "Coils", "qty":   2, "basic": 1650,  "spec": ""},
                    {"desc": "Building/Zonal IP audio amplifier",                 "unit": "M",     "qty":   1, "basic": 4900,  "spec": ""},
                    {"desc": "20m AV cables -- building MIC to zonal amp",        "unit": "M",     "qty":  20, "basic":   19,  "spec": ""},
                    {"desc": "Audio speaker cables (pair)",                       "unit": "M",     "qty": 100, "basic":    3,  "spec": ""},
                ]},
                {"letter": "B", "title": "EQUIPMENT AND ACCESSORIES", "subsection": "", "items": [
                    {"desc": "IP Cam dome 100m, 180-degree view, night vision",   "unit": "Nos.", "qty": 3,  "basic": 865, "spec": ""},
                    {"desc": "Circular ceiling recessed audio speakers",          "unit": "Nos.", "qty": 10, "basic": 260, "spec": ""},
                    {"desc": "Wall mounted audio speakers",                       "unit": "Nos.", "qty": 3,  "basic": 400, "spec": ""},
                    {"desc": "Power strip",                                       "unit": "Nos.", "qty": 1,  "basic": 150, "spec": ""},
                ]},
            ]},
        ],
    },

    # ─── Typical Office Floor ─────────────────────────────────────────────
    "office-typical": {
        "name":        "Typical Commercial Office floor",
        "purpose":     "commercial",
        "subtype":     "Office",
        "description": "Lean office-floor BOQ: lighting + sockets + data, basic earthing, no fire system. Good starter for SME / co-working / banking-hall projects.",
        "bills": [
            {"no": 1, "name": "PRELIMINARIES", "sections": [
                {"letter": "A", "title": "PRELIMINARY ITEMS", "subsection": "", "items": [
                    {"desc": "Site mobilisation and setup",          "unit": "Lot",  "qty": 1, "basic": 12000, "spec": ""},
                    {"desc": "Project manager allowance",            "unit": "Mth",  "qty": 2, "basic":  8500, "spec": ""},
                    {"desc": "Health & safety provisions",           "unit": "Lot",  "qty": 1, "basic":  4500, "spec": ""},
                    {"desc": "Tools and small plant",                "unit": "Lot",  "qty": 1, "basic":  3000, "spec": ""},
                    {"desc": "Final commissioning and handover",     "unit": "Lot",  "qty": 1, "basic":  5000, "spec": ""},
                ]},
            ]},
            {"no": 2, "name": "INTERNAL ELECTRICAL WIRING", "sections": [
                {"letter": "A", "title": "SWITCH BOARDS AND DISTRIBUTION BOARDS", "subsection": "", "items": [
                    {"desc": "12-way SPN Memshield MCB Distribution Board c/w 100A INT. switch", "unit": "Nos.", "qty": 1, "basic": 4200, "spec": ""},
                    {"desc": "8-way SPN Memshield MCB Distribution Board c/w 63A INT. switch",   "unit": "Nos.", "qty": 1, "basic": 2800, "spec": ""},
                    {"desc": "100A TPN load Isolator",                                            "unit": "Nos.", "qty": 1, "basic": 1470, "spec": ""},
                ]},
                {"letter": "B", "title": "WIRING OF POINTS", "subsection": "Light points", "items": [
                    {"desc": "1.5mm2 PVC insulated copper cable (Brown)", "unit": "Coils", "qty": 8,  "basic": 391,  "spec": ""},
                    {"desc": "1.5mm2 PVC insulated copper cable (Blue)",  "unit": "Coils", "qty": 8,  "basic": 391,  "spec": ""},
                    {"desc": "20mm diameter PVC conduit pipe",            "unit": "Nos.",  "qty": 120,"basic": 14.63,"spec": ""},
                    {"desc": "75mm x 75mm steel conduit boxes",           "unit": "Nos.",  "qty": 80, "basic": 13,   "spec": ""},
                ]},
                {"letter": "B", "title": "WIRING OF POINTS", "subsection": "Socket points", "items": [
                    {"desc": "2.5mm2 PVC insulated copper cable (Brown)", "unit": "Coils", "qty": 3, "basic": 653, "spec": ""},
                    {"desc": "2.5mm2 PVC insulated copper cable (Blue)",  "unit": "Coils", "qty": 3, "basic": 653, "spec": ""},
                ]},
                {"letter": "C", "title": "LUMINAIRES", "subsection": "", "items": [
                    {"desc": "40W 600x600mm LED recessed panel light c/w driver",   "unit": "Nos.", "qty": 18, "basic":  599, "spec": ""},
                    {"desc": "18W LED round surface panel light",                   "unit": "Nos.", "qty":  8, "basic":  305, "spec": ""},
                    {"desc": "Emergency exit luminaire c/w battery backup",         "unit": "Nos.", "qty":  4, "basic":  480, "spec": ""},
                ]},
                {"letter": "D", "title": "ACCESSORIES", "subsection": "", "items": [
                    {"desc": "6A One Way two gang light switch (MK)",          "unit": "Nos.", "qty": 12, "basic":  34.13, "spec": ""},
                    {"desc": "2 x 13A Switched Socket outlet (MK)",            "unit": "Nos.", "qty": 24, "basic":  60,    "spec": ""},
                    {"desc": "2 x 13A USB Socket outlet (MK)",                 "unit": "Nos.", "qty":  8, "basic":  95,    "spec": ""},
                    {"desc": "6 Compartment floor box c/w 2 double sockets",   "unit": "Nos.", "qty":  6, "basic": 2100,    "spec": ""},
                ]},
            ]},
            {"no": 5, "name": "DATA AND VOICE COMMUNICATIONS", "sections": [
                {"letter": "A", "title": "DATA EQUIPMENT AND ACCESSORIES", "subsection": "", "items": [
                    {"desc": "Cat 6e UTP Data cable",                                         "unit": "Coils", "qty": 4, "basic": 1650, "spec": ""},
                    {"desc": "24 port CAT 6 Switch w/ 1GB fibre optic uplink",                "unit": "Nos.",  "qty": 1, "basic": 1800, "spec": ""},
                    {"desc": "12U Data network cabinet",                                      "unit": "Nos.",  "qty": 1, "basic": 1600, "spec": ""},
                    {"desc": "RJ45 double data outlet c/w faceplate",                         "unit": "Nos.",  "qty":12, "basic":  104, "spec": ""},
                ]},
            ]},
        ],
    },

    # ─── Hospital Ward ────────────────────────────────────────────────────
    "hospital-ward": {
        "name":        "Hospital Ward floor",
        "purpose":     "commercial",
        "subtype":     "Hospital",
        "description": "Hospital-ward template with essential power split (normal + emergency), nurse call wiring, oxygen / medical-grade sockets.",
        "bills": [
            {"no": 1, "name": "PRELIMINARIES", "sections": [
                {"letter": "A", "title": "PRELIMINARY ITEMS", "subsection": "", "items": [
                    {"desc": "Site mobilisation and setup",          "unit": "Lot",  "qty": 1, "basic": 18000, "spec": ""},
                    {"desc": "Project manager allowance",            "unit": "Mth",  "qty": 3, "basic":  8500, "spec": ""},
                    {"desc": "Site engineer allowance",              "unit": "Mth",  "qty": 3, "basic":  7000, "spec": ""},
                    {"desc": "Health & safety / infection control",  "unit": "Lot",  "qty": 1, "basic":  8500, "spec": ""},
                    {"desc": "Final commissioning and handover",     "unit": "Lot",  "qty": 1, "basic":  6500, "spec": ""},
                ]},
            ]},
            {"no": 2, "name": "INTERNAL ELECTRICAL WIRING", "sections": [
                {"letter": "A", "title": "SWITCH BOARDS AND DISTRIBUTION BOARDS", "subsection": "", "items": [
                    {"desc": "12-way TPN Memshield MCB DB c/w 200A INT. switch (Normal Power)",   "unit": "Nos.", "qty": 1, "basic": 16500, "spec": ""},
                    {"desc": "8-way TPN Memshield MCB DB c/w 100A INT. switch (Essential Power)", "unit": "Nos.", "qty": 1, "basic":  8200, "spec": ""},
                    {"desc": "6-way TPN Memshield MCB DB c/w 63A INT. switch (UPS Power)",        "unit": "Nos.", "qty": 1, "basic":  3308.81,"spec": ""},
                    {"desc": "ATS Panel 200A c/w controller",                                     "unit": "Nos.", "qty": 1, "basic": 22000, "spec": ""},
                ]},
                {"letter": "B", "title": "WIRING OF POINTS", "subsection": "Light points", "items": [
                    {"desc": "1.5mm2 PVC insulated copper cable (Brown)", "unit": "Coils", "qty": 18, "basic": 391,  "spec": ""},
                    {"desc": "1.5mm2 PVC insulated copper cable (Blue)",  "unit": "Coils", "qty": 18, "basic": 391,  "spec": ""},
                    {"desc": "20mm diameter PVC conduit pipe",            "unit": "Nos.",  "qty":300, "basic": 14.63,"spec": ""},
                ]},
                {"letter": "B", "title": "WIRING OF POINTS", "subsection": "Medical-grade socket points", "items": [
                    {"desc": "4.0mm2 PVC insulated copper cable (Brown)", "unit": "Coils", "qty": 6, "basic": 1037, "spec": ""},
                    {"desc": "4.0mm2 PVC insulated copper cable (Blue)",  "unit": "Coils", "qty": 6, "basic": 1037, "spec": ""},
                ]},
                {"letter": "C", "title": "LUMINAIRES", "subsection": "", "items": [
                    {"desc": "40W 600x600mm LED recessed panel light c/w driver", "unit": "Nos.", "qty": 22, "basic": 599, "spec": ""},
                    {"desc": "Emergency LED exam-room luminaire",                  "unit": "Nos.", "qty":  6, "basic": 850, "spec": ""},
                    {"desc": "Emergency exit luminaire c/w battery backup",        "unit": "Nos.", "qty":  6, "basic": 480, "spec": ""},
                ]},
                {"letter": "D", "title": "ACCESSORIES", "subsection": "", "items": [
                    {"desc": "Medical-grade twin socket outlet (red, essential)",  "unit": "Nos.", "qty": 18, "basic": 220, "spec": ""},
                    {"desc": "Medical-grade twin socket outlet (white, normal)",   "unit": "Nos.", "qty": 24, "basic": 180, "spec": ""},
                    {"desc": "6A One Way two gang light switch (MK)",              "unit": "Nos.", "qty": 18, "basic":  34.13, "spec": ""},
                ]},
            ]},
            {"no": 4, "name": "FIRE ALARM SYSTEM", "sections": [
                {"letter": "A", "title": "WIRING OF FIRE POINTS", "subsection": "", "items": [
                    {"desc": "3c x 2.5mm2 red fire-resistant detection cable", "unit": "M",    "qty": 350, "basic": 30,   "spec": ""},
                    {"desc": "20mm diameter thermoplastic fire conduit",       "unit": "Nos.", "qty": 80,  "basic": 14.63,"spec": ""},
                ]},
                {"letter": "B", "title": "FIRE PANEL AND ACCESSORIES", "subsection": "", "items": [
                    {"desc": "Addressable optical Smoke detector", "unit": "Nos.", "qty": 18, "basic":  532, "spec": ""},
                    {"desc": "Break glass call point",             "unit": "Nos.", "qty":  6, "basic":  600, "spec": ""},
                    {"desc": "8 Zone Addressable Fire Panel",      "unit": "Nos.", "qty":  1, "basic": 53640,"spec": ""},
                ]},
            ]},
            {"no": 6, "name": "SIGNAL COMMUNICATION SYSTEMS", "sections": [
                {"letter": "A", "title": "NURSE CALL SYSTEM", "subsection": "", "items": [
                    {"desc": "Nurse call patient bedhead unit",               "unit": "Nos.", "qty": 12, "basic": 1600, "spec": ""},
                    {"desc": "Nurse call corridor display",                    "unit": "Nos.", "qty":  2, "basic": 2200, "spec": ""},
                    {"desc": "Nurse call master station",                      "unit": "Nos.", "qty":  1, "basic": 6800, "spec": ""},
                    {"desc": "Nurse call wiring 4c x 0.5mm2 shielded",          "unit": "M",    "qty":400, "basic":   18, "spec": ""},
                ]},
            ]},
        ],
    },

    # ─── Hostel ───────────────────────────────────────────────────────────
    "hostel-typical": {
        "name":        "Hostel / Student Residence floor",
        "purpose":     "residential",
        "subtype":     "Hostel",
        "description": "Hostel-floor BOQ for student or staff accommodation -- per-room DBs, basic lighting + sockets, communal areas.",
        "bills": [
            {"no": 1, "name": "PRELIMINARIES", "sections": [
                {"letter": "A", "title": "PRELIMINARY ITEMS", "subsection": "", "items": [
                    {"desc": "Site mobilisation and setup",        "unit": "Lot", "qty": 1, "basic":  8000, "spec": ""},
                    {"desc": "Project manager allowance",          "unit": "Mth", "qty": 2, "basic":  6500, "spec": ""},
                    {"desc": "Final commissioning and handover",   "unit": "Lot", "qty": 1, "basic":  3500, "spec": ""},
                ]},
            ]},
            {"no": 2, "name": "INTERNAL ELECTRICAL WIRING", "sections": [
                {"letter": "A", "title": "SWITCH BOARDS AND DISTRIBUTION BOARDS", "subsection": "", "items": [
                    {"desc": "12-way SPN Consumer Unit c/w 100A switch (per floor)", "unit": "Nos.", "qty": 1, "basic":  3800, "spec": ""},
                    {"desc": "6-way SPN room consumer unit",                          "unit": "Nos.", "qty": 8, "basic":   850, "spec": ""},
                ]},
                {"letter": "B", "title": "WIRING OF POINTS", "subsection": "Light points (per room)", "items": [
                    {"desc": "1.5mm2 PVC insulated copper cable (Brown)", "unit": "Coils","qty":12, "basic": 391,    "spec": ""},
                    {"desc": "1.5mm2 PVC insulated copper cable (Blue)",  "unit": "Coils","qty":12, "basic": 391,    "spec": ""},
                    {"desc": "20mm diameter PVC conduit pipe",            "unit": "Nos.", "qty":180,"basic":   14.63,"spec": ""},
                    {"desc": "75mm x 75mm steel conduit boxes",           "unit": "Nos.", "qty":150,"basic":   13,   "spec": ""},
                ]},
                {"letter": "B", "title": "WIRING OF POINTS", "subsection": "Socket points (per room)", "items": [
                    {"desc": "2.5mm2 PVC insulated copper cable (Brown)", "unit": "Coils","qty": 5, "basic": 653, "spec": ""},
                    {"desc": "2.5mm2 PVC insulated copper cable (Blue)",  "unit": "Coils","qty": 5, "basic": 653, "spec": ""},
                ]},
                {"letter": "C", "title": "LUMINAIRES", "subsection": "", "items": [
                    {"desc": "18W LED ceiling round panel light",  "unit": "Nos.", "qty": 16, "basic": 226, "spec": ""},
                    {"desc": "LED bathroom waterproof fitting",     "unit": "Nos.", "qty":  8, "basic": 380, "spec": ""},
                ]},
                {"letter": "D", "title": "ACCESSORIES", "subsection": "", "items": [
                    {"desc": "6A One Way One gang light switch (MK)",  "unit": "Nos.", "qty": 16, "basic": 20.73, "spec": ""},
                    {"desc": "2 x 13A Switched Socket outlet (MK)",    "unit": "Nos.", "qty": 24, "basic": 60,    "spec": ""},
                    {"desc": "1 x 13A unswitched Socket outlet (MK)",  "unit": "Nos.", "qty":  8, "basic": 40,    "spec": ""},
                    {"desc": "20A DP switch with neon indicator (water heater)",  "unit": "Nos.", "qty":  8, "basic": 35,    "spec": ""},
                ]},
            ]},
        ],
    },
}


# ----- Helpers -----------------------------------------------------------

def _boq_template_list(purpose: str = "") -> list:
    """Public list of templates, optionally filtered by primary purpose."""
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
    """Yield flat tuples for the checkbox render:
       (bill_no, bill_name, section_letter, section_title, subsection,
        line_index, desc, unit, qty, basic, spec)
    line_index is globally unique within the template so the checkbox
    form can keep stable references on round-trip."""
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
