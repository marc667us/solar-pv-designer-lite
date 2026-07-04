# -*- coding: utf-8 -*-
"""End-to-end test of the Generation-Station BOQ rework (owner 2026-07-03):
  1/5 Build-all + all buildings priced (finish route, per-facility scope)
  2   Excel per-service sheets always present (+ Solar Farm tab)
  3/4 TWO BOQs: facilities (capital_facilities) + 20MWp solar (capital_solar_farm)
  6   New reports: wiring / single_line / energy_impact / economic_impact /
      implementation_plan render valid PDFs
  7   Isolation: /boq-projects hides capital BOQs by default; ?scope=capital shows them
Imports the ACTIVE new_capital_investment_routes.py (NOT the v2 backup)."""
import os, sys, io, importlib
REPO = r"C:\Users\USER\Desktop\solar-pv-designer-lite"
os.chdir(REPO); sys.path.insert(0, REPO)
os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "x")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "y")
os.environ["DB_PATH"] = os.path.join(REPO, "tmp", "_two_boq.db")
os.environ["CI_MAX_AUTOBUILD_FLOORS"] = "6"   # force the deferred-floor path
try: os.remove(os.environ["DB_PATH"])
except OSError: pass

import web_app  # imports the ACTIVE module
app = web_app.app; app.config["WTF_CSRF_ENABLED"] = False
from new_boq_hierarchy_schema import ensure_boq_hierarchy_schema
ensure_boq_hierarchy_schema(web_app.get_db)

with web_app.get_db() as cx:
    row = cx.execute("SELECT id FROM users WHERE username=?", ("marc667us",)).fetchone()
uid = row["id"] if row else row[0]

fails = []
def ck(n, c, e=''):
    print(("PASS" if c else "FAIL"), "-", n, e)
    if not c: fails.append(n)

c = app.test_client()
with c.session_transaction() as s:
    s["user_id"] = uid; s["_csrf"] = "tok"

# --- create + walk the wizard (8 buildings so the cap defers 2) ---
r = c.post("/large-scale-solar/new", data={"_csrf":"tok","project_name":"TwoBOQ Test",
    "project_type":"utility_scale","country":"Ghana","region":"Ashanti",
    "target_mwp":"20","currency":"GHS","project_status":"concept"})
pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
c.post(f"/large-scale-solar/{pid}/step3", data={"_csrf":"tok","terrain":"flat","slope":"lt_3","soil":"loam","land_area_ha":"40"})
buildings = ["control_room","om_building","security_gate","battery_room",
             "inverter_room","switchgear_bldg","transformer_bldg","scada_bldg"]
c.post(f"/large-scale-solar/{pid}/step4", data={"_csrf":"tok","buildings":buildings,"external_works":["pv_field"]})
c.post(f"/large-scale-solar/{pid}/step5", data={"_csrf":"tok","technologies":["scada","string_mon"]})
c.post(f"/large-scale-solar/{pid}/step6", data={"_csrf":"tok","services":["internal_installation","fire_alarm","power_supply"]})
c.post(f"/large-scale-solar/{pid}/step7", data={"_csrf":"tok","module_tech":"mono_topcon","kwp":"20000"})
c.post(f"/large-scale-solar/{pid}/step8", data={"_csrf":"tok","tariff_local_per_kwh":"1.5","fx_local_per_usd":"12","revenue_model":"ppa","monte_carlo_runs":"0"})
r = c.post(f"/large-scale-solar/{pid}/step9", data={"_csrf":"tok"}, follow_redirects=False)
ck("step9 redirects (no 500)", r.status_code == 302, r.status_code)

# --- inspect the two BOQs ---
with web_app.get_db() as cx:
    prow = dict(cx.execute("SELECT * FROM capital_investment_projects WHERE id=?", (pid,)).fetchone())
    fac_pid = prow.get("boq_facilities_project_id")
    sol_pid = prow.get("boq_solar_project_id")
    ck("facilities BOQ id set", bool(fac_pid), fac_pid)
    ck("solar BOQ id set", bool(sol_pid), sol_pid)
    ck("legacy boq_project_id == facilities", prow.get("boq_project_id") == fac_pid,
       (prow.get("boq_project_id"), fac_pid))
    ptypes = {r2["id"]: r2["project_type"] for r2 in
              cx.execute("SELECT id, project_type FROM boq_projects WHERE user_id=?", (uid,)).fetchall()}
    ck("facilities project_type", ptypes.get(fac_pid) == "capital_facilities", ptypes.get(fac_pid))
    ck("solar project_type", ptypes.get(sol_pid) == "capital_solar_farm", ptypes.get(sol_pid))
    # Default free-tier path: Step 9 defers pricing (structure only), so both
    # BOQs are linked but empty until "Finish BOQ pricing" runs.
    fac_items = cx.execute("SELECT COUNT(*) FROM boq_floor_items WHERE project_id=?", (fac_pid,)).fetchone()[0]
    sol_items = cx.execute("SELECT COUNT(*) FROM boq_floor_items WHERE project_id=?", (sol_pid,)).fetchone()[0]
    ck("step9 defers pricing (facilities empty)", fac_items == 0, fac_items)
    ck("step9 defers pricing (solar empty)", sol_items == 0, sol_items)
    n_bldg_total = cx.execute("SELECT COUNT(*) FROM boq_buildings WHERE project_id=?", (fac_pid,)).fetchone()[0]
    ck("all 8 facility buildings linked", n_bldg_total == 8, n_bldg_total)

# --- finish route: price deferred facility floors + solar over repeated clicks
# (each click prices <= CI_MAX_AUTOBUILD_FLOORS facility floors OR the solar
# floor, never both) ---
for _click in range(1, 8):
    r = c.post(f"/large-scale-solar/{pid}/boq/finish", data={"_csrf":"tok"}, follow_redirects=False)
    if r.status_code != 302:
        ck(f"finish click {_click} redirects", False, r.status_code); break
    with web_app.get_db() as cx:
        nb = cx.execute("SELECT COUNT(DISTINCT building_id) FROM boq_floor_items WHERE project_id=?", (fac_pid,)).fetchone()[0]
        si = cx.execute("SELECT COUNT(*) FROM boq_floor_items WHERE project_id=?", (sol_pid,)).fetchone()[0]
    if nb == 8 and si > 0:
        break
with web_app.get_db() as cx:
    n_bldg_priced2 = cx.execute("SELECT COUNT(DISTINCT building_id) FROM boq_floor_items WHERE project_id=?", (fac_pid,)).fetchone()[0]
    sol_items2 = cx.execute("SELECT COUNT(*) FROM boq_floor_items WHERE project_id=?", (sol_pid,)).fetchone()[0]
    sol_src = cx.execute("SELECT DISTINCT source_type FROM boq_floor_items WHERE project_id=?", (sol_pid,)).fetchall()
    # New 12-bill farm BOQ (Codex template 2026-07-03): distinct bill_no values.
    sol_bills = cx.execute("SELECT COUNT(DISTINCT bill_no) FROM boq_floor_items WHERE project_id=?", (sol_pid,)).fetchone()[0]
    sol_bldg_name = cx.execute("SELECT building_name FROM boq_buildings WHERE project_id=?", (sol_pid,)).fetchone()
    sol_floor_name = cx.execute("SELECT floor_name FROM boq_floors f JOIN boq_buildings b ON b.id=f.building_id WHERE b.project_id=?", (sol_pid,)).fetchone()
ck("ALL 8 facility buildings priced after finish clicks", n_bldg_priced2 == 8, n_bldg_priced2)
ck("solar farm BOQ is the full 12-bill catalog (>=50 items)", sol_items2 >= 50, sol_items2)
ck("solar farm BOQ spans all 12 bills", sol_bills == 12, sol_bills)
ck("solar building reads as a farm, not a building",
   sol_bldg_name and "Generation Assets" in (sol_bldg_name[0] or ""), sol_bldg_name)
ck("solar floor reads as a farm zone",
   sol_floor_name and "Farm BOQ Zone" in (sol_floor_name[0] or ""), sol_floor_name)
ck("solar rows tagged capital_solar_autobuild",
   [x[0] for x in sol_src] == ["capital_solar_autobuild"], [x[0] for x in sol_src])

# --- Excel export: Summary + service sheets + Solar Farm sheet ---
r = c.get(f"/large-scale-solar/{pid}/cost-plan.xlsx")
ck("xlsx 200", r.status_code == 200, r.status_code)
import openpyxl
wb = openpyxl.load_workbook(io.BytesIO(r.data))
names = wb.sheetnames
ck("Summary first", names[0] == "Summary", names[:3])
ck("has a Solar/PV sheet", any("Solar" in n or "PV" in n or "Module" in n for n in names), names)
ck(">=5 sheets", len(names) >= 5, len(names))

# --- new reports render valid PDFs ---
for key in ("wiring","single_line","energy_impact","economic_impact","implementation_plan"):
    rr = c.get(f"/large-scale-solar/{pid}/report/{key}.pdf")
    ok = rr.status_code == 200 and rr.data[:4] == b"%PDF"
    ck(f"report {key}.pdf valid", ok, (rr.status_code, rr.data[:4]))

# --- isolation on /boq-projects ---
r = c.get("/boq-projects")
default_hidden = (b"capital_facilities" not in r.data) and (str(sol_pid).encode() not in r.data or b"Solar Farm 20MWp" not in r.data)
ck("default /boq-projects hides capital BOQs", (b"Solar Farm 20MWp" not in r.data), "check body")
r2 = c.get("/boq-projects?scope=capital")
ck("scope=capital shows capital BOQs", b"Solar Farm 20MWp" in r2.data or b"Facilities" in r2.data, "check body")

print("=== TWO-BOQ SOLAR-FARM:", "ALL PASS" if not fails else "FAIL "+str(fails), "===")
sys.exit(1 if fails else 0)
