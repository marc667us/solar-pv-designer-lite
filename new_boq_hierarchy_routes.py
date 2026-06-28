# new_boq_hierarchy_routes.py
# Phase 3 -- Dynamic BOQ Library Builder with the full
# Project -> Building -> Floor -> Item hierarchy from the master prompt
# (sections 1-21).
#
# Topology mirrored 1:1 with the relations declared in
# new_boq_hierarchy_schema.py:
#
#   boq_projects (1)
#     -> boq_buildings (N)
#         -> boq_floors (N)
#             -> boq_floor_items (N)
#                 -> boq_floor_rate_buildup (1:1, internal-only)
#                 -> equipment_catalog.id   (library_item_id, nullable)
#                 -> suppliers.id           (supplier_id, nullable)
#
# Spec rate formula (s13):
#   supply  = basic if blank ; install = 0 if blank
#   prelim  = supply + install
#   final   = prelim * (1 + OH% + Profit% + Cont% + VAT%) /100  (each as %)
#   total   = qty * final
#
# Client BOQ columns (spec s11): No / Description / Unit / Qty / Rate / Amount / Remarks.
# Internal Rate Build-Up adds Basic / Supply / Install / OH / Profit / Cont / VAT
# / Final Rate columns. Same view-toggle pattern as the marketplace BOQ.


# ---------------- helpers ---------------------------------------------------

_BOQ_PRIMARY_PURPOSES = ["residential", "commercial", "industrial"]
_BOQ_PURPOSE_SUBTYPES = {
    "residential": [
        "Single Family House", "Apartment Block", "Hostel",
        "Staff Housing", "Gated Estate", "Boys Quarters", "Other",
    ],
    "commercial": [
        "Office", "Hospital", "Retail / Shopping Centre", "Hotel",
        "School / Educational Facility", "Auditorium",
        "Church / Worship Facility", "Data Centre", "Laboratory",
        "Restaurant", "Bank", "Mixed-Use Commercial", "Other",
    ],
    "industrial": [
        "Factory", "Warehouse", "Workshop", "Processing Plant",
        "Cold Store", "Manufacturing Facility", "Power Plant", "Other",
    ],
}

_BOQ_SECTIONS = [
    ("preliminaries",    "Preliminaries"),
    ("switchboards",     "Switch Boards & DBs"),
    ("sub_feeders",      "Sub-feeder Cables"),
    ("wiring",           "Wiring of Points"),
    ("luminaires",       "Luminaires"),
    ("accessories",      "Accessories"),
    ("earthing",         "Bonding & Earthing"),
    ("fire_alarm",       "Fire Detection & Alarm"),
    ("data_voice",       "Data & Voice"),
    ("lightning",        "Lightning Protection"),
    ("external_lighting","External Lighting"),
    ("solar_pv",         "Solar PV System"),
    ("generator_ups",    "Generator & UPS"),
    ("testing",          "Testing & Commissioning"),
    ("documentation",    "Documentation & Handover"),
    ("other",            "Other"),
]


def _boq_ensure_schema():
    """Lazy bootstrap of the BOQ hierarchy tables. Idempotent."""
    try:
        from new_boq_hierarchy_schema import ensure_boq_hierarchy_schema
        ensure_boq_hierarchy_schema(get_db)
    except Exception as e:
        try:
            app.logger.warning("boq schema bootstrap: %s", e)
        except Exception:
            pass


def _boq_tenant_clause(alias: str = ""):
    """Return (sql_fragment, params_tuple) to AND tenant_id onto a BOQ
    query. SOC 2 M3.1 defence in depth on top of migrations 003 + 007
    RLS so a request that bypasses RLS (admin GUC, future cross-tenant
    report code) still cannot read a neighbour tenant's BOQ rows.
    Admits `tenant_id IS NULL` for parallel-run safety; Phase 7 cutover
    drops that escape.

    Imported lazily because this source file gets injected into
    web_app.py via Pattern B; the helper itself lives in the injected
    block and reuses the _kc_current_tenant_id alias that web_app.py
    imports at module load."""
    try:
        tid = _kc_current_tenant_id()  # noqa: F821 -- web_app.py provides this
    except Exception:
        tid = None
    if not tid:
        return "", ()
    col = f"{alias}.tenant_id" if alias else "tenant_id"
    return f" AND ({col} IS NULL OR {col} = ?)", (tid,)


def _boq_project_owned_or_404(pid: int, uid: int):
    _boq_ensure_schema()
    t_clause, t_params = _boq_tenant_clause()
    with get_db() as c:
        row = c.execute(
            "SELECT * FROM boq_projects WHERE id=? AND user_id=?" + t_clause,
            (pid, uid) + t_params,
        ).fetchone()
    if not row:
        abort(404)
    return row


def _boq_building_owned_or_404(bid: int, pid: int):
    t_clause, t_params = _boq_tenant_clause()
    with get_db() as c:
        row = c.execute(
            "SELECT * FROM boq_buildings WHERE id=? AND project_id=?" + t_clause,
            (bid, pid) + t_params,
        ).fetchone()
    if not row:
        abort(404)
    return row


def _boq_floor_owned_or_404(fid: int, bid: int):
    t_clause, t_params = _boq_tenant_clause()
    with get_db() as c:
        row = c.execute(
            "SELECT * FROM boq_floors WHERE id=? AND building_id=?" + t_clause,
            (fid, bid) + t_params,
        ).fetchone()
    if not row:
        abort(404)
    return row


def _boq_compute_rate(basic, supply, install, oh_pct, prf_pct, cnt_pct=0, vat_pct=0, vat_in_basic=False):
    """2026-06-28 owner spec. supply/install are PERCENTAGES.
    cnt_pct ignored. vat_in_basic suppresses VAT on supply.
        supply_amount   = basic * (1 + (supply + (0 if vat_in_basic else vat))/100)
        install_amount  = basic * ((install + oh + prf)/100)
        total           = supply_amount + install_amount
    """
    b  = max(0.0, float(basic or 0))
    sp = max(0.0, float(supply  or 0))
    ip = max(0.0, float(install or 0))
    op = max(0.0, float(oh_pct  or 0))
    pp = max(0.0, float(prf_pct or 0))
    vp = max(0.0, float(vat_pct or 0))
    eff_vat = 0.0 if vat_in_basic else vp
    supply_amount  = b * (1.0 + (sp + eff_vat) / 100.0)
    install_amount = b * ((ip + op + pp) / 100.0)
    return supply_amount + install_amount
def _boq_make_floors(project_id: int, building_id: int,
                     n_floors: int, basement: bool, roof: bool):
    """Spec s5: auto-create Ground/First/Second... + optional Basement + Roof."""
    floors = []
    if basement:
        floors.append(("Basement", -1, "basement"))
    # Ground + upper floors
    n = max(1, int(n_floors or 1))
    floors.append(("Ground Floor", 0, "ground"))
    NAMES = ["First Floor", "Second Floor", "Third Floor", "Fourth Floor",
             "Fifth Floor", "Sixth Floor", "Seventh Floor", "Eighth Floor",
             "Ninth Floor", "Tenth Floor"]
    for i in range(1, n):
        nm = NAMES[i - 1] if i - 1 < len(NAMES) else f"Floor {i}"
        floors.append((nm, i, "upper"))
    if roof:
        floors.append(("Roof Level", 99, "roof"))

    with get_db() as c:
        for name, level, ftype in floors:
            c.execute(
                "INSERT INTO boq_floors (building_id, project_id, floor_name, "
                "floor_level, floor_type) VALUES (?,?,?,?,?)",
                (building_id, project_id, name, level, ftype),
            )


# ---------------- routes ----------------------------------------------------

@app.route("/boq-projects")
@login_required
def boq_projects_list():
    uid = session["user_id"]
    _boq_ensure_schema()
    with get_db() as c:
        projects = c.execute(
            "SELECT p.*, "
            "  (SELECT COUNT(*) FROM boq_buildings b WHERE b.project_id=p.id) AS n_buildings, "
            "  (SELECT COUNT(*) FROM boq_floor_items i WHERE i.project_id=p.id) AS n_items, "
            "  (SELECT COALESCE(SUM(total_amount),0) FROM boq_floor_items i WHERE i.project_id=p.id) AS grand_total "
            "FROM boq_projects p "
            "WHERE p.user_id=? "
            "ORDER BY p.updated_at DESC, p.id DESC",
            (uid,),
        ).fetchall()
    return render_template("boq_projects_list.html", user=current_user(), projects=projects)


@app.route("/boq-projects/new", methods=["GET", "POST"])
@login_required
def boq_projects_new():
    uid = session["user_id"]
    _boq_ensure_schema()
    if request.method == "POST":
        csrf_protect()
        f = request.form
        name = (f.get("project_name") or "").strip()[:300]
        client = (f.get("client_name") or "").strip()[:300]
        location = (f.get("location") or "").strip()[:300]
        ptype = (f.get("project_type") or "single_building").strip()
        ext_works = 1 if f.get("external_works_included") else 0
        infra = 1 if f.get("infrastructure_included") else 0
        if not name:
            flash("Project name is required.", "warning")
            return redirect(url_for("boq_projects_new"))
        with get_db() as c:
            cur = c.execute(
                "INSERT INTO boq_projects (user_id, project_name, client_name, "
                "location, project_type, external_works_included, infrastructure_included) "
                "VALUES (?,?,?,?,?,?,?)",
                (uid, name, client, location, ptype, ext_works, infra),
            )
            pid = int(cur.lastrowid or 0)
        try:
            from new_boq_hierarchy_schema import boq_audit
            boq_audit(get_db, uid, "boq_project_created", "boq_project", pid)
        except Exception:
            pass
        return redirect(url_for("boq_building_new", pid=pid))
    return render_template("boq_project_new.html", user=current_user())


@app.route("/boq-projects/<int:pid>")
@login_required
def boq_project_overview(pid):
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    with get_db() as c:
        buildings = c.execute(
            "SELECT b.*, "
            "  (SELECT COUNT(*) FROM boq_floors f WHERE f.building_id=b.id) AS n_floors, "
            "  (SELECT COALESCE(SUM(total_amount),0) FROM boq_floor_items i WHERE i.building_id=b.id) AS subtotal "
            "FROM boq_buildings b "
            "WHERE b.project_id=? ORDER BY b.id",
            (pid,),
        ).fetchall()
        grand = c.execute(
            "SELECT COALESCE(SUM(total_amount),0) AS g FROM boq_floor_items WHERE project_id=?",
            (pid,),
        ).fetchone()
    grand_total = float(grand["g"] or 0) if grand else 0.0
    return render_template("boq_project_overview.html",
                           user=current_user(),
                           project=project, buildings=buildings,
                           grand_total=grand_total,
                           sections=_BOQ_SECTIONS)


@app.route("/boq-projects/<int:pid>/buildings/new", methods=["GET", "POST"])
@login_required
def boq_building_new(pid):
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    if request.method == "POST":
        csrf_protect()
        f = request.form
        name = (f.get("building_name") or "").strip()[:300]
        code = (f.get("building_code") or "").strip()[:80]
        primary = (f.get("primary_purpose") or "").strip().lower()
        subtype = (f.get("purpose_subtype") or "").strip()[:80]
        other_desc = (f.get("other_purpose_description") or "").strip()[:300]
        try:
            area = float(f.get("building_area") or 0)
        except ValueError:
            area = 0.0
        try:
            n_floors = max(1, int(f.get("number_of_floors") or 1))
        except ValueError:
            n_floors = 1
        basement = 1 if f.get("basement_included") else 0
        roof     = 1 if f.get("roof_level_included") else 0
        ext_area = 1 if f.get("external_area_included") else 0

        # Spec s22 validation: purpose required; subtype required; Other
        # requires the free-text description.
        if not name:
            flash("Building name is required.", "warning"); return redirect(url_for("boq_building_new", pid=pid))
        if primary not in _BOQ_PRIMARY_PURPOSES:
            flash("Select a building purpose (Residential / Commercial / Industrial).", "warning")
            return redirect(url_for("boq_building_new", pid=pid))
        if not subtype:
            flash("Select a subtype for the chosen purpose.", "warning")
            return redirect(url_for("boq_building_new", pid=pid))
        if subtype == "Other" and not other_desc:
            flash("Enter a description for 'Other' purpose.", "warning")
            return redirect(url_for("boq_building_new", pid=pid))

        with get_db() as c:
            cur = c.execute(
                "INSERT INTO boq_buildings (project_id, building_name, building_code, "
                "primary_purpose, purpose_subtype, other_purpose_description, "
                "building_area, number_of_floors, basement_included, roof_level_included, "
                "external_area_included) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (pid, name, code, primary, subtype, other_desc,
                 area, n_floors, basement, roof, ext_area),
            )
            bid = int(cur.lastrowid or 0)
        _boq_make_floors(pid, bid, n_floors, bool(basement), bool(roof))
        try:
            from new_boq_hierarchy_schema import boq_audit
            boq_audit(get_db, uid, "boq_building_created", "boq_building", bid,
                      f"purpose={primary}/{subtype}")
        except Exception:
            pass
        flash(f"Building '{name}' created with {n_floors} floor(s).", "success")
        return redirect(url_for("boq_building_view", pid=pid, bid=bid))
    return render_template("boq_building_new.html",
                           user=current_user(), project=project,
                           subtypes=_BOQ_PURPOSE_SUBTYPES)


@app.route("/boq-projects/<int:pid>/buildings/<int:bid>")
@login_required
def boq_building_view(pid, bid):
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    building = _boq_building_owned_or_404(bid, pid)
    with get_db() as c:
        floors = c.execute(
            "SELECT f.*, "
            "  (SELECT COUNT(*) FROM boq_floor_items i WHERE i.floor_id=f.id) AS n_items, "
            "  (SELECT COALESCE(SUM(total_amount),0) FROM boq_floor_items i WHERE i.floor_id=f.id) AS subtotal "
            "FROM boq_floors f "
            "WHERE f.building_id=? ORDER BY f.floor_level",
            (bid,),
        ).fetchall()
        subtotal = c.execute(
            "SELECT COALESCE(SUM(total_amount),0) AS g FROM boq_floor_items WHERE building_id=?",
            (bid,),
        ).fetchone()
    return render_template("boq_building_view.html",
                           user=current_user(),
                           project=project, building=building, floors=floors,
                           building_subtotal=float(subtotal["g"] or 0) if subtotal else 0.0)


@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>")
@login_required
def boq_floor_view(pid, bid, fid):
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    building = _boq_building_owned_or_404(bid, pid)
    floor = _boq_floor_owned_or_404(fid, bid)
    with get_db() as c:
        items = c.execute(
            "SELECT i.*, b.final_built_up_rate AS bu_final, "
            "       b.basic_price AS bu_basic, b.supply_rate AS bu_supply, "
            "       b.install_rate AS bu_install, b.overhead_pct AS bu_oh, "
            "       b.profit_pct AS bu_profit, b.contingency_pct AS bu_cont, "
            "       b.vat_pct AS bu_vat "
            "FROM boq_floor_items i "
            "LEFT JOIN boq_floor_rate_buildup b ON b.floor_item_id=i.id "
            "WHERE i.floor_id=? ORDER BY i.section, i.id",
            (fid,),
        ).fetchall()
        subtotal_row = c.execute(
            "SELECT COALESCE(SUM(total_amount),0) AS g FROM boq_floor_items WHERE floor_id=?",
            (fid,),
        ).fetchone()
    return render_template("boq_floor_view.html",
                           user=current_user(),
                           project=project, building=building, floor=floor,
                           items=items,
                           floor_subtotal=float(subtotal_row["g"] or 0) if subtotal_row else 0.0,
                           sections=_BOQ_SECTIONS)


@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/items", methods=["POST"])
@login_required
def boq_floor_add_item(pid, bid, fid):
    uid = session["user_id"]
    _boq_project_owned_or_404(pid, uid)
    _boq_building_owned_or_404(bid, pid)
    _boq_floor_owned_or_404(fid, bid)
    csrf_protect()
    f = request.form

    def _num(name, default=0.0):
        try:
            v = f.get(name, "")
            return float(v) if v not in (None, "",) else float(default)
        except (TypeError, ValueError):
            return float(default)

    def _pct(name):
        return max(0.0, min(100.0, _num(name, 0.0)))

    desc = (f.get("description") or "").strip()[:500]
    if not desc:
        flash("Description is required.", "warning"); return redirect(url_for("boq_floor_view", pid=pid, bid=bid, fid=fid))
    section = (f.get("section") or "preliminaries").strip()[:80]
    spec    = (f.get("specification") or "").strip()
    unit    = (f.get("unit") or "No.").strip()[:20]
    qty     = max(0.0, _num("qty", 1.0))
    library_id = 0
    try:
        library_id = int(f.get("library_item_id") or 0)
    except ValueError:
        library_id = 0
    remarks = (f.get("remarks") or "").strip()[:500]
    save_option = (f.get("save_option") or "current_boq_only").strip()

    basic   = max(0.0, _num("basic_price", 0.0))
    # Rate engine v3 (2026-06-28): supply_pct + install_pct are PERCENTAGES.
    supply_pct  = _pct("supply_pct")
    install_pct = _pct("install_pct")
    oh, prf, vat = _pct("overhead_pct"), _pct("profit_pct"), _pct("vat_pct")
    vat_in_basic = 1 if f.get("vat_in_basic") else 0
    from boq_rate_v3 import boq_rate_v3
    supply, install, final_rate = boq_rate_v3(
        basic, supply_pct, install_pct, oh, prf, vat,
        vat_in_basic=bool(vat_in_basic))
    total = qty * final_rate
    if final_rate <= 0:
        flash("Rate must be > 0. Enter a basic price.", "warning")
        return redirect(url_for("boq_floor_view", pid=pid, bid=bid, fid=fid))

    # Optional: copy item to catalogue if save_option promotes it.
    catalogue_id = library_id if library_id > 0 else 0
    if save_option in ("save_to_project_library", "submit_to_master_library") and not catalogue_id:
        approval = ("pending_library_review"
                    if save_option == "submit_to_master_library"
                    else "project_only")
        source_type = ("project_library"
                       if save_option == "save_to_project_library"
                       else "custom_current_boq")
        try:
            with get_db() as c:
                cur = c.execute(
                    "INSERT INTO equipment_catalog "
                    "(category, name, brand, model, spec, unit, price_usd, "
                    " is_active, is_verified, is_public_visible, "
                    " source_type, approval_status, submitted_by_user_id) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (section, desc, "", "", spec, unit, basic,
                     1, 0, 0, source_type, approval, uid),
                )
                catalogue_id = int(cur.lastrowid or 0)
        except Exception:
            catalogue_id = 0

    src = ("master_library" if library_id > 0
           else ("project_library" if save_option == "save_to_project_library"
                 else ("pending_library_review" if save_option == "submit_to_master_library"
                       else "custom_current_boq")))
    approval = ("pending_library_review" if save_option == "submit_to_master_library"
                else ("project_only" if save_option == "save_to_project_library"
                      else "draft"))

    with get_db() as c:
        cur = c.execute(
            "INSERT INTO boq_floor_items "
            "(floor_id, building_id, project_id, user_id, section, subsection, "
            " library_item_id, supplier_id, item_no, description, specification, "
            " unit, qty, final_built_up_rate, total_amount, remarks, "
            " source_type, approval_status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (fid, bid, pid, uid, section, "",
             catalogue_id or None, None, "",
             desc, spec, unit, qty, final_rate, total, remarks,
             src, approval),
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
        boq_audit(get_db, uid, "boq_floor_item_added", "boq_floor_item", item_id,
                  f"section={section} rate={final_rate:.2f}")
    except Exception:
        pass
    flash("Line item added.", "success")
    return redirect(url_for("boq_floor_view", pid=pid, bid=bid, fid=fid))


@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/items/<int:iid>/delete", methods=["POST"])
@login_required
def boq_floor_delete_item(pid, bid, fid, iid):
    uid = session["user_id"]
    _boq_project_owned_or_404(pid, uid)
    _boq_building_owned_or_404(bid, pid)
    _boq_floor_owned_or_404(fid, bid)
    csrf_protect()
    with get_db() as c:
        c.execute("DELETE FROM boq_floor_rate_buildup WHERE floor_item_id=?", (iid,))
        c.execute("DELETE FROM boq_floor_items WHERE id=? AND floor_id=?", (iid, fid))
    try:
        from new_boq_hierarchy_schema import boq_audit
        boq_audit(get_db, uid, "boq_floor_item_deleted", "boq_floor_item", iid)
    except Exception:
        pass
    return redirect(url_for("boq_floor_view", pid=pid, bid=bid, fid=fid))


@app.route("/boq-projects/<int:pid>/boq")
@login_required
def boq_project_boq(pid):
    """Client-clean combined BOQ. ?view=internal exposes rate build-up."""
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    internal_view = bool(request.args.get("view") == "internal")
    with get_db() as c:
        rows = c.execute(
            "SELECT i.*, b.building_name, b.building_code, b.primary_purpose, "
            "       b.purpose_subtype, f.floor_name, f.floor_level, "
            "       rb.basic_price, rb.supply_rate, rb.install_rate, "
            "       rb.overhead_pct, rb.profit_pct, rb.contingency_pct, rb.vat_pct "
            "FROM boq_floor_items i "
            "JOIN boq_buildings b ON b.id=i.building_id "
            "JOIN boq_floors    f ON f.id=i.floor_id "
            "LEFT JOIN boq_floor_rate_buildup rb ON rb.floor_item_id=i.id "
            "WHERE i.project_id=? "
            "ORDER BY b.id, f.floor_level, i.section, i.id",
            (pid,),
        ).fetchall()
    if internal_view:
        try:
            from new_boq_hierarchy_schema import boq_audit
            boq_audit(get_db, uid, "boq_buildup_viewed", "boq_project", pid)
        except Exception:
            pass
    return render_template("boq_project_boq.html",
                           user=current_user(),
                           project=project, rows=rows,
                           internal_view=internal_view,
                           can_view_buildup=True,
                           sections_lookup=dict(_BOQ_SECTIONS))


@app.route("/boq-projects/<int:pid>/summary")
@login_required
def boq_project_summary(pid):
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    with get_db() as c:
        per_building = c.execute(
            "SELECT b.id, b.building_name, b.primary_purpose, b.purpose_subtype, "
            "       COALESCE(SUM(i.total_amount),0) AS subtotal "
            "FROM boq_buildings b "
            "LEFT JOIN boq_floor_items i ON i.building_id=b.id "
            "WHERE b.project_id=? GROUP BY b.id ORDER BY b.id",
            (pid,),
        ).fetchall()
        per_floor = c.execute(
            "SELECT b.id AS bid, b.building_name, f.id AS fid, f.floor_name, "
            "       f.floor_level, COALESCE(SUM(i.total_amount),0) AS subtotal "
            "FROM boq_floors f "
            "JOIN boq_buildings b ON b.id=f.building_id "
            "LEFT JOIN boq_floor_items i ON i.floor_id=f.id "
            "WHERE f.project_id=? GROUP BY b.id, f.id "
            "ORDER BY b.id, f.floor_level",
            (pid,),
        ).fetchall()
        grand_row = c.execute(
            "SELECT COALESCE(SUM(total_amount),0) AS g FROM boq_floor_items WHERE project_id=?",
            (pid,),
        ).fetchone()
    grand_total = float(grand_row["g"] or 0) if grand_row else 0.0
    return render_template("boq_project_summary.html",
                           user=current_user(),
                           project=project,
                           per_building=per_building,
                           per_floor=per_floor,
                           grand_total=grand_total)
