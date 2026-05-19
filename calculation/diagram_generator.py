# calculation/diagram_generator.py
# Generates inline SVG diagrams for the Installation Method HTML Report.
# Uses only Python standard library — no external dependencies.

# ── Colour palette ────────────────────────────────────────────────────────────
BG     = "#12121f"
PANEL  = "#1c1c30"
BOX    = "#222242"
ORANGE = "#f5a623"
BLUE   = "#4fc3f7"
GREEN  = "#66bb6a"
TEAL   = "#4db6ac"
GREY   = "#607585"
YELLOW = "#ffd54f"
RED    = "#ef5350"
WHITE  = "#dde3ec"
DIM    = "#505075"
BORD   = "#3a3a5c"
LGREY  = "#9aacbc"

# ── Arrow marker defs (embedded once per diagram) ─────────────────────────────
DEFS = """\
<defs>
  <marker id="aw" viewBox="0 0 8 6" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0,0 8,3 0,6" fill="#dde3ec"/></marker>
  <marker id="ao" viewBox="0 0 8 6" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0,0 8,3 0,6" fill="#f5a623"/></marker>
  <marker id="ab" viewBox="0 0 8 6" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0,0 8,3 0,6" fill="#4fc3f7"/></marker>
  <marker id="ag" viewBox="0 0 8 6" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0,0 8,3 0,6" fill="#66bb6a"/></marker>
  <marker id="at" viewBox="0 0 8 6" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0,0 8,3 0,6" fill="#4db6ac"/></marker>
  <marker id="ay" viewBox="0 0 8 6" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0,0 8,3 0,6" fill="#ffd54f"/></marker>
</defs>"""

# ── SVG primitives ────────────────────────────────────────────────────────────

def _svg(w, h, *parts):
    body = "\n  ".join(p for p in parts if p)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" style="max-width:100%;height:auto;display:block;margin:12px auto">\n'
            f'  {DEFS}\n'
            f'  <rect width="{w}" height="{h}" fill="{BG}" rx="10"/>\n'
            f'  {body}\n</svg>')


def _r(x, y, w, h, fill=BOX, stroke=BORD, rx=5, sw=1.5, opacity=1, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"{d}/>')


def _t(x, y, s, sz=12, fill=WHITE, anchor="middle", bold=False, italic=False):
    fw = "bold" if bold else "normal"
    fi = "italic" if italic else "normal"
    return (f'<text x="{x}" y="{y}" font-size="{sz}" fill="{fill}" '
            f'text-anchor="{anchor}" font-weight="{fw}" font-style="{fi}" '
            f'font-family="Segoe UI,Arial,sans-serif">{s}</text>')


def _l(x1, y1, x2, y2, stroke=WHITE, sw=2, dash="", m_end=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    m = f' marker-end="url(#{m_end})"' if m_end else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{sw}"{d}{m}/>'


def _c(cx, cy, r, fill=BOX, stroke=BORD, sw=1.5):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def _poly(pts, fill="none", stroke=WHITE, sw=2):
    p = " ".join(f"{x},{y}" for x, y in pts)
    return f'<polyline points="{p}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def _arrow(x1, y1, x2, y2, color=WHITE, sw=2, label="", lsz=10):
    mk = {ORANGE: "ao", BLUE: "ab", GREEN: "ag", TEAL: "at", YELLOW: "ay"}.get(color, "aw")
    els = [_l(x1, y1, x2, y2, color, sw, m_end=mk)]
    if label:
        mx, my = (x1 + x2) // 2, (y1 + y2) // 2
        off_x = 10 if y1 != y2 else 0
        off_y = -8 if y1 == y2 else 0
        els.append(_t(mx + off_x, my + off_y, label, lsz, color,
                      anchor="start" if y1 != y2 else "middle"))
    return "\n".join(els)


def _box(x, y, w, h, title, lines=(), fill=BOX, stroke=BORD, tc=ORANGE, lc=LGREY):
    els = [_r(x, y, w, h, fill=fill, stroke=stroke, rx=6, sw=2)]
    els.append(_t(x + w // 2, y + 20, title, 12, tc, bold=True))
    for i, ln in enumerate(lines):
        els.append(_t(x + w // 2, y + 36 + i * 16, ln, 10, lc))
    return "\n".join(els)


def _badge(x, y, w, h, label, color=YELLOW):
    return "\n".join([
        _r(x, y, w, h, fill=PANEL, stroke=color, rx=3, sw=1.5),
        _t(x + w // 2, y + h // 2 + 4, label, 10, color),
    ])


def _legend(x, y, items):
    """items = [(color, dash, label), ...]"""
    rows = [_r(x, y, 110, 16 + len(items) * 18, PANEL, BORD, rx=4, sw=1)]
    rows.append(_t(x + 55, y + 12, "LEGEND", 9, DIM, bold=True))
    for i, (col, dash, lbl) in enumerate(items):
        ry = y + 22 + i * 18
        rows.append(_l(x + 8, ry, x + 32, ry, col, 2, dash=dash))
        rows.append(_t(x + 36, ry + 4, lbl, 9, col, anchor="start"))
    return "\n".join(rows)


# ── Diagram 1 — System Architecture ──────────────────────────────────────────

def system_architecture_svg(pv_kw, num_panels, battery_kwh, num_batteries, inverter_kw):
    W, H = 820, 520

    # Box positions: (x, y, w, h)
    PV  = (25,  100, 115, 220)
    CB  = (205, 155, 110,  95)
    INV = (380,  70, 150, 260)
    ACB = (598, 105, 130, 145)
    BAT = (380, 380, 150, 105)
    LD  = (598, 320, 130, 155)

    pv_box = _box(*PV,  "PV ARRAY",
                  [f"{pv_kw:.2f} kWp", f"{num_panels} × 400 Wp", "Monocrystalline"],
                  fill=BOX, stroke=ORANGE)

    # Mini panel icons inside PV box
    panels_svg = "\n".join(
        "\n".join([
            _r(PV[0]+10, PV[1]+58+i*48, 95, 34, fill="#182838", stroke=BLUE, rx=3, sw=1),
            _l(PV[0]+42, PV[1]+58+i*48, PV[0]+42, PV[1]+92+i*48, BLUE, 0.5),
            _l(PV[0]+74, PV[1]+58+i*48, PV[0]+74, PV[1]+92+i*48, BLUE, 0.5),
            _l(PV[0]+10, PV[1]+75+i*48, PV[0]+105, PV[1]+75+i*48, BLUE, 0.5),
        ]) for i in range(3)
    )

    cb_box  = _box(*CB,  "DC COMBINER", ["String Box", "Fuses + SPD"],
                   fill=BOX, stroke=YELLOW)
    inv_box = _box(*INV, "HYBRID INVERTER",
                   [f"{inverter_kw:.2f} kW", "MPPT Charger", "Bat Charger",
                    "DC/AC Inverter", "230 V  50 Hz"],
                   fill=BOX, stroke=ORANGE)
    acb_box = _box(*ACB, "AC BOARD",
                   ["MCB + RCCB", "30 mA RCD", "Type II SPD"],
                   fill=BOX, stroke=BLUE)
    bat_box = _box(*BAT, "BATTERY BANK",
                   [f"{battery_kwh:.2f} kWh",
                    f"{num_batteries} × 2.4 kWh", "LiFePO4  48 V"],
                   fill=BOX, stroke=TEAL)
    ld_box  = _box(*LD,  "LOADS",
                   ["Lighting", "Socket Outlets", "AC / HVAC"],
                   fill=BOX, stroke=BLUE)

    # Arrows
    mid_row = PV[1] + PV[3] // 2          # ≈ 210
    a_pv_cb  = _arrow(PV[0]+PV[2], mid_row,     CB[0],          mid_row, ORANGE, 2, "DC 6mm²")
    a_cb_inv = _arrow(CB[0]+CB[2], mid_row+5,   INV[0],         mid_row+5, ORANGE, 2)
    a_inv_ac = _arrow(INV[0]+INV[2], mid_row,   ACB[0],         mid_row, BLUE, 2, "AC 10mm²")

    bat_mid_x = BAT[0] + BAT[2] // 2
    a_chg  = _arrow(bat_mid_x+14, INV[1]+INV[3], bat_mid_x+14, BAT[1], ORANGE, 2)
    a_dchg = _arrow(bat_mid_x-14, BAT[1],         bat_mid_x-14, INV[1]+INV[3], TEAL, 2)
    chg_l  = _t(bat_mid_x+22, (INV[1]+INV[3]+BAT[1])//2, "Charge",    9, ORANGE, anchor="start")
    dchg_l = _t(bat_mid_x-22, (INV[1]+INV[3]+BAT[1])//2, "Discharge", 9, TEAL,   anchor="end")

    ac_mid_x = ACB[0] + ACB[2] // 2
    a_ac_ld  = _arrow(ac_mid_x, ACB[1]+ACB[3], ac_mid_x, LD[1], BLUE, 2)

    # Earth dashed bus
    e_inv_x = INV[0] + 10
    e_acb_x = ACB[0] + 10
    e_y     = H - 28
    earth = "\n".join([
        _l(e_inv_x, INV[1]+INV[3], e_inv_x, e_y, GREEN, 1.5, dash="5,3"),
        _l(e_acb_x, ACB[1]+ACB[3], e_acb_x, e_y, GREEN, 1.5, dash="5,3"),
        _l(e_inv_x, e_y,           e_acb_x, e_y, GREEN, 1.5, dash="5,3"),
        _t((e_inv_x+e_acb_x)//2, e_y+14, "PE — Protective Earth Bus", 9, GREEN),
    ])

    title = _t(W//2, 42, "OVERALL SYSTEM ARCHITECTURE — POWER FLOW", 14, ORANGE, bold=True)
    leg = _legend(700, 390, [
        (ORANGE, "",    "DC + / PV"),
        (GREY,   "",    "DC −"),
        (BLUE,   "",    "AC supply"),
        (TEAL,   "",    "Battery"),
        (GREEN,  "5,3", "Earth PE"),
    ])

    return _svg(W, H, title, pv_box, panels_svg, cb_box, inv_box, acb_box, bat_box, ld_box,
                a_pv_cb, a_cb_inv, a_inv_ac,
                a_chg, a_dchg, chg_l, dchg_l, a_ac_ld,
                earth, leg)


# ── Diagram 2 — Mounting Structure Cross-Section ──────────────────────────────

def mounting_structure_svg():
    W, H = 780, 400

    title = _t(W//2, 32, "MOUNTING STRUCTURE — ROOF CROSS-SECTION", 14, ORANGE, bold=True)

    # Roof slope surface (left low, right high — represents tilted roof)
    roof_y_l, roof_y_r = 250, 150   # left lower, right higher
    roof_pts = [(60, roof_y_l), (700, roof_y_r)]
    roof_line = _l(60, roof_y_l, 700, roof_y_r, LGREY, 3)
    # Roof fill (shaded area below)
    roof_fill = (f'<polygon points="60,{roof_y_l} 700,{roof_y_r} 700,{H-20} 60,{H-20}" '
                 f'fill="#1a1a28" stroke="none"/>')
    roof_label = _t(380, roof_y_l + 30, "ROOF SURFACE  (10°–15° tilt)", 10, DIM, italic=True)

    # ── One mounting assembly at x≈280 ──
    # Rafter: from (260, roof_y_at_260+20) down to (280, H-40)
    # Roof surface y at x=280: lerp between (60,250) and (700,150)
    def roof_y(x):
        return int(roof_y_l + (roof_y_r - roof_y_l) * (x - 60) / (700 - 60))

    MX = 280          # mounting x
    RY = roof_y(MX)   # surface y at MX

    # Rafter (wooden beam, behind roof)
    rafter = "\n".join([
        _r(MX-8, RY+8, 18, 90, fill="#3a2a1a", stroke="#806040", rx=3, sw=1.5),
        _t(MX, RY+110, "Rafter", 9, "#806040"),
    ])

    # L-foot bracket
    bracket = "\n".join([
        _r(MX-6, RY-18, 14, 20, fill="#404060", stroke=LGREY, rx=2, sw=1.5),
        _t(MX, RY-26, "L-Foot + Gasket", 9, LGREY),
    ])

    # Aluminium rail (horizontal)
    rail_y = RY - 32
    rail = "\n".join([
        _r(MX-80, rail_y-6, 200, 14, fill="#505080", stroke=LGREY, rx=3, sw=1.5),
        _t(MX+60, rail_y-14, "Aluminium Rail", 9, LGREY),
    ])

    # Mid-clamps on rail
    clamps = "\n".join([
        _r(MX-30, rail_y-9, 10, 20, fill="#707090", stroke=LGREY, rx=1, sw=1),
        _r(MX+22, rail_y-9, 10, 20, fill="#707090", stroke=LGREY, rx=1, sw=1),
    ])

    # Panel 1 (left of mid-clamp)
    pnl1_x = MX - 90
    pnl1_y = rail_y - 38
    panel1 = "\n".join([
        _r(pnl1_x, pnl1_y, 86, 36, fill="#1a2838", stroke=BLUE, rx=3, sw=1.5),
        _l(pnl1_x+28, pnl1_y, pnl1_x+28, pnl1_y+36, BLUE, 0.5),
        _l(pnl1_x+57, pnl1_y, pnl1_x+57, pnl1_y+36, BLUE, 0.5),
        _l(pnl1_x, pnl1_y+18, pnl1_x+86, pnl1_y+18, BLUE, 0.5),
        _t(pnl1_x+43, pnl1_y-8, "PV Module  400 Wp", 9, BLUE),
    ])

    # Panel 2 (right)
    pnl2_x = MX + 36
    panel2 = "\n".join([
        _r(pnl2_x, pnl1_y, 86, 36, fill="#1a2838", stroke=BLUE, rx=3, sw=1.5),
        _l(pnl2_x+28, pnl1_y, pnl2_x+28, pnl1_y+36, BLUE, 0.5),
        _l(pnl2_x+57, pnl1_y, pnl2_x+57, pnl1_y+36, BLUE, 0.5),
        _l(pnl2_x, pnl1_y+18, pnl2_x+86, pnl1_y+18, BLUE, 0.5),
    ])

    # Earth bonding lug on rail
    earth_lug = "\n".join([
        _c(MX + 100, rail_y, 5, fill=GREEN, stroke=GREEN, sw=1),
        _l(MX+100, rail_y, MX+100, RY+80, GREEN, 1.5, dash="4,3"),
        _t(MX+112, rail_y+40, "Earth Bond", 9, GREEN, anchor="start"),
    ])

    # MC4 cable drooping from panel
    mc4 = "\n".join([
        _c(pnl1_x+43, pnl1_y+36, 4, fill=ORANGE, stroke=ORANGE, sw=1),
        _l(pnl1_x+43, pnl1_y+40, pnl1_x+43, pnl1_y+60, ORANGE, 1.5),
        _t(pnl1_x+52, pnl1_y+54, "MC4", 8, ORANGE, anchor="start"),
    ])

    # Callout arrows
    callouts = "\n".join([
        _arrow(pnl1_x + 43, pnl1_y - 20, pnl1_x + 43, pnl1_y, WHITE, 1.5),
        _t(pnl1_x + 43, pnl1_y - 26, "Module frame & glass", 9, LGREY),
    ])

    # Tilt angle arc annotation
    angle_note = "\n".join([
        _t(130, roof_y_l + 18, "10°–15°", 11, YELLOW, bold=True),
        _t(130, roof_y_l + 32, "tilt", 9, YELLOW),
    ])

    return _svg(W, H, title, roof_fill, roof_line, roof_label,
                rafter, bracket, rail, clamps, panel1, panel2,
                earth_lug, mc4, callouts, angle_note)


# ── Diagram 3 — PV String Wiring ──────────────────────────────────────────────

def string_wiring_svg(num_panels, string_a, string_b):
    W = 820
    H = 360

    title = _t(W//2, 30, f"PV STRING WIRING  ({num_panels} MODULES — 2 STRINGS)", 14, ORANGE, bold=True)

    MAX_SHOW = 5   # max panels to draw per string before truncation
    CELL_W = 90
    GAP    = 14
    PH     = 52    # panel height

    def _string_row(panels, ry, label, label_color):
        show  = min(panels, MAX_SHOW)
        trunc = panels > MAX_SHOW
        total_w = show * CELL_W + (show - 1) * GAP + (60 if trunc else 0)
        start_x = (W - 120 - total_w) // 2 + 20
        els = [_t(start_x - 12, ry - 14, label, 11, label_color, bold=True, anchor="start")]

        px = start_x
        for i in range(show):
            # panel rect
            els += [
                _r(px, ry, CELL_W, PH, fill="#182838", stroke=BLUE, rx=4, sw=1.5),
                _l(px+30, ry, px+30, ry+PH, BLUE, 0.5),
                _l(px+60, ry, px+60, ry+PH, BLUE, 0.5),
                _l(px, ry+26, px+CELL_W, ry+26, BLUE, 0.5),
                _t(px + CELL_W//2, ry + PH + 14, f"P{i+1}", 9, DIM),
            ]
            # + terminal (left) and – terminal (right)
            els += [
                _c(px,          ry + PH//2, 6, fill=ORANGE, stroke=ORANGE, sw=1),
                _c(px + CELL_W, ry + PH//2, 6, fill=GREY,   stroke=GREY,   sw=1),
            ]
            # Connecting wire to next panel
            if i < show - 1:
                nx = px + CELL_W + GAP
                els.append(_l(px + CELL_W, ry + PH//2, nx, ry + PH//2, WHITE, 1.5))
            px += CELL_W + GAP

        # Truncation dots
        if trunc:
            els.append(_t(px + 10, ry + PH//2 + 4, f"… +{panels-show} more", 10, DIM))
            px += 60

        # String output to combiner
        out_x = start_x + total_w
        els.append(_l(px - GAP - CELL_W, ry + PH//2, out_x - 10, ry + PH//2, ORANGE, 1.5))

        return "\n".join(els), out_x, ry + PH//2

    str_a_svg, ax, ay = _string_row(string_a, 80,  f"String A  ({string_a} panels in series)", ORANGE)
    str_b_svg, bx, by = _string_row(string_b, 210, f"String B  ({string_b} panels in series)", YELLOW)

    # Combiner box on right
    CB_X = max(ax, bx) + 30
    CB_Y = 70
    CB_W = 120
    CB_H = 210
    comb_box = _box(CB_X, CB_Y, CB_W, CB_H, "DC COMBINER",
                    ["String A fuse", "String B fuse", "SPD", "DC MCBs", "→ Inverter"],
                    fill=BOX, stroke=YELLOW, tc=YELLOW)

    # Lines from string outputs to combiner
    mid_y = CB_Y + CB_H // 2
    con_a = "\n".join([
        _arrow(ax, ay, CB_X, CB_Y + 60, ORANGE, 2),
    ])
    con_b = "\n".join([
        _arrow(bx, by, CB_X, CB_Y + 120, YELLOW, 2),
    ])

    # Polarity labels
    pol = "\n".join([
        _t(50, ay + 4, "(+)", 10, ORANGE, anchor="start"),
        _t(50, by + 4, "(+)", 10, YELLOW, anchor="start"),
    ])

    # MC4 detail callout
    mc4_detail = "\n".join([
        _r(30, 290, 260, 55, fill=PANEL, stroke=BORD, rx=4, sw=1),
        _t(160, 306, "MC4 CONNECTOR DETAIL", 9, DIM, bold=True),
        _c(80,  325, 7, fill=PANEL, stroke=ORANGE, sw=2),
        _c(110, 325, 7, fill=ORANGE, stroke=ORANGE, sw=1),
        _l(87, 325, 103, 325, ORANGE, 2),
        _t(95, 338, "Male (+)", 8, ORANGE),
        _c(170, 325, 7, fill=PANEL, stroke=GREY, sw=2),
        _c(200, 325, 7, fill=GREY,   stroke=GREY,   sw=1),
        _l(177, 325, 193, 325, GREY, 2),
        _t(185, 338, "Female (−)", 8, GREY),
        _t(155, 305, "Lock with MC4 spanner until audible click", 8, DIM),
    ])

    return _svg(W, H, title, str_a_svg, str_b_svg, comb_box, con_a, con_b, pol, mc4_detail)


# ── Diagram 4 — DC Combiner Box Internal Wiring ───────────────────────────────

def combiner_box_svg():
    W, H = 700, 420

    title = _t(W//2, 30, "DC COMBINER BOX — INTERNAL WIRING", 14, ORANGE, bold=True)

    # Outer enclosure
    enc = _r(60, 55, 580, 320, fill=PANEL, stroke=YELLOW, rx=8, sw=2.5)
    enc_label = _t(W//2, 75, "IP65 Weatherproof Enclosure", 9, DIM, italic=True)

    # Cable entries (left side)
    ce1 = _r(55, 120, 12, 30, fill=GREY, stroke=LGREY, rx=2, sw=1)
    ce2 = _r(55, 200, 12, 30, fill=GREY, stroke=LGREY, rx=2, sw=1)
    ce3 = _r(55, 290, 12, 14, fill=GREEN, stroke=GREEN, rx=2, sw=1)
    # Cable entry (right side — DC output)
    ce4 = _r(633, 195, 12, 30, fill=ORANGE, stroke=ORANGE, rx=2, sw=1)
    cet1 = _t(42, 140, "Str A", 8, ORANGE, anchor="end")
    cet2 = _t(42, 220, "Str B", 8, YELLOW, anchor="end")
    cet3 = _t(42, 300, "Earth", 8, GREEN,  anchor="end")
    cet4 = _t(650, 215, "DC Out", 8, ORANGE, anchor="start")

    # Fuses
    fs1 = _badge(140, 115, 60, 28, "Fuse 15A", ORANGE)
    fs2 = _badge(140, 195, 60, 28, "Fuse 15A", YELLOW)
    ft1 = _t(170, 105, "String A", 9, ORANGE)
    ft2 = _t(170, 185, "String B", 9, YELLOW)

    # Positive busbar
    pb_x, pb_y, pb_w, pb_h = 250, 108, 260, 16
    pos_bus = "\n".join([
        _r(pb_x, pb_y, pb_w, pb_h, fill="#3a2800", stroke=ORANGE, rx=3, sw=2),
        _t(pb_x + pb_w//2, pb_y + 11, "(+) POSITIVE BUSBAR", 9, ORANGE, bold=True),
    ])

    # Negative busbar
    nb_x, nb_y, nb_w, nb_h = 250, 208, 260, 16
    neg_bus = "\n".join([
        _r(nb_x, nb_y, nb_w, nb_h, fill="#1a1a1a", stroke=GREY, rx=3, sw=2),
        _t(nb_x + nb_w//2, nb_y + 11, "(−) NEGATIVE BUSBAR", 9, GREY, bold=True),
    ])

    # SPD between busbars
    spd_x, spd_y = 390, 140
    spd = "\n".join([
        _r(spd_x, spd_y, 50, 68, fill=BOX, stroke=RED, rx=4, sw=2),
        _t(spd_x + 25, spd_y + 14, "SPD", 10, RED, bold=True),
        _t(spd_x + 25, spd_y + 28, "Type II", 8, RED),
        _t(spd_x + 25, spd_y + 42, "BS EN", 8, DIM),
        _t(spd_x + 25, spd_y + 56, "61643", 8, DIM),
        _l(spd_x + 25, spd_y,      spd_x + 25, pb_y + pb_h, RED, 1.5),
        _l(spd_x + 25, spd_y+68,   spd_x + 25, nb_y, RED, 1.5),
    ])

    # DC MCB (at output, before cable exit)
    mcb_x, mcb_y = 480, 145
    mcb = "\n".join([
        _r(mcb_x, mcb_y, 48, 58, fill=BOX, stroke=ORANGE, rx=4, sw=2),
        _t(mcb_x + 24, mcb_y + 14, "DC MCB", 9, ORANGE, bold=True),
        _t(mcb_x + 24, mcb_y + 28, "63A", 9, LGREY),
        _t(mcb_x + 24, mcb_y + 42, "500 V DC", 8, DIM),
    ])

    # Connecting wires
    wires = "\n".join([
        # Fuse A output → positive bus
        _l(200, 129, 250, 116, ORANGE, 1.5),
        # String A input → Fuse A
        _l(67, 135, 140, 129, ORANGE, 1.5),
        # Fuse B output → positive bus
        _l(200, 209, 250, 216, YELLOW, 1.5),
        # String B input → Fuse B
        _l(67, 215, 140, 209, YELLOW, 1.5),
        # Neg bus ← string A neg
        _l(67, 240, 250, 216, GREY, 1.5),
        # Neg bus ← string B neg
        _l(67, 260, 250, 224, GREY, 1.5),
        # Positive bus → MCB in
        _l(510, 116, mcb_x + 24, mcb_y, ORANGE, 1.5),
        # MCB out → output terminal
        _l(mcb_x + 24, mcb_y+58, mcb_x + 24, nb_y + 8, ORANGE, 1.5),
        # Neg bus → output
        _l(510, 216, 633, 210, GREY, 1.5),
        # Earth
        _l(67, 297, 350, 297, GREEN, 1.5, dash="4,3"),
        _l(350, 297, spd_x+25, spd_y+68+10, GREEN, 1.5, dash="4,3"),
    ])

    # Status window on SPD
    spd_window = "\n".join([
        _c(spd_x + 25, spd_y + 58, 5, fill=GREEN, stroke=GREEN, sw=1),
        _t(spd_x + 35, spd_y + 62, "OK", 7, GREEN, anchor="start"),
    ])

    return _svg(W, H, title, enc, enc_label,
                ce1, ce2, ce3, ce4, cet1, cet2, cet3, cet4,
                pos_bus, neg_bus, spd, spd_window, mcb,
                fs1, fs2, ft1, ft2, wires)


# ── Diagram 5 — Inverter Terminal Connections ─────────────────────────────────

def inverter_connections_svg(inverter_kw):
    W, H = 740, 480

    title = _t(W//2, 30, "HYBRID INVERTER — TERMINAL CONNECTION DIAGRAM", 14, ORANGE, bold=True)

    # Central inverter body
    IV_X, IV_Y, IV_W, IV_H = 220, 80, 300, 300
    inv_body = "\n".join([
        _r(IV_X, IV_Y, IV_W, IV_H, fill=BOX, stroke=ORANGE, rx=8, sw=2.5),
        _t(IV_X + IV_W//2, IV_Y + 22, "HYBRID INVERTER", 13, ORANGE, bold=True),
        _t(IV_X + IV_W//2, IV_Y + 40, f"{inverter_kw:.2f} kW  415/230V  50 Hz", 10, LGREY),
        # Internal zone labels
        _r(IV_X+16, IV_Y+54, IV_W-32, 44, fill=PANEL, stroke=BORD, rx=4, sw=1),
        _t(IV_X + IV_W//2, IV_Y + 74, "MPPT SOLAR CHARGE CONTROLLER", 9, BLUE, bold=True),
        _t(IV_X + IV_W//2, IV_Y + 88, "DC Input 60–150 V  /  Max PV Current", 8, DIM),
        _r(IV_X+16, IV_Y+106, IV_W-32, 44, fill=PANEL, stroke=BORD, rx=4, sw=1),
        _t(IV_X + IV_W//2, IV_Y + 126, "BATTERY CHARGER", 9, TEAL, bold=True),
        _t(IV_X + IV_W//2, IV_Y + 140, "48 V DC  /  Constant Current/Voltage", 8, DIM),
        _r(IV_X+16, IV_Y+158, IV_W-32, 44, fill=PANEL, stroke=BORD, rx=4, sw=1),
        _t(IV_X + IV_W//2, IV_Y + 178, "DC / AC INVERTER", 9, BLUE, bold=True),
        _t(IV_X + IV_W//2, IV_Y + 192, "Pure Sine Wave  /  ≥ 95% Efficiency", 8, DIM),
        _r(IV_X+16, IV_Y+210, IV_W-32, 44, fill=PANEL, stroke=BORD, rx=4, sw=1),
        _t(IV_X + IV_W//2, IV_Y + 230, "AUTO TRANSFER SWITCH", 9, YELLOW, bold=True),
        _t(IV_X + IV_W//2, IV_Y + 244, "Grid / Generator / Battery priority", 8, DIM),
        # Bottom
        _t(IV_X + IV_W//2, IV_Y + 285, "LCD Display  ·  BMS Port  ·  RS485", 9, DIM),
    ])

    # ── PV DC Input (top) ──
    pv_x = IV_X + 60
    pv_term = "\n".join([
        _r(pv_x,    IV_Y-40, 24, 40, fill="#2a1800", stroke=ORANGE, rx=3, sw=1.5),
        _r(pv_x+40, IV_Y-40, 24, 40, fill="#1a1a1a", stroke=GREY,   rx=3, sw=1.5),
        _t(pv_x+12, IV_Y-44, "(+)", 9, ORANGE), _t(pv_x+52, IV_Y-44, "(−)", 9, GREY),
        _t(pv_x+20, IV_Y-54, "PV DC INPUT", 10, ORANGE, bold=True),
        # Cables coming from top
        _arrow(pv_x+12,  IV_Y-90, pv_x+12,  IV_Y-40, ORANGE, 2, "From Combiner"),
        _arrow(pv_x+52,  IV_Y-90, pv_x+52,  IV_Y-40, GREY,   2),
    ])

    # ── Battery Terminals (left) ──
    bat_y = IV_Y + 140
    bat_term = "\n".join([
        _r(IV_X-45, bat_y,    40, 24, fill="#2a1800", stroke=TEAL, rx=3, sw=1.5),
        _r(IV_X-45, bat_y+36, 40, 24, fill="#1a1a1a", stroke=GREY, rx=3, sw=1.5),
        _t(IV_X-25, bat_y+12,    "BAT(+)", 9, TEAL),
        _t(IV_X-25, bat_y+48,    "BAT(−)", 9, GREY),
        _t(IV_X-25, bat_y-12,    "BATTERY", 10, TEAL, bold=True),
        # Cables to left
        _arrow(IV_X-130, bat_y+12,    IV_X-45, bat_y+12,    TEAL, 2, "16mm²"),
        _arrow(IV_X-130, bat_y+48,    IV_X-45, bat_y+48,    GREY, 2),
        _t(IV_X-145, bat_y+12, "BAT+", 9, TEAL,  anchor="end"),
        _t(IV_X-145, bat_y+48, "BAT−", 9, GREY,  anchor="end"),
    ])

    # ── AC Output Terminals (right) ──
    ac_y = IV_Y + 110
    ac_term = "\n".join([
        _r(IV_X+IV_W+5, ac_y,    40, 24, fill="#182030", stroke=BLUE, rx=3, sw=1.5),
        _r(IV_X+IV_W+5, ac_y+34, 40, 24, fill="#182030", stroke=LGREY, rx=3, sw=1.5),
        _r(IV_X+IV_W+5, ac_y+68, 40, 24, fill="#182030", stroke=GREEN, rx=3, sw=1.5),
        _t(IV_X+IV_W+25, ac_y+12,    "L",  10, BLUE,  bold=True),
        _t(IV_X+IV_W+25, ac_y+46,    "N",  10, LGREY, bold=True),
        _t(IV_X+IV_W+25, ac_y+80,    "PE", 10, GREEN, bold=True),
        _t(IV_X+IV_W+25, ac_y-12, "AC OUTPUT", 10, BLUE, bold=True),
        # Cables to right
        _arrow(IV_X+IV_W+45, ac_y+12, IV_X+IV_W+150, ac_y+12, BLUE,  2, "10mm²"),
        _arrow(IV_X+IV_W+45, ac_y+46, IV_X+IV_W+150, ac_y+46, WHITE, 2),
        _arrow(IV_X+IV_W+45, ac_y+80, IV_X+IV_W+150, ac_y+80, GREEN, 2),
        _t(IV_X+IV_W+160, ac_y+12, "→ AC Board L",  9, BLUE,  anchor="start"),
        _t(IV_X+IV_W+160, ac_y+46, "→ AC Board N",  9, LGREY, anchor="start"),
        _t(IV_X+IV_W+160, ac_y+80, "→ Earth Bar PE",9, GREEN, anchor="start"),
    ])

    # ── Grid Input (bottom, optional) ──
    gr_x = IV_X + 180
    grid_term = "\n".join([
        _r(gr_x, IV_Y+IV_H+5, 60, 30, fill=PANEL, stroke=DIM, rx=3, sw=1.5, dash="4,2"),
        _t(gr_x+30, IV_Y+IV_H+24, "GRID IN (opt.)", 9, DIM),
        _l(gr_x+30, IV_Y+IV_H+35, gr_x+30, IV_Y+IV_H+70, DIM, 1.5, dash="4,3"),
        _t(gr_x+30, IV_Y+IV_H+82, "Grid / Generator", 9, DIM),
    ])

    # Setting note
    note = "\n".join([
        _r(30, 400, 320, 60, fill=PANEL, stroke=BORD, rx=5, sw=1),
        _t(190, 415, "KEY SETTINGS AFTER POWER-ON", 9, YELLOW, bold=True),
        _t(190, 430, "Battery Type: LiFePO4  ·  Capacity: set to system kWh", 8, DIM),
        _t(190, 444, "Charge V: 58.4V  ·  Cut-off: 44V  ·  AC: 230V 50Hz", 8, DIM),
    ])

    return _svg(W, H, title, inv_body, pv_term, bat_term, ac_term, grid_term, note)


# ── Diagram 6 — Battery Parallel Bank ────────────────────────────────────────

def battery_bank_svg(num_batteries, battery_kwh):
    SHOW = min(num_batteries, 5)
    CELL_W = 100
    GAP    = 20
    BH     = 100
    TOTAL  = SHOW * CELL_W + (SHOW - 1) * GAP
    OFFSET = (640 - TOTAL) // 2
    W = 760
    H = 340

    title = _t(W//2, 30, f"BATTERY BANK — PARALLEL WIRING  ({num_batteries} × 2.4 kWh = {battery_kwh:.2f} kWh)", 13, ORANGE, bold=True)

    # Positive bus rail
    bus_y_pos = 72
    bus_y_neg = bus_y_pos + BH + 58
    pos_rail = "\n".join([
        _r(OFFSET - 15, bus_y_pos - 10, TOTAL + 30, 14, fill="#2a1800", stroke=ORANGE, rx=3, sw=2),
        _t(OFFSET + TOTAL//2, bus_y_pos, "(+) POSITIVE BUS — 48 V", 9, ORANGE, bold=True),
    ])
    neg_rail = "\n".join([
        _r(OFFSET - 15, bus_y_neg, TOTAL + 30, 14, fill="#1a1a1a", stroke=GREY, rx=3, sw=2),
        _t(OFFSET + TOTAL//2, bus_y_neg + 10, "(−) NEGATIVE BUS", 9, GREY, bold=True),
    ])

    # Battery cells
    cells = []
    for i in range(SHOW):
        bx = OFFSET + i * (CELL_W + GAP)
        by = bus_y_pos + 14
        trunc = (num_batteries > SHOW and i == SHOW - 1)

        cells += [
            _r(bx, by, CELL_W, BH, fill=BOX, stroke=TEAL, rx=5, sw=2),
            _t(bx + CELL_W//2, by + 16, "BATTERY", 9, TEAL, bold=True),
            _t(bx + CELL_W//2, by + 30, "2.4 kWh", 10, WHITE),
            _t(bx + CELL_W//2, by + 46, "LiFePO4", 9, LGREY),
            _t(bx + CELL_W//2, by + 60, "48 V DC", 9, LGREY),
            _t(bx + CELL_W//2, by + 76, "BMS", 9, GREEN),
            # Vertical connectors to bus
            _l(bx + CELL_W//2, by,           bx + CELL_W//2, bus_y_pos + 14, ORANGE, 2),
            _l(bx + CELL_W//2, by + BH,       bx + CELL_W//2, bus_y_neg,     GREY, 2),
            # Terminal circles
            _c(bx + CELL_W//2, by,       6, fill=ORANGE, stroke=ORANGE, sw=1),
            _c(bx + CELL_W//2, by + BH,  6, fill=GREY,   stroke=GREY,   sw=1),
        ]
        if trunc and num_batteries > SHOW:
            cells.append(_t(bx + CELL_W//2, by + BH + 22,
                             f"(+{num_batteries - SHOW} more)", 9, DIM))

    # Output connection to inverter (right side)
    out_x = OFFSET + TOTAL + 40
    out_conn = "\n".join([
        _arrow(OFFSET + TOTAL + 14, bus_y_pos + 7,    out_x + 60, bus_y_pos + 7,    ORANGE, 2, "→ INV BAT(+)"),
        _arrow(OFFSET + TOTAL + 14, bus_y_neg  + 7,   out_x + 60, bus_y_neg  + 7,   GREY,   2, "→ INV BAT(−)"),
        _t(out_x + 65, bus_y_pos + 7,  "16mm²  Red",   9, ORANGE, anchor="start"),
        _t(out_x + 65, bus_y_neg + 7,  "16mm²  Black", 9, GREY,   anchor="start"),
    ])

    # Note
    note = _t(W//2, H - 20,
               "Connect (−) first, then (+).  All units must be same SOC (±5%) before linking.",
               10, YELLOW)

    return _svg(W, H, title, pos_rail, neg_rail, *cells, out_conn, note)


# ── Diagram 7 — Earthing System ───────────────────────────────────────────────

def earthing_system_svg():
    W, H = 760, 500

    title = _t(W//2, 30, "EARTHING & BONDING SYSTEM  (BS 7430 / BS 7671)", 14, ORANGE, bold=True)

    # Ground level line
    GL = 330
    ground_line = "\n".join([
        _l(40, GL, W - 40, GL, LGREY, 2.5),
        _t(W//2, GL + 16, "GROUND LEVEL", 9, LGREY, italic=True),
        # Hatching
        "\n".join(
            _l(40 + i*18, GL, 40 + i*18 + 12, GL + 12, DIM, 1)
            for i in range(40)
        ),
    ])

    # Earth rod
    rod_x = 120
    rod = "\n".join([
        _r(rod_x - 5, GL, 10, 130, fill="#b07830", stroke="#d0a050", rx=2, sw=1.5),
        _t(rod_x, GL + 145, "Earth Rod", 9, "#d0a050"),
        _t(rod_x, GL + 158, "Cu-clad 14mm", 8, DIM),
        _t(rod_x, GL + 170, "≥ 1.2 m deep", 8, DIM),
        # Ground resistance annotation
        _r(rod_x - 35, GL + 60, 80, 28, fill=PANEL, stroke=GREEN, rx=3, sw=1),
        _t(rod_x, GL + 73, "R ≤ 5 Ω", 9, GREEN, bold=True),
        _t(rod_x, GL + 85, "target", 8, GREEN),
    ])

    # Main earth conductor (from rod to main earth bar)
    EB_X = 300
    earth_conductor = "\n".join([
        _l(rod_x, GL, rod_x, 280, GREEN, 2.5),
        _l(rod_x, 280, EB_X, 280, GREEN, 2.5),
        _t((rod_x + EB_X) // 2, 268, "10mm² green/yellow", 8, GREEN),
    ])

    # Main Earth Bar (in DB)
    EB_Y = 260
    earth_bar = "\n".join([
        _r(EB_X, EB_Y, 80, 36, fill="#1a3020", stroke=GREEN, rx=4, sw=2),
        _t(EB_X + 40, EB_Y + 13, "MAIN", 9, GREEN, bold=True),
        _t(EB_X + 40, EB_Y + 26, "EARTH BAR", 9, GREEN, bold=True),
    ])

    # Equipment boxes (building interior)
    equip = [
        (400, 130, 80, 50, "PV MODULE\nFRAMES",  BLUE,   "PV frames via rail bonding lug"),
        (500, 130, 80, 50, "DC COMBINER\nBOX",   YELLOW, "Enclosure earth stud"),
        (600, 130, 80, 50, "BATTERY\nRACK",       TEAL,   "Metal frame earth"),
        (400, 220, 80, 50, "HYBRID\nINVERTER",    ORANGE, "Chassis earth terminal"),
        (500, 220, 80, 50, "AC DIST.\nBOARD",     BLUE,   "Earth bar in DB"),
        (600, 220, 80, 50, "CABLE\nTRUNKING",     LGREY,  "Metal trunking earth continuity"),
    ]

    equip_svgs = []
    bond_lines = []
    for ex, ey, ew, eh, lbl, col, note in equip:
        lines_in_lbl = lbl.split("\n")
        equip_svgs += [
            _r(ex, ey, ew, eh, fill=BOX, stroke=col, rx=5, sw=1.5),
            _t(ex + ew//2, ey + 18, lines_in_lbl[0], 8, col, bold=True),
            _t(ex + ew//2, ey + 32, lines_in_lbl[1] if len(lines_in_lbl) > 1 else "", 8, col),
        ]
        # Bond line from equipment down/left to earth bar
        bond_lines.append(
            _l(ex + ew//2, ey + eh, ex + ew//2, EB_Y + 18, GREEN, 1.5, dash="5,3")
        )
        bond_lines.append(
            _l(ex + ew//2, EB_Y + 18, EB_X + 80, EB_Y + 18, GREEN, 1.5, dash="5,3")
        )

    # Test point annotation
    test_pt = "\n".join([
        _c(rod_x, GL - 5, 7, fill=PANEL, stroke=YELLOW, sw=2),
        _t(rod_x + 12, GL - 12, "Test point  (earth resistance test here)", 9, YELLOW, anchor="start"),
    ])

    # Building outline
    bldg = _r(370, 100, 350, 200, fill="none", stroke=BORD, rx=6, sw=1, dash="6,4")
    bldg_lbl = _t(545, 95, "BUILDING INTERIOR", 9, DIM, italic=True)

    return _svg(W, H, title, ground_line, rod, earth_conductor, earth_bar,
                bldg, bldg_lbl,
                *equip_svgs, *bond_lines, test_pt)


# ── Diagram 8 — AC Distribution Board ────────────────────────────────────────

def ac_distribution_board_svg():
    W, H = 680, 480

    title = _t(W//2, 30, "AC DISTRIBUTION BOARD — INTERNAL LAYOUT", 14, ORANGE, bold=True)

    # DB enclosure
    enc = _r(60, 55, 560, 380, fill=PANEL, stroke=BLUE, rx=8, sw=2.5)
    enc_lbl = _t(W//2, 72, "Consumer Unit / Distribution Board  (surface-mount, IP4X)", 9, DIM, italic=True)

    # DIN rail
    rail = "\n".join([
        _r(90, 95, 500, 8, fill="#404040", stroke=LGREY, rx=2, sw=1),
        _t(560, 95, "DIN Rail", 8, DIM, anchor="start"),
    ])

    # Incoming cable labels (left side)
    inc = "\n".join([
        _r(55, 120, 12, 26, fill=BLUE,  stroke=BLUE,  rx=2, sw=1),
        _r(55, 155, 12, 26, fill=LGREY, stroke=LGREY, rx=2, sw=1),
        _r(55, 190, 12, 26, fill=GREEN, stroke=GREEN, rx=2, sw=1),
        _t(50, 136, "L",  9, BLUE,  anchor="end"),
        _t(50, 171, "N",  9, LGREY, anchor="end"),
        _t(50, 206, "PE", 9, GREEN, anchor="end"),
        _t(45, 108, "FROM", 8, DIM, anchor="end"),
        _t(45, 118, "INVERTER", 8, DIM, anchor="end"),
    ])

    # RCCB
    rccb_x, rccb_y, rccb_w, rccb_h = 100, 100, 100, 140
    rccb = "\n".join([
        _r(rccb_x, rccb_y, rccb_w, rccb_h, fill=BOX, stroke=ORANGE, rx=6, sw=2.5),
        _t(rccb_x + rccb_w//2, rccb_y + 18, "RCCB", 13, ORANGE, bold=True),
        _t(rccb_x + rccb_w//2, rccb_y + 36, "30 mA", 10, LGREY),
        _t(rccb_x + rccb_w//2, rccb_y + 52, "2-Pole", 9, DIM),
        _t(rccb_x + rccb_w//2, rccb_y + 66, "BS EN", 9, DIM),
        _t(rccb_x + rccb_w//2, rccb_y + 80, "61008", 9, DIM),
        # TEST button
        _r(rccb_x+30, rccb_y+92, 40, 20, fill="#2a0000", stroke=RED, rx=3, sw=1.5),
        _t(rccb_x+50, rccb_y+105, "TEST", 8, RED, bold=True),
        _t(rccb_x + rccb_w//2, rccb_y + 130, "↑ test monthly", 8, DIM, italic=True),
    ])

    # MCBs
    mcb_labels = [
        ("MCB 1", "Lighting", "20A", "Type B"),
        ("MCB 2", "Sockets",  "32A", "Type B"),
        ("MCB 3", "Spare",    "20A", "Type B"),
    ]
    mcb_svgs = []
    for i, (title_m, circ, rating, typ) in enumerate(mcb_labels):
        mx = rccb_x + rccb_w + 20 + i * 80
        my = rccb_y
        mcb_svgs += [
            _r(mx, my, 72, rccb_h, fill=BOX, stroke=BLUE, rx=5, sw=2),
            _t(mx + 36, my + 18, title_m,  10, BLUE, bold=True),
            _t(mx + 36, my + 34, circ,     9, WHITE),
            _t(mx + 36, my + 50, rating,   10, LGREY, bold=True),
            _t(mx + 36, my + 65, typ,      8, DIM),
            _t(mx + 36, my + 80, "BS EN",  8, DIM),
            _t(mx + 36, my + 94, "60898",  8, DIM),
        ]

    # Neutral bar
    nb_y = 265
    n_bar = "\n".join([
        _r(90, nb_y, 500, 16, fill="#182030", stroke=LGREY, rx=3, sw=1.5),
        _t(340, nb_y + 10, "NEUTRAL BAR (N)", 9, LGREY, bold=True),
    ])

    # Earth bar
    eb_y = 305
    e_bar = "\n".join([
        _r(90, eb_y, 500, 16, fill="#0a2010", stroke=GREEN, rx=3, sw=1.5),
        _t(340, eb_y + 10, "EARTH BAR (PE)  →  to earth rod", 9, GREEN, bold=True),
    ])

    # Wiring from incoming to RCCB
    in_wires = "\n".join([
        _l(67,  133, rccb_x, 125, BLUE,  2),
        _l(67,  168, rccb_x, 158, LGREY, 1.5),
        _l(67,  203, 90, 310, GREEN, 1.5, dash="4,3"),
        # RCCB L out → MCB 1 in
        _l(rccb_x + rccb_w, 120, rccb_x + rccb_w + 20, 120, BLUE, 2),
        # RCCB N out → neutral bar
        _l(rccb_x + rccb_w//2, rccb_y + rccb_h, rccb_x + rccb_w//2, nb_y, LGREY, 1.5),
        # MCBs to neutral bar
        "\n".join(
            _l(rccb_x + rccb_w + 20 + i*80 + 36, rccb_y + rccb_h,
               rccb_x + rccb_w + 20 + i*80 + 36, nb_y, LGREY, 1)
            for i in range(3)
        ),
    ])

    # Circuit output labels (below MCBs)
    circuit_labels = "\n".join([
        _arrow(rccb_x + rccb_w + 20 + i*80 + 36, eb_y + 16,
               rccb_x + rccb_w + 20 + i*80 + 36, eb_y + 70, BLUE, 1.5)
        for i in range(3)
    ] + [
        _t(rccb_x + rccb_w + 20 + i*80 + 36, eb_y + 82,
           ["Lighting", "Sockets", "Spare"][i], 9, BLUE)
        for i in range(3)
    ])

    # Test note
    test_note = "\n".join([
        _r(90, 390, 500, 34, fill=PANEL, stroke=BORD, rx=4, sw=1),
        _t(340, 405, "After installation: press TEST button — RCCB must trip within 300 ms.", 9, YELLOW),
        _t(340, 420, "Use RCD tester to verify at 30 mA, 50 mA, 100 mA.  Reset and confirm hold.", 9, DIM),
    ])

    return _svg(W, H, title, enc, enc_lbl, rail, inc, rccb, *mcb_svgs,
                n_bar, e_bar, in_wires, circuit_labels, test_note)
