# Byte-level follow-up patch: add tenant-clause defence-in-depth to the
# /boq-projects list (Codex MED-4). Idempotent. Depends on
# patch_boq_projects_isolation_2026-07-03.py having run first.
data = open("web_app.py", "rb").read()

# --- 1. compute tenant clause before the query ---
OLD1 = (
    b"        _type_clause = (\" AND (p.project_type IS NULL OR p.project_type "
    b"NOT IN ('capital_facilities','capital_solar_farm')) \")\r\n"
    b'    with get_db() as c:\r\n'
)
NEW1 = (
    b"        _type_clause = (\" AND (p.project_type IS NULL OR p.project_type "
    b"NOT IN ('capital_facilities','capital_solar_farm')) \")\r\n"
    b'    _tc, _tp = _boq_tenant_clause("p")\r\n'
    b'    with get_db() as c:\r\n'
)

# --- 2. inject the clause + params into the query ---
OLD2 = (
    b'            "WHERE p.user_id=? " + _type_clause +\r\n'
    b'            "ORDER BY p.updated_at DESC, p.id DESC",\r\n'
    b'            (uid,),\r\n'
)
NEW2 = (
    b'            "WHERE p.user_id=? " + _type_clause + _tc +\r\n'
    b'            "ORDER BY p.updated_at DESC, p.id DESC",\r\n'
    b'            tuple([uid] + list(_tp)),\r\n'
)

if b'_tc, _tp = _boq_tenant_clause("p")' in data:
    print("ALREADY PATCHED - no change")
else:
    n1 = data.count(OLD1); n2 = data.count(OLD2)
    assert n1 == 1, f"OLD1 matches={n1}"
    assert n2 == 1, f"OLD2 matches={n2}"
    data = data.replace(OLD1, NEW1).replace(OLD2, NEW2)
    open("web_app.py", "wb").write(data)
    print("PATCHED boq_projects_list tenant clause OK")
