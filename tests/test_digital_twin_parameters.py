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


def test_row_pitch_spreads_the_field_without_inventing_or_deleting_panels():
    """Widening the pitch makes the ARRAY LONGER. It does not change how many panels there
    are.

    This test used to assert the opposite -- that a wider pitch yields FEWER rows -- because
    the pre-rebuild twin fitted rows into a fixed rectangle and silently dropped whatever did
    not fit. That is exactly the fabrication the owner caught in the 2026-07-11 review ("wrong
    panel count"), and the rebuilt `build_scene_from_project` is an exact copy of the design:
    the design says 181,818 modules, so the twin places 181,818 modules and grows the land to
    suit. Pitch is a LAYOUT parameter, not a capacity one.
    """
    tight = build_scene_from_project(_proj(row_pitch=6.0))["pv"]["meta"]
    wide = build_scene_from_project(_proj(row_pitch=12.0))["pv"]["meta"]

    assert wide["field_l_m"] > tight["field_l_m"], "a wider pitch must lengthen the field"
    assert tight["row_pitch_m"] == 6.0 and wide["row_pitch_m"] == 12.0

    # The design's module count is honoured exactly, at BOTH pitches. This is the guarantee
    # the whole twin rebuild exists to make.
    assert tight["n_modules_placed"] == tight["n_modules_planned"] == 181818
    assert wide["n_modules_placed"] == wide["n_modules_planned"] == 181818


def test_transformer_position_override_moves_object():
    """The Phase-6 drag persists as electrical_config.transformer_pos and must survive a
    rebuild. The object it moves is the SUBSTATION COMPOUND -- the rebuilt scene models a real
    substation (`substation_pad` + `grid_transformer_N` + MV switchgear) where the old one had
    a single abstract `transformer_yard` box."""
    scene = build_scene_from_project(_proj(transformer_pos={"x": 100.0, "z": -50.0}))
    xf = [o for o in scene["objects"] if o["id"] == "substation_pad"]
    assert xf, "substation_pad object not found"
    pos = xf[0]["transform"]["position"]
    assert pos[0] == pytest.approx(100.0)
    assert pos[2] == pytest.approx(-50.0)


def test_default_transformer_position_when_no_override():
    scene = build_scene_from_project(_proj())
    xf = [o for o in scene["objects"] if o["id"] == "substation_pad"][0]
    pos = xf["transform"]["position"]
    # Default is the SE corner (positive x and z), not the origin.
    assert pos[0] > 0 and pos[2] > 0
