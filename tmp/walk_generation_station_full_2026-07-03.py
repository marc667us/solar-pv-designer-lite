"""Full end-to-end LOCAL walk of the Generation Station (PV Capital Investment)
14-step wizard + reports + digital twin + regulatory.

Purpose: reproduce and CATALOG the faults / hiccups the owner reported on live.
Drives the real Flask handlers via test_client with an injected admin session
(bypassing the KC OIDC dance), against a throwaway SQLite DB.

For every surface it records the HTTP status and flags:
  * any 5xx (a genuine fault/hiccup)
  * any redirect back to the SAME step (a silent "did nothing" hiccup)
  * Step 9: whether priced BOQ cells were actually created
  * report PDFs: whether real PDF bytes came back

Run:  python tmp/walk_generation_station_full_2026-07-03.py
"""
from __future__ import annotations
import os, sys, tempfile, re

_tmp_db = tempfile.NamedTemporaryFile(prefix="solarpro_ci_walk_", suffix=".db", delete=False)
_tmp_db.close()
os.environ["DB_PATH"] = _tmp_db.name
os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "test-admin-pass-1234")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "test-owner-pass-1234")
os.environ.setdefault("SECRET_KEY", "test-secret-key-1234567890abcdef")
os.environ["KEYCLOAK_ENABLED"] = "false"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

import web_app  # noqa: E402
import new_capital_investment_routes as ci  # noqa: E402

app = web_app.app
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False
try:
    web_app.init_db()
except Exception:
    pass

FAULTS: list[str] = []
def fault(msg: str):
    FAULTS.append(msg)
    print(f"  [FAULT] {msg}")
def ok(msg: str):
    print(f"  [ok]    {msg}")

def _login_admin(client):
    with web_app.get_db() as c:
        row = c.execute("SELECT id FROM users WHERE username=?", ("admin",)).fetchone()
    with client.session_transaction() as s:
        s["user_id"] = row[0]
        s["username"] = "admin"
        s["_csrf"] = "walktok"

def _first(codes):
    return list(codes)[0] if codes else ""

def _post(client, url, data, label, allow_same=False):
    data = dict(data); data.setdefault("_csrf", "walktok")
    r = client.post(url, data=data, follow_redirects=False)
    if r.status_code >= 500:
        fault(f"{label}: POST {url} -> {r.status_code} (server error)")
        return r
    loc = r.headers.get("Location", "")
    if not allow_same and url.rstrip("/") == loc.rstrip("/"):
        fault(f"{label}: POST {url} redirected back to itself (silent no-op) loc={loc}")
    else:
        ok(f"{label}: POST -> {r.status_code} loc={loc[-48:]}")
    return r

def _get(client, url, label, expect=200):
    r = client.get(url, follow_redirects=False)
    if r.status_code >= 500:
        fault(f"{label}: GET {url} -> {r.status_code} (server error)")
    elif r.status_code != expect and r.status_code not in (200, 302):
        fault(f"{label}: GET {url} -> {r.status_code} (expected {expect})")
    else:
        ok(f"{label}: GET -> {r.status_code}")
    return r

def run():
    print(f"=== Generation Station FULL walk (local SQLite {_tmp_db.name}) ===")
    with app.test_client() as client:
        _login_admin(client)

        # Step 1 - create project
        r = _post(client, "/large-scale-solar/new", {
            "project_name": "Walk 20 MW Ghana Solar Farm",
            "client_name": "Walk Client", "investor": "Walk Investor",
            "developer": "Walk Dev", "country": "Ghana", "region": "Greater Accra",
            "district": "Tema", "gps_lat": "5.66", "gps_lon": "-0.02",
            "description": "full walk", "project_status": "concept",
            "target_cod": "2028-06", "target_mwp": "20.0", "design_standard": "IEC",
            "currency": "GHS", "tax_regime": "standard", "project_type": "utility_scale",
        }, "step1/new")
        loc = r.headers.get("Location", "")
        m = re.search(r"/large-scale-solar/(\d+)", loc)
        if not m:
            fault(f"step1: no project id in redirect ({loc}) - ABORTING walk")
            return
        pid = int(m.group(1))
        ok(f"created project pid={pid}")

        base = f"/large-scale-solar/{pid}"

        # Step 2 - project type
        _get(client, f"{base}/step2", "step2")
        _post(client, f"{base}/step2", {"project_type": _first(ci.PROJECT_TYPE_CODES)}, "step2")

        # Step 3 - site
        _get(client, f"{base}/step3", "step3")
        _post(client, f"{base}/step3", {"land_area_ha": "40", "grid_distance_km": "3"}, "step3")

        # Step 4 - facility (choose several buildings incl. control room + O&M + transformer + external)
        _get(client, f"{base}/step4", "step4")
        want = [b for b in ("control_room", "om_building", "transformer_bldg",
                            "security_gate", "battery_room") if b in ci.BUILDING_CODES]
        if not want:
            want = list(ci.BUILDING_CODES)[:3]
        ext = list(ci.EXTERNAL_WORKS_CODES)[:4]
        _post(client, f"{base}/step4", {"buildings": want, "external_works": ext}, "step4")

        # Step 5 - technology
        _get(client, f"{base}/step5", "step5")
        techs = list(ci.TECHNOLOGY_CODES)[:6]
        _post(client, f"{base}/step5", {"technology": techs}, "step5")

        # Step 6 - electrical
        _get(client, f"{base}/step6", "step6")
        svcs = list(ci.ELECTRICAL_SERVICE_CODES)[:5]
        _post(client, f"{base}/step6", {"services": svcs}, "step6")

        # Step 7 - PV (must set kwp so step8 finance can compute)
        _get(client, f"{base}/step7", "step7")
        _post(client, f"{base}/step7", {
            "module_tech": "mono_topcon", "mounting": "fixed_tilt",
            "inverter_type": "central", "battery_chem": "none",
            "kwp": "20000", "module_wp": "550", "dc_ac_ratio": "1.2",
            "tilt_deg": "10", "azimuth_deg": "180", "psh_daily": "5.4",
            "performance_ratio": "0.78", "availability_pct": "98",
            "annual_degradation_pct": "0.5", "project_life_yr": "25",
        }, "step7")

        # Step 8 - finance
        _get(client, f"{base}/step8", "step8")
        _post(client, f"{base}/step8", {
            "tariff_local_per_kwh": "1.5", "fx_local_per_usd": "12",
            "revenue_model": "ppa", "project_life_yr": "25",
            "discount_rate_pct": "10", "debt_ratio_pct": "70",
            "debt_rate_pct": "10", "debt_tenor_yr": "12", "tax_rate_pct": "25",
            "monte_carlo_runs": "50",
        }, "step8")

        # Step 9 - BOQ generate (THE hiccup-prone one)
        _get(client, f"{base}/step9", "step9")
        r9 = _post(client, f"{base}/step9", {}, "step9-generate")
        # verify BOQ rows
        with web_app.get_db() as c:
            prow = c.execute("SELECT boq_project_id FROM capital_investment_projects WHERE id=?", (pid,)).fetchone()
            boq_pid = prow[0] if prow else None
            if not boq_pid:
                fault("step9: boq_project_id NOT set after generate (BOQ did not link)")
            else:
                nb = c.execute("SELECT COUNT(*) FROM boq_buildings WHERE project_id=?", (boq_pid,)).fetchone()[0]
                nf = c.execute("SELECT COUNT(*) FROM boq_floors WHERE project_id=?", (boq_pid,)).fetchone()[0]
                ni = c.execute("SELECT COUNT(*) FROM boq_floor_items WHERE floor_id IN (SELECT id FROM boq_floors WHERE project_id=?)", (boq_pid,)).fetchone()[0]
                svc = c.execute("SELECT services_csv FROM boq_projects WHERE id=?", (boq_pid,)).fetchone()[0]
                if nb == 0: fault(f"step9: 0 boq_buildings created (boq_pid={boq_pid})")
                if nf == 0: fault(f"step9: 0 boq_floors created")
                if ni == 0: fault(f"step9: 0 priced boq_floor_items created (cells did NOT auto-build)")
                if not svc: fault("step9: boq_projects.services_csv is EMPTY")
                ok(f"step9: BOQ linked boq_pid={boq_pid} buildings={nb} floors={nf} cells={ni} services='{(svc or '')[:40]}'")

        # Step 10 - marketplace (GET)
        _get(client, f"{base}/step10", "step10")

        # Step 11 - CRM create opportunity
        _get(client, f"{base}/step11", "step11")
        _post(client, f"{base}/step11", {"action": "sync", "investor": "Walk Investor"}, "step11-create")

        # Step 12 - pipeline advance
        _get(client, f"{base}/step12", "step12")
        stage2 = list(ci.PIPELINE_STAGE_CODES)[1] if len(ci.PIPELINE_STAGE_CODES) > 1 else list(ci.PIPELINE_STAGE_CODES)[0]
        _post(client, f"{base}/step12", {"stage": stage2}, "step12-advance")

        # Step 13 - reports menu + every report PDF
        _get(client, f"{base}/step13", "step13")
        for rk in ci.FULL_REPORT_KEYS:
            r = client.get(f"{base}/report/{rk}.pdf", follow_redirects=False)
            if r.status_code >= 500:
                fault(f"report[{rk}]: {r.status_code} server error")
            elif r.status_code == 302:
                fault(f"report[{rk}]: redirected (PDF build failed) loc={r.headers.get('Location','')[-40:]}")
            elif r.status_code == 200 and r.data[:4] == b"%PDF":
                ok(f"report[{rk}]: real PDF ({len(r.data)} bytes)")
            elif r.status_code == 200:
                fault(f"report[{rk}]: 200 but not PDF bytes (head={r.data[:8]!r})")
            else:
                fault(f"report[{rk}]: unexpected {r.status_code}")

        # Step 14 - agents run all
        _get(client, f"{base}/step14", "step14")
        _post(client, f"{base}/step14", {"agent": "all"}, "step14-runall")

        # Digital twin + json endpoints
        _get(client, f"{base}/digital-twin", "digital-twin")
        _get(client, f"{base}/dt/scene.json", "dt/scene.json")
        _get(client, f"{base}/dt/sun.json?month=6&hour=12", "dt/sun.json")

        # Regulatory
        _get(client, f"{base}/regulatory", "regulatory")
        _post(client, f"{base}/regulatory", {"land_tenure": ""}, "regulatory", allow_same=True)

        # Project overview (should show completion + linked BOQ)
        _get(client, f"{base}", "project-overview")

    print(f"\n=== WALK COMPLETE: {len(FAULTS)} fault(s) ===")
    for f in FAULTS:
        print(f"   - {f}")
    return 1 if FAULTS else 0

if __name__ == "__main__":
    try:
        rc = run()
    finally:
        try: os.unlink(_tmp_db.name)
        except Exception: pass
    sys.exit(rc)
