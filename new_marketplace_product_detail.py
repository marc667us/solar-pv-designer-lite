# ─── Route — public product detail (/marketplace/product/<id>) ───────────────
# CLAUDE.md claimed Slice 1 included this route; it never shipped. Adding it
# now so the marketplace cards can deep-link to a full-spec view and so
# `/marketplace/product/<id>` stops 404-ing on prod.


@app.route("/marketplace/product/<int:pid>")
def marketplace_product_detail(pid):
    _ensure_marketplace_tables()
    currency = (request.args.get("currency") or "GHS").strip().upper()
    if currency not in _CURRENCY_RATES_FROM_USD:
        currency = "GHS"
    rate = _CURRENCY_RATES_FROM_USD.get(currency, 1.0)
    with get_db() as c:
        row = c.execute(
            "SELECT ec.*, "
            "       s.id   AS supplier_id, "
            "       s.name AS supplier_name, "
            "       s.country AS supplier_country, "
            "       s.phone   AS supplier_phone, "
            "       s.email   AS supplier_email, "
            "       s.address AS supplier_address, "
            "       s.is_verified AS supplier_verified, "
            "       pc.name AS category_name, pc.icon AS category_icon "
            "FROM equipment_catalog ec "
            "LEFT JOIN suppliers s            ON s.id = ec.supplier_id "
            "LEFT JOIN product_categories pc  ON pc.id = ec.category_id "
            "WHERE ec.id=? "
            "  AND ec.is_active=1 AND ec.is_public_visible=1 AND ec.is_verified=1",
            (pid,),
        ).fetchone()
    if not row:
        abort(404)
    product = dict(row)
    product["price_in_currency"] = float(product.get("price_usd") or 0) * float(rate)
    return render_template(
        "marketplace_product.html",
        user=current_user(),
        product=product,
        currency=currency,
        currencies=list(_CURRENCY_RATES_FROM_USD.keys()),
        rates_as_of=_CURRENCY_RATES_AS_OF,
    )
