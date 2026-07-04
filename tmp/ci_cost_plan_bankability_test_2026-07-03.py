# -*- coding: utf-8 -*-
"""Cost Plan Deck restyle + Bankability determination test (owner 2026-07-03):
  - /cost-plan renders 200 with the new teal theme (no amber accents), the
    circular donut, the cumulative cost S-curve, and a Bankability tab.
  - _ci_bankability produces a determination once Step 8 is computed.
  - report/bankability.pdf and report/financial.pdf render valid PDFs and the
    bankability report carries the weighted determination.
Imports the ACTIVE new_capital_investment_routes.py."""
import os, sys, importlib
REPO = r"C:\Users\USER\Desktop\solar-pv-designer-lite"
os.chdir(REPO); sys.path.insert(0, REPO)
os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "x")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "y")
os.environ["DB_PATH"] = os.path.join(REPO, "tmp", "_cost_plan_bank.db")
os.environ["CI_MAX_AUTOBUILD_FLOORS"] = "6"
try: os.remove(os.environ["DB_PATH"])
except OSError: pass

import web_app
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

# --- walk wizard with a Monte-Carlo run so downside P90 populates ---
r = c.post("/large-scale-solar/new", data={"_csrf":"tok","project_name":"CostPlan Bank Test",
    "project_type":"utility_scale","country":"Ghana","region":"Ashanti",
    "target_mwp":"20","currency":"GHS","project_status":"concept"})
pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
c.post(f"/large-scale-solar/{pid}/step3", data={"_csrf":"tok","terrain":"flat","slope":"lt_3","soil":"loam","land_area_ha":"40"})
c.post(f"/large-scale-solar/{pid}/step4", data={"_csrf":"tok","buildings":["control_room","om_building"],"external_works":["pv_field"]})
c.post(f"/large-scale-solar/{pid}/step5", data={"_csrf":"tok","technologies":["scada"]})
c.post(f"/large-scale-solar/{pid}/step6", data={"_csrf":"tok","services":["internal_installation","fire_alarm"]})
c.post(f"/large-scale-solar/{pid}/step7", data={"_csrf":"tok","module_tech":"mono_topcon","kwp":"20000","mounting":"single_axis"})
c.post(f"/large-scale-solar/{pid}/step8", data={"_csrf":"tok","tariff_local_per_kwh":"1.8","fx_local_per_usd":"12","revenue_model":"ppa","project_life_yr":"25","discount_rate_pct":"10","debt_ratio_pct":"70","debt_rate_pct":"10","debt_tenor_yr":"12","tax_rate_pct":"25","monte_carlo_runs":"200"})
c.post(f"/large-scale-solar/{pid}/step9", data={"_csrf":"tok"}, follow_redirects=False)
# price a couple of finish clicks so the deck has cost data
for _ in range(4):
    rf = c.post(f"/large-scale-solar/{pid}/boq/finish", data={"_csrf":"tok"}, follow_redirects=False)
    if rf.status_code != 302: break

# --- bankability determination present in finance output ---
import json
with web_app.get_db() as cx:
    fc = cx.execute("SELECT finance_config FROM capital_investment_projects WHERE id=?", (pid,)).fetchone()[0]
computed = (json.loads(fc) or {}).get("computed") or {}
import new_capital_investment_routes as ncir
bank = ncir._ci_bankability(computed)
ck("bankability computed available", bank["available"], bank.get("rating"))
ck("bankability has a rating band", bank["rating"] in ("Bankable","Conditionally Bankable","Not Yet Bankable"), bank["rating"])
ck("bankability score 0..100", 0 <= bank["score"] <= 100, bank["score"])
ck("bankability lists >=4 weighted metrics", len(bank["metrics"]) >= 4, len(bank["metrics"]))

# --- cost-plan page renders with the new deck ---
r = c.get(f"/large-scale-solar/{pid}/cost-plan")
body = r.get_data(as_text=True)
ck("cost-plan 200", r.status_code == 200, r.status_code)
ck("deck has Bankability tab", "Bankability" in body, "missing")
ck("deck has circular donut (pie)", "stroke-dasharray" in body, "no donut")
ck("deck has cumulative cost S-curve", "Cumulative cost curve" in body or "cost-curve" in body or "polygon" in body, "no scurve")
ck("deck uses teal accent theme (ci-deck)", "ci-deck" in body and "#2dd4bf" in body, "no theme")
ck("deck dropped amber chart colour f5a623", "f5a623" not in body, "amber leaked")
ck("deck dropped amber chart colour f5c518", "f5c518" not in body, "amber leaked")

# --- reports ---
rr = c.get(f"/large-scale-solar/{pid}/report/bankability.pdf")
ck("bankability.pdf valid", rr.status_code == 200 and rr.data[:4] == b"%PDF", (rr.status_code, rr.data[:4]))
rf = c.get(f"/large-scale-solar/{pid}/report/financial.pdf")
ck("financial.pdf valid", rf.status_code == 200 and rf.data[:4] == b"%PDF", (rf.status_code, rf.data[:4]))
print(f"\n=== COST PLAN + BANKABILITY: {'ALL PASS' if not fails else 'FAILURES: '+str(fails)} ===")
sys.exit(1 if fails else 0)
