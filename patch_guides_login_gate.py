# Byte-level patch: login-gate the two INTERNAL guide slugs (portal-tutorial,
# sales-pitch) on the otherwise-public /guides/<slug> and /guides/<slug>/pdf
# routes. Before this change they were only reachable via the @login_required
# /support/asset/<slug> route, so exposing them publicly would leak the internal
# rep call script + admin onboarding. The 3 general guides stay public.
# CRLF-safe, idempotent, asserts each anchor is unique. NEVER Edit web_app.py.
import sys

PATH = "web_app.py"
data = open(PATH, "rb").read()


def crlf(s: str) -> bytes:
    return s.replace("\n", "\r\n").encode("utf-8")


if b"_GUIDE_LOGIN_ONLY" in data:
    print("Already patched (found _GUIDE_LOGIN_ONLY) -- no change.")
    sys.exit(0)

# 1) define the set just before _guide_lookup
OLD_DEF = crlf("def _guide_lookup(slug):")
NEW_DEF = crlf(
    "# Internal collateral: readable only when logged in (the 3 general guides\n"
    "# stay public for marketing). Gated in guides_view + guides_pdf below.\n"
    '_GUIDE_LOGIN_ONLY = {"portal-tutorial", "sales-pitch"}\n'
    "\n"
    "\n"
    "def _guide_lookup(slug):"
)

# 2) gate guides_view (anchor: its unique demo_url map opener)
OLD_VIEW = crlf(
    '    demo_url = {\n'
    '        "quick":           url_for("dashboard") + "?tutorial=auto",'
)
NEW_VIEW = crlf(
    '    if slug in _GUIDE_LOGIN_ONLY and not current_user():\n'
    '        return redirect(url_for("login"))\n'
    '    demo_url = {\n'
    '        "quick":           url_for("dashboard") + "?tutorial=auto",'
)

# 3) gate guides_pdf (anchor: its unique `safe = slug.replace` line)
OLD_PDF = crlf('    safe = slug.replace("-", "_")')
NEW_PDF = crlf(
    '    if slug in _GUIDE_LOGIN_ONLY and not current_user():\n'
    '        return redirect(url_for("login"))\n'
    '    safe = slug.replace("-", "_")'
)

for label, old, new in [("def", OLD_DEF, NEW_DEF),
                        ("view", OLD_VIEW, NEW_VIEW),
                        ("pdf", OLD_PDF, NEW_PDF)]:
    n = data.count(old)
    if n != 1:
        print(f"ABORT: anchor '{label}' found {n} times (need exactly 1)")
        sys.exit(1)
    data = data.replace(old, new)

open(PATH, "wb").write(data)
print("Patched web_app.py: login-gated portal-tutorial + sales-pitch.")
