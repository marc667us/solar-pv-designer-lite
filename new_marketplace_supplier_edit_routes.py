# ─── Routes — Supplier product Edit + Delete (scope tightening) ──────────────
# User-confirmed scope 2026-06-18: "supplier add and edit their products only
# and respond to rfq". Slice 2 already shipped ADD via /supplier/products/add
# and the RFQ response surface is at /supplier/rfqs/<id>. This module adds the
# missing EDIT + DELETE actions for products the supplier already owns.
#
# Authorisation: every action checks (supplier_id == _current_supplier().id).
# Suppliers can NEVER touch a product owned by another supplier.
# Delete is SOFT (is_active=0) so the product disappears from the marketplace
# but historical BOM/BOQ references survive.


def _supplier_product_owned_or_404(pid: int):
    """Return the equipment_catalog row IFF it belongs to the current supplier
    (the logged-in supplier_admin user's own supplier). 404 otherwise."""
    s = _current_supplier()
    if not s:
        abort(404)
    with get_db() as c:
        row = c.execute(
            "SELECT * FROM equipment_catalog WHERE id=? AND supplier_id=?",
            (pid, s["id"]),
        ).fetchone()
    if not row:
        abort(404)
    return row, s


@app.route("/supplier/products/<int:pid>/edit", methods=["GET", "POST"])
@supplier_required
def supplier_product_edit(pid):
    """Supplier edits one of their own products. Name, brand, model, spec,
    unit, price, lead time, category, subcategory are mutable. Edits drop the
    is_verified flag back to 0 so the admin must re-approve material changes
    before the new values are published on the public marketplace."""
    row, s = _supplier_product_owned_or_404(pid)
    with get_db() as c:
        categories = c.execute(
            "SELECT id, name FROM product_categories "
            "WHERE is_active=1 ORDER BY display_order"
        ).fetchall()
    if request.method == "GET":
        return render_template(
            "supplier_product_edit.html",
            user=current_user(),
            supplier=s,
            product=row,
            categories=categories,
        )
    csrf_protect()
    f = request.form
    name = (f.get("name") or "").strip()
    if not name:
        flash("Product name is required.", "danger")
        return redirect(url_for("supplier_product_edit", pid=pid))
    cat_id = _safe_int(f.get("category_id"), 0)
    with get_db() as c:
        cat_row = c.execute(
            "SELECT name FROM product_categories WHERE id=?", (cat_id,)
        ).fetchone()
        cat_label = cat_row["name"] if cat_row else (row["category"] or "")
        c.execute(
            "UPDATE equipment_catalog SET "
            "  name=?, brand=?, model=?, spec=?, unit=?, "
            "  price_usd=?, lead_time_days=?, "
            "  category_id=?, category=?, subcategory=?, "
            "  is_verified=0 "
            "WHERE id=? AND supplier_id=?",
            (
                name,
                (f.get("brand") or "").strip(),
                (f.get("model") or "").strip(),
                (f.get("spec") or "").strip(),
                (f.get("unit") or "No.").strip(),
                _safe_int(f.get("price_usd"), 0),
                _safe_int(f.get("lead_time_days"), 30),
                cat_id,
                cat_label,
                (f.get("subcategory") or "").strip(),
                pid,
                s["id"],
            ),
        )
    flash(
        f"Saved changes to '{name}'. Your edits will appear on the public "
        f"marketplace after admin re-verification.",
        "success",
    )
    return redirect(url_for("supplier_products"))


@app.route("/supplier/products/<int:pid>/delete", methods=["POST"])
@supplier_required
def supplier_product_delete(pid):
    """Soft-delete (is_active=0) so the product drops out of the marketplace
    immediately but historical BOM/BOQ references stay intact."""
    csrf_protect()
    row, s = _supplier_product_owned_or_404(pid)
    with get_db() as c:
        c.execute(
            "UPDATE equipment_catalog SET is_active=0 "
            "WHERE id=? AND supplier_id=?",
            (pid, s["id"]),
        )
    flash(f"Removed '{row['name']}' from your catalog.", "success")
    return redirect(url_for("supplier_products"))
