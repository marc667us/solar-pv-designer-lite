# ui.py
# Solar PV Designer Lite - Graphical User Interface
# Uses Python's built-in tkinter library (no external dependencies)

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import os
import sys

# Add project root to path so imports work when running ui.py directly
def _app_dir():
    """Return the app base directory — works both as a .py script and a frozen exe."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, _app_dir())

from calculation.load_estimation import estimate_load
from calculation.pv_sizing import size_pv
from calculation.battery_sizing import size_battery
from calculation.inverter_sizing import size_inverter
from calculation.boq_generator import generate_boq
from calculation.specification_generator import generate_specification
from calculation.installation_method_generator import generate_installation_method
from calculation.economic_impact_generator import generate_economic_impact
from config.ghana_regions import (REGIONS, REGION_LIST, DEFAULT_REGION,
                                   POWER_ISSUES, temp_derating_factor)


# ── Colours & fonts ──────────────────────────────────────────────────────────
BG          = "#1e1e2e"
PANEL       = "#2a2a3e"
ACCENT      = "#f5a623"
ACCENT2     = "#4fc3f7"
TEXT        = "#e0e0e0"
TEXT_DIM    = "#888888"
SUCCESS     = "#66bb6a"
ERROR       = "#ef5350"
BORDER      = "#3a3a5c"

FONT_TITLE  = ("Segoe UI", 16, "bold")
FONT_HEAD   = ("Segoe UI", 11, "bold")
FONT_LABEL  = ("Segoe UI", 10)
FONT_INPUT  = ("Segoe UI", 11)
FONT_RESULT = ("Segoe UI", 10)
FONT_MONO   = ("Courier New", 9)


# ── Ghana map geometry ────────────────────────────────────────────────────────
# Approximate clockwise outline of Ghana (longitude, latitude).
# Canvas 210 × 242 px.  Mapping:
#   x = int(10 + (lon + 3.3) / 4.5 * 188)
#   y = int(15 + (11.2 - lat) / 6.7 * 218)
GHANA_OUTLINE = [
    (-3.07, 11.10), (-2.80, 11.15), (-2.00, 11.15), (-1.00, 11.10),
    ( 0.00, 10.95), ( 0.30, 11.05), ( 0.55, 10.70), ( 0.70, 10.20),
    ( 0.80,  9.50), ( 0.75,  8.50), ( 0.60,  7.50), ( 1.15,  6.20),
    ( 1.05,  5.80), ( 0.55,  5.40), ( 0.20,  5.30), (-0.30,  5.05),
    (-0.80,  4.90), (-1.60,  4.80), (-2.10,  4.85), (-2.50,  5.10),
    (-3.10,  5.20), (-3.25,  6.00), (-3.10,  7.00), (-3.20,  8.00),
    (-3.25,  9.00), (-3.15, 10.00), (-3.07, 11.10),
]

# Approximate geographic centre of each region (longitude, latitude)
REGION_CENTERS = {
    "Greater Accra": (-0.20,  5.60),
    "Central":       (-1.20,  5.50),
    "Western":       (-2.10,  5.00),
    "Ashanti":       (-1.60,  6.70),
    "Eastern":       (-0.50,  6.50),
    "Volta":         ( 0.30,  6.80),
    "Western North": (-2.80,  6.50),
    "Ahafo":         (-2.50,  6.80),
    "Bono":          (-2.50,  7.80),
    "Bono East":     (-1.50,  7.80),
    "Oti":           ( 0.30,  8.00),
    "Northern":      (-1.20,  9.50),
    "Savannah":      (-1.60,  9.00),
    "North East":    (-0.50, 10.50),
    "Upper West":    (-2.30, 10.30),
    "Upper East":    (-1.00, 10.90),
}


class SolarPVApp(tk.Toplevel):
    def __init__(self, master, current_user: dict = None, on_back=None):
        super().__init__(master)
        self.current_user = current_user or {}
        self._on_back     = on_back

        self.title("Solar PV Designer Lite")
        self.geometry("1200x860")
        self.minsize(1050, 720)
        self.configure(bg=BG)
        self.resizable(True, True)

        # Center on screen
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"1200x860+{(sw-1200)//2}+{(sh-860)//2}")

        self.protocol("WM_DELETE_WINDOW", self._handle_close)

        self._build_header()
        self._build_region_banner()   # ← full-width region selector + profile
        self._build_body()
        self._build_footer()

    def _handle_close(self):
        if self._on_back:
            self._on_back()
        self.destroy()

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = tk.Frame(self, bg=ACCENT, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="☀  Solar PV Designer Lite",
                 font=FONT_TITLE, bg=ACCENT, fg="#1e1e2e").pack(side="left", padx=20, pady=12)

        # ← Back to Dashboard button (only if launched from dashboard)
        if self._on_back:
            tk.Button(hdr, text="←  Dashboard",
                      font=("Segoe UI", 9, "bold"),
                      bg="#d4911a", fg="#1e1e2e",
                      activebackground="#b8790f",
                      relief="flat", cursor="hand2", padx=12, pady=6,
                      command=self._handle_close).pack(side="right", padx=10, pady=10)

        # Logged-in user info
        uname = self.current_user.get("full_name") or self.current_user.get("username", "")
        role  = self.current_user.get("role", "")
        if uname:
            tk.Label(hdr, text=f"👤  {uname}  [{role}]",
                     font=FONT_LABEL, bg=ACCENT, fg="#4a3000").pack(side="right", padx=(0, 6), pady=12)
        else:
            tk.Label(hdr, text="Off-Grid System Sizing Tool  |  Ghana",
                     font=FONT_LABEL, bg=ACCENT, fg="#4a3000").pack(side="right", padx=20)

    # ── Region banner ─────────────────────────────────────────────────────────
    def _build_region_banner(self):
        """3-column banner: [dropdown + Ghana map | solar profile | power reliability]"""
        banner = tk.Frame(self, bg=PANEL, pady=6)
        banner.pack(fill="x", padx=0)

        inner = tk.Frame(banner, bg=PANEL)
        inner.pack(fill="x", padx=16)

        # ════════════════════════════════════════════════════════════════════
        # Column 1 — region selector + Ghana map
        # ════════════════════════════════════════════════════════════════════
        col1 = tk.Frame(inner, bg=PANEL)
        col1.pack(side="left", anchor="n", padx=(0, 14))

        tk.Label(col1, text="INSTALLATION REGION",
                 font=("Segoe UI", 8, "bold"), bg=PANEL, fg=ACCENT2).pack(anchor="w")
        tk.Frame(col1, bg=BORDER, height=1).pack(fill="x", pady=(2, 6))

        self.var_region = tk.StringVar(value=DEFAULT_REGION)
        combo = ttk.Combobox(
            col1, textvariable=self.var_region,
            values=REGION_LIST, state="readonly", width=22,
            font=FONT_INPUT,
        )
        combo.pack(anchor="w")
        combo.bind("<<ComboboxSelected>>", self._on_region_change)

        # Style the combobox
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox",
                         fieldbackground="#12121f", background=PANEL,
                         foreground=ACCENT, selectbackground=BORDER,
                         selectforeground=ACCENT, arrowcolor=ACCENT2,
                         bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
        style.map("TCombobox",
                  fieldbackground=[("readonly", "#12121f")],
                  foreground=[("readonly", ACCENT)])

        # Ghana map canvas — kept compact so the banner doesn't crowd the body
        self._map_canvas = tk.Canvas(
            col1, width=196, height=196,
            bg="#0d1117", highlightthickness=1,
            highlightbackground=BORDER,
        )
        self._map_canvas.pack(pady=(6, 0))

        # ════════════════════════════════════════════════════════════════════
        # Column 2 — solar profile stat chips
        # ════════════════════════════════════════════════════════════════════
        col2 = tk.Frame(inner, bg=PANEL)
        col2.pack(side="left", anchor="n", padx=(0, 14))

        tk.Label(col2, text="SOLAR PROFILE",
                 font=("Segoe UI", 8, "bold"), bg=PANEL, fg=ACCENT2).pack(anchor="w")
        tk.Frame(col2, bg=BORDER, height=1).pack(fill="x", pady=(2, 6))

        stats_frame = tk.Frame(col2, bg=PANEL)
        stats_frame.pack(anchor="w")

        row1 = tk.Frame(stats_frame, bg=PANEL)
        row1.pack(anchor="w")
        row2 = tk.Frame(stats_frame, bg=PANEL)
        row2.pack(anchor="w", pady=(4, 0))

        self._stat_vars = {}
        primary_stats = [
            ("psh_val",    "Peak Sun Hours",  "— h/day",  ACCENT),
            ("temp_val",   "Avg Temperature", "— °C",     "#ef5350"),
            ("ghi_val",    "Annual GHI",      "— kWh/m²", "#ffd54f"),
            ("rating_val", "Solar Rating",    "—",        SUCCESS),
        ]
        secondary_stats = [
            ("climate_val", "Climate Zone",    "—",   TEXT_DIM),
            ("tilt_val",    "Rec. Tilt Angle", "—°",  ACCENT2),
            ("rainy_val",   "Rainy Months",    "—",   ACCENT2),
            ("capital_val", "Region Capital",  "—",   TEXT_DIM),
        ]

        for key, label, default, color in primary_stats:
            chip = self._stat_chip(row1, label, default, color)
            chip.pack(side="left", padx=(0, 6))
            self._stat_vars[key] = chip.var

        for key, label, default, color in secondary_stats:
            chip = self._stat_chip(row2, label, default, color)
            chip.pack(side="left", padx=(0, 6))
            self._stat_vars[key] = chip.var

        # Notes line
        self.var_region_note = tk.StringVar(value="")
        tk.Label(col2, textvariable=self.var_region_note,
                 font=("Segoe UI", 8, "italic"), bg=PANEL,
                 fg=TEXT_DIM, wraplength=380, justify="left",
                 ).pack(anchor="w", pady=(8, 0))

        # ════════════════════════════════════════════════════════════════════
        # Column 3 — grid & power reliability
        # ════════════════════════════════════════════════════════════════════
        col3 = tk.Frame(inner, bg=PANEL)
        col3.pack(side="left", anchor="n")

        tk.Label(col3, text="GRID & POWER RELIABILITY",
                 font=("Segoe UI", 8, "bold"), bg=PANEL, fg="#ef5350").pack(anchor="w")
        tk.Frame(col3, bg=BORDER, height=1).pack(fill="x", pady=(2, 6))

        # Stat rows
        self._power_vars = {}
        _PCOL = "#1c1c2e"
        power_rows = [
            ("pwr_zone",     "Distribution Utility", "—",  ACCENT2),
            ("pwr_outage",   "Est. Daily Outage",    "—",  "#ff7043"),
            ("pwr_coverage", "Grid Coverage",        "—",  "#ffd54f"),
            ("pwr_reliable", "Reliability",          "—",  TEXT_DIM),
        ]
        for key, label, default, color in power_rows:
            row = tk.Frame(col3, bg=_PCOL, padx=8, pady=4,
                           highlightbackground=BORDER, highlightthickness=1)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, font=("Segoe UI", 7, "bold"),
                     bg=_PCOL, fg=TEXT_DIM).pack(anchor="w")
            var = tk.StringVar(value=default)
            lbl = tk.Label(row, textvariable=var,
                           font=("Segoe UI", 9, "bold"),
                           bg=_PCOL, fg=color)
            lbl.pack(anchor="w")
            self._power_vars[key] = var
            if key == "pwr_reliable":
                self._lbl_reliability = lbl   # keep ref so we can change fg

        # Key issues
        tk.Label(col3, text="KEY ISSUES",
                 font=("Segoe UI", 7, "bold"), bg=PANEL, fg=TEXT_DIM
                 ).pack(anchor="w", pady=(6, 2))
        self.var_power_issues = tk.StringVar(value="—")
        tk.Label(col3, textvariable=self.var_power_issues,
                 font=("Segoe UI", 8), bg=PANEL, fg="#ef5350",
                 wraplength=220, justify="left").pack(anchor="w")

        # Populate with default region immediately
        self._on_region_change()

    def _stat_chip(self, parent, label, default, color):
        """A small labeled stat card. Returns the frame with a .var attribute."""
        chip = tk.Frame(parent, bg="#1c1c2e", padx=8, pady=4,
                        highlightbackground=BORDER, highlightthickness=1)
        tk.Label(chip, text=label, font=("Segoe UI", 7, "bold"),
                 bg="#1c1c2e", fg=TEXT_DIM).pack(anchor="w")
        var = tk.StringVar(value=default)
        tk.Label(chip, textvariable=var, font=("Segoe UI", 11, "bold"),
                 bg="#1c1c2e", fg=color).pack(anchor="w")
        chip.var = var
        return chip

    # ── Ghana map drawing ─────────────────────────────────────────────────────
    def _geo_to_px(self, lon, lat):
        """Convert geographic coordinates to canvas pixel position (196×196 canvas)."""
        x = int(8 + (lon + 3.3) / 4.5 * 178)
        y = int(13 + (11.2 - lat) / 6.7 * 172)
        return x, y

    def _draw_ghana_map(self, selected_region=""):
        c = self._map_canvas
        c.delete("all")

        W, H = 196, 196
        c.create_rectangle(0, 0, W, H, fill="#0d1117", outline="")

        # Title
        c.create_text(W // 2, 6, text="GHANA — REGION MAP",
                      fill=ACCENT2, font=("Segoe UI", 6, "bold"), anchor="center")

        # Ghana outline polygon
        pts = []
        for lon, lat in GHANA_OUTLINE:
            pts.extend(self._geo_to_px(lon, lat))
        c.create_polygon(*pts, fill="#1a3028", outline="#4db6ac", width=1.5, smooth=False)

        # All region dots (colour by solar rating)
        for name, (lon, lat) in REGION_CENTERS.items():
            x, y = self._geo_to_px(lon, lat)
            r_data = REGIONS.get(name, {})
            dot_color = r_data.get("rating_color", "#888888")
            if name == selected_region:
                c.create_oval(x - 6, y - 6, x + 6, y + 6,
                              fill=ACCENT, outline="#ffffff", width=1.5)
                short = name if len(name) <= 9 else name.split()[0]
                c.create_text(x, y + 10, text=short,
                              fill=ACCENT, font=("Segoe UI", 6, "bold"), anchor="n")
            else:
                c.create_oval(x - 3, y - 3, x + 3, y + 3,
                              fill=dot_color, outline="", width=0)

        # Compass N
        c.create_text(H - 7, 14, text="N", fill=TEXT_DIM,
                      font=("Segoe UI", 6, "bold"), anchor="center")
        c.create_line(H - 7, 20, H - 7, 27, fill=TEXT_DIM, width=1,
                      arrow="last", arrowshape=(4, 5, 2))

        # Legend strip
        ly = H - 10
        legend = [
            ("#4fc3f7", "Mod"), ("#66bb6a", "Good"),
            ("#ffd54f", "VGood"), ("#f5a623", "Excel"),
        ]
        lx = 3
        for col, label in legend:
            c.create_oval(lx, ly - 3, lx + 5, ly + 3, fill=col, outline="")
            c.create_text(lx + 8, ly, text=label, fill=TEXT_DIM,
                          font=("Segoe UI", 5), anchor="w")
            lx += 47

    def _on_region_change(self, event=None):
        """Update solar profile, Ghana map, and power reliability panel."""
        name = self.var_region.get()
        r = REGIONS.get(name)
        if not r:
            return

        # ── Solar profile chips ──
        self._stat_vars["psh_val"].set(f"{r['psh']} h/day")
        self._stat_vars["temp_val"].set(f"{r['avg_temp']} °C")
        self._stat_vars["ghi_val"].set(f"{r['ghi_annual']:,} kWh/m²")
        self._stat_vars["rating_val"].set(r["rating"])
        self._stat_vars["climate_val"].set(r["climate"])
        self._stat_vars["tilt_val"].set(f"{r['tilt_angle']}°")
        self._stat_vars["rainy_val"].set(r["rainy_months"])
        self._stat_vars["capital_val"].set(r["capital"])
        self.var_region_note.set(r["notes"])

        # ── Ghana map ──
        self._draw_ghana_map(name)

        # ── Power reliability panel ──
        pi = POWER_ISSUES.get(name, {})
        self._power_vars["pwr_zone"].set(pi.get("ecg_zone", "—"))
        self._power_vars["pwr_outage"].set(pi.get("daily_outage_hrs", "—"))
        cov = pi.get("grid_coverage_pct", "—")
        self._power_vars["pwr_coverage"].set(f"{cov}%" if isinstance(cov, int) else "—")
        reliability = pi.get("reliability", "—")
        self._power_vars["pwr_reliable"].set(reliability)
        rel_color = {
            "Very Poor": ERROR,
            "Poor":      "#ff7043",
            "Fair":      "#ffd54f",
            "Good":      SUCCESS,
        }.get(reliability, TEXT_DIM)
        self._lbl_reliability.config(fg=rel_color)
        issues = pi.get("main_issues", [])
        self.var_power_issues.set("\n".join(f"• {i}" for i in issues))

        # ── Auto-fill Peak Sun Hours input ──
        if hasattr(self, "var_psh"):
            self.var_psh.set(str(r["psh"]))

    # ── Main body ─────────────────────────────────────────────────────────────
    def _build_body(self):
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=12)

        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        self._build_left_panel(body)
        self._build_right_panel(body)

    # ── Left panel: inputs ────────────────────────────────────────────────────
    def _build_left_panel(self, parent):
        left = tk.Frame(parent, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(0, weight=1)   # inputs area expands
        left.rowconfigure(1, weight=0)   # buttons row stays fixed at bottom
        left.columnconfigure(0, weight=1)

        # ── Scrollable inputs area ──
        inp_outer = tk.Frame(left, bg=BG)
        inp_outer.grid(row=0, column=0, sticky="nsew")
        inp_outer.rowconfigure(0, weight=1)
        inp_outer.columnconfigure(0, weight=1)

        inp_canvas = tk.Canvas(inp_outer, bg=BG, highlightthickness=0)
        inp_canvas.grid(row=0, column=0, sticky="nsew")

        inp_frame = tk.Frame(inp_canvas, bg=BG)
        _iwin = inp_canvas.create_window((0, 0), window=inp_frame, anchor="nw")

        inp_frame.bind("<Configure>",
            lambda e: inp_canvas.configure(scrollregion=inp_canvas.bbox("all")))
        inp_canvas.bind("<Configure>",
            lambda e: inp_canvas.itemconfig(_iwin, width=e.width))

        # Load inputs
        self._section(inp_frame, "Load Requirements (kWh/day)")
        self.var_lighting = self._input_row(inp_frame, "Lighting Load",  "kWh/day", "2.5")
        self.var_sockets  = self._input_row(inp_frame, "Socket Load",    "kWh/day", "3.0")
        self.var_ac       = self._input_row(inp_frame, "AC / HVAC Load", "kWh/day", "4.0")

        # System assumptions
        self._section(inp_frame, "System Assumptions")
        self.var_psh  = self._input_row(inp_frame, "Peak Sun Hours",    "h/day", "5")
        self.var_eff  = self._input_row(inp_frame, "System Efficiency", "0–1",   "0.75")
        self.var_dod  = self._input_row(inp_frame, "Battery DoD",       "0–1",   "0.80")
        self.var_auto = self._input_row(inp_frame, "Autonomy",          "days",  "1")

        # ── Buttons — pinned to bottom, always visible ──
        btn_frame = tk.Frame(left, bg=BG)
        btn_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        tk.Button(btn_frame, text="  Run Design  ",
                  font=("Segoe UI", 11, "bold"),
                  bg=ACCENT, fg="#1e1e2e", activebackground="#d4911a",
                  relief="flat", cursor="hand2", padx=10, pady=8,
                  command=self._run_design).pack(fill="x", pady=(0, 6))

        tk.Button(btn_frame, text="  Clear  ",
                  font=FONT_LABEL, bg=PANEL, fg=TEXT_DIM,
                  activebackground=BORDER, relief="flat", cursor="hand2",
                  padx=10, pady=6,
                  command=self._clear).pack(fill="x")

    # ── Right panel: results + log ────────────────────────────────────────────
    def _build_right_panel(self, parent):
        outer = tk.Frame(parent, bg=BG)
        outer.grid(row=0, column=1, sticky="nsew")
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        # Scrollable canvas so all content is reachable on small screens
        vscroll = ttk.Scrollbar(outer, orient="vertical")
        vscroll.grid(row=0, column=1, sticky="ns")

        scroll_canvas = tk.Canvas(outer, bg=BG, highlightthickness=0,
                                   yscrollcommand=vscroll.set)
        scroll_canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.config(command=scroll_canvas.yview)

        right = tk.Frame(scroll_canvas, bg=BG)
        _win = scroll_canvas.create_window((0, 0), window=right, anchor="nw")

        def _on_frame_configure(e):
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))

        def _on_canvas_configure(e):
            scroll_canvas.itemconfig(_win, width=e.width)

        right.bind("<Configure>", _on_frame_configure)
        scroll_canvas.bind("<Configure>", _on_canvas_configure)

        # Mouse-wheel scroll (Windows)
        def _on_mousewheel(e):
            scroll_canvas.yview_scroll(-1 * (e.delta // 120), "units")
        scroll_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # ── Results cards ──
        self._section(right, "Sizing Results")

        cards = tk.Frame(right, bg=BG)
        cards.pack(fill="x", pady=(0, 10))
        cards.columnconfigure((0, 1, 2), weight=1)

        self.card_pv      = self._result_card(cards, 0, "PV Array",   "—", "kWp")
        self.card_panels  = self._result_card(cards, 1, "Modules",    "—", "pcs")
        self.card_battery = self._result_card(cards, 2, "Battery",    "—", "kWh")
        self.card_units   = self._result_card(cards, 3, "Batt. Units","—", "pcs")
        self.card_inv     = self._result_card(cards, 4, "Inverter",   "—", "kW")
        self.card_load    = self._result_card(cards, 5, "Total Load", "—", "kWh/day")

        # ── Economic Viability Verdict banner ──
        self._section(right, "Economic Viability Assessment")

        self._verdict_frame = tk.Frame(right, bg=PANEL, padx=14, pady=12,
                                       highlightthickness=2,
                                       highlightbackground=BORDER)
        self._verdict_frame.pack(fill="x", pady=(0, 4))

        verdict_top = tk.Frame(self._verdict_frame, bg=PANEL)
        verdict_top.pack(fill="x")

        # Big verdict badge (left)
        self._verdict_badge = tk.Label(
            verdict_top, text="AWAITING DESIGN",
            font=("Segoe UI", 14, "bold"),
            bg=PANEL, fg=TEXT_DIM, width=20, anchor="w",
        )
        self._verdict_badge.pack(side="left")

        # Payback chip (right)
        payback_chip = tk.Frame(verdict_top, bg="#1c1c2e", padx=10, pady=6)
        payback_chip.pack(side="right")
        tk.Label(payback_chip, text="SIMPLE PAYBACK",
                 font=("Segoe UI", 7, "bold"), bg="#1c1c2e", fg=TEXT_DIM).pack(anchor="w")
        self._verdict_payback = tk.StringVar(value="— yrs")
        tk.Label(payback_chip, textvariable=self._verdict_payback,
                 font=("Segoe UI", 14, "bold"), bg="#1c1c2e", fg=ACCENT2).pack(anchor="w")

        # NPV + ROI chips row
        kpi_row = tk.Frame(self._verdict_frame, bg=PANEL)
        kpi_row.pack(fill="x", pady=(8, 0))

        for attr, label, color in [
            ("_verdict_npv",  "25-yr NPV (GHS)", "#66bb6a"),
            ("_verdict_roi",  "ROI",             "#ffd54f"),
            ("_verdict_save", "Year-1 Savings",  ACCENT2),
        ]:
            chip = tk.Frame(kpi_row, bg="#1c1c2e", padx=10, pady=5)
            chip.pack(side="left", padx=(0, 6))
            tk.Label(chip, text=label, font=("Segoe UI", 7, "bold"),
                     bg="#1c1c2e", fg=TEXT_DIM).pack(anchor="w")
            var = tk.StringVar(value="—")
            tk.Label(chip, textvariable=var, font=("Segoe UI", 11, "bold"),
                     bg="#1c1c2e", fg=color).pack(anchor="w")
            setattr(self, attr, var)

        # Conditions / risk flags text
        self._verdict_notes = tk.StringVar(value="")
        self._verdict_notes_lbl = tk.Label(
            self._verdict_frame, textvariable=self._verdict_notes,
            font=("Segoe UI", 8), bg=PANEL, fg=TEXT_DIM,
            wraplength=560, justify="left",
        )
        self._verdict_notes_lbl.pack(anchor="w", pady=(8, 0))

        # ── Output file links ──
        self._section(right, "Output Reports")

        reports_frame = tk.Frame(right, bg=BG)
        reports_frame.pack(fill="x", pady=(0, 6))

        output_files = [
            ("📄  Design Report",                    "output/report.txt"),
            ("📋  Bill of Quantities (BoQ)",          "output/boq.txt"),
            ("📘  PV Technical Specification",        "output/pv_master_technical_specification.txt"),
            ("🔧  Installation Method Report (TXT)",  "output/installation_method_report.txt"),
            ("🖼️  Installation Method Report (HTML)", "output/installation_method_report.html"),
            ("💰  Economic Impact Report (TXT)",       "output/economic_impact_report.txt"),
            ("📊  Economic Impact Report (HTML)",      "output/economic_impact_report.html"),
        ]

        self.report_buttons = []
        for label, filepath in output_files:
            btn = tk.Button(
                reports_frame, text=label,
                font=FONT_LABEL, bg=PANEL, fg=ACCENT2,
                activebackground=BORDER, activeforeground=ACCENT,
                relief="flat", cursor="hand2", anchor="w",
                padx=10, pady=3,
                command=lambda f=filepath: self._open_file(f)
            )
            btn.pack(fill="x", pady=1)
            btn.config(state="disabled")
            self.report_buttons.append(btn)

        # ── Log ──
        self._section(right, "Output Log")

        self.log = scrolledtext.ScrolledText(
            right, font=FONT_MONO, bg="#0d0d1a", fg=TEXT,
            insertbackground=TEXT, relief="flat",
            wrap="word", state="disabled", height=7
        )
        self.log.pack(fill="both", expand=True)
        self.log.tag_config("ok",   foreground=SUCCESS)
        self.log.tag_config("err",  foreground=ERROR)
        self.log.tag_config("head", foreground=ACCENT)
        self.log.tag_config("dim",  foreground=TEXT_DIM)

        self._log("Solar PV Designer Lite ready.", "dim")
        self._log("Enter load values and click  Run Design.", "dim")

    # ── Footer ────────────────────────────────────────────────────────────────
    def _build_footer(self):
        ftr = tk.Frame(self, bg=PANEL, height=32)
        ftr.pack(fill="x", side="bottom")
        ftr.pack_propagate(False)

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(ftr, textvariable=self.status_var,
                 font=FONT_LABEL, bg=PANEL, fg=TEXT_DIM).pack(side="left", padx=16)
        tk.Label(ftr, text="Location: Ghana  |  BS 7671:2018  |  415/230V 50Hz",
                 font=FONT_LABEL, bg=PANEL, fg=TEXT_DIM).pack(side="right", padx=16)

    # ── Helpers: UI widgets ───────────────────────────────────────────────────
    def _section(self, parent, title):
        tk.Label(parent, text=title.upper(),
                 font=("Segoe UI", 8, "bold"),
                 bg=BG, fg=ACCENT2).pack(anchor="w", pady=(10, 4))
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=(0, 8))

    def _input_row(self, parent, label, unit, default):
        row = tk.Frame(parent, bg=PANEL, padx=10, pady=6)
        row.pack(fill="x", pady=2)
        row.columnconfigure(1, weight=1)

        tk.Label(row, text=label, font=FONT_LABEL,
                 bg=PANEL, fg=TEXT, width=18, anchor="w").grid(row=0, column=0, sticky="w")

        var = tk.StringVar(value=default)
        entry = tk.Entry(row, textvariable=var, font=FONT_INPUT,
                         bg="#12121f", fg=ACCENT, insertbackground=ACCENT,
                         relief="flat", width=10)
        entry.grid(row=0, column=1, sticky="ew", padx=6)

        tk.Label(row, text=unit, font=FONT_LABEL,
                 bg=PANEL, fg=TEXT_DIM, width=8, anchor="w").grid(row=0, column=2, sticky="w")

        return var

    def _result_card(self, parent, col, title, value, unit):
        card = tk.Frame(parent, bg=PANEL, padx=10, pady=8)
        card.grid(row=col // 3, column=col % 3, sticky="ew", padx=4, pady=4)

        tk.Label(card, text=title, font=("Segoe UI", 8),
                 bg=PANEL, fg=TEXT_DIM).pack(anchor="w")

        val_var = tk.StringVar(value=value)
        tk.Label(card, textvariable=val_var, font=("Segoe UI", 18, "bold"),
                 bg=PANEL, fg=ACCENT).pack(anchor="w")

        tk.Label(card, text=unit, font=("Segoe UI", 8),
                 bg=PANEL, fg=TEXT_DIM).pack(anchor="w")

        return val_var

    # ── Open output file ─────────────────────────────────────────────────────
    def _open_file(self, filepath):
        full_path = os.path.join(_app_dir(), filepath)
        if os.path.exists(full_path):
            os.startfile(full_path)
        else:
            messagebox.showwarning("File Not Found",
                f"'{filepath}' does not exist yet.\nRun the design first.")

    def _enable_report_buttons(self):
        for btn in self.report_buttons:
            btn.config(state="normal")

    # ── Helpers: log ─────────────────────────────────────────────────────────
    def _log(self, msg, tag=""):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    # ── Run design ────────────────────────────────────────────────────────────
    def _run_design(self):
        self._clear_log()
        self.status_var.set("Running...")
        self.update()

        # Validate inputs
        try:
            lighting = float(self.var_lighting.get())
            sockets  = float(self.var_sockets.get())
            ac       = float(self.var_ac.get())
            psh      = float(self.var_psh.get())
            eff      = float(self.var_eff.get())
            dod      = float(self.var_dod.get())
            auto     = float(self.var_auto.get())
        except ValueError:
            messagebox.showerror("Input Error", "All fields must be numeric values.")
            self.status_var.set("Error — invalid input")
            return

        if any(v < 0 for v in [lighting, sockets, ac, psh, eff, dod, auto]):
            messagebox.showerror("Input Error", "Values cannot be negative.")
            self.status_var.set("Error — negative value")
            return

        if lighting + sockets + ac == 0:
            messagebox.showerror("Input Error", "Total load cannot be zero.")
            self.status_var.set("Error — zero load")
            return

        if not (0 < eff <= 1):
            messagebox.showerror("Input Error", "System Efficiency must be between 0 and 1.")
            return

        if not (0 < dod <= 1):
            messagebox.showerror("Input Error", "Battery DoD must be between 0 and 1.")
            return

        # Override config values with UI inputs
        import config.system_inputs as cfg
        region_name           = self.var_region.get()
        region_data           = REGIONS.get(region_name, {})
        cfg.SELECTED_REGION   = region_name
        cfg.PEAK_SUN_HOURS    = psh
        cfg.SYSTEM_EFFICIENCY = eff
        cfg.TEMP_DERATING     = temp_derating_factor(region_data.get("avg_temp", 25.0))
        cfg.BATTERY_DOD       = dod
        cfg.AUTONOMY_DAYS     = auto

        # Redirect stdout to log
        import io
        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()

        try:
            self._log("=" * 48, "head")
            self._log("  RUNNING SOLAR PV DESIGN", "head")
            self._log("=" * 48, "head")

            total_load              = estimate_load(lighting, sockets, ac)
            pv_kw, num_panels       = size_pv(total_load)
            battery_kwh, num_batt   = size_battery(total_load)
            inverter_kw             = size_inverter(total_load)

            sys.stdout = old_stdout

            # Flush captured stdout to log
            for line in buffer.getvalue().splitlines():
                self._log(line)

            # Update result cards
            self.card_load.set(f"{total_load:.2f}")
            self.card_pv.set(f"{pv_kw:.2f}")
            self.card_panels.set(str(num_panels))
            self.card_battery.set(f"{battery_kwh:.2f}")
            self.card_units.set(str(num_batt))
            self.card_inv.set(f"{inverter_kw:.2f}")

            # Generate output files
            self._log("\n--- Generating Output Files ---", "head")
            os.chdir(_app_dir())

            self._generate_report(lighting, sockets, ac, total_load,
                                   pv_kw, num_panels, battery_kwh, num_batt, inverter_kw)
            generate_boq(pv_kw, num_panels, battery_kwh, num_batt, inverter_kw)
            generate_specification(pv_kw, num_panels, battery_kwh, num_batt, inverter_kw)
            generate_installation_method(pv_kw, num_panels, battery_kwh, num_batt, inverter_kw)
            verdict_dict = generate_economic_impact(pv_kw, num_panels, battery_kwh,
                                                     num_batt, inverter_kw, total_load)
            self._update_verdict(verdict_dict)

            self._log("\n  output/report.txt", "ok")
            self._log("  output/boq.txt", "ok")
            self._log("  output/pv_master_technical_specification.txt", "ok")
            self._log("  output/installation_method_report.txt", "ok")
            self._log("  output/installation_method_report.html", "ok")
            self._log("  output/economic_impact_report.txt", "ok")
            self._log("  output/economic_impact_report.html", "ok")
            self._log("\n  Design complete!", "ok")
            self.status_var.set("Design complete — output files saved")
            self._enable_report_buttons()

            # Track design count for the logged-in user
            if self.current_user.get("username"):
                try:
                    from auth.user_store import increment_designs
                    increment_designs(self.current_user["username"])
                except Exception:
                    pass

        except Exception as e:
            sys.stdout = old_stdout
            self._log(f"\nError: {e}", "err")
            self.status_var.set(f"Error: {e}")

    def _generate_report(self, lighting, sockets, ac, total_load,
                          pv_kw, num_panels, battery_kwh, num_batteries, inverter_kw):
        os.makedirs("output", exist_ok=True)
        from config.system_inputs import (PEAK_SUN_HOURS, SYSTEM_EFFICIENCY,
                                          TEMP_DERATING, BATTERY_DOD, AUTONOMY_DAYS,
                                          SELECTED_REGION)
        region_data = REGIONS.get(SELECTED_REGION, {})

        lines = [
            "SOLAR PV SYSTEM DESIGN REPORT",
            "=" * 60,
            "Project  : Solar PV Off-Grid System",
            "Location : Ghana",
            f"Region   : {SELECTED_REGION}  ({region_data.get('capital', '')})",
            "Date     : 2026-04-10",
            "Tool     : Solar PV Designer Lite",
            "=" * 60,
            "",
            "1. LOAD SUMMARY",
            "-" * 40,
            f"  Lighting Load : {lighting:.2f} kWh/day",
            f"  Socket Load   : {sockets:.2f} kWh/day",
            f"  AC Load       : {ac:.2f} kWh/day",
            f"  Total Load    : {total_load:.2f} kWh/day",
            "",
            "2. REGIONAL SOLAR PROFILE",
            "-" * 40,
            f"  Region                : {SELECTED_REGION}",
            f"  Capital               : {region_data.get('capital', '—')}",
            f"  Climate Zone          : {region_data.get('climate', '—')}",
            f"  Latitude              : {region_data.get('latitude', '—')}° N",
            f"  Peak Sun Hours (PSH)  : {region_data.get('psh', PEAK_SUN_HOURS)} h/day",
            f"  Annual GHI            : {region_data.get('ghi_annual', '—')} kWh/m²/yr",
            f"  Avg. Temperature      : {region_data.get('avg_temp', '—')} °C",
            f"  Temp Derating Factor  : {TEMP_DERATING:.4f}  (panel loss above 25 °C STC)",
            f"  Recommended Tilt      : {region_data.get('tilt_angle', '—')}° (fixed, toward equator)",
            f"  Rainy Season          : {region_data.get('rainy_months', '—')}",
            f"  Solar Rating          : {region_data.get('rating', '—')}",
            "",
            "3. DESIGN ASSUMPTIONS",
            "-" * 40,
            "  Location              : Ghana",
            f"  Peak Sun Hours        : {PEAK_SUN_HOURS} h/day",
            f"  System Efficiency     : {SYSTEM_EFFICIENCY} ({int(SYSTEM_EFFICIENCY*100)}%)",
            f"  Temp Derating         : {TEMP_DERATING:.4f}",
            f"  Effective Efficiency  : {SYSTEM_EFFICIENCY * TEMP_DERATING:.4f}",
            f"  Battery DoD           : {int(BATTERY_DOD*100)}%",
            f"  Autonomy              : {int(AUTONOMY_DAYS)} day",
            "  DC System Voltage     : 48V",
            "  AC System Voltage     : 415/230V, 3-phase/single-phase, 50 Hz",
            "  Wiring Standard       : BS 7671:2018 (18th Edition)",
            "",
            "4. SIZING RESULTS",
            "-" * 40,
            f"  PV Array Size         : {pv_kw:.2f} kWp",
            f"  No. of PV Modules     : {num_panels} x 400 Wp modules",
            f"  Battery Capacity      : {battery_kwh:.2f} kWh",
            f"  No. of Battery Units  : {num_batteries} x 2.4 kWh units",
            f"  Inverter Size         : {inverter_kw:.2f} kW",
            f"  Inverter AC Output    : 415/230V, 50 Hz (BS EN 62109)",
            "",
            "5. OUTPUT FILES",
            "-" * 40,
            "  output/report.txt",
            "  output/boq.txt",
            "  output/pv_master_technical_specification.txt",
            "  output/installation_method_report.txt",
            "",
            "=" * 60,
            "End of Report",
        ]
        with open("output/report.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # ── Update verdict banner ─────────────────────────────────────────────────
    def _update_verdict(self, v):
        """Populate the Economic Viability Assessment banner from verdict dict."""
        verdict = v.get("verdict", "UNKNOWN")
        payback = v.get("simple_payback", 0)
        npv     = v.get("npv", 0)
        roi     = v.get("roi_pct", 0)
        net_y1  = v.get("net_annual", 0)
        conds   = v.get("conditions", [])
        flags   = v.get("risk_flags", [])
        high_r  = v.get("high_risks", 0)

        # Badge text and colour
        if verdict == "APPROVED":
            badge_text  = "✅  APPROVED — PROJECT VIABLE"
            badge_color = "#66bb6a"
            border_col  = "#388e3c"
        elif verdict == "CONDITIONAL":
            badge_text  = "⚠️  CONDITIONAL APPROVAL"
            badge_color = "#ffd54f"
            border_col  = "#f9a825"
        else:
            badge_text  = "❌  REJECTED — NOT VIABLE"
            badge_color = "#ef5350"
            border_col  = "#b71c1c"

        self._verdict_badge.config(text=badge_text, fg=badge_color)
        self._verdict_frame.config(highlightbackground=border_col)

        # KPI chips
        self._verdict_payback.set(f"{payback:.1f} yrs")
        self._verdict_npv.set(f"GHS {npv:,.0f}")
        self._verdict_roi.set(f"{roi:.1f}%")
        self._verdict_save.set(f"GHS {net_y1:,.0f}/yr")

        # Conditions and flags note
        notes_lines = []
        if conds:
            notes_lines.append("Conditions: " + "  •  ".join(conds))
        if flags:
            notes_lines.append("Risk flags: " + "  •  ".join(flags[:3]))
        if high_r:
            notes_lines.append(f"High-severity risks identified: {high_r} — review Economic Impact Report.")
        self._verdict_notes.set("\n".join(notes_lines))

        # Log verdict summary
        tag = "ok" if verdict == "APPROVED" else ("err" if verdict == "REJECTED" else "head")
        self._log(f"\n  Viability: {badge_text}", tag)
        self._log(f"  Payback: {payback:.1f} yrs  |  NPV: GHS {npv:,.0f}  |  ROI: {roi:.1f}%", tag)

    # ── Clear ─────────────────────────────────────────────────────────────────
    def _clear(self):
        self.var_region.set(DEFAULT_REGION)
        self._on_region_change()   # refreshes stats and PSH

        for var, default in [
            (self.var_lighting, "2.5"),
            (self.var_sockets,  "3.0"),
            (self.var_ac,       "4.0"),
            (self.var_eff,      "0.75"),
            (self.var_dod,      "0.80"),
            (self.var_auto,     "1"),
        ]:
            var.set(default)

        for card in [self.card_pv, self.card_panels, self.card_battery,
                     self.card_units, self.card_inv, self.card_load]:
            card.set("—")

        self._clear_log()
        self._log(f"Inputs reset to defaults  ({DEFAULT_REGION}).", "dim")
        self.status_var.set("Ready")


if __name__ == "__main__":
    try:
        from auth.dashboard_window import DashboardWindow

        # Single hidden root owns all windows and the event loop.
        root = tk.Tk()
        root.withdraw()
        root.title("Solar PV Designer Lite")

        def _start():
            """Show homepage; login is triggered from within it."""
            from auth.home_window import HomeWindow
            home = HomeWindow(root)
            root.wait_window(home)

            user = home.login_result
            if not user:
                root.destroy()   # user closed homepage without logging in — exit
                return

            _open_dashboard(user)

        def _open_dashboard(user):
            """Show dashboard; handle logout (back to homepage) or plain close (exit)."""
            dash = DashboardWindow(
                root, user,
                on_launch_designer=lambda: _launch_designer(user, dash),
                on_logout=_do_logout,
            )
            root.wait_window(dash)

            if getattr(dash, "do_logout", False):
                _do_logout()
            else:
                root.destroy()   # window closed normally — exit

        def _do_logout():
            """Return to homepage (which has the login button)."""
            _start()

        def _launch_designer(user, dash):
            """Hide dashboard, open designer; restore dashboard on close."""
            dash.withdraw()

            def _on_designer_close():
                try:
                    dash.deiconify()
                    # Refresh the designs-run counter shown in dashboard
                    if hasattr(dash, '_populate_table'):
                        dash._populate_table()
                except Exception:
                    pass

            designer = SolarPVApp(root, current_user=user, on_back=_on_designer_close)
            # Designer manages itself; dashboard will reappear on close.

        root.after(50, _start)
        root.mainloop()

    except Exception as _exc:
        import traceback
        _log_path = os.path.join(_app_dir(), "error.log")
        with open(_log_path, "w", encoding="utf-8") as _f:
            traceback.print_exc(file=_f)
        tk.Tk().withdraw()
        from tkinter import messagebox as _mb
        _mb.showerror("Startup Error",
                      f"The application failed to start.\n\nDetails saved to:\n{_log_path}")
        raise
