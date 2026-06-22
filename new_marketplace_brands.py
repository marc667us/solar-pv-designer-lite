# === BEGIN: marketplace_brands splice ===
# 2026-06-22 (session B): product_brands table + admin manage page.
#
# Schema (idempotent CREATE on both SQLite and Postgres via per-statement
# try/except so re-runs are no-ops):
#
#   CREATE TABLE product_brands (
#     id            INTEGER PRIMARY KEY AUTOINCREMENT,
#     name          TEXT UNIQUE NOT NULL,
#     country       TEXT DEFAULT '',
#     website       TEXT DEFAULT '',
#     is_active     INTEGER DEFAULT 1,
#     created_at    TEXT DEFAULT CURRENT_TIMESTAMP
#   )
#
# Seed pipeline:
#   1. Insert (or skip) every entry in _MARKETPLACE_BRANDS.
#   2. Top-up with any DISTINCT brand value already present in
#      equipment_catalog (so historical inventory doesn't disappear from
#      the dropdown).
#
# Helpers:
#   _get_active_brands() -> [{'id','name'}, ...] ordered by name.
#
# Routes:
#   GET  /admin/marketplace/brands                  list + add form
#   POST /admin/marketplace/brands/add              create
#   POST /admin/marketplace/brands/<bid>/edit       update
#   POST /admin/marketplace/brands/<bid>/toggle     activate / deactivate

# Canonical brand registry. Owner edits this list to add brands universally;
# admin can also add via the UI which writes to product_brands directly.
_MARKETPLACE_BRANDS = [
    # Solar / PV
    "JinkoSolar", "LONGi", "Canadian Solar", "Trina Solar", "JA Solar",
    "REC Group", "Q CELLS",
    # Solar inverters / hybrid / off-grid
    "Sungrow", "SMA", "Huawei", "Deye", "Victron", "GoodWe", "Growatt",
    "SolarEdge", "Enphase",
    # Storage
    "BYD", "Pylontech", "Dyness", "LG Chem",
    # MV / LV switchgear + breakers
    "ABB", "Schneider Electric", "Siemens", "Eaton", "Legrand", "Hager",
    "Chint", "DELIXI",
    # Wires + cables
    "Reroy", "Nexans", "Prysmian", "Belden", "Tratos",
    # Accessories
    "MK", "Crabtree", "Clipsal", "Lake", "Multibrand",
    # Generators + power systems
    "Cummins", "Caterpillar", "Perkins", "FG Wilson", "Kohler", "Atlas Copco",
    "Generac", "Leroy Somer", "DEEPSEA Electronics", "Safenergy",
    # ICT / network
    "Cisco", "Dell", "Lenovo", "Microsoft", "HP", "HPE", "Fortinet", "VMware",
    "APC", "Dell EMC", "Ubiquiti",
    # Lighting
    "Philips", "Osram", "Tridonic",
    # Generic / agency
    "Agenda", "Generic",
]


def _ensure_brands_table():
    """Idempotent CREATE on both engines. Cheap to call every route hit."""
    is_pg = bool(os.environ.get("DATABASE_URL"))
    if is_pg:
        ddls = [
            """CREATE TABLE IF NOT EXISTS product_brands (
                id            SERIAL PRIMARY KEY,
                name          VARCHAR(120) UNIQUE NOT NULL,
                country       VARCHAR(60) DEFAULT '',
                website       VARCHAR(200) DEFAULT '',
                is_active     INTEGER DEFAULT 1,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_product_brands_active ON product_brands(is_active)",
        ]
    else:
        ddls = [
            """CREATE TABLE IF NOT EXISTS product_brands (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT UNIQUE NOT NULL,
                country       TEXT DEFAULT '',
                website       TEXT DEFAULT '',
                is_active     INTEGER DEFAULT 1,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_product_brands_active ON product_brands(is_active)",
        ]
    for ddl in ddls:
        try:
            with get_db() as c:
                c.execute(ddl)
        except Exception:
            pass


def _seed_marketplace_brands():
    """Idempotent. (a) inserts every entry in _MARKETPLACE_BRANDS that isn't
    already in product_brands; (b) tops up with DISTINCT brand values from
    equipment_catalog so historical inventory doesn't disappear from the
    dropdown.  Runs on every cold start via _ensure_marketplace_tables()."""
    _ensure_brands_table()
    is_pg = bool(os.environ.get("DATABASE_URL"))
    try:
        with get_db() as c:
            for name in _MARKETPLACE_BRANDS:
                try:
                    if is_pg:
                        c.execute(
                            "INSERT INTO product_brands (name, is_active) VALUES (?, 1) "
                            "ON CONFLICT (name) DO NOTHING",
                            (name,),
                        )
                    else:
                        c.execute(
                            "INSERT OR IGNORE INTO product_brands (name, is_active) VALUES (?, 1)",
                            (name,),
                        )
                except Exception:
                    pass
            # Top up from equipment_catalog so legacy data shows in the dropdown.
            try:
                rows = c.execute(
                    "SELECT DISTINCT brand FROM equipment_catalog "
                    "WHERE brand IS NOT NULL AND TRIM(brand) <> ''"
                ).fetchall()
                for r in rows:
                    nm = (r["brand"] if hasattr(r, "keys") else r[0]).strip()
                    if not nm:
                        continue
                    try:
                        if is_pg:
                            c.execute(
                                "INSERT INTO product_brands (name, is_active) VALUES (?, 1) "
                                "ON CONFLICT (name) DO NOTHING",
                                (nm,),
                            )
                        else:
                            c.execute(
                                "INSERT OR IGNORE INTO product_brands (name, is_active) VALUES (?, 1)",
                                (nm,),
                            )
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception as _e:
        try: app.logger.warning("_seed_marketplace_brands failed: %s", _e)
        except Exception: pass


def _get_active_brands():
    """Return active brand rows ordered by name. Always re-seeds first so
    a newly-added brand shows up immediately in the dropdown."""
    _seed_marketplace_brands()
    try:
        with get_db() as c:
            rows = c.execute(
                "SELECT id, name FROM product_brands WHERE is_active=1 ORDER BY name"
            ).fetchall()
        return [{"id": (r["id"] if hasattr(r, "keys") else r[0]),
                 "name": (r["name"] if hasattr(r, "keys") else r[1])} for r in rows]
    except Exception:
        return []


@app.route("/admin/marketplace/brands")
@admin_required
def admin_marketplace_brands():
    _seed_marketplace_brands()
    with get_db() as c:
        rows = c.execute(
            "SELECT id, name, country, website, is_active "
            "FROM product_brands ORDER BY name"
        ).fetchall()
        # product count per brand so admins can see usage
        counts = {}
        try:
            crows = c.execute(
                "SELECT brand, COUNT(*) AS n FROM equipment_catalog "
                "WHERE brand IS NOT NULL AND TRIM(brand) <> '' AND is_active=1 "
                "GROUP BY brand"
            ).fetchall()
            for r in crows:
                key = (r["brand"] if hasattr(r, "keys") else r[0])
                counts[key] = int(r["n"] if hasattr(r, "keys") else r[1])
        except Exception:
            pass
    return render_template(
        "admin_marketplace_brands.html",
        user=current_user(), brands=rows, brand_counts=counts,
    )


@app.route("/admin/marketplace/brands/add", methods=["POST"])
@admin_required
def admin_marketplace_brands_add():
    _ensure_brands_table()
    csrf_protect()
    f = request.form
    name = (f.get("name") or "").strip()[:120]
    if not name:
        flash("Brand name is required.", "danger")
        return redirect(url_for("admin_marketplace_brands"))
    country = (f.get("country") or "").strip()[:60]
    website = (f.get("website") or "").strip()[:200]
    is_pg = bool(os.environ.get("DATABASE_URL"))
    try:
        with get_db() as c:
            if is_pg:
                c.execute(
                    "INSERT INTO product_brands (name, country, website, is_active) "
                    "VALUES (?, ?, ?, 1) "
                    "ON CONFLICT (name) DO UPDATE SET country=EXCLUDED.country, website=EXCLUDED.website",
                    (name, country, website),
                )
            else:
                c.execute(
                    "INSERT OR REPLACE INTO product_brands (id, name, country, website, is_active, created_at) "
                    "VALUES ((SELECT id FROM product_brands WHERE name=?), ?, ?, ?, 1, COALESCE((SELECT created_at FROM product_brands WHERE name=?), CURRENT_TIMESTAMP))",
                    (name, name, country, website, name),
                )
        _log_marketplace_action("add_brand", "product_brand", 0, f"{name}")
        flash(f"Brand '{name}' added.", "success")
    except Exception as e:
        try: app.logger.exception("admin_marketplace_brands_add: %s", e)
        except Exception: pass
        flash(f"Could not add brand: {e!s}", "danger")
    return redirect(url_for("admin_marketplace_brands"))


@app.route("/admin/marketplace/brands/<int:bid>/edit", methods=["POST"])
@admin_required
def admin_marketplace_brands_edit(bid):
    _ensure_brands_table()
    csrf_protect()
    f = request.form
    name = (f.get("name") or "").strip()[:120]
    if not name:
        flash("Brand name is required.", "danger")
        return redirect(url_for("admin_marketplace_brands"))
    country = (f.get("country") or "").strip()[:60]
    website = (f.get("website") or "").strip()[:200]
    try:
        with get_db() as c:
            row = c.execute(
                "SELECT id, name FROM product_brands WHERE id=?", (bid,)
            ).fetchone()
            if not row:
                abort(404)
            old_name = row["name"] if hasattr(row, "keys") else row[1]
            c.execute(
                "UPDATE product_brands SET name=?, country=?, website=? WHERE id=?",
                (name, country, website, bid),
            )
            # If the brand was renamed, propagate to existing products so the
            # dropdown value still matches what's saved on each catalogue row.
            if old_name and old_name != name:
                try:
                    c.execute(
                        "UPDATE equipment_catalog SET brand=? WHERE brand=?",
                        (name, old_name),
                    )
                except Exception:
                    pass
        _log_marketplace_action("edit_brand", "product_brand", bid, f"{old_name} -> {name}")
        flash(f"Brand '{name}' updated.", "success")
    except Exception as e:
        try: app.logger.exception("admin_marketplace_brands_edit: %s", e)
        except Exception: pass
        flash(f"Could not update brand: {e!s}", "danger")
    return redirect(url_for("admin_marketplace_brands"))


@app.route("/admin/marketplace/brands/<int:bid>/toggle", methods=["POST"])
@admin_required
def admin_marketplace_brands_toggle(bid):
    _ensure_brands_table()
    csrf_protect()
    with get_db() as c:
        row = c.execute(
            "SELECT id, name, is_active FROM product_brands WHERE id=?", (bid,)
        ).fetchone()
        if not row:
            abort(404)
        new_state = 0 if (row["is_active"] or 0) else 1
        c.execute(
            "UPDATE product_brands SET is_active=? WHERE id=?", (new_state, bid),
        )
    _log_marketplace_action(
        "toggle_brand", "product_brand", bid,
        f"{row['name']}: {'activated' if new_state else 'deactivated'}",
    )
    flash(
        f"Brand '{row['name']}' {'activated' if new_state else 'deactivated'}.",
        "success" if new_state else "warning",
    )
    return redirect(url_for("admin_marketplace_brands"))


# === END: marketplace_brands splice ===
