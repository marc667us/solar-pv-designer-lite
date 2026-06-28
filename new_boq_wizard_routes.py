# new_boq_wizard_routes.py
# Multi-building BOQ wizard — one click instantiates a full project from
# template picks. Replaces the click-by-click "new project -> new building
# -> new floor -> from-template" sequence.
#
# Flow:
#   GET  /boq-projects/wizard           form with all templates as ticks + counts
#   POST /boq-projects/wizard/build     creates project + N buildings + N floors,
#                                       populates every floor with its template lines


@app.route("/boq-projects/wizard", methods=["GET"])
@login_required
def boq_wizard():
    _boq_ensure_schema()
    from new_boq_project_templates import _boq_template_list
    # Group templates by purpose for the form.
    all_templates = _boq_template_list()
    grouped = {}
    for t in all_templates:
        grouped.setdefault(t["purpose"] or "other", []).append(t)
    # Stable order for purposes
    order = ["healthcare", "residential", "commercial", "industrial", "other"]
    grouped_order = [(p, grouped[p]) for p in order if p in grouped]
    return render_template(
        "boq_wizard.html",
        user=current_user(),
        grouped=grouped_order,
        total_templates=len(all_templates),
    )


@app.route("/boq-projects/wizard/build", methods=["POST"])
@login_required
def boq_wizard_build():
    uid = session["user_id"]
    _boq_ensure_schema()
    csrf_protect()
    f = request.form

    name = (f.get("project_name") or "").strip()[:300]
    if not name:
        flash("Project name is required.", "warning")
        return redirect(url_for("boq_wizard"))
    client = (f.get("client_name") or "").strip()[:300]
    location = (f.get("location") or "").strip()[:300]

    # Section-wide markup defaults (applied to every line on every floor).
    def _pct(key):
        try:
            v = f.get(key, "")
            return max(0.0, min(100.0, float(v))) if v not in (None, "") else 0.0
        except (TypeError, ValueError):
            return 0.0
    oh   = _pct("overhead_pct")
    prf  = _pct("profit_pct")
    vat  = _pct("vat_pct")
    sup_default_pct = _pct("supply_default_pct")
    ins_default_pct = _pct("install_default_pct")
    vat_in_basic = 1 if f.get("vat_in_basic") else 0

    # Collect picks: per-template count.
    from new_boq_project_templates import _boq_template_list, _boq_template_get, _boq_template_iter_lines
    # 2026-06-28 learning layer: pull overrides recorded from prior edits
    # so the template auto-fills with the user's last-used values.
    # _boq_template_lines_with_overrides is defined alongside this route in
    # web_app.py once both modules splice; globals() lookup is the safe way
    # to discover it without forcing a module import.
    _wiover = globals().get("_boq_template_lines_with_overrides")
    all_templates = _boq_template_list()

    picks = []
    for t in all_templates:
        slug = t["slug"]
        if not f.get(f"pick_{slug}"):
            continue
        try:
            count = max(1, min(50, int(f.get(f"count_{slug}") or 1)))
        except (TypeError, ValueError):
            count = 1
        picks.append((slug, t["name"], t["subtype"], t["purpose"], count))

    if not picks:
        flash("Tick at least one building type.", "warning")
        return redirect(url_for("boq_wizard"))

    # Create the project.
    with get_db() as c:
        cur = c.execute(
            "INSERT INTO boq_projects (user_id, project_name, client_name, "
            "location, project_type, external_works_included, infrastructure_included) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, name, client, location, "multi_building", 0, 0),
        )
        pid = int(cur.lastrowid or 0)

    # For each pick, create one building per count, with one floor named after
    # the template; populate every template line onto that floor.
    total_buildings = 0
    total_floors = 0
    total_items = 0

    for slug, tname, subtype, purpose, count in picks:
        tpl = _boq_template_get(slug)
        if not tpl:
            continue
        for n in range(1, count + 1):
            bld_name = tname if count == 1 else f"{tname} #{n}"
            primary = (purpose or "commercial").lower()
            # Map any unknown purpose to "commercial" so the building form check passes.
            if primary not in {"residential", "commercial", "industrial", "healthcare"}:
                primary = "commercial"
            with get_db() as c:
                cur = c.execute(
                    "INSERT INTO boq_buildings (project_id, building_name, building_code, "
                    "primary_purpose, purpose_subtype, other_purpose_description, "
                    "building_area, number_of_floors, basement_included, roof_level_included, "
                    "external_area_included) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (pid, bld_name[:300], "", primary, (subtype or "")[:80], "",
                     0.0, 1, 0, 0, 0),
                )
                bid = int(cur.lastrowid or 0)
                # Single floor named after the template.
                cur2 = c.execute(
                    "INSERT INTO boq_floors (building_id, project_id, floor_name, "
                    "floor_level, floor_type) VALUES (?,?,?,?,?)",
                    (bid, pid, "Ground Floor", 0, "ground"),
                )
                fid = int(cur2.lastrowid or 0)

            # Populate floor items from every template line. Pricing intentionally
            # zero -- owner edits after. Rate engine v3: supply/install are %s.
            # Override layer overlays the owner's last-used basic+unit+qty.
            from boq_rate_v3 import boq_rate_v3
            line_iter = (_wiover(uid, tpl) if _wiover
                         else _boq_template_iter_lines(tpl))
            next_no_cache = {}
            with get_db() as c:
                for (bill_no, bill_name, sect_letter, sect_title, subsec, idx,
                     desc, unit, qty_d, basic_d, spec) in line_iter:
                    qty = float(qty_d or 0)
                    basic = float(basic_d or 0)
                    if not desc.strip():
                        continue
                    supply_amount, install_amount, final_rate = boq_rate_v3(
                        basic, sup_default_pct, ins_default_pct,
                        oh, prf, vat, vat_in_basic=bool(vat_in_basic))
                    total = qty * final_rate

                    key = (bill_no, sect_letter)
                    if key not in next_no_cache:
                        next_no_cache[key] = 1
                    item_no_disp = str(next_no_cache[key])
                    next_no_cache[key] += 1

                    cur = c.execute(
                        "INSERT INTO boq_floor_items "
                        "(floor_id, building_id, project_id, user_id, section, subsection, "
                        " library_item_id, supplier_id, item_no, description, specification, "
                        " unit, qty, final_built_up_rate, total_amount, remarks, "
                        " source_type, approval_status, "
                        " bill_no, bill_name, section_letter, subsection_label, item_no_display) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (fid, bid, pid, uid, sect_title.lower()[:80], "",
                         None, None, item_no_disp,
                         desc, spec or "", unit, qty, final_rate, total, "",
                         "wizard_library", "project_only",
                         bill_no, bill_name, sect_letter, subsec or "", item_no_disp),
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
                         sup_default_pct, ins_default_pct, supply_amount, install_amount,
                         oh, prf, 0, vat, vat_in_basic, final_rate, total),
                    )
                    total_items += 1
            total_floors += 1
            total_buildings += 1

    try:
        from new_boq_hierarchy_schema import boq_audit
        boq_audit(get_db, uid, "boq_wizard_built", "boq_project", pid,
                  f"buildings={total_buildings} floors={total_floors} items={total_items}")
    except Exception:
        pass

    flash(f"Project created: {total_buildings} building(s), {total_floors} floor(s), {total_items} item(s) populated. "
          "Edit pricing per row before exporting.", "success")
    return redirect(url_for("boq_project_overview", pid=pid))
