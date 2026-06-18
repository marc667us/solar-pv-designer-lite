# ─── Routes — Marketplace Procurement Specialist + Staff Election + CRUD ──────
# Slice 7: procurement_specialist is a new user role the admin can promote
# any solar user into. Specialists get full CRUD on suppliers, products,
# and prices — they can administer the marketplace without being a global
# is_admin=1 user. Admin still owns the promote/demote action itself.

def procurement_role_required(f):
    """Decorator: allows is_admin=1 OR role='procurement_specialist'.
    Anonymous → /login. Authenticated-but-wrong-role → 403."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        u = current_user()
        if not u:
            return redirect(url_for("login"))
        if u["is_admin"]:
            return f(*args, **kwargs)
        if (u["role"] or "") == "procurement_specialist":
            return f(*args, **kwargs)
        abort(403)
    return decorated


# ──────────────────────── 7B — Admin elects procurement specialists ─────


@app.route("/admin/marketplace/staff")
@admin_required
def admin_marketplace_staff():
    """Admin-only roster. Lists every user with a quick promote / demote
    toggle. Currently elected procurement specialists are listed at the
    top, then candidates ordered by created_at desc."""
    _ensure_supplier_schema()
    with get_db() as c:
        rows = c.execute(
            "SELECT id, username, email, name, company, role, is_admin, created_at "
            "FROM users ORDER BY "
            "  CASE WHEN role='procurement_specialist' THEN 0 ELSE 1 END, "
            "  created_at DESC LIMIT 500"
        ).fetchall()
    return render_template(
        "admin_marketplace_staff.html", user=current_user(), users=rows
    )


@app.route("/admin/marketplace/staff/<int:uid>/promote", methods=["POST"])
@admin_required
def admin_marketplace_promote_specialist(uid):
    csrf_protect()
    with get_db() as c:
        row = c.execute("SELECT id, username, role FROM users WHERE id=?", (uid,)).fetchone()
        if not row:
            abort(404)
        if (row["role"] or "") == "supplier_admin":
            flash("Cannot elect a supplier_admin to procurement_specialist — "
                  "demote them from supplier_admin first.", "danger")
            return redirect(url_for("admin_marketplace_staff"))
        c.execute("UPDATE users SET role='procurement_specialist' WHERE id=?", (uid,))
    _log_marketplace_action(
        "promote_specialist", "user", uid, f"{row['username']} (was role='{row['role'] or ''}')"
    )
    flash(f"Elected '{row['username']}' as procurement specialist.", "success")
    return redirect(url_for("admin_marketplace_staff"))


@app.route("/admin/marketplace/staff/<int:uid>/demote", methods=["POST"])
@admin_required
def admin_marketplace_demote_specialist(uid):
    csrf_protect()
    with get_db() as c:
        row = c.execute("SELECT id, username, role FROM users WHERE id=?", (uid,)).fetchone()
        if not row:
            abort(404)
        if (row["role"] or "") != "procurement_specialist":
            flash("User is not currently a procurement specialist.", "warning")
            return redirect(url_for("admin_marketplace_staff"))
        c.execute("UPDATE users SET role='' WHERE id=?", (uid,))
    _log_marketplace_action("demote_specialist", "user", uid, row["username"])
    flash(f"Removed procurement specialist role from '{row['username']}'.", "success")
    return redirect(url_for("admin_marketplace_staff"))


# ──────────────────────── 7C — Supplier CRUD ───────────────────────────


@app.route("/admin/marketplace/suppliers")
@procurement_role_required
def admin_marketplace_suppliers_list():
    """Single admin/specialist directory of every supplier — verified +
    unverified + suspended — with quick edit/delete links."""
    _ensure_supplier_schema()
    q = (request.args.get("q") or "").strip()
    with get_db() as c:
        if q:
            like = f"%{q.lower()}%"
            rows = c.execute(
                "SELECT s.*, u.username AS owner_username "
                "FROM suppliers s LEFT JOIN users u ON u.id=s.user_id "
                "WHERE LOWER(s.name) LIKE ? OR LOWER(s.country) LIKE ? "
                "      OR LOWER(s.email) LIKE ? "
                "ORDER BY s.created_at DESC LIMIT 200",
                (like, like, like),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT s.*, u.username AS owner_username "
                "FROM suppliers s LEFT JOIN users u ON u.id=s.user_id "
                "ORDER BY s.created_at DESC LIMIT 200"
            ).fetchall()
    return render_template(
        "admin_marketplace_suppliers.html", user=current_user(),
        suppliers=rows, q=q,
    )


@app.route("/admin/marketplace/suppliers/<int:sid>/edit", methods=["GET", "POST"])
@procurement_role_required
def admin_marketplace_supplier_edit(sid):
    with get_db() as c:
        s = c.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone()
    if not s:
        abort(404)
    if request.method == "GET":
        return render_template(
            "admin_marketplace_supplier_edit.html",
            user=current_user(), supplier=s, countries=get_countries(),
        )
    csrf_protect()
    f = request.form
    with get_db() as c:
        c.execute(
            "UPDATE suppliers SET name=?, country=?, contact_name=?, phone=?, "
            "email=?, website=?, categories=?, lead_time_days=?, "
            "payment_terms=?, rating=?, is_verified=?, is_active=? "
            "WHERE id=?",
            (
                (f.get("name") or "").strip(),
                (f.get("country") or "").strip(),
                (f.get("contact_name") or "").strip(),
                (f.get("phone") or "").strip(),
                (f.get("email") or "").strip(),
                (f.get("website") or "").strip(),
                (f.get("categories") or "").strip(),
                _safe_int(f.get("lead_time_days"), 30),
                (f.get("payment_terms") or "").strip(),
                _safe_int(f.get("rating"), 5),
                1 if f.get("is_verified") else 0,
                1 if f.get("is_active") else 0,
                sid,
            ),
        )
    _log_marketplace_action("edit_supplier", "supplier", sid, s["name"])
    flash(f"Updated supplier '{s['name']}'.", "success")
    return redirect(url_for("admin_marketplace_suppliers_list"))


@app.route("/admin/marketplace/suppliers/<int:sid>/delete", methods=["POST"])
@procurement_role_required
def admin_marketplace_supplier_delete(sid):
    csrf_protect()
    with get_db() as c:
        s = c.execute("SELECT id, name FROM suppliers WHERE id=?", (sid,)).fetchone()
        if not s:
            abort(404)
        # Soft delete — flip flags so the supplier disappears from public +
        # admin queues but the historical RFQ + product links stay intact.
        c.execute(
            "UPDATE suppliers SET is_active=0, is_verified=0 WHERE id=?", (sid,)
        )
        c.execute(
            "UPDATE equipment_catalog SET is_public_visible=0 WHERE supplier_id=?",
            (sid,),
        )
    _log_marketplace_action("delete_supplier", "supplier", sid, s["name"])
    flash(f"Soft-deleted supplier '{s['name']}'.", "warning")
    return redirect(url_for("admin_marketplace_suppliers_list"))


# ──────────────────────── 7C — Product CRUD ────────────────────────────


@app.route("/admin/marketplace/products")
@procurement_role_required
def admin_marketplace_products_list():
    _ensure_marketplace_tables()
    q = (request.args.get("q") or "").strip()
    cat_id = _safe_int(request.args.get("cat"), 0)
    with get_db() as c:
        sql = (
            "SELECT ec.*, s.name AS supplier_name, pc.name AS category_name "
            "FROM equipment_catalog ec "
            "LEFT JOIN suppliers s ON s.id=ec.supplier_id "
            "LEFT JOIN product_categories pc ON pc.id=ec.category_id "
            "WHERE 1=1 "
        )
        args = []
        if cat_id:
            sql += "AND ec.category_id=? "
            args.append(cat_id)
        if q:
            like = f"%{q.lower()}%"
            sql += ("AND (LOWER(ec.name) LIKE ? OR LOWER(ec.brand) LIKE ? "
                    "     OR LOWER(ec.model) LIKE ?) ")
            args.extend([like, like, like])
        sql += "ORDER BY ec.created_at DESC LIMIT 200"
        rows = c.execute(sql, args).fetchall()
        categories = c.execute(
            "SELECT id, name FROM product_categories "
            "WHERE is_active=1 ORDER BY display_order"
        ).fetchall()
    return render_template(
        "admin_marketplace_products.html", user=current_user(),
        products=rows, categories=categories, selected_cat=cat_id, q=q,
    )


@app.route("/admin/marketplace/products/<int:pid>/edit", methods=["GET", "POST"])
@procurement_role_required
def admin_marketplace_product_edit(pid):
    _ensure_marketplace_tables()
    with get_db() as c:
        p = c.execute(
            "SELECT * FROM equipment_catalog WHERE id=?", (pid,)
        ).fetchone()
        if not p:
            abort(404)
        categories = c.execute(
            "SELECT id, name FROM product_categories "
            "WHERE is_active=1 ORDER BY display_order"
        ).fetchall()
        suppliers = c.execute(
            "SELECT id, name FROM suppliers WHERE is_active=1 ORDER BY name"
        ).fetchall()
    if request.method == "GET":
        return render_template(
            "admin_marketplace_product_edit.html",
            user=current_user(), product=p, categories=categories, suppliers=suppliers,
        )
    csrf_protect()
    f = request.form
    cat_id = _safe_int(f.get("category_id"), 0)
    with get_db() as c:
        cat_label = ""
        if cat_id:
            row = c.execute(
                "SELECT name FROM product_categories WHERE id=?", (cat_id,)
            ).fetchone()
            if row:
                cat_label = row["name"]
        try:
            price = float(f.get("price_usd") or 0)
        except ValueError:
            price = 0
        c.execute(
            "UPDATE equipment_catalog SET name=?, brand=?, model=?, spec=?, "
            "unit=?, price_usd=?, supplier_id=?, lead_time_days=?, "
            "category_id=?, category=?, subcategory=?, "
            "is_verified=?, is_public_visible=?, is_active=? "
            "WHERE id=?",
            (
                (f.get("name") or "").strip(),
                (f.get("brand") or "").strip(),
                (f.get("model") or "").strip(),
                (f.get("spec") or "").strip(),
                (f.get("unit") or "No.").strip(),
                price,
                _safe_int(f.get("supplier_id"), 0),
                _safe_int(f.get("lead_time_days"), 30),
                cat_id, cat_label,
                (f.get("subcategory") or "").strip(),
                1 if f.get("is_verified") else 0,
                1 if f.get("is_public_visible") else 0,
                1 if f.get("is_active") else 0,
                pid,
            ),
        )
    _log_marketplace_action("edit_product", "product", pid, p["name"])
    flash(f"Updated product '{p['name']}'.", "success")
    return redirect(url_for("admin_marketplace_products_list"))


@app.route("/admin/marketplace/products/<int:pid>/delete", methods=["POST"])
@procurement_role_required
def admin_marketplace_product_delete(pid):
    csrf_protect()
    with get_db() as c:
        p = c.execute(
            "SELECT id, name FROM equipment_catalog WHERE id=?", (pid,)
        ).fetchone()
        if not p:
            abort(404)
        c.execute(
            "UPDATE equipment_catalog SET is_active=0, is_public_visible=0 WHERE id=?",
            (pid,),
        )
    _log_marketplace_action("delete_product", "product", pid, p["name"])
    flash(f"Soft-deleted product '{p['name']}'.", "warning")
    return redirect(url_for("admin_marketplace_products_list"))


# ──────────────────────── 7D — User dashboard at /me ───────────────────


@app.route("/me")
@login_required
def me_dashboard():
    _ensure_rfq_tables()
    _ensure_bom_tables()
    uid = session["user_id"]
    u = current_user()
    with get_db() as c:
        # Buyer-side counts
        my_rfqs_draft = c.execute(
            "SELECT COUNT(*) FROM rfqs WHERE user_id=? AND status='draft'", (uid,)
        ).fetchone()[0]
        my_rfqs_sent = c.execute(
            "SELECT COUNT(*) FROM rfqs WHERE user_id=? AND status='sent'", (uid,)
        ).fetchone()[0]
        my_rfqs_awarded = c.execute(
            "SELECT COUNT(*) FROM rfqs WHERE user_id=? AND status='awarded'", (uid,)
        ).fetchone()[0]
        my_boms = c.execute(
            "SELECT COUNT(*) FROM marketplace_boms WHERE user_id=?", (uid,)
        ).fetchone()[0]
        recent_rfqs = c.execute(
            "SELECT r.id, r.title, r.status, r.updated_at, "
            "  (SELECT COUNT(*) FROM rfq_responses WHERE rfq_id=r.id) AS responses "
            "FROM rfqs r WHERE r.user_id=? ORDER BY r.updated_at DESC LIMIT 5",
            (uid,),
        ).fetchall()
        recent_boms = c.execute(
            "SELECT b.id, b.title, b.updated_at, "
            "  (SELECT COUNT(*) FROM marketplace_bom_items WHERE bom_id=b.id) AS items "
            "FROM marketplace_boms b WHERE b.user_id=? "
            "ORDER BY b.updated_at DESC LIMIT 5",
            (uid,),
        ).fetchall()
        # Supplier-side counts (only if user is a supplier_admin)
        supplier_row = None
        inbox_open = 0
        my_products = 0
        if (u["role"] or "") == "supplier_admin":
            supplier_row = c.execute(
                "SELECT id, name, is_verified FROM suppliers WHERE user_id=? LIMIT 1",
                (uid,),
            ).fetchone()
            if supplier_row:
                inbox_open = c.execute(
                    "SELECT COUNT(*) FROM rfq_supplier_targets rst "
                    "JOIN rfqs r ON r.id=rst.rfq_id "
                    "WHERE rst.supplier_id=? AND r.status='sent' "
                    "AND NOT EXISTS (SELECT 1 FROM rfq_responses rr "
                    "                WHERE rr.rfq_id=rst.rfq_id "
                    "                AND rr.supplier_id=?)",
                    (supplier_row["id"], supplier_row["id"]),
                ).fetchone()[0]
                my_products = c.execute(
                    "SELECT COUNT(*) FROM equipment_catalog "
                    "WHERE supplier_id=? AND is_active=1",
                    (supplier_row["id"],),
                ).fetchone()[0]
    return render_template(
        "me_dashboard.html",
        user=u,
        my_rfqs_draft=my_rfqs_draft, my_rfqs_sent=my_rfqs_sent,
        my_rfqs_awarded=my_rfqs_awarded, my_boms=my_boms,
        recent_rfqs=recent_rfqs, recent_boms=recent_boms,
        supplier=supplier_row, inbox_open=inbox_open, my_products=my_products,
    )
