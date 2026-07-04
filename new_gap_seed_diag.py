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
    # Run the seed with full traceback capture
    try:
        _seed_solar_farm_gap_products()
        out["seed_ran"] = True
    except Exception:
        out["seed_exception"] = traceback.format_exc()
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
