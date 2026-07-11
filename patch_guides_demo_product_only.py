# Byte-level patch: the live "Video" walkthrough is only offered for the three
# PRODUCT guides (quick / full-user / technical), which walk real product
# screens. The two INTERNAL document guides (portal-tutorial admin onboarding,
# sales-pitch call script) have no product-screen walkthrough, so we drop their
# demo_url -> their guide pages show Read/Listen only, no mismatched video.
# CRLF-safe, idempotent. NEVER Edit web_app.py directly.
import sys

PATH = "web_app.py"
data = open(PATH, "rb").read()


def crlf(s: str) -> bytes:
    return s.replace("\n", "\r\n").encode("utf-8")


OLD = crlf(
    '        "technical":       url_for("capital_investment_landing") + "?tutorial=auto",\n'
    '        "portal-tutorial": url_for("dashboard") + "?tutorial=auto",\n'
    '        "sales-pitch":     url_for("marketplace_public") + "?tutorial=auto",\n'
    '    }.get(slug, "")'
)
NEW = crlf(
    '        "technical":       url_for("capital_investment_landing") + "?tutorial=auto",\n'
    '    }.get(slug, "")'
)

if OLD not in data:
    if NEW in data:
        print("Already patched -- no change.")
        sys.exit(0)
    print("ABORT: anchor not found")
    sys.exit(1)

n = data.count(OLD)
if n != 1:
    print(f"ABORT: anchor found {n} times (need 1)")
    sys.exit(1)

data = data.replace(OLD, NEW)
open(PATH, "wb").write(data)
print("Patched web_app.py: demo_url now product-guides only.")
