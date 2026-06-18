# ─── Routes — Marketplace RFQ Workflow ────────────────────────────────────────
# Slice 4: logged-in users build an RFQ from marketplace products, send it to
# selected suppliers, suppliers respond with prices + lead-time, buyer compares
# and awards. All four sides (buyer, supplier, marketplace, admin audit) ride
# off the same RFQ tables defined here.

_RFQ_STATUSES = {"draft", "sent", "awarded", "cancelled", "expired"}
_RFQ_TARGET_STATUSES = {"pending", "responded", "declined"}


def _ensure_rfq_tables():
    """Idempotent — five tables for the RFQ workflow."""
    with get_db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS rfqs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id             INTEGER NOT NULL,
                title               TEXT NOT NULL,
                delivery_country    TEXT DEFAULT '',
                deadline_date       TEXT DEFAULT '',
                notes               TEXT DEFAULT '',
                status              TEXT DEFAULT 'draft',
                awarded_supplier_id INTEGER DEFAULT 0,
                created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
                sent_at             TEXT DEFAULT '',
                updated_at          TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_rfqs_user ON rfqs(user_id);
            CREATE INDEX IF NOT EXISTS idx_rfqs_status ON rfqs(status);

            CREATE TABLE IF NOT EXISTS rfq_items (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                rfq_id       INTEGER NOT NULL,
                product_id   INTEGER DEFAULT 0,
                custom_name  TEXT NOT NULL,
                qty          REAL DEFAULT 1,
                unit         TEXT DEFAULT 'No.',
                spec_notes   TEXT DEFAULT '',
                created_at   TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_rfq_items_rfq ON rfq_items(rfq_id);

            CREATE TABLE IF NOT EXISTS rfq_supplier_targets (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                rfq_id        INTEGER NOT NULL,
                supplier_id   INTEGER NOT NULL,
                status        TEXT DEFAULT 'pending',
                sent_at       TEXT DEFAULT CURRENT_TIMESTAMP,
                responded_at  TEXT DEFAULT '',
                UNIQUE(rfq_id, supplier_id)
            );
            CREATE INDEX IF NOT EXISTS idx_rfq_targets_supplier ON rfq_supplier_targets(supplier_id);
            CREATE INDEX IF NOT EXISTS idx_rfq_targets_rfq ON rfq_supplier_targets(rfq_id);

            CREATE TABLE IF NOT EXISTS rfq_responses (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                rfq_id          INTEGER NOT NULL,
                supplier_id     INTEGER NOT NULL,
                total_price     REAL DEFAULT 0,
                currency        TEXT DEFAULT 'USD',
                lead_time_days  INTEGER DEFAULT 30,
                notes           TEXT DEFAULT '',
                valid_until     TEXT DEFAULT '',
                created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(rfq_id, supplier_id)
            );
            CREATE INDEX IF NOT EXISTS idx_rfq_responses_rfq ON rfq_responses(rfq_id);

            CREATE TABLE IF NOT EXISTS rfq_response_items (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                response_id    INTEGER NOT NULL,
                rfq_item_id    INTEGER NOT NULL,
                unit_price     REAL DEFAULT 0,
                available      INTEGER DEFAULT 1,
                notes          TEXT DEFAULT '',
                UNIQUE(response_id, rfq_item_id)
            );
            CREATE INDEX IF NOT EXISTS idx_rfq_resp_items_resp ON rfq_response_items(response_id);
            """
        )


def _rfq_owned_or_404(rfq_id: int, user_id: int):
    """Fetch an RFQ row only if the current user owns it; otherwise abort 404
    to avoid leaking RFQ existence."""
    with get_db() as c:
        row = c.execute(
            "SELECT * FROM rfqs WHERE id=? AND user_id=?", (rfq_id, user_id)
        ).fetchone()
    if not row:
        abort(404)
    return row


def _supplier_can_see_rfq(rfq_id: int, supplier_id: int) -> bool:
    with get_db() as c:
        row = c.execute(
            "SELECT 1 FROM rfq_supplier_targets WHERE rfq_id=? AND supplier_id=?",
            (rfq_id, supplier_id),
        ).fetchone()
    return bool(row)


# ──────────────────────── BUYER side ──────────────────────────────────────


@app.route("/rfqs")
@login_required
def rfqs_list():
    """List the current user's RFQs (drafts + sent + awarded)."""
    _ensure_rfq_tables()
    uid = session["user_id"]
    with get_db() as c:
        rows = c.execute(
            "SELECT r.*, "
            "  (SELECT COUNT(*) FROM rfq_items WHERE rfq_id=r.id) AS item_count, "
            "  (SELECT COUNT(*) FROM rfq_supplier_targets WHERE rfq_id=r.id) AS sent_to, "
            "  (SELECT COUNT(*) FROM rfq_responses WHERE rfq_id=r.id) AS responses "
            "FROM rfqs r WHERE r.user_id=? ORDER BY r.updated_at DESC",
            (uid,),
        ).fetchall()
    return render_template("rfqs_list.html", user=current_user(), rfqs=rows)


@app.route("/rfqs/new", methods=["GET", "POST"])
@login_required
def rfqs_new():
    _ensure_rfq_tables()
    _ensure_marketplace_tables()
    uid = session["user_id"]

    if request.method == "GET":
        # Optional ?product_id=X — pre-populate the first line from the
        # marketplace card the buyer just clicked.
        seed_pid = _safe_int(request.args.get("product_id"), 0)
        seed_product = None
        if seed_pid:
            with get_db() as c:
                seed_product = c.execute(
                    "SELECT id, name, unit FROM equipment_catalog "
                    "WHERE id=? AND is_active=1 AND is_public_visible=1 AND is_verified=1",
                    (seed_pid,),
                ).fetchone()
        return render_template(
            "rfq_new.html",
            user=current_user(),
            countries=get_countries(),
            seed_product=seed_product,
        )

    csrf_protect()
    f = request.form
    title = (f.get("title") or "").strip()
    if not title:
        flash("Give your RFQ a title.", "danger")
        return redirect(url_for("rfqs_new"))
    with get_db() as c:
        cur = c.execute(
            "INSERT INTO rfqs (user_id, title, delivery_country, deadline_date, notes) "
            "VALUES (?,?,?,?,?)",
            (
                uid, title,
                (f.get("delivery_country") or "").strip(),
                (f.get("deadline_date") or "").strip(),
                (f.get("notes") or "").strip(),
            ),
        )
        rfq_id = cur.lastrowid
        # Optional first item from seed_product or the form.
        first_name = (f.get("first_item_name") or "").strip()
        first_pid = _safe_int(f.get("first_item_product_id"), 0)
        if first_name:
            c.execute(
                "INSERT INTO rfq_items (rfq_id, product_id, custom_name, qty, unit, spec_notes) "
                "VALUES (?,?,?,?,?,?)",
                (
                    rfq_id, first_pid, first_name,
                    float(f.get("first_item_qty") or 1),
                    (f.get("first_item_unit") or "No.").strip(),
                    (f.get("first_item_spec") or "").strip(),
                ),
            )
    flash("RFQ draft created.", "success")
    return redirect(url_for("rfqs_view", rfq_id=rfq_id))


@app.route("/rfqs/<int:rfq_id>")
@login_required
def rfqs_view(rfq_id):
    _ensure_rfq_tables()
    uid = session["user_id"]
    rfq = _rfq_owned_or_404(rfq_id, uid)
    with get_db() as c:
        items = c.execute(
            "SELECT ri.*, ec.name AS product_name, ec.brand AS product_brand, "
            "       ec.price_usd AS product_price "
            "FROM rfq_items ri "
            "LEFT JOIN equipment_catalog ec ON ec.id=ri.product_id "
            "WHERE ri.rfq_id=? ORDER BY ri.id",
            (rfq_id,),
        ).fetchall()
        targets = c.execute(
            "SELECT rst.*, s.name AS supplier_name, s.country AS supplier_country "
            "FROM rfq_supplier_targets rst "
            "LEFT JOIN suppliers s ON s.id=rst.supplier_id "
            "WHERE rst.rfq_id=? ORDER BY s.name",
            (rfq_id,),
        ).fetchall()
        responses = c.execute(
            "SELECT rr.*, s.name AS supplier_name, s.country AS supplier_country, "
            "       s.is_verified AS supplier_verified "
            "FROM rfq_responses rr "
            "LEFT JOIN suppliers s ON s.id=rr.supplier_id "
            "WHERE rr.rfq_id=? ORDER BY rr.total_price ASC",
            (rfq_id,),
        ).fetchall()
        # Available suppliers for the "send" picker.
        suppliers = c.execute(
            "SELECT id, name, country FROM suppliers "
            "WHERE is_active=1 AND is_verified=1 "
            "ORDER BY name"
        ).fetchall()
    return render_template(
        "rfq_view.html",
        user=current_user(),
        rfq=rfq,
        items=items,
        targets=targets,
        responses=responses,
        suppliers=suppliers,
    )


@app.route("/rfqs/<int:rfq_id>/items/add", methods=["POST"])
@login_required
def rfqs_add_item(rfq_id):
    uid = session["user_id"]
    rfq = _rfq_owned_or_404(rfq_id, uid)
    if rfq["status"] != "draft":
        abort(400)
    csrf_protect()
    f = request.form
    name = (f.get("name") or "").strip()
    if not name:
        flash("Item name is required.", "danger")
        return redirect(url_for("rfqs_view", rfq_id=rfq_id))
    try:
        qty = float(f.get("qty") or 1)
    except ValueError:
        qty = 1
    pid = _safe_int(f.get("product_id"), 0)
    # If the user passed product_id, validate it's a real public product.
    if pid:
        with get_db() as c:
            ok = c.execute(
                "SELECT 1 FROM equipment_catalog "
                "WHERE id=? AND is_active=1 AND is_public_visible=1 AND is_verified=1",
                (pid,),
            ).fetchone()
        if not ok:
            pid = 0
    with get_db() as c:
        c.execute(
            "INSERT INTO rfq_items (rfq_id, product_id, custom_name, qty, unit, spec_notes) "
            "VALUES (?,?,?,?,?,?)",
            (rfq_id, pid, name, qty,
             (f.get("unit") or "No.").strip(),
             (f.get("spec_notes") or "").strip()),
        )
        c.execute("UPDATE rfqs SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (rfq_id,))
    return redirect(url_for("rfqs_view", rfq_id=rfq_id))


@app.route("/rfqs/<int:rfq_id>/items/<int:item_id>/delete", methods=["POST"])
@login_required
def rfqs_delete_item(rfq_id, item_id):
    uid = session["user_id"]
    rfq = _rfq_owned_or_404(rfq_id, uid)
    if rfq["status"] != "draft":
        abort(400)
    csrf_protect()
    with get_db() as c:
        c.execute(
            "DELETE FROM rfq_items WHERE id=? AND rfq_id=?",
            (item_id, rfq_id),
        )
        c.execute("UPDATE rfqs SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (rfq_id,))
    return redirect(url_for("rfqs_view", rfq_id=rfq_id))


@app.route("/rfqs/<int:rfq_id>/send", methods=["POST"])
@login_required
def rfqs_send(rfq_id):
    uid = session["user_id"]
    rfq = _rfq_owned_or_404(rfq_id, uid)
    if rfq["status"] != "draft":
        abort(400)
    csrf_protect()
    raw_sids = request.form.getlist("supplier_ids")
    sids = [int(x) for x in raw_sids if x.isdigit()]
    if not sids:
        flash("Pick at least one supplier to send to.", "danger")
        return redirect(url_for("rfqs_view", rfq_id=rfq_id))
    with get_db() as c:
        items_n = c.execute(
            "SELECT COUNT(*) FROM rfq_items WHERE rfq_id=?", (rfq_id,)
        ).fetchone()[0]
        if not items_n:
            flash("Add at least one item before sending.", "danger")
            return redirect(url_for("rfqs_view", rfq_id=rfq_id))
        targeted = 0
        for sid in sids:
            # Only target verified active suppliers; skip silently otherwise.
            ok = c.execute(
                "SELECT 1 FROM suppliers WHERE id=? AND is_active=1 AND is_verified=1",
                (sid,),
            ).fetchone()
            if not ok:
                continue
            try:
                c.execute(
                    "INSERT INTO rfq_supplier_targets (rfq_id, supplier_id, status) "
                    "VALUES (?, ?, 'pending')",
                    (rfq_id, sid),
                )
                targeted += 1
            except sqlite3.IntegrityError:
                pass  # already targeted — idempotent
        # If no submitted supplier survived the active+verified filter the
        # RFQ stays in draft. Otherwise it would land in 'sent' status with
        # zero targets and become permanently unanswerable (Codex finding).
        if targeted == 0:
            flash(
                "None of the selected suppliers are currently verified — "
                "the RFQ stays in draft. Pick at least one verified supplier.",
                "danger",
            )
            return redirect(url_for("rfqs_view", rfq_id=rfq_id))
        c.execute(
            "UPDATE rfqs SET status='sent', sent_at=CURRENT_TIMESTAMP, "
            "updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (rfq_id,),
        )
    flash(f"RFQ sent to {targeted} supplier{'s' if targeted != 1 else ''}.", "success")
    return redirect(url_for("rfqs_view", rfq_id=rfq_id))


@app.route("/rfqs/<int:rfq_id>/award/<int:supplier_id>", methods=["POST"])
@login_required
def rfqs_award(rfq_id, supplier_id):
    uid = session["user_id"]
    rfq = _rfq_owned_or_404(rfq_id, uid)
    if rfq["status"] not in ("sent",):
        abort(400)
    csrf_protect()
    with get_db() as c:
        ok = c.execute(
            "SELECT 1 FROM rfq_responses WHERE rfq_id=? AND supplier_id=?",
            (rfq_id, supplier_id),
        ).fetchone()
        if not ok:
            flash("That supplier has not responded — cannot award.", "danger")
            return redirect(url_for("rfqs_view", rfq_id=rfq_id))
        c.execute(
            "UPDATE rfqs SET status='awarded', awarded_supplier_id=?, "
            "updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (supplier_id, rfq_id),
        )
    flash("RFQ awarded.", "success")
    return redirect(url_for("rfqs_view", rfq_id=rfq_id))


@app.route("/rfqs/<int:rfq_id>/cancel", methods=["POST"])
@login_required
def rfqs_cancel(rfq_id):
    uid = session["user_id"]
    rfq = _rfq_owned_or_404(rfq_id, uid)
    if rfq["status"] in ("awarded", "cancelled"):
        abort(400)
    csrf_protect()
    with get_db() as c:
        c.execute(
            "UPDATE rfqs SET status='cancelled', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (rfq_id,),
        )
    flash("RFQ cancelled.", "warning")
    return redirect(url_for("rfqs_list"))


# ──────────────────────── SUPPLIER side ──────────────────────────────────


@app.route("/supplier/rfqs")
@supplier_required
def supplier_rfqs_inbox():
    """List RFQs targeted at the current supplier."""
    _ensure_rfq_tables()
    s = _current_supplier()
    if not s:
        return redirect(url_for("supplier_dashboard"))
    with get_db() as c:
        rows = c.execute(
            "SELECT r.id, r.title, r.delivery_country, r.deadline_date, "
            "       r.status AS rfq_status, r.created_at, r.sent_at, "
            "       rst.status AS target_status, rst.responded_at, "
            "       (SELECT COUNT(*) FROM rfq_items WHERE rfq_id=r.id) AS item_count, "
            "       (SELECT 1 FROM rfq_responses WHERE rfq_id=r.id AND supplier_id=?) AS responded "
            "FROM rfq_supplier_targets rst "
            "JOIN rfqs r ON r.id=rst.rfq_id "
            "WHERE rst.supplier_id=? "
            "ORDER BY rst.sent_at DESC",
            (s["id"], s["id"]),
        ).fetchall()
    return render_template(
        "supplier_rfqs_inbox.html", user=current_user(), supplier=s, rfqs=rows
    )


@app.route("/supplier/rfqs/<int:rfq_id>", methods=["GET", "POST"])
@supplier_required
def supplier_rfqs_respond(rfq_id):
    _ensure_rfq_tables()
    s = _current_supplier()
    if not s:
        return redirect(url_for("supplier_dashboard"))
    # Tenant scope: this supplier must be a target of this RFQ, else 404.
    if not _supplier_can_see_rfq(rfq_id, s["id"]):
        abort(404)
    with get_db() as c:
        rfq = c.execute("SELECT * FROM rfqs WHERE id=?", (rfq_id,)).fetchone()
        if not rfq:
            abort(404)
        items = c.execute(
            "SELECT * FROM rfq_items WHERE rfq_id=? ORDER BY id", (rfq_id,)
        ).fetchall()
        existing = c.execute(
            "SELECT * FROM rfq_responses WHERE rfq_id=? AND supplier_id=?",
            (rfq_id, s["id"]),
        ).fetchone()
        existing_items = {}
        if existing:
            for ri in c.execute(
                "SELECT * FROM rfq_response_items WHERE response_id=?",
                (existing["id"],),
            ).fetchall():
                existing_items[ri["rfq_item_id"]] = ri

    if request.method == "GET":
        return render_template(
            "supplier_rfq_respond.html",
            user=current_user(),
            supplier=s,
            rfq=rfq,
            items=items,
            existing=existing,
            existing_items=existing_items,
        )

    csrf_protect()
    if rfq["status"] != "sent":
        flash("This RFQ is no longer accepting responses.", "warning")
        return redirect(url_for("supplier_rfqs_inbox"))
    f = request.form
    try:
        lead_time = int(f.get("lead_time_days") or 30)
    except ValueError:
        lead_time = 30
    currency = (f.get("currency") or "USD").strip().upper()[:3]
    notes = (f.get("notes") or "").strip()
    valid_until = (f.get("valid_until") or "").strip()

    # Compute total from per-line prices.
    total = 0.0
    line_prices: list[tuple[int, float, int]] = []
    for it in items:
        try:
            unit_price = float(f.get(f"unit_price_{it['id']}") or 0)
        except ValueError:
            unit_price = 0
        available = 1 if f.get(f"available_{it['id']}") else 0
        qty = float(it["qty"] or 0)
        if available and unit_price > 0:
            total += unit_price * qty
        line_prices.append((int(it["id"]), unit_price, available))

    with get_db() as c:
        if existing:
            response_id = existing["id"]
            c.execute(
                "UPDATE rfq_responses "
                "SET total_price=?, currency=?, lead_time_days=?, notes=?, "
                "    valid_until=? "
                "WHERE id=?",
                (total, currency, lead_time, notes, valid_until, response_id),
            )
        else:
            cur = c.execute(
                "INSERT INTO rfq_responses (rfq_id, supplier_id, total_price, "
                "currency, lead_time_days, notes, valid_until) "
                "VALUES (?,?,?,?,?,?,?)",
                (rfq_id, s["id"], total, currency, lead_time, notes, valid_until),
            )
            response_id = cur.lastrowid
        # Upsert per-line entries.
        for (item_id, unit_price, available) in line_prices:
            existing_line = c.execute(
                "SELECT id FROM rfq_response_items WHERE response_id=? AND rfq_item_id=?",
                (response_id, item_id),
            ).fetchone()
            if existing_line:
                c.execute(
                    "UPDATE rfq_response_items "
                    "SET unit_price=?, available=? "
                    "WHERE id=?",
                    (unit_price, available, existing_line["id"]),
                )
            else:
                c.execute(
                    "INSERT INTO rfq_response_items "
                    "(response_id, rfq_item_id, unit_price, available) "
                    "VALUES (?,?,?,?)",
                    (response_id, item_id, unit_price, available),
                )
        c.execute(
            "UPDATE rfq_supplier_targets "
            "SET status='responded', responded_at=CURRENT_TIMESTAMP "
            "WHERE rfq_id=? AND supplier_id=?",
            (rfq_id, s["id"]),
        )

    flash("Response submitted. The buyer can now see your price.", "success")
    return redirect(url_for("supplier_rfqs_inbox"))
