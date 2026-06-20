# patch_solar_report_boq_clean.py
# Phase 1 part B: same client-clean rule applied to /project/<pid>/report/boq.
# Default = client view; ?view=internal exposes Basic + Total Rate (BOM owner only).

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

if b'def report_boq(pid):' not in data:
    print("Anchor missing — bail.")
    raise SystemExit(1)

if b'# client-clean toggle for solar engineering BOQ' in data:
    print("Already patched. No changes written.")
    raise SystemExit(0)

OLD = (
    b'@app.route("/project/<int:pid>/report/boq")\r\n'
    b'@login_required\r\n'
    b'def report_boq(pid):\r\n'
    b'    gate = _paid_only(pid)\r\n'
    b'    if gate: return gate\r\n'
    b'    project = get_project(pid)\r\n'
    b'    if not project or "results" not in project["data"]:\r\n'
    b'        return redirect(url_for("project_results", pid=pid))\r\n'
    b'    return render_template("report_boq.html", user=current_user(),\r\n'
    b'                           project=project, d=project["data"],\r\n'
    b'                           r=project["data"]["results"])\r\n'
)

NEW = (
    b'@app.route("/project/<int:pid>/report/boq")\r\n'
    b'@login_required\r\n'
    b'def report_boq(pid):\r\n'
    b'    # client-clean toggle for solar engineering BOQ (master prompt s11).\r\n'
    b'    gate = _paid_only(pid)\r\n'
    b'    if gate: return gate\r\n'
    b'    project = get_project(pid)\r\n'
    b'    if not project or "results" not in project["data"]:\r\n'
    b'        return redirect(url_for("project_results", pid=pid))\r\n'
    b'    internal_view = bool(request.args.get("view") == "internal")\r\n'
    b'    if internal_view:\r\n'
    b'        try:\r\n'
    b'            from new_boq_hierarchy_schema import boq_audit\r\n'
    b'            boq_audit(get_db, session["user_id"], "boq_buildup_viewed", "solar_project", pid)\r\n'
    b'        except Exception:\r\n'
    b'            pass\r\n'
    b'    return render_template("report_boq.html", user=current_user(),\r\n'
    b'                           project=project, d=project["data"],\r\n'
    b'                           r=project["data"]["results"],\r\n'
    b'                           internal_view=internal_view,\r\n'
    b'                           can_view_buildup=True)\r\n'
)

assert data.count(OLD) == 1, f"anchor count={data.count(OLD)}"
data = data.replace(OLD, NEW)
TARGET.write_bytes(data)
print(f"OK -- patched report_boq route (+{len(NEW)-len(OLD)} bytes)")
