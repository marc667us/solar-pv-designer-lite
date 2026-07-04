# -*- coding: utf-8 -*-
"""Focused test for the Step 9 free-tier autobuild floor cap
(_CI_MAX_AUTOBUILD_FLOORS). Forces the cap to 1 with a 2-facility project and
verifies: (a) BOTH floors + BOTH link rows are still created (nothing dropped),
(b) only ONE floor is pre-priced synchronously, (c) the flash tells the user the
extra floor was linked-but-not-priced and to use Build-all. In-process swap of
v2 against real base.html; touches no live files."""
import os, sys, json, importlib.util

REPO = r"C:\Users\USER\Desktop\solar-pv-designer-lite"
os.chdir(REPO); sys.path.insert(0, REPO)
os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "test-admin-pw-123")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "test-owner-pw-123")
os.environ["DB_PATH"] = os.path.join(REPO, "tmp", "_step9cap_swap.db")
os.environ["CI_MAX_AUTOBUILD_FLOORS"] = "1"   # <-- force the cap
try:
    os.remove(os.environ["DB_PATH"])
except OSError:
    pass

spec = importlib.util.spec_from_file_location(
    "new_capital_investment_routes",
    os.path.join(REPO, "new_capital_investment_routes_v2.py"))
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
sys.modules["new_capital_investment_routes"] = mod
assert mod._CI_MAX_AUTOBUILD_FLOORS == 1, mod._CI_MAX_AUTOBUILD_FLOORS
print("cap =", mod._CI_MAX_AUTOBUILD_FLOORS)

import web_app  # noqa: E402
app = web_app.app
app.config["WTF_CSRF_ENABLED"] = False
try:
    from new_boq_hierarchy_schema import ensure_boq_hierarchy_schema
    ensure_boq_hierarchy_schema(web_app.get_db)
except Exception as e:
    print("WARN boq schema:", e)

with web_app.get_db() as c:
    row = c.execute("SELECT id FROM users WHERE username=?", ("marc667us",)).fetchone()
uid = row["id"] if row else row[0]

fails = []
def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), "-", name, extra)
    if not cond:
        fails.append(name)

c = app.test_client()
with c.session_transaction() as s:
    s["user_id"] = uid; s["_csrf"] = "tok"

# Step 1 create
r = c.post("/large-scale-solar/new", data={
    "_csrf": "tok", "project_name": "Step9 Cap Test",
    "project_type": "utility_scale", "country": "Ghana",
    "target_mwp": "25", "currency": "GHS", "project_status": "concept"},
    follow_redirects=False)
pid = int(r.headers.get("Location", "").rstrip("/").split("/")[-1])
print("pid =", pid)

# Step 3 site
c.post(f"/large-scale-solar/{pid}/step3", data={
    "_csrf": "tok", "terrain": "flat", "slope": "lt_3", "soil": "loam",
    "land_area_ha": "48.5"})
# Step 4 -> 2 facilities
c.post(f"/large-scale-solar/{pid}/step4", data={
    "_csrf": "tok", "buildings": ["control_room", "om_building"],
    "external_works": ["pv_field", "fence"]})
# Step 5 tech
c.post(f"/large-scale-solar/{pid}/step5", data={
    "_csrf": "tok", "technologies": ["scada", "digital_twin"]})
# Step 6 electrical
c.post(f"/large-scale-solar/{pid}/step6", data={
    "_csrf": "tok", "services": ["internal_installation", "fire_alarm"]})
# Step 7 PV (save)
c.post(f"/large-scale-solar/{pid}/step7", data={
    "_csrf": "tok", "module_tech": "mono_topcon", "kwp": "25000"})
# Step 8 finance (save)
c.post(f"/large-scale-solar/{pid}/step8", data={
    "_csrf": "tok", "tariff_local_per_kwh": "1.5", "fx_local_per_usd": "12",
    "revenue_model": "ppa", "project_life_yr": "25", "monte_carlo_runs": "0"})

# Step 9 generate — follow the redirect so the flash renders on the overview
r = c.post(f"/large-scale-solar/{pid}/step9", data={"_csrf": "tok"},
           follow_redirects=True)
check("step9 generate 200 (followed)", r.status_code == 200, r.status_code)
check("flash: extra floor linked-but-not-priced",
      b"not pre-priced" in r.data, "flash missing")
check("flash: points to Build-all", b"Build-all" in r.data, "no Build-all hint")

with web_app.get_db() as db:
    bpid = db.execute("SELECT boq_project_id FROM capital_investment_projects "
                      "WHERE id=?", (pid,)).fetchone()[0]
check("linked boq_project_id set", bool(bpid), bpid)
if bpid:
    with web_app.get_db() as db:
        nfloor = db.execute("SELECT COUNT(*) FROM boq_floors WHERE project_id=?",
                            (bpid,)).fetchone()[0]
        nlinks = db.execute("SELECT COUNT(*) FROM capital_investment_boq_links "
                            "WHERE capital_investment_project_id=?", (pid,)).fetchone()[0]
        npriced_floors = db.execute(
            "SELECT COUNT(DISTINCT floor_id) FROM boq_floor_items "
            "WHERE project_id=? AND source_type='capital_autobuild'",
            (bpid,)).fetchone()[0]
        nitems = db.execute("SELECT COUNT(*) FROM boq_floor_items WHERE "
                            "project_id=? AND source_type='capital_autobuild'",
                            (bpid,)).fetchone()[0]
    # The cap must NOT drop structure: both floors + both links persist.
    check("both floors still created (cap != drop)", nfloor == 2, nfloor)
    # 2 facility links + 1 solar_farm link (two-BOQ split, 2026-07-03)
    check("link rows still created (cap != drop): 2 facility + 1 solar", nlinks == 3, nlinks)
    # Only ONE floor is pre-priced under cap=1; the other is deferred.
    check("exactly ONE floor pre-priced under cap=1", npriced_floors == 1,
          npriced_floors)
    check("priced floor has items > 0", nitems > 0, nitems)

print(f"\n=== STEP9 CAP TEST: {'ALL PASS' if not fails else 'FAILURES: ' + str(fails)} ===")
sys.exit(1 if fails else 0)
