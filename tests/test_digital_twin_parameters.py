"""Digital Twin parameter / action effect tests (Phase 3 + Phase 6).

Integration through build_scene_from_project: the persisted row pitch and the
persisted transformer position must actually change the generated scene, and
the scene must come out augmented (dt_scene_v2). These are the server-side
effects the POST /dt/parameters and /dt/object-action routes rely on; the HTTP
routes themselves are verified live in the Supervisor gate.
"""
from __future__ import annotations

import json

import pytest

from new_capital_investment_routes import build_scene_from_project


def _proj(row_pitch=6.0, transformer_pos=None):
    pv = {"kwp": 100000, "module_wp": 550, "tilt_deg": 12, "azimuth_deg": 180,
          "row_pitch_m": row_pitch,
          "sizing": {"n_modules": 181818, "n_central_inverters": 4,
                     "central_inverter_kw": 1500}}
    elec = {"selected": ["transformers"]}
    if transformer_pos:
        elec["transformer_pos"] = transformer_pos
    return {
        "id": 42,
        "pv_config": json.dumps(pv),
        "facility_config": json.dumps({"buildings": ["control_room", "om_building"]}),
        "site_config": json.dumps({"land_area_ha": 125}),
        "electrical_config": json.dumps(elec),
        "technology_config": json.dumps({"selected": ["weather"]}),
        "gps_lat": 6.0, "gps_lon": 0.0, "country": "Ghana",
        "region": "Greater Accra", "target_kwp": 100000,
    }


def test_scene_is_augmented():
    scene = build_scene_from_project(_proj())
    assert scene["schema_version"] == "dt_scene_v2"
    assert scene["objects"], "augmented objects missing"


def test_row_pitch_changes_row_count():
    tight = build_scene_from_project(_proj(row_pitch=6.0))["pv"]["meta"]["n_rows"]
    wide = build_scene_from_project(_proj(row_pitch=12.0))["pv"]["meta"]["n_rows"]
    assert tight > wide, f"wider pitch should place fewer rows ({tight} vs {wide})"


def test_transformer_position_override_moves_object():
    scene = build_scene_from_project(_proj(transformer_pos={"x": 100.0, "z": -50.0}))
    xf = [o for o in scene["objects"] if o["id"] == "transformer_yard"]
    assert xf, "transformer_yard object not found"
    pos = xf[0]["transform"]["position"]
    assert pos[0] == pytest.approx(100.0)
    assert pos[2] == pytest.approx(-50.0)


def test_default_transformer_position_when_no_override():
    scene = build_scene_from_project(_proj())
    xf = [o for o in scene["objects"] if o["id"] == "transformer_yard"][0]
    pos = xf["transform"]["position"]
    # Default is the SE corner (positive x and z), not the origin.
    assert pos[0] > 0 and pos[2] > 0
