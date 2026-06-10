"""
pdf_diagrams.py - matplotlib renderers for the diagrams missing from PDF reports.

Each function returns a `data:image/png;base64,...` URI string so the diagram
embeds directly in markdown that's then fed to markdown-pdf. No file I/O, no
template path. Headless (`Agg`) backend for Render/CI.

Wired into PDF export routes (BOQ + Installation + Proposal). HTML reports
keep their JS/D3 diagrams; these are the print-quality static fallbacks.
"""

from __future__ import annotations
import base64
import io
import math

import matplotlib
matplotlib.use("Agg")  # headless server
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, FancyArrowPatch


def _fig_to_data_uri(fig, dpi=130):
    """Render a matplotlib figure to a base64 PNG data-URI."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _block(ax, x, y, w, h, label, color="#dbeafe", edge="#1e3a8a", text_color="#0f172a"):
    """Render a labelled rounded-rect block."""
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.1",
                       linewidth=1.6, edgecolor=edge, facecolor=color)
    ax.add_patch(p)
    ax.text(x + w/2, y + h/2, label, ha="center", va="center",
            fontsize=9.5, color=text_color, weight="bold")


def _arrow(ax, x1, y1, x2, y2, color="#374151", style="-|>"):
    """Render a directional connector."""
    a = FancyArrowPatch((x1, y1), (x2, y2),
                        arrowstyle=style, mutation_scale=14,
                        linewidth=1.4, color=color)
    ax.add_patch(a)


# ── Single Line Diagram ──────────────────────────────────────────────────────

def single_line_diagram_b64(pv_kw, inv_kw, bat_kwh, num_bat, mppt_a,
                            chemistry="LiFePO4", system_type="hybrid"):
    """Single-line electrical schematic: PV -> DC isolator -> MPPT -> inverter
    -> AC DB -> grid + loads, with battery branch off the inverter DC bus.

    Returns data-URI PNG.
    """
    fig, ax = plt.subplots(figsize=(8.5, 5.5), facecolor="white")
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 7)
    ax.axis("off")

    ax.text(5.5, 6.6, "SINGLE LINE DIAGRAM",
            ha="center", fontsize=12, weight="bold", color="#1e3a8a")
    ax.text(5.5, 6.2, f"{pv_kw:.2f} kWp PV  |  {inv_kw:.0f} kW Hybrid Inverter  "
            f"|  {bat_kwh:.1f} kWh {chemistry}",
            ha="center", fontsize=9.5, color="#374151")

    # Row 1: PV Array (yellow) -> DC Isolator -> MPPT
    _block(ax, 0.3, 4.2, 1.8, 1.0, f"PV Array\n{pv_kw:.2f} kWp",
           color="#fef3c7", edge="#b45309")
    _arrow(ax, 2.1, 4.7, 3.0, 4.7)
    _block(ax, 3.0, 4.2, 1.5, 1.0, "DC Isolator\n1000 V",
           color="#e5e7eb", edge="#374151")
    _arrow(ax, 4.5, 4.7, 5.4, 4.7)
    _block(ax, 5.4, 4.2, 1.6, 1.0, f"MPPT\n{mppt_a} A",
           color="#dcfce7", edge="#15803d")
    _arrow(ax, 7.0, 4.7, 7.9, 4.7)

    # Row 1 right: Inverter
    _block(ax, 7.9, 3.7, 2.5, 2.0, f"Hybrid Inverter\n{inv_kw:.0f} kW",
           color="#dbeafe", edge="#1e3a8a")

    # Battery branch (below inverter)
    _arrow(ax, 9.15, 3.7, 9.15, 2.7)
    _block(ax, 8.1, 1.7, 2.1, 1.0, f"Battery\n{num_bat} x {bat_kwh/max(num_bat,1):.2g} kWh",
           color="#fce7f3", edge="#9d174d")

    # AC side (right of inverter -> AC DB -> grid + loads)
    _arrow(ax, 10.4, 4.7, 10.7, 4.7)
    # AC DB block at the right edge (visual: thin column)
    ax.text(10.55, 4.7, "||", ha="center", va="center", fontsize=14, color="#1e3a8a")

    _block(ax, 4.5, 2.0, 2.0, 1.0, "AC Distribution\nBoard",
           color="#e0e7ff", edge="#4338ca")
    _arrow(ax, 9.15, 3.7, 5.5, 3.0, color="#374151")

    if system_type in ("hybrid", "grid-tied"):
        _block(ax, 0.3, 2.0, 1.6, 1.0, "Utility\nGrid",
               color="#fef9c3", edge="#a16207")
        _arrow(ax, 1.9, 2.5, 4.5, 2.5)

    # Loads at bottom
    _block(ax, 4.7, 0.3, 1.6, 1.0, "Loads",
           color="#fee2e2", edge="#991b1b")
    _arrow(ax, 5.5, 2.0, 5.5, 1.3)

    # Earthing rail
    ax.plot([0.3, 10.7], [0.05, 0.05], color="#15803d", linewidth=2)
    ax.text(0.3, -0.12, "PE/Earth (16 mm^2 Cu, BS 7430)", fontsize=8, color="#15803d")

    return _fig_to_data_uri(fig)


# ── System Topology ──────────────────────────────────────────────────────────

def system_topology_b64(pv_kw, inv_kw, bat_kwh, daily_kwh, psh, system_type="hybrid"):
    """High-level system flow diagram for the executive proposal page."""
    fig, ax = plt.subplots(figsize=(8.5, 4.5), facecolor="white")
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 5.5)
    ax.axis("off")

    ax.text(5.5, 5.1, "SYSTEM TOPOLOGY",
            ha="center", fontsize=12, weight="bold", color="#1e3a8a")
    ax.text(5.5, 4.7, f"Daily generation target: {daily_kwh:.1f} kWh  "
            f"|  PSH: {psh:.2f} h  |  Mode: {system_type.title()}",
            ha="center", fontsize=9.5, color="#374151")

    # Sun -> PV
    ax.text(0.5, 3.6, "Sun", ha="center", fontsize=11, color="#b45309")
    ax.add_patch(plt.Circle((0.5, 3.0), 0.32, color="#fbbf24"))
    _arrow(ax, 0.95, 3.0, 1.8, 3.0, color="#b45309")
    _block(ax, 1.8, 2.5, 1.8, 1.1, f"PV Array\n{pv_kw:.2f} kWp",
           color="#fef3c7", edge="#b45309")
    _arrow(ax, 3.6, 3.0, 4.4, 3.0)

    # Power Conversion
    _block(ax, 4.4, 2.5, 2.0, 1.1, f"Power Conversion\n{inv_kw:.0f} kW Hybrid",
           color="#dbeafe", edge="#1e3a8a")
    _arrow(ax, 6.4, 3.0, 7.2, 3.0)

    # Loads
    _block(ax, 7.2, 2.5, 1.8, 1.1, f"Loads\n{daily_kwh:.1f} kWh/day",
           color="#fee2e2", edge="#991b1b")

    # Storage below
    _block(ax, 4.4, 0.7, 2.0, 1.1, f"Energy Storage\n{bat_kwh:.1f} kWh",
           color="#fce7f3", edge="#9d174d")
    _arrow(ax, 5.4, 2.5, 5.4, 1.8, color="#374151", style="<|-|>")

    # Grid
    if system_type in ("hybrid", "grid-tied"):
        _block(ax, 9.3, 2.5, 1.5, 1.1, "Utility\nGrid",
               color="#fef9c3", edge="#a16207")
        _arrow(ax, 9.0, 3.3, 9.3, 3.3, color="#374151", style="<|-|>")

    return _fig_to_data_uri(fig)


# ── Mounting Plan ────────────────────────────────────────────────────────────

def mounting_plan_b64(num_panels, panel_wp=400, orientation="landscape",
                      roof_type="rooftop_pitched"):
    """Top-view roof mounting layout. Tries to arrange panels in a sensible
    rectangle: e.g. 13 panels -> 4x4 with one removed, 24 -> 4x6, etc."""
    if num_panels <= 0:
        num_panels = 1

    # Pick row/col closest to a rectangle, max 8 cols.
    cols = min(8, max(1, math.ceil(math.sqrt(num_panels * 1.6))))
    rows = math.ceil(num_panels / cols)
    placed = num_panels

    fig, ax = plt.subplots(figsize=(8.5, max(4.0, 0.7 * rows + 1.5)),
                           facecolor="white")
    ax.text(0.5, 1.04, "MOUNTING PLAN (TOP VIEW)",
            ha="center", transform=ax.transAxes,
            fontsize=12, weight="bold", color="#1e3a8a")
    ax.text(0.5, 1.00, f"{num_panels} x {panel_wp} Wp panels  |  {rows} rows x {cols} cols max  "
            f"|  {roof_type.replace('_', ' ').title()}",
            ha="center", transform=ax.transAxes,
            fontsize=9.5, color="#374151")

    if orientation == "portrait":
        pw, ph = 0.8, 1.5
    else:
        pw, ph = 1.5, 0.9
    gap = 0.12

    # Roof outline
    total_w = cols * (pw + gap) + gap
    total_h = rows * (ph + gap) + gap
    ax.add_patch(Rectangle((-0.4, -0.4), total_w + 0.8, total_h + 0.8,
                           fill=False, edgecolor="#9ca3af", linewidth=1.2,
                           linestyle="--"))

    panel_idx = 0
    for r in range(rows - 1, -1, -1):
        for c in range(cols):
            if panel_idx >= placed:
                break
            x = gap + c * (pw + gap)
            y = gap + r * (ph + gap)
            ax.add_patch(Rectangle((x, y), pw, ph,
                                   facecolor="#1e3a8a", edgecolor="#1e1b4b",
                                   linewidth=1.0))
            ax.text(x + pw/2, y + ph/2, f"{panel_idx + 1}",
                    ha="center", va="center", color="white",
                    fontsize=8, weight="bold")
            panel_idx += 1
        if panel_idx >= placed:
            break

    ax.set_xlim(-0.5, total_w + 0.5)
    ax.set_ylim(-0.7, total_h + 0.4)
    ax.set_aspect("equal")
    ax.axis("off")

    # North arrow
    ax.annotate("N", xy=(total_w + 0.2, total_h - 0.3),
                xytext=(total_w + 0.2, total_h - 1.0),
                ha="center", fontsize=10, color="#374151",
                arrowprops=dict(arrowstyle="-|>", color="#374151"))

    return _fig_to_data_uri(fig)
