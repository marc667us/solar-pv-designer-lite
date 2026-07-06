# ─────────────────────────────────────────────────────────────────────────────
# "Clear All" for the admin dashboard alert indicators (owner directive 2026-07-06).
#
# Resets the dashboard's notification/alert indicators (the navbar bell badge, the
# "Notifications" tile, and the browser/device alert stream) by marking every
# admin notification read in one shot, then returns to the dashboard.
#
# Deliberately does NOT touch ticket / feedback / lead records: the Open Tickets,
# New Feedback and New Leads KPI cards reflect real pending work, and silently
# zeroing them would hide outstanding items. If the owner wants those "new"
# counters resettable too, that needs a per-admin "seen-at" timestamp — a separate
# gated change.
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/admin/indicators/clear", methods=["POST"])
@admin_required
def admin_indicators_clear():
    csrf_protect()
    cleared = 0
    try:
        with get_db() as c:
            _ensure_admin_notifications_table(c)
            cur = c.execute(
                "UPDATE admin_notifications SET read_at=CURRENT_TIMESTAMP, read_by=? "
                "WHERE read_at IS NULL", (session.get("user_id"),))
            try:
                cleared = int(getattr(cur, "rowcount", 0) or 0)
            except Exception:
                cleared = 0
    except Exception:
        app.logger.exception("admin_indicators_clear failed")
    try:
        _write_audit_event("admin_indicators_clear", user_id=session.get("user_id"))
    except Exception:
        pass
    if cleared > 0:
        flash("Dashboard alert indicators cleared (%d notification%s marked read)."
              % (cleared, "" if cleared == 1 else "s"), "success")
    else:
        flash("No alert indicators to clear — you're all caught up.", "info")
    return redirect(url_for("admin_dashboard"))
