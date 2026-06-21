# new_boq_section_grid_routes.py
# 2026-06-21 -- Section GRID editor for fast BOQ data entry.
#
# Goal (owner directive): cut the time to write a BOQ like the auditorium
# sample by 90%. The form heading IS the section heading; each line's
# Description field is a DROPDOWN scoped to that section's item catalogue.
# Picking a description auto-fills Unit + Basic Rate -- owner just types
# the Qty.
#
# Workflow:
#   1. From the floor view, "Open new section" -> section setup form.
#   2. Section setup posts and redirects into the GRID editor.
#   3. The GRID page is titled with the Section heading. It shows the
#      catalogue of typical items for that section as a dropdown on every
#      row; picking auto-fills unit + basic. The owner enters Qty for
#      each line, leaves blank rows blank, and clicks "Save all".
#   4. POST bulk-inserts every non-empty row in one transaction.
#
# The catalogue mirrors the 1UGLS Auditorium sample so all the typical
# Bill 2 (Internal Electrical Wiring), Bill 3 (Bonding & Earthing),
# Bill 4 (Fire Alarm), Bill 5 (Data & Voice) and Bill 6 (Signal Comms)
# items are one click away.


# ----- Section item catalogue ---------------------------------------------

# Schema for each entry:
#   ("Description", "Unit", basic_price)
#
# Section keys must match exactly (case-insensitive) what the section
# setup form posts as "section_title". The lookup also tries the upper
# case form so the owner can pick either casing.

_BOQ_SECTION_ITEM_CATALOG = {

    # ===== Bill 2 -- INTERNAL ELECTRICAL WIRING =========================
    "SWITCH BOARDS AND DISTRIBUTION BOARDS": [
        ("6-way TPN Memshield MCCB Distribution Panel Board c/w 400A Incomer", "Nos.", 19800),
        ("6-way TPN Memshield MCB Distribution Board c/w 200A INT. switch",    "Nos.", 15500),
        ("6-way TPN Memshield MCB Distribution Board c/w 125A INT. switch",    "Nos.",  8500),
        ("6-way TPN Memshield MCB Distribution Board c/w 100A INT. switch",    "Nos.",  6800),
        ("6-way TPN Memshield MCB Distribution Board c/w 63A INT. switch",     "Nos.",  3308.81),
        ("6-way TPN Memshield MCB Distribution Board c/w 32A INT. switch",     "Nos.",  3309.81),
        ("4-way TPN Memshield MCB Distribution Board c/w 32A INT. switch",     "Nos.",  3200),
        ("8-way SPN Memshield MCB Distribution Board c/w 63A INT. switch",     "Nos.",  2800),
        ("12-way SPN Memshield MCB Distribution Board c/w 100A INT. switch",   "Nos.",  4200),
        ("400A TPN Fuse Switch",                                                "Nos.", 12160),
        ("200A TPN Fuse Switch",                                                "Nos.",  6700),
        ("125A TPN Fuse Switch",                                                "Nos.",  4600),
        ("100A TPN load Isolator",                                              "Nos.",  1470),
        ("63A TPN load Isolator",                                               "Nos.",   900),
        ("32A TPN load Isolator",                                               "Nos.",   650),
    ],

    "SUBFEEDER CABLES AND EARTHLEADS": [
        ("4c x 240mm2 PVC/PVC Insulated copper cable c/w connecting accessories", "M",  3849),
        ("4c x 185mm2 PVC/PVC Insulated copper cable c/w connecting accessories", "M",  2900),
        ("4c x 150mm2 PVC/PVC Insulated copper cable c/w connecting accessories", "M",  2500),
        ("4c x 120mm2 PVC/PVC Insulated copper cable c/w connecting accessories", "M",  2242.80),
        ("4c x 95mm2 PVC/PVC Insulated copper cable c/w connecting accessories",  "M",  1850),
        ("4c x 70mm2 PVC/PVC Insulated copper cable c/w connecting accessories",  "M",  1100),
        ("4c x 50mm2 PVC/PVC Insulated copper cable c/w connecting accessories",  "M",   651),
        ("4c x 35mm2 PVC/PVC Insulated copper cable c/w connecting accessories",  "M",   470),
        ("4c x 25mm2 PVC/PVC Insulated copper cable c/w connecting accessories",  "M",   290),
        ("4c x 16mm2 PVC/PVC Insulated copper cable c/w connecting accessories",  "M",   190),
        ("4c x 10mm2 PVC/PVC Insulated copper cable c/w connecting accessories",  "M",   125),
        ("1c x 240mm2 PVC Insulated copper cable c/w connecting accessories",     "M",   780),
        ("1c x 185mm2 PVC Insulated copper cable c/w connecting accessories",     "M",   560),
        ("1c x 120mm2 PVC Insulated copper cable c/w connecting accessories",     "M",   400),
        ("1c x 95mm2 PVC Insulated copper cable c/w connecting accessories",      "M",   350),
        ("1c x 70mm2 PVC Insulated copper cable c/w connecting accessories",      "M",   298),
        ("1c x 50mm2 PVC Insulated copper cable c/w connecting accessories",      "M",   170),
        ("1c x 35mm2 PVC Insulated copper cable c/w connecting accessories",      "M",   120),
        ("1c x 25mm2 PVC Insulated copper cable c/w connecting accessories",      "M",    65),
        ("1c x 16mm2 PVC Insulated copper cable c/w connecting accessories",      "M",    42),
        ("1c x 10mm2 PVC Insulated copper cable c/w connecting accessories",      "M",    27),
        ("100mm diameter PVC pipe",                                                "M",    25),
        ("75mm diameter PVC pipe",                                                 "M",    18),
        ("50mm diameter PVC pipe",                                                 "M",    12),
    ],

    "WIRING OF POINTS": [
        ("1.5mm2 PVC insulated copper cable (Brown)",         "Coils", 391),
        ("1.5mm2 PVC insulated copper cable (Blue)",          "Coils", 391),
        ("1.5mm2 PVC insulated copper cable (Grey)",          "Coils", 391),
        ("1.5mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 391),
        ("2.5mm2 PVC insulated copper cable (Brown)",         "Coils", 653),
        ("2.5mm2 PVC insulated copper cable (Blue)",          "Coils", 653),
        ("2.5mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 653),
        ("4.0mm2 PVC insulated copper cable (Brown)",         "Coils", 1037),
        ("4.0mm2 PVC insulated copper cable (Blue)",          "Coils", 1037),
        ("4.0mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 1037),
        ("6.0mm2 PVC insulated copper cable (Brown)",         "Coils", 1500),
        ("6.0mm2 PVC insulated copper cable (Blue)",          "Coils", 1500),
        ("6.0mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 1500),
        ("20mm diameter PVC conduit pipe",                    "Nos.",   14.63),
        ("25mm diameter PVC conduit pipe",                    "Nos.",   19.50),
        ("32mm diameter PVC conduit pipe",                    "Nos.",   28.00),
        ("75mm x 75mm steel conduit boxes",                   "Nos.",   13),
        ("150mm x 75mm steel conduit boxes",                  "Nos.",   18),
        ("Circular boxes of various ways",                    "Nos.",    5),
        ("Junction boxes",                                    "Nos.",    8),
    ],

    "LUMINAIRES": [
        ("35W Round Recessed downlighter",                                         "Nos.", 550),
        ("40W 230V 50Hz 600x600mm LED recessed FL light fitting c/w driver",       "Nos.", 599),
        ("36W 1200mm LED linear Panel light c/w enclosure",                        "Nos.", 707.01),
        ("36W 1200mm LED linear Panel light",                                      "Nos.", 372),
        ("36W Round surface panel light",                                          "Nos.", 550),
        ("18W LED round surface panel light",                                      "Nos.", 305),
        ("18W LED round recessed panel light",                                     "Nos.", 310),
        ("12W LED round surface panel light",                                      "Nos.", 226),
        ("87W LED round high bay 230V 50Hz light",                                 "Nos.", 1100),
        ("LED Strip light",                                                        "Coil",   35),
        ("Emergency exit luminaire c/w battery backup",                            "Nos.", 480),
        ("Outdoor wall-mounted LED floodlight 50W",                                "Nos.", 380),
    ],

    "ACCESSORIES": [
        ("6A One Way One gang light switch (MK)",                              "Nos.",  20.73),
        ("6A One Way two gang light switch (MK)",                              "Nos.",  34.13),
        ("6A One Way three gang light switch (MK)",                            "Nos.",  51.52),
        ("6A two Way one gang light switch (MK)",                              "Nos.",  23.16),
        ("6A two Way two gang light switch (MK)",                              "Nos.",  35),
        ("6A two Way three gang light switch (MK)",                            "Nos.",  55),
        ("6 Compartment floor box c/w 2 double sockets + 2 double data outlet","Nos.", 2100),
        ("1 x 13A unswitched Socket outlet (MK)",                              "Nos.",  40),
        ("2 x 13A Switched Socket outlet (MK)",                                "Nos.",  60),
        ("2 x 13A Switched Socket outlet with light + red colour (MK)",        "Nos.",  74),
        ("2 x 13A USB Socket outlet (MK)",                                     "Nos.",  95),
        ("20A DP switch with neon indicator (MK)",                             "Nos.",  35),
        ("Plastic Automatic Hand Dryer",                                       "Nos.", 1250),
        ("Weatherproof IP65 socket outlet",                                    "Nos.", 110),
    ],

    # ===== Bill 3 -- BONDING AND EARTHING ===============================
    "BONDING AND EARTHING": [
        ("70mm2 bare copper conductor",                                  "M",    289),
        ("50mm2 bare copper conductor",                                  "M",    133),
        ("35mm2 bare copper conductor",                                  "M",    120),
        ("Galvanised steel holding rings",                               "Nos.",  20.30),
        ("Equalisation bar c/w 8 studs and connecting accessories",      "Nos.", 548.55),
        ("6x6 IP65 grounding junction box 20cm above FFL",               "Nos.",  36.57),
        ("3x3 square box",                                               "Nos.",  13),
        ("Arc welding -- mechanical attaching taps",                     "Pts.", 135),
        ("Exothermic welding",                                           "Nos.", 750),
        ("600mm x 600mm copper earth mat c/w 1500mm copper earth rod",   "Nos.",1700),
        ("Roll of warning tape (yellow/green)",                          "Nos.", 150),
        ("Standard 1.5M high graded copper earth rod",                   "Nos.",1200),
        ("Concrete inspection chamber with cover",                       "Nos.", 457.13),
        ("Test the installation -- electrical engineer's scripts",       "Lot",  5000),
    ],

    "EARTH ELECTRODE NETWORK": [
        ("1500mm copper earth rod, buried 1.5m below ground",            "Set",  1200),
        ("Prefabricated earth inspection chamber with lid",              "No.",   457.13),
        ("1c x 240mm2 bare copper cable as earth jumper",                "M",     700),
        ("6x6 IP65 junction box",                                        "M",      36.57),
        ("Earth tape clamp",                                             "Nos.",   45),
    ],

    # ===== Bill 4 -- FIRE ALARM SYSTEM ==================================
    "WIRING OF FIRE POINTS": [
        ("3c x 2.5mm2 red fire-resistant network detection cable",       "M",   30),
        ("20mm diameter self-extinguishing thermoplastic conduit pipe",  "Nos.",14.63),
        ("75mm x 75mm steel conduit boxes",                              "Nos.",13),
        ("Circular boxes of various ways",                               "Nos.", 5),
    ],

    "FIRE PANEL AND ACCESSORIES": [
        ("Addressable optical Smoke detector",                                            "Nos.",  532),
        ("Addressable heat detector",                                                     "Nos.",  580),
        ("Break glass call point",                                                        "Nos.",  600),
        ("Fire Alarm Beacon/Sounder indoor with strobe",                                  "Nos.",  980),
        ("Outdoor Weatherproof siren c/w strobe",                                         "Nos.",  980),
        ("Fire Alarm Junction Box",                                                       "Nos.",  250),
        ("8 Zone Addressable Fire Alarm Control Panel inc LCD module and Control Keys",   "Nos.",53640),
        ("4 Zone Conventional Fire Alarm Control Panel",                                  "Nos.", 8500),
        ("Fire Exit Sign",                                                                "Nos.",  120),
        ("Emergency Fire Bell",                                                           "Nos.",  450),
    ],

    # ===== Bill 5 -- DATA AND VOICE COMMUNICATIONS ======================
    "DATA EQUIPMENT AND ACCESSORIES": [
        ("Cat 6e UTP Data cable",                                                       "Coils",1650),
        ("48 Port CAT 6 patch panel",                                                   "Nos.", 1500),
        ("48 port CAT 6 Switch w/ 1GB fibre optic uplink (Cisco / Juniper class)",      "Nos.", 2300),
        ("24 port CAT 6 Switch w/ 1GB fibre optic uplink",                              "Nos.", 1800),
        ("Fibre patch",                                                                 "Nos.",  850),
        ("12U Data network cabinet",                                                    "Nos.", 1600),
        ("OM3 Laser-Optimized Multimode Aqua fibre optic cable",                        "M",      52),
        ("RJ45 double data outlet c/w faceplate, insert and mounting screws",           "Nos.",  104),
        ("Power strip",                                                                 "Nos.",  150),
        ("Patch cord 1m CAT 6",                                                         "Nos.",   45),
        ("Patch cord 2m CAT 6",                                                         "Nos.",   65),
    ],

    "VOICE EQUIPMENT AND ACCESSORIES": [
        ("IP desk phone",                                                "Nos.",  650),
        ("Wireless DECT base + handset",                                 "Nos.", 1200),
        ("Voice cabling (Cat 6e)",                                       "Coils",1650),
        ("Voice patch panel 24-port",                                    "Nos.", 1100),
    ],

    # ===== Bill 6 -- SIGNAL COMMUNICATION SYSTEMS =======================
    "EQUIPMENT AND ACCESSORIES": [
        ("IP Cam dome 100m, 180-degree view, night vision, motion detection",            "Nos.",  865),
        ("IP Cam bullet IR 30m, outdoor IP67",                                           "Nos.", 1050),
        ("Circular ceiling recessed audio speakers",                                     "Nos.",  260),
        ("Wall mounted audio speakers",                                                  "Nos.",  400),
        ("Power strip",                                                                  "Nos.",  150),
        ("Building/Zonal IP audio amplifier",                                            "M",   4900),
        ("20m AV cables -- building MIC to zonal amp",                                   "M",     19),
        ("Audio speaker cables (pair)",                                                  "M",      3),
        ("Network video recorder (NVR) 8-channel",                                       "Nos.", 5500),
        ("Network video recorder (NVR) 16-channel",                                      "Nos.", 8800),
        ("Access control reader (HID class)",                                            "Nos.", 1850),
        ("Electromagnetic door lock",                                                    "Nos.", 1200),
    ],

    # ===== Bill 1 -- PRELIMINARIES ======================================
    "PRELIMINARY ITEMS": [
        ("Site mobilisation and setup",                                  "Lot", 25000),
        ("Site insurance",                                               "Lot", 15000),
        ("Project manager allowance",                                    "Mth",  8500),
        ("Site engineer allowance",                                      "Mth",  7000),
        ("Health & safety provisions",                                   "Lot",  6500),
        ("Site office accommodation",                                    "Mth",  3500),
        ("Tools and small plant",                                        "Lot",  4500),
        ("Final commissioning and handover",                             "Lot",  8000),
    ],
}


def _boq_catalog_for_section(section_title: str) -> list:
    """Lookup helper: tries exact, upper, then partial-prefix match
    against the catalogue keys."""
    if not section_title:
        return []
    s = section_title.strip()
    if s in _BOQ_SECTION_ITEM_CATALOG:
        return list(_BOQ_SECTION_ITEM_CATALOG[s])
    if s.upper() in _BOQ_SECTION_ITEM_CATALOG:
        return list(_BOQ_SECTION_ITEM_CATALOG[s.upper()])
    # Partial: first key whose start matches the title (e.g. "WIRING OF
    # POINTS - Light points" -> "WIRING OF POINTS").
    s_up = s.upper()
    for key, items in _BOQ_SECTION_ITEM_CATALOG.items():
        if s_up.startswith(key) or key.startswith(s_up):
            return list(items)
    return []


# ----- Routes --------------------------------------------------------------

@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/bill/<int:bill_no>/section/<letter>/grid", methods=["GET"])
@login_required
def boq_section_grid(pid, bid, fid, bill_no, letter):
    """Spreadsheet-style entry page. Section heading is the page heading.
    Catalogue dropdown on every Description field is scoped to the
    section title -- pick auto-fills Unit + Basic Rate. Owner types Qty
    and hits 'Save all rows'."""
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    building = _boq_building_owned_or_404(bid, pid)
    floor = _boq_floor_owned_or_404(fid, bid)
    letter = (letter or "").upper()[:8]
    title = (request.args.get("title") or "").strip()[:160]
    bill_name = (request.args.get("bill_name") or _boq_lookup_bill_name(bill_no)).strip()[:120]
    subsec = (request.args.get("sub") or "").strip()[:20]
    if not title:
        title = bill_name

    catalog = _boq_catalog_for_section(title)
    # Always offer at least a small batch of empty rows so the owner can
    # add bespoke items.
    rows = list(catalog)
    while len(rows) < max(8, len(catalog) + 3):
        rows.append(("", "No.", 0))

    # Existing items already saved under this Bill+Section -- shown above
    # the grid (read-only) so the owner can see what they have without
    # leaving the page.
    with get_db() as c:
        existing = c.execute(
            "SELECT * FROM boq_floor_items "
            "WHERE floor_id=? AND bill_no=? AND section_letter=? "
            "ORDER BY id",
            (fid, bill_no, letter),
        ).fetchall()
    next_item_no = _boq_next_item_no(fid, bill_no, letter)

    return render_template(
        "boq_floor_section_grid.html",
        user=current_user(),
        project=project, building=building, floor=floor,
        bill_no=bill_no, bill_name=bill_name,
        section_letter=letter, section_title=title,
        subsection_label=subsec,
        catalog=catalog,           # raw [(desc, unit, basic), ...] for the description dropdown
        rows=rows,                 # initial table rows
        existing=existing,
        next_item_no=next_item_no,
    )


@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/bill/<int:bill_no>/section/<letter>/grid/save", methods=["POST"])
@login_required
def boq_section_grid_save(pid, bid, fid, bill_no, letter):
    """Bulk-save every non-empty row from the grid in one transaction.
    Owner directive: 90% time saving vs. a one-form-per-item flow."""
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

    # Defaults applied to every row in the bulk save -- typed once at the
    # top of the grid, then propagated. Spec rate formula = build-up math.
    def _pct(name):
        try:
            v = f.get(name, "")
            return max(0.0, min(100.0, float(v))) if v not in (None, "",) else 0.0
        except (TypeError, ValueError):
            return 0.0

    oh, prf, cnt, vat = _pct("overhead_pct"), _pct("profit_pct"), _pct("contingency_pct"), _pct("vat_pct")

    # Each row is posted with indexed keys: description[0], qty[0], ...
    descriptions = f.getlist("description[]")
    qtys         = f.getlist("qty[]")
    units        = f.getlist("unit[]")
    basics       = f.getlist("basic_price[]")
    supplies     = f.getlist("supply_rate[]")
    installs     = f.getlist("install_rate[]")
    specs        = f.getlist("specification[]")
    remarks_l    = f.getlist("remarks[]")
    # tick[] contains the row indices the owner checked. row_id[] is the
    # parallel array of indices for each rendered row so we can map ticks
    # back to row positions. If neither is present, fall back to saving
    # any non-empty row (legacy behaviour, pre-checkbox grid).
    row_ids      = f.getlist("row_id[]")
    ticked_raw   = f.getlist("tick[]")
    ticked = set()
    legacy_mode = not row_ids
    for v in ticked_raw:
        try: ticked.add(int(v))
        except (TypeError, ValueError): pass

    def _row_float(arr, i):
        try:
            v = arr[i] if i < len(arr) else ""
            return float(v) if v not in (None, "",) else None
        except (TypeError, ValueError):
            return None

    saved = 0
    skipped = 0
    next_no = int(_boq_next_item_no(fid, bill_no, letter))
    with get_db() as c:
        for i in range(len(descriptions)):
            desc = (descriptions[i] or "").strip()[:500]
            qty = _row_float(qtys, i) or 0.0
            basic = _row_float(basics, i) or 0.0
            supply_raw = _row_float(supplies, i)
            install_raw = _row_float(installs, i)
            unit = (units[i] if i < len(units) else "No.").strip() or "No."
            spec_t = (specs[i] if i < len(specs) else "").strip()
            remark = (remarks_l[i] if i < len(remarks_l) else "").strip()[:500]

            # Skip unticked rows when the grid posts a tick[] array.
            if not legacy_mode:
                try:
                    rid = int(row_ids[i]) if i < len(row_ids) else i
                except (TypeError, ValueError):
                    rid = i
                if rid not in ticked:
                    skipped += 1
                    continue

            # Skip rows the owner left empty.
            if not desc or qty <= 0 or basic <= 0:
                skipped += 1
                continue

            # Supply defaults to basic; install defaults to 0 (spec rule).
            supply = supply_raw if supply_raw is not None else basic
            install = install_raw if install_raw is not None else 0.0
            final_rate = _boq_safe_rate(basic, supply, install, oh, prf, cnt, vat)
            total = qty * final_rate
            item_no_disp = str(next_no)
            next_no += 1

            cur = c.execute(
                "INSERT INTO boq_floor_items "
                "(floor_id, building_id, project_id, user_id, section, subsection, "
                " library_item_id, supplier_id, item_no, description, specification, "
                " unit, qty, final_built_up_rate, total_amount, remarks, "
                " source_type, approval_status, "
                " bill_no, bill_name, section_letter, subsection_label, item_no_display) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fid, bid, pid, uid, title.lower()[:80], "",
                 None, None, item_no_disp,
                 desc, spec_t, unit, qty, final_rate, total, remark,
                 "custom_current_boq", "project_only",
                 bill_no, bill_name, letter, subsec, item_no_disp),
            )
            item_id = int(cur.lastrowid or 0)
            c.execute(
                "INSERT INTO boq_floor_rate_buildup "
                "(floor_item_id, project_id, user_id, basic_price, supply_rate, "
                " install_rate, overhead_pct, profit_pct, contingency_pct, vat_pct, "
                " final_built_up_rate, total_amount) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (item_id, pid, uid, basic, supply, install,
                 oh, prf, cnt, vat, final_rate, total),
            )
            saved += 1
        c.execute("UPDATE boq_projects  SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (pid,))
        c.execute("UPDATE boq_buildings SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (bid,))
        c.execute("UPDATE boq_floors    SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (fid,))

    try:
        from new_boq_hierarchy_schema import boq_audit
        boq_audit(get_db, uid, "boq_section_grid_saved", "boq_floor", fid,
                  f"bill={bill_no} sec={letter} saved={saved} skipped={skipped}")
    except Exception:
        pass

    flash(f"Saved {saved} item(s) under {letter}. {title}. "
          f"({skipped} blank row(s) ignored.)", "success")

    nxt = (f.get("next_action") or "back").strip()
    if nxt == "open_next":
        return redirect(url_for("boq_section_setup", pid=pid, bid=bid, fid=fid, bill_no=bill_no))
    if nxt == "stay":
        return redirect(url_for(
            "boq_section_grid",
            pid=pid, bid=bid, fid=fid, bill_no=bill_no, letter=letter,
            title=title, bill_name=bill_name, sub=subsec,
        ))
    if nxt == "generate":
        return redirect(url_for("boq_project_boq", pid=pid))
    return redirect(url_for("boq_floor_view", pid=pid, bid=bid, fid=fid))
