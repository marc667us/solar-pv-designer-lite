# ─────────────────────────────────────────────────────────────────────────────
# AI-SOC — Slice 3: admin UI inside the existing Operations Centre
# ─────────────────────────────────────────────────────────────────────────────
# Per plan Slice 3 + spec §13 (SupportIncidentDashboard, IncidentDetailPanel,
# PendingApprovals, SecurityIncidentPanel). NO new portal, NO new login — these
# routes live under /admin/soc and are @admin_required + CSRF (spec line 1386).
# Read-only views + ONE admin control (set incident status) which is an operator
# action on data, not an automated remediation, so it is allowed with the SOC
# still in detection mode.
#
# Spliced by patch_soc_slice3.py (byte-level, CRLF-aware).

# Full incident status set (spec §15). The admin status control validates against
# this; open vs closed is derived from _SOC_OPEN_STATUSES (Slice 2).
_SOC_ALL_STATUSES = (
    "Detected", "Classified", "Assigned", "Investigating",
    "Automated Fix Running", "Awaiting Approval", "Fix Approved", "Fix Rejected",
    "Deploying to Staging", "Staging Verification", "Deploying to Production",
    "Monitoring", "Resolved", "Closed", "Reopened",
)


def _soc_row_to_dict(row, keys):
    if row is None:
        return None
    if hasattr(row, "keys"):
        return {k: row[k] for k in keys}
    return {k: row[i] for i, k in enumerate(keys)}


def _soc_admin_read(fn):
    """Run a read query under an admin-elevated, schema-ensured connection.
    fn(c) -> value. Returns fn's value or a default on failure (never raises)."""
    try:
        with get_db() as c:
            if _inbox_is_pg():
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            _ensure_soc_schema(c)
            return fn(c)
    except Exception:
        app.logger.exception("soc admin read failed")
        return None


def _soc_list_incidents(status=None, severity=None, limit=200):
    keys = ("id", "status", "severity", "module", "source", "tier", "title",
            "probable_cause", "fingerprint", "assigned_agent", "created_at", "updated_at")
    def _q(c):
        sql = ("SELECT id, status, severity, module, source, tier, title, "
               "probable_cause, fingerprint, assigned_agent, created_at, updated_at "
               "FROM support_incidents")
        where, params = [], []
        if status:
            where.append("status=?"); params.append(status)
        if severity:
            where.append("severity=?"); params.append(severity)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"; params.append(int(limit))
        return [_soc_row_to_dict(r, keys) for r in c.execute(sql, tuple(params)).fetchall()]
    return _soc_admin_read(_q) or []


@app.route("/admin/soc/incidents", methods=["GET"])
@admin_required
def admin_soc_incidents():
    """SupportIncidentDashboard (JSON). Optional ?status= &severity= filters."""
    status = (request.args.get("status") or "").strip() or None
    severity = (request.args.get("severity") or "").strip() or None
    incidents = _soc_list_incidents(status=status, severity=severity)
    # severity counts for the dashboard header
    def _counts(c):
        out = {}
        for r in c.execute("SELECT severity, COUNT(*) FROM support_incidents GROUP BY severity").fetchall():
            out[(r[0] if not hasattr(r, "keys") else r[0])] = int(r[1])
        return out
    return jsonify({"incidents": incidents, "count": len(incidents),
                    "by_severity": _soc_admin_read(_counts) or {}})


@app.route("/admin/soc/incidents/<int:iid>", methods=["GET"])
@admin_required
def admin_soc_incident_detail(iid):
    """IncidentDetailPanel (JSON): the incident + its events, actions, approvals."""
    inc_keys = ("id", "status", "severity", "module", "source", "tier", "title",
                "summary", "probable_cause", "fingerprint", "assigned_agent",
                "human_reviewer", "audit_reference", "created_at", "updated_at", "resolved_at")
    ev_keys = ("id", "source", "event_type", "severity", "module", "error_code", "created_at")
    ac_keys = ("id", "agent", "action_type", "mode", "status", "detail", "created_at")
    ap_keys = ("id", "requested_by", "status", "decided_by", "decided_at", "reason", "created_at")

    def _q(c):
        inc = _soc_row_to_dict(c.execute(
            "SELECT id, status, severity, module, source, tier, title, summary, "
            "probable_cause, fingerprint, assigned_agent, human_reviewer, "
            "audit_reference, created_at, updated_at, resolved_at "
            "FROM support_incidents WHERE id=?", (iid,)).fetchone(), inc_keys)
        if inc is None:
            return None
        inc["events"] = [_soc_row_to_dict(r, ev_keys) for r in c.execute(
            "SELECT id, source, event_type, severity, module, error_code, created_at "
            "FROM support_events WHERE incident_id=? ORDER BY id DESC LIMIT 200", (iid,)).fetchall()]
        inc["actions"] = [_soc_row_to_dict(r, ac_keys) for r in c.execute(
            "SELECT id, agent, action_type, mode, status, detail, created_at "
            "FROM support_actions WHERE incident_id=? ORDER BY id DESC LIMIT 200", (iid,)).fetchall()]
        inc["approvals"] = [_soc_row_to_dict(r, ap_keys) for r in c.execute(
            "SELECT id, requested_by, status, decided_by, decided_at, reason, created_at "
            "FROM support_approvals WHERE incident_id=? ORDER BY id DESC LIMIT 200", (iid,)).fetchall()]
        return inc

    inc = _soc_admin_read(_q)
    if inc is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(inc)


@app.route("/admin/soc/approvals", methods=["GET"])
@admin_required
def admin_soc_approvals():
    """PendingApprovals (JSON): approvals awaiting a human decision."""
    keys = ("id", "incident_id", "action_id", "requested_by", "status", "reason", "created_at")
    def _q(c):
        return [_soc_row_to_dict(r, keys) for r in c.execute(
            "SELECT id, incident_id, action_id, requested_by, status, reason, created_at "
            "FROM support_approvals WHERE status='pending' ORDER BY id DESC LIMIT 200").fetchall()]
    rows = _soc_admin_read(_q) or []
    return jsonify({"pending": rows, "count": len(rows)})


@app.route("/admin/soc/security", methods=["GET"])
@admin_required
def admin_soc_security():
    """SecurityIncidentPanel (JSON)."""
    keys = ("id", "incident_id", "category", "severity", "source_ip", "subject_user",
            "status", "created_at")
    def _q(c):
        return [_soc_row_to_dict(r, keys) for r in c.execute(
            "SELECT id, incident_id, category, severity, source_ip, subject_user, "
            "status, created_at FROM security_incidents ORDER BY id DESC LIMIT 200").fetchall()]
    rows = _soc_admin_read(_q) or []
    return jsonify({"security_incidents": rows, "count": len(rows)})


@app.route("/admin/soc/incidents/<int:iid>/status", methods=["POST"])
@admin_required
def admin_soc_incident_set_status(iid):
    """Operator control: set an incident's status (admin + CSRF + audit). This is
    a human action on data, not an automated remediation."""
    csrf_protect()
    new_status = (request.form.get("status") or "").strip()
    if new_status not in _SOC_ALL_STATUSES:
        return jsonify({"error": "bad_status",
                        "allowed": list(_SOC_ALL_STATUSES)}), 400
    uid = session.get("user_id")
    ok = False
    try:
        with get_db() as c:
            if _inbox_is_pg():
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            _ensure_soc_schema(c)
            resolved = ", resolved_at=CURRENT_TIMESTAMP" if new_status in ("Resolved", "Closed") else ""
            cur = c.execute(
                "UPDATE support_incidents SET status=?, human_reviewer=?, "
                "updated_at=CURRENT_TIMESTAMP" + resolved + " WHERE id=?",
                (new_status, uid, iid))
            ok = int(getattr(cur, "rowcount", 0) or 0) > 0
    except Exception:
        app.logger.exception("admin_soc_incident_set_status failed")
    if not ok:
        return jsonify({"error": "not_found_or_failed"}), 404
    try:
        log_audit(action="soc_incident_status", user_id=uid, status="success",
                  detail="incident %s -> %s" % (iid, new_status))
    except Exception:
        pass
    return jsonify({"ok": True, "incident_id": iid, "status": new_status})


@app.route("/admin/soc/dashboard", methods=["GET"])
@admin_required
def admin_soc_dashboard():
    """Server-rendered incident board inside the admin area — no new portal, no
    JS required (so every incident is visibly listed). Extends the app's
    base.html. Reuses the same data as the JSON endpoints."""
    from flask import render_template_string
    incidents = _soc_list_incidents(limit=200)
    tpl = """{% extends "base.html" %}{% block content %}
    <div class="container-fluid py-3">
      <h3 class="mb-3"><i class="bi bi-shield-exclamation me-2"></i>AI-SOC — Incidents</h3>
      <p class="text-muted small">Support &amp; security operations centre. Automation is governed by the
        <a href="{{ url_for('admin_soc_status') }}">kill switch</a>; this board is read-only + status control.</p>
      {% if not incidents %}
        <div class="alert alert-info">No incidents recorded. (The SOC records incidents only when enabled.)</div>
      {% else %}
      <table class="table table-sm table-striped align-middle">
        <thead><tr><th>#</th><th>Severity</th><th>Status</th><th>Tier</th><th>Module</th>
          <th>Title</th><th>Probable cause</th><th>Created</th></tr></thead>
        <tbody>
        {% for i in incidents %}
          <tr>
            <td>{{ i.id }}</td>
            <td><span class="badge bg-{{ 'danger' if i.severity in ['P1','P2'] else 'secondary' }}">{{ i.severity }}</span></td>
            <td>{{ i.status }}</td><td>{{ i.tier }}</td><td>{{ i.module or '-' }}</td>
            <td>{{ i.title }}</td><td class="small text-muted">{{ i.probable_cause or '-' }}</td>
            <td class="small">{{ i.created_at }}</td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
      {% endif %}
    </div>{% endblock %}"""
    return render_template_string(tpl, incidents=incidents)
