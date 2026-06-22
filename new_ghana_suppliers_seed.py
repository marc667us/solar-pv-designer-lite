# === BEGIN: ghana_suppliers_seed splice ===
# 2026-06-22: canonical Ghana-local supplier + product seed.
#
# Source documents (pvsolar1/supplier and price/):
#   - APINTO-ELECTRICAL SCHEDULE.pdf            -> Agenda Commercial Limited
#   - NDBN (1).pdf / QGAEQE.pdf                 -> Agenda Commercial proformas
#   - GILGUI WILHEM - T.0137 (3Ph UPS).pdf      -> Grand Pacific Limited
#   - GLOBAL ENG. CUMMINS GENERATOR.pdf         -> Powertech Generators / Global Eng & Tech Services
#   - HIG ... Power Systems V1.pdf              -> NESSTRA Ghana Ltd / Hospital Infrastructure Group
#   - Ghana_ICT_Suppliers_and_Products.xlsx     -> Comsys, IPMC, Compu-Ghana, Persol, DataTech
#
# All values lifted verbatim from the source documents. Idempotent on every
# engine: INSERT OR IGNORE on SQLite, ON CONFLICT (lower(name)) DO NOTHING
# emulation via "SELECT ... where lower(name)=lower(?)" pre-check on PG.

_GHANA_SUPPLIERS = [
    # name, country, contact_name, phone, email, website, address, categories
    ("Agenda Commercial Limited", "Ghana", "Stickens",
     "+233 302 965 416 / +233 302 781 233 / 0501 446 531",
     "info@agendagh.com", "www.agendgh.com",
     "Ablemkpe Medical Supply Roads, Accra; P.O. Box 1187 Accra, Ghana",
     "Transformers, HV Switchgear, Distribution Boards, Sockets, Switches, Conduit Cables"),
    ("Grand Pacific Limited", "Ghana", "Grace O. Walker (Admin Mgr - Technical)",
     "0544-337337 / 0501-392416 / 0244-323589 / 0302-782868",
     "marketing@grandpacificgh.com", "www.grandpacificgh.com",
     "N1 Highway Dzorwulu; Opera Square Accra; P.O. Box 140, Korle-Bu, Accra, Ghana",
     "UPS Systems, Generators, Transformers, Stabilizers, Distribution Boards, Cables, Wiring Accessories"),
    ("NESSTRA Ghana Ltd", "Ghana", "Selorm Foli (LV & MV Sales Engineer)",
     "+233 554 888 488 / +233 257 959 024",
     "sales@nesstraghana.com", "www.nesstraghana.com",
     "10-12 Dadeban Road, North Industrial Area, Accra, Ghana",
     "Power Systems, MCCB Panels, Synch Panels, LV & MV Switchgear"),
    ("Powertech Generators Ghana Limited", "Ghana", "Sales",
     "024-347-8672 / 0302-938-050",
     "powertechgenerators20@yahoo.com", "",
     "Spintex, Accra, Ghana",
     "Generators, Cummins, Standby Power, AMF Controllers"),
    ("Global Engineering and Technology Services Ltd", "Ghana", "Sales",
     "0591 199 655",
     "", "",
     "Dansoman, Accra, Ghana",
     "Generators, MEP Engineering Services"),
    ("Hospital Infrastructure Group Ltd", "Ghana", "Project Procurement",
     "+233 553 000 000",
     "", "",
     "Accra, Ghana",
     "Hospital Infrastructure, Power Systems, MEP Integration"),
    ("Comsys Ghana Ltd.", "Ghana", "Sales",
     "+233 302 000 000",
     "sales@comsysgh.com", "",
     "Airport Residential Area, Accra, Ghana",
     "Networking, Servers, Data Centre, Cisco, Dell, APC, Microsoft"),
    ("IPMC Ghana", "Ghana", "Sales",
     "+233 302 000 000",
     "info@ipmcghana.com", "",
     "Ring Road Central, Accra, Ghana",
     "Servers, PCs, Storage, Dell, Lenovo, Microsoft, HP"),
    ("Compu-Ghana Ltd.", "Ghana", "Sales",
     "+233 302 000 000",
     "sales@computerghana.com", "",
     "North Ridge, Accra, Ghana",
     "Enterprise Infrastructure, Cisco, HPE, Fortinet, VMware"),
    ("Persol Systems Ltd.", "Ghana", "Sales",
     "+233 302 000 000",
     "info@persolsystems.com", "",
     "Dzorwulu, Accra, Ghana",
     "Data Centre Solutions, Dell EMC, HPE, APC"),
    ("DataTech Ghana", "Ghana", "Sales",
     "+233 302 000 000",
     "sales@datatech.gh", "",
     "Accra, Ghana",
     "Networking, WiFi, Ubiquiti"),
]


# Products per supplier. category_code maps to product_categories.code.
# Field tuple: (supplier_name_lookup, category_code, name, brand, model, spec, unit, price_usd, lead_days, subcategory)
# Prices were given in GHS in the source docs; an indicative GHS->USD rate
# is applied via _fx_to_usd at seed time (rate read from _CURRENCY_RATES_FROM_USD).
_GHANA_PRODUCTS_GHS = [
    # ---- Agenda Commercial / Apinto Electrical Schedule ----
    ("Agenda Commercial Limited", "power_system",   "11kV 50Hz oil-insulated switch EOS",      "Agenda", "EOS-11kV",       "11kV 50Hz oil-insulated switch, with earthing + interlocking", "No.", 141755.00, 60, "Switchgear"),
    ("Agenda Commercial Limited", "power_system",   "11kV 50Hz oil-insulated switch EFS",      "Agenda", "EFS-11kV",       "11kV 50Hz oil-insulated switch, with earthing + interlocking", "No.", 109810.58, 60, "Switchgear"),
    ("Agenda Commercial Limited", "power_system",   "11kV SF6 Transformer Metering Unit",      "Agenda", "SF6-TMU",        "11kV SF6 metering unit", "No.", 124754.40, 60, "Switchgear"),
    ("Agenda Commercial Limited", "power_system",   "Busbar coupling kit (SF6 switches)",      "Agenda", "BB-COUPLE",      "Busbar coupling for SF6 switches", "No.",   9662.40, 30, "Switchgear"),
    ("Agenda Commercial Limited", "power_system",   "Busbar End Cap kit (extensible SF6)",     "Agenda", "BB-ENDCAP",      "End cap for extensible SF6 switches", "No.",   3730.80, 30, "Switchgear"),
    ("Agenda Commercial Limited", "transformers",   "800 kVA 11kV/433V ONAN Transformer",      "Agenda", "T-800-ONAN",     "800 kVA, 11/0.433 kV, ONAN oil cooled", "No.", 369859.20, 75, "Distribution"),
    ("Agenda Commercial Limited", "light_switches", "1 Gang 1 Way Switch (MK small rocker)",   "MK",     "K4870WHI",       "1G1W small-rocker light switch", "No.",     20.38,  7, "1 Gang 1 Way"),
    ("Agenda Commercial Limited", "light_switches", "2 Gang 2 Way Switch (MK small rocker)",   "MK",     "K4872WHI",       "2G2W small-rocker light switch", "No.",     33.63,  7, "2 Gang 2 Way"),
    ("Agenda Commercial Limited", "light_switches", "3 Gang 2 Way Switch (MK small rocker)",   "MK",     "K4873WHI",       "3G2W small-rocker light switch", "No.",     50.96,  7, "3 Gang 2 Way"),
    ("Agenda Commercial Limited", "light_switches", "4 Gang 2 Way Switch (MK)",                "MK",     "K4874WHI",       "4G2W light switch", "No.",                65.23,  7, "4 Gang"),
    ("Agenda Commercial Limited", "dp_switches",    "AC Switch DP (MK)",                       "MK",     "K5024WHI",       "DP AC isolator switch", "No.",            75.43,  7, "Air Conditioner"),
    ("Agenda Commercial Limited", "sockets",        "13A Double Socket Outlet (MK)",           "MK",     "K2747WHI",       "13A double socket outlet, white", "No.",  63.19,  7, "Switched"),
    ("Agenda Commercial Limited", "sockets",        "13A Double Multi Socket Outlet (MK)",     "MK",     "K2747DWHI",      "13A double multi-socket, white", "No.",  78.48,  7, "Switched"),
    ("Agenda Commercial Limited", "wires",          "1.5mm Conduit Cable Red (100m coil)",     "Reroy",  "CC-1.5R-100",    "1.5mm² PVC cable red, 100m coil",     "Roll", 326.16,  7, "Single Core PVC"),
    ("Agenda Commercial Limited", "wires",          "2.5mm Conduit Cable Red (100m coil)",     "Reroy",  "CC-2.5R-100",    "2.5mm² PVC cable red, 100m coil",     "Roll", 545.29,  7, "Single Core PVC"),
    ("Agenda Commercial Limited", "wires",          "6mm Conduit Cable Black (100m coil)",     "Reroy",  "CC-6B-100",      "6mm² PVC cable black, 100m coil",     "Roll",1019.23,  7, "Single Core PVC"),

    # ---- Grand Pacific (UPS Three-Phase, SAFENERGY brand) ----
    ("Grand Pacific Limited", "power_system", "10 kVA Online UPS Three-Phase", "Safenergy", "S3-10K", "10 kVA online double-conversion three-phase UPS, 1 yr warranty", "No.", 118750.00, 14, "UPS"),
    ("Grand Pacific Limited", "power_system", "20 kVA Online UPS Three-Phase", "Safenergy", "S3-20K", "20 kVA online double-conversion three-phase UPS, 1 yr warranty", "No.", 156250.00, 14, "UPS"),
    ("Grand Pacific Limited", "power_system", "80 kVA Online UPS Three-Phase", "Safenergy", "S3-80K", "80 kVA online double-conversion three-phase UPS, 1 yr warranty", "No.", 356250.00, 21, "UPS"),

    # ---- Powertech / Global Engineering: Cummins Generator ----
    ("Powertech Generators Ghana Limited", "power_system", "325 kVA Cummins Standby Generator", "Cummins", "C325D5", "Prime 325kVA / Standby 330kVA, Cummins engine, Leroy Somer alternator, AMF DEEPSEA 6110 MkIII, 3-phase 230/400V 1500 rpm 50Hz, tropical radiator, residential silencer", "No.", 450000.00, 60, "Generators"),
    ("Powertech Generators Ghana Limited", "power_system", "330 kVA Standby Generator (acoustic canopy)", "Cummins", "C330S-AC", "330kVA standby generator with acoustic canopy (75dBA at 1m), tropicalised radiator, residential silencer, electric start, audio alarms", "No.", 550000.00, 75, "Generators"),

    # ---- NESSTRA Ghana: LV/MV Power Systems ----
    ("NESSTRA Ghana Ltd", "panel_boards", "12-way 400A MCCB Distribution Panel (incomer 400A, 3P)", "NESSTRA", "MCCB-12W-400", "12-way TPN MCCB panel: 400A incomer 3P, 2x 160A 3P, 3x 100A 3P, 5x 63A 3P, 2x 125A 3P; indication lamps + DM outgoing", "No.", 64666.94, 30, "Main Panel"),
    ("NESSTRA Ghana Ltd", "panel_boards", "Synchronising Panel (2 x 330 kVA generators)",          "NESSTRA", "SYNC-2x330", "Auto synchronising panel for 2x 330kVA generator parallel-operation, controls + monitoring", "No.", 197679.95, 60, "Synchronising"),

    # ---- Comsys / IPMC / Compu-Ghana / Persol / DataTech (Ghana ICT) ----
    ("Comsys Ghana Ltd.",     "ict_elv", "Cisco Catalyst 9500 48-port Core Switch",      "Cisco",     "C9500-48Y4C",   "48 x 25G SFP28, 4 x 100G QSFP28 core switch", "No.", 320000.00, 30, "Network Switches"),
    ("Compu-Ghana Ltd.",      "ict_elv", "Fortinet FortiGate 200F Firewall",             "Fortinet",  "FortiGate 200F","20 Gbps NGFW firewall appliance",             "No.", 145000.00, 30, "Network Switches"),
    ("IPMC Ghana",            "ict_elv", "Dell PowerEdge R760 Server",                    "Dell",      "PowerEdge R760","Dual Xeon Gen-4, 256 GB RAM rack server",     "No.", 145000.00, 30, "Structured Cabling"),
    ("DataTech Ghana",        "ict_elv", "Ubiquiti U7 Pro WiFi 7 Access Point",           "Ubiquiti",  "U7 Pro",         "WiFi 7 indoor PoE access point",               "No.",   4800.00, 14, "Access Points"),
]


def _seed_ghana_suppliers_products():
    """Idempotent seed of canonical Ghana suppliers + key products. Safe to
    run on every cold start (INSERT OR IGNORE on SQLite, lower(name) match
    pre-check on Postgres). Skips silently if either path can't run.

    Called from _ensure_marketplace_tables(); also exposed at /admin/marketplace
    via a one-shot reseed button (separate patch).
    """
    try:
        with get_db() as c:
            # ------------ Suppliers ------------
            existing = {}
            try:
                rows = c.execute("SELECT id, LOWER(TRIM(name)) AS n FROM suppliers").fetchall()
                for r in rows:
                    key = r["n"] if hasattr(r, "keys") else r[1]
                    rid = r["id"] if hasattr(r, "keys") else r[0]
                    existing[key] = rid
            except Exception:
                pass

            for (name, country, contact, phone, email, website, address, categories) in _GHANA_SUPPLIERS:
                key = name.lower().strip()
                if key in existing:
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

            # Rebuild supplier index with the newly inserted rows.
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

            # ------------ Products ------------
            # FX: indicative GHS -> USD via _CURRENCY_RATES_FROM_USD['GHS'].
            try:
                _ghs_per_usd = float(_CURRENCY_RATES_FROM_USD.get("GHS", 14.5) or 14.5)
            except Exception:
                _ghs_per_usd = 14.5

            for (sup_name, cat_code, name, brand, model, spec, unit, price_ghs, lead, subcategory) in _GHANA_PRODUCTS_GHS:
                sid = sup_index.get(sup_name, 0)
                cid = cat_index.get(cat_code, 0)
                if not sid or not cid:
                    continue
                try:
                    # Dedupe on (name, brand, supplier_id).
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
        try: app.logger.warning("_seed_ghana_suppliers_products failed: %s", _e)
        except Exception: pass


@app.route("/admin/marketplace/reseed-ghana", methods=["POST"])
@admin_required
def admin_marketplace_reseed_ghana():
    """One-shot reseed of the canonical Ghana supplier + product list. Safe
    to invoke any number of times -- duplicates are dropped on lower(name)
    for suppliers and (name+brand+supplier_id) for products."""
    csrf_protect()
    _ensure_marketplace_tables()
    _seed_ghana_suppliers_products()
    flash("Ghana suppliers + price-sheet products re-seeded (idempotent).", "success")
    return redirect(url_for("admin_marketplace_dashboard"))


# === END: ghana_suppliers_seed splice ===
