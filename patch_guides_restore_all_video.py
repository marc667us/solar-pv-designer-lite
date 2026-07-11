# Byte-level patch: restore a live-walkthrough demo_url for ALL five guides
# (owner wants Video on every tutorial). The two internal guides point at the
# dashboard product walkthrough. Login-gating (from patch_guides_login_gate.py)
# still protects the internal guide CONTENT; this only restores their Video.
# CRLF-safe, idempotent. NEVER Edit web_app.py directly.
import sys

PATH = "web_app.py"
data = open(PATH, "rb").read()


def crlf(s: str) -> bytes:
    return s.replace("\n", "\r\n").encode("utf-8")


OLD = crlf(
    '        "technical":       url_for("capital_investment_landing") + "?tutorial=auto",\n'
    '    }.get(slug, "")'
)
NEW = crlf(
    '        "technical":       url_for("capital_investment_landing") + "?tutorial=auto",\n'
    '        "portal-tutorial": url_for("dashboard") + "?tutorial=auto",\n'
    '        "sales-pitch":     url_for("dashboard") + "?tutorial=auto",\n'
    '    }.get(slug, "")'
)

if crlf('"portal-tutorial": url_for("dashboard") + "?tutorial=auto",') in data:
    print("Already restored -- no change.")
    sys.exit(0)

n = data.count(OLD)
if n != 1:
    print(f"ABORT: anchor found {n} times (need 1)")
    sys.exit(1)

data = data.replace(OLD, NEW)
open(PATH, "wb").write(data)
print("Patched web_app.py: demo_url restored for all 5 guides.")
