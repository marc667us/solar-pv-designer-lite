# ─── Routes — Marketplace BOM / BOQ Builder ───────────────────────────────────
# Slice 5: logged-in users build a Bill of Materials by adding marketplace
# products, override per-line unit prices when needed, then export as a
# printable BOQ or clone the whole BOM into an RFQ to chase live prices from
# suppliers.

def _ensure_bom_tables():
    """Idempotent — two new tables for the BOM/BOQ builder."""
    with get_db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS marketplace_boms (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                title         TEXT NOT NULL,
                project_name  TEXT DEFAULT '',
                client_name   TEXT DEFAULT '',
                notes         TEXT DEFAULT '',
                status        TEXT DEFAULT 'draft',
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at    TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_marketplace_boms_user
                ON marketplace_boms(user_id);

            CREATE TABLE IF NOT EXISTS marketplace_bom_items (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                bom_id              INTEGER NOT NULL,
                product_id          INTEGER DEFAULT 0,
                custom_name         TEXT NOT NULL,
                qty                 REAL DEFAULT 1,
                unit                TEXT DEFAULT 'No.',
                unit_price_override REAL,
                notes               TEXT DEFAULT '',
                created_at          TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_marketplace_bom_items_bom
                ON marketplace_bom_items(bom_id);
            """
        )


def _bom_owned_or_404(bom_id: int, user_id: int):
    """Tenant scope: a BOM is only visible to its owner."""
    with get_db() as c:
        row = c.execute(
            "SELECT * FROM marketplace_boms WHERE id=? AND user_id=?",
            (bom_id, user_id),
        ).fetchone()
    if not row:
        abort(404)
    return row


def _bom_items_with_prices(bom_id: int):
    """Fetch BOM items joined to the catalog so we have current prices
    + category names ready for both the editor and the printable BOQ."""
    with get_db() as c:
        return c.execute(
            "SELECT bi.*, "
            "       ec.name        AS catalog_name, "
            "       ec.brand       AS catalog_brand, "
            "       ec.model       AS catalog_model, "
            "       ec.spec        AS catalog_spec, "
            "       ec.price_usd   AS catalog_price, "
            "       ec.is_verified AS catalog_verified, "
            "       s.name         AS supplier_name, "
            "       s.country      AS supplier_country, "
            "       pc.name        AS category_name "
            "FROM marketplace_bom_items bi "
            "LEFT JOIN equipment_catalog ec   ON ec.id=bi.product_id "
            "LEFT JOIN suppliers s            ON s.id=ec.supplier_id "
            "LEFT JOIN product_categories pc  ON pc.id=ec.category_id "
            "WHERE bi.bom_id=? "
            "ORDER BY pc.display_order, bi.id",
            (bom_id,),
        ).fetchall()


def _bom_totals(items) -> dict:
    """Roll up line totals + category subtotals."""
    cat_totals: dict[str, float] = {}
    grand = 0.0
    lines = []
    for it in items:
        price = (
            it["unit_price_override"]
            if it["unit_price_override"] is not None
            else (it["catalog_price"] or 0)
        )
        line_total = float(price or 0) * float(it["qty"] or 0)
        cat = it["category_name"] or "Uncategorised"
        cat_totals[cat] = cat_totals.get(cat, 0) + line_total
        grand += line_total
        lines.append({"item": it, "unit_price": float(price or 0),
                      "line_total": line_total})
    return {"lines": lines, "category_totals": cat_totals, "grand_total": grand}


# ──────────────────────── BOM list / new ─────────────────────────────────


@app.route("/boms")
@login_required
def boms_list():
    _ensure_bom_tables()
    uid = session["user_id"]
    with get_db() as c:
        rows = c.execute(
            "SELECT b.*, "
            "  (SELECT COUNT(*) FROM marketplace_bom_items WHERE bom_id=b.id) AS item_count "
            "FROM marketplace_boms b "
            "WHERE b.user_id=? ORDER BY b.updated_at DESC",
            (uid,),
        ).fetchall()
    return render_template("boms_list.html", user=current_user(), boms=rows)


@app.route("/boms/new", methods=["GET", "POST"])
@login_required
def boms_new():
    _ensure_bom_tables()
    uid = session["user_id"]
    if request.method == "GET":
        return render_template("bom_new.html", user=current_user())
    csrf_protect()
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Give your BOM a title.", "danger")
        return redirect(url_for("boms_new"))
    with get_db() as c:
        cur = c.execute(
            "INSERT INTO marketplace_boms "
            "(user_id, title, project_name, client_name, notes) "
            "VALUES (?,?,?,?,?)",
            (
                uid, title,
                (request.form.get("project_name") or "").strip(),
                (request.form.get("client_name") or "").strip(),
                (request.form.get("notes") or "").strip(),
            ),
        )
        bom_id = cur.lastrowid
    flash("BOM draft created.", "success")
    return redirect(url_for("boms_view", bom_id=bom_id))


@app.route("/boms/<int:bom_id>")
@login_required
def boms_view(bom_id):
    _ensure_bom_tables()
    uid = session["user_id"]
    bom = _bom_owned_or_404(bom_id, uid)
    items = _bom_items_with_prices(bom_id)
    totals = _bom_totals(items)
    return render_template(
        "bom_view.html",
        user=current_user(),
        bom=bom, items=items, totals=totals,
    )


# ──────────────────────── BOM item add / update / delete ────────────────


@app.route("/boms/<int:bom_id>/items/add", methods=["POST"])
@login_required
def boms_add_item(bom_id):
    uid = session["user_id"]
    bom = _bom_owned_or_404(bom_id, uid)
    csrf_protect()
    f = request.form
    name = (f.get("name") or "").strip()
    if not name:
        flash("Item name is required.", "danger")
        return redirect(url_for("boms_view", bom_id=bom_id))
    try:
        qty = float(f.get("qty") or 1)
    except ValueError:
        qty = 1
    pid = _safe_int(f.get("product_id"), 0)
    # Validate product_id against a real public verified product.
    if pid:
        with get_db() as c:
            ok = c.execute(
                "SELECT 1 FROM equipment_catalog "
                "WHERE id=? AND is_active=1 AND is_public_visible=1 AND is_verified=1",
                (pid,),
            ).fetchone()
        if not ok:
            pid = 0
    override_raw = (f.get("unit_price_override") or "").strip()
    try:
        override = float(override_raw) if override_raw else None
    except ValueError:
        override = None
    with get_db() as c:
        c.execute(
            "INSERT INTO marketplace_bom_items "
            "(bom_id, product_id, custom_name, qty, unit, unit_price_override, notes) "
            "VALUES (?,?,?,?,?,?,?)",
            (bom_id, pid, name, qty,
             (f.get("unit") or "No.").strip(),
             override,
             (f.get("notes") or "").strip()),
        )
        c.execute(
            "UPDATE marketplace_boms SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (bom_id,),
        )
    return redirect(url_for("boms_view", bom_id=bom_id))


@app.route("/boms/<int:bom_id>/items/<int:item_id>/delete", methods=["POST"])
@login_required
def boms_delete_item(bom_id, item_id):
    uid = session["user_id"]
    bom = _bom_owned_or_404(bom_id, uid)
    csrf_protect()
    with get_db() as c:
        c.execute(
            "DELETE FROM marketplace_bom_items WHERE id=? AND bom_id=?",
            (item_id, bom_id),
        )
        c.execute(
            "UPDATE marketplace_boms SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (bom_id,),
        )
    return redirect(url_for("boms_view", bom_id=bom_id))


# ──────────────────────── Marketplace → BOM funnel ───────────────────────


@app.route("/boms/add-product/<int:pid>", methods=["POST"])
@login_required
def boms_add_from_marketplace(pid):
    """One-click "Add to BOM" from a marketplace product card.

    POST-only with CSRF protection — a state-mutating endpoint must not be
    a GET (Codex finding: a third-party page could trigger insertion via
    <img src=...> on a logged-in user). The marketplace template renders
    this as a tiny <form method="POST"> per card.

    Picks the user's most-recently-updated draft BOM and appends the product;
    if no draft exists, creates a fresh BOM titled with today's date. Then
    redirects to /boms/<id>."""
    csrf_protect()
    _ensure_bom_tables()
    _ensure_marketplace_tables()
    uid = session["user_id"]
    with get_db() as c:
        product = c.execute(
            "SELECT id, name, unit, brand FROM equipment_catalog "
            "WHERE id=? AND is_active=1 AND is_public_visible=1 AND is_verified=1",
            (pid,),
        ).fetchone()
    if not product:
        flash("Product is no longer available.", "warning")
        return redirect(url_for("marketplace_public"))
    with get_db() as c:
        draft = c.execute(
            "SELECT id, title FROM marketplace_boms "
            "WHERE user_id=? AND status='draft' "
            "ORDER BY updated_at DESC LIMIT 1",
            (uid,),
        ).fetchone()
        if draft:
            bom_id = draft["id"]
        else:
            cur = c.execute(
                "INSERT INTO marketplace_boms (user_id, title) VALUES (?,?)",
                (uid, f"Quick BOM — {datetime.now().strftime('%Y-%m-%d %H:%M')}"),
            )
            bom_id = cur.lastrowid
        c.execute(
            "INSERT INTO marketplace_bom_items "
            "(bom_id, product_id, custom_name, qty, unit) "
            "VALUES (?,?,?,?,?)",
            (bom_id, pid, product["name"], 1, product["unit"] or "No."),
        )
        c.execute(
            "UPDATE marketplace_boms SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (bom_id,),
        )
    flash(f"Added '{product['name']}' to BOM.", "success")
    return redirect(url_for("boms_view", bom_id=bom_id))


# ──────────────────────── BOM → RFQ funnel ───────────────────────────────


@app.route("/boms/<int:bom_id>/clone-to-rfq", methods=["POST"])
@login_required
def boms_clone_to_rfq(bom_id):
    """Create a fresh RFQ pre-populated with every BOM item."""
    uid = session["user_id"]
    bom = _bom_owned_or_404(bom_id, uid)
    csrf_protect()
    _ensure_rfq_tables()
    items = _bom_items_with_prices(bom_id)
    if not items:
        flash("Add items to the BOM before cloning to an RFQ.", "danger")
        return redirect(url_for("boms_view", bom_id=bom_id))
    with get_db() as c:
        cur = c.execute(
            "INSERT INTO rfqs (user_id, title, notes) VALUES (?,?,?)",
            (uid, f"From BOM: {bom['title']}",
             f"Cloned from BOM #{bom_id} on {datetime.now().strftime('%Y-%m-%d')}"),
        )
        rfq_id = cur.lastrowid
        for it in items:
            c.execute(
                "INSERT INTO rfq_items "
                "(rfq_id, product_id, custom_name, qty, unit, spec_notes) "
                "VALUES (?,?,?,?,?,?)",
                (rfq_id, it["product_id"], it["custom_name"], it["qty"],
                 it["unit"], it["notes"] or ""),
            )
    flash(f"Created RFQ from BOM ({len(items)} items).", "success")
    return redirect(url_for("rfqs_view", rfq_id=rfq_id))


# ──────────────────────── BOQ printable + PDF ────────────────────────────


@app.route("/boms/<int:bom_id>/boq")
@login_required
def boms_boq(bom_id):
    uid = session["user_id"]
    bom = _bom_owned_or_404(bom_id, uid)
    items = _bom_items_with_prices(bom_id)
    totals = _bom_totals(items)
    return render_template(
        "bom_boq.html",
        user=current_user(),
        bom=bom, items=items, totals=totals,
    )
