# new_boq_title_instructions_route.py
# Editable BOQ title + free-text instructions cell on the project overview.
# 2026-06-28 owner directive — the instructions render above the BOQ table
# on Excel / PDF exports.


@app.route("/boq-projects/<int:pid>/title-instructions", methods=["POST"])
@login_required
def boq_project_title_instructions(pid):
    uid = session["user_id"]
    _boq_project_owned_or_404(pid, uid)
    csrf_protect()
    f = request.form
    title = (f.get("project_name") or "").strip()[:300]
    instructions = (f.get("instructions") or "").strip()[:4000]
    if not title:
        flash("Title is required.", "warning")
        return redirect(url_for("boq_project_overview", pid=pid))
    with get_db() as c:
        c.execute(
            "UPDATE boq_projects SET project_name=?, instructions=?, "
            "updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
            (title, instructions, pid, uid),
        )
    try:
        from new_boq_hierarchy_schema import boq_audit
        boq_audit(get_db, uid, "boq_project_title_updated", "boq_project", pid,
                  f"title_len={len(title)} instr_len={len(instructions)}")
    except Exception:
        pass
    flash("Title and instructions saved.", "success")
    return redirect(url_for("boq_project_overview", pid=pid))
