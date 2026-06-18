# ─── Routes — Technical Support Role (installation-staff assignments) ─────────
# Parallel to procurement_specialist (Slice 7). Admin promotes any solar user
# into role='technical_support'. Technical-support staff can review approved
# installers and the queue of completed designs that may need install dispatch.
# Admin still owns the promote/demote action.


def tech_support_role_required(f):
    """Decorator: allows is_admin=1 OR role='technical_support'.
    Anonymous → /login. Authenticated-but-wrong-role → 403."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        u = current_user()
        if not u:
            return redirect(url_for("login"))
        if u["is_admin"]:
            return f(*args, **kwargs)
        if (u["role"] or "") == "technical_support":
            return f(*args, **kwargs)
        abort(403)
    return decorated


@app.route("/admin/marketplace/staff/<int:uid>/promote-tech-support", methods=["POST"])
@admin_required
def admin_marketplace_promote_tech_support(uid):
    csrf_protect()
    with get_db() as c:
        row = c.execute("SELECT id, username, role FROM users WHERE id=?", (uid,)).fetchone()
        if not row:
            abort(404)
        if (row["role"] or "") == "supplier_admin":
            flash("Cannot elect a supplier_admin as technical support — "
                  "demote them from supplier_admin first.", "danger")
            return redirect(url_for("admin_marketplace_staff"))
        c.execute("UPDATE users SET role='technical_support' WHERE id=?", (uid,))
    try:
        _log_marketplace_action(
            "promote_tech_support", "user", uid,
            f"{row['username']} (was role='{row['role'] or ''}')"
        )
    except Exception:
        pass
    flash(f"Elected '{row['username']}' as technical support for installation staff assignments.", "success")
    return redirect(url_for("admin_marketplace_staff"))


@app.route("/admin/marketplace/staff/<int:uid>/demote-tech-support", methods=["POST"])
@admin_required
def admin_marketplace_demote_tech_support(uid):
    csrf_protect()
    with get_db() as c:
        row = c.execute("SELECT id, username, role FROM users WHERE id=?", (uid,)).fetchone()
        if not row:
            abort(404)
        if (row["role"] or "") != "technical_support":
            flash("User is not currently technical support.", "warning")
            return redirect(url_for("admin_marketplace_staff"))
        c.execute("UPDATE users SET role='' WHERE id=?", (uid,))
    try:
        _log_marketplace_action("demote_tech_support", "user", uid, row["username"])
    except Exception:
        pass
    flash(f"Removed technical-support role from '{row['username']}'.", "success")
    return redirect(url_for("admin_marketplace_staff"))


@app.route("/installation-support")
@tech_support_role_required
def support_dashboard():
    """Technical-support landing — approved installers + designs awaiting
    install dispatch. Admins can view too (decorator allows is_admin)."""
    with get_db() as c:
        approved_installers = c.execute(
            "SELECT id, company_name, contact_name, email, phone, country, "
            "       regions, years_exp, staff_count, specialties, max_project_kw, "
            "       ai_grade, created_at "
            "FROM installers WHERE status='approved' "
            "ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
        pending_installers = c.execute(
            "SELECT COUNT(*) FROM installers WHERE status='pending'"
        ).fetchone()[0]
        # Completed-design queue (stage='results' means the design is finalised
        # and the project is ready to be handed to an installer). LIMIT 50 so
        # the page stays snappy even when the queue grows.
        ready_for_dispatch = c.execute(
            "SELECT p.id, p.name AS project_name, p.updated_at, "
            "       u.username AS owner "
            "FROM projects p LEFT JOIN users u ON u.id=p.user_id "
            "WHERE p.stage='results' "
            "ORDER BY p.updated_at DESC LIMIT 50"
        ).fetchall()
    return render_template(
        "support_dashboard.html",
        user=current_user(),
        approved_installers=approved_installers,
        pending_installers=pending_installers,
        ready_for_dispatch=ready_for_dispatch,
    )
