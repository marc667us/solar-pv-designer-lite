# new_boq_complete_route.py
# 2026-06-29 unified BOQ engine refactor (projectboq build update1.txt).
#
# Mode 2 -- Complete BOQ. Replaces "Build by Template". Loads every section
# from the project's selected services into ONE editable page that reuses
# the existing Section Builder editors (no new editing UI is introduced).
#
# Two routes:
#
#   GET  /boq-projects/<pid>/buildings/<bid>/floors/<fid>/complete
#        Renders the floor's BOQ grouped by Bill -> Section. If no rows
#        exist yet, shows a service-configuration summary + Generate prompt.
#
#   POST /boq-projects/<pid>/buildings/<bid>/floors/<fid>/complete/generate
#        Idempotent. For every section in the project's services that does
#        not already have an item on this floor, inserts the skeleton items
#        (one row per item) and one boq_floor_rate_buildup row per item,
#        seeded with the project's default supply/install/oh/profit/vat.


@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/complete")
@login_required
def boq_floor_complete(pid, bid, fid):
    """Mode 2 -- Complete BOQ view. Reuses the existing per-row editors."""
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    building = _boq_building_owned_or_404(bid, pid)
    floor = _boq_floor_owned_or_404(fid, bid)

    services = _services_csv_to_list(project["services_csv"] or "")
    if not services:
        flash("Pick the engineering services this project must cover first.", "warning")
        return redirect(url_for("boq_project_edit", pid=pid))

    # Skeleton (the list of bills the user is ABOUT to see + the rows that
    # would be inserted on Generate).
    skeleton_rows = _services_section_rows(services)
    skeleton_sections = _services_loaded_sections(services)

    with get_db() as c:
        items = c.execute(
            "SELECT i.*, b.final_built_up_rate AS bu_final, "
            "       b.basic_price AS bu_basic, b.supply_rate AS bu_supply, "
            "       b.install_rate AS bu_install, b.overhead_pct AS bu_oh, "
            "       b.profit_pct AS bu_profit, b.contingency_pct AS bu_cont, "
            "       b.vat_pct AS bu_vat "
            "FROM boq_floor_items i "
            "LEFT JOIN boq_floor_rate_buildup b ON b.floor_item_id=i.id "
            "WHERE i.floor_id=? "
            "ORDER BY COALESCE(i.bill_no,0), COALESCE(i.section_letter,''), "
            "         COALESCE(i.display_order,0), "
            "         COALESCE(NULLIF(i.item_no_display,''),'0'), i.id",
            (fid,),
        ).fetchall()
        subtotal_row = c.execute(
            "SELECT COALESCE(SUM(total_amount),0) AS g FROM boq_floor_items WHERE floor_id=?",
            (fid,),
        ).fetchone()

    floor_subtotal = float(subtotal_row["g"] or 0) if subtotal_row else 0.0

    # Build the bill-grouped view directly off the skeleton so EVERY service's
    # section appears even when empty. Items get attached to their (bill_no,
    # section_letter) bucket; if no items exist yet, the section shows empty
    # rows with the skeleton item descriptions as placeholders.
    bill_index = {}  # bill_no -> {"name", "sections": {(letter, title, subsection): [items]}}
    for r in skeleton_sections:
        bill_no = r["bill_no"]
        bill_index.setdefault(bill_no, {"name": r["bill_name"], "sections": []})
        bill_index[bill_no]["sections"].append({
            "letter": r["section_letter"],
            "title":  r["section_title"],
            "subsection": r["subsection"],
            "service_code": r["service_code"],
            "items": [],
        })

    # Attach real items to the right section. boq_floor_items uses the
    # ``section`` column (not ``section_title``) -- that column was added by
    # the section setup form back in 2026-06 and holds the human-readable
    # title. ``bill_name`` + ``section_letter`` are the canonical join keys.
    def _row_get(row, key, default=""):
        try:
            v = row[key]
        except (KeyError, IndexError):
            return default
        return v if v is not None else default

    for it in items:
        bill_no = int(_row_get(it, "bill_no", 0) or 0)
        letter = (_row_get(it, "section_letter", "") or "").upper()
        title = (_row_get(it, "section", "") or "").upper()
        subsec = _row_get(it, "subsection_label", "") or _row_get(it, "subsection", "")
        bucket = bill_index.get(bill_no)
        if not bucket:
            # Item exists under a bill no longer in the service set -- park it
            # under a synthetic "Legacy items" bill at the end (preserves
            # data while making the orphan visible to the user).
            bill_index.setdefault(9999, {"name": "LEGACY ITEMS (not in current Service Configuration)", "sections": []})
            bucket = bill_index[9999]
            sec = next((s for s in bucket["sections"] if s["letter"] == letter and s["title"].upper() == title), None)
            if not sec:
                sec = {"letter": letter or "Z", "title": (_row_get(it, "section", "") or "Uncategorised"), "subsection": subsec, "service_code": "", "items": []}
                bucket["sections"].append(sec)
            sec["items"].append(it)
            continue
        sec = next((s for s in bucket["sections"] if s["letter"] == letter and s["title"].upper() == title), None)
        if sec is None:
            # Section letter is in this bill but with a different title --
            # add it to the bucket so the item still renders.
            sec = {"letter": letter, "title": (_row_get(it, "section", "") or "Section"), "subsection": subsec, "service_code": "", "items": []}
            bucket["sections"].append(sec)
        sec["items"].append(it)

    bills = [
        {"no": no, "name": bill_index[no]["name"], "sections": bill_index[no]["sections"]}
        for no in sorted(bill_index.keys())
    ]

    return render_template(
        "boq_floor_complete.html",
        user=current_user(),
        project=project,
        building=building,
        floor=floor,
        bills=bills,
        services=services,
        service_labels=_BOQ_SERVICE_LABEL,
        service_icons=_BOQ_SERVICE_ICON,
        has_items=bool(items),
        n_items=len(items),
        skeleton_item_count=len(skeleton_rows),
        floor_subtotal=floor_subtotal,
    )


@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/complete/generate", methods=["POST"])
@login_required
def boq_floor_complete_generate(pid, bid, fid):
    """Bulk-insert the skeleton item rows for every selected service that
    doesn't already have a row on this floor. Idempotent -- existing items
    are NEVER touched (matches on bill_no + section_letter + description).
    """
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    building = _boq_building_owned_or_404(bid, pid)
    floor = _boq_floor_owned_or_404(fid, bid)
    csrf_protect()

    services = _services_csv_to_list(project["services_csv"] or "")
    if not services:
        flash("Pick the engineering services first.", "warning")
        return redirect(url_for("boq_project_edit", pid=pid))

    rows = _services_section_rows(services)

    n_inserted = 0
    with get_db() as c:
        # Existing (bill_no, section_letter, description) keys -- skip dupes.
        existing = {
            (int(r["bill_no"] or 0), (r["section_letter"] or "").upper(), (r["description"] or "").strip().lower())
            for r in c.execute(
                "SELECT bill_no, section_letter, description FROM boq_floor_items WHERE floor_id=?",
                (fid,),
            ).fetchall()
        }
        # Default percentages for new rows -- read from any sibling rate-buildup
        # on this floor; fallback to (10, 15, 10, 15, 12.5).
        sib = c.execute(
            "SELECT b.supply_pct, b.install_pct, b.overhead_pct, b.profit_pct, b.vat_pct "
            "FROM boq_floor_rate_buildup b "
            "JOIN boq_floor_items i ON i.id = b.floor_item_id "
            "WHERE i.floor_id=? LIMIT 1",
            (fid,),
        ).fetchone()
        if sib:
            sp_def = float(sib["supply_pct"] or 10)
            ip_def = float(sib["install_pct"] or 15)
            oh_def = float(sib["overhead_pct"] or 10)
            prf_def = float(sib["profit_pct"] or 15)
            vat_def = float(sib["vat_pct"] or 12.5)
        else:
            sp_def, ip_def, oh_def, prf_def, vat_def = 10.0, 15.0, 10.0, 15.0, 12.5

        # display_order continues from whatever the highest is on this floor.
        max_disp_row = c.execute(
            "SELECT COALESCE(MAX(display_order),0) AS m FROM boq_floor_items WHERE floor_id=?",
            (fid,),
        ).fetchone()
        next_disp = int(max_disp_row["m"] or 0) + 1

        for r in rows:
            key = (int(r["bill_no"]), (r["section_letter"] or "").upper(), (r["desc"] or "").strip().lower())
            if key in existing:
                continue
            try:
                basic = float(r.get("basic") or 0)
            except Exception:
                basic = 0.0
            try:
                qty = float(r.get("qty") or 0)
            except Exception:
                qty = 0.0
            # Compute amounts via boq_rate_v3 so the new row matches the
            # markup-only semantics everywhere else.
            try:
                from boq_rate_v3 import boq_rate_v3 as _rate_v3
                supply_amt, install_amt, total_rate = _rate_v3(basic, sp_def, ip_def, oh_def, prf_def, vat_def, 0)
            except Exception:
                supply_amt = basic * (sp_def + vat_def) / 100.0
                install_amt = basic * (ip_def + oh_def + prf_def) / 100.0
                total_rate = basic + supply_amt + install_amt
            total_amount = qty * total_rate

            cur = c.execute(
                "INSERT INTO boq_floor_items ("
                "  floor_id, building_id, project_id, user_id, "
                "  section, subsection, "
                "  bill_no, bill_name, section_letter, subsection_label, "
                "  description, specification, unit, qty, "
                "  final_built_up_rate, total_amount, "
                "  display_order, service_code) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    fid, bid, pid, uid,
                    r["section_title"], r["subsection_label"],
                    r["bill_no"], r["bill_name"], r["section_letter"], r["subsection_label"],
                    r["desc"], r.get("spec", ""), r.get("unit", ""), qty,
                    total_rate, total_amount,
                    next_disp, r.get("service_code", ""),
                ),
            )
            new_id = int(cur.lastrowid or 0)
            next_disp += 1
            n_inserted += 1

            # Note: user_id is NOT NULL in the rate_buildup schema. We must
            # include it -- on Postgres, a NULL-violation here poisons the
            # transaction and the NEXT iteration's INSERT throws
            # "current transaction is aborted" (unhandled -> 500). On SQLite
            # the NOT NULL is laxly enforced and the bug never surfaces.
            c.execute(
                "INSERT INTO boq_floor_rate_buildup ("
                "  floor_item_id, project_id, user_id, basic_price, "
                "  supply_rate, install_rate, "
                "  overhead_pct, profit_pct, contingency_pct, vat_pct, "
                "  supply_pct, install_pct, vat_in_basic, "
                "  final_built_up_rate, total_amount) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    new_id, pid, uid, basic,
                    supply_amt, install_amt,
                    oh_def, prf_def, 0.0, vat_def,
                    sp_def, ip_def, 0,
                    total_rate, total_amount,
                ),
            )

    try:
        from new_boq_hierarchy_schema import boq_audit
        boq_audit(get_db, uid, "boq_complete_generate", "boq_floor", fid,
                  f"services={services} inserted={n_inserted}")
    except Exception:
        pass

    if n_inserted:
        flash(f"Generated {n_inserted} starter row(s) from your Service Configuration. Edit quantities and prices in place.", "success")
    else:
        flash("No new rows added -- every skeleton row already exists on this floor.", "info")
    return redirect(url_for("boq_floor_complete", pid=pid, bid=bid, fid=fid))
