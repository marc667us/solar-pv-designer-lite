"""Append a one-line marketplace PS to every transactional email solar sends.

Without this patch, only the 4 dedicated marketplace notifications carry
the /marketplace URL. With it, every password-reset, verify-email,
support reply, etc. also gets a "PS — browse our free Electrical
Pricing Marketplace" line at the bottom.

Implementation: the marker `body_text` in _send_system_email's body
gets a marketplace footer appended before the HTML wrap. The footer
is a single line + URL — minimal, professional, easy to revert.

Idempotent — skips if the footer constant is already present.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"

OLD = (
    b"def _send_system_email(to_addr, subject, body_text):\r\n"
    b"    \"\"\"Send a transactional system email (password reset, alerts).\"\"\"\r\n"
    b"    html = (\"<div style='font-family:sans-serif;padding:24px;color:#1a1a2e'>\"\r\n"
    b"            \"<pre style='white-space:pre-wrap'>\" + body_text + \"</pre></div>\")\r\n"
    b"    return _send_email(to_addr, subject, html, text_body=body_text)\r\n"
)

NEW = (
    b"_MARKETPLACE_PS = (\r\n"
    b"    \"\\n\\n--\\n\"\r\n"
    b"    \"PS - browse our free Electrical Pricing Marketplace: \"\r\n"
    b"    \"https://solarpro.aiappinvent.com/marketplace\"\r\n"
    b")\r\n"
    b"\r\n"
    b"\r\n"
    b"def _send_system_email(to_addr, subject, body_text):\r\n"
    b"    \"\"\"Send a transactional system email (password reset, alerts).\r\n"
    b"\r\n"
    b"    Appends a one-line marketplace PS to every transactional email\r\n"
    b"    so the new Electrical Pricing Marketplace gets quiet passive\r\n"
    b"    promotion across every solar touchpoint.\r\n"
    b"    \"\"\"\r\n"
    b"    if _MARKETPLACE_PS not in body_text:\r\n"
    b"        body_text = body_text + _MARKETPLACE_PS\r\n"
    b"    html = (\"<div style='font-family:sans-serif;padding:24px;color:#1a1a2e'>\"\r\n"
    b"            \"<pre style='white-space:pre-wrap'>\" + body_text + \"</pre></div>\")\r\n"
    b"    return _send_email(to_addr, subject, html, text_body=body_text)\r\n"
)


def patch() -> int:
    src = open(TARGET, "rb").read()
    if b"_MARKETPLACE_PS" in src:
        print("[skip] marketplace footer already present")
        return 0
    if OLD not in src:
        print("[fail] pre-fix _send_system_email block not found")
        return 4
    src = src.replace(OLD, NEW)
    open(TARGET, "wb").write(src)
    print("[ok] _send_system_email now appends marketplace PS to every body")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
