"""Reorder: the 2026-06-28 topic-training KB block landed AFTER the
2026-06-27 growth/marketplace block, so generic keywords like "marketplace",
"bom", "supplier", "boq" hit the older entries first and shadow the
specific topic-training answers.

Fix: lift the topic-training block from its current spot and reinsert it
right after acknowledgements, so it wins the first-match scan over the
broader growth/marketplace block.

Idempotent via the existing kb-topic-training-2026-06-28 sentinel + a
new placement marker.
"""
from __future__ import annotations
from pathlib import Path
import sys, re

TARGET = Path(__file__).parent / "web_app.py"

PLACE_SENTINEL = b"# kb-topic-training-2026-06-28-anchored"

CURRENT_HEAD = b"        # kb-topic-training-2026-06-28\r\n"
GROWTH_HEAD  = b"        # kb-growth-marketplace-2026-06-27\r\n"


def main() -> int:
    src = TARGET.read_bytes()
    if PLACE_SENTINEL in src:
        print("[skip] topic-training already anchored above growth/marketplace")
        return 0
    if CURRENT_HEAD not in src or GROWTH_HEAD not in src:
        print("[fail] missing one of the sentinels")
        return 2

    # Extract everything from CURRENT_HEAD up to (but not including) the
    # next stable sentinel after it -- which is the maintenance/alarm
    # anchor (kept stable across patches).
    MAINT_ANCHOR = (
        b'        # Monitoring/alarms before project (both mention "dashboard")\r\n'
    )
    start = src.find(CURRENT_HEAD)
    end   = src.find(MAINT_ANCHOR, start)
    if start < 0 or end < 0:
        print("[fail] could not delimit topic-training block")
        return 3
    BLOCK = src[start:end]
    if not BLOCK:
        print("[fail] empty block")
        return 4

    # Remove the block from its original location, then insert it BEFORE
    # the growth/marketplace block (so it wins first-match).
    new = src.replace(BLOCK, b"", 1)
    # Now insert before GROWTH_HEAD.
    # Tag the new placement with the PLACE_SENTINEL so a re-run is idempotent.
    REINSERT = (
        b"        " + PLACE_SENTINEL + b"\r\n"
        + BLOCK
    )
    new = new.replace(GROWTH_HEAD, REINSERT + GROWTH_HEAD, 1)

    # Compile-check
    try:
        compile(new, str(TARGET), "exec")
    except SyntaxError as e:
        print(f"[fail] SyntaxError at line {e.lineno}: {e.msg}")
        return 5

    TARGET.write_bytes(new)
    print(f"[ok] moved topic-training block ({len(BLOCK)} bytes) above growth/marketplace")
    return 0


if __name__ == "__main__":
    sys.exit(main())
