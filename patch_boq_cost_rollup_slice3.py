"""Cost roll-up Slice 3 (2026-06-30 owner directive): percentage analytics
at every summary level.

Adds:
  * Floor summary: % of floor column on Bills table, plus a new
    Per-section breakdown table with % of floor.       [Slice 3a + 3b]
  * Project summary: % of project column on per-building and per-floor
    tables.                                            [Slice 3c]

Building summary already has % of building (shipped in Slice 2).

The floor-summary handler in new_boq_section_loop_routes.py is extended
to compute a second per-section query and pass `sections` to the
template. Existing handler params unchanged so any older callers are
unaffected.

Re-runnable: each replace checks for the post-patch shape and skips.
"""
from __future__ import annotations
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
CRLF = b"\r\n"

def crlf(s: bytes) -> bytes:
    return s.replace(b"\r\n", b"\n").replace(b"\n", CRLF)

def replace_once(d, old, new, label, *, crlf_target):
    if crlf_target:
        old_c, new_c = crlf(old), crlf(new)
    else:
        old_c, new_c = old, new
    if new_c in d:
        print(f"  {label}: already patched, skipping")
        return d
    n = d.count(old_c)
    if n != 1:
        sys.exit(f"  {label}: expected 1 OLD match, found {n}")
    print(f"  {label}: patched")
    return d.replace(old_c, new_c, 1)


# ============================================================
# 3a -- floor_summary handler: add per-section query
# ============================================================
LOOP = REPO / "new_boq_section_loop_routes.py"
loop_data = LOOP.read_bytes()  # CRLF file

LOOP_OLD = b'''    with get_db() as c:
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

LOOP_NEW = b'''    with get_db() as c:
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
loop_data = replace_once(loop_data, LOOP_OLD, LOOP_NEW, "3a: floor_summary handler per-section query", crlf_target=True)
LOOP.write_bytes(loop_data)


# ============================================================
# 3b -- floor summary template: % of floor + per-section breakdown
# ============================================================
FS = REPO / "templates" / "boq_floor_summary.html"
fs_data = FS.read_bytes()  # CRLF file

# Replace the Bills table block. The existing block:
#   <tr><th>Item</th><th>Description</th><th class="text-end">Amount</th></tr>
# and the bill rows that follow get a new "% of floor" column.
FS_OLD_HEADER = b'      <tr><th>Item</th><th>Description</th><th class="text-end">Amount</th></tr>'
FS_NEW_HEADER = b'      <tr><th>Item</th><th>Description</th><th class="text-end">Amount</th><th class="text-end" style="width:120px">% of Floor</th></tr>'
fs_data = replace_once(fs_data, FS_OLD_HEADER, FS_NEW_HEADER, "3b-i: floor summary header adds % of Floor", crlf_target=True)

FS_OLD_BILLROW = b'''      <tr>
        <td class="text-secondary">{{ loop.index }}</td>
        <td><strong>BILL No. {{ b.bill_no }} \xe2\x80\x94 {{ b.bill_name }}</strong></td>
        <td class="text-end">{{ (b.subtotal)|money }}</td>
      </tr>'''
FS_NEW_BILLROW = b'''      <tr>
        <td class="text-secondary">{{ loop.index }}</td>
        <td><strong>BILL No. {{ b.bill_no }} \xe2\x80\x94 {{ b.bill_name }}</strong></td>
        <td class="text-end">{{ (b.subtotal)|money }}</td>
        <td class="text-end text-secondary">{% if subtotal > 0 %}{{ '%.1f'|format(b.subtotal * 100 / subtotal) }}%{% else %}\xe2\x80\x94{% endif %}</td>
      </tr>'''
fs_data = replace_once(fs_data, FS_OLD_BILLROW, FS_NEW_BILLROW, "3b-ii: bill row adds % of Floor cell", crlf_target=True)

# Update SUB TOTAL row from 2-col to 3-col
FS_OLD_SUBTOT = b'''      <tr>
        <td></td>
        <td class="fw-bold" style="border-top:1px solid #1e1e3a">SUB TOTAL</td>
        <td class="text-end fw-bold" style="border-top:1px solid #1e1e3a">{{ (subtotal)|money }}</td>
      </tr>
      <tr>
        <td></td>
        <td>CONTINGENCIES ({{ (contingency_pct)|fmt }}%)</td>
        <td class="text-end">{{ (contingency)|fmt }}</td>
      </tr>'''
FS_NEW_SUBTOT = b'''      <tr>
        <td></td>
        <td class="fw-bold" style="border-top:1px solid #1e1e3a">SUB TOTAL</td>
        <td class="text-end fw-bold" style="border-top:1px solid #1e1e3a">{{ (subtotal)|money }}</td>
        <td class="text-end fw-bold text-secondary" style="border-top:1px solid #1e1e3a">100.0%</td>
      </tr>
      <tr>
        <td></td>
        <td>CONTINGENCIES ({{ (contingency_pct)|fmt }}%)</td>
        <td class="text-end">{{ (contingency)|fmt }}</td>
        <td class="text-end text-secondary">+{{ (contingency_pct)|fmt }}%</td>
      </tr>'''
fs_data = replace_once(fs_data, FS_OLD_SUBTOT, FS_NEW_SUBTOT, "3b-iii: SUB TOTAL row adds 100% / contingency %", crlf_target=True)

# Update grand-total row (already relabeled in Slice 2 to point at Building Summary)
FS_OLD_CARRIED = b'''      <tr style="background:rgba(245,158,11,.10);border-top:2px solid #1e1e3a">
        <td></td>
        <td class="fw-black" style="font-size:15px">
          <a href="{{ url_for('boq_building_summary', pid=project.id, bid=building.id) }}" class="text-warning text-decoration-none" title="Open this building's summary">
            Total carried to Building Summary <i class="bi bi-arrow-right-circle"></i>
          </a>
        </td>
        <td class="text-end fw-black text-warning" style="font-size:17px">{{ (carried)|fmt }}</td>
      </tr>'''
FS_NEW_CARRIED = b'''      <tr style="background:rgba(245,158,11,.10);border-top:2px solid #1e1e3a">
        <td></td>
        <td class="fw-black" style="font-size:15px">
          <a href="{{ url_for('boq_building_summary', pid=project.id, bid=building.id) }}" class="text-warning text-decoration-none" title="Open this building's summary">
            Total carried to Building Summary <i class="bi bi-arrow-right-circle"></i>
          </a>
        </td>
        <td class="text-end fw-black text-warning" style="font-size:17px">{{ (carried)|fmt }}</td>
        <td class="text-end fw-black text-warning">{{ '%.1f'|format(100 + contingency_pct) }}%</td>
      </tr>'''
fs_data = replace_once(fs_data, FS_OLD_CARRIED, FS_NEW_CARRIED, "3b-iv: carried row adds % column", crlf_target=True)

# Insert per-section breakdown card AFTER the contingency form.
# Anchor: the closing `</form>` of the contingency form (followed by `</div>`).
FS_OLD_TAIL = b'''  <form method="POST" action="{{ url_for('boq_floor_set_contingency', pid=project.id, bid=building.id, fid=floor.id) }}" class="row g-2 no-print">
    <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
    <div class="col-md-3">
      <label class="form-label small text-secondary">Contingency %</label>
      <input type="number" step="0.1" min="0" max="100" class="form-control form-control-sm" name="contingency_pct" value="{{ "%.2f"|format(contingency_pct) }}">
    </div>
    <div class="col-md-3 d-flex align-items-end">
      <button class="btn btn-outline-warning btn-sm w-100"><i class="bi bi-save me-1"></i>Update contingency</button>
    </div>
  </form>
</div>'''
FS_NEW_TAIL = b'''  <form method="POST" action="{{ url_for('boq_floor_set_contingency', pid=project.id, bid=building.id, fid=floor.id) }}" class="row g-2 no-print">
    <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
    <div class="col-md-3">
      <label class="form-label small text-secondary">Contingency %</label>
      <input type="number" step="0.1" min="0" max="100" class="form-control form-control-sm" name="contingency_pct" value="{{ "%.2f"|format(contingency_pct) }}">
    </div>
    <div class="col-md-3 d-flex align-items-end">
      <button class="btn btn-outline-warning btn-sm w-100"><i class="bi bi-save me-1"></i>Update contingency</button>
    </div>
  </form>
</div>

{% if sections %}
<div class="solar-card p-4 mt-3">
  <h6 class="fw-bold mb-3"><i class="bi bi-grid-3x3-gap text-warning me-1"></i>Per-section breakdown</h6>
  <table class="table table-sm align-middle" style="color:#e0e0f0;font-size:13px">
    <thead style="color:#9090c0;font-size:11px;text-transform:uppercase;letter-spacing:.5px;border-bottom:2px solid #1e1e3a">
      <tr>
        <th style="width:80px">Bill</th>
        <th style="width:60px">Section</th>
        <th>Title</th>
        <th class="text-end" style="width:70px">Rows</th>
        <th class="text-end">Subtotal</th>
        <th class="text-end" style="width:120px">% of Floor</th>
      </tr>
    </thead>
    <tbody>
      {% for s in sections %}
      <tr>
        <td class="text-secondary small">{{ s.bill_no }}</td>
        <td class="fw-bold text-warning">{{ s.section_letter }}</td>
        <td class="small">{{ s.section_title }}</td>
        <td class="text-end small text-secondary">{{ s.row_count }}</td>
        <td class="text-end fw-bold">{{ (s.subtotal)|money }}</td>
        <td class="text-end text-secondary">{% if subtotal > 0 %}{{ '%.1f'|format(s.subtotal * 100 / subtotal) }}%{% else %}\xe2\x80\x94{% endif %}</td>
      </tr>
      {% endfor %}
      <tr style="background:rgba(245,158,11,.10);border-top:2px solid #1e1e3a">
        <td colspan="4" class="text-end fw-black">FLOOR SUB TOTAL</td>
        <td class="text-end fw-black text-warning">{{ (subtotal)|money }}</td>
        <td class="text-end fw-black text-warning">100.0%</td>
      </tr>
    </tbody>
  </table>
</div>
{% endif %}'''
fs_data = replace_once(fs_data, FS_OLD_TAIL, FS_NEW_TAIL, "3b-v: append per-section breakdown card", crlf_target=True)
FS.write_bytes(fs_data)


# ============================================================
# 3c -- project summary: % of project on building + floor tables
# ============================================================
PS = REPO / "templates" / "boq_project_summary.html"
ps_data = PS.read_bytes()  # CRLF file

# Per-building table header
PS_OLD_BHEAD = b'      <tr><th>Building</th><th>Purpose</th><th>Subtype</th><th class="text-end">Subtotal</th></tr>'
PS_NEW_BHEAD = b'      <tr><th>Building</th><th>Purpose</th><th>Subtype</th><th class="text-end">Subtotal</th><th class="text-end" style="width:120px">% of Project</th></tr>'
ps_data = replace_once(ps_data, PS_OLD_BHEAD, PS_NEW_BHEAD, "3c-i: per-building header adds % col", crlf_target=True)

# Per-building row -- already includes the link from Slice 2c
PS_OLD_BROW = b'''      <tr>
        <td><strong><a href="{{ url_for('boq_building_summary', pid=project.id, bid=b.id) }}" class="text-warning" title="Open this building's summary">{{ b.building_name }}</a></strong></td>
        <td class="small">{{ b.primary_purpose|title }}</td>
        <td class="small text-secondary">{{ b.purpose_subtype }}</td>
        <td class="text-end fw-bold text-warning">{{ (b.subtotal or 0)|money }}</td>
      </tr>'''
PS_NEW_BROW = b'''      <tr>
        <td><strong><a href="{{ url_for('boq_building_summary', pid=project.id, bid=b.id) }}" class="text-warning" title="Open this building's summary">{{ b.building_name }}</a></strong></td>
        <td class="small">{{ b.primary_purpose|title }}</td>
        <td class="small text-secondary">{{ b.purpose_subtype }}</td>
        <td class="text-end fw-bold text-warning">{{ (b.subtotal or 0)|money }}</td>
        <td class="text-end text-secondary">{% if grand_total > 0 %}{{ '%.1f'|format((b.subtotal or 0) * 100 / grand_total) }}%{% else %}\xe2\x80\x94{% endif %}</td>
      </tr>'''
ps_data = replace_once(ps_data, PS_OLD_BROW, PS_NEW_BROW, "3c-ii: per-building row adds % cell", crlf_target=True)

# Per-building tfoot grand total
PS_OLD_BFOOT = b'''      <tr style="background:rgba(245,158,11,.10)">
        <td colspan="3" class="text-end fw-black">PROJECT GRAND TOTAL</td>
        <td class="text-end fw-black text-warning">{{ (grand_total)|money }}</td>
      </tr>'''
PS_NEW_BFOOT = b'''      <tr style="background:rgba(245,158,11,.10)">
        <td colspan="3" class="text-end fw-black">PROJECT GRAND TOTAL</td>
        <td class="text-end fw-black text-warning">{{ (grand_total)|money }}</td>
        <td class="text-end fw-black text-warning">100.0%</td>
      </tr>'''
ps_data = replace_once(ps_data, PS_OLD_BFOOT, PS_NEW_BFOOT, "3c-iii: per-building tfoot adds % cell", crlf_target=True)

# Per-floor table header
PS_OLD_FHEAD = b'      <tr><th>Building</th><th>Floor</th><th>Level</th><th class="text-end">Subtotal</th></tr>'
PS_NEW_FHEAD = b'      <tr><th>Building</th><th>Floor</th><th>Level</th><th class="text-end">Subtotal</th><th class="text-end" style="width:120px">% of Project</th></tr>'
ps_data = replace_once(ps_data, PS_OLD_FHEAD, PS_NEW_FHEAD, "3c-iv: per-floor header adds % col", crlf_target=True)

# Per-floor row
PS_OLD_FROW = b'''      <tr>
        <td>{{ f.building_name }}</td>
        <td>{{ f.floor_name }}</td>
        <td class="small text-secondary">{{ f.floor_level }}</td>
        <td class="text-end fw-bold">{{ (f.subtotal or 0)|money }}</td>
      </tr>'''
PS_NEW_FROW = b'''      <tr>
        <td>{{ f.building_name }}</td>
        <td>{{ f.floor_name }}</td>
        <td class="small text-secondary">{{ f.floor_level }}</td>
        <td class="text-end fw-bold">{{ (f.subtotal or 0)|money }}</td>
        <td class="text-end text-secondary">{% if grand_total > 0 %}{{ '%.1f'|format((f.subtotal or 0) * 100 / grand_total) }}%{% else %}\xe2\x80\x94{% endif %}</td>
      </tr>'''
ps_data = replace_once(ps_data, PS_OLD_FROW, PS_NEW_FROW, "3c-v: per-floor row adds % cell", crlf_target=True)

PS.write_bytes(ps_data)

print("done.")
