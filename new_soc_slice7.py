# ─────────────────────────────────────────────────────────────────────────────
# AI-SOC — Slice 7: Tier 3 repair PACKAGE + human approval gate
# ─────────────────────────────────────────────────────────────────────────────
# Per plan Slice 7 + spec §10 (issue package, lines 1814-1830) + the inviolable
# rule "Do not allow Claude Code to commit directly to the production branch"
# (spec line 574) / "Production changes are not deployed blindly".
#
# The Tier-3 agent PRODUCES a structured repair package and records a PENDING
# approval + a 'proposed' deployment_changes row. It NEVER deploys. There is
# deliberately NO function anywhere in the AI-SOC that triggers a production
# deploy — production remains the existing, human-run `Force Render Deploy`
# workflow. Approving an approval marks intent; it does NOT ship anything.
#
# Spliced by patch_soc_slice7.py (byte-level, CRLF-aware).


def soc_tier3_build_repair_package(incident_id):
    """Build the structured issue package (spec §10) for a human/Claude-Code to
    action. Deterministic, read-mostly, NEVER deploys. Returns a dict or None."""
    try:
        if not soc_enabled():
            return None
        diag = soc_tier2_diagnose(incident_id) or {}   # Slice 6 (read-only)
        with get_db() as c:
            if _inbox_is_pg():
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            row = c.execute(
                "SELECT id, module, severity, source, tier, title, summary, "
                "probable_cause FROM support_incidents WHERE id=?", (incident_id,)).fetchone()
            if row is None:
                return None
            keys = ("id", "module", "severity", "source", "tier", "title",
                    "summary", "probable_cause")
            inc = {k: (row[k] if hasattr(row, "keys") else row[i]) for i, k in enumerate(keys)}
            ev_rows = c.execute(
                "SELECT event_type, error_code, payload FROM support_events "
                "WHERE incident_id=? ORDER BY id DESC LIMIT 20", (incident_id,)).fetchall()
        logs = []
        for r in ev_rows:
            logs.append({"event_type": (r[0] if not hasattr(r, "keys") else r["event_type"]),
                         "error_code": (r[1] if not hasattr(r, "keys") else r["error_code"])})

        module = inc.get("module")
        return {
            "incident_id": incident_id,
            "error_details": inc.get("title"),
            "stack_trace": None,                       # captured by error_logs, not stored here
            "module": module,
            "logs": logs,
            "repro_steps": "Reproduce the request that hit %s and observe the failure." % (module or "the module"),
            "expected": "The endpoint returns a successful response.",
            "actual": inc.get("summary") or "Failure recorded by the SOC.",
            "severity": inc.get("severity"),
            "risk_classification": diag.get("risk_level", "medium"),
            "related_files": ["web_app.py"],           # single-file app (ADR-0001)
            "related_endpoint": module,
            "related_tables": [],
            "tenant_impact": "unknown — verify tenant scoping",
            "proposed_tests": [
                "Regression test that the failing path in %s returns 2xx." % (module or "?"),
                "Guard test for the error condition (%s)." % (inc.get("probable_cause") or "root cause"),
            ],
            "proposed_fix": diag.get("proposed_fix"),
            "rollback_plan": diag.get("rollback_plan"),
        }
    except Exception:
        return None


def soc_tier3_open_repair(incident_id, requested_by="tier3"):
    """Record a Tier-3 repair request: a 'proposed' deployment_changes row + a
    PENDING support_approvals row + a 'proposed' support_actions row carrying the
    package. Opens NO deploy. Returns {approval_id, deployment_change_id, package}
    or None. Gated on soc_enabled. NEVER raises."""
    try:
        if not soc_enabled():
            return None
        pkg = soc_tier3_build_repair_package(incident_id)
        if pkg is None:
            return None
        approval_id = None
        dc_id = None
        with get_db() as c:
            if _inbox_is_pg():
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            _ensure_soc_schema(c)
            cur = c.execute(
                "INSERT INTO deployment_changes (incident_id, status, notes) "
                "VALUES (?,?,?)",
                (incident_id, "proposed", "Tier-3 repair package; awaiting human approval + manual deploy"))
            try:
                dc_id = int(getattr(cur, "lastrowid", 0) or 0)
            except Exception:
                dc_id = None
            cur = c.execute(
                "INSERT INTO support_approvals (incident_id, requested_by, status, reason) "
                "VALUES (?,?,?,?)",
                (incident_id, requested_by, "pending",
                 "Approve the Tier-3 repair package. Approval does NOT deploy; a human runs Force Render Deploy."))
            try:
                approval_id = int(getattr(cur, "lastrowid", 0) or 0)
            except Exception:
                approval_id = None
        # record the package as a proposed action (never executed)
        try:
            _soc_record_action(incident_id, "tier3", "repair_package", "proposed",
                               "proposed", "approval=%s dc=%s fix=%s" %
                               (approval_id, dc_id, pkg.get("proposed_fix")))
            _soc_agent_run("tier3", incident_id, "succeeded")
        except Exception:
            pass
        return {"approval_id": approval_id, "deployment_change_id": dc_id, "package": pkg}
    except Exception:
        return None


def soc_decide_approval(approval_id, approve, user_id=None, reason=None):
    """Human decision on a pending approval. Sets approved/rejected — and does
    NOTHING ELSE. There is no deploy here by design: an approval records intent;
    a human still runs the production deploy workflow separately.
    Returns bool ok. NEVER raises."""
    try:
        status = "approved" if approve else "rejected"
        with get_db() as c:
            if _inbox_is_pg():
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            _ensure_soc_schema(c)
            cur = c.execute(
                "UPDATE support_approvals SET status=?, decided_by=?, "
                "decided_at=CURRENT_TIMESTAMP, reason=COALESCE(?, reason) "
                "WHERE id=? AND status='pending'",
                (status, user_id, reason, approval_id))
            ok = int(getattr(cur, "rowcount", 0) or 0) > 0
        try:
            log_audit(action="soc_approval_decision", user_id=user_id, status=status,
                      detail="approval %s -> %s (no deploy performed)" % (approval_id, status))
        except Exception:
            pass
        return ok
    except Exception:
        return False


@app.route("/admin/soc/approvals/<int:aid>/decide", methods=["POST"])
@admin_required
def admin_soc_approval_decide(aid):
    """Approve/reject a pending approval (admin + CSRF + audit). This NEVER
    deploys — production ships only via the human-run Force Render Deploy."""
    csrf_protect()
    decision = (request.form.get("decision") or "").strip().lower()
    if decision not in ("approve", "reject"):
        return jsonify({"error": "decision must be approve|reject"}), 400
    ok = soc_decide_approval(aid, decision == "approve",
                             user_id=session.get("user_id"),
                             reason=(request.form.get("reason") or None))
    if not ok:
        return jsonify({"error": "not_found_or_not_pending"}), 404
    return jsonify({"ok": True, "approval_id": aid,
                    "status": "approved" if decision == "approve" else "rejected",
                    "note": "Approval recorded. Production deploy is a separate, human-run step."})
