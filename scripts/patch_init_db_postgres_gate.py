"""
Session C / C3 — replace web_app.py:init_db() with the version in
new_init_db.py that gates SQLite-only DDL on `DATABASE_URL`.

The new function (defined in new_init_db.py at the repo root) keeps the
SQLite path byte-identical: same CREATE TABLE block, same ALTER chain,
same seed phase. When DATABASE_URL is set it skips the executescript
block and the ALTER loops (the mirror schema migration owns those) and
runs only the seed phase, which is row-level SQL that works on both
backends.

Byte-patch is required (CRLF + mojibake constraint per CLAUDE.md). Old
function spans web_app.py:226 -> 707 inclusive (def init_db through the
final `c.executemany(... _default_news)` line; verified by checking the
next line is blank then a new section header).
"""
from __future__ import annotations
import os, sys

ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET   = os.path.join(ROOT, "web_app.py")
NEW_FILE = os.path.join(ROOT, "new_init_db.py")

START_ANCHOR = b"def init_db():"
# Distinctive enough — there's only one news_posts seed in the file.
# The trailing `\r\n` is included so the boundary is unambiguous.
END_ANCHOR   = b"                _default_news)"


def main() -> int:
    data = open(TARGET, "rb").read()
    new_src_lf = open(NEW_FILE, "rb").read()
    new_src_crlf = new_src_lf.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

    starts = []
    pos = 0
    while True:
        i = data.find(START_ANCHOR, pos)
        if i == -1: break
        starts.append(i); pos = i + 1
    if len(starts) != 1:
        print(f"ERROR: expected 1 start match, got {len(starts)} at {starts}", file=sys.stderr)
        return 2
    start = starts[0]

    ends = []
    pos = start
    while True:
        i = data.find(END_ANCHOR, pos)
        if i == -1: break
        ends.append(i); pos = i + 1
    if len(ends) != 1:
        print(f"ERROR: expected 1 end match after start, got {len(ends)} at {ends}", file=sys.stderr)
        return 3
    line_end = data.find(b"\r\n", ends[0])
    if line_end == -1:
        print("ERROR: end anchor not terminated by CRLF", file=sys.stderr)
        return 4
    end_excl = line_end + 2

    old_block = data[start:end_excl]
    print(f"Replacing {end_excl - start:,} bytes ({old_block.count(b'\r\n')} lines) "
          f"with {len(new_src_crlf):,} bytes ({new_src_crlf.count(b'\r\n')} lines)")

    patched = data[:start] + new_src_crlf + data[end_excl:]
    open(TARGET, "wb").write(patched)
    print(f"OK wrote {len(patched):,} bytes to {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
