# === BEGIN: lv_panel_avr_seed splice ===
# 2026-07-01: LV Power Cables + Panel Boards + Automatic Voltage Regulators
# marketplace seed. Sourced verbatim from:
#   - pvsolar1/lv cable update11.txt   (24 LV cable products across 3 subcats)
#   - pvsolar1/planel update 11.txt    (34 panel board products across 7 subcats
#                                       + 19 AVR products across 2 subcats)
#
# Prices are Market Reference Prices (per source spec), NOT verified live
# supplier quotations. Suppliers can update live prices via the supplier
# portal once they onboard.
#
# Category / brand / supplier / subcategory names match _MARKETPLACE_*
# taxonomy already in web_app.py. New subcategories added by the companion
# patch script `patch_add_lv_panel_avr_subcats.py`:
#   - lv_cables: "1C XLPE/PVC"
#   - panel_boards: "SPN Distribution", "TPN Distribution"
#
# Suppliers ("Supplier / Market" column in the source spec):
#   - Agenda Electricals   (Ghana - general electrical market)
#   - Grand Pacific        (Ghana - Opera Square / Dzorwulu market channel)
#   - Opera Market         (Ghana - Opera Square electrical market)
# Grand Pacific and Agenda Electricals are near-name-matches to existing
# rows "Grand Pacific Limited" / "Agenda Commercial Limited" but are seeded
# separately here because the source spec labels them differently and lists
# these as market channels for this particular price schedule. Owner can
# consolidate later via the /admin/marketplace UI if desired.
#
# Idempotent: INSERT OR IGNORE / lower(name) pre-check for suppliers,
# (name, brand, supplier_id) dedup for products.

_LV_PANEL_AVR_SUPPLIERS = [
    # name, country, contact_name, phone, email, website, address, categories
    ("Agenda Electricals", "Ghana", "Sales",
     "+233 302 000 000", "", "",
     "Accra, Ghana",
     "LV Cables, Panel Boards, Distribution Boards, AVRs, Electrical Materials"),
    ("Grand Pacific", "Ghana", "Sales",
     "+233 302 782 868", "marketing@grandpacificgh.com", "www.grandpacificgh.com",
     "N1 Highway Dzorwulu; Opera Square Accra; P.O. Box 140, Korle-Bu, Accra, Ghana",
     "LV Cables, Panel Boards, AVRs, UPS, Generators, Distribution Boards"),
    ("Opera Market", "Ghana", "Multiple Vendors",
     "+233 302 000 000", "", "",
     "Opera Square Electrical Market, Accra, Ghana",
     "LV Cables, Panel Boards, AVRs, General Electrical Supplies"),
]


# Product tuple:
# (supplier_name_lookup, category_code, name, brand, model, spec, unit,
#  price_ghs, lead_days, subcategory)

_LV_PANEL_AVR_PRODUCTS_GHS = [
    # ================================================================
    # A. LV Cables -- 4-Core XLPE/SWA/PVC Copper Armoured, 600/1000V
    # ================================================================
    ("Agenda Electricals", "lv_cables", "4C x 70mm2 Cu XLPE/SWA/PVC Armoured Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-4C-70-XLPE",
     "4-core 70mm2 copper XLPE insulated, PVC bedded, SWA armoured, PVC outer sheath, 600/1000V",
     "m", 900.00, 21, "XLPE/SWA/PVC"),
    ("Grand Pacific", "lv_cables", "4C x 95mm2 Cu XLPE/SWA/PVC Armoured Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-4C-95-XLPE",
     "4-core 95mm2 copper XLPE insulated, PVC bedded, SWA armoured, PVC outer sheath, 600/1000V",
     "m", 1190.00, 21, "XLPE/SWA/PVC"),
    ("Opera Market", "lv_cables", "4C x 120mm2 Cu XLPE/SWA/PVC Armoured Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-4C-120-XLPE",
     "4-core 120mm2 copper XLPE insulated, PVC bedded, SWA armoured, PVC outer sheath, 600/1000V",
     "m", 1500.00, 21, "XLPE/SWA/PVC"),
    ("Agenda Electricals", "lv_cables", "4C x 150mm2 Cu XLPE/SWA/PVC Armoured Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-4C-150-XLPE",
     "4-core 150mm2 copper XLPE insulated, PVC bedded, SWA armoured, PVC outer sheath, 600/1000V",
     "m", 1850.00, 21, "XLPE/SWA/PVC"),
    ("Grand Pacific", "lv_cables", "4C x 185mm2 Cu XLPE/SWA/PVC Armoured Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-4C-185-XLPE",
     "4-core 185mm2 copper XLPE insulated, PVC bedded, SWA armoured, PVC outer sheath, 600/1000V",
     "m", 2300.00, 21, "XLPE/SWA/PVC"),
    ("Opera Market", "lv_cables", "4C x 240mm2 Cu XLPE/SWA/PVC Armoured Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-4C-240-XLPE",
     "4-core 240mm2 copper XLPE insulated, PVC bedded, SWA armoured, PVC outer sheath, 600/1000V",
     "m", 3000.00, 21, "XLPE/SWA/PVC"),
    ("Agenda Electricals", "lv_cables", "4C x 300mm2 Cu XLPE/SWA/PVC Armoured Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-4C-300-XLPE",
     "4-core 300mm2 copper XLPE insulated, PVC bedded, SWA armoured, PVC outer sheath, 600/1000V",
     "m", 3750.00, 21, "XLPE/SWA/PVC"),
    ("Grand Pacific", "lv_cables", "4C x 400mm2 Cu XLPE/SWA/PVC Armoured Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-4C-400-XLPE",
     "4-core 400mm2 copper XLPE insulated, PVC bedded, SWA armoured, PVC outer sheath, 600/1000V",
     "m", 5000.00, 28, "XLPE/SWA/PVC"),

    # ================================================================
    # B. LV Cables -- 4-Core PVC/SWA/PVC Copper Armoured, 600/1000V
    # ================================================================
    ("Agenda Electricals", "lv_cables", "4C x 70mm2 Cu PVC/SWA/PVC Armoured Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-4C-70-PVC",
     "4-core 70mm2 copper PVC insulated, PVC bedded, SWA armoured, PVC outer sheath, 600/1000V",
     "m", 840.00, 21, "PVC/SWA/PVC"),
    ("Grand Pacific", "lv_cables", "4C x 95mm2 Cu PVC/SWA/PVC Armoured Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-4C-95-PVC",
     "4-core 95mm2 copper PVC insulated, PVC bedded, SWA armoured, PVC outer sheath, 600/1000V",
     "m", 1110.00, 21, "PVC/SWA/PVC"),
    ("Opera Market", "lv_cables", "4C x 120mm2 Cu PVC/SWA/PVC Armoured Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-4C-120-PVC",
     "4-core 120mm2 copper PVC insulated, PVC bedded, SWA armoured, PVC outer sheath, 600/1000V",
     "m", 1400.00, 21, "PVC/SWA/PVC"),
    ("Agenda Electricals", "lv_cables", "4C x 150mm2 Cu PVC/SWA/PVC Armoured Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-4C-150-PVC",
     "4-core 150mm2 copper PVC insulated, PVC bedded, SWA armoured, PVC outer sheath, 600/1000V",
     "m", 1730.00, 21, "PVC/SWA/PVC"),
    ("Grand Pacific", "lv_cables", "4C x 185mm2 Cu PVC/SWA/PVC Armoured Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-4C-185-PVC",
     "4-core 185mm2 copper PVC insulated, PVC bedded, SWA armoured, PVC outer sheath, 600/1000V",
     "m", 2150.00, 21, "PVC/SWA/PVC"),
    ("Opera Market", "lv_cables", "4C x 240mm2 Cu PVC/SWA/PVC Armoured Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-4C-240-PVC",
     "4-core 240mm2 copper PVC insulated, PVC bedded, SWA armoured, PVC outer sheath, 600/1000V",
     "m", 2800.00, 21, "PVC/SWA/PVC"),
    ("Agenda Electricals", "lv_cables", "4C x 300mm2 Cu PVC/SWA/PVC Armoured Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-4C-300-PVC",
     "4-core 300mm2 copper PVC insulated, PVC bedded, SWA armoured, PVC outer sheath, 600/1000V",
     "m", 3500.00, 21, "PVC/SWA/PVC"),
    ("Grand Pacific", "lv_cables", "4C x 400mm2 Cu PVC/SWA/PVC Armoured Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-4C-400-PVC",
     "4-core 400mm2 copper PVC insulated, PVC bedded, SWA armoured, PVC outer sheath, 600/1000V",
     "m", 4650.00, 28, "PVC/SWA/PVC"),

    # ================================================================
    # C. LV Cables -- Single-Core XLPE/PVC Copper Cable, 600/1000V
    # ================================================================
    ("Agenda Electricals", "lv_cables", "1C x 70mm2 Cu XLPE/PVC Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-1C-70-XLPE",
     "Single-core 70mm2 copper XLPE insulated, PVC outer sheath, 600/1000V, unarmoured",
     "m", 230.00, 14, "1C XLPE/PVC"),
    ("Grand Pacific", "lv_cables", "1C x 95mm2 Cu XLPE/PVC Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-1C-95-XLPE",
     "Single-core 95mm2 copper XLPE insulated, PVC outer sheath, 600/1000V, unarmoured",
     "m", 310.00, 14, "1C XLPE/PVC"),
    ("Opera Market", "lv_cables", "1C x 120mm2 Cu XLPE/PVC Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-1C-120-XLPE",
     "Single-core 120mm2 copper XLPE insulated, PVC outer sheath, 600/1000V, unarmoured",
     "m", 390.00, 14, "1C XLPE/PVC"),
    ("Agenda Electricals", "lv_cables", "1C x 150mm2 Cu XLPE/PVC Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-1C-150-XLPE",
     "Single-core 150mm2 copper XLPE insulated, PVC outer sheath, 600/1000V, unarmoured",
     "m", 485.00, 14, "1C XLPE/PVC"),
    ("Grand Pacific", "lv_cables", "1C x 185mm2 Cu XLPE/PVC Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-1C-185-XLPE",
     "Single-core 185mm2 copper XLPE insulated, PVC outer sheath, 600/1000V, unarmoured",
     "m", 600.00, 14, "1C XLPE/PVC"),
    ("Opera Market", "lv_cables", "1C x 240mm2 Cu XLPE/PVC Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-1C-240-XLPE",
     "Single-core 240mm2 copper XLPE insulated, PVC outer sheath, 600/1000V, unarmoured",
     "m", 775.00, 14, "1C XLPE/PVC"),
    ("Agenda Electricals", "lv_cables", "1C x 300mm2 Cu XLPE/PVC Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-1C-300-XLPE",
     "Single-core 300mm2 copper XLPE insulated, PVC outer sheath, 600/1000V, unarmoured",
     "m", 970.00, 14, "1C XLPE/PVC"),
    ("Grand Pacific", "lv_cables", "1C x 400mm2 Cu XLPE/PVC Cable 600/1000V",
     "Nexans / Tropical / Elsewedy", "LV-1C-400-XLPE",
     "Single-core 400mm2 copper XLPE insulated, PVC outer sheath, 600/1000V, unarmoured",
     "m", 1290.00, 21, "1C XLPE/PVC"),

    # ================================================================
    # D. Panel Boards -- SPN Distribution Boards, 230V, Single Phase
    # ================================================================
    ("Agenda Electricals", "panel_boards", "4 Way SPN Distribution Board, 63A incomer, MCB outgoing ways, metal enclosure",
     "Schneider / ABB / Hager", "SPN-4W-63A",
     "4-way SPN distribution board, 230V single phase 50Hz, 63A SP incomer, MCB outgoing ways, metal enclosure IP42",
     "No.", 850.00, 14, "SPN Distribution"),
    ("Grand Pacific", "panel_boards", "6 Way SPN Distribution Board, 63A incomer, MCB outgoing ways, metal enclosure",
     "Schneider / ABB / Hager", "SPN-6W-63A",
     "6-way SPN distribution board, 230V single phase 50Hz, 63A SP incomer, MCB outgoing ways, metal enclosure IP42",
     "No.", 1050.00, 14, "SPN Distribution"),
    ("Opera Market", "panel_boards", "8 Way SPN Distribution Board, 63A incomer, MCB outgoing ways, metal enclosure",
     "Schneider / ABB / Hager", "SPN-8W-63A",
     "8-way SPN distribution board, 230V single phase 50Hz, 63A SP incomer, MCB outgoing ways, metal enclosure IP42",
     "No.", 1250.00, 14, "SPN Distribution"),
    ("Agenda Electricals", "panel_boards", "12 Way SPN Distribution Board, 80A incomer, MCB outgoing ways, metal enclosure",
     "Schneider / ABB / Hager", "SPN-12W-80A",
     "12-way SPN distribution board, 230V single phase 50Hz, 80A SP incomer, MCB outgoing ways, metal enclosure IP42",
     "No.", 1650.00, 14, "SPN Distribution"),
    ("Grand Pacific", "panel_boards", "16 Way SPN Distribution Board, 100A incomer, MCB outgoing ways, metal enclosure",
     "Schneider / ABB / Hager", "SPN-16W-100A",
     "16-way SPN distribution board, 230V single phase 50Hz, 100A SP incomer, MCB outgoing ways, metal enclosure IP42",
     "No.", 2200.00, 14, "SPN Distribution"),

    # ================================================================
    # E. Panel Boards -- TPN Distribution Boards, 400/230V, Three Phase
    # ================================================================
    ("Agenda Electricals", "panel_boards", "4 Way TPN Distribution Board, 100A TP incomer, MCB outgoing ways",
     "Schneider / ABB / Hager / Legrand", "TPN-4W-100A",
     "4-way TPN distribution board, 400/230V three phase 50Hz, 100A TP&N incomer, MCB outgoing ways, metal enclosure IP42",
     "No.", 3500.00, 21, "TPN Distribution"),
    ("Grand Pacific", "panel_boards", "6 Way TPN Distribution Board, 100A TP incomer, MCB outgoing ways",
     "Schneider / ABB / Hager / Legrand", "TPN-6W-100A",
     "6-way TPN distribution board, 400/230V three phase 50Hz, 100A TP&N incomer, MCB outgoing ways, metal enclosure IP42",
     "No.", 4200.00, 21, "TPN Distribution"),
    ("Opera Market", "panel_boards", "8 Way TPN Distribution Board, 125A TP incomer, MCB outgoing ways",
     "Schneider / ABB / Hager / Legrand", "TPN-8W-125A",
     "8-way TPN distribution board, 400/230V three phase 50Hz, 125A TP&N incomer, MCB outgoing ways, metal enclosure IP42",
     "No.", 5200.00, 21, "TPN Distribution"),
    ("Agenda Electricals", "panel_boards", "12 Way TPN Distribution Board, 160A TP incomer, MCB outgoing ways",
     "Schneider / ABB / Hager / Legrand", "TPN-12W-160A",
     "12-way TPN distribution board, 400/230V three phase 50Hz, 160A TP&N incomer, MCB outgoing ways, metal enclosure IP42",
     "No.", 6800.00, 21, "TPN Distribution"),
    ("Grand Pacific", "panel_boards", "16 Way TPN Distribution Board, 200A TP incomer, MCB outgoing ways",
     "Schneider / ABB / Hager / Legrand", "TPN-16W-200A",
     "16-way TPN distribution board, 400/230V three phase 50Hz, 200A TP&N incomer, MCB outgoing ways, metal enclosure IP42",
     "No.", 8500.00, 21, "TPN Distribution"),

    # ================================================================
    # F. Panel Boards -- Sub-Main Panel Boards, 400/230V
    # ================================================================
    ("Agenda Electricals", "panel_boards", "125A TP&N Sub-Main Panel Board, MCCB incomer, outgoing MCCBs, metering, SPD",
     "Schneider / ABB / Siemens", "SMP-125A",
     "125A TP&N sub-main panel, 400/230V three phase 50Hz, MCCB incomer, outgoing MCCB ways, metering (V/A/kWh), Type 2 SPD, IP42 metal enclosure",
     "No.", 12500.00, 30, "Sub-main Panel"),
    ("Grand Pacific", "panel_boards", "160A TP&N Sub-Main Panel Board, MCCB incomer, outgoing MCCBs, metering, SPD",
     "Schneider / ABB / Siemens", "SMP-160A",
     "160A TP&N sub-main panel, 400/230V three phase 50Hz, MCCB incomer, outgoing MCCB ways, metering (V/A/kWh), Type 2 SPD, IP42 metal enclosure",
     "No.", 15000.00, 30, "Sub-main Panel"),
    ("Opera Market", "panel_boards", "250A TP&N Sub-Main Panel Board, MCCB incomer, outgoing MCCBs, metering, SPD",
     "Schneider / ABB / Siemens", "SMP-250A",
     "250A TP&N sub-main panel, 400/230V three phase 50Hz, MCCB incomer, outgoing MCCB ways, metering (V/A/kWh), Type 2 SPD, IP42 metal enclosure",
     "No.", 22000.00, 30, "Sub-main Panel"),
    ("Agenda Electricals", "panel_boards", "400A TP&N Sub-Main Panel Board, MCCB incomer, outgoing MCCBs, metering, SPD",
     "Schneider / ABB / Siemens", "SMP-400A",
     "400A TP&N sub-main panel, 400/230V three phase 50Hz, MCCB incomer, outgoing MCCB ways, metering (V/A/kWh), Type 2 SPD, IP42 metal enclosure",
     "No.", 34000.00, 45, "Sub-main Panel"),
    ("Grand Pacific", "panel_boards", "630A TP&N Sub-Main Panel Board, MCCB incomer, outgoing MCCBs, metering, SPD",
     "Schneider / ABB / Siemens", "SMP-630A",
     "630A TP&N sub-main panel, 400/230V three phase 50Hz, MCCB incomer, outgoing MCCB ways, metering (V/A/kWh), Type 2 SPD, IP42 floor-standing enclosure",
     "No.", 55000.00, 45, "Sub-main Panel"),

    # ================================================================
    # G. Panel Boards -- Main LV Panel Boards, Floor Standing
    # ================================================================
    ("Agenda Electricals", "panel_boards", "800A Main LV Panel Board, ACB incomer, MCCB feeders, metering, SPD, busbars",
     "Schneider / ABB / Siemens / LS", "MLV-800A",
     "800A main LV panel, 400/230V three phase 50Hz, ACB incomer with electronic trip, MCCB feeders, full metering, Type 1+2 SPD, tin-plated Cu busbars, floor-standing IP42 enclosure",
     "No.", 95000.00, 60, "Main Panel"),
    ("Grand Pacific", "panel_boards", "1000A Main LV Panel Board, ACB incomer, MCCB feeders, metering, SPD, busbars",
     "Schneider / ABB / Siemens / LS", "MLV-1000A",
     "1000A main LV panel, 400/230V three phase 50Hz, ACB incomer with electronic trip, MCCB feeders, full metering, Type 1+2 SPD, tin-plated Cu busbars, floor-standing IP42 enclosure",
     "No.", 125000.00, 60, "Main Panel"),
    ("Opera Market", "panel_boards", "1250A Main LV Panel Board, ACB incomer, MCCB feeders, metering, SPD, busbars",
     "Schneider / ABB / Siemens / LS", "MLV-1250A",
     "1250A main LV panel, 400/230V three phase 50Hz, ACB incomer with electronic trip, MCCB feeders, full metering, Type 1+2 SPD, tin-plated Cu busbars, floor-standing IP42 enclosure",
     "No.", 160000.00, 75, "Main Panel"),
    ("Agenda Electricals", "panel_boards", "1600A Main LV Panel Board, ACB incomer, MCCB feeders, metering, SPD, busbars",
     "Schneider / ABB / Siemens / LS", "MLV-1600A",
     "1600A main LV panel, 400/230V three phase 50Hz, ACB incomer with electronic trip, MCCB feeders, full metering, Type 1+2 SPD, tin-plated Cu busbars, floor-standing IP42 enclosure",
     "No.", 220000.00, 75, "Main Panel"),
    ("Grand Pacific", "panel_boards", "2000A Main LV Panel Board, ACB incomer, MCCB feeders, metering, SPD, busbars",
     "Schneider / ABB / Siemens / LS", "MLV-2000A",
     "2000A main LV panel, 400/230V three phase 50Hz, ACB incomer with electronic trip, MCCB feeders, full metering, Type 1+2 SPD, tin-plated Cu busbars, floor-standing IP42 enclosure",
     "No.", 310000.00, 90, "Main Panel"),

    # ================================================================
    # H. Panel Boards -- Automatic Transfer Switch (ATS) Panels
    # ================================================================
    ("Agenda Electricals", "panel_boards", "100A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure",
     "Socomec / Schneider / ABB", "ATS-100A-4P",
     "100A ATS panel, 4-pole, mains/generator changeover, controller with AMF logic, indicator lamps, IP54 metal enclosure",
     "No.", 12000.00, 30, "ATS Panel"),
    ("Grand Pacific", "panel_boards", "160A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure",
     "Socomec / Schneider / ABB", "ATS-160A-4P",
     "160A ATS panel, 4-pole, mains/generator changeover, controller with AMF logic, indicator lamps, IP54 metal enclosure",
     "No.", 16000.00, 30, "ATS Panel"),
    ("Opera Market", "panel_boards", "250A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure",
     "Socomec / Schneider / ABB", "ATS-250A-4P",
     "250A ATS panel, 4-pole, mains/generator changeover, controller with AMF logic, indicator lamps, IP54 metal enclosure",
     "No.", 24000.00, 30, "ATS Panel"),
    ("Agenda Electricals", "panel_boards", "400A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure",
     "Socomec / Schneider / ABB", "ATS-400A-4P",
     "400A ATS panel, 4-pole, mains/generator changeover, controller with AMF logic, indicator lamps, IP54 metal enclosure",
     "No.", 38000.00, 45, "ATS Panel"),
    ("Grand Pacific", "panel_boards", "630A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure",
     "Socomec / Schneider / ABB", "ATS-630A-4P",
     "630A ATS panel, 4-pole, mains/generator changeover, controller with AMF logic, indicator lamps, IP54 metal enclosure",
     "No.", 65000.00, 45, "ATS Panel"),
    ("Opera Market", "panel_boards", "1000A Automatic Transfer Switch Panel, 4P, mains/generator, controller, enclosure",
     "Socomec / Schneider / ABB", "ATS-1000A-4P",
     "1000A ATS panel, 4-pole, mains/generator changeover, controller with AMF logic, indicator lamps, IP54 metal enclosure",
     "No.", 110000.00, 60, "ATS Panel"),

    # ================================================================
    # I. Panel Boards -- Motor Control Centre (MCC) Panels
    # ================================================================
    ("Agenda Electricals", "panel_boards", "4 Feeder MCC Panel, motor starters, overloads, control wiring, enclosure",
     "Schneider / ABB / Siemens / LS", "MCC-4F",
     "4-feeder MCC panel, DOL/star-delta motor starters with overload relays, control wiring, aux contacts, indicator lamps, IP42 enclosure",
     "No.", 28000.00, 45, "MCC Panel"),
    ("Grand Pacific", "panel_boards", "6 Feeder MCC Panel, motor starters, overloads, control wiring, enclosure",
     "Schneider / ABB / Siemens / LS", "MCC-6F",
     "6-feeder MCC panel, DOL/star-delta motor starters with overload relays, control wiring, aux contacts, indicator lamps, IP42 enclosure",
     "No.", 38000.00, 45, "MCC Panel"),
    ("Opera Market", "panel_boards", "8 Feeder MCC Panel, motor starters, overloads, control wiring, enclosure",
     "Schneider / ABB / Siemens / LS", "MCC-8F",
     "8-feeder MCC panel, DOL/star-delta motor starters with overload relays, control wiring, aux contacts, indicator lamps, IP42 enclosure",
     "No.", 50000.00, 60, "MCC Panel"),
    ("Agenda Electricals", "panel_boards", "12 Feeder MCC Panel, motor starters, overloads, control wiring, enclosure",
     "Schneider / ABB / Siemens / LS", "MCC-12F",
     "12-feeder MCC panel, DOL/star-delta motor starters with overload relays, control wiring, aux contacts, indicator lamps, IP42 enclosure",
     "No.", 72000.00, 60, "MCC Panel"),

    # ================================================================
    # J. Panel Boards -- Power Factor Correction (PFC) Panels
    # ================================================================
    ("Agenda Electricals", "panel_boards", "50 kVAr Automatic PFC Panel, capacitors, contactors, controller, enclosure",
     "Schneider / ABB / Ducati / Circutor", "PFC-50KVAR",
     "50 kVAr automatic power factor correction panel, dry-type capacitors, PFC contactors, PFC controller, IP42 metal enclosure",
     "No.", 20000.00, 45, "PFC Panel"),
    ("Grand Pacific", "panel_boards", "100 kVAr Automatic PFC Panel, capacitors, contactors, controller, enclosure",
     "Schneider / ABB / Ducati / Circutor", "PFC-100KVAR",
     "100 kVAr automatic power factor correction panel, dry-type capacitors, PFC contactors, PFC controller, IP42 metal enclosure",
     "No.", 34000.00, 45, "PFC Panel"),
    ("Opera Market", "panel_boards", "150 kVAr Automatic PFC Panel, capacitors, contactors, controller, enclosure",
     "Schneider / ABB / Ducati / Circutor", "PFC-150KVAR",
     "150 kVAr automatic power factor correction panel, dry-type capacitors, PFC contactors, PFC controller, IP42 metal enclosure",
     "No.", 48000.00, 60, "PFC Panel"),
    ("Agenda Electricals", "panel_boards", "200 kVAr Automatic PFC Panel, capacitors, contactors, controller, enclosure",
     "Schneider / ABB / Ducati / Circutor", "PFC-200KVAR",
     "200 kVAr automatic power factor correction panel, dry-type capacitors, PFC contactors, PFC controller, IP42 metal enclosure",
     "No.", 62000.00, 60, "PFC Panel"),

    # ================================================================
    # K. AVRs -- Single Phase Automatic Voltage Regulators
    # ================================================================
    ("Agenda Electricals", "avr", "1 kVA Single Phase Automatic Voltage Regulator",
     "Sollatek / Blue Gate / APC", "AVR-1KVA-1P",
     "1 kVA single-phase AVR, 230V input 140-260V, output 230V +/-3%, 50Hz, bypass switch, digital display, overload/short-circuit/over-voltage/under-voltage protection",
     "No.", 850.00, 14, "Single-phase"),
    ("Grand Pacific", "avr", "2 kVA Single Phase Automatic Voltage Regulator",
     "Sollatek / Blue Gate / APC", "AVR-2KVA-1P",
     "2 kVA single-phase AVR, 230V input 140-260V, output 230V +/-3%, 50Hz, bypass switch, digital display, overload/short-circuit/over-voltage/under-voltage protection",
     "No.", 1250.00, 14, "Single-phase"),
    ("Opera Market", "avr", "3 kVA Single Phase Automatic Voltage Regulator",
     "Sollatek / Blue Gate / APC", "AVR-3KVA-1P",
     "3 kVA single-phase AVR, 230V input 140-260V, output 230V +/-3%, 50Hz, bypass switch, digital display, overload/short-circuit/over-voltage/under-voltage protection",
     "No.", 1850.00, 14, "Single-phase"),
    ("Agenda Electricals", "avr", "5 kVA Single Phase Automatic Voltage Regulator",
     "Sollatek / Blue Gate / APC", "AVR-5KVA-1P",
     "5 kVA single-phase AVR, 230V input 140-260V, output 230V +/-3%, 50Hz, bypass switch, digital display, overload/short-circuit/over-voltage/under-voltage protection",
     "No.", 2850.00, 14, "Single-phase"),
    ("Grand Pacific", "avr", "7.5 kVA Single Phase Automatic Voltage Regulator",
     "Sollatek / Blue Gate / APC", "AVR-7.5KVA-1P",
     "7.5 kVA single-phase AVR, 230V input 140-260V, output 230V +/-3%, 50Hz, bypass switch, digital display, overload/short-circuit/over-voltage/under-voltage protection",
     "No.", 4500.00, 14, "Single-phase"),
    ("Opera Market", "avr", "10 kVA Single Phase Automatic Voltage Regulator",
     "Sollatek / Blue Gate / APC", "AVR-10KVA-1P",
     "10 kVA single-phase AVR, 230V input 140-260V, output 230V +/-3%, 50Hz, bypass switch, digital display, overload/short-circuit/over-voltage/under-voltage protection",
     "No.", 5800.00, 21, "Single-phase"),
    ("Agenda Electricals", "avr", "15 kVA Single Phase Automatic Voltage Regulator",
     "Sollatek / Blue Gate / APC", "AVR-15KVA-1P",
     "15 kVA single-phase AVR, 230V input 140-260V, output 230V +/-3%, 50Hz, bypass switch, digital display, overload/short-circuit/over-voltage/under-voltage protection",
     "No.", 8200.00, 21, "Single-phase"),
    ("Grand Pacific", "avr", "20 kVA Single Phase Automatic Voltage Regulator",
     "Sollatek / Blue Gate / APC", "AVR-20KVA-1P",
     "20 kVA single-phase AVR, 230V input 140-260V, output 230V +/-3%, 50Hz, bypass switch, digital display, overload/short-circuit/over-voltage/under-voltage protection",
     "No.", 10800.00, 21, "Single-phase"),

    # ================================================================
    # L. AVRs -- Three Phase Automatic Voltage Regulators
    # ================================================================
    ("Agenda Electricals", "avr", "10 kVA Three Phase Automatic Voltage Regulator",
     "Sollatek / ServoMax / ABB", "AVR-10KVA-3P",
     "10 kVA three-phase AVR, 400V input 280-460V, output 400V +/-1%, 50Hz, servo/static regulation, bypass switch, digital display, full protection suite, floor-standing enclosure",
     "No.", 12500.00, 30, "Three-phase"),
    ("Grand Pacific", "avr", "15 kVA Three Phase Automatic Voltage Regulator",
     "Sollatek / ServoMax / ABB", "AVR-15KVA-3P",
     "15 kVA three-phase AVR, 400V input 280-460V, output 400V +/-1%, 50Hz, servo/static regulation, bypass switch, digital display, full protection suite, floor-standing enclosure",
     "No.", 15500.00, 30, "Three-phase"),
    ("Opera Market", "avr", "20 kVA Three Phase Automatic Voltage Regulator",
     "Sollatek / ServoMax / ABB", "AVR-20KVA-3P",
     "20 kVA three-phase AVR, 400V input 280-460V, output 400V +/-1%, 50Hz, servo/static regulation, bypass switch, digital display, full protection suite, floor-standing enclosure",
     "No.", 18500.00, 30, "Three-phase"),
    ("Agenda Electricals", "avr", "30 kVA Three Phase Automatic Voltage Regulator",
     "Sollatek / ServoMax / ABB", "AVR-30KVA-3P",
     "30 kVA three-phase AVR, 400V input 280-460V, output 400V +/-1%, 50Hz, servo/static regulation, bypass switch, digital display, full protection suite, floor-standing enclosure",
     "No.", 24000.00, 30, "Three-phase"),
    ("Grand Pacific", "avr", "50 kVA Three Phase Automatic Voltage Regulator",
     "Sollatek / ServoMax / ABB", "AVR-50KVA-3P",
     "50 kVA three-phase AVR, 400V input 280-460V, output 400V +/-1%, 50Hz, servo/static regulation, bypass switch, digital display, full protection suite, floor-standing enclosure",
     "No.", 36000.00, 45, "Three-phase"),
    ("Opera Market", "avr", "75 kVA Three Phase Automatic Voltage Regulator",
     "Sollatek / ServoMax / ABB", "AVR-75KVA-3P",
     "75 kVA three-phase AVR, 400V input 280-460V, output 400V +/-1%, 50Hz, servo/static regulation, bypass switch, digital display, full protection suite, floor-standing enclosure",
     "No.", 52000.00, 45, "Three-phase"),
    ("Agenda Electricals", "avr", "100 kVA Three Phase Automatic Voltage Regulator",
     "Sollatek / ServoMax / ABB", "AVR-100KVA-3P",
     "100 kVA three-phase AVR, 400V input 280-460V, output 400V +/-1%, 50Hz, servo/static regulation, bypass switch, digital display, full protection suite, floor-standing enclosure",
     "No.", 68000.00, 45, "Three-phase"),
    ("Grand Pacific", "avr", "150 kVA Three Phase Automatic Voltage Regulator",
     "Sollatek / ServoMax / ABB", "AVR-150KVA-3P",
     "150 kVA three-phase AVR, 400V input 280-460V, output 400V +/-1%, 50Hz, servo/static regulation, bypass switch, digital display, full protection suite, floor-standing enclosure",
     "No.", 98000.00, 60, "Three-phase"),
    ("Opera Market", "avr", "200 kVA Three Phase Automatic Voltage Regulator",
     "Sollatek / ServoMax / ABB", "AVR-200KVA-3P",
     "200 kVA three-phase AVR, 400V input 280-460V, output 400V +/-1%, 50Hz, servo/static regulation, bypass switch, digital display, full protection suite, floor-standing enclosure",
     "No.", 128000.00, 60, "Three-phase"),
    ("Agenda Electricals", "avr", "300 kVA Three Phase Automatic Voltage Regulator",
     "Sollatek / ServoMax / ABB", "AVR-300KVA-3P",
     "300 kVA three-phase AVR, 400V input 280-460V, output 400V +/-1%, 50Hz, servo/static regulation, bypass switch, digital display, full protection suite, floor-standing enclosure",
     "No.", 185000.00, 75, "Three-phase"),
    ("Grand Pacific", "avr", "500 kVA Three Phase Automatic Voltage Regulator",
     "Sollatek / ServoMax / ABB", "AVR-500KVA-3P",
     "500 kVA three-phase AVR, 400V input 280-460V, output 400V +/-1%, 50Hz, servo/static regulation, bypass switch, digital display, full protection suite, floor-standing enclosure",
     "No.", 295000.00, 90, "Three-phase"),
]


def _seed_lv_panel_avr_products():
    """Idempotent seed of the LV Cable / Panel Board / AVR marketplace
    schedules sourced from pvsolar1/lv cable update11.txt +
    pvsolar1/planel update 11.txt. Safe to run on every cold start.

    Suppliers: (name) is unique-keyed via lower(trim(name)) pre-check.
    Products: dedup on (name, brand, supplier_id) so re-running never
    duplicates a row.

    Called from _ensure_marketplace_tables() alongside
    _seed_ghana_suppliers_products(). Also exposed at
    /admin/marketplace/reseed-lv-panel-avr for manual re-run.
    """
    try:
        with get_db() as c:
            # ---------------------------------------------------------
            # Suppliers -- 3 new market channels per source spec.
            # ---------------------------------------------------------
            existing = {}
            try:
                rows = c.execute("SELECT id, LOWER(TRIM(name)) AS n FROM suppliers").fetchall()
                for r in rows:
                    key = r["n"] if hasattr(r, "keys") else r[1]
                    rid = r["id"] if hasattr(r, "keys") else r[0]
                    existing[key] = rid
            except Exception:
                pass

            for (name, country, contact, phone, email, website, address, categories) in _LV_PANEL_AVR_SUPPLIERS:
                key = name.lower().strip()
                if key in existing:
                    continue
                try:
                    c.execute(
                        "INSERT INTO suppliers (name,country,contact_name,phone,email,website,address,"
                        "categories,lead_time_days,payment_terms,rating,user_id,is_verified,is_active) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (name, country, contact, phone, email, website, address,
                         categories, 21, "TT 30 days", 5, 0, 1, 1),
                    )
                except Exception:
                    pass

            # Rebuild supplier index.
            sup_index = {}
            try:
                rows = c.execute("SELECT id, name FROM suppliers WHERE is_active=1").fetchall()
                for r in rows:
                    sup_index[(r["name"] if hasattr(r, "keys") else r[1]).strip()] = (r["id"] if hasattr(r, "keys") else r[0])
            except Exception:
                pass

            # Category index by code.
            cat_index = {}
            try:
                rows = c.execute("SELECT id, code FROM product_categories WHERE is_active=1").fetchall()
                for r in rows:
                    cat_index[(r["code"] if hasattr(r, "keys") else r[1])] = (r["id"] if hasattr(r, "keys") else r[0])
            except Exception:
                pass

            # ---------------------------------------------------------
            # Products -- convert GHS -> USD, INSERT with dedup.
            # ---------------------------------------------------------
            try:
                _ghs_per_usd = float(_CURRENCY_RATES_FROM_USD.get("GHS", 14.5) or 14.5)
            except Exception:
                _ghs_per_usd = 14.5

            for (sup_name, cat_code, name, brand, model, spec, unit, price_ghs, lead, subcategory) in _LV_PANEL_AVR_PRODUCTS_GHS:
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
        try: app.logger.warning("_seed_lv_panel_avr_products failed: %s", _e)
        except Exception: pass


@app.route("/admin/marketplace/reseed-lv-panel-avr", methods=["POST"])
@admin_required
def admin_marketplace_reseed_lv_panel_avr():
    """One-shot reseed of the LV Cable + Panel Board + AVR schedules.
    Safe to invoke any number of times -- duplicates are dropped on
    lower(name) for suppliers and (name+brand+supplier_id) for products."""
    csrf_protect()
    _ensure_marketplace_tables()
    _seed_lv_panel_avr_products()
    flash("LV Cables + Panel Boards + AVRs re-seeded (77 products across 3 categories, 3 suppliers).", "success")
    return redirect(url_for("admin_marketplace_dashboard"))


# === END: lv_panel_avr_seed splice ===
