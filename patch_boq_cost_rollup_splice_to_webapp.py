"""Critical bridge: the new_boq_*.py files are SOURCE-only; the deployed
code lives spliced into web_app.py. My earlier patch to
new_boq_hierarchy_routes.py (adding boq_building_summary) and
new_boq_section_loop_routes.py (adding per-section query to
boq_floor_summary) is dormant -- web_app.py was untouched.

Templates ARE live (they're loaded from templates/ at request time).
But the project-summary "View building" link points at a route the
deployed app doesn't have, and the floor-summary template references
a `sections` kwarg that the deployed handler doesn't pass.

This patch splices both changes directly into web_app.py via the
byte-level pattern from CLAUDE.md (web_app.py has CRLF endings + must
not be Edit-tool touched).

  * Slice 2-fix: insert boq_building_summary BEFORE boq_project_summary
                (anchor: '@app.route("/boq-projects/<int:pid>/summary")')
  * Slice 3-fix: extend boq_floor_summary handler with per_section query
                + sections kwarg
"""
from __future__ import annotations
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web_app.py"
data = WEB.read_bytes()
CRLF = b"\r\n"


def crlf(s: bytes) -> bytes:
    return s.replace(b"\r\n", b"\n").replace(b"\n", CRLF)


def replace_once(d: bytes, old: bytes, new: bytes, label: str) -> bytes:
    old_c, new_c = crlf(old), crlf(new)
    if new_c in d:
        print(f"  {label}: already patched, skipping")
        return d
    n = d.count(old_c)
    if n != 1:
        sys.exit(f"  {label}: expected exactly 1 OLD match, found {n}")
    print(f"  {label}: patched")
    return d.replace(old_c, new_c, 1)


# ============================================================
# Slice 2-fix: insert boq_building_summary route
# ============================================================
B_OLD = b'''@app.route("/boq-projects/<int:pid>/summary")
@login_required
def boq_project_summary(pid):
'''

B_NEW = b'''@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/summary")
@login_required
def boq_building_summary(pid, bid):
    """Building-level summary: per-floor subtotals -> grand total carried
    to Project Summary. Each floor row links to its own Bills summary;
    the grand-total row links to the project summary."""
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    building = _boq_building_owned_or_404(bid, pid)
    with get_db() as c:
        per_floor = c.execute(
            "SELECT f.id AS fid, f.floor_name, f.floor_level, "
            "       COALESCE(SUM(i.total_amount),0) AS subtotal "
            "FROM boq_floors f "
            "LEFT JOIN boq_floor_items i ON i.floor_id=f.id "
            "WHERE f.building_id=? "
            "GROUP BY f.id "
            "ORDER BY f.floor_level, f.id",
            (bid,),
        ).fetchall()
    floors = [
        {
            "fid": int(r["fid"]),
            "floor_name": r["floor_name"],
            "floor_level": r["floor_level"],
            "subtotal": float(r["subtotal"] or 0),
        }
        for r in per_floor
    ]
    building_total = sum(f["subtotal"] for f in floors)
    return render_template(
        "boq_building_summary.html",
        user=current_user(),
        project=project, building=building,
        floors=floors, building_total=building_total,
    )


@app.route("/boq-projects/<int:pid>/summary")
@login_required
def boq_project_summary(pid):
'''

data = replace_once(data, B_OLD, B_NEW, "Slice2-fix: insert boq_building_summary into web_app.py")


# ============================================================
# Slice 3-fix: extend boq_floor_summary handler in web_app.py
# ============================================================
F_OLD = b'''    with get_db() as c:
        per_bill = c.execute(
            "SELECT COALESCE(bill_no,0) AS bill_no, "
            "       COALESCE(bill_name,'') AS bill_name, "
            "       COALESCE(SUM(total_amount),0) AS subtotal "
            "FROM boq_floor_items "
            "WHERE floor_id=? "
            "GROUP BY bill_no, bill_name "
            "ORDER BY bill_no",
            (fid,),
        ).fetchall()

    bills = [
        {
            "bill_no":   int(r["bill_no"]   or 0),
            "bill_name": (r["bill_name"]    or _boq_lookup_bill_name(int(r["bill_no"] or 0)) or "OTHER"),
            "subtotal":  float(r["subtotal"] or 0),
        }
        for r in per_bill
    ]
    subtotal = sum(b["subtotal"] for b in bills)
    cont_pct = float((floor["contingency_pct"] if "contingency_pct" in floor.keys() else 10) or 10)
    contingency = subtotal * cont_pct / 100.0
    carried = subtotal + contingency
    return render_template(
        "boq_floor_summary.html",
        user=current_user(),
        project=project, building=building, floor=floor,
        bills=bills, subtotal=subtotal,
        contingency_pct=cont_pct, contingency=contingency,
        carried=carried,
    )'''

F_NEW = b'''    with get_db() as c:
        per_bill = c.execute(
            "SELECT COALESCE(bill_no,0) AS bill_no, "
            "       COALESCE(bill_name,'') AS bill_name, "
            "       COALESCE(SUM(total_amount),0) AS subtotal "
            "FROM boq_floor_items "
            "WHERE floor_id=? "
            "GROUP BY bill_no, bill_name "
            "ORDER BY bill_no",
            (fid,),
        ).fetchall()
        per_section = c.execute(
            "SELECT COALESCE(bill_no,0) AS bill_no, "
            "       COALESCE(bill_name,'') AS bill_name, "
            "       COALESCE(section_letter,'') AS section_letter, "
            "       COALESCE(section,'') AS section_title, "
            "       COALESCE(SUM(total_amount),0) AS subtotal, "
            "       COUNT(*) AS row_count "
            "FROM boq_floor_items "
            "WHERE floor_id=? "
            "GROUP BY bill_no, bill_name, section_letter, section "
            "ORDER BY bill_no, section_letter",
            (fid,),
        ).fetchall()

    bills = [
        {
            "bill_no":   int(r["bill_no"]   or 0),
            "bill_name": (r["bill_name"]    or _boq_lookup_bill_name(int(r["bill_no"] or 0)) or "OTHER"),
            "subtotal":  float(r["subtotal"] or 0),
        }
        for r in per_bill
    ]
    subtotal = sum(b["subtotal"] for b in bills)
    sections = [
        {
            "bill_no":        int(r["bill_no"] or 0),
            "bill_name":      (r["bill_name"]   or _boq_lookup_bill_name(int(r["bill_no"] or 0)) or "OTHER"),
            "section_letter": (r["section_letter"] or "").upper(),
            "section_title":  (r["section_title"]  or ""),
            "subtotal":       float(r["subtotal"]  or 0),
            "row_count":      int(r["row_count"] or 0),
        }
        for r in per_section
    ]
    cont_pct = float((floor["contingency_pct"] if "contingency_pct" in floor.keys() else 10) or 10)
    contingency = subtotal * cont_pct / 100.0
    carried = subtotal + contingency
    return render_template(
        "boq_floor_summary.html",
        user=current_user(),
        project=project, building=building, floor=floor,
        bills=bills, sections=sections, subtotal=subtotal,
        contingency_pct=cont_pct, contingency=contingency,
        carried=carried,
    )'''

data = replace_once(data, F_OLD, F_NEW, "Slice3-fix: extend boq_floor_summary in web_app.py")

WEB.write_bytes(data)
print("done.")
