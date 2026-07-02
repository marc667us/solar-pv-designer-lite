# -*- coding: utf-8 -*-
"""
patch_ci_step8_finance_boq.py
=============================
SSS section 8 - link Step 8 (Financial Engineering) CAPEX to the REAL, linked
Step 9 Generation-Station BOQ.

What this adds (reuse-first, no parallel engine):
  * _ci_boq_actuals(get_db, boq_project_id, uid, fx) - summarises the linked
    boq_floor_items totals the standard engine already wrote, grouped by
    facility (boq_buildings.purpose_subtype). USD + local + per-facility +
    facility_costs_usd (labelled, for CRM / SSS section 8 downstream).
  * A reconciliation block on Step 8: facilities-CAPEX estimate vs BOQ actual
    (indicative) vs variance, plus per-facility chips.
  * An OPT-IN checkbox "use_boq_capex" (default OFF): when ticked, the
    electrical + SCADA + security CAPEX per-kWp lines are replaced by the BOQ
    actual (as a single boq_facilities per-kWp line) so the headline CAPEX is
    driven by the bill of quantities. Off by default because Step 9 seeds
    qty=1 indicative starter cells until the user completes Build-all.

Both files are CRLF; new_capital_investment_routes.py carries a few non-ASCII
bytes so we patch at the byte level, CRLF-aware. Template has 0 non-ASCII but
is CRLF - patched the same way to keep endings consistent. Idempotent.
"""

MODULE = "new_capital_investment_routes.py"
TEMPLATE = "templates/capital_investment_step8_finance.html"


def crlf(s: str) -> bytes:
    return s.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")


def apply(path, edits, sentinel):
    data = open(path, "rb").read()
    if sentinel in data:
        print(f"{path}: already patched - no-op")
        return
    for i, (old, new) in enumerate(edits, 1):
        ob, nb = crlf(old), crlf(new)
        n = data.count(ob)
        assert n == 1, f"{path}: edit {i} anchor count={n} (expected 1)"
        data = data.replace(ob, nb, 1)
    open(path, "wb").write(data)
    print(f"{path}: patched OK ({len(edits)} edits)")


# ---------------------------------------------------------------------------
# MODULE edits
# ---------------------------------------------------------------------------
M_HELPER_OLD = '''def _ci_facility_services(building_code: str) -> list[str]:'''
M_HELPER_NEW = '''# Facilities-related CAPEX lines - the subset the Step 9 BOQ actually covers
# (building interiors: electrical fit-out + SCADA/ICT + security). Modules,
# inverters, structures, civil, grid connection = PV field / balance of plant,
# NOT building BOQ, so they are excluded from the BOQ reconciliation.
_CI_FACILITY_CAPEX_KEYS: tuple[str, ...] = ("electrical", "ict_scada", "security")


def _ci_boq_actuals(get_db, boq_project_id, uid, fx: float = 12.0) -> dict:
    """Summarise a linked Generation-Station BOQ by REUSING the boq_floor_items
    totals the standard engine already wrote - no parallel costing. Returns the
    local + USD grand total, per-facility breakdown (facility =
    boq_buildings.purpose_subtype) and a labelled facility_costs_usd map for
    CRM / SSS section 8. Every figure is INDICATIVE while Step 9 seeds qty=1
    starter cells. Empty (linked=False) when nothing is linked."""
    out = {
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

M_UID_OLD = '''        proj = _load_project(pid)
        fin_cfg = _safe_json(proj.get("finance_config"))
        pv_cfg = _safe_json(proj.get("pv_config"))'''
M_UID_NEW = '''        proj = _load_project(pid)
        uid = session["user_id"]
        fin_cfg = _safe_json(proj.get("finance_config"))
        pv_cfg = _safe_json(proj.get("pv_config"))'''

M_FX_OLD = '''            fx = _n("fx_local_per_usd", 12.0)
            revenue_model = (f.get("revenue_model") or "ppa").strip()'''
M_FX_NEW = '''            fx = _n("fx_local_per_usd", 12.0)
            use_boq_capex = bool(f.get("use_boq_capex"))
            revenue_model = (f.get("revenue_model") or "ppa").strip()'''

M_CALL_OLD = '''            computed = finance_utility(
                kwp=kwp,
                annual_gen_mwh=annual_gen_mwh,
                tariff_local_per_kwh=tariff,
                fx_local_per_usd=fx,
                capex_usd_per_kwp=capex_form,'''
M_CALL_NEW = '''            # SSS section 8 - reconcile CAPEX against the linked Step 9 BOQ and
            # (opt-in) drive the facilities CAPEX lines from the BOQ actual.
            boq_actuals = _ci_boq_actuals(
                get_db, proj.get("boq_project_id"), uid, fx)
            est_facilities_usd = round(
                sum(float(capex_form.get(k, 0.0) or 0.0)
                    for k in _CI_FACILITY_CAPEX_KEYS) * kwp, 2)
            capex_effective = dict(capex_form)
            if (use_boq_capex and boq_actuals["grand_total_usd"] > 0
                    and kwp > 0):
                for _k in _CI_FACILITY_CAPEX_KEYS:
                    capex_effective[_k] = 0.0
                capex_effective["boq_facilities"] = round(
                    boq_actuals["grand_total_usd"] / kwp, 4)
            recon = {
                "est_facilities_usd": est_facilities_usd,
                "boq_actual_usd":     boq_actuals["grand_total_usd"],
                "boq_actual_local":   boq_actuals["grand_total_local"],
                "variance_usd":       round(
                    boq_actuals["grand_total_usd"] - est_facilities_usd, 2),
                "use_boq_capex":      bool(use_boq_capex),
                "n_items":            boq_actuals["n_items"],
            }

            computed = finance_utility(
                kwp=kwp,
                annual_gen_mwh=annual_gen_mwh,
                tariff_local_per_kwh=tariff,
                fx_local_per_usd=fx,
                capex_usd_per_kwp=capex_effective,'''

M_SAVED_OLD = '''            saved = {
                "capex_usd_per_kwp":       capex_form,
                "opex_usd_per_kwp_yr":     opex_form,'''
M_SAVED_NEW = '''            computed["boq_reconciliation"] = recon
            computed["facility_costs_usd"] = boq_actuals["facility_costs_usd"]

            saved = {
                "capex_usd_per_kwp":       capex_form,
                "use_boq_capex":           bool(use_boq_capex),
                "opex_usd_per_kwp_yr":     opex_form,'''

M_RECOMPUTE_OLD = '''                    revenue_models=REVENUE_MODELS,
                    kwp=kwp,
                    annual_gen_mwh=annual_gen_mwh,
                )
            flash("Financial model saved. Continue with Step 9.", "success")'''
M_RECOMPUTE_NEW = '''                    revenue_models=REVENUE_MODELS,
                    kwp=kwp,
                    annual_gen_mwh=annual_gen_mwh,
                    boq_actuals=boq_actuals,
                    recon=recon,
                )
            flash("Financial model saved. Continue with Step 9.", "success")'''

M_GET_OLD = '''        # GET
        return render_template(
            "capital_investment_step8_finance.html",
            user=current_user(),
            proj=proj,
            pv_cfg=pv_cfg,
            cfg=fin_cfg,
            computed=fin_cfg.get("computed") or {},
            default_capex=DEFAULT_CAPEX_USD_PER_KWP,
            default_opex=DEFAULT_OPEX_USD_PER_KWP_YR,
            revenue_models=REVENUE_MODELS,
            kwp=kwp,
            annual_gen_mwh=annual_gen_mwh,
        )'''
M_GET_NEW = '''        # GET - rebuild the BOQ reconciliation from the saved finance config.
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
        }
        return render_template(
            "capital_investment_step8_finance.html",
            user=current_user(),
            proj=proj,
            pv_cfg=pv_cfg,
            cfg=fin_cfg,
            computed=fin_cfg.get("computed") or {},
            default_capex=DEFAULT_CAPEX_USD_PER_KWP,
            default_opex=DEFAULT_OPEX_USD_PER_KWP_YR,
            revenue_models=REVENUE_MODELS,
            kwp=kwp,
            annual_gen_mwh=annual_gen_mwh,
            boq_actuals=g_boq,
            recon=g_recon,
        )'''

MODULE_EDITS = [
    (M_HELPER_OLD, M_HELPER_NEW),
    (M_UID_OLD, M_UID_NEW),
    (M_FX_OLD, M_FX_NEW),
    (M_CALL_OLD, M_CALL_NEW),
    (M_SAVED_OLD, M_SAVED_NEW),
    (M_RECOMPUTE_OLD, M_RECOMPUTE_NEW),
    (M_GET_OLD, M_GET_NEW),
]

# ---------------------------------------------------------------------------
# TEMPLATE edit - reconciliation panel + opt-in checkbox after the CAPEX block
# ---------------------------------------------------------------------------
T_OLD = '''        </div>

        <hr class="my-4" style="border-color:#1e1e3a">

        {# --- OPEX block --- #}'''
T_NEW = '''        </div>

        {# --- Generation Station BOQ linkage (SSS section 8) --- #}
        <div class="mt-3 p-3 rounded" style="background:#12122b;border:1px solid #1e1e3a">
          <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold text-info"><i class="bi bi-diagram-3 me-1"></i>Linked BOQ reconciliation</span>
            {% if recon and recon.get('n_items') %}
              <span class="badge bg-info-subtle text-info">{{ recon.n_items }} BOQ line items</span>
            {% else %}
              <span class="badge bg-secondary">no linked BOQ yet</span>
            {% endif %}
          </div>
          {% if recon and recon.get('n_items') %}
            <div class="row g-2 small">
              <div class="col-4"><div class="text-secondary">Facilities CAPEX estimate</div>
                <div class="fw-bold">USD {{ '{:,.0f}'.format(recon.est_facilities_usd) }}</div>
                <div class="text-secondary" style="font-size:11px">electrical + SCADA + security &times; kWp</div></div>
              <div class="col-4"><div class="text-secondary">BOQ actual (indicative)</div>
                <div class="fw-bold">USD {{ '{:,.0f}'.format(recon.boq_actual_usd) }}</div>
                <div class="text-secondary" style="font-size:11px">local {{ '{:,.0f}'.format(recon.boq_actual_local) }}</div></div>
              <div class="col-4"><div class="text-secondary">Variance</div>
                <div class="fw-bold {% if recon.variance_usd >= 0 %}text-warning{% else %}text-success{% endif %}">USD {{ '{:,.0f}'.format(recon.variance_usd) }}</div>
                <div class="text-secondary" style="font-size:11px">{% if recon.variance_usd >= 0 %}BOQ over estimate{% else %}BOQ under estimate{% endif %}</div></div>
            </div>
            {% if boq_actuals and boq_actuals.get('per_facility_usd') %}
              <div class="mt-2 small">
                <div class="text-secondary mb-1">Per-facility (USD, indicative):</div>
                <div class="d-flex flex-wrap gap-1">
                  {% for fac, usd in boq_actuals.per_facility_usd.items() %}
                    <span class="badge bg-dark border border-secondary text-light">{{ fac.replace('_',' ').title() }}: {{ '{:,.0f}'.format(usd) }}</span>
                  {% endfor %}
                </div>
              </div>
            {% endif %}
            <div class="form-check mt-3">
              <input class="form-check-input" type="checkbox" name="use_boq_capex" id="use_boq_capex" value="1" {% if recon.get('use_boq_capex') %}checked{% endif %}>
              <label class="form-check-label small" for="use_boq_capex">
                Drive electrical / SCADA / security CAPEX from the linked BOQ actual instead of the per-kWp estimate above.
                <span class="text-secondary">Off by default &mdash; BOQ cells seed at qty&nbsp;1 (indicative) until you complete quantities in Build-all.</span>
              </label>
            </div>
          {% else %}
            <div class="text-secondary small">Generate the BOQ on <strong>Step 9</strong> to reconcile these CAPEX lines against a real bill of quantities and (optionally) drive facilities CAPEX from it.</div>
          {% endif %}
        </div>

        <hr class="my-4" style="border-color:#1e1e3a">

        {# --- OPEX block --- #}'''

TEMPLATE_EDITS = [(T_OLD, T_NEW)]


if __name__ == "__main__":
    apply(MODULE, MODULE_EDITS, crlf("def _ci_boq_actuals("))
    apply(TEMPLATE, TEMPLATE_EDITS, crlf("Linked BOQ reconciliation"))
    print("done")
