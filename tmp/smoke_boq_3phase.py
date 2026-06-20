"""End-to-end smoke test for Phase 1+2+3 of the BOQ rework.

Walks:
  - Phase 1: marketplace BOQ — client-clean default, ?view=internal exposes
    build-up, /boms/<id>/rate-buildup renders, exports respect include_buildup.
  - Phase 2: + Add Library Item modal posts to /boms/<id>/add-library-item.
  - Phase 3: BOQ project hierarchy — create project, add building with
    purpose wizard, auto-floors, add floor item, summary + relations.

Run from repo root:
    python tmp/smoke_boq_3phase.py
"""
from __future__ import annotations

import os
import sys
import tempfile

# 1) Sandbox the DB. web_app.DB_PATH is hard-coded so we monkey-patch it
#    BEFORE calling init_db. SOLARPRO_*_PASSWORD must be set before init_db
#    runs since the seed reads them then.
TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
TMP_DB.close()
os.environ["SOLARPRO_ADMIN_PASSWORD"] = "smoke-admin-pwd-2026"
os.environ["SOLARPRO_OWNER_PASSWORD"] = "smoke-owner-pwd-2026"
os.environ["SECRET_KEY"] = "smoke-secret-2026"
for k in ("BREVO_API_KEY","RESEND_API_KEY","ANTHROPIC_API_KEY","OPENROUTER_API_KEY","DATABASE_URL"):
    os.environ.pop(k, None)

# 2) Import the app, override DB_PATH, then init_db() + bootstrap marketplace.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import web_app  # noqa: E402
web_app.DB_PATH = TMP_DB.name
web_app.init_db()
web_app._ensure_marketplace_tables()
web_app._ensure_bom_tables()
web_app._ensure_bom_rates_table()
# Backfill columns added by other code paths we don't hit in the smoke test.
with web_app.get_db() as _c:
    for _stmt in [
        "ALTER TABLE equipment_catalog ADD COLUMN is_verified INTEGER DEFAULT 1",
        "ALTER TABLE suppliers          ADD COLUMN user_id INTEGER DEFAULT 0",
        "ALTER TABLE suppliers          ADD COLUMN is_verified INTEGER DEFAULT 1",
        "ALTER TABLE users              ADD COLUMN role TEXT DEFAULT ''",
    ]:
        try: _c.execute(_stmt)
        except Exception: pass
# Phase 1/2/3 schema migration we added.
from new_boq_hierarchy_schema import ensure_boq_hierarchy_schema  # noqa: E402
ensure_boq_hierarchy_schema(web_app.get_db)
app = web_app.app

app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False  # we send the _csrf form field explicitly

OK = []
FAIL = []

def check(label, cond, hint=""):
    (OK if cond else FAIL).append((label, hint))
    print(f"{'PASS' if cond else 'FAIL'}  {label}{(' — '+hint) if hint and not cond else ''}")

def login(client, username, password):
    """Log in via /login. Pulls CSRF from the form first."""
    r = client.get("/login")
    assert r.status_code == 200, f"login GET {r.status_code}"
    import re
    m = re.search(rb'name="_csrf"\s+value="([^"]+)"', r.data)
    token = m.group(1).decode() if m else ""
    r = client.post("/login", data={
        "username": username, "password": password, "_csrf": token,
    }, follow_redirects=False)
    return r

def get_csrf(client, path):
    r = client.get(path)
    import re
    m = re.search(rb'name="_csrf"\s+value="([^"]+)"', r.data)
    return m.group(1).decode() if m else ""


with app.test_client() as c:
    # ── PHASE 0 — login ──────────────────────────────────────────────────
    r = login(c, "marc667us", "smoke-owner-pwd-2026")
    check("login marc667us (302)", r.status_code in (302, 303), f"got {r.status_code}")

    # ── PHASE 1 — marketplace BOQ ────────────────────────────────────────
    csrf = get_csrf(c, "/boms/new")
    r = c.post("/boms/new", data={"_csrf": csrf,
                                  "title": "Smoke BOM 1",
                                  "project_name": "Smoke Project",
                                  "client_name": "Smoke Client"}, follow_redirects=True)
    check("create BOM (200)", r.status_code == 200)

    # Find new bom_id.
    from web_app import get_db
    with get_db() as cur:
        row = cur.execute("SELECT id FROM marketplace_boms ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        # Debug: dump last 500 bytes of the response that came back.
        body = r.data.decode("utf-8", "replace")
        snippet = body[body.find("<body"):body.find("<body")+1500] if "<body" in body else body[:500]
        print("DEBUG: no BOM created — response snippet:", snippet[:600])
        sys.exit(2)
    bom_id = int(row["id"])
    check("BOM created with id", bom_id > 0, f"bom_id={bom_id}")

    # Add a plain BOM item (existing flow).
    csrf = get_csrf(c, f"/boms/{bom_id}")
    r = c.post(f"/boms/{bom_id}/items/add", data={"_csrf": csrf,
                                                  "name": "Test panel",
                                                  "qty": "10",
                                                  "unit": "No.",
                                                  "unit_price_override": "100"},
               follow_redirects=False)
    check("add line item (302)", r.status_code in (302, 303))

    # Default BOQ view = client-clean: must NOT contain "Basic Rate" or "Total Rate" headers.
    r = c.get(f"/boms/{bom_id}/boq")
    body = r.data.decode("utf-8", "replace")
    check("BOQ default = client-clean (no Basic Rate header)", "Basic Rate" not in body)
    check("BOQ default = client-clean (no Total Rate header)", "Total Rate" not in body)
    check("BOQ default has Remarks column",  "Remarks" in body)

    # Internal view exposes the build-up.
    r = c.get(f"/boms/{bom_id}/boq?view=internal")
    body = r.data.decode("utf-8", "replace")
    check("BOQ ?view=internal exposes Basic Price", "Basic Price" in body)
    check("BOQ ?view=internal exposes Final Rate",   "Final Rate" in body)
    check("BOQ ?view=internal has the red lock notice", "Internal document" in body)

    # /boms/<id>/rate-buildup renders.
    r = c.get(f"/boms/{bom_id}/rate-buildup")
    check("/rate-buildup renders (200)", r.status_code == 200)
    check("/rate-buildup exposes build-up cols", "Final Rate" in r.data.decode("utf-8","replace"))

    # Excel export — default = client-clean (column 6 = Amount; no "Basic" header).
    r = c.get(f"/boms/{bom_id}/boq.xlsx")
    check("xlsx default OK (200)", r.status_code == 200)
    check("xlsx default mimetype xlsx", "spreadsheetml" in (r.mimetype or ""))

    # Excel export with build-up — should include "Project Rate Build-Up" worksheet.
    r = c.get(f"/boms/{bom_id}/boq.xlsx?include_buildup=1")
    check("xlsx +build-up (200)", r.status_code == 200)
    import io as _io, openpyxl as _xl
    try:
        _wb = _xl.load_workbook(_io.BytesIO(r.data), read_only=True)
        sheet_names = _wb.sheetnames
    except Exception as _e:
        sheet_names = []
    check("xlsx include_buildup adds Rate Build-Up sheet",
          "Project Rate Build-Up" in sheet_names,
          f"sheets={sheet_names}")

    # PDF export — default contains "Rate" header, NOT "Basic Rate".
    r = c.get(f"/boms/{bom_id}/boq.pdf")
    check("pdf default OK (200)", r.status_code == 200)

    # ── PHASE 2 — + Add Library Item modal POST ──────────────────────────
    csrf = get_csrf(c, f"/boms/{bom_id}")
    r = c.post(f"/boms/{bom_id}/add-library-item", data={
        "_csrf": csrf,
        "description": "Bespoke 240mm² XLPE cable",
        "section": "sub_feeders",
        "specification": "Cu, 4C, 0.6/1kV, XLPE/SWA/PVC, BS 6724",
        "unit": "m",
        "qty": "50",
        "brand": "Nexans",
        "basic_price": "100",
        "supply_rate": "",       # defaults to basic per spec
        "install_rate": "",      # defaults to 0
        "overhead_pct": "10",
        "profit_pct": "10",
        "contingency_pct": "5",
        "vat_pct": "12.5",
        "remarks": "Spec to be confirmed on site",
        "save_option": "submit_to_master_library",
    }, follow_redirects=False)
    check("POST /add-library-item (302)", r.status_code in (302, 303),
          f"got {r.status_code} body={r.data[:200]!r}")

    # Verify the BOM line was created with rate ~= 100 * (1+0.375) = 137.5
    with get_db() as cur:
        rows = cur.execute(
            "SELECT custom_name, final_built_up_rate FROM marketplace_bom_items "
            "WHERE bom_id=? AND custom_name LIKE 'Bespoke%'", (bom_id,)
        ).fetchall()
    check("library item added to BOM",  len(rows) == 1, f"rows={len(rows)}")
    if rows:
        rate = float(rows[0]["final_built_up_rate"] or 0)
        check("rate built per spec (100*1.375 ~ 137.5)", abs(rate - 137.5) < 0.01,
              f"rate={rate}")

    # Verify equipment_catalog has a pending_library_review row.
    with get_db() as cur:
        prows = cur.execute(
            "SELECT id, name, approval_status FROM equipment_catalog "
            "WHERE approval_status='pending_library_review'"
        ).fetchall()
    check("equipment_catalog pending row created", len(prows) == 1)

    # ── PHASE 3 — BOQ project hierarchy ──────────────────────────────────
    csrf = get_csrf(c, "/boq-projects/new")
    r = c.post("/boq-projects/new", data={
        "_csrf": csrf,
        "project_name": "Smoke BOQ Project",
        "client_name": "Smoke Client Ltd",
        "location": "Accra, Ghana",
        "project_type": "single_building",
    }, follow_redirects=False)
    check("create BOQ project (302)", r.status_code in (302, 303))

    with get_db() as cur:
        prow = cur.execute("SELECT id FROM boq_projects ORDER BY id DESC LIMIT 1").fetchone()
    pid = int(prow["id"])

    # Building wizard — commercial / office, 3 floors + basement + roof.
    csrf = get_csrf(c, f"/boq-projects/{pid}/buildings/new")
    r = c.post(f"/boq-projects/{pid}/buildings/new", data={
        "_csrf": csrf,
        "building_name": "Block A",
        "building_code": "BLK-A",
        "primary_purpose": "commercial",
        "purpose_subtype": "Office",
        "building_area": "1200",
        "number_of_floors": "3",
        "basement_included": "on",
        "roof_level_included": "on",
    }, follow_redirects=False)
    check("create building w/ commercial purpose (302)", r.status_code in (302, 303))

    with get_db() as cur:
        brow = cur.execute("SELECT id FROM boq_buildings WHERE project_id=?", (pid,)).fetchone()
    bid = int(brow["id"])

    # Floors should be auto-created: basement, ground, first, second, roof = 5 floors.
    with get_db() as cur:
        floors = cur.execute("SELECT * FROM boq_floors WHERE building_id=? ORDER BY floor_level", (bid,)).fetchall()
    check("auto-floors created (5: basement + ground + 1st + 2nd + roof)", len(floors) == 5,
          f"got {len(floors)}")
    floor_names = [f["floor_name"] for f in floors]
    check("Basement included", "Basement" in floor_names)
    check("Ground Floor included", "Ground Floor" in floor_names)
    check("Roof Level included", "Roof Level" in floor_names)

    # Add a floor item to Ground Floor.
    ground = [f for f in floors if f["floor_name"] == "Ground Floor"][0]
    fid = int(ground["id"])
    csrf = get_csrf(c, f"/boq-projects/{pid}/buildings/{bid}/floors/{fid}")
    r = c.post(f"/boq-projects/{pid}/buildings/{bid}/floors/{fid}/items", data={
        "_csrf": csrf,
        "description": "Wiring of socket point — 13A",
        "section": "wiring",
        "specification": "PVC conduit + 4mm² wires, BS 7671",
        "unit": "point",
        "qty": "24",
        "basic_price": "75",
        "overhead_pct": "10",
        "profit_pct": "10",
        "contingency_pct": "5",
        "vat_pct": "12.5",
        "save_option": "current_boq_only",
        "remarks": "First floor type B",
    }, follow_redirects=False)
    check("add floor item (302)", r.status_code in (302, 303))

    # Verify FK relations land in all tables and rate is computed.
    with get_db() as cur:
        items = cur.execute(
            "SELECT i.id, i.final_built_up_rate, i.total_amount, "
            "       b.id AS bid_link, p.id AS pid_link, f.id AS fid_link, "
            "       rb.basic_price, rb.overhead_pct, rb.vat_pct "
            "FROM boq_floor_items i "
            "JOIN boq_buildings b ON b.id=i.building_id "
            "JOIN boq_projects p ON p.id=i.project_id "
            "JOIN boq_floors f   ON f.id=i.floor_id "
            "JOIN boq_floor_rate_buildup rb ON rb.floor_item_id=i.id "
            "WHERE i.project_id=?", (pid,)
        ).fetchall()
    check("FK joins yield 1 row", len(items) == 1)
    if items:
        it = items[0]
        check("rate=75*1.375=103.125", abs(float(it["final_built_up_rate"]) - 103.125) < 0.01)
        check("total=24*103.125=2475", abs(float(it["total_amount"]) - 2475.0) < 0.01)
        check("rate-buildup basic_price stored", float(it["basic_price"]) == 75.0)

    # Project BOQ — default client-clean, no build-up columns.
    r = c.get(f"/boq-projects/{pid}/boq")
    body = r.data.decode("utf-8", "replace")
    check("project BOQ default client-clean (no '+Profit' header)", "+Profit" not in body)
    check("project BOQ default shows Remarks", "Remarks" in body)
    check("project BOQ default shows the item", "Wiring of socket" in body)

    # Project BOQ internal view exposes build-up.
    r = c.get(f"/boq-projects/{pid}/boq?view=internal")
    body = r.data.decode("utf-8", "replace")
    check("project BOQ internal exposes '+Profit'", "+Profit" in body)
    check("project BOQ internal exposes Final Rate", "Final Rate" in body)

    # Summary page — must include the building and floor.
    r = c.get(f"/boq-projects/{pid}/summary")
    body = r.data.decode("utf-8", "replace")
    check("summary lists Block A", "Block A" in body)
    check("summary lists Ground Floor", "Ground Floor" in body)
    check("summary lists Roof Level", "Roof Level" in body)
    check("summary shows 2475", "2475" in body or "2,475" in body)

    # Audit log should have rows.
    with get_db() as cur:
        n_audit = cur.execute("SELECT COUNT(*) AS n FROM boq_audit_log").fetchone()["n"]
    check("audit log has rows", n_audit > 0, f"n={n_audit}")

print()
print(f"PASS: {len(OK)}  FAIL: {len(FAIL)}")
for label, hint in FAIL:
    print(f"  FAIL  {label} — {hint}")

# Cleanup temp DB.
try:
    os.unlink(TMP_DB.name)
except Exception:
    pass

sys.exit(0 if not FAIL else 1)
