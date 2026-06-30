# new_boq_section_loop_routes.py
# 2026-06-21 -- Sectioned BOQ workflow patterned after the
# 1UGLS Auditorium sample.
#
# Real BOQ shape:
#   Floor -> BILL No. N (Preliminaries / Internal Wiring / Bonding & Earthing /
#            Fire Alarm / Data & Voice / Signal Comms / ...)
#     -> Section letter (A / B / C / ...) with section title
#       -> Optional sub-section label (I / II / III, e.g.
#          "I. Light and fan points")
#         -> Items 1, 2, 3, ... with Item No / Description / Qty /
#            Unit / Basic Rate / Rate / Amount
#
# Workflow:
#   1. From the floor page, "Open new section" -> section setup form
#      (picks Bill No, Section letter, Section name from a dropdown of
#      the standard 16 sections, optional sub-section label).
#   2. Section setup posts and redirects into the item-add LOOP page
#      whose heading is the section title. The user adds items in a
#      tight loop: pick from the catalogue dropdown or type a custom
#      line, set qty + basic rate, hit "Add & continue".
#   3. When the section is done, click "End section" -> back to the
#      floor view with the new section rendered.
#   4. Repeat for the next section in the same Bill, then move to the
#      next Bill, then the next floor.
#
# Floor Bills Summary (page accessible from floor view):
#   - Per-bill subtotals (BILL No. 1 PRELIMINARIES -> total, ...)
#   - SUBTOTAL across bills
#   - CONTINGENCIES at the floor contingency_pct (default 10)
#   - Total carried to General Summary  (per the sample wording)

# ----- Standard taxonomy ---------------------------------------------------

# Standard Bills used in electrical installation BOQs.
_BOQ_BILLS = [
    (1,  "PRELIMINARIES"),
    (2,  "INTERNAL ELECTRICAL WIRING"),
    (3,  "BONDING AND EARTHING"),
    (4,  "FIRE ALARM SYSTEM"),
    (5,  "DATA AND VOICE COMMUNICATIONS"),
    (6,  "SIGNAL COMMUNICATION SYSTEMS"),
    (7,  "LIGHTNING PROTECTION"),
    (8,  "EXTERNAL LIGHTING"),
    (9,  "SOLAR PV SYSTEM"),
    (10, "GENERATOR AND UPS"),
    (11, "TESTING AND COMMISSIONING"),
    (12, "DOCUMENTATION AND HANDOVER"),
]

# Common Section titles per Bill -- shown as a dropdown when opening a
# new section. The user can still override with a free-text title.
_BOQ_SECTION_TITLES = {
    1: [
        "Preliminary Items",
        "Site Establishment",
        "Insurance and Indemnities",
        "Mobilisation and Demobilisation",
    ],
    2: [
        "SWITCH BOARDS AND DISTRIBUTION BOARDS",
        "SUBFEEDER CABLES AND EARTHLEADS",
        "WIRING OF POINTS",
        "LUMINAIRES",
        "ACCESSORIES",
    ],
    3: [
        "BONDING AND EARTHING",
        "EARTH ELECTRODE NETWORK",
        "EQUIPOTENTIAL BONDING",
    ],
    4: [
        "WIRING OF FIRE POINTS",
        "FIRE PANEL AND ACCESSORIES",
        "EMERGENCY LIGHTING",
    ],
    5: [
        "WIRING OF POINTS",
        "DATA EQUIPMENT AND ACCESSORIES",
        "VOICE EQUIPMENT AND ACCESSORIES",
        "STRUCTURED CABLING",
    ],
    6: [
        "SMALL SIGNAL IP NETWORK",
        "EQUIPMENT AND ACCESSORIES",
        "CCTV SYSTEM",
        "ACCESS CONTROL",
        "PUBLIC ADDRESS SYSTEM",
    ],
    7: [
        "AIR TERMINATION NETWORK",
        "DOWN CONDUCTORS",
        "EARTH TERMINATION",
    ],
    8: [
        "POLES AND FITTINGS",
        "STREET LIGHTING LUMINAIRES",
        "EXTERNAL CABLES",
    ],
    9: [
        "PV MODULES AND MOUNTING",
        "INVERTERS",
        "BATTERIES AND CHARGE CONTROL",
        "DC AND AC PROTECTION",
        "STRING CABLING",
    ],
    10: [
        "GENERATOR SET",
        "AUTOMATIC TRANSFER SWITCH",
        "UPS UNIT",
        "FUEL AND EXHAUST",
    ],
    11: [
        "MAIN INSTALLATION TESTING",
        "EARTHING SYSTEM TESTING",
        "INSULATION TESTING",
        "FUNCTIONAL COMMISSIONING",
    ],
    12: [
        "AS-BUILT DRAWINGS",
        "TEST CERTIFICATES",
        "OPERATION AND MAINTENANCE MANUAL",
        "TRAINING",
    ],
}


def _boq_bills_dropdown():
    return [{"no": n, "name": name} for n, name in _BOQ_BILLS]


def _boq_lookup_bill_name(bill_no: int) -> str:
    for n, name in _BOQ_BILLS:
        if n == bill_no:
            return name
    return ""


def _boq_section_titles_for_bill(bill_no: int) -> list:
    return list(_BOQ_SECTION_TITLES.get(bill_no, []))


def _boq_next_section_letter(floor_id: int, bill_no: int) -> str:
    """Return the next available letter (A, B, C, ...) for the given
    floor + bill. Letters are scoped per Bill within a Floor so each
    Bill restarts at A."""
    with get_db() as c:
        rows = c.execute(
            "SELECT DISTINCT section_letter FROM boq_floor_items "
            "WHERE floor_id=? AND bill_no=? AND section_letter != '' "
            "ORDER BY section_letter",
            (floor_id, bill_no),
        ).fetchall()
    used = {(r["section_letter"] or "").strip().upper() for r in rows}
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if ch not in used:
            return ch
    return "Z"


def _boq_next_item_no(floor_id: int, bill_no: int, section_letter: str) -> str:
    """Return next item number ('1', '2', ...) within the section."""
    with get_db() as c:
        row = c.execute(
            "SELECT COALESCE(MAX(CAST(item_no_display AS INTEGER)),0) AS n "
            "FROM boq_floor_items "
            "WHERE floor_id=? AND bill_no=? AND section_letter=?",
            (floor_id, bill_no, section_letter),
        ).fetchone()
    return str(int((row["n"] if row else 0) or 0) + 1)


def _boq_safe_rate(basic, supply, install, oh, prf, cnt=0, vat=0, vat_in_basic=False):
    """Thin wrapper around boq_rate_v3.boq_rate_v3 -- the single source of
    truth for BOQ rate computation (2026-06-29 unification).

    Returns the per-unit total rate (basic + markup-only supply + markup-only
    install). ``cnt`` is accepted for backward-compat with old callsites but
    IGNORED (contingency was retired 2026-06-28).

    Formula (delegated to boq_rate_v3, revised 2026-06-30):
        effective_vat   = 0 if vat_in_basic else vat
        supply_amount   = basic * (supply + overhead + profit + effective_vat) / 100
        install_amount  = basic * install / 100
        total_rate      = basic + supply_amount + install_amount   (per unit)
    """
    from boq_rate_v3 import boq_rate_v3
    _supply_amt, _install_amt, total_rate = boq_rate_v3(
        basic, supply, install, oh, prf, vat, vat_in_basic
    )
    return total_rate


# ----- Routes --------------------------------------------------------------

@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/section/new", methods=["GET"])
@login_required
def boq_section_setup(pid, bid, fid):
    """Section setup form. Owner picks Bill, Section letter (default
    next free), Section title (dropdown of standards filtered by bill,
    plus 'Other' free text), and optional sub-section label."""
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    building = _boq_building_owned_or_404(bid, pid)
    floor = _boq_floor_owned_or_404(fid, bid)

    # Default Bill 2 (Internal Electrical Wiring) -- most common starting point.
    bill_no = request.args.get("bill_no", type=int) or 2
    bill_name = _boq_lookup_bill_name(bill_no)
    next_letter = _boq_next_section_letter(fid, bill_no)
    return render_template(
        "boq_floor_section_setup.html",
        user=current_user(),
        project=project, building=building, floor=floor,
        bills=_boq_bills_dropdown(),
        bill_no=bill_no, bill_name=bill_name,
        next_letter=next_letter,
        section_titles=_boq_section_titles_for_bill(bill_no),
    )


@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/section", methods=["POST"])
@login_required
def boq_section_open(pid, bid, fid):
    """Accept the section setup form, then redirect into the item-loop
    page. We don't persist a 'section' record on its own -- the (bill_no,
    section_letter, section_title) tuple lives on each item row. That
    keeps the schema simple: a section 'exists' iff at least one item
    has been added under it."""
    uid = session["user_id"]
    _boq_project_owned_or_404(pid, uid)
    _boq_building_owned_or_404(bid, pid)
    _boq_floor_owned_or_404(fid, bid)
    csrf_protect()
    f = request.form
    try:
        bill_no = int(f.get("bill_no") or 0)
    except ValueError:
        bill_no = 0
    if bill_no < 1:
        flash("Pick a Bill No. for this section.", "warning")
        return redirect(url_for("boq_section_setup", pid=pid, bid=bid, fid=fid))
    bill_name = (f.get("bill_name") or _boq_lookup_bill_name(bill_no)).strip()[:120]
    letter = (f.get("section_letter") or _boq_next_section_letter(fid, bill_no)).strip().upper()[:8]
    title  = (f.get("section_title") or "").strip()[:160]
    if not title:
        flash("Pick or enter a section title.", "warning")
        return redirect(url_for("boq_section_setup", pid=pid, bid=bid, fid=fid, bill_no=bill_no))
    subsec = (f.get("subsection_label") or "").strip()[:20]
    # Default flow = grid (bulk auto-populated from section catalogue, 90% faster).
    # Keep boq_section_loop as a fallback for one-off custom additions.
    return redirect(url_for(
        "boq_section_grid",
        pid=pid, bid=bid, fid=fid,
        bill_no=bill_no, letter=letter,
        title=title, bill_name=bill_name, sub=subsec,
    ))


@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/bill/<int:bill_no>/section/<letter>", methods=["GET"])
@login_required
def boq_section_loop(pid, bid, fid, bill_no, letter):
    """Item-add LOOP for a section. The page heading is the section
    title. The user adds items one after the other; each Add posts to
    boq_section_add_item and redirects back here so the loop continues
    without leaving the URL. 'End section' returns to the floor view."""
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    building = _boq_building_owned_or_404(bid, pid)
    floor = _boq_floor_owned_or_404(fid, bid)
    letter = (letter or "").upper()[:8]
    title = (request.args.get("title") or "").strip()[:160]
    bill_name = (request.args.get("bill_name") or _boq_lookup_bill_name(bill_no)).strip()[:120]
    subsec = (request.args.get("sub") or "").strip()[:20]
    if not title:
        # If user landed here without a title, fall back to the bill name.
        title = bill_name

    # Existing items in this section -- show them on top so the user
    # can see what's been added in the loop so far.
    with get_db() as c:
        items = c.execute(
            "SELECT i.*, "
            "       b.basic_price AS bu_basic, "
            "       b.supply_rate AS bu_supply, "
            "       b.install_rate AS bu_install "
            "FROM boq_floor_items i "
            "LEFT JOIN boq_floor_rate_buildup b ON b.floor_item_id=i.id "
            "WHERE i.floor_id=? AND i.bill_no=? AND i.section_letter=? "
            "ORDER BY i.id",
            (fid, bill_no, letter),
        ).fetchall()

    # Catalogue dropdown -- restrict to active, public-visible products.
    # User can still type a custom item if none match.
    with get_db() as c:
        catalogue = c.execute(
            "SELECT id, name, brand, model, spec, unit, price_usd "
            "FROM equipment_catalog "
            "WHERE COALESCE(is_active,1)=1 "
            "  AND COALESCE(is_public_visible,1)=1 "
            "ORDER BY name LIMIT 400"
        ).fetchall()

    next_item_no = _boq_next_item_no(fid, bill_no, letter)

    return render_template(
        "boq_floor_section_loop.html",
        user=current_user(),
        project=project, building=building, floor=floor,
        bill_no=bill_no, bill_name=bill_name,
        section_letter=letter, section_title=title,
        subsection_label=subsec,
        items=items,
        catalogue=catalogue,
        next_item_no=next_item_no,
    )


@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/bill/<int:bill_no>/section/<letter>/items", methods=["POST"])
@login_required
def boq_section_add_item(pid, bid, fid, bill_no, letter):
    """Append one item to the open section, redirect back to the loop
    URL so the user can keep adding."""
    uid = session["user_id"]
    _boq_project_owned_or_404(pid, uid)
    _boq_building_owned_or_404(bid, pid)
    _boq_floor_owned_or_404(fid, bid)
    csrf_protect()
    f = request.form
    letter = (letter or "").upper()[:8]
    title    = (f.get("section_title") or "").strip()[:160]
    bill_name= (f.get("bill_name")     or _boq_lookup_bill_name(bill_no)).strip()[:120]
    subsec   = (f.get("subsection_label") or "").strip()[:20]

    def _num(name, default=0.0):
        try:
            v = f.get(name, "")
            return float(v) if v not in (None, "",) else float(default)
        except (TypeError, ValueError):
            return float(default)

    def _pct(name):
        return max(0.0, min(100.0, _num(name, 0.0)))

    # Catalogue pick OR free text. catalogue_id=0 means free text.
    try:
        catalogue_id = int(f.get("catalogue_id") or 0)
    except ValueError:
        catalogue_id = 0
    desc_override = (f.get("description") or "").strip()[:500]
    unit          = (f.get("unit") or "").strip()[:20]
    spec_override = (f.get("specification") or "").strip()
    basic         = max(0.0, _num("basic_price", 0.0))
    qty           = max(0.0, _num("qty", 1.0))

    # If catalogue line was picked, fill in description / unit / basic
    # from the catalogue when those fields were left blank.
    if catalogue_id > 0:
        with get_db() as c:
            row = c.execute(
                "SELECT name, spec, unit, price_usd FROM equipment_catalog WHERE id=?",
                (catalogue_id,),
            ).fetchone()
        if row:
            desc_override = desc_override or (row["name"] or "")
            spec_override = spec_override or (row["spec"] or "")
            unit          = unit or (row["unit"] or "No.")
            if not basic:
                basic = float(row["price_usd"] or 0)

    if not desc_override:
        flash("Description is required.", "warning")
        return redirect(_section_loop_url(pid, bid, fid, bill_no, letter, title, bill_name, subsec))
    if not unit:
        unit = "No."

    # Rate engine v3 (2026-06-28): supply_pct + install_pct are PERCENTAGES.
    oh, prf, vat = _pct("overhead_pct"), _pct("profit_pct"), _pct("vat_pct")
    supply_pct  = _pct("supply_pct")
    install_pct = _pct("install_pct")
    vat_in_basic = 1 if f.get("vat_in_basic") else 0
    from boq_rate_v3 import boq_rate_v3
    supply, install, final_rate = boq_rate_v3(
        basic, supply_pct, install_pct, oh, prf, vat,
        vat_in_basic=bool(vat_in_basic))
    total = qty * final_rate
    if final_rate <= 0:
        flash("Rate must be > 0. Enter a basic price.", "warning")
        return redirect(_section_loop_url(pid, bid, fid, bill_no, letter, title, bill_name, subsec))

    item_no_disp = _boq_next_item_no(fid, bill_no, letter)
    remarks = (f.get("remarks") or "").strip()[:500]

    with get_db() as c:
        cur = c.execute(
            "INSERT INTO boq_floor_items "
            "(floor_id, building_id, project_id, user_id, section, subsection, "
            " library_item_id, supplier_id, item_no, description, specification, "
            " unit, qty, final_built_up_rate, total_amount, remarks, "
            " source_type, approval_status, "
            " bill_no, bill_name, section_letter, subsection_label, item_no_display) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (fid, bid, pid, uid, title.lower()[:80], "",
             catalogue_id or None, None, item_no_disp,
             desc_override, spec_override, unit, qty, final_rate, total, remarks,
             ("master_library" if catalogue_id > 0 else "custom_current_boq"),
             "project_only",
             bill_no, bill_name, letter, subsec, item_no_disp),
        )
        item_id = int(cur.lastrowid or 0)
        c.execute(
            "INSERT INTO boq_floor_rate_buildup "
            "(floor_item_id, project_id, user_id, basic_price, "
            " supply_pct, install_pct, supply_rate, install_rate, "
            " overhead_pct, profit_pct, contingency_pct, vat_pct, "
            " vat_in_basic, final_built_up_rate, total_amount) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (item_id, pid, uid, basic,
             supply_pct, install_pct, supply, install,
             oh, prf, 0, vat, vat_in_basic, final_rate, total),
        )
        c.execute("UPDATE boq_projects  SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (pid,))
        c.execute("UPDATE boq_buildings SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (bid,))
        c.execute("UPDATE boq_floors    SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (fid,))
    try:
        from new_boq_hierarchy_schema import boq_audit
        boq_audit(get_db, uid, "boq_section_item_added", "boq_floor_item", item_id,
                  f"bill={bill_no} sec={letter} item={item_no_disp} rate={final_rate:.2f}")
    except Exception:
        pass

    # Decide where to go next: "Add & continue" stays in the loop;
    # "End section" returns to the floor; "End section & open next"
    # opens a new section under the same bill.
    nxt = (f.get("next_action") or "continue").strip()
    if nxt == "end":
        flash(f"Section {letter}. {title} closed -- item {item_no_disp} added.", "success")
        return redirect(url_for("boq_floor_view", pid=pid, bid=bid, fid=fid))
    if nxt == "end_open_next":
        return redirect(url_for("boq_section_setup", pid=pid, bid=bid, fid=fid, bill_no=bill_no))
    return redirect(_section_loop_url(pid, bid, fid, bill_no, letter, title, bill_name, subsec))


def _section_loop_url(pid, bid, fid, bill_no, letter, title, bill_name, sub):
    return url_for(
        "boq_section_loop",
        pid=pid, bid=bid, fid=fid,
        bill_no=bill_no, letter=letter,
        title=title, bill_name=bill_name, sub=sub,
    )


@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/summary")
@login_required
def boq_floor_summary(pid, bid, fid):
    """Per-floor Bills Summary -- matches the auditorium sample's
    'GROUND FLOOR' summary table. Lists each Bill's subtotal, adds
    Contingencies at the floor's contingency_pct (default 10), and
    yields 'Total carried to General Summary'."""
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    building = _boq_building_owned_or_404(bid, pid)
    floor = _boq_floor_owned_or_404(fid, bid)

    with get_db() as c:
        per_bill = c.execute(
            "SELECT COALESCE(bill_no,0) AS bill_no, "
            "       COALESCE(bill_name,'') AS bill_name, "
            "       COALESCE(SUM(total_amount),0) AS subtotal "
            "FROM boq_floor_items "
            "WHERE floor_id=? "
            "GROUP BY bill_no, bill_name "
            "ORDER BY bill_no",
            (fid,),
        ).fetchall()

    bills = [
        {
            "bill_no":   int(r["bill_no"]   or 0),
            "bill_name": (r["bill_name"]    or _boq_lookup_bill_name(int(r["bill_no"] or 0)) or "OTHER"),
            "subtotal":  float(r["subtotal"] or 0),
        }
        for r in per_bill
    ]
    subtotal = sum(b["subtotal"] for b in bills)
    cont_pct = float((floor["contingency_pct"] if "contingency_pct" in floor.keys() else 10) or 10)
    contingency = subtotal * cont_pct / 100.0
    carried = subtotal + contingency
    return render_template(
        "boq_floor_summary.html",
        user=current_user(),
        project=project, building=building, floor=floor,
        bills=bills, subtotal=subtotal,
        contingency_pct=cont_pct, contingency=contingency,
        carried=carried,
    )


@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/contingency", methods=["POST"])
@login_required
def boq_floor_set_contingency(pid, bid, fid):
    uid = session["user_id"]
    _boq_project_owned_or_404(pid, uid)
    _boq_building_owned_or_404(bid, pid)
    _boq_floor_owned_or_404(fid, bid)
    csrf_protect()
    try:
        pct = float(request.form.get("contingency_pct", 10))
    except (TypeError, ValueError):
        pct = 10.0
    pct = max(0.0, min(100.0, pct))
    with get_db() as c:
        c.execute("UPDATE boq_floors SET contingency_pct=? WHERE id=?", (pct, fid))
    flash(f"Contingency set to {pct}%.", "success")
    return redirect(url_for("boq_floor_summary", pid=pid, bid=bid, fid=fid))
