"""Campus (project) summary extras (2026-06-30 owner directive, revised).

Per user clarification: the additional cost items belong at the CAMPUS
level (the project summary), NOT per-building.

Hierarchy:
  Floor totals -> Building Summary (sum of its floors)
  Building totals -> Campus (Project) Summary (sum of all buildings)
  Campus Summary = sum(building totals) + 5 extras

5 campus-level extras:
  1. Power Supply
  2. Meter & Service Connection
  3. Utility Administrative Charges
  4. Taxes from Utility
  5. Withholding Tax (govt income tax)

Storage: 5 REAL columns on boq_projects, lazy ALTER on first hit.

Changes:
  1. web_app.py
     - helper _ensure_boq_project_extras_schema()
     - helper _read_project_extras()
     - boq_project_summary handler computes grand_total = floor_grand + extras_total
     - new POST route /boq-projects/<pid>/summary/extras -> boq_project_extras_save
  2. templates/boq_project_summary.html
     - new "Campus-level Additional Costs" card with 5 rows + extras_total + grand_total
     - edit form (no-print) below
     - Updated label: "PROJECT GRAND TOTAL" -> "CAMPUS GRAND TOTAL"
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
        print(f"  {label}: already patched, skipping"); return d
    n = d.count(old_c)
    if n != 1:
        sys.exit(f"  {label}: expected 1 OLD match, found {n}")
    print(f"  {label}: patched")
    return d.replace(old_c, new_c, 1)


# ============================================================
# 1. web_app.py
# ============================================================
WEB = REPO / "web_app.py"
data = WEB.read_bytes()

# CRITICAL: include the decorators in the OLD anchor so the NEW block
# (helpers + replacement decorators + new handler) lands cleanly.
HANDLER_OLD = b'''@app.route("/boq-projects/<int:pid>/summary")
@login_required
def boq_project_summary(pid):
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    with get_db() as c:
        per_building = c.execute(
            "SELECT b.id, b.building_name, b.primary_purpose, b.purpose_subtype, "
            "       COALESCE(SUM(i.total_amount),0) AS subtotal "
            "FROM boq_buildings b "
            "LEFT JOIN boq_floor_items i ON i.building_id=b.id "
            "WHERE b.project_id=? GROUP BY b.id ORDER BY b.id",
            (pid,),
        ).fetchall()
        per_floor = c.execute(
            "SELECT b.id AS bid, b.building_name, f.id AS fid, f.floor_name, "
            "       f.floor_level, COALESCE(SUM(i.total_amount),0) AS subtotal "
            "FROM boq_floors f "
            "JOIN boq_buildings b ON b.id=f.building_id "
            "LEFT JOIN boq_floor_items i ON i.floor_id=f.id "
            "WHERE f.project_id=? GROUP BY b.id, f.id "
            "ORDER BY b.id, f.floor_level",
            (pid,),
        ).fetchall()
        grand_row = c.execute(
            "SELECT COALESCE(SUM(total_amount),0) AS g FROM boq_floor_items WHERE project_id=?",
            (pid,),
        ).fetchone()
    grand_total = float(grand_row["g"] or 0) if grand_row else 0.0
    return render_template("boq_project_summary.html",
                           user=current_user(),
                           project=project,
                           per_building=per_building,
                           per_floor=per_floor,
                           grand_total=grand_total)'''

HANDLER_NEW = b'''_PROJECT_EXTRAS_COLS = (
    "extras_power_supply",
    "extras_meter_service",
    "extras_utility_admin",
    "extras_taxes_utility",
    "extras_withholding_tax",
)


def _ensure_boq_project_extras_schema(c):
    """Lazy ALTER for the 5 campus-level extras columns on boq_projects."""
    is_pg = bool(os.environ.get("DATABASE_URL"))
    for col in _PROJECT_EXTRAS_COLS:
        try:
            if is_pg:
                c.execute(
                    f"ALTER TABLE boq_projects ADD COLUMN IF NOT EXISTS {col} REAL DEFAULT 0"
                )
            else:
                c.execute(
                    f"ALTER TABLE boq_projects ADD COLUMN {col} REAL DEFAULT 0"
                )
        except Exception:
            pass


def _read_project_extras(project_row):
    keys = project_row.keys() if hasattr(project_row, "keys") else ()
    def _g(k):
        if k in keys:
            return float(project_row[k] or 0)
        return 0.0
    return {
        "power_supply":    _g("extras_power_supply"),
        "meter_service":   _g("extras_meter_service"),
        "utility_admin":   _g("extras_utility_admin"),
        "taxes_utility":   _g("extras_taxes_utility"),
        "withholding_tax": _g("extras_withholding_tax"),
    }


@app.route("/boq-projects/<int:pid>/summary/extras", methods=["POST"])
@login_required
def boq_project_extras_save(pid):
    """Bulk-save the five campus-level extras on the project."""
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    csrf_protect()
    def _f(name):
        try:
            return max(0.0, float(request.form.get(name, 0) or 0))
        except (TypeError, ValueError):
            return 0.0
    ps = _f("extras_power_supply")
    ms = _f("extras_meter_service")
    ua = _f("extras_utility_admin")
    tu = _f("extras_taxes_utility")
    wt = _f("extras_withholding_tax")
    with get_db() as c:
        _ensure_boq_project_extras_schema(c)
        c.execute(
            "UPDATE boq_projects "
            "SET extras_power_supply=?, extras_meter_service=?, "
            "    extras_utility_admin=?, extras_taxes_utility=?, "
            "    extras_withholding_tax=? "
            "WHERE id=? AND user_id=?",
            (ps, ms, ua, tu, wt, pid, uid),
        )
    flash("Campus extras saved.", "success")
    return redirect(url_for("boq_project_summary", pid=pid))


@app.route("/boq-projects/<int:pid>/summary")
@login_required
def boq_project_summary(pid):
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    with get_db() as c:
        _ensure_boq_project_extras_schema(c)
        # Re-fetch the project row so the new columns are visible.
        project = c.execute(
            "SELECT * FROM boq_projects WHERE id=? AND user_id=?",
            (pid, uid),
        ).fetchone()
        per_building = c.execute(
            "SELECT b.id, b.building_name, b.primary_purpose, b.purpose_subtype, "
            "       COALESCE(SUM(i.total_amount),0) AS subtotal "
            "FROM boq_buildings b "
            "LEFT JOIN boq_floor_items i ON i.building_id=b.id "
            "WHERE b.project_id=? GROUP BY b.id ORDER BY b.id",
            (pid,),
        ).fetchall()
        per_floor = c.execute(
            "SELECT b.id AS bid, b.building_name, f.id AS fid, f.floor_name, "
            "       f.floor_level, COALESCE(SUM(i.total_amount),0) AS subtotal "
            "FROM boq_floors f "
            "JOIN boq_buildings b ON b.id=f.building_id "
            "LEFT JOIN boq_floor_items i ON i.floor_id=f.id "
            "WHERE f.project_id=? GROUP BY b.id, f.id "
            "ORDER BY b.id, f.floor_level",
            (pid,),
        ).fetchall()
        grand_row = c.execute(
            "SELECT COALESCE(SUM(total_amount),0) AS g FROM boq_floor_items WHERE project_id=?",
            (pid,),
        ).fetchone()
    floor_grand = float(grand_row["g"] or 0) if grand_row else 0.0
    extras = _read_project_extras(project)
    extras_total = sum(extras.values())
    grand_total = floor_grand + extras_total
    return render_template("boq_project_summary.html",
                           user=current_user(),
                           project=project,
                           per_building=per_building,
                           per_floor=per_floor,
                           floor_grand=floor_grand,
                           extras=extras,
                           extras_total=extras_total,
                           grand_total=grand_total)'''

data = replace_once(data, HANDLER_OLD, HANDLER_NEW,
                    "1: campus project summary handler + save route + helpers",
                    crlf_target=True)

WEB.write_bytes(data)


# ============================================================
# 2. templates/boq_project_summary.html -- extras card + form + grand total
# ============================================================
PS = REPO / "templates" / "boq_project_summary.html"
ps = PS.read_bytes()

# Add the extras card AFTER the per-floor table block.
# Anchor: the closing `</div>` of the per-floor card + `{% endblock %}`.
PS_OLD = b'''<div class="solar-card p-3">
  <h6 class="fw-bold mb-3"><i class="bi bi-layers me-1 text-warning"></i>Per-floor subtotals</h6>
  <table class="table table-sm align-middle" style="color:#e0e0f0;font-size:13px">
    <thead style="color:#9090c0;font-size:11px;text-transform:uppercase;letter-spacing:.5px">
      <tr><th>Building</th><th>Floor</th><th>Level</th><th class="text-end">Subtotal</th><th class="text-end" style="width:120px">% of Project</th></tr>
    </thead>
    <tbody>
      {% for f in per_floor %}
      <tr>
        <td>{{ f.building_name }}</td>
        <td>{{ f.floor_name }}</td>
        <td class="small text-secondary">{{ f.floor_level }}</td>
        <td class="text-end fw-bold">{{ (f.subtotal or 0)|money }}</td>
        <td class="text-end text-secondary">{% if grand_total > 0 %}{{ '%.1f'|format((f.subtotal or 0) * 100 / grand_total) }}%{% else %}\xe2\x80\x94{% endif %}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}'''

PS_NEW = b'''<div class="solar-card p-3">
  <h6 class="fw-bold mb-3"><i class="bi bi-layers me-1 text-warning"></i>Per-floor subtotals</h6>
  <table class="table table-sm align-middle" style="color:#e0e0f0;font-size:13px">
    <thead style="color:#9090c0;font-size:11px;text-transform:uppercase;letter-spacing:.5px">
      <tr><th>Building</th><th>Floor</th><th>Level</th><th class="text-end">Subtotal</th><th class="text-end" style="width:120px">% of Project</th></tr>
    </thead>
    <tbody>
      {% for f in per_floor %}
      <tr>
        <td>{{ f.building_name }}</td>
        <td>{{ f.floor_name }}</td>
        <td class="small text-secondary">{{ f.floor_level }}</td>
        <td class="text-end fw-bold">{{ (f.subtotal or 0)|money }}</td>
        <td class="text-end text-secondary">{% if grand_total > 0 %}{{ '%.1f'|format((f.subtotal or 0) * 100 / grand_total) }}%{% else %}\xe2\x80\x94{% endif %}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<div class="solar-card p-3 mt-3">
  <h6 class="fw-bold mb-3"><i class="bi bi-plug text-warning me-1"></i>Campus-level Additional Costs</h6>
  <p class="text-secondary small mb-3 no-print">
    These costs apply to the whole campus (project), not to any single building.
    They are added on top of the sum of all building totals to produce the Campus Grand Total.
  </p>
  <table class="table table-sm align-middle mb-3" style="color:#e0e0f0;font-size:14px">
    <thead style="color:#9090c0;font-size:11px;text-transform:uppercase;letter-spacing:.5px;border-bottom:2px solid #1e1e3a">
      <tr>
        <th style="width:30px">#</th>
        <th>Campus Cost Item</th>
        <th class="text-end">Amount</th>
        <th class="text-end" style="width:120px">% of Campus</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td class="text-secondary">A</td>
        <td><strong>All Building Summaries</strong><div class="text-secondary small">sum of every building total carried up from building summaries</div></td>
        <td class="text-end fw-bold">{{ (floor_grand or 0)|money }}</td>
        <td class="text-end text-secondary">{% if grand_total > 0 %}{{ '%.1f'|format((floor_grand or 0) * 100 / grand_total) }}%{% else %}\xe2\x80\x94{% endif %}</td>
      </tr>
      <tr>
        <td class="text-secondary">B</td>
        <td><strong>Power Supply</strong></td>
        <td class="text-end fw-bold">{{ (extras.power_supply or 0)|money }}</td>
        <td class="text-end text-secondary">{% if grand_total > 0 %}{{ '%.1f'|format((extras.power_supply or 0) * 100 / grand_total) }}%{% else %}\xe2\x80\x94{% endif %}</td>
      </tr>
      <tr>
        <td class="text-secondary">C</td>
        <td><strong>Meter &amp; Service Connection</strong></td>
        <td class="text-end fw-bold">{{ (extras.meter_service or 0)|money }}</td>
        <td class="text-end text-secondary">{% if grand_total > 0 %}{{ '%.1f'|format((extras.meter_service or 0) * 100 / grand_total) }}%{% else %}\xe2\x80\x94{% endif %}</td>
      </tr>
      <tr>
        <td class="text-secondary">D</td>
        <td><strong>Utility Administrative Charges</strong><div class="text-secondary small">on power supply + connection materials</div></td>
        <td class="text-end fw-bold">{{ (extras.utility_admin or 0)|money }}</td>
        <td class="text-end text-secondary">{% if grand_total > 0 %}{{ '%.1f'|format((extras.utility_admin or 0) * 100 / grand_total) }}%{% else %}\xe2\x80\x94{% endif %}</td>
      </tr>
      <tr>
        <td class="text-secondary">E</td>
        <td><strong>Taxes from Utility</strong></td>
        <td class="text-end fw-bold">{{ (extras.taxes_utility or 0)|money }}</td>
        <td class="text-end text-secondary">{% if grand_total > 0 %}{{ '%.1f'|format((extras.taxes_utility or 0) * 100 / grand_total) }}%{% else %}\xe2\x80\x94{% endif %}</td>
      </tr>
      <tr>
        <td class="text-secondary">F</td>
        <td><strong>Withholding Tax (Govt)</strong></td>
        <td class="text-end fw-bold">{{ (extras.withholding_tax or 0)|money }}</td>
        <td class="text-end text-secondary">{% if grand_total > 0 %}{{ '%.1f'|format((extras.withholding_tax or 0) * 100 / grand_total) }}%{% else %}\xe2\x80\x94{% endif %}</td>
      </tr>
      <tr style="background:rgba(245,158,11,.08);border-top:2px solid #1e1e3a">
        <td></td>
        <td class="fw-bold text-warning small" style="text-transform:uppercase;letter-spacing:.5px">CAMPUS EXTRAS SUBTOTAL (B+C+D+E+F)</td>
        <td class="text-end fw-black text-warning">{{ (extras_total or 0)|money }}</td>
        <td class="text-end text-warning fw-bold">{% if grand_total > 0 %}{{ '%.1f'|format((extras_total or 0) * 100 / grand_total) }}%{% else %}\xe2\x80\x94{% endif %}</td>
      </tr>
      <tr style="background:rgba(245,158,11,.15);border-top:3px solid var(--solar-gold,#f59e0b)">
        <td></td>
        <td class="fw-black" style="font-size:16px">CAMPUS GRAND TOTAL <span class="text-secondary small fw-normal">(A + B + C + D + E + F)</span></td>
        <td class="text-end fw-black text-warning" style="font-size:18px">{{ (grand_total)|money }}</td>
        <td class="text-end fw-black text-warning">100.0%</td>
      </tr>
    </tbody>
  </table>

  <hr class="my-4 no-print" style="border-color:#1e1e3a">

  <form method="POST" action="{{ url_for('boq_project_extras_save', pid=project.id) }}" class="row g-2 no-print">
    <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
    <div class="col-md-4 col-lg-3">
      <label class="form-label small text-secondary">Power Supply</label>
      <input type="number" step="0.01" min="0" class="form-control form-control-sm"
             name="extras_power_supply" value="{{ '%.2f'|format(extras.power_supply or 0) }}">
    </div>
    <div class="col-md-4 col-lg-3">
      <label class="form-label small text-secondary">Meter &amp; Service Connection</label>
      <input type="number" step="0.01" min="0" class="form-control form-control-sm"
             name="extras_meter_service" value="{{ '%.2f'|format(extras.meter_service or 0) }}">
    </div>
    <div class="col-md-4 col-lg-3">
      <label class="form-label small text-secondary">Utility Administrative Charges</label>
      <input type="number" step="0.01" min="0" class="form-control form-control-sm"
             name="extras_utility_admin" value="{{ '%.2f'|format(extras.utility_admin or 0) }}">
    </div>
    <div class="col-md-4 col-lg-3">
      <label class="form-label small text-secondary">Taxes from Utility</label>
      <input type="number" step="0.01" min="0" class="form-control form-control-sm"
             name="extras_taxes_utility" value="{{ '%.2f'|format(extras.taxes_utility or 0) }}">
    </div>
    <div class="col-md-4 col-lg-3">
      <label class="form-label small text-secondary">Withholding Tax (Govt)</label>
      <input type="number" step="0.01" min="0" class="form-control form-control-sm"
             name="extras_withholding_tax" value="{{ '%.2f'|format(extras.withholding_tax or 0) }}">
    </div>
    <div class="col-12 d-flex justify-content-end mt-2">
      <button class="btn btn-warning fw-bold btn-sm">
        <i class="bi bi-save me-1"></i>Save campus extras
      </button>
    </div>
  </form>
</div>

{% endblock %}'''

ps = replace_once(ps, PS_OLD, PS_NEW,
                  "2: project summary template campus extras card + form",
                  crlf_target=True)

# Also update the top-line KPI label + grand-total tfoot wording.
PS_KPI_OLD = b'    <h5 class="fw-black mb-0 mt-1"><i class="bi bi-stack text-warning me-1"></i>Final Project Summary</h5>'
PS_KPI_NEW = b'    <h5 class="fw-black mb-0 mt-1"><i class="bi bi-stack text-warning me-1"></i>Campus (Final Project) Summary</h5>'
ps = replace_once(ps, PS_KPI_OLD, PS_KPI_NEW, "2b: title -> Campus", crlf_target=True)

PS_FOOT_OLD = b'        <td colspan="3" class="text-end fw-black">PROJECT GRAND TOTAL</td>'
PS_FOOT_NEW = b'        <td colspan="3" class="text-end fw-black">SUM OF BUILDING TOTALS (campus extras added below)</td>'
ps = replace_once(ps, PS_FOOT_OLD, PS_FOOT_NEW, "2c: per-building tfoot relabel", crlf_target=True)

PS.write_bytes(ps)

print("done.")
