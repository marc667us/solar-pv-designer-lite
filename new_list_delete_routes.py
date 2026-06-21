# new_list_delete_routes.py
# Per-list Remove actions: BOM, RFQ, price sheet. BOQ project deletion
# already exists. All four require ownership through the *_owned_or_404
# helpers + typed confirmation on destructive actions where the modal
# already supplies it.


@app.route("/boms/<int:bom_id>/delete", methods=["POST"])
@login_required
def boms_delete(bom_id):
    uid = session["user_id"]
    bom = _bom_owned_or_404(bom_id, uid)
    csrf_protect()
    title = bom["title"]
    with get_db() as c:
        c.execute("DELETE FROM marketplace_bom_items WHERE bom_id=?", (bom_id,))
        try: c.execute("DELETE FROM marketplace_bom_rates WHERE bom_id=?", (bom_id,))
        except Exception: pass
        c.execute("DELETE FROM marketplace_boms WHERE id=? AND user_id=?", (bom_id, uid))
    flash(f"BOM/Quick Cost Estimate '{title}' deleted.", "success")
    return redirect(url_for("boms_list"))


@app.route("/rfqs/<int:rfq_id>/delete", methods=["POST"])
@login_required
def rfqs_delete(rfq_id):
    uid = session["user_id"]
    csrf_protect()
    # Ownership check
    with get_db() as c:
        r = c.execute(
            "SELECT title, user_id FROM rfqs WHERE id=?", (rfq_id,)
        ).fetchone()
    if not r or int(r["user_id"] or 0) != int(uid):
        u = current_user()
        if not (u and u["is_admin"]):
            abort(404)
    title = r["title"]
    with get_db() as c:
        c.execute("DELETE FROM rfq_items WHERE rfq_id=?", (rfq_id,))
        try: c.execute("DELETE FROM rfq_supplier_targets WHERE rfq_id=?", (rfq_id,))
        except Exception: pass
        try: c.execute("DELETE FROM rfq_responses WHERE rfq_id=?", (rfq_id,))
        except Exception: pass
        c.execute("DELETE FROM rfqs WHERE id=?", (rfq_id,))
    flash(f"RFQ '{title}' deleted.", "success")
    return redirect(url_for("rfqs_list"))


@app.route("/price-sheets/<int:sheet_id>/delete", methods=["POST"])
@login_required
def price_sheets_delete(sheet_id):
    uid = session["user_id"]
    csrf_protect()
    with get_db() as c:
        s = c.execute(
            "SELECT title, user_id FROM marketplace_price_sheets WHERE id=?",
            (sheet_id,),
        ).fetchone()
    if not s or int(s["user_id"] or 0) != int(uid):
        u = current_user()
        if not (u and u["is_admin"]):
            abort(404)
    title = s["title"]
    with get_db() as c:
        c.execute(
            "DELETE FROM marketplace_price_sheet_items WHERE sheet_id=?", (sheet_id,)
        )
        c.execute(
            "DELETE FROM marketplace_price_sheets WHERE id=?", (sheet_id,)
        )
    flash(f"Basic Price Sheet '{title}' deleted.", "success")
    return redirect(url_for("price_sheets_list"))
