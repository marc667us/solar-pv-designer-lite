# new_unattended_routes.py
# 2026-06-21 -- three pending items from the owner's "check unattended"
# audit, all in one place:
#
#   A. POST /boms/<bom_id>/items/<item_id>/edit-qty
#      Inline qty edit on the BOM/Quick Cost Estimate editor. Updates
#      qty (and optionally unit + unit_price_override) for a single row.
#      Recomputes nothing -- _bom_totals_with_rates derives everything
#      from qty + override on read.
#
#   B. POST /boq-projects/<pid>/buildings/<bid>/floors/<fid>/items/<iid>/move
#      Up/down reordering for floor BOQ items inside a section. Swaps
#      display_order with the adjacent item in the same (bill_no,
#      section_letter) group. Schema adds a display_order REAL column
#      (idempotent ALTER).
#
#   C. boq_floor_view ordering uses display_order ASC so the manual
#      reorder is honored alongside the existing bill/section grouping.


# ---- Schema: display_order on floor items ----

def _ensure_display_order_column():
    is_pg = bool(os.environ.get("DATABASE_URL"))
    try:
        with get_db() as c:
            if is_pg:
                try: c.execute("ALTER TABLE boq_floor_items ADD COLUMN IF NOT EXISTS display_order REAL DEFAULT 0")
                except Exception: pass
            else:
                try: c.execute("ALTER TABLE boq_floor_items ADD COLUMN display_order REAL DEFAULT 0")
                except Exception: pass
    except Exception:
        pass


# ---- A. Edit qty on BOM line item ----

@app.route("/boms/<int:bom_id>/items/<int:item_id>/edit-qty", methods=["POST"])
@login_required
def boms_edit_item_qty(bom_id, item_id):
    """Inline qty (+ optional unit + override) edit on the BOM editor.
    The Quick Cost Estimate is NOT a basic price sheet -- the owner needs
    to set real quantities + may want to override the unit price."""
    uid = session["user_id"]
    _bom_owned_or_404(bom_id, uid)
    csrf_protect()
    f = request.form
    try:
        qty = max(0.0, float(f.get("qty") or 0))
    except (TypeError, ValueError):
        qty = 0.0
    if qty <= 0:
        flash("Quantity must be greater than 0.", "warning")
        return redirect(url_for("boms_view", bom_id=bom_id))
    unit = (f.get("unit") or "").strip()[:20] or None
    override_raw = (f.get("unit_price_override") or "").strip()
    try:
        override = float(override_raw) if override_raw else None
    except ValueError:
        override = None

    with get_db() as c:
        if unit and override is not None:
            c.execute(
                "UPDATE marketplace_bom_items SET qty=?, unit=?, unit_price_override=? "
                "WHERE id=? AND bom_id=?",
                (qty, unit, override, item_id, bom_id),
            )
        elif unit:
            c.execute(
                "UPDATE marketplace_bom_items SET qty=?, unit=? WHERE id=? AND bom_id=?",
                (qty, unit, item_id, bom_id),
            )
        elif override is not None:
            c.execute(
                "UPDATE marketplace_bom_items SET qty=?, unit_price_override=? "
                "WHERE id=? AND bom_id=?",
                (qty, override, item_id, bom_id),
            )
        else:
            c.execute(
                "UPDATE marketplace_bom_items SET qty=? WHERE id=? AND bom_id=?",
                (qty, item_id, bom_id),
            )
        c.execute(
            "UPDATE marketplace_boms SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (bom_id,),
        )
    flash(f"Line #{item_id} updated to qty {qty}.", "success")
    return redirect(url_for("boms_view", bom_id=bom_id))


# ---- B. Move floor BOQ item up/down ----

@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/items/<int:iid>/move", methods=["POST"])
@login_required
def boq_floor_move_item(pid, bid, fid, iid):
    """Swap display_order with the adjacent item in the same (bill_no,
    section_letter) group, in the requested direction."""
    uid = session["user_id"]
    _boq_project_owned_or_404(pid, uid)
    _boq_building_owned_or_404(bid, pid)
    _boq_floor_owned_or_404(fid, bid)
    csrf_protect()
    _ensure_display_order_column()
    direction = (request.form.get("dir") or "up").lower()
    if direction not in ("up", "down"):
        direction = "up"
    with get_db() as c:
        me = c.execute(
            "SELECT id, bill_no, section_letter, COALESCE(display_order,0) AS d_order "
            "FROM boq_floor_items WHERE id=? AND floor_id=?",
            (iid, fid),
        ).fetchone()
        if not me:
            abort(404)
        # Backfill display_order for the whole section if every row is 0
        # (initial state) so we have something to swap against.
        rows = c.execute(
            "SELECT id, COALESCE(display_order,0) AS d_order FROM boq_floor_items "
            "WHERE floor_id=? AND bill_no=? AND section_letter=? ORDER BY id",
            (fid, me["bill_no"], me["section_letter"]),
        ).fetchall()
        all_zero = all(float(r["d_order"] or 0) == 0 for r in rows)
        if all_zero:
            for n, r in enumerate(rows, 1):
                c.execute(
                    "UPDATE boq_floor_items SET display_order=? WHERE id=?",
                    (float(n), r["id"]),
                )
            me_order = float([n for n, r in enumerate(rows, 1) if r["id"] == iid][0])
        else:
            me_order = float(me["d_order"] or 0)
        # Find the adjacent neighbour in the requested direction.
        if direction == "up":
            neigh = c.execute(
                "SELECT id, COALESCE(display_order,0) AS d_order FROM boq_floor_items "
                "WHERE floor_id=? AND bill_no=? AND section_letter=? "
                "  AND COALESCE(display_order,0) < ? "
                "ORDER BY COALESCE(display_order,0) DESC LIMIT 1",
                (fid, me["bill_no"], me["section_letter"], me_order),
            ).fetchone()
        else:
            neigh = c.execute(
                "SELECT id, COALESCE(display_order,0) AS d_order FROM boq_floor_items "
                "WHERE floor_id=? AND bill_no=? AND section_letter=? "
                "  AND COALESCE(display_order,0) > ? "
                "ORDER BY COALESCE(display_order,0) ASC LIMIT 1",
                (fid, me["bill_no"], me["section_letter"], me_order),
            ).fetchone()
        if neigh:
            # Swap
            c.execute(
                "UPDATE boq_floor_items SET display_order=? WHERE id=?",
                (float(neigh["d_order"] or 0), iid),
            )
            c.execute(
                "UPDATE boq_floor_items SET display_order=? WHERE id=?",
                (me_order, neigh["id"]),
            )
            c.execute(
                "UPDATE boq_floors SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (fid,),
            )
    try:
        from new_boq_hierarchy_schema import boq_audit
        boq_audit(get_db, uid, f"boq_floor_item_moved_{direction}",
                  "boq_floor_item", iid)
    except Exception:
        pass
    return redirect(url_for("boq_floor_view", pid=pid, bid=bid, fid=fid))
