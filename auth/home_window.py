# auth/home_window.py
# Public homepage — shown on app start.
# Displays a live solar PV industry news feed (refreshed every 48 hrs)
# and a Login button.

import tkinter as tk
from tkinter import ttk
import threading
import webbrowser

# ── Palette ───────────────────────────────────────────────────────────────────
BG       = "#0d0d1a"
PANEL    = "#1a1a2e"
CARD     = "#12121f"
CARD2    = "#1e1e35"
ACCENT   = "#f5a623"
ACCENT2  = "#4fc3f7"
TEXT     = "#e0e0e0"
TEXT_DIM = "#888888"
SUCCESS  = "#66bb6a"
ERROR    = "#ef5350"
BORDER   = "#2a2a4a"
WARN     = "#ffd54f"
PURPLE   = "#ce93d8"

# ── Category colours ──────────────────────────────────────────────────────────
CAT_COLORS = {
    "Industry":  "#4fc3f7",
    "Products":  "#f5a623",
    "Market":    "#66bb6a",
    "Policy":    "#ce93d8",
    "Africa":    "#ff7043",
}
ALL_CATS = ["All"] + list(CAT_COLORS.keys())

# ── Static fallback news (shown instantly while live feed loads) ──────────────
_STATIC_NEWS = [
    {
        "cat": "Market",
        "title": "Solar Panel Prices Hit Historic Low of $0.09/Wp Ex-Factory",
        "source": "PV Magazine",
        "date": "April 11, 2026",
        "summary": (
            "Chinese module manufacturers have driven average ex-factory spot prices "
            "below $0.09 per watt-peak for the first time, with major producers including "
            "LONGi, JA Solar, and Jinko Solar reporting record shipment volumes in Q1 2026. "
            "Analysts forecast further declines as new cell capacity comes online mid-year."
        ),
        "link": "",
    },
    {
        "cat": "Products",
        "title": "LONGi Hi-MO 9 Achieves 750Wp in Commercial-Scale Module",
        "source": "Solar Power World",
        "date": "April 9, 2026",
        "summary": (
            "LONGi Green Energy has unveiled its Hi-MO 9 module series reaching 750Wp using "
            "its latest HPBC (Hybrid Passivated Back Contact) cell technology. The module "
            "delivers a module efficiency of 24.8%, setting a new benchmark for utility and "
            "commercial rooftop applications. Available in Q3 2026."
        ),
        "link": "",
    },
    {
        "cat": "Africa",
        "title": "Ghana Doubles Renewable Energy Target to 10% of Grid Mix by 2030",
        "source": "Africa Energy Portal",
        "date": "April 8, 2026",
        "summary": (
            "The Ghana Energy Commission has revised its national renewable energy target "
            "upward from 5% to 10% of total electricity generation by 2030. The policy "
            "shift is backed by an IFC-supported financing facility targeting 500 MW of "
            "distributed solar and mini-grid installations across all 16 regions."
        ),
        "link": "",
    },
    {
        "cat": "Industry",
        "title": "Global Cumulative Solar PV Capacity Crosses 3 Terawatts",
        "source": "IEA Solar Report",
        "date": "April 7, 2026",
        "summary": (
            "The International Energy Agency confirmed that global installed solar PV capacity "
            "surpassed 3 TW in early 2026, a milestone reached just three years after the 2 TW "
            "mark. China accounts for 40% of installed base, with Europe, USA, and India each "
            "contributing 10-12%. Sub-Saharan Africa stands at 12 GW total."
        ),
        "link": "",
    },
    {
        "cat": "Products",
        "title": "Victron Energy MultiPlus-II 48/5000 Gets Enhanced SolarEdge BMS Integration",
        "source": "Victron Blog",
        "date": "April 6, 2026",
        "summary": (
            "Victron Energy has released firmware v500 for the MultiPlus-II series, adding "
            "native integration with the SolarEdge Home Battery and improved CAN-bus "
            "communication for third-party BMS units. The update also brings Dynamic ESS "
            "scheduling for time-of-use tariff optimisation — relevant to markets with "
            "block tariff structures such as Ghana ECG."
        ),
        "link": "",
    },
    {
        "cat": "Policy",
        "title": "ECOWAS Adopts Harmonised Net Metering Framework for 15 Member States",
        "source": "ECREEE",
        "date": "April 5, 2026",
        "summary": (
            "The ECOWAS Centre for Renewable Energy has published a model net metering "
            "regulation that member states are expected to adopt by end of 2026. The framework "
            "sets a standardised bidirectional tariff floor, streamlined interconnection "
            "standards, and a dispute resolution mechanism — removing a key barrier for "
            "rooftop solar deployment across West Africa."
        ),
        "link": "",
    },
    {
        "cat": "Products",
        "title": "Pylontech Launches Force H2 10kWh Stackable LiFePO4 Battery",
        "source": "Energy Storage Journal",
        "date": "April 4, 2026",
        "summary": (
            "Pylontech has introduced the Force H2, a 10 kWh 48V LiFePO4 battery module "
            "designed for residential and light-commercial off-grid systems. The unit offers "
            "a 10-year warranty at 6,000 cycles to 80% DoD, built-in BMS, and CANbus/RS485 "
            "communications compatible with leading hybrid inverters including Growatt, "
            "Goodwe, and Victron."
        ),
        "link": "",
    },
    {
        "cat": "Industry",
        "title": "Canadian Solar Reports Record 11.8 GW Module Shipments in FY2025",
        "source": "PV Tech",
        "date": "April 3, 2026",
        "summary": (
            "Canadian Solar posted full-year 2025 module shipments of 11.8 GW, a 22% increase "
            "on the prior year, driven by strong demand in emerging markets and the USA. The "
            "company's TOPCon HiKu7 modules now represent 70% of shipments, displacing "
            "older PERC technology. Gross margin improved to 16.4%."
        ),
        "link": "",
    },
    {
        "cat": "Products",
        "title": "Growatt NOAH 2000 Portable Power Station Targets Off-Grid Africa",
        "source": "Growatt Newsroom",
        "date": "April 2, 2026",
        "summary": (
            "Growatt has launched the NOAH 2000 — a 2 kWh LiFePO4 portable energy storage "
            "system with a 2.4 kW AC output, designed for off-grid homes and small businesses "
            "in markets with unreliable grid supply. The unit integrates a 600W MPPT solar "
            "input and features a companion app for real-time monitoring."
        ),
        "link": "",
    },
    {
        "cat": "Africa",
        "title": "Off-Grid Solar Market in Sub-Saharan Africa Grows 34% Year-on-Year",
        "source": "GOGLA Annual Report",
        "date": "March 31, 2026",
        "summary": (
            "The Global Off-Grid Lighting Association reports that off-grid solar product "
            "sales in sub-Saharan Africa grew 34% year-on-year in 2025, with sales of "
            "solar home systems above 10Wp increasing fastest. Nigeria, Kenya, Tanzania, "
            "Ethiopia, and Ghana ranked as the top five markets by units sold."
        ),
        "link": "",
    },
    {
        "cat": "Products",
        "title": "JA Solar DeepBlue 4.0 Pro Series Reaches 625Wp with n-Type TOPCon",
        "source": "JA Solar Press",
        "date": "March 28, 2026",
        "summary": (
            "JA Solar has launched the DeepBlue 4.0 Pro module series featuring its n-Type "
            "TOPCon cell technology, achieving 625Wp per panel with a 22.8% module efficiency. "
            "The series offers a 30-year linear power warranty with no more than 1% first-year "
            "degradation and 0.35%/year thereafter."
        ),
        "link": "",
    },
    {
        "cat": "Policy",
        "title": "Ghana PURC Approves 15% Electricity Tariff Review for 2026-2027",
        "source": "Graphic Business Ghana",
        "date": "March 25, 2026",
        "summary": (
            "Ghana's Public Utilities Regulatory Commission has approved a 15% blended "
            "electricity tariff increase effective May 2026, affecting residential, "
            "commercial and industrial customers. The review cites rising fuel costs and "
            "infrastructure maintenance, improving the case for rooftop solar."
        ),
        "link": "",
    },
    {
        "cat": "Market",
        "title": "Polysilicon Spot Price Falls to $4.50/kg — Lowest in a Decade",
        "source": "InfoLink Consulting",
        "date": "March 10, 2026",
        "summary": (
            "Polysilicon spot prices have declined to $4.50 per kilogram, driven by a surge "
            "in Chinese production capacity that has created a significant supply overhang. "
            "The price collapse is now feeding through to module prices globally, with analysts "
            "at Bloomberg NEF projecting an average module price of $0.08/Wp by end of 2026."
        ),
        "link": "",
    },
    {
        "cat": "Industry",
        "title": "Jinko Solar Ships 100 GW Cumulative — First Manufacturer to Hit Milestone",
        "source": "Jinko Solar IR",
        "date": "March 5, 2026",
        "summary": (
            "Jinko Solar has announced it has shipped a cumulative 100 GW of solar modules "
            "since its founding — the first manufacturer in the industry to reach this "
            "milestone. Jinko plans to expand its African distribution network with "
            "regional warehouses in Ghana, Kenya, and South Africa."
        ),
        "link": "",
    },
]


class HomeWindow(tk.Toplevel):
    """Public homepage — live news feed + Login button.
    Sets self.login_result to the user dict after successful login,
    or None if window is closed without logging in.
    """

    def __init__(self, master):
        super().__init__(master)
        self.login_result  = None
        self._active_cat   = "All"
        self._articles     = list(_STATIC_NEWS)   # shown immediately
        self._fetched_at   = ""
        self._is_loading   = False

        self.title("Solar PV Designer Lite")
        self.state("zoomed")
        self.configure(bg=BG)
        self.resizable(True, True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()

        # Kick off background news load after window appears
        self.after(300, self._start_bg_load)

    # ── Background news loading ───────────────────────────────────────────────
    def _start_bg_load(self, force=False):
        if self._is_loading:
            return
        self._is_loading = True
        if hasattr(self, "_refresh_btn"):
            self._refresh_btn.config(state="disabled", text="⟳  Loading...")
        if hasattr(self, "_status_var"):
            self._status_var.set("Checking for latest news...")
        threading.Thread(
            target=self._bg_load_news,
            args=(force,),
            daemon=True
        ).start()

    def _bg_load_news(self, force=False):
        try:
            from auth.news_fetcher import load_news
            articles, fetched_at = load_news(force_refresh=force)
            if articles:
                self._articles   = articles
                self._fetched_at = fetched_at
        except Exception:
            pass   # keep static fallback
        self._is_loading = False
        try:
            self.after(0, self._on_news_ready)
        except Exception:
            pass   # window may have been closed

    def _on_news_ready(self):
        # Update hero count chip
        if hasattr(self, "_news_count_var"):
            self._news_count_var.set(str(len(self._articles)))

        # Update footer/status timestamp
        ts = self._fetched_at[:19] if self._fetched_at else "static fallback"
        if hasattr(self, "_status_var"):
            self._status_var.set(f"Last updated: {ts}")

        # Re-enable refresh button
        if hasattr(self, "_refresh_btn"):
            self._refresh_btn.config(state="normal", text="⟳  Refresh")

        self._render_cards()

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build(self):
        self._build_header()
        self._build_hero()
        self._build_filter_bar()
        self._build_news_section()
        self._build_footer()

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = tk.Frame(self, bg=ACCENT, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="☀  Solar PV Designer Lite",
                 font=("Segoe UI", 15, "bold"),
                 bg=ACCENT, fg="#1e1e2e").pack(side="left", padx=22, pady=12)

        tk.Label(hdr, text="Off-Grid System Sizing Platform  |  Ghana",
                 font=("Segoe UI", 9), bg=ACCENT, fg="#4a3000"
                 ).pack(side="left", padx=(0, 20), pady=12)

        tk.Button(
            hdr,
            text="  🔑  Login / Get Started  ",
            font=("Segoe UI", 11, "bold"),
            bg="#1e1e2e", fg=ACCENT,
            activebackground="#12121f", activeforeground=ACCENT,
            relief="flat", cursor="hand2", padx=14, pady=6,
            command=self._open_login,
        ).pack(side="right", padx=18, pady=10)

    # ── Hero strip ────────────────────────────────────────────────────────────
    def _build_hero(self):
        hero = tk.Frame(self, bg="#0a0a1a", height=110)
        hero.pack(fill="x")
        hero.pack_propagate(False)

        inner = tk.Frame(hero, bg="#0a0a1a")
        inner.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(inner,
                 text="Solar PV Industry News & Market Insights",
                 font=("Segoe UI", 18, "bold"),
                 bg="#0a0a1a", fg=TEXT).pack()

        tk.Label(inner,
                 text=(
                     "Latest updates on solar panels, inverters, batteries, manufacturers, "
                     "market trends, policy and Africa energy news"
                 ),
                 font=("Segoe UI", 10), bg="#0a0a1a", fg=TEXT_DIM).pack(pady=(4, 0))

        # Stats strip — article count is dynamic
        self._news_count_var = tk.StringVar(value=str(len(self._articles)))
        stats_row = tk.Frame(inner, bg="#0a0a1a")
        stats_row.pack(pady=(10, 0))

        static_stats = [
            ("Categories",    str(len(CAT_COLORS))),
            ("Brands Covered", "12+"),
            ("Refresh Cycle", "48 hrs"),
        ]

        # Dynamic article count chip (first)
        chip = tk.Frame(stats_row, bg=PANEL, padx=12, pady=4,
                        highlightbackground=BORDER, highlightthickness=1)
        chip.pack(side="left", padx=5)
        tk.Label(chip, textvariable=self._news_count_var,
                 font=("Segoe UI", 11, "bold"),
                 bg=PANEL, fg=ACCENT2).pack()
        tk.Label(chip, text="News Articles",
                 font=("Segoe UI", 7),
                 bg=PANEL, fg=TEXT_DIM).pack()

        for label, value in static_stats:
            chip = tk.Frame(stats_row, bg=PANEL, padx=12, pady=4,
                            highlightbackground=BORDER, highlightthickness=1)
            chip.pack(side="left", padx=5)
            tk.Label(chip, text=value, font=("Segoe UI", 11, "bold"),
                     bg=PANEL, fg=ACCENT2).pack()
            tk.Label(chip, text=label, font=("Segoe UI", 7),
                     bg=PANEL, fg=TEXT_DIM).pack()

    # ── Category filter bar ───────────────────────────────────────────────────
    def _build_filter_bar(self):
        bar = tk.Frame(self, bg=PANEL, height=48)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        inner = tk.Frame(bar, bg=PANEL)
        inner.pack(side="left", padx=18, fill="y")

        tk.Label(inner, text="FILTER:", font=("Segoe UI", 8, "bold"),
                 bg=PANEL, fg=TEXT_DIM).pack(side="left", pady=14, padx=(0, 10))

        self._cat_buttons = {}
        for cat in ALL_CATS:
            color = CAT_COLORS.get(cat, ACCENT2) if cat != "All" else TEXT
            btn = tk.Button(
                inner, text=cat,
                font=("Segoe UI", 9, "bold"),
                bg=CARD if cat != "All" else ACCENT2,
                fg="#0d0d1a" if cat == "All" else color,
                activebackground=BORDER,
                relief="flat", cursor="hand2", padx=12, pady=4,
                command=lambda c=cat: self._filter(c),
            )
            btn.pack(side="left", padx=3, pady=10)
            self._cat_buttons[cat] = btn

        # Right side: count label + status + refresh button
        right = tk.Frame(bar, bg=PANEL)
        right.pack(side="right", padx=10, fill="y")

        self._refresh_btn = tk.Button(
            right,
            text="⟳  Refresh",
            font=("Segoe UI", 8, "bold"),
            bg=CARD, fg=ACCENT2,
            activebackground=BORDER,
            relief="flat", cursor="hand2", padx=10, pady=4,
            command=lambda: self._start_bg_load(force=True),
        )
        self._refresh_btn.pack(side="right", padx=(6, 0), pady=10)

        self._status_var = tk.StringVar(value="Loading live feed...")
        tk.Label(right, textvariable=self._status_var,
                 font=("Segoe UI", 8), bg=PANEL, fg=TEXT_DIM
                 ).pack(side="right", padx=(0, 6), pady=14)

        self._count_var = tk.StringVar(value=f"{len(self._articles)} articles")
        tk.Label(bar, textvariable=self._count_var,
                 font=("Segoe UI", 9), bg=PANEL, fg=TEXT_DIM
                 ).pack(side="left", padx=0, pady=14)

    def _filter(self, cat):
        self._active_cat = cat
        for c, btn in self._cat_buttons.items():
            is_active = (c == cat)
            col = CAT_COLORS.get(c, ACCENT2) if c != "All" else TEXT
            btn.config(
                bg=col if is_active else CARD,
                fg="#0d0d1a" if is_active else (col if c != "All" else TEXT_DIM),
            )
        self._render_cards()

    # ── Scrollable news grid ──────────────────────────────────────────────────
    def _build_news_section(self):
        wrapper = tk.Frame(self, bg=BG)
        wrapper.pack(fill="both", expand=True)
        wrapper.rowconfigure(0, weight=1)
        wrapper.columnconfigure(0, weight=1)

        vscroll = ttk.Scrollbar(wrapper, orient="vertical")
        vscroll.grid(row=0, column=1, sticky="ns")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Home.Vertical.TScrollbar",
                         troughcolor=BG, background=BORDER,
                         arrowcolor=TEXT_DIM, bordercolor=BG)

        self._canvas = tk.Canvas(wrapper, bg=BG, highlightthickness=0,
                                  yscrollcommand=vscroll.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.config(command=self._canvas.yview)

        self._news_frame = tk.Frame(self._canvas, bg=BG)
        self._win_id = self._canvas.create_window(
            (0, 0), window=self._news_frame, anchor="nw")

        self._news_frame.bind(
            "<Configure>",
            lambda e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))

        self._canvas.bind(
            "<Configure>",
            lambda e: (
                self._canvas.itemconfig(self._win_id, width=e.width),
                self._render_cards(),
            ))

        self._canvas.bind_all("<MouseWheel>",
            lambda e: self._canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        self._news_frame.columnconfigure(0, weight=1)
        self._news_frame.columnconfigure(1, weight=1)

        self._render_cards()

    def _render_cards(self):
        """Clear and rebuild the news card grid for the active category."""
        for w in self._news_frame.winfo_children():
            w.destroy()

        items = (self._articles if self._active_cat == "All"
                 else [n for n in self._articles if n.get("cat") == self._active_cat])

        self._count_var.set(f"{len(items)} article{'s' if len(items) != 1 else ''}")

        if not items:
            tk.Label(self._news_frame,
                     text="No articles in this category yet.\nCheck back after the next refresh.",
                     font=("Segoe UI", 12), bg=BG, fg=TEXT_DIM,
                     justify="center"
                     ).grid(row=0, column=0, columnspan=2, pady=40)
        else:
            for i, item in enumerate(items):
                card = self._make_card(self._news_frame, item)
                card.grid(row=i // 2, column=i % 2,
                          sticky="nsew", padx=10, pady=6)

            if len(items) % 2 == 1:
                last = self._news_frame.grid_slaves(
                    row=(len(items) - 1) // 2, column=0)
                if last:
                    last[0].grid_configure(columnspan=2)

        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        self._canvas.yview_moveto(0)

    def _make_card(self, parent, item):
        cat   = item.get("cat", "Industry")
        color = CAT_COLORS.get(cat, ACCENT2)
        link  = item.get("link", "").strip()

        outer = tk.Frame(parent, bg=BORDER, padx=1, pady=1)

        card = tk.Frame(outer, bg=CARD2, padx=16, pady=14)
        card.pack(fill="both", expand=True)

        # Top row: category badge + date
        top = tk.Frame(card, bg=CARD2)
        top.pack(fill="x")

        tk.Label(top, text=f"  {cat.upper()}  ",
                 font=("Segoe UI", 7, "bold"),
                 bg=color, fg="#0d0d1a",
                 padx=6, pady=2).pack(side="left")

        tk.Label(top, text=item.get("date", ""),
                 font=("Segoe UI", 8), bg=CARD2, fg=TEXT_DIM
                 ).pack(side="right")

        # Coloured accent line
        tk.Frame(card, bg=color, height=2).pack(fill="x", pady=(8, 10))

        # Title
        tk.Label(card, text=item.get("title", ""),
                 font=("Segoe UI", 11, "bold"),
                 bg=CARD2, fg=TEXT,
                 wraplength=460, justify="left", anchor="w"
                 ).pack(fill="x")

        # Source + "Read More" on same row
        src_row = tk.Frame(card, bg=CARD2)
        src_row.pack(fill="x", pady=(4, 6))

        tk.Label(src_row, text=f"📰  {item.get('source', '')}",
                 font=("Segoe UI", 8), bg=CARD2, fg=color
                 ).pack(side="left")

        if link:
            lnk = tk.Label(src_row, text="Read More →",
                           font=("Segoe UI", 8, "underline"),
                           bg=CARD2, fg=ACCENT2, cursor="hand2")
            lnk.pack(side="right")
            lnk.bind("<Button-1>", lambda e, u=link: webbrowser.open(u))
            lnk.bind("<Enter>", lambda e, w=lnk: w.config(fg=ACCENT))
            lnk.bind("<Leave>", lambda e, w=lnk: w.config(fg=ACCENT2))

        # Summary
        tk.Label(card, text=item.get("summary", ""),
                 font=("Segoe UI", 9), bg=CARD2, fg=TEXT_DIM,
                 wraplength=460, justify="left", anchor="w"
                 ).pack(fill="x")

        return outer

    # ── Footer ────────────────────────────────────────────────────────────────
    def _build_footer(self):
        ftr = tk.Frame(self, bg=PANEL, height=34)
        ftr.pack(fill="x", side="bottom")
        ftr.pack_propagate(False)

        tk.Label(ftr,
                 text="Solar PV Designer Lite  ·  Off-Grid System Sizing Platform  ·  Ghana",
                 font=("Segoe UI", 8), bg=PANEL, fg=TEXT_DIM
                 ).pack(side="left", padx=16)

        tk.Label(ftr,
                 text="Live RSS feed  ·  Refreshed every 48 hours  ·  Click 'Read More' to visit source",
                 font=("Segoe UI", 8), bg=PANEL, fg=TEXT_DIM
                 ).pack(side="right", padx=16)

    # ── Login trigger ─────────────────────────────────────────────────────────
    def _open_login(self):
        from auth.login_window import LoginWindow
        login = LoginWindow(self)
        self.wait_window(login)

        if login.result_user:
            self.login_result = login.result_user
            self.destroy()

    def _on_close(self):
        self.login_result = None
        self.destroy()
