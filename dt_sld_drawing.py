"""Render a real single-line diagram (SVG) from the SLD model.

The Electrical SLD page previously showed only a vertical stack of *stage cards*
-- ratings, standards, protection notes -- but no actual one-line drawing. This
module draws the diagram itself: IEC-style symbols wired together from the PV
array down through the string fuses, combiner, DC switchgear, inverter, LV AC
switchgear and step-up transformer onto the MV collection busbar, then out to
the main substation metering and the grid point of interconnection.

Reuse (Agentic ADK Extension SS0.3): consumes the dict returned by
``dt_electrical_sld.build_sld_model`` -- it derives NO new engineering values and
owns no sizing logic. Pure + importable: no Flask, no request context, no I/O.

Never-raises: ``render_sld_svg`` returns "" if anything goes wrong, so a bad
project can degrade the page to the existing stage cards rather than 500.

Honesty: ``build_sld_model`` falls back to a sizing DERIVED from the project's
target capacity when Step-7 sizing has not been committed. A drawing built from
derived numbers must not be presented as committed engineering, so callers pass
``committed=has_committed_sizing(proj)`` and the title block says which it is.

Public API
----------
render_sld_svg(sld: dict, *, committed: bool = True) -> str
    in : the build_sld_model(proj) mapping; committed = is the sizing real?
    out: an <svg> markup string (already escaped), or "" on any failure
"""
from __future__ import annotations

from html import escape
from typing import Any

__all__ = ["render_sld_svg"]

# ---- palette (matches the dark app chrome used by the SLD template) ----
_LINE = "#8fa3b8"       # conductor
_MV = "#f59e0b"         # medium-voltage conductor / busbar
_DC = "#4ade80"         # DC conductor
_SYM = "#cbd5e1"        # symbol stroke
_TXT = "#e6edf3"        # primary label
_DIM = "#94a3b8"        # secondary label
_ACC = "#f59e0b"        # titles
_GHOST = "#3b4a5e"      # repeated (ghost) feeders

_W, _H = 1180, 1010     # viewBox
_COL = 250              # x of the detailed inverter-block column
_BUS_Y = 838            # y of the MV collection busbar
_BUS_X0, _BUS_X1 = 120, 900


def _f(v: Any, d: float = 0.0) -> float:
    """Coerce to float, never raising. in: any, default. out: float."""
    try:
        f = float(v)
        return f if f == f and abs(f) != float("inf") else d
    except Exception:
        return d


def _i(v: Any, d: int = 0) -> int:
    """Coerce to int, never raising. in: any, default. out: int."""
    try:
        return int(_f(v, d))
    except Exception:
        return d


def _t(x: float, y: float, s: str, *, fill: str = _TXT, size: int = 12,
       weight: str = "400", anchor: str = "start") -> str:
    """One <text> node with escaped content. out: svg markup."""
    return (f'<text x="{x:.0f}" y="{y:.0f}" fill="{fill}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}" '
            f'font-family="system-ui,Segoe UI,sans-serif">{escape(str(s))}</text>')


def _wire(x1: float, y1: float, x2: float, y2: float, *,
          color: str = _LINE, width: float = 1.6, dash: str = "") -> str:
    """A conductor segment. out: svg markup."""
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
            f'stroke="{color}" stroke-width="{width}"{d} stroke-linecap="round"/>')


# --------------------------------------------------------------------------
# IEC-ish symbols. Each is drawn centred on (x, y) and returns svg markup.
# --------------------------------------------------------------------------
def _sym_pv(x: float, y: float) -> str:
    """PV array: a module face with cell grid and the incident-light arrow."""
    w, h = 84, 52
    p = [f'<rect x="{x-w/2:.0f}" y="{y-h/2:.0f}" width="{w}" height="{h}" rx="3" '
         f'fill="#0f2038" stroke="{_SYM}" stroke-width="1.6"/>']
    for i in range(1, 4):                       # vertical cell divisions
        cx = x - w / 2 + i * w / 4
        p.append(_wire(cx, y - h / 2, cx, y + h / 2, color=_SYM, width=0.8))
    p.append(_wire(x - w / 2, y, x + w / 2, y, color=_SYM, width=0.8))
    for dx in (-16, 4):                          # sun arrows onto the face
        p.append(_wire(x + dx - 10, y - h / 2 - 20, x + dx + 2, y - h / 2 - 6,
                       color=_ACC, width=1.4))
        p.append(f'<path d="M{x+dx+2:.0f},{y-h/2-6:.0f} l-6,0 l4,-5 z" fill="{_ACC}"/>')
    return "".join(p)


def _sym_fuse(x: float, y: float) -> str:
    """String fuse: rectangle straddling the conductor (IEC 60269)."""
    return (f'<rect x="{x-7:.0f}" y="{y-13:.0f}" width="14" height="26" '
            f'fill="#0b1220" stroke="{_SYM}" stroke-width="1.5"/>'
            + _wire(x, y - 13, x, y + 13, color=_SYM, width=1.0))


def _sym_combiner(x: float, y: float) -> str:
    """DC combiner box: enclosure with several string inputs merging to one."""
    w, h = 92, 44
    p = [f'<rect x="{x-w/2:.0f}" y="{y-h/2:.0f}" width="{w}" height="{h}" rx="3" '
         f'fill="#0b1220" stroke="{_SYM}" stroke-width="1.6"/>']
    for dx in (-28, -10, 8):                     # incoming strings
        p.append(_wire(x + dx, y - h / 2, x + dx, y - 4, color=_DC, width=1.2))
        p.append(_wire(x + dx, y - 4, x + 26, y - 4, color=_DC, width=1.2))
    p.append(_wire(x + 26, y - 4, x + 26, y + h / 2, color=_DC, width=1.4))
    return "".join(p)


def _sym_disconnect(x: float, y: float) -> str:
    """Load-break disconnector: hinged blade open at an angle."""
    return (_wire(x, y - 16, x, y - 6, color=_SYM)
            + _wire(x, y - 6, x + 13, y + 8, color=_SYM)
            + _wire(x, y + 6, x, y + 16, color=_SYM)
            + f'<circle cx="{x:.0f}" cy="{y-6:.0f}" r="2.4" fill="{_SYM}"/>'
            + f'<circle cx="{x:.0f}" cy="{y+6:.0f}" r="2.4" fill="{_SYM}"/>')


def _sym_inverter(x: float, y: float) -> str:
    """Inverter: square split by a diagonal, DC side '=' and AC side sine."""
    s = 46
    p = [f'<rect x="{x-s/2:.0f}" y="{y-s/2:.0f}" width="{s}" height="{s}" rx="3" '
         f'fill="#0b1220" stroke="{_SYM}" stroke-width="1.6"/>',
         _wire(x - s / 2, y + s / 2, x + s / 2, y - s / 2, color=_SYM, width=1.2)]
    p.append(_wire(x - 15, y - 9, x - 5, y - 9, color=_DC, width=1.4))   # '='
    p.append(_wire(x - 15, y - 4, x - 5, y - 4, color=_DC, width=1.4))
    p.append(f'<path d="M{x+3:.0f},{y+9:.0f} q4,-9 8,0 q4,9 8,0" fill="none" '
             f'stroke="{_LINE}" stroke-width="1.4"/>')                    # sine
    return "".join(p)


def _sym_breaker(x: float, y: float, *, color: str = _SYM) -> str:
    """Circuit breaker: IEC square on the conductor."""
    return (f'<rect x="{x-9:.0f}" y="{y-9:.0f}" width="18" height="18" '
            f'fill="none" stroke="{color}" stroke-width="1.8"/>')


def _sym_transformer(x: float, y: float) -> str:
    """Two-winding transformer: the classic pair of interlinked circles."""
    return (f'<circle cx="{x:.0f}" cy="{y-11:.0f}" r="16" fill="none" '
            f'stroke="{_SYM}" stroke-width="1.6"/>'
            f'<circle cx="{x:.0f}" cy="{y+11:.0f}" r="16" fill="none" '
            f'stroke="{_SYM}" stroke-width="1.6"/>')


def _sym_meter(x: float, y: float) -> str:
    """Revenue metering point: circle marked M."""
    return (f'<circle cx="{x:.0f}" cy="{y:.0f}" r="12" fill="#0b1220" '
            f'stroke="{_MV}" stroke-width="1.6"/>'
            + _t(x, y + 4, "M", fill=_MV, size=12, weight="700", anchor="middle"))


def _sym_grid(x: float, y: float) -> str:
    """Grid point of interconnection: a transmission pylon."""
    p = [_wire(x - 16, y + 30, x, y - 26, color=_MV, width=1.6),
         _wire(x + 16, y + 30, x, y - 26, color=_MV, width=1.6),
         _wire(x - 11, y + 12, x + 11, y + 12, color=_MV, width=1.4),
         _wire(x - 7, y - 4, x + 7, y - 4, color=_MV, width=1.4),
         _wire(x - 20, y - 12, x + 20, y - 12, color=_MV, width=1.4)]
    return "".join(p)


def _label(x: float, y: float, title: str, sub: str = "") -> str:
    """Right-hand callout: bold title + dim subtitle. out: svg markup."""
    out = _t(x, y, title, fill=_TXT, size=13, weight="700")
    if sub:
        out += _t(x, y + 15, sub, fill=_DIM, size=11)
    return out


def _tag(x: float, y: float, text: str) -> str:
    """Small gold quantity tag drawn left of the riser (e.g. 'x12')."""
    w = 20 + 7 * len(str(text))
    return (f'<rect x="{x-w:.0f}" y="{y-9:.0f}" width="{w}" height="18" rx="9" '
            f'fill="#2a1f06" stroke="{_ACC}" stroke-width="1"/>'
            + _t(x - w / 2, y + 4, text, fill=_ACC, size=10, weight="700",
                 anchor="middle"))


def render_sld_svg(sld: dict[str, Any], *, committed: bool = True) -> str:
    """Draw the single-line diagram for a Generation-Station project.

    in : sld       -- the mapping returned by dt_electrical_sld.build_sld_model
         committed -- True when the sizing is Step-7 committed; False when it was
                      derived from the target capacity (the drawing is then
                      captioned as indicative, never as committed engineering)
    out: <svg> markup string; "" if the model is unusable (never raises)
    """
    try:
        if not isinstance(sld, dict):
            return ""
        proj = sld.get("project") or {}
        volts = sld.get("voltages") or {}
        stages = {s.get("key"): s for s in (sld.get("stages") or [])
                  if isinstance(s, dict)}
        if not stages:
            return ""

        def qty(key: str) -> int:
            return _i((stages.get(key) or {}).get("qty"))

        n_mod = _i(proj.get("n_modules"))
        dc_kwp = _f(proj.get("dc_kwp"))
        ac_mw = _f(proj.get("ac_mw"))
        if n_mod <= 0 and dc_kwp <= 0:
            return ""                     # no committed sizing -> nothing truthful to draw

        n_str = qty("string")
        n_comb = qty("combiner")
        n_inv = qty("inverter")
        mv_kv = _f(volts.get("mv_kv"), 33.0)
        poi_kv = _f(volts.get("poi_kv"), mv_kv)
        lv_v = _f(volts.get("inverter_ac_v"), 800.0)
        dc_v = _f(volts.get("dc_system_v"), 1500.0)
        vmp = _f(volts.get("string_vmp"))

        s: list[str] = []
        s.append(f'<svg viewBox="0 0 {_W} {_H}" role="img" '
                 f'aria-label="Single-line diagram" '
                 f'style="width:100%;height:auto;background:#0b1220;'
                 f'border:1px solid #1c2a3d;border-radius:10px">')

        # ---- title block -------------------------------------------------
        s.append(_t(28, 26, "SINGLE-LINE DIAGRAM", fill=_ACC, size=14, weight="700"))
        s.append(_t(28, 44, f"{proj.get('name') or 'Solar Generation Station'}  "
                            f"·  {dc_kwp:,.0f} kWp DC  ·  {ac_mw:,.1f} MWac  "
                            f"·  {mv_kv:.0f} kV collection", fill=_DIM, size=11))
        # Honesty caption: never let a target-derived drawing read as committed
        # engineering. Mirrors the Showcase honesty gate.
        if not committed:
            s.append(_t(_W - 28, 26, "INDICATIVE — derived from target capacity",
                        fill=_ACC, size=11, weight="700", anchor="end"))
            s.append(_t(_W - 28, 44, "PV sizing not yet committed (Step 7)",
                        fill=_DIM, size=10, anchor="end"))

        lx = _COL + 90        # label column x
        # ---- 1. PV array --------------------------------------------------
        y = 120
        s.append(_sym_pv(_COL, y))
        s.append(_label(lx, y - 4, "PV ARRAY",
                        f"{n_mod:,} modules × {_f(proj.get('module_wp'), 550):.0f} Wp "
                        f"· {dc_kwp:,.0f} kWp · {dc_v:.0f} V DC max"))
        s.append(_wire(_COL, y + 26, _COL, y + 62, color=_DC))

        # ---- 2. String + fuse ---------------------------------------------
        y = 208
        s.append(_sym_fuse(_COL, y))
        s.append(_label(lx, y - 4, "PV STRINGS + STRING FUSES",
                        f"{n_str:,} strings · {vmp:.0f} V Vmp · gPV fuse both poles"))
        if n_str:
            s.append(_tag(_COL - 26, y, f"×{n_str:,}"))
        s.append(_wire(_COL, y + 13, _COL, y + 56, color=_DC))

        # ---- 3. Combiner ---------------------------------------------------
        y = 290
        s.append(_sym_combiner(_COL, y))
        s.append(_label(lx, y - 4, "STRING COMBINER BOX",
                        f"{n_comb:,} combiners · SPD Type 1+2 DC · monitoring"))
        if n_comb:
            s.append(_tag(_COL - 60, y, f"×{n_comb:,}"))
        s.append(_wire(_COL + 26, y + 22, _COL + 26, y + 44, color=_DC))
        s.append(_wire(_COL + 26, y + 44, _COL, y + 44, color=_DC))
        s.append(_wire(_COL, y + 44, _COL, y + 62, color=_DC))

        # ---- 4. DC switchgear ----------------------------------------------
        y = 368
        s.append(_sym_disconnect(_COL, y))
        s.append(_label(lx, y - 4, "DC ARRAY SWITCHGEAR",
                        f"{dc_v:.0f} V load-break disconnector · SPD Type 2 at inverter"))
        s.append(_wire(_COL, y + 16, _COL, y + 54, color=_DC))

        # ---- 5. Inverter ----------------------------------------------------
        y = 445
        s.append(_sym_inverter(_COL, y))
        s.append(_label(lx, y - 4, "CENTRAL INVERTER",
                        f"{n_inv:,} × inverter · DC {dc_v:.0f} V → AC {lv_v:.0f} V "
                        f"· anti-islanding, LVRT"))
        s.append(_wire(_COL, y + 23, _COL, y + 60, color=_LINE))

        # ---- 6. LV AC switchgear --------------------------------------------
        y = 523
        s.append(_sym_breaker(_COL, y))
        s.append(_label(lx, y - 4, "LV AC SWITCHGEAR",
                        f"ACB/MCCB at {lv_v:.0f} V · O/C + E/F protection · metering"))
        s.append(_wire(_COL, y + 9, _COL, y + 52, color=_LINE))

        # ---- 7. Step-up transformer ------------------------------------------
        y = 596
        s.append(_sym_transformer(_COL, y))
        s.append(_label(lx, y + 22, "LV/MV STEP-UP TRANSFORMER",
                        f"{lv_v/1000.0:.2f}/{mv_kv:.0f} kV · Dyn11 · one per inverter station"))
        s.append(_wire(_COL, y + 27, _COL, y + 64, color=_MV))

        # ---- 8. MV switchgear (RMU) -------------------------------------------
        y = 686
        s.append(_sym_breaker(_COL, y, color=_MV))
        s.append(_label(lx, y - 4, "MV SWITCHGEAR (RMU)",
                        f"{mv_kv:.0f} kV ring main unit · SF6/vacuum · IDMT O/C + E/F"))
        s.append(_wire(_COL, y + 9, _COL, _BUS_Y, color=_MV))

        # ---- inverter-station boundary + repeat tag ----------------------------
        # Boundary top clears the PV symbol's incident-light arrows (y ~ 74);
        # its caption sits ABOVE the boundary so it cannot collide with them.
        s.append(f'<rect x="{_COL-150:.0f}" y="68" width="640" height="652" rx="10" '
                 f'fill="none" stroke="{_GHOST}" stroke-width="1" stroke-dasharray="5 5"/>')
        s.append(_t(_COL - 150, 62, "ONE INVERTER STATION (typical)",
                    fill=_DIM, size=10, weight="700"))
        if n_inv:
            s.append(_tag(_COL - 26, 770, f"×{n_inv:,} stations"))

        # ---- ghost feeders: the remaining identical stations --------------------
        # Drawn BELOW the boundary (y > 720) so the caption reads as annotation
        # on the busbar, not as part of the typical station.
        for gx in (_COL + 300, _COL + 400, _COL + 500):
            s.append(_wire(gx, 736, gx, _BUS_Y, color=_GHOST, dash="4 4"))
            s.append(_sym_breaker(gx, 786, color=_GHOST))
            s.append(f'<circle cx="{gx:.0f}" cy="{730:.0f}" r="2" fill="{_GHOST}"/>')
        s.append(_t(_COL + 522, 760, "identical inverter stations",
                    fill=_GHOST, size=10))

        # ---- MV collection busbar ------------------------------------------------
        s.append(_wire(_BUS_X0, _BUS_Y, _BUS_X1, _BUS_Y, color=_MV, width=5))
        s.append(_t(_BUS_X0, _BUS_Y + 26, f"MV COLLECTION BUSBAR — {mv_kv:.0f} kV",
                    fill=_MV, size=11, weight="700"))

        # ---- main substation: metering -> main breaker -> POI ---------------------
        rx = 960
        s.append(_wire(_BUS_X1, _BUS_Y, rx, _BUS_Y, color=_MV, width=2.4))
        s.append(_wire(rx, _BUS_Y, rx, 700, color=_MV, width=2.4))
        s.append(_sym_meter(rx, 668))
        s.append(_wire(rx, 656, rx, 620, color=_MV, width=2.4))
        s.append(_sym_breaker(rx, 606, color=_MV))
        s.append(_wire(rx, 597, rx, 560, color=_MV, width=2.4))
        s.append(_sym_grid(rx, 520))
        s.append(_t(rx, 470, "GRID POI", fill=_MV, size=12, weight="700", anchor="middle"))
        s.append(_t(rx, 486, f"{poi_kv:.0f} kV · {ac_mw:,.1f} MW export",
                    fill=_DIM, size=10, anchor="middle"))
        s.append(_t(rx + 26, 672, "Revenue metering CT/VT", fill=_DIM, size=10))
        s.append(_t(rx + 26, 610, "Main incomer CB", fill=_DIM, size=10))

        # ---- earthing symbol on the busbar ----------------------------------------
        ex = _BUS_X0 + 40
        s.append(_wire(ex, _BUS_Y, ex, _BUS_Y + 44, color=_LINE, width=1.4))
        for i, hw in enumerate((14, 9, 4)):
            yy = _BUS_Y + 44 + i * 5
            s.append(_wire(ex - hw, yy, ex + hw, yy, color=_LINE, width=1.4))
        s.append(_t(ex + 22, _BUS_Y + 58, "Solidly/impedance earthed neutral",
                    fill=_DIM, size=10))

        s.append("</svg>")
        return "".join(s)
    except Exception:
        # Never break the page: the template falls back to the stage cards.
        return ""
