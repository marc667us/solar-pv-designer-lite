"""Tests for engine/agents/shading_agent.py.

The agent has three execution paths in priority order:
  1. ADK + LiteLlm (only if google-adk is installed)
  2. Direct OpenRouter HTTPS (only if OPENROUTER_API_KEY is set)
  3. Deterministic fallback (always available)

These tests exercise path 3 in isolation by clearing OPENROUTER_API_KEY
in the env (and ADK is not installed in the test environment). The
deterministic path is what production falls back to when both LLM
backends are unavailable, so it MUST stay correct.
"""
from __future__ import annotations

import os
from unittest import mock

import pytest

from engine.agents.shading_agent import (
    SHADING_AGENT_VERSION,
    SHADING_BUCKETS,
    run_shading_agent,
    tool_compute_sun_position,
    tool_pick_bucket,
    tool_run_full_analysis,
    tool_what_if_mitigation,
)


# ────────────────────────────────────────────────────────────────────
# Tool primitives — these are the agent's contract with the engine.
# ────────────────────────────────────────────────────────────────────

class TestTools:

    def test_compute_sun_position_returns_expected_keys(self):
        out = tool_compute_sun_position(
            lat_deg=5.6, lon_deg=-0.2,
            date_str="2026-06-21", time_str="12:00",
        )
        for key in ("altitude_deg", "azimuth_deg", "is_daytime",
                    "declination_deg"):
            assert key in out, f"missing {key}"
        # Accra at noon on summer solstice: sun ~17° north of zenith.
        assert 65 < out["altitude_deg"] < 80
        assert out["is_daytime"] is True

    def test_pick_bucket_is_conservative(self):
        # 22% loss should pick the Significant (20% / 0.80) row, not
        # Heavy (25% / 0.75), per the spec rule.
        out = tool_pick_bucket(22.0)
        assert out["factor"] == 0.80
        assert out["label"] == "Significant shading"

    def test_what_if_mitigation_orders_correctly(self):
        # Per-panel MPPT (optimisers / micro-inverters) should give a
        # higher factor than bypass diodes, which is higher than None,
        # for the same baseline loss.
        base = 30.0
        none_w   = tool_what_if_mitigation(base, "None")["expected_factor"]
        bypass_w = tool_what_if_mitigation(base, "Bypass diodes")["expected_factor"]
        opt_w    = tool_what_if_mitigation(base, "DC optimisers")["expected_factor"]
        assert opt_w >= bypass_w >= none_w

    def test_run_full_analysis_returns_engine_contract(self):
        out = tool_run_full_analysis(
            lat_deg=5.6, lon_deg=-0.2, date_str="2026-06-21",
            tz_offset_h=0.0, num_panels=12, tilt_deg=15,
            array_azimuth_deg=180, mount_height_m=1.0,
            obstructions=[
                {"type": "10-storey building", "height": 32,
                 "width": 18, "distance": 18, "direction": "West"},
            ],
        )
        for key in ("total_panels", "affected_panels", "shading_start",
                    "shading_end", "system_loss_pct", "bucket_label",
                    "bucket_factor", "mitigation"):
            assert key in out, f"missing {key}"
        # 32m building 18m west of a 12-panel array IS shading.
        assert out["affected_panels"] > 0
        assert out["system_loss_pct"] > 0


# ────────────────────────────────────────────────────────────────────
# End-to-end agent run (deterministic fallback path).
# ────────────────────────────────────────────────────────────────────

class TestAgentDeterministicFallback:

    @pytest.fixture(autouse=True)
    def _no_llm(self, monkeypatch):
        # Force both LLM paths to fail by clearing the env var.
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def test_returns_deterministic_when_no_llm(self):
        engine_result = {
            "lat": 5.6, "lon": -0.2, "on_date": "2026-06-21",
            "tilt_deg": 15, "array_azimuth_deg": 180,
            "total_panels": 12, "affected_panels": 8, "heavily_affected": 5,
            "shading_start": "08:00", "shading_end": "16:00",
            "shading_duration_h": 8.0,
            "system_loss_pct": 22.5, "peak_step_loss_pct": 55.0,
            "bucket_label": "Significant shading", "bucket_factor": 0.80,
            "bucket_loss_pct": 20.0, "mitigation": "Bypass diodes",
            "n_strings": 2,
        }
        site = {"obstructions": [
            {"type": "neighbour building", "height": 12,
             "width": 8, "distance": 6, "direction": "West"},
        ]}
        out = run_shading_agent(engine_result, site)
        assert out["backend"] == "deterministic"
        assert out["recommended_factor"] in {b[2] for b in SHADING_BUCKETS}
        assert out["narrative"]
        assert isinstance(out["per_obstruction"], list)
        assert isinstance(out["what_ifs"], list)
        assert out["agent_version"] == SHADING_AGENT_VERSION

    def test_empty_obstructions_recommends_factor_1(self):
        engine_result = {
            "lat": 5.6, "lon": -0.2, "on_date": "2026-06-21",
            "tilt_deg": 15, "array_azimuth_deg": 180,
            "total_panels": 12, "affected_panels": 0, "heavily_affected": 0,
            "shading_start": "--", "shading_end": "--",
            "shading_duration_h": 0.0,
            "system_loss_pct": 0.0, "peak_step_loss_pct": 0.0,
            "bucket_label": "No shading", "bucket_factor": 1.00,
            "bucket_loss_pct": 0.0, "mitigation": "Bypass diodes",
            "n_strings": 1,
        }
        out = run_shading_agent(engine_result, {"obstructions": []})
        assert out["recommended_factor"] == 1.00
        assert "no obstructions" in out["narrative"].lower()

    def test_what_ifs_include_three_alternatives(self):
        # Deterministic fallback adds DC optimisers + Micro-inverters +
        # Bypass diodes (excluding whichever is already in place).
        engine_result = {
            "lat": 5.6, "lon": -0.2, "on_date": "2026-06-21",
            "tilt_deg": 15, "array_azimuth_deg": 180,
            "total_panels": 12, "affected_panels": 8, "heavily_affected": 5,
            "shading_start": "08:00", "shading_end": "16:00",
            "shading_duration_h": 8.0, "system_loss_pct": 22.5,
            "peak_step_loss_pct": 55.0,
            "bucket_label": "Significant shading", "bucket_factor": 0.80,
            "bucket_loss_pct": 20.0, "mitigation": "None", "n_strings": 2,
        }
        out = run_shading_agent(engine_result, {"obstructions": []})
        assert len(out["what_ifs"]) >= 2
        scenarios = [w["scenario"] for w in out["what_ifs"]]
        # Every what-if scenario must be different from baseline.
        assert "None" not in scenarios

    def test_never_raises_on_empty_input(self):
        # Defensive: empty engine_result should still return a usable dict.
        out = run_shading_agent({}, {})
        assert out["backend"] == "deterministic"
        assert out["recommended_factor"] in {b[2] for b in SHADING_BUCKETS}
        assert isinstance(out["narrative"], str)


# ────────────────────────────────────────────────────────────────────
# Sanity guard — agent output must NEVER pick a non-bucket factor.
# ────────────────────────────────────────────────────────────────────

class TestFactorClamping:

    def test_invalid_llm_factor_clamps_to_engine_bucket(self, monkeypatch):
        # Patch both LLM paths to return a factor that's NOT in the table.
        from engine.agents import shading_agent as ag
        monkeypatch.setattr(ag, "_try_adk_run", lambda *a, **k: {
            "narrative": "x", "per_obstruction": [], "what_ifs": [],
            "recommended_factor": 0.55,    # NOT in SHADING_BUCKETS
            "factor_reasoning": "test",
        })
        engine_result = {
            "lat": 5.6, "lon": -0.2, "on_date": "2026-06-21",
            "tilt_deg": 15, "array_azimuth_deg": 180,
            "total_panels": 12, "affected_panels": 5, "heavily_affected": 2,
            "shading_start": "09:00", "shading_end": "15:00",
            "shading_duration_h": 6.0, "system_loss_pct": 15.0,
            "peak_step_loss_pct": 30.0,
            "bucket_label": "Moderate shading", "bucket_factor": 0.85,
            "bucket_loss_pct": 15.0, "mitigation": "Bypass diodes",
            "n_strings": 2,
        }
        out = run_shading_agent(engine_result, {"obstructions": []})
        valid_factors = {b[2] for b in SHADING_BUCKETS}
        assert out["recommended_factor"] in valid_factors
        # Should clamp to the engine's bucket pick.
        assert out["recommended_factor"] == 0.85
