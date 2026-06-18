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

    _MARKETPLACE_PG_DONE["v"] = True
    try:
        app.logger.info("marketplace pg schema ready")
    except Exception:
        pass
