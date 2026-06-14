"""
Solar shading geometry engine — pure Python, no external deps.

Authoritative deterministic core for the AI 3D Shading Simulation Agent.
Implements:

  * Sun position (NOAA Solar Position Algorithm, ~0.1° accuracy)
  * Sun ray direction (unit vector pointing AWAY from sun)
  * PV panel grid generation in a 3D site frame
  * Obstruction silhouette → shadow polygon on the array plane
  * Per-panel shaded-area fraction via convex polygon clipping
  * Time-series shading across a day (sunrise → sunset)
  * Energy loss with string-electrical knowledge:
        - Bypass-diode substring isolation (3 diodes / panel by default)
        - String MPPT mismatch penalty (worst-panel rule of thumb)
        - DC optimisers / micro-inverters eliminate string mismatch
  * Mapping computed loss% → SHADING_BUCKETS row (matches the spec table)

The ADK LlmAgent wrapping this engine (engine/agents/shading_agent.py)
adds narration, mitigation what-ifs, and tie-breaking. Every number that
appears in any output comes from THIS module, not from the LLM.

Coordinate convention
---------------------
Right-handed site frame, origin at centre of the mounting area at ground:
    +x = East · +y = North · +z = Up

Azimuth follows the PV industry convention:
    0° = North · 90° = East · 180° = South · 270° = West
Tilt is the angle of the panel plane from horizontal:
    0° = flat · 90° = vertical
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ───────────────────────────────────────────────────────────────────────
# Reference tables (single source of truth — web_app.py mirrors these)
# ───────────────────────────────────────────────────────────────────────

# 8-row bucket table from the spec. (label, loss_pct, factor).
SHADING_BUCKETS: List[Tuple[str, float, float]] = [
    ("No shading",          0.0,  1.00),
    ("Very light shading",  5.0,  0.95),
    ("Light shading",      10.0,  0.90),
    ("Moderate shading",   15.0,  0.85),
    ("Significant shading",20.0,  0.80),
    ("Heavy shading",      25.0,  0.75),
    ("Severe shading",     30.0,  0.70),
    ("Very severe shading",40.0,  0.60),
]

# Cardinal direction label → azimuth degrees (where the obstruction SITS
# relative to the array).
DIRECTION_AZ: Dict[str, float] = {
    "N":  0,   "North":       0,
    "NE": 45,  "North-East":  45,  "NorthEast": 45,
    "E":  90,  "East":        90,
    "SE": 135, "South-East":  135, "SouthEast": 135,
    "S":  180, "South":       180,
    "SW": 225, "South-West":  225, "SouthWest": 225,
    "W":  270, "West":        270,
    "NW": 315, "North-West":  315, "NorthWest": 315,
}

# Default module electrical topology (most modern 60/72-cell modules).
DEFAULT_BYPASS_DIODES_PER_PANEL = 3
DEFAULT_PANELS_PER_STRING       = 10

# Mitigation labels mapped to electrical behaviour flags.
MITIGATION_BEHAVIOUR = {
    "None":             {"bypass": False, "per_panel_mppt": False},
    "Bypass diodes":    {"bypass": True,  "per_panel_mppt": False},
    "DC optimisers":    {"bypass": True,  "per_panel_mppt": True},
    "Micro-inverters":  {"bypass": True,  "per_panel_mppt": True},
    "Combination":      {"bypass": True,  "per_panel_mppt": True},
}


# ───────────────────────────────────────────────────────────────────────
# Lightweight 3D primitives
# ───────────────────────────────────────────────────────────────────────

Vec3 = Tuple[float, float, float]
Vec2 = Tuple[float, float]


@dataclass
class Panel:
    """One PV module as 4 corners in 3D site frame + a local 2D frame.

    The local 2D frame is what shadow polygons get clipped against.
    """
    panel_id:  int
    row:       int
    col:       int
    corners3:  List[Vec3]   # 4 corners in site frame, ordered CCW looking down sun normal
    centre3:   Vec3
    width_m:   float
    height_m:  float
    # 2D-in-plane basis (u along panel width, v along panel "up the tilt")
    u_axis:    Vec3
    v_axis:    Vec3
    normal:    Vec3         # outward normal of the panel face


@dataclass
class Obstruction:
    """User-described obstruction; geometry is built lazily.

    `type` matches the labels surfaced in the form: "10-storey building",
    "tree", "water tank", "boundary wall", "parapet wall", "telecom mast",
    "neighbour building", etc.

    For v1 every obstruction is modelled as a vertical bounding cuboid
    sized by (height, width, depth) and placed at (distance) from the
    array centre in the cardinal direction. Trees use a smaller effective
    width to account for leaf gaps.
    """
    obs_id:        int
    type:          str
    height_m:      float
    width_m:       float
    depth_m:       float
    distance_m:    float
    direction:     str
    base_elev_m:   float = 0.0
    notes:         str   = ""
    mitigation:    str   = "None"   # kept on the obstruction for what-if recomputes


# ───────────────────────────────────────────────────────────────────────
# Sun position — NOAA Solar Position Algorithm (simplified)
# Accurate to ~0.1°. Reference: NOAA ESRL solar calculator.
# ───────────────────────────────────────────────────────────────────────

def sun_position(lat_deg: float,
                 lon_deg: float,
                 when: datetime,
                 tz_offset_h: float = 0.0) -> Dict[str, float]:
    """Solar altitude + azimuth from GPS + wall-clock time.

    Args:
        lat_deg:      Latitude in decimal degrees (-90..+90), N positive.
        lon_deg:      Longitude in decimal degrees (-180..+180), E positive.
        when:         Datetime — treated as wall-clock at tz_offset_h.
        tz_offset_h:  Local timezone offset from UTC in hours (Ghana = 0).

    Returns dict:
        altitude_deg:     Elevation above horizon (negative = sun below)
        azimuth_deg:      Bearing CW from North (0..360, 180 = South)
        declination_deg:  Solar declination (-23.45..+23.45)
        hour_angle_deg:   Local hour angle (15°/hr from solar noon)
        eot_min:          Equation of Time correction, minutes
        is_daytime:       True if altitude > 0
    """
    # Julian day (NOAA fractional)
    y, m, d = when.year, when.month, when.day
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    jd = (math.floor(365.25 * (y + 4716))
          + math.floor(30.6001 * (m + 1))
          + d + b - 1524.5)
    h = when.hour + when.minute / 60 + when.second / 3600
    jd += (h - tz_offset_h) / 24

    # Julian century since J2000
    t = (jd - 2451545.0) / 36525.0

    # Mean longitude + mean anomaly
    L  = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360
    M  = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    Mr = math.radians(M)
    e  = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)

    # Equation of centre + true longitude
    C = (math.sin(Mr)        * (1.914602 - t * (0.004817 + 0.000014 * t))
         + math.sin(2 * Mr)  * (0.019993 - 0.000101 * t)
         + math.sin(3 * Mr)  * 0.000289)
    true_long = L + C

    # Obliquity of the ecliptic (deg)
    obliq = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60

    # Declination
    decl = math.degrees(math.asin(math.sin(math.radians(obliq))
                                   * math.sin(math.radians(true_long))))

    # Equation of Time (minutes)
    y_ = math.tan(math.radians(obliq) / 2) ** 2
    eot = 4 * math.degrees(
        y_ * math.sin(2 * math.radians(L))
        - 2 * e * math.sin(Mr)
        + 4 * e * y_ * math.sin(Mr) * math.cos(2 * math.radians(L))
        - 0.5 * y_ * y_ * math.sin(4 * math.radians(L))
        - 1.25 * e * e * math.sin(2 * Mr))

    # True solar time → hour angle
    true_solar_min = (h * 60 + eot + 4 * lon_deg - 60 * tz_offset_h) % 1440
    ha = true_solar_min / 4 - 180

    # Altitude
    lat_r  = math.radians(lat_deg)
    decl_r = math.radians(decl)
    ha_r   = math.radians(ha)
    sin_alt = (math.sin(lat_r) * math.sin(decl_r)
               + math.cos(lat_r) * math.cos(decl_r) * math.cos(ha_r))
    sin_alt = max(-1.0, min(1.0, sin_alt))
    alt = math.degrees(math.asin(sin_alt))

    # Azimuth
    cos_az = ((math.sin(decl_r) - math.sin(math.radians(alt)) * math.sin(lat_r))
              / (math.cos(math.radians(alt)) * math.cos(lat_r) + 1e-9))
    cos_az = max(-1.0, min(1.0, cos_az))
    az = math.degrees(math.acos(cos_az))
    if ha > 0:
        az = 360 - az

    return {
        "altitude_deg":    alt,
        "azimuth_deg":     az % 360,
        "declination_deg": decl,
        "hour_angle_deg":  ha,
        "eot_min":         eot,
        "is_daytime":      alt > 0,
    }


def sun_ray_vector(altitude_deg: float, azimuth_deg: float) -> Vec3:
    """Unit vector pointing in the direction the sun's light TRAVELS.

    i.e. from the sun toward the ground. Negate to get the "to-sun"
    vector used by shading software. Azimuth follows PV convention
    (0=N, 90=E, 180=S, 270=W).
    """
    alt = math.radians(altitude_deg)
    az  = math.radians(azimuth_deg)
    # Sun is at altitude alt, azimuth az → from-sun direction is
    # opposite: dx = -sin(az)*cos(alt), dy = -cos(az)*cos(alt),
    # dz = -sin(alt). (East = +x, North = +y, Up = +z.)
    dx = -math.sin(az) * math.cos(alt)
    dy = -math.cos(az) * math.cos(alt)
    dz = -math.sin(alt)
    return (dx, dy, dz)


# ───────────────────────────────────────────────────────────────────────
# Panel grid construction
# ───────────────────────────────────────────────────────────────────────

def _rotate_around_axis(v: Vec3, axis: Vec3, angle_rad: float) -> Vec3:
    """Rodrigues' rotation formula. Axis assumed unit length."""
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    ax, ay, az = axis
    vx, vy, vz = v
    dot = ax * vx + ay * vy + az * vz
    cx = ay * vz - az * vy
    cy = az * vx - ax * vz
    cz = ax * vy - ay * vx
    return (vx * c + cx * s + ax * dot * (1 - c),
            vy * c + cy * s + ay * dot * (1 - c),
            vz * c + cz * s + az * dot * (1 - c))


def build_panel_grid(num_panels: int,
                     tilt_deg: float,
                     array_azimuth_deg: float,
                     mount_height_m: float = 0.0,
                     panel_w_m: float = 1.13,     # standard 400 W mono
                     panel_h_m: float = 1.72,
                     col_gap_m: float = 0.02,
                     row_gap_m: float = 0.50,
                     cols: Optional[int] = None) -> List[Panel]:
    """Lay out `num_panels` modules on a tilted plane.

    Args:
        num_panels:        Total panel count.
        tilt_deg:          Tilt of array plane (0=flat).
        array_azimuth_deg: Direction the panels FACE (PV convention).
        mount_height_m:    Bottom edge above ground for the lowest row.
        panel_w_m/h_m:     Single module dimensions.
        col_gap_m:         Gap between panels in a row.
        row_gap_m:         Inter-row gap (along the tilt-down direction).
        cols:              Force columns/row; default = auto sqrt-ish.

    Returns: list[Panel] with 3D corners + 2D in-plane axes filled in.
    """
    if num_panels <= 0:
        return []

    if cols is None:
        cols = max(1, int(round(math.sqrt(num_panels * 1.6))))  # wider than tall
    rows = math.ceil(num_panels / cols)

    # Panel "up the tilt" direction in horizontal plane: opposite of array azimuth.
    # (If panels face South 180°, the up-tilt direction points North.)
    az_face = math.radians(array_azimuth_deg)
    horiz_up_tilt = (-math.sin(az_face), -math.cos(az_face), 0.0)
    # Across-row axis (horizontal, perpendicular to up_tilt).
    across = (math.cos(az_face), -math.sin(az_face), 0.0)
    # Apply tilt: rotate horiz_up_tilt around `across` by tilt_deg.
    tilt_r = math.radians(tilt_deg)
    panel_v = _rotate_around_axis(horiz_up_tilt, across, -tilt_r)  # tilts upward toward sun
    panel_u = across
    # Outward normal of the panel face = v × u (right-handed; this gives a
    # +z-leaning normal for any tilted panel).
    nx = panel_v[1] * panel_u[2] - panel_v[2] * panel_u[1]
    ny = panel_v[2] * panel_u[0] - panel_v[0] * panel_u[2]
    nz = panel_v[0] * panel_u[1] - panel_v[1] * panel_u[0]
    panel_n = (nx, ny, nz)

    # Centre the grid on origin in the horizontal x/y plane.
    total_w = cols * panel_w_m + (cols - 1) * col_gap_m
    total_h = rows * panel_h_m + (rows - 1) * row_gap_m
    origin_x = -total_w / 2 + panel_w_m / 2
    origin_y = -total_h / 2 + panel_h_m / 2

    panels: List[Panel] = []
    pid = 0
    for r in range(rows):
        for c in range(cols):
            if pid >= num_panels:
                break
            # Centre in panel-local plane (u, v) coords (before tilt):
            cu = origin_x + c * (panel_w_m + col_gap_m)
            cv = origin_y + r * (panel_h_m + row_gap_m)
            # Translate to 3D centre.
            cx = cu * panel_u[0] + cv * panel_v[0]
            cy = cu * panel_u[1] + cv * panel_v[1]
            cz = mount_height_m + cu * panel_u[2] + cv * panel_v[2]
            centre = (cx, cy, cz)
            # 4 corners (CCW from bottom-left in the panel's own u/v plane).
            half_u = panel_w_m / 2
            half_v = panel_h_m / 2
            corners = []
            for du, dv in [(-half_u, -half_v), (+half_u, -half_v),
                           (+half_u, +half_v), (-half_u, +half_v)]:
                px = cx + du * panel_u[0] + dv * panel_v[0]
                py = cy + du * panel_u[1] + dv * panel_v[1]
                pz = cz + du * panel_u[2] + dv * panel_v[2]
                corners.append((px, py, pz))
            panels.append(Panel(
                panel_id=pid, row=r, col=c,
                corners3=corners, centre3=centre,
                width_m=panel_w_m, height_m=panel_h_m,
                u_axis=panel_u, v_axis=panel_v, normal=panel_n,
            ))
            pid += 1
    return panels


# ───────────────────────────────────────────────────────────────────────
# Obstruction → shadow polygon on a panel plane
# ───────────────────────────────────────────────────────────────────────

def _obstruction_corners(obs: Obstruction) -> List[Vec3]:
    """8 corners of the obstruction's vertical bounding cuboid.

    Trees use 70 % of nominal width to model leaf gaps.
    """
    az = DIRECTION_AZ.get(obs.direction, 180.0)
    az_r = math.radians(az)
    # Position the cuboid centre at (distance) from origin in direction az.
    cx = obs.distance_m * math.sin(az_r)
    cy = obs.distance_m * math.cos(az_r)
    cz = obs.base_elev_m
    w  = obs.width_m * (0.70 if "tree" in obs.type.lower() else 1.0)
    d  = obs.depth_m if obs.depth_m > 0 else w
    h  = obs.height_m
    # Half-extents in the obstruction's own (across, depth, up) frame —
    # aligned so depth runs radially AWAY from the array.
    radial = (math.sin(az_r), math.cos(az_r), 0.0)
    across = (math.cos(az_r), -math.sin(az_r), 0.0)
    half_w, half_d, half_h = w / 2, d / 2, h / 2
    corners = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (0, 1):  # cuboid bottom on the ground, top at +h
                px = cx + sx * half_w * across[0] + sy * half_d * radial[0]
                py = cy + sx * half_w * across[1] + sy * half_d * radial[1]
                pz = cz + sz * h
                corners.append((px, py, pz))
    return corners


def _project_point_onto_plane(p: Vec3, ray_dir: Vec3,
                              plane_point: Vec3, plane_normal: Vec3) -> Optional[Vec3]:
    """Where does the line {p + t*ray_dir} hit the plane?

    Returns None if ray is parallel to the plane (no intersection).
    """
    denom = (ray_dir[0] * plane_normal[0]
             + ray_dir[1] * plane_normal[1]
             + ray_dir[2] * plane_normal[2])
    if abs(denom) < 1e-9:
        return None
    diff = (plane_point[0] - p[0],
            plane_point[1] - p[1],
            plane_point[2] - p[2])
    t = (diff[0] * plane_normal[0]
         + diff[1] * plane_normal[1]
         + diff[2] * plane_normal[2]) / denom
    return (p[0] + t * ray_dir[0],
            p[1] + t * ray_dir[1],
            p[2] + t * ray_dir[2])


def _to_plane2d(p3: Vec3, origin: Vec3, u: Vec3, v: Vec3) -> Vec2:
    """Convert 3D point on a plane to 2D (u,v) coords relative to origin."""
    dx = p3[0] - origin[0]
    dy = p3[1] - origin[1]
    dz = p3[2] - origin[2]
    return (dx * u[0] + dy * u[1] + dz * u[2],
            dx * v[0] + dy * v[1] + dz * v[2])


def _convex_hull_2d(points: Sequence[Vec2]) -> List[Vec2]:
    """Andrew's monotone-chain convex hull. Returns CCW polygon."""
    pts = sorted(set(points))
    if len(pts) <= 1:
        return list(pts)
    def cross(o: Vec2, a: Vec2, b: Vec2) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower: List[Vec2] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: List[Vec2] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def project_shadow_polygon(obs: Obstruction,
                           sun_alt_deg: float,
                           sun_az_deg: float,
                           panel: Panel) -> List[Vec2]:
    """Shadow of `obs` cast onto `panel`'s plane, in the panel's 2D (u,v) frame.

    Returns CCW convex polygon (empty list if obstruction is below horizon
    relative to the panel or sun is below horizon).
    """
    if sun_alt_deg <= 0:
        return []
    ray = sun_ray_vector(sun_alt_deg, sun_az_deg)
    # Project each of the 8 obstruction corners along the ray onto the
    # panel plane.
    projected_2d: List[Vec2] = []
    for c3 in _obstruction_corners(obs):
        hit = _project_point_onto_plane(c3, ray, panel.centre3, panel.normal)
        if hit is None:
            continue
        projected_2d.append(_to_plane2d(hit, panel.centre3,
                                        panel.u_axis, panel.v_axis))
    if len(projected_2d) < 3:
        return []
    return _convex_hull_2d(projected_2d)


# ───────────────────────────────────────────────────────────────────────
# Polygon clipping & area
# ───────────────────────────────────────────────────────────────────────

def _polygon_area(poly: Sequence[Vec2]) -> float:
    """Signed shoelace area. Absolute value gives geometric area."""
    if len(poly) < 3:
        return 0.0
    s = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) * 0.5


def _clip_convex(subject: Sequence[Vec2], clip: Sequence[Vec2]) -> List[Vec2]:
    """Sutherland-Hodgman polygon clipping. Both inputs must be convex CCW."""
    output = list(subject)
    if not output:
        return []
    n = len(clip)
    for i in range(n):
        if not output:
            break
        a = clip[i]
        b = clip[(i + 1) % n]
        edge_dx = b[0] - a[0]
        edge_dy = b[1] - a[1]
        new_output: List[Vec2] = []
        s = output[-1]
        for e in output:
            # Inside if cross(edge, p - a) >= 0 (CCW clip polygon).
            in_s = edge_dx * (s[1] - a[1]) - edge_dy * (s[0] - a[0]) >= 0
            in_e = edge_dx * (e[1] - a[1]) - edge_dy * (e[0] - a[0]) >= 0
            if in_e:
                if not in_s:
                    # Compute intersection of edge (a,b) with segment (s,e).
                    dx = e[0] - s[0]
                    dy = e[1] - s[1]
                    denom = edge_dx * dy - edge_dy * dx
                    if abs(denom) > 1e-12:
                        t = (edge_dx * (s[1] - a[1])
                             - edge_dy * (s[0] - a[0])) / -denom
                        new_output.append((s[0] + t * dx, s[1] + t * dy))
                new_output.append(e)
            elif in_s:
                dx = e[0] - s[0]
                dy = e[1] - s[1]
                denom = edge_dx * dy - edge_dy * dx
                if abs(denom) > 1e-12:
                    t = (edge_dx * (s[1] - a[1])
                         - edge_dy * (s[0] - a[0])) / -denom
                    new_output.append((s[0] + t * dx, s[1] + t * dy))
            s = e
        output = new_output
    return output


# ───────────────────────────────────────────────────────────────────────
# Per-panel shaded fraction at a single sun position
# ───────────────────────────────────────────────────────────────────────

def shaded_panel_fractions(panels: Sequence[Panel],
                           obstructions: Sequence[Obstruction],
                           sun_alt_deg: float,
                           sun_az_deg: float) -> List[float]:
    """For each panel, return the fraction (0..1) of its area in shadow.

    Multiple obstructions are unioned via per-panel max (sub-additive —
    overlapping shadows don't double-count). Conservative compared to the
    true union but cheap and stable.
    """
    out: List[float] = []
    if sun_alt_deg <= 0:
        return [1.0] * len(panels)  # night — no production
    for panel in panels:
        # Panel rectangle in its own (u,v) frame, centred at 0.
        hu = panel.width_m  / 2
        hv = panel.height_m / 2
        panel_poly: List[Vec2] = [(-hu, -hv), (+hu, -hv), (+hu, +hv), (-hu, +hv)]
        panel_area = panel.width_m * panel.height_m
        max_frac = 0.0
        for obs in obstructions:
            shadow = project_shadow_polygon(obs, sun_alt_deg, sun_az_deg, panel)
            if not shadow:
                continue
            clipped = _clip_convex(panel_poly, shadow)
            if not clipped:
                continue
            frac = _polygon_area(clipped) / panel_area
            if frac > max_frac:
                max_frac = frac
        out.append(min(1.0, max_frac))
    return out


# ───────────────────────────────────────────────────────────────────────
# Time-series shading across a day
# ───────────────────────────────────────────────────────────────────────

@dataclass
class TimeStepResult:
    when:                datetime
    altitude_deg:        float
    azimuth_deg:         float
    per_panel_fraction:  List[float]
    avg_fraction:        float
    panels_partially_shaded: int
    panels_fully_shaded:     int


def time_series_shading(panels: Sequence[Panel],
                        obstructions: Sequence[Obstruction],
                        lat_deg: float,
                        lon_deg: float,
                        on_date: datetime,
                        tz_offset_h: float = 0.0,
                        step_minutes: int = 30,
                        start_hour: int = 6,
                        end_hour: int = 18) -> List[TimeStepResult]:
    """Sweep the sun across the day; per-panel shading at each step.

    `on_date` provides the calendar date (time component ignored).
    """
    out: List[TimeStepResult] = []
    base = on_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    steps = int((end_hour - start_hour) * 60 / step_minutes) + 1
    for i in range(steps):
        when = base + timedelta(minutes=i * step_minutes)
        sp = sun_position(lat_deg, lon_deg, when, tz_offset_h)
        fracs = shaded_panel_fractions(panels, obstructions,
                                       sp["altitude_deg"], sp["azimuth_deg"])
        partial = sum(1 for f in fracs if 0.01 < f < 0.95)
        full    = sum(1 for f in fracs if f >= 0.95)
        avg     = sum(fracs) / len(fracs) if fracs else 0.0
        out.append(TimeStepResult(
            when=when, altitude_deg=sp["altitude_deg"],
            azimuth_deg=sp["azimuth_deg"],
            per_panel_fraction=fracs, avg_fraction=avg,
            panels_partially_shaded=partial, panels_fully_shaded=full,
        ))
    return out


# ───────────────────────────────────────────────────────────────────────
# Energy loss with electrical-string knowledge
# ───────────────────────────────────────────────────────────────────────

def _insolation_weight(altitude_deg: float) -> float:
    """Crude sin(alt) weight — a panel at solar noon counts more than at 7 am.

    For day-long energy-loss integration. Below horizon = 0.
    """
    if altitude_deg <= 0:
        return 0.0
    return math.sin(math.radians(altitude_deg))


def energy_loss_with_electrical_model(
        series: Sequence[TimeStepResult],
        mitigation: str = "Bypass diodes",
        panels_per_string: int = DEFAULT_PANELS_PER_STRING,
        diodes_per_panel: int = DEFAULT_BYPASS_DIODES_PER_PANEL) -> Dict[str, float]:
    """Translate per-panel shading time-series into a system energy-loss %.

    Domain knowledge baked in:

      * **No mitigation**: a single panel >0 % shaded drags its whole
        string proportionally (worst-panel-on-string rule).
      * **Bypass diodes** (3 substrings / panel typical): each substring
        bypasses cleanly when ≥X% shaded; the rest of the panel keeps
        producing. Per-panel effective loss = shaded_fraction (because
        substrings are roughly equal-sized cells), but the STRING penalty
        is the WORST shaded panel in the string (Kirchhoff — string current
        is set by the dimmest module).
      * **DC optimisers / micro-inverters**: per-panel MPPT eliminates the
        string mismatch term entirely. System loss = mean of per-panel
        loss across panels.

    The result is integrated over the day weighted by sin(altitude) so an
    afternoon shadow at low sun matters less than a noon shadow.
    """
    behaviour = MITIGATION_BEHAVIOUR.get(mitigation, MITIGATION_BEHAVIOUR["None"])
    has_bypass = behaviour["bypass"]
    per_panel_mppt = behaviour["per_panel_mppt"]

    if not series or not series[0].per_panel_fraction:
        return {"system_loss_pct": 0.0, "peak_step_loss_pct": 0.0,
                "weighted_avg_fraction": 0.0}

    n_panels = len(series[0].per_panel_fraction)
    if panels_per_string <= 0:
        panels_per_string = max(1, n_panels)
    n_strings = max(1, math.ceil(n_panels / panels_per_string))

    weighted_loss_num = 0.0
    weight_sum        = 0.0
    peak_step_loss    = 0.0
    frac_weighted_num = 0.0

    for step in series:
        w = _insolation_weight(step.altitude_deg)
        if w <= 0:
            continue
        fracs = step.per_panel_fraction

        if per_panel_mppt:
            # No string mismatch: each panel loses exactly its shaded fraction.
            step_loss = sum(fracs) / n_panels
        else:
            # Aggregate per string, then average.
            total = 0.0
            for s_idx in range(n_strings):
                start = s_idx * panels_per_string
                end   = min(start + panels_per_string, n_panels)
                if start >= end:
                    continue
                string_fracs = fracs[start:end]
                if has_bypass:
                    # Each panel contributes its own shaded fraction (substring
                    # bypass keeps unshaded parts producing). String-level
                    # loss = mean of panel losses + mismatch penalty:
                    panel_mean = sum(string_fracs) / len(string_fracs)
                    worst      = max(string_fracs)
                    # Mismatch penalty: 30 % of the gap between worst and mean.
                    mismatch   = 0.30 * (worst - panel_mean)
                    string_loss = min(1.0, panel_mean + mismatch)
                else:
                    # No bypass: worst-panel rule of thumb — the whole string
                    # drops to the worst-shaded panel's production.
                    worst = max(string_fracs)
                    string_loss = worst
                total += string_loss * len(string_fracs)
            step_loss = total / n_panels

        weighted_loss_num += step_loss * w
        weight_sum        += w
        peak_step_loss     = max(peak_step_loss, step_loss)
        frac_weighted_num += step.avg_fraction * w

    sys_loss = (weighted_loss_num / weight_sum) if weight_sum > 0 else 0.0
    avg_frac = (frac_weighted_num / weight_sum) if weight_sum > 0 else 0.0

    return {
        "system_loss_pct":       round(sys_loss * 100.0, 2),
        "peak_step_loss_pct":    round(peak_step_loss * 100.0, 2),
        "weighted_avg_fraction": round(avg_frac, 4),
    }


# ───────────────────────────────────────────────────────────────────────
# Bucket selection
# ───────────────────────────────────────────────────────────────────────

def pick_shading_bucket(loss_pct: float) -> Tuple[str, float, float]:
    """Map a computed loss% to a SHADING_BUCKETS row.

    Conservative pick: choose the highest row whose loss <= computed
    loss%, matching the spec rule "interpolate or select the conservative
    lower shading factor".
    """
    chosen = SHADING_BUCKETS[0]
    for label, bucket_loss, factor in SHADING_BUCKETS:
        if loss_pct >= bucket_loss:
            chosen = (label, bucket_loss, factor)
    return chosen


# ───────────────────────────────────────────────────────────────────────
# Top-level convenience: run the whole pipeline once
# ───────────────────────────────────────────────────────────────────────

def run_full_analysis(*,
                      lat_deg: float,
                      lon_deg: float,
                      on_date: datetime,
                      tz_offset_h: float,
                      num_panels: int,
                      tilt_deg: float,
                      array_azimuth_deg: float,
                      mount_height_m: float,
                      obstructions: Sequence[Obstruction],
                      mitigation: str = "Bypass diodes",
                      panels_per_string: int = DEFAULT_PANELS_PER_STRING,
                      step_minutes: int = 30,
                      panel_w_m: float = 1.13,
                      panel_h_m: float = 1.72) -> Dict[str, object]:
    """Build panels, run time-series, integrate losses, pick a bucket.

    Returned dict is the contract every UI/PDF/agent piece reads from.
    """
    panels = build_panel_grid(
        num_panels=num_panels,
        tilt_deg=tilt_deg,
        array_azimuth_deg=array_azimuth_deg,
        mount_height_m=mount_height_m,
        panel_w_m=panel_w_m, panel_h_m=panel_h_m,
    )
    series = time_series_shading(
        panels=panels, obstructions=obstructions,
        lat_deg=lat_deg, lon_deg=lon_deg, on_date=on_date,
        tz_offset_h=tz_offset_h, step_minutes=step_minutes,
    )
    energy = energy_loss_with_electrical_model(
        series, mitigation=mitigation,
        panels_per_string=panels_per_string,
    )
    bucket = pick_shading_bucket(energy["system_loss_pct"])

    # Shading start/end: first and last step with avg_fraction > 1 %.
    shading_steps = [s for s in series if s.avg_fraction > 0.01]
    shading_start = shading_steps[0].when.strftime("%H:%M") if shading_steps else "--"
    shading_end   = shading_steps[-1].when.strftime("%H:%M") if shading_steps else "--"
    shading_duration_h = (len(shading_steps) * step_minutes) / 60.0

    # Peak-step affected counts (for the dashboard banner).
    peak_step = max(series, key=lambda s: s.avg_fraction, default=None)
    affected_panels = sum(1 for f in (peak_step.per_panel_fraction if peak_step else [])
                          if f > 0.01)
    heavily_affected = sum(1 for f in (peak_step.per_panel_fraction if peak_step else [])
                           if f > 0.25)

    return {
        "panels":              panels,
        "series":              series,
        "energy":              energy,
        "bucket_label":        bucket[0],
        "bucket_loss_pct":     bucket[1],
        "bucket_factor":       bucket[2],
        "shading_start":       shading_start,
        "shading_end":         shading_end,
        "shading_duration_h":  round(shading_duration_h, 2),
        "affected_panels":     affected_panels,
        "heavily_affected":    heavily_affected,
        "total_panels":        len(panels),
        "n_strings":           max(1, math.ceil(len(panels) / panels_per_string)),
        "mitigation":          mitigation,
    }
