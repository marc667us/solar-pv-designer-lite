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

__all__ = ["render_plant_aerial", "aerial_callout_anchors",
           "render_plant_view", "view_available", "SHOWCASE_VIEWS"]

# The showcase gallery. Each view is the SAME scene the twin renders, framed on
# a different part of the customer's own plant -- never a stock photograph.
# (layers to frame, zoom, night, anchor) -- anchor "south" frames the subject's
# leading edge so the shot has foreground ground instead of wall-to-wall array.
SHOWCASE_VIEWS: dict[str, tuple[tuple[str, ...], float, bool, str]] = {
    "aerial":     ((), 1.0, False, "centroid"),
    "panels":     (("pv_row", "pv_array"), 5.0, False, "south"),
    # one representative skid, not the mean of a dozen spread across 600 m --
    # a centroid of scattered equipment frames the empty gap between them
    "inverter":   (("inverter",), 13.0, False, "nearest"),
    "substation": (("substation", "transformer_bldg", "transformer",
                    "control_room", "om_building", "battery_room"), 4.2,
                   False, "centroid"),
    "night":      ((), 1.0, True, "centroid"),
}

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


# Render budget. A utility plant's row count grows with the site, and a close-up
# would otherwise walk every row (and every table in it) just to discover it is
# off-frame. These bound the work one request can do on the free-tier box.
_CULL_MARGIN = 48.0      # px of slack around the viewport before an object is cut
_MAX_TABLES = 24000      # detailed tables per render; rows past it draw as ribbons


def _proj_bbox(px: float, pz: float, hw: float, hl: float, ytop: float,
               scale: float, cx: float, cy: float) -> tuple[float, float,
                                                            float, float]:
    """Screen bounding box (x0, y0, x1, y1) of an axis-aligned box object."""
    xs, ys = [], []
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            for y in (0.0, ytop):
                sxp, syp = _project(px + sx * hw, y, pz + sz * hl, scale, cx, cy)
                xs.append(sxp)
                ys.append(syp)
    return min(xs), min(ys), max(xs), max(ys)


def _off_frame(bbox: tuple[float, float, float, float],
               width: int, height: int) -> bool:
    x0, y0, x1, y1 = bbox
    return (x1 < -_CULL_MARGIN or x0 > width + _CULL_MARGIN
            or y1 < -_CULL_MARGIN or y0 > height + _CULL_MARGIN)


def _pv_row_geometry(o: dict[str, Any]) -> tuple[float, float, float, float,
                                                 float, float, float, int]:
    """Unpack one pv_row into (px, py, pz, hw, half_depth, rise, tilt, n_tables).

    A row is stored as a flat box plus a tilt in meta/rotation. Rendering it as
    the stored box gives a featureless stripe, so we recover the real geometry:
    the module plane is tilted about the east-west axis, its north edge lifted
    by `rise` and its south edge dropped by the same, which foreshortens the
    plan depth to l*cos(tilt).
    """
    t = (o.get("transform") or {}).get("position") or [0, 0, 0]
    px, py, pz = float(t[0]), float(t[1]), float(t[2])
    dm = o.get("dimensions") or {}
    w = abs(float(dm.get("w", 1) or 1))
    l = abs(float(dm.get("l", 1) or 1))
    meta = o.get("meta") or {}
    tilt = meta.get("tilt_deg")
    if tilt is None:
        rot = (o.get("transform") or {}).get("rotation_deg") or [0, 0, 0]
        tilt = rot[0] if rot else 0.0
    tilt = abs(float(tilt or 0.0))
    tilt = tilt if 0.0 <= tilt <= 60.0 else 0.0
    rad = math.radians(tilt)
    n = int(meta.get("modules") or (o.get("engineering") or {}).get("quantity") or 1)
    n = max(1, min(n, 400))
    return (px, py, pz, w / 2.0, l * math.cos(rad) / 2.0,
            l * math.sin(rad) / 2.0, tilt, n)


def _draw_pv_row(d, o: dict[str, Any], scale: float, cx: float, cy: float,
                 night: bool, width: int, budget: int) -> int:
    """Draw one PV row as tilted module tables on piles. Returns tables drawn.

    LOD: a table narrower than ~7 screen px cannot show a frame or a support
    pile, so the whole row collapses to a single tilted quad -- the whole-site
    aerial stays fast and clean, while a close-up resolves real hardware. The
    same collapse happens once `budget` tables have been drawn, so no single
    request can be made to rasterise an unbounded number of polygons.
    """
    px, py, pz, hw, hd, rise, tilt, n = _pv_row_geometry(o)
    glass = _shade((28, 42, 92), 0.42 if night else 1.0)
    frame = _shade((176, 182, 194), 0.42 if night else 1.0)
    pile = _shade((84, 88, 96), 0.42 if night else 1.0)
    zn, zs = pz - hd, pz + hd            # north (high) and south (low) edges
    yn, ys = py + rise, py - rise
    table_px = (2.0 * hw / n) * scale

    if table_px < 7.0 or budget <= 0:     # far view / budget spent: one ribbon
        poly = [_project(px - hw, yn, zn, scale, cx, cy),
                _project(px + hw, yn, zn, scale, cx, cy),
                _project(px + hw, ys, zs, scale, cx, cy),
                _project(px - hw, ys, zs, scale, cx, cy)]
        d.polygon(poly, fill=glass)
        return 0

    # only the tables whose x-span lands on screen need drawing. Solve for the
    # index range directly instead of projecting all n of them -- at a close-up
    # zoom a 600 m row has thousands of metres outside the viewport.
    pitch = 2.0 * hw / n
    gap = pitch * 0.06                    # 6% inter-table gap, as built
    x_at_left, _y = _project(px - hw, yn, zn, scale, cx, cy)
    lo = int((-_CULL_MARGIN - x_at_left) / (pitch * scale)) - 1
    hi = int((width + _CULL_MARGIN - x_at_left) / (pitch * scale)) + 1
    lo, hi = max(0, lo), min(n, hi + 1)
    drawn = 0
    for i in range(lo, hi):
        if drawn >= budget:
            break
        x0 = px - hw + i * pitch
        x1 = x0 + pitch - gap
        # supporting pile under the south edge of every table
        a = _project((x0 + x1) / 2.0, ys, zs, scale, cx, cy)
        b = _project((x0 + x1) / 2.0, 0.0, zs, scale, cx, cy)
        d.line([a, b], fill=pile, width=max(1, int(table_px * 0.05)))
        poly = [_project(x0, yn, zn, scale, cx, cy),
                _project(x1, yn, zn, scale, cx, cy),
                _project(x1, ys, zs, scale, cx, cy),
                _project(x0, ys, zs, scale, cx, cy)]
        d.polygon(poly, fill=glass, outline=frame if table_px >= 14 else None)
        drawn += 1
    return drawn


def render_plant_aerial(scene: dict[str, Any], width: int = 1600,
                        height: int = 900, *,
                        focus: tuple[float, float] | None = None,
                        zoom: float = 1.0, night: bool = False) -> bytes:
    """Render the scene as an oblique PNG (bytes). Never raises.

    in : scene -- the twin scene graph (build_scene_from_project + augment)
         focus -- (x, z) world point to centre the frame on; None = whole site
         zoom  -- >1 moves the camera in (a close-up of equipment or panels)
         night -- dusk palette with lit windows on the equipment
    out: PNG bytes, or b"" on any failure
    """
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
        zoom = max(0.2, min(float(zoom or 1.0), 40.0))

        sky_top = (18, 26, 54) if night else (74, 134, 200)
        sky_bot = (86, 74, 96) if night else (196, 216, 230)
        ground = (30, 44, 30) if night else (74, 110, 58)
        stripe = (34, 48, 33) if night else (80, 118, 62)

        img = Image.new("RGB", (width, height), sky_bot)
        d = ImageDraw.Draw(img, "RGBA")
        # sky gradient (top) -> haze near horizon
        for yy in range(int(height * 0.42)):
            f = yy / max(1.0, height * 0.42)
            col = tuple(int(sky_top[i] + (sky_bot[i] - sky_top[i]) * f) for i in range(3))
            d.line([(0, yy), (width, yy)], fill=col)

        # fit the whole site into the lower ~75% of the frame, then zoom in
        scale = min(width / (side * (1.0 + _SKEW)),
                    height / (side * _DEPTH)) * 0.82 * zoom
        cx, cy = width / 2.0, height * 0.46
        # re-centre the frame on the focus point (a panel block, the inverter
        # skid, the substation) so a close-up actually frames its subject
        if focus is not None:
            fx, fz = float(focus[0]), float(focus[1])
            px, py = _project(fx, 0.0, fz, scale, cx, cy)
            cx += (width / 2.0) - px
            cy += (height * 0.56) - py

        # ground: the site quad for the whole-site aerial. A focused close-up
        # re-centres and magnifies, so the site square no longer covers the
        # viewport -- sky colour would show through beneath the field. Re-centre
        # the quad on the subject and grow it to the visible world extent.
        h2 = side / 2.0
        if focus is None:
            gx0, gz0, gh = 0.0, 0.0, h2
        else:
            gx0, gz0 = float(focus[0]), float(focus[1])
            gh = max(h2, (width + height) / max(scale, 1e-6))
        gstep = max(4.0, 2.0 * gh / 35.0)
        gcorners = [_project(gx0 - gh, 0, gz0 - gh, scale, cx, cy),
                    _project(gx0 + gh, 0, gz0 - gh, scale, cx, cy),
                    _project(gx0 + gh, 0, gz0 + gh, scale, cx, cy),
                    _project(gx0 - gh, 0, gz0 + gh, scale, cx, cy)]
        d.polygon(gcorners, fill=ground)
        # faint field striations for texture
        for i in range(int(2.0 * gh / gstep) + 1):
            gx = gx0 - gh + i * gstep
            a = _project(gx, 0, gz0 - gh, scale, cx, cy)
            b = _project(gx, 0, gz0 + gh, scale, cx, cy)
            d.line([a, b], fill=stripe, width=1)

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
        budget = _MAX_TABLES
        for o in drawable:
            try:
                # ground shadow (soft) for lift
                pos = (o.get("transform") or {}).get("position") or [0, 0, 0]
                dm = o.get("dimensions") or {}
                hw = float(dm.get("w", 1) or 1) / 2.0
                hl = float(dm.get("l", 1) or 1) / 2.0
                # object-level frustum cull: a close-up frames a few rows out of
                # hundreds, so reject the rest before touching their geometry
                if _off_frame(_proj_bbox(float(pos[0]), float(pos[2]), hw, hl,
                                         float(dm.get("h", 1) or 1),
                                         scale, cx, cy), width, height):
                    continue
                sh = [_project(pos[0] - hw + 1.5, 0, pos[2] - hl + 1.5, scale, cx, cy),
                      _project(pos[0] + hw + 1.5, 0, pos[2] - hl + 1.5, scale, cx, cy),
                      _project(pos[0] + hw + 1.5, 0, pos[2] + hl + 1.5, scale, cx, cy),
                      _project(pos[0] - hw + 1.5, 0, pos[2] + hl + 1.5, scale, cx, cy)]
                d.polygon(sh, fill=(0, 0, 0, 55))
                # a PV row is a tilted module plane, not a slab -- drawing it as
                # a box yields a featureless stripe under any magnification.
                if o.get("layer") in ("pv_row", "pv_array"):
                    budget -= _draw_pv_row(d, o, scale, cx, cy, night,
                                           width, budget)
                    continue
                faces, _c = _box_faces(o, scale, cx, cy)
                for poly, col in faces:
                    if night:
                        col = _shade(col, 0.42)
                    d.polygon(poly, fill=col, outline=_shade(col, 0.6))
                # at dusk the occupied buildings show light
                if night and o.get("layer") in ("inverter", "substation",
                                                "transformer_bldg", "control_room",
                                                "om_building", "building"):
                    lx, ly = _project(pos[0], 2.2, pos[2], scale, cx, cy)
                    r = max(2.0, 2.6 * (scale / 3.0))
                    d.ellipse([lx - r, ly - r, lx + r, ly + r], fill=(255, 214, 130, 220))
            except Exception:
                continue

        # perimeter fence outline
        fc = [_project(-h2 + 1, 0, -h2 + 1, scale, cx, cy),
              _project(h2 - 1, 0, -h2 + 1, scale, cx, cy),
              _project(h2 - 1, 0, h2 - 1, scale, cx, cy),
              _project(-h2 + 1, 0, h2 - 1, scale, cx, cy)]
        d.line(fc + [fc[0]], fill=(96, 96, 80) if night else (150, 150, 120), width=2)

        img = img.filter(ImageFilter.SMOOTH_MORE)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return b""


def _centroid_of(scene: dict[str, Any], layers: tuple[str, ...],
                 anchor: str = "centroid"):
    """Framing point for a group of objects. out: (x, z) or None if absent.

    in : anchor -- "centroid" (middle of the group), "south" (the group's
         near/leading edge, so a close-up keeps open ground in the foreground),
         or "nearest" (the single member closest to the centroid, so a tight
         shot lands on real hardware rather than the gap between two units)
    """
    xs, zs = [], []
    for o in (scene or {}).get("objects") or []:
        if o.get("layer") not in layers:
            continue
        p = (o.get("transform") or {}).get("position") or None
        if not (isinstance(p, (list, tuple)) and len(p) >= 3):
            continue
        try:
            xs.append(float(p[0]))
            zs.append(float(p[2]))
        except (TypeError, ValueError):
            continue
    if not xs:
        return None
    mx, mz = sum(xs) / len(xs), sum(zs) / len(zs)
    if anchor == "south":
        return (mx, max(zs))
    if anchor == "nearest":
        return min(zip(xs, zs),
                   key=lambda p: (p[0] - mx) ** 2 + (p[1] - mz) ** 2)
    return (mx, mz)


def render_plant_view(scene: dict[str, Any], view: str = "aerial",
                      width: int = 1600, height: int = 900) -> bytes:
    """Render one showcase view of the customer's OWN plant. Never raises.

    Each view frames the same scene graph the 3D twin consumes, so the gallery
    depicts the actual design -- module count, row pitch, equipment placement --
    rather than a stock photograph of somebody else's solar farm.

    in : scene, view (a key of SHOWCASE_VIEWS), width, height
    out: PNG bytes; b"" if the view is unknown or the render fails
    """
    try:
        spec = SHOWCASE_VIEWS.get(str(view or "aerial"))
        if not spec:
            return b""
        layers, zoom, night, anchor = spec
        focus = _centroid_of(scene, layers, anchor) if layers else None
        if layers and focus is None:
            # This plant has no such equipment. Falling back to the whole-site
            # frame would put the entire plant under a caption that names a
            # substation or an inverter station -- the exact kind of "picture
            # that isn't what it claims to be" this module exists to prevent.
            # No subject, no frame; callers omit the scene (see view_available).
            return b""
        return render_plant_aerial(scene, width, height,
                                   focus=focus, zoom=zoom, night=night)
    except Exception:
        return b""


def view_available(scene: dict[str, Any], view: str) -> bool:
    """True when `view` has a subject to frame in this scene. Never raises.

    Lets the gallery drop a scene it cannot honestly render, instead of showing
    a substitute image under that scene's caption.
    """
    try:
        spec = SHOWCASE_VIEWS.get(str(view or ""))
        if not spec:
            return False
        layers, _zoom, _night, anchor = spec
        return (not layers) or _centroid_of(scene, layers, anchor) is not None
    except Exception:
        return False


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
