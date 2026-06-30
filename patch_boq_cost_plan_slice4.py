"""Slice 4 -- Cost plan / cash flow (2026-06-30 owner directive).

Adds:
  1. New table boq_cost_plan_months. Lazy CREATE TABLE IF NOT EXISTS
     fires on first request so no migration ceremony is needed. Both
     SQLite (local) and Postgres (Render) variants.
  2. Three routes in web_app.py:
       GET  /boq-projects/<pid>/cost-plan        -- render editor
       POST /boq-projects/<pid>/cost-plan/save   -- bulk upsert
       POST /boq-projects/<pid>/cost-plan/seed   -- auto-distribute
  3. "Cost Plan" link on /boq-projects/<pid>/summary so users can
     reach it.

The new template boq_cost_plan.html ships separately.

Re-runnable byte patch. Compile-checked.
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
        sys.exit(f"  {label}: expected exactly 1 OLD match, found {n}")
    print(f"  {label}: patched")
    return d.replace(old_c, new_c, 1)


# ============================================================
# 1. web_app.py -- add helpers + 3 routes BEFORE boq_project_summary
# ============================================================
WEB = REPO / "web_app.py"
web = WEB.read_bytes()

# Inject right BEFORE the boq_project_summary route (so the route order
# stays sane: cost-plan routes for a project then the summary route).
# Anchor: the building-summary route (added earlier in this session)
# directly precedes the project-summary route.
ANCHOR_OLD = b'@app.route("/boq-projects/<int:pid>/summary")\r\n@login_required\r\ndef boq_project_summary(pid):\r\n'

INJECT = b'''def _ensure_boq_cost_plan_schema(c):
    """Lazy create-if-missing for the cost plan table. SQLite + Postgres."""
    if bool(os.environ.get("DATABASE_URL")):
        c.execute(
            "CREATE TABLE IF NOT EXISTS boq_cost_plan_months ("
            "id SERIAL PRIMARY KEY, "
            "project_id INTEGER NOT NULL REFERENCES boq_projects(id) ON DELETE CASCADE, "
            "month_index INTEGER NOT NULL, "
            "month_label VARCHAR(80) DEFAULT '', "
            "planned_amount REAL DEFAULT 0, "
            "actual_amount REAL DEFAULT 0, "
            "notes TEXT DEFAULT '', "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "UNIQUE (project_id, month_index))"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_boq_cost_plan_project ON boq_cost_plan_months(project_id)"
        )
    else:
        c.execute(
            "CREATE TABLE IF NOT EXISTS boq_cost_plan_months ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "project_id INTEGER NOT NULL, "
            "month_index INTEGER NOT NULL, "
            "month_label TEXT DEFAULT '', "
            "planned_amount REAL DEFAULT 0, "
            "actual_amount REAL DEFAULT 0, "
            "notes TEXT DEFAULT '', "
            "created_at TEXT DEFAULT CURRENT_TIMESTAMP, "
            "updated_at TEXT DEFAULT CURRENT_TIMESTAMP, "
            "UNIQUE (project_id, month_index), "
            "FOREIGN KEY (project_id) REFERENCES boq_projects(id) ON DELETE CASCADE)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_boq_cost_plan_project ON boq_cost_plan_months(project_id)"
        )


@app.route("/boq-projects/<int:pid>/cost-plan", methods=["GET"])
@login_required
def boq_cost_plan(pid):
    """Render the cost plan / cash flow editor. Lazy-creates the
    underlying table on first hit."""
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    with get_db() as c:
        _ensure_boq_cost_plan_schema(c)
        rows = c.execute(
            "SELECT month_index, month_label, planned_amount, actual_amount, notes "
            "FROM boq_cost_plan_months WHERE project_id=? "
            "ORDER BY month_index",
            (pid,),
        ).fetchall()
        grand_row = c.execute(
            "SELECT COALESCE(SUM(total_amount),0) AS g FROM boq_floor_items WHERE project_id=?",
            (pid,),
        ).fetchone()
    months = [
        {
            "month_index": int(r["month_index"]),
            "month_label": r["month_label"] or "",
            "planned_amount": float(r["planned_amount"] or 0),
            "actual_amount": float(r["actual_amount"] or 0),
            "notes": r["notes"] or "",
        }
        for r in rows
    ]
    grand_total = float(grand_row["g"] or 0) if grand_row else 0.0
    total_planned = sum(m["planned_amount"] for m in months)
    total_actual = sum(m["actual_amount"] for m in months)
    return render_template(
        "boq_cost_plan.html",
        user=current_user(),
        project=project,
        months=months,
        grand_total=grand_total,
        total_planned=total_planned,
        total_actual=total_actual,
    )


@app.route("/boq-projects/<int:pid>/cost-plan/seed", methods=["POST"])
@login_required
def boq_cost_plan_seed(pid):
    """Auto-distribute the project grand total evenly across N months.
    Existing rows are CLEARED before seeding -- this is destructive on
    purpose, used only when the user explicitly clicks 'Generate' or
    'Reset & reseed'."""
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    csrf_protect()
    try:
        n = int(request.form.get("n_months", 12))
    except (TypeError, ValueError):
        n = 12
    n = max(1, min(60, n))
    start_label = (request.form.get("start_label", "") or "").strip()
    with get_db() as c:
        _ensure_boq_cost_plan_schema(c)
        c.execute("DELETE FROM boq_cost_plan_months WHERE project_id=?", (pid,))
        grand_row = c.execute(
            "SELECT COALESCE(SUM(total_amount),0) AS g FROM boq_floor_items WHERE project_id=?",
            (pid,),
        ).fetchone()
        grand_total = float(grand_row["g"] or 0) if grand_row else 0.0
        per_month = grand_total / n if n > 0 else 0.0
        for i in range(1, n + 1):
            label = f"{start_label} Month {i}".strip() if start_label else f"Month {i}"
            c.execute(
                "INSERT INTO boq_cost_plan_months "
                "(project_id, month_index, month_label, planned_amount, actual_amount, notes) "
                "VALUES (?,?,?,?,?,?)",
                (pid, i, label, per_month, 0.0, ""),
            )
    flash(f"Cost plan seeded with {n} months at {per_month:,.2f} each.", "success")
    return redirect(url_for("boq_cost_plan", pid=pid))


@app.route("/boq-projects/<int:pid>/cost-plan/save", methods=["POST"])
@login_required
def boq_cost_plan_save(pid):
    """Bulk upsert of the cost plan rows submitted from the form."""
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    csrf_protect()
    months = request.form.getlist("month_index[]")
    labels = request.form.getlist("month_label[]")
    planned = request.form.getlist("planned_amount[]")
    actual = request.form.getlist("actual_amount[]")
    notes = request.form.getlist("notes[]")
    updated = 0
    with get_db() as c:
        _ensure_boq_cost_plan_schema(c)
        for i, mi in enumerate(months):
            try:
                mi_int = int(mi)
            except (TypeError, ValueError):
                continue
            label = (labels[i] if i < len(labels) else "") or ""
            try:
                p = float(planned[i]) if i < len(planned) and planned[i] != "" else 0.0
            except (TypeError, ValueError):
                p = 0.0
            try:
                a = float(actual[i]) if i < len(actual) and actual[i] != "" else 0.0
            except (TypeError, ValueError):
                a = 0.0
            note = (notes[i] if i < len(notes) else "") or ""
            # Upsert by (project_id, month_index). SQLite supports
            # INSERT OR REPLACE; Postgres needs ON CONFLICT.
            if bool(os.environ.get("DATABASE_URL")):
                c.execute(
                    "INSERT INTO boq_cost_plan_months "
                    "(project_id, month_index, month_label, planned_amount, actual_amount, notes) "
                    "VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT (project_id, month_index) DO UPDATE SET "
                    "month_label=EXCLUDED.month_label, "
                    "planned_amount=EXCLUDED.planned_amount, "
                    "actual_amount=EXCLUDED.actual_amount, "
                    "notes=EXCLUDED.notes, "
                    "updated_at=CURRENT_TIMESTAMP",
                    (pid, mi_int, label, p, a, note),
                )
            else:
                c.execute(
                    "INSERT OR REPLACE INTO boq_cost_plan_months "
                    "(project_id, month_index, month_label, planned_amount, actual_amount, notes, updated_at) "
                    "VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                    (pid, mi_int, label, p, a, note),
                )
            updated += 1
    flash(f"Cost plan saved ({updated} month{'s' if updated != 1 else ''}).", "success")
    return redirect(url_for("boq_cost_plan", pid=pid))


@app.route("/boq-projects/<int:pid>/summary")
@login_required
def boq_project_summary(pid):
'''

INJECT_CRLF = INJECT.replace(b"\n", b"\r\n")
if INJECT_CRLF in web:
    print("  Slice4: web_app.py routes already injected, skipping")
else:
    if ANCHOR_OLD not in web:
        sys.exit("  Slice4: anchor not found")
    web = web.replace(ANCHOR_OLD, INJECT_CRLF, 1)
    print("  Slice4: web_app.py routes injected")


# ============================================================
# 2. templates/boq_project_summary.html -- add Cost Plan button
# ============================================================
PS = REPO / "templates" / "boq_project_summary.html"
ps = PS.read_bytes()  # CRLF

PS_OLD = b'    <h5 class="fw-black mb-0 mt-1"><i class="bi bi-stack text-warning me-1"></i>Final Project Summary</h5>'
PS_NEW = b'''    <h5 class="fw-black mb-0 mt-1"><i class="bi bi-stack text-warning me-1"></i>Final Project Summary</h5>
    <div class="mt-2">
      <a href="{{ url_for('boq_cost_plan', pid=project.id) }}" class="btn btn-outline-warning btn-sm">
        <i class="bi bi-calendar3 me-1"></i>Cost Plan / Cash Flow
      </a>
    </div>'''
ps = replace_once(ps, PS_OLD, PS_NEW, "2: Cost Plan link on project summary", crlf_target=True)
PS.write_bytes(ps)


WEB.write_bytes(web)
print("done.")
