# -*- coding: utf-8 -*-
"""
patch_ci_step8_finance_boq_fixes.py
===================================
Codex review fixes for the Step 8 finance -> BOQ linkage:

  HIGH  Override double-count: scope _ci_boq_actuals to the facilities BOQ
        service codes (_CI_BOQ_SERVICE_ORDER = building electrical / SCADA-ICT
        / security) so a later-edited linked BOQ carrying grid/civil/external
        scopes can't overstate the boq_facilities override.
  MED1  Grand total vs per-facility mismatch: ONE LEFT JOIN aggregation - the
        grand total is the sum of the per-facility rows; items with a missing
        building_id count as 'unassigned' instead of silently vanishing.
  MED2  Explicit tenant predicate: apply web_app._boq_tenant_clause("i") on top
        of RLS (parallel-run safe).
  MED3  FX sanitisation: clamp fx > 0 ONCE in the POST + GET paths so the BOQ
        reconciliation and finance_utility use the same positive FX.
  LOW   Stale GET panel: flag recon.stale when the live facilities-BOQ total
        drifts from the saved model; template shows a "Recompute" hint.

Byte-level, CRLF-aware, idempotent. Applies on top of
patch_ci_step8_finance_boq.py.
"""

MODULE = "new_capital_investment_routes.py"
TEMPLATE = "templates/capital_investment_step8_finance.html"


def crlf(s: str) -> bytes:
    return s.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")


def apply(path, edits, sentinel):
    data = open(path, "rb").read()
    if sentinel in data:
        print(f"{path}: already fix-patched - no-op")
        return
    for i, (old, new) in enumerate(edits, 1):
        ob, nb = crlf(old), crlf(new)
        n = data.count(ob)
        assert n == 1, f"{path}: edit {i} anchor count={n} (expected 1)"
        data = data.replace(ob, nb, 1)
    open(path, "wb").write(data)
    print(f"{path}: fix-patched OK ({len(edits)} edits)")


# ---------------------------------------------------------------------------
# HIGH + MED1 + MED2 - rewrite the _ci_boq_actuals body (facilities scope,
# single LEFT JOIN aggregation, explicit tenant clause).
# ---------------------------------------------------------------------------
HELPER_OLD = '''    out = {
        "linked": False,
        "boq_project_id": int(boq_project_id or 0),
        "grand_total_local": 0.0,
        "grand_total_usd": 0.0,
        "per_facility_local": {},
        "per_facility_usd": {},
        "facility_costs_usd": {},
        "n_items": 0,
    }
    try:
        fx = float(fx) or 12.0
    except (TypeError, ValueError):
        fx = 12.0
    if not boq_project_id:
        return out
    try:
        with get_db() as c:
            grow = c.execute(
                "SELECT COALESCE(SUM(total_amount),0), COUNT(*) "
                "FROM boq_floor_items WHERE project_id=? AND user_id=?",
                (int(boq_project_id), int(uid))).fetchone()
            g_local = float((grow[0] if grow else 0) or 0)
            n_items = int((grow[1] if grow else 0) or 0)
            rows = c.execute(
                "SELECT b.purpose_subtype, COALESCE(SUM(i.total_amount),0) "
                "FROM boq_floor_items i "
                "JOIN boq_buildings b ON b.id=i.building_id "
                "WHERE i.project_id=? AND i.user_id=? "
                "GROUP BY b.purpose_subtype",
                (int(boq_project_id), int(uid))).fetchall()
    except Exception:
        return out
    out["linked"] = True
    out["grand_total_local"] = round(g_local, 2)
    out["grand_total_usd"] = round(g_local / fx, 2) if fx else 0.0
    out["n_items"] = n_items
    _labels = {cd: L for cd, L, _, _ in BUILDING_TYPES}
    for r in (rows or []):
        fac = ((r[0] if r else "") or "").strip() or "unassigned"
        tot = float((r[1] if r and len(r) > 1 else 0) or 0)
        out["per_facility_local"][fac] = round(tot, 2)
        usd = round(tot / fx, 2) if fx else 0.0
        out["per_facility_usd"][fac] = usd
        out["facility_costs_usd"][_labels.get(fac, fac)] = usd
    return out


def _ci_facility_services(building_code: str) -> list[str]:'''
HELPER_NEW = '''    out = {
        "linked": False,
        "boq_project_id": int(boq_project_id or 0),
        "grand_total_local": 0.0,
        "grand_total_usd": 0.0,
        "per_facility_local": {},
        "per_facility_usd": {},
        "facility_costs_usd": {},
        "n_items": 0,
    }
    try:
        fx = float(fx)
    except (TypeError, ValueError):
        fx = 12.0
    if fx <= 0:
        fx = 12.0
    if not boq_project_id:
        return out
    # Scope the reconciliation to the facilities BOQ services (building
    # electrical / SCADA-ICT / security) - the SAME scope the three replaced
    # CAPEX lines represent - so the override never double-counts unrelated
    # scopes (grid, civil, external works) a user might later add to the
    # linked BOQ via the standard editor.
    svc = list(_CI_BOQ_SERVICE_ORDER)
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
                tuple(params)).fetchall()
    except Exception:
        return out
    out["linked"] = True
    _labels = {cd: L for cd, L, _, _ in BUILDING_TYPES}
    g_local = 0.0
    n_items = 0
    for r in (rows or []):
        fac = ((r[0] if r else "") or "").strip() or "unassigned"
        tot = float((r[1] if r and len(r) > 1 else 0) or 0)
        cnt = int((r[2] if r and len(r) > 2 else 0) or 0)
        g_local += tot
        n_items += cnt
        usd = round(tot / fx, 2) if fx else 0.0
        out["per_facility_local"][fac] = round(tot, 2)
        out["per_facility_usd"][fac] = usd
        out["facility_costs_usd"][_labels.get(fac, fac)] = usd
    out["grand_total_local"] = round(g_local, 2)
    out["grand_total_usd"] = round(g_local / fx, 2) if fx else 0.0
    out["n_items"] = n_items
    return out


def _ci_facility_services(building_code: str) -> list[str]:'''

# ---------------------------------------------------------------------------
# MED3 - clamp POST fx > 0 once (reused by BOQ reconciliation + finance).
# ---------------------------------------------------------------------------
POST_FX_OLD = '''            fx = _n("fx_local_per_usd", 12.0)
            use_boq_capex = bool(f.get("use_boq_capex"))'''
POST_FX_NEW = '''            fx = _n("fx_local_per_usd", 12.0)
            if fx <= 0:
                fx = 12.0
            use_boq_capex = bool(f.get("use_boq_capex"))'''

# ---------------------------------------------------------------------------
# MED3 + LOW - clamp GET gfx > 0 and flag a stale panel.
# ---------------------------------------------------------------------------
GET_OLD = '''        # GET - rebuild the BOQ reconciliation from the saved finance config.
        gfx = 12.0
        try:
            gfx = float(fin_cfg.get("fx_local_per_usd") or 12.0) or 12.0
        except (TypeError, ValueError):
            gfx = 12.0
        g_boq = _ci_boq_actuals(get_db, proj.get("boq_project_id"), uid, gfx)
        g_capex = fin_cfg.get("capex_usd_per_kwp") or DEFAULT_CAPEX_USD_PER_KWP
        g_est = round(sum(float(g_capex.get(k, 0.0) or 0.0)
                          for k in _CI_FACILITY_CAPEX_KEYS) * kwp, 2)
        g_recon = {
            "est_facilities_usd": g_est,
            "boq_actual_usd":     g_boq["grand_total_usd"],
            "boq_actual_local":   g_boq["grand_total_local"],
            "variance_usd":       round(g_boq["grand_total_usd"] - g_est, 2),
            "use_boq_capex":      bool(fin_cfg.get("use_boq_capex")),
            "n_items":            g_boq["n_items"],
        }'''
GET_NEW = '''        # GET - rebuild the BOQ reconciliation from the saved finance config.
        gfx = 12.0
        try:
            gfx = float(fin_cfg.get("fx_local_per_usd") or 12.0)
        except (TypeError, ValueError):
            gfx = 12.0
        if gfx <= 0:
            gfx = 12.0
        g_boq = _ci_boq_actuals(get_db, proj.get("boq_project_id"), uid, gfx)
        g_capex = fin_cfg.get("capex_usd_per_kwp") or DEFAULT_CAPEX_USD_PER_KWP
        g_est = round(sum(float(g_capex.get(k, 0.0) or 0.0)
                          for k in _CI_FACILITY_CAPEX_KEYS) * kwp, 2)
        # Flag when the live facilities-BOQ total has drifted from the model
        # that produced the saved CAPEX/NPV cards, so the panel can prompt a
        # Recompute instead of showing a live actual beside stale finance.
        _saved_recon = (fin_cfg.get("computed") or {}).get(
            "boq_reconciliation") or {}
        g_stale = bool(
            _saved_recon and abs(
                g_boq["grand_total_usd"]
                - float(_saved_recon.get("boq_actual_usd") or 0.0)) > 1.0)
        g_recon = {
            "est_facilities_usd": g_est,
            "boq_actual_usd":     g_boq["grand_total_usd"],
            "boq_actual_local":   g_boq["grand_total_local"],
            "variance_usd":       round(g_boq["grand_total_usd"] - g_est, 2),
            "use_boq_capex":      bool(fin_cfg.get("use_boq_capex")),
            "n_items":            g_boq["n_items"],
            "stale":              g_stale,
        }'''

MODULE_EDITS = [
    (HELPER_OLD, HELPER_NEW),
    (POST_FX_OLD, POST_FX_NEW),
    (GET_OLD, GET_NEW),
]

# ---------------------------------------------------------------------------
# LOW - template stale hint inside the reconciliation panel.
# ---------------------------------------------------------------------------
T_OLD = '''            </div>
            {% if boq_actuals and boq_actuals.get('per_facility_usd') %}'''
T_NEW = '''            </div>
            {% if recon.get('stale') %}
              <div class="small text-warning mt-2"><i class="bi bi-exclamation-triangle me-1"></i>The linked BOQ changed since this model was last saved &mdash; click <strong>Recompute</strong> to refresh CAPEX / NPV.</div>
            {% endif %}
            {% if boq_actuals and boq_actuals.get('per_facility_usd') %}'''

TEMPLATE_EDITS = [(T_OLD, T_NEW)]


if __name__ == "__main__":
    apply(MODULE, MODULE_EDITS, crlf("Scope the reconciliation to the facilities BOQ services"))
    apply(TEMPLATE, TEMPLATE_EDITS, crlf("The linked BOQ changed since this model"))
    print("done")
