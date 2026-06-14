"""
SolarPro shading engine.

Pure-Python deterministic geometry + electrical-string model used by the
AI 3D Shading Simulation Agent. No external dependencies.
"""
from .shading_engine import (
    sun_position,
    sun_ray_vector,
    build_panel_grid,
    project_shadow_polygon,
    shaded_panel_fractions,
    time_series_shading,
    energy_loss_with_electrical_model,
    pick_shading_bucket,
    SHADING_BUCKETS,
    DIRECTION_AZ,
)

__all__ = [
    "sun_position",
    "sun_ray_vector",
    "build_panel_grid",
    "project_shadow_polygon",
    "shaded_panel_fractions",
    "time_series_shading",
    "energy_loss_with_electrical_model",
    "pick_shading_bucket",
    "SHADING_BUCKETS",
    "DIRECTION_AZ",
]
