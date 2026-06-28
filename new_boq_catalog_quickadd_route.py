# new_boq_catalog_quickadd_route.py
# 2026-06-28: when a BOQ row's description has no catalogue match (or the
# owner just wants to spin up a new item on the fly), this lightweight
# endpoint INSERTs into equipment_catalog and returns the new id + basic
# price as JSON so the calling form can pop it back into the BOQ row.


@app.route("/equipment-catalog/quick-add", methods=["POST"])
@login_required
def boq_catalog_quick_add():
    uid = session["user_id"]
    csrf_protect()
    f = request.form
    name  = (f.get("name") or "").strip()[:300]
    brand = (f.get("brand") or "").strip()[:120]
    cat   = (f.get("category") or "").strip().lower()[:80]
    new_cat = (f.get("new_category") or "").strip().lower()[:80]
    if new_cat:
        cat = new_cat
    unit  = (f.get("unit") or "No.").strip()[:20]
    spec  = (f.get("spec") or "").strip()
    try:
        basic = max(0.0, float(f.get("basic_price") or 0))
    except (TypeError, ValueError):
        basic = 0.0
    if not name:
        return jsonify({"ok": False, "error": "Name is required."}), 400
    if not cat:
        return jsonify({"ok": False, "error": "Pick or type a category."}), 400
    if basic <= 0:
        return jsonify({"ok": False, "error": "Basic price must be > 0."}), 400

    with get_db() as c:
        cur = c.execute(
            "INSERT INTO equipment_catalog "
            "(category, name, brand, model, spec, unit, price_usd, "
            " is_active, is_verified, is_public_visible, "
            " source_type, approval_status, submitted_by_user_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cat, name, brand, "", spec, unit, basic,
             1, 0, 0, "project_library", "project_only", uid),
        )
        new_id = int(cur.lastrowid or 0)

    try:
        from new_boq_hierarchy_schema import boq_audit
        boq_audit(get_db, uid, "catalogue_quick_add", "equipment_catalog", new_id,
                  f"cat={cat} brand={brand} basic={basic:.2f}")
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "id": new_id,
        "name": name,
        "brand": brand,
        "category": cat,
        "unit": unit,
        "basic_price": basic,
    })


@app.route("/equipment-catalog/categories", methods=["GET"])
@login_required
def boq_catalog_categories():
    """Distinct category list for the quick-add dropdown."""
    with get_db() as c:
        rows = c.execute(
            "SELECT DISTINCT category FROM equipment_catalog "
            "WHERE COALESCE(category,'') <> '' AND COALESCE(is_active,1)=1 "
            "ORDER BY category"
        ).fetchall()
    return jsonify({"categories": [r["category"] for r in rows]})
