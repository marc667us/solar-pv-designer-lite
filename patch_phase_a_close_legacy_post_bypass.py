"""Phase A: close legacy POST-bypass on /login + /register + /forgot-password + /reset-password.

Pattern A byte patch on web_app.py. Keep ?legacy=1 GET escape hatch for the seed
admin during the migration window; remove fully in Phase B (>= 2026-06-30).
"""
import sys

path = "web_app.py"
data = open(path, "rb").read()
orig_len = len(data)

# 1) /login + /register: extend the GET-only KC guard to also cover POST.
old_a = b'    if request.method == "GET" \\\r\n'
new_a = b'    if request.method in ("GET", "POST") \\\r\n'
hits_a = data.count(old_a)
if hits_a != 2:
    print(f"FAIL: expected 2 hits of guard prefix, got {hits_a}")
    sys.exit(1)
data = data.replace(old_a, new_a)

# 2) /forgot-password: add KC guard at top of function body.
old_b = b'def forgot_password():\r\n    if request.method == "POST":\r\n'
new_b = (
    b'def forgot_password():\r\n'
    b'    if os.environ.get("KEYCLOAK_ENABLED", "").lower() in ("1", "true", "yes", "on") \\\r\n'
    b'        and request.args.get("legacy") != "1":\r\n'
    b'        flash("Password reset is now managed by the SolarPro identity service. '
    b'Use the \\"Forgot password?\\" link on the login page.", "info")\r\n'
    b'        return redirect(url_for("oidc.auth_login"))\r\n'
    b'    if request.method == "POST":\r\n'
)
if data.count(old_b) != 1:
    print(f"FAIL: expected 1 hit of forgot_password signature, got {data.count(old_b)}")
    sys.exit(1)
data = data.replace(old_b, new_b)

# 3) /reset-password/<token>: add KC guard at top of function body.
old_c = b'def reset_password(token):\r\n    with get_db() as c:\r\n'
new_c = (
    b'def reset_password(token):\r\n'
    b'    if os.environ.get("KEYCLOAK_ENABLED", "").lower() in ("1", "true", "yes", "on") \\\r\n'
    b'        and request.args.get("legacy") != "1":\r\n'
    b'        flash("Password reset is now managed by the SolarPro identity service. '
    b'Use the \\"Forgot password?\\" link on the login page.", "info")\r\n'
    b'        return redirect(url_for("oidc.auth_login"))\r\n'
    b'    with get_db() as c:\r\n'
)
if data.count(old_c) != 1:
    print(f"FAIL: expected 1 hit of reset_password signature, got {data.count(old_c)}")
    sys.exit(1)
data = data.replace(old_c, new_c)

open(path, "wb").write(data)
print(f"OK: web_app.py {orig_len} -> {len(data)} bytes (+{len(data)-orig_len})")
