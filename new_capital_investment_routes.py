# -*- coding: utf-8 -*-
"""
new_capital_investment_routes.py
================================
PV Independent Solar Capital Investment Design Module.

Extends SolarPro (does NOT duplicate). Source spec:
    C:\\Users\\USER\\Documents\\pvsolar1\\solar power plant1.txt

The module lives at URL prefix /large-scale-solar and adds a 14-step
wizard for utility-scale / IPP / commercial-generation solar plant
design that REUSES the existing SolarPro engines:

    Step 1  Project Registration                (this module)
    Step 2  Project Type                        (this module)
    Step 3  Site Configuration                  (this module)
    Step 4  Facility Configuration              (this module + BOQ hierarchy)
    Step 5  Technology Configuration            (this module)
    Step 6  Electrical System Configuration     (reuses _BOQ_SERVICES)
    Step 7  PV Design                           (reuses calc_pv / calc_boq)
    Step 8  Financial Engineering               (reuses calc_economics + adds LCOE/MC)
    Step 9  BOQ                                 (reuses Section-by-Section + Build-all)
    Step 10 Marketplace                         (reuses BOM->BOQ sync)
    Step 11 CRM                                 (reuses leads / assessment_requests)
    Step 12 Sales Pipeline                      (reuses admin_pipeline stages)
    Step 13 Reports                             (reuses _render_pdf + bespoke PDFs)
    Step 14 AI Agents                           (hook only; wired later per operator)

    +Development & Regulatory Configuration     (spec recommendation)
    +3D Digital Twin Studio                     (replaces /project/<pid>/shading)

Slice 1 (this commit) implements: landing, Step 1 registration, project
overview. Later slices extend the same wizard shell.

Entry point for web_app.py:
    from new_capital_investment_routes import register_capital_investment
    register_capital_investment(app)

Author: SolarPro platform team
Date:   2026-07-01
"""

from __future__ import annotations

import json
from functools import wraps
from typing import Any

from flask import (
    render_template, request, redirect, url_for,
    session, flash, abort, jsonify,
)


# ---------------------------------------------------------------------------
# Constants (Step 2 project types, Step 1 dropdowns)
# ---------------------------------------------------------------------------

# Spec Step 2 - user picks exactly one.
PROJECT_TYPES: list[tuple[str, str, str]] = [
    ("ground_mount",       "Ground-Mounted Solar Farm",        "bi-tree"),
    ("commercial_rooftop", "Commercial Rooftop Generation",    "bi-buildings"),
    ("industrial",         "Industrial Solar Plant",           "bi-tools"),
    ("utility_scale",      "Utility-Scale Solar",              "bi-lightning-charge"),
    ("embedded",           "Embedded Generation",              "bi-plug"),
    ("ipp",                "Independent Power Producer (IPP)", "bi-bank"),
    ("mining",             "Mining Solar Plant",               "bi-gem"),
    ("agricultural",       "Agricultural Solar (Agri-PV)",     "bi-flower1"),
    ("floating",           "Floating Solar (Floatovoltaic)",   "bi-water"),
    ("hybrid",             "Hybrid Solar Plant (PV + BESS)",   "bi-battery-charging"),
    ("bess",               "Battery Energy Storage Plant",     "bi-battery-full"),
    ("other",              "Other",                            "bi-three-dots"),
]
PROJECT_TYPE_CODES: set[str] = {c for c, _, _ in PROJECT_TYPES}

# Spec Step 1 - project_status field.
PROJECT_STATUSES: list[tuple[str, str]] = [
    ("concept",         "Concept"),
    ("prefeasibility",  "Pre-feasibility"),
    ("feasibility",     "Feasibility"),
    ("bankable_design", "Bankable Design"),
    ("financial_close", "Financial Close"),
    ("construction",   "Construction"),
    ("commissioning",  "Commissioning"),
    ("operating",      "Operating"),
]
PROJECT_STATUS_CODES: set[str] = {c for c, _ in PROJECT_STATUSES}

# Spec Step 1 - design_standard field.
DESIGN_STANDARDS: list[tuple[str, str]] = [
    ("IEC",         "IEC (International)"),
    ("IEEE",        "IEEE (US)"),
    ("EN",          "EN / CENELEC (EU)"),
    ("BS",          "BS (UK / Commonwealth)"),
    ("NEC",         "NEC (US National Electrical Code)"),
    ("SANS",        "SANS (South Africa)"),
    ("GS1000",      "Ghana Standards (GS)"),
    ("NIS",         "NIS (Nigeria)"),
    ("KEBS",        "KEBS (Kenya)"),
    ("HYBRID_IEC_LOCAL", "IEC + Local National Code"),
]
DESIGN_STANDARD_CODES: set[str] = {c for c, _ in DESIGN_STANDARDS}

# Spec Step 1 - currency field. Match SolarPro's ISO discipline.
CURRENCIES: list[tuple[str, str]] = [
    ("GHS", "GHS - Ghanaian Cedi"),
    ("NGN", "NGN - Nigerian Naira"),
    ("KES", "KES - Kenyan Shilling"),
    ("ZAR", "ZAR - South African Rand"),
    ("XOF", "XOF - West African CFA"),
    ("USD", "USD - US Dollar"),
    ("EUR", "EUR - Euro"),
    ("GBP", "GBP - Pound Sterling"),
]
CURRENCY_CODES: set[str] = {c for c, _ in CURRENCIES}

# Spec Step 1 - tax_regime field.
TAX_REGIMES: list[tuple[str, str]] = [
    ("standard",     "Standard corporate tax"),
    ("epa_exempt",   "Renewable Energy Act - tax exemption"),
    ("free_zone",    "Free Zone / SEZ"),
    ("ppa_pass",     "PPA pass-through"),
    ("bot",          "Build-Operate-Transfer concession"),
    ("public",       "Government / public sector"),
    ("negotiated",   "Negotiated / bilateral"),
]
TAX_REGIME_CODES: set[str] = {c for c, _ in TAX_REGIMES}


# ---------------------------------------------------------------------------
# Step 3 - Site Configuration dropdowns
# ---------------------------------------------------------------------------

SITE_TERRAINS: list[tuple[str, str]] = [
    ("flat",       "Flat"),
    ("rolling",    "Rolling / gently undulating"),
    ("sloped",     "Sloped"),
    ("hilly",      "Hilly / broken"),
    ("mountainous","Mountainous"),
    ("mixed",      "Mixed"),
]
SITE_SLOPES: list[tuple[str, str]] = [
    ("lt_3",  "< 3 % (near-flat)"),
    ("3_5",   "3-5 %"),
    ("5_10",  "5-10 %"),
    ("10_20", "10-20 %"),
    ("gt_20", "> 20 %"),
]
SITE_SOILS: list[tuple[str, str]] = [
    ("sandy",       "Sandy"),
    ("clay",        "Clay"),
    ("loam",        "Loam"),
    ("rocky",       "Rocky / laterite"),
    ("marshy",      "Marshy / soft"),
    ("mixed",       "Mixed"),
    ("unknown",     "Unknown / needs geotech"),
]
SITE_FLOOD_RISKS: list[tuple[str, str]] = [
    ("none",     "None"),
    ("low",      "Low (1-in-100 year)"),
    ("medium",   "Medium (1-in-25 year)"),
    ("high",     "High (annual)"),
    ("unknown",  "Unknown"),
]
SITE_WIND_ZONES: list[tuple[str, str]] = [
    ("z1_low",     "Zone 1 - Low wind (< 30 m/s basic wind)"),
    ("z2_medium",  "Zone 2 - Medium (30-45 m/s)"),
    ("z3_high",    "Zone 3 - High (45-60 m/s)"),
    ("cyclone",    "Cyclone / hurricane-prone"),
    ("unknown",    "Unknown"),
]
SITE_SEISMIC_ZONES: list[tuple[str, str]] = [
    ("zone_0", "Zone 0 - negligible"),
    ("zone_1", "Zone 1 - low"),
    ("zone_2", "Zone 2 - moderate"),
    ("zone_3", "Zone 3 - severe"),
    ("zone_4", "Zone 4 - very severe"),
    ("unknown","Unknown"),
]
SITE_ACCESS: list[tuple[str, str]] = [
    ("paved",       "Paved public road"),
    ("gravel",      "Gravel access road"),
    ("dirt_ok",     "Dirt track - passable dry season"),
    ("dirt_seasonal","Dirt track - seasonal only"),
    ("none",        "No access road - construction required"),
]
SITE_WATER: list[tuple[str, str]] = [
    ("piped",   "Piped mains supply"),
    ("borehole","On-site borehole"),
    ("tanker",  "Tanker delivery"),
    ("river",   "Nearby river / stream"),
    ("none",    "None - civil supply required"),
]


# ---------------------------------------------------------------------------
# Step 4 - Facility Configuration (17 buildings + external works)
# ---------------------------------------------------------------------------

# Building type list. Each entry: (code, label, icon, is_recommended_default)
BUILDING_TYPES: list[tuple[str, str, str, bool]] = [
    ("control_room",     "Control Room Building",         "bi-cpu",              True),
    ("om_building",      "Operations & Maintenance",      "bi-tools",            True),
    ("security_gate",    "Security Gatehouse",            "bi-shield-lock",      True),
    ("warehouse",        "Warehouse",                     "bi-boxes",            False),
    ("workshop",         "Workshop",                      "bi-wrench-adjustable",False),
    ("admin",            "Administration Building",       "bi-building",         False),
    ("training",         "Training Room",                 "bi-mortarboard",      False),
    ("spare_parts",      "Spare Parts Store",             "bi-archive",          False),
    ("chemical",         "Chemical / Consumables Store",  "bi-droplet",          False),
    ("battery_room",     "Battery Building",              "bi-battery-full",     False),
    ("inverter_room",    "Inverter Building",             "bi-plug",             False),
    ("transformer_bldg", "Transformer Building",          "bi-lightning",        False),
    ("switchgear_bldg",  "Switchgear Building",           "bi-diagram-2",        False),
    ("scada_bldg",       "SCADA Building",                "bi-hdd-network",      False),
    ("comms_bldg",       "Communication Building",        "bi-broadcast",        False),
    ("welfare",          "Staff Welfare Building",        "bi-cup-hot",          False),
    ("washroom",         "Washroom",                      "bi-water",            False),
    ("parking",          "Parking",                       "bi-car-front",        False),
]
BUILDING_CODES: set[str] = {c for c, _, _, _ in BUILDING_TYPES}

# Per-building item lists (spec Step 4 sub-configurations).  These become
# the auto-generated BOQ section rows when the building is enabled.
BUILDING_SUB_ITEMS: dict[str, list[str]] = {
    "control_room": [
        "SCADA workstation", "Monitoring screens", "Operator consoles",
        "Video wall", "Server room rack", "Network cabinet", "Patch panels",
        "UPS system", "Battery backup", "HVAC power", "Emergency lighting",
        "Fire alarm", "IP CCTV", "Access control", "Public address",
        "VoIP telephony", "Small power outlets", "Data outlets",
        "Earthing & bonding", "Lightning protection",
    ],
    "om_building": [
        "Maintenance office", "Technician office", "Workshop",
        "Testing bench area", "Repair bench", "Tool store",
        "Consumables store", "Spare parts store", "Battery maintenance area",
        "Electrical maintenance area", "Cable store",
        "Plant documentation room", "ICT room", "Lighting",
        "Socket outlets", "Fire alarm", "CCTV", "VoIP",
        "LAN", "WiFi", "UPS", "Earthing", "External lighting",
    ],
    "security_gate": [
        "Gatehouse lighting", "Socket outlets", "CCTV monitor",
        "Access control panel", "Boom barrier power", "Data outlet",
        "Intercom / VoIP", "External security lighting", "UPS supply",
    ],
    "battery_room": [
        "Battery racks", "Battery monitoring", "Battery DC cabling",
        "Protection panels", "Fire detection", "Temperature monitoring",
        "Gas detection", "Ventilation / cooling power", "HVAC",
        "UPS", "Emergency lighting", "Safety signage", "Access control",
        "Earthing & bonding",
    ],
    "switchgear_bldg": [
        "MV switchgear", "LV switchgear", "Protection panels",
        "Metering panels", "Control panels", "Cable basement", "Earthing",
        "Lighting", "HVAC", "Fire alarm", "Access control",
    ],
    "transformer_bldg": [
        "Power transformers", "RMU (Ring Main Unit)", "MV switchgear",
        "Lightning protection", "Oil bund / containment", "Earthing grid",
        "Cable trenches", "Yard lighting", "Security fence",
        "Danger signs",
    ],
    "scada_bldg": [
        "SCADA servers", "Historian / data logger", "EMS", "PPC controller",
        "Network switches", "Industrial firewall", "Fibre patch panels",
        "GPS time sync", "NTP server", "UPS", "Server rack HVAC",
        "Fire alarm", "Access control",
    ],
    "comms_bldg": [
        "Fibre distribution frame", "Radio / microwave equipment",
        "Antenna cabling", "Grounding kit", "UPS", "HVAC",
        "Fire detection", "Access control",
    ],
    "warehouse":   ["Lighting", "Small power", "Fire detection", "CCTV",
                    "Earthing", "Loading bay power", "Ventilation"],
    "workshop":    ["Workbench power outlets", "Lighting", "Small power",
                    "Fire alarm", "CCTV", "Compressed-air supply",
                    "Welding supply", "Data outlets"],
    "admin":       ["Lighting", "Small power", "Data outlets", "VoIP",
                    "Fire alarm", "HVAC", "Access control"],
    "training":    ["Lighting", "Projector power", "Data outlets", "HVAC",
                    "Fire alarm", "Small power"],
    "spare_parts": ["Lighting", "Small power", "Fire detection", "CCTV",
                    "Access control", "Temperature monitoring"],
    "chemical":    ["Lighting", "Small power", "Fire suppression",
                    "Ventilation", "Emergency lighting", "Access control"],
    "inverter_room": ["Inverter AC output panels", "DC input protection",
                    "Ventilation", "Fire alarm", "Temperature monitoring",
                    "Emergency lighting", "Earthing"],
    "welfare":     ["Lighting", "Small power", "Water heaters",
                    "Fire alarm", "HVAC"],
    "washroom":    ["Lighting", "Small power", "Water heaters",
                    "Ventilation"],
    "parking":     ["Perimeter lighting", "EV charging provision",
                    "CCTV coverage", "Barrier control"],
}

# Spec External Works (17 items).
EXTERNAL_WORKS: list[tuple[str, str, str, bool]] = [
    ("pv_field",        "PV module field",         "bi-grid-3x3",           True),
    ("mounting",        "Mounting structures",     "bi-columns-gap",        True),
    ("internal_roads",  "Internal roads",          "bi-signpost-2",         True),
    ("cable_trench",    "Cable trenches",          "bi-arrow-down-square",  True),
    ("ducts",           "Underground ducts",       "bi-diagram-3",          True),
    ("drainage",        "Drainage",                "bi-cloud-drizzle",      True),
    ("fence",           "Perimeter fence",         "bi-shield",             True),
    ("security_light",  "Security lighting",       "bi-lightbulb",          True),
    ("gate",            "Gate",                    "bi-door-open",          True),
    ("guardhouse",      "Guardhouse",              "bi-house-lock",         False),
    ("water_supply",    "Water supply",            "bi-droplet-fill",       False),
    ("fire_tank",       "Fire water tank",         "bi-water",              False),
    ("weather_station", "Weather station",         "bi-cloud-sun",          True),
    ("mast",            "Communication mast",      "bi-broadcast-pin",      False),
    ("signage",         "Site signage",            "bi-sign-turn-right",    False),
    ("landscaping",     "Landscaping",             "bi-tree",               False),
    ("stormwater",      "Storm water management",  "bi-cloud-rain-heavy",   False),
]
EXTERNAL_WORKS_CODES: set[str] = {c for c, _, _, _ in EXTERNAL_WORKS}


# ---------------------------------------------------------------------------
# Step 5 - Technology Configuration (33 items grouped)
# ---------------------------------------------------------------------------

TECHNOLOGY_GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("Plant Control", [
        ("scada",         "SCADA",                          "bi-cpu"),
        ("ems",           "EMS (Energy Management)",        "bi-graph-up"),
        ("ppc",           "Power Plant Controller",         "bi-sliders"),
        ("digital_twin",  "Digital Twin",                   "bi-diagram-3"),
    ]),
    ("Monitoring & Metering", [
        ("weather",       "Weather Station",                "bi-cloud-sun"),
        ("string_mon",    "String Monitoring",              "bi-bezier"),
        ("energy_meter",  "Energy Metering",                "bi-speedometer2"),
        ("pq_meter",      "Power Quality Monitoring",       "bi-activity"),
        ("bms",           "Battery Management System",      "bi-battery-charging"),
        ("txfr_mon",      "Transformer Monitoring",         "bi-thermometer-half"),
        ("inv_mon",       "Inverter Monitoring",            "bi-plug"),
        ("remote_mon",    "Remote Monitoring",              "bi-cloud-check"),
        ("cloud_mon",     "Cloud Monitoring",               "bi-cloud-arrow-up"),
        ("thermal_cam",   "Thermal Camera Monitoring",      "bi-camera-video"),
    ]),
    ("AI & Analytics", [
        ("ai_fault",      "AI Fault Prediction",            "bi-lightning"),
        ("drone_insp",    "Drone Inspection",               "bi-airplane"),
        ("predictive",    "Predictive Maintenance",         "bi-graph-up-arrow"),
    ]),
    ("Asset & O&M", [
        ("gis",           "GIS Mapping",                    "bi-geo-alt"),
        ("asset_mgmt",    "Asset Management",               "bi-boxes"),
        ("cmms",          "CMMS (Maintenance Mgmt)",        "bi-tools"),
        ("spares",        "Spare Parts Management",         "bi-archive"),
        ("scheduler",     "Maintenance Scheduler",          "bi-calendar-check"),
        ("wo_mgmt",       "Work Order Management",          "bi-clipboard-check"),
    ]),
    ("Network & Security", [
        ("cyber",         "Cyber Security",                 "bi-shield-shaded"),
        ("firewall",      "Industrial Firewall",            "bi-shield-lock"),
        ("ind_eth",       "Industrial Ethernet",            "bi-diagram-2"),
        ("fibre",         "Fibre Optic Network",            "bi-slash-lg"),
        ("ind_wifi",      "Industrial WiFi",                "bi-wifi"),
        ("gps_sync",      "GPS Time Synchronisation",       "bi-broadcast"),
        ("ntp",           "NTP Server",                     "bi-clock-history"),
    ]),
    ("Servers & Storage", [
        ("ind_servers",   "Industrial Servers",             "bi-server"),
        ("storage_srv",   "Storage Servers",                "bi-hdd-stack"),
        ("backup_srv",    "Backup Servers",                 "bi-hdd"),
        ("cloud_backup",  "Cloud Backup",                   "bi-cloud-upload"),
        ("dr",            "Disaster Recovery",              "bi-arrow-counterclockwise"),
    ]),
]
TECHNOLOGY_CODES: set[str] = {
    c for _, items in TECHNOLOGY_GROUPS for c, _, _ in items
}


# ---------------------------------------------------------------------------
# Step 6 - Electrical System Configuration (25 services, spec order)
# ---------------------------------------------------------------------------

ELECTRICAL_SERVICES: list[tuple[str, str, str, bool]] = [
    ("internal_installation", "Internal Electrical Installation", "bi-plug",           True),
    ("power_supply",          "Power Supply",                     "bi-lightning",      True),
    ("hv_distribution",       "HV Distribution",                  "bi-diagram-3",      True),
    ("lv_distribution",       "LV Distribution",                  "bi-diagram-2",      True),
    ("dc_collection",         "DC Collection",                    "bi-arrow-down-circle", True),
    ("ac_collection",         "AC Collection",                    "bi-arrow-up-circle",True),
    ("inverters",             "Inverters",                        "bi-plug-fill",      True),
    ("transformers",          "Transformers",                     "bi-lightning-charge",True),
    ("rmu",                   "Ring Main Unit (RMU)",             "bi-arrow-repeat",   True),
    ("hv_switchgear",         "HV Switchgear",                    "bi-toggles",        True),
    ("lv_switchgear",         "LV Switchgear",                    "bi-toggles2",       True),
    ("earthing",              "Earthing",                         "bi-arrow-down",     True),
    ("lightning_protection",  "Lightning Protection",             "bi-cloud-lightning",True),
    ("external_lighting",     "External Lighting",                "bi-lightbulb",      True),
    ("fire_alarm",            "Fire Alarm",                       "bi-fire",           True),
    ("ip_cctv",               "IP CCTV",                          "bi-camera-video",   True),
    ("access_control",        "Access Control",                   "bi-shield-lock",    True),
    ("voip",                  "VoIP",                             "bi-telephone",      False),
    ("public_address",        "Public Address",                   "bi-megaphone",      False),
    ("tv",                    "TV",                               "bi-tv",             False),
    ("ip_clock",              "IP Clock",                         "bi-clock",          False),
    ("lan",                   "LAN",                              "bi-hdd-network",    True),
    ("wan",                   "WAN",                              "bi-router",         False),
    ("server_infra",          "Server Infrastructure",            "bi-server",         False),
    ("scada",                 "SCADA",                            "bi-cpu",            True),
]
ELECTRICAL_SERVICE_CODES: set[str] = {c for c, _, _, _ in ELECTRICAL_SERVICES}


# ---------------------------------------------------------------------------
# Facility / technology / electrical  ->  existing BOQ service-code mapping.
#
# The Generation Station module REUSES the platform BOQ engine. Step 9 turns
# the wizard selections into the SAME service codes the standard BOQ engine
# uses (web_app._BOQ_SERVICES), so an auto-generated BOQ project loads real
# Section-by-Section / Build-all sections instead of an empty shell.
# Source: SSS_generation_station_design_2026-07-02.md section 4.
# ---------------------------------------------------------------------------

# Canonical non-medical BOQ service codes, in web_app._BOQ_SERVICES order, so
# the generated services_csv is deterministic. Medical services (nurse_call,
# medical_equip) are intentionally excluded from generation-plant scope.
_CI_BOQ_SERVICE_ORDER: list[str] = [
    "internal_electrical", "fire_alarm", "earthing_bonding",
    "lightning_protection", "power_supply_lv", "lan_wlan", "it_server_room",
    "voip", "ip_pa", "ip_cctv", "tv_system", "ip_clock", "bms",
]
_CI_BOQ_SERVICE_SET: set[str] = set(_CI_BOQ_SERVICE_ORDER)

# Every enabled building gets at least this baseline electrical scope.
_CI_FACILITY_DEFAULT_SERVICES: list[str] = [
    "internal_electrical", "power_supply_lv", "fire_alarm", "earthing_bonding",
]

# Building code -> BOQ service codes (SSS section 4 facility mapping).
FACILITY_BOQ_SERVICES: dict[str, list[str]] = {
    "control_room":     ["internal_electrical", "power_supply_lv", "lan_wlan",
                         "it_server_room", "fire_alarm", "ip_cctv", "voip",
                         "ip_pa", "earthing_bonding", "lightning_protection",
                         "bms"],
    "om_building":      ["internal_electrical", "power_supply_lv", "lan_wlan",
                         "fire_alarm", "ip_cctv", "voip", "earthing_bonding",
                         "bms"],
    "security_gate":    ["internal_electrical", "power_supply_lv", "lan_wlan",
                         "ip_cctv", "voip", "fire_alarm", "earthing_bonding"],
    "battery_room":     ["internal_electrical", "power_supply_lv", "fire_alarm",
                         "lan_wlan", "it_server_room", "earthing_bonding",
                         "lightning_protection", "bms"],
    "inverter_room":    ["internal_electrical", "power_supply_lv", "fire_alarm",
                         "lan_wlan", "earthing_bonding", "bms"],
    "switchgear_bldg":  ["internal_electrical", "power_supply_lv", "fire_alarm",
                         "lan_wlan", "ip_cctv", "earthing_bonding",
                         "lightning_protection", "bms"],
    "transformer_bldg": ["power_supply_lv", "earthing_bonding",
                         "lightning_protection", "ip_cctv",
                         "internal_electrical"],
    "scada_bldg":       ["internal_electrical", "power_supply_lv", "lan_wlan",
                         "it_server_room", "fire_alarm", "ip_cctv", "voip",
                         "earthing_bonding", "lightning_protection", "bms"],
    "comms_bldg":       ["internal_electrical", "power_supply_lv", "lan_wlan",
                         "it_server_room", "fire_alarm", "earthing_bonding",
                         "lightning_protection"],
    "spare_parts":      ["internal_electrical", "fire_alarm", "ip_cctv",
                         "lan_wlan", "earthing_bonding"],
    "workshop":         ["internal_electrical", "power_supply_lv", "lan_wlan",
                         "fire_alarm", "ip_cctv", "earthing_bonding"],
    "welfare":          ["internal_electrical", "power_supply_lv", "fire_alarm",
                         "earthing_bonding"],
    "washroom":         ["internal_electrical", "power_supply_lv",
                         "earthing_bonding"],
}

# Technology code -> BOQ service codes (SSS section 4 technology mapping).
TECHNOLOGY_BOQ_SERVICES: dict[str, list[str]] = {
    "scada":        ["lan_wlan", "it_server_room", "bms", "power_supply_lv"],
    "ems":          ["it_server_room", "lan_wlan", "bms"],
    "ppc":          ["it_server_room", "lan_wlan", "bms"],
    "weather":      ["lan_wlan", "power_supply_lv", "earthing_bonding",
                     "lightning_protection"],
    "string_mon":   ["lan_wlan", "power_supply_lv", "bms"],
    "energy_meter": ["power_supply_lv", "lan_wlan"],
    "pq_meter":     ["power_supply_lv", "lan_wlan"],
    "bms":          ["bms", "lan_wlan", "power_supply_lv", "fire_alarm"],
    "txfr_mon":     ["bms", "lan_wlan", "power_supply_lv"],
    "inv_mon":      ["bms", "lan_wlan"],
    "remote_mon":   ["lan_wlan", "it_server_room"],
    "cloud_mon":    ["lan_wlan", "it_server_room"],
    "thermal_cam":  ["ip_cctv", "lan_wlan", "power_supply_lv"],
    "ai_fault":     ["it_server_room", "lan_wlan", "bms"],
    "predictive":   ["bms", "it_server_room", "lan_wlan"],
    "gis":          ["it_server_room", "lan_wlan"],
    "asset_mgmt":   ["it_server_room", "lan_wlan"],
    "cmms":         ["it_server_room", "lan_wlan"],
    "scheduler":    ["it_server_room", "lan_wlan"],
    "wo_mgmt":      ["it_server_room", "lan_wlan"],
    "cyber":        ["lan_wlan", "it_server_room"],
    "firewall":     ["lan_wlan", "it_server_room"],
    "ind_eth":      ["lan_wlan"],
    "fibre":        ["lan_wlan"],
    "ind_wifi":     ["lan_wlan"],
    "gps_sync":     ["lan_wlan", "it_server_room"],
    "ntp":          ["it_server_room", "lan_wlan"],
    "ind_servers":  ["it_server_room"],
    "storage_srv":  ["it_server_room"],
    "backup_srv":   ["it_server_room"],
    "cloud_backup": ["it_server_room", "lan_wlan"],
    "dr":           ["it_server_room", "lan_wlan"],
    "digital_twin": ["it_server_room", "lan_wlan", "bms"],
    # drone_insp, spares -> no default BOQ service (procurement/marketplace).
}

# Module electrical-service code -> BOQ service code(s) (SSS section 5 Step 6).
ELECTRICAL_TO_BOQ_SERVICE: dict[str, list[str]] = {
    "internal_installation": ["internal_electrical"],
    "power_supply":          ["power_supply_lv"],
    "hv_distribution":       ["power_supply_lv"],
    "lv_distribution":       ["power_supply_lv"],
    "dc_collection":         ["power_supply_lv"],
    "ac_collection":         ["power_supply_lv"],
    "inverters":             ["power_supply_lv"],
    "transformers":          ["power_supply_lv"],
    "rmu":                   ["power_supply_lv"],
    "hv_switchgear":         ["power_supply_lv"],
    "lv_switchgear":         ["power_supply_lv"],
    "earthing":              ["earthing_bonding"],
    "lightning_protection":  ["lightning_protection"],
    "external_lighting":     ["power_supply_lv"],
    "fire_alarm":            ["fire_alarm"],
    "ip_cctv":               ["ip_cctv"],
    "access_control":        ["ip_cctv"],
    "voip":                  ["voip"],
    "public_address":        ["ip_pa"],
    "tv":                    ["tv_system"],
    "ip_clock":              ["ip_clock"],
    "lan":                   ["lan_wlan"],
    "wan":                   ["lan_wlan"],
    "server_infra":          ["it_server_room"],
    "scada":                 ["bms"],
}

# External works -> shared site-wide BOQ scope (added once if any selected).
EXTERNAL_WORKS_BOQ_SERVICES: list[str] = [
    "power_supply_lv", "earthing_bonding", "lightning_protection",
    "ip_cctv", "lan_wlan", "internal_electrical",
]


def _ci_facility_services(building_code: str) -> list[str]:
    """BOQ service codes for one facility/building; defaults to a baseline
    electrical scope for buildings without an explicit mapping."""
    return FACILITY_BOQ_SERVICES.get(
        building_code, _CI_FACILITY_DEFAULT_SERVICES,
    )


def _ci_order_services(codes) -> list[str]:
    """De-duplicate + restrict to valid BOQ codes + return in canonical
    _CI_BOQ_SERVICE_ORDER order for a stable services_csv."""
    have = {c for c in codes if c in _CI_BOQ_SERVICE_SET}
    return [c for c in _CI_BOQ_SERVICE_ORDER if c in have]


def _ci_derive_boq_services(fac_cfg: dict, tech_cfg: dict,
                            elec_cfg: dict) -> list[str]:
    """Union of BOQ service codes implied by facility buildings, external
    works, technology and electrical selections - ordered + valid."""
    codes: list[str] = []
    for b in (fac_cfg.get("buildings") or []):
        codes.extend(_ci_facility_services(b))
    if fac_cfg.get("external_works"):
        codes.extend(EXTERNAL_WORKS_BOQ_SERVICES)
    for t in (tech_cfg.get("selected") or []):
        codes.extend(TECHNOLOGY_BOQ_SERVICES.get(t, []))
    for e in (elec_cfg.get("selected") or []):
        codes.extend(ELECTRICAL_TO_BOQ_SERVICE.get(e, []))
    return _ci_order_services(codes)


# ---------------------------------------------------------------------------
# Step 7 - PV Design dropdowns
# ---------------------------------------------------------------------------

PV_MODULE_TECHS: list[tuple[str, str, float]] = [
    # (code, label, default_wp)
    ("mono_perc",   "Monocrystalline PERC",       550.0),
    ("mono_topcon", "Monocrystalline TOPCon",     600.0),
    ("mono_hjt",    "Monocrystalline HJT",        625.0),
    ("bifacial",    "Bifacial (mono)",            580.0),
    ("thin_film",   "Thin-film (CdTe)",           470.0),
    ("cigs",        "CIGS",                       360.0),
]
PV_MOUNTING_TYPES: list[tuple[str, str]] = [
    ("fixed_tilt",         "Fixed-tilt racking"),
    ("single_axis",        "Single-axis tracker (HSAT)"),
    ("dual_axis",          "Dual-axis tracker"),
    ("east_west",          "East-West flat mounting"),
    ("rooftop_ballasted",  "Rooftop ballasted (flat roof)"),
    ("rooftop_pitched",    "Rooftop pitched"),
]
PV_INVERTER_TYPES: list[tuple[str, str]] = [
    ("string",   "String inverters (100-250 kW)"),
    ("central",  "Central inverters (1-5 MW blocks)"),
    ("micro",    "Microinverters (rooftop only)"),
]
PV_BATTERY_CHEMISTRIES: list[tuple[str, str]] = [
    ("none",      "No battery / grid-tied only"),
    ("lifepo4",   "LiFePO4 (LFP)"),
    ("nmc",       "NMC"),
    ("flow",      "Vanadium flow"),
    ("lead_acid", "Lead-acid (VRLA / OPzS)"),
]


# ---------------------------------------------------------------------------
# Step 8 - Financial dropdowns + CAPEX/OPEX line items
# ---------------------------------------------------------------------------

# Default CAPEX composition in USD/kWp for a Ghana / West-Africa utility PV
# project (spec Step 8 line items). These are editable in the form.
DEFAULT_CAPEX_USD_PER_KWP: dict[str, float] = {
    "modules":          360.0,   # PV modules
    "inverters":         75.0,
    "structures":       150.0,   # racking / trackers
    "civil":            110.0,   # roads, foundations, drainage
    "electrical":       190.0,   # DC/AC cabling, LV/MV panels, transformer
    "grid_connection":   80.0,   # substation extension, HV line, protection
    "development":       35.0,   # ESIA, permits, land title
    "professional":      45.0,   # EPC margin, engineering, PM
    "contingency":       50.0,   # 5-6 % of hard cost
    "land":              15.0,   # capitalised land purchase
    "ict_scada":         25.0,   # SCADA + monitoring + comms
    "security":          10.0,   # fencing, CCTV, guardhouse capex
    "bess":               0.0,   # editable - 0 if grid-tied only
    "other":              0.0,
}

# Default OPEX (USD/kWp/year).
DEFAULT_OPEX_USD_PER_KWP_YR: dict[str, float] = {
    "om_labour":         8.0,
    "cleaning":          3.0,
    "spare_parts":       2.5,
    "insurance":         3.5,
    "land_lease":        1.5,
    "grid_charges":      2.0,
    "admin_overhead":    2.0,
    "security":          1.5,
    "other":             0.0,
}

REVENUE_MODELS: list[tuple[str, str]] = [
    ("ppa",             "PPA (fixed tariff)"),
    ("merchant",        "Merchant (spot market)"),
    ("net_metering",    "Net metering / self-consumption"),
    ("wheeling",        "Wheeling / bilateral"),
    ("captive",         "Captive (industrial off-take)"),
]


# ---------------------------------------------------------------------------
# Slice 6 - CRM + Sales Pipeline + Reports + Development/Regulatory
# ---------------------------------------------------------------------------

# Spec Step 12 - 13-stage utility-scale pipeline. This is a SUPERSET of
# SolarPro's marketplace pipeline (which stops at "won / installation /
# after_sales") because utility-scale projects also carry a construction
# and commissioning tail.
PIPELINE_STAGES: list[tuple[str, str, str]] = [
    # (code, label, icon)
    ("lead",            "Lead",             "bi-search"),
    ("opportunity",     "Opportunity",      "bi-lightbulb"),
    ("concept_design",  "Concept Design",   "bi-pencil-square"),
    ("feasibility",     "Feasibility",      "bi-clipboard-check"),
    ("financial_model", "Financial Model",  "bi-cash-coin"),
    ("proposal",        "Proposal",         "bi-file-earmark-text"),
    ("investor_review", "Investor Review",  "bi-people"),
    ("bank_review",     "Bank Review",      "bi-bank"),
    ("negotiation",     "Negotiation",      "bi-chat-square-text"),
    ("award",           "Award",            "bi-award"),
    ("construction",    "Construction",     "bi-cone-striped"),
    ("commissioning",   "Commissioning",    "bi-toggle-on"),
    ("completed",       "Completed",        "bi-check2-circle"),
]
PIPELINE_STAGE_CODES: list[str] = [c for c, _, _ in PIPELINE_STAGES]
PIPELINE_STAGE_LABEL: dict[str, str] = {c: L for c, L, _ in PIPELINE_STAGES}


# Spec Step 13 - 13 report types. Slice 6 fully implements 4 as PDFs
# (marked full=True); the rest are stubs that render a "Coming soon"
# page inline and can be built out in a later slice.
REPORT_TYPES: list[tuple[str, str, str, bool]] = [
    # (key, label, icon, full=True for implemented PDFs)
    ("executive",       "Executive Summary",     "bi-clipboard-data",  True),
    ("technical",       "Technical Report",      "bi-cpu",             True),
    ("financial",       "Financial Report",      "bi-cash-coin",       True),
    ("bankability",     "Bankability Report",    "bi-bank",            True),
    ("investment_memo", "Investment Memorandum", "bi-file-earmark-text", True),
    ("risk",            "Risk Assessment",       "bi-shield-exclamation", False),
    ("boq",             "BOQ",                   "bi-list-check",      False),
    ("bom",             "BOM",                   "bi-boxes",           False),
    ("rfq",             "Marketplace RFQ",       "bi-cart",            False),
    ("construction_est","Construction Estimate", "bi-hammer",          False),
    ("maintenance",     "Maintenance Strategy",  "bi-tools",           False),
    ("monitoring",      "Monitoring Strategy",   "bi-eye",             False),
    ("ops_manual",      "Operations Manual",     "bi-journal",         False),
]
REPORT_KEYS: set[str] = {k for k, _, _, _ in REPORT_TYPES}
FULL_REPORT_KEYS: set[str] = {k for k, _, _, full in REPORT_TYPES if full}


# Development & Regulatory sub-step (spec's recommended pre-PV-design bolt-on).
# Every entry stores a status + narrative in regulatory_config JSON.
REGULATORY_ITEMS: list[tuple[str, str, str]] = [
    # (code, label, hint)
    ("land_tenure",       "Land ownership / lease",
     "Owned / long-lease / concession / negotiating"),
    ("esia",              "ESIA (Environmental & Social)",
     "Screening -> Scoping -> Full ESIA -> approval"),
    ("grid_interconnect", "Grid interconnection",
     "Feasibility study, connection agreement, wheeling"),
    ("utility_approval",  "Utility approval",
     "Off-taker approval, dispatch instructions"),
    ("energy_commission", "Energy Commission licensing",
     "Generation licence, transmission licence"),
    ("epa_approval",      "EPA approval",
     "Air / noise / waste permits"),
    ("building_permits",  "Building permits",
     "District Assembly building permits"),
    ("financial_close",   "Financial close milestones",
     "Term sheet, credit approval, drawdown"),
    ("construction_sched","Construction schedule",
     "Baseline schedule + critical path"),
    ("cod",               "Commercial Operation Date (COD)",
     "Target COD + commissioning tests"),
]
REGULATORY_ITEM_CODES: set[str] = {c for c, _, _ in REGULATORY_ITEMS}

REGULATORY_STATUSES: list[tuple[str, str, str]] = [
    ("not_started",  "Not started",         "secondary"),
    ("in_progress",  "In progress",         "warning"),
    ("applied",      "Applied / submitted", "warning"),
    ("pending",      "Pending decision",    "info"),
    ("approved",     "Approved / complete", "success"),
    ("denied",       "Denied / blocked",    "danger"),
    ("na",           "Not applicable",      "secondary"),
]
REGULATORY_STATUS_CODES: set[str] = {c for c, _, _ in REGULATORY_STATUSES}


# ---------------------------------------------------------------------------
# Country-specific regulatory frameworks - drives the Development &
# Regulatory step's practice tips, authorities, tenure options, and
# permits sequence. Extend by adding a country key; unlisted countries
# fall back to the "generic" framework.
#
# Data compiled from official sources (Energy Commission Ghana, NERC
# Nigeria, EPRA Kenya, DMRE South Africa, MEMC Cote d'Ivoire, MEPA
# Senegal); double-check the current statutes when a project moves to
# concept-design stage.
# ---------------------------------------------------------------------------

COUNTRY_REGULATORY_FRAMEWORKS: dict[str, dict[str, Any]] = {
    "Ghana": {
        "flag": "🇬🇭",
        "regulator": {"name": "Energy Commission of Ghana", "abbr": "EC",
                      "url": "https://www.energycom.gov.gh"},
        "esia_authority": {"name": "Environmental Protection Agency",
                           "abbr": "EPA-GH",
                           "url": "https://epa.gov.gh"},
        "tariff_regulator": {"name": "Public Utilities Regulatory Commission",
                             "abbr": "PURC"},
        "grid_operator":   ["GRIDCo (transmission)", "ECG / NEDCo (distribution)"],
        "utility_offtakers": ["ECG", "NEDCo", "VRA", "Bulk consumers via wheeling"],
        "land_tenures": [
            {"code":"private_freehold",  "label":"Private freehold title",
             "notes":"Registered at Lands Commission; verify indenture chain."},
            {"code":"stool_land",        "label":"Stool land (customary)",
             "notes":"Traditional Authority + Regional House of Chiefs consent required; site inspection with chief."},
            {"code":"skin_land",         "label":"Skin land (Northern)",
             "notes":"Analogous to stool land in Upper East / Upper West / Northern."},
            {"code":"family_land",       "label":"Family land",
             "notes":"All principal elders must sign; head-of-family alone is not sufficient."},
            {"code":"government_lease",  "label":"Government / state leasehold",
             "notes":"Lands Commission grant; typical 50-yr with renewal option."},
            {"code":"leasehold_from_stool","label":"Long-lease from stool",
             "notes":"50-99 yr lease from Traditional Council; register at Lands Commission."},
        ],
        "land_practices": [
            "Before signing anything: obtain a Lands Commission search on the exact parcel; verify a site plan attached to a valid indenture.",
            "For stool / family land: convene a formal meeting with the Chief, Queen Mother and principal elders. Record consent in writing and register at the Regional House of Chiefs.",
            "Do NOT pay 'drink money' informally - use a Land Purchase Agreement with escrow through a lawyer.",
            "Instruct a licensed surveyor to peg boundaries; discrepancies with the indenture are a red flag.",
            "Publish a public notice at the District Assembly for 21 days to flush out competing claims (Land Act 1036, 2020, s. 96).",
            "For 25+ MW ground-mount, expect 6-12 months from LOI to registered title. Budget for stakeholder engagement.",
            "Confirm the site is NOT within a Forest Reserve, Ramsar Site, or Archaeological Site (Wildlife Division / Museums Board consultation).",
        ],
        "regulations": [
            "Energy Commission Act 541 (1997)",
            "Renewable Energy Act 832 (2011) as amended by Act 1045 (2020)",
            "Electricity Regulations LI 1937 (2008)",
            "Environmental Assessment Regulations LI 1652 (1999)",
            "Land Act 1036 (2020)",
            "Local Governance Act 936 (2016) - District Assembly permits",
            "Feed-in-tariff Guidelines (PURC)",
            "Renewable Energy Sub-Code (2015) - grid connection technical rules",
            "Distribution Code (GRIDCo)",
        ],
        "permits_sequence": [
            "Site suitability + LOI from Traditional Authority",
            "Land registration at Lands Commission",
            "ESIA registration + Scoping Report -> EPA",
            "Provisional Wholesale Electricity Supply Licence -> Energy Commission",
            "Grid connection application -> GRIDCo (transmission) or ECG/NEDCo (distribution)",
            "Full ESIA + EPA Permit",
            "PPA negotiation -> ECG / NEDCo / bulk off-taker",
            "PURC tariff approval",
            "Construction Permit -> District Assembly",
            "Wholesale Electricity Supply Licence (final) -> Energy Commission",
            "Interconnection Agreement -> GRIDCo",
            "Commissioning + Operations Licence",
        ],
        "typical_timeline_months": {
            "concept_to_esia": 6,
            "esia_to_permit":  9,
            "permit_to_ppa":  12,
            "ppa_to_fc":       9,
            "fc_to_cod":      18,
        },
        "notes": "Ghana's 10% RE target under the Renewable Energy Master Plan; incentives incl. reduced import duty on modules. Watch for Cedi devaluation clauses in PPA.",
    },
    "Nigeria": {
        "flag": "🇳🇬",
        "regulator": {"name": "Nigerian Electricity Regulatory Commission",
                      "abbr": "NERC", "url": "https://nerc.gov.ng"},
        "esia_authority": {"name": "Federal Ministry of Environment",
                           "abbr": "FMEnv"},
        "tariff_regulator": {"name": "NERC", "abbr": "NERC"},
        "grid_operator":   ["TCN (transmission)", "11 DisCos (distribution)"],
        "utility_offtakers": ["NBET (bulk trader)", "11 DisCos", "Eligible customers"],
        "land_tenures": [
            {"code":"c_of_o",       "label":"Certificate of Occupancy (C of O)",
             "notes":"Governor-issued under Land Use Act 1978; 99-yr statutory right."},
            {"code":"customary",    "label":"Customary right of occupancy",
             "notes":"Community land; requires Governor's consent for alienation."},
            {"code":"state_lease",  "label":"State Government lease",
             "notes":"Direct grant from State; watch tenure length + revocation clauses."},
            {"code":"federal_grant","label":"Federal Government grant",
             "notes":"Only for federal projects; process via Federal Ministry of Works."},
        ],
        "land_practices": [
            "Land Use Act 1978 vests all urban land in the Governor - a private 'sale' without Governor's consent is voidable.",
            "Apply for Governor's Consent to Assignment before construction; expect 3-6 months.",
            "Perpetual due diligence: search at the State Land Registry + the FCT (if in Abuja).",
            "Verify with the community and traditional ruler for customary land; document with a signed Deed of Grant.",
            "Environmental notice at the Local Government Area is a requirement for large projects (EIA Act 1992).",
            "Land acquisition compensation follows the Land Use Act formulas - budget for host-community payments.",
        ],
        "regulations": [
            "Electric Power Sector Reform Act 2005",
            "Electricity Act 2023 (new law - enables sub-national electricity markets)",
            "Land Use Act 1978",
            "EIA Act 1992 (Cap E12 LFN 2004)",
            "NERC Regulation on Embedded Generation 2012",
            "NERC Regulation on Independent Electricity Distribution Networks 2012",
            "NERC Feed-in Tariff Regulations (REFIT) 2015",
            "NBET's PPA templates (standard)",
        ],
        "permits_sequence": [
            "MOU with State Government + host community",
            "Land C of O / customary right documentation",
            "EIA registration + Scoping -> FMEnv",
            "Generation Licence application -> NERC",
            "Grid connection study -> TCN or relevant DisCo",
            "Full EIA + Certificate",
            "PPA with NBET or eligible customer",
            "Generation Licence granted -> NERC",
            "Construction permit + Building approval (state)",
            "Interconnection Agreement -> TCN / DisCo",
            "Commissioning + Operations Licence",
        ],
        "typical_timeline_months": {
            "concept_to_esia":  6,
            "esia_to_permit":  12,
            "permit_to_ppa":   14,
            "ppa_to_fc":       12,
            "fc_to_cod":       20,
        },
        "notes": "The 2023 Electricity Act enables sub-national electricity markets - state-level projects can be attractive. Naira convertibility risk should be modelled.",
    },
    "Kenya": {
        "flag": "🇰🇪",
        "regulator": {"name": "Energy and Petroleum Regulatory Authority",
                      "abbr": "EPRA", "url": "https://www.epra.go.ke"},
        "esia_authority": {"name": "National Environment Management Authority",
                           "abbr": "NEMA"},
        "tariff_regulator": {"name": "EPRA", "abbr": "EPRA"},
        "grid_operator":   ["KETRACO (transmission)", "KPLC (distribution)"],
        "utility_offtakers": ["KPLC (Kenya Power)", "Wheeling to bulk consumers"],
        "land_tenures": [
            {"code":"freehold",     "label":"Freehold title",
             "notes":"Absolute ownership; register at Ministry of Lands."},
            {"code":"leasehold_99", "label":"Leasehold (99-yr)",
             "notes":"Standard for non-Kenyan investors; capped at 99 yr under 2010 Constitution."},
            {"code":"community",    "label":"Community land",
             "notes":"Community Land Act 2016 - registered community assent required."},
            {"code":"public_lease", "label":"Public land lease",
             "notes":"National Land Commission grant."},
        ],
        "land_practices": [
            "Non-Kenyans are restricted to 99-yr leasehold - structure land holdings via a Kenyan-registered SPV.",
            "Community Land Act 2016: for community land, get a resolution from the registered Community Land Committee + Council of Elders.",
            "Land Control Board consent required for any transaction on agricultural land (Land Control Act).",
            "Title verification at the Registry of Titles is mandatory; do NOT rely on the seller's copy.",
            "Confirm the site is not within a wildlife corridor (KWS consultation) or gazetted forest (KFS).",
            "Land Acquisition Act 2011 governs compulsory acquisition compensation.",
        ],
        "regulations": [
            "Energy Act 2019",
            "Constitution of Kenya 2010 (art. 65 - land tenure)",
            "Land Registration Act 2012",
            "Land Act 2012",
            "Community Land Act 2016",
            "Environmental Management and Coordination Act 1999 (EMCA)",
            "EPRA Renewable Energy FIT Policy 2012 (revised 2021)",
            "Kenya Grid Code",
            "Physical and Land Use Planning Act 2019 - county planning permits",
        ],
        "permits_sequence": [
            "MOU with community / county government",
            "Land title / community assent",
            "ESIA licence application -> NEMA",
            "Generation Licence application -> EPRA",
            "Grid connection study -> KETRACO or KPLC",
            "ESIA licence granted",
            "PPA negotiation with KPLC",
            "Generation Licence granted -> EPRA",
            "County construction permit",
            "Interconnection Agreement",
            "Commissioning + Operations Licence",
        ],
        "typical_timeline_months": {
            "concept_to_esia":  5,
            "esia_to_permit":   8,
            "permit_to_ppa":   14,
            "ppa_to_fc":       10,
            "fc_to_cod":       16,
        },
        "notes": "Kenya's power sector reform includes wheeling for eligible consumers >1 MW. Take-or-pay PPA structures common; watch KPLC counterparty risk.",
    },
    "South Africa": {
        "flag": "🇿🇦",
        "regulator": {"name": "National Energy Regulator of South Africa",
                      "abbr": "NERSA", "url": "https://www.nersa.org.za"},
        "esia_authority": {"name": "Department of Forestry, Fisheries and the Environment",
                           "abbr": "DFFE"},
        "tariff_regulator": {"name": "NERSA", "abbr": "NERSA"},
        "grid_operator":   ["Eskom (national)", "Municipal distributors"],
        "utility_offtakers": ["Eskom", "Municipalities", "Private off-takers (wheeling)"],
        "land_tenures": [
            {"code":"freehold",   "label":"Freehold title",
             "notes":"Deeds Office registration."},
            {"code":"leasehold",  "label":"Leasehold from state/municipality",
             "notes":"State Land Disposal Act; check reversion clauses."},
            {"code":"traditional","label":"Traditional / communal land",
             "notes":"IPILRA 1996 protection; require community consent + Traditional Authority."},
            {"code":"mining_land","label":"Land subject to mining rights",
             "notes":"Coexistence with MPRDA 2002 rights holders; get servitude."},
        ],
        "land_practices": [
            "Communal land: Interim Protection of Informal Land Rights Act (IPILRA) requires informed consent of communal-right holders.",
            "Section 42 (MPRDA) consent needed from prospecting/mining rights holders for coexistence.",
            "Deeds Office search is authoritative; verify title deed + endorsements + servitudes.",
            "For land >10 ha, environmental authorisation is mandatory (NEMA Listing Notice 1).",
            "Public participation process (30 days minimum) via I&AP register.",
            "Municipal zoning (SPLUMA 2013) - rezoning from agricultural to solar-plant use is often the critical path.",
        ],
        "regulations": [
            "Electricity Regulation Act 4 (2006) as amended",
            "National Energy Act 2008",
            "Renewable Energy Independent Power Producer Procurement (REIPPPP) framework",
            "Integrated Resource Plan (IRP) 2019",
            "National Environmental Management Act 107 (1998, NEMA)",
            "SPLUMA (Spatial Planning and Land Use Management Act 2013)",
            "IPILRA (Interim Protection of Informal Land Rights Act 1996)",
            "MPRDA (Mineral and Petroleum Resources Development Act 2002)",
            "Grid Code + Distribution Code (NERSA)",
        ],
        "permits_sequence": [
            "Land option / rights secured",
            "Environmental Impact Assessment - scoping",
            "Grid connection cost estimate letter -> Eskom",
            "Generation licence application -> NERSA (or registration if <100 MW self-gen)",
            "EIA + Environmental Authorisation -> DFFE / Provincial DEA",
            "Water Use Licence Application if applicable -> DWS",
            "PPA (REIPPPP bid or private off-take)",
            "Budget Quote + Cost Estimate Letter -> Eskom",
            "Grid Connection Agreement (final)",
            "Rezoning + Municipal building permits (SPLUMA)",
            "Construction + Commissioning + Operating Licence",
        ],
        "typical_timeline_months": {
            "concept_to_esia":  6,
            "esia_to_permit": 12,
            "permit_to_ppa":  10,
            "ppa_to_fc":      12,
            "fc_to_cod":      20,
        },
        "notes": "Post-2023 NERSA licensing threshold raised to 100 MW - projects under this only need registration. Wheeling is now practical; Eskom curtailment risk should be modelled.",
    },
    "Cote d'Ivoire": {
        "flag": "🇨🇮",
        "regulator": {"name": "Autorite de Regulation du Secteur de l'Electricite",
                      "abbr": "ANARE-CI"},
        "esia_authority": {"name": "Agence Nationale de l'Environnement",
                           "abbr": "ANDE"},
        "tariff_regulator": {"name": "ANARE-CI"},
        "grid_operator":   ["CI-Energies", "CIE (concessionaire)"],
        "utility_offtakers": ["CI-Energies (single-buyer)"],
        "land_tenures": [
            {"code":"freehold_ret","label":"Retention (title de propriete)",
             "notes":"Registered under Loi 98-750; strongest tenure."},
            {"code":"customary",   "label":"Droit coutumier",
             "notes":"Requires Certificat Foncier Rural via village Comite de Gestion Fonciere Rurale."},
            {"code":"state_grant", "label":"Concession from the State",
             "notes":"Grants via decree; typical 25-50 yr for IPP."},
        ],
        "land_practices": [
            "Loi 98-750 formalises customary land into Certificats Fonciers Ruraux; without a CFR, land is legally state-owned.",
            "Village-level Comite de Gestion Fonciere Rurale must certify the CFR - allow 6-9 months.",
            "Consult the sous-prefet + prefet + community; formal public inquiry (enquete de commodo et incommodo) is required.",
            "Domain public: coastal / river / forest reserves are off-limits without special decree.",
            "OHADA business framework governs the SPV structure.",
        ],
        "regulations": [
            "Loi 2014-132 portant Code de l'Electricite",
            "Loi 98-750 relative au Domaine Foncier Rural",
            "Loi 96-766 Code de l'Environnement",
            "Decret 96-894 (etude d'impact environnemental)",
            "Codes OHADA (business law harmonisation)",
        ],
        "permits_sequence": [
            "Protocole d'Accord with CI-Energies",
            "Certificat Foncier Rural or state concession",
            "Etude d'impact environnemental (ANDE)",
            "Convention de Concession",
            "Contrat d'achat d'electricite (CAE)",
            "Autorisation de production -> Ministere du Petrole, de l'Energie et des Energies Renouvelables",
            "Permis de construire + amenagement",
            "Interconnection Agreement -> CI-Energies",
            "Mise en service + Autorisation d'exploitation",
        ],
        "typical_timeline_months": {
            "concept_to_esia":  6,
            "esia_to_permit": 10,
            "permit_to_ppa":  12,
            "ppa_to_fc":      12,
            "fc_to_cod":      20,
        },
        "notes": "Cote d'Ivoire is a stable single-buyer market via CI-Energies. XOF is pegged to Euro so FX risk is contained.",
    },
    "Senegal": {
        "flag": "🇸🇳",
        "regulator": {"name": "Commission de Regulation du Secteur de l'Electricite",
                      "abbr": "CRSE"},
        "esia_authority": {"name": "Direction de l'Environnement et des Etablissements Classes",
                           "abbr": "DEEC"},
        "tariff_regulator": {"name": "CRSE"},
        "grid_operator":   ["Senelec (integrated utility)"],
        "utility_offtakers": ["Senelec"],
        "land_tenures": [
            {"code":"national_domain","label":"National Domain (customary)",
             "notes":"~95% of rural land; must be re-classified to Domain Prive de l'Etat before IPP."},
            {"code":"private_title", "label":"Titre foncier",
             "notes":"Registered private ownership; strongest tenure."},
            {"code":"state_lease",   "label":"Bail emphyteotique",
             "notes":"18-99 yr state lease; typical for IPP."},
        ],
        "land_practices": [
            "The National Domain (Loi 64-46) covers most rural land; conversion to state private domain via decree is required.",
            "Rural Council (Conseil Rural) deliberation formally allocates land within the National Domain.",
            "Prefectorial approval + inter-ministerial commission for large land takings.",
            "Community consultation via ADL / customary chiefs is a political requirement even where not legally mandatory.",
        ],
        "regulations": [
            "Loi 98-29 portant Code de l'Electricite",
            "Loi 64-46 relative au Domaine National",
            "Loi 2001-01 Code de l'Environnement",
            "Loi 2015-24 sur la production independante",
        ],
        "permits_sequence": [
            "Term sheet with Senelec",
            "Land tenure documentation",
            "Notice d'impact environnemental",
            "Convention de concession",
            "Contrat d'Achat d'Electricite (CAE)",
            "Etude d'impact + certificat de conformite -> DEEC",
            "Autorisation d'exploiter -> Ministere du Petrole et des Energies",
            "Permis de construire",
            "Interconnection Agreement",
            "COD",
        ],
        "typical_timeline_months": {
            "concept_to_esia":  6,
            "esia_to_permit":  9,
            "permit_to_ppa":  10,
            "ppa_to_fc":       9,
            "fc_to_cod":      18,
        },
        "notes": "Senegal's SCALING SOLAR programme (WB) has proven a viable IPP path (Kael + Kahone). XOF peg to Euro contains FX risk.",
    },
    "generic": {
        "flag": "🌍",
        "regulator": {"name": "National electricity regulator", "abbr": "NER"},
        "esia_authority": {"name": "National environment authority", "abbr": "NEA"},
        "tariff_regulator": {"name": "National tariff regulator"},
        "grid_operator":   ["National transmission operator",
                            "National / regional distributor(s)"],
        "utility_offtakers": ["National utility", "Bulk / private off-takers"],
        "land_tenures": [
            {"code":"freehold",  "label":"Freehold title", "notes":"Verify at the national land registry."},
            {"code":"leasehold", "label":"Long-lease (25-99 yr)", "notes":"Standard for IPP."},
            {"code":"customary", "label":"Customary / community land", "notes":"Requires community consent + registration."},
            {"code":"state",     "label":"State grant / concession", "notes":"Ministry-issued; check renewal terms."},
        ],
        "land_practices": [
            "Search the national / regional land registry for the exact parcel.",
            "Instruct a licensed surveyor to peg boundaries before signing.",
            "For customary land, obtain written community consent with witnesses.",
            "Confirm the site is not in a gazetted forest / wetland / protected area.",
            "Structure land holdings through a local SPV where foreign ownership is restricted.",
        ],
        "regulations": [
            "National electricity act / code",
            "National environmental impact assessment law",
            "National land law + registration act",
            "Grid code / distribution code",
            "Foreign investment framework",
        ],
        "permits_sequence": [
            "Site suitability + LOI",
            "Land tenure documentation",
            "ESIA / EIA screening",
            "Generation licence application",
            "Grid connection application",
            "ESIA / EIA full report + approval",
            "PPA negotiation",
            "Generation licence granted",
            "Construction permit",
            "Interconnection agreement",
            "Commissioning + operations",
        ],
        "typical_timeline_months": {
            "concept_to_esia":  6,
            "esia_to_permit": 10,
            "permit_to_ppa":  12,
            "ppa_to_fc":      12,
            "fc_to_cod":      18,
        },
        "notes": "Country-specific practice not yet loaded for this jurisdiction. Verify each step with a locally-admitted energy / real estate counsel before commitment.",
    },
}


# ---------------------------------------------------------------------------
# Step 14 - AI Agent specialists.
#
# Each agent is a pure Python function that takes the project dict and
# returns a structured report: {status, score (0-100), findings, recs}.
# The orchestrator dispatches all agents in a fixed order, aggregates
# scores, and can optionally add an LLM-generated narrative through the
# existing api_manager AI chain (Claude -> OpenRouter -> Ollama -> GH
# Models -> rule-based). No Google ADK; reuses SolarPro's plumbing.
# ---------------------------------------------------------------------------

AGENT_DEPARTMENTS: list[tuple[str, str, str, str]] = [
    # (code, label, department, icon)
    ("pv_design",      "PV Design Agent",              "Engineering", "bi-sun"),
    ("electrical",     "Electrical Design Agent",      "Engineering", "bi-plug"),
    ("civil",          "Civil Design Agent",           "Engineering", "bi-bricks"),
    ("structural",     "Structural Agent",             "Engineering", "bi-columns-gap"),
    ("ict",            "ICT Infrastructure Agent",     "Engineering", "bi-hdd-network"),
    ("scada",          "SCADA Agent",                  "Engineering", "bi-cpu"),
    ("grid",           "Grid Connection Agent",        "Engineering", "bi-lightning-charge"),
    ("financial",      "Financial Engineering Agent",  "Finance",     "bi-cash-coin"),
    ("investment",     "Investment Agent",             "Finance",     "bi-bank"),
    ("risk",           "Risk Analysis Agent",          "Finance",     "bi-shield-exclamation"),
    ("marketplace",    "Marketplace Agent",            "Procurement", "bi-shop"),
    ("boq",            "BOQ Agent",                    "Procurement", "bi-list-check"),
    ("report_writer",  "Report Writer Agent",          "Reporting",   "bi-file-earmark-text"),
    ("qa_qc",          "QA/QC Agent",                  "Governance",  "bi-clipboard-check"),
    ("reviewer",       "Project Reviewer Agent",       "Governance",  "bi-check2-circle"),
]
AGENT_CODES: set[str] = {c for c, _, _, _ in AGENT_DEPARTMENTS}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v in (None, "", "None"):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _rating(score: int) -> str:
    if score >= 85: return "A - excellent"
    if score >= 70: return "B - good"
    if score >= 55: return "C - acceptable"
    if score >= 40: return "D - marginal"
    return "F - not ready"


def _agent_pv_design(proj: dict[str, Any]) -> dict[str, Any]:
    pv = _safe_json(proj.get("pv_config"))
    site = _safe_json(proj.get("site_config"))
    sizing = pv.get("sizing") or {}
    kwp = _f(sizing.get("kwp_input") or pv.get("kwp") or proj.get("target_kwp"))
    findings, recs = [], []
    score = 100
    if kwp <= 0:
        findings.append("kWp not set (Step 7 not completed)")
        recs.append("Complete Step 7 with a plant capacity")
        score = 15
    else:
        # DC/AC ratio sanity
        dcac = _f(pv.get("dc_ac_ratio"), 1.20)
        if dcac < 1.05:
            findings.append(f"DC/AC ratio {dcac:.2f} is low - inverters over-sized, CAPEX inefficient")
            recs.append("Target DC/AC 1.15-1.30 for most tropical climates")
            score -= 10
        elif dcac > 1.40:
            findings.append(f"DC/AC ratio {dcac:.2f} is high - meaningful clipping losses expected")
            recs.append("Model clipping loss and validate against inverter curve")
            score -= 10
        # Tilt sanity for Ghana (near equator)
        gps_lat = _f(proj.get("gps_lat"), 6.0)
        tilt = _f(pv.get("tilt_deg"), 10)
        ideal_tilt = abs(gps_lat)
        if abs(tilt - ideal_tilt) > 10 and pv.get("mounting") == "fixed_tilt":
            findings.append(f"Fixed tilt {tilt}deg differs by {abs(tilt-ideal_tilt):.0f}deg from latitude-optimal ({ideal_tilt:.0f}deg)")
            recs.append("Snap tilt closer to latitude unless site-specific reason")
            score -= 5
        # Land area vs capacity (~1.5 ha per MW for utility ground-mount)
        land_ha = _f(site.get("land_area_ha"))
        needed_ha = kwp / 1000.0 * 1.5
        if land_ha > 0 and land_ha < needed_ha:
            findings.append(f"Land {land_ha:.1f} ha may be tight for {kwp/1000:.1f} MW (~{needed_ha:.1f} ha recommended)")
            recs.append("Verify with a bifacial + HSAT layout or increase land area")
            score -= 10
        # Availability
        avail = _f(pv.get("availability_pct"), 98)
        if avail < 96:
            findings.append(f"Availability {avail}% is lower than utility norm (98-99%)")
            score -= 5
        if not findings:
            findings.append("PV design values are all within utility-scale norms")
    return {"status": "ok" if score >= 55 else "warning",
            "score": max(0, min(100, score)),
            "findings": findings, "recs": recs,
            "summary": f"PV design rating: {_rating(max(0, score))}"}


def _agent_electrical(proj: dict[str, Any]) -> dict[str, Any]:
    elec = _safe_json(proj.get("electrical_config"))
    pv = _safe_json(proj.get("pv_config"))
    sizing = pv.get("sizing") or {}
    selected = set(elec.get("selected") or [])
    findings, recs = [], []
    score = 100
    core = {"internal_installation", "hv_distribution", "lv_distribution",
            "inverters", "transformers", "earthing", "lightning_protection"}
    missing = core - selected
    if missing:
        findings.append(f"Missing core electrical scope: {', '.join(sorted(missing))}")
        recs.append("Enable the missing services on Step 6 before proceeding")
        score -= 8 * len(missing)
    ac_kw = _f(sizing.get("inverter_ac_kw"))
    if ac_kw > 5000 and "hv_switchgear" not in selected:
        findings.append(f"Plant AC {ac_kw/1000:.1f} MW requires HV switchgear but none selected")
        score -= 10
    if "hv_distribution" in selected and "rmu" not in selected:
        findings.append("HV distribution enabled without RMU - MV interconnection likely incomplete")
        recs.append("Add RMU on Step 6 or note bypass rationale")
        score -= 5
    if "scada" in selected and "lan" not in selected:
        findings.append("SCADA enabled without LAN backbone")
        recs.append("Enable LAN on Step 6 for SCADA connectivity")
        score -= 3
    if not findings:
        findings.append("Electrical scope is complete for a utility-scale plant")
    return {"status": "ok" if score >= 55 else "warning",
            "score": max(0, min(100, score)),
            "findings": findings, "recs": recs,
            "summary": f"Electrical rating: {_rating(max(0, score))}"}


def _agent_civil(proj: dict[str, Any]) -> dict[str, Any]:
    site = _safe_json(proj.get("site_config"))
    fac = _safe_json(proj.get("facility_config"))
    findings, recs = [], []
    score = 100
    slope = (site.get("slope") or "").strip()
    if slope == "gt_20":
        findings.append("Slope > 20% - major grading + geotech needed")
        recs.append("Add 6-9% civil CAPEX contingency")
        score -= 20
    elif slope == "10_20":
        findings.append("Slope 10-20% - grading + drainage attention needed")
        score -= 8
    flood = site.get("flood_risk")
    if flood == "high":
        findings.append("High flood risk - elevated mounting + drainage compulsory")
        recs.append("Add drainage + PV table height provision")
        score -= 15
    access = site.get("access_road")
    if access in ("dirt_seasonal", "none"):
        findings.append(f"Access road '{access}' - construction access + module delivery risk")
        recs.append("Budget for construction access improvement")
        score -= 10
    soil = site.get("soil")
    if soil == "marshy":
        findings.append("Marshy soil - deep pile foundations mandatory")
        recs.append("Instruct a geotech CPT/SPT campaign")
        score -= 12
    if soil == "unknown":
        findings.append("Soil type unknown - geotech survey required")
        recs.append("Commission a geotech survey before EPC bid")
        score -= 6
    ex_works = fac.get("external_works") or []
    if "drainage" not in ex_works and flood in ("low", "medium", "high"):
        findings.append(f"Flood risk '{flood}' but drainage not enabled in Step 4 external works")
        recs.append("Enable drainage on Step 4")
        score -= 5
    if not findings:
        findings.append("Civil / geotech risk profile is low for the given site data")
    return {"status": "ok" if score >= 55 else "warning",
            "score": max(0, min(100, score)),
            "findings": findings, "recs": recs,
            "summary": f"Civil rating: {_rating(max(0, score))}"}


def _agent_structural(proj: dict[str, Any]) -> dict[str, Any]:
    site = _safe_json(proj.get("site_config"))
    pv = _safe_json(proj.get("pv_config"))
    findings, recs = [], []
    score = 100
    wind = site.get("wind_zone")
    mounting = pv.get("mounting")
    if wind == "cyclone":
        findings.append("Cyclone-prone zone")
        recs.append("Specify structures certified to IEC 61400 Class-I or equivalent")
        score -= 20
        if mounting == "single_axis":
            findings.append("Single-axis trackers in cyclone zone - stow angle + control required")
            score -= 10
    elif wind == "z3_high":
        findings.append("High wind zone - upgrade module clamps + rail gauge")
        score -= 8
    seismic = site.get("seismic_zone")
    if seismic in ("zone_3", "zone_4"):
        findings.append(f"Seismic {seismic} - anchor & bracing design attention")
        recs.append("Structural PE sign-off on foundations + transformer base")
        score -= 10
    if not findings:
        findings.append("Structural loading profile is standard for site data given")
    return {"status": "ok" if score >= 55 else "warning",
            "score": max(0, min(100, score)),
            "findings": findings, "recs": recs,
            "summary": f"Structural rating: {_rating(max(0, score))}"}


def _agent_ict(proj: dict[str, Any]) -> dict[str, Any]:
    tech = _safe_json(proj.get("technology_config"))
    selected = set(tech.get("selected") or [])
    findings, recs = [], []
    score = 100
    if not selected:
        findings.append("No technology stack selected on Step 5")
        recs.append("Enable at least SCADA + monitoring + cyber security")
        score = 25
        return {"status": "warning", "score": score,
                "findings": findings, "recs": recs,
                "summary": f"ICT rating: {_rating(score)}"}
    if "cyber" not in selected:
        findings.append("Cyber security not selected - not bankable for utility off-take")
        recs.append("Enable cyber security + firewall on Step 5")
        score -= 15
    if "gps_sync" not in selected and "scada" in selected:
        findings.append("SCADA without GPS time sync - IEC 61850 event correlation degraded")
        score -= 8
    if "fibre" not in selected and "ind_eth" not in selected:
        findings.append("Neither fibre nor industrial Ethernet backbone selected")
        recs.append("Enable fibre for the plant collection network")
        score -= 12
    if "backup_srv" not in selected and "cloud_backup" not in selected:
        findings.append("No backup strategy (backup server nor cloud backup)")
        recs.append("Choose at least one backup path for SCADA historian")
        score -= 8
    if not findings:
        findings.append("ICT infrastructure is comprehensive")
    return {"status": "ok" if score >= 55 else "warning",
            "score": max(0, min(100, score)),
            "findings": findings, "recs": recs,
            "summary": f"ICT rating: {_rating(max(0, score))}"}


def _agent_scada(proj: dict[str, Any]) -> dict[str, Any]:
    tech = _safe_json(proj.get("technology_config"))
    elec = _safe_json(proj.get("electrical_config"))
    s = set(tech.get("selected") or [])
    e = set(elec.get("selected") or [])
    findings, recs = [], []
    score = 100
    if "scada" not in s:
        findings.append("SCADA not enabled in Step 5 technology stack")
        recs.append("Enable SCADA + EMS + PPC on Step 5")
        score -= 25
    if "scada" in s and "scada" not in e:
        findings.append("SCADA in tech stack but no SCADA service on Step 6 - cabling scope missing")
        recs.append("Enable SCADA in Step 6 electrical services")
        score -= 8
    if "ems" not in s:
        findings.append("EMS not selected - dispatch optimisation missing")
        recs.append("Enable EMS on Step 5")
        score -= 5
    if "ppc" not in s:
        findings.append("Power Plant Controller (PPC) not selected - grid-code compliance risk")
        recs.append("Enable PPC on Step 5 to meet reactive/frequency response requirements")
        score -= 10
    if "weather" not in s:
        findings.append("Weather station missing - performance model can't be measured")
        recs.append("Enable weather station on Step 5")
        score -= 3
    if not findings:
        findings.append("SCADA / EMS / PPC stack is complete")
    return {"status": "ok" if score >= 55 else "warning",
            "score": max(0, min(100, score)),
            "findings": findings, "recs": recs,
            "summary": f"SCADA rating: {_rating(max(0, score))}"}


def _agent_grid(proj: dict[str, Any]) -> dict[str, Any]:
    site = _safe_json(proj.get("site_config"))
    elec = _safe_json(proj.get("electrical_config"))
    pv = _safe_json(proj.get("pv_config"))
    sizing = pv.get("sizing") or {}
    ac_kw = _f(sizing.get("inverter_ac_kw"))
    findings, recs = [], []
    score = 100
    dist_km = _f(site.get("grid_distance_km"), -1)
    if dist_km < 0:
        findings.append("Grid distance not set on Step 3")
        score -= 8
    elif dist_km > 15:
        findings.append(f"Grid distance {dist_km:.1f} km - substation extension CAPEX will be material")
        recs.append("Include line construction + wayleave cost in Step 8 CAPEX")
        score -= 10
    elif dist_km > 5:
        findings.append(f"Grid distance {dist_km:.1f} km - budget for interconnection line + easements")
        score -= 3
    hv_kv = _f(site.get("hv_line_kv"), -1)
    if hv_kv > 0 and ac_kw > 0:
        # Rough sanity: 33 kV OK up to ~15 MW, 66 kV up to ~50 MW, else 132/161 kV
        if ac_kw > 15000 and hv_kv <= 33:
            findings.append(f"Interconnect at {hv_kv} kV for {ac_kw/1000:.1f} MW AC - consider 66 kV+")
            score -= 8
        if ac_kw > 50000 and hv_kv < 66:
            findings.append(f"Interconnect at {hv_kv} kV for {ac_kw/1000:.1f} MW AC - 132 kV recommended")
            score -= 12
    services = set(elec.get("selected") or [])
    if "transformers" not in services:
        findings.append("Transformers not selected on Step 6")
        recs.append("Enable transformer service on Step 6")
        score -= 15
    if "rmu" not in services and ac_kw > 3000:
        findings.append("RMU absent for a > 3 MW plant")
        recs.append("Enable RMU on Step 6")
        score -= 5
    if not findings:
        findings.append("Grid interconnection scope is coherent")
    return {"status": "ok" if score >= 55 else "warning",
            "score": max(0, min(100, score)),
            "findings": findings, "recs": recs,
            "summary": f"Grid rating: {_rating(max(0, score))}"}


def _agent_financial(proj: dict[str, Any]) -> dict[str, Any]:
    fin = _safe_json(proj.get("finance_config"))
    computed = fin.get("computed") or {}
    findings, recs = [], []
    score = 100
    if not computed:
        return {"status": "warning", "score": 20,
                "findings": ["Financial model not yet computed on Step 8"],
                "recs": ["Complete Step 8 to run the finance engine"],
                "summary": "Financial rating: F - not ready"}
    irr = _f(computed.get("irr_pct"))
    lcoe = _f(computed.get("lcoe_local_per_kwh"))
    tariff = _f(fin.get("tariff_local_per_kwh"))
    dscr_min = _f(computed.get("dscr_min"))
    payback = _f(computed.get("payback_years"))
    if irr < 8:
        findings.append(f"IRR {irr:.1f}% is below the 8% utility benchmark")
        recs.append("Renegotiate PPA or reduce CAPEX assumptions")
        score -= 15
    elif irr < 12:
        findings.append(f"IRR {irr:.1f}% is acceptable but not compelling")
        score -= 5
    if dscr_min > 0 and dscr_min < 1.20:
        findings.append(f"DSCR min {dscr_min:.2f}x - lenders typically require >= 1.25x")
        recs.append("Lengthen debt tenor or lower leverage")
        score -= 15
    elif dscr_min > 0 and dscr_min < 1.30:
        findings.append(f"DSCR min {dscr_min:.2f}x is right at the covenant floor - tight")
        score -= 5
    if tariff > 0 and lcoe > 0:
        margin = (tariff - lcoe) / tariff * 100
        if margin < 15:
            findings.append(f"Tariff-LCOE margin {margin:.1f}% is thin - sensitive to tariff review")
            score -= 8
    if payback > 12:
        findings.append(f"Payback {payback:.1f} yr is longer than the debt tenor")
        recs.append("Consider ITC / accelerated depreciation")
        score -= 5
    if not findings:
        findings.append("Financial metrics are all within bank-comfort range")
    return {"status": "ok" if score >= 55 else "warning",
            "score": max(0, min(100, score)),
            "findings": findings, "recs": recs,
            "summary": f"Financial rating: {_rating(max(0, score))}"}


def _agent_investment(proj: dict[str, Any]) -> dict[str, Any]:
    findings, recs = [], []
    score = 100
    if not (proj.get("investor") or "").strip():
        findings.append("Investor field is empty on Step 1")
        recs.append("Populate Step 1 investor when a champion emerges")
        score -= 20
    if not (proj.get("developer") or "").strip():
        findings.append("Developer / EPC not identified")
        score -= 5
    if not (proj.get("description") or "").strip():
        findings.append("Executive description missing - investor memo will be weak")
        score -= 5
    if not (proj.get("client_name") or "").strip():
        findings.append("Off-taker / client is blank")
        recs.append("Investors need clarity on the off-take - populate Step 1 client")
        score -= 15
    if not findings:
        findings.append("Deal team + off-taker identity is clear")
    return {"status": "ok" if score >= 55 else "warning",
            "score": max(0, min(100, score)),
            "findings": findings, "recs": recs,
            "summary": f"Investment posture: {_rating(max(0, score))}"}


def _agent_risk(proj: dict[str, Any]) -> dict[str, Any]:
    reg = _safe_json(proj.get("regulatory_config"))
    findings, recs = [], []
    score = 100
    items = reg.get("items") or {}
    if not items:
        findings.append("Development & Regulatory not yet completed")
        recs.append("Open /large-scale-solar/<pid>/regulatory to capture posture")
        score -= 25
    else:
        critical = ("esia", "grid_interconnect", "energy_commission", "land_tenure")
        for code in critical:
            st = (items.get(code) or {}).get("status") or "not_started"
            if st in ("not_started", "denied"):
                findings.append(f"{code}: {st}")
                score -= 8
    if not reg.get("land_tenure"):
        findings.append("Land tenure structure not chosen")
        recs.append("Pick a tenure on the Regulatory step")
        score -= 10
    fin = _safe_json(proj.get("finance_config"))
    if fin.get("revenue_model") == "merchant":
        findings.append("Merchant revenue model - price + volume risk material")
        recs.append("Consider PPA cover for at least the debt tenor")
        score -= 10
    if not findings:
        findings.append("Development risk posture is under control")
    return {"status": "ok" if score >= 55 else "warning",
            "score": max(0, min(100, score)),
            "findings": findings, "recs": recs,
            "summary": f"Risk profile: {_rating(max(0, score))}"}


def _agent_marketplace(proj: dict[str, Any]) -> dict[str, Any]:
    tech = _safe_json(proj.get("technology_config"))
    elec = _safe_json(proj.get("electrical_config"))
    pv = _safe_json(proj.get("pv_config"))
    cats = _marketplace_categories_for(pv, tech, elec)
    findings, recs = [], []
    score = 100
    if not cats:
        findings.append("No marketplace categories derived - Steps 5-7 incomplete")
        score = 30
    if len(cats) < 6:
        findings.append(f"Only {len(cats)} categories mapped - procurement scope narrow")
        recs.append("Enable more technology + electrical services on Steps 5-6")
        score -= 8
    if not findings:
        findings.append(f"{len(cats)} marketplace categories mapped from tech/electrical picks")
    return {"status": "ok" if score >= 55 else "warning",
            "score": max(0, min(100, score)),
            "findings": findings, "recs": recs,
            "summary": f"Marketplace coverage: {_rating(max(0, score))}"}


def _agent_boq(proj: dict[str, Any]) -> dict[str, Any]:
    findings, recs = [], []
    score = 100
    if not proj.get("boq_project_id"):
        findings.append("No BOQ project linked - Step 9 not run")
        recs.append("Run Step 9 to auto-generate a linked BOQ project + buildings")
        score = 40
    else:
        findings.append(f"BOQ project #{proj['boq_project_id']} linked")
    fac = _safe_json(proj.get("facility_config"))
    if not (fac.get("buildings") or []):
        findings.append("No buildings enabled on Step 4 - BOQ scope will be sparse")
        recs.append("Enable at least Control Room + O&M + Transformer Yard")
        score -= 15
    return {"status": "ok" if score >= 55 else "warning",
            "score": max(0, min(100, score)),
            "findings": findings, "recs": recs,
            "summary": f"BOQ readiness: {_rating(max(0, score))}"}


def _agent_report_writer(proj: dict[str, Any]) -> dict[str, Any]:
    findings, recs = [], []
    score = 100
    # This agent nominally invokes the LLM narrative through the SolarPro
    # AI chain. Here we produce a deterministic executive narrative from
    # the project's stored data so the agent is always useful even when
    # the LLM chain is down.
    pv = _safe_json(proj.get("pv_config"))
    fin = _safe_json(proj.get("finance_config"))
    sizing = pv.get("sizing") or {}
    computed = fin.get("computed") or {}
    kwp = _f(sizing.get("kwp_input") or pv.get("kwp") or proj.get("target_kwp"))
    if kwp <= 0:
        findings.append("Not enough data to author reports - complete Steps 1-8")
        return {"status": "warning", "score": 30,
                "findings": findings, "recs": ["Return once Step 8 is done"],
                "summary": "Reports not ready"}
    narrative = (
        f"{proj.get('project_name')} is a {kwp/1000:.1f} MWp "
        f"utility-scale plant proposed for "
        f"{proj.get('district') or ''} {proj.get('region') or ''} {proj.get('country') or ''}. "
        f"The design produces {_f(sizing.get('annual_gen_mwh')):,.0f} MWh/yr at PR "
        f"{_f(pv.get('performance_ratio'), 0.78):.2f}. "
        f"Total CAPEX is USD {_f(computed.get('total_capex_usd'))/1e6:.1f}M "
        f"with a base-case IRR of {_f(computed.get('irr_pct')):.1f}% "
        f"and LCOE {_f(computed.get('lcoe_local_per_kwh')):.4f} {proj.get('currency') or 'GHS'}/kWh."
    )
    findings.append("Executive narrative drafted from project data")
    recs.append("Download the 5 PDF reports on Step 13")
    return {"status": "ok", "score": score,
            "findings": findings, "recs": recs,
            "summary": "Report narrative ready",
            "narrative": narrative}


def _agent_qa_qc(proj: dict[str, Any]) -> dict[str, Any]:
    findings, recs = [], []
    score = 100
    checks = [
        ("Step 1 identity", bool((proj.get("project_name") or "").strip())),
        ("Step 2 project type", bool((proj.get("project_type") or "").strip())),
        ("Step 3 site config", _is_meaningfully_populated("site_config", proj.get("site_config"))),
        ("Step 4 facility",   _is_meaningfully_populated("facility_config", proj.get("facility_config"))),
        ("Step 5 technology", _is_meaningfully_populated("technology_config", proj.get("technology_config"))),
        ("Step 6 electrical", _is_meaningfully_populated("electrical_config", proj.get("electrical_config"))),
        ("Step 7 PV design",  _is_meaningfully_populated("pv_config", proj.get("pv_config"))),
        ("Step 8 finance",    _is_meaningfully_populated("finance_config", proj.get("finance_config"))),
        ("Step 9 BOQ linked", bool(proj.get("boq_project_id"))),
    ]
    missing = [name for name, done in checks if not done]
    if missing:
        findings.append(f"Missing / incomplete steps: {', '.join(missing)}")
        score -= 6 * len(missing)
        recs.append("Complete the missing steps before requesting Enterprise sign-off")
    if not missing:
        findings.append("All upstream engineering + finance steps are populated")
    return {"status": "ok" if score >= 55 else "warning",
            "score": max(0, min(100, score)),
            "findings": findings, "recs": recs,
            "summary": f"QA/QC completeness: {_rating(max(0, score))}"}


def _agent_reviewer(proj: dict[str, Any], sub_scores: dict[str, int]) -> dict[str, Any]:
    """Overall bankability + readiness score - aggregates every specialist."""
    findings, recs = [], []
    if not sub_scores:
        return {"status": "warning", "score": 0,
                "findings": ["No specialist scores available"],
                "recs": [], "summary": "Not ready"}
    avg = sum(sub_scores.values()) / len(sub_scores)
    score = int(round(avg))
    reds = [k for k, v in sub_scores.items() if v < 55]
    ambers = [k for k, v in sub_scores.items() if 55 <= v < 70]
    if reds:
        findings.append(f"Red-status specialists: {', '.join(reds)}")
        recs.append("Address every red-status specialist before EPC bid")
    if ambers:
        findings.append(f"Amber-status specialists: {', '.join(ambers)}")
    if not reds and not ambers:
        findings.append("Every specialist above 70 - project is EPC-ready")
    findings.append(f"Overall bankability score: {score}/100 ({_rating(score)})")
    return {"status": "ok" if score >= 55 else "warning",
            "score": score,
            "findings": findings, "recs": recs,
            "summary": f"Project readiness: {_rating(score)}"}


AGENT_RUNNERS: dict[str, Any] = {
    "pv_design":     _agent_pv_design,
    "electrical":    _agent_electrical,
    "civil":         _agent_civil,
    "structural":    _agent_structural,
    "ict":           _agent_ict,
    "scada":         _agent_scada,
    "grid":          _agent_grid,
    "financial":     _agent_financial,
    "investment":    _agent_investment,
    "risk":          _agent_risk,
    "marketplace":   _agent_marketplace,
    "boq":           _agent_boq,
    "report_writer": _agent_report_writer,
    "qa_qc":         _agent_qa_qc,
    # 'reviewer' is orchestrator-only and runs last with sub-scores.
}


def run_agent_orchestrator(proj: dict[str, Any]) -> dict[str, Any]:
    """Dispatch every specialist against the project, then run the
    reviewer with the collected sub-scores. Returns a full report."""
    results: dict[str, dict[str, Any]] = {}
    for code in AGENT_CODES:
        if code == "reviewer":
            continue
        runner = AGENT_RUNNERS.get(code)
        if not runner:
            continue
        try:
            results[code] = runner(proj)
        except Exception as e:   # pragma: no cover
            results[code] = {"status": "error", "score": 0,
                             "findings": [f"Agent crash: {e}"],
                             "recs": ["Retry after fixing the project data"],
                             "summary": "Agent error"}
    sub_scores = {c: r["score"] for c, r in results.items()}
    results["reviewer"] = _agent_reviewer(proj, sub_scores)
    return {"specialists": results,
            "aggregate_score": results["reviewer"]["score"],
            "aggregate_status": results["reviewer"]["status"]}


# ---- agent-runs storage ----

_AGENTRUN_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS capital_investment_agent_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id     INTEGER NOT NULL,
    user_id        INTEGER NOT NULL,
    agent_code     TEXT NOT NULL,
    status         TEXT DEFAULT 'ok',
    score          INTEGER DEFAULT 0,
    payload        TEXT DEFAULT '{}',
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ciar_project ON capital_investment_agent_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_ciar_user    ON capital_investment_agent_runs(user_id);
CREATE INDEX IF NOT EXISTS idx_ciar_recent  ON capital_investment_agent_runs(project_id, created_at DESC);
"""
_AGENTRUN_POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS capital_investment_agent_runs (
    id             SERIAL PRIMARY KEY,
    project_id     INTEGER NOT NULL,
    user_id        INTEGER NOT NULL,
    agent_code     TEXT NOT NULL,
    status         TEXT DEFAULT 'ok',
    score          INTEGER DEFAULT 0,
    payload        TEXT DEFAULT '{}',
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ciar_project ON capital_investment_agent_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_ciar_user    ON capital_investment_agent_runs(user_id);
CREATE INDEX IF NOT EXISTS idx_ciar_recent  ON capital_investment_agent_runs(project_id, created_at DESC);
"""


def _ensure_agent_runs_schema(get_db) -> None:
    try:
        with get_db() as c:
            c.executescript(_AGENTRUN_SQLITE_DDL)
        return
    except Exception:
        pass
    for stmt in _AGENTRUN_POSTGRES_DDL.split(";"):
        s = stmt.strip()
        if not s:
            continue
        try:
            with get_db() as c:
                c.execute(s)
        except Exception:
            pass


def country_framework(country: str | None) -> dict[str, Any]:
    """Return the regulatory framework for a country, falling back to
    'generic' when unknown. Match is case-insensitive by leading match."""
    if not country:
        return COUNTRY_REGULATORY_FRAMEWORKS["generic"]
    c = country.strip()
    if c in COUNTRY_REGULATORY_FRAMEWORKS:
        return COUNTRY_REGULATORY_FRAMEWORKS[c]
    # Case-insensitive fallback
    for k, v in COUNTRY_REGULATORY_FRAMEWORKS.items():
        if k.lower() == c.lower():
            return v
    return COUNTRY_REGULATORY_FRAMEWORKS["generic"]


# ---------------------------------------------------------------------------
# Slice 7 - 3D Digital Twin Studio (replaces the classic /shading page for
# capital-investment projects). Scene is built server-side into a JSON
# graph consumed by Three.js in the template.
# ---------------------------------------------------------------------------

# Layer palette used by both scene generation and the left-nav toggles.
DT_LAYER_PALETTE: dict[str, str] = {
    # Site
    "terrain":         "#3a4a2a",   # olive-brown ground
    "fence":           "#c0a060",   # tan
    "gate":            "#e0a020",   # amber
    "internal_roads":  "#606060",   # grey
    "drainage":        "#3a5a80",   # slate blue
    # Buildings
    "building":        "#e0c080",   # sand
    "control_room":    "#f59e0b",   # SolarPro warning
    "om_building":     "#c76a2e",
    "security_gate":   "#a06040",
    "battery_room":    "#7c4e9f",
    "switchgear_bldg": "#5c7cff",
    "transformer_bldg":"#c04040",
    "scada_bldg":      "#20b0a0",
    # Power system
    "pv_array":        "#1a3468",   # deep blue
    "pv_row":          "#2050a0",
    "combiner":        "#40a0e0",
    "inverter":        "#e0c020",
    "transformer":     "#c04040",
    "rmu":             "#e05050",
    "mv_switchgear":   "#a02020",
    "cable_trench":    "#606060",
    # ICT / SCADA / SAFETY
    "cctv_pole":       "#ffffff",
    "weather_mast":    "#20e0c0",
    "lighting_pole":   "#f0e080",
    "earthing_pit":    "#606030",
    "fire_hydrant":    "#e02020",
    "warning_sign":    "#e0a020",
}

# Every scene object carries a layer code so the left-nav can toggle it.
DT_LAYER_GROUPS: list[tuple[str, str, list[str]]] = [
    # (group_label, group_icon, [object_layer_codes])
    ("SITE",       "bi-map",             ["terrain", "fence", "gate",
                                          "internal_roads", "drainage"]),
    ("BUILDINGS",  "bi-buildings",       ["control_room", "om_building",
                                          "security_gate", "battery_room",
                                          "switchgear_bldg", "transformer_bldg",
                                          "scada_bldg", "building"]),
    ("PV FIELD",   "bi-grid-3x3",        ["pv_array", "pv_row"]),
    ("POWER SYSTEM","bi-lightning",      ["combiner", "inverter", "transformer",
                                          "rmu", "mv_switchgear", "cable_trench"]),
    ("ICT",        "bi-hdd-network",     ["cctv_pole", "weather_mast"]),
    ("LIGHTING",   "bi-lightbulb",       ["lighting_pole"]),
    ("EARTHING",   "bi-arrow-down",      ["earthing_pit"]),
    ("SAFETY",     "bi-fire",            ["fire_hydrant", "warning_sign"]),
]


def _sun_position(lat_deg: float, lon_deg: float,
                  month: int, hour: float,
                  tz_offset_h: float = 0.0) -> dict[str, float]:
    """NOAA-simplified solar altitude / azimuth for a mid-month day.
    Inputs are latitude, longitude (unused for local-hour convention),
    integer month 1-12, and float hour 0-24 in local solar time.
    Returns dict with 'altitude_deg' and 'azimuth_deg' (0=N, 90=E, 180=S, 270=W).
    Robust enough for shading + digital twin sun-path animation."""
    import math

    # Day-of-year for the 15th of the month.
    day_of_year_by_month = {1:15, 2:46, 3:74, 4:105, 5:135, 6:166,
                            7:196, 8:227, 9:258, 10:288, 11:319, 12:349}
    doy = day_of_year_by_month.get(month, 172)
    # Declination.
    decl = 23.45 * math.sin(math.radians(360.0 * (284 + doy) / 365.0))
    decl_r = math.radians(decl)
    lat_r  = math.radians(lat_deg)
    # Local solar-time hour angle. hour=12 -> H=0.
    H = math.radians(15.0 * (hour - 12.0))
    sin_alt = (math.sin(lat_r) * math.sin(decl_r)
               + math.cos(lat_r) * math.cos(decl_r) * math.cos(H))
    sin_alt = max(-1.0, min(1.0, sin_alt))
    alt = math.asin(sin_alt)
    # Azimuth via atan2 - measured from North, clockwise (0=N, 90=E, 180=S).
    y = -math.sin(H)
    x = math.tan(decl_r) * math.cos(lat_r) - math.sin(lat_r) * math.cos(H)
    az = math.degrees(math.atan2(y, x))
    az = (az + 360.0) % 360.0
    return {
        "altitude_deg": round(math.degrees(alt), 3),
        "azimuth_deg":  round(az, 3),
        "month":        month,
        "hour":         round(hour, 3),
        "is_daylight":  math.degrees(alt) > 0.0,
    }


def build_scene_from_project(proj: dict[str, Any]) -> dict[str, Any]:
    """Return a scene-graph dict consumable by the Three.js template.
    Units: metres. Origin at site centre. +X = East, +Z = South (Three.js
    right-handed). Buildings from facility_config, PV field sized from
    pv_config, tacked around a rough grid layout."""
    import math

    pv_cfg = _safe_json(proj.get("pv_config"))
    fac_cfg = _safe_json(proj.get("facility_config"))
    site_cfg = _safe_json(proj.get("site_config"))
    elec_cfg = _safe_json(proj.get("electrical_config"))
    tech_cfg = _safe_json(proj.get("technology_config"))

    sizing = pv_cfg.get("sizing") or {}
    kwp = float(sizing.get("kwp_input") or pv_cfg.get("kwp")
                or (proj.get("target_kwp") or 0))
    land_area_ha = float(site_cfg.get("land_area_ha") or max(kwp / 800.0, 5.0))
    land_side_m = math.sqrt(land_area_ha * 10_000.0)   # square approximation
    tilt_deg = float(pv_cfg.get("tilt_deg") or 12.0)
    azimuth_deg = float(pv_cfg.get("azimuth_deg") or 180.0)
    n_modules = int(sizing.get("n_modules") or 0)
    n_central_inv = int(sizing.get("n_central_inverters") or 0)

    # --- Terrain ---
    terrain = {
        "layer": "terrain",
        "kind": "ground",
        "side_m": land_side_m,
        "label": "Site",
        "meta": {"land_area_ha": land_area_ha,
                 "terrain": site_cfg.get("terrain") or "flat",
                 "soil":    site_cfg.get("soil") or "sandy"},
    }

    # --- Fence (perimeter square inset 1m) ---
    inset = -land_side_m / 2.0 + 1.0
    fence = {
        "layer": "fence",
        "kind":  "line_loop",
        "points": [
            [inset,               inset],
            [-inset,              inset],
            [-inset,             -inset],
            [inset,              -inset],
        ],
        "height_m": 2.4,
        "label": "Perimeter security fence",
        "meta":  {"perimeter_m": round(4 * (land_side_m - 2.0), 1)},
    }

    # --- Buildings (arranged in a strip along the northern edge) ---
    selected_buildings = fac_cfg.get("buildings") or []
    buildings = []
    strip_z = -land_side_m / 2.0 + 25.0   # 25m from north edge
    strip_x0 = -land_side_m / 2.0 + 15.0
    x_cursor = strip_x0
    building_gap = 8.0
    building_dim_defaults: dict[str, dict[str, float]] = {
        "control_room":     {"w": 15, "l": 12, "h": 6},
        "om_building":      {"w": 20, "l": 12, "h": 5},
        "security_gate":    {"w": 6,  "l": 5,  "h": 3},
        "warehouse":        {"w": 25, "l": 15, "h": 6},
        "workshop":         {"w": 15, "l": 10, "h": 5},
        "admin":            {"w": 15, "l": 10, "h": 5},
        "training":         {"w": 10, "l": 8,  "h": 4},
        "spare_parts":      {"w": 10, "l": 8,  "h": 4},
        "chemical":         {"w": 8,  "l": 6,  "h": 4},
        "battery_room":     {"w": 20, "l": 10, "h": 5},
        "inverter_room":    {"w": 15, "l": 8,  "h": 4},
        "transformer_bldg": {"w": 12, "l": 10, "h": 6},
        "switchgear_bldg":  {"w": 15, "l": 10, "h": 5},
        "scada_bldg":       {"w": 12, "l": 8,  "h": 5},
        "comms_bldg":       {"w": 8,  "l": 6,  "h": 4},
        "welfare":          {"w": 10, "l": 8,  "h": 4},
        "washroom":         {"w": 6,  "l": 4,  "h": 3},
        "parking":          {"w": 30, "l": 15, "h": 0.2},
    }
    for b in selected_buildings:
        dims = building_dim_defaults.get(b, {"w": 12, "l": 8, "h": 5})
        # Layer key is the building code itself so we can pick a color +
        # a left-nav toggle for it.
        layer = b if b in DT_LAYER_PALETTE else "building"
        label = next((L for c, L, _, _ in BUILDING_TYPES if c == b), b)
        buildings.append({
            "id":    f"bldg_{b}",
            "layer": layer,
            "kind":  "box",
            "x":     x_cursor + dims["w"] / 2.0,
            "y":     dims["h"] / 2.0,
            "z":     strip_z,
            "w":     dims["w"],
            "h":     dims["h"],
            "l":     dims["l"],
            "label": label,
            "meta":  {"building_code": b,
                      "sub_items":     BUILDING_SUB_ITEMS.get(b, []),
                      "footprint_m2":  round(dims["w"] * dims["l"], 1)},
        })
        x_cursor += dims["w"] + building_gap

    # --- Transformer yard (SE corner, only if transformer_bldg not enabled) ---
    if "transformers" in (elec_cfg.get("selected") or []) \
            or "transformer_bldg" not in selected_buildings:
        buildings.append({
            "id":    "transformer_yard",
            "layer": "transformer",
            "kind":  "box",
            "x":      land_side_m / 2.0 - 20.0,
            "y":      3.0,
            "z":      land_side_m / 2.0 - 20.0,
            "w":     15, "h": 6, "l": 15,
            "label": "Transformer yard",
            "meta":  {"contents": "Step-up transformer, RMU, protection"},
        })

    # --- PV field ---
    # Available PV area = land_area minus a 60m northern strip for buildings
    # and a 20m perimeter margin.
    pv_field_z_start = strip_z + 30.0
    pv_field_z_end   = land_side_m / 2.0 - 20.0
    pv_field_x_start = -land_side_m / 2.0 + 20.0
    pv_field_x_end   =  land_side_m / 2.0 - 20.0
    pv_field_l = max(pv_field_z_end - pv_field_z_start, 20.0)
    pv_field_w = max(pv_field_x_end - pv_field_x_start, 20.0)

    # Row layout: single-axis tracker rows aligned N-S; row pitch = 6m;
    # row width = 2m; row length spans the plot with 5m gap at either end.
    row_pitch = 6.0
    row_width = 2.0
    row_length = max(pv_field_l - 10.0, 10.0)
    # Number of rows we can physically fit.
    max_rows = max(1, int(pv_field_w / row_pitch))
    # Number of rows we NEED to fit the module count.
    modules_per_row_area = int(row_length / 2.0) if row_length > 0 else 30
    modules_per_row = max(10, min(60, modules_per_row_area))
    needed_rows = max(1, math.ceil(n_modules / modules_per_row))
    n_rows = min(max_rows, needed_rows) if n_modules else 0

    pv_rows: list[dict[str, Any]] = []
    for i in range(n_rows):
        x_i = pv_field_x_start + row_pitch / 2.0 + i * row_pitch
        pv_rows.append({
            "id":    f"row_{i+1:03d}",
            "layer": "pv_row",
            "kind":  "box",
            "x":     x_i,
            "y":     1.5,
            "z":     (pv_field_z_start + pv_field_z_end) / 2.0,
            "w":     row_width,
            "h":     0.05,
            "l":     row_length,
            "tilt_deg": tilt_deg,
            "azimuth_deg": azimuth_deg,
            "label": f"PV row {i+1}",
            "meta":  {"modules": modules_per_row,
                      "row_index": i + 1,
                      "tilt_deg": tilt_deg,
                      "azimuth_deg": azimuth_deg},
        })

    pv_meta = {
        "kwp": kwp,
        "n_modules_planned": n_modules,
        "n_modules_placed":  n_rows * modules_per_row if n_rows else 0,
        "n_rows": n_rows,
        "modules_per_row": modules_per_row,
        "row_pitch_m": row_pitch,
        "tilt_deg": tilt_deg,
        "azimuth_deg": azimuth_deg,
        "field_w_m": round(pv_field_w, 1),
        "field_l_m": round(pv_field_l, 1),
    }

    # --- Central inverters (spaced through the PV field) ---
    inverters: list[dict[str, Any]] = []
    if n_central_inv > 0 and n_rows > 0:
        for i in range(n_central_inv):
            frac = (i + 0.5) / max(1, n_central_inv)
            inv_x = pv_field_x_start + frac * (pv_field_x_end - pv_field_x_start)
            inverters.append({
                "id":    f"inv_{i+1:02d}",
                "layer": "inverter",
                "kind":  "box",
                "x":     inv_x,
                "y":     1.5,
                "z":     pv_field_z_end - 6.0,
                "w":     4.0, "h": 2.5, "l": 3.0,
                "label": f"Central inverter #{i+1}",
                "meta":  {"kw": sizing.get("central_inverter_kw"),
                          "index": i + 1},
            })

    # --- Internal roads (a spine road along the eastern edge) ---
    roads = [{
        "id":    "spine_road",
        "layer": "internal_roads",
        "kind":  "box",
        "x":     land_side_m / 2.0 - 8.0,
        "y":     0.05,
        "z":     0.0,
        "w":     4.0,
        "h":     0.1,
        "l":     land_side_m - 20.0,
        "label": "Internal spine road",
        "meta":  {"length_m": round(land_side_m - 20.0, 1)},
    }]

    # --- Weather station mast + perimeter CCTV poles + lighting poles ---
    ict = []
    if "weather" in (tech_cfg.get("selected") or []):
        ict.append({
            "id":    "weather_mast",
            "layer": "weather_mast",
            "kind":  "mast",
            "x": pv_field_x_start + 10.0, "y": 6.0, "z": 0.0,
            "w": 0.4, "h": 12.0, "l": 0.4,
            "label": "Weather station mast",
            "meta":  {"instruments": "pyranometer + ambient + module T"},
        })

    # 8 CCTV poles along fence corners + midpoints
    corners = [(inset+1, inset+1), (-inset-1, inset+1),
               (-inset-1, -inset-1), (inset+1, -inset-1)]
    for i, (cx, cz) in enumerate(corners):
        ict.append({
            "id":    f"cctv_{i+1}",
            "layer": "cctv_pole",
            "kind":  "mast",
            "x": cx, "y": 4.0, "z": cz,
            "w": 0.3, "h": 8.0, "l": 0.3,
            "label": f"CCTV pole #{i+1}",
            "meta":  {"coverage_m": 80},
        })

    # 6 perimeter lighting poles
    lighting = []
    perim_positions = [
        ( land_side_m / 4.0, inset+2),
        (-land_side_m / 4.0, inset+2),
        ( land_side_m / 4.0, -inset-2),
        (-land_side_m / 4.0, -inset-2),
        ( inset+2, 0.0),
        (-inset-2, 0.0),
    ]
    for i, (lx, lz) in enumerate(perim_positions):
        lighting.append({
            "id":    f"light_{i+1}",
            "layer": "lighting_pole",
            "kind":  "mast",
            "x": lx, "y": 3.0, "z": lz,
            "w": 0.2, "h": 6.0, "l": 0.2,
            "label": f"Perimeter light #{i+1}",
            "meta":  {"lumens": 20000, "wattage_W": 200},
        })

    # --- Earthing pit near transformer yard ---
    safety = []
    if selected_buildings or n_rows > 0:
        safety.append({
            "id":    "earth_pit_main",
            "layer": "earthing_pit",
            "kind":  "box",
            "x":     land_side_m / 2.0 - 25.0,
            "y":     0.3,
            "z":     land_side_m / 2.0 - 25.0,
            "w":     1.5, "h": 0.6, "l": 1.5,
            "label": "Main earthing pit",
            "meta":  {"resistance_ohm_target": 1.0},
        })

    # --- Assemble scene ---
    return {
        "site": {
            "kwp":               kwp,
            "land_area_ha":      land_area_ha,
            "land_side_m":       round(land_side_m, 1),
            "gps": {"lat": proj.get("gps_lat"),
                    "lon": proj.get("gps_lon")},
            "country":           proj.get("country"),
            "region":            proj.get("region"),
        },
        "camera": {
            # Camera position and target for the initial view.
            "position": [land_side_m * 0.7, land_side_m * 0.5, land_side_m * 0.7],
            "target":   [0, 0, 0],
        },
        "terrain":   terrain,
        "fence":     fence,
        "roads":     roads,
        "buildings": buildings,
        "pv":        {"meta": pv_meta, "rows": pv_rows},
        "inverters": inverters,
        "ict":       ict,
        "lighting":  lighting,
        "safety":    safety,
        "palette":   DT_LAYER_PALETTE,
        "layer_groups": [
            {"label": g_label, "icon": g_icon, "codes": codes}
            for g_label, g_icon, codes in DT_LAYER_GROUPS
        ],
    }


# --- Opportunity DB schema (extends, doesn't duplicate the residential
# leads table since utility-scale is a different domain) ---

_CIO_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS capital_investment_opportunities (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    capital_investment_project_id INTEGER NOT NULL,
    user_id                       INTEGER NOT NULL,
    project_name                  TEXT DEFAULT '',
    investor                      TEXT DEFAULT '',
    developer                     TEXT DEFAULT '',
    client                        TEXT DEFAULT '',
    location                      TEXT DEFAULT '',
    country                       TEXT DEFAULT '',
    currency                      TEXT DEFAULT 'GHS',
    capacity_mwp                  REAL,
    capex_local                   REAL,
    capex_usd                     REAL,
    revenue_y1_local              REAL,
    annual_gen_mwh                REAL,
    npv_local                     REAL,
    irr_pct                       REAL,
    lcoe_local_per_kwh            REAL,
    payback_years                 REAL,
    dscr_avg                      REAL,
    stage                         TEXT DEFAULT 'lead',
    stage_history                 TEXT DEFAULT '[]',
    pipeline_notes                TEXT DEFAULT '',
    tenant_id                     TEXT,
    created_at                    TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at                    TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cio_project ON capital_investment_opportunities(capital_investment_project_id);
CREATE INDEX IF NOT EXISTS idx_cio_user    ON capital_investment_opportunities(user_id);
CREATE INDEX IF NOT EXISTS idx_cio_stage   ON capital_investment_opportunities(user_id, stage);
"""

_CIO_POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS capital_investment_opportunities (
    id                            SERIAL PRIMARY KEY,
    capital_investment_project_id INTEGER NOT NULL,
    user_id                       INTEGER NOT NULL,
    project_name                  TEXT DEFAULT '',
    investor                      TEXT DEFAULT '',
    developer                     TEXT DEFAULT '',
    client                        TEXT DEFAULT '',
    location                      TEXT DEFAULT '',
    country                       TEXT DEFAULT '',
    currency                      TEXT DEFAULT 'GHS',
    capacity_mwp                  DOUBLE PRECISION,
    capex_local                   DOUBLE PRECISION,
    capex_usd                     DOUBLE PRECISION,
    revenue_y1_local              DOUBLE PRECISION,
    annual_gen_mwh                DOUBLE PRECISION,
    npv_local                     DOUBLE PRECISION,
    irr_pct                       DOUBLE PRECISION,
    lcoe_local_per_kwh            DOUBLE PRECISION,
    payback_years                 DOUBLE PRECISION,
    dscr_avg                      DOUBLE PRECISION,
    stage                         TEXT DEFAULT 'lead',
    stage_history                 TEXT DEFAULT '[]',
    pipeline_notes                TEXT DEFAULT '',
    tenant_id                     UUID,
    created_at                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cio_project ON capital_investment_opportunities(capital_investment_project_id);
CREATE INDEX IF NOT EXISTS idx_cio_user    ON capital_investment_opportunities(user_id);
CREATE INDEX IF NOT EXISTS idx_cio_stage   ON capital_investment_opportunities(user_id, stage);
"""


def _ensure_opportunities_schema(get_db) -> None:
    """Idempotent opportunities-table creation. Same per-statement
    transaction discipline as _ensure_capital_investment_schema so a
    Postgres failure doesn't cascade."""
    try:
        with get_db() as c:
            c.executescript(_CIO_SQLITE_DDL)
        return
    except Exception:
        pass
    for stmt in _CIO_POSTGRES_DDL.split(";"):
        s = stmt.strip()
        if not s:
            continue
        try:
            with get_db() as c:
                c.execute(s)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Opportunity builder - derives capacity/CAPEX/revenue/IRR/etc. from an
# already-populated capital-investment project. Called on Step 11 to
# auto-populate the opportunity row.
# ---------------------------------------------------------------------------

def build_opportunity_from_project(proj: dict[str, Any]) -> dict[str, Any]:
    """Return the opportunity payload dict derived from the project's
    stored config blobs. All numeric fields default to None when the
    underlying step hasn't been completed yet."""
    pv_cfg = _safe_json(proj.get("pv_config"))
    fin_cfg = _safe_json(proj.get("finance_config"))
    sizing = pv_cfg.get("sizing") or {}
    computed = fin_cfg.get("computed") or {}

    kwp = sizing.get("kwp_input") or pv_cfg.get("kwp")
    capacity_mwp = round(kwp / 1000.0, 3) if kwp else None
    if capacity_mwp is None and proj.get("target_kwp"):
        capacity_mwp = round(proj["target_kwp"] / 1000.0, 3)

    return {
        "capital_investment_project_id": proj["id"],
        "user_id":       proj["user_id"],
        "project_name":  proj.get("project_name") or "",
        "investor":      proj.get("investor") or "",
        "developer":     proj.get("developer") or "",
        "client":        proj.get("client_name") or "",
        "location":      ", ".join(x for x in (proj.get("region"),
                                               proj.get("country")) if x),
        "country":       proj.get("country") or "",
        "currency":      proj.get("currency") or "GHS",
        "capacity_mwp":  capacity_mwp,
        "capex_local":       computed.get("total_capex_local"),
        "capex_usd":         computed.get("total_capex_usd"),
        "revenue_y1_local":  computed.get("revenue_y1_local"),
        "annual_gen_mwh":    computed.get("annual_gen_mwh")
                             or sizing.get("annual_gen_mwh"),
        "npv_local":         computed.get("npv_local"),
        "irr_pct":           computed.get("irr_pct"),
        "lcoe_local_per_kwh": computed.get("lcoe_local_per_kwh"),
        "payback_years":     computed.get("payback_years"),
        "dscr_avg":          computed.get("dscr_avg"),
    }


# ---------------------------------------------------------------------------
# Engineering: utility-scale PV sizing (self-contained; NOT the load-driven
# calc_pv in web_app.py which tops out at 100 kW). Reuses Ghana climate
# defaults from calc_pv when caller does not specify.
# ---------------------------------------------------------------------------

def size_utility_pv(*,
                    kwp: float,
                    module_wp: float = 550.0,
                    dc_ac_ratio: float = 1.20,
                    tilt_deg: float = 10.0,
                    azimuth_deg: float = 180.0,
                    psh_daily: float = 5.4,
                    performance_ratio: float = 0.78,
                    availability_pct: float = 98.0,
                    annual_degradation_pct: float = 0.5,
                    project_life_yr: int = 25,
                    modules_per_string: int = 28,
                    strings_per_combiner: int = 20,
                    central_inverter_kw: float = 1500.0
                    ) -> dict[str, Any]:
    """Return a utility-scale PV design dict.

    Formulas (industry standard, greenfield ground-mount):
        n_modules       = ceil(kwp * 1000 / module_wp)
        inverter_ac_kw  = kwp / dc_ac_ratio
        n_central_inv   = ceil(inverter_ac_kw / central_inverter_kw)
        strings         = ceil(n_modules / modules_per_string)
        combiners       = ceil(strings / strings_per_combiner)
        annual_gen_mwh  = kwp * psh * 365 * PR * availability / 1000
        lifetime_gen    = sum_{t=1..N} annual_gen * (1 - degrad)^(t-1)
    """
    import math

    if kwp <= 0:
        return {"error": "kwp must be > 0"}
    if module_wp <= 0:
        module_wp = 550.0
    if dc_ac_ratio <= 0:
        dc_ac_ratio = 1.20
    if psh_daily <= 0:
        psh_daily = 5.4
    if performance_ratio <= 0 or performance_ratio > 1:
        performance_ratio = 0.78
    if availability_pct <= 0 or availability_pct > 100:
        availability_pct = 98.0

    n_modules       = int(math.ceil(kwp * 1000 / module_wp))
    dc_kwp_actual   = round(n_modules * module_wp / 1000.0, 2)
    inverter_ac_kw  = round(kwp / dc_ac_ratio, 2)
    n_central_inv   = int(math.ceil(inverter_ac_kw / central_inverter_kw))
    strings         = int(math.ceil(n_modules / max(1, modules_per_string)))
    combiners       = int(math.ceil(strings / max(1, strings_per_combiner)))

    availability_frac = availability_pct / 100.0
    annual_gen_mwh    = round(
        kwp * psh_daily * 365 * performance_ratio * availability_frac / 1000.0,
        2,
    )
    monthly_gen_mwh   = round(annual_gen_mwh / 12.0, 2)

    # Lifetime energy with degradation.
    lifetime_mwh = 0.0
    for t in range(1, project_life_yr + 1):
        lifetime_mwh += annual_gen_mwh * ((1 - annual_degradation_pct / 100.0) ** (t - 1))
    lifetime_mwh = round(lifetime_mwh, 2)

    # First-year specific yield (kWh/kWp/yr).
    specific_yield_kwh_per_kwp = round(annual_gen_mwh * 1000.0 / kwp, 1)

    # DC cable length estimate (m). Rough: modules × 3 m per string plus
    # combiner-to-inverter runs. Utility site typically 5-8 m/kWp of DC cable.
    dc_cable_m_est = int(round(kwp * 6.5, 0))
    # AC MV cable to substation ~ 4 m/kW under 15 km line-of-sight.
    ac_cable_m_est = int(round(kwp * 3.5, 0))

    return {
        "kwp_input":               round(kwp, 2),
        "dc_kwp_actual":           dc_kwp_actual,
        "module_wp":               module_wp,
        "n_modules":               n_modules,
        "dc_ac_ratio":             dc_ac_ratio,
        "inverter_ac_kw":          inverter_ac_kw,
        "n_central_inverters":     n_central_inv,
        "central_inverter_kw":     central_inverter_kw,
        "strings":                 strings,
        "modules_per_string":      modules_per_string,
        "combiners":               combiners,
        "strings_per_combiner":    strings_per_combiner,
        "tilt_deg":                tilt_deg,
        "azimuth_deg":             azimuth_deg,
        "psh_daily":               psh_daily,
        "performance_ratio":       performance_ratio,
        "availability_pct":        availability_pct,
        "annual_degradation_pct":  annual_degradation_pct,
        "project_life_yr":         project_life_yr,
        "annual_gen_mwh":          annual_gen_mwh,
        "monthly_gen_mwh":         monthly_gen_mwh,
        "lifetime_gen_mwh":        lifetime_mwh,
        "specific_yield_kwh_per_kwp": specific_yield_kwh_per_kwp,
        "dc_cable_m_est":          dc_cable_m_est,
        "ac_cable_m_est":          ac_cable_m_est,
    }


# ---------------------------------------------------------------------------
# Engineering: utility-scale finance
# ---------------------------------------------------------------------------

def _irr_bisect(cash_flows: list[float],
                lo: float = -0.99, hi: float = 1.0,
                iters: int = 80) -> float | None:
    """Robust IRR by bisection - handles the sign-change with wide bounds."""
    def npv(r: float) -> float:
        return sum(cf / ((1 + r) ** t) for t, cf in enumerate(cash_flows))
    f_lo, f_hi = npv(lo), npv(hi)
    # Extend upper bound if same sign.
    if f_lo * f_hi > 0:
        for hi in (2.0, 5.0, 10.0):
            f_hi = npv(hi)
            if f_lo * f_hi < 0:
                break
        else:
            return None
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid)
        if abs(f_mid) < 1e-6:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    return (lo + hi) / 2.0


def finance_utility(*,
                    kwp: float,
                    annual_gen_mwh: float,
                    tariff_local_per_kwh: float,
                    fx_local_per_usd: float = 12.0,
                    capex_usd_per_kwp: dict[str, float] | None = None,
                    opex_usd_per_kwp_yr: dict[str, float] | None = None,
                    project_life_yr: int = 25,
                    discount_rate: float = 0.10,
                    debt_ratio: float = 0.70,
                    debt_rate: float = 0.10,
                    debt_tenor_yr: int = 12,
                    tax_rate: float = 0.25,
                    tariff_escalation: float = 0.02,
                    opex_escalation: float = 0.03,
                    degradation_pct: float = 0.5,
                    bess_capex_usd: float = 0.0,
                    contingency_pct: float | None = None,
                    carbon_credit_usd_per_tco2: float = 5.0,
                    grid_ef_kgco2_per_kwh: float = 0.45,
                    monte_carlo_runs: int = 200
                    ) -> dict[str, Any]:
    """CAPEX/OPEX/NPV/IRR/LCOE/DSCR + Monte Carlo P10/P50/P90.

    Convention: money reported in LOCAL currency using fx_local_per_usd. NPV
    uses the discount_rate on nominal local-currency cash flows.
    """
    import math, random

    cx = dict(DEFAULT_CAPEX_USD_PER_KWP)
    if capex_usd_per_kwp:
        cx.update(capex_usd_per_kwp)
    ox = dict(DEFAULT_OPEX_USD_PER_KWP_YR)
    if opex_usd_per_kwp_yr:
        ox.update(opex_usd_per_kwp_yr)

    # CAPEX totals (USD).
    capex_lines_usd: dict[str, float] = {}
    for k, per_kwp in cx.items():
        capex_lines_usd[k] = round(per_kwp * kwp, 2)
    # BESS is a fixed sum, not per-kWp.
    if bess_capex_usd > 0:
        capex_lines_usd["bess_fixed"] = round(bess_capex_usd, 2)
    total_capex_usd = round(sum(capex_lines_usd.values()), 2)
    if contingency_pct is not None and contingency_pct > 0:
        cont = round(total_capex_usd * contingency_pct / 100.0, 2)
        capex_lines_usd["contingency_pct_extra"] = cont
        total_capex_usd = round(total_capex_usd + cont, 2)
    total_capex_local = round(total_capex_usd * fx_local_per_usd, 2)

    # OPEX totals (USD/yr).
    opex_lines_usd_yr: dict[str, float] = {}
    for k, per_kwp_yr in ox.items():
        opex_lines_usd_yr[k] = round(per_kwp_yr * kwp, 2)
    total_opex_usd_yr = round(sum(opex_lines_usd_yr.values()), 2)
    total_opex_local_yr = round(total_opex_usd_yr * fx_local_per_usd, 2)

    # Debt structuring.
    debt_local = round(total_capex_local * debt_ratio, 2)
    equity_local = round(total_capex_local - debt_local, 2)

    # Annual debt service (level payment).
    if debt_local > 0 and debt_rate > 0 and debt_tenor_yr > 0:
        r = debt_rate
        n = debt_tenor_yr
        annuity_factor = (r * (1 + r) ** n) / (((1 + r) ** n) - 1)
        annual_debt_service_local = round(debt_local * annuity_factor, 2)
    else:
        annual_debt_service_local = 0.0

    # Cash flows.
    #  Year 0: -equity
    #  Years 1..N: (revenue - opex - debt service - tax) escalated per year
    revenue_local_y1 = annual_gen_mwh * 1000.0 * tariff_local_per_kwh
    carbon_local_y1 = (annual_gen_mwh * grid_ef_kgco2_per_kwh
                       * carbon_credit_usd_per_tco2 * fx_local_per_usd)
    cash_flows: list[float] = [-equity_local]
    revenue_by_year: list[float] = []
    opex_by_year:    list[float] = []
    debt_by_year:    list[float] = []
    net_by_year:     list[float] = []

    for t in range(1, project_life_yr + 1):
        degrad = (1 - degradation_pct / 100.0) ** (t - 1)
        rev_esc = (1 + tariff_escalation) ** (t - 1)
        opex_esc = (1 + opex_escalation) ** (t - 1)
        rev_t = revenue_local_y1 * degrad * rev_esc + carbon_local_y1 * degrad
        opex_t = total_opex_local_yr * opex_esc
        debt_t = annual_debt_service_local if t <= debt_tenor_yr else 0.0
        taxable = rev_t - opex_t
        tax_t = max(0.0, taxable) * tax_rate
        net_t = rev_t - opex_t - debt_t - tax_t
        revenue_by_year.append(round(rev_t, 2))
        opex_by_year.append(round(opex_t, 2))
        debt_by_year.append(round(debt_t, 2))
        net_by_year.append(round(net_t, 2))
        cash_flows.append(net_t)

    # NPV / IRR / payback / DSCR / LCOE.
    npv_local = round(
        sum(cf / ((1 + discount_rate) ** t) for t, cf in enumerate(cash_flows)),
        2,
    )
    irr_val = _irr_bisect(cash_flows)
    irr_pct = round(irr_val * 100.0, 2) if irr_val is not None else None

    payback_years: float | None = None
    running = -equity_local
    for t, net_t in enumerate(net_by_year, start=1):
        running += net_t
        if running >= 0:
            payback_years = t - (running - net_t) / net_t if net_t else float(t)
            payback_years = round(max(0.0, payback_years), 2)
            break

    dscr_years = []
    for t in range(1, min(debt_tenor_yr, project_life_yr) + 1):
        rev_t = revenue_by_year[t - 1]
        opex_t = opex_by_year[t - 1]
        debt_t = debt_by_year[t - 1]
        if debt_t > 0:
            dscr_years.append((rev_t - opex_t) / debt_t)
    dscr_avg = round(sum(dscr_years) / len(dscr_years), 2) if dscr_years else None
    dscr_min = round(min(dscr_years), 2) if dscr_years else None

    # LCOE - total discounted cost / total discounted energy.
    disc_energy_kwh = 0.0
    for t in range(1, project_life_yr + 1):
        gen_t = annual_gen_mwh * 1000.0 * ((1 - degradation_pct / 100.0) ** (t - 1))
        disc_energy_kwh += gen_t / ((1 + discount_rate) ** t)
    disc_opex_local = sum(
        opex_by_year[t - 1] / ((1 + discount_rate) ** t)
        for t in range(1, project_life_yr + 1)
    )
    lcoe_local_per_kwh = round(
        (total_capex_local + disc_opex_local) / disc_energy_kwh, 4
    ) if disc_energy_kwh > 0 else None

    # Monte Carlo on NPV + IRR.
    if monte_carlo_runs and monte_carlo_runs > 0:
        rng = random.Random(42)
        mc_npv: list[float] = []
        mc_irr: list[float] = []
        for _ in range(monte_carlo_runs):
            # Sample: tariff +/-20%, degrad +/-0.3pt, opex esc +/-2%
            tariff_shock = rng.uniform(0.80, 1.20)
            degrad_shock = degradation_pct + rng.uniform(-0.3, 0.3)
            opex_shock   = opex_escalation + rng.uniform(-0.02, 0.02)
            cf = [-equity_local]
            for t in range(1, project_life_yr + 1):
                degrad_t = (1 - degrad_shock / 100.0) ** (t - 1)
                rev_esc_t = (1 + tariff_escalation) ** (t - 1)
                rev_t = revenue_local_y1 * tariff_shock * degrad_t * rev_esc_t \
                        + carbon_local_y1 * degrad_t
                opex_t = total_opex_local_yr * ((1 + opex_shock) ** (t - 1))
                debt_t = annual_debt_service_local if t <= debt_tenor_yr else 0.0
                taxable = rev_t - opex_t
                tax_t = max(0.0, taxable) * tax_rate
                cf.append(rev_t - opex_t - debt_t - tax_t)
            npv_run = sum(v / ((1 + discount_rate) ** t) for t, v in enumerate(cf))
            mc_npv.append(npv_run)
            irr_run = _irr_bisect(cf)
            if irr_run is not None:
                mc_irr.append(irr_run)
        mc_npv.sort()
        mc_irr.sort()

        def _pct(vals, p):
            if not vals:
                return None
            idx = max(0, min(len(vals) - 1, int(p / 100.0 * len(vals))))
            return round(vals[idx], 2)

        monte_carlo = {
            "runs": monte_carlo_runs,
            "npv_p10": _pct(mc_npv, 10),
            "npv_p50": _pct(mc_npv, 50),
            "npv_p90": _pct(mc_npv, 90),
            "irr_p10_pct": round(_pct(mc_irr, 10) * 100, 2) if _pct(mc_irr, 10) else None,
            "irr_p50_pct": round(_pct(mc_irr, 50) * 100, 2) if _pct(mc_irr, 50) else None,
            "irr_p90_pct": round(_pct(mc_irr, 90) * 100, 2) if _pct(mc_irr, 90) else None,
        }
    else:
        monte_carlo = None

    return {
        "kwp":                       round(kwp, 2),
        "annual_gen_mwh":            annual_gen_mwh,
        "tariff_local_per_kwh":      tariff_local_per_kwh,
        "fx_local_per_usd":          fx_local_per_usd,
        "capex_lines_usd":           capex_lines_usd,
        "total_capex_usd":           total_capex_usd,
        "total_capex_local":         total_capex_local,
        "capex_usd_per_kwp":         round(total_capex_usd / kwp, 2) if kwp else 0.0,
        "opex_lines_usd_yr":         opex_lines_usd_yr,
        "total_opex_usd_yr":         total_opex_usd_yr,
        "total_opex_local_yr":       total_opex_local_yr,
        "debt_local":                debt_local,
        "equity_local":              equity_local,
        "annual_debt_service_local": annual_debt_service_local,
        "revenue_y1_local":          round(revenue_local_y1, 2),
        "carbon_y1_local":           round(carbon_local_y1, 2),
        "npv_local":                 npv_local,
        "irr_pct":                   irr_pct,
        "payback_years":             payback_years,
        "dscr_avg":                  dscr_avg,
        "dscr_min":                  dscr_min,
        "lcoe_local_per_kwh":        lcoe_local_per_kwh,
        "project_life_yr":           project_life_yr,
        "revenue_by_year":           revenue_by_year,
        "opex_by_year":              opex_by_year,
        "debt_by_year":              debt_by_year,
        "net_by_year":               net_by_year,
        "monte_carlo":               monte_carlo,
    }


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

# Inline lazy CREATE - matches the SolarPro convention (see
# _ensure_opps_crawled_table in web_app.py at ~L36196). Postgres path
# mirrors SQLite with SERIAL + ADD COLUMN IF NOT EXISTS idempotency.
_CIP_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS capital_investment_projects (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL,
    project_name      TEXT NOT NULL,
    client_name       TEXT DEFAULT '',
    investor          TEXT DEFAULT '',
    developer         TEXT DEFAULT '',
    country           TEXT DEFAULT '',
    region            TEXT DEFAULT '',
    district          TEXT DEFAULT '',
    gps_lat           REAL,
    gps_lon           REAL,
    description       TEXT DEFAULT '',
    project_status    TEXT DEFAULT 'concept',
    target_cod        TEXT DEFAULT '',
    target_kwp        REAL,
    design_standard   TEXT DEFAULT 'IEC',
    currency          TEXT DEFAULT 'GHS',
    tax_regime        TEXT DEFAULT 'standard',
    project_type      TEXT DEFAULT '',
    site_config       TEXT DEFAULT '',
    facility_config   TEXT DEFAULT '',
    technology_config TEXT DEFAULT '',
    electrical_config TEXT DEFAULT '',
    pv_config         TEXT DEFAULT '',
    finance_config    TEXT DEFAULT '',
    regulatory_config TEXT DEFAULT '',
    boq_project_id    INTEGER,
    tenant_id         TEXT,
    created_at        TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at        TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cip_user_id      ON capital_investment_projects(user_id);
CREATE INDEX IF NOT EXISTS idx_cip_tenant_id    ON capital_investment_projects(tenant_id);
CREATE INDEX IF NOT EXISTS idx_cip_user_status  ON capital_investment_projects(user_id, project_status);
CREATE INDEX IF NOT EXISTS idx_cip_user_updated ON capital_investment_projects(user_id, updated_at DESC);
"""

_CIP_POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS capital_investment_projects (
    id                SERIAL PRIMARY KEY,
    user_id           INTEGER NOT NULL,
    project_name      TEXT NOT NULL,
    client_name       TEXT DEFAULT '',
    investor          TEXT DEFAULT '',
    developer         TEXT DEFAULT '',
    country           TEXT DEFAULT '',
    region            TEXT DEFAULT '',
    district          TEXT DEFAULT '',
    gps_lat           DOUBLE PRECISION,
    gps_lon           DOUBLE PRECISION,
    description       TEXT DEFAULT '',
    project_status    TEXT DEFAULT 'concept',
    target_cod        TEXT DEFAULT '',
    target_kwp        DOUBLE PRECISION,
    design_standard   TEXT DEFAULT 'IEC',
    currency          TEXT DEFAULT 'GHS',
    tax_regime        TEXT DEFAULT 'standard',
    project_type      TEXT DEFAULT '',
    site_config       TEXT DEFAULT '',
    facility_config   TEXT DEFAULT '',
    technology_config TEXT DEFAULT '',
    electrical_config TEXT DEFAULT '',
    pv_config         TEXT DEFAULT '',
    finance_config    TEXT DEFAULT '',
    regulatory_config TEXT DEFAULT '',
    boq_project_id    INTEGER,
    tenant_id         UUID,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cip_user_id      ON capital_investment_projects(user_id);
CREATE INDEX IF NOT EXISTS idx_cip_tenant_id    ON capital_investment_projects(tenant_id);
CREATE INDEX IF NOT EXISTS idx_cip_user_status  ON capital_investment_projects(user_id, project_status);
CREATE INDEX IF NOT EXISTS idx_cip_user_updated ON capital_investment_projects(user_id, updated_at DESC);
"""

# Additive column migrations that run AFTER the CREATE. Each is a lone ALTER
# swallowed by a try/except so an already-added column is a no-op. Add new
# rows at the bottom - do NOT reorder or remove.
_CIP_SQLITE_MIGRATIONS = [
    "ALTER TABLE capital_investment_projects ADD COLUMN target_kwp REAL",
]
_CIP_POSTGRES_MIGRATIONS = [
    "ALTER TABLE capital_investment_projects "
    "ADD COLUMN IF NOT EXISTS target_kwp DOUBLE PRECISION",
]


def _ensure_capital_investment_schema(get_db) -> None:
    """Idempotent lazy schema creation + additive migrations.

    CRITICAL: on Postgres, if one statement in a transaction fails,
    every subsequent statement in the SAME transaction fails with
    "current transaction is aborted, commands ignored until end of
    transaction block". Each DDL therefore runs in its OWN
    `with get_db()` block so failures don't cascade to the
    ADD COLUMN migrations we depend on for `target_kwp`.
    """
    # Try SQLite first (single-statement executescript is Postgres-hostile,
    # so we let it raise on Postgres and fall through).
    sqlite_ok = False
    try:
        with get_db() as c:
            c.executescript(_CIP_SQLITE_DDL)
        sqlite_ok = True
    except Exception:
        sqlite_ok = False
    if sqlite_ok:
        for ddl in _CIP_SQLITE_MIGRATIONS:
            try:
                with get_db() as c:
                    c.execute(ddl)
            except Exception:
                pass   # column already present or backend mismatch
        return

    # Postgres path - split into individual statements, each in its own
    # transaction, so a duplicate-object NOTICE or CREATE-INDEX conflict
    # can't abort the later ADD COLUMN migrations.
    for stmt in _CIP_POSTGRES_DDL.split(";"):
        s = stmt.strip()
        if not s:
            continue
        try:
            with get_db() as c:
                c.execute(s)
        except Exception:
            pass
    for ddl in _CIP_POSTGRES_MIGRATIONS:
        try:
            with get_db() as c:
                c.execute(ddl)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# capital_investment_boq_links - traceability + idempotency between a capital
# investment project's facilities and the generated BOQ buildings/floors.
# Source: SSS_generation_station_design_2026-07-02.md section 3.3.
# ---------------------------------------------------------------------------
_CIBL_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS capital_investment_boq_links (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    capital_investment_project_id INTEGER NOT NULL,
    user_id                       INTEGER NOT NULL,
    tenant_id                     TEXT,
    facility_code                 TEXT NOT NULL,
    source_kind                   TEXT NOT NULL DEFAULT 'facility',
    boq_project_id                INTEGER NOT NULL,
    boq_building_id               INTEGER,
    boq_floor_id                  INTEGER,
    service_codes_csv             TEXT DEFAULT '',
    created_at                    TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at                    TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(capital_investment_project_id, facility_code, source_kind)
);
CREATE INDEX IF NOT EXISTS idx_cibl_project     ON capital_investment_boq_links(capital_investment_project_id);
CREATE INDEX IF NOT EXISTS idx_cibl_boq_project ON capital_investment_boq_links(boq_project_id);
CREATE INDEX IF NOT EXISTS idx_cibl_user        ON capital_investment_boq_links(user_id);
CREATE INDEX IF NOT EXISTS idx_cibl_tenant      ON capital_investment_boq_links(tenant_id);
"""

_CIBL_POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS capital_investment_boq_links (
    id                            SERIAL PRIMARY KEY,
    capital_investment_project_id INTEGER NOT NULL,
    user_id                       INTEGER NOT NULL,
    tenant_id                     UUID,
    facility_code                 TEXT NOT NULL,
    source_kind                   TEXT NOT NULL DEFAULT 'facility',
    boq_project_id                INTEGER NOT NULL,
    boq_building_id               INTEGER,
    boq_floor_id                  INTEGER,
    service_codes_csv             TEXT DEFAULT '',
    created_at                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(capital_investment_project_id, facility_code, source_kind)
);
CREATE INDEX IF NOT EXISTS idx_cibl_project     ON capital_investment_boq_links(capital_investment_project_id);
CREATE INDEX IF NOT EXISTS idx_cibl_boq_project ON capital_investment_boq_links(boq_project_id);
CREATE INDEX IF NOT EXISTS idx_cibl_user        ON capital_investment_boq_links(user_id);
CREATE INDEX IF NOT EXISTS idx_cibl_tenant      ON capital_investment_boq_links(tenant_id);
"""

# Verification result, remembered so a failed live-PG migration is observable
# rather than silently swallowed on every request.
_CIBL_SCHEMA_STATE: dict[str, object] = {"ready": False, "error": ""}


def _ensure_capital_investment_boq_links_schema(get_db) -> bool:
    """Eager, idempotent, per-statement schema creation for the BOQ link
    table WITH verification. Unlike a silent lazy _ensure_*, this VERIFIES the
    table is queryable and remembers the result (see _CIBL_SCHEMA_STATE), so a
    failed live-PostgreSQL migration surfaces instead of being swallowed.
    Returns True when the table is confirmed present + queryable."""
    if _CIBL_SCHEMA_STATE["ready"]:
        return True
    # SQLite fast path (executescript is Postgres-hostile -> falls through).
    try:
        with get_db() as c:
            c.executescript(_CIBL_SQLITE_DDL)
    except Exception:
        # Postgres path - one statement per transaction so an index conflict
        # cannot abort the CREATE TABLE.
        for stmt in _CIBL_POSTGRES_DDL.split(";"):
            s = stmt.strip()
            if not s:
                continue
            try:
                with get_db() as c:
                    c.execute(s)
            except Exception:
                pass
    # Verify the table is actually queryable before declaring success.
    try:
        with get_db() as c:
            c.execute("SELECT 1 FROM capital_investment_boq_links LIMIT 1")
        _CIBL_SCHEMA_STATE["ready"] = True
        _CIBL_SCHEMA_STATE["error"] = ""
    except Exception as exc:
        _CIBL_SCHEMA_STATE["ready"] = False
        _CIBL_SCHEMA_STATE["error"] = str(exc)[:300]
    return bool(_CIBL_SCHEMA_STATE["ready"])


class _CIGenerationRaceLost(Exception):
    """Raised inside the Step 9 create+claim transaction when a concurrent
    request already claimed BOQ generation for this project. Raising (rather
    than returning) rolls back the orphan boq_projects row via get_db()'s
    exception-rollback, so no partial/duplicate BOQ is left behind."""


# ---------------------------------------------------------------------------
# Subscription tier gating - the module is a paid-tier feature.
#
#   FREE       -> marketing landing only.
#   STARTER    -> marketing landing + read-only DEMO.
#   PROFESSIONAL / BUSINESS  -> Steps 1-7 setup + PV sizing summary.
#                                Steps 8-13 + Digital Twin + Regulatory + PDFs
#                                all show an "Upgrade to Enterprise" upsell.
#   ENTERPRISE -> full access.
# ---------------------------------------------------------------------------

CI_TIER_LEVEL: dict[str, int] = {
    "free":         0,
    "starter":      1,
    "professional": 2,
    "business":     2,
    "enterprise":   3,
}
CI_LEVEL_MARKETING = 0   # marketing landing only
CI_LEVEL_DEMO      = 1   # read-only showcase project
CI_LEVEL_SETUP     = 2   # can create real projects + walk Steps 1-7
CI_LEVEL_FULL      = 3   # BOQ, finance, marketplace, CRM, pipeline, reports,
                         # regulatory, digital twin

CI_TIER_LABEL: dict[str, str] = {
    "free": "Free", "starter": "Starter",
    "professional": "Professional", "business": "Business",
    "enterprise": "Enterprise",
}


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    """Portable row accessor - handles sqlite3.Row (IndexError on missing
    column), psycopg2 DictRow / RealDictRow (KeyError), plain dict, and
    attribute-style row objects. Never raises."""
    if row is None:
        return default
    try:
        v = row[key]
        return default if v is None else v
    except (KeyError, IndexError, TypeError):
        pass
    try:
        v = getattr(row, key)
        return default if v is None else v
    except AttributeError:
        return default


def _ci_tier_of(user: Any) -> str:
    """Return the user's Capital Investment tier code.
    Anonymous -> 'free'. Admins are treated as Enterprise regardless
    of stored plan. Bulletproof against both sqlite3.Row (IndexError
    on missing column) and psycopg2 DictRow (KeyError)."""
    if not user:
        return "free"
    try:
        is_admin_raw = _row_get(user, "is_admin", 0) or 0
        is_admin = int(is_admin_raw) if not isinstance(is_admin_raw, bool) else int(bool(is_admin_raw))
    except (TypeError, ValueError):
        is_admin = 0
    if is_admin:
        return "enterprise"
    plan_raw = _row_get(user, "plan", "free") or "free"
    try:
        plan = str(plan_raw).strip().lower()
    except (TypeError, AttributeError):
        plan = "free"
    return plan if plan in CI_TIER_LEVEL else "free"


def _ci_level_of(user: Any) -> int:
    return CI_TIER_LEVEL.get(_ci_tier_of(user), 0)


# ---------------------------------------------------------------------------
# Showcase / demo project (read-only Ghana 20 MW example).
# Used by /large-scale-solar/demo so Starter tier users can see what the
# module produces before signing up for Enterprise.
# ---------------------------------------------------------------------------

def _demo_project() -> dict[str, Any]:
    """Return a hardcoded 20 MW Ghana demo project + derived sizing/finance
    numbers. All fields match the schema of capital_investment_projects so
    templates can render it without special-casing."""
    proj: dict[str, Any] = {
        "id":              0,
        "user_id":         0,
        "project_name":    "DEMO: Tema 20 MWp Solar Farm (Ghana IPP)",
        "client_name":     "Volta River Authority (illustrative)",
        "investor":        "IFC + private-equity fund (illustrative)",
        "developer":       "SolarPro Ghana EPC",
        "country":         "Ghana",
        "region":          "Greater Accra",
        "district":        "Tema Metropolitan",
        "gps_lat":         5.6634, "gps_lon": -0.0166,
        "description":     "20 MWp ground-mount, single-axis tracker, 30 MWh BESS "
                           "in tender-stage feasibility. This is a static demo "
                           "used to showcase the Capital Investment module - all "
                           "numbers are illustrative.",
        "project_status":  "feasibility",
        "target_cod":      "2028-06",
        "target_kwp":      20000.0,
        "design_standard": "IEC",
        "currency":        "GHS",
        "tax_regime":      "epa_exempt",
        "project_type":    "utility_scale",
        "boq_project_id":  None,
        "created_at":      "2026-07-01 12:00:00",
        "updated_at":      "2026-07-01 12:00:00",
    }
    sizing = size_utility_pv(
        kwp=20000, module_wp=600, dc_ac_ratio=1.20, tilt_deg=12,
        azimuth_deg=180, psh_daily=5.4, performance_ratio=0.78,
        availability_pct=98, annual_degradation_pct=0.5,
        project_life_yr=25, central_inverter_kw=1500,
    )
    pv_cfg = {
        "kwp": 20000, "module_wp": 600, "dc_ac_ratio": 1.20,
        "module_tech": "mono_topcon", "mounting": "single_axis",
        "inverter_type": "central", "tilt_deg": 12, "azimuth_deg": 180,
        "psh_daily": 5.4, "performance_ratio": 0.78,
        "availability_pct": 98, "annual_degradation_pct": 0.5,
        "project_life_yr": 25, "battery_chem": "lifepo4",
        "battery_mwh": 30, "sizing": sizing,
    }
    proj["pv_config"] = json.dumps(pv_cfg)
    proj["site_config"] = json.dumps({
        "land_area_ha": 50, "terrain": "flat", "slope": "3_5",
        "soil": "sandy", "flood_risk": "low", "wind_zone": "z2_medium",
        "seismic_zone": "zone_1", "access_road": "gravel",
        "water_availability": "borehole", "grid_distance_km": 3.2,
        "substation_distance_km": 5.8, "hv_line_kv": 33,
    })
    proj["facility_config"] = json.dumps({
        "buildings": ["control_room", "om_building", "security_gate",
                      "battery_room", "transformer_bldg"],
        "external_works": ["pv_field", "mounting", "internal_roads",
                           "cable_trench", "fence", "security_light",
                           "gate", "weather_station"],
    })
    proj["technology_config"] = json.dumps({
        "selected": ["scada", "ems", "ppc", "weather", "string_mon",
                     "energy_meter", "bms", "remote_mon", "cyber",
                     "firewall", "fibre", "gps_sync", "cmms", "spares"],
    })
    proj["electrical_config"] = json.dumps({
        "selected": ["internal_installation", "hv_distribution",
                     "lv_distribution", "dc_collection", "ac_collection",
                     "inverters", "transformers", "rmu", "hv_switchgear",
                     "lv_switchgear", "earthing", "lightning_protection",
                     "fire_alarm", "ip_cctv", "access_control", "lan", "scada"],
    })
    # Finance computed once so it displays consistently every visit.
    fin_computed = finance_utility(
        kwp=20000, annual_gen_mwh=sizing["annual_gen_mwh"],
        tariff_local_per_kwh=1.5, fx_local_per_usd=12.0,
        project_life_yr=25, discount_rate=0.10, debt_ratio=0.70,
        debt_rate=0.10, debt_tenor_yr=12, tax_rate=0.25,
        tariff_escalation=0.02, opex_escalation=0.03,
        degradation_pct=0.5, bess_capex_usd=6_000_000,
        carbon_credit_usd_per_tco2=5.0, grid_ef_kgco2_per_kwh=0.45,
        monte_carlo_runs=200,
    )
    proj["finance_config"] = json.dumps({
        "revenue_model": "ppa", "tariff_local_per_kwh": 1.5,
        "fx_local_per_usd": 12.0, "computed": fin_computed,
    })
    proj["regulatory_config"] = ""
    return proj


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------

def register_capital_investment(app, *, get_db, login_required, csrf_protect,
                                current_user):
    """Register /large-scale-solar/* routes on the Flask app.

    The four dependencies are passed in explicitly to avoid a hard import
    dependency on web_app (which would create a circular import).

    - get_db          : contextmanager returning a DB connection
    - login_required  : decorator that enforces session['user_id']
    - csrf_protect    : callable, aborts 400 on bad _csrf field
    - current_user    : callable returning the logged-in user row or None
    """

    # ------------------------------------------------------------------
    # Tier gate helper - closes over current_user + session so we can
    # keep individual route handlers a single-line check.
    # ------------------------------------------------------------------
    def _gate(min_level: int):
        """Return None if the current user's tier is >= min_level, else a
        Flask redirect response to the upsell page. Store the incoming
        path so /upgrade can explain what was locked."""
        user = current_user()
        level = _ci_level_of(user)
        if level >= min_level:
            return None
        session["ci_upsell_from"] = request.path
        session["ci_upsell_min_level"] = min_level
        return redirect(url_for("capital_investment_upgrade"))

    # ------------------------------------------------------------------
    # GET /large-scale-solar - landing / marketing / start CTA
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar", endpoint="capital_investment_landing")
    def _landing():
        _ensure_capital_investment_schema(get_db)
        # Eager-create sibling tables so any wizard hop that INSERTs into
        # them doesn't 500 with 'relation does not exist' on live PG. The
        # helpers are cheap + idempotent + per-statement transactional.
        try: _ensure_opportunities_schema(get_db)
        except Exception: pass
        try: _ensure_agent_runs_schema(get_db)
        except Exception: pass
        recent = []
        user = current_user()
        tier = _ci_tier_of(user)
        tier_level = _ci_level_of(user)
        uid = session.get("user_id")
        try:
            from flask import current_app
            current_app.logger.info(
                "capital_investment _landing: uid=%s tier=%s level=%s",
                uid, tier, tier_level,
            )
        except Exception:
            pass
        if uid and tier_level >= CI_LEVEL_SETUP:
            try:
                with get_db() as c:
                    rows = c.execute(
                        "SELECT id, project_name, client_name, project_type, "
                        "project_status, currency, target_kwp, updated_at "
                        "FROM capital_investment_projects "
                        "WHERE user_id=? "
                        "ORDER BY updated_at DESC, id DESC LIMIT 6",
                        (uid,),
                    ).fetchall()
                    recent = [dict(r) for r in rows] if rows else []
            except Exception:
                recent = []
        return render_template(
            "capital_investment_landing.html",
            user=user,
            tier=tier,
            tier_level=tier_level,
            tier_label=CI_TIER_LABEL.get(tier, "Free"),
            recent=recent,
            project_types=PROJECT_TYPES,
        )

    # ------------------------------------------------------------------
    # GET /large-scale-solar/demo - read-only Ghana 20 MW showcase.
    # Available to Starter+ (or anon-with-hint on the landing page).
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/demo",
               endpoint="capital_investment_demo")
    def _demo():
        # Anon can see the demo (Starter-level content). We block only
        # logged-in FREE users from wasting a slot in the funnel - anon
        # still gets full read-only demo access as a marketing pull.
        user = current_user()
        if user and _ci_level_of(user) < CI_LEVEL_DEMO:
            session["ci_upsell_from"] = request.path
            session["ci_upsell_min_level"] = CI_LEVEL_DEMO
            return redirect(url_for("capital_investment_upgrade"))
        proj = _demo_project()
        pv_cfg = json.loads(proj["pv_config"])
        fin_cfg = json.loads(proj["finance_config"])
        return render_template(
            "capital_investment_demo.html",
            user=user,
            proj=proj,
            sizing=pv_cfg.get("sizing") or {},
            computed=fin_cfg.get("computed") or {},
            tier=_ci_tier_of(user),
            tier_level=_ci_level_of(user),
        )

    # ------------------------------------------------------------------
    # GET /large-scale-solar/upgrade - upsell page explaining why the
    # module is Enterprise-gated + CTA to the existing /upgrade route.
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/upgrade",
               endpoint="capital_investment_upgrade")
    def _upgrade():
        user = current_user()
        tier = _ci_tier_of(user)
        tier_level = _ci_level_of(user)
        upsell_from = session.pop("ci_upsell_from", None)
        upsell_min_level = session.pop("ci_upsell_min_level", CI_LEVEL_SETUP)
        return render_template(
            "capital_investment_upgrade.html",
            user=user,
            tier=tier,
            tier_level=tier_level,
            tier_label=CI_TIER_LABEL.get(tier, "Free"),
            upsell_from=upsell_from,
            upsell_min_level=upsell_min_level,
        )

    # ------------------------------------------------------------------
    # GET / POST /large-scale-solar/new - Step 1 Project Registration
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/new", methods=["GET", "POST"],
               endpoint="capital_investment_new")
    @login_required
    def _new():
        try:
            from flask import current_app
            _u = current_user()
            current_app.logger.info(
                "capital_investment _new: entry method=%s uid=%s tier=%s level=%s",
                request.method, session.get("user_id"),
                _ci_tier_of(_u), _ci_level_of(_u),
            )
        except Exception:
            pass
        if (g := _gate(CI_LEVEL_SETUP)) is not None:
            try:
                from flask import current_app
                current_app.logger.info(
                    "capital_investment _new: tier gate redirect to /upgrade uid=%s",
                    session.get("user_id"),
                )
            except Exception:
                pass
            return g
        _ensure_capital_investment_schema(get_db)
        # Eager-create sibling tables so Step 11 (CRM) / Step 14 (Agents)
        # routes never 500 on missing table on this user's live backend.
        try: _ensure_opportunities_schema(get_db)
        except Exception: pass
        try: _ensure_agent_runs_schema(get_db)
        except Exception: pass
        uid = session["user_id"]

        if request.method == "POST":
            csrf_protect()
            f = request.form
            name = (f.get("project_name") or "").strip()[:300]
            if not name:
                flash("Project name is required.", "warning")
                return redirect(url_for("capital_investment_new"))

            client   = (f.get("client_name")     or "").strip()[:300]
            investor = (f.get("investor")        or "").strip()[:300]
            dev      = (f.get("developer")       or "").strip()[:300]
            country  = (f.get("country")         or "Ghana").strip()[:100]
            region   = (f.get("region")          or "").strip()[:100]
            district = (f.get("district")        or "").strip()[:100]

            def _flt(v):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None

            lat = _flt(f.get("gps_lat"))
            lon = _flt(f.get("gps_lon"))

            desc     = (f.get("description")     or "").strip()[:4000]
            status   = (f.get("project_status")  or "concept").strip()
            if status not in PROJECT_STATUS_CODES:
                status = "concept"
            target_cod = (f.get("target_cod")    or "").strip()[:32]
            # Target capacity - the ONE headline design input. Entered here
            # in MWp for ergonomics; converted to kWp for storage / passing
            # into the PV engine on Step 7.
            target_mwp = _flt(f.get("target_mwp"))
            target_kwp_val: float | None = None
            if target_mwp is not None and target_mwp > 0:
                target_kwp_val = round(target_mwp * 1000.0, 2)
            standard   = (f.get("design_standard") or "IEC").strip()
            if standard not in DESIGN_STANDARD_CODES:
                standard = "IEC"
            currency   = (f.get("currency")      or "GHS").strip().upper()
            if currency not in CURRENCY_CODES:
                currency = "GHS"
            tax        = (f.get("tax_regime")    or "standard").strip()
            if tax not in TAX_REGIME_CODES:
                tax = "standard"
            ptype      = (f.get("project_type")  or "").strip()
            if ptype and ptype not in PROJECT_TYPE_CODES:
                ptype = ""

            # INSERT ... RETURNING id: portable across SQLite 3.35+ and
            # Postgres. Bypasses the lastrowid / SELECT lastval() edge
            # cases that made the previous defensive path silently
            # redirect the user back to /new with a 'please retry'
            # warning even after a successful INSERT.
            pid = 0
            insert_error = None
            try:
                with get_db() as c:
                    cur = c.execute(
                        "INSERT INTO capital_investment_projects ("
                        "user_id, project_name, client_name, investor, developer, "
                        "country, region, district, gps_lat, gps_lon, description, "
                        "project_status, target_cod, target_kwp, design_standard, "
                        "currency, tax_regime, project_type"
                        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                        "RETURNING id",
                        (uid, name, client, investor, dev,
                         country, region, district, lat, lon, desc,
                         status, target_cod, target_kwp_val, standard,
                         currency, tax, ptype),
                    )
                    row = cur.fetchone()
                    pid = int(row[0]) if row else 0
            except Exception as e:
                insert_error = str(e)
                try:
                    with get_db() as c:
                        cur = c.execute(
                            "INSERT INTO capital_investment_projects ("
                            "user_id, project_name, client_name, investor, developer, "
                            "country, region, district, gps_lat, gps_lon, description, "
                            "project_status, target_cod, design_standard, "
                            "currency, tax_regime, project_type"
                            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                            "RETURNING id",
                            (uid, name, client, investor, dev,
                             country, region, district, lat, lon, desc,
                             status, target_cod, standard,
                             currency, tax, ptype),
                        )
                        row = cur.fetchone()
                        pid = int(row[0]) if row else 0
                    # Follow-up UPDATE for target_kwp - the column MAY
                    # exist even when the wide INSERT failed for another
                    # reason; try once and swallow if it doesn't.
                    if pid and target_kwp_val is not None:
                        try:
                            with get_db() as c:
                                c.execute(
                                    "UPDATE capital_investment_projects "
                                    "SET target_kwp=? WHERE id=?",
                                    (target_kwp_val, pid),
                                )
                        except Exception:
                            pass
                except Exception as e2:
                    try:
                        from flask import current_app
                        current_app.logger.error(
                            "capital_investment _new: both INSERT paths failed "
                            "wide_err=%r narrow_err=%r uid=%s",
                            insert_error, str(e2), uid,
                        )
                    except Exception:
                        pass
                    flash(f"Could not create the project: {e2}. "
                          "Try again in a moment; if this persists, "
                          "contact support.", "danger")
                    return redirect(url_for("capital_investment_new"))
            if pid <= 0:
                flash(f"Project creation returned an unexpected ID. "
                      f"({insert_error or 'unknown error'}) "
                      "Please retry.", "warning")
                return redirect(url_for("capital_investment_new"))
            flash("Capital investment project created. Continue with Step 2.", "success")
            return redirect(url_for("capital_investment_project", pid=pid))

        # GET
        return render_template(
            "capital_investment_step1_registration.html",
            user=current_user(),
            project_types=PROJECT_TYPES,
            project_statuses=PROJECT_STATUSES,
            design_standards=DESIGN_STANDARDS,
            currencies=CURRENCIES,
            tax_regimes=TAX_REGIMES,
        )

    # ------------------------------------------------------------------
    # GET /large-scale-solar/<pid> - project overview (wizard state)
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/<int:pid>",
               endpoint="capital_investment_project")
    @login_required
    def _project(pid: int):
        if (g := _gate(CI_LEVEL_SETUP)) is not None: return g
        _ensure_capital_investment_schema(get_db)
        uid = session["user_id"]
        with get_db() as c:
            row = c.execute(
                "SELECT * FROM capital_investment_projects "
                "WHERE id=? AND user_id=?",
                (pid, uid),
            ).fetchone()
        if not row:
            abort(404)
        proj: dict[str, Any] = dict(row)
        # Compute wizard progress from which JSON blobs are populated.
        progress: list[dict[str, Any]] = _wizard_progress(proj)
        return render_template(
            "capital_investment_project.html",
            user=current_user(),
            proj=proj,
            progress=progress,
            project_types=PROJECT_TYPES,
            project_statuses=PROJECT_STATUSES,
            design_standards=DESIGN_STANDARDS,
            currencies=CURRENCIES,
            tax_regimes=TAX_REGIMES,
        )

    # ------------------------------------------------------------------
    # helper: load-and-authorize
    # ------------------------------------------------------------------
    def _load_project(pid: int) -> dict[str, Any]:
        _ensure_capital_investment_schema(get_db)
        uid = session["user_id"]
        with get_db() as c:
            row = c.execute(
                "SELECT * FROM capital_investment_projects "
                "WHERE id=? AND user_id=?",
                (pid, uid),
            ).fetchone()
        if not row:
            abort(404)
        return dict(row)

    def _save_project_field(pid: int, field: str, value: str) -> None:
        uid = session["user_id"]
        with get_db() as c:
            c.execute(
                f"UPDATE capital_investment_projects "
                f"SET {field}=?, updated_at=CURRENT_TIMESTAMP "
                f"WHERE id=? AND user_id=?",
                (value, pid, uid),
            )

    # ------------------------------------------------------------------
    # DIAG - who am I? Any logged-in user. Reveals the state that drives
    # the tier gate on /large-scale-solar/new. Use to reproduce hiccups.
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/diag/whoami",
               endpoint="capital_investment_diag_whoami")
    @login_required
    def _diag_whoami():
        user = current_user()
        out: dict[str, Any] = {
            "session_user_id":  session.get("user_id"),
            "session_username": session.get("username"),
            "current_user_row": None,
            "user_tier":        _ci_tier_of(user),
            "user_level":       _ci_level_of(user),
            "tier_labels":      CI_TIER_LABEL,
            "level_thresholds": {
                "CI_LEVEL_MARKETING": CI_LEVEL_MARKETING,
                "CI_LEVEL_DEMO":      CI_LEVEL_DEMO,
                "CI_LEVEL_SETUP":     CI_LEVEL_SETUP,
                "CI_LEVEL_FULL":      CI_LEVEL_FULL,
            },
            "tier_gate_new":       _ci_level_of(user) >= CI_LEVEL_SETUP,
            "tier_gate_full":      _ci_level_of(user) >= CI_LEVEL_FULL,
        }
        if user is not None:
            keys = ("id", "username", "email", "is_admin", "plan", "role")
            row_dict: dict[str, Any] = {}
            for k in keys:
                row_dict[k] = _row_get(user, k, None)
            out["current_user_row"] = row_dict
        return jsonify(out)

    # ------------------------------------------------------------------
    # DIAG - inspect live schema state (admin-only)
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/diag/schema",
               endpoint="capital_investment_diag_schema")
    @login_required
    def _diag_schema():
        user = current_user()
        # Admin OR enterprise only.
        if _ci_level_of(user) < CI_LEVEL_FULL:
            abort(404)
        _ensure_capital_investment_schema(get_db)
        _ensure_opportunities_schema(get_db)
        out: dict[str, Any] = {"backend": "unknown", "tables": {}}
        # Try SQLite pragma first (fast).
        try:
            with get_db() as c:
                rows = c.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name IN ("
                    "'capital_investment_projects', "
                    "'capital_investment_opportunities')",
                ).fetchall()
                if rows is not None:
                    out["backend"] = "sqlite"
                    for r in rows:
                        t = r[0] if not hasattr(r, "keys") else r["name"]
                        cols = c.execute(f"PRAGMA table_info({t})").fetchall()
                        out["tables"][t] = [
                            {"name": (col[1] if not hasattr(col, "keys") else col["name"]),
                             "type": (col[2] if not hasattr(col, "keys") else col["type"])}
                            for col in cols
                        ]
                        rc = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
                        out.setdefault("counts", {})[t] = (rc[0] if rc else 0)
        except Exception as e:
            out["sqlite_err"] = str(e)
        # If SQLite pragma yielded nothing, try Postgres.
        if not out["tables"]:
            try:
                with get_db() as c:
                    rows = c.execute(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema='public' AND table_name IN ("
                        "'capital_investment_projects', "
                        "'capital_investment_opportunities')",
                    ).fetchall()
                    if rows:
                        out["backend"] = "postgres"
                    for r in rows or []:
                        t = r[0] if not hasattr(r, "keys") else r["table_name"]
                        cols = c.execute(
                            "SELECT column_name, data_type FROM "
                            "information_schema.columns "
                            "WHERE table_schema='public' AND table_name=? "
                            "ORDER BY ordinal_position",
                            (t,),
                        ).fetchall()
                        out["tables"][t] = [
                            {"name": (col[0] if not hasattr(col, "keys") else col["column_name"]),
                             "type": (col[1] if not hasattr(col, "keys") else col["data_type"])}
                            for col in cols
                        ]
                        rc = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
                        out.setdefault("counts", {})[t] = (rc[0] if rc else 0)
            except Exception as e:
                out["postgres_err"] = str(e)
        # Highlight the target_kwp presence (the key symptom of the hiccup).
        cip = out["tables"].get("capital_investment_projects") or []
        out["has_target_kwp"] = any(c["name"] == "target_kwp" for c in cip)
        out["user_tier"] = _ci_tier_of(user)
        out["user_level"] = _ci_level_of(user)
        return jsonify(out)

    # ------------------------------------------------------------------
    # STEP 2 - Project Type
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/<int:pid>/step2",
               methods=["GET", "POST"],
               endpoint="capital_investment_step2")
    @login_required
    def _step2(pid: int):
        if (g := _gate(CI_LEVEL_SETUP)) is not None: return g
        proj = _load_project(pid)
        if request.method == "POST":
            csrf_protect()
            ptype = (request.form.get("project_type") or "").strip()
            if ptype not in PROJECT_TYPE_CODES:
                flash("Choose a project type.", "warning")
                return redirect(url_for("capital_investment_step2", pid=pid))
            _save_project_field(pid, "project_type", ptype)
            flash("Project type saved. Continue with Step 3.", "success")
            return redirect(url_for("capital_investment_step3", pid=pid))
        return render_template(
            "capital_investment_step2_type.html",
            user=current_user(),
            proj=proj,
            project_types=PROJECT_TYPES,
        )

    # ------------------------------------------------------------------
    # STEP 3 - Site Configuration
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/<int:pid>/step3",
               methods=["GET", "POST"],
               endpoint="capital_investment_step3")
    @login_required
    def _step3(pid: int):
        if (g := _gate(CI_LEVEL_SETUP)) is not None: return g
        proj = _load_project(pid)
        site_cfg = _safe_json(proj.get("site_config"))
        if request.method == "POST":
            csrf_protect()
            f = request.form

            def _num(key: str) -> float | None:
                try:
                    v = f.get(key)
                    return float(v) if v not in (None, "") else None
                except ValueError:
                    return None

            new_cfg = {
                "land_area_ha":        _num("land_area_ha"),
                "roof_area_m2":        _num("roof_area_m2"),
                "terrain":             _pick(f, "terrain",       SITE_TERRAINS),
                "slope":               _pick(f, "slope",         SITE_SLOPES),
                "soil":                _pick(f, "soil",          SITE_SOILS),
                "flood_risk":          _pick(f, "flood_risk",    SITE_FLOOD_RISKS),
                "wind_zone":           _pick(f, "wind_zone",     SITE_WIND_ZONES),
                "seismic_zone":        _pick(f, "seismic_zone",  SITE_SEISMIC_ZONES),
                "access_road":         _pick(f, "access_road",   SITE_ACCESS),
                "water_availability":  _pick(f, "water",         SITE_WATER),
                "grid_distance_km":    _num("grid_distance_km"),
                "substation_distance_km": _num("substation_distance_km"),
                "hv_line_kv":          _num("hv_line_kv"),
                "environmental_constraints":
                    (f.get("environmental_constraints") or "").strip()[:2000],
                "protected_areas":
                    (f.get("protected_areas") or "").strip()[:1000],
                "existing_buildings":
                    (f.get("existing_buildings") or "").strip()[:1000],
                "future_expansion_area_ha": _num("future_expansion_area_ha"),
                "shading_assessment":
                    (f.get("shading_assessment") or "").strip()[:1000],
                "drone_survey_url":
                    (f.get("drone_survey_url") or "").strip()[:500],
                "gis_data_url":
                    (f.get("gis_data_url") or "").strip()[:500],
                "satellite_image_url":
                    (f.get("satellite_image_url") or "").strip()[:500],
            }
            _save_project_field(pid, "site_config", json.dumps(new_cfg))
            flash("Site configuration saved. Continue with Step 4.", "success")
            return redirect(url_for("capital_investment_step4", pid=pid))

        return render_template(
            "capital_investment_step3_site.html",
            user=current_user(),
            proj=proj,
            cfg=site_cfg,
            terrains=SITE_TERRAINS,
            slopes=SITE_SLOPES,
            soils=SITE_SOILS,
            flood_risks=SITE_FLOOD_RISKS,
            wind_zones=SITE_WIND_ZONES,
            seismic_zones=SITE_SEISMIC_ZONES,
            access_options=SITE_ACCESS,
            water_options=SITE_WATER,
        )

    # ------------------------------------------------------------------
    # STEP 4 - Facility Configuration
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/<int:pid>/step4",
               methods=["GET", "POST"],
               endpoint="capital_investment_step4")
    @login_required
    def _step4(pid: int):
        if (g := _gate(CI_LEVEL_SETUP)) is not None: return g
        proj = _load_project(pid)
        fac_cfg = _safe_json(proj.get("facility_config"))
        if request.method == "POST":
            csrf_protect()
            f = request.form
            selected_buildings = [
                b for b in (f.getlist("buildings") or []) if b in BUILDING_CODES
            ]
            selected_external = [
                x for x in (f.getlist("external_works") or [])
                if x in EXTERNAL_WORKS_CODES
            ]
            # Per-building notes captured as building_notes__<code>
            per_building_notes: dict[str, str] = {}
            for b in selected_buildings:
                key = f"building_notes__{b}"
                v = (f.get(key) or "").strip()[:800]
                if v:
                    per_building_notes[b] = v
            new_cfg = {
                "buildings":       selected_buildings,
                "external_works":  selected_external,
                "building_notes":  per_building_notes,
                "generic_notes":   (f.get("facility_notes") or "").strip()[:2000],
            }
            _save_project_field(pid, "facility_config", json.dumps(new_cfg))
            flash("Facility configuration saved. Continue with Step 5.", "success")
            return redirect(url_for("capital_investment_step5", pid=pid))

        return render_template(
            "capital_investment_step4_facility.html",
            user=current_user(),
            proj=proj,
            cfg=fac_cfg,
            building_types=BUILDING_TYPES,
            building_sub_items=BUILDING_SUB_ITEMS,
            external_works=EXTERNAL_WORKS,
        )

    # ------------------------------------------------------------------
    # STEP 5 - Technology Configuration
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/<int:pid>/step5",
               methods=["GET", "POST"],
               endpoint="capital_investment_step5")
    @login_required
    def _step5(pid: int):
        if (g := _gate(CI_LEVEL_SETUP)) is not None: return g
        proj = _load_project(pid)
        tech_cfg = _safe_json(proj.get("technology_config"))
        if request.method == "POST":
            csrf_protect()
            selected = [
                t for t in (request.form.getlist("technology") or [])
                if t in TECHNOLOGY_CODES
            ]
            notes = (request.form.get("tech_notes") or "").strip()[:2000]
            _save_project_field(pid, "technology_config",
                                json.dumps({"selected": selected,
                                            "notes": notes}))
            flash("Technology stack saved. Continue with Step 6.", "success")
            return redirect(url_for("capital_investment_step6", pid=pid))
        return render_template(
            "capital_investment_step5_technology.html",
            user=current_user(),
            proj=proj,
            cfg=tech_cfg,
            technology_groups=TECHNOLOGY_GROUPS,
        )

    # ------------------------------------------------------------------
    # STEP 6 - Electrical System Configuration
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/<int:pid>/step6",
               methods=["GET", "POST"],
               endpoint="capital_investment_step6")
    @login_required
    def _step6(pid: int):
        if (g := _gate(CI_LEVEL_SETUP)) is not None: return g
        proj = _load_project(pid)
        elec_cfg = _safe_json(proj.get("electrical_config"))
        if request.method == "POST":
            csrf_protect()
            selected = [
                s for s in (request.form.getlist("services") or [])
                if s in ELECTRICAL_SERVICE_CODES
            ]
            notes = (request.form.get("elec_notes") or "").strip()[:2000]
            _save_project_field(
                pid, "electrical_config",
                json.dumps({"selected": selected, "notes": notes}),
            )
            flash("Electrical scope saved. Continue with Step 7.", "success")
            return redirect(url_for("capital_investment_step7", pid=pid))
        return render_template(
            "capital_investment_step6_electrical.html",
            user=current_user(),
            proj=proj,
            cfg=elec_cfg,
            electrical_services=ELECTRICAL_SERVICES,
        )

    # ------------------------------------------------------------------
    # STEP 7 - PV Design
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/<int:pid>/step7",
               methods=["GET", "POST"],
               endpoint="capital_investment_step7")
    @login_required
    def _step7(pid: int):
        if (g := _gate(CI_LEVEL_SETUP)) is not None: return g
        proj = _load_project(pid)
        pv_cfg = _safe_json(proj.get("pv_config"))
        sizing: dict[str, Any] = {}

        if request.method == "POST":
            csrf_protect()
            f = request.form

            def _n(k, d=0.0):
                try:
                    v = f.get(k)
                    return float(v) if v not in (None, "") else float(d)
                except ValueError:
                    return float(d)

            module_tech = (f.get("module_tech") or "mono_topcon").strip()
            valid_tech = {c for c, _, _ in PV_MODULE_TECHS}
            if module_tech not in valid_tech:
                module_tech = "mono_topcon"

            mounting = (f.get("mounting") or "fixed_tilt").strip()
            valid_mount = {c for c, _ in PV_MOUNTING_TYPES}
            if mounting not in valid_mount:
                mounting = "fixed_tilt"

            inv_type = (f.get("inverter_type") or "central").strip()
            valid_inv = {c for c, _ in PV_INVERTER_TYPES}
            if inv_type not in valid_inv:
                inv_type = "central"

            batt_chem = (f.get("battery_chem") or "none").strip()
            valid_batt = {c for c, _ in PV_BATTERY_CHEMISTRIES}
            if batt_chem not in valid_batt:
                batt_chem = "none"

            kwp = _n("kwp", 0)
            module_wp = _n("module_wp", 550)
            dc_ac_ratio = _n("dc_ac_ratio", 1.20)
            tilt_deg = _n("tilt_deg", 10)
            azimuth_deg = _n("azimuth_deg", 180)
            psh_daily = _n("psh_daily", 5.4)
            performance_ratio = _n("performance_ratio", 0.78)
            availability_pct = _n("availability_pct", 98)
            annual_degradation_pct = _n("annual_degradation_pct", 0.5)
            project_life_yr = int(_n("project_life_yr", 25))
            battery_mwh = _n("battery_mwh", 0)

            central_inverter_kw = 1500.0 if inv_type == "central" else 250.0

            sizing = size_utility_pv(
                kwp=kwp,
                module_wp=module_wp,
                dc_ac_ratio=dc_ac_ratio,
                tilt_deg=tilt_deg,
                azimuth_deg=azimuth_deg,
                psh_daily=psh_daily,
                performance_ratio=performance_ratio,
                availability_pct=availability_pct,
                annual_degradation_pct=annual_degradation_pct,
                project_life_yr=project_life_yr,
                central_inverter_kw=central_inverter_kw,
            )

            saved = {
                "module_tech":              module_tech,
                "mounting":                 mounting,
                "inverter_type":            inv_type,
                "battery_chem":             batt_chem,
                "battery_mwh":              battery_mwh,
                "kwp":                      kwp,
                "module_wp":                module_wp,
                "dc_ac_ratio":              dc_ac_ratio,
                "tilt_deg":                 tilt_deg,
                "azimuth_deg":              azimuth_deg,
                "psh_daily":                psh_daily,
                "performance_ratio":        performance_ratio,
                "availability_pct":         availability_pct,
                "annual_degradation_pct":   annual_degradation_pct,
                "project_life_yr":          project_life_yr,
                "sizing":                   sizing,
                "notes":                    (f.get("pv_notes") or "").strip()[:2000],
            }
            _save_project_field(pid, "pv_config", json.dumps(saved))

            if f.get("recompute_only"):
                # Stay on Step 7 to iterate on inputs
                pv_cfg = saved
                return render_template(
                    "capital_investment_step7_pv.html",
                    user=current_user(),
                    proj=proj,
                    cfg=pv_cfg,
                    sizing=sizing,
                    module_techs=PV_MODULE_TECHS,
                    mounting_types=PV_MOUNTING_TYPES,
                    inverter_types=PV_INVERTER_TYPES,
                    battery_chemistries=PV_BATTERY_CHEMISTRIES,
                )
            flash("PV design saved. Continue with Step 8.", "success")
            return redirect(url_for("capital_investment_step8", pid=pid))

        # GET
        return render_template(
            "capital_investment_step7_pv.html",
            user=current_user(),
            proj=proj,
            cfg=pv_cfg,
            sizing=pv_cfg.get("sizing") or {},
            module_techs=PV_MODULE_TECHS,
            mounting_types=PV_MOUNTING_TYPES,
            inverter_types=PV_INVERTER_TYPES,
            battery_chemistries=PV_BATTERY_CHEMISTRIES,
        )

    # ------------------------------------------------------------------
    # STEP 8 - Financial Engineering
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/<int:pid>/step8",
               methods=["GET", "POST"],
               endpoint="capital_investment_step8")
    @login_required
    def _step8(pid: int):
        if (g := _gate(CI_LEVEL_FULL)) is not None: return g
        proj = _load_project(pid)
        fin_cfg = _safe_json(proj.get("finance_config"))
        pv_cfg = _safe_json(proj.get("pv_config"))
        sizing = pv_cfg.get("sizing") or {}
        kwp = float(sizing.get("kwp_input") or pv_cfg.get("kwp") or 0)
        annual_gen_mwh = float(sizing.get("annual_gen_mwh") or 0)

        computed: dict[str, Any] = {}
        if request.method == "POST":
            csrf_protect()
            f = request.form

            def _n(k, d=0.0):
                try:
                    v = f.get(k)
                    return float(v) if v not in (None, "") else float(d)
                except ValueError:
                    return float(d)

            # Read CAPEX / OPEX from form (fallback to defaults).
            capex_form: dict[str, float] = {}
            for k in DEFAULT_CAPEX_USD_PER_KWP:
                capex_form[k] = _n(f"capex_{k}", DEFAULT_CAPEX_USD_PER_KWP[k])
            opex_form: dict[str, float] = {}
            for k in DEFAULT_OPEX_USD_PER_KWP_YR:
                opex_form[k] = _n(f"opex_{k}", DEFAULT_OPEX_USD_PER_KWP_YR[k])

            tariff = _n("tariff_local_per_kwh", 1.5)   # GHS/kWh default
            fx = _n("fx_local_per_usd", 12.0)
            revenue_model = (f.get("revenue_model") or "ppa").strip()
            if revenue_model not in {c for c, _ in REVENUE_MODELS}:
                revenue_model = "ppa"
            project_life = int(_n("project_life_yr", 25))
            discount = _n("discount_rate_pct", 10) / 100.0
            debt_ratio = _n("debt_ratio_pct", 70) / 100.0
            debt_rate = _n("debt_rate_pct", 10) / 100.0
            debt_tenor = int(_n("debt_tenor_yr", 12))
            tax_rate = _n("tax_rate_pct", 25) / 100.0
            tariff_esc = _n("tariff_escalation_pct", 2) / 100.0
            opex_esc = _n("opex_escalation_pct", 3) / 100.0
            degrad = _n("annual_degradation_pct",
                        pv_cfg.get("annual_degradation_pct", 0.5))
            bess_capex = _n("bess_capex_usd", 0)
            carbon_price = _n("carbon_credit_usd_per_tco2", 5.0)
            grid_ef = _n("grid_ef_kgco2_per_kwh", 0.45)
            mc_runs = int(_n("monte_carlo_runs", 200))

            if kwp <= 0 or annual_gen_mwh <= 0:
                flash("PV kWp and annual generation must be set on Step 7 "
                      "before finance can be computed.", "warning")
                return redirect(url_for("capital_investment_step7", pid=pid))

            computed = finance_utility(
                kwp=kwp,
                annual_gen_mwh=annual_gen_mwh,
                tariff_local_per_kwh=tariff,
                fx_local_per_usd=fx,
                capex_usd_per_kwp=capex_form,
                opex_usd_per_kwp_yr=opex_form,
                project_life_yr=project_life,
                discount_rate=discount,
                debt_ratio=debt_ratio,
                debt_rate=debt_rate,
                debt_tenor_yr=debt_tenor,
                tax_rate=tax_rate,
                tariff_escalation=tariff_esc,
                opex_escalation=opex_esc,
                degradation_pct=degrad,
                bess_capex_usd=bess_capex,
                carbon_credit_usd_per_tco2=carbon_price,
                grid_ef_kgco2_per_kwh=grid_ef,
                monte_carlo_runs=mc_runs,
            )

            saved = {
                "capex_usd_per_kwp":       capex_form,
                "opex_usd_per_kwp_yr":     opex_form,
                "tariff_local_per_kwh":    tariff,
                "fx_local_per_usd":        fx,
                "revenue_model":           revenue_model,
                "project_life_yr":         project_life,
                "discount_rate_pct":       discount * 100,
                "debt_ratio_pct":          debt_ratio * 100,
                "debt_rate_pct":           debt_rate * 100,
                "debt_tenor_yr":           debt_tenor,
                "tax_rate_pct":            tax_rate * 100,
                "tariff_escalation_pct":   tariff_esc * 100,
                "opex_escalation_pct":     opex_esc * 100,
                "annual_degradation_pct":  degrad,
                "bess_capex_usd":          bess_capex,
                "carbon_credit_usd_per_tco2": carbon_price,
                "grid_ef_kgco2_per_kwh":   grid_ef,
                "monte_carlo_runs":        mc_runs,
                "computed":                computed,
                "notes":                   (f.get("fin_notes") or "").strip()[:2000],
            }
            _save_project_field(pid, "finance_config", json.dumps(saved))

            if f.get("recompute_only"):
                fin_cfg = saved
                return render_template(
                    "capital_investment_step8_finance.html",
                    user=current_user(),
                    proj=proj,
                    pv_cfg=pv_cfg,
                    cfg=fin_cfg,
                    computed=computed,
                    default_capex=DEFAULT_CAPEX_USD_PER_KWP,
                    default_opex=DEFAULT_OPEX_USD_PER_KWP_YR,
                    revenue_models=REVENUE_MODELS,
                    kwp=kwp,
                    annual_gen_mwh=annual_gen_mwh,
                )
            flash("Financial model saved. Continue with Step 9.", "success")
            return redirect(url_for("capital_investment_step9", pid=pid))

        # GET
        return render_template(
            "capital_investment_step8_finance.html",
            user=current_user(),
            proj=proj,
            pv_cfg=pv_cfg,
            cfg=fin_cfg,
            computed=fin_cfg.get("computed") or {},
            default_capex=DEFAULT_CAPEX_USD_PER_KWP,
            default_opex=DEFAULT_OPEX_USD_PER_KWP_YR,
            revenue_models=REVENUE_MODELS,
            kwp=kwp,
            annual_gen_mwh=annual_gen_mwh,
        )

    # ------------------------------------------------------------------
    # STEP 9 - BOQ (auto-create linked boq_projects row + boq_buildings
    # for every enabled facility). REUSES the existing BOQ engine - this
    # module does NOT ship its own BOQ implementation.
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/<int:pid>/step9",
               methods=["GET", "POST"],
               endpoint="capital_investment_step9")
    @login_required
    def _step9(pid: int):
        if (g := _gate(CI_LEVEL_FULL)) is not None: return g
        proj = _load_project(pid)
        uid = session["user_id"]
        fac_cfg = _safe_json(proj.get("facility_config"))
        elec_cfg = _safe_json(proj.get("electrical_config"))
        selected_buildings = fac_cfg.get("buildings") or []
        selected_external  = fac_cfg.get("external_works") or []
        boq_project_id = proj.get("boq_project_id")
        # Enumerate what would be auto-created.
        planned_buildings = [
            {"code": b,
             "label": next((L for c, L, _, _ in BUILDING_TYPES if c == b), b),
             "sub_items": BUILDING_SUB_ITEMS.get(b, [])}
            for b in selected_buildings
        ]

        if request.method == "POST":
            csrf_protect()
            # Idempotency: if already linked, do NOT re-create; jump to view.
            if boq_project_id:
                flash("BOQ project already linked.", "info")
                return redirect(url_for("capital_investment_project", pid=pid))
            if not selected_buildings:
                flash("Enable at least one facility on Step 4 before "
                      "generating the BOQ.", "warning")
                return redirect(url_for("capital_investment_step4", pid=pid))

            # 0. Derive the BOQ service codes this plant needs from the
            #    facility, technology and electrical selections. REUSES the
            #    existing _BOQ_SERVICES codes so the generated BOQ project
            #    loads real Section-by-Section / Build-all sections.
            tech_cfg = _safe_json(proj.get("technology_config"))
            service_codes = _ci_derive_boq_services(fac_cfg, tech_cfg, elec_cfg)
            services_csv = ",".join(service_codes)
            # Tenant context from the canonical BOQ-engine source (JWT), not
            # the user row - matches web_app._boq_tenant_clause reads.
            try:
                from web_app import _kc_current_tenant_id as _kc_tid
                tenant_id = _kc_tid()
            except Exception:
                tenant_id = None

            # Eager + VERIFIED link-table migration. Honour the boolean so a
            # failed live-PG migration is observable, not silently swallowed.
            links_ready = False
            try:
                links_ready = bool(
                    _ensure_capital_investment_boq_links_schema(get_db))
            except Exception:
                links_ready = False

            project_name = (
                f"{proj['project_name']} - Capital Investment BOQ"
            )[:300]
            location = ", ".join(x for x in (proj.get("region"),
                                             proj.get("country")) if x)[:300]
            external_flag = 1 if selected_external else 0
            built_floors: list = []
            link_errors = 0
            new_boq_pid = 0

            # Create + claim + build in ONE transaction. get_db() rolls back on
            # any exception (both SQLite and the psycopg2 adapter), so a lost
            # race or a mid-build failure leaves boq_project_id NULL with no
            # orphan row - and boq_project_id goes straight NULL -> real id
            # (no leaky -1 sentinel that templates would render as "#-1").
            try:
                with get_db() as c:
                    # 1. Linked boq_projects row WITH services_csv + tenant_id.
                    try:
                        cur = c.execute(
                            "INSERT INTO boq_projects "
                            "(user_id, tenant_id, project_name, client_name, "
                            " location, project_type, external_works_included, "
                            " infrastructure_included, services_csv) "
                            "VALUES (?,?,?,?,?,?,?,?,?)",
                            (uid, tenant_id, project_name,
                             proj.get("client_name") or "", location, "campus",
                             external_flag, 1, services_csv),
                        )
                    except Exception:
                        # Older schema without tenant_id / services_csv.
                        cur = c.execute(
                            "INSERT INTO boq_projects "
                            "(user_id, project_name, client_name, location, "
                            " project_type, external_works_included, "
                            " infrastructure_included) "
                            "VALUES (?,?,?,?,?,?,?)",
                            (uid, project_name, proj.get("client_name") or "",
                             location, "campus", external_flag, 1),
                        )
                    new_boq_pid = int(cur.lastrowid or 0)

                    # 2. Atomic claim: set boq_project_id to the REAL id only
                    #    if still unset. rowcount != 1 means a concurrent POST
                    #    won - raise to roll back this orphan boq_projects row.
                    cclaim = c.execute(
                        "UPDATE capital_investment_projects "
                        "SET boq_project_id=? WHERE id=? AND user_id=? AND "
                        "(boq_project_id IS NULL OR boq_project_id=0)",
                        (new_boq_pid, pid, uid),
                    )
                    if int(getattr(cclaim, "rowcount", 0) or 0) != 1:
                        raise _CIGenerationRaceLost()

                    # 3. One boq_buildings + Ground Floor per enabled facility.
                    for b in selected_buildings:
                        label = next(
                            (L for cd, L, _, _ in BUILDING_TYPES if cd == b), b,
                        )
                        b_services = _ci_facility_services(b)
                        bid = 0
                        try:
                            bcur = c.execute(
                                "INSERT INTO boq_buildings "
                                "(project_id, tenant_id, building_name, "
                                " building_code, primary_purpose, "
                                " purpose_subtype, building_area, "
                                " number_of_floors, basement_included, "
                                " roof_level_included, external_area_included) "
                                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                (new_boq_pid, tenant_id, label, b.upper(),
                                 "commercial", b, 0, 1, 0, 1, 0),
                            )
                            bid = int(bcur.lastrowid or 0)
                        except Exception:
                            try:
                                bcur = c.execute(
                                    "INSERT INTO boq_buildings "
                                    "(project_id, building_name, "
                                    " building_code, number_of_floors) "
                                    "VALUES (?,?,?,?)",
                                    (new_boq_pid, label, b.upper(), 1),
                                )
                                bid = int(bcur.lastrowid or 0)
                            except Exception:
                                bid = 0

                        # 4. Ground Floor (standard boq_floors shape).
                        fid = 0
                        if bid:
                            try:
                                fcur = c.execute(
                                    "INSERT INTO boq_floors "
                                    "(building_id, project_id, tenant_id, "
                                    " floor_name, floor_level, floor_type) "
                                    "VALUES (?,?,?,?,?,?)",
                                    (bid, new_boq_pid, tenant_id,
                                     "Ground Floor", 0, "ground"),
                                )
                                fid = int(fcur.lastrowid or 0)
                            except Exception:
                                try:
                                    fcur = c.execute(
                                        "INSERT INTO boq_floors "
                                        "(building_id, project_id, floor_name, "
                                        " floor_level, floor_type) "
                                        "VALUES (?,?,?,?,?)",
                                        (bid, new_boq_pid, "Ground Floor", 0,
                                         "ground"),
                                    )
                                    fid = int(fcur.lastrowid or 0)
                                except Exception:
                                    fid = 0
                        if fid:
                            built_floors.append((bid, fid, list(b_services)))

                        # 5. Traceability link - only when the schema verified;
                        #    count failures so they surface (never swallowed).
                        if links_ready:
                            try:
                                c.execute(
                                    "INSERT INTO capital_investment_boq_links "
                                    "(capital_investment_project_id, user_id, "
                                    " tenant_id, facility_code, source_kind, "
                                    " boq_project_id, boq_building_id, "
                                    " boq_floor_id, service_codes_csv) "
                                    "VALUES (?,?,?,?,?,?,?,?,?)",
                                    (pid, uid, tenant_id, b, "facility",
                                     new_boq_pid, bid or None, fid or None,
                                     ",".join(_ci_order_services(b_services))),
                                )
                            except Exception:
                                link_errors += 1
            except _CIGenerationRaceLost:
                # A concurrent POST won; our orphan boq_projects row was rolled
                # back by get_db()'s exception handler. Nothing to clean up.
                flash("BOQ generation is already in progress or complete for "
                      "this project.", "info")
                return redirect(url_for("capital_investment_project", pid=pid))
            except Exception:
                # Whole transaction rolled back - boq_project_id stays NULL so
                # the user can retry cleanly. Nothing partial is left behind.
                try:
                    from flask import current_app
                    current_app.logger.exception(
                        "capital step9 BOQ creation failed for pid=%s", pid)
                except Exception:
                    pass
                flash("BOQ generation failed - nothing was linked. Please try "
                      "again; the error was logged.", "danger")
                return redirect(url_for("capital_investment_step9", pid=pid))

            # 6. Auto-build the cell-level BOQ line items for every generated
            #    floor, REUSING the standard catalog + boq_rate_v3
            #    (web_app._ci_autobuild_floor_items). Runs AFTER the insert
            #    transaction closes to avoid a nested DB connection. Failures
            #    are logged + surfaced, never silently swallowed.
            items_built = 0
            try:
                from web_app import _ci_autobuild_floor_items as _autobuild
            except Exception:
                _autobuild = None
            if _autobuild:
                for _bid, _fid, _svcs in built_floors:
                    try:
                        items_built += int(
                            _autobuild(_fid, _bid, new_boq_pid, uid, _svcs)
                            or 0)
                    except Exception:
                        try:
                            from flask import current_app
                            current_app.logger.exception(
                                "capital step9 autobuild floor=%s failed", _fid)
                        except Exception:
                            pass

            # boq_project_id was already set atomically in the claim above -
            # no _save_project_field needed (that is what removed the -1 leak).
            notes = []
            if not links_ready or link_errors:
                notes.append("facility links unavailable - see admin diagnostics")
            suffix = (" (" + "; ".join(notes) + ")") if notes else ""
            if service_codes and items_built == 0:
                flash(
                    f"Linked BOQ project #{new_boq_pid} created with "
                    f"{len(selected_buildings)} building(s) and "
                    f"{len(service_codes)} service(s), but line items could "
                    f"NOT be auto-priced - open the BOQ and use Build-all to "
                    f"add them." + suffix,
                    "warning",
                )
            else:
                flash(
                    f"Linked BOQ project #{new_boq_pid} created: "
                    f"{len(selected_buildings)} building(s), "
                    f"{len(service_codes)} service(s), {items_built} priced "
                    f"line item(s) pre-loaded. Open it to review or edit."
                    + suffix,
                    "success",
                )
            return redirect(url_for("capital_investment_project", pid=pid))

        return render_template(
            "capital_investment_step9_boq.html",
            user=current_user(),
            proj=proj,
            planned_buildings=planned_buildings,
            selected_external=selected_external,
            external_works=EXTERNAL_WORKS,
            boq_project_id=boq_project_id,
            electrical_selected=elec_cfg.get("selected") or [],
        )

    # ------------------------------------------------------------------
    # STEP 10 - Marketplace (preview relevant categories + link out)
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/<int:pid>/step10",
               endpoint="capital_investment_step10")
    @login_required
    def _step10(pid: int):
        if (g := _gate(CI_LEVEL_FULL)) is not None: return g
        proj = _load_project(pid)
        tech_cfg = _safe_json(proj.get("technology_config"))
        elec_cfg = _safe_json(proj.get("electrical_config"))
        pv_cfg = _safe_json(proj.get("pv_config"))
        # Marketplace category shortcuts the user should sweep. This is a
        # curated list mapped from the technology + electrical picks - the
        # actual product search happens in the existing /marketplace UI.
        categories = _marketplace_categories_for(pv_cfg, tech_cfg, elec_cfg)
        return render_template(
            "capital_investment_step10_marketplace.html",
            user=current_user(),
            proj=proj,
            categories=categories,
        )

    # ------------------------------------------------------------------
    # STEP 11 - CRM Investment Opportunity (auto-created from project)
    # ------------------------------------------------------------------
    def _load_opportunity(pid: int, uid: int) -> dict[str, Any] | None:
        _ensure_opportunities_schema(get_db)
        with get_db() as c:
            row = c.execute(
                "SELECT * FROM capital_investment_opportunities "
                "WHERE capital_investment_project_id=? AND user_id=? "
                "ORDER BY id DESC LIMIT 1",
                (pid, uid),
            ).fetchone()
        return dict(row) if row else None

    @app.route("/large-scale-solar/<int:pid>/step11",
               methods=["GET", "POST"],
               endpoint="capital_investment_step11")
    @login_required
    def _step11(pid: int):
        if (g := _gate(CI_LEVEL_FULL)) is not None: return g
        proj = _load_project(pid)
        uid = session["user_id"]
        _ensure_opportunities_schema(get_db)
        opp = _load_opportunity(pid, uid)

        if request.method == "POST":
            csrf_protect()
            action = request.form.get("action") or "sync"

            derived = build_opportunity_from_project(proj)
            # Allow overrides for investor / notes only - the numeric side
            # is authoritative from the project's engineering + finance.
            derived["investor"] = (request.form.get("investor")
                                   or derived["investor"])[:300]
            notes = (request.form.get("pipeline_notes") or "").strip()[:2000]

            if opp is None:
                # Create.
                with get_db() as c:
                    cur = c.execute(
                        "INSERT INTO capital_investment_opportunities ("
                        "capital_investment_project_id, user_id, project_name, "
                        "investor, developer, client, location, country, "
                        "currency, capacity_mwp, capex_local, capex_usd, "
                        "revenue_y1_local, annual_gen_mwh, npv_local, "
                        "irr_pct, lcoe_local_per_kwh, payback_years, "
                        "dscr_avg, stage, pipeline_notes"
                        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (derived["capital_investment_project_id"],
                         derived["user_id"], derived["project_name"],
                         derived["investor"], derived["developer"],
                         derived["client"], derived["location"],
                         derived["country"], derived["currency"],
                         derived["capacity_mwp"], derived["capex_local"],
                         derived["capex_usd"], derived["revenue_y1_local"],
                         derived["annual_gen_mwh"], derived["npv_local"],
                         derived["irr_pct"], derived["lcoe_local_per_kwh"],
                         derived["payback_years"], derived["dscr_avg"],
                         "lead", notes),
                    )
                    oid = int(cur.lastrowid or 0)
                flash(f"Investment opportunity #{oid} created and set to "
                      "'Lead' stage.", "success")
            else:
                # Refresh numeric fields; keep stage + history.
                with get_db() as c:
                    c.execute(
                        "UPDATE capital_investment_opportunities SET "
                        "investor=?, developer=?, client=?, location=?, "
                        "country=?, currency=?, capacity_mwp=?, capex_local=?, "
                        "capex_usd=?, revenue_y1_local=?, annual_gen_mwh=?, "
                        "npv_local=?, irr_pct=?, lcoe_local_per_kwh=?, "
                        "payback_years=?, dscr_avg=?, pipeline_notes=?, "
                        "updated_at=CURRENT_TIMESTAMP "
                        "WHERE id=? AND user_id=?",
                        (derived["investor"], derived["developer"],
                         derived["client"], derived["location"],
                         derived["country"], derived["currency"],
                         derived["capacity_mwp"], derived["capex_local"],
                         derived["capex_usd"], derived["revenue_y1_local"],
                         derived["annual_gen_mwh"], derived["npv_local"],
                         derived["irr_pct"], derived["lcoe_local_per_kwh"],
                         derived["payback_years"], derived["dscr_avg"],
                         notes, opp["id"], uid),
                    )
                flash("Investment opportunity refreshed from project data.",
                      "success")
            if action == "advance":
                return redirect(url_for("capital_investment_step12", pid=pid))
            return redirect(url_for("capital_investment_step11", pid=pid))

        # GET - preview the derived opportunity if none saved yet.
        derived = build_opportunity_from_project(proj) if opp is None else None
        return render_template(
            "capital_investment_step11_crm.html",
            user=current_user(),
            proj=proj,
            opp=opp,
            derived=derived,
        )

    # ------------------------------------------------------------------
    # STEP 12 - Sales Pipeline (13-stage utility-scale progression)
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/<int:pid>/step12",
               methods=["GET", "POST"],
               endpoint="capital_investment_step12")
    @login_required
    def _step12(pid: int):
        if (g := _gate(CI_LEVEL_FULL)) is not None: return g
        proj = _load_project(pid)
        uid = session["user_id"]
        _ensure_opportunities_schema(get_db)
        opp = _load_opportunity(pid, uid)

        if opp is None:
            flash("Create the investment opportunity on Step 11 first.",
                  "warning")
            return redirect(url_for("capital_investment_step11", pid=pid))

        if request.method == "POST":
            csrf_protect()
            new_stage = (request.form.get("stage") or "").strip()
            if new_stage not in set(PIPELINE_STAGE_CODES):
                flash("Unknown pipeline stage.", "warning")
                return redirect(url_for("capital_investment_step12", pid=pid))

            # Append to stage history and update current stage.
            history = []
            try:
                history = json.loads(opp.get("stage_history") or "[]")
                if not isinstance(history, list):
                    history = []
            except (TypeError, ValueError):
                history = []
            history.append({"from": opp.get("stage"), "to": new_stage,
                            "at": _utc_now_iso()})
            with get_db() as c:
                c.execute(
                    "UPDATE capital_investment_opportunities "
                    "SET stage=?, stage_history=?, updated_at=CURRENT_TIMESTAMP "
                    "WHERE id=? AND user_id=?",
                    (new_stage, json.dumps(history), opp["id"], uid),
                )
            flash(f"Pipeline advanced to '{PIPELINE_STAGE_LABEL[new_stage]}'.",
                  "success")
            return redirect(url_for("capital_investment_step12", pid=pid))

        # Reload after any change.
        opp = _load_opportunity(pid, uid)
        try:
            history = json.loads(opp.get("stage_history") or "[]")
        except (TypeError, ValueError):
            history = []
        return render_template(
            "capital_investment_step12_pipeline.html",
            user=current_user(),
            proj=proj,
            opp=opp,
            history=history,
            pipeline_stages=PIPELINE_STAGES,
        )

    # ------------------------------------------------------------------
    # STEP 13 - Reports menu + PDF download endpoint
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/<int:pid>/step13",
               endpoint="capital_investment_step13")
    @login_required
    def _step13(pid: int):
        if (g := _gate(CI_LEVEL_FULL)) is not None: return g
        proj = _load_project(pid)
        uid = session["user_id"]
        opp = _load_opportunity(pid, uid)
        return render_template(
            "capital_investment_step13_reports.html",
            user=current_user(),
            proj=proj,
            opp=opp,
            report_types=REPORT_TYPES,
        )

    @app.route("/large-scale-solar/<int:pid>/report/<report_key>.pdf",
               endpoint="capital_investment_report_pdf")
    @login_required
    def _report_pdf(pid: int, report_key: str):
        if (g := _gate(CI_LEVEL_FULL)) is not None: return g
        if report_key not in FULL_REPORT_KEYS:
            abort(404)
        proj = _load_project(pid)
        uid = session["user_id"]
        opp = _load_opportunity(pid, uid)
        md, title = _build_report_markdown(report_key, proj, opp)
        try:
            pdf_bytes = _render_pdf_bytes(md, title)
        except Exception as e:  # pragma: no cover
            flash(f"Could not build the PDF - {e}. "
                  "markdown-pdf missing?", "danger")
            return redirect(url_for("capital_investment_step13", pid=pid))
        from flask import make_response
        safe_name = (proj["project_name"] or "project").replace(" ", "_")[:80]
        filename = f"{safe_name}_{report_key}.pdf"
        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = (
            f'attachment; filename="{filename}"'
        )
        return resp

    # ------------------------------------------------------------------
    # STEP 14 - AI Agents (15 specialists + orchestrator)
    # Enterprise-gated. Rule-based agents that review the project's
    # stored config and return findings + recommendations + score.
    # Runs are persisted to capital_investment_agent_runs.
    # ------------------------------------------------------------------
    def _load_latest_agent_runs(pid: int) -> dict[str, dict[str, Any]]:
        """Return {agent_code: last_run_dict} for this project."""
        _ensure_agent_runs_schema(get_db)
        out: dict[str, dict[str, Any]] = {}
        try:
            with get_db() as c:
                rows = c.execute(
                    "SELECT agent_code, status, score, payload, created_at "
                    "FROM capital_investment_agent_runs "
                    "WHERE project_id=? "
                    "ORDER BY created_at DESC, id DESC LIMIT 200",
                    (pid,),
                ).fetchall()
        except Exception:
            return out
        for r in rows or []:
            d = dict(r) if hasattr(r, "keys") else {
                "agent_code": r[0], "status": r[1], "score": r[2],
                "payload": r[3], "created_at": r[4],
            }
            code = d["agent_code"]
            if code in out:
                continue
            try:
                pl = json.loads(d.get("payload") or "{}")
            except (TypeError, ValueError):
                pl = {}
            out[code] = {
                "status":  d.get("status"),
                "score":   d.get("score"),
                "created": d.get("created_at"),
                **pl,
            }
        return out

    @app.route("/large-scale-solar/<int:pid>/step14",
               methods=["GET", "POST"],
               endpoint="capital_investment_step14")
    @login_required
    def _step14(pid: int):
        if (g := _gate(CI_LEVEL_FULL)) is not None: return g
        proj = _load_project(pid)
        uid = session["user_id"]
        _ensure_agent_runs_schema(get_db)

        if request.method == "POST":
            csrf_protect()
            which = (request.form.get("agent") or "all").strip()
            if which == "all":
                report = run_agent_orchestrator(proj)
                specialists = report["specialists"]
            else:
                if which not in AGENT_CODES:
                    flash("Unknown agent.", "warning")
                    return redirect(url_for("capital_investment_step14", pid=pid))
                if which == "reviewer":
                    # Reviewer needs sub-scores - just run the whole orchestrator.
                    report = run_agent_orchestrator(proj)
                    specialists = report["specialists"]
                else:
                    runner = AGENT_RUNNERS.get(which)
                    specialists = {which: runner(proj)} if runner else {}
            with get_db() as c:
                for code, payload in specialists.items():
                    try:
                        c.execute(
                            "INSERT INTO capital_investment_agent_runs "
                            "(project_id, user_id, agent_code, status, "
                            " score, payload) VALUES (?,?,?,?,?,?)",
                            (pid, uid, code,
                             payload.get("status") or "ok",
                             int(payload.get("score") or 0),
                             json.dumps(payload)),
                        )
                    except Exception:
                        pass
            flash(f"{len(specialists)} agent(s) ran.", "success")
            return redirect(url_for("capital_investment_step14", pid=pid))

        latest = _load_latest_agent_runs(pid)
        aggregate_score = None
        if latest:
            considered = [v["score"] for k, v in latest.items()
                          if k != "reviewer" and v.get("score") is not None]
            if considered:
                aggregate_score = int(round(sum(considered) / len(considered)))
        return render_template(
            "capital_investment_step14_agents.html",
            user=current_user(),
            proj=proj,
            agents=AGENT_DEPARTMENTS,
            latest=latest,
            aggregate_score=aggregate_score,
        )

    # ------------------------------------------------------------------
    # 3D DIGITAL TWIN STUDIO
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/<int:pid>/digital-twin",
               endpoint="capital_investment_digital_twin")
    @login_required
    def _digital_twin(pid: int):
        if (g := _gate(CI_LEVEL_FULL)) is not None: return g
        proj = _load_project(pid)
        # Scene is built server-side once so the template can render the
        # left-nav layer list without a second round-trip.
        scene = build_scene_from_project(proj)
        return render_template(
            "capital_investment_digital_twin.html",
            user=current_user(),
            proj=proj,
            scene=scene,
            layer_groups=scene["layer_groups"],
        )

    @app.route("/large-scale-solar/<int:pid>/dt/scene.json",
               endpoint="capital_investment_dt_scene")
    @login_required
    def _dt_scene_json(pid: int):
        if (g := _gate(CI_LEVEL_FULL)) is not None: return g
        proj = _load_project(pid)
        scene = build_scene_from_project(proj)
        return jsonify(scene)

    @app.route("/large-scale-solar/<int:pid>/dt/sun.json",
               endpoint="capital_investment_dt_sun")
    @login_required
    def _dt_sun_json(pid: int):
        if (g := _gate(CI_LEVEL_FULL)) is not None: return g
        proj = _load_project(pid)
        try:
            month = int(request.args.get("month", "6"))
            hour = float(request.args.get("hour", "12"))
        except (TypeError, ValueError):
            month, hour = 6, 12.0
        month = max(1, min(12, month))
        hour = max(0.0, min(24.0, hour))
        lat = proj.get("gps_lat") or 6.0     # Ghana default
        lon = proj.get("gps_lon") or 0.0
        sun = _sun_position(float(lat), float(lon), month, hour)
        return jsonify(sun)

    # ------------------------------------------------------------------
    # Development & Regulatory Configuration (spec's recommended
    # pre-PV-design bolt-on, country-scoped).
    # ------------------------------------------------------------------
    @app.route("/large-scale-solar/<int:pid>/regulatory",
               methods=["GET", "POST"],
               endpoint="capital_investment_regulatory")
    @login_required
    def _regulatory(pid: int):
        if (g := _gate(CI_LEVEL_FULL)) is not None: return g
        proj = _load_project(pid)
        reg_cfg = _safe_json(proj.get("regulatory_config"))
        framework = country_framework(proj.get("country"))

        if request.method == "POST":
            csrf_protect()
            f = request.form

            items: dict[str, dict[str, str]] = {}
            for code, _label, _hint in REGULATORY_ITEMS:
                status = (f.get(f"status__{code}") or "not_started").strip()
                if status not in REGULATORY_STATUS_CODES:
                    status = "not_started"
                notes = (f.get(f"notes__{code}") or "").strip()[:2000]
                items[code] = {"status": status, "notes": notes}

            # Country-specific land-acquisition control block: capture the
            # chosen tenure + a free-text field for community-consent
            # documentation. Country's own tenure list is used to validate.
            valid_tenures = {t["code"] for t in framework.get("land_tenures", [])}
            selected_tenure = (f.get("land_tenure") or "").strip()
            if selected_tenure and selected_tenure not in valid_tenures:
                selected_tenure = ""
            new_cfg = {
                "items":               items,
                "country":             proj.get("country") or "",
                "land_tenure":         selected_tenure,
                "land_acquisition_notes":
                    (f.get("land_acquisition_notes") or "").strip()[:4000],
                "community_engagement":
                    (f.get("community_engagement") or "").strip()[:2000],
                "regulatory_notes":
                    (f.get("regulatory_notes") or "").strip()[:2000],
            }
            _save_project_field(pid, "regulatory_config", json.dumps(new_cfg))
            flash("Development & regulatory scope saved.", "success")
            return redirect(url_for("capital_investment_regulatory", pid=pid))

        return render_template(
            "capital_investment_regulatory.html",
            user=current_user(),
            proj=proj,
            cfg=reg_cfg,
            framework=framework,
            regulatory_items=REGULATORY_ITEMS,
            regulatory_statuses=REGULATORY_STATUSES,
        )

    return app


# ---------------------------------------------------------------------------
# Report markdown builders
# ---------------------------------------------------------------------------

def _fmt_money(v: Any, currency: str = "") -> str:
    if v is None:
        return "n/a"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(v) >= 1_000_000:
        s = f"{v/1_000_000:,.2f}M"
    elif abs(v) >= 1_000:
        s = f"{v:,.0f}"
    else:
        s = f"{v:.2f}"
    return f"{currency} {s}" if currency else s


def _fmt_pct(v: Any) -> str:
    if v is None:
        return "n/a"
    try:
        return f"{float(v):.2f} %"
    except (TypeError, ValueError):
        return str(v)


def _build_report_markdown(key: str, proj: dict[str, Any],
                           opp: dict[str, Any] | None) -> tuple[str, str]:
    """Return (markdown, doc_title) for the given report key."""
    pv = _safe_json(proj.get("pv_config"))
    fin = _safe_json(proj.get("finance_config"))
    fac = _safe_json(proj.get("facility_config"))
    tech = _safe_json(proj.get("technology_config"))
    elec = _safe_json(proj.get("electrical_config"))
    site = _safe_json(proj.get("site_config"))
    reg = _safe_json(proj.get("regulatory_config"))
    sizing = pv.get("sizing") or {}
    computed = fin.get("computed") or {}
    cur = proj.get("currency") or "GHS"
    framework = country_framework(proj.get("country"))

    header = (
        f"# {proj['project_name']}\n\n"
        f"**Client:** {proj.get('client_name') or '(unspecified)'}  \n"
        f"**Investor:** {proj.get('investor') or '(unspecified)'}  \n"
        f"**Developer:** {proj.get('developer') or '(unspecified)'}  \n"
        f"**Location:** "
        f"{proj.get('district') or ''} {proj.get('region') or ''} "
        f"{proj.get('country') or ''}  \n"
        f"**Target COD:** {proj.get('target_cod') or 'to be confirmed'}  \n"
        f"**Design standard:** {proj.get('design_standard') or 'IEC'}  \n\n"
    )

    if key == "executive":
        title = f"Executive Summary - {proj['project_name']}"
        md = header + (
            "## Executive summary\n\n"
            f"{proj.get('description') or ''}\n\n"
            "### Headline\n\n"
            f"- **Capacity:** {_fmt_money(sizing.get('kwp_input') or (proj.get('target_kwp') or 0))} kWp DC "
            f"({(sizing.get('kwp_input') or proj.get('target_kwp') or 0)/1000:.1f} MWp)\n"
            f"- **Annual generation:** {_fmt_money(sizing.get('annual_gen_mwh'))} MWh\n"
            f"- **Total CAPEX:** {_fmt_money(computed.get('total_capex_usd'), 'USD')} "
            f"({_fmt_money(computed.get('total_capex_local'), cur)})\n"
            f"- **IRR:** {_fmt_pct(computed.get('irr_pct'))}\n"
            f"- **NPV:** {_fmt_money(computed.get('npv_local'), cur)}\n"
            f"- **LCOE:** {computed.get('lcoe_local_per_kwh') or 'n/a'} {cur}/kWh\n"
            f"- **Payback:** "
            f"{('%.1f yr' % computed['payback_years']) if computed.get('payback_years') else 'beyond project life'}\n\n"
            "### Facilities\n\n"
            + (", ".join(fac.get("buildings") or []) or "not yet configured")
            + "\n\n"
            "### Technology stack\n\n"
            + (", ".join(tech.get("selected") or []) or "not yet configured")
            + "\n\n"
            "### Jurisdiction\n\n"
            f"Regulator: **{framework.get('regulator', {}).get('name', '')}**  \n"
            f"ESIA authority: **{framework.get('esia_authority', {}).get('name', '')}**  \n"
            f"Off-taker(s): {', '.join(framework.get('utility_offtakers') or [])}\n"
        )
    elif key == "technical":
        title = f"Technical Report - {proj['project_name']}"
        md = header + (
            "## Technical report\n\n"
            "### PV design\n\n"
            f"- **DC capacity:** {sizing.get('dc_kwp_actual') or 'n/a'} kWp\n"
            f"- **AC capacity:** {sizing.get('inverter_ac_kw') or 'n/a'} kW\n"
            f"- **Module technology:** {pv.get('module_tech') or 'n/a'}\n"
            f"- **Module Wp:** {pv.get('module_wp') or 'n/a'} W\n"
            f"- **Modules:** {sizing.get('n_modules') or 'n/a'}\n"
            f"- **Strings:** {sizing.get('strings') or 'n/a'}\n"
            f"- **Combiner boxes:** {sizing.get('combiners') or 'n/a'}\n"
            f"- **Central inverters:** {sizing.get('n_central_inverters') or 'n/a'} "
            f"x {sizing.get('central_inverter_kw') or 'n/a'} kW\n"
            f"- **Mounting:** {pv.get('mounting') or 'n/a'}\n"
            f"- **Tilt / azimuth:** {pv.get('tilt_deg') or 'n/a'}deg / {pv.get('azimuth_deg') or 'n/a'}deg\n"
            f"- **PSH:** {pv.get('psh_daily') or 'n/a'} kWh/m2/day\n"
            f"- **PR:** {pv.get('performance_ratio') or 'n/a'}\n"
            f"- **Availability:** {pv.get('availability_pct') or 'n/a'} %\n"
            f"- **Annual degradation:** {pv.get('annual_degradation_pct') or 'n/a'} %\n"
            f"- **Specific yield:** {sizing.get('specific_yield_kwh_per_kwp') or 'n/a'} kWh/kWp\n"
            f"- **Annual gen:** {_fmt_money(sizing.get('annual_gen_mwh'))} MWh\n"
            f"- **Lifetime gen:** {_fmt_money(sizing.get('lifetime_gen_mwh'))} MWh\n\n"
            "### Site\n\n"
            f"- Land area: {site.get('land_area_ha') or 'n/a'} ha\n"
            f"- Terrain: {site.get('terrain') or 'n/a'}\n"
            f"- Slope: {site.get('slope') or 'n/a'}\n"
            f"- Soil: {site.get('soil') or 'n/a'}\n"
            f"- Flood risk: {site.get('flood_risk') or 'n/a'}\n"
            f"- Wind zone: {site.get('wind_zone') or 'n/a'}\n"
            f"- Grid distance: {site.get('grid_distance_km') or 'n/a'} km\n"
            f"- HV line: {site.get('hv_line_kv') or 'n/a'} kV\n\n"
            "### Facilities\n\n"
            + "\n".join(f"- {b}" for b in (fac.get("buildings") or []) or ["(none)"])
            + "\n\n### Electrical scope\n\n"
            + "\n".join(f"- {s}" for s in (elec.get("selected") or []) or ["(none)"])
            + "\n\n### Technology stack\n\n"
            + "\n".join(f"- {t}" for t in (tech.get("selected") or []) or ["(none)"])
        )
    elif key == "financial":
        title = f"Financial Report - {proj['project_name']}"
        md = header + (
            "## Financial report\n\n"
            "### CAPEX\n\n"
            f"- **Total CAPEX:** {_fmt_money(computed.get('total_capex_usd'), 'USD')} "
            f"({_fmt_money(computed.get('total_capex_local'), cur)})\n"
            f"- **USD per kWp:** {_fmt_money(computed.get('capex_usd_per_kwp'), 'USD')}\n\n"
            "CAPEX breakdown (USD):\n\n"
            + ("\n".join(f"- {k.replace('_', ' ').title()}: {_fmt_money(v)}"
                        for k, v in (computed.get('capex_lines_usd') or {}).items())
               or "(not yet computed)")
            + "\n\n### OPEX\n\n"
            f"- **Annual OPEX:** {_fmt_money(computed.get('total_opex_usd_yr'), 'USD')} "
            f"({_fmt_money(computed.get('total_opex_local_yr'), cur)})\n\n"
            "OPEX breakdown (USD/yr):\n\n"
            + ("\n".join(f"- {k.replace('_', ' ').title()}: {_fmt_money(v)}"
                        for k, v in (computed.get('opex_lines_usd_yr') or {}).items())
               or "(not yet computed)")
            + "\n\n### Debt & equity\n\n"
            f"- Debt: {_fmt_money(computed.get('debt_local'), cur)}\n"
            f"- Equity: {_fmt_money(computed.get('equity_local'), cur)}\n"
            f"- Annual debt service: {_fmt_money(computed.get('annual_debt_service_local'), cur)}\n\n"
            "### Returns\n\n"
            f"- NPV: {_fmt_money(computed.get('npv_local'), cur)}\n"
            f"- IRR: {_fmt_pct(computed.get('irr_pct'))}\n"
            f"- LCOE: {computed.get('lcoe_local_per_kwh') or 'n/a'} {cur}/kWh\n"
            f"- Payback: "
            f"{('%.1f yr' % computed['payback_years']) if computed.get('payback_years') else 'beyond project life'}\n"
        )
    elif key == "bankability":
        title = f"Bankability Report - {proj['project_name']}"
        mc = computed.get("monte_carlo") or {}
        md = header + (
            "## Bankability report\n\n"
            "### Base-case metrics\n\n"
            f"- NPV: {_fmt_money(computed.get('npv_local'), cur)}\n"
            f"- IRR: {_fmt_pct(computed.get('irr_pct'))}\n"
            f"- LCOE: {computed.get('lcoe_local_per_kwh') or 'n/a'} {cur}/kWh\n"
            f"- Payback: "
            f"{('%.1f yr' % computed['payback_years']) if computed.get('payback_years') else 'beyond project life'}\n"
            f"- DSCR average: {computed.get('dscr_avg') or 'n/a'}x\n"
            f"- DSCR minimum: {computed.get('dscr_min') or 'n/a'}x\n\n"
            "### Monte Carlo\n\n"
            f"Runs: {mc.get('runs') or '(not run)'}\n\n"
            f"- NPV P10 / P50 / P90: {mc.get('npv_p10') or '-'} / "
            f"{mc.get('npv_p50') or '-'} / {mc.get('npv_p90') or '-'}\n"
            f"- IRR P10 / P50 / P90 (%): {mc.get('irr_p10_pct') or '-'} / "
            f"{mc.get('irr_p50_pct') or '-'} / {mc.get('irr_p90_pct') or '-'}\n\n"
            "### Key risks\n\n"
            "- FX / convertibility risk\n"
            "- Off-taker credit\n"
            "- PPA tariff review clauses\n"
            "- Grid curtailment\n"
            "- Component degradation vs. warranty\n"
            "- Land tenure disputes\n"
            "- Regulatory + permit delays\n\n"
            "### Jurisdictional bankability\n\n"
            f"{framework.get('notes') or ''}\n"
        )
    elif key == "investment_memo":
        title = f"Investment Memorandum - {proj['project_name']}"
        md = header + (
            "## Investment memorandum\n\n"
            "### Opportunity\n\n"
            f"{proj.get('description') or ''}\n\n"
            "### Investment ask\n\n"
            f"- Equity requirement: {_fmt_money(computed.get('equity_local'), cur)}\n"
            f"- Debt requirement: {_fmt_money(computed.get('debt_local'), cur)}\n\n"
            "### Expected returns\n\n"
            f"- IRR (base): {_fmt_pct(computed.get('irr_pct'))}\n"
            f"- Payback: "
            f"{('%.1f yr' % computed['payback_years']) if computed.get('payback_years') else 'beyond project life'}\n\n"
            "### Structure\n\n"
            f"- Currency: {cur}\n"
            f"- Debt ratio: {fin.get('debt_ratio_pct') or 'n/a'}%\n"
            f"- Debt rate: {fin.get('debt_rate_pct') or 'n/a'}%\n"
            f"- Debt tenor: {fin.get('debt_tenor_yr') or 'n/a'} yr\n"
            f"- Off-take: {fin.get('revenue_model') or 'n/a'}\n"
            f"- Tariff: {fin.get('tariff_local_per_kwh') or 'n/a'} {cur}/kWh\n\n"
            "### Jurisdiction\n\n"
            f"- Country: {proj.get('country') or ''}\n"
            f"- Regulator: {framework.get('regulator', {}).get('name', '')}\n"
            f"- ESIA authority: {framework.get('esia_authority', {}).get('name', '')}\n"
            f"- Off-takers: {', '.join(framework.get('utility_offtakers') or [])}\n\n"
            f"### Regulatory posture\n\n"
            + ("\n".join(
                f"- {label}: {(reg.get('items') or {}).get(code, {}).get('status', 'not_started')}"
                for code, label, _ in REGULATORY_ITEMS)
               if reg.get("items") else "(regulatory posture not yet captured)")
        )
    else:
        title = "Report"
        md = header + "This report has not been implemented yet."

    return md, title


def _render_pdf_bytes(markdown_text: str, doc_title: str) -> bytes:
    """Render markdown to PDF using markdown-pdf (same library the rest
    of SolarPro uses)."""
    from markdown_pdf import MarkdownPdf, Section
    import io

    pdf = MarkdownPdf(toc_level=2)
    pdf.meta["title"] = doc_title
    pdf.add_section(Section(markdown_text, toc=True))
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Marketplace category mapper
# ---------------------------------------------------------------------------

def _marketplace_categories_for(pv_cfg: dict, tech_cfg: dict,
                                elec_cfg: dict) -> list[dict[str, Any]]:
    """Return categories to sweep in the existing marketplace. Each entry:
    label, count-hint, marketplace_href (relative URL)."""
    pv_selected = bool((pv_cfg or {}).get("kwp"))
    tech_selected = set((tech_cfg or {}).get("selected") or [])
    elec_selected = set((elec_cfg or {}).get("selected") or [])

    def _cat(label: str, cat: str, sub: str = "", why: str = "") -> dict:
        href = f"/marketplace?cat={cat}"
        if sub:
            href += f"&sub={sub}"
        return {"label": label, "why": why, "href": href}

    cats: list[dict] = []
    # PV backbone.
    if pv_selected:
        cats.append(_cat("PV Modules",       "pv_modules",
                         why="Confirm Wp band, warranty, bifacial gain if bifacial"))
        cats.append(_cat("Inverters",        "inverters",
                         why="Central 1-5 MW blocks for utility, 100-250 kW string otherwise"))
        cats.append(_cat("Mounting / Trackers","mounting_structures",
                         why="Fixed-tilt vs. HSAT; check +/- 60 deg range for HSAT"))
        cats.append(_cat("DC Cables",        "cables",
                         why="Solar-rated DC cable 1500 V, UV-stable"))
        cats.append(_cat("Combiner Boxes",   "combiners",
                         why="String monitoring, fuses, DC surge protection"))
    # HV / MV backbone.
    if "transformers" in elec_selected or "hv_distribution" in elec_selected:
        cats.append(_cat("Power Transformers","transformers",
                         why="Step-up MV -> HV; oil vs. dry; NEMA / IEC"))
        cats.append(_cat("RMU / MV Switchgear","power_system",
                         why="Ring Main Unit + protection relays"))
    if "lv_switchgear" in elec_selected or "lv_distribution" in elec_selected:
        cats.append(_cat("LV Panels & Switchgear","power_system",
                         why="LV combiner + main LV distribution"))
    if "earthing" in elec_selected or "lightning_protection" in elec_selected:
        cats.append(_cat("Earthing & Lightning Protection", "earthing",
                         why="Earth rods, mesh grid, LPS air terminals"))
    if "fire_alarm" in elec_selected:
        cats.append(_cat("Fire Alarm & Detection", "fire_alarm",
                         why="Smoke/heat/beam detectors + control panel"))
    if "ip_cctv" in elec_selected:
        cats.append(_cat("CCTV & NVR", "cctv",
                         why="Perimeter + gate coverage; PoE recommended"))
    if "access_control" in elec_selected:
        cats.append(_cat("Access Control", "access_control",
                         why="Card readers, boom barriers, biometrics"))
    if "lan" in elec_selected or "wan" in elec_selected \
            or "ind_eth" in tech_selected or "fibre" in tech_selected:
        cats.append(_cat("Network Switches / Firewalls / Fibre", "networking",
                         why="Industrial-grade Ethernet + fibre backbone"))
    # SCADA / EMS / BMS.
    if ("scada" in tech_selected or "scada" in elec_selected
            or "ems" in tech_selected or "ppc" in tech_selected):
        cats.append(_cat("SCADA / EMS / PPC Servers", "server_equipment",
                         why="Redundant server pair + historian"))
    if "bms" in tech_selected:
        cats.append(_cat("Battery Management System", "monitoring",
                         why="BMS master + cell-level monitoring"))
    if "weather" in tech_selected:
        cats.append(_cat("Weather Stations", "monitoring",
                         why="Pyranometer + ambient + module temperature"))
    if "cctv" not in [c["label"] for c in cats] and "cctv" in tech_selected:
        cats.append(_cat("CCTV & NVR", "cctv"))
    if "ups" not in [c["label"] for c in cats]:
        cats.append(_cat("UPS Systems", "ups",
                         why="Control room + SCADA continuity"))
    return cats


# ---------------------------------------------------------------------------
# Small helpers used inside the step handlers
# ---------------------------------------------------------------------------

def _safe_json(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else {}
    except (TypeError, ValueError):
        return {}


def _pick(form_like, key: str, allowed: list[tuple[str, str]]) -> str:
    codes = {c for c, _ in allowed}
    v = (form_like.get(key) or "").strip()
    return v if v in codes else ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STEP_LABELS: list[tuple[int, str, str, str]] = [
    # (n, label, done_field, endpoint_or_'' for stub)
    (1,  "Project Registration",           "project_name",       "capital_investment_project"),
    (2,  "Project Type",                   "project_type",       "capital_investment_step2"),
    (3,  "Site Configuration",             "site_config",        "capital_investment_step3"),
    (4,  "Facility Configuration",         "facility_config",    "capital_investment_step4"),
    (5,  "Technology Configuration",       "technology_config",  "capital_investment_step5"),
    (6,  "Electrical System Configuration","electrical_config",  "capital_investment_step6"),
    (7,  "PV Design",                      "pv_config",          "capital_investment_step7"),
    (8,  "Financial Engineering",          "finance_config",     "capital_investment_step8"),
    (9,  "BOQ",                            "boq_project_id",     "capital_investment_step9"),
    (10, "Marketplace",                    "_marketplace_hook",  "capital_investment_step10"),
    (11, "CRM Opportunity",                "_crm_hook",          "capital_investment_step11"),
    (12, "Sales Pipeline",                 "_pipeline_hook",     "capital_investment_step12"),
    (13, "Reports",                        "_report_hook",       "capital_investment_step13"),
    (14, "AI Agents",                      "_agents_hook",       "capital_investment_step14"),
]


def _is_meaningfully_populated(field: str, val: Any) -> bool:
    """A JSON blob field counts as done only if it has real content."""
    if val is None:
        return False
    if field.startswith("_"):
        return False
    if field == "boq_project_id":
        return bool(val)
    if not isinstance(val, str):
        return bool(val)
    s = val.strip()
    if not s:
        return False
    # JSON blob fields must actually contain something meaningful.
    JSON_FIELDS = {"site_config", "facility_config", "technology_config",
                   "electrical_config", "pv_config", "finance_config",
                   "regulatory_config"}
    if field in JSON_FIELDS:
        try:
            parsed = json.loads(s)
        except (TypeError, ValueError):
            return False
        if not isinstance(parsed, dict):
            return bool(parsed)
        # Truthy if any leaf value is set (non-empty string / non-empty list /
        # a real number, but NOT None / '' / [] / {}).
        for v in parsed.values():
            if v in (None, "", [], {}):
                continue
            return True
        return False
    return True


def _wizard_progress(proj: dict[str, Any]) -> list[dict[str, Any]]:
    """Return one dict per step, each with n, label, done, active, endpoint."""
    out: list[dict[str, Any]] = []
    for n, label, field, endpoint in _STEP_LABELS:
        val = proj.get(field)
        done = _is_meaningfully_populated(field, val)
        out.append({"n": n, "label": label, "field": field,
                    "endpoint": endpoint,
                    "done": done, "active": False})
    # Mark the next-not-done step as active.
    for step in out:
        if not step["done"]:
            step["active"] = True
            break
    return out
