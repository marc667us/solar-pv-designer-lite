# -*- coding: utf-8 -*-
"""
Local smoke test for Generation Station Step 8 (Finance) -> BOQ linkage.

Proves:
  * Step 9 builds the linked BOQ (reused from the step9 smoke path),
  * _ci_boq_actuals() summarises boq_floor_items by facility (USD + local),
  * Step 8 GET renders the reconciliation panel (200 + marker text),
  * Step 8 recompute WITHOUT use_boq_capex keeps the estimate CAPEX,
  * Step 8 recompute WITH use_boq_capex drives CAPEX from the BOQ actual
    (electrical/ict_scada/security zeroed, boq_facilities line added),
  * saved finance_config carries use_boq_capex + boq_reconciliation.

Non-destructive: inserts a throwaway project + BOQ, asserts, cleans up.
Run:  python tmp/smoke_generation_station_step8_finance_2026-07-02.py
"""
import os
import sys

os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "smoke-admin-pw")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "smoke-owner-pw")
os.environ.setdefault("SECRET_KEY", "smoke-secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import web_app  # noqa: E402
import new_capital_investment_routes as ci  # noqa: E402

app = web_app.app
get_db = web_app.get_db

FAIL = []


def check(cond, msg):
    print(("  PASS " if cond else "  FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def _admin_uid():
    with get_db() as c:
        row = c.execute(
            "SELECT id FROM users WHERE is_admin=1 ORDER BY id LIMIT 1"
        ).fetchone()
    return int(row[0]) if row else None


def main():
    app.config["TESTING"] = True
    uid = _admin_uid()
    if uid is None:
        print("NO ADMIN USER in local DB - cannot run smoke test")
        sys.exit(2)
    print(f"Using admin uid={uid}")

    client = app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["_csrf"] = "smoketok"

    client.get("/large-scale-solar")

    facility = {
        "buildings": ["control_room", "om_building", "transformer_bldg",
                      "battery_room", "security_gate"],
        "external_works": ["pv_field", "cable_trench", "fence"],
    }
    technology = {"selected": ["scada", "weather", "remote_mon", "bms"]}
    electrical = {"selected": ["internal_installation", "power_supply",
                               "earthing", "fire_alarm", "ip_cctv", "lan",
                               "scada"]}
    # Step 7 sizing so finance has kwp + generation.
    pv_config = {"sizing": {"kwp_input": 5000.0, "annual_gen_mwh": 8500.0},
                 "kwp": 5000.0}

    with get_db() as c:
        cur = c.execute(
            "INSERT INTO capital_investment_projects "
            "(user_id, project_name, client_name, project_type, "
            " facility_config, technology_config, electrical_config, "
            " pv_config, target_kwp) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (uid, "SMOKE Finance Station", "Smoke Client", "utility_scale",
             json.dumps(facility), json.dumps(technology),
             json.dumps(electrical), json.dumps(pv_config), 5000.0),
        )
        pid = int(cur.lastrowid or 0)
    print(f"Created capital project pid={pid}")
    check(pid > 0, "capital project inserted")

    # Build the BOQ via Step 9.
    client.post(f"/large-scale-solar/{pid}/step9", data={"_csrf": "smoketok"})
    with get_db() as c:
        row = c.execute(
            "SELECT boq_project_id FROM capital_investment_projects WHERE id=?",
            (pid,)).fetchone()
    boq_pid = int(row[0]) if row and row[0] else 0
    check(boq_pid > 0, f"boq_project_id linked (={boq_pid})")

    # ---- _ci_boq_actuals directly ----
    fx = 12.0
    act = ci._ci_boq_actuals(get_db, boq_pid, uid, fx)
    print(f"actuals: linked={act['linked']} n_items={act['n_items']} "
          f"local={act['grand_total_local']} usd={act['grand_total_usd']} "
          f"facilities={list(act['per_facility_usd'].keys())}")
    check(act["linked"], "actuals linked=True")
    check(act["n_items"] > 0, f"actuals has cells (n_items={act['n_items']})")
    check(act["grand_total_usd"] > 0, "actuals grand_total_usd > 0")
    check(abs(act["grand_total_usd"] - act["grand_total_local"] / fx) < 1.0,
          "usd == local / fx (fx conversion)")
    check(len(act["per_facility_usd"]) >= 1, "per-facility breakdown present")
    check(len(act["facility_costs_usd"]) >= 1,
          "facility_costs_usd (labelled) present")
    sum_fac = round(sum(act["per_facility_local"].values()), 0)
    check(abs(sum_fac - round(act["grand_total_local"], 0)) < 2.0,
          f"per-facility local sums to grand total ({sum_fac})")

    # ---- Step 8 GET renders the reconciliation panel ----
    r_get = client.get(f"/large-scale-solar/{pid}/step8")
    body = r_get.get_data(as_text=True)
    check(r_get.status_code == 200, f"step8 GET 200 (got {r_get.status_code})")
    check("Linked BOQ reconciliation" in body,
          "reconciliation panel rendered")
    check("BOQ line items" in body, "BOQ line-item badge rendered")
    check("use_boq_capex" in body, "opt-in checkbox rendered")

    # ---- Recompute WITHOUT override: CAPEX uses the estimate ----
    base_form = {
        "_csrf": "smoketok", "recompute_only": "1",
        "tariff_local_per_kwh": "1.5", "fx_local_per_usd": str(fx),
        "capex_electrical": "190", "capex_ict_scada": "25",
        "capex_security": "10", "capex_modules": "360",
    }
    r1 = client.post(f"/large-scale-solar/{pid}/step8", data=dict(base_form))
    check(r1.status_code == 200, f"recompute (no override) 200 (got {r1.status_code})")
    with get_db() as c:
        fc = c.execute(
            "SELECT finance_config FROM capital_investment_projects WHERE id=?",
            (pid,)).fetchone()[0]
    saved1 = json.loads(fc)
    capex1 = saved1.get("computed", {}).get("capex_lines_usd", {})
    check(saved1.get("use_boq_capex") is False, "saved use_boq_capex=False")
    check(float(capex1.get("electrical", 0)) > 0,
          "electrical CAPEX line kept (no override)")
    check("boq_facilities" not in capex1,
          "no boq_facilities line without override")
    recon1 = saved1.get("computed", {}).get("boq_reconciliation", {})
    check(recon1.get("n_items", 0) > 0, "saved reconciliation has n_items")

    # ---- Recompute WITH override: CAPEX driven by BOQ actual ----
    ov_form = dict(base_form)
    ov_form["use_boq_capex"] = "1"
    r2 = client.post(f"/large-scale-solar/{pid}/step8", data=ov_form)
    check(r2.status_code == 200, f"recompute (override) 200 (got {r2.status_code})")
    with get_db() as c:
        fc2 = c.execute(
            "SELECT finance_config FROM capital_investment_projects WHERE id=?",
            (pid,)).fetchone()[0]
    saved2 = json.loads(fc2)
    capex2 = saved2.get("computed", {}).get("capex_lines_usd", {})
    check(saved2.get("use_boq_capex") is True, "saved use_boq_capex=True")
    check(float(capex2.get("electrical", 1)) == 0.0,
          "electrical CAPEX zeroed under override")
    check(float(capex2.get("ict_scada", 1)) == 0.0,
          "ict_scada CAPEX zeroed under override")
    check(float(capex2.get("security", 1)) == 0.0,
          "security CAPEX zeroed under override")
    check("boq_facilities" in capex2, "boq_facilities line added under override")
    # boq_facilities total (USD) should equal the BOQ actual USD (within rounding).
    bf = float(capex2.get("boq_facilities", 0))
    check(abs(bf - act["grand_total_usd"]) / max(act["grand_total_usd"], 1) < 0.02,
          f"boq_facilities ~= BOQ actual USD (bf={bf:,.0f} vs {act['grand_total_usd']:,.0f})")

    # ---- Codex HIGH/MED1 verification: source_type scope + LEFT JOIN ----
    # (a) A BROAD item under an ALLOWED facilities service code
    #     (power_supply_lv = TRANSFORMERS/grid scope) added MANUALLY - it must
    #     be EXCLUDED because it is not source_type='capital_autobuild'. This
    #     is exactly the case a service_code filter would have missed.
    # (b) An autobuild orphan with a bad building_id - must still count as
    #     'unassigned' and keep grand total == sum of per-facility rows.
    with get_db() as c:
        frow = c.execute(
            "SELECT id, building_id FROM boq_floor_items "
            "WHERE project_id=? ORDER BY id LIMIT 1", (boq_pid,)).fetchone()
        fid0, bid0 = int(frow[0]), int(frow[1] or 0)
        c.execute(
            "INSERT INTO boq_floor_items (floor_id, building_id, project_id, "
            " user_id, service_code, section, bill_no, description, unit, qty, "
            " final_built_up_rate, total_amount, source_type) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (fid0, bid0, boq_pid, uid, "power_supply_lv", "TRANSFORMERS", 8,
             "2 MVA distribution transformer", "No.", 1, 999999.0, 999999.0,
             "manual"))
        c.execute(
            "INSERT INTO boq_floor_items (floor_id, building_id, project_id, "
            " user_id, service_code, section, bill_no, description, unit, qty, "
            " final_built_up_rate, total_amount, source_type) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (fid0, -12345, boq_pid, uid, "power_supply_lv", "Orphan", 5,
             "Orphaned LV item", "No.", 1, 1200.0, 1200.0, "capital_autobuild"))
    act2 = ci._ci_boq_actuals(get_db, boq_pid, uid, fx)
    check(act2["grand_total_local"] < act["grand_total_local"] + 999999.0,
          "broad manual power_supply_lv item EXCLUDED (source_type scope)")
    check("unassigned" in act2["per_facility_usd"],
          "autobuild orphan (bad building_id) grouped as 'unassigned'")
    s2 = round(sum(act2["per_facility_local"].values()), 0)
    check(abs(s2 - round(act2["grand_total_local"], 0)) < 2.0,
          f"grand total == sum of per-facility rows after edits ({s2})")
    check(abs((act2["grand_total_local"] - act["grand_total_local"]) - 1200.0)
          < 2.0, "only the +1200 autobuild orphan added (broad item excluded)")

    # ---- cleanup ----
    with get_db() as c:
        if boq_pid:
            c.execute("DELETE FROM boq_floor_rate_buildup WHERE project_id=?", (boq_pid,))
            c.execute("DELETE FROM boq_floor_items WHERE project_id=?", (boq_pid,))
            c.execute("DELETE FROM boq_floors WHERE project_id=?", (boq_pid,))
            c.execute("DELETE FROM boq_buildings WHERE project_id=?", (boq_pid,))
            c.execute("DELETE FROM boq_projects WHERE id=?", (boq_pid,))
        c.execute("DELETE FROM capital_investment_boq_links WHERE capital_investment_project_id=?", (pid,))
        c.execute("DELETE FROM capital_investment_projects WHERE id=?", (pid,))
    print("cleanup done")

    print()
    if FAIL:
        print(f"RESULT: {len(FAIL)} FAILED")
        for m in FAIL:
            print("  - " + m)
        sys.exit(1)
    print("RESULT: ALL PASS")


if __name__ == "__main__":
    main()
