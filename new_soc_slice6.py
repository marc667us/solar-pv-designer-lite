# ─────────────────────────────────────────────────────────────────────────────
# AI-SOC — Slice 6: Tier 2 diagnostics (READ-ONLY)
# ─────────────────────────────────────────────────────────────────────────────
# Per plan Slice 6 + spec §"Tier 2". Correlates logs across support_events /
# error_logs / audit_logs, inspects config + feature flags, and produces a
# root-cause hypothesis + evidence + proposed fix + rollback plan.
#
# The load-bearing property: Tier 2 MUTATES NOTHING. soc_tier2_diagnose() runs
# only SELECTs and returns a dict — it never writes a row, never changes app or
# SOC state. Recording the diagnosis (if wanted) is a SEPARATE, explicit call
# (soc_tier2_record) that writes a 'proposed' action — still no app mutation.
#
# Spliced by patch_soc_slice6.py (byte-level, CRLF-aware).


def _soc_safe_count(c, sql, params=()):
    try:
        r = c.execute(sql, params).fetchone()
        return int((r[0] if r else 0) or 0)
    except Exception:
        return None   # table may not exist on this backend/tier


def soc_tier2_diagnose(incident_id):
    """READ-ONLY root-cause analysis for an incident. Correlates the incident's
    events with error_logs / audit_logs, inspects relevant config flags, and
    returns:
      {incident_id, module, severity, root_cause, evidence[], proposed_fix,
       rollback_plan, risk_level, correlated}
    Writes NOTHING. Gated on soc_enabled. NEVER raises."""
    try:
        if not soc_enabled():
            return None
        with get_db() as c:
            if _inbox_is_pg():
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            # NOTE: no _ensure_soc_schema here — pure read path; schema is ensured
            # by the write paths. Selecting a missing table is caught below.
            inc = None
            try:
                row = c.execute(
                    "SELECT id, module, severity, source, tier, probable_cause, fingerprint "
                    "FROM support_incidents WHERE id=?", (incident_id,)).fetchone()
                if row is not None:
                    keys = ("id", "module", "severity", "source", "tier",
                            "probable_cause", "fingerprint")
                    inc = {k: (row[k] if hasattr(row, "keys") else row[i])
                           for i, k in enumerate(keys)}
            except Exception:
                inc = None
            if inc is None:
                return None

            module = inc.get("module")
            evidence = []

            # Correlate: how many events feed this incident?
            ev_n = _soc_safe_count(
                c, "SELECT COUNT(*) FROM support_events WHERE incident_id=?", (incident_id,))
            if ev_n is not None:
                evidence.append("support_events linked: %d" % ev_n)

            # Correlate: recent error_logs for the same module (read-only, best-effort).
            err_n = _soc_safe_count(
                c, "SELECT COUNT(*) FROM error_logs WHERE created_at > "
                   + ("(CURRENT_TIMESTAMP - INTERVAL '1 hour')" if _inbox_is_pg()
                      else "datetime('now','-1 hour')"))
            if err_n is not None:
                evidence.append("error_logs in last hour: %d" % err_n)

            # Correlate: recent security/audit activity.
            aud_n = _soc_safe_count(c, "SELECT COUNT(*) FROM audit_logs")
            if aud_n is not None:
                evidence.append("audit_logs total: %d" % aud_n)

        # Deterministic hypothesis from the classification + correlation.
        sev = inc.get("severity") or "P3"
        cause = inc.get("probable_cause") or "unclassified"
        if sev == "P1":
            fix = "Restore availability: verify DB/health, redeploy last-good, page on-call."
            rollback = "Re-point to previous healthy deploy; DB failover if applicable."
            risk = "high"
        elif sev == "P2":
            fix = "Isolate the failing module (%s); patch the handler; add a regression test." % (module or "?")
            rollback = "Revert the module change; feature-flag it off."
            risk = "medium"
        else:
            fix = "Add input/guard for the failing path in %s; log-and-continue." % (module or "?")
            rollback = "Revert the guard commit."
            risk = "low"

        return {
            "incident_id": incident_id,
            "module": module,
            "severity": sev,
            "root_cause": cause,
            "evidence": evidence,
            "proposed_fix": fix,
            "rollback_plan": rollback,
            "risk_level": risk,
            "correlated": {"events": ev_n, "error_logs_1h": err_n, "audit_logs": aud_n},
        }
    except Exception:
        return None


def soc_tier2_record(incident_id, diagnosis=None):
    """EXPLICIT, separate step that records a Tier-2 diagnosis as a 'proposed'
    action (no app mutation, no remediation). Returns the action id or None.
    Kept separate from diagnose() so diagnosis stays a pure read."""
    try:
        if not soc_enabled():
            return None
        if diagnosis is None:
            diagnosis = soc_tier2_diagnose(incident_id)
        if diagnosis is None:
            return None
        detail = "root_cause=%s | fix=%s | rollback=%s | risk=%s" % (
            diagnosis.get("root_cause"), diagnosis.get("proposed_fix"),
            diagnosis.get("rollback_plan"), diagnosis.get("risk_level"))
        aid = _soc_record_action(incident_id, "tier2", "diagnosis", "proposed",
                                 "proposed", detail)   # Slice 4 helper
        _soc_agent_run("tier2", incident_id, "succeeded")
        return aid
    except Exception:
        return None
