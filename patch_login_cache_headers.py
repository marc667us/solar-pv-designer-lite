"""Add Cache-Control / Pragma / Expires headers to the SUCCESS-path 302
redirects in:

  * app/auth/oidc_routes.py :: auth_login()    -> KC OIDC authorize URL
  * app/auth/oidc_routes.py :: auth_register() -> KC OIDC registration URL
  * web_app.py             :: /login shim     -> /auth/login

Without these headers browsers cache the 302 and any transient KC outage
(deploy window, OOM-restart) gets sticky-served from disk cache, leaving
the user staring at an apparent "login not going to KC" page until they
hard-refresh. The _oidc_fail_redirect helper in oidc_routes.py already
documents the pattern; this patch applies it to the success path too.

Re-run safe: each replacement checks for the post-patch shape and skips
if already applied.
"""
from __future__ import annotations
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent

# ---------- app/auth/oidc_routes.py ----------
OIDC = REPO / "app" / "auth" / "oidc_routes.py"
oidc = OIDC.read_bytes()

# auth_login success path: replace the bare `return redirect(...)` that
# fires after `_kc_next` stashing in the session.
LOGIN_OLD = b'    return redirect(f"{_authorize_url()}?{urlencode(params)}")\r\n'
LOGIN_NEW = (
    b'    _resp = redirect(f"{_authorize_url()}?{urlencode(params)}")\r\n'
    b'    _resp.headers["Cache-Control"] = "no-store, must-revalidate"\r\n'
    b'    _resp.headers["Pragma"] = "no-cache"\r\n'
    b'    _resp.headers["Expires"] = "0"\r\n'
    b'    return _resp\r\n'
)
if LOGIN_NEW in oidc:
    print("oidc_routes.auth_login: already patched, skipping")
elif LOGIN_OLD in oidc:
    oidc = oidc.replace(LOGIN_OLD, LOGIN_NEW, 1)
    print("oidc_routes.auth_login: patched")
else:
    sys.exit("oidc_routes.auth_login: anchor not found, abort")

# auth_register success path: same shape, different URL builder.
REG_OLD = b'    return redirect(f"{_registrations_url()}?{urlencode(params)}")\r\n'
REG_NEW = (
    b'    _resp = redirect(f"{_registrations_url()}?{urlencode(params)}")\r\n'
    b'    _resp.headers["Cache-Control"] = "no-store, must-revalidate"\r\n'
    b'    _resp.headers["Pragma"] = "no-cache"\r\n'
    b'    _resp.headers["Expires"] = "0"\r\n'
    b'    return _resp\r\n'
)
if REG_NEW in oidc:
    print("oidc_routes.auth_register: already patched, skipping")
elif REG_OLD in oidc:
    oidc = oidc.replace(REG_OLD, REG_NEW, 1)
    print("oidc_routes.auth_register: patched")
else:
    sys.exit("oidc_routes.auth_register: anchor not found, abort")

OIDC.write_bytes(oidc)

# ---------- web_app.py ----------
WEB = REPO / "web_app.py"
data = WEB.read_bytes()

# The /login shim 5-line block (CRLF, 4-space indent).
SHIM_OLD = (
    b'    if request.method in ("GET", "POST"):\r\n'
    b'        _kc_next = request.args.get("next")\r\n'
    b'        if _kc_next:\r\n'
    b'            return redirect(url_for("oidc.auth_login", next=_kc_next))\r\n'
    b'        return redirect(url_for("oidc.auth_login"))\r\n'
)
SHIM_NEW = (
    b'    if request.method in ("GET", "POST"):\r\n'
    b'        _kc_next = request.args.get("next")\r\n'
    b'        if _kc_next:\r\n'
    b'            _r = redirect(url_for("oidc.auth_login", next=_kc_next))\r\n'
    b'        else:\r\n'
    b'            _r = redirect(url_for("oidc.auth_login"))\r\n'
    b'        _r.headers["Cache-Control"] = "no-store, must-revalidate"\r\n'
    b'        _r.headers["Pragma"] = "no-cache"\r\n'
    b'        _r.headers["Expires"] = "0"\r\n'
    b'        return _r\r\n'
)
if SHIM_NEW in data:
    print("web_app.py /login shim: already patched, skipping")
elif SHIM_OLD in data:
    data = data.replace(SHIM_OLD, SHIM_NEW, 1)
    print("web_app.py /login shim: patched")
else:
    sys.exit("web_app.py /login shim: anchor not found, abort")

WEB.write_bytes(data)
print("done.")
