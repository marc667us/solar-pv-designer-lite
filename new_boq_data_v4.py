# new_boq_data_v4.py
# 2026-06-21 -- owner ask: every template's Bill 2 must have an
# "EARTHING AND EARTH LEADS" section directly below FEEDERS AND
# SUBFEEDERS. Single-core earth lead lines that previously rode along
# Section B are moved into the new Section C, plus a handful of standard
# earthing-component lines. The existing Sections C/D/E (Wiring,
# Luminaires, Accessories) renumber to D/E/F.
#
# Same in-place mutation pattern as v3 -- runs after v3 has populated
# _BOQ_PROJECT_TEMPLATES and _BOQ_SECTION_ITEM_CATALOG.


def _it(desc, unit, qty, basic, spec=""):
    return {"desc": desc, "unit": unit, "qty": qty, "basic": basic, "spec": spec}


# Per-section earth lead items that should accompany the auditorium-style
# main feeders. Index keyed by floor area scale (multiplier 0.4 = small
# residence, 1.0 = office, 1.5 = auditorium).
def _scaled_earth_items(scale: float = 1.0):
    def q(n): return max(1, int(round(n * scale)))
    return [
        _it("Supply, lay and terminate 1c x 25mm2 PVC insulated copper cable as earth lead", "M",   q(25), 65),
        _it("Supply, lay and terminate 1c x 16mm2 PVC insulated copper cable as earth lead", "M",   q(40), 42),
        _it("Supply, lay and terminate 1c x 10mm2 PVC insulated copper cable as earth lead", "M",   q(40), 27),
        _it("Supply, lay and terminate 1c x 6mm2 PVC insulated copper cable as earth lead",  "M",   q(30), 18),
        _it("Supply and install 50mm x 6mm copper earth bar c/w mounting accessories",       "Nos.", q(2), 380),
        _it("Supply and install earth tape clamp",                                            "Nos.", q(10),  45),
        _it("Supply and install 35mm2 bare copper bonding tape",                              "M",   q(20), 120),
    ]


_EARTHING_SUBHEADING = (
    "Supply, lay and terminate earth leads of approved brands "
    "e.g. Tropical or Kable Metal -- c/w lugs, glands and cable markers"
)


def _is_earth_lead(desc: str) -> bool:
    d = (desc or "").lower()
    return (
        "1c x" in d
        and ("earth lead" in d or "earth jumper" in d)
    )


# ---- Mutate templates in place ------------------------------------------
try:
    _tpls = _BOQ_PROJECT_TEMPLATES
except NameError:
    _tpls = None


def _renumber_sections_after(sections, start_letter: str) -> None:
    """Renumber sections whose letter is >= start_letter by +1.
    Stops at Z. Sections inserted with empty letter are ignored."""
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if start_letter not in letters:
        return
    base = letters.index(start_letter)
    # Walk backwards so we don't overwrite letters that will themselves move.
    for s in reversed(sections):
        L = (s.get("letter") or "").upper()
        if L in letters and letters.index(L) >= base:
            idx = letters.index(L)
            if idx + 1 < len(letters):
                s["letter"] = letters[idx + 1]


def _build_earthing_section(scale: float = 1.0) -> dict:
    return {
        "letter":     "C",
        "title":      "EARTHING AND EARTH LEADS",
        "subsection": "",
        "subheading": _EARTHING_SUBHEADING,
        "items":      _scaled_earth_items(scale),
    }


if _tpls is not None:
    # Per-template scale for earth lead quantities (auditorium > office > hostel ~ residence).
    _scale_by_slug = {
        "auditorium-1ugls": 1.5,
        "office-typical":   1.0,
        "hospital-ward":    1.2,
        "hostel-typical":   0.8,
        "residence-typical":0.5,
    }
    for _slug, _t in _tpls.items():
        # Find Bill 2
        _bill2 = next((b for b in _t.get("bills", []) if b.get("no") == 2), None)
        if not _bill2:
            continue
        # Check we don't already have an EARTHING AND EARTH LEADS section
        if any((s.get("title", "") == "EARTHING AND EARTH LEADS") for s in _bill2["sections"]):
            continue
        # Find the position of Section B (Feeders and Subfeeders).
        _b_idx = None
        for _i, _s in enumerate(_bill2["sections"]):
            if (_s.get("letter") or "").upper() == "B":
                _b_idx = _i
                break
        if _b_idx is None:
            continue
        # Move any "1c x ... earth lead" items from Section B to a holding list.
        _section_b = _bill2["sections"][_b_idx]
        _earth_held = [it for it in _section_b["items"] if _is_earth_lead(it["desc"])]
        _section_b["items"] = [it for it in _section_b["items"] if not _is_earth_lead(it["desc"])]
        # Renumber subsequent sections (C -> D, D -> E, E -> F)
        _renumber_sections_after(_bill2["sections"], "C")
        # Build the new Section C: held earth leads first, then standard earthing items.
        _scale = _scale_by_slug.get(_slug, 1.0)
        _new = _build_earthing_section(_scale)
        if _earth_held:
            _new["items"] = _earth_held + _new["items"]
        # Insert directly after Section B
        _bill2["sections"].insert(_b_idx + 1, _new)


# ---- Mutate catalogue: add a key for the new section --------------------
try:
    _cat = _BOQ_SECTION_ITEM_CATALOG
except NameError:
    _cat = None

if _cat is not None and "EARTHING AND EARTH LEADS" not in _cat:
    _cat["EARTHING AND EARTH LEADS"] = [
        ("Supply, lay and terminate 1c x 25mm2 PVC insulated copper cable as earth lead", "M",   65),
        ("Supply, lay and terminate 1c x 16mm2 PVC insulated copper cable as earth lead", "M",   42),
        ("Supply, lay and terminate 1c x 10mm2 PVC insulated copper cable as earth lead", "M",   27),
        ("Supply, lay and terminate 1c x 6mm2 PVC insulated copper cable as earth lead",  "M",   18),
        ("Supply, lay and terminate 1c x 4mm2 PVC insulated copper cable as earth lead",  "M",   12),
        ("Supply and install 50mm x 6mm copper earth bar c/w mounting accessories",       "Nos.", 380),
        ("Supply and install earth tape clamp",                                            "Nos.",  45),
        ("Supply and install 35mm2 bare copper bonding tape",                              "M",   120),
        ("Supply and install earth boss",                                                  "Nos.",  85),
    ]


# ---- Register the new subheading + tweak existing ones ------------------
try:
    _BOQ_SECTION_SUBHEADINGS["EARTHING AND EARTH LEADS"] = _EARTHING_SUBHEADING
    # Owner-revised WIRING OF POINTS subheading per the auditorium sample.
    _BOQ_SECTION_SUBHEADINGS["WIRING OF POINTS"] = (
        "Wire the following using PVC insulated copper conduit wires "
        "with appropriate coloured codes"
    )
except NameError:
    pass


# ---- Also apply the v4 subheadings to any template sections already
# loaded (so the template-checkbox view reflects them too).
if _tpls is not None:
    for _t in _tpls.values():
        for _b in _t.get("bills", []):
            for _s in _b.get("sections", []):
                _title_up = (_s.get("title") or "").upper()
                if _title_up in _BOQ_SECTION_SUBHEADINGS:
                    _s["subheading"] = _BOQ_SECTION_SUBHEADINGS[_title_up]
