#!/usr/bin/env python3
"""patch_clear_synthetic_button.py -- 2026-06-22.

Adds:
  - dashboard() route now passes synth_count (admin-only).
  - new admin POST /dashboard/clear-synthetic that bulk-deletes every
    projects row whose name starts with 'SyntheticHealth-' (the hourly
    synthetic-health cron's marker prefix). Logs to marketplace_audit_log.
  - template button below.
"""
from __future__ import annotations
import sys

PATH = "web_app.py"


def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    orig_len = len(data)
    log = []

    # ---- (1) dashboard() computes synth_count for admins ----
    n_ds = (
        b"    with get_db() as c:\r\n"
        b"        raw_projects = c.execute(\r\n"
        b"            \"SELECT * FROM projects WHERE user_id=? ORDER BY updated_at DESC\",\r\n"
        b"            (uid,)).fetchall()\r\n"
        b"        open_tickets = c.execute(\r\n"
        b"            \"SELECT COUNT(*) FROM tickets WHERE user_id=? AND status='open'\",\r\n"
        b"            (uid,)).fetchone()[0]\r\n"
        b"        emails_sent  = c.execute(\r\n"
        b"            \"SELECT COUNT(*) FROM email_logs WHERE user_id=? AND status='sent'\",\r\n"
        b"            (uid,)).fetchone()[0]\r\n"
    )
    r_ds = (
        b"    with get_db() as c:\r\n"
        b"        raw_projects = c.execute(\r\n"
        b"            \"SELECT * FROM projects WHERE user_id=? ORDER BY updated_at DESC\",\r\n"
        b"            (uid,)).fetchall()\r\n"
        b"        open_tickets = c.execute(\r\n"
        b"            \"SELECT COUNT(*) FROM tickets WHERE user_id=? AND status='open'\",\r\n"
        b"            (uid,)).fetchone()[0]\r\n"
        b"        emails_sent  = c.execute(\r\n"
        b"            \"SELECT COUNT(*) FROM email_logs WHERE user_id=? AND status='sent'\",\r\n"
        b"            (uid,)).fetchone()[0]\r\n"
        b"        # 2026-06-22 (session B): admin-only count of synthetic-health monitor rows.\r\n"
        b"        try:\r\n"
        b"            synth_count = int(c.execute(\r\n"
        b"                \"SELECT COUNT(*) FROM projects WHERE name LIKE 'SyntheticHealth-%' OR name LIKE 'SyntheticHealth_%' OR name LIKE 'synthetic_health-%'\"\r\n"
        b"            ).fetchone()[0] or 0)\r\n"
        b"        except Exception:\r\n"
        b"            synth_count = 0\r\n"
    )
    if n_ds in data:
        data = data.replace(n_ds, r_ds, 1)
        log.append("(1) dashboard() computes synth_count.")
    elif b"synth_count = int(c.execute(" in data:
        log.append("(1) already wired.")
    else:
        log.append("(1) dashboard SELECT anchor NOT FOUND.")

    # ---- (2) pass synth_count to render_template -- find the dashboard return ----
    # The route returns render_template("dashboard.html", ...). We add the kwarg.
    n_rt = b"return render_template(\"dashboard.html\","
    if n_rt in data and b"synth_count=synth_count" not in data:
        # Inject right after the open paren of the render_template call.
        data = data.replace(
            n_rt,
            b"return render_template(\"dashboard.html\", synth_count=synth_count,",
            1,
        )
        log.append("(2) synth_count passed to dashboard.html.")
    elif b"synth_count=synth_count" in data:
        log.append("(2) already wired.")
    else:
        log.append("(2) dashboard render anchor NOT FOUND.")

    # ---- (3) new POST /dashboard/clear-synthetic route ----
    insert_marker = b"# === BEGIN: admin_actions_log splice ==="
    if insert_marker in data and b"@app.route(\"/dashboard/clear-synthetic\"" not in data:
        new_route = (
            b"\r\n# 2026-06-22 (session B): admin button on /dashboard that wipes the\r\n"
            b"# synthetic-health monitor's project rows so they don't pollute the UI.\r\n"
            b"@app.route(\"/dashboard/clear-synthetic\", methods=[\"POST\"])\r\n"
            b"@admin_required\r\n"
            b"def dashboard_clear_synthetic():\r\n"
            b"    csrf_protect()\r\n"
            b"    n = 0\r\n"
            b"    try:\r\n"
            b"        with get_db() as c:\r\n"
            b"            rows = c.execute(\r\n"
            b"                \"SELECT id FROM projects WHERE name LIKE 'SyntheticHealth-%' OR name LIKE 'SyntheticHealth_%' OR name LIKE 'synthetic_health-%'\"\r\n"
            b"            ).fetchall()\r\n"
            b"            n = len(rows)\r\n"
            b"            if n:\r\n"
            b"                c.execute(\r\n"
            b"                    \"DELETE FROM projects WHERE name LIKE 'SyntheticHealth-%' OR name LIKE 'SyntheticHealth_%' OR name LIKE 'synthetic_health-%'\"\r\n"
            b"                )\r\n"
            b"        try: _log_marketplace_action(\"clear_synthetic_health\", \"projects\", n, f\"deleted {n} synthetic-health project row(s)\")\r\n"
            b"        except Exception: pass\r\n"
            b"        if n:\r\n"
            b"            flash(f\"Cleared {n} synthetic-health project row(s).\", \"success\")\r\n"
            b"        else:\r\n"
            b"            flash(\"No synthetic-health rows to clear.\", \"info\")\r\n"
            b"    except Exception as _e:\r\n"
            b"        try: app.logger.exception(\"clear_synthetic failed: %s\", _e)\r\n"
            b"        except Exception: pass\r\n"
            b"        flash(f\"Could not clear synthetic-health rows: {_e!s}\", \"danger\")\r\n"
            b"    return redirect(url_for(\"dashboard\"))\r\n"
            b"\r\n"
        )
        data = data.replace(insert_marker, new_route + insert_marker, 1)
        log.append("(3) /dashboard/clear-synthetic route added.")
    elif b"@app.route(\"/dashboard/clear-synthetic\"" in data:
        log.append("(3) already added.")
    else:
        log.append("(3) insertion marker NOT FOUND.")

    if len(data) == orig_len and data == open(PATH, "rb").read():
        log.append("\nNo changes -- already patched.")
        print("\n".join(log))
        return
    with open(PATH, "wb") as fh:
        fh.write(data)
    log.append(f"\nwrote {PATH} ({orig_len} -> {len(data)} bytes)")
    print("\n".join(log))


if __name__ == "__main__":
    main()
