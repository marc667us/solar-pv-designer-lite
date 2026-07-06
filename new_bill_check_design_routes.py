# ─── Check My Bill → Solar Design auto-handoff ───────────────────────────────
# Added 2026-07-06 (owner queued feature #1).
#
# Purpose: let a Check-My-Bill user turn their bill straight into a finished
# solar design + results page in ONE click — no manual wizard. Owner framing:
# these are ADDITIVE tweaks to the EXISTING app, so we REUSE the same calc_*
# engine, the same project table, the same coverage helpers — we do NOT fork
# the interactive wizard handler.
#
# Flow:
#   POST /bill-check/design
#     • logged-in  -> create a project seeded from the bill, run the full design
#                     in-process, redirect to /project/<pid>/results.
#     • anonymous  -> stash the bill payload in session['pending_bill_design'],
#                     bounce through registration with
#                     ?next=/bill-check/design/continue.
#   GET  /bill-check/design/continue   (login_required)
#     • consume the stash after auth, then create+design+redirect exactly as the
#       logged-in branch does.
#
# Every module-level name used below (get_db, get_project, current_user,
# save_project_data, get_solar_data, PLAN_LIMITS, the calc_* engine,
# BATTERY_CHEMISTRY, PANEL_SPEC, inverter_brand, math, json, _bc_compute,
# _bc_bill_to_kwh, _bc_refresh_coverage) is already defined in web_app.py at the
# point this block is spliced in (before `if __name__ == "__main__":`).


def _run_project_design(pid, data, loads):
    """Self-contained design pass for project `pid`.

    Mirrors the compute block inside the interactive `project_loads` POST handler
    (peak/diversified-peak -> auto phase -> calc_loads -> calc_pv -> calc_battery
    -> calc_inverter -> calc_mppt -> size_all_cables -> calc_boq ->
    calc_economics) so a bill-seeded project reaches the SAME results shape the
    wizard produces — without surgically refactoring (and risking) that live
    handler. Thin duplicate orchestration is the deliberate, safe choice.

    Inputs
      pid   : project id (int)
      data  : the project's data dict (mutated: loads/phase/results/coverage set)
      loads : list of load dicts (name/category/wattage/quantity/hours/
              demand_factor/critical)
    Output: pid (after persisting via save_project_data).
    """
    data["loads"] = loads

    # Connected peak load (wattage x qty, no demand factor) — drives phase
    # selection & cable sizing. Diversified peak (x demand factor) — inverter.
    peak_kw = sum(
        float(ld.get("wattage", 0)) * float(ld.get("quantity", 1))
        for ld in loads) / 1000.0
    div_peak_kw = sum(
        float(ld.get("wattage", 0)) * float(ld.get("quantity", 1))
        * float(ld.get("demand_factor", 0.70))
        for ld in loads) / 1000.0

    # > 8 kW connected load -> 3-phase 415V (IEC 60364 / BS 7671), else single.
    auto_phase = "three" if peak_kw > 8.0 else "single"
    data["phase"] = auto_phase

    # ── Engine inputs (all sourced from the seeded project data) ──
    daily_kwh   = calc_loads(loads)
    psh         = data.get("psh", 5.0)
    temp        = data.get("avg_temp", 28.0)
    autonomy    = data.get("autonomy", 1)
    system_type = data.get("system_type", "off-grid")
    phase       = auto_phase
    tariff      = data.get("tariff", 2.0)
    currency    = data.get("currency", "USD")
    symbol      = data.get("symbol", "$")
    cost_kwp    = data.get("cost_usd_kwp", 900)
    fx          = data.get("fx_usd", 1.0)
    chemistry   = data.get("chemistry", "LiFePO4")
    dc_voltage  = data.get("voltage", 48)
    panel_wp    = data.get("panel_wp", 400)
    supply_markup_pct = float(data.get("supply_markup_pct", 8))
    install_rate_pct  = float(data.get("install_rate_pct", 15))

    # Shading correction (1.0 = none; operator sets it after site inspection).
    _sh = data.get("shading", {}) or {}
    _sh_factor = float(_sh.get("factor", 1.0) or 1.0)

    pv_kw, num_panels, td, pv_kw_base = calc_pv(
        daily_kwh, psh, temp, panel_wp, shading_factor=_sh_factor)
    bat_kwh, num_bat, unit_bat = calc_battery(daily_kwh, autonomy, chemistry)
    inv_kw = calc_inverter(daily_kwh, peak_kw=div_peak_kw)
    mppt_a = calc_mppt(pv_kw, dc_voltage)
    ac_cables = size_all_cables(inv_kw, pv_kw, system_type, phase, ambient_c=temp)
    pps = 2 if dc_voltage <= 24 else 4 if dc_voltage <= 48 else 8
    num_strings = math.ceil(num_panels / pps)
    boq_rows, boq_grand = calc_boq(
        num_panels, num_bat, inv_kw, pv_kw, bat_kwh,
        unit_bat, chemistry, mppt_a, cost_kwp, fx, panel_wp,
        ac_cables=ac_cables, voltage=dc_voltage, num_strings=num_strings,
        supply_markup_pct=supply_markup_pct, install_rate_pct=install_rate_pct)
    economics = calc_economics(
        pv_kw, num_panels, bat_kwh, num_bat, inv_kw,
        daily_kwh, tariff, currency, symbol, cost_kwp, fx, autonomy,
        boq_total_local=boq_grand,
        chemistry=chemistry,
        funding_mode=data.get("funding_mode", "loan"),
        install_rate_pct=install_rate_pct)

    chem_info = BATTERY_CHEMISTRY.get(chemistry, BATTERY_CHEMISTRY["LiFePO4"])
    data["results"] = {
        "daily_kwh":      daily_kwh,
        "pv_kw":          pv_kw,
        "pv_kw_base":     pv_kw_base,
        "shading_factor": _sh_factor,
        "shading":        _sh,
        "num_panels":     num_panels,
        "panel_wp":       panel_wp,
        "temp_derating":  td,
        "bat_kwh":        bat_kwh,
        "num_bat":        num_bat,
        "unit_bat_kwh":   unit_bat,
        "chemistry":      chemistry,
        "chem_name":      chem_info["name"],
        "chem_dod":       chem_info["dod"],
        "chem_cycles":    chem_info["cycle_life"],
        "chem_life":      chem_info["lifetime_yr"],
        "chem_brands":    chem_info["brands"],
        "inv_kw":         inv_kw,
        "inv_brand":      inverter_brand(inv_kw),
        "mppt_a":         mppt_a,
        "peak_kw":        round(peak_kw, 2),
        "div_peak_kw":    round(div_peak_kw, 2),
        "auto_phase":     auto_phase,
        "panel_spec":     PANEL_SPEC,
        "economics":      economics,
        "boq_rows":       boq_rows,
        "boq_grand":      boq_grand,
        "ac_cables":      ac_cables,
    }
    # Attach the Energy Coverage analysis (design vs bill) so the funding pitch
    # lands with the correct ~100% Full-Load reading for a bill-seeded design.
    _bc_refresh_coverage(data)
    save_project_data(pid, data)
    return pid


def _bc_synthetic_loads(bill_monthly_kwh):
    """One representative whole-premises load standing in for the customer's
    metered consumption, derived from the bill-estimated monthly kWh.

    Undiversified (demand_factor 1.0) and run 8h/day, so the entered wattage is
    daily_kWh * 1000 / 8. This yields a load schedule whose UNDIVERSIFIED energy
    equals the bill estimate — which is exactly the basis _bc_coverage compares
    against, so a bill-seeded design reads ~100% (Full Load)."""
    kwh = max(0.0, float(bill_monthly_kwh or 0))
    daily = kwh / 30.44
    watt = (daily * 1000.0 / 8.0) if daily > 0 else 0.0
    return [{
        "name":          "Estimated total load (from bill)",
        "category":      "Other",
        "wattage":       round(watt, 1),
        "quantity":      1,
        "hours":         8,
        "demand_factor": 1.0,
        "critical":      False,
    }]


def _bc_design_seed(payload):
    """Build (initial_data, loads, project_name) for a Check-My-Bill auto-design.

    The bill_check snapshot is RECOMPUTED server-side via _bc_compute (never
    trust client-sent numbers). The sizing energy is derived INDEPENDENTLY by
    inverting the live PURC bands on the actual bill (_bc_bill_to_kwh) — matching
    the coverage helper's own basis — with the compute's monthly_kwh as a
    fallback. Location defaults to Ghana / Greater Accra (the platform's home
    market); grid-tied, GHS."""
    bc = _bc_compute(payload, loads=None)  # loads=None -> bill-derived kWh path
    actual_bill = float(bc.get("actual_bill") or 0)
    category = (bc.get("inputs") or {}).get("category") \
        or "Residential Standard (0-300 kWh/month)"

    # Size on the SAME basis _bc_refresh_coverage will use as the coverage
    # denominator, so a bill-seeded design reads ~100% (Full Load) in every case:
    #   • genuine meter reading  -> size from that reading (coverage override too)
    #   • bill only              -> independent PURC inversion of the bill
    energy = bc.get("energy") or {}
    if energy.get("source") == "user_provided_kwh" \
            and float(energy.get("monthly_kwh") or 0) > 0:
        bill_kwh = float(energy["monthly_kwh"])
    else:
        bill_kwh = _bc_bill_to_kwh(actual_bill, category)
        if bill_kwh <= 0:
            bill_kwh = float(energy.get("monthly_kwh") or 0)
    loads = _bc_synthetic_loads(bill_kwh)

    country, region = "Ghana", "Greater Accra"
    sd = get_solar_data(country, region) or {}
    fx = float(sd.get("fx_usd", 12.0) or 12.0)
    cost_usd_kwp = sd.get("cost_usd_kwp", 850)
    # Honour the Cost/kWp the user tuned in the funding pitch (entered in GHS)
    # so the delivered design's economics match the numbers they were shown.
    try:
        ghs_cost = float(payload.get("system_cost_per_kwp") or 0)
    except (TypeError, ValueError):
        ghs_cost = 0.0
    if ghs_cost > 0 and fx > 0:
        cost_usd_kwp = ghs_cost / fx
    initial_data = {
        "country":       country,
        "region":        region,
        "psh":           sd.get("psh", 5.3),
        "avg_temp":      sd.get("avg_temp", 28.0),
        "tariff":        sd.get("tariff", 2.0),
        "currency":      sd.get("currency", "GHS"),
        "symbol":        sd.get("symbol", "GHS "),
        "cost_usd_kwp":  cost_usd_kwp,
        "fx_usd":        fx,
        "system_type":   "grid-tied",
        "phase":         "single",
        "voltage":       48,
        "autonomy":      1,
        "building_type": "Residential",
        "from_bill_check": True,
        "bill_check":    bc,
        "loads":         loads,
    }
    proj_name = "Solar design from bill ({} {:,.0f}/month)".format(
        sd.get("currency", "GHS"), actual_bill)
    return initial_data, loads, proj_name


def _bc_create_and_design(payload):
    """Create a bill-seeded project for the current user, run the full design,
    and return (pid, error_redirect). On plan-limit breach returns
    (None, redirect_response). Caller redirects to results on success."""
    user = current_user()
    plan = (user["plan"] or "free").lower()
    limit = PLAN_LIMITS.get(plan, 1)
    initial_data, loads, proj_name = _bc_design_seed(payload)
    # Server-side validation: a zero/sub-service-charge bill inverts to 0 kWh,
    # which would seed a degenerate zero-panel "design". Refuse it here (the JS
    # guards too, but a direct POST bypasses that).
    if not loads or float(loads[0].get("wattage") or 0) <= 0:
        flash("Please enter a valid monthly electricity bill before we can "
              "design a system.", "warning")
        return None, redirect(url_for("bill_check_landing"))
    with get_db() as c:
        count = c.execute(
            "SELECT COUNT(*) FROM projects WHERE user_id=?",
            (session["user_id"],)).fetchone()[0]
        if count >= limit:
            flash(
                "Your {} plan allows up to {} project{}. Upgrade to design "
                "more systems.".format(
                    plan.title(), limit, "s" if limit > 1 else ""),
                "warning")
            return None, redirect(url_for("dashboard"))
        c.execute(
            "INSERT INTO projects (user_id, name, data_json) VALUES (?,?,?)",
            (session["user_id"], proj_name, json.dumps(initial_data)))
        pid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    # Re-load through get_project so the design runs on the same data shape the
    # rest of the app persists, then compute + save results.
    proj = get_project(pid)
    data = (proj.get("data") if proj else None) or initial_data
    _run_project_design(pid, data, loads)
    return pid, None


@app.route("/bill-check/design", methods=["POST"])
def bill_check_design():
    """One-click: turn a Check-My-Bill result into a finished solar design.

    Accepts the same field set the bill-check calculator posts (JSON or form).
    Logged-in users get a project created + designed immediately. Anonymous
    users have their bill payload stashed and are sent through registration,
    returning to /bill-check/design/continue afterwards."""
    csrf_protect()
    payload = request.get_json(force=True, silent=True) or request.form.to_dict()

    if session.get("user_id"):
        try:
            pid, err = _bc_create_and_design(payload)
        except Exception:
            app.logger.exception("bill_check_design: auto-design failed")
            flash("We couldn't build the design automatically. Please try the "
                  "manual designer.", "danger")
            return redirect(url_for("dashboard"))
        if err is not None:
            return err
        flash("We designed a starter system from your bill. Review and refine "
              "it below.", "success")
        return redirect(url_for("project_results", pid=pid))

    # Anonymous: stash the (small, non-sensitive) bill payload and register.
    session["pending_bill_design"] = {
        "actual_bill":          payload.get("actual_bill"),
        "actual_kwh":           payload.get("actual_kwh"),
        "category":             payload.get("category"),
        "meter_type":           payload.get("meter_type"),
        "completeness":         payload.get("completeness"),
        "target_reduction_pct": payload.get("target_reduction_pct"),
        "system_cost_per_kwp":  payload.get("system_cost_per_kwp"),
        "loan_years":           payload.get("loan_years"),
        "loan_interest_pct":    payload.get("loan_interest_pct"),
    }
    return redirect(url_for("register", next="/bill-check/design/continue"))


# Interstitial shown after auth: the OIDC callback can only redirect here via a
# GET, so the GET never mutates state — it renders a CSRF-bearing form that
# auto-submits to the POST below, which does the actual project creation. This
# keeps design/project creation strictly behind POST + CSRF (no state-mutating
# GET), while still working as the post-registration landing page.
_BC_CONTINUE_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Building your solar design…</title>
<style>
  body{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#0b1220;color:#f1f5f9;
       display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
  .card{text-align:center;max-width:22rem;padding:2rem}
  .spin{width:2.5rem;height:2.5rem;border:4px solid rgba(241,245,249,.25);
        border-top-color:#f59e0b;border-radius:50%;margin:0 auto 1rem;animation:s 1s linear infinite}
  @keyframes s{to{transform:rotate(360deg)}}
  button{background:#f59e0b;color:#0b1220;border:0;border-radius:.5rem;
         padding:.6rem 1.2rem;font-weight:700;cursor:pointer;margin-top:1rem}
</style></head><body>
<div class="card">
  <div class="spin"></div>
  <p>Designing a starter solar system from your bill…</p>
  <form id="bcgo" method="POST" action="__ACTION__">
    <input type="hidden" name="_csrf" value="__CSRF__">
    <noscript><button type="submit">Continue</button></noscript>
  </form>
</div>
<script>document.getElementById("bcgo").submit();</script>
</body></html>"""


@app.route("/bill-check/design/continue", methods=["GET"])
@login_required
def bill_check_design_continue():
    """Post-auth landing (GET, non-mutating). If a stashed bill payload exists,
    render an auto-submitting CSRF form that POSTs to the mutating handler."""
    if not session.get("pending_bill_design"):
        flash("Your bill details expired. Please run Check My Bill again.",
              "info")
        return redirect(url_for("bill_check_landing"))
    html = (_BC_CONTINUE_HTML
            .replace("__ACTION__", url_for("bill_check_design_continue_run"))
            .replace("__CSRF__", generate_csrf()))
    return html


@app.route("/bill-check/design/continue", methods=["POST"], endpoint="bill_check_design_continue_run")
@login_required
def bill_check_design_continue_run():
    """CSRF-protected consumer of the stashed bill payload — the only place the
    post-auth auto-design actually creates a project."""
    csrf_protect()
    payload = session.pop("pending_bill_design", None)
    if not payload:
        flash("Your bill details expired. Please run Check My Bill again.",
              "info")
        return redirect(url_for("bill_check_landing"))
    try:
        pid, err = _bc_create_and_design(payload)
    except Exception:
        app.logger.exception("bill_check_design_continue: auto-design failed")
        flash("We couldn't build the design automatically. Please try the "
              "manual designer.", "danger")
        return redirect(url_for("dashboard"))
    if err is not None:
        return err
    flash("We designed a starter system from your bill. Review and refine it "
          "below.", "success")
    return redirect(url_for("project_results", pid=pid))
