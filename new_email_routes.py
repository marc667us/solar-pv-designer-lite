
# -- Admin Ops: Email status & test (v2 - with diagnostics) ------------------

@app.route("/admin/ops/email/status")
@admin_required
def admin_ops_email_status():
    # Show current email configuration (masked) - forces env reload
    import os
    from api_manager import api as _apim
    try:
        _apim.email._load()
    except Exception:
        pass
    host  = os.environ.get("SMTP_HOST",  "")
    port  = os.environ.get("SMTP_PORT",  "")
    user  = os.environ.get("SMTP_USER",  "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    frm   = os.environ.get("SMTP_FROM",  "")
    tls   = os.environ.get("SMTP_TLS",   "")
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
        "smtp_tls": tls or "(not set)",
        "email_sales":     os.environ.get("EMAIL_SALES",     "(not set)"),
        "email_support":   os.environ.get("EMAIL_SUPPORT",   "(not set)"),
        "email_billing":   os.environ.get("EMAIL_BILLING",   "(not set)"),
    })


@app.route("/admin/ops/email/test", methods=["POST"])
@admin_required
def admin_ops_email_test():
    # Send a test email with detailed per-provider diagnostics
    csrf_protect()
    import os, smtplib
    from api_manager import api as _apim
    # Reload env vars so Render picks up latest secrets
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
    html = ("<div style='font-family:sans-serif;padding:20px;background:#0f0f22;color:#e2e2f0'>"
            "<h2 style='color:#f59e0b'>SolarPro Admin Email Test</h2>"
            "<p>Test from Admin Operations Center. Delivery is working!</p>"
            "<small style='color:#6868a0'>solarpro.aiappinvent.com</small></div>")
    subject = "SolarPro Admin - Email Test"
    diagnostics = []

    # --- Try Resend first (HTTPS, works through Render firewall) ---
    resend_key = os.environ.get("RESEND_API_KEY", "")
    if resend_key and not resend_key.startswith("re_..."):
        try:
            import resend as _r
            _r.api_key = resend_key
            params = {"from": "onboarding@resend.dev",
                      "to": [admin_email], "subject": subject, "html": html}
            result = _r.Emails.send(params)
            if result and result.get("id"):
                diagnostics.append({"provider": "resend", "status": "ok", "id": result["id"]})
                return jsonify({"status": "ok", "sent_to": admin_email,
                               "provider": "resend", "diagnostics": diagnostics,
                               "message": "Test email sent via Resend to " + admin_email})
            else:
                diagnostics.append({"provider": "resend", "status": "error", "detail": str(result)[:80]})
        except Exception as e:
            diagnostics.append({"provider": "resend", "status": "error", "detail": str(e)[:120]})
    else:
        diagnostics.append({"provider": "resend", "status": "skipped", "detail": "RESEND_API_KEY not configured"})

    # --- Try SMTP (port from env - use 587 STARTTLS on Render) ---
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    smtp_tls  = os.environ.get("SMTP_TLS", "true").lower() in ("1", "true", "yes")
    if smtp_host and smtp_user and smtp_pass:
        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText as _MT
            msg2 = MIMEMultipart("alternative")
            msg2["From"]    = os.environ.get("SMTP_FROM", smtp_user)
            msg2["To"]      = admin_email
            msg2["Subject"] = subject
            msg2.attach(_MT(html, "html"))
            if smtp_tls:
                srv = smtplib.SMTP(smtp_host, smtp_port, timeout=12)
                srv.ehlo()
                srv.starttls()
            else:
                srv = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=12)
            srv.login(smtp_user, smtp_pass)
            srv.sendmail(msg2["From"], [admin_email], msg2.as_string())
            srv.quit()
            diagnostics.append({"provider": "smtp", "status": "ok", "host": smtp_host, "port": smtp_port, "tls": smtp_tls})
            return jsonify({"status": "ok", "sent_to": admin_email,
                           "provider": "smtp", "diagnostics": diagnostics,
                           "message": "Test email sent via SMTP to " + admin_email})
        except smtplib.SMTPAuthenticationError as e:
            diagnostics.append({"provider": "smtp", "status": "auth_error", "detail": str(e)[:120], "host": smtp_host, "port": smtp_port})
        except (OSError, smtplib.SMTPConnectError) as e:
            diagnostics.append({"provider": "smtp", "status": "connection_error", "detail": str(e)[:120], "host": smtp_host, "port": smtp_port,
                                 "hint": "Render blocks outbound SMTP. Use Resend API instead."})
        except Exception as e:
            diagnostics.append({"provider": "smtp", "status": "error", "detail": str(e)[:120], "host": smtp_host, "port": smtp_port})
    else:
        diagnostics.append({"provider": "smtp", "status": "skipped", "detail": "SMTP credentials not configured"})

    return jsonify({
        "status": "error",
        "sent_to": admin_email,
        "message": "Email delivery failed on all providers. See diagnostics.",
        "diagnostics": diagnostics,
        "hint": "Fix: verify Resend domain at resend.com/domains OR ensure SMTP_PORT=587 + SMTP_TLS=true in Render env vars."
    })

