"""
Improve /admin/ops/email/test to:
1. Show which provider (Resend vs SMTP) succeeded/failed and exact error
2. Try Resend first explicitly with diagnostics
3. Report exact SMTP error (connection refused vs timeout vs auth)
Also adds smtp_tls to email status response.
"""
import subprocess, sys

path = 'web_app.py'
data = open(path, 'rb').read()

OLD = b'''@app.route("/admin/ops/email/test", methods=["POST"])
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
        "<div style=\'font-family:sans-serif;padding:24px;background:#0f0f22;color:#e2e2f0;border-radius:12px\'>"
        "<h2 style=\'color:#f59e0b\'>SolarPro Admin \\xe2\\x80\\x94 Email Test</h2>"
        "<p>This is a test email from the Admin Operations Center.</p>"
        "<p style=\'color:#22c55e\'>If you received this, email delivery is working correctly.</p>"
        "<hr style=\'border-color:#1e1e3a\'>"
        "<small style=\'color:#6868a0\'>Sent from SolarPro Global | solarpro.aiappinvent.com</small>"
        "</div>"
    )
    ok, msg = _apim.email.send(admin_email, "SolarPro Admin \\xe2\\x80\\x94 Email Test", html)
    return jsonify({
        "status": "ok" if ok else "error",
        "sent_to": admin_email,
        "result": msg,
        "message": "Test email sent successfully" if ok else "Email delivery failed: " + str(msg)
    })'''

# The actual bytes in the file
OLD_B = old_bytes = None
# Find the function by its route decorator
start = data.find(b'@app.route("/admin/ops/email/test"')
if start == -1:
    print("ERROR: email test route not found")
    sys.exit(1)

# Find the end of this function (next @app.route or if __name__)
end_markers = [b'\r\n\r\n@app.route', b'\r\n\r\n\r\nif __name__']
end = len(data)
for marker in end_markers:
    pos = data.find(marker, start + 10)
    if pos != -1 and pos < end:
        end = pos

old_func = data[start:end]
print("Found email test function, length:", len(old_func))

NEW_FUNC = b'''@app.route("/admin/ops/email/test", methods=["POST"])
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
    # Get admin email
    try:
        conn = get_db()
        row = conn.execute("SELECT email FROM users WHERE is_admin=1 LIMIT 1").fetchone()
        conn.close()
        admin_email = row[0] if row else None
    except Exception:
        admin_email = None
    if not admin_email:
        admin_email = os.environ.get("EMAIL_SUPPORT", "support@aiappinvent.com")
    html = ("<div style=\'font-family:sans-serif;padding:20px;background:#0f0f22;color:#e2e2f0\'>"
            "<h2 style=\'color:#f59e0b\'>SolarPro Admin Email Test</h2>"
            "<p>Test from Admin Operations Center. Delivery is working!</p>"
            "<small style=\'color:#6868a0\'>solarpro.aiappinvent.com</small></div>")
    subject = "SolarPro Admin - Email Test"
    diagnostics = []

    # --- Try Resend ---
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

    # --- Try SMTP ---
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
            diagnostics.append({"provider": "smtp", "status": "ok",
                                 "host": smtp_host, "port": smtp_port, "tls": smtp_tls})
            return jsonify({"status": "ok", "sent_to": admin_email,
                           "provider": "smtp", "diagnostics": diagnostics,
                           "message": "Test email sent via SMTP to " + admin_email})
        except smtplib.SMTPAuthenticationError as e:
            diagnostics.append({"provider": "smtp", "status": "auth_error",
                                 "detail": str(e)[:120], "host": smtp_host, "port": smtp_port})
        except (OSError, smtplib.SMTPConnectError, ConnectionRefusedError) as e:
            diagnostics.append({"provider": "smtp", "status": "connection_error",
                                 "detail": str(e)[:120], "host": smtp_host, "port": smtp_port,
                                 "hint": "Render may block outbound SMTP. Use Resend API instead."})
        except Exception as e:
            diagnostics.append({"provider": "smtp", "status": "error",
                                 "detail": str(e)[:120], "host": smtp_host, "port": smtp_port})
    else:
        diagnostics.append({"provider": "smtp", "status": "skipped", "detail": "SMTP credentials not configured"})

    return jsonify({
        "status": "error",
        "sent_to": admin_email,
        "message": "Email delivery failed on all providers. See diagnostics.",
        "diagnostics": diagnostics,
        "hint": "Fix: verify Resend domain at resend.com/domains OR set SMTP_PORT=587 + SMTP_TLS=true in Render env vars."
    })'''

data = data[:start] + NEW_FUNC + data[end:]

# Also update email/status to show smtp_tls
STATUS_OLD = b'"smtp_from": frm or "(not set)",'
STATUS_NEW = (b'"smtp_from": frm or "(not set)",'
              b'\r\n        "smtp_tls": os.environ.get("SMTP_TLS", "(not set)"),')
if data.find(STATUS_OLD) != -1:
    data = data.replace(STATUS_OLD, STATUS_NEW, 1)
    print("Email status smtp_tls field added")

open(path, 'wb').write(data)
print("File size: {:,} bytes".format(len(data)))

r = subprocess.run([sys.executable, "-m", "py_compile", path], capture_output=True, text=True)
if r.returncode == 0:
    print("Syntax OK")
else:
    print("SYNTAX ERROR:", r.stderr)
    sys.exit(1)
