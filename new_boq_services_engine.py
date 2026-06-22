# === BEGIN: boq_services_engine splice ===
# 2026-06-22 (session A): BOQ project services. Users tick which services
# the project must cover BEFORE picking a template. Templates are then
# scored against the chosen services and any chosen service that isn't in
# the template gets a generic placeholder bill injected so the BOQ never
# silently drops a service the project requires.

# Ordered service registry. Codes are stable (used in boq_projects.services_csv).
# Owner can add more later via _BOQ_SERVICES + skeleton in _BOQ_SERVICE_BILL_SKELETON.
_BOQ_SERVICES = [
    ("power_supply_lighting", "Power supply & external lighting",  "bi-lightning-charge"),
    ("internal_electrical",   "Internal electrical installation",  "bi-plug-fill"),
    ("it_network",            "IT & network systems",              "bi-hdd-network"),
    ("fire_alarm",            "Fire alarm system",                 "bi-fire"),
    ("lightning_protection",  "Lightning protection",              "bi-cloud-lightning-rain"),
    ("earthing_bonding",      "Equipotential earthing & bonding",  "bi-arrow-down-square"),
    ("ip_cctv",               "IP CCTV system",                    "bi-camera-video"),
    ("nurse_call",            "Nurse call system",                 "bi-bell-fill"),
    ("ip_pa",                 "IP PA / public-address system",     "bi-megaphone"),
    ("bms",                   "BMS (building management)",         "bi-cpu"),
]
_BOQ_SERVICE_CODES = [c for c, _, _ in _BOQ_SERVICES]
_BOQ_SERVICE_LABEL = {c: l for c, l, _ in _BOQ_SERVICES}
_BOQ_SERVICE_ICON  = {c: ic for c, _, ic in _BOQ_SERVICES}


# Map existing template bill names -> services. Uses uppercase substring match.
# A bill may serve multiple services.
_BOQ_BILL_TO_SERVICES = [
    ("PRELIMINARIES",                 []),  # not a service on its own
    ("INTERNAL ELECTRICAL",           ["internal_electrical", "power_supply_lighting"]),
    ("EXTERNAL LIGHTING",             ["power_supply_lighting"]),
    ("BONDING AND EARTHING",          ["earthing_bonding"]),
    ("EQUIPOTENTIAL",                 ["earthing_bonding"]),
    ("LIGHTNING PROTECTION",          ["lightning_protection"]),
    ("FIRE ALARM",                    ["fire_alarm"]),
    ("DATA AND VOICE",                ["it_network"]),
    ("STRUCTURED CABLING",            ["it_network"]),
    ("IT AND NETWORK",                ["it_network"]),
    ("SIGNAL COMMUNICATION",          ["ip_pa", "ip_cctv"]),
    ("CCTV",                          ["ip_cctv"]),
    ("PUBLIC ADDRESS",                ["ip_pa"]),
    ("NURSE CALL",                    ["nurse_call"]),
    ("BMS",                           ["bms"]),
    ("BUILDING MANAGEMENT",           ["bms"]),
]


def _template_services(template: dict) -> list:
    """Return the de-duplicated service codes a template covers."""
    services = []
    seen = set()
    for bill in template.get("bills", []):
        name = (bill.get("name") or "").upper()
        for needle, svc_list in _BOQ_BILL_TO_SERVICES:
            if needle in name:
                for s in svc_list:
                    if s not in seen:
                        seen.add(s)
                        services.append(s)
    return services


# Generic placeholder bills -- 1 per service. These mirror the supplier price
# sheets the owner shared (Apinto Agenda + Grand Pacific) so the lines feel
# real even when nothing in the picked template covered that service.
_BOQ_SERVICE_BILL_SKELETON = {
    "power_supply_lighting": {
        "name": "POWER SUPPLY AND EXTERNAL LIGHTING",
        "sections": [
            {"letter": "A", "title": "UTILITY SUPPLY AND METERING", "subsection": "", "items": [
                {"desc": "Utility metering kiosk + bulk meter",   "unit": "Lot",  "qty": 1, "basic":  8500, "spec": "Per ECG / NEDCo standard"},
                {"desc": "Main incoming switchgear",              "unit": "No.",  "qty": 1, "basic": 15000, "spec": "Rated per project demand"},
            ]},
            {"letter": "B", "title": "EXTERNAL AREA LIGHTING", "subsection": "", "items": [
                {"desc": "9m steel street-light pole + LED head", "unit": "No.",  "qty": 6, "basic":  3200, "spec": "60W LED, IP66"},
                {"desc": "Underground feed cable to poles",       "unit": "m",    "qty": 80,"basic":    65, "spec": "4C x 6mm2 Cu/XLPE/SWA/PVC"},
                {"desc": "Photocell + contactor control unit",    "unit": "No.",  "qty": 1, "basic":  1850, "spec": "32A dusk-to-dawn"},
            ]},
        ],
    },
    "internal_electrical": {
        "name": "INTERNAL ELECTRICAL INSTALLATION",
        "sections": [
            {"letter": "A", "title": "DISTRIBUTION BOARDS", "subsection": "", "items": [
                {"desc": "Final DB c/w MCBs", "unit": "No.", "qty": 1, "basic": 3200, "spec": "TPN, 12-way, 100A"},
            ]},
            {"letter": "B", "title": "WIRING OF POINTS", "subsection": "Lighting + socket circuits", "items": [
                {"desc": "1.5mm² PVC copper cable", "unit": "Roll", "qty": 4, "basic": 390, "spec": "BS 6004"},
                {"desc": "2.5mm² PVC copper cable", "unit": "Roll", "qty": 4, "basic": 650, "spec": "BS 6004"},
                {"desc": "PVC conduit 20mm + boxes", "unit": "Lot", "qty": 1, "basic": 1850, "spec": "Heavy gauge"},
            ]},
        ],
    },
    "it_network": {
        "name": "IT AND NETWORK SYSTEMS",
        "sections": [
            {"letter": "A", "title": "STRUCTURED CABLING", "subsection": "", "items": [
                {"desc": "Cat6 UTP horizontal cable",         "unit": "Roll", "qty": 4, "basic": 1200, "spec": "305m / box, blue jacket"},
                {"desc": "Cat6 RJ45 keystone outlet",         "unit": "No.",  "qty":40, "basic":   28, "spec": "T568B punch-down"},
                {"desc": "24-port Cat6 patch panel",          "unit": "No.",  "qty": 2, "basic":  650, "spec": "1U, loaded"},
            ]},
            {"letter": "B", "title": "ACTIVE NETWORK EQUIPMENT", "subsection": "", "items": [
                {"desc": "24-port Gigabit PoE switch",        "unit": "No.",  "qty": 1, "basic": 7500, "spec": "L2, 370W PoE budget"},
                {"desc": "Wireless access point (WiFi 6)",    "unit": "No.",  "qty": 4, "basic": 1800, "spec": "PoE-fed"},
            ]},
        ],
    },
    "fire_alarm": {
        "name": "FIRE ALARM SYSTEM",
        "sections": [
            {"letter": "A", "title": "PANELS AND DETECTORS", "subsection": "", "items": [
                {"desc": "Addressable FACP",                  "unit": "No.",  "qty": 1, "basic": 8500, "spec": "2-loop, EN 54-2/4"},
                {"desc": "Optical smoke detector",            "unit": "No.",  "qty":24, "basic":  220, "spec": "Addressable, EN 54-7"},
                {"desc": "Manual call point",                 "unit": "No.",  "qty": 8, "basic":  180, "spec": "EN 54-11"},
                {"desc": "Sounder + strobe",                  "unit": "No.",  "qty": 8, "basic":  320, "spec": "100dB, EN 54-3/23"},
            ]},
            {"letter": "B", "title": "CABLING", "subsection": "", "items": [
                {"desc": "Fire-resistant cable",              "unit": "m",    "qty":250,"basic":   14, "spec": "FP200, 1.5mm² 2C"},
            ]},
        ],
    },
    "lightning_protection": {
        "name": "LIGHTNING PROTECTION SYSTEM",
        "sections": [
            {"letter": "A", "title": "AIR TERMINALS AND DOWN CONDUCTORS", "subsection": "", "items": [
                {"desc": "Copper air-terminal rod (1m, 16mm dia)", "unit": "No.",  "qty": 4, "basic":  450, "spec": "BS EN 62305"},
                {"desc": "25 x 3mm copper tape down conductor",    "unit": "m",    "qty":80, "basic":   42, "spec": "Hard-drawn copper"},
                {"desc": "Roof + wall tape clips",                  "unit": "No.",  "qty":40, "basic":   12, "spec": ""},
            ]},
            {"letter": "B", "title": "EARTHING", "subsection": "", "items": [
                {"desc": "Copper-bonded earth rod (1.5m)",         "unit": "No.",  "qty": 4, "basic":  280, "spec": "16mm dia"},
                {"desc": "Inspection pit + clamp",                 "unit": "No.",  "qty": 4, "basic":  650, "spec": ""},
            ]},
        ],
    },
    "earthing_bonding": {
        "name": "EQUIPOTENTIAL EARTHING AND BONDING",
        "sections": [
            {"letter": "A", "title": "MAIN EARTHING TERMINAL", "subsection": "", "items": [
                {"desc": "Main earth bar (copper, drilled)",      "unit": "No.",  "qty": 1, "basic":  850, "spec": "Insulated, lockable"},
                {"desc": "70mm² PVC copper earth conductor",      "unit": "m",    "qty":40, "basic":   95, "spec": "Green/yellow"},
                {"desc": "Earth rod 1.5m + boss + clamp",         "unit": "No.",  "qty": 3, "basic":  320, "spec": ""},
            ]},
            {"letter": "B", "title": "BONDING", "subsection": "", "items": [
                {"desc": "Equipotential bonding to services",     "unit": "Lot",  "qty": 1, "basic": 1200, "spec": "Water, gas, structural steel"},
            ]},
        ],
    },
    "ip_cctv": {
        "name": "IP CCTV SYSTEM",
        "sections": [
            {"letter": "A", "title": "CAMERAS AND RECORDER", "subsection": "", "items": [
                {"desc": "5MP IP dome camera (PoE)",              "unit": "No.",  "qty": 8, "basic": 1450, "spec": "H.265, IK10, IR 30m"},
                {"desc": "5MP IP bullet camera (PoE)",            "unit": "No.",  "qty": 4, "basic": 1550, "spec": "H.265, IP67, IR 50m"},
                {"desc": "16-channel NVR + 4TB HDD",              "unit": "No.",  "qty": 1, "basic": 6500, "spec": "RAID-1 / motion-search"},
                {"desc": "23\" LED monitor",                     "unit": "No.",  "qty": 1, "basic": 1200, "spec": "Full HD"},
            ]},
        ],
    },
    "nurse_call": {
        "name": "NURSE CALL SYSTEM",
        "sections": [
            {"letter": "A", "title": "PANEL AND BEDSIDE UNITS", "subsection": "", "items": [
                {"desc": "Nurse call master station",             "unit": "No.",  "qty": 1, "basic": 5500, "spec": "Wired, IP65 backbox"},
                {"desc": "Bedside call point + pull cord",        "unit": "No.",  "qty":12, "basic":  280, "spec": "Push + reset"},
                {"desc": "Corridor over-door indicator",          "unit": "No.",  "qty": 6, "basic":  220, "spec": "Red/green LED"},
                {"desc": "Staff staff-presence override key",     "unit": "No.",  "qty": 6, "basic":   90, "spec": ""},
            ]},
        ],
    },
    "ip_pa": {
        "name": "IP PA AND PUBLIC ADDRESS SYSTEM",
        "sections": [
            {"letter": "A", "title": "AMPLIFIER AND SPEAKERS", "subsection": "", "items": [
                {"desc": "120W IP PA amplifier",                  "unit": "No.",  "qty": 1, "basic": 4500, "spec": "100V line, zone-paging"},
                {"desc": "Ceiling speaker 6W (100V)",             "unit": "No.",  "qty":18, "basic":  180, "spec": "Fire-rated dome"},
                {"desc": "Paging microphone (push-to-talk)",      "unit": "No.",  "qty": 1, "basic":  850, "spec": ""},
            ]},
        ],
    },
    "bms": {
        "name": "BUILDING MANAGEMENT SYSTEM (BMS)",
        "sections": [
            {"letter": "A", "title": "CONTROLLERS AND I/O", "subsection": "", "items": [
                {"desc": "BACnet/IP DDC controller",              "unit": "No.",  "qty": 2, "basic": 5500, "spec": "32 UI / 16 UO"},
                {"desc": "Field I/O module (8AI / 8DI / 8DO)",   "unit": "No.",  "qty": 4, "basic": 1800, "spec": "BACnet MSTP"},
                {"desc": "BMS server PC + license",               "unit": "Lot",  "qty": 1, "basic":11500, "spec": "100 BACnet points"},
            ]},
            {"letter": "B", "title": "SENSORS AND ACTUATORS", "subsection": "", "items": [
                {"desc": "Duct temperature sensor",               "unit": "No.",  "qty":12, "basic":  140, "spec": "NTC10K"},
                {"desc": "Motorised damper actuator",             "unit": "No.",  "qty": 8, "basic":  850, "spec": "24V 5Nm"},
            ]},
        ],
    },
}


def _inject_service_bills(template: dict, chosen_services: list) -> dict:
    """Return a copy of ``template`` with extra bills appended for any chosen
    service the template doesn't already cover.

    The injected bills carry bill numbers starting at ``max(existing_no) + 1``
    so the existing numbering is preserved (auditorium-1ugls has bills 1..6 --
    injected bills start at 7+).
    """
    existing_codes = set(_template_services(template))
    missing = [s for s in chosen_services
               if s in _BOQ_SERVICE_BILL_SKELETON and s not in existing_codes]
    if not missing:
        return template
    # Deep-ish copy so mutations don't bleed back to _BOQ_PROJECT_TEMPLATES.
    out = {
        "name":        template["name"],
        "purpose":     template["purpose"],
        "subtype":     template["subtype"],
        "description": template["description"],
        "bills":       [dict(b, sections=list(b.get("sections", []))) for b in template["bills"]],
    }
    next_no = max((b["no"] for b in out["bills"]), default=0) + 1
    for svc in missing:
        skel = _BOQ_SERVICE_BILL_SKELETON[svc]
        out["bills"].append({
            "no": next_no,
            "name": skel["name"],
            "sections": [dict(s) for s in skel["sections"]],
            "_injected_service": svc,
        })
        next_no += 1
    out["_services_injected"] = missing
    return out


def _services_csv_to_list(csv: str) -> list:
    """Split boq_projects.services_csv into a clean list of known codes."""
    if not csv:
        return []
    out = []
    for tok in (csv or "").split(","):
        t = tok.strip()
        if t and t in _BOQ_SERVICE_LABEL and t not in out:
            out.append(t)
    return out


def _services_label_list(codes: list) -> list:
    """Map a list of service codes to their human labels (order preserved)."""
    return [_BOQ_SERVICE_LABEL[c] for c in codes if c in _BOQ_SERVICE_LABEL]

# === END: boq_services_engine splice ===
