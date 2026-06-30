"""Fix collisions when the same (bill_no, section_letter) renders more
than once on Build-all (typical for WIRING OF POINTS which appears
under multiple services).

Two changes:
  1. boq_floor_build_all.html: pass instance_id=loop.index0 into the
     partial via `{% with %}`.
  2. _boq_section_grid_inline.html: include instance_id in the sid
     so duplicate (bill_no, section_letter) pairs get distinct sids.
     Falls back to 0 when instance_id is not passed, so any other
     caller of the partial keeps its old sid.

Re-runnable byte patch.
"""
from __future__ import annotations
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
CRLF = b"\r\n"

def crlf(s):
    return s.replace(b"\r\n", b"\n").replace(b"\n", CRLF)

def replace_once(d, old, new, label):
    old_c, new_c = crlf(old), crlf(new)
    if new_c in d:
        print(f"  {label}: already patched, skipping"); return d
    n = d.count(old_c)
    if n != 1:
        sys.exit(f"  {label}: expected 1 OLD match, found {n}")
    print(f"  {label}: patched")
    return d.replace(old_c, new_c, 1)


# 1. build-all template: pass instance_id
B = REPO / "templates" / "boq_floor_build_all.html"
b = B.read_bytes()
B_OLD = b'      {% with bill_no=bill.no, bill_name=bill.name, section_letter=sec.letter, section_title=sec.title, subsection_label=sec.subsection, catalog=(sec.catalog or []), existing=(sec[\'items\'] or []) %}'
B_NEW = b'      {% with bill_no=bill.no, bill_name=bill.name, section_letter=sec.letter, section_title=sec.title, subsection_label=sec.subsection, catalog=(sec.catalog or []), existing=(sec[\'items\'] or []), instance_id=loop.index0 %}'
b = replace_once(b, B_OLD, B_NEW, "1: pass instance_id from build-all to partial")
B.write_bytes(b)


# 2. partial: make sid include instance_id
G = REPO / "templates" / "_boq_section_grid_inline.html"
g = G.read_bytes()
G_OLD = b"{% set sid = bill_no|string ~ '_' ~ section_letter|string %}"
G_NEW = b"{% set sid = bill_no|string ~ '_' ~ section_letter|string ~ '_' ~ (instance_id|default(0)|string) %}"
g = replace_once(g, G_OLD, G_NEW, "2: include instance_id in sid")
G.write_bytes(g)

print("done.")
