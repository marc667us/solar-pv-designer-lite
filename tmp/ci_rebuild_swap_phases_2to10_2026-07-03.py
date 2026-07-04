# -*- coding: utf-8 -*-
"""Phase 2 verification: swap v2 module in-process, walk Step 2-6 + regulatory
against the real base.html. Touches no live files/wiring."""
import os, sys, importlib.util

REPO = r"C:\Users\USER\Desktop\solar-pv-designer-lite"
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "test-admin-pw-123")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "test-owner-pw-123")
os.environ["DB_PATH"] = os.path.join(REPO, "tmp", "_phase2_swap.db")
os.environ["CI_STEP9_PREPRICE"] = "1"   # test the synchronous pre-price path
try:
    os.remove(os.environ["DB_PATH"])
except OSError:
    pass

# --- swap v2 in BEFORE web_app imports it ---
spec = importlib.util.spec_from_file_location(
    "new_capital_investment_routes",
    os.path.join(REPO, "new_capital_investment_routes_v2.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
sys.modules["new_capital_investment_routes"] = mod
assert mod.CI_MODULE_BUILD == "v2-rebuild-2026-07-03", mod.CI_MODULE_BUILD

import web_app  # noqa: E402
app = web_app.app
app.config["WTF_CSRF_ENABLED"] = False

# marc667us user id
with web_app.get_db() as c:
    row = c.execute("SELECT id FROM users WHERE username=?", ("marc667us",)).fetchone()
uid = row["id"] if row else row[0]
print("marc667us uid =", uid)

fails = []
def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), "-", name, extra)
    if not cond:
        fails.append(name)

c = app.test_client()
with c.session_transaction() as s:
    s["user_id"] = uid
    s["_csrf"] = "tok"

# create a project (Step 1)
r = c.post("/large-scale-solar/new", data={
    "_csrf": "tok", "project_name": "Phase2 Rebuild Test",
    "project_type": "utility_scale", "country": "Ghana",
    "target_mwp": "25", "currency": "GHS", "project_status": "concept",
}, follow_redirects=False)
check("step1 create redirects", r.status_code == 302, r.status_code)
loc = r.headers.get("Location", "")
pid = int(loc.rstrip("/").split("/")[-1])
print("created pid =", pid, "->", loc)

# overview
r = c.get(f"/large-scale-solar/{pid}")
check("overview 200", r.status_code == 200, r.status_code)
check("overview shows regulatory link", b"Development &amp; Regulatory" in r.data or b"Development & Regulatory" in r.data)

# Step 2
r = c.get(f"/large-scale-solar/{pid}/step2")
check("step2 GET 200", r.status_code == 200, r.status_code)
r = c.post(f"/large-scale-solar/{pid}/step2", data={
    "_csrf": "tok", "project_type": "ipp", "project_status": "feasibility",
    "design_standard": "IEC"}, follow_redirects=False)
check("step2 POST redirects to step3", r.status_code == 302 and "/step3" in r.headers.get("Location",""),
      r.headers.get("Location"))

# invalid project_type ignored
r = c.post(f"/large-scale-solar/{pid}/step2", data={
    "_csrf": "tok", "project_type": "BOGUS", "project_status": "concept"},
    follow_redirects=False)
with web_app.get_db() as db:
    pt = db.execute("SELECT project_type FROM capital_investment_projects WHERE id=?", (pid,)).fetchone()[0]
check("invalid project_type stored as ''", pt == "", repr(pt))

# reset to valid
c.post(f"/large-scale-solar/{pid}/step2", data={"_csrf":"tok","project_type":"ipp","project_status":"feasibility","design_standard":"IEC"})

# Step 3 site
r = c.get(f"/large-scale-solar/{pid}/step3")
check("step3 GET 200", r.status_code == 200, r.status_code)
r = c.post(f"/large-scale-solar/{pid}/step3", data={
    "_csrf":"tok","terrain":"flat","slope":"lt_3","soil":"loam","flood_risk":"low",
    "wind_zone":"z2_medium","seismic_zone":"zone_1","access":"paved","water":"borehole",
    "land_area_ha":"48.5","notes":"good site","seismic_zone_bad":"xx"}, follow_redirects=False)
check("step3 POST -> step4", r.status_code == 302 and "/step4" in r.headers.get("Location",""), r.headers.get("Location"))
import json
with web_app.get_db() as db:
    sc = db.execute("SELECT site_config FROM capital_investment_projects WHERE id=?", (pid,)).fetchone()[0]
site = json.loads(sc)
check("site_config persisted terrain", site.get("terrain")=="flat", site.get("terrain"))
check("site_config land_area_ha=48.5", abs((site.get("land_area_ha") or 0)-48.5)<1e-6, site.get("land_area_ha"))

# invalid select value dropped
r = c.post(f"/large-scale-solar/{pid}/step3", data={"_csrf":"tok","terrain":"NOPE","slope":"lt_3"})
with web_app.get_db() as db:
    site2 = json.loads(db.execute("SELECT site_config FROM capital_investment_projects WHERE id=?", (pid,)).fetchone()[0])
check("invalid terrain dropped", site2.get("terrain")=="", repr(site2.get("terrain")))
# restore
c.post(f"/large-scale-solar/{pid}/step3", data={"_csrf":"tok","terrain":"flat","slope":"lt_3","soil":"loam","land_area_ha":"48.5"})

# Step 4 facilities
r = c.get(f"/large-scale-solar/{pid}/step4")
check("step4 GET 200", r.status_code == 200, r.status_code)
r = c.post(f"/large-scale-solar/{pid}/step4", data={
    "_csrf":"tok",
    "buildings":["control_room","om_building","BOGUS"],
    "external_works":["pv_field","fence"],
    "sub_control_room":["SCADA workstation","NotReal"],
    "sub_om_building":["Maintenance office"],
    "notes":"two buildings"}, follow_redirects=False)
check("step4 POST -> step5", r.status_code==302 and "/step5" in r.headers.get("Location",""), r.headers.get("Location"))
with web_app.get_db() as db:
    fc = json.loads(db.execute("SELECT facility_config FROM capital_investment_projects WHERE id=?", (pid,)).fetchone()[0])
check("facilities: only valid buildings", sorted(fc.get("buildings",[]))==["control_room","om_building"], fc.get("buildings"))
check("facilities: BOGUS building dropped", "BOGUS" not in fc.get("buildings",[]))
check("facilities: valid sub-items only", fc.get("sub_items",{}).get("control_room")==["SCADA workstation"], fc.get("sub_items"))
check("facilities: external works", sorted(fc.get("external_works",[]))==["fence","pv_field"], fc.get("external_works"))

# Step 5 technology
r = c.get(f"/large-scale-solar/{pid}/step5")
check("step5 GET 200", r.status_code == 200, r.status_code)
r = c.post(f"/large-scale-solar/{pid}/step5", data={
    "_csrf":"tok","technologies":["scada","digital_twin","BOGUS"],
    "notes":"control"}, follow_redirects=False)
check("step5 POST -> step6", r.status_code==302 and "/step6" in r.headers.get("Location",""), r.headers.get("Location"))
with web_app.get_db() as db:
    tc = json.loads(db.execute("SELECT technology_config FROM capital_investment_projects WHERE id=?", (pid,)).fetchone()[0])
check("tech: valid only", sorted(tc.get("technologies",[]))==["digital_twin","scada"], tc.get("technologies"))

# Step 6 electrical
r = c.get(f"/large-scale-solar/{pid}/step6")
check("step6 GET 200", r.status_code == 200, r.status_code)
r = c.post(f"/large-scale-solar/{pid}/step6", data={
    "_csrf":"tok","services":["internal_installation","fire_alarm","BOGUS"],
    "notes":"elec"}, follow_redirects=False)
# step7 now built -> chains forward to step7
check("step6 POST -> step7", r.status_code==302 and "/step7" in r.headers.get("Location",""), r.headers.get("Location"))
with web_app.get_db() as db:
    ec = json.loads(db.execute("SELECT electrical_config FROM capital_investment_projects WHERE id=?", (pid,)).fetchone()[0])
check("elec: valid only", sorted(ec.get("services",[]))==["fire_alarm","internal_installation"], ec.get("services"))

# Regulatory (Ghana country -> Ghana framework)
r = c.get(f"/large-scale-solar/{pid}/regulatory")
check("regulatory GET 200", r.status_code == 200, r.status_code)
check("regulatory shows Ghana regulator", b"Energy Commission" in r.data)
check("regulatory shows Ghana tenure", b"Stool land" in r.data)
r = c.post(f"/large-scale-solar/{pid}/regulatory", data={
    "_csrf":"tok","land_tenure":"stool_land",
    "status_esia":"applied","note_esia":"scoping done",
    "status_land_tenure":"in_progress","status_BOGUS":"x",
    "notes":"reg notes"}, follow_redirects=False)
check("regulatory POST -> overview", r.status_code==302, r.status_code)
with web_app.get_db() as db:
    rc = json.loads(db.execute("SELECT regulatory_config FROM capital_investment_projects WHERE id=?", (pid,)).fetchone()[0])
check("reg: land_tenure valid", rc.get("land_tenure")=="stool_land", rc.get("land_tenure"))
check("reg: esia status stored", rc.get("items",{}).get("esia",{}).get("status")=="applied", rc.get("items",{}).get("esia"))
check("reg: unknown item not injected", "BOGUS" not in rc.get("items",{}))

# --- Phase 3: Step 7 PV design ---
r = c.get(f"/large-scale-solar/{pid}/step7")
check("step7 GET 200", r.status_code == 200, r.status_code)
check("step7 seeds kWp from target (25MWp=25000)", b'value="25000' in r.data or b'value="25000.0' in r.data)
# recompute (stay on page, 200 with results)
r = c.post(f"/large-scale-solar/{pid}/step7", data={
    "_csrf":"tok","module_tech":"mono_topcon","module_wp":"600","mounting":"single_axis",
    "inverter_type":"central","battery_chem":"none","kwp":"25000","dc_ac_ratio":"1.2",
    "tilt_deg":"10","azimuth_deg":"180","psh_daily":"5.4","performance_ratio":"0.78",
    "availability_pct":"98","annual_degradation_pct":"0.5","project_life_yr":"25",
    "recompute_only":"1"}, follow_redirects=False)
check("step7 recompute stays 200", r.status_code == 200, r.status_code)
check("step7 results show yield", b"Annual yield" in r.data)
with web_app.get_db() as db:
    pc = json.loads(db.execute("SELECT pv_config FROM capital_investment_projects WHERE id=?", (pid,)).fetchone()[0])
sz = pc.get("sizing", {})
# 25 MWp @ 600Wp -> ceil(25_000_000/600)=41667 modules
check("step7 module count sane", sz.get("n_modules") == 41667, sz.get("n_modules"))
check("step7 annual_gen computed", (sz.get("annual_gen_mwh") or 0) > 0, sz.get("annual_gen_mwh"))
check("step7 invalid mounting kept valid on recompute", pc.get("mounting") == "single_axis", pc.get("mounting"))
# invalid module_tech falls back
r = c.post(f"/large-scale-solar/{pid}/step7", data={
    "_csrf":"tok","module_tech":"BOGUS","kwp":"25000","recompute_only":"1"}, follow_redirects=False)
with web_app.get_db() as db:
    pc2 = json.loads(db.execute("SELECT pv_config FROM capital_investment_projects WHERE id=?", (pid,)).fetchone()[0])
check("step7 invalid module_tech -> mono_topcon", pc2.get("module_tech") == "mono_topcon", pc2.get("module_tech"))
# final save -> step8 now built -> chains to step8
r = c.post(f"/large-scale-solar/{pid}/step7", data={
    "_csrf":"tok","module_tech":"mono_topcon","kwp":"25000"}, follow_redirects=False)
check("step7 save -> step8", r.status_code==302 and "/step8" in r.headers.get("Location",""), r.headers.get("Location"))

# ensure BOQ hierarchy schema exists (harness DB is fresh)
try:
    from new_boq_hierarchy_schema import ensure_boq_hierarchy_schema
    ensure_boq_hierarchy_schema(web_app.get_db)
    print("BOQ hierarchy schema ensured")
except Exception as e:
    print("WARN could not ensure BOQ schema:", e)

# --- Phase 4: Step 8 finance ---
r = c.get(f"/large-scale-solar/{pid}/step8")
check("step8 GET 200", r.status_code == 200, r.status_code)
check("step8 shows CAPEX section", b"CAPEX" in r.data)
check("step8 no-linked-BOQ note", b"No linked BOQ yet" in r.data)
r = c.post(f"/large-scale-solar/{pid}/step8", data={
    "_csrf":"tok","tariff_local_per_kwh":"1.5","fx_local_per_usd":"12",
    "revenue_model":"ppa","project_life_yr":"25","discount_rate_pct":"10",
    "debt_ratio_pct":"70","debt_rate_pct":"10","debt_tenor_yr":"12","tax_rate_pct":"25",
    "tariff_escalation_pct":"2","opex_escalation_pct":"3","annual_degradation_pct":"0.5",
    "monte_carlo_runs":"50","recompute_only":"1"}, follow_redirects=False)
check("step8 recompute stays 200", r.status_code == 200, r.status_code)
check("step8 shows model results", b"Model results" in r.data)
with web_app.get_db() as db:
    fc = json.loads(db.execute("SELECT finance_config FROM capital_investment_projects WHERE id=?", (pid,)).fetchone()[0])
comp = fc.get("computed", {})
check("step8 NPV computed", "npv_local" in comp, list(comp)[:5])
check("step8 total CAPEX > 0", (comp.get("total_capex_local") or 0) > 0, comp.get("total_capex_local"))
check("step8 IRR present", "irr_pct" in comp)
check("step8 recon present (0 items)", comp.get("boq_reconciliation",{}).get("n_items") == 0, comp.get("boq_reconciliation"))
check("step8 monte carlo ran", (comp.get("monte_carlo") or {}).get("runs") == 50, (comp.get("monte_carlo") or {}).get("runs"))
# invalid revenue_model falls back
r = c.post(f"/large-scale-solar/{pid}/step8", data={"_csrf":"tok","revenue_model":"BOGUS","monte_carlo_runs":"0","recompute_only":"1"}, follow_redirects=False)
with web_app.get_db() as db:
    fc2 = json.loads(db.execute("SELECT finance_config FROM capital_investment_projects WHERE id=?", (pid,)).fetchone()[0])
check("step8 invalid revenue_model -> ppa", fc2.get("revenue_model") == "ppa", fc2.get("revenue_model"))
# save -> step9 now built -> chains to step9
r = c.post(f"/large-scale-solar/{pid}/step8", data={"_csrf":"tok","monte_carlo_runs":"0"}, follow_redirects=False)
check("step8 save -> step9", r.status_code==302 and "/step9" in r.headers.get("Location",""), r.headers.get("Location"))

# --- Phase 5: Step 9 BOQ (auto-generate linked BOQ, reuse standard engine) ---
r = c.get(f"/large-scale-solar/{pid}/step9")
check("step9 GET 200", r.status_code == 200, r.status_code)
check("step9 lists planned buildings", b"Control Room" in r.data and b"Operations" in r.data)
check("step9 shows Generate button", b"Generate linked BOQ" in r.data)
r = c.post(f"/large-scale-solar/{pid}/step9", data={"_csrf":"tok"}, follow_redirects=False)
check("step9 generate redirects to overview", r.status_code==302 and r.headers.get("Location","").rstrip("/").endswith(f"/large-scale-solar/{pid}"), r.headers.get("Location"))
with web_app.get_db() as db:
    bpid = db.execute("SELECT boq_project_id FROM capital_investment_projects WHERE id=?", (pid,)).fetchone()[0]
check("step9 linked boq_project_id set", bool(bpid), bpid)
if bpid:
    with web_app.get_db() as db:
        bp = db.execute("SELECT services_csv, project_type FROM boq_projects WHERE id=?", (bpid,)).fetchone()
        nbuild = db.execute("SELECT COUNT(*) FROM boq_buildings WHERE project_id=?", (bpid,)).fetchone()[0]
        nfloor = db.execute("SELECT COUNT(*) FROM boq_floors WHERE project_id=?", (bpid,)).fetchone()[0]
        nitems = db.execute("SELECT COUNT(*) FROM boq_floor_items WHERE project_id=? AND source_type='capital_autobuild'", (bpid,)).fetchone()[0]
        subtypes = [r2[0] for r2 in db.execute("SELECT purpose_subtype FROM boq_buildings WHERE project_id=?", (bpid,)).fetchall()]
        nlinks = db.execute("SELECT COUNT(*) FROM capital_investment_boq_links WHERE capital_investment_project_id=?", (pid,)).fetchone()[0]
    check("step9 boq_projects services_csv non-empty", bool((bp[0] or "").strip()), bp[0])
    check("step9 boq_projects type=capital_facilities", bp[1] == "capital_facilities", bp[1])
    check("step9 2 buildings created", nbuild == 2, nbuild)
    check("step9 2 floors created", nfloor == 2, nfloor)
    check("step9 purpose_subtype = building codes", sorted(subtypes) == ["control_room","om_building"], subtypes)
    check("step9 autobuild items > 0 (source=capital_autobuild)", nitems > 0, nitems)
    # 2 facility links + 1 solar_farm link (two-BOQ split, 2026-07-03)
    check("step9 link rows created (2 facility + 1 solar)", nlinks == 3, nlinks)
# idempotent re-POST -> this project's link is unchanged, no new buildings
r = c.post(f"/large-scale-solar/{pid}/step9", data={"_csrf":"tok"}, follow_redirects=False)
with web_app.get_db() as db:
    bpid2 = db.execute("SELECT boq_project_id FROM capital_investment_projects WHERE id=?", (pid,)).fetchone()[0]
    nbuild2 = db.execute("SELECT COUNT(*) FROM boq_buildings WHERE project_id=?", (bpid2,)).fetchone()[0]
check("step9 idempotent: same linked BOQ id", bpid2 == bpid, (bpid, bpid2))
check("step9 idempotent: no extra buildings", nbuild2 == 2, nbuild2)
# GET step9 now shows linked state
r = c.get(f"/large-scale-solar/{pid}/step9")
check("step9 GET shows linked state", b"BOQ linked" in r.data)

# --- Phase 5 x 4: Step 8 reconciliation now sees the linked BOQ actuals ---
r = c.get(f"/large-scale-solar/{pid}/step8")
check("step8 reconciliation now has BOQ items", b"BOQ actual" in r.data and b"No linked BOQ yet" not in r.data)
# recompute finance so reconciliation numbers refresh from the linked BOQ
r = c.post(f"/large-scale-solar/{pid}/step8", data={"_csrf":"tok","monte_carlo_runs":"0","recompute_only":"1"}, follow_redirects=False)
with web_app.get_db() as db:
    fc3 = json.loads(db.execute("SELECT finance_config FROM capital_investment_projects WHERE id=?", (pid,)).fetchone()[0])
recon3 = fc3.get("computed",{}).get("boq_reconciliation",{})
check("step8 recon n_items > 0 after BOQ", (recon3.get("n_items") or 0) > 0, recon3.get("n_items"))
check("step8 recon boq_actual_usd > 0", (recon3.get("boq_actual_usd") or 0) > 0, recon3.get("boq_actual_usd"))

# --- Phase 6: Step 10 marketplace (curated links out) ---
r = c.get(f"/large-scale-solar/{pid}/step10")
check("step10 GET 200", r.status_code == 200, r.status_code)
check("step10 shows PV Modules (kwp set)", b"PV Modules" in r.data)
check("step10 shows Fire Alarm (fire_alarm service)", b"Fire Alarm" in r.data)
check("step10 shows SCADA (scada tech)", b"SCADA" in r.data)
check("step10 links to /marketplace?cat=", b"/marketplace?cat=" in r.data)
check("step10 links to full marketplace", b"Open full Marketplace" in r.data)

# --- Phase 7: Step 11 CRM opportunity + Step 12 pipeline ---
r = c.get(f"/large-scale-solar/{pid}/step11")
check("step11 GET 200", r.status_code == 200, r.status_code)
check("step11 preview shows capacity 25 MWp", b"25.0 MWp" in r.data)
check("step11 preview shows NPV (finance done)", b"NPV" in r.data)
# create opportunity
r = c.post(f"/large-scale-solar/{pid}/step11", data={"_csrf":"tok","action":"sync","investor":"Acme Fund","pipeline_notes":"hot"}, follow_redirects=False)
check("step11 create redirects to step11", r.status_code==302 and "/step11" in r.headers.get("Location",""), r.headers.get("Location"))
with web_app.get_db() as db:
    opp = db.execute("SELECT id, stage, capex_local, npv_local, investor, capacity_mwp FROM capital_investment_opportunities WHERE capital_investment_project_id=? AND user_id=?", (pid, uid)).fetchone()
check("step11 opportunity created", opp is not None)
if opp:
    check("step11 opp stage=lead", opp[1] == "lead", opp[1])
    check("step11 opp capex_local > 0", (opp[2] or 0) > 0, opp[2])
    check("step11 opp npv set", opp[3] is not None)
    check("step11 opp investor override kept", opp[4] == "Acme Fund", opp[4])
    check("step11 opp capacity 25 MWp", abs((opp[5] or 0)-25.0)<0.01, opp[5])
# pipeline lead mirror (Codex #4) - only assert if the platform table exists
try:
    with web_app.get_db() as db:
        nlead = db.execute("SELECT COUNT(*) FROM assessment_requests WHERE source=?", ("generation_station_step11",)).fetchone()[0]
    check("step11 mirrored lead into pipeline (Codex #4)", nlead >= 1, nlead)
except Exception as e:
    print("SKIP pipeline-lead mirror check (no assessment_requests table):", str(e)[:60])
# step11 GET now shows saved
r = c.get(f"/large-scale-solar/{pid}/step11")
check("step11 GET shows Saved badge", b"Saved" in r.data)
# step12 pipeline
r = c.get(f"/large-scale-solar/{pid}/step12")
check("step12 GET 200", r.status_code == 200, r.status_code)
check("step12 shows stages", b"Feasibility" in r.data and b"Financial Model" in r.data)
r = c.post(f"/large-scale-solar/{pid}/step12", data={"_csrf":"tok","stage":"feasibility"}, follow_redirects=False)
check("step12 stage update redirects", r.status_code==302, r.status_code)
with web_app.get_db() as db:
    o2 = db.execute("SELECT stage, stage_history FROM capital_investment_opportunities WHERE capital_investment_project_id=? AND user_id=?", (pid, uid)).fetchone()
check("step12 stage now feasibility", o2[0] == "feasibility", o2[0])
hist = json.loads(o2[1] or "[]")
check("step12 stage_history has 1 entry", len(hist) == 1 and hist[0].get("to")=="feasibility", hist)
# invalid stage rejected
r = c.post(f"/large-scale-solar/{pid}/step12", data={"_csrf":"tok","stage":"BOGUS"}, follow_redirects=False)
with web_app.get_db() as db:
    o3 = db.execute("SELECT stage FROM capital_investment_opportunities WHERE capital_investment_project_id=? AND user_id=?", (pid, uid)).fetchone()[0]
check("step12 invalid stage ignored (still feasibility)", o3 == "feasibility", o3)

# --- Phase 8: Step 13 reports (all 13 downloadable PDFs) ---
r = c.get(f"/large-scale-solar/{pid}/step13")
check("step13 GET 200", r.status_code == 200, r.status_code)
check("step13 lists Executive Summary", b"Executive Summary" in r.data)
check("step13 lists all 13 report links", r.data.count(b"/report/") >= 13, r.data.count(b"/report/"))
REPORT_KEYS = ["executive","technical","financial","bankability","investment_memo","risk",
               "boq","bom","rfq","construction_est","maintenance","monitoring","ops_manual"]
pdf_ok = 0
for rk in REPORT_KEYS:
    rr = c.get(f"/large-scale-solar/{pid}/report/{rk}.pdf")
    ok = (rr.status_code == 200 and rr.headers.get("Content-Type")=="application/pdf"
          and rr.data[:4] == b"%PDF" and len(rr.data) > 800)
    check(f"report PDF '{rk}' downloads (valid %PDF)", ok, f"{rr.status_code} {rr.headers.get('Content-Type')} {len(rr.data)}B")
    if ok: pdf_ok += 1
check("ALL 13 report PDFs render", pdf_ok == 13, pdf_ok)
# unknown report key -> 404
rr = c.get(f"/large-scale-solar/{pid}/report/bogus.pdf")
check("unknown report key -> 404", rr.status_code == 404, rr.status_code)
# BOQ report carries real linked-BOQ totals (source_type items exist)
rr = c.get(f"/large-scale-solar/{pid}/report/boq.pdf")
check("boq report is a valid PDF with content", rr.data[:4]==b"%PDF" and len(rr.data) > 1000, len(rr.data))

# --- Phase 10: Step 14 AI agents ---
r = c.get(f"/large-scale-solar/{pid}/step14")
check("step14 GET 200", r.status_code == 200, r.status_code)
check("step14 shows Run all agents", b"Run all agents" in r.data)
r = c.post(f"/large-scale-solar/{pid}/step14", data={"_csrf":"tok","agent":"all"}, follow_redirects=False)
check("step14 run-all redirects", r.status_code==302, r.status_code)
with web_app.get_db() as db:
    nruns = db.execute("SELECT COUNT(DISTINCT agent_code) FROM capital_investment_agent_runs WHERE project_id=?", (pid,)).fetchone()[0]
    hasrev = db.execute("SELECT COUNT(*) FROM capital_investment_agent_runs WHERE project_id=? AND agent_code='reviewer'", (pid,)).fetchone()[0]
check("step14 ran >=14 distinct agents", nruns >= 14, nruns)
check("step14 reviewer run persisted", hasrev >= 1, hasrev)
r = c.get(f"/large-scale-solar/{pid}/step14")
check("step14 GET shows aggregate readiness", b"aggregate readiness" in r.data)
check("step14 agents scored (not all dashes)", r.data.count(b"bg-success")+r.data.count(b"bg-warning")+r.data.count(b"bg-danger") >= 5)
# single agent re-run
r = c.post(f"/large-scale-solar/{pid}/step14", data={"_csrf":"tok","agent":"financial"}, follow_redirects=False)
check("step14 single-agent run redirects", r.status_code==302, r.status_code)
# unknown agent rejected
r = c.post(f"/large-scale-solar/{pid}/step14", data={"_csrf":"tok","agent":"nope"}, follow_redirects=False)
check("step14 unknown agent handled", r.status_code==302, r.status_code)

# --- Phase 9: Digital Twin ---
r = c.get(f"/large-scale-solar/{pid}/digital-twin")
check("digital-twin GET 200", r.status_code == 200, r.status_code)
check("digital-twin loads vendored three.js", b"three-r147-umd/three.min.js" in r.data)
check("digital-twin has 3D DIGITAL TWIN badge", b"3D DIGITAL TWIN" in r.data)
check("digital-twin embeds scene JSON (pv rows)", b"pv" in r.data)

# --- bolt-on links on overview ---
r = c.get(f"/large-scale-solar/{pid}")
check("overview shows Digital Twin link", b"3D Digital Twin" in r.data)
check("overview shows Regulatory link", b"Development" in r.data)
check("overview: step14 marks done (agents ran)", r.data.count(b"bi-check-circle-fill") >= 12)

# Wizard progress reflects completion after all saves
r = c.get(f"/large-scale-solar/{pid}")
check("overview 200 post-walk", r.status_code == 200, r.status_code)
check("overview: step9 marks done", b"bi-check" in r.data)
check("overview: step11/12 marked done (opp+pipeline)", r.data.count(b"bi-check-circle-fill") >= 10)

# reload persistence: step3 GET should show saved terrain selected
r = c.get(f"/large-scale-solar/{pid}/step3")
check("step3 reload keeps terrain=flat selected",
      b'value="flat" selected' in r.data or b'value="flat"  selected' in r.data)

print("\n=== Phase 2:", "ALL PASS" if not fails else f"{len(fails)} FAIL: {fails}", "===")
sys.exit(1 if fails else 0)
