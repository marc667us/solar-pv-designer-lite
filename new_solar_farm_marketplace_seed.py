# new_solar_farm_marketplace_seed.py
# Generation-Station "Solar Farm Equipment BOQ" -- SLICE 1: seed the marketplace
# gaps so every solar-farm BOQ line has a priceable product match (else BOQ
# shows "item not available"). Owner 2026-07-04.
#
# Adds two categories (Circuit Breakers, Plant Control & SCADA), an IPS +
# Battery Chargers subcategory under the existing Power System category, and
# ~31 sample products with ACCURATE Ghana-market pricing (duty/VAT/clearing-
# inclusive, researched), stored as USD via the app's 11.2 GHS/USD rate so the
# marketplace displays the real Ghana price.
#
# The four marketplace registries are mutable module-level globals defined
# earlier in web_app.py; this block runs at import time (spliced before the
# __main__ guard, after every definition) and extends them idempotently, so the
# runtime category-seed loop (ON CONFLICT DO NOTHING, both backends) picks up
# the new categories on cold start for existing databases too.

# --- 1. Extend the taxonomy registries (idempotent) -------------------------
_SF_NEW_CATEGORIES = [
    # (code, name, icon, display_order)
    ("circuit_breakers", "Circuit Breakers",       "bi-toggles",   220),
    ("plant_control",    "Plant Control & SCADA",  "bi-diagram-3", 230),
]
_sf_existing_codes = {row[0] for row in _MARKETPLACE_CATEGORIES}
for _entry in _SF_NEW_CATEGORIES:
    if _entry[0] not in _sf_existing_codes:
        _MARKETPLACE_CATEGORIES.append(_entry)

_MARKETPLACE_SUBCATEGORIES.setdefault("circuit_breakers", [
    "MCB", "MCCB", "RCCB", "RCBO", "ACB", "MPCB",
    "DC MCB", "DC MCCB", "DC Breaker", "Fuse Carrier",
])
_MARKETPLACE_SUBCATEGORIES.setdefault("plant_control", [
    "SCADA System", "Power Plant Controller", "Weather Station", "RTU",
    "HMI Panel", "Energy Meter", "Communication Gateway", "Data Logger",
])
# IPS (instrument power supply) + battery chargers live beside UPS.
if "IPS" not in _MARKETPLACE_SUBCATEGORIES.get("power_system", []):
    _MARKETPLACE_SUBCATEGORIES["power_system"] = (
        _MARKETPLACE_SUBCATEGORIES.get("power_system", []) + ["IPS", "Battery Chargers"]
    )

_MARKETPLACE_DEFAULT_UNIT.setdefault("circuit_breakers", "No.")
_MARKETPLACE_DEFAULT_UNIT.setdefault("plant_control", "No.")

_MARKETPLACE_SPEC_FIELDS.setdefault("circuit_breakers", [
    "Current rating", "Number of poles", "Breaking capacity", "Voltage rating",
    "Trip curve / unit", "Type (AC/DC)", "Mounting",
])
_MARKETPLACE_SPEC_FIELDS.setdefault("plant_control", [
    "Function", "Communication protocol", "IO / points", "Power supply",
    "Enclosure / IP rating", "Standards",
])

# --- 2. Sample products with Ghana-market pricing ---------------------------
# (cat_code, subcategory, name, brand, model, spec, unit, price_usd, lead_days)
# price_usd = researched Ghana GHS price / 11.2 (the app's GHS/USD rate), so the
# displayed GHS figure reflects the actual duty/VAT/clearing-inclusive Ghana
# price. Industrial items (ACB/SCADA/PPC/IPS/RTU) are equipment-only; integrator
# engineering, commissioning and civils are excluded (as in a real BOQ line).
_SOLAR_FARM_GAP_PRODUCTS = [
    # ---- AC MCBs ----
    ("circuit_breakers", "MCB",  "MCB 1P 6A Type C 6kA",   "Schneider", "A9F74106", "1P, 6A, type C, 6kA, Acti9 iC60N",       "No.",     5.80, 14),
    ("circuit_breakers", "MCB",  "MCB 1P 16A Type C 6kA",  "Schneider", "A9F74116", "1P, 16A, type C, 6kA, Acti9 iC60N",      "No.",     6.25, 14),
    ("circuit_breakers", "MCB",  "MCB 1P 32A Type C 6kA",  "Schneider", "A9F74132", "1P, 32A, type C, 6kA, Acti9 iC60N",      "No.",     7.59, 14),
    ("circuit_breakers", "MCB",  "MCB 1P 63A Type C 6kA",  "Schneider", "A9F74163", "1P, 63A, type C, 6kA, Acti9 iC60N",      "No.",    12.05, 14),
    ("circuit_breakers", "MCB",  "MCB 3P 32A Type C 6kA",  "Schneider", "A9F74332", "3P, 32A, type C, 6kA, Acti9 iC60N",      "No.",    22.32, 14),
    ("circuit_breakers", "MCB",  "MCB 3P 63A Type C 6kA",  "Schneider", "A9F74363", "3P, 63A, type C, 6kA, Acti9 iC60N",      "No.",    30.36, 14),
    # ---- MCCBs ----
    ("circuit_breakers", "MCCB", "MCCB 3P 100A 36kA",      "Schneider", "LV510333", "3P, 100A, Icu 36kA @415V, TMD, EasyPact CVS100B", "No.",  169.64, 21),
    ("circuit_breakers", "MCCB", "MCCB 3P 250A 36kA",      "Schneider", "LV525303", "3P, 250A, Icu 36kA, TMD, EasyPact CVS250B",       "No.",  383.93, 21),
    ("circuit_breakers", "MCCB", "MCCB 4P 400A 50kA",      "Schneider", "LV432693", "4P, 400A, Icu 50kA, Micrologic 2.3, ComPact NSX400N", "No.", 821.43, 30),
    ("circuit_breakers", "MCCB", "MCCB 4P 630A 50kA",      "Schneider", "LV432894", "4P, 630A, Icu 50kA, Micrologic 2.3, ComPact NSX630N", "No.", 1294.64, 30),
    # ---- RCCB / RCBO ----
    ("circuit_breakers", "RCCB", "RCCB 2P 40A 30mA Type AC", "Schneider", "A9R71240", "2P, 40A, 30mA, type AC, Acti9 iID",     "No.",    32.14, 14),
    ("circuit_breakers", "RCCB", "RCCB 4P 63A 30mA Type AC", "Schneider", "A9R71463", "4P, 63A, 30mA, type AC, Acti9 iID",     "No.",    60.71, 14),
    ("circuit_breakers", "RCBO", "RCBO 1P+N 32A 30mA 6kA",   "Schneider", "A9D31632", "1P+N, 32A, type C, 30mA, 6kA, Acti9",   "No.",    29.46, 14),
    # ---- ACBs ----
    ("circuit_breakers", "ACB",  "ACB 3P 800A 65kA fixed",   "Schneider", "MTZ108H1", "3P, 800A, Icu 65kA, fixed, Micrologic 2.0, MasterPact MTZ1", "No.", 2410.71, 60),
    ("circuit_breakers", "ACB",  "ACB 4P 1600A draw-out",    "Schneider", "MTZ216N1", "4P, 1600A, Icu 50kA, draw-out, Micrologic 5.0, MasterPact MTZ2", "No.", 4821.43, 75),
    ("circuit_breakers", "ACB",  "ACB 4P 2500A draw-out",    "Schneider", "MTZ225N1", "4P, 2500A, Icu 50-66kA, draw-out, Micrologic 5.0, MasterPact MTZ2", "No.", 7857.14, 90),
    # ---- Motor protection ----
    ("circuit_breakers", "MPCB", "MPCB 0.16-25A adjustable", "Schneider", "GV2ME-RANGE", "3P motor circuit protector, adjustable to 25A, TeSys GV2", "No.", 64.29, 21),
    # ---- DC breakers (solar / BESS) ----
    ("circuit_breakers", "DC MCB",     "DC MCB 1P 16A 500VDC PV",  "CHINT",     "NB1-63DC-16", "1P, 16A, 500VDC, PV string protection", "No.",    14.29, 21),
    ("circuit_breakers", "DC MCB",     "DC MCB 2P 32A 1000VDC",    "Schneider", "A9N61653",    "2P, 32A, 1000VDC, Acti9 C60H-DC",       "No.",    32.14, 21),
    ("circuit_breakers", "DC MCB",     "DC MCB 2P 63A 1000VDC",    "Schneider", "A9N61658",    "2P, 63A, 1000VDC, Acti9 C60H-DC",       "No.",    44.64, 21),
    ("circuit_breakers", "DC MCCB",    "DC MCCB 250A 1000VDC",     "Schneider", "NSX250-DCPV", "250A, 1000VDC, battery/BESS duty, ComPact NSX DC-PV", "No.", 607.14, 45),
    ("circuit_breakers", "DC Breaker", "DC Breaker 630A 1500VDC",  "ABB",       "XT-DC-630",   "630A, 1500VDC, BESS main isolation, Tmax XT DC",  "No.", 2232.14, 60),
    # ---- IPS (into existing power_system category) ----
    ("power_system", "IPS", "IPS 110VDC 20A + Battery Bank",  "Benning",  "ENERTRONIC-110-20", "110VDC substation DC system, 20A charger + VRLA bank + DC distribution", "No.", 10267.86, 75),
    ("power_system", "IPS", "IPS 220VDC 40A Industrial DC",   "Statron",  "ARE-N-220-40",      "220VDC industrial DC system, redundant 40A chargers + battery + DC board", "No.", 17857.14, 90),
    # ---- Plant control / SCADA ----
    ("plant_control", "Power Plant Controller", "Solar Power Plant Controller (PPC)", "Huawei",   "SMART-PPC",     "Utility PV plant controller, P/Q/PF + grid-code compliance (SmartLogger3000 + Smart Power Sensor)", "No.", 22321.43, 90),
    ("plant_control", "SCADA System",           "Utility Solar SCADA Server + Software", "Schneider", "ECOSTRUXURE-SCADA", "Utility solar SCADA: redundant server, HMI, historian, licenses", "No.", 80357.14, 120),
    ("plant_control", "Weather Station",         "Solar Met/Weather Station (Class A)", "Ammonit",  "METEO-40-PV",   "IEC 61724-1 Class A: pyranometer (irradiance) + ambient/module temp + wind", "No.", 16517.86, 75),
    ("plant_control", "RTU",                     "Grid-Interface RTU (IEC 61850/DNP3)", "Schneider", "SAITEL-DR",     "Remote terminal unit for utility grid interface, IEC 61850 / DNP3", "No.", 10267.86, 75),
    ("plant_control", "HMI Panel",               "Industrial HMI Touchscreen 15in",     "Schneider", "HMIGTU-15",     "15in industrial HMI, PCAP, Ethernet/Modbus, Harmony GTU", "No.", 3392.86, 45),
    ("plant_control", "Energy Meter",            "Revenue/Check Energy Meter 3P MID",   "Schneider", "ION9000",       "3P MID revenue meter, class 0.2S, power quality, PowerLogic ION9000", "No.", 4464.29, 30),
    ("plant_control", "Communication Gateway",   "Protocol Gateway Modbus/IEC 61850",   "Schneider", "LINK150-GW",    "Modbus TCP/RTU to IEC 61850 protocol gateway/data logger", "No.", 4642.86, 30),
]


def _seed_solar_farm_gap_products():
    """Idempotently seed the solar-farm BOQ gap products (AC + DC circuit
    breakers, IPS, plant-control/SCADA) into equipment_catalog so every
    generation-station BOQ line has a priceable marketplace match. Each row is
    skipped if a product with the same brand+model already exists, so it is safe
    on every cold start and never duplicates. Opens its own db connection like
    the sibling seeders. Inputs: none. Output: none (writes equipment_catalog).
    price_usd values are Ghana GHS prices / 11.2 so the displayed local price is
    accurate. `is_public_visible=1` keeps them on the public marketplace."""
    try:
        with get_db() as c:
            # Serialize this one-time seed across concurrent cold-start workers.
            # equipment_catalog has no UNIQUE(brand,model) arbiter, so under
            # Postgres READ COMMITTED two workers could otherwise both pass the
            # WHERE NOT EXISTS and double-insert. A transaction-scoped advisory
            # lock is held until this `with get_db()` block commits (psycopg2
            # autocommit is off; _PgConnAdapter.__exit__ commits), then
            # auto-releases -- so the losing worker blocks, then sees the
            # committed rows and inserts nothing. No-op on SQLite (function
            # absent -> caught; SQLite serializes writers anyway).
            try:
                c.execute("SELECT pg_advisory_xact_lock(?)", (760741042,))
            except Exception:
                pass
            # Ensure the two new categories exist first (order-independent: does
            # not rely on the runtime category-seed loop having run yet). code is
            # UNIQUE, so ON CONFLICT DO NOTHING is fully race-safe against a
            # concurrent cold-start worker (same idiom the runtime loop uses).
            for _code, _name, _icon, _order in _SF_NEW_CATEGORIES:
                c.execute(
                    "INSERT INTO product_categories (code, name, icon, display_order) "
                    "VALUES (?,?,?,?) ON CONFLICT (code) DO NOTHING",
                    (_code, _name, _icon, _order))
            cats = {r["code"]: r["id"] for r in c.execute(
                "SELECT id, code FROM product_categories").fetchall()}
            sup_rows = {r["name"]: r["id"] for r in c.execute(
                "SELECT id, name FROM suppliers").fetchall()}
            sup_id = 0
            for pref in ("APT Ghana", "Tricord Limited", "RS Components",
                         "Schneider Electric"):
                if pref in sup_rows:
                    sup_id = sup_rows[pref]; break
            if not sup_id and sup_rows:
                sup_id = sorted(sup_rows.values())[0]
            code_to_label = {row[0]: row[1] for row in _MARKETPLACE_CATEGORIES}
            for (code, sub, name, brand, model, spec, unit, price_usd, lt) in _SOLAR_FARM_GAP_PRODUCTS:
                cat_id = cats.get(code, 0)
                # Atomic idempotent insert: INSERT ... SELECT ... WHERE NOT EXISTS
                # collapses the SELECT-then-INSERT into ONE statement so a
                # concurrent cold-start worker cannot double-insert the same
                # (brand, model). Works on SQLite + Postgres; db_adapter maps
                # ? -> %s. (equipment_catalog has no UNIQUE(brand,model) to add
                # retroactively without risking existing dupes, so this is the
                # correct race-narrowing idiom here.)
                c.execute(
                    "INSERT INTO equipment_catalog (category, name, brand, model, spec, "
                    "unit, price_usd, supplier_id, lead_time_days, category_id, "
                    "subcategory, is_public_visible) "
                    "SELECT ?,?,?,?,?,?,?,?,?,?,?,1 "
                    "WHERE NOT EXISTS (SELECT 1 FROM equipment_catalog WHERE brand=? AND model=?)",
                    (code_to_label.get(code, ""), name, brand, model, spec, unit,
                     price_usd, sup_id, lt, cat_id, sub, brand, model))
    except Exception as e:
        try: app.logger.warning("solar-farm gap product seed failed: %s", e)
        except Exception: pass
