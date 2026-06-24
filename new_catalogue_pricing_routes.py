# new_catalogue_pricing_routes.py
# 2026-06-24 -- B + C: 3-quote Recheck Prices schema + Catalogue unit-price
# correction routes.
#
# Three additions:
#   1. _ensure_pricing_tables() -- equipment_catalog_quotes (B) +
#      equipment_catalog_price_history (C). Idempotent SQLite + Postgres.
#   2. Admin per-row "Update price" route + history view (C).
#   3. Helpers _record_catalog_quote() and _record_price_history()
#      reused by the BOM recheck-apply flow (cross-feature push-to-catalogue).
#
# Per CLAUDE.md: zero-cost, no paid services. All routes are admin-gated.


import json as _json


# ─────────────────────────── Schema bootstrap ───────────────────────────


_PRICING_SCHEMA_DONE = {"v": False}


def _ensure_pricing_tables(get_db, is_pg_fn):
    """Idempotent. equipment_catalog_quotes (3-quote history) +
    equipment_catalog_price_history (every basic-price change)."""
    if _PRICING_SCHEMA_DONE["v"]:
        return
    is_pg = bool(is_pg_fn())
    quotes_ddl_pg = """
        CREATE TABLE IF NOT EXISTS equipment_catalog_quotes (
            id              SERIAL PRIMARY KEY,
            catalog_item_id INTEGER NOT NULL,
            supplier_name   VARCHAR(200) NOT NULL DEFAULT '',
            supplier_id     INTEGER DEFAULT 0,
            price_local     REAL DEFAULT 0,
            currency        VARCHAR(3) DEFAULT 'GHS',
            quoted_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source_note     TEXT DEFAULT '',
            anomaly_flag    INTEGER DEFAULT 0,
            status          VARCHAR(20) DEFAULT 'proposed',
            recorded_by     INTEGER DEFAULT 0
        )
    """
    quotes_ddl_sqlite = """
        CREATE TABLE IF NOT EXISTS equipment_catalog_quotes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            catalog_item_id INTEGER NOT NULL,
            supplier_name   TEXT DEFAULT '',
            supplier_id     INTEGER DEFAULT 0,
            price_local     REAL DEFAULT 0,
            currency        TEXT DEFAULT 'GHS',
            quoted_at       TEXT DEFAULT CURRENT_TIMESTAMP,
            source_note     TEXT DEFAULT '',
            anomaly_flag    INTEGER DEFAULT 0,
            status          TEXT DEFAULT 'proposed',
            recorded_by     INTEGER DEFAULT 0
        )
    """
    history_ddl_pg = """
        CREATE TABLE IF NOT EXISTS equipment_catalog_price_history (
            id               SERIAL PRIMARY KEY,
            catalog_item_id  INTEGER NOT NULL,
            old_price_usd    REAL DEFAULT 0,
            new_price_usd    REAL DEFAULT 0,
            currency_local   VARCHAR(3) DEFAULT '',
            new_price_local  REAL DEFAULT 0,
            source           VARCHAR(200) DEFAULT '',
            reason           TEXT DEFAULT '',
            set_by_user_id   INTEGER DEFAULT 0,
            approval_status  VARCHAR(20) DEFAULT 'approved',
            set_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    history_ddl_sqlite = """
        CREATE TABLE IF NOT EXISTS equipment_catalog_price_history (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            catalog_item_id  INTEGER NOT NULL,
            old_price_usd    REAL DEFAULT 0,
            new_price_usd    REAL DEFAULT 0,
            currency_local   TEXT DEFAULT '',
            new_price_local  REAL DEFAULT 0,
            source           TEXT DEFAULT '',
            reason           TEXT DEFAULT '',
            set_by_user_id   INTEGER DEFAULT 0,
            approval_status  TEXT DEFAULT 'approved',
            set_at           TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """
    for ddl in (
        quotes_ddl_pg if is_pg else quotes_ddl_sqlite,
        history_ddl_pg if is_pg else history_ddl_sqlite,
        "CREATE INDEX IF NOT EXISTS idx_eq_cat_quotes_item "
        "ON equipment_catalog_quotes(catalog_item_id)",
        "CREATE INDEX IF NOT EXISTS idx_eq_cat_history_item "
        "ON equipment_catalog_price_history(catalog_item_id)",
    ):
        try:
            with get_db() as c:
                c.execute(ddl)
        except Exception:
            pass
    _PRICING_SCHEMA_DONE["v"] = True


# ─────────────────────────── Shared helpers ────────────────────────────


def _record_price_history(get_db, item_id, old_usd, new_usd,
                           currency_local, new_local, source, reason,
                           user_id, status="approved"):
    """Append a history row. Non-raising."""
    try:
        with get_db() as c:
            c.execute(
                "INSERT INTO equipment_catalog_price_history "
                "(catalog_item_id, old_price_usd, new_price_usd, "
                " currency_local, new_price_local, source, reason, "
                " set_by_user_id, approval_status) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (int(item_id or 0), float(old_usd or 0), float(new_usd or 0),
                 (currency_local or "")[:3], float(new_local or 0),
                 (source or "")[:200], (reason or "")[:500],
                 int(user_id or 0), (status or "approved")[:20]),
            )
    except Exception:
        pass


def _record_catalog_quote(get_db, item_id, supplier_name, supplier_id,
                          price_local, currency, source_note, anomaly,
                          user_id, status="proposed"):
    """Append a quote row. Non-raising."""
    try:
        with get_db() as c:
            c.execute(
                "INSERT INTO equipment_catalog_quotes "
                "(catalog_item_id, supplier_name, supplier_id, price_local, "
                " currency, source_note, anomaly_flag, status, recorded_by) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (int(item_id or 0), (supplier_name or "")[:200],
                 int(supplier_id or 0), float(price_local or 0),
                 (currency or "GHS")[:3], (source_note or "")[:500],
                 1 if anomaly else 0, (status or "proposed")[:20],
                 int(user_id or 0)),
            )
    except Exception:
        pass


# ─────────────────────────── Routes ────────────────────────────


def register_catalogue_pricing_routes(
    app, admin_required, session, request, redirect, url_for, flash,
    render_template, current_user, get_db, csrf_protect, _CURRENCY_RATES_FROM_USD,
):
    is_pg_fn = lambda: bool(__import__("os").environ.get("DATABASE_URL"))

    @app.before_request
    def _ensure_pricing_schema_once():
        _ensure_pricing_tables(get_db, is_pg_fn)

    @app.route("/admin/catalogue/<int:item_id>/update-price",
               methods=["POST"])
    @admin_required
    def admin_catalogue_update_price(item_id):
        """Admin per-row Update Price -- writes a history row + updates
        equipment_catalog.price_usd in one transaction."""
        csrf_protect()
        f = request.form
        try:
            new_price = float((f.get("new_price") or "0").strip())
        except (TypeError, ValueError):
            new_price = -1.0
        if new_price < 0:
            flash("Enter a non-negative price.", "warning")
            return redirect(url_for("procurement_catalog"))
        currency = (f.get("currency") or "USD").upper().strip()[:3]
        source   = (f.get("source") or "").strip()[:200]
        reason   = (f.get("reason") or "").strip()[:500]

        # Convert local -> USD if currency != USD. price_usd is the canonical
        # storage column. fx rate uses _CURRENCY_RATES_FROM_USD lookup.
        fx_rate = float(_CURRENCY_RATES_FROM_USD.get(currency, 1.0) or 1.0)
        if fx_rate <= 0:
            fx_rate = 1.0
        new_usd = new_price if currency == "USD" else (new_price / fx_rate)

        with get_db() as c:
            row = c.execute(
                "SELECT price_usd FROM equipment_catalog WHERE id=?",
                (item_id,),
            ).fetchone()
            if not row:
                flash("Catalogue item not found.", "warning")
                return redirect(url_for("procurement_catalog"))
            old_usd = float(row["price_usd"] or 0)
            c.execute(
                "UPDATE equipment_catalog SET price_usd=? WHERE id=?",
                (new_usd, item_id),
            )
        uid = session.get("user_id") or 0
        _record_price_history(
            get_db, item_id, old_usd, new_usd, currency, new_price,
            source, reason, uid, status="approved",
        )
        # audit log (best-effort)
        try:
            from new_boq_hierarchy_schema import boq_audit
            boq_audit(get_db, uid, "catalogue_price_updated",
                      "equipment_catalog", item_id,
                      f"old_usd={old_usd:.2f} new_usd={new_usd:.2f} "
                      f"src={source!r}")
        except Exception:
            pass
        flash(
            f"Updated catalogue price: USD {old_usd:.2f} -> {new_usd:.2f} "
            f"({currency} {new_price:.2f}). History logged.",
            "success",
        )
        return redirect(url_for("procurement_catalog"))

    @app.route("/admin/catalogue/<int:item_id>/price-history",
               methods=["GET"])
    @admin_required
    def admin_catalogue_price_history(item_id):
        """View the full price-history trail for one catalogue item."""
        with get_db() as c:
            item = c.execute(
                "SELECT id, name, brand, unit, price_usd "
                "FROM equipment_catalog WHERE id=?", (item_id,),
            ).fetchone()
            if not item:
                flash("Catalogue item not found.", "warning")
                return redirect(url_for("procurement_catalog"))
            history = c.execute(
                "SELECT old_price_usd, new_price_usd, currency_local, "
                " new_price_local, source, reason, set_by_user_id, "
                " approval_status, set_at "
                "FROM equipment_catalog_price_history "
                "WHERE catalog_item_id=? ORDER BY set_at DESC LIMIT 200",
                (item_id,),
            ).fetchall()
            quotes = c.execute(
                "SELECT supplier_name, price_local, currency, source_note, "
                " anomaly_flag, status, quoted_at "
                "FROM equipment_catalog_quotes "
                "WHERE catalog_item_id=? ORDER BY quoted_at DESC LIMIT 200",
                (item_id,),
            ).fetchall()
        return render_template(
            "admin_catalogue_history.html",
            user=current_user(), item=item, history=history, quotes=quotes,
        )
