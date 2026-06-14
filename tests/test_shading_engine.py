"""Tests for engine/shading_engine.py.

Verifies the deterministic core that the AI 3D Shading Simulation Agent
delegates every numeric output to. Run with::

    python -m pytest tests/test_shading_engine.py -v
"""
from __future__ import annotations

import math
from datetime import datetime

import pytest

from engine.shading_engine import (
    Obstruction,
    SHADING_BUCKETS,
    build_panel_grid,
    energy_loss_with_electrical_model,
    pick_shading_bucket,
    project_shadow_polygon,
    run_full_analysis,
    shaded_panel_fractions,
    sun_position,
    sun_ray_vector,
    time_series_shading,
)


# ────────────────────────────────────────────────────────────────────
# Sun position
# ────────────────────────────────────────────────────────────────────

class TestSunPosition:
    """NOAA SPA simplified should match published values to ~0.5°."""

    def test_accra_summer_solstice_noon(self):
        # Accra, Ghana — 5.6° N, -0.2° E. 21 June solar noon (~12:08 local).
        # Sun is ~17° north of zenith because declination (+23.45°) is north
        # of the site (5.6°N); altitude = 90 - |5.6 - 23.45| ≈ 72.1°.
        sp = sun_position(5.6, -0.2, datetime(2026, 6, 21, 12, 8))
        assert sp["is_daytime"] is True
        assert 68.0 < sp["altitude_deg"] < 76.0
        # Azimuth near 0° (North) or 360° — sun is to the north at noon.
        az = sp["azimuth_deg"]
        assert az < 30 or az > 330, f"expected near-north azimuth, got {az}"

    def test_london_winter_low_sun(self):
        # London — 51.5° N, -0.1° E. 21 December noon — should be very low.
        sp = sun_position(51.5, -0.1, datetime(2026, 12, 21, 12, 0))
        assert sp["is_daytime"] is True
        # Winter solstice sun ≈ 15° at London.
        assert 10.0 < sp["altitude_deg"] < 20.0
        # South-facing (azimuth ≈ 180°).
        assert 170.0 < sp["azimuth_deg"] < 190.0

    def test_pre_sunrise_returns_negative_altitude(self):
        # Accra pre-dawn — sun below horizon.
        sp = sun_position(5.6, -0.2, datetime(2026, 6, 21, 4, 0))
        assert sp["altitude_deg"] < 0
        assert sp["is_daytime"] is False

    def test_ray_vector_points_downward_when_sun_up(self):
        # Sun at 45° altitude due south should give ray pointing North-down.
        ray = sun_ray_vector(45.0, 180.0)
        assert ray[2] < 0           # going downward
        assert ray[1] > 0           # towards +y (North) — sun is south
        # Unit length.
        mag = math.sqrt(ray[0]**2 + ray[1]**2 + ray[2]**2)
        assert abs(mag - 1.0) < 1e-6


# ────────────────────────────────────────────────────────────────────
# Panel grid
# ────────────────────────────────────────────────────────────────────

class TestPanelGrid:

    def test_zero_panels_returns_empty(self):
        assert build_panel_grid(0, tilt_deg=15, array_azimuth_deg=180) == []

    def test_panel_count_matches_request(self):
        panels = build_panel_grid(12, tilt_deg=15, array_azimuth_deg=180)
        assert len(panels) == 12

    def test_panel_face_normal_is_outward_unit_vector(self):
        # For any positive tilt the panel normal must have +z (outward,
        # i.e. away from the ground) and be unit length.
        panels = build_panel_grid(1, tilt_deg=30, array_azimuth_deg=180)
        n = panels[0].normal
        assert n[2] > 0.5, f"expected upward-leaning normal, got {n}"
        mag = math.sqrt(n[0]**2 + n[1]**2 + n[2]**2)
        assert abs(mag - 1.0) < 1e-6, f"normal not unit length: |n|={mag}"

    def test_flat_array_has_straight_up_normal(self):
        # Tilt 0 → normal is (0,0,1) exactly, regardless of azimuth.
        for az in (0, 90, 180, 270):
            panels = build_panel_grid(1, tilt_deg=0, array_azimuth_deg=az)
            n = panels[0].normal
            assert abs(n[2] - 1.0) < 1e-6, f"az={az}: nz={n[2]} (expected 1.0)"
            assert abs(n[0]) < 1e-6 and abs(n[1]) < 1e-6


# ────────────────────────────────────────────────────────────────────
# Shadow projection + per-panel intersection
# ────────────────────────────────────────────────────────────────────

class TestShadowProjection:

    def _flat_array(self, n=4):
        # Flat horizontal panel grid so shadow projection math is intuitive.
        return build_panel_grid(n, tilt_deg=0, array_azimuth_deg=180,
                                panel_w_m=1.0, panel_h_m=1.0,
                                col_gap_m=0.0, row_gap_m=0.0, cols=2)

    def test_no_shadow_below_horizon(self):
        panels = self._flat_array(4)
        obs = [Obstruction(obs_id=1, type="building", height_m=10,
                           width_m=5, depth_m=5, distance_m=5,
                           direction="South")]
        # Sun below horizon → all panels fully un-producing (returned as 1.0
        # to signal "no power" — note this is the "fraction shaded" output
        # which for the energy model means the panel can't produce).
        fracs = shaded_panel_fractions(panels, obs, -5.0, 180.0)
        assert all(f == 1.0 for f in fracs)

    def test_no_obstructions_means_no_shading(self):
        panels = self._flat_array(4)
        fracs = shaded_panel_fractions(panels, [], 60.0, 180.0)
        assert all(f == 0.0 for f in fracs)

    def test_tall_close_obstruction_shades_panels(self):
        # Sun low at 20° altitude, due South. A 10-m tall wall 2 m to the
        # South should cast a long shadow over the panels (centred at origin).
        panels = self._flat_array(4)
        obs = [Obstruction(obs_id=1, type="building", height_m=10,
                           width_m=10, depth_m=2, distance_m=2,
                           direction="South")]
        fracs = shaded_panel_fractions(panels, obs, 20.0, 180.0)
        # At least one panel should be shaded.
        assert any(f > 0.0 for f in fracs), f"expected shading, got {fracs}"

    def test_distant_obstruction_misses_panels(self):
        # Sun high (75° at noon), 5 m tall obstruction 200 m away
        # → shadow falls way past the array.
        panels = self._flat_array(4)
        obs = [Obstruction(obs_id=1, type="tree", height_m=5,
                           width_m=2, depth_m=2, distance_m=200,
                           direction="South")]
        fracs = shaded_panel_fractions(panels, obs, 75.0, 180.0)
        # No panel should be fully shaded.
        assert max(fracs) < 0.50


# ────────────────────────────────────────────────────────────────────
# Time series + energy loss model
# ────────────────────────────────────────────────────────────────────

class TestTimeSeriesAndEnergyModel:

    def test_unshaded_day_has_zero_loss(self):
        panels = build_panel_grid(10, tilt_deg=15, array_azimuth_deg=180)
        series = time_series_shading(
            panels, obstructions=[],
            lat_deg=5.6, lon_deg=-0.2,
            on_date=datetime(2026, 6, 21),
            tz_offset_h=0.0, step_minutes=60,
        )
        energy = energy_loss_with_electrical_model(series, mitigation="None")
        assert energy["system_loss_pct"] == 0.0

    def test_per_panel_mppt_beats_no_mitigation(self):
        # One severe obstruction. Compare mitigation strategies:
        # No bypass < bypass diodes < optimisers (lower system loss).
        panels = build_panel_grid(20, tilt_deg=15, array_azimuth_deg=180)
        obs = [Obstruction(obs_id=1, type="building", height_m=20,
                           width_m=15, depth_m=10, distance_m=8,
                           direction="South")]
        series = time_series_shading(
            panels, obstructions=obs,
            lat_deg=5.6, lon_deg=-0.2,
            on_date=datetime(2026, 6, 21),
            tz_offset_h=0.0, step_minutes=60,
        )
        none_loss = energy_loss_with_electrical_model(
            series, mitigation="None")["system_loss_pct"]
        bypass_loss = energy_loss_with_electrical_model(
            series, mitigation="Bypass diodes")["system_loss_pct"]
        opt_loss = energy_loss_with_electrical_model(
            series, mitigation="DC optimisers")["system_loss_pct"]
        # Each mitigation step should NOT make things worse.
        assert bypass_loss <= none_loss + 0.01
        assert opt_loss <= bypass_loss + 0.01


# ────────────────────────────────────────────────────────────────────
# Bucket selection
# ────────────────────────────────────────────────────────────────────

class TestBucketSelection:

    @pytest.mark.parametrize("loss,expected_label,expected_factor", [
        (0.0,  "No shading",            1.00),
        (4.9,  "No shading",            1.00),
        (5.0,  "Very light shading",    0.95),
        (12.0, "Light shading",         0.90),
        (18.0, "Moderate shading",      0.85),
        (24.9, "Significant shading",   0.80),
        (25.0, "Heavy shading",         0.75),
        (33.0, "Severe shading",        0.70),
        (100.0,"Very severe shading",   0.60),
    ])
    def test_bucket_selection_is_conservative(self, loss, expected_label,
                                              expected_factor):
        label, _, factor = pick_shading_bucket(loss)
        assert label == expected_label
        assert factor == expected_factor

    def test_buckets_table_matches_spec(self):
        # Spec rows: 0/5/10/15/20/25/30/40 → 1.00/0.95/0.90/0.85/0.80/0.75/0.70/0.60
        expected = [
            (0.0, 1.00), (5.0, 0.95), (10.0, 0.90), (15.0, 0.85),
            (20.0, 0.80), (25.0, 0.75), (30.0, 0.70), (40.0, 0.60),
        ]
        actual = [(b[1], b[2]) for b in SHADING_BUCKETS]
        assert actual == expected


# ────────────────────────────────────────────────────────────────────
# Top-level pipeline
# ────────────────────────────────────────────────────────────────────

class TestFullPipeline:

    def test_run_full_analysis_returns_complete_contract(self):
        result = run_full_analysis(
            lat_deg=5.6, lon_deg=-0.2,
            on_date=datetime(2026, 6, 21),
            tz_offset_h=0.0,
            num_panels=12, tilt_deg=15, array_azimuth_deg=180,
            mount_height_m=1.0,
            obstructions=[
                Obstruction(obs_id=1, type="10-storey building",
                            height_m=32, width_m=18, depth_m=12,
                            distance_m=18, direction="West"),
            ],
            mitigation="Bypass diodes",
        )
        for key in ["panels", "series", "energy", "bucket_label",
                    "bucket_loss_pct", "bucket_factor", "shading_start",
                    "shading_end", "shading_duration_h", "affected_panels",
                    "heavily_affected", "total_panels", "n_strings",
                    "mitigation"]:
            assert key in result, f"missing key {key!r}"
        # Factor must be one of the 8 spec rows.
        valid_factors = {b[2] for b in SHADING_BUCKETS}
        assert result["bucket_factor"] in valid_factors

    def test_unobstructed_site_produces_factor_1(self):
        result = run_full_analysis(
            lat_deg=5.6, lon_deg=-0.2,
            on_date=datetime(2026, 6, 21),
            tz_offset_h=0.0,
            num_panels=20, tilt_deg=15, array_azimuth_deg=180,
            mount_height_m=1.0, obstructions=[],
            mitigation="None",
        )
        assert result["bucket_factor"] == 1.00
        assert result["bucket_label"] == "No shading"
        assert result["affected_panels"] == 0
