"""Digital Twin sun-position tests (Phase 4).

dt_scene_v2.sun_position must be a backward-compatible SUPERSET of the legacy
5-key payload and add the extended engineering fields.
"""
from __future__ import annotations

import pytest

import dt_scene_v2 as dtv2


LEGACY_KEYS = {"altitude_deg", "azimuth_deg", "month", "hour", "is_daylight"}
EXTENDED_KEYS = {"declination_deg", "hour_angle_deg", "elevation_deg",
                 "sunrise_hour", "sunset_hour", "solar_noon_hour",
                 "shadow_length_factor", "timezone_offset_h", "refraction_applied"}


def test_legacy_keys_preserved():
    s = dtv2.sun_position(6.0, 0.0, 6, 12.0)
    assert LEGACY_KEYS.issubset(s)


def test_extended_keys_present_and_numeric():
    s = dtv2.sun_position(6.0, 0.0, 6, 9.0)
    assert EXTENDED_KEYS.issubset(s)
    for k in ("declination_deg", "sunrise_hour", "sunset_hour", "shadow_length_factor"):
        assert isinstance(s[k], (int, float))


def test_accra_summer_noon_high_sun():
    # Accra ~6N, June solar noon -> sun very high, daylight.
    s = dtv2.sun_position(6.0, 0.0, 6, 12.0)
    assert s["is_daylight"] is True
    assert s["altitude_deg"] > 70.0


def test_night_is_not_daylight():
    s = dtv2.sun_position(6.0, 0.0, 6, 2.0)
    assert s["is_daylight"] is False
    assert s["shadow_length_factor"] == 0.0


def test_sunrise_before_noon_before_sunset():
    s = dtv2.sun_position(6.0, 0.0, 3, 12.0)
    assert s["sunrise_hour"] < s["solar_noon_hour"] < s["sunset_hour"]
    # Near the equator in March, day length ~12h.
    assert 5.0 < s["sunrise_hour"] < 7.0
    assert 17.0 < s["sunset_hour"] < 19.0


def test_shadow_factor_longer_at_low_sun():
    noon = dtv2.sun_position(6.0, 0.0, 6, 12.0)
    morning = dtv2.sun_position(6.0, 0.0, 6, 7.0)
    assert morning["shadow_length_factor"] > noon["shadow_length_factor"]


def test_polar_night_does_not_crash():
    # High latitude midwinter -> acos clamp keeps it finite.
    s = dtv2.sun_position(80.0, 0.0, 12, 12.0)
    assert "sunrise_hour" in s and "sunset_hour" in s
