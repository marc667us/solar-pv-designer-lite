# Byte-level, CRLF-aware patch: isolate Generation-Station capital BOQs from the
# marketplace BOQ workspace list (/boq-projects). web_app.py must never be
# text-edited (mojibake); this replaces one pure-ASCII region only. Idempotent.
# Owner directive 2026-07-03 issue #7 ("new project BOQ mixed with generation
# station BOQ"). Default list hides capital_* project types; ?scope=capital shows
# only them.
data = open("web_app.py", "rb").read()

OLD = (
    b'    uid = session["user_id"]\r\n'
    b'    _boq_ensure_schema()\r\n'
    b'    with get_db() as c:\r\n'
    b'        projects = c.execute(\r\n'
    b'            "SELECT p.*, "\r\n'
    b'            "  (SELECT COUNT(*) FROM boq_buildings b WHERE b.project_id=p.id) AS n_buildings, "\r\n'
    b'            "  (SELECT COUNT(*) FROM boq_floor_items i WHERE i.project_id=p.id) AS n_items, "\r\n'
    b'            "  (SELECT COALESCE(SUM(total_amount),0) FROM boq_floor_items i WHERE i.project_id=p.id) AS grand_total "\r\n'
    b'            "FROM boq_projects p "\r\n'
    b'            "WHERE p.user_id=? "\r\n'
    b'            "ORDER BY p.updated_at DESC, p.id DESC",\r\n'
    b'            (uid,),\r\n'
    b'        ).fetchall()\r\n'
    b'    return render_template("boq_projects_list.html", user=current_user(), projects=projects)\r\n'
)

NEW = (
    b'    uid = session["user_id"]\r\n'
    b'    _boq_ensure_schema()\r\n'
    b'    # Isolation (owner 2026-07-03 #7): Generation-Station capital BOQs share\r\n'
    b'    # the boq_projects table but must NOT clutter the marketplace BOQ list.\r\n'
    b'    # Default view hides them; ?scope=capital shows only them.\r\n'
    b'    _scope = (request.args.get("scope") or "").strip().lower()\r\n'
    b'    if _scope == "capital":\r\n'
    b'        _type_clause = (" AND p.project_type IN '
    b"('capital_facilities','capital_solar_farm') \")\r\n"
    b'    else:\r\n'
    b'        _type_clause = (" AND (p.project_type IS NULL OR p.project_type '
    b"NOT IN ('capital_facilities','capital_solar_farm')) \")\r\n"
    b'    with get_db() as c:\r\n'
    b'        projects = c.execute(\r\n'
    b'            "SELECT p.*, "\r\n'
    b'            "  (SELECT COUNT(*) FROM boq_buildings b WHERE b.project_id=p.id) AS n_buildings, "\r\n'
    b'            "  (SELECT COUNT(*) FROM boq_floor_items i WHERE i.project_id=p.id) AS n_items, "\r\n'
    b'            "  (SELECT COALESCE(SUM(total_amount),0) FROM boq_floor_items i WHERE i.project_id=p.id) AS grand_total "\r\n'
    b'            "FROM boq_projects p "\r\n'
    b'            "WHERE p.user_id=? " + _type_clause +\r\n'
    b'            "ORDER BY p.updated_at DESC, p.id DESC",\r\n'
    b'            (uid,),\r\n'
    b'        ).fetchall()\r\n'
    b'    return render_template("boq_projects_list.html", user=current_user(), projects=projects, boq_scope=_scope)\r\n'
)

if NEW in data:
    print("ALREADY PATCHED - no change")
else:
    n = data.count(OLD)
    assert n == 1, f"expected exactly 1 match, found {n}"
    data = data.replace(OLD, NEW)
    open("web_app.py", "wb").write(data)
    print("PATCHED boq_projects_list isolation OK")
