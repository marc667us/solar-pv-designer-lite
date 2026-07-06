# ─── Admin Notification Inbox + device/browser alerting ──────────────────────
# Added 2026-07-06 (owner queued feature #3). "App issues + fault notifications
# are written to an admin inbox; opt-in browser/device alerting draws the admin's
# attention when enabled."
#
# This is the ATTENTION layer, not a second fault store. Detailed faults still
# live in error_logs (with stack traces + resolve workflow); each notification
# can point back to an error_logs row via (ref_type='error_log', ref_id). The
# inbox aggregates heterogeneous producers (500s, escalations, ops probes,
# system notices) into one admin-facing stream with an unread badge.
#
# Reuses existing infra: _admin_setting / _admin_setting_set for the opt-in
# toggle (no new settings table), get_db + _PgCursorWrap for portability, and
# the base.html bell/poll/toast components for the UI.
#
# Spliced verbatim into web_app.py before `if __name__ == "__main__":`, so
# get_db, os, datetime, render_template, request, session, jsonify, redirect,
# url_for, flash, abort, csrf_protect, admin_required, current_user,
# _admin_setting, _admin_setting_set, _write_audit_event, app are all in scope.

_INBOX_ALERTS_KEY = "inbox_browser_alerts"   # admin_settings key prefix: "1" | "0"


def _inbox_is_pg():
    """Match get_db()'s backend detection exactly — a DATABASE_URL of
    `sqlite:///...` must NOT be treated as Postgres (that would pick the SERIAL
    DDL on SQLite and leave id NULL)."""
    return (os.environ.get("DATABASE_URL") or "").startswith(
        ("postgres://", "postgresql://"))


def _inbox_alerts_key():
    """Per-admin opt-in key so one admin's toggle never changes another's."""
    return _INBOX_ALERTS_KEY + ":" + str(session.get("user_id") or "0")


def _ensure_admin_notifications_table(conn):
    """Idempotent create. Branch on backend (like _ensure_admin_settings_table)
    rather than try-Postgres-first: on SQLite the Postgres DDL SUCCEEDS but
    `id SERIAL PRIMARY KEY` is treated as a plain type affinity (NOT an
    autoincrement alias for ROWID), leaving `id` NULL on every insert."""
    is_pg = _inbox_is_pg()
    id_ddl = "id SERIAL PRIMARY KEY" if is_pg else "id INTEGER PRIMARY KEY AUTOINCREMENT"
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS admin_notifications ("
            + id_ddl + ","
            "created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,"
            "source      TEXT,"
            "severity    TEXT NOT NULL DEFAULT 'info',"
            "title       TEXT NOT NULL,"
            "body        TEXT,"
            "ref_type    TEXT,"
            "ref_id      INTEGER,"
            "fingerprint TEXT,"
            "tenant_id   TEXT,"
            "read_at     TIMESTAMP,"
            "read_by     INTEGER)")
    except Exception:
        pass
    for idx in (
        "CREATE INDEX IF NOT EXISTS idx_admin_notif_created ON admin_notifications(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_admin_notif_read ON admin_notifications(read_at)",
        "CREATE INDEX IF NOT EXISTS idx_admin_notif_fp ON admin_notifications(fingerprint)",
    ):
        try:
            conn.execute(idx)
        except Exception:
            pass


def _admin_notify(source, severity, title, body="", ref_type=None, ref_id=None,
                  fingerprint=None, tenant_id=None, dedupe_minutes=10):
    """Best-effort writer for one admin-inbox notification. NEVER raises — a
    notification failure must not escalate the fault that triggered it.

    Dedupe: when `fingerprint` is given, an UNREAD row with the same fingerprint
    created within `dedupe_minutes` suppresses the new insert, so a burst of the
    same 500 doesn't flood the inbox. Returns the new row id, 0 if deduped, or
    None on failure.
    """
    try:
        sev = severity if severity in ("info", "warning", "critical") else "info"
        title = (str(title) or "Notification")[:200]
        body = (str(body) if body is not None else "")[:2000]
        is_pg = _inbox_is_pg()
        with get_db() as c:
            _ensure_admin_notifications_table(c)
            if fingerprint:
                if is_pg:
                    dup = c.execute(
                        "SELECT 1 FROM admin_notifications WHERE fingerprint=? "
                        "AND read_at IS NULL AND created_at > "
                        "(CURRENT_TIMESTAMP - INTERVAL '%d minutes') LIMIT 1"
                        % int(dedupe_minutes), (fingerprint,)).fetchone()
                else:
                    dup = c.execute(
                        "SELECT 1 FROM admin_notifications WHERE fingerprint=? "
                        "AND read_at IS NULL AND created_at > datetime('now', ?) LIMIT 1",
                        (fingerprint, "-%d minutes" % int(dedupe_minutes))).fetchone()
                if dup:
                    return 0
            cur = c.execute(
                "INSERT INTO admin_notifications "
                "(source, severity, title, body, ref_type, ref_id, fingerprint, tenant_id) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (source, sev, title, body, ref_type, ref_id, fingerprint, tenant_id))
            return getattr(cur, "lastrowid", None)
    except Exception:
        try:
            app.logger.warning("admin_notify write failed")
        except Exception:
            pass
        return None


def _inbox_alerts_enabled():
    """True when THIS admin's opt-in for browser/device alerts is on."""
    return str(_admin_setting(_inbox_alerts_key(), "0")) == "1"


def _inbox_unread_count():
    try:
        with get_db() as c:
            _ensure_admin_notifications_table(c)
            r = c.execute(
                "SELECT COUNT(*) FROM admin_notifications WHERE read_at IS NULL"
            ).fetchone()
        return int(r[0] if r else 0)
    except Exception:
        return 0


@app.route("/admin/inbox")
@admin_required
def admin_inbox():
    """Admin notification inbox — newest first, unread highlighted."""
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    per = 50
    offset = (page - 1) * per
    show = request.args.get("show", "all")  # all | unread
    rows, total, unread = [], 0, 0
    try:
        with get_db() as c:
            _ensure_admin_notifications_table(c)
            where = "WHERE read_at IS NULL" if show == "unread" else ""
            total = int(c.execute(
                "SELECT COUNT(*) FROM admin_notifications " + where).fetchone()[0])
            unread = int(c.execute(
                "SELECT COUNT(*) FROM admin_notifications WHERE read_at IS NULL"
            ).fetchone()[0])
            rows = c.execute(
                "SELECT id, created_at, source, severity, title, body, ref_type, "
                "ref_id, tenant_id, read_at FROM admin_notifications " + where +
                " ORDER BY id DESC LIMIT ? OFFSET ?", (per, offset)).fetchall()
            rows = [dict(r) for r in rows]
    except Exception:
        app.logger.exception("admin_inbox: load failed")
    has_next = (offset + per) < total
    return render_template(
        "admin_inbox.html", user=current_user(), notifications=rows,
        total=total, unread=unread, page=page, has_next=has_next, show=show,
        alerts_enabled=_inbox_alerts_enabled())


@app.route("/admin/inbox/status")
@admin_required
def admin_inbox_status():
    """Poll target for the navbar bell + browser-alert JS. Returns the unread
    count, the newest id (so the client can detect fresh arrivals), the opt-in
    flag, and up to 3 unread previews for the notification body."""
    unread, latest_id, previews = 0, 0, []
    try:
        with get_db() as c:
            _ensure_admin_notifications_table(c)
            unread = int(c.execute(
                "SELECT COUNT(*) FROM admin_notifications WHERE read_at IS NULL"
            ).fetchone()[0])
            mx = c.execute("SELECT MAX(id) FROM admin_notifications").fetchone()[0]
            latest_id = int(mx or 0)
            pv = c.execute(
                "SELECT id, severity, title FROM admin_notifications "
                "WHERE read_at IS NULL ORDER BY id DESC LIMIT 3").fetchall()
            previews = [{"id": r[0], "severity": r[1], "title": r[2]} for r in pv]
    except Exception:
        pass
    return jsonify({"unread": unread, "latest_id": latest_id,
                    "alerts_enabled": _inbox_alerts_enabled(), "latest": previews})


@app.route("/admin/inbox/<int:nid>/read", methods=["POST"])
@admin_required
def admin_inbox_mark_read(nid):
    csrf_protect()
    try:
        with get_db() as c:
            _ensure_admin_notifications_table(c)
            c.execute(
                "UPDATE admin_notifications SET read_at=CURRENT_TIMESTAMP, read_by=? "
                "WHERE id=? AND read_at IS NULL",
                (session.get("user_id"), nid))
    except Exception:
        app.logger.exception("admin_inbox_mark_read failed")
    try:
        _write_audit_event("admin_inbox_read", user_id=session.get("user_id"))
    except Exception:
        pass
    if request.is_json or request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True, "unread": _inbox_unread_count()})
    return redirect(url_for("admin_inbox"))


@app.route("/admin/inbox/read-all", methods=["POST"])
@admin_required
def admin_inbox_mark_all_read():
    csrf_protect()
    try:
        with get_db() as c:
            _ensure_admin_notifications_table(c)
            c.execute(
                "UPDATE admin_notifications SET read_at=CURRENT_TIMESTAMP, read_by=? "
                "WHERE read_at IS NULL", (session.get("user_id"),))
    except Exception:
        app.logger.exception("admin_inbox_mark_all_read failed")
    try:
        _write_audit_event("admin_inbox_read_all", user_id=session.get("user_id"))
    except Exception:
        pass
    flash("All notifications marked as read.", "success")
    return redirect(url_for("admin_inbox"))


@app.route("/admin/inbox/settings", methods=["POST"])
@admin_required
def admin_inbox_settings():
    """Toggle the browser/device alert opt-in."""
    csrf_protect()
    enabled = "1" if (request.form.get("browser_alerts") in ("1", "on", "true")) else "0"
    _admin_setting_set(_inbox_alerts_key(), enabled)
    try:
        _write_audit_event("admin_inbox_settings", user_id=session.get("user_id"))
    except Exception:
        pass
    flash("Browser alerts " + ("enabled." if enabled == "1" else "disabled."), "info")
    return redirect(url_for("admin_inbox"))


@app.route("/admin/inbox/test", methods=["POST"])
@admin_required
def admin_inbox_test():
    """Emit a sample notification so the admin can verify the bell + alerting."""
    csrf_protect()
    nid = _admin_notify(
        "test", "info", "Test notification",
        "This is a test alert from the admin inbox settings. If browser alerts "
        "are enabled and permitted, your device should have notified you.")
    if request.is_json:
        return jsonify({"ok": True, "id": nid})
    flash("Test notification created.", "success")
    return redirect(url_for("admin_inbox"))
