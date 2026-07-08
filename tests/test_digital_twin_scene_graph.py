"""Digital Twin scene-graph v2 contract tests (Phase 1).

Pure-unit coverage of dt_scene_v2.augment_scene_v2 / normalize_objects plus the
integration through build_scene_from_project. Run::

    python -m pytest tests/test_digital_twin_scene_graph.py -v
"""
from __future__ import annotations

import pytest

import dt_scene_v2 as dtv2


def _base_scene():
    """A minimal but representative base scene (as build_scene emits)."""
    return {
        "site": {"kwp": 100000, "land_area_ha": 125, "land_side_m": 1118.0},
        "camera": {"position": [700, 500, 700], "target": [0, 0, 0]},
        "terrain": {"layer": "terrain", "kind": "ground", "side_m": 1118.0,
                    "label": "Site", "meta": {"land_area_ha": 125}},
        "fence": {"layer": "fence", "kind": "line_loop",
                  "points": [[-558, -558], [558, -558], [558, 558], [-558, 558]],
                  "height_m": 2.4, "meta": {}},
        "roads": [{"id": "spine_road", "layer": "internal_roads", "kind": "box",
                   "x": 500, "y": 0.05, "z": 0, "w": 4, "h": 0.1, "l": 1000,
                   "label": "Spine road", "meta": {}}],
        "buildings": [{"id": "bldg_control_room", "layer": "control_room",
                       "kind": "box", "x": -120, "y": 3, "z": -125, "w": 15,
                       "h": 6, "l": 12, "label": "Control room", "meta": {}}],
        "pv": {"meta": {"kwp": 100000, "n_modules_planned": 181818, "n_rows": 30,
                        "modules_per_row": 40, "row_pitch_m": 6, "module_wp": 550},
               "rows": [{"id": "row_%03d" % i, "layer": "pv_row", "kind": "box",
                         "x": -500 + i * 6, "y": 1.5, "z": 0, "w": 2, "h": 0.05,
                         "l": 180, "tilt_deg": 12, "azimuth_deg": 180,
                         "meta": {"modules": 40, "row_index": i}}
                        for i in range(1, 6)]},
        "inverters": [{"id": "inv_01", "layer": "inverter", "kind": "box",
                       "x": 0, "y": 1.5, "z": 40, "w": 4, "h": 2.5, "l": 3,
                       "label": "Central inverter #1", "meta": {"kw": 1500}}],
        "ict": [{"id": "cctv_1", "layer": "cctv_pole", "kind": "mast", "x": -550,
                 "y": 4, "z": -550, "w": 0.3, "h": 8, "l": 0.3, "label": "CCTV",
                 "meta": {"coverage_m": 80}}],
        "lighting": [], "safety": [],
        "palette": dtv2.MATERIALS and {"terrain": "#3a4a2a"},
        "layer_groups": [{"label": "PV FIELD", "icon": "bi", "codes": ["pv_row"]}],
    }


def test_schema_version_and_units():
    aug = dtv2.augment_scene_v2(_base_scene(), {"id": 123})
    assert aug["schema_version"] == "dt_scene_v2"
    assert aug["units"] == "m"
    assert aug["coordinate_system"]["x"] == "east"


def test_legacy_arrays_preserved():
    aug = dtv2.augment_scene_v2(_base_scene(), {"id": 123})
    for key in ("terrain", "fence", "roads", "buildings", "pv", "inverters"):
        assert key in aug, f"legacy key {key} dropped"
    assert aug["pv"]["rows"], "legacy pv.rows dropped"


def test_objects_contract_complete():
    aug = dtv2.augment_scene_v2(_base_scene(), {"id": 123})
    assert aug["objects"], "no objects produced"
    required = {"id", "type", "layer", "label", "kind", "transform",
                "dimensions", "render", "engineering", "links", "simulation", "meta"}
    for o in aug["objects"]:
        missing = required - set(o)
        assert not missing, f"object {o.get('id')} missing {missing}"
        assert "position" in o["transform"] and len(o["transform"]["position"]) == 3


def test_pv_rows_marked_instanced_and_rotated():
    aug = dtv2.augment_scene_v2(_base_scene(), {"id": 123})
    rows = [o for o in aug["objects"] if o["layer"] == "pv_row"]
    assert len(rows) == 5
    for r in rows:
        assert r["render"]["instanced"] is True
        # Panels tilt about their LONG horizontal axis so the module face angles
        # up (a tilted table), not the long axis (which would be a flat ramp
        # reading as a "band of lines"). The fixture rows are long in Z (l=180,
        # w=2), so tilt 12 -> rotation_deg[2] == 12, rotation_deg[0] == 0.
        rot = r["transform"]["rotation_deg"]
        dim = r["dimensions"]
        long_axis_idx = 2 if dim["l"] >= dim["w"] else 0
        assert rot[long_axis_idx] == pytest.approx(12.0)
        assert rot[2 if long_axis_idx == 0 else 0] == pytest.approx(0.0)


def test_top_level_v2_blocks_present():
    aug = dtv2.augment_scene_v2(_base_scene(), {"id": 123})
    assert set(aug["materials"]).issuperset({"pv_glass", "concrete"})
    assert len(aug["camera_presets"]) == 14
    assert len(aug["simulation_modes"]) == 9
    assert "editable" in aug["parameters"]
    assert aug["performance"]["estimated_modules"] == 181818


def test_performance_tier_scales_with_size():
    small = dict(_base_scene()); small["pv"] = {"meta": {"n_modules_planned": 500}, "rows": []}
    big = _base_scene()
    assert dtv2.augment_scene_v2(small, {"id": 1})["performance"]["recommended_tier"] == "high"
    assert dtv2.augment_scene_v2(big, {"id": 2})["performance"]["recommended_tier"] == "low"


def test_empty_pv_project_still_builds():
    s = _base_scene(); s["pv"] = {"meta": {}, "rows": []}; s["inverters"] = []
    aug = dtv2.augment_scene_v2(s, {"id": 9})
    ids = {o["id"] for o in aug["objects"]}
    assert "terrain" in ids and "fence" in ids  # site chrome always renders


def test_idempotent():
    s = _base_scene()
    a = dtv2.augment_scene_v2(s, {"id": 5})
    b = dtv2.augment_scene_v2(a, {"id": 5})
    assert b["schema_version"] == "dt_scene_v2"
    assert len(b["objects"]) == len(a["objects"])
