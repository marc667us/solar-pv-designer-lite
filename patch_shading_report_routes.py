"""Inject the Shading Report routes (HTML + PDF) + add the report to the
email REPORT_OPTIONS list. Project rule: NEVER use Edit on web_app.py
because of CRLF + mojibake; use byte-patching via separate routes file.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"
NEW_ROUTES = "new_shading_report_routes.py"


def patch():
    if not open(TARGET, "rb").read():
        print("[fail] empty target")
        return 2
    src = open(TARGET, "rb").read()

    if b"def report_shading" in src and b"def export_pdf_shading" in src:
        print("[skip] shading report routes already present")
    else:
        new_code = open(NEW_ROUTES, "rb").read()
        # Strip the leading comment-block (lines starting with '#') so we
        # just inject pure Python.
        new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        TARGET_ANCHOR = b'if __name__ == "__main__":'
        pos = src.rfind(TARGET_ANCHOR)
        if pos < 0:
            print("[fail] could not find __main__ block to inject before")
            return 3
        src = src[:pos] + new_code_crlf + b"\r\n\r\n" + src[pos:]
        print("[ok] injected report_shading + export_pdf_shading routes")

    # Add the shading report to REPORT_OPTIONS so the existing email
    # pipeline can attach it.
    REPORT_OPTION_ANCHOR = (
        b'        ("Full Proposal (All Reports)", url_for("export_pdf_proposal",    pid=pid)),\r\n'
    )
    NEW_OPTION = (
        b'        ("Full Proposal (All Reports)", url_for("export_pdf_proposal",    pid=pid)),\r\n'
        b'        ("Shading Analysis Report",     url_for("export_pdf_shading",     pid=pid)),\r\n'
    )
    if b'"Shading Analysis Report"' in src:
        print("[skip] Shading Report already in REPORT_OPTIONS")
    elif REPORT_OPTION_ANCHOR in src:
        src = src.replace(REPORT_OPTION_ANCHOR, NEW_OPTION, 1)
        print("[ok] added Shading Analysis Report to email REPORT_OPTIONS")
    else:
        print("[warn] REPORT_OPTIONS anchor not found; email option not wired")

    open(TARGET, "wb").write(src)
    return 0


if __name__ == "__main__":
    sys.exit(patch())
