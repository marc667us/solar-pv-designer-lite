# -*- coding: utf-8 -*-
"""
patch_ci_step8_finance_boq_fix2.py
==================================
Codex round-2 fix - the HIGH scope discriminator.

Round-1 scoped _ci_boq_actuals by `service_code IN (_CI_BOQ_SERVICE_ORDER)`.
Codex correctly flagged that this is still too broad: `power_supply_lv` carries
the standard BOQ's TRANSFORMERS + EXTERNAL LIGHTING sections, and the capital
module maps grid / inverter / BOP electrical scopes onto the same facilities
service codes. So once a user edits the linked BOQ, service_code alone cannot
fence the boq_facilities override.

Robust fix: scope to the rows Step 9 ITSELF generated -
`source_type = 'capital_autobuild'` (written by web_app._ci_autobuild_floor_items
and PRESERVED through Build-all edits - verified: the qty-edit UPDATE at
web_app.py:24896 and the row-edit UPDATE at :33574 never touch source_type).
Any broad scope a user adds later gets a different source_type and is excluded.
Quantity completion (which only rewrites rate/total on the existing autobuild
rows) is still reflected.

Byte-level, CRLF-aware, idempotent. Applies on top of the two prior patches.
"""

MODULE = "new_capital_investment_routes.py"


def crlf(s: str) -> bytes:
    return s.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")


def apply(path, edits, sentinel):
    data = open(path, "rb").read()
    if sentinel in data:
        print(f"{path}: already fix2-patched - no-op")
        return
    for i, (old, new) in enumerate(edits, 1):
        ob, nb = crlf(old), crlf(new)
        n = data.count(ob)
        assert n == 1, f"{path}: edit {i} anchor count={n} (expected 1)"
        data = data.replace(ob, nb, 1)
    open(path, "wb").write(data)
    print(f"{path}: fix2-patched OK ({len(edits)} edits)")


# 1. Add the autobuild source-type constant next to _CI_FACILITY_CAPEX_KEYS.
CONST_OLD = '''_CI_FACILITY_CAPEX_KEYS: tuple[str, ...] = ("electrical", "ict_scada", "security")'''
CONST_NEW = '''_CI_FACILITY_CAPEX_KEYS: tuple[str, ...] = ("electrical", "ict_scada", "security")

# The immutable scope tag web_app._ci_autobuild_floor_items writes on every
# Step 9 facilities cell. Used to scope the BOQ reconciliation / override so it
# reflects ONLY the generated facilities BOQ (durable across Build-all edits).
_CI_AUTOBUILD_SOURCE: str = "capital_autobuild"'''

# 2. Swap the service_code filter for the source_type filter.
SCOPE_OLD = '''    svc = list(_CI_BOQ_SERVICE_ORDER)
    svc_ph = ",".join("?" for _ in svc)
    # Defence-in-depth tenant scoping on top of RLS (parallel-run safe).
    try:
        from web_app import _boq_tenant_clause
        tclause, tparams = _boq_tenant_clause("i")
    except Exception:
        tclause, tparams = "", ()
    params = [int(boq_project_id), int(uid)] + svc + list(tparams)
    try:
        with get_db() as c:
            # ONE aggregation source. LEFT JOIN so an item with a missing/bad
            # building_id still counts (grouped 'unassigned') and the grand
            # total always equals the sum of the per-facility rows.
            rows = c.execute(
                "SELECT b.purpose_subtype, "
                "       COALESCE(SUM(i.total_amount),0), COUNT(*) "
                "FROM boq_floor_items i "
                "LEFT JOIN boq_buildings b "
                "       ON b.id=i.building_id AND b.project_id=i.project_id "
                "WHERE i.project_id=? AND i.user_id=? "
                "  AND i.service_code IN (" + svc_ph + ")" + tclause +
                " GROUP BY b.purpose_subtype",
                tuple(params)).fetchall()'''
SCOPE_NEW = '''    # Defence-in-depth tenant scoping on top of RLS (parallel-run safe).
    try:
        from web_app import _boq_tenant_clause
        tclause, tparams = _boq_tenant_clause("i")
    except Exception:
        tclause, tparams = "", ()
    params = [int(boq_project_id), int(uid), _CI_AUTOBUILD_SOURCE] + list(tparams)
    try:
        with get_db() as c:
            # ONE aggregation source. LEFT JOIN so an item with a missing/bad
            # building_id still counts (grouped 'unassigned') and the grand
            # total always equals the sum of the per-facility rows.
            #
            # Scope by source_type (the Step 9 autobuild tag), NOT service_code:
            # service codes like 'power_supply_lv' are broad (they also carry
            # TRANSFORMERS / EXTERNAL LIGHTING and the module maps grid / BOP
            # scope onto them), so a service_code filter cannot fence the
            # override once a user edits the linked BOQ. source_type is
            # immutable across edits, so it precisely and durably marks the
            # generated facilities scope; anything the user adds later is
            # excluded.
            rows = c.execute(
                "SELECT b.purpose_subtype, "
                "       COALESCE(SUM(i.total_amount),0), COUNT(*) "
                "FROM boq_floor_items i "
                "LEFT JOIN boq_buildings b "
                "       ON b.id=i.building_id AND b.project_id=i.project_id "
                "WHERE i.project_id=? AND i.user_id=? "
                "  AND i.source_type=?" + tclause +
                " GROUP BY b.purpose_subtype",
                tuple(params)).fetchall()'''

MODULE_EDITS = [
    (CONST_OLD, CONST_NEW),
    (SCOPE_OLD, SCOPE_NEW),
]


if __name__ == "__main__":
    apply(MODULE, MODULE_EDITS, crlf("_CI_AUTOBUILD_SOURCE"))
    print("done")
