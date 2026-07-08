"""Digital Twin scene-graph v2 engine (SolarPro Generation Station).

This module is the *additive* engineering layer on top of the existing
``build_scene_from_project()`` output in ``new_capital_investment_routes_v2.py``.
It does NOT replace that generator; it augments its dict with a versioned,
normalized object graph plus the metadata the upgraded Three.js client needs
(materials, per-object engineering + links + simulation fields, camera presets,
simulation modes, editable-parameter descriptors, a graphics-performance
profile). Legacy top-level arrays (``pv.rows``, ``buildings``, ``roads`` ...)
are preserved untouched for backward compatibility.

Public API (kept stable so other apps / tests can import it):
    - ``augment_scene_v2(scene, proj)``  -> scene dict with ``schema_version``
      and top-level ``objects`` / ``materials`` / ``links`` / ``performance``
      / ``camera_presets`` / ``simulation_modes`` / ``parameters``.
    - ``sun_position(lat, lon, month, hour, tz_offset_h=0.0)`` -> extended
      solar dict (superset of the legacy keys).
    - ``shadow_analysis(scene, sun)`` -> per-row shading severity + loss.
    - ``normalize_objects(scene)`` -> the flat ``objects`` list only.
    - Constants: ``SCHEMA_VERSION``, ``MATERIALS``, ``MARKET_MAP``.

Units: metres. Coordinate system matches the base generator: origin at site
centre, +X = East, +Y = up, +Z = South (Three.js right-handed).
"""
from __future__ import annotations

import math
from typing import Any

__all__ = [
    "SCHEMA_VERSION", "MATERIALS", "MARKET_MAP",
    "augment_scene_v2", "normalize_objects", "sun_position",
    "shadow_analysis", "camera_presets", "simulation_modes_meta",
]

# Bump this string whenever the object contract changes shape; the client and
# tests assert on it so a schema drift fails loudly instead of silently.
SCHEMA_VERSION = "dt_scene_v2"

# ---------------------------------------------------------------------------
# Material library. Keys are referenced by every object's render.material.
# Values are plain PBR descriptors the client turns into MeshStandardMaterial
# (Phase 7). Colours mirror DT_LAYER_PALETTE where a layer maps 1:1.
# ---------------------------------------------------------------------------
MATERIALS: dict[str, dict[str, Any]] = {
    "pv_glass":       {"color": "#0e2350", "roughness": 0.14, "metalness": 0.45},
    "aluminum_frame": {"color": "#9aa3ad", "roughness": 0.45, "metalness": 0.80},
    "concrete":       {"color": "#b8b2a6", "roughness": 0.90, "metalness": 0.02},
    "asphalt":        {"color": "#4a4a4a", "roughness": 0.95, "metalness": 0.00},
    "soil":           {"color": "#5f7f3d", "roughness": 1.00, "metalness": 0.00},
    "steel":          {"color": "#8892a0", "roughness": 0.40, "metalness": 0.85},
    "fence_metal":    {"color": "#c0a060", "roughness": 0.55, "metalness": 0.60},
    "building_wall":  {"color": "#e0c080", "roughness": 0.80, "metalness": 0.05},
    "transformer":    {"color": "#c04040", "roughness": 0.60, "metalness": 0.50},
    "inverter":       {"color": "#e0c020", "roughness": 0.50, "metalness": 0.55},
    "warning":        {"color": "#e02020", "roughness": 0.70, "metalness": 0.10},
    "water":          {"color": "#3a5a80", "roughness": 0.20, "metalness": 0.00},
}

# Layer -> material key. Layers not listed fall back to "building_wall".
_LAYER_MATERIAL: dict[str, str] = {
    "terrain": "soil", "fence": "fence_metal", "gate": "fence_metal",
    "internal_roads": "asphalt", "drainage": "water",
    "pv_row": "pv_glass", "pv_array": "pv_glass",
    "inverter": "inverter", "combiner": "inverter",
    "transformer": "transformer", "transformer_bldg": "transformer",
    "rmu": "transformer", "mv_switchgear": "steel", "switchgear_bldg": "steel",
    "cctv_pole": "steel", "weather_mast": "steel", "lighting_pole": "steel",
    "earthing_pit": "concrete", "fire_hydrant": "warning",
    "warning_sign": "warning", "battery_room": "building_wall",
    "control_room": "building_wall", "om_building": "building_wall",
    "scada_bldg": "steel", "security_gate": "building_wall",
    "building": "building_wall",
}

# Layer -> marketplace category slug (reuses the existing /marketplace?cat=...).
# Mirrors the map that was inline in the template so the server is authoritative.
MARKET_MAP: dict[str, str] = {
    "pv_row": "pv_modules", "pv_array": "pv_modules",
    "inverter": "inverters", "combiner": "combiners",
    "transformer": "transformers", "transformer_bldg": "transformers",
    "rmu": "power_system", "mv_switchgear": "power_system",
    "switchgear_bldg": "power_system", "battery_room": "battery_systems",
    "cctv_pole": "cctv", "weather_mast": "monitoring",
    "lighting_pole": "lighting", "earthing_pit": "earthing",
    "scada_bldg": "server_equipment",
}

# Layers whose objects the engineer may reposition (drag) in the twin. Anything
# else is selectable/inspectable but not movable in Phase 6.
_MOVABLE_LAYERS = {"transformer", "transformer_bldg", "inverter",
                   "weather_mast", "cctv_pole", "lighting_pole"}


def _material_for(layer: str) -> str:
    """Return the material-library key for a layer code (never raises)."""
    return _LAYER_MATERIAL.get(layer, "building_wall")


def _links_for(pid: Any, layer: str) -> dict[str, Any]:
    """Build the object -> existing-SolarPro-surface link map.

    Inputs: project id, object layer code.
    Output: dict of URLs into the EXISTING BOQ/finance/report/marketplace
    routes (no new engines). Missing links are ``None`` (client renders them
    as disabled rather than broken).
    """
    base = f"/large-scale-solar/{pid}"
    cat = MARKET_MAP.get(layer)
    return {
        "boq":         f"{base}/step9",
        "financial":   f"{base}/step8",
        "reports":     f"{base}/step13",
        "marketplace": (f"/marketplace?cat={cat}" if cat else None),
        "bom":         None,
        "maintenance": None,
        "datasheet":   None,
    }


def _engineering_for(layer: str, meta: dict[str, Any]) -> dict[str, Any]:
    """Derive the per-object engineering descriptor (editable/quantity/...).

    Inputs: layer code and the object's existing ``meta`` dict.
    Output: dict describing how the object may be manipulated + its quantity /
    capacity where known. Purely additive metadata; never mutates ``meta``.
    """
    quantity = meta.get("modules") or meta.get("sub_items") or None
    if isinstance(quantity, list):
        quantity = len(quantity)
    return {
        "editable":   layer not in ("terrain",),
        "selectable": True,
        "movable":    layer in _MOVABLE_LAYERS,
        "rotatable":  layer in ("pv_row", "pv_array"),
        "duplicable": False,   # server-backed duplicate is out of scope here
        "deletable":  False,   # deletion requires an explicit server action
        "locked":     False,
        "quantity":   quantity,
        "capacity_kwp": meta.get("capacity_kwp"),
        "dependencies": _dependencies_for(layer),
    }


def _dependencies_for(layer: str) -> list[str]:
    """Which project config blobs / steps an object depends on (for dirty-tracking)."""
    if layer in ("pv_row", "pv_array"):
        return ["pv_config.sizing", "boq.step9", "finance.step8"]
    if layer in ("inverter", "combiner"):
        return ["pv_config.sizing", "boq.step9"]
    if layer in ("transformer", "transformer_bldg", "mv_switchgear", "rmu"):
        return ["electrical_config", "boq.step9"]
    if layer in ("battery_room",):
        return ["facility_config", "finance.step8"]
    return ["facility_config"]


def _obj_from_legacy(o: dict[str, Any], pid: Any,
                     default_layer: str) -> dict[str, Any]:
    """Normalize one legacy scene dict into the v2 object contract.

    Inputs: a legacy object (``id/layer/kind/x/y/z/w/h/l/label/meta`` shape),
    the project id (for links) and a fallback layer code.
    Output: a fully-formed v2 object dict. Positions/dimensions default to 0 so
    a malformed legacy row can never raise.
    """
    layer = o.get("layer", default_layer)
    meta = o.get("meta") or {}
    tilt = float(o.get("tilt_deg") or 0.0)
    az = float(o.get("azimuth_deg") or 0.0)
    # PV rows tilt about the East-West (X) axis and yaw to face their azimuth;
    # everything else sits axis-aligned. rotation_deg is [x, y, z] in degrees.
    rot = [(-tilt if layer in ("pv_row", "pv_array") else 0.0),
           (-(az - 180.0) if layer in ("pv_row", "pv_array") else 0.0),
           0.0]
    return {
        "id":    o.get("id") or f"{layer}_obj",
        "type":  layer,
        "layer": layer,
        "label": o.get("label") or layer.replace("_", " ").title(),
        "kind":  o.get("kind") or "box",
        "transform": {
            "position": [float(o.get("x") or 0.0),
                         float(o.get("y") or 0.0),
                         float(o.get("z") or 0.0)],
            "rotation_deg": rot,
            "scale": [1.0, 1.0, 1.0],
        },
        "dimensions": {"w": float(o.get("w") or 0.0),
                       "h": float(o.get("h") or 0.0),
                       "l": float(o.get("l") or 0.0)},
        "render": {
            "material": _material_for(layer),
            "lod": "high",
            "instanced": layer in ("pv_row", "pv_array"),
            "cast_shadow": layer not in ("terrain", "internal_roads"),
            "receive_shadow": True,
        },
        "engineering": _engineering_for(layer, meta),
        "links": _links_for(pid, layer),
        "simulation": {
            "shadow": {"severity": "none", "loss_pct": 0.0, "caused_by": []},
            "irradiance_wm2": None,
            "warnings": [],
        },
        "meta": meta,
    }


def normalize_objects(scene: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten every legacy scene array into one v2 ``objects`` list.

    Input: the base scene dict from ``build_scene_from_project``.
    Output: list of normalized v2 objects (terrain, fence, roads, buildings,
    PV rows, inverters, ICT, lighting, safety). Order is stable and deterministic
    so tests and the client object index are reproducible.
    """
    pid = (scene.get("site") or {}).get("pid")
    objects: list[dict[str, Any]] = []

    # Terrain (single ground plane) -> one object sized to the site square.
    terrain = scene.get("terrain") or {}
    if terrain:
        side = float(terrain.get("side_m") or 0.0)
        t = dict(terrain)
        t.update({"x": 0.0, "y": -0.01, "z": 0.0, "w": side, "h": 0.02,
                  "l": side, "id": "terrain", "layer": "terrain"})
        objects.append(_obj_from_legacy(t, pid, "terrain"))

    # Fence loop -> a single logical object (client still draws the segments).
    fence = scene.get("fence") or {}
    if fence.get("points"):
        f = dict(fence)
        f.update({"x": 0.0, "y": float(fence.get("height_m") or 2.4) / 2.0,
                  "z": 0.0, "w": 0.0, "h": float(fence.get("height_m") or 2.4),
                  "l": 0.0, "id": "fence", "layer": "fence"})
        obj = _obj_from_legacy(f, pid, "fence")
        obj["kind"] = "line_loop"
        obj["meta"] = dict(fence.get("meta") or {})
        obj["meta"]["points"] = fence.get("points")
        objects.append(obj)

    for road in scene.get("roads") or []:
        objects.append(_obj_from_legacy(road, pid, "internal_roads"))
    for bld in scene.get("buildings") or []:
        objects.append(_obj_from_legacy(bld, pid, "building"))
    for row in (scene.get("pv") or {}).get("rows") or []:
        objects.append(_obj_from_legacy(row, pid, "pv_row"))
    for inv in scene.get("inverters") or []:
        objects.append(_obj_from_legacy(inv, pid, "inverter"))
    for ict in scene.get("ict") or []:
        objects.append(_obj_from_legacy(ict, pid, "cctv_pole"))
    for lp in scene.get("lighting") or []:
        objects.append(_obj_from_legacy(lp, pid, "lighting_pole"))
    for sf in scene.get("safety") or []:
        objects.append(_obj_from_legacy(sf, pid, "earthing_pit"))

    return objects


def camera_presets(land_side_m: float) -> dict[str, dict[str, Any]]:
    """Compute engineering camera presets scaled to the site size.

    Input: site square side in metres.
    Output: dict of preset-name -> {position:[x,y,z], target:[x,y,z], fov, label}.
    Every preset is a real camera move (Phase 4), not a static image.
    """
    s = max(float(land_side_m or 100.0), 40.0)
    half = s / 2.0
    return {
        "top":         {"position": [0, s * 1.4, 0.001], "target": [0, 0, 0],
                        "fov": 45, "label": "Top / Plan"},
        "north":       {"position": [0, s * 0.35, -s * 1.1], "target": [0, 0, 0],
                        "fov": 45, "label": "North"},
        "south":       {"position": [0, s * 0.35, s * 1.1], "target": [0, 0, 0],
                        "fov": 45, "label": "South"},
        "east":        {"position": [s * 1.1, s * 0.35, 0], "target": [0, 0, 0],
                        "fov": 45, "label": "East"},
        "west":        {"position": [-s * 1.1, s * 0.35, 0], "target": [0, 0, 0],
                        "fov": 45, "label": "West"},
        "birdseye":    {"position": [s * 0.7, s * 0.5, s * 0.7], "target": [0, 0, 0],
                        "fov": 45, "label": "Bird's eye"},
        "drone":       {"position": [s * 0.4, s * 0.25, s * 0.4], "target": [0, 5, 0],
                        "fov": 55, "label": "Drone"},
        "walkthrough": {"position": [-half + 10, 2.0, half - 10], "target": [0, 2, 0],
                        "fov": 65, "label": "Ground walkthrough"},
        "technician":  {"position": [half - 25, 3.0, half - 25], "target": [half - 20, 2, half - 20],
                        "fov": 60, "label": "Technician"},
        "maintenance": {"position": [0, 6, half - 15], "target": [0, 1.5, 0],
                        "fov": 60, "label": "Maintenance route"},
        "investor":    {"position": [s * 0.85, s * 0.45, s * 0.85], "target": [0, 0, 0],
                        "fov": 40, "label": "Investor aerial"},
        "construction":{"position": [s * 0.5, s * 0.4, -s * 0.5], "target": [0, 0, 0],
                        "fov": 50, "label": "Construction"},
        "night":       {"position": [s * 0.6, s * 0.4, s * 0.6], "target": [0, 0, 0],
                        "fov": 45, "label": "Night"},
        "inspection":  {"position": [15, 4, 15], "target": [0, 1.5, 0],
                        "fov": 55, "label": "Inspection"},
    }


def simulation_modes_meta() -> dict[str, dict[str, Any]]:
    """Static descriptors for the 9 simulation modes.

    Output: mode-name -> {label, camera(preset), lighting, labels(bool),
    layers("all"|list), analysis(panel tab)}. The client applies these; the
    server just declares them so behaviour is data-driven, not hardcoded in JS.
    """
    return {
        "plan_2d":     {"label": "2D Plan", "camera": "top", "lighting": "flat",
                        "labels": True, "layers": "all", "analysis": "properties"},
        "three_d":     {"label": "3D View", "camera": "birdseye", "lighting": "day",
                        "labels": True, "layers": "all", "analysis": "properties"},
        "sun_path":    {"label": "Sun Path", "camera": "birdseye", "lighting": "day",
                        "labels": False, "layers": "all", "analysis": "sun"},
        "shadow":      {"label": "Shadow Analysis", "camera": "birdseye",
                        "lighting": "day", "labels": False, "layers": "all",
                        "analysis": "shadow"},
        "energy_flow": {"label": "Energy Flow", "camera": "birdseye",
                        "lighting": "day", "labels": True,
                        "layers": ["pv_row", "inverter", "transformer",
                                   "transformer_bldg", "internal_roads"],
                        "analysis": "energy"},
        "maintenance": {"label": "Maintenance", "camera": "maintenance",
                        "lighting": "day", "labels": True, "layers": "all",
                        "analysis": "properties"},
        "construction":{"label": "Construction", "camera": "construction",
                        "lighting": "day", "labels": True, "layers": "all",
                        "analysis": "properties"},
        "night":       {"label": "Night", "camera": "night", "lighting": "night",
                        "labels": True,
                        "layers": ["lighting_pole", "cctv_pole", "control_room",
                                   "om_building", "internal_roads", "fence"],
                        "analysis": "properties"},
        "investor":    {"label": "Investor", "camera": "investor", "lighting": "day",
                        "labels": False, "layers": "all", "analysis": "energy"},
    }


def _editable_parameters(scene: dict[str, Any]) -> dict[str, Any]:
    """Descriptor for the live Design-Parameters panel (Phase 3).

    Input: base scene (reads current pv meta / site).
    Output: dict of param-path -> {label, value, min, max, step, unit, group}.
    The client renders inputs from this; POST /dt/parameters consumes the same
    paths. Values are the CURRENT design so the panel opens pre-filled.
    """
    pv = (scene.get("pv") or {}).get("meta") or {}
    site = scene.get("site") or {}
    return {
        "pv.kwp":           {"label": "PV capacity", "value": pv.get("kwp") or 0,
                             "min": 0, "max": 500000, "step": 100, "unit": "kWp",
                             "group": "System"},
        "pv.module_wp":     {"label": "Module wattage", "value": pv.get("module_wp") or 550,
                             "min": 200, "max": 800, "step": 5, "unit": "W",
                             "group": "PV Module"},
        "pv.tilt_deg":      {"label": "Tilt angle", "value": pv.get("tilt_deg") or 12,
                             "min": 0, "max": 60, "step": 1, "unit": "deg",
                             "group": "Mounting"},
        "pv.azimuth_deg":   {"label": "Azimuth", "value": pv.get("azimuth_deg") or 180,
                             "min": 0, "max": 359, "step": 1, "unit": "deg",
                             "group": "Mounting"},
        "pv.row_pitch_m":   {"label": "Row spacing", "value": pv.get("row_pitch_m") or 6,
                             "min": 2, "max": 20, "step": 0.25, "unit": "m",
                             "group": "Mounting"},
        "site.land_area_ha":{"label": "Land area", "value": site.get("land_area_ha") or 0,
                             "min": 1, "max": 5000, "step": 1, "unit": "ha",
                             "group": "Site"},
    }


def _recommended_tier(n_modules: int, n_objects: int) -> str:
    """Pick a default graphics tier from scene weight (low|medium|high)."""
    if n_modules >= 60000 or n_objects >= 600:
        return "low"
    if n_modules >= 8000 or n_objects >= 150:
        return "medium"
    return "high"


def augment_scene_v2(scene: dict[str, Any],
                     proj: dict[str, Any]) -> dict[str, Any]:
    """Augment a base scene dict with the v2 engineering graph (in place).

    Inputs: the dict returned by ``build_scene_from_project`` and the project
    row (for id + gps). Output: the SAME dict, mutated additively with
    ``schema_version``, ``objects``, ``materials``, ``links``, ``performance``,
    ``camera_presets``, ``simulation_modes`` and ``parameters``. Legacy keys are
    left intact. Safe to call twice (idempotent).
    """
    if not isinstance(scene, dict):
        return scene
    pid = proj.get("id") if isinstance(proj, dict) else None
    # Stamp the pid into site so normalize_objects can build links.
    site = scene.setdefault("site", {})
    site["pid"] = pid

    objects = normalize_objects(scene)
    pv_meta = (scene.get("pv") or {}).get("meta") or {}
    n_modules = int(pv_meta.get("n_modules_planned") or 0)

    scene["schema_version"] = SCHEMA_VERSION
    scene["units"] = "m"
    scene["coordinate_system"] = {"origin": "site_center", "x": "east",
                                  "y": "up", "z": "south"}
    scene["objects"] = objects
    scene["materials"] = MATERIALS
    scene["links"] = {
        "boq":         f"/large-scale-solar/{pid}/step9",
        "financial":   f"/large-scale-solar/{pid}/step8",
        "marketplace": "/marketplace",
        "reports":     f"/large-scale-solar/{pid}/step13",
    }
    scene["performance"] = {
        "recommended_tier": _recommended_tier(n_modules, len(objects)),
        "estimated_modules": n_modules,
        "estimated_objects": len(objects),
    }
    scene["camera_presets"] = camera_presets(
        (scene.get("terrain") or {}).get("side_m")
        or site.get("land_side_m") or 100.0)
    scene["simulation_modes"] = simulation_modes_meta()
    scene["parameters"] = {"editable": _editable_parameters(scene)}
    return scene


# ---------------------------------------------------------------------------
# Sun position (extended, backward-compatible superset of the legacy fn).
# ---------------------------------------------------------------------------
def sun_position(lat_deg: float, lon_deg: float, month: int, hour: float,
                 tz_offset_h: float | None = None) -> dict[str, float]:
    """NOAA-simplified solar geometry for a mid-month day (extended payload).

    Inputs: latitude/longitude (deg, +E), integer month 1-12, local **clock**
    hour 0-24, and optional timezone offset in hours. When ``tz_offset_h`` is
    None it is estimated from longitude (``round(lon/15)``). Longitude, the
    timezone meridian and the equation-of-time are applied so solar noon,
    sunrise/sunset, altitude, azimuth and shadow direction are correct away
    from the prime meridian -- not just an assumed local-solar-time frame.

    Output: dict that is a SUPERSET of the legacy keys (``altitude_deg``,
    ``azimuth_deg``, ``month``, ``hour``, ``is_daylight``) plus
    ``declination_deg``, ``hour_angle_deg``, ``elevation_deg``,
    ``sunrise_hour``, ``sunset_hour``, ``solar_noon_hour``,
    ``shadow_length_factor``, ``timezone_offset_h``, ``equation_of_time_min``,
    ``refraction_applied``. Azimuth convention: 0=N, 90=E, 180=S, 270=W.
    """
    if tz_offset_h is None:
        # Nautical timezone estimate from longitude (15 deg per hour).
        tz_offset_h = round(lon_deg / 15.0)
    day_of_year_by_month = {1: 15, 2: 46, 3: 74, 4: 105, 5: 135, 6: 166,
                            7: 196, 8: 227, 9: 258, 10: 288, 11: 319, 12: 349}
    doy = day_of_year_by_month.get(int(month), 172)
    decl = 23.45 * math.sin(math.radians(360.0 * (284 + doy) / 365.0))
    decl_r = math.radians(decl)
    lat_r = math.radians(lat_deg)

    # Equation of time (minutes) + longitude/timezone-meridian correction turn
    # the input clock hour into local solar time.
    b = math.radians(360.0 * (doy - 81) / 364.0)
    eot_min = (9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b))
    lstm = 15.0 * tz_offset_h                       # local standard-time meridian
    tc_min = 4.0 * (lon_deg - lstm) + eot_min       # time-correction (minutes)
    lst = hour + tc_min / 60.0                       # local solar time
    solar_noon = 12.0 - tc_min / 60.0                # clock hour of solar noon

    hour_angle = 15.0 * (lst - 12.0)
    H = math.radians(hour_angle)
    sin_alt = (math.sin(lat_r) * math.sin(decl_r)
               + math.cos(lat_r) * math.cos(decl_r) * math.cos(H))
    sin_alt = max(-1.0, min(1.0, sin_alt))
    alt = math.asin(sin_alt)
    alt_deg = math.degrees(alt)
    y = -math.sin(H)
    x = math.tan(decl_r) * math.cos(lat_r) - math.sin(lat_r) * math.cos(H)
    az = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0

    # Sunrise / sunset hour angle: cos(H0) = -tan(lat) tan(decl). Clamp for
    # polar day/night so the value is always finite. Expressed in clock time
    # about the corrected solar noon.
    cos_h0 = -math.tan(lat_r) * math.tan(decl_r)
    cos_h0 = max(-1.0, min(1.0, cos_h0))
    h0_deg = math.degrees(math.acos(cos_h0))
    sunrise = solar_noon - h0_deg / 15.0
    sunset = solar_noon + h0_deg / 15.0

    # Shadow length factor = cot(altitude), clamped so a near-horizon sun does
    # not yield an astronomically long shadow. 0 when the sun is down.
    if alt_deg > 0.5:
        shadow_factor = min(1.0 / math.tan(alt), 20.0)
    else:
        shadow_factor = 0.0

    return {
        "altitude_deg": round(alt_deg, 3),
        "elevation_deg": round(alt_deg, 3),
        "azimuth_deg": round(az, 3),
        "declination_deg": round(decl, 3),
        "hour_angle_deg": round(hour_angle, 3),
        "equation_of_time_min": round(eot_min, 3),
        "month": int(month),
        "hour": round(hour, 3),
        "sunrise_hour": round(sunrise, 3),
        "sunset_hour": round(sunset, 3),
        "solar_noon_hour": round(solar_noon, 3),
        "shadow_length_factor": round(shadow_factor, 3),
        "timezone_offset_h": tz_offset_h,
        "is_daylight": alt_deg > 0.0,
        "refraction_applied": False,
    }


# ---------------------------------------------------------------------------
# Shadow analysis (row-level, conservative bounding-box approximation).
# ---------------------------------------------------------------------------
def _severity(loss_pct: float) -> str:
    """Map a loss percentage to a severity band (none|light|moderate|heavy)."""
    if loss_pct < 0.5:
        return "none"
    if loss_pct < 3.0:
        return "light"
    if loss_pct < 8.0:
        return "moderate"
    return "heavy"


def shadow_analysis(scene: dict[str, Any],
                    sun: dict[str, Any]) -> dict[str, Any]:
    """Estimate per-PV-row shading for a given sun position.

    Inputs: an augmented (or base) scene and a ``sun_position`` dict.
    Output: ``{sun, is_night, affected_objects:[{object_id, severity,
    shadow_loss_pct, irradiance_wm2, energy_loss_kwh_day, caused_by}],
    summary:{affected_rows, weighted_loss_pct}}``.

    Model (deliberately conservative, row-level, cheap enough for 100MW):
      1. Row-to-row self-shading grows as the sun drops and the projected
         shadow of a row exceeds the row pitch.
      2. Tall objects (buildings, transformer yard, masts) cast a rectangular
         shadow ``height * shadow_length_factor`` long in the sun-away
         direction; PV rows whose centre falls inside it take extra loss and
         record the caster in ``caused_by``.
    Not a bankable PVsyst raytrace; labelled as an engineering estimate.
    """
    alt = float(sun.get("altitude_deg") or 0.0)
    if alt <= 0.0:
        return {"sun": sun, "is_night": True, "affected_objects": [],
                "summary": {"affected_rows": 0, "weighted_loss_pct": 0.0}}

    shadow_factor = float(sun.get("shadow_length_factor") or 0.0)
    az = float(sun.get("azimuth_deg") or 180.0)
    # Sun horizontal direction (unit): +X=E, +Z=S. Shadows fall opposite.
    az_r = math.radians(az)
    shadow_dir = (-math.sin(az_r), -math.cos(az_r))

    objects = scene.get("objects")
    if not objects:
        objects = normalize_objects(scene)

    pv_meta = (scene.get("pv") or {}).get("meta") or {}
    row_pitch = float(pv_meta.get("row_pitch_m") or 6.0)
    modules_per_row = int(pv_meta.get("modules_per_row") or 30)
    module_wp = float(((scene.get("pv") or {}).get("meta") or {}).get(
        "module_wp") or 550.0)

    rows = [o for o in objects if o.get("layer") in ("pv_row", "pv_array")]
    casters = [o for o in objects
               if o.get("layer") not in ("pv_row", "pv_array", "terrain",
                                          "internal_roads", "fence")
               and o.get("dimensions", {}).get("h", 0) >= 2.0]

    affected: list[dict[str, Any]] = []
    total_loss = 0.0
    for row in rows:
        pos = row.get("transform", {}).get("position", [0, 0, 0])
        dims = row.get("dimensions", {})
        row_h = max(float(dims.get("h") or 0.05), 1.5)  # tilted panel height

        # (1) Row-to-row self shading. Projected shadow length of this row.
        row_shadow_len = row_h * shadow_factor
        rtr_loss = 0.0
        if row_shadow_len > row_pitch:
            over = (row_shadow_len - row_pitch) / max(row_pitch, 0.1)
            rtr_loss = min(over * 6.0, 18.0)   # cap self-shading contribution

        # (2) Tall-object shadows.
        obj_loss = 0.0
        caused_by: list[str] = []
        for c in casters:
            cpos = c.get("transform", {}).get("position", [0, 0, 0])
            ch = float(c.get("dimensions", {}).get("h") or 0.0)
            reach = ch * shadow_factor
            if reach < 2.0:
                continue
            # Vector from caster to row; is the row within the shadow beam?
            dx = pos[0] - cpos[0]
            dz = pos[2] - cpos[2]
            along = dx * shadow_dir[0] + dz * shadow_dir[1]
            if along <= 0 or along > reach:
                continue
            # Perpendicular offset from the shadow centre-line.
            perp = abs(dx * (-shadow_dir[1]) + dz * shadow_dir[0])
            cw = max(float(c.get("dimensions", {}).get("w") or 0.0),
                     float(c.get("dimensions", {}).get("l") or 0.0)) / 2.0 + 3.0
            if perp <= cw:
                # Loss falls off with distance along the shadow.
                frac = 1.0 - (along / reach)
                obj_loss = max(obj_loss, min(frac * 40.0, 35.0))
                caused_by.append(c.get("id"))

        loss = min(rtr_loss + obj_loss, 45.0)
        if loss < 0.5:
            continue
        # Daily energy loss for this row (rough): row kWp * PSH-equiv * loss.
        row_kwp = modules_per_row * module_wp / 1000.0
        energy_loss = round(row_kwp * 5.0 * (loss / 100.0), 2)
        irr = round(1000.0 * (1.0 - loss / 100.0) * math.sin(math.radians(alt)), 1)
        affected.append({
            "object_id": row.get("id"),
            "severity": _severity(loss),
            "shadow_loss_pct": round(loss, 2),
            "irradiance_wm2": irr,
            "energy_loss_kwh_day": energy_loss,
            "financial_loss_local_day": None,
            "caused_by": caused_by,
        })
        total_loss += loss

    weighted = round(total_loss / len(rows), 2) if rows else 0.0
    return {
        "sun": sun,
        "is_night": False,
        "affected_objects": affected,
        "summary": {"affected_rows": len(affected),
                    "weighted_loss_pct": weighted,
                    "total_rows": len(rows)},
    }
