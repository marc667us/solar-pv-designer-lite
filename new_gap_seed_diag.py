# new_gap_seed_diag.py  (TEMPORARY diagnostic -- remove after slice-1 verified)
# Admin-only endpoint that reports the live state of the solar-farm gap seed and
# runs it once with full exception capture, so we can diagnose why products did
# not seed on live Postgres (free tier hides runtime logs).

@app.route("/api/debug/gap-seed-diag")
def _gap_seed_diag():
    import traceback, json as _json
    u = current_user() if 'current_user' in globals() else None
    if not (u and u.get("is_admin")):
        from flask import abort as _abort
        return _abort(403)
    out = {}
    try:
        out["append_live"] = any(r[0] == "circuit_breakers" for r in _MARKETPLACE_CATEGORIES)
        out["subcat_live"] = "circuit_breakers" in _MARKETPLACE_SUBCATEGORIES
        out["gap_product_count_defined"] = len(_SOLAR_FARM_GAP_PRODUCTS)
    except Exception as e:
        out["registry_error"] = repr(e)
    # DB state before
    try:
        with get_db() as c:
            out["backend"] = "postgres" if os.environ.get("DATABASE_URL") else "sqlite"
            row = c.execute("SELECT id, code FROM product_categories WHERE code IN ('circuit_breakers','plant_control')").fetchall()
            out["new_categories_in_db"] = [dict(r) if hasattr(r, 'keys') else list(r) for r in row]
            out["supplier_count"] = c.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0]
            cnt = c.execute("SELECT COUNT(*) FROM equipment_catalog WHERE brand=? AND model=?", ("Schneider","A9F74116")).fetchone()[0]
            out["mcb_A9F74116_present_before"] = cnt
    except Exception as e:
        out["db_state_error"] = repr(e)
    # Run the seed steps INLINE (bypassing the seed's own try/except that
    # swallows + rolls back) so the real failing statement surfaces.
    out["steps"] = []
    try:
        with get_db() as c:
            try:
                c.execute("SELECT set_config('app.current_role', 'admin', true)")
                out["steps"].append("role_elevated")
            except Exception as _e:
                out["steps"].append("role_set_failed:%r" % _e)
            for _code, _name, _icon, _order in _SF_NEW_CATEGORIES:
                c.execute(
                    "INSERT INTO product_categories (code, name, icon, display_order) "
                    "VALUES (?,?,?,?) ON CONFLICT (code) DO NOTHING",
                    (_code, _name, _icon, _order))
            out["steps"].append("category_insert_ok")
            cats = {r["code"]: r["id"] for r in c.execute(
                "SELECT id, code FROM product_categories").fetchall()}
            out["steps"].append("cats_has_cb=%s" % ("circuit_breakers" in cats))
            code, sub, name, brand, model, spec, unit, price_usd, lt = _SOLAR_FARM_GAP_PRODUCTS[0]
            cat_id = cats.get(code, 0)
            c.execute(
                "INSERT INTO equipment_catalog (category, name, brand, model, spec, "
                "unit, price_usd, supplier_id, lead_time_days, category_id, "
                "subcategory, is_public_visible, is_verified) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,1,1)",
                ("Circuit Breakers", name, brand, model, spec, unit,
                 price_usd, 0, lt, cat_id, sub))
            out["steps"].append("product_insert_ok")
        out["inline_committed"] = True
    except Exception:
        out["inline_exception"] = traceback.format_exc()
    # DB state after
    try:
        with get_db() as c:
            out["mcb_A9F74116_present_after"] = c.execute("SELECT COUNT(*) FROM equipment_catalog WHERE brand=? AND model=?", ("Schneider","A9F74116")).fetchone()[0]
            out["circuit_breaker_products"] = c.execute(
                "SELECT COUNT(*) FROM equipment_catalog WHERE category_id=(SELECT id FROM product_categories WHERE code='circuit_breakers')").fetchone()[0]
            out["plant_control_products"] = c.execute(
                "SELECT COUNT(*) FROM equipment_catalog WHERE category_id=(SELECT id FROM product_categories WHERE code='plant_control')").fetchone()[0]
    except Exception as e:
        out["db_after_error"] = repr(e)
    from flask import Response
    return Response(_json.dumps(out, indent=2, default=str), mimetype="application/json")
