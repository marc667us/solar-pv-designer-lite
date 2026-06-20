# new_boq_add_library_item_route.py
# Phase 2 — POST /boms/<bom_id>/add-library-item.
#
# Master prompt sections 9-13: when the user can't find an item in the
# library, this route accepts the modal payload, builds the rate per the
# spec formula, optionally writes a new catalogue row (project library /
# master library submission), and adds the line to the current BOM with
# its full build-up stored as per-item overrides.
#
# Rate formula (spec s13):
#     supply  = basic_price if supply_rate empty else supply_rate
#     install = 0 if install_rate empty else install_rate
#     prelim  = supply + install
#     final   = prelim * (1 + oh% + profit% + contingency% + vat%)
#     total   = qty * final
#
# Save options:
#     current_boq_only          -> no catalogue row written
#     save_to_project_library   -> catalogue row, approval_status='project_only'
#     submit_to_master_library  -> catalogue row, approval_status='pending_library_review'


@app.route("/boms/<int:bom_id>/add-library-item", methods=["POST"])
@login_required
def boms_add_library_item(bom_id):
    """Phase 2: add a new BOQ library item with full rate build-up, optionally
    promoting it to the project or master catalogue."""
    uid = session["user_id"]
    bom = _bom_owned_or_404(bom_id, uid)
    csrf_protect()

    # Make sure the per-item override columns are in place (idempotent).
    try:
        from new_boq_hierarchy_schema import ensure_boq_hierarchy_schema, boq_audit
        ensure_boq_hierarchy_schema(get_db)
    except Exception:
        boq_audit = None  # type: ignore

    f = request.form

    def _num(name, default=0.0):
        try:
            v = f.get(name, "")
            return float(v) if v not in (None, "",) else float(default)
        except (TypeError, ValueError):
            return float(default)

    def _pct(name):
        v = _num(name, 0.0)
        return max(0.0, min(100.0, v))

    desc        = (f.get("description") or "").strip()[:500]
    section     = (f.get("section") or "preliminaries").strip()[:80]
    spec        = (f.get("specification") or "").strip()
    unit        = (f.get("unit") or "No.").strip()[:20]
    qty         = max(0.0, _num("qty", 1.0))
    brand       = (f.get("brand") or "").strip()[:120]
    supplier_nm = (f.get("supplier_name") or "").strip()[:200]
    remarks     = (f.get("remarks") or "").strip()[:500]
    save_option = (f.get("save_option") or "current_boq_only").strip()

    if not desc:
        flash("Description is required.", "warning")
        return redirect(url_for("boms_view", bom_id=bom_id))

    basic   = max(0.0, _num("basic_price", 0.0))
    supply  = _num("supply_rate", -1.0)
    install = _num("install_rate", -1.0)
    oh_pct  = _pct("overhead_pct")
    prf_pct = _pct("profit_pct")
    cnt_pct = _pct("contingency_pct")
    vat_pct = _pct("vat_pct")

    # Spec s13: supply defaults to basic, install defaults to 0.
    if supply < 0:
        supply = basic
    if install < 0:
        install = 0.0
    prelim = supply + install
    final_rate = prelim * (1.0 + (oh_pct + prf_pct + cnt_pct + vat_pct) / 100.0)
    total_amount = qty * final_rate

    if final_rate <= 0:
        flash("Item rate must be > 0. Enter a basic price or supply rate.", "warning")
        return redirect(url_for("boms_view", bom_id=bom_id))

    # Optional catalogue row (Save to Project Library / Submit to Master).
    catalogue_id = 0
    if save_option in ("save_to_project_library", "submit_to_master_library"):
        approval = ("pending_library_review"
                    if save_option == "submit_to_master_library"
                    else "project_only")
        source_type = ("custom_current_boq"
                       if save_option == "save_to_project_library"
                       else "project_library")
        try:
            with get_db() as c:
                cur = c.execute(
                    "INSERT INTO equipment_catalog "
                    "(category, name, brand, model, spec, unit, price_usd, "
                    " is_active, is_verified, is_public_visible, "
                    " source_type, approval_status, submitted_by_user_id) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (section, desc, brand, "", spec, unit, basic,
                     1, 0, 0,  # not public, not verified -- pending review
                     source_type, approval,
                     uid),
                )
                catalogue_id = int(cur.lastrowid or 0)
        except Exception:
            catalogue_id = 0  # non-fatal -- still add the line

    # Insert the BOM line with the full per-item build-up stored as overrides.
    try:
        with get_db() as c:
            c.execute(
                "INSERT INTO marketplace_bom_items "
                "(bom_id, product_id, custom_name, qty, unit, unit_price_override, notes, "
                " basic_price, supply_rate, install_rate, overhead_pct, profit_pct, "
                " contingency_pct, vat_pct, final_built_up_rate, remarks, "
                " source_type, approval_status) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (bom_id, catalogue_id, desc, qty, unit, final_rate, spec[:500],
                 basic, supply, install, oh_pct, prf_pct,
                 cnt_pct, vat_pct, final_rate, remarks,
                 ("project_library" if save_option == "save_to_project_library"
                  else "custom_current_boq" if save_option == "current_boq_only"
                  else "pending_library_review"),
                 ("pending_library_review"
                  if save_option == "submit_to_master_library"
                  else ("project_only" if save_option == "save_to_project_library"
                        else "draft"))),
            )
            c.execute(
                "UPDATE marketplace_boms SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (bom_id,),
            )
    except Exception as e:
        try:
            app.logger.warning("add_library_item failed: %s", e)
        except Exception:
            pass
        flash("Could not add the item — please try again.", "danger")
        return redirect(url_for("boms_view", bom_id=bom_id))

    # Audit log (best-effort).
    if boq_audit:
        try:
            boq_audit(get_db, uid, "library_item_added",
                      "marketplace_bom", bom_id,
                      f"save={save_option} catalogue_id={catalogue_id} rate={final_rate:.2f}")
        except Exception:
            pass

    msg = {
        "current_boq_only":         "Item added to this BOQ only.",
        "save_to_project_library":  "Item added and saved to project library.",
        "submit_to_master_library": "Item added — submitted to master library for review.",
    }.get(save_option, "Item added.")
    flash(msg, "success")
    return redirect(url_for("boms_view", bom_id=bom_id))


@app.route("/admin/library/pending")
@login_required
def admin_library_pending():
    """Admin: list catalogue items pending review (Submit to Master Library)."""
    u = current_user()
    if not (u and u["is_admin"]):
        abort(403)
    try:
        from new_boq_hierarchy_schema import ensure_boq_hierarchy_schema
        ensure_boq_hierarchy_schema(get_db)
    except Exception:
        pass
    with get_db() as c:
        rows = c.execute(
            "SELECT id, name, brand, spec, unit, price_usd, category, "
            "       source_type, approval_status, submitted_by_user_id, created_at "
            "FROM equipment_catalog "
            "WHERE approval_status='pending_library_review' "
            "ORDER BY id DESC LIMIT 200"
        ).fetchall()
    return render_template("admin_library_pending.html", user=u, rows=rows)


@app.route("/admin/library/<int:item_id>/approve", methods=["POST"])
@login_required
def admin_library_approve(item_id):
    u = current_user()
    if not (u and u["is_admin"]):
        abort(403)
    csrf_protect()
    with get_db() as c:
        c.execute(
            "UPDATE equipment_catalog "
            "SET approval_status='approved_library_item', "
            "    is_verified=1, is_public_visible=1 "
            "WHERE id=? AND approval_status='pending_library_review'",
            (item_id,),
        )
    try:
        from new_boq_hierarchy_schema import boq_audit
        boq_audit(get_db, session["user_id"], "library_item_approved",
                  "equipment_catalog", item_id)
    except Exception:
        pass
    flash(f"Library item #{item_id} approved.", "success")
    return redirect(url_for("admin_library_pending"))


@app.route("/admin/library/<int:item_id>/reject", methods=["POST"])
@login_required
def admin_library_reject(item_id):
    u = current_user()
    if not (u and u["is_admin"]):
        abort(403)
    csrf_protect()
    with get_db() as c:
        c.execute(
            "UPDATE equipment_catalog SET approval_status='rejected' WHERE id=?",
            (item_id,),
        )
    try:
        from new_boq_hierarchy_schema import boq_audit
        boq_audit(get_db, session["user_id"], "library_item_rejected",
                  "equipment_catalog", item_id)
    except Exception:
        pass
    flash(f"Library item #{item_id} rejected.", "warning")
    return redirect(url_for("admin_library_pending"))
