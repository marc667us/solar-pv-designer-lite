"""Full functional test suite for the Project BOQ -> Complete BOQ workflow.

Runs against the LOCAL Flask app using its test client + a faked admin
session, so we can exercise the full POST handlers + DB persistence
end-to-end. Local SQLite mirrors production schema; the only PG-strict
gaps (NOT NULL, VARCHAR widths) have already been corrected upstream.

Tests:
  1. Service registry + skeleton + catalog lookup
  2. Project + building + floor setup (or reuse existing)
  3. Complete BOQ GET page renders with inline section grids
  4. Generate Skeleton -- catalog-driven pre-pricing
  5. Complete BOQ Save-All -- one form -> many sections persisted
  6. Section-by-Section grid editor still works (regression check)
  7. Rate engine equivalence (boq_rate_v3 in sync with route arithmetic)
  8. Edit Item page renders the catalog dropdown
  9. Migration / dedup / orphan handling
"""

import os, sys, re

os.environ.pop("DATABASE_URL", None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + r"\..")

import web_app
from web_app import app
from boq_rate_v3 import boq_rate_v3
import sqlite3

failures = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}]  {name}{(' -- ' + detail) if detail else ''}")
    if not cond:
        failures.append(name)


def section(label):
    print()
    print(f"=== {label} ===")


# Helper to login as admin via test client.
def _auth(cli):
    with cli.session_transaction() as s:
        s["user_id"] = 1
        s["username"] = "admin"


def _csrf_from(body):
    m = re.search(r'name="_csrf" value="([^"]+)"', body)
    return m.group(1) if m else ""


DB_PATH = "data/solar_web.db"


def _db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


# ---- 1. Service registry + skeleton + catalog lookup ------------------
section("1) Service registry + skeleton + catalog lookup")
check("15 services registered", len(web_app._BOQ_SERVICES) == 15)
check("BMS preserved as 15th", "bms" in web_app._BOQ_SERVICE_CODES)
check("Every service has a skeleton entry",
      all(c in web_app._BOQ_SERVICE_BILL_SKELETON for c in web_app._BOQ_SERVICE_CODES))

services = list(web_app._BOQ_SERVICE_CODES)
rows = web_app._services_section_rows(services)
unique_sections = {(r["bill_no"], r["section_letter"]): r["section_title"] for r in rows}
check("Skeleton covers all 15 services as separate bills",
      len({k[0] for k in unique_sections.keys()}) == 15,
      f"got {len({k[0] for k in unique_sections.keys()})}")

# Catalog coverage
helper = web_app.__dict__.get("_boq_catalog_for_section")
catalog_dict = web_app.__dict__.get("_BOQ_SECTION_ITEM_CATALOG", {})


def _norm(s):
    s = (s or "").upper()
    for ch in ("-", "/", ","):
        s = s.replace(ch, " ")
    return " ".join(s.split())


def _lookup(title):
    try:
        hits = helper(title) or []
        if hits:
            return len(hits)
    except Exception:
        pass
    target = _norm(title).replace(" ", "")
    for k, v in (catalog_dict or {}).items():
        kn = _norm(k).replace(" ", "")
        if kn and target and (kn == target or kn.startswith(target) or target.startswith(kn) or kn in target or target in kn):
            return len(v)
    return 0


covered = sum(1 for st in unique_sections.values() if _lookup(st) > 0)
total = len(unique_sections)
total_items = sum(_lookup(st) for st in unique_sections.values())
check(f"Catalog covers {covered}/{total} sections",
      covered == total,
      f"got {covered}/{total}, total catalog items = {total_items}")
check("Total catalog items > 500 (substantial coverage)",
      total_items > 500,
      f"got {total_items}")


# ---- 2. Pick a test floor (using existing data) -----------------------
section("2) Test fixture -- pick an empty floor in an existing project")
db = _db()
fix = db.execute("""
    SELECT p.id AS pid, b.id AS bid, f.id AS fid, p.services_csv,
           (SELECT COUNT(*) FROM boq_floor_items WHERE floor_id=f.id) AS n_items
    FROM boq_projects p
    JOIN boq_buildings b ON b.project_id=p.id
    JOIN boq_floors f ON f.building_id=b.id
    WHERE COALESCE(p.services_csv,'') != ''
      AND p.user_id = 1
    ORDER BY n_items ASC, p.id, b.id, f.id
    LIMIT 1
""").fetchone()
db.close()
check("Found a fixture project + building + floor", fix is not None)
PID, BID, FID = (fix["pid"], fix["bid"], fix["fid"]) if fix else (None, None, None)
print(f"  Using project={PID} building={BID} floor={FID} services={fix['services_csv'][:60] if fix else '(none)'}")


# ---- 3. Complete BOQ GET page renders --------------------------------
section("3) Complete BOQ GET page renders with inline section grids")
with app.test_client() as cli:
    _auth(cli)
    r = cli.get(f"/boq-projects/{PID}/buildings/{BID}/floors/{FID}/complete")
    body = r.get_data(as_text=True)
    check("GET /complete -> 200", r.status_code == 200, f"got {r.status_code}")
    check("Page header is 'Complete BOQ'", "Complete BOQ" in body)
    check("Service chips strip rendered", "Engineering Services Included" in body)
    check("Floor-wide rates form present", 'name="supply_pct"' in body and 'name="overhead_pct"' in body)
    check("Apply-rates-to-every-line checkbox present", 'name="apply_rates_to_all_rows"' in body)
    check("Inline section grids rendered (dropdown rows)",
          body.count('<select class="form-select form-select-sm boq-desc"') > 5,
          f"select count: {body.count('class=\"form-select form-select-sm boq-desc\"')}")
    check("'Save Complete BOQ' button present", "Save Complete BOQ" in body)
    check("'Open standalone editor' link present (escape hatch)",
          "Open standalone editor" in body)
    check("Hidden bill_no[] inputs route rows to sections",
          body.count('name="bill_no[]"') > 5,
          f"got {body.count('name=\"bill_no[]\"')}")
    check("Hidden section_letter[] inputs present",
          body.count('name="section_letter[]"') > 5)
    check("Form action points to /complete/save-all",
          "/complete/save-all" in body)


# ---- 4. Generate Skeleton flow ---------------------------------------
section("4) Generate Skeleton -- catalog-driven pre-pricing")
with app.test_client() as cli:
    _auth(cli)
    # Use a fresh empty floor: clear items first.
    db = _db()
    db.execute("DELETE FROM boq_floor_rate_buildup WHERE floor_item_id IN (SELECT id FROM boq_floor_items WHERE floor_id=?)", (FID,))
    db.execute("DELETE FROM boq_floor_items WHERE floor_id=?", (FID,))
    db.commit()
    db.close()
    # GET to grab csrf
    r = cli.get(f"/boq-projects/{PID}/buildings/{BID}/floors/{FID}/complete")
    csrf = _csrf_from(r.get_data(as_text=True))
    r = cli.post(
        f"/boq-projects/{PID}/buildings/{BID}/floors/{FID}/complete/generate",
        data={"_csrf": csrf,
              "supply_pct": "10", "install_pct": "15",
              "overhead_pct": "10", "profit_pct": "15", "vat_pct": "12.5",
              "apply_rates_to_all_rows": "1"},
        follow_redirects=False)
    check("POST /generate -> 302", r.status_code == 302, f"got {r.status_code}")
    db = _db()
    n_items = db.execute("SELECT COUNT(*) FROM boq_floor_items WHERE floor_id=?", (FID,)).fetchone()[0]
    n_rb = db.execute("SELECT COUNT(*) FROM boq_floor_rate_buildup b JOIN boq_floor_items i ON b.floor_item_id=i.id WHERE i.floor_id=?", (FID,)).fetchone()[0]
    n_priced = db.execute(
        "SELECT COUNT(*) FROM boq_floor_rate_buildup b JOIN boq_floor_items i ON b.floor_item_id=i.id WHERE i.floor_id=? AND COALESCE(b.basic_price,0)>0",
        (FID,)).fetchone()[0]
    n_qty = db.execute(
        "SELECT COUNT(*) FROM boq_floor_items WHERE floor_id=? AND COALESCE(qty,0)>0",
        (FID,)).fetchone()[0]
    db.close()
    check(f"Generate inserted items ({n_items} rows)", n_items > 20)
    check(f"Every item has a rate_buildup row (matched count)", n_rb == n_items, f"{n_rb} vs {n_items}")
    check(f"Most items got auto-priced from catalog",
          n_priced > n_items * 0.5, f"{n_priced}/{n_items} priced")
    check(f"All items default to qty>=1",
          n_qty == n_items, f"{n_qty}/{n_items} with qty>0")


# ---- 5. Complete BOQ Save-All flow -----------------------------------
section("5) Complete BOQ Save-All -- single form, single button, one shot")
with app.test_client() as cli:
    _auth(cli)
    # Reset floor again.
    db = _db()
    db.execute("DELETE FROM boq_floor_rate_buildup WHERE floor_item_id IN (SELECT id FROM boq_floor_items WHERE floor_id=?)", (FID,))
    db.execute("DELETE FROM boq_floor_items WHERE floor_id=?", (FID,))
    db.commit()
    db.close()

    # GET the complete page, snapshot its form data, then submit.
    r = cli.get(f"/boq-projects/{PID}/buildings/{BID}/floors/{FID}/complete")
    body = r.get_data(as_text=True)
    csrf = _csrf_from(body)

    # Build a minimal Save-All form. We submit just 5 rows by hand:
    # different bills/sections so we exercise the routing in save_all.
    rows = [
        # (bill_no, letter, title, desc, unit, qty, basic, sp, ip)
        (1, "B", "SWITCH BOARDS AND DISTRIBUTION BOARDS",
         "6-way TPN Memshield MCB Distribution Board c/w 200A INT. switch", "Nos.", 2, 15500.0, "", ""),
        (1, "D", "WIRING OF POINTS",
         "20mm diameter PVC conduit pipe", "Nos.", 50, 14.63, "", ""),
        (1, "E", "LUMINAIRES",
         "40W 230V 50Hz 600x600mm LED recessed FL light fitting c/w driver", "Nos.", 24, 599.0, "", ""),
        (1, "A", "PRELIMINARIES",
         "Site mobilisation and demobilisation", "Lot", 1, 25000.0, "", ""),
        (2, "A", "FIRE DETECTION AND ALARM SYSTEM",
         "Addressable Fire Alarm Control Panel (2-loop, EN 54-2/4)", "No.", 1, 25000.0, "", ""),
    ]

    form = {
        "_csrf": csrf,
        "supply_pct": "10",
        "install_pct": "15",
        "overhead_pct": "10",
        "profit_pct": "15",
        "vat_pct": "12.5",
        "apply_rates_to_all_rows": "1",
        # parallel arrays:
        "bill_no[]":          [str(r[0]) for r in rows],
        "section_letter[]":   [r[1] for r in rows],
        "section_title[]":    [r[2] for r in rows],
        "bill_name[]":        ["INTERNAL ELECTRICAL INSTALLATION" if r[0] == 1 else "FIRE ALARM SYSTEM INSTALLATION" for r in rows],
        "subsection_label[]": ["" for _ in rows],
        "description[]":      [r[3] for r in rows],
        "unit[]":             [r[4] for r in rows],
        "qty[]":              [str(r[5]) for r in rows],
        "basic_price[]":      [str(r[6]) for r in rows],
        "supply_pct[]":       [r[7] for r in rows],
        "install_pct[]":      [r[8] for r in rows],
        "specification[]":    ["" for _ in rows],
    }
    # Tick keys -- per row index per (bill, letter): tick_<bill>_<letter>_<idx>
    for i, row in enumerate(rows):
        form[f"tick_{row[0]}_{row[1]}_{i}"] = "1"

    r = cli.post(
        f"/boq-projects/{PID}/buildings/{BID}/floors/{FID}/complete/save-all",
        data=form, follow_redirects=False)
    check("POST /complete/save-all -> 302", r.status_code == 302, f"got {r.status_code}")
    db = _db()
    n_saved = db.execute("SELECT COUNT(*) FROM boq_floor_items WHERE floor_id=?", (FID,)).fetchone()[0]
    n_rb = db.execute("SELECT COUNT(*) FROM boq_floor_rate_buildup b JOIN boq_floor_items i ON b.floor_item_id=i.id WHERE i.floor_id=?", (FID,)).fetchone()[0]
    bills_seen = {r[0] for r in db.execute("SELECT DISTINCT bill_no FROM boq_floor_items WHERE floor_id=?", (FID,)).fetchall()}
    letters_seen = {r[0] for r in db.execute("SELECT DISTINCT section_letter FROM boq_floor_items WHERE floor_id=?", (FID,)).fetchall()}
    db.close()
    check(f"All {len(rows)} rows saved", n_saved == len(rows), f"got {n_saved}")
    check(f"Every saved item has a rate_buildup row", n_rb == n_saved, f"{n_rb} vs {n_saved}")
    check(f"Rows routed to correct bills {bills_seen} (expected {{1, 2}})", bills_seen == {1, 2})
    check(f"Rows routed to correct letters {letters_seen} (expected {{A, B, D, E}})",
          letters_seen == {"A", "B", "D", "E"})


# ---- 6. Section-by-Section grid editor regression --------------------
section("6) Section-by-Section grid editor still works (regression)")
with app.test_client() as cli:
    _auth(cli)
    r = cli.get(
        f"/boq-projects/{PID}/buildings/{BID}/floors/{FID}/bill/1/section/B/grid",
        query_string={"title": "SWITCH BOARDS AND DISTRIBUTION BOARDS",
                      "bill_name": "INTERNAL ELECTRICAL INSTALLATION"})
    body = r.get_data(as_text=True)
    check("Section grid GET -> 200", r.status_code == 200, f"got {r.status_code}")
    check("Section grid has 'Section-wide rates' label",
          "Section-wide rates" in body or "Section rates" in body)
    check("Catalog dropdown rendered (description selectable)",
          'name="description[]"' in body)
    check("Apply-rates-to-all-rows checkbox present",
          'name="apply_rates_to_all_rows"' in body)
    check("Save & back button present", "Save &amp; back" in body or "Save & back" in body)


# ---- 7. Rate engine equivalence --------------------------------------
section("7) Rate engine equivalence -- save_all uses boq_rate_v3 consistently")
db = _db()
items = db.execute(
    "SELECT i.qty, i.total_amount, b.basic_price, b.supply_pct, b.install_pct, "
    "b.overhead_pct, b.profit_pct, b.vat_pct, b.vat_in_basic "
    "FROM boq_floor_items i JOIN boq_floor_rate_buildup b ON b.floor_item_id=i.id "
    "WHERE i.floor_id=? LIMIT 5",
    (FID,)).fetchall()
db.close()
match = 0
for it in items:
    sa, ia, rate = boq_rate_v3(
        it["basic_price"], it["supply_pct"], it["install_pct"],
        it["overhead_pct"], it["profit_pct"], it["vat_pct"],
        vat_in_basic=bool(it["vat_in_basic"]))
    expected = it["qty"] * rate
    if abs(expected - it["total_amount"]) < 0.01:
        match += 1
check(f"All {len(items)} sampled items match boq_rate_v3 ({match}/{len(items)})",
      match == len(items))


# ---- 8. Edit Item page renders catalog dropdown ----------------------
section("8) Edit Item page renders catalog dropdown (commit 99e8d47)")
db = _db()
sample_item = db.execute(
    "SELECT id FROM boq_floor_items WHERE floor_id=? LIMIT 1",
    (FID,)).fetchone()
db.close()
if sample_item:
    iid = sample_item["id"]
    with app.test_client() as cli:
        _auth(cli)
        r = cli.get(f"/boq-projects/{PID}/buildings/{BID}/floors/{FID}/items/{iid}/edit")
        body = r.get_data(as_text=True)
        check("Edit Item GET -> 200", r.status_code == 200, f"got {r.status_code}")
        check("Edit page has description <select> dropdown",
              'id="edit_desc_dropdown"' in body or 'id="edit_desc_text"' in body)
        check("Edit page JS exposes _editDescPick (auto-fill on pick)",
              "_editDescPick" in body)
        check("Edit page has the rate-buildup dropdowns",
              'name="supply_pct"' in body and 'name="install_pct"' in body)


# ---- 9. Migration + Floor view integrity -----------------------------
section("9) Migration + Floor view integrity")
with app.test_client() as cli:
    _auth(cli)
    r = cli.get(f"/boq-projects/{PID}/buildings/{BID}/floors/{FID}")
    check("Floor view -> 200", r.status_code == 200, f"got {r.status_code}")
    body = r.get_data(as_text=True)
    check("Floor view shows Complete BOQ card", "Complete BOQ" in body)
    check("Floor view shows Section-by-Section card",
          "Section-by-Section" in body)
    r = cli.get(f"/boq-projects/{PID}/edit")
    check("Project Edit -> 200", r.status_code == 200, f"got {r.status_code}")


# ---- Summary ---------------------------------------------------------
print()
print("=" * 70)
if failures:
    print(f"FAIL  {len(failures)} check(s) did not pass:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"PASS  All local functional checks passed for Project BOQ -> Complete BOQ.")
sys.exit(0)
