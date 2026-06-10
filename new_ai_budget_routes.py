# ── AI Budget — quota status endpoint ────────────────────────────────────────
# Lets the chat widget show remaining-tokens / reset-time, and lets admin UIs
# read org-wide spend without scraping the ledger. Login required.
@app.route("/api/ai/quota")
@login_required
def api_ai_quota():
    import ai_budget as _ab
    uid = session.get("user_id")
    remaining, reset_s, used = _ab.get_user_remaining(uid)
    spend = _ab.get_org_spend_this_month()
    return jsonify({
        "user": {
            "used":           used,
            "limit":          _ab.USER_TOKEN_CAP_24H,
            "remaining":      remaining,
            "reset_seconds":  reset_s,
        },
        "org": {
            "spent_usd":  round(spend, 4),
            "limit_usd":  _ab.SPEND_CAP_USD_MONTHLY,
        },
    })


