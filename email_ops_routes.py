
# -- Admin Ops: Email diagnostics & test --------------------------------------

@app.route("/admin/ops/email/status")
@admin_required
def admin_ops_email_status():
    # Show current email configuration (masked) without sending
    import os
    from api_manager import api as _apim
    # Force reload from current env vars
    try:
        _apim.email._load()
    except Exception:
        pass
    host  = os.environ.get("SMTP_HOST",  "")
    port  = os.environ.get("SMTP_PORT",  "")
    user  = os.environ.get("SMTP_USER",  "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    frm   = os.environ.get("SMTP_FROM",  "")
    resend = os.environ.get("RESEND_API_KEY", "")
    return jsonify({
        "status": "ok",
        "resend_configured": bool(resend and not resend.startswith("re_...")),
        "resend_key_prefix": resend[:8] + "..." if resend else "(not set)",
        "smtp_configured": bool(host and user and smtp_pass),
        "smtp_host": host or "(not set)",
        "smtp_port": port or "(not set)",
        "smtp_user": user or "(not set)",
        "smtp_pass": ("*" * 8) if smtp_pass else "(not set)",
        "smtp_from": frm or "(not set)",
        "email_sales":     os.environ.get("EMAIL_SALES",     "(not set)"),
        "email_support":   os.environ.get("EMAIL_SUPPORT",   "(not set)"),
        "email_billing":   os.environ.get("EMAIL_BILLING",   "(not set)"),
    })


@app.route("/admin/ops/email/test", methods=["POST"])
@admin_required
def admin_ops_email_test():
    # Send a test email to the admin's email address
    csrf_protect()
    import os
    from api_manager import api as _apim
    # Force reload from current env vars (picks up any new Render env vars)
    try:
        _apim.email._load()
    except Exception:
        pass
    # Get admin email from DB
    try:
        conn = get_db()
        row = conn.execute("SELECT email FROM users WHERE is_admin=1 LIMIT 1").fetchone()
        conn.close()
        admin_email = row[0] if row else None
    except Exception:
        admin_email = None
    if not admin_email:
        admin_email = os.environ.get("EMAIL_SUPPORT", "support@aiappinvent.com")
    html = (
        "<div style='font-family:sans-serif;padding:24px;background:#0f0f22;color:#e2e2f0;border-radius:12px'>"
        "<h2 style='color:#f59e0b'>SolarPro Admin — Email Test</h2>"
        "<p>This is a test email from the Admin Operations Center.</p>"
        "<p style='color:#22c55e'>If you received this, email delivery is working correctly.</p>"
        "<hr style='border-color:#1e1e3a'>"
        "<small style='color:#6868a0'>Sent from SolarPro Global | solarpro.aiappinvent.com</small>"
        "</div>"
    )
    ok, msg = _apim.email.send(admin_email, "SolarPro Admin — Email Test", html)
    return jsonify({
        "status": "ok" if ok else "error",
        "sent_to": admin_email,
        "result": msg,
        "message": "Test email sent successfully" if ok else "Email delivery failed: " + str(msg)
    })

