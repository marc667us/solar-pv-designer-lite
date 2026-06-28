# new_boq_bom_sync_route.py
# 2026-06-28: pull quantities from a BOM into the BOQ project's items.
# Matches BOM `custom_name` against BOQ `description` (case-insensitive
# substring); on a match, overwrites the BOQ qty + recomputes total.


@app.route("/boq-projects/<int:pid>/sync-from-bom", methods=["GET", "POST"])
@login_required
def boq_project_sync_from_bom(pid):
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)

    # GET: render a picker page listing the owner's BOMs (most recent first).
    if request.method == "GET":
        with get_db() as c:
            boms = c.execute(
                "SELECT id, title, project_name, client_name, updated_at, "
                "  (SELECT COUNT(*) FROM marketplace_bom_items WHERE bom_id=marketplace_boms.id) AS n_items "
                "FROM marketplace_boms WHERE user_id=? ORDER BY updated_at DESC, id DESC",
                (uid,),
            ).fetchall()
        return render_template(
            "boq_sync_from_bom.html",
            user=current_user(), project=project, boms=boms,
        )

    csrf_protect()
    try:
        bom_id = int(request.form.get("bom_id") or 0)
    except (TypeError, ValueError):
        bom_id = 0
    if bom_id <= 0:
        flash("Pick a BOM to sync from.", "warning")
        return redirect(url_for("boq_project_sync_from_bom", pid=pid))

    with get_db() as c:
        bom = c.execute(
            "SELECT id, title FROM marketplace_boms WHERE id=? AND user_id=?",
            (bom_id, uid),
        ).fetchone()
        if not bom:
            flash("BOM not found.", "warning")
            return redirect(url_for("boq_project_sync_from_bom", pid=pid))
        bom_items = c.execute(
            "SELECT custom_name, qty, unit FROM marketplace_bom_items WHERE bom_id=?",
            (bom_id,),
        ).fetchall()
        items = c.execute(
            "SELECT id, description, qty AS old_qty, final_built_up_rate "
            "FROM boq_floor_items WHERE project_id=?",
            (pid,),
        ).fetchall()

    # Build a lowercase-name lookup. Multiple BOM items with the same name
    # collapse to the SUM of their qty (preserves total intent).
    bom_lookup = {}
    for bi in bom_items:
        key = (bi["custom_name"] or "").strip().lower()
        if not key:
            continue
        bom_lookup[key] = bom_lookup.get(key, 0.0) + float(bi["qty"] or 0)

    updated = 0
    skipped = 0
    with get_db() as c:
        for it in items:
            desc = (it["description"] or "").strip().lower()
            new_qty = None
            # Exact match first; fall back to first BOM key that's a
            # substring of the item description.
            if desc in bom_lookup:
                new_qty = bom_lookup[desc]
            else:
                for k, q in bom_lookup.items():
                    if k and k in desc:
                        new_qty = q; break
            if new_qty is None or new_qty <= 0:
                skipped += 1
                continue
            if abs(float(it["old_qty"] or 0) - float(new_qty)) < 1e-9:
                skipped += 1
                continue
            rate = float(it["final_built_up_rate"] or 0)
            new_total = float(new_qty) * rate
            c.execute(
                "UPDATE boq_floor_items SET qty=?, total_amount=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=? AND project_id=?",
                (float(new_qty), new_total, it["id"], pid),
            )
            c.execute(
                "UPDATE boq_floor_rate_buildup SET total_amount=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE floor_item_id=?",
                (new_total, it["id"]),
            )
            updated += 1

    try:
        from new_boq_hierarchy_schema import boq_audit
        boq_audit(get_db, uid, "boq_bom_sync", "boq_project", pid,
                  f"bom_id={bom_id} updated={updated} skipped={skipped}")
    except Exception:
        pass

    flash(f"Synced from BOM \"{bom['title']}\": {updated} item(s) updated, {skipped} unchanged.", "success")
    return redirect(url_for("boq_project_overview", pid=pid))
