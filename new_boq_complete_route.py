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

    # ------------------------------------------------------------------
    # 2026-06-29 owner directive: auto-fill basic prices from the
    # marketplace (equipment_catalog) + user overrides (learning layer)
    # so the user does NOT have to type a basic price for every line.
    # Matches Section-by-Section's behaviour where the grid catalogue
    # dropdown auto-fills Unit + Basic. Order of precedence per item:
    #     1. boq_user_item_overrides  -- user's last-saved price/unit
    #     2. equipment_catalog        -- marketplace canonical price (exact name match)
    #     3. equipment_catalog        -- substring match (fuzzy)
    #     4. _BOQ_SECTION_ITEM_CATALOG -- hardcoded section catalog (legacy)
    #     5. skeleton default basic=0 -- user adds via /equipment-catalog/quick-add
    # ------------------------------------------------------------------
    n_priced_from_overrides = 0
    n_priced_from_catalog = 0
    n_needs_price = 0
    try:
        overrides = _boq_lookup_overrides_for_user(uid)
    except Exception:
        overrides = {}
    # Pull catalog into a {lower(name): (id, unit, price_usd, spec)} once.
    try:
        with get_db() as c:
            cat_rows = c.execute(
                "SELECT id, LOWER(name) AS lname, unit, price_usd, spec "
                "FROM equipment_catalog WHERE COALESCE(is_active,1)=1 "
                "AND COALESCE(price_usd,0) > 0"
            ).fetchall()
        catalog_by_name = {
            (r["lname"] or ""): (
                int(r["id"]),
                (r["unit"] or "No."),
                float(r["price_usd"] or 0),
                (r["spec"] or ""),
            )
            for r in cat_rows
        }
    except Exception:
        catalog_by_name = {}

    # Build a sorted list of (lname, tuple) for prefix/substring search.
    catalog_lnames = sorted(catalog_by_name.keys(), key=lambda x: -len(x))

    def _find_in_catalog(desc):
        d = (desc or "").strip().lower()
        if not d:
            return None
        if d in catalog_by_name:
            return catalog_by_name[d]
        # Substring: prefer the LONGEST catalog name that is contained in the
        # skeleton description (avoids "Cable" matching everything).
        for ln in catalog_lnames:
            if len(ln) >= 8 and ln in d:
                return catalog_by_name[ln]
        return None

    enriched_rows = []
    for r in rows:
        new_r = dict(r)
        new_r.setdefault("library_item_id", None)
        desc = r.get("desc", "")
        key = _boq_desc_key(desc)
        # 1. User override (most personal).
        if key and key in overrides:
            ov_unit, ov_basic, _ov_sp, _ov_ip, _ov_qty = overrides[key]
            if ov_basic > 0:
                new_r["basic"] = ov_basic
                new_r["unit"] = ov_unit or new_r.get("unit", "No.")
                n_priced_from_overrides += 1
                enriched_rows.append(new_r)
                continue
        # 2-3. Marketplace (equipment_catalog) -- exact then fuzzy.
        cat_hit = _find_in_catalog(desc)
        if cat_hit:
            cat_id, cat_unit, cat_price, cat_spec = cat_hit
            new_r["basic"] = cat_price
            new_r["unit"] = cat_unit or new_r.get("unit", "No.")
            if cat_spec and not new_r.get("spec"):
                new_r["spec"] = cat_spec
            new_r["library_item_id"] = cat_id
            n_priced_from_catalog += 1
            enriched_rows.append(new_r)
            continue
        # 4. Not found anywhere -- mark for the quick-add flow.
        n_needs_price += 1
        enriched_rows.append(new_r)
    rows = enriched_rows

    n_inserted = 0
    n_skipped = 0
    with get_db() as c:
        # Existing (bill_no, section_letter, description) keys -- skip dupes.
        # ONLY dedup against rows that came from Generate Skeleton previously
        # (service_code is set). Items added via Section-by-Section have
        # service_code='' and must NOT block the skeleton from filling its
        # canonical rows -- the user's Section-by-Section work and the
        # Complete BOQ skeleton can coexist on the same floor.
        existing = {
            (int(r["bill_no"] or 0), (r["section_letter"] or "").upper(), (r["description"] or "").strip().lower())
            for r in c.execute(
                "SELECT bill_no, section_letter, description FROM boq_floor_items "
                "WHERE floor_id=? AND COALESCE(service_code,'') <> ''",
                (fid,),
            ).fetchall()
        }
        # 2026-06-29 owner directive: the floor-wide rates form on the
        # Complete BOQ page lets the user enter Supply%, Install%, OH%,
        # Profit%, VAT%, and "VAT in basic" ONCE -- those values apply to
        # every row that gets inserted.
        # Precedence:
        #   1. Form values (user just typed them on Generate Skeleton)
        #   2. Any existing sibling rate_buildup (preserves previous Generate)
        #   3. Hardcoded fallback (10, 15, 10, 15, 12.5)
        f = request.form
        def _pct(name, default):
            try:
                v = f.get(name, "")
                return max(0.0, min(100.0, float(v))) if v not in (None, "",) else default
            except (TypeError, ValueError):
                return default
        sp_form = f.get("supply_pct")
        if sp_form not in (None, "",):
            sp_def = _pct("supply_pct", 10.0)
            ip_def = _pct("install_pct", 15.0)
            oh_def = _pct("overhead_pct", 10.0)
            prf_def = _pct("profit_pct", 15.0)
            vat_def = _pct("vat_pct", 12.5)
            vinb_def = 1 if f.get("vat_in_basic") else 0
        else:
            sib = c.execute(
                "SELECT b.supply_pct, b.install_pct, b.overhead_pct, b.profit_pct, b.vat_pct, b.vat_in_basic "
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
                vinb_def = int(sib["vat_in_basic"] or 0)
            else:
                sp_def, ip_def, oh_def, prf_def, vat_def = 10.0, 15.0, 10.0, 15.0, 12.5
                vinb_def = 0

        # display_order continues from whatever the highest is on this floor.
        max_disp_row = c.execute(
            "SELECT COALESCE(MAX(display_order),0) AS m FROM boq_floor_items WHERE floor_id=?",
            (fid,),
        ).fetchone()
        next_disp = int(max_disp_row["m"] or 0) + 1

        for r in rows:
            key = (int(r["bill_no"]), (r["section_letter"] or "").upper(), (r["desc"] or "").strip().lower())
            if key in existing:
                n_skipped += 1
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
            # markup-only semantics everywhere else. Honour vat_in_basic
            # from the form so the floor-wide rates entry stays consistent.
            _eff_vat = 0 if vinb_def else vat_def
            try:
                from boq_rate_v3 import boq_rate_v3 as _rate_v3
                supply_amt, install_amt, total_rate = _rate_v3(basic, sp_def, ip_def, oh_def, prf_def, vat_def, bool(vinb_def))
            except Exception:
                supply_amt = basic * (sp_def + _eff_vat) / 100.0
                install_amt = basic * (ip_def + oh_def + prf_def) / 100.0
                total_rate = basic + supply_amt + install_amt
            total_amount = qty * total_rate

            # Defensive truncation -- even with the ALTER on subsection_label
            # to VARCHAR(200), legacy DBs that haven't picked up the migration
            # yet would still throw "string data, right truncation" on PG.
            # Clamp each value to its known column ceiling.
            _section      = (r["section_title"] or "")[:80]
            _subsection   = (r["subsection_label"] or "")[:200]
            _bill_name    = (r["bill_name"] or "")[:120]
            _sec_letter   = (r["section_letter"] or "")[:8]
            _sub_label    = (r["subsection_label"] or "")[:200]
            _desc         = (r["desc"] or "")[:500]
            _spec         = (r.get("spec", "") or "")
            _unit         = (r.get("unit", "") or "")[:20]
            _service_code = (r.get("service_code", "") or "")[:40]

            _library_item_id = r.get("library_item_id")  # None when not in catalog

            cur = c.execute(
                "INSERT INTO boq_floor_items ("
                "  floor_id, building_id, project_id, user_id, "
                "  section, subsection, "
                "  bill_no, bill_name, section_letter, subsection_label, "
                "  description, specification, unit, qty, "
                "  final_built_up_rate, total_amount, "
                "  display_order, service_code, library_item_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    fid, bid, pid, uid,
                    _section, _subsection,
                    r["bill_no"], _bill_name, _sec_letter, _sub_label,
                    _desc, _spec, _unit, qty,
                    total_rate, total_amount,
                    next_disp, _service_code, _library_item_id,
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
                    sp_def, ip_def, vinb_def,
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
        # Compose a single, plain-English flash that shows the user
        # exactly how much work is left -- and how much was pre-filled
        # from the marketplace + their own override history.
        bits = [f"Generated {n_inserted} new line item(s)."]
        if n_priced_from_overrides:
            bits.append(f"{n_priced_from_overrides} pre-priced from your saved overrides.")
        if n_priced_from_catalog:
            bits.append(f"{n_priced_from_catalog} pre-priced from the Marketplace catalog.")
        if n_needs_price:
            bits.append(f"{n_needs_price} item(s) have no marketplace match -- type the basic price OR click \"Add to Marketplace\" next to the row to save it for next time.")
        if n_skipped:
            bits.append(f"{n_skipped} skeleton row(s) were already on the floor.")
        flash(" ".join(bits), "success")
    else:
        # Tell the user EXACTLY what's there so they understand nothing was
        # missing. Avoid the previous "no new rows" terseness that read as
        # an error.
        with get_db() as c:
            n_total = c.execute(
                "SELECT COUNT(*) FROM boq_floor_items WHERE floor_id=?", (fid,)
            ).fetchone()[0]
        flash(
            f"Your Service Configuration's {n_skipped} skeleton row(s) are already on this floor "
            f"({n_total} total items including any Section-by-Section additions). Open any bill below "
            f"to edit quantities + prices, or change services on the Edit Project page to add more bills.",
            "info",
        )
    return redirect(url_for("boq_floor_complete", pid=pid, bid=bid, fid=fid))
