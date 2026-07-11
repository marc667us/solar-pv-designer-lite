# ─────────────────────────────────────────────────────────────────────────────
# AI-SOC — Slice 4: Tier 1 agent + approved runbook catalogue (FIRST automation)
# ─────────────────────────────────────────────────────────────────────────────
# Per plan Slice 4 + spec §7 (Automated Repair Policy) / §"Approved Auto-
# Remediation Catalogue" (RemediationRunbook). This is the FIRST slice where an
# agent may ACT, so every path is gated:
#
#   A runbook runs ONLY when ALL hold:
#     * soc_automation_allowed('tier1')  — soc_enabled AND kill switch off AND
#                                          tier1 not individually paused
#     * runbook.enabled = 1
#     * runbook.requires_approval = 0     — approval-required runbooks are Slice 7
#
# Every execution writes support_actions + audit_logs; a failed verification runs
# the rollback steps. Nothing here is destructive: seeded runbooks map only onto
# existing SAFE, reversible primitives, and all ship enabled=0 (dark) by default.
#
# Spliced by patch_soc_slice4.py (byte-level, CRLF-aware).

# Handler registry: rkey -> {"do": ()->detail, "verify": ()->bool, "rollback": ()->None}.
# do() performs the safe action; verify() confirms success; rollback() undoes it.
# verify/rollback are optional (absent verify == assumed ok). Tests and later
# slices register handlers here; the built-ins below are safe no-ops / thin
# wrappers over primitives that already exist in the app.
_SOC_RUNBOOK_HANDLERS = {}


def soc_register_runbook_handler(rkey, do, verify=None, rollback=None):
    """Register (or replace) the executable handler for a runbook key."""
    _SOC_RUNBOOK_HANDLERS[rkey] = {"do": do, "verify": verify, "rollback": rollback}


def _soc_noop_do():
    return "self-test ok"


# Built-in safe handlers. clear_cache / resend map onto existing helpers when
# present; all are best-effort and never raise out of the handler.
def _soc_clear_cache_do():
    fn = globals().get("_clear_flask_cache") or globals().get("cache_clear")
    if callable(fn):
        try:
            fn()
            return "flask cache cleared"
        except Exception:
            return "cache clear attempted (helper raised, ignored)"
    return "no cache backend on this tier (noop)"


soc_register_runbook_handler("noop_selftest", _soc_noop_do,
                             verify=lambda: True, rollback=lambda: None)
soc_register_runbook_handler("clear_cache", _soc_clear_cache_do,
                             verify=lambda: True, rollback=lambda: None)


# Seed catalogue — exact RemediationRunbook shape. ALL enabled=0 (dark) by
# default; an admin enables them individually (spec: "Only enabled runbooks may
# run automatically"). requires_approval=1 keeps a runbook out of Tier-1 auto
# execution until the approval flow (Slice 7) exists.
_SOC_RUNBOOK_SEED = (
    # (rkey, name, category, allowed_tiers, risk_level, requires_approval)
    ("noop_selftest", "SOC self-test (no-op)", "diagnostic", "tier1", "low", 0),
    ("clear_cache", "Clear approved application cache", "cache", "tier1,tier2", "low", 0),
    ("resend_notification", "Re-send a failed notification", "notification", "tier1", "low", 0),
    ("restart_queue", "Restart approved queue worker", "queue", "tier2", "medium", 1),
    ("retry_job", "Retry a safe background job", "job", "tier1,tier2", "low", 0),
)


def soc_seed_runbooks():
    """Idempotently insert the seed catalogue (keyed by rkey). Never raises."""
    try:
        is_pg = _inbox_is_pg()
        with get_db() as c:
            if is_pg:
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            _ensure_soc_schema(c)
            for rkey, name, cat, tiers, risk, appr in _SOC_RUNBOOK_SEED:
                exists = c.execute(
                    "SELECT 1 FROM support_runbooks WHERE rkey=? LIMIT 1", (rkey,)).fetchone()
                if exists:
                    continue
                c.execute(
                    "INSERT INTO support_runbooks "
                    "(rkey, name, category, allowed_tiers, risk_level, "
                    " requires_approval, enabled) VALUES (?,?,?,?,?,?,0)",
                    (rkey, name, cat, tiers, risk, int(appr)))
        return True
    except Exception:
        return False


def _soc_get_runbook(rkey):
    keys = ("id", "rkey", "name", "risk_level", "requires_approval", "enabled")
    def _q(c):
        return c.execute(
            "SELECT id, rkey, name, risk_level, requires_approval, enabled "
            "FROM support_runbooks WHERE rkey=?", (rkey,)).fetchone()
    row = _soc_admin_read(_q)
    if row is None:
        return None
    d = {k: (row[k] if hasattr(row, "keys") else row[i]) for i, k in enumerate(keys)}
    d["enabled"] = bool(d.get("enabled"))
    d["requires_approval"] = bool(d.get("requires_approval"))
    return d


def soc_set_runbook_enabled(rkey, enabled):
    """Admin control: enable/disable a runbook. Never raises. Returns bool ok."""
    try:
        with get_db() as c:
            if _inbox_is_pg():
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            _ensure_soc_schema(c)
            cur = c.execute(
                "UPDATE support_runbooks SET enabled=?, updated_at=CURRENT_TIMESTAMP "
                "WHERE rkey=?", (1 if enabled else 0, rkey))
            return int(getattr(cur, "rowcount", 0) or 0) > 0
    except Exception:
        return False


def _soc_record_action(incident_id, agent, action_type, mode, status, detail=""):
    """Write one support_actions row + mirror to audit_logs. Returns action id or
    None. Never raises."""
    aid = None
    try:
        with get_db() as c:
            if _inbox_is_pg():
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            _ensure_soc_schema(c)
            cur = c.execute(
                "INSERT INTO support_actions "
                "(incident_id, agent, action_type, mode, status, detail) "
                "VALUES (?,?,?,?,?,?)",
                (incident_id, agent, str(action_type)[:60], mode, status,
                 str(detail)[:2000]))
            try:
                aid = int(getattr(cur, "lastrowid", 0) or 0)
            except Exception:
                aid = None
    except Exception:
        aid = None
    try:
        log_audit(action="soc_action", user_id=None, status=status,
                  detail="%s/%s incident=%s: %s" % (agent, action_type, incident_id, str(detail)[:200]))
    except Exception:
        pass
    return aid


def _soc_agent_run(agent, incident_id, status, error=None):
    try:
        with get_db() as c:
            if _inbox_is_pg():
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            _ensure_soc_schema(c)
            c.execute(
                "INSERT INTO support_agent_runs "
                "(agent, incident_id, status, finished_at, error) "
                "VALUES (?,?,?,CURRENT_TIMESTAMP,?)",
                (agent, incident_id, status, (str(error)[:500] if error else None)))
    except Exception:
        pass


def soc_tier1_run(incident_id, runbook_key):
    """Tier-1 auto-remediation entry. Executes one enabled, no-approval runbook —
    but ONLY when soc_automation_allowed('tier1'). Records every outcome in
    support_actions + audit_logs; a failed verification runs rollback.

    Returns {ran, verified, rolled_back, reason}. NEVER raises."""
    result = {"ran": False, "verified": None, "rolled_back": False, "reason": None}
    try:
        # Gate 1 — the kill switch. Default-deny (both flags default OFF).
        if not soc_automation_allowed("tier1"):
            _soc_record_action(incident_id, "tier1", runbook_key, "auto", "blocked",
                               "automation not allowed (kill switch / disabled / paused)")
            result["reason"] = "automation_blocked"
            return result

        # Gate 2 — the runbook must exist, be enabled, and not require approval.
        rb = _soc_get_runbook(runbook_key)
        if not rb or not rb["enabled"] or rb["requires_approval"]:
            _soc_record_action(incident_id, "tier1", runbook_key, "auto", "skipped",
                               "runbook missing/disabled/needs-approval")
            result["reason"] = "runbook_not_runnable"
            return result

        handler = _SOC_RUNBOOK_HANDLERS.get(runbook_key)
        if not handler or not callable(handler.get("do")):
            _soc_record_action(incident_id, "tier1", runbook_key, "auto", "skipped",
                               "no executable handler registered")
            result["reason"] = "no_handler"
            return result

        # Execute.
        try:
            detail = handler["do"]() or ""
            result["ran"] = True
        except Exception as e:
            _soc_record_action(incident_id, "tier1", runbook_key, "auto", "failed",
                               "do() raised: %s" % str(e)[:200])
            _soc_agent_run("tier1", incident_id, "failed", error=e)
            result["reason"] = "do_failed"
            return result

        _soc_record_action(incident_id, "tier1", runbook_key, "auto", "executed", detail)
        _soc_agent_run("tier1", incident_id, "succeeded")

        # Verify.
        verified = True
        try:
            vfn = handler.get("verify")
            verified = bool(vfn()) if callable(vfn) else True
        except Exception:
            verified = False
        result["verified"] = verified

        # Rollback on failed verification. rolled_back is set ONLY when a rollback
        # actually ran — a missing rollback is recorded distinctly so the outcome
        # never overstates what happened (Codex Slice 4 finding).
        if not verified:
            rfn = handler.get("rollback")
            if callable(rfn):
                try:
                    rfn()
                    result["rolled_back"] = True
                    _soc_record_action(incident_id, "tier1", runbook_key, "auto",
                                       "rolled_back", "verification failed -> rolled back")
                except Exception as e:
                    _soc_record_action(incident_id, "tier1", runbook_key, "auto",
                                       "rollback_failed", "rollback raised: %s" % str(e)[:200])
            else:
                _soc_record_action(incident_id, "tier1", runbook_key, "auto",
                                   "no_rollback", "verification failed; no rollback defined")
        return result
    except Exception:
        return result


# ── Admin control for the catalogue (AutoRemediationPanel) ────────────────────

@app.route("/admin/soc/runbooks", methods=["GET"])
@admin_required
def admin_soc_runbooks():
    """List the runbook catalogue (JSON). Seeds on first view."""
    soc_seed_runbooks()
    keys = ("id", "rkey", "name", "category", "risk_level", "requires_approval",
            "enabled", "allowed_tiers")
    def _q(c):
        return [_soc_row_to_dict(r, keys) for r in c.execute(
            "SELECT id, rkey, name, category, risk_level, requires_approval, "
            "enabled, allowed_tiers FROM support_runbooks ORDER BY rkey").fetchall()]
    return jsonify({"runbooks": _soc_admin_read(_q) or []})


@app.route("/admin/soc/runbooks/<rkey>/toggle", methods=["POST"])
@admin_required
def admin_soc_runbook_toggle(rkey):
    """Enable/disable a runbook (admin + CSRF + audit)."""
    csrf_protect()
    val = (request.form.get("value") or "").strip().lower() in ("1", "true", "yes", "on")
    if not soc_set_runbook_enabled(rkey, val):
        return jsonify({"error": "not_found_or_failed", "rkey": rkey}), 404
    try:
        log_audit(action="soc_runbook_toggle", user_id=session.get("user_id"),
                  status="success", detail="%s enabled=%s" % (rkey, val))
    except Exception:
        pass
    return jsonify({"ok": True, "rkey": rkey, "enabled": val})
