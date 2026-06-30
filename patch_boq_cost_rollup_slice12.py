"""Cost roll-up Slices 1 + 2 (2026-06-30 owner directive).

Adds:
  * Section subtotal at the bottom of each section block on the Build-all
    page, with a 'Carried to Floor Summary' link.       [Slice 1]
  * New /boq-projects/<pid>/buildings/<bid>/summary route + handler in
    new_boq_hierarchy_routes.py.                        [Slice 2]
  * Floor summary's grand-total row relabeled 'Total carried to Building
    Summary' with a link to the new building summary.   [Slice 2]
  * Project summary's per-building rows link to the new building summary
    page so the user can drill from project -> building -> floor.  [Slice 2]

The new template templates/boq_building_summary.html is written
separately (via Write tool) since it's a brand-new file.

Re-runnable: each replace checks for the post-patch shape and skips.
"""
from __future__ import annotations
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
CRLF = b"\r\n"

def crlf(s: bytes) -> bytes:
    return s.replace(b"\r\n", b"\n").replace(b"\n", CRLF)

def replace_once(d: bytes, old: bytes, new: bytes, label: str, *, crlf_target: bool) -> bytes:
    if crlf_target:
        old_c, new_c = crlf(old), crlf(new)
    else:
        old_c, new_c = old, new
    if new_c in d:
        print(f"  {label}: already patched, skipping")
        return d
    n = d.count(old_c)
    if n != 1:
        sys.exit(f"  {label}: expected exactly 1 match of OLD anchor, found {n}")
    print(f"  {label}: patched")
    return d.replace(old_c, new_c, 1)


# ============================================================
# SLICE 1 -- section subtotal at bottom of each section block
# ============================================================
GRID = REPO / "templates" / "_boq_section_grid_inline.html"
grid_data = GRID.read_bytes()  # LF file

# Insert subtotal block right before the closing </div> of the section card.
# Anchor: the final `  </div>` that closes <div class="solar-card ..." id="sec_{{ sid }}">
# Adding before the LAST </div> of the file (since the file IS the section card body).
GRID_OLD = b'''      </tbody>
    </table>
  </div>
</div>
'''
GRID_NEW = b'''      </tbody>
    </table>
  </div>

  {% if existing %}
  {% set ns = namespace(t=0) %}
  {% for it in existing %}{% set ns.t = ns.t + (it.total_amount or 0) %}{% endfor %}
  <div class="d-flex justify-content-between align-items-center mt-2 px-3 py-2 flex-wrap gap-2"
       style="background:rgba(245,158,11,.10);border-top:2px solid var(--solar-gold,#f59e0b);border-radius:0 0 6px 6px">
    <div>
      <span class="text-warning fw-bold small" style="letter-spacing:.5px;text-transform:uppercase">
        Section {{ section_letter }} subtotal (saved rows)
      </span>
      <span class="text-secondary small ms-2">{{ existing|length }} row{{ '' if existing|length == 1 else 's' }}</span>
    </div>
    <div class="d-flex align-items-center gap-2 flex-wrap">
      <span class="text-warning fw-black" style="font-size:16px">{{ ns.t|money }}</span>
      <a href="{{ url_for('boq_floor_summary', pid=project.id, bid=building.id, fid=floor.id) }}"
         class="btn btn-outline-warning btn-sm py-0 px-2" style="font-size:11px"
         title="Open this floor's bills summary">
        <i class="bi bi-arrow-right-circle me-1"></i>Carried to Floor Summary
      </a>
    </div>
  </div>
  {% endif %}
</div>
'''
grid_data = replace_once(grid_data, GRID_OLD, GRID_NEW, "Slice1: section subtotal on grid", crlf_target=False)
GRID.write_bytes(grid_data)


# ============================================================
# SLICE 2a -- new building summary route
# ============================================================
HIER = REPO / "new_boq_hierarchy_routes.py"
hier_data = HIER.read_bytes()  # CRLF file

# Insert immediately AFTER the existing boq_building_view route block.
# Anchor: the route just before /buildings/<bid>/floors/<fid> in the file.
# Look for the project summary route and inject the building summary route
# right BEFORE it (alphabetical-ish ordering doesn't matter for Flask).
HIER_OLD = b'@app.route("/boq-projects/<int:pid>/summary")\r\n@login_required\r\ndef boq_project_summary(pid):\r\n'
HIER_NEW = b'''@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/summary")
@login_required
def boq_building_summary(pid, bid):
    """Building-level summary: per-floor subtotals -> grand total
    carried to Project Summary. Each floor row links to its own Bills
    summary; the grand-total row links to the project summary."""
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
# NB: The HIER_NEW already includes the next route's first three lines,
# so a re-run will idempotently match either OLD or NEW.
hier_data = replace_once(hier_data, HIER_OLD, HIER_NEW.replace(b"\n", b"\r\n"),
                         "Slice2a: building summary route", crlf_target=False)
HIER.write_bytes(hier_data)


# ============================================================
# SLICE 2b -- floor summary: relabel "General Summary" -> link to Building Summary
# ============================================================
FS = REPO / "templates" / "boq_floor_summary.html"
fs_data = FS.read_bytes()  # CRLF file

FS_OLD = b'        <td class="fw-black" style="font-size:15px">Total carried to General Summary</td>'
FS_NEW = b'''        <td class="fw-black" style="font-size:15px">
          <a href="{{ url_for('boq_building_summary', pid=project.id, bid=building.id) }}" class="text-warning text-decoration-none" title="Open this building's summary">
            Total carried to Building Summary <i class="bi bi-arrow-right-circle"></i>
          </a>
        </td>'''
fs_data = replace_once(fs_data, FS_OLD, FS_NEW, "Slice2b: floor summary relabel", crlf_target=True)
FS.write_bytes(fs_data)


# ============================================================
# SLICE 2c -- project summary: link each building row to its summary
# ============================================================
PS = REPO / "templates" / "boq_project_summary.html"
ps_data = PS.read_bytes()  # CRLF file

PS_OLD = b'        <td><strong>{{ b.building_name }}</strong></td>'
PS_NEW = b'        <td><strong><a href="{{ url_for(\'boq_building_summary\', pid=project.id, bid=b.id) }}" class="text-warning" title="Open this building\'s summary">{{ b.building_name }}</a></strong></td>'
ps_data = replace_once(ps_data, PS_OLD, PS_NEW, "Slice2c: project summary building link", crlf_target=True)
PS.write_bytes(ps_data)

print("done.")
