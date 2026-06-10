"""
Local smoke test for the new superset proposal PDF route.

Builds a minimal valid project structure that exercises every section the new
proposal touches, calls `export_pdf_proposal` through the Flask test client,
and verifies a non-trivial PDF comes back.

Run: python scripts/smoke_proposal_superset.py
"""
from __future__ import annotations
import json, os, sqlite3, sys, tempfile, time

# Use a throwaway DB file so we don't touch local dev state.
DB = tempfile.NamedTemporaryFile(prefix="smoke_proposal_", suffix=".db", delete=False).name
os.environ["DB_PATH"] = DB
os.environ["SECRET_KEY"] = "smoke-secret"
os.environ["SOLARPRO_ADMIN_PASSWORD"] = "SmokeAdmin!2026"
os.environ["SOLARPRO_OWNER_PASSWORD"] = "SmokeOwner!2026"
os.environ.setdefault("DISABLE_RATE_LIMIT", "true")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import web_app  # noqa: E402 — env vars must be set first

PROJECT_DATA = {
    "region": "Greater Accra",
    "country": "Ghana",
    "currency": "GHS",
    "symbol": "GHS",
    "tariff": 1.9688,
    "psh": 5.0,
    "avg_temp": 28,
    "system_type": "off-grid",
    "phase": "single",
    "voltage": 48,
    "autonomy": 1,
    "chemistry": "LiFePO4",
    "fx_usd": 12.5,
    "loads": [
        {"category": "Lighting",   "name": "LED Lights", "wattage": 10,  "quantity": 4, "hours": 6,  "df": 75},
        {"category": "Cooling",    "name": "Fan",        "wattage": 75,  "quantity": 1, "hours": 8,  "df": 65},
        {"category": "Appliances", "name": "Fridge",     "wattage": 150, "quantity": 1, "hours": 24, "df": 50},
    ],
    "mounting_type": "rooftop_pitched",
    "results": {
        "daily_kwh": 4.41,
        "peak_kw": 0.51,
        "div_peak_kw": 0.30,
        "pv_kw": 1.18,
        "num_panels": 3,
        "panel_wp": 400,
        "temp_derating": 0.93,
        "bat_kwh": 5.5,
        "num_bat": 2,
        "unit_bat_kwh": 2.75,
        "chemistry": "LiFePO4",
        "chem_dod": 0.9,
        "chem_cycles": "6,000+",
        "chem_life": "15",
        "inv_kw": 1.5,
        "inv_brand": "Victron / Growatt / Deye",
        "mppt_a": 30,
        "boq_grand": 12450.0,
        "boq_rows": [
            {"no": "1.1", "desc": "PV Panel", "spec": "400 Wp Mono PERC", "qty": 3, "unit": "No.", "basic": 950, "total_r": 1026.0, "amount": 3078.0},
            {"no": "2.1", "desc": "Inverter",  "spec": "1.5 kW Hybrid",   "qty": 1, "unit": "No.", "basic": 2200, "total_r": 2376.0, "amount": 2376.0},
            {"no": "3.1", "desc": "Battery",   "spec": "2.75 kWh LiFePO4", "qty": 2, "unit": "No.", "basic": 2700, "total_r": 2916.0, "amount": 5832.0},
        ],
        "ac_cables": [
            {
                "circuit": "Inverter -> DB", "power_kw": 1.5, "voltage_v": 230, "phase": "single",
                "design_current": 7.5, "length_m": 12, "cable_size_mm2": 4, "core_type": "Cu PVC",
                "cable_capacity": 32, "vd_volts": 1.5, "vd_percent": 0.65, "vd_limit_pct": 1.5,
                "vd_ok": True, "breaker_a": 16, "vd_mv_am": 11.0,
                "install_method": "C", "install_desc": "Clipped direct",
                "ambient_c": 30, "temp_factor": 1.0, "group_factor": 1.0, "i_z_required": 7.9,
            },
        ],
        "economics": {
            "verdict": "APPROVED", "bankability": "BANKABLE",
            "payback": 5.76, "npv": 109269.0, "irr_pct": 25.2, "dscr": 1.85, "roi_pct": 320,
            "annual_kwh": 1610.0, "annual_sav": 3170.0, "om_yr1": 150.0, "net_yr1": 3020.0,
            "cumul_10": 28000.0, "cumul_25": 105000.0,
            "co2_yr": 0.64,
            "equip_local": 12450.0, "install_local": 1867.5, "total_local": 14317.5, "install_rate_pct": 15,
            "loan_amt": 10022.0, "equity": 4295.0, "pmt": 195.0, "annual_pmt": 2340.0,
            "tariff": 1.9688, "breakeven": 6,
            "verdict_reasons": ["Payback < 7 years", "DSCR >= 1.5", "Positive NPV"],
            "bank_reasons": [],
            "cf_rows": [
                {"yr": i, "gross": 3170.0 * (1.08 ** (i-1)), "om": 150.0 * (1.05 ** (i-1)),
                 "net": (3170.0 * (1.08 ** (i-1))) - (150.0 * (1.05 ** (i-1))),
                 "cumul": sum((3170.0 * (1.08 ** (k-1))) - (150.0 * (1.05 ** (k-1))) for k in range(1, i+1))}
                for i in range(1, 26)
            ],
        },
    },
}


def seed_db_and_session():
    web_app.app.config["TESTING"] = True
    web_app.app.config["WTF_CSRF_ENABLED"] = False
    web_app.app.config["SECRET_KEY"] = "smoke-secret"

    # init_db runs at module import; make a paid user + project
    with web_app.get_db() as c:
        # admin seed already happened; bump to paid plan so _paid_only doesn't gate us
        c.execute("UPDATE users SET plan='professional' WHERE username='admin'")
        c.execute(
            "INSERT INTO projects (user_id, name, data_json, created_at) "
            "VALUES ((SELECT id FROM users WHERE username='admin'), ?, ?, ?)",
            ("SmokeProposal", json.dumps(PROJECT_DATA), time.strftime("%Y-%m-%d %H:%M:%S")),
        )
        c.commit()
        pid = c.execute(
            "SELECT id FROM projects WHERE name='SmokeProposal'"
        ).fetchone()[0]
    return pid


def main() -> int:
    pid = seed_db_and_session()
    # Resolve the admin user id we need to drop into the session.
    with web_app.get_db() as c:
        uid = c.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]

    client = web_app.app.test_client()
    # The login route enforces CSRF independently; for a Python-level smoke
    # test we plant the session directly. This is the same mechanism login uses.
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = "admin"

    r = client.get(f"/project/{pid}/report/proposal/pdf")
    ctype = r.headers.get("Content-Type", "")
    size  = len(r.data or b"")
    print(f"proposal PDF: status={r.status_code}  ctype={ctype}  bytes={size:,}")

    if r.status_code != 200:
        # Spit out body so we can see the traceback / redirect
        body = r.data.decode("utf-8", errors="replace") if r.data else ""
        print("--- response body (first 4 KB) ---")
        print(body[:4096])
        return 3
    if size < 8000:
        print("PDF suspiciously small — likely missing sections.")
        return 4
    if not (ctype.startswith("application/pdf") or r.data[:4] == b"%PDF"):
        print("Response is not a PDF.")
        return 5

    # Persist for visual inspection
    out = os.path.join(ROOT, "logs", "smoke_proposal_superset.pdf")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(r.data)
    print(f"saved: {out}")
    print("OK — superset proposal PDF rendered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
