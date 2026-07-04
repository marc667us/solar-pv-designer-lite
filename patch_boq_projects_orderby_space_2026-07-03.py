# Byte-level fix: `_boq_tenant_clause("p")` returns a clause with NO trailing
# space, so `... + _tc +\r\n "ORDER BY ..."` concatenated to `= ?)ORDER BY`,
# a SQL syntax error whenever a Keycloak tenant context is active (Supervisor
# HIGH). Add a leading space to the ORDER BY fragment. Idempotent.
data = open("web_app.py", "rb").read()
OLD = (
    b'            "WHERE p.user_id=? " + _type_clause + _tc +\r\n'
    b'            "ORDER BY p.updated_at DESC, p.id DESC",\r\n'
)
NEW = (
    b'            "WHERE p.user_id=? " + _type_clause + _tc +\r\n'
    b'            " ORDER BY p.updated_at DESC, p.id DESC",\r\n'
)
if NEW in data:
    print("ALREADY PATCHED - no change")
else:
    n = data.count(OLD)
    assert n == 1, f"expected 1 match, found {n}"
    open("web_app.py", "wb").write(data.replace(OLD, NEW))
    print("PATCHED ORDER BY space OK")
