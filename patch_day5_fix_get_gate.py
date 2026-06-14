"""Day 5 patch fix: the GET-time engine call still gated on ?v2=1,
but the template was flipped to make v2 the default (?v1=1 = back-out).
Result: every visit lands on v2 mode but never fires the engine, so the
3D canvas renders with engine-data = {} and the user sees nothing.

One-line fix — drop the `request.args.get("v2") and` from the gate.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"

OLD = b'    if request.args.get("v2") and not shading.get("engine"):\r\n'
NEW = ('    # Engine runs on GET whenever no engine output exists yet, regardless\r\n'
       '    # of the v1/v2 flag — the template decides which view to render.\r\n'
       '    if not shading.get("engine"):\r\n').encode("utf-8")


def patch():
    src = open(TARGET, "rb").read()
    if b"Engine runs on GET whenever no engine output exists yet" in src:
        print("[skip] already patched")
        return 0
    if OLD not in src:
        print("[fail] anchor not found")
        return 2
    open(TARGET, "wb").write(src.replace(OLD, NEW, 1))
    print("[ok] GET-time engine call now runs unconditionally")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
