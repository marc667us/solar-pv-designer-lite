"""Patch script: inject new_soc2_pdf_email_routes.py into web_app.py.

Standard Pattern B (per CLAUDE.md):
  * read both files as bytes
  * convert injected code to CRLF to match web_app.py line endings
  * splice it right before `if __name__ == "__main__":`
  * idempotent via a unique marker string at the top of the injected block
"""
import sys

WEB_APP = "web_app.py"
SRC_FILE = "new_soc2_pdf_email_routes.py"
MARKER = b"_soc2_make_aicpa_markdown"  # uniquely identifies the injected block
ANCHOR = b'if __name__ == "__main__":'


def main():
    data = open(WEB_APP, "rb").read()
    if MARKER in data:
        print(f"FAIL: marker {MARKER!r} already present in {WEB_APP} -- already injected.")
        print("To re-inject, manually delete the existing block first.")
        sys.exit(1)
    pos = data.rfind(ANCHOR)
    if pos < 0:
        print(f"FAIL: anchor {ANCHOR!r} not found in {WEB_APP}.")
        sys.exit(2)

    new_code = open(SRC_FILE, "rb").read()
    # Normalize to CRLF to match web_app.py's line-ending convention.
    new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    # Pad with a blank line separator on either side so the spliced block
    # is visually distinct.
    block = b"\r\n" + new_code_crlf + b"\r\n\r\n"

    out = data[:pos] + block + data[pos:]
    open(WEB_APP, "wb").write(out)
    added_lines = new_code_crlf.count(b"\r\n")
    print(f"OK: injected {len(block)} bytes (~{added_lines} lines) into {WEB_APP}.")
    print(f"    marker now present: {MARKER!r}")


if __name__ == "__main__":
    main()
