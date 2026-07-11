# ─────────────────────────────────────────────────────────────────────────────
# AI-SOC — Slice 2: Support Orchestrator + deterministic classification
# ─────────────────────────────────────────────────────────────────────────────
# Per docs/AI_SOC_IMPLEMENTATION_PLAN_2026-07-10.md Slice 2 and source spec
# (agentic support.txt §6/§8). The single entry point that turns a support_event
# into a classified support_incident, writes it to the EXISTING admin inbox, and
# records the agent run. Still ZERO actions — classification + notification is
# always-allowed diagnosis (gated only on soc_enabled, not the kill switch).
#
# Classification is DETERMINISTIC-FIRST (plan constraint 4: the live LLM chain is
# degraded, so a security control must not depend on it). An optional LLM
# enrichment step may add a probable_cause but is always allowed to be absent.
#
# Spliced into web_app.py by patch_soc_slice2.py (byte-level, CRLF-aware).

import hashlib as _soc2_hashlib
import json as _soc2_json


# Severity -> admin-inbox severity (the inbox accepts info|warning|critical).
_SOC_SEV_TO_INBOX = {"P1": "critical", "P2": "warning", "P3": "warning", "P4": "info"}

# Incident statuses that count as OPEN (a new event with the same fingerprint
# attaches to the open incident instead of spawning a duplicate).
_SOC_OPEN_STATUSES = ("Detected", "Classified", "Assigned", "Investigating",
                      "Automated Fix Running", "Awaiting Approval",
                      "Fix Approved", "Monitoring", "Reopened")

# Security-signal keywords (event_type substrings) -> route to the SecurityAgent.
_SOC_SECURITY_HINTS = ("brute", "token", "injection", "xss", "csrf", "cross_tenant",
                       "privilege", "malware", "unauthorized", "secret", "hijack",
                       "anomalous_admin", "abuse")


def _soc_hash(obj):
    """Stable short hash for agent-run input/output attribution (§8 of the ADK
    extension: support_agent_runs carries input_hash/output_hash)."""
    try:
        raw = _soc2_json.dumps(obj, sort_keys=True, default=str)
    except Exception:
        raw = str(obj)
    return _soc2_hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


def _soc_classify(event):
    """DETERMINISTIC severity/tier/module classifier. Pure function of the event
    dict — no I/O, no LLM. Maps to spec §6/§8:

      P1 Critical : platform/DB/auth unavailable, security breach, cross-tenant.
      P2 High     : major module (payment/auth) failure, repeated API failures.
      P3 Medium   : single-module backend 5xx, recoverable degradation.
      P4 Low      : cosmetic / minor / doc request.

    Tier: P1 -> tier3 (or security), P2 -> tier3, P3 -> tier2, P4 -> tier1;
    any security signal -> the security tier regardless of severity.

    Returns {severity, tier, module, probable_cause, source}."""
    src = (event.get("source") or "").lower()
    etype = (event.get("event_type") or "").lower()
    module = (event.get("module") or "")
    mod_l = module.lower()

    is_security = (src == "security") or any(k in etype for k in _SOC_SECURITY_HINTS)

    severity = "P3"
    tier = "tier2"
    cause = None

    if etype in ("liveness_down", "health_degraded") or "ping" in mod_l or "boot" in mod_l:
        severity, tier, cause = "P1", "tier3", "platform / DB availability signal"
    elif src == "database" or mod_l == "db" or "database" in mod_l:
        severity, tier, cause = "P1", "tier3", "database failure"
    elif is_security and any(k in etype for k in ("cross_tenant", "breach", "privilege", "injection")):
        severity, tier, cause = "P1", "security", "security breach indicator"
    elif is_security:
        severity, tier, cause = "P2", "security", "security signal requires triage"
    elif etype == "http_5xx" and any(k in mod_l for k in
                                     ("pay", "stripe", "paystack", "auth", "login",
                                      "oidc", "keycloak", "proposal")):
        severity, tier, cause = "P2", "tier3", "failure in a critical module (payment/auth/proposal)"
    elif etype == "http_5xx":
        severity, tier, cause = "P3", "tier2", "backend 5xx in a single module"
    elif any(k in etype for k in ("cosmetic", "ui_", "usability", "doc", "minor")):
        severity, tier, cause = "P4", "tier1", "cosmetic / minor user issue"

    return {"severity": severity, "tier": tier, "module": module or None,
            "probable_cause": cause, "source": event.get("source")}


def _soc_llm_enrich(event, decision):
    """OPTIONAL probable-cause enrichment. Allowed to be absent/fail entirely
    (plan constraint 4). Never raises, never blocks classification. Kept as a
    stub that returns the deterministic cause unchanged until an LLM budget
    exists; the boundary is here so a later drop-in needs no caller change."""
    return decision.get("probable_cause")


def _soc_load_event(c, event_id):
    row = c.execute(
        "SELECT id, tenant_id, incident_id, source, event_type, severity, module, "
        "error_code, payload, fingerprint FROM support_events WHERE id=?",
        (event_id,)).fetchone()
    if not row:
        return None
    keys = ("id", "tenant_id", "incident_id", "source", "event_type", "severity",
            "module", "error_code", "payload", "fingerprint")
    if hasattr(row, "keys"):
        return {k: row[k] for k in keys}
    return {k: row[i] for i, k in enumerate(keys)}


def soc_orchestrate(event_id):
    """THE single entry point (spec: "all agents operate through one
    orchestrator"). Classify one support_event, create-or-attach a
    support_incident, mirror to the admin inbox, and record the orchestrator run.
    Detection/documentation only — NO remediation. Gated on soc_enabled.

    Returns the incident id, or None if disabled/failed. NEVER raises."""
    try:
        if not soc_enabled():
            return None
        is_pg = _inbox_is_pg()
        with get_db() as c:
            if is_pg:
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            _ensure_soc_schema(c)
            ev = _soc_load_event(c, event_id)
            if ev is None:
                return None

            decision = _soc_classify(ev)
            decision["probable_cause"] = _soc_llm_enrich(ev, decision) or decision.get("probable_cause")
            fp = ev.get("fingerprint")

            # De-dupe incidents: attach to an OPEN incident with the same
            # fingerprint rather than spawning a duplicate.
            incident_id = None
            if fp:
                placeholders = ",".join("?" for _ in _SOC_OPEN_STATUSES)
                existing = c.execute(
                    "SELECT id FROM support_incidents WHERE fingerprint=? "
                    "AND status IN (" + placeholders + ") "
                    "ORDER BY id DESC LIMIT 1", (fp,) + _SOC_OPEN_STATUSES).fetchone()
                if existing:
                    incident_id = existing[0] if not hasattr(existing, "keys") else existing["id"]

            created = False
            if incident_id is None:
                title = "%s: %s" % (decision["severity"],
                                    (decision.get("module") or ev.get("event_type") or "incident"))
                # lastrowid is on the cursor, not the connection (see Slice 1).
                cur = c.execute(
                    "INSERT INTO support_incidents "
                    "(tenant_id, status, severity, module, source, tier, title, "
                    " summary, probable_cause, fingerprint, assigned_agent) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (ev.get("tenant_id"), "Classified", decision["severity"],
                     decision.get("module"), ev.get("source"), decision["tier"],
                     title[:200],
                     "Auto-classified from event #%s (%s)" % (ev.get("id"), ev.get("event_type")),
                     decision.get("probable_cause"), fp, decision["tier"]))
                try:
                    incident_id = int(getattr(cur, "lastrowid", 0) or 0)
                except Exception:
                    incident_id = None
                created = True

            # Link the event to its incident.
            if incident_id:
                try:
                    c.execute("UPDATE support_events SET incident_id=? WHERE id=?",
                              (incident_id, ev.get("id")))
                except Exception:
                    pass

            # Record the orchestrator agent run (§8: input_hash/output_hash).
            try:
                c.execute(
                    "INSERT INTO support_agent_runs "
                    "(tenant_id, agent, incident_id, input_hash, output_hash, status, finished_at) "
                    "VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                    (ev.get("tenant_id"), "orchestrator", incident_id,
                     _soc_hash(ev), _soc_hash(decision), "succeeded"))
            except Exception:
                pass

        # Inbox mirror OUTSIDE the write txn (uses its own connection). Only on a
        # newly-created incident, so a repeat signal doesn't spam the inbox.
        if created and incident_id:
            try:
                inbox_sev = _SOC_SEV_TO_INBOX.get(decision["severity"], "warning")
                _admin_notify(
                    "soc", inbox_sev,
                    "%s incident: %s" % (decision["severity"], decision.get("module") or "SolarPro"),
                    "Tier %s · %s" % (decision["tier"], decision.get("probable_cause") or "see incident"),
                    ref_type="support_incident", ref_id=incident_id,
                    fingerprint="soc_incident:%s" % (fp or incident_id))
            except Exception:
                pass
        return incident_id
    except Exception:
        return None


def soc_orchestrate_pending(limit=100):
    """Classify every support_event that has no incident yet (the batch entry the
    cron/backfill uses). Bounded by `limit`. Returns the number processed.
    NEVER raises."""
    processed = 0
    try:
        if not soc_enabled():
            return 0
        with get_db() as c:
            if _inbox_is_pg():
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            _ensure_soc_schema(c)
            rows = c.execute(
                "SELECT id FROM support_events WHERE incident_id IS NULL "
                "ORDER BY id ASC LIMIT ?", (int(limit),)).fetchall()
            ids = [(r[0] if not hasattr(r, "keys") else r["id"]) for r in rows]
        for eid in ids:
            if soc_orchestrate(eid) is not None:
                processed += 1
    except Exception:
        pass
    return processed
