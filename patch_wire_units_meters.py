"""Wire units: Coils -> Meters (2026-06-30 owner directive).

A coil is 92 m, so the basic price per metre is coil_price / 92.
Applies to EVERY wire entry in the WIRING OF POINTS catalog -- both
the structured subsection block (Lighting/Socket/AC/Water Heater)
AND the legacy entries kept at the tail of the section.

Per-metre price table:
   1.5mm2: 391  / 92 = 4.25   (was per coil)
   2.5mm2: 653  / 92 = 7.10
   4.0mm2: 1037 / 92 = 11.27
   6.0mm2: 1500 / 92 = 16.30

Applies to BOTH catalogs (basic + v3 spec-formatted). Re-runnable.
"""
from __future__ import annotations
import re, sys
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web_app.py"
data = WEB.read_bytes()

PRICE_PER_METRE = {
    b"391":  b"4.25",
    b"653":  b"7.10",
    b"1037": b"11.27",
    b"1500": b"16.30",
}

# Match lines like ("...PVC...copper cable...", "Coils", PRICE),
# Whitespace varies across the file -- catch with \s+
WIRE_RE = re.compile(
    rb'\("([^"\r\n]*PVC[^"\r\n]*copper cable[^"\r\n]*)",(\s+)"Coils",(\s+)(391|653|1037|1500)\)'
)

count_updated = 0
already_updated = 0

def _do(m):
    global count_updated
    desc = m.group(1)
    sp1, sp2 = m.group(2), m.group(3)
    coil_price = m.group(4)
    per_m = PRICE_PER_METRE[coil_price]
    # Keep the alignment whitespace identical
    count_updated += 1
    return b'("' + desc + b'",' + sp1 + b'"M",    ' + sp2.lstrip() + per_m + b')'

# Check post-patch shape first to make this idempotent
POST_RE = re.compile(
    rb'\("([^"\r\n]*PVC[^"\r\n]*copper cable[^"\r\n]*)",\s+"M",\s+(4\.25|7\.10|11\.27|16\.30)\)'
)
already = len(POST_RE.findall(data))

new_data, n = WIRE_RE.subn(_do, data)
if n == 0 and already > 0:
    print(f"all {already} wire entries already converted to meters, nothing to do")
    sys.exit(0)
if n == 0:
    sys.exit("no wire entries found to convert -- catalog signature changed?")

WEB.write_bytes(new_data)
print(f"wire entries updated: {n}  (already-converted before this run: {already})")

# Sanity: report any "Coils" tuples that survived (should be 0 for wire-shaped ones)
remaining = re.findall(rb'\("([^"\r\n]*PVC[^"\r\n]*copper cable[^"\r\n]*)",\s+"Coils"', new_data)
print(f"PVC copper cable lines still on Coils: {len(remaining)}")
for r in remaining[:5]:
    print(f"  -> {r.decode(errors='replace')}")
