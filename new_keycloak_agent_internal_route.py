# ── Phase 3 pilot: SA-only internal route ──────────────────────────────
#
# Demonstrates the §19 task 15-18 acceptance criterion:
#   "agent -> backend call without a valid service-account JWT returns 401.
#    With a valid JWT, audit log shows `agent_id` of the service account,
#    not a human user id."
#
# When KEYCLOAK_ENABLED is unset, @require_service_account is a no-op
# pass-through (parallel-run), so this route is reachable but the
# audit_log line will record an empty azp -- harmless in dev, and the
# whole route only goes live once the flag flips to true.

@app.route("/api/agents/internal/heartbeat", methods=["POST"])
@require_service_account()
def agents_internal_heartbeat():
    """Lightweight liveness ping for SolarPro AI service accounts.

    Any of the 5 service-account clients (catalogue, tender, report,
    email, payment) may call this route to confirm its JWT is being
    accepted. The response echoes the agent's identity so the caller
    can verify it is who Keycloak says it is.
    """
    ctx = get_request_context()
    azp = ctx.azp if ctx else None
    user_id = ctx.user_id if ctx else None
    try:
        log_audit(
            action="AGENT_HEARTBEAT",
            agent_id=azp,
            service_account_user=user_id,
            ip=request.remote_addr,
        )
    except Exception:
        pass
    return jsonify(
        ok=True,
        agent_id=azp,
        service_account_user=user_id,
    ), 200


