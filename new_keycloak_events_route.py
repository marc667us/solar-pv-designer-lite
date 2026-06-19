# ── Phase 6: Keycloak event webhook ───────────────────────────────────
#
# Plan §19 task 30 of docs/SECURITY_MIGRATION_KEYCLOAK.md.
#
# Receives admin + user events from the Keycloak event listener SPI.
# Verifies the HMAC-SHA256 signature in X-Keycloak-Event-Signature,
# deduplicates within the configured TTL window, normalises the event
# name, then writes one audit_logs row.
#
# Returns 401 on signature failure (so a misconfigured Keycloak doesn't
# silently flood the table) and 202 on success (so the listener's
# default retry policy doesn't fire on intermittent storage hiccups).

@app.route("/api/keycloak/events", methods=["POST"])
def kc_event_webhook():
    """Webhook receiver for the Keycloak event listener SPI."""
    raw = request.get_data(cache=False, as_text=False) or b""
    sig = request.headers.get("X-Keycloak-Event-Signature", "")
    from app.security.keycloak_events import verify_signature, process_event
    if not verify_signature(raw, sig):
        return jsonify(error="INVALID_SIGNATURE"), 401
    try:
        import json as _json
        payload = _json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return jsonify(error="INVALID_JSON"), 400
    if isinstance(payload, list):
        # Some listener implementations batch events; process each.
        results = [process_event(p) for p in payload if isinstance(p, dict)]
        return jsonify(processed=len(results), results=results), 202
    result = process_event(payload)
    if result == "invalid":
        return jsonify(error="INVALID_PAYLOAD"), 400
    return jsonify(result=result), 202


