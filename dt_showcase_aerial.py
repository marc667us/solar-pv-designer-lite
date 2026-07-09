"""Design-driven showcase aerial renderer (SolarPro Generation Station).

Truthful presentation rule: the Showcase must depict the CUSTOMER'S OWN design,
not a generic stock photo. This module renders an oblique bird's-eye aerial of
the ACTUAL twin scene (the same object graph the 3D Digital Twin consumes, from
``build_scene_from_project``), so Showcase, Twin and design results all show the
identical arrangement. It is a *generated view of the design*, labelled as such
in the UI -- never presented as a photograph of a built plant.

Pure + importable (reuse rule 0.3): consumes a scene dict, returns a PNG (bytes)
plus the projected screen anchors of the key equipment so the callout chips sit
on the real objects. No new sizing/finance engine. Never raises: a malformed or
empty scene yields a plain sited-field image rather than an exception.

Rendering: Pillow only (self-hosted, deterministic, no WebGL -> works headless
and on Render). Oblique frontal projection: +X east -> right, +Z south -> toward
the viewer/bottom, +Y up -> raised on screen; painter's algorithm north->south.
"""
from __future__ import annotations

import io
import math
from typing import Any

__all__ = ["render_plant_aerial", "aerial_callout_anchors"]

# ---- oblique projection tuned to echo the reference aerial composition -------
_DEPTH = 0.55     # z (south) foreshortening -> vertical screen travel
_SKEW = 0.20      # z contribution to screen-x -> gives the oblique side-face
_RISE = 0.72      # y (height) -> screen-up


def _project(x: float, y: float, z: float, scale: float,
             cx: float, cy: float) -> tuple[float, float]:
    sx = cx + x * scale + z * scale * _SKEW
    sy = cy + z * scale * _DEPTH - y * scale * _RISE
    return sx, sy


def _shade(rgb: tuple[int, int, int], f: float) -> tuple[int, int, int]:
    return (max(0, min(255, int(rgb[0] * f))),
            max(0, min(255, int(rgb[1] * f))),
            max(0, min(255, int(rgb[2] * f))))


# layer -> (top, side, front) base colours
_COLORS: dict[str, tuple[int, int, int]] = {
    "pv_row": (28, 42, 92), "pv_array": (28, 42, 92),
    "inverter": (196, 170, 60), "combiner": (196, 170, 60),
    "transformer": (70, 120, 84), "transformer_bldg": (70, 120, 84),
    "rmu": (120, 128, 138), "mv_switchgear": (120, 128, 138),
    "control_room": (210, 196, 150), "om_building": (206, 190, 160),
    "building": (208, 194, 158), "scada_bldg": (150, 158, 168),
    "battery_room": (176, 150, 120), "security_gate": (200, 190, 170),
    "internal_roads": (74, 74, 78), "cable_trench": (52, 52, 56),
    "grid_line": (120, 128, 138), "weather_mast": (150, 158, 150),
    "cctv_pole": (150, 158, 150), "lighting_pole": (150, 158, 150),
}


def _box_faces(o: dict[str, Any], scale: float, cx: float, cy: float):
    """Return painter-ordered (polygon, colour) faces for one box object."""
    t = (o.get("transform") or {}).get("position") or [o.get("x", 0),
                                                        o.get("y", 0), o.get("z", 0)]
    px, py, pz = float(t[0]), float(t[1]), float(t[2])
    dm = o.get("dimensions") or {}
    w = float(dm.get("w", o.get("w", 1)) or 1)
    h = float(dm.get("h", o.get("h", 1)) or 1)
    l = float(dm.get("l", o.get("l", 1)) or 1)
    hw, hl = w / 2.0, l / 2.0
    base = _COLORS.get(o.get("layer"), (170, 170, 174))
    top = _shade(base, 1.0)
    front = _shade(base, 0.72)   # south face (toward viewer)
    side = _shade(base, 0.55)    # east face
    y0, y1 = py - h / 2.0, py + h / 2.0

    def P(dx, dy, dz):
        return _project(px + dx, dy, pz + dz, scale, cx, cy)

    faces = []
    # east side face (x+)
    faces.append(([P(hw, y0, -hl), P(hw, y0, hl), P(hw, y1, hl), P(hw, y1, -hl)], side))
    # south front face (z+)
    faces.append(([P(-hw, y0, hl), P(hw, y0, hl), P(hw, y1, hl), P(-hw, y1, hl)], front))
    # top face (y+)
    faces.append(([P(-hw, y1, -hl), P(hw, y1, -hl), P(hw, y1, hl), P(-hw, y1, hl)], top))
    return faces, (px, py, pz)


def render_plant_aerial(scene: dict[str, Any], width: int = 1600,
                        height: int = 900) -> bytes:
    """Render the scene as an oblique aerial PNG (bytes). Never raises."""
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except Exception:
        return b""
    try:
        objs = (scene or {}).get("objects") or []
        terrain = (scene or {}).get("terrain") or {}
        side = float(terrain.get("side_m") or
                     ((scene or {}).get("site") or {}).get("land_side_m") or 300.0)
        side = max(side, 40.0)

        img = Image.new("RGB", (width, height), (150, 180, 205))
        d = ImageDraw.Draw(img, "RGBA")
        # sky gradient (top) -> haze near horizon
        for yy in range(int(height * 0.42)):
            f = yy / max(1.0, height * 0.42)
            col = (int(74 + (196 - 74) * f), int(134 + (216 - 134) * f),
                   int(200 + (230 - 200) * f))
            d.line([(0, yy), (width, yy)], fill=col)

        # fit the whole site into the lower ~75% of the frame
        scale = min(width / (side * (1.0 + _SKEW)), height / (side * _DEPTH)) * 0.82
        cx, cy = width / 2.0, height * 0.46

        # ground: project the four terrain corners as a filled quad
        h2 = side / 2.0
        gcorners = [_project(-h2, 0, -h2, scale, cx, cy),
                    _project(h2, 0, -h2, scale, cx, cy),
                    _project(h2, 0, h2, scale, cx, cy),
                    _project(-h2, 0, h2, scale, cx, cy)]
        d.polygon(gcorners, fill=(74, 110, 58))
        # faint field striations for texture
        for gx in range(-int(h2), int(h2), 14):
            a = _project(gx, 0, -h2, scale, cx, cy)
            b = _project(gx, 0, h2, scale, cx, cy)
            d.line([a, b], fill=(80, 118, 62), width=1)

        # linear routes (cable trenches / grid line) carry meta.route endpoints;
        # draw them as thin ground lines BEFORE the boxes (a box would render a
        # rotated route as a full-width bar, since _box_faces is axis-aligned).
        for o in objs:
            if o.get("layer") not in ("cable_trench", "grid_line"):
                continue
            # per-item guard: a single malformed route must not abort the whole
            # render (which would blank the truthful design aerial). Skip it.
            try:
                rt = (o.get("meta") or {}).get("route")
                if not (isinstance(rt, list) and len(rt) == 2):
                    continue
                yq = 4.0 if o.get("layer") == "grid_line" else 0.12
                a = _project(float(rt[0][0]), yq, float(rt[0][1]), scale, cx, cy)
                b = _project(float(rt[1][0]), yq, float(rt[1][1]), scale, cx, cy)
                col = (150, 158, 168) if o.get("layer") == "grid_line" else (46, 46, 50)
                d.line([a, b], fill=col,
                       width=3 if o.get("layer") == "grid_line" else 2)
            except (TypeError, ValueError, IndexError):
                continue

        # collect + painter-sort all box faces by object depth (north first)
        drawable = [o for o in objs
                    if o.get("layer") not in ("terrain", "fence",
                                              "cable_trench", "grid_line")]
        drawable.sort(key=lambda o: ((o.get("transform") or {}).get("position",
                      [0, 0, o.get("z", 0)])[2]))
        for o in drawable:
            try:
                faces, _c = _box_faces(o, scale, cx, cy)
                # ground shadow (soft) for lift
                pos = (o.get("transform") or {}).get("position") or [0, 0, 0]
                dm = o.get("dimensions") or {}
                hw = float(dm.get("w", 1) or 1) / 2.0
                hl = float(dm.get("l", 1) or 1) / 2.0
                sh = [_project(pos[0] - hw + 1.5, 0, pos[2] - hl + 1.5, scale, cx, cy),
                      _project(pos[0] + hw + 1.5, 0, pos[2] - hl + 1.5, scale, cx, cy),
                      _project(pos[0] + hw + 1.5, 0, pos[2] + hl + 1.5, scale, cx, cy),
                      _project(pos[0] - hw + 1.5, 0, pos[2] + hl + 1.5, scale, cx, cy)]
                d.polygon(sh, fill=(0, 0, 0, 55))
                for poly, col in faces:
                    d.polygon(poly, fill=col, outline=_shade(col, 0.6))
            except Exception:
                continue

        # perimeter fence outline
        fc = [_project(-h2 + 1, 0, -h2 + 1, scale, cx, cy),
              _project(h2 - 1, 0, -h2 + 1, scale, cx, cy),
              _project(h2 - 1, 0, h2 - 1, scale, cx, cy),
              _project(-h2 + 1, 0, h2 - 1, scale, cx, cy)]
        d.line(fc + [fc[0]], fill=(150, 150, 120), width=2)

        img = img.filter(ImageFilter.SMOOTH_MORE)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return b""


def aerial_callout_anchors(scene: dict[str, Any], width: int = 1600,
                           height: int = 900) -> dict[str, dict[str, float]]:
    """Return {key: {x%, y%}} anchors for PV array / inverter / substation,
    projected from the ACTUAL object positions so callouts sit on real equipment.
    Never raises; missing groups are omitted.
    """
    out: dict[str, dict[str, float]] = {}
    try:
        objs = (scene or {}).get("objects") or []
        terrain = (scene or {}).get("terrain") or {}
        # resolve the site side length the SAME way render_plant_aerial does
        # (terrain.side_m, else site.land_side_m, else 300) so the projected
        # callout anchors line up with the rendered image, not a stale default.
        side = max(float(terrain.get("side_m") or
                         ((scene or {}).get("site") or {}).get("land_side_m")
                         or 300.0), 40.0)
        scale = min(width / (side * (1.0 + _SKEW)), height / (side * _DEPTH)) * 0.82
        cx, cy = width / 2.0, height * 0.46

        def centroid(layers):
            pts = [(o.get("transform") or {}).get("position") or [0, 0, 0]
                   for o in objs if o.get("layer") in layers]
            if not pts:
                return None
            ax = sum(p[0] for p in pts) / len(pts)
            ay = sum(p[1] for p in pts) / len(pts)
            az = sum(p[2] for p in pts) / len(pts)
            sx, sy = _project(ax, ay + 4, az, scale, cx, cy)
            return {"x": round(100.0 * sx / width, 1),
                    "y": round(100.0 * sy / height, 1)}

        for key, layers in (("array", ("pv_row", "pv_array")),
                            ("inverter", ("inverter", "combiner")),
                            ("substation", ("transformer", "transformer_bldg",
                                            "control_room", "om_building",
                                            "building"))):
            a = centroid(layers)
            if a:
                out[key] = a
    except Exception:
        return out
    return out
