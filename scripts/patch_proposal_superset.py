"""
P3: byte-replace export_pdf_proposal in web_app.py with the superset version
from new_proposal_route.py.

Why a byte-level patch (per CLAUDE.md):
- web_app.py is CRLF + has mojibake (Windows-1252-encoded UTF-8). Text-mode
  Edits introduce curly quotes that corrupt the file.

Procedure:
1. Read web_app.py as raw bytes.
2. Locate the OLD function: from `def export_pdf_proposal(pid):` through the
   final `return _render_pdf(f"PV Solar Proposal ...` line (inclusive).
3. Read the NEW function bytes from new_proposal_route.py and convert LF->CRLF
   so it matches the surrounding file's line endings.
4. Verify single occurrence of both start and end anchors and that start < end.
5. Replace and write back.
"""
from __future__ import annotations
import os, sys

ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET   = os.path.join(ROOT, "web_app.py")
NEW_FILE = os.path.join(ROOT, "new_proposal_route.py")

START_ANCHOR = b"def export_pdf_proposal(pid):"
# Last line of the OLD function. Distinctive enough to be unique in web_app.py.
END_ANCHOR   = b'return _render_pdf(f"PV Solar Proposal'


def main() -> int:
    data = open(TARGET, "rb").read()
    new_src_lf = open(NEW_FILE, "rb").read()
    # New file was written with LF endings; match the target's CRLF.
    new_src_crlf = new_src_lf.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

    starts = []
    pos = 0
    while True:
        i = data.find(START_ANCHOR, pos)
        if i == -1: break
        starts.append(i); pos = i + 1
    if len(starts) != 1:
        print(f"ERROR: expected 1 start match, got {len(starts)} at offsets {starts}", file=sys.stderr)
        return 2
    start = starts[0]

    ends = []
    pos = start
    while True:
        i = data.find(END_ANCHOR, pos)
        if i == -1: break
        ends.append(i); pos = i + 1
    if len(ends) != 1:
        print(f"ERROR: expected 1 end match after start, got {len(ends)} at offsets {ends}", file=sys.stderr)
        return 3
    # End of the function is the end of THAT LINE (find the next CRLF after the anchor).
    line_end = data.find(b"\r\n", ends[0])
    if line_end == -1:
        print("ERROR: end anchor not terminated by CRLF", file=sys.stderr)
        return 4
    end_excl = line_end + 2  # include the CRLF

    old_block = data[start:end_excl]
    print(f"Replacing {end_excl - start:,} bytes ({old_block.count(b'\r\n')} lines) "
          f"with {len(new_src_crlf):,} bytes ({new_src_crlf.count(b'\r\n')} lines)")

    patched = data[:start] + new_src_crlf + data[end_excl:]
    open(TARGET, "wb").write(patched)
    print(f"OK wrote {len(patched):,} bytes to {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
