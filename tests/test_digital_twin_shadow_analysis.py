"""Digital Twin shadow-analysis tests (Phase 5).

Row-level, conservative model. Verifies night short-circuit, longer shadows at
low sun, tall-object attribution, and safe empty results.
"""
from __future__ import annotations

import dt_scene_v2 as dtv2


def _scene(rows=5, with_tower=False):
    objs_rows = [{"id": "row_%03d" % i, "layer": "pv_row", "kind": "box",
                  "x": -50 + i * 6, "y": 1.5, "z": 0, "w": 2, "h": 2.0, "l": 100,
                  "tilt_deg": 12, "azimuth_deg": 180, "meta": {"modules": 40}}
                 for i in range(1, rows + 1)]
    buildings = []
    if with_tower:
        # A tall control room just EAST of the row block: a morning (eastern)
        # sun casts its shadow WESTWARD across the rows sitting to its west.
        buildings.append({"id": "bldg_tower", "layer": "control_room",
                          "kind": "box", "x": -14, "y": 8, "z": 0, "w": 16,
                          "h": 16, "l": 16, "label": "Tower", "meta": {}})
    base = {"site": {"land_side_m": 300}, "terrain": {"side_m": 300, "kind": "ground"},
            "buildings": buildings,
            "pv": {"meta": {"row_pitch_m": 6, "modules_per_row": 40, "module_wp": 550},
                   "rows": objs_rows},
            "layer_groups": [], "palette": {}}
    return dtv2.augment_scene_v2(base, {"id": 1})


def test_night_returns_empty():
    scene = _scene()
    night = dtv2.sun_position(6.0, 0.0, 6, 1.0)
    r = dtv2.shadow_analysis(scene, night)
    assert r["is_night"] is True
    assert r["affected_objects"] == []
    assert r["summary"]["affected_rows"] == 0


def test_summary_shape():
    scene = _scene()
    sun = dtv2.sun_position(6.0, 0.0, 6, 9.0)
    r = dtv2.shadow_analysis(scene, sun)
    assert set(r) == {"sun", "is_night", "affected_objects", "summary"}
    assert "weighted_loss_pct" in r["summary"]
    assert r["summary"]["total_rows"] == 5


def test_tall_object_casts_on_rows_at_low_sun():
    scene = _scene(with_tower=True)
    low = dtv2.sun_position(6.0, 0.0, 6, 7.0)   # low eastern morning sun
    r = dtv2.shadow_analysis(scene, low)
    # At least one row should be flagged and attribute the tower as a cause.
    caused = [a for a in r["affected_objects"] if "bldg_tower" in (a.get("caused_by") or [])]
    assert caused, "expected the tower to shade at least one row at low sun"
    for a in caused:
        assert a["severity"] in ("light", "moderate", "heavy")
        assert 0 < a["shadow_loss_pct"] <= 45


def test_no_tower_no_attribution():
    scene = _scene(with_tower=False)
    low = dtv2.sun_position(6.0, 0.0, 6, 7.0)
    r = dtv2.shadow_analysis(scene, low)
    for a in r["affected_objects"]:
        assert not a["caused_by"], "no tall casters present, so none should be blamed"


def test_no_rows_safe():
    base = {"site": {"land_side_m": 300}, "terrain": {"side_m": 300, "kind": "ground"},
            "buildings": [], "pv": {"meta": {}, "rows": []}, "layer_groups": [], "palette": {}}
    scene = dtv2.augment_scene_v2(base, {"id": 1})
    r = dtv2.shadow_analysis(scene, dtv2.sun_position(6.0, 0.0, 6, 9.0))
    assert r["affected_objects"] == []
    assert r["summary"]["weighted_loss_pct"] == 0.0
