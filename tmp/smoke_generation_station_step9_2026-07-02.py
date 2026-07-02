# -*- coding: utf-8 -*-
"""
Local smoke test for Generation Station Step 9 BOQ auto-build (cell level).

Proves that POSTing Step 9 for a capital-investment project with facilities
selected creates:
  * a linked boq_projects row WITH a non-empty services_csv,
  * one boq_buildings + Ground Floor boq_floors per facility,
  * capital_investment_boq_links traceability rows,
  * boq_floor_items CELL rows priced via the standard engine,
  * boq_floor_rate_buildup rows for those cells.

Non-destructive: inserts a throwaway project + BOQ, asserts, then deletes
everything it created. Run:  python tmp/smoke_generation_station_step9_2026-07-02.py
"""
import os
import sys

os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "smoke-admin-pw")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "smoke-owner-pw")
os.environ.setdefault("SECRET_KEY", "smoke-secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import web_app  # noqa: E402

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

    # Ensure capital-investment schema exists (landing triggers _ensure_*).
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

    # Insert a throwaway capital-investment project directly.
    with get_db() as c:
        cur = c.execute(
            "INSERT INTO capital_investment_projects "
            "(user_id, project_name, client_name, project_type, "
            " facility_config, technology_config, electrical_config, "
            " target_kwp) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (uid, "SMOKE Generation Station", "Smoke Client", "utility_scale",
             json.dumps(facility), json.dumps(technology),
             json.dumps(electrical), 5000.0),
        )
        pid = int(cur.lastrowid or 0)
    print(f"Created capital project pid={pid}")
    check(pid > 0, "capital project inserted")

    # POST Step 9.
    resp = client.post(
        f"/large-scale-solar/{pid}/step9",
        data={"_csrf": "smoketok"},
        follow_redirects=False,
    )
    check(resp.status_code in (302, 303), f"step9 POST redirected (got {resp.status_code})")

    # Re-load project to get boq_project_id.
    with get_db() as c:
        row = c.execute(
            "SELECT boq_project_id FROM capital_investment_projects WHERE id=?",
            (pid,)).fetchone()
    boq_pid = int(row[0]) if row and row[0] else 0
    check(boq_pid > 0, f"boq_project_id linked (={boq_pid})")

    services_csv = ""
    n_buildings = n_floors = n_items = n_links = n_buildup = 0
    if boq_pid:
        with get_db() as c:
            r = c.execute("SELECT services_csv FROM boq_projects WHERE id=?",
                          (boq_pid,)).fetchone()
            services_csv = (r[0] if r and r[0] else "") or ""
            n_buildings = int(c.execute(
                "SELECT COUNT(*) FROM boq_buildings WHERE project_id=?",
                (boq_pid,)).fetchone()[0])
            n_floors = int(c.execute(
                "SELECT COUNT(*) FROM boq_floors WHERE project_id=?",
                (boq_pid,)).fetchone()[0])
            n_items = int(c.execute(
                "SELECT COUNT(*) FROM boq_floor_items WHERE project_id=?",
                (boq_pid,)).fetchone()[0])
            n_buildup = int(c.execute(
                "SELECT COUNT(*) FROM boq_floor_rate_buildup WHERE project_id=?",
                (boq_pid,)).fetchone()[0])
            n_links = int(c.execute(
                "SELECT COUNT(*) FROM capital_investment_boq_links "
                "WHERE capital_investment_project_id=?", (pid,)).fetchone()[0])
            grand = c.execute(
                "SELECT COALESCE(SUM(total_amount),0) FROM boq_floor_items "
                "WHERE project_id=?", (boq_pid,)).fetchone()[0]

    print(f"services_csv = {services_csv!r}")
    print(f"buildings={n_buildings} floors={n_floors} items(cells)={n_items} "
          f"rate_buildup={n_buildup} links={n_links} grand_total={grand}")

    check(bool(services_csv.strip()), "services_csv is non-empty")
    check(n_buildings == 5, f"5 boq_buildings created (got {n_buildings})")
    check(n_floors == 5, f"5 Ground Floors created (got {n_floors})")
    check(n_items > 0, f"cell-level boq_floor_items created (got {n_items})")
    check(n_buildup == n_items, f"rate_buildup row per item ({n_buildup}=={n_items})")
    check(n_links == 5, f"5 capital_investment_boq_links (got {n_links})")
    check(float(grand or 0) > 0, "grand total > 0 (rates applied)")

    # Idempotency: a second POST must NOT create a second BOQ project.
    resp2 = client.post(f"/large-scale-solar/{pid}/step9",
                        data={"_csrf": "smoketok"})
    with get_db() as c:
        again = c.execute(
            "SELECT COUNT(*) FROM boq_projects WHERE user_id=? AND project_name LIKE ?",
            (uid, "SMOKE Generation Station%")).fetchone()[0]
    check(int(again) == 1, f"idempotent - still one BOQ project (got {again})")

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
