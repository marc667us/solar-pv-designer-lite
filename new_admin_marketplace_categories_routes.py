# === BEGIN: admin_marketplace_categories splice ===
# 2026-06-22 (session A): admin can add new product categories from the UI.
# Hardcoded _MARKETPLACE_CATEGORIES (21 seeds) stays as fallback seed; the DB
# is the source of truth at query time.  New rows added here pick up the
# extra columns spliced into product_categories by patch_bom_supplier_categories.py:
#   default_unit       TEXT
#   subcategories_csv  TEXT  (comma-separated)
#   spec_fields_csv    TEXT  (comma-separated)
#
# Routes:
#   GET  /admin/marketplace/categories                  list + add form
#   POST /admin/marketplace/categories/add              create
#   POST /admin/marketplace/categories/<cid>/edit       update
#   POST /admin/marketplace/categories/<cid>/toggle     activate / deactivate
#
# Helper:
#   _merged_marketplace_taxonomy()  ->  returns {subcategories, default_unit,
#   spec_fields} dicts that combine the hardcoded registries with whatever the
#   admin has saved in product_categories. Used by the supplier product add
#   form, the admin product edit form, and the BOM library modal so any new
#   category shows up everywhere automatically.

def _merged_marketplace_taxonomy():
    """Return three dicts keyed by category code, merging the hardcoded
    registries (_MARKETPLACE_SUBCATEGORIES / _MARKETPLACE_DEFAULT_UNIT /
    _MARKETPLACE_SPEC_FIELDS) with the per-row overrides admins typed into
    product_categories.subcategories_csv / default_unit / spec_fields_csv.
    DB values WIN when present so admins can extend hardcoded categories too.
    """
    subs = {k: list(v) for k, v in _MARKETPLACE_SUBCATEGORIES.items()}
    units = dict(_MARKETPLACE_DEFAULT_UNIT)
    specs = {k: list(v) for k, v in _MARKETPLACE_SPEC_FIELDS.items()}
    try:
        with get_db() as c:
            rows = c.execute(
                "SELECT code, default_unit, subcategories_csv, spec_fields_csv "
                "FROM product_categories WHERE is_active=1"
            ).fetchall()
        for r in rows:
            code = (r["code"] or "").strip()
            if not code:
                continue
            du = (r["default_unit"] if "default_unit" in r.keys() else "") or ""
            sc = (r["subcategories_csv"] if "subcategories_csv" in r.keys() else "") or ""
            sf = (r["spec_fields_csv"] if "spec_fields_csv" in r.keys() else "") or ""
            if du.strip():
                units[code] = du.strip()
            if sc.strip():
                subs[code] = [s.strip() for s in sc.split(",") if s.strip()]
            if sf.strip():
                specs[code] = [s.strip() for s in sf.split(",") if s.strip()]
    except Exception:
        pass
    return subs, units, specs


def _slugify_category_code(name: str) -> str:
    """Turn 'Switchgear & Protection' -> 'switchgear_protection'. Used when
    admin doesn't supply an explicit code."""
    import re as _re
    s = (name or "").lower().strip()
    s = _re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s[:40] or "category"


@app.route("/admin/marketplace/categories")
@admin_required
def admin_marketplace_categories():
    """List every product category. Admins can add new ones from this page."""
    _ensure_marketplace_tables()
    _ensure_bom_tables()  # also runs the product_categories ALTERs
    with get_db() as c:
        rows = c.execute(
            "SELECT id, code, name, icon, display_order, is_active, "
            "       default_unit, subcategories_csv, spec_fields_csv "
            "FROM product_categories ORDER BY display_order, name"
        ).fetchall()
        # Per-category product counts so admins can see usage at a glance.
        counts = {}
        try:
            cnt_rows = c.execute(
                "SELECT category_id, COUNT(*) AS n FROM equipment_catalog "
                "WHERE is_active=1 GROUP BY category_id"
            ).fetchall()
            for r in cnt_rows:
                counts[int(r["category_id"] or 0)] = int(r["n"] or 0)
        except Exception:
            pass
    return render_template(
        "admin_marketplace_categories.html",
        user=current_user(),
        categories=rows,
        product_counts=counts,
    )


@app.route("/admin/marketplace/categories/add", methods=["POST"])
@admin_required
def admin_marketplace_categories_add():
    _ensure_marketplace_tables()
    _ensure_bom_tables()
    csrf_protect()
    f = request.form
    name = (f.get("name") or "").strip()
    if not name:
        flash("Category name is required.", "danger")
        return redirect(url_for("admin_marketplace_categories"))
    code = (f.get("code") or "").strip().lower() or _slugify_category_code(name)
    icon = (f.get("icon") or "bi-box").strip()
    try:
        order = int(f.get("display_order") or 220)
    except (TypeError, ValueError):
        order = 220
    default_unit = (f.get("default_unit") or "No.").strip()[:20]
    subcats = (f.get("subcategories_csv") or "").strip()
    specs = (f.get("spec_fields_csv") or "").strip()
    try:
        with get_db() as c:
            c.execute(
                "INSERT INTO product_categories "
                "(code, name, icon, display_order, is_active, "
                " default_unit, subcategories_csv, spec_fields_csv) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (code, name, icon, order, 1, default_unit, subcats, specs),
            )
        _log_marketplace_action("add_category", "product_category", 0, f"{code}: {name}")
        flash(f"Added category '{name}' ({code}).", "success")
    except Exception as e:
        _msg = str(e).lower()
        if "unique" in _msg or "duplicate" in _msg:
            flash(f"A category with code '{code}' already exists.", "warning")
        else:
            try:
                app.logger.exception("admin_marketplace_categories_add failed: %s", e)
            except Exception:
                pass
            flash(f"Could not add category: {e!s}", "danger")
    return redirect(url_for("admin_marketplace_categories"))


@app.route("/admin/marketplace/categories/<int:cid>/edit", methods=["POST"])
@admin_required
def admin_marketplace_categories_edit(cid):
    _ensure_marketplace_tables()
    _ensure_bom_tables()
    csrf_protect()
    f = request.form
    name = (f.get("name") or "").strip()
    if not name:
        flash("Category name is required.", "danger")
        return redirect(url_for("admin_marketplace_categories"))
    icon = (f.get("icon") or "bi-box").strip()
    try:
        order = int(f.get("display_order") or 220)
    except (TypeError, ValueError):
        order = 220
    default_unit = (f.get("default_unit") or "No.").strip()[:20]
    subcats = (f.get("subcategories_csv") or "").strip()
    specs = (f.get("spec_fields_csv") or "").strip()
    try:
        with get_db() as c:
            row = c.execute(
                "SELECT id, code, name FROM product_categories WHERE id=?", (cid,)
            ).fetchone()
            if not row:
                abort(404)
            c.execute(
                "UPDATE product_categories SET name=?, icon=?, display_order=?, "
                "default_unit=?, subcategories_csv=?, spec_fields_csv=? WHERE id=?",
                (name, icon, order, default_unit, subcats, specs, cid),
            )
        _log_marketplace_action("edit_category", "product_category", cid, f"{row['code']}: {name}")
        flash(f"Updated category '{name}'.", "success")
    except Exception as e:
        try:
            app.logger.exception("admin_marketplace_categories_edit failed: %s", e)
        except Exception:
            pass
        flash(f"Could not update category: {e!s}", "danger")
    return redirect(url_for("admin_marketplace_categories"))


@app.route("/admin/marketplace/categories/<int:cid>/toggle", methods=["POST"])
@admin_required
def admin_marketplace_categories_toggle(cid):
    _ensure_marketplace_tables()
    csrf_protect()
    with get_db() as c:
        row = c.execute(
            "SELECT id, code, name, is_active FROM product_categories WHERE id=?",
            (cid,),
        ).fetchone()
        if not row:
            abort(404)
        new_state = 0 if (row["is_active"] or 0) else 1
        c.execute(
            "UPDATE product_categories SET is_active=? WHERE id=?",
            (new_state, cid),
        )
    _log_marketplace_action(
        "toggle_category", "product_category", cid,
        f"{row['code']}: {'activated' if new_state else 'deactivated'}",
    )
    flash(
        f"Category '{row['name']}' {'activated' if new_state else 'deactivated'}.",
        "success" if new_state else "warning",
    )
    return redirect(url_for("admin_marketplace_categories"))


# === END: admin_marketplace_categories splice ===
