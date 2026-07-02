# -*- coding: utf-8 -*-
"""
patch_webapp_ci_cell_cap.py
===========================
Owner feedback: Step 9 auto-building every catalog item at qty=1 produced far
too many cells (~3012 for a 5-building plant) and an inflated total.

Alternative: seed a small REPRESENTATIVE sample per section (cap per section)
plus a hard per-floor ceiling, so the generated BOQ is a lean starting point
the user expands via the standard Build-all page. Transparent (not silent):
the caps are named module constants and the Step 9 flash calls them a sample.

Byte-level, CRLF-aware, idempotent.
"""

PATH = "web_app.py"


def crlf(s: str) -> bytes:
    return s.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")


data = open(PATH, "rb").read()

if b"_CI_MAX_ITEMS_PER_SECTION" in data:
    print("already patched - no-op")
    raise SystemExit(0)

# --- R1: module constants before the helper ---
R1_ANCHOR = crlf(
    "def _ci_autobuild_floor_items(fid, bid, pid, uid, service_codes):\r\n"
)
assert data.count(R1_ANCHOR) == 1, "R1 anchor not unique"
R1_NEW = crlf('''# Step 9 auto-build is a LEAN STARTER BOQ, not the full catalog. Seed a small
# representative sample per section (the user expands via Build-all). Tune here.
_CI_MAX_ITEMS_PER_SECTION = 1
_CI_MAX_ITEMS_PER_FLOOR = 500


def _ci_autobuild_floor_items(fid, bid, pid, uid, service_codes):
''')
data = data.replace(R1_ANCHOR, R1_NEW, 1)

# --- R2: cap items per section during row build ---
R2_OLD = crlf("        for item in (cat or []):\r\n")
assert data.count(R2_OLD) == 1, "R2 anchor not unique"
R2_NEW = crlf(
    "        # Representative sample only - cap items per section.\r\n"
    "        for item in (cat or [])[:_CI_MAX_ITEMS_PER_SECTION]:\r\n"
)
data = data.replace(R2_OLD, R2_NEW, 1)

# --- R3: hard per-floor ceiling in the insert loop ---
R3_OLD = crlf(
    "        for r in rows:\r\n"
    "            try:\r\n"
    "                basic = float(r.get(\"basic\") or 0.0)\r\n"
)
assert data.count(R3_OLD) == 1, "R3 anchor not unique"
R3_NEW = crlf(
    "        for r in rows:\r\n"
    "            if inserted >= _CI_MAX_ITEMS_PER_FLOOR:\r\n"
    "                break\r\n"
    "            try:\r\n"
    "                basic = float(r.get(\"basic\") or 0.0)\r\n"
)
data = data.replace(R3_OLD, R3_NEW, 1)

open(PATH, "wb").write(data)
print("web_app.py cell caps applied "
      "(per-section=%s, per-floor=%s)" % (1, 500))
