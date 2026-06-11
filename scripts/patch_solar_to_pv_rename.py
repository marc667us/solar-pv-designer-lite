"""Byte-replace rename of display text in web_app.py: Solar PV -> PV Solar.

Follows CLAUDE.md §CRITICAL: never use the Edit tool on web_app.py
(mojibake + CRLF would get corrupted). Each replacement is a narrow,
phrase-specific byte substitution with an asserted expected occurrence
count (per the Codex rename-plan review, finding #5).

Skipped here on purpose — these are FUNCTIONAL/identifier, not display:
  • Web search queries (lines ~8856, ~8860, ~9461) — 'solar PV' as Google query
  • Keyword match filters (lines ~9278, ~9509) — matches scraped content
  • AI analyst system prompt (line ~8979) — LLM domain anchor
  • _GH_REPO constant (line ~10082) — GitHub slug

Idempotent: re-running after success is a no-op (asserts will fail
fast because the needles no longer exist).
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "web_app.py"

# Each entry: (needle_bytes, expected_count, replacement_bytes, why)
# Needles MUST be display-text-specific so the C-category functional lines
# stay untouched. See reviews/rename-plan.md §4c.
EDITS: list[tuple[bytes, int, bytes, str]] = [
    (b"Intelligent Solar PV Design & Financial",  1,
     b"Intelligent PV Solar Design & Financial",
     "line ~2150: about-page markdown header"),

    (b"professional solar PV design platform",    1,
     b"professional pv solar design platform",
     "line ~2158: landing/about prose"),

    (b"Solar PV Panels",                          2,
     b"PV Solar Panels",
     "lines ~4643, ~5561: proposal BoQ row"),

    (b"Solar PV cert",                            3,
     b"PV Solar cert",
     "lines ~4836, ~4936, ~5729: engineer qualification"),

    (b"Solar PV design qualification",            2,
     b"PV Solar design qualification",
     "lines ~4965, ~5753: engineer cert sentence"),

    (b"# Solar PV System Proposal",               1,
     b"# PV Solar System Proposal",
     "line ~5172: markdown proposal heading"),

    (b'f"Solar PV Proposal',                      1,
     b'f"PV Solar Proposal',
     "line ~5835: PDF title (anchor — patcher scripts updated in lockstep)"),

    (b"Solar PV System Design Report",            1,
     b"PV Solar System Design Report",
     "line ~8355: docx run-text"),
]


def main() -> int:
    if not TARGET.exists():
        sys.exit(f"target not found: {TARGET}")
    data = TARGET.read_bytes()
    print(f"read {TARGET.name}: {len(data):,} bytes")

    new_data = data
    for needle, expected, replacement, why in EDITS:
        got = new_data.count(needle)
        if got != expected:
            sys.exit(
                f"abort: needle {needle!r} found {got} times, expected {expected}\n"
                f"  context: {why}\n"
                f"  fix: re-run discovery or update the EDITS table"
            )
        before = new_data
        new_data = new_data.replace(needle, replacement)
        assert before != new_data, f"replace was a no-op for {needle!r}"
        print(f"  ok: {got}x  {needle.decode('latin1')[:60]:60s}  -> {replacement.decode('latin1')[:60]}")

    if new_data == data:
        sys.exit("nothing changed — aborting write")
    TARGET.write_bytes(new_data)
    print(f"wrote {TARGET.name}: {len(new_data):,} bytes (delta {len(new_data)-len(data):+d})")

    # py_compile sanity check
    import py_compile
    try:
        py_compile.compile(str(TARGET), doraise=True)
        print(f"  py_compile OK")
    except py_compile.PyCompileError as e:
        sys.exit(f"py_compile FAILED post-edit:\n{e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
