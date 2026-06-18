# ─── Routes — Procurement Center + Basic Price Sheet ──────────────────────────
# Slice 9: the user-facing "Procurement Center" entry point. After login the
# user lands on /procurement-center, searches catalog products, ticks the
# checkbox on each one they want, picks a currency + doc type (Basic Price
# Sheet / BOM / BOQ) from the left-side panel, and clicks Add. The chosen
# products land in a new document of the selected type, prices converted
# to the picked currency.
#
# Basic Price Sheet is new — it's a reference list with qty=1 per row and
# supplier contact details (name, brand, phone, email, address) so the
# estimator can call the supplier directly. BOM + BOQ reuse the existing
# Slice 5+8 surfaces.

_CURRENCY_RATES_FROM_USD = {
    # Indicative rates — refreshed periodically. Customers see a disclaimer
    # so they know to verify before quoting.
    "USD": 1.0,
    "EUR": 0.93,
    "GBP": 0.79,
    "GHS": 14.5,
    "NGN": 1550.0,
    "KES": 130.0,
    "ZAR": 18.5,
}
_CURRENCY_RATES_AS_OF = "2026-06-18"


def _convert_from_usd(price_usd: float, currency: str) -> float:
    rate = _CURRENCY_RATES_FROM_USD.get(
        (currency or "USD").upper(), 1.0
    )
    return float(price_usd or 0) * float(rate or 1.0)


def _ensure_price_sheet_tables():
    """Idempotent — works on both SQLite (dev) and Postgres (Render)."""
    is_pg = bool(os.environ.get("DATABASE_URL"))
    if is_pg:
        for ddl in [
            """CREATE TABLE IF NOT EXISTS marketplace_price_sheets (
                id            SERIAL PRIMARY KEY,
                user_id       INTEGER NOT NULL,
                title         VARCHAR(300) NOT NULL,
                currency      VARCHAR(3) DEFAULT 'GHS',
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_marketplace_price_sheets_user ON marketplace_price_sheets(user_id)",
            """CREATE TABLE IF NOT EXISTS marketplace_price_sheet_items (
                id                 SERIAL PRIMARY KEY,
                sheet_id           INTEGER NOT NULL,
                product_id         INTEGER DEFAULT 0,
                custom_name        VARCHAR(300) NOT NULL,
                unit               VARCHAR(20) DEFAULT 'No.',
                price_at_add       REAL DEFAULT 0,
                supplier_name      VARCHAR(200) DEFAULT '',
                supplier_brand     VARCHAR(120) DEFAULT '',
                supplier_phone     VARCHAR(40) DEFAULT '',
                supplier_email     VARCHAR(200) DEFAULT '',
                supplier_address   TEXT DEFAULT '',
                created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_marketplace_price_sheet_items_sheet ON marketplace_price_sheet_items(sheet_id)",
        ]:
            try:
                with get_db() as c:
                    c.execute(ddl)
            except Exception:
                pass
        return
    with get_db() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS marketplace_price_sheets (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                title         TEXT NOT NULL,
                currency      TEXT DEFAULT 'GHS',
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at    TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_marketplace_price_sheets_user
                ON marketplace_price_sheets(user_id);
            CREATE TABLE IF NOT EXISTS marketplace_price_sheet_items (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                sheet_id          INTEGER NOT NULL,
                product_id        INTEGER DEFAULT 0,
                custom_name       TEXT NOT NULL,
                unit              TEXT DEFAULT 'No.',
                price_at_add      REAL DEFAULT 0,
                supplier_name     TEXT DEFAULT '',
                supplier_brand    TEXT DEFAULT '',
                supplier_phone    TEXT DEFAULT '',
                supplier_email    TEXT DEFAULT '',
                supplier_address  TEXT DEFAULT '',
                created_at        TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_marketplace_price_sheet_items_sheet
                ON marketplace_price_sheet_items(sheet_id);
        """)


def _price_sheet_owned_or_404(sheet_id: int, user_id: int):
    with get_db() as c:
        row = c.execute(
            "SELECT * FROM marketplace_price_sheets WHERE id=? AND user_id=?",
            (sheet_id, user_id),
        ).fetchone()
    if not row:
        abort(404)
    return row


# ──────────────────────── GET /procurement-center ───────────────────────


@app.route("/procurement-center")
@login_required
def procurement_center():
    _ensure_marketplace_tables()
    _ensure_supplier_schema()
    _ensure_price_sheet_tables()
    q = (request.args.get("q") or "").strip()
    cat_id = _safe_int(request.args.get("cat"), 0)
    currency = (request.args.get("currency") or "GHS").strip().upper()
    if currency not in _CURRENCY_RATES_FROM_USD:
        currency = "GHS"

    with get_db() as c:
        categories = c.execute(
            "SELECT id, name, icon, "
            "  (SELECT COUNT(*) FROM equipment_catalog ec "
            "   WHERE ec.category_id=pc.id AND ec.is_active=1 "
            "         AND ec.is_public_visible=1 AND ec.is_verified=1) AS n "
            "FROM product_categories pc WHERE pc.is_active=1 "
            "ORDER BY pc.display_order"
        ).fetchall()

        sql = (
            "SELECT ec.id, ec.name, ec.brand, ec.model, ec.spec, ec.unit, "
            "       ec.price_usd, ec.lead_time_days, "
            "       s.name AS supplier_name, s.country AS supplier_country, "
            "       s.phone AS supplier_phone, s.email AS supplier_email, "
            "       pc.name AS category_name, pc.icon AS category_icon "
            "FROM equipment_catalog ec "
            "LEFT JOIN suppliers s ON s.id=ec.supplier_id "
            "LEFT JOIN product_categories pc ON pc.id=ec.category_id "
            "WHERE ec.is_active=1 AND ec.is_public_visible=1 AND ec.is_verified=1 "
        )
        args = []
        if cat_id:
            sql += "AND ec.category_id=? "
            args.append(cat_id)
        if q:
            like = f"%{q.lower()}%"
            sql += ("AND (LOWER(ec.name) LIKE ? OR LOWER(ec.brand) LIKE ? "
                    "     OR LOWER(ec.model) LIKE ? OR LOWER(ec.spec) LIKE ?) ")
            args.extend([like, like, like, like])
        sql += "ORDER BY ec.created_at DESC LIMIT 200"
        products = c.execute(sql, args).fetchall()

    # Pre-compute per-product converted price for the template.
    rate = _CURRENCY_RATES_FROM_USD.get(currency, 1.0)
    products_view = []
    for p in products:
        d = dict(p)
        d["price_in_currency"] = float(d["price_usd"] or 0) * rate
        products_view.append(d)

    return render_template(
        "procurement_center.html",
        user=current_user(),
        categories=categories,
        products=products_view,
        selected_cat=cat_id,
        q=q,
        currency=currency,
        currencies=list(_CURRENCY_RATES_FROM_USD.keys()),
        rates_as_of=_CURRENCY_RATES_AS_OF,
    )


# ──────────────────────── POST /procurement-center/add ──────────────────


@app.route("/procurement-center/add", methods=["POST"])
@login_required
def procurement_center_add():
    """Take the checked product IDs from the form + the chosen doc type
    + currency, and create the new doc populated with those products."""
    csrf_protect()
    _ensure_marketplace_tables()
    _ensure_supplier_schema()
    _ensure_bom_tables()
    _ensure_price_sheet_tables()
    uid = session["user_id"]

    doc_type = (request.form.get("doc_type") or "").strip()
    currency = (request.form.get("currency") or "GHS").strip().upper()
    if currency not in _CURRENCY_RATES_FROM_USD:
        currency = "GHS"
    if doc_type not in ("price_sheet", "bom", "boq"):
        flash("Choose a document type (Basic Price Sheet, BOM, or BOQ).", "danger")
        return redirect(url_for("procurement_center"))

    raw_pids = request.form.getlist("product_ids")
    pids = [int(x) for x in raw_pids if x.isdigit()]
    if not pids:
        flash("Tick at least one product on the grid before clicking Add.", "danger")
        return redirect(url_for("procurement_center"))

    # Fetch the selected products + supplier contact in one query.
    with get_db() as c:
        placeholders = ",".join(["?"] * len(pids))
        rows = c.execute(
            f"SELECT ec.id, ec.name, ec.brand, ec.model, ec.spec, ec.unit, "
            f"       ec.price_usd, "
            f"       s.name AS supplier_name, s.phone AS supplier_phone, "
            f"       s.email AS supplier_email, s.address AS supplier_address "
            f"FROM equipment_catalog ec "
            f"LEFT JOIN suppliers s ON s.id=ec.supplier_id "
            f"WHERE ec.id IN ({placeholders}) "
            f"  AND ec.is_active=1 AND ec.is_public_visible=1 AND ec.is_verified=1",
            pids,
        ).fetchall()

    if not rows:
        flash("None of the selected products are available.", "danger")
        return redirect(url_for("procurement_center"))

    rate = _CURRENCY_RATES_FROM_USD.get(currency, 1.0)
    today = datetime.now().strftime("%Y-%m-%d")

    if doc_type == "price_sheet":
        with get_db() as c:
            cur = c.execute(
                "INSERT INTO marketplace_price_sheets (user_id, title, currency) "
                "VALUES (?, ?, ?)",
                (uid, f"Price Sheet — {today}", currency),
            )
            sheet_id = cur.lastrowid
            for r in rows:
                price_in_currency = float(r["price_usd"] or 0) * rate
                c.execute(
                    "INSERT INTO marketplace_price_sheet_items "
                    "(sheet_id, product_id, custom_name, unit, price_at_add, "
                    " supplier_name, supplier_brand, supplier_phone, "
                    " supplier_email, supplier_address) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        sheet_id, r["id"], r["name"], r["unit"] or "No.",
                        round(price_in_currency, 2),
                        r["supplier_name"] or "",
                        r["brand"] or "",
                        r["supplier_phone"] or "",
                        r["supplier_email"] or "",
                        r["supplier_address"] or "",
                    ),
                )
        flash(
            f"Basic Price Sheet created with {len(rows)} item"
            f"{'s' if len(rows) != 1 else ''} in {currency}.", "success",
        )
        return redirect(url_for("price_sheet_view", sheet_id=sheet_id))

    if doc_type == "bom":
        with get_db() as c:
            cur = c.execute(
                "INSERT INTO marketplace_boms (user_id, title) VALUES (?, ?)",
                (uid, f"BOM — {today}"),
            )
            bom_id = cur.lastrowid
            for r in rows:
                c.execute(
                    "INSERT INTO marketplace_bom_items "
                    "(bom_id, product_id, custom_name, qty, unit) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (bom_id, r["id"], r["name"], 1, r["unit"] or "No."),
                )
        flash(f"BOM created with {len(rows)} item{'s' if len(rows) != 1 else ''}.", "success")
        return redirect(url_for("boms_view", bom_id=bom_id))

    # doc_type == "boq" — same as BOM today since the BOQ is a printable
    # view of a BOM. Land them in the BOM editor; they then click View BOQ
    # / Excel / PDF from there.
    with get_db() as c:
        cur = c.execute(
            "INSERT INTO marketplace_boms (user_id, title) VALUES (?, ?)",
            (uid, f"BOQ — {today}"),
        )
        bom_id = cur.lastrowid
        for r in rows:
            c.execute(
                "INSERT INTO marketplace_bom_items "
                "(bom_id, product_id, custom_name, qty, unit) "
                "VALUES (?, ?, ?, ?, ?)",
                (bom_id, r["id"], r["name"], 1, r["unit"] or "No."),
            )
    flash(
        f"BOQ draft created with {len(rows)} item"
        f"{'s' if len(rows) != 1 else ''}. Set quantities + rates, then view the BOQ.",
        "success",
    )
    return redirect(url_for("boms_view", bom_id=bom_id))


# ──────────────────────── Price Sheet list / view ───────────────────────


@app.route("/price-sheets")
@login_required
def price_sheets_list():
    _ensure_price_sheet_tables()
    uid = session["user_id"]
    with get_db() as c:
        rows = c.execute(
            "SELECT s.*, "
            "  (SELECT COUNT(*) FROM marketplace_price_sheet_items "
            "   WHERE sheet_id=s.id) AS item_count "
            "FROM marketplace_price_sheets s "
            "WHERE s.user_id=? ORDER BY s.updated_at DESC",
            (uid,),
        ).fetchall()
    return render_template(
        "price_sheets_list.html", user=current_user(), sheets=rows
    )


@app.route("/price-sheets/<int:sheet_id>")
@login_required
def price_sheet_view(sheet_id):
    _ensure_price_sheet_tables()
    uid = session["user_id"]
    sheet = _price_sheet_owned_or_404(sheet_id, uid)
    with get_db() as c:
        items = c.execute(
            "SELECT * FROM marketplace_price_sheet_items "
            "WHERE sheet_id=? ORDER BY id",
            (sheet_id,),
        ).fetchall()
    return render_template(
        "price_sheet_view.html",
        user=current_user(), sheet=sheet, items=items,
        rates_as_of=_CURRENCY_RATES_AS_OF,
    )
