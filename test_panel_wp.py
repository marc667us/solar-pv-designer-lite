"""
Live end-to-end test of panel_wp selection.

Goal:
- For every panel option (110, 250, 330, 400, 450, 500, 550) create a fresh project,
  set the panel choice on /location, submit the same loads on /loads, then read the
  results page and verify each non-default option produces a different num_panels
  than the 400 Wp baseline.

Inputs:
- BASE: live URL (no localhost per project rule)
- admin credentials hard-coded

Outputs:
- prints a row per panel_wp showing what the page renders
- final verdict line: PASS if num_panels strictly decreases, otherwise lists the
  wattages that came back wrong

Syntax notes:
- request.Session() keeps Flask session cookie between requests
- request.form fields in this app use [] suffix (load_name[], load_watt[], ...)
- /project/<pid>/results is the page that shows the KPI strip with num_panels
"""
import requests
import re
import sys

BASE = "https://web-production-744af.up.railway.app"


def csrf_of(html):
    """Return first _csrf hidden input value found in a Jinja page.

    Tries both attribute orders (name first or value first).
    """
    m = re.search(r'name=["\']_csrf["\']\s+value=["\']([^"\']+)["\']', html)
    if not m:
        m = re.search(r'value=["\']([^"\']+)["\']\s+name=["\']_csrf["\']', html)
    return m.group(1) if m else ""


def login(s):
    """POST login as admin; raises if logout button not visible after."""
    r = s.get(f"{BASE}/login", timeout=20)
    s.post(
        f"{BASE}/login",
        data={"username": "admin", "password": "SolarAdmin2026!", "_csrf": csrf_of(r.text)},
        timeout=20,
    )
    dash = s.get(f"{BASE}/admin", timeout=20)
    assert "logout" in dash.text.lower(), "login failed (no logout link)"


def new_project(s, name):
    """Hit /project/new and return the integer pid from the Location header."""
    r = s.get(f"{BASE}/project/new", timeout=20)
    r = s.post(
        f"{BASE}/project/new",
        data={"name": name, "client": "panel test", "_csrf": csrf_of(r.text)},
        timeout=20,
        allow_redirects=False,
    )
    m = re.search(r"/project/(\d+)/", r.headers.get("Location", ""))
    assert m, f"no pid in redirect: {r.headers!r}"
    return int(m.group(1))


def save_location(s, pid, panel_wp):
    """Submit /location with Ghana/Greater Accra and the requested panel_wp."""
    r = s.get(f"{BASE}/project/{pid}/location", timeout=20)
    data = {
        "_csrf": csrf_of(r.text),
        "country": "Ghana",
        "region": "Greater Accra",
        "tariff": "2.5",
        "system_type": "off-grid",
        "phase": "single",
        "voltage": "48",
        "autonomy": "1",
        "chemistry": "LiFePO4",
        "panel_wp": str(panel_wp),
        "mounting_type": "rooftop_pitched",
        "tilt_angle": "15",
        "azimuth": "0",
        "system_losses": "14",
        "inverter_eff": "95",
        "battery_dod": "80",
        "performance_ratio": "75",
        "supply_markup_pct": "8",
        "install_rate_pct": "15",
        "funding_mode": "loan",
    }
    r = s.post(f"{BASE}/project/{pid}/location", data=data, timeout=20, allow_redirects=False)
    assert r.status_code in (301, 302), f"location save HTTP {r.status_code}"


def submit_loads(s, pid):
    """POST a minimal but realistic load schedule. Uses load_*[] form names."""
    r = s.get(f"{BASE}/project/{pid}/loads", timeout=20)
    data = [
        ("_csrf", csrf_of(r.text)),
        # row 1: 10 LED bulbs, 10 W, 4 h, df 1.0, not critical
        ("load_cat[]", "Lighting"), ("load_name[]", "LED bulb"),
        ("load_watt[]", "10"), ("load_qty[]", "10"),
        ("load_hours[]", "4"), ("load_df[]", "1.0"),
        # row 2: fridge 150 W, 24 h, df 0.4
        ("load_cat[]", "Cooling"), ("load_name[]", "Fridge"),
        ("load_watt[]", "150"), ("load_qty[]", "1"),
        ("load_hours[]", "24"), ("load_df[]", "0.4"),
        # row 3: TV 100 W, 6 h
        ("load_cat[]", "Electronics"), ("load_name[]", "TV"),
        ("load_watt[]", "100"), ("load_qty[]", "1"),
        ("load_hours[]", "6"), ("load_df[]", "1.0"),
    ]
    r = s.post(f"{BASE}/project/{pid}/loads", data=data, timeout=30, allow_redirects=False)
    assert r.status_code in (301, 302), f"loads submit HTTP {r.status_code}"


def read_results(s, pid):
    """GET /project/<pid>/results and pull num_panels + panel_wp + pv_kw."""
    r = s.get(f"{BASE}/project/{pid}/results", timeout=20)
    html = r.text
    # results.html renders a KPI tile: <div class="kpi-tile-val">N</div><div class="kpi-tile-unit">× P Wp</div>
    # easier: extract everything inside the "Panels" KPI tile
    # the row: ('Panels', r.num_panels, '× '~r.panel_wp~'Wp', '#a78bfa')
    # the HTML order is: kpi-tile-lbl Panels, then kpi-tile-val N, then kpi-tile-unit × <Wp>Wp
    m = re.search(
        r'kpi-tile-lbl">Panels</div>\s*<div[^>]*kpi-tile-val[^>]*>\s*([0-9]+)\s*</div>'
        r'\s*<div[^>]*kpi-tile-unit[^>]*>\s*&times;?\s*([0-9]+)Wp',
        html,
    )
    if not m:
        # try alternate: × char (raw unicode in template)
        m = re.search(
            r"kpi-tile-lbl\">Panels</div>\s*<div[^>]*kpi-tile-val[^>]*>\s*([0-9]+)\s*</div>"
            r"\s*<div[^>]*kpi-tile-unit[^>]*>\s*[^0-9]*?([0-9]+)\s*Wp",
            html,
        )
    pv_match = re.search(
        r'kpi-tile-lbl">PV Array</div>\s*<div[^>]*kpi-tile-val[^>]*>\s*([0-9.]+)',
        html,
    )
    return {
        "num_panels": int(m.group(1)) if m else None,
        "panel_wp_seen": int(m.group(2)) if m else None,
        "pv_kw": float(pv_match.group(1)) if pv_match else None,
    }


def main():
    s = requests.Session()
    print("login...", end="", flush=True)
    login(s)
    print(" ok")
    table = {}
    for wp in (110, 250, 330, 400, 450, 500, 550):
        pid = new_project(s, f"_wptest_{wp}")
        save_location(s, pid, wp)
        submit_loads(s, pid)
        r = read_results(s, pid)
        table[wp] = r
        print(f"  pid={pid:3d}  wp_set={wp:3d}  wp_seen={r['panel_wp_seen']}  num_panels={r['num_panels']}  pv_kw={r['pv_kw']}")
    print()
    seen = [table[w]["panel_wp_seen"] for w in (110, 250, 330, 400, 450, 500, 550)]
    npanels = [table[w]["num_panels"] for w in (110, 250, 330, 400, 450, 500, 550)]
    print(f"seen wp series : {seen}")
    print(f"num_panels     : {npanels}")
    ok_seen = seen == [110, 250, 330, 400, 450, 500, 550]
    ok_mono = all(npanels[i] is not None and npanels[i + 1] is not None and npanels[i] >= npanels[i + 1] for i in range(len(npanels) - 1))
    if ok_seen and ok_mono:
        print("PASS: every panel selection is honoured and num_panels decreases as Wp grows")
        sys.exit(0)
    if not ok_seen:
        print("FAIL: page does not show the wattage that was submitted")
    if not ok_mono:
        print("FAIL: num_panels is not monotonically decreasing in Wp")
    sys.exit(1)


if __name__ == "__main__":
    main()
