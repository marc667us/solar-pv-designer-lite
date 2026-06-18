# ─── Routes — Marketplace Admin Verification ──────────────────────────────────
# Slice 3: solar admin reviews supplier-uploaded products + new supplier
# registrations, approves or rejects them. Approved items appear on the
# public /marketplace and on the supplier's own dashboard as "Live".

_MARKETPLACE_AUDIT_ACTIONS = {
    "approve_product", "reject_product", "hide_product",
    "approve_supplier", "reject_supplier",
}


def _log_marketplace_action(action: str, target_kind: str, target_id: int, notes: str = ""):
    """Lightweight audit logger — writes one row to marketplace_audit_log.

    Idempotent table creation so this works even on the very first action."""
    with get_db() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS marketplace_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_kind TEXT NOT NULL,
                target_id INTEGER NOT NULL,
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        c.execute(
            "INSERT INTO marketplace_audit_log "
            "(user_id, action, target_kind, target_id, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (session.get("user_id", 0), action, target_kind, target_id, notes),
        )


@app.route("/admin/marketplace")
@admin_required
def admin_marketplace_dashboard():
    """Admin landing for the marketplace verification queue."""
    _ensure_marketplace_tables()
    _ensure_supplier_schema()
    with get_db() as c:
        pending_suppliers = c.execute(
            "SELECT COUNT(*) FROM suppliers WHERE is_verified=0 AND is_active=1"
        ).fetchone()[0]
        verified_suppliers = c.execute(
            "SELECT COUNT(*) FROM suppliers WHERE is_verified=1 AND is_active=1"
        ).fetchone()[0]
        pending_products = c.execute(
            "SELECT COUNT(*) FROM equipment_catalog WHERE is_verified=0 AND is_active=1"
        ).fetchone()[0]
        verified_products = c.execute(
            "SELECT COUNT(*) FROM equipment_catalog WHERE is_verified=1 AND is_active=1"
        ).fetchone()[0]
        recent_actions = c.execute(
            "SELECT mal.*, u.username AS actor "
            "FROM marketplace_audit_log mal "
            "LEFT JOIN users u ON u.id=mal.user_id "
            "ORDER BY mal.created_at DESC LIMIT 20"
        ).fetchall() if c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='marketplace_audit_log'"
        ).fetchone() else []
    return render_template(
        "admin_marketplace.html",
        user=current_user(),
        pending_suppliers=pending_suppliers,
        verified_suppliers=verified_suppliers,
        pending_products=pending_products,
        verified_products=verified_products,
        recent_actions=recent_actions,
    )


@app.route("/admin/marketplace/pending")
@admin_required
def admin_marketplace_pending():
    """Review queue: pending suppliers + pending products in one screen."""
    _ensure_marketplace_tables()
    _ensure_supplier_schema()
    cat_id = _safe_int(request.args.get("cat"), 0)
    q = (request.args.get("q") or "").strip()
    with get_db() as c:
        suppliers = c.execute(
            "SELECT s.*, u.username AS owner_username, u.email AS owner_email "
            "FROM suppliers s "
            "LEFT JOIN users u ON u.id=s.user_id "
            "WHERE s.is_verified=0 AND s.is_active=1 "
            "ORDER BY s.created_at DESC LIMIT 100"
        ).fetchall()
        sql = (
            "SELECT ec.*, s.name AS supplier_name, pc.name AS category_name "
            "FROM equipment_catalog ec "
            "LEFT JOIN suppliers s ON s.id=ec.supplier_id "
            "LEFT JOIN product_categories pc ON pc.id=ec.category_id "
            "WHERE ec.is_verified=0 AND ec.is_active=1 "
        )
        args = []
        if cat_id:
            sql += "AND ec.category_id=? "
            args.append(cat_id)
        if q:
            sql += ("AND (ec.name LIKE ? OR ec.brand LIKE ? OR ec.model LIKE ? "
                    "     OR s.name LIKE ?) ")
            like = f"%{q}%"
            args.extend([like, like, like, like])
        sql += "ORDER BY ec.created_at DESC LIMIT 200"
        products = c.execute(sql, args).fetchall()
        categories = c.execute(
            "SELECT id, name FROM product_categories WHERE is_active=1 "
            "ORDER BY display_order"
        ).fetchall()
    return render_template(
        "admin_marketplace_pending.html",
        user=current_user(),
        suppliers=suppliers,
        products=products,
        categories=categories,
        selected_cat=cat_id,
        q=q,
    )


@app.route("/admin/marketplace/supplier/<int:sid>/approve", methods=["POST"])
@admin_required
def admin_marketplace_approve_supplier(sid):
    csrf_protect()
    with get_db() as c:
        row = c.execute(
            "SELECT id, name FROM suppliers WHERE id=?", (sid,)
        ).fetchone()
        if not row:
            abort(404)
        c.execute("UPDATE suppliers SET is_verified=1 WHERE id=?", (sid,))
        # Surface ONLY the supplier's already-verified products. Unverified
        # products must continue to wait for product-level approval to avoid
        # leaking unreviewed listings on supplier approval (Codex finding).
        c.execute(
            "UPDATE equipment_catalog SET is_public_visible=1 "
            "WHERE supplier_id=? AND is_active=1 AND is_verified=1", (sid,),
        )
    _log_marketplace_action("approve_supplier", "supplier", sid, row["name"])
    flash(f"Approved supplier '{row['name']}'.", "success")
    return redirect(url_for("admin_marketplace_pending"))


@app.route("/admin/marketplace/supplier/<int:sid>/reject", methods=["POST"])
@admin_required
def admin_marketplace_reject_supplier(sid):
    csrf_protect()
    with get_db() as c:
        row = c.execute("SELECT id, name FROM suppliers WHERE id=?", (sid,)).fetchone()
        if not row:
            abort(404)
        c.execute("UPDATE suppliers SET is_active=0 WHERE id=?", (sid,))
        # Also hide their products from public.
        c.execute(
            "UPDATE equipment_catalog SET is_public_visible=0 WHERE supplier_id=?",
            (sid,),
        )
    _log_marketplace_action("reject_supplier", "supplier", sid, row["name"])
    flash(f"Rejected supplier '{row['name']}'.", "warning")
    return redirect(url_for("admin_marketplace_pending"))


@app.route("/admin/marketplace/product/<int:pid>/approve", methods=["POST"])
@admin_required
def admin_marketplace_approve_product(pid):
    csrf_protect()
    with get_db() as c:
        row = c.execute(
            "SELECT ec.id, ec.name, s.is_verified AS supplier_verified "
            "FROM equipment_catalog ec "
            "LEFT JOIN suppliers s ON s.id=ec.supplier_id "
            "WHERE ec.id=?", (pid,),
        ).fetchone()
        if not row:
            abort(404)
        # Mark verified + visible only if owning supplier is also verified.
        if row["supplier_verified"]:
            c.execute(
                "UPDATE equipment_catalog SET is_verified=1, is_public_visible=1 "
                "WHERE id=?", (pid,),
            )
        else:
            c.execute(
                "UPDATE equipment_catalog SET is_verified=1 WHERE id=?", (pid,),
            )
    _log_marketplace_action("approve_product", "product", pid, row["name"])
    flash(
        f"Approved '{row['name']}'." if row["supplier_verified"]
        else f"Approved '{row['name']}' (will go live once supplier is verified).",
        "success",
    )
    return redirect(url_for("admin_marketplace_pending"))


@app.route("/admin/marketplace/product/<int:pid>/reject", methods=["POST"])
@admin_required
def admin_marketplace_reject_product(pid):
    csrf_protect()
    with get_db() as c:
        row = c.execute("SELECT id, name FROM equipment_catalog WHERE id=?", (pid,)).fetchone()
        if not row:
            abort(404)
        c.execute(
            "UPDATE equipment_catalog SET is_active=0, is_public_visible=0 WHERE id=?",
            (pid,),
        )
    _log_marketplace_action("reject_product", "product", pid, row["name"])
    flash(f"Rejected '{row['name']}'.", "warning")
    return redirect(url_for("admin_marketplace_pending"))


@app.route("/admin/marketplace/bulk", methods=["POST"])
@admin_required
def admin_marketplace_bulk():
    """Batch action over a selection of products and/or suppliers.

    Form fields:
      - action: one of approve_product, reject_product, approve_supplier, reject_supplier
      - product_ids[]: list of pids (string)
      - supplier_ids[]: list of sids (string)
    """
    csrf_protect()
    action = (request.form.get("action") or "").strip()
    if action not in _MARKETPLACE_AUDIT_ACTIONS:
        flash(f"Unknown action: {action}", "danger")
        return redirect(url_for("admin_marketplace_pending"))

    raw_pids = request.form.getlist("product_ids")
    raw_sids = request.form.getlist("supplier_ids")
    pids = [int(x) for x in raw_pids if x.isdigit()]
    sids = [int(x) for x in raw_sids if x.isdigit()]
    n = 0
    with get_db() as c:
        if action == "approve_product" and pids:
            placeholders = ",".join(["?"] * len(pids))
            cur = c.execute(
                f"UPDATE equipment_catalog SET is_verified=1, is_public_visible=1 "
                f"WHERE id IN ({placeholders}) "
                f"  AND supplier_id IN (SELECT id FROM suppliers WHERE is_verified=1)",
                pids,
            )
            n = cur.rowcount or 0
            # Also flip the unverified-supplier rows so the verification flag is
            # set even if visibility is gated on supplier review.
            c.execute(
                f"UPDATE equipment_catalog SET is_verified=1 "
                f"WHERE id IN ({placeholders}) AND is_verified=0",
                pids,
            )
        elif action == "reject_product" and pids:
            placeholders = ",".join(["?"] * len(pids))
            cur = c.execute(
                f"UPDATE equipment_catalog SET is_active=0, is_public_visible=0 "
                f"WHERE id IN ({placeholders})",
                pids,
            )
            n = cur.rowcount or 0
        elif action == "approve_supplier" and sids:
            placeholders = ",".join(["?"] * len(sids))
            cur = c.execute(
                f"UPDATE suppliers SET is_verified=1 WHERE id IN ({placeholders})",
                sids,
            )
            n = cur.rowcount or 0
            # Only flip visibility for already-verified products of these
            # suppliers — unverified products must continue to wait for their
            # own approval (Codex finding).
            c.execute(
                f"UPDATE equipment_catalog SET is_public_visible=1 "
                f"WHERE supplier_id IN ({placeholders}) AND is_active=1 AND is_verified=1",
                sids,
            )
        elif action == "reject_supplier" and sids:
            placeholders = ",".join(["?"] * len(sids))
            cur = c.execute(
                f"UPDATE suppliers SET is_active=0 WHERE id IN ({placeholders})",
                sids,
            )
            n = cur.rowcount or 0
            c.execute(
                f"UPDATE equipment_catalog SET is_public_visible=0 "
                f"WHERE supplier_id IN ({placeholders})",
                sids,
            )
    # Log the batch as a single audit row with the count in notes.
    if pids or sids:
        kind = "product" if "product" in action else "supplier"
        ids_csv = ",".join(str(x) for x in (pids if kind == "product" else sids))
        _log_marketplace_action(action, kind, 0, f"bulk n={n}; ids={ids_csv}")
    flash(f"{action.replace('_', ' ').title()}: applied to {n} row{'s' if n != 1 else ''}.",
          "success" if n else "warning")
    return redirect(url_for("admin_marketplace_pending"))
