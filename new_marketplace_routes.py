# ─── Routes — Public Electrical Marketplace ───────────────────────────────────
# Magnet feature: free public browse of electrical products + prices + suppliers.
# Anonymous visitors see prices and supplier names; action buttons (RFQ, compare,
# download) gate on /register so the marketplace funnels into solar signups.
#
# Reuses the existing `equipment_catalog` and `suppliers` tables (added via
# ALTER TABLE ADD COLUMN below, with IF NOT EXISTS semantics). Existing solar
# items keep working; new electrical items use the richer 18-category taxonomy.

_MARKETPLACE_CATEGORIES = [
    # (code, name, icon, display_order)
    ("transformers",      "Transformers",                     "bi-lightning-charge",  10),
    ("avr",               "Voltage Regulators / AVR",         "bi-arrow-up-down",     20),
    ("hv_cables",         "HV Power Cables",                  "bi-plug",              30),
    ("lv_cables",         "LV Power Cables",                  "bi-plug",              40),
    ("wires",             "Electrical Wires",                 "bi-three-dots",        50),
    ("panel_boards",      "Panel Boards",                     "bi-grid-3x3",          60),
    ("distribution_boards", "Distribution Boards",            "bi-grid",              70),
    ("isolators",         "Isolators",                        "bi-shield",            80),
    ("fuse_switches",     "Fuse Switches",                    "bi-shield-exclamation", 90),
    ("conduit",           "Conduit Pipes",                    "bi-record-circle",    100),
    ("steel_boxes",       "Steel Square Boxes",               "bi-square",           110),
    ("circular_boxes",    "Circular Boxes",                   "bi-circle",           120),
    ("cable_trays",       "Cable Trays",                      "bi-bricks",           130),
    ("trunking",          "Plastic Trunking",                 "bi-distribute-horizontal", 140),
    ("earthing",          "Earthing Materials",               "bi-arrow-down",       150),
    ("sockets",           "13A Socket Outlets",               "bi-outlet",           160),
    ("dp_switches",       "20A DP Switches",                  "bi-toggle-on",        170),
    ("light_switches",    "Light Switches",                   "bi-lightbulb",        180),
    ("solar_equipment",   "Solar Equipment",                  "bi-sun",              190),
    ("ict_elv",           "ICT / ELV Products",               "bi-router",           200),
]


def _ensure_marketplace_tables():
    """Idempotent — runs on every marketplace route hit. Cheap (CREATE IF NOT EXISTS)."""
    with get_db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS product_categories (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                code          TEXT UNIQUE NOT NULL,
                name          TEXT NOT NULL,
                icon          TEXT DEFAULT 'bi-box',
                display_order INTEGER DEFAULT 0,
                is_active     INTEGER DEFAULT 1,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_product_categories_order
                ON product_categories(display_order);
            """
        )
        # Extend equipment_catalog with marketplace fields (idempotent — PRAGMA check first).
        cols = {r["name"] for r in c.execute("PRAGMA table_info(equipment_catalog)").fetchall()}
        if "category_id" not in cols:
            c.execute("ALTER TABLE equipment_catalog ADD COLUMN category_id INTEGER DEFAULT 0")
        if "subcategory" not in cols:
            c.execute("ALTER TABLE equipment_catalog ADD COLUMN subcategory TEXT DEFAULT ''")
        if "image_url" not in cols:
            c.execute("ALTER TABLE equipment_catalog ADD COLUMN image_url TEXT DEFAULT ''")
        if "is_public_visible" not in cols:
            c.execute("ALTER TABLE equipment_catalog ADD COLUMN is_public_visible INTEGER DEFAULT 1")
        # Seed categories if empty.
        if c.execute("SELECT COUNT(*) FROM product_categories").fetchone()[0] == 0:
            c.executemany(
                "INSERT INTO product_categories (code,name,icon,display_order) VALUES (?,?,?,?)",
                _MARKETPLACE_CATEGORIES,
            )
        # Backfill: any equipment_catalog row with category_id=0 maps to Solar Equipment.
        solar_cat = c.execute(
            "SELECT id FROM product_categories WHERE code='solar_equipment'"
        ).fetchone()
        if solar_cat:
            c.execute(
                "UPDATE equipment_catalog SET category_id=? WHERE category_id=0 AND category_id IS NOT NULL",
                (solar_cat["id"],),
            )
        # Seed a handful of electrical products so the marketplace isn't empty on first visit.
        if c.execute(
            "SELECT COUNT(*) FROM equipment_catalog WHERE category_id IN "
            "(SELECT id FROM product_categories WHERE code != 'solar_equipment')"
        ).fetchone()[0] == 0:
            _seed_marketplace_samples(c)


def _seed_marketplace_samples(c):
    """Seed ~25 sample electrical products across non-solar categories so the
    marketplace has content on first visit. Idempotent: only runs if no
    non-solar products exist yet."""
    cats = {r["code"]: r["id"] for r in c.execute(
        "SELECT id, code FROM product_categories"
    ).fetchall()}
    sup = {r["name"]: r["id"] for r in c.execute(
        "SELECT id, name FROM suppliers"
    ).fetchall()}
    schneider = sup.get("Schneider Electric", 0)
    rs = sup.get("RS Components", 0)
    # (category_code, name, brand, model, spec, unit, price_usd, supplier_id, lead_time, subcategory)
    samples = [
        ("transformers",       "ABB 500 kVA Distribution Transformer", "ABB",       "TRF-500-DT", "500 kVA, 11/0.433 kV, Dyn11, ONAN, IEC 60076",       "No.",  9800, schneider, 60, "Distribution"),
        ("transformers",       "Schneider 250 kVA Oil Immersed",       "Schneider", "MT250-OIL",  "250 kVA, 11/0.4 kV, ONAN, hermetically sealed",      "No.",  6500, schneider, 60, "Oil Immersed"),
        ("avr",                "Servo AVR 30 kVA 3-Phase",             "Generic",   "SAVR-30K",   "30 kVA, 3PH, Servo, ±15% input range",               "No.",  1450, rs,        21, "Three-phase"),
        ("hv_cables",          "11 kV XLPE 3C 70mm² Cu Armoured",      "Nexans",    "HV-11-3C70", "11 kV, XLPE/SWA/PVC, Copper, 3 core, 70mm²",         "m",      52, rs,        45, "Armoured"),
        ("lv_cables",          "LV 4C 16mm² Cu XLPE/SWA/PVC",          "Nexans",    "LV-4C-16",   "0.6/1 kV, 4 core, 16mm², Cu, XLPE/SWA/PVC",          "m",      14, rs,        21, "Armoured"),
        ("lv_cables",          "LV 4C 25mm² Cu XLPE/SWA/PVC",          "Nexans",    "LV-4C-25",   "0.6/1 kV, 4 core, 25mm², Cu, XLPE/SWA/PVC",          "m",      22, rs,        21, "Armoured"),
        ("wires",              "Single Core 2.5mm² PVC Red (100m)",    "Generic",   "SC-2.5-R",   "2.5mm² Cu, 450/750 V, PVC, red",                     "Roll",   28, rs,        7,  "Single Core PVC"),
        ("wires",              "Single Core 4mm² PVC Blue (100m)",     "Generic",   "SC-4-B",     "4mm² Cu, 450/750 V, PVC, blue",                      "Roll",   42, rs,        7,  "Single Core PVC"),
        ("panel_boards",       "Schneider 400A MCC Panel",             "Schneider", "MCC-400",    "400A TPN MCC, Form 3b, 50kA, IP54",                  "No.",  3800, schneider, 45, "MCC Panels"),
        ("distribution_boards","18-way TPN Distribution Board",        "Schneider", "DB-18TPN",   "18-way TPN, 100A incomer, 10kA, IP43",               "No.",   285, schneider, 21, "TPN"),
        ("distribution_boards","8-way SPN Consumer Unit",              "Schneider", "DB-8SPN",    "8-way SPN consumer unit, 63A RCD",                   "No.",   145, schneider, 14, "SPN"),
        ("isolators",          "63A 4-Pole Isolator",                  "Schneider", "ISO-63-4P",  "63A 4P AC isolator, IP65",                           "No.",    58, schneider, 14, "Four-pole"),
        ("fuse_switches",      "100A Switch Fuse with HRC Fuses",      "Schneider", "SF-100-HRC", "100A switch fuse, IP30, HRC fuses included",         "No.",   145, schneider, 21, "HRC"),
        ("conduit",            "PVC Conduit 25mm Heavy Gauge (3m)",    "Generic",   "PVC-25-HG",  "25mm dia heavy-gauge PVC conduit, 3m length",        "m",       1, rs,        7,  "Heavy Gauge"),
        ("steel_boxes",        "1 Gang Deep Steel Box",                "Generic",   "SB-1G-D",    "1 gang deep flush steel back box, 50mm deep",        "No.",     3, rs,        7,  "1 Gang"),
        ("steel_boxes",        "2 Gang Deep Steel Box",                "Generic",   "SB-2G-D",    "2 gang deep flush steel back box, 50mm deep",        "No.",     4, rs,        7,  "2 Gang"),
        ("circular_boxes",     "Ceiling Circular Box 65mm",            "Generic",   "CB-65",      "65mm dia ceiling box with knockouts",                "No.",     2, rs,        7,  "Ceiling"),
        ("cable_trays",        "Perforated Cable Tray 300mm (3m)",     "Generic",   "CT-300P",    "300mm wide perforated cable tray, hot-dip galv, 3m", "m",      18, rs,        21, "Perforated"),
        ("trunking",           "PVC Mini Trunking 38x16mm (2m)",       "Generic",   "MT-38-16",   "PVC mini trunking, 38x16mm, white, 2m",              "m",       4, rs,        7,  "Mini"),
        ("earthing",           "Copper Earth Bar 600mm",               "Generic",   "EB-600",     "600mm Cu earth bar, 25mm x 6mm, 10 holes",           "No.",    52, rs,        14, "Earth Bars"),
        ("earthing",           "Earth Inspection Pit",                 "Generic",   "EIP-1",      "Concrete earth inspection pit, 300x300mm with cover","No.",    38, rs,        14, "Inspection Pits"),
        ("sockets",            "MK 13A Twin Switched Socket",          "MK",        "K2747WHI",   "13A twin switched socket, white, flush",             "No.",    14, rs,        7,  "Switched"),
        ("sockets",            "MK 13A Twin USB Socket",               "MK",        "K2743WHI",   "13A twin socket with 2x USB-A, white, flush",        "No.",    22, rs,        14, "USB"),
        ("dp_switches",        "20A DP Water Heater Switch",           "MK",        "K5403WHI",   "20A DP switch with neon, flush, white",              "No.",    11, rs,        7,  "Water Heater"),
        ("light_switches",     "1 Gang 2 Way Switch",                  "MK",        "K4871WHI",   "1 gang 2 way switch, 10A, white",                    "No.",     6, rs,        7,  "1 Gang 2 Way"),
        ("light_switches",     "2 Gang 2 Way Switch",                  "MK",        "K4872WHI",   "2 gang 2 way switch, 10A, white",                    "No.",     8, rs,        7,  "2 Gang 2 Way"),
        ("light_switches",     "3 Gang 2 Way Switch",                  "MK",        "K4873WHI",   "3 gang 2 way switch, 10A, white",                    "No.",    11, rs,        7,  "3 Gang 2 Way"),
    ]
    # Build a code → display-name map from the seed list so the legacy
    # free-text `category` column carries a human-readable label, matching
    # how solar's existing rows ("PV Modules", "Inverters", ...) are stored.
    code_to_label = {row[0]: row[1] for row in _MARKETPLACE_CATEGORIES}
    for (code, name, brand, model, spec, unit, price, sup_id, lt, sub) in samples:
        cat_id = cats.get(code, 0)
        legacy_label = code_to_label.get(code, "")
        c.execute(
            "INSERT INTO equipment_catalog (category, name, brand, model, spec, unit, "
            "price_usd, supplier_id, lead_time_days, category_id, subcategory, is_public_visible) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,1)",
            (legacy_label, name, brand, model, spec, unit, price, sup_id, lt, cat_id, sub),
        )


def _safe_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


@app.route("/marketplace")
def marketplace_public():
    """Public landing for the electrical pricing marketplace.

    Anonymous visitors see categories, products, prices, supplier names.
    Action buttons (request quote, send RFQ, download BOM) redirect to
    /register?next=/marketplace so the magnet funnels into signups."""
    _ensure_marketplace_tables()
    q = (request.args.get("q") or "").strip()
    cat_id = _safe_int(request.args.get("cat", 0))

    with get_db() as c:
        categories = c.execute(
            "SELECT pc.id, pc.code, pc.name, pc.icon, "
            "  (SELECT COUNT(*) FROM equipment_catalog ec "
            "   WHERE ec.category_id=pc.id AND ec.is_active=1 "
            "         AND ec.is_public_visible=1 AND ec.is_verified=1) AS product_count "
            "FROM product_categories pc "
            "WHERE pc.is_active=1 "
            "ORDER BY pc.display_order"
        ).fetchall()

        sql = ("SELECT ec.id, ec.name, ec.brand, ec.model, ec.spec, ec.unit, "
               "       ec.price_usd, ec.lead_time_days, ec.subcategory, "
               "       ec.image_url, ec.category_id, "
               "       s.name AS supplier_name, s.country AS supplier_country, "
               "       s.rating AS supplier_rating, "
               "       pc.name AS category_name, pc.icon AS category_icon "
               "FROM equipment_catalog ec "
               "LEFT JOIN suppliers s ON s.id=ec.supplier_id "
               "LEFT JOIN product_categories pc ON pc.id=ec.category_id "
               "WHERE ec.is_active=1 AND ec.is_public_visible=1 AND ec.is_verified=1 ")
        args = []
        if cat_id:
            sql += "AND ec.category_id=? "
            args.append(cat_id)
        if q:
            # LOWER() on both sides so search is case-insensitive on Postgres
            # (LIKE is case-sensitive there; SQLite is case-insensitive for
            # ASCII, so this keeps both backends behaving the same).
            sql += ("AND (LOWER(ec.name) LIKE ? OR LOWER(ec.brand) LIKE ? "
                    "     OR LOWER(ec.model) LIKE ? OR LOWER(ec.spec) LIKE ?) ")
            like = f"%{q.lower()}%"
            args.extend([like, like, like, like])
        sql += "ORDER BY ec.created_at DESC LIMIT 200"
        products = c.execute(sql, args).fetchall()

        total_products = c.execute(
            "SELECT COUNT(*) FROM equipment_catalog "
            "WHERE is_active=1 AND is_public_visible=1 AND is_verified=1"
        ).fetchone()[0]
        total_suppliers = c.execute(
            "SELECT COUNT(*) FROM suppliers WHERE is_active=1"
        ).fetchone()[0]
        countries = c.execute(
            "SELECT COUNT(DISTINCT country) FROM suppliers "
            "WHERE is_active=1 AND country!=''"
        ).fetchone()[0]

    selected_category = None
    if cat_id:
        for cat in categories:
            if cat["id"] == cat_id:
                selected_category = cat
                break

    return render_template(
        "marketplace.html",
        user=current_user(),
        categories=categories,
        products=products,
        total_products=total_products,
        total_suppliers=total_suppliers,
        total_countries=countries,
        selected_category=selected_category,
        q=q,
    )


@app.route("/marketplace/action/<string:action>")
def marketplace_action_gate(action):
    """All action buttons (RFQ, BOM, contact, download) hit this gate.
    Anonymous → /register?next=/marketplace. Logged-in → coming-soon notice
    (Slice 2 will wire each action to its real implementation)."""
    if not current_user():
        return redirect(url_for("register") + "?next=" + url_for("marketplace_public"))
    flash(f"'{action.replace('_', ' ').title()}' arrives in the next marketplace release. "
          "Your interest is logged.", "info")
    return redirect(url_for("marketplace_public"))
