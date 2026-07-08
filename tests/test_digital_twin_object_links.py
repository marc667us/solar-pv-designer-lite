"""Digital Twin object-link tests (Phase 2).

Every object must link into the EXISTING BOQ/finance/report/marketplace
surfaces -- never a new engine, never a broken URL.
"""
from __future__ import annotations

import dt_scene_v2 as dtv2


def _scene_with(layer, kind="box", meta=None):
    o = {"id": layer + "_x", "layer": layer, "kind": kind, "x": 0, "y": 1,
         "z": 0, "w": 3, "h": 3, "l": 3, "label": layer, "meta": meta or {}}
    base = {"site": {"land_side_m": 300}, "terrain": {"side_m": 300, "kind": "ground"},
            "buildings": [o], "layer_groups": [], "palette": {}}
    return dtv2.augment_scene_v2(base, {"id": 77})


def test_boq_and_finance_links_use_existing_steps():
    aug = _scene_with("control_room")
    obj = [o for o in aug["objects"] if o["layer"] == "control_room"][0]
    assert obj["links"]["boq"] == "/large-scale-solar/77/step9"
    assert obj["links"]["financial"] == "/large-scale-solar/77/step8"
    assert obj["links"]["reports"] == "/large-scale-solar/77/step13"


def test_marketplace_category_mapping():
    cases = {
        "pv_row": "pv_modules", "inverter": "inverters",
        "transformer": "transformers", "battery_room": "battery_systems",
        "cctv_pole": "cctv", "lighting_pole": "lighting",
    }
    for layer, cat in cases.items():
        aug = _scene_with(layer)
        obj = [o for o in aug["objects"] if o["layer"] == layer][0]
        assert obj["links"]["marketplace"] == "/marketplace?cat=" + cat


def test_unmapped_layer_has_no_marketplace_link():
    aug = _scene_with("internal_roads")
    obj = [o for o in aug["objects"] if o["layer"] == "internal_roads"][0]
    assert obj["links"]["marketplace"] is None       # absent, not broken


def test_optional_links_are_none_not_missing():
    aug = _scene_with("control_room")
    obj = [o for o in aug["objects"] if o["layer"] == "control_room"][0]
    for k in ("bom", "maintenance", "datasheet"):
        assert k in obj["links"] and obj["links"][k] is None


def test_engineering_flags_by_layer():
    pv = _scene_with("pv_row", meta={"modules": 40})
    row = [o for o in pv["objects"] if o["layer"] == "pv_row"][0]
    assert row["engineering"]["rotatable"] is True
    assert row["engineering"]["quantity"] == 40
    xf = _scene_with("transformer")
    t = [o for o in xf["objects"] if o["layer"] == "transformer"][0]
    assert t["engineering"]["movable"] is True
