"""
Verify the /project/<id>/shading SVG actually changes with project data.

We insert/refresh one local project with three combinations of
  (mount_type, roof_height_m, sim_time)
and grep the rendered HTML for the values that should now flow through.
"""
import os, sys, sqlite3, json, re, requests
from dotenv import load_dotenv
load_dotenv()

BASE = "http://localhost:5000"
DB = "data/solar_web.db"
ADMIN = os.environ.get("SOLARPRO_ADMIN_USER", "admin")
PASSWORD = os.environ.get("SOLARPRO_ADMIN_PASSWORD") or sys.exit("no admin password")

# Get the admin user id
con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
uid = con.execute("SELECT id FROM users WHERE username=?", (ADMIN,)).fetchone()["id"]

PROJECT_NAME = "AUTOTEST_shading_svg"

def upsert_project(mount, roof_h, sim_time):
    data = {
        "country": "Ghana", "region": "Greater Accra",
        "mounting_type": mount,
        "shading": {
            "mount_type": mount,
            "roof_height_m": roof_h,
            "sim_time": sim_time,
            "obstructions": [
                {"type": "tree", "height": 8.0, "width": 4.0, "distance": 7.0, "direction": "E"},
                {"type": "boundary wall", "height": 4.0, "width": 5.0, "distance": 5.0, "direction": "W"},
            ],
        },
        "results": {"pv_kw_base": 5.0, "pv_kw": 5.0},
    }
    blob = json.dumps(data)
    row = con.execute("SELECT id FROM projects WHERE user_id=? AND name=?", (uid, PROJECT_NAME)).fetchone()
    if row:
        con.execute("UPDATE projects SET data_json=?, stage='results' WHERE id=?", (blob, row["id"]))
        pid = row["id"]
    else:
        cur = con.execute("INSERT INTO projects (user_id, name, stage, data_json) VALUES (?, ?, 'results', ?)",
                          (uid, PROJECT_NAME, blob))
        pid = cur.lastrowid
    con.commit()
    return pid

# Login
s = requests.Session()
g = s.get(f"{BASE}/login")
csrf = re.search(r'name="_csrf"\s+value="([^"]+)"', g.text).group(1)
r = s.post(f"{BASE}/login", data={"username": ADMIN, "password": PASSWORD, "_csrf": csrf}, allow_redirects=False)
assert r.status_code == 302, f"login failed: {r.status_code}"
print("login OK")

variants = [
    ("rooftop_pitched", 5,  "08:00", "morning, single-storey sloped"),
    ("rooftop_pitched", 32, "12:00", "noon, 10-storey block (sloped)"),
    ("rooftop_flat",    18, "15:00", "afternoon, mid-rise flat roof"),
    ("ground_fixed",     2, "11:00", "ground rack, late morning"),
    ("ground_tracking",  2, "06:30", "ground tracking, dawn"),
]

print()
print(f"{'mount':>17}  {'roof_h':>6}  {'sim':>6}  {'sun_x':>5} {'sun_y':>5}  {'has_house':>9}  {'has_rack':>8}  note")
print("-" * 110)
ok = bad = 0
for mount, roof_h, sim_time, note in variants:
    pid = upsert_project(mount, roof_h, sim_time)
    r = s.get(f"{BASE}/project/{pid}/shading")
    assert r.status_code == 200, f"shading page failed for {mount}: {r.status_code}"
    html = r.text
    sun_match  = re.search(r'id="svgSunDisk"\s+cx="(\d+)"\s+cy="(\d+)"', html)
    has_house  = "url(#houseGradN)" in html
    has_rack   = "Ground-Mount Array" in html
    sun_x, sun_y = (sun_match.group(1), sun_match.group(2)) if sun_match else ("?", "?")
    # Sanity expectations
    expect_house = mount.startswith("rooftop")
    expect_rack  = mount.startswith("ground")
    house_ok = (has_house == expect_house)
    rack_ok  = (has_rack == expect_rack)
    sun_ok   = (sun_match is not None and sun_match.group(1) != "700")  # default would've been 700
    line_ok = house_ok and rack_ok and sun_ok
    if line_ok: ok += 1
    else: bad += 1
    print(f"{mount:>17}  {roof_h:>6}  {sim_time:>6}  {sun_x:>5} {sun_y:>5}  {str(has_house):>9}  {str(has_rack):>8}  {'PASS' if line_ok else 'FAIL'}  {note}")

con.close()
print()
print(f"{ok}/{ok+bad} variants match expectations")
sys.exit(0 if bad == 0 else 1)
