# new_boq_data_v3.py
# 2026-06-21 -- in-place patches to the v2 catalogue + templates after the
# owner's walkthrough.
#
#   1. Section A (Switch Boards) brand: Memshield -> Eaton.
#   2. Section B renamed "SUBFEEDER CABLES AND EARTHLEADS" -> "FEEDERS AND
#      SUBFEEDERS" with the same items.
#   3. Each section gets a `subheading` string -- the verb+brand instruction
#      line the auditorium sample puts beneath the section letter heading.
#
# This runs after v2 is loaded into the module namespace, mutates the
# already-defined _BOQ_PROJECT_TEMPLATES + _BOQ_SECTION_ITEM_CATALOG in
# place, and re-binds the helpers. No new dict literal -- so the patch is
# tiny and never drifts out of sync with v2's shape.


# ---- Section-level subheading per Section TITLE -------------------------
_BOQ_SECTION_SUBHEADINGS = {
    "SWITCH BOARDS AND DISTRIBUTION BOARDS":
        "Supply and install the following as Eaton or approved equal",
    "FEEDERS AND SUBFEEDERS":
        "Supply, lay and terminate as armoured or non-armoured cables of approved brands e.g. Tropical or Kable Metal",
    "SUBFEEDER CABLES AND EARTHLEADS":
        "Supply, lay and terminate as armoured or non-armoured cables of approved brands e.g. Tropical or Kable Metal",
    "WIRING OF POINTS":
        "Wire the following points in conduit/trunking as directed using PVC insulated copper cable",
    "LUMINAIRES":
        "Supply and fix the following luminaires as Philips or approved equal",
    "ACCESSORIES":
        "Supply and fix the following accessories as MK or approved equal",
    "BONDING AND EARTHING":
        "Supply, install and test the following bonding and earthing items",
    "EARTH ELECTRODE NETWORK":
        "Supply and install the earth electrode network",
    "WIRING OF FIRE POINTS":
        "Wire the following fire detection points using fire-resistant cable",
    "FIRE PANEL AND ACCESSORIES":
        "Supply, install, connect and commission as Hochiki or approved equal",
    "DATA EQUIPMENT AND ACCESSORIES":
        "Supply, install and commission as Cisco / Juniper or approved equal",
    "VOICE EQUIPMENT AND ACCESSORIES":
        "Supply, install and commission as Panasonic or approved equal",
    "EQUIPMENT AND ACCESSORIES":
        "Supply, install and commission as Panasonic / Hikvision or approved equal",
    "SMALL SIGNAL IP NETWORK":
        "Supply, install and commission small signal IP network equipment",
    "NURSE CALL SYSTEM":
        "Supply, install and commission Nurse Call system as approved equal",
    "PRELIMINARY ITEMS":
        "Allow for the following preliminary items",
}


def _boq_section_subheading(section_title: str) -> str:
    """Return the brand/instruction subheading for a section title.
    Falls back to '' if no mapping exists."""
    if not section_title:
        return ""
    t = section_title.strip().upper()
    return _BOQ_SECTION_SUBHEADINGS.get(t, "")


# ---- Mutate the v2 templates dict in place ------------------------------
try:
    _tpls = _BOQ_PROJECT_TEMPLATES  # provided by v2 splice
except NameError:
    _tpls = None

if _tpls is not None:
    for _t in _tpls.values():
        for _b in _t.get("bills", []):
            for _s in _b.get("sections", []):
                _letter = (_s.get("letter") or "").upper()
                _title  = (_s.get("title")  or "").upper()
                # Rename Section B title for Bill 2
                if _letter == "B" and _b.get("no") == 2 and "SUBFEEDER" in _title:
                    _s["title"] = "FEEDERS AND SUBFEEDERS"
                # Swap Memshield -> Eaton in Section A items (Bill 2)
                if _letter == "A" and _b.get("no") == 2:
                    for _it in _s.get("items", []):
                        _it["desc"] = _it["desc"].replace("Memshield", "Eaton")
                # Attach subheading from the lookup map (uses possibly-renamed title)
                _s["subheading"] = _boq_section_subheading(_s["title"])


# ---- Mutate the v2 catalogue dict in place ------------------------------
try:
    _cat = _BOQ_SECTION_ITEM_CATALOG
except NameError:
    _cat = None

if _cat is not None:
    # 1. Memshield -> Eaton in SWITCH BOARDS section.
    _sb = _cat.get("SWITCH BOARDS AND DISTRIBUTION BOARDS")
    if _sb is not None:
        _cat["SWITCH BOARDS AND DISTRIBUTION BOARDS"] = [
            (d.replace("Memshield", "Eaton"), u, p) for (d, u, p) in _sb
        ]
    # 2. Alias FEEDERS AND SUBFEEDERS -> SUBFEEDER CABLES AND EARTHLEADS
    _sub = _cat.get("SUBFEEDER CABLES AND EARTHLEADS")
    if _sub is not None:
        _cat["FEEDERS AND SUBFEEDERS"] = list(_sub)


# ---- Override the catalogue lookup so the renamed section finds items ----
try:
    _orig_catalog_for_section = _boq_catalog_for_section
except NameError:
    _orig_catalog_for_section = None


def _boq_catalog_for_section(section_title: str) -> list:  # type: ignore[no-redef]
    if not section_title:
        return []
    s = section_title.strip()
    if s in _BOQ_SECTION_ITEM_CATALOG:
        return list(_BOQ_SECTION_ITEM_CATALOG[s])
    s_up = s.upper()
    if s_up in _BOQ_SECTION_ITEM_CATALOG:
        return list(_BOQ_SECTION_ITEM_CATALOG[s_up])
    # Map renamed section back to the original catalogue key as a fallback.
    aliases = {
        "FEEDERS AND SUBFEEDERS": "SUBFEEDER CABLES AND EARTHLEADS",
        "SUBFEEDER CABLES AND EARTHLEADS": "FEEDERS AND SUBFEEDERS",
    }
    if s_up in aliases and aliases[s_up] in _BOQ_SECTION_ITEM_CATALOG:
        return list(_BOQ_SECTION_ITEM_CATALOG[aliases[s_up]])
    for key, items in _BOQ_SECTION_ITEM_CATALOG.items():
        if s_up.startswith(key) or key.startswith(s_up):
            return list(items)
    return []


# ---- Expose helpers as Jinja globals so templates can call them ---------
try:
    app.jinja_env.globals["boq_section_subheading"] = _boq_section_subheading
    app.jinja_env.globals["boq_section_subheadings"] = _BOQ_SECTION_SUBHEADINGS
except Exception:
    pass
