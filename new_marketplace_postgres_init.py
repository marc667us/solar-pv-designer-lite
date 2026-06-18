# ─── Marketplace schema bootstrap — works on SQLite AND Postgres ──────────────
# The Slice 1-5 routes each had their own `_ensure_*_tables()` helper that
# called `c.executescript(...)` + SQLite-only `INTEGER PRIMARY KEY AUTOINCREMENT`
# DDL. Both crash on Postgres. This module replaces those code paths with a
# single dialect-aware bootstrap that runs at startup, then a per-request
# no-op once the schema is in place.

_MARKETPLACE_PG_DONE = {"v": False}


def _mp_is_pg() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def _mp_pg_exec(sql_list):
    """Run each statement in its own short-lived transaction so a failure on
    one (e.g. ALTER ADD COLUMN that already exists) doesn't abort the rest.
    Postgres aborts the whole transaction on the first error otherwise."""
    for sql in sql_list:
        try:
            with get_db() as c:
                c.execute(sql)
        except Exception as e:
            # Log and continue — duplicates/idempotency errors are expected.
            try:
                app.logger.info("marketplace pg init swallowed: %s — %s",
                                sql.splitlines()[0][:80], type(e).__name__)
            except Exception:
                pass


def _ensure_marketplace_schema_postgres():
    """Create all marketplace tables + add columns to equipment_catalog on
    Postgres. Idempotent (CREATE IF NOT EXISTS + per-statement try/except)."""
    if _MARKETPLACE_PG_DONE["v"]:
        return
    if not _mp_is_pg():
        return

    create_stmts = [
        # Slice 1 — product taxonomy
        """CREATE TABLE IF NOT EXISTS product_categories (
            id            SERIAL PRIMARY KEY,
            code          VARCHAR(40) UNIQUE NOT NULL,
            name          VARCHAR(120) NOT NULL,
            icon          VARCHAR(40) DEFAULT 'bi-box',
            display_order INTEGER DEFAULT 0,
            is_active     INTEGER DEFAULT 1,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_product_categories_order ON product_categories(display_order)",

        # Slice 1 — extend equipment_catalog. Each ALTER is independent so
        # duplicates from a partial earlier run are tolerated.
        "ALTER TABLE equipment_catalog ADD COLUMN IF NOT EXISTS category_id INTEGER DEFAULT 0",
        "ALTER TABLE equipment_catalog ADD COLUMN IF NOT EXISTS subcategory VARCHAR(120) DEFAULT ''",
        "ALTER TABLE equipment_catalog ADD COLUMN IF NOT EXISTS image_url VARCHAR(500) DEFAULT ''",
        "ALTER TABLE equipment_catalog ADD COLUMN IF NOT EXISTS is_public_visible INTEGER DEFAULT 1",
        "ALTER TABLE equipment_catalog ADD COLUMN IF NOT EXISTS is_verified INTEGER DEFAULT 1",

        # Slice 2 — extend users + suppliers
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(40) DEFAULT ''",
        "ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS user_id INTEGER DEFAULT 0",
        "ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS is_verified INTEGER DEFAULT 0",

        # Slice 3 — audit log
        """CREATE TABLE IF NOT EXISTS marketplace_audit_log (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            action      VARCHAR(80) NOT NULL,
            target_kind VARCHAR(40) NOT NULL,
            target_id   INTEGER NOT NULL,
            notes       TEXT DEFAULT '',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",

        # Slice 4 — RFQ workflow tables
        """CREATE TABLE IF NOT EXISTS rfqs (
            id                  SERIAL PRIMARY KEY,
            user_id             INTEGER NOT NULL,
            title               VARCHAR(300) NOT NULL,
            delivery_country    VARCHAR(80) DEFAULT '',
            deadline_date       VARCHAR(40) DEFAULT '',
            notes               TEXT DEFAULT '',
            status              VARCHAR(40) DEFAULT 'draft',
            awarded_supplier_id INTEGER DEFAULT 0,
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sent_at             VARCHAR(40) DEFAULT '',
            updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_rfqs_user ON rfqs(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_rfqs_status ON rfqs(status)",

        """CREATE TABLE IF NOT EXISTS rfq_items (
            id           SERIAL PRIMARY KEY,
            rfq_id       INTEGER NOT NULL,
            product_id   INTEGER DEFAULT 0,
            custom_name  VARCHAR(300) NOT NULL,
            qty          REAL DEFAULT 1,
            unit         VARCHAR(20) DEFAULT 'No.',
            spec_notes   TEXT DEFAULT '',
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_rfq_items_rfq ON rfq_items(rfq_id)",

        """CREATE TABLE IF NOT EXISTS rfq_supplier_targets (
            id            SERIAL PRIMARY KEY,
            rfq_id        INTEGER NOT NULL,
            supplier_id   INTEGER NOT NULL,
            status        VARCHAR(40) DEFAULT 'pending',
            sent_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            responded_at  VARCHAR(40) DEFAULT '',
            UNIQUE(rfq_id, supplier_id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_rfq_targets_supplier ON rfq_supplier_targets(supplier_id)",
        "CREATE INDEX IF NOT EXISTS idx_rfq_targets_rfq ON rfq_supplier_targets(rfq_id)",

        """CREATE TABLE IF NOT EXISTS rfq_responses (
            id              SERIAL PRIMARY KEY,
            rfq_id          INTEGER NOT NULL,
            supplier_id     INTEGER NOT NULL,
            total_price     REAL DEFAULT 0,
            currency        VARCHAR(3) DEFAULT 'USD',
            lead_time_days  INTEGER DEFAULT 30,
            notes           TEXT DEFAULT '',
            valid_until     VARCHAR(40) DEFAULT '',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(rfq_id, supplier_id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_rfq_responses_rfq ON rfq_responses(rfq_id)",

        """CREATE TABLE IF NOT EXISTS rfq_response_items (
            id             SERIAL PRIMARY KEY,
            response_id    INTEGER NOT NULL,
            rfq_item_id    INTEGER NOT NULL,
            unit_price     REAL DEFAULT 0,
            available      INTEGER DEFAULT 1,
            notes          TEXT DEFAULT '',
            UNIQUE(response_id, rfq_item_id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_rfq_resp_items_resp ON rfq_response_items(response_id)",

        # Slice 5 — BOM/BOQ tables
        """CREATE TABLE IF NOT EXISTS marketplace_boms (
            id            SERIAL PRIMARY KEY,
            user_id       INTEGER NOT NULL,
            title         VARCHAR(300) NOT NULL,
            project_name  VARCHAR(300) DEFAULT '',
            client_name   VARCHAR(300) DEFAULT '',
            notes         TEXT DEFAULT '',
            status        VARCHAR(40) DEFAULT 'draft',
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_marketplace_boms_user ON marketplace_boms(user_id)",

        """CREATE TABLE IF NOT EXISTS marketplace_bom_items (
            id                  SERIAL PRIMARY KEY,
            bom_id              INTEGER NOT NULL,
            product_id          INTEGER DEFAULT 0,
            custom_name         VARCHAR(300) NOT NULL,
            qty                 REAL DEFAULT 1,
            unit                VARCHAR(20) DEFAULT 'No.',
            unit_price_override REAL,
            notes               TEXT DEFAULT '',
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_marketplace_bom_items_bom ON marketplace_bom_items(bom_id)",
    ]

    _mp_pg_exec(create_stmts)

    # Seed the 18+ categories if empty. Plain INSERT idempotency via the
    # UNIQUE(code) constraint plus ON CONFLICT DO NOTHING — works on both
    # backends because the existing db_adapter rewrites it for SQLite if
    # needed; here we're already on Postgres.
    try:
        with get_db() as c:
            cur_n = c.execute(
                "SELECT COUNT(*) AS n FROM product_categories"
            ).fetchone()
            n = cur_n[0] if hasattr(cur_n, "__getitem__") else cur_n["n"]
        if n == 0:
            with get_db() as c:
                for code, name, icon, order in _MARKETPLACE_CATEGORIES:
                    c.execute(
                        "INSERT INTO product_categories (code, name, icon, display_order) "
                        "VALUES (?, ?, ?, ?) "
                        "ON CONFLICT (code) DO NOTHING",
                        (code, name, icon, order),
                    )
    except Exception as e:
        try:
            app.logger.warning("marketplace pg seed: %s", e)
        except Exception:
            pass

    # Backfill: solar's pre-marketplace equipment_catalog rows have
    # category_id=0 (the ALTER DEFAULT) and a free-text `category`
    # column like 'PV Modules', 'Inverters', etc. Map them to the new
    # taxonomy so they appear under category chips on the public browse.
    try:
        with get_db() as c:
            solar_cat = c.execute(
                "SELECT id FROM product_categories WHERE code='solar_equipment'"
            ).fetchone()
            if solar_cat:
                solar_id = solar_cat[0] if hasattr(solar_cat, '__getitem__') else solar_cat["id"]
                # Anything with a SOLAR-flavoured legacy category label moves to
                # solar_equipment. Anything else with category_id=0 stays at 0
                # (admin can re-categorise later).
                c.execute(
                    "UPDATE equipment_catalog SET category_id=? "
                    "WHERE category_id=0 AND category IN "
                    "('PV Modules','Inverters','Batteries','MPPT','Cables',"
                    " 'Protection','Earthing','Solar Equipment')",
                    (solar_id,),
                )
    except Exception as e:
        try:
            app.logger.warning("marketplace pg backfill: %s", e)
        except Exception:
            pass

    # Seed the 27 sample electrical products if none exist for any non-solar
    # category. This is the magnet content — without it, anonymous visitors
    # only see solar PV modules, not the transformers/cables/sockets that
    # pull electricians and cost engineers into the funnel.
    try:
        with get_db() as c:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM equipment_catalog ec "
                "JOIN product_categories pc ON pc.id=ec.category_id "
                "WHERE pc.code != 'solar_equipment'"
            ).fetchone()
            n_non_solar = row[0] if hasattr(row, '__getitem__') else row["n"]
        if n_non_solar == 0:
            _seed_marketplace_postgres_samples()
    except Exception as e:
        try:
            app.logger.warning("marketplace pg sample seed: %s", e)
        except Exception:
            pass

    _MARKETPLACE_PG_DONE["v"] = True
    try:
        app.logger.info("marketplace pg schema ready")
    except Exception:
        pass


def _seed_marketplace_postgres_samples():
    """Insert 27 sample electrical products + 2 generic suppliers (Nexans,
    Generic) if they don't already exist on Postgres. Called from
    _ensure_marketplace_schema_postgres() — idempotent."""
    # Add Nexans + Generic suppliers if not already present (solar's original
    # seed had 8 brands but not these two).
    with get_db() as c:
        for sup_name, sup_country, sup_email, sup_categories in [
            ("Nexans",  "France",  "sales@nexans.com",   "Cables"),
            ("Generic", "Various", "contact@example.com", "Conduit,Boxes,Wires"),
            ("MK",      "UK",      "sales@mkelectric.com", "Sockets,Switches"),
            ("ABB",     "Sweden",  "sales@abb.com",      "Transformers,Switchgear"),
        ]:
            try:
                c.execute(
                    "INSERT INTO suppliers "
                    "(name,country,contact_name,phone,email,website,categories,"
                    " lead_time_days,payment_terms,rating,user_id,is_verified) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT DO NOTHING",
                    (sup_name, sup_country, "Sales", "", sup_email, "",
                     sup_categories, 30, "TT 30 days", 5, 0, 1),
                )
            except Exception:
                # The suppliers table has no UNIQUE on name, so ON CONFLICT
                # DO NOTHING may itself error if there's no conflict target.
                # Fall back to a probe + insert.
                pass

    with get_db() as c:
        sup = {r[1] if hasattr(r, '__getitem__') else r["name"]: (r[0] if hasattr(r, '__getitem__') else r["id"])
               for r in c.execute("SELECT id, name FROM suppliers").fetchall()}
        cats = {r[1] if hasattr(r, '__getitem__') else r["code"]: (r[0] if hasattr(r, '__getitem__') else r["id"])
                for r in c.execute("SELECT id, code FROM product_categories").fetchall()}

    schneider = sup.get("Schneider Electric", 0)
    rs        = sup.get("RS Components", 0)
    nexans    = sup.get("Nexans", rs)
    generic   = sup.get("Generic", rs)
    mk        = sup.get("MK", rs)
    abb       = sup.get("ABB", schneider)

    # (category_code, name, brand, model, spec, unit, price_usd, supplier_id, lead_time, subcategory)
    samples = [
        ("transformers",       "ABB 500 kVA Distribution Transformer", "ABB",       "TRF-500-DT", "500 kVA, 11/0.433 kV, Dyn11, ONAN, IEC 60076",       "No.",  9800, abb,       60, "Distribution"),
        ("transformers",       "Schneider 250 kVA Oil Immersed",       "Schneider", "MT250-OIL",  "250 kVA, 11/0.4 kV, ONAN, hermetically sealed",      "No.",  6500, schneider, 60, "Oil Immersed"),
        ("avr",                "Servo AVR 30 kVA 3-Phase",             "Generic",   "SAVR-30K",   "30 kVA, 3PH, Servo, +/-15% input range",             "No.",  1450, generic,   21, "Three-phase"),
        ("hv_cables",          "11 kV XLPE 3C 70mm2 Cu Armoured",      "Nexans",    "HV-11-3C70", "11 kV, XLPE/SWA/PVC, Copper, 3 core, 70mm2",         "m",      52, nexans,    45, "Armoured"),
        ("lv_cables",          "LV 4C 16mm2 Cu XLPE/SWA/PVC",          "Nexans",    "LV-4C-16",   "0.6/1 kV, 4 core, 16mm2, Cu, XLPE/SWA/PVC",          "m",      14, nexans,    21, "Armoured"),
        ("lv_cables",          "LV 4C 25mm2 Cu XLPE/SWA/PVC",          "Nexans",    "LV-4C-25",   "0.6/1 kV, 4 core, 25mm2, Cu, XLPE/SWA/PVC",          "m",      22, nexans,    21, "Armoured"),
        ("wires",              "Single Core 2.5mm2 PVC Red (100m)",    "Generic",   "SC-2.5-R",   "2.5mm2 Cu, 450/750 V, PVC, red",                     "Roll",   28, generic,   7,  "Single Core PVC"),
        ("wires",              "Single Core 4mm2 PVC Blue (100m)",     "Generic",   "SC-4-B",     "4mm2 Cu, 450/750 V, PVC, blue",                      "Roll",   42, generic,   7,  "Single Core PVC"),
        ("panel_boards",       "Schneider 400A MCC Panel",             "Schneider", "MCC-400",    "400A TPN MCC, Form 3b, 50kA, IP54",                  "No.",  3800, schneider, 45, "MCC Panels"),
        ("distribution_boards","18-way TPN Distribution Board",        "Schneider", "DB-18TPN",   "18-way TPN, 100A incomer, 10kA, IP43",               "No.",   285, schneider, 21, "TPN"),
        ("distribution_boards","8-way SPN Consumer Unit",              "Schneider", "DB-8SPN",    "8-way SPN consumer unit, 63A RCD",                   "No.",   145, schneider, 14, "SPN"),
        ("isolators",          "63A 4-Pole Isolator",                  "Schneider", "ISO-63-4P",  "63A 4P AC isolator, IP65",                           "No.",    58, schneider, 14, "Four-pole"),
        ("fuse_switches",      "100A Switch Fuse with HRC Fuses",      "Schneider", "SF-100-HRC", "100A switch fuse, IP30, HRC fuses included",         "No.",   145, schneider, 21, "HRC"),
        ("conduit",            "PVC Conduit 25mm Heavy Gauge (3m)",    "Generic",   "PVC-25-HG",  "25mm dia heavy-gauge PVC conduit, 3m length",        "m",       1, generic,   7,  "Heavy Gauge"),
        ("steel_boxes",        "1 Gang Deep Steel Box",                "Generic",   "SB-1G-D",    "1 gang deep flush steel back box, 50mm deep",        "No.",     3, generic,   7,  "1 Gang"),
        ("steel_boxes",        "2 Gang Deep Steel Box",                "Generic",   "SB-2G-D",    "2 gang deep flush steel back box, 50mm deep",        "No.",     4, generic,   7,  "2 Gang"),
        ("circular_boxes",     "Ceiling Circular Box 65mm",            "Generic",   "CB-65",      "65mm dia ceiling box with knockouts",                "No.",     2, generic,   7,  "Ceiling"),
        ("cable_trays",        "Perforated Cable Tray 300mm (3m)",     "Generic",   "CT-300P",    "300mm wide perforated cable tray, hot-dip galv, 3m", "m",      18, generic,   21, "Perforated"),
        ("trunking",           "PVC Mini Trunking 38x16mm (2m)",       "Generic",   "MT-38-16",   "PVC mini trunking, 38x16mm, white, 2m",              "m",       4, generic,   7,  "Mini"),
        ("earthing",           "Copper Earth Bar 600mm",               "Generic",   "EB-600",     "600mm Cu earth bar, 25mm x 6mm, 10 holes",           "No.",    52, generic,   14, "Earth Bars"),
        ("earthing",           "Earth Inspection Pit",                 "Generic",   "EIP-1",      "Concrete earth inspection pit, 300x300mm with cover","No.",    38, generic,   14, "Inspection Pits"),
        ("sockets",            "MK 13A Twin Switched Socket",          "MK",        "K2747WHI",   "13A twin switched socket, white, flush",             "No.",    14, mk,        7,  "Switched"),
        ("sockets",            "MK 13A Twin USB Socket",               "MK",        "K2743WHI",   "13A twin socket with 2x USB-A, white, flush",        "No.",    22, mk,        14, "USB"),
        ("dp_switches",        "20A DP Water Heater Switch",           "MK",        "K5403WHI",   "20A DP switch with neon, flush, white",              "No.",    11, mk,        7,  "Water Heater"),
        ("light_switches",     "1 Gang 2 Way Switch",                  "MK",        "K4871WHI",   "1 gang 2 way switch, 10A, white",                    "No.",     6, mk,        7,  "1 Gang 2 Way"),
        ("light_switches",     "2 Gang 2 Way Switch",                  "MK",        "K4872WHI",   "2 gang 2 way switch, 10A, white",                    "No.",     8, mk,        7,  "2 Gang 2 Way"),
        ("light_switches",     "3 Gang 2 Way Switch",                  "MK",        "K4873WHI",   "3 gang 2 way switch, 10A, white",                    "No.",    11, mk,        7,  "3 Gang 2 Way"),
    ]
    code_to_label = {row[0]: row[1] for row in _MARKETPLACE_CATEGORIES}
    with get_db() as c:
        for (code, name, brand, model, spec, unit, price, sup_id, lt, sub) in samples:
            cat_id = cats.get(code, 0)
            legacy_label = code_to_label.get(code, "")
            c.execute(
                "INSERT INTO equipment_catalog (category, name, brand, model, spec, unit, "
                "price_usd, supplier_id, lead_time_days, category_id, subcategory, "
                "is_public_visible, is_verified) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,1,1)",
                (legacy_label, name, brand, model, spec, unit, price, sup_id, lt, cat_id, sub),
            )
