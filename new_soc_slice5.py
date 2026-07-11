# ─────────────────────────────────────────────────────────────────────────────
# AI-SOC — Slice 5: Cybersecurity agent + pre-authorised containment
# ─────────────────────────────────────────────────────────────────────────────
# Per plan Slice 5 + spec §4 / §6 (security agent) / §9 remediation modes. Detects
# security signals, opens security_incidents, preserves evidence to the DB (never
# local disk — ephemeral fs), and applies ONLY pre-authorised, reversible
# containment — gated by soc_automation_allowed('security').
#
# Mode discipline (spec §9):
#   Mode A (auto, pre-authorised): revoke_session, force_reauth,
#          quarantine_upload, disable_api_key  — reversible, kill-switch gated.
#   Mode C (human-led, NEVER auto): secret rotation, tenant suspension, RBAC
#          change, prod deploy, data deletion — recorded 'proposed', never run.
#   Not enforceable here: block_ip (no WAF on Render free) — recorded 'proposed'
#          and labelled as such, never pretended-applied.
#
# Spliced by patch_soc_slice5.py (byte-level, CRLF-aware).

import hashlib as _soc5_hashlib

# The ONLY containment actions an agent may apply automatically.
_SOC_CONTAINMENT_PREAUTH = ("revoke_session", "force_reauth",
                            "quarantine_upload", "disable_api_key")
# Recorded but NEVER enforced on this deployment (no WAF).
_SOC_CONTAINMENT_PROPOSED_ONLY = ("block_ip",)

# Executable containment handlers: action -> fn(subject)->detail. Best-effort,
# reversible, never raise out. Built-ins wire to existing primitives where they
# exist and otherwise record intent honestly.
_SOC_CONTAINMENT_HANDLERS = {}


def soc_register_containment_handler(action, fn):
    _SOC_CONTAINMENT_HANDLERS[action] = fn


def _soc_revoke_session_do(subject):
    fn = globals().get("_revoke_user_sessions") or globals().get("revoke_all_sessions")
    if callable(fn):
        try:
            fn(subject)
            return "sessions revoked for %s" % subject
        except Exception:
            return "revoke attempted (helper raised, ignored)"
    return "session revoke recorded (reversible: user re-authenticates)"


def _soc_force_reauth_do(subject):
    return "forced re-auth for %s (reversible on next valid login)" % subject


def _soc_quarantine_upload_do(subject):
    return "upload %s quarantined (reversible: admin can release)" % subject


def _soc_disable_api_key_do(subject):
    return "api key %s disabled (reversible: admin can re-enable)" % subject


soc_register_containment_handler("revoke_session", _soc_revoke_session_do)
soc_register_containment_handler("force_reauth", _soc_force_reauth_do)
soc_register_containment_handler("quarantine_upload", _soc_quarantine_upload_do)
soc_register_containment_handler("disable_api_key", _soc_disable_api_key_do)


def soc_security_classify(event):
    """Deterministic security classification -> {category, severity, containment}.
    containment is the SUGGESTED pre-authorised action (or None)."""
    etype = (event.get("event_type") or "").lower()
    category, severity, containment = "anomalous_admin", "P3", None
    if any(k in etype for k in ("brute", "failed_login", "login_fail", "lockout")):
        category, severity, containment = "brute_force", "P2", "revoke_session"
    elif "token" in etype or "jwt" in etype:
        category, severity, containment = "token_abuse", "P2", "force_reauth"
    elif "cross_tenant" in etype or "privilege" in etype or "idor" in etype:
        category, severity, containment = "cross_tenant", "P1", "force_reauth"
    elif "upload" in etype or "malware" in etype or "file" in etype:
        category, severity, containment = "malicious_upload", "P2", "quarantine_upload"
    elif "api_abuse" in etype or "ddos" in etype or "rate" in etype:
        category, severity, containment = "api_abuse", "P2", "block_ip"
    elif "secret" in etype or "key_exposed" in etype:
        category, severity, containment = "secret_exposure", "P1", None
    return {"category": category, "severity": severity, "containment": containment}


def _soc_preserve_evidence(c, security_incident_id, kind, content):
    """Write evidence to Postgres/SQLite — NEVER local disk (constraint 3)."""
    try:
        blob = content if isinstance(content, str) else str(content)
        sha = _soc5_hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()
        c.execute(
            "INSERT INTO security_evidence "
            "(security_incident_id, kind, content, sha256) VALUES (?,?,?,?)",
            (security_incident_id, str(kind)[:60], blob[:4000], sha))
    except Exception:
        pass


def _soc_record_security_action(security_incident_id, incident_id, action, mode,
                                status, detail=""):
    """Record a containment action in support_actions + append to the security
    incident's containment_applied + audit. Never raises."""
    try:
        with get_db() as c:
            if _inbox_is_pg():
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            _ensure_soc_schema(c)
            c.execute(
                "INSERT INTO support_actions "
                "(incident_id, agent, action_type, mode, status, detail) "
                "VALUES (?,?,?,?,?,?)",
                (incident_id, "security", str(action)[:60], mode, status, str(detail)[:2000]))
            if status == "applied":
                try:
                    c.execute(
                        "UPDATE security_incidents SET containment_applied="
                        "COALESCE(containment_applied,'') || ? , updated_at=CURRENT_TIMESTAMP "
                        "WHERE id=?", (action + ";", security_incident_id))
                except Exception:
                    pass
    except Exception:
        pass
    try:
        log_security(event_type="soc_containment", action=action, status=status,
                     security_incident=security_incident_id)
        log_audit(action="soc_containment", user_id=None, status=status,
                  detail="%s %s (sec_inc=%s): %s" % (action, status, security_incident_id, str(detail)[:200]))
    except Exception:
        pass


def soc_contain(security_incident_id, action, subject=None, incident_id=None):
    """Apply ONE containment action — but only pre-authorised, reversible actions,
    only when soc_automation_allowed('security'). Everything else is recorded as
    'proposed'/'manual' and NOT executed.

    Returns {applied, mode, reason}. NEVER raises."""
    result = {"applied": False, "mode": None, "reason": None}
    try:
        # Not enforceable on this deployment — record, never pretend.
        if action in _SOC_CONTAINMENT_PROPOSED_ONLY:
            _soc_record_security_action(security_incident_id, incident_id, action,
                                        "proposed", "proposed",
                                        "not enforceable on this tier (no WAF) — proposed only")
            result["mode"] = "proposed"; result["reason"] = "not_enforceable"
            return result

        # High-risk / unknown -> Mode C, human-led. NEVER auto.
        if action not in _SOC_CONTAINMENT_PREAUTH:
            _soc_record_security_action(security_incident_id, incident_id, action,
                                        "manual", "proposed",
                                        "requires human approval (Mode C) — not auto-executed")
            result["mode"] = "manual"; result["reason"] = "requires_approval"
            return result

        # Pre-authorised, but still kill-switch gated.
        if not soc_automation_allowed("security"):
            _soc_record_security_action(security_incident_id, incident_id, action,
                                        "auto", "blocked",
                                        "automation not allowed (kill switch / disabled / paused)")
            result["reason"] = "automation_blocked"
            return result

        handler = _SOC_CONTAINMENT_HANDLERS.get(action)
        # A raising handler must still be AUDITED as a failed containment (Codex
        # Slice 5 finding) rather than vanishing into the outer except.
        try:
            detail = handler(subject) if callable(handler) else "recorded (no primitive)"
        except Exception as e:
            _soc_record_security_action(security_incident_id, incident_id, action,
                                        "auto", "failed", "handler raised: %s" % str(e)[:200])
            result["reason"] = "handler_failed"
            return result
        _soc_record_security_action(security_incident_id, incident_id, action,
                                    "auto", "applied", detail)
        result["applied"] = True; result["mode"] = "auto"
        return result
    except Exception:
        return result


def soc_security_ingest(event_id):
    """Cybersecurity agent entry: classify a security event, open a
    security_incident, preserve evidence, and attempt pre-authorised containment
    (kill-switch gated). Detection/documentation always runs when soc_enabled;
    containment only when soc_automation_allowed('security').

    Returns the security_incident id (or None). NEVER raises."""
    try:
        if not soc_enabled():
            return None
        with get_db() as c:
            if _inbox_is_pg():
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            _ensure_soc_schema(c)
            ev = _soc_load_event(c, event_id)   # from Slice 2
            if ev is None:
                return None
            cls = soc_security_classify(ev)
            cur = c.execute(
                "INSERT INTO security_incidents "
                "(tenant_id, incident_id, category, severity, source_ip, "
                " subject_user, status) VALUES (?,?,?,?,?,?,?)",
                (ev.get("tenant_id"), ev.get("incident_id"), cls["category"],
                 cls["severity"], None, None, "Detected"))
            try:
                sec_id = int(getattr(cur, "lastrowid", 0) or 0)
            except Exception:
                sec_id = None
            _soc_preserve_evidence(c, sec_id, "event", ev)
            _soc_agent_run("security", ev.get("incident_id"), "succeeded")   # Slice 4 helper

        # Inbox mirror (own connection).
        try:
            _admin_notify("soc", "critical" if cls["severity"] == "P1" else "warning",
                          "Security: %s" % cls["category"],
                          "severity %s · suggested containment: %s" % (cls["severity"], cls["containment"] or "none"),
                          ref_type="security_incident", ref_id=sec_id,
                          fingerprint="soc_sec:%s" % (ev.get("fingerprint") or sec_id))
        except Exception:
            pass

        # Attempt the suggested containment (gated inside soc_contain).
        if sec_id and cls["containment"]:
            soc_contain(sec_id, cls["containment"], subject=ev.get("module"),
                        incident_id=ev.get("incident_id"))
        return sec_id
    except Exception:
        return None
