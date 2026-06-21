# new_boq_project_edit_delete_routes.py
# Project-level Edit / Delete / Start-all-over routes.
#
# These three actions were missing -- once a project was created the
# owner had no way to rename it, clear its items, or get rid of it
# entirely. This file adds:
#
#   GET  /boq-projects/<pid>/edit   -- edit form (name / client / location / project_type)
#   POST /boq-projects/<pid>/edit   -- save changes
#   POST /boq-projects/<pid>/reset  -- clear all line items + rate-buildup rows
#                                      across the project (keeps buildings + floors)
#   POST /boq-projects/<pid>/delete -- delete the project + cascade everything
#
# All three enforce ownership through _boq_project_owned_or_404.


@app.route("/boq-projects/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def boq_project_edit(pid):
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    if request.method == "POST":
        csrf_protect()
        f = request.form
        name = (f.get("project_name") or "").strip()[:300]
        client = (f.get("client_name") or "").strip()[:300]
        location = (f.get("location") or "").strip()[:300]
        ptype = (f.get("project_type") or "single_building").strip()
        ext_works = 1 if f.get("external_works_included") else 0
        infra = 1 if f.get("infrastructure_included") else 0
        if not name:
            flash("Project name is required.", "warning")
            return redirect(url_for("boq_project_edit", pid=pid))
        with get_db() as c:
            c.execute(
                "UPDATE boq_projects SET project_name=?, client_name=?, location=?, "
                "project_type=?, external_works_included=?, infrastructure_included=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
                (name, client, location, ptype, ext_works, infra, pid, uid),
            )
        try:
            from new_boq_hierarchy_schema import boq_audit
            boq_audit(get_db, uid, "boq_project_edited", "boq_project", pid)
        except Exception:
            pass
        flash(f"Project '{name}' updated.", "success")
        return redirect(url_for("boq_project_overview", pid=pid))
    return render_template(
        "boq_project_edit.html",
        user=current_user(),
        project=project,
    )


@app.route("/boq-projects/<int:pid>/reset", methods=["POST"])
@login_required
def boq_project_reset(pid):
    """Start all over -- delete every line item + rate-buildup row in the
    project but KEEP the project, buildings and floors. Owner can then
    re-pick templates / re-add items from scratch."""
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    csrf_protect()
    confirm = (request.form.get("confirm") or "").strip()
    if confirm != "RESET":
        flash("Type RESET to confirm starting over.", "warning")
        return redirect(url_for("boq_project_overview", pid=pid))
    with get_db() as c:
        # Delete rate-buildup rows first (FK ON DELETE CASCADE should handle
        # it too, but be explicit so older databases without FK enforcement
        # don't leak orphans).
        c.execute(
            "DELETE FROM boq_floor_rate_buildup WHERE project_id=?",
            (pid,),
        )
        c.execute(
            "DELETE FROM boq_floor_items WHERE project_id=?",
            (pid,),
        )
        c.execute(
            "UPDATE boq_projects SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (pid,),
        )
    try:
        from new_boq_hierarchy_schema import boq_audit
        boq_audit(get_db, uid, "boq_project_reset", "boq_project", pid,
                  f"all line items cleared for {project['project_name']}")
    except Exception:
        pass
    flash(f"Project '{project['project_name']}' has been reset -- every "
          f"line item cleared. Buildings and floors are intact; pick a "
          f"template or open a section to start adding lines.", "success")
    return redirect(url_for("boq_project_overview", pid=pid))


@app.route("/boq-projects/<int:pid>/delete", methods=["POST"])
@login_required
def boq_project_delete(pid):
    """Delete the project and EVERYTHING under it (buildings, floors,
    items, rate build-up). The FOREIGN KEY ON DELETE CASCADE chain handles
    the cascade -- we delete explicitly anyway in case SQLite FK
    enforcement is off."""
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    csrf_protect()
    confirm = (request.form.get("confirm") or "").strip()
    if confirm != "DELETE":
        flash("Type DELETE to confirm permanent removal.", "warning")
        return redirect(url_for("boq_project_overview", pid=pid))
    name = project["project_name"]
    with get_db() as c:
        c.execute("DELETE FROM boq_floor_rate_buildup WHERE project_id=?", (pid,))
        c.execute("DELETE FROM boq_floor_items WHERE project_id=?", (pid,))
        c.execute("DELETE FROM boq_floors WHERE project_id=?", (pid,))
        c.execute("DELETE FROM boq_buildings WHERE project_id=?", (pid,))
        c.execute("DELETE FROM boq_projects WHERE id=? AND user_id=?", (pid, uid))
    try:
        from new_boq_hierarchy_schema import boq_audit
        boq_audit(get_db, uid, "boq_project_deleted", "boq_project", pid,
                  f"deleted {name}")
    except Exception:
        pass
    flash(f"Project '{name}' deleted.", "success")
    return redirect(url_for("boq_projects_list"))
