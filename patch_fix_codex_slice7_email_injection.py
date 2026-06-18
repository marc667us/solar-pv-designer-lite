"""Apply Codex Slice 7 high-severity fix to the already-injected web_app.py.

Codex Slice 7 finding: supplier-controlled strings (company name, RFQ title)
flowed raw into email subject + body. solar's _send_system_email wraps the
body in <pre>{body_text}</pre> with NO HTML escaping, so HTML/<script> in
a company name would land in the admin's inbox as live markup, and CR/LF
in any string could inject an SMTP header.

Fix: rip out the 4 marketplace notify helpers' old bodies and replace with
the new versions from new_marketplace_email_routes.py that:
  - html.escape() every user-controlled string before substitution
  - _safe_email_subject() strips CR/LF + clips to 160 chars

Idempotent — skips if _safe_email_text is already present in web_app.py.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"
SOURCE = "new_marketplace_email_routes.py"


def patch() -> int:
    src = open(TARGET, "rb").read()
    if b"def _safe_email_text" in src:
        print("[skip] _safe_email_text already present")
        return 0

    # Strategy: locate the marketplace email helper block (begins with the
    # banner comment we own) and replace it wholesale with the updated source.
    BANNER = b"# \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80 Marketplace Email Notifications"
    start = src.find(BANNER)
    if start < 0:
        print("[fail] banner not found")
        return 4
    # The block extends until the next `# ───` banner OR the __main__ guard.
    end_main = src.find(b'if __name__ == "__main__":', start)
    if end_main < 0:
        print("[fail] __main__ not found after banner")
        return 5
    new_block = open(SOURCE, "rb").read().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    src = src[:start] + new_block + b"\r\n\r\n" + src[end_main:]
    open(TARGET, "wb").write(src)
    print("[ok] replaced marketplace email block with HTML-escape-safe version")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
