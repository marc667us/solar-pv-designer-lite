# new_boq_build_all_routes.py
# 2026-06-30 BOQ refactor (owner directive):
#   - Complete BOQ standalone page REMOVED.
#   - Section-by-Section is the canonical BOQ editor.
#   - This file provides a "Build all sections" page that stacks the
#     Section-by-Section grid for every section in the project's
#     Service Configuration on one page, so the user can build the
#     whole floor at once when they want.
#
# Routes:
#
#   GET  /boq-projects/<pid>/buildings/<bid>/floors/<fid>/build-all
#        Renders every section grouped by Bill -> Section using the
#        canonical inline Section-by-Section grid template. ONE set of
#        floor-wide rates at the top applies to every row.
#
#   POST /boq-projects/<pid>/buildings/<bid>/floors/<fid>/build-all/save
#        Iterates every ticked row across every section, inserts into
#        boq_floor_items + boq_floor_rate_buildup. The floor-wide rates
#        (supply%, install%, overhead%, profit%, VAT%, vat_in_basic) at
#        the top of the page apply to every row.


@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/build-all")
@login_required
def boq_floor_build_all(pid, bid, fid):
    """Renders every section from the floor's Service Configuration as a
    stacked Section-by-Section grid on one page."""
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    building = _boq_building_owned_or_404(bid, pid)
    floor = _boq_floor_owned_or_404(fid, bid)

    services = _services_csv_to_list(project["services_csv"] or "")
    if not services:
        flash("Pick the engineering services this project must cover first.", "warning")
        return redirect(url_for("boq_project_edit", pid=pid))

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

    bill_index = {}
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
            sec = {"letter": letter, "title": (_row_get(it, "section", "") or "Section"), "subsection": subsec, "service_code": "", "items": []}
            bucket["sections"].append(sec)
        sec["items"].append(it)

    def _norm_view(s):
        s = (s or "").upper()
        for ch in ("-", "/", ","):
            s = s.replace(ch, " ")
        return " ".join(s.split())

    _cat_dict = globals().get("_BOQ_SECTION_ITEM_CATALOG", {}) or {}

    def _lookup_for_view(title):
        try:
            hits = _boq_catalog_for_section(title) or []
            if hits:
                return hits
        except Exception:
            pass
        target = _norm_view(title).replace(" ", "")
        for k, v in _cat_dict.items():
            kn = _norm_view(k).replace(" ", "")
            if kn and target and (kn == target or kn.startswith(target) or target.startswith(kn) or kn in target or target in kn):
                return list(v)
        return []

    for no, bucket in bill_index.items():
        for sec in bucket["sections"]:
            try:
                cat = _lookup_for_view(sec["title"])
                try:
                    cat = _boq_apply_overrides(uid, cat) if cat else cat
                except Exception:
                    pass
                sec["catalog"] = cat or []
            except Exception:
                sec["catalog"] = []

    bills = [
        {"no": no, "name": bill_index[no]["name"], "sections": bill_index[no]["sections"]}
        for no in sorted(bill_index.keys())
    ]

    return render_template(
        "boq_floor_build_all.html",
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
        floor_subtotal=floor_subtotal,
    )


@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/build-all/save", methods=["POST"])
@login_required
def boq_floor_build_all_save(pid, bid, fid):
    """Save the WHOLE Build-all form in one shot. Floor-wide rates apply to
    every row. 2026-06-30 rate formula: Overhead + Profit ride on Supply."""
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    _boq_building_owned_or_404(bid, pid)
    _boq_floor_owned_or_404(fid, bid)
    csrf_protect()
    f = request.form

    def _pct(name, default=0.0):
        try:
            v = f.get(name, "")
            return max(0.0, min(100.0, float(v))) if v not in (None, "",) else default
        except (TypeError, ValueError):
            return default

    floor_oh   = _pct("overhead_pct", 10.0)
    floor_prf  = _pct("profit_pct",   15.0)
    floor_vat  = _pct("vat_pct",      12.5)
    floor_sp   = _pct("supply_pct",   10.0)
    floor_ip   = _pct("install_pct",  15.0)
    floor_vinb = 1 if f.get("vat_in_basic") else 0

    bill_nos        = f.getlist("bill_no[]")
    section_letters = f.getlist("section_letter[]")
    section_titles  = f.getlist("section_title[]")
    bill_names      = f.getlist("bill_name[]")
    subsection_lbls = f.getlist("subsection_label[]")
    descriptions    = f.getlist("description[]")
    units           = f.getlist("unit[]")
    qtys            = f.getlist("qty[]")
    basics          = f.getlist("basic_price[]")
    supplies        = f.getlist("supply_pct[]")
    installs        = f.getlist("install_pct[]")
    specs           = f.getlist("specification[]")

    n = len(bill_nos)
    if not n:
        flash("Nothing to save -- no rows submitted.", "warning")
        return redirect(url_for("boq_floor_build_all", pid=pid, bid=bid, fid=fid))

    try:
        from boq_rate_v3 import boq_rate_v3
    except Exception:
        boq_rate_v3 = None

    saved = 0
    skipped = 0
    next_no_by_sec = {}

    def _row_float(arr, i, default=0.0):
        try:
            v = arr[i] if i < len(arr) else ""
            return float(v) if v not in (None, "",) else default
        except (TypeError, ValueError):
            return default

    with get_db() as c:
        for i in range(n):
            try:
                bill_no = int(bill_nos[i])
            except (TypeError, ValueError):
                bill_no = 0
            letter = (section_letters[i] or "").upper()[:8]
            title  = (section_titles[i] or "").strip()[:80]
            bill_nm= (bill_names[i] or "").strip()[:120]
            sublbl = (subsection_lbls[i] or "").strip()[:200]
            desc   = (descriptions[i] or "").strip()[:500]
            unit   = (units[i] if i < len(units) else "No.").strip()[:20] or "No."
            qty    = _row_float(qtys, i)
            basic  = _row_float(basics, i)
            row_sp = _row_float(supplies, i, floor_sp)
            row_ip = _row_float(installs, i, floor_ip)
            spec_t = (specs[i] if i < len(specs) else "").strip()
            tick_key = f"tick_{bill_no}_{letter}_{i}"
            ticked = (f.get(tick_key) == "1")

            if not ticked or not desc or qty <= 0 or basic <= 0:
                skipped += 1
                continue

            # Compute rate via v3 helper (2026-06-30 formula: OH+Profit on Supply).
            if boq_rate_v3:
                supply_amt, install_amt, total_rate = boq_rate_v3(
                    basic, row_sp, row_ip, floor_oh, floor_prf, floor_vat,
                    vat_in_basic=bool(floor_vinb))
            else:
                eff_vat = 0 if floor_vinb else floor_vat
                supply_amt = basic * (row_sp + floor_oh + floor_prf + eff_vat) / 100.0
                install_amt = basic * row_ip / 100.0
                total_rate = basic + supply_amt + install_amt
            total = qty * total_rate

            sec_key = (bill_no, letter)
            if sec_key not in next_no_by_sec:
                try:
                    next_no_by_sec[sec_key] = int(_boq_next_item_no(fid, bill_no, letter))
                except Exception:
                    next_no_by_sec[sec_key] = 1
            item_no_disp = str(next_no_by_sec[sec_key])
            next_no_by_sec[sec_key] += 1

            cur = c.execute(
                "INSERT INTO boq_floor_items ("
                "  floor_id, building_id, project_id, user_id, "
                "  section, subsection, "
                "  bill_no, bill_name, section_letter, subsection_label, "
                "  item_no, item_no_display, "
                "  description, specification, unit, qty, "
                "  final_built_up_rate, total_amount, "
                "  source_type, approval_status) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    fid, bid, pid, uid,
                    title[:80], "",
                    bill_no, bill_nm[:120], letter, sublbl[:200],
                    item_no_disp, item_no_disp,
                    desc[:500], spec_t, unit[:20], qty,
                    total_rate, total,
                    "build_all", "project_only",
                ),
            )
            new_id = int(cur.lastrowid or 0)
            saved += 1

            try:
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
                        floor_oh, floor_prf, 0.0, floor_vat,
                        row_sp, row_ip, floor_vinb,
                        total_rate, total,
                    ),
                )
            except Exception:
                pass

        c.execute("UPDATE boq_floors SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (fid,))

    try:
        from new_boq_hierarchy_schema import boq_audit
        boq_audit(get_db, uid, "boq_build_all_save", "boq_floor", fid,
                  f"saved={saved} skipped={skipped}")
    except Exception:
        pass

    if saved:
        flash(f"Saved {saved} line item(s) across the floor. {skipped} row(s) were unticked / left blank.", "success")
    else:
        flash("Nothing saved -- tick the rows you want, set Quantity and Basic Price on each, then Save again.", "warning")
    return redirect(url_for("boq_floor_view", pid=pid, bid=bid, fid=fid))
