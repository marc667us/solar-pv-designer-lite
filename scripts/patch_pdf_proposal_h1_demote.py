"""
Fix the blank-page bug in the Proposal PDF.

Root cause: _render_pdf at web_app.py:3816 splits markdown on every `\n# `
and creates a separate Section per piece. Each Section becomes a forced
page break in markdown-pdf. The proposal has 17 H1 headings (intro +
3 parts + 13 subsections) — so the PDF has 17 forced page breaks, leaving
the small subsection tables as nearly-blank pages.

Fix: demote subsection headers (# A1, # A2, ..., # C3) to H2 (## A1, ...).
Keep PART A / PART B / PART C as H1 — those are real major page breaks.
After this change the proposal renders as 3 sections + 1 intro = 4 page
breaks total, with subsections flowing naturally within each part.

Why a binary patch: web_app.py is CRLF + Windows-1252 mojibake. Edit-tool
curly quotes corrupt the file. Idempotent (safe to re-run).
"""
import re
import sys
from pathlib import Path

WEB = Path(__file__).parent.parent / "web_app.py"
data = WEB.read_bytes()
orig_size = len(data)

# Pattern: \r\n# A1., \r\n# A2., ..., \r\n# C3. — ANYWHERE in file but the
# proposal markdown is the only place this shape exists.
# Negative-guard: don't touch \r\n# PART  (the major-part markers).
pattern = re.compile(rb'\r\n# ([ABC]\d{1,2}\.)', re.MULTILINE)

count_before = len(pattern.findall(data))
if count_before == 0:
    # Either already patched OR the proposal was refactored — check both
    if b'\r\n## A1.' in data:
        print(f"[skip] already applied (no `\\r\\n# A1.`-style headers remain; ## A1. present)")
        sys.exit(0)
    print(f"[abort] no `\\r\\n# [ABC]N.` headers found — proposal structure may have changed")
    sys.exit(2)

# Apply the demotion
new_data = pattern.sub(rb'\r\n## \1', data)
count_after = len(pattern.findall(new_data))

print(f"[match] {count_before} subsection headers found")
print(f"[apply] demoted to H2; {count_after} remaining (should be 0)")
if count_after != 0:
    print(f"[abort] leftover matches — refusing to write")
    sys.exit(3)

# Sanity: still CRLF
crlf = new_data.count(b'\r\n')
lf   = new_data.count(b'\n') - crlf
if lf != 0:
    print(f"[abort] bare LFs present after patch: {lf}")
    sys.exit(4)

bak = WEB.with_suffix(WEB.suffix + ".bak_proposal_h2")
if not bak.exists():
    bak.write_bytes(WEB.read_bytes())
    print(f"[backup] {bak.name} written")
WEB.write_bytes(new_data)
print(f"[write]  web_app.py: {orig_size} -> {len(new_data)} bytes (CRLF preserved)")
