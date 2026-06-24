# new_catalogue_pricing_routes.py
# 2026-06-24 -- B + C: 3-quote Recheck Prices schema + Catalogue unit-price
# correction routes.
#
# Three additions:
#   1. _ensure_pricing_tables() -- equipment_catalog_quotes (B) +
#      equipment_catalog_price_history (C). Idempotent SQLite + Postgres.
#   2. Admin per-row "Update price" route + history view (C).
#   3. Helpers _record_catalog_quote() and _record_price_history()
#      reused by the BOM recheck-apply flow (cross-feature push-to-catalogue).
#
# Per CLAUDE.md: zero-cost, no paid services. All routes are admin-gated.


import json as _json


# ─────────────────────────── Schema bootstrap ───────────────────────────


_PRICING_SCHEMA_DONE = {"v": False}


def _ensure_pricing_tables(get_db, is_pg_fn):
    """Idempotent. equipment_catalog_quotes (3-quote history) +
    equipment_catalog_price_history (every basic-price change)."""
    if _PRICING_SCHEMA_DONE["v"]:
        return
    is_pg = bool(is_pg_fn())
    quotes_ddl_pg = """
        CREATE TABLE IF NOT EXISTS equipment_catalog_quotes (
            id              SERIAL PRIMARY KEY,
            catalog_item_id INTEGER NOT NULL,
            supplier_name   VARCHAR(200) NOT NULL DEFAULT '',
            supplier_id     INTEGER DEFAULT 0,
            price_local     REAL DEFAULT 0,
            currency        VARCHAR(3) DEFAULT 'GHS',
            quoted_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source_note     TEXT DEFAULT '',
            anomaly_flag    INTEGER DEFAULT 0,
            status          VARCHAR(20) DEFAULT 'proposed',
            recorded_by     INTEGER DEFAULT 0
        )
    """
    quotes_ddl_sqlite = """
        CREATE TABLE IF NOT EXISTS equipment_catalog_quotes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            catalog_item_id INTEGER NOT NULL,
            supplier_name   TEXT DEFAULT '',
            supplier_id     INTEGER DEFAULT 0,
            price_local     REAL DEFAULT 0,
            currency        TEXT DEFAULT 'GHS',
            quoted_at       TEXT DEFAULT CURRENT_TIMESTAMP,
            source_note     TEXT DEFAULT '',
            anomaly_flag    INTEGER DEFAULT 0,
            status          TEXT DEFAULT 'proposed',
            recorded_by     INTEGER DEFAULT 0
        )
    """
    history_ddl_pg = """
        CREATE TABLE IF NOT EXISTS equipment_catalog_price_history (
            id                  SERIAL PRIMARY KEY,
            catalog_item_id     INTEGER NOT NULL,
            old_price_usd       REAL DEFAULT 0,
            new_price_usd       REAL DEFAULT 0,
            currency_local      VARCHAR(3) DEFAULT '',
            new_price_local     REAL DEFAULT 0,
            source              VARCHAR(200) DEFAULT '',
            reason              TEXT DEFAULT '',
            set_by_user_id      INTEGER DEFAULT 0,
            submitted_by_email  VARCHAR(200) DEFAULT '',
            approval_status     VARCHAR(20) DEFAULT 'approved',
            set_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            decided_at          TIMESTAMP,
            decided_by_user_id  INTEGER DEFAULT 0
        )
    """
    history_ddl_sqlite = """
        CREATE TABLE IF NOT EXISTS equipment_catalog_price_history (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            catalog_item_id     INTEGER NOT NULL,
            old_price_usd       REAL DEFAULT 0,
            new_price_usd       REAL DEFAULT 0,
            currency_local      TEXT DEFAULT '',
            new_price_local     REAL DEFAULT 0,
            source              TEXT DEFAULT '',
            reason              TEXT DEFAULT '',
            set_by_user_id      INTEGER DEFAULT 0,
            submitted_by_email  TEXT DEFAULT '',
            approval_status     TEXT DEFAULT 'approved',
            set_at              TEXT DEFAULT CURRENT_TIMESTAMP,
            decided_at          TEXT,
            decided_by_user_id  INTEGER DEFAULT 0
        )
    """
    for ddl in (
        quotes_ddl_pg if is_pg else quotes_ddl_sqlite,
        history_ddl_pg if is_pg else history_ddl_sqlite,
        "CREATE INDEX IF NOT EXISTS idx_eq_cat_quotes_item "
        "ON equipment_catalog_quotes(catalog_item_id)",
        "CREATE INDEX IF NOT EXISTS idx_eq_cat_history_item "
        "ON equipment_catalog_price_history(catalog_item_id)",
        "CREATE INDEX IF NOT EXISTS idx_eq_cat_history_status "
        "ON equipment_catalog_price_history(approval_status)",
    ):
        try:
            with get_db() as c:
                c.execute(ddl)
        except Exception:
            pass
    # Idempotent ALTERs for the 3 columns added 2026-06-24 v3 (anomaly queue).
    for col_ddl in (
        "ALTER TABLE equipment_catalog_price_history ADD COLUMN "
        + ("IF NOT EXISTS " if is_pg else "")
        + "submitted_by_email "
        + ("VARCHAR(200) DEFAULT ''" if is_pg else "TEXT DEFAULT ''"),
        "ALTER TABLE equipment_catalog_price_history ADD COLUMN "
        + ("IF NOT EXISTS " if is_pg else "")
        + "decided_at "
        + ("TIMESTAMP" if is_pg else "TEXT"),
        "ALTER TABLE equipment_catalog_price_history ADD COLUMN "
        + ("IF NOT EXISTS " if is_pg else "")
        + "decided_by_user_id INTEGER DEFAULT 0",
    ):
        try:
            with get_db() as c:
                c.execute(col_ddl)
        except Exception:
            pass
    _PRICING_SCHEMA_DONE["v"] = True


# ─────────────────────────── Shared helpers ────────────────────────────


def _resolve_user_email(get_db, user_id):
    """Look up the user's email by id. Returns '' on miss."""
    if not user_id:
        return ""
    try:
        with get_db() as c:
            row = c.execute(
                "SELECT email FROM users WHERE id=?", (int(user_id),),
            ).fetchone()
        if row:
            return (row["email"] or "")[:200]
    except Exception:
        pass
    return ""


def _record_price_history(get_db, item_id, old_usd, new_usd,
                           currency_local, new_local, source, reason,
                           user_id, status="approved",
                           submitted_by_email=None):
    """Append a history row. Non-raising. Returns the inserted row id (or 0)."""
    if submitted_by_email is None:
        submitted_by_email = _resolve_user_email(get_db, user_id)
    try:
        with get_db() as c:
            cur = c.execute(
                "INSERT INTO equipment_catalog_price_history "
                "(catalog_item_id, old_price_usd, new_price_usd, "
                " currency_local, new_price_local, source, reason, "
                " set_by_user_id, submitted_by_email, approval_status) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (int(item_id or 0), float(old_usd or 0), float(new_usd or 0),
                 (currency_local or "")[:3], float(new_local or 0),
                 (source or "")[:200], (reason or "")[:500],
                 int(user_id or 0), (submitted_by_email or "")[:200],
                 (status or "approved")[:20]),
            )
            try:
                return int(cur.lastrowid or 0)
            except Exception:
                return 0
    except Exception:
        # Schema may pre-date submitted_by_email -- retry without it.
        try:
            with get_db() as c:
                c.execute(
                    "INSERT INTO equipment_catalog_price_history "
                    "(catalog_item_id, old_price_usd, new_price_usd, "
                    " currency_local, new_price_local, source, reason, "
                    " set_by_user_id, approval_status) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (int(item_id or 0), float(old_usd or 0), float(new_usd or 0),
                     (currency_local or "")[:3], float(new_local or 0),
                     (source or "")[:200], (reason or "")[:500],
                     int(user_id or 0), (status or "approved")[:20]),
                )
        except Exception:
            pass
    return 0


def _record_catalog_quote(get_db, item_id, supplier_name, supplier_id,
                          price_local, currency, source_note, anomaly,
                          user_id, status="proposed"):
    """Append a quote row. Non-raising."""
    try:
        with get_db() as c:
            c.execute(
                "INSERT INTO equipment_catalog_quotes "
                "(catalog_item_id, supplier_name, supplier_id, price_local, "
                " currency, source_note, anomaly_flag, status, recorded_by) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (int(item_id or 0), (supplier_name or "")[:200],
                 int(supplier_id or 0), float(price_local or 0),
                 (currency or "GHS")[:3], (source_note or "")[:500],
                 1 if anomaly else 0, (status or "proposed")[:20],
                 int(user_id or 0)),
            )
    except Exception:
        pass


# ─────────────────────────── Routes ────────────────────────────


def register_catalogue_pricing_routes(
    app, admin_required, session, request, redirect, url_for, flash,
    render_template, current_user, get_db, csrf_protect, _CURRENCY_RATES_FROM_USD,
):
    is_pg_fn = lambda: bool(__import__("os").environ.get("DATABASE_URL"))

    @app.before_request
    def _ensure_pricing_schema_once():
        _ensure_pricing_tables(get_db, is_pg_fn)

    @app.context_processor
    def _inject_pending_anomaly_count():
        """Expose `pending_anomaly_count` to every template so the catalogue
        + bulk-recheck pages can badge it. Non-raising; returns 0 on miss."""
        try:
            with get_db() as c:
                row = c.execute(
                    "SELECT COUNT(*) AS n FROM equipment_catalog_price_history "
                    "WHERE approval_status='pending'"
                ).fetchone()
            return {"pending_anomaly_count": int((row["n"] if row else 0) or 0)}
        except Exception:
            return {"pending_anomaly_count": 0}

    @app.route("/admin/catalogue/<int:item_id>/update-price",
               methods=["POST"])
    @admin_required
    def admin_catalogue_update_price(item_id):
        """Admin per-row Update Price -- writes a history row + updates
        equipment_catalog.price_usd in one transaction."""
        csrf_protect()
        f = request.form
        try:
            new_price = float((f.get("new_price") or "0").strip())
        except (TypeError, ValueError):
            new_price = -1.0
        if new_price < 0:
            flash("Enter a non-negative price.", "warning")
            return redirect(url_for("procurement_catalog"))
        currency = (f.get("currency") or "USD").upper().strip()[:3]
        source   = (f.get("source") or "").strip()[:200]
        reason   = (f.get("reason") or "").strip()[:500]

        # Convert local -> USD if currency != USD. price_usd is the canonical
        # storage column. fx rate uses _CURRENCY_RATES_FROM_USD lookup.
        fx_rate = float(_CURRENCY_RATES_FROM_USD.get(currency, 1.0) or 1.0)
        if fx_rate <= 0:
            fx_rate = 1.0
        new_usd = new_price if currency == "USD" else (new_price / fx_rate)

        with get_db() as c:
            row = c.execute(
                "SELECT price_usd FROM equipment_catalog WHERE id=?",
                (item_id,),
            ).fetchone()
            if not row:
                flash("Catalogue item not found.", "warning")
                return redirect(url_for("procurement_catalog"))
            old_usd = float(row["price_usd"] or 0)
            c.execute(
                "UPDATE equipment_catalog SET price_usd=? WHERE id=?",
                (new_usd, item_id),
            )
        uid = session.get("user_id") or 0
        _record_price_history(
            get_db, item_id, old_usd, new_usd, currency, new_price,
            source, reason, uid, status="approved",
        )
        # audit log (best-effort)
        try:
            from new_boq_hierarchy_schema import boq_audit
            boq_audit(get_db, uid, "catalogue_price_updated",
                      "equipment_catalog", item_id,
                      f"old_usd={old_usd:.2f} new_usd={new_usd:.2f} "
                      f"src={source!r}")
        except Exception:
            pass
        flash(
            f"Updated catalogue price: USD {old_usd:.2f} -> {new_usd:.2f} "
            f"({currency} {new_price:.2f}). History logged.",
            "success",
        )
        return redirect(url_for("procurement_catalog"))

    # ─────────── Bulk catalogue recheck (admin-only) ───────────

    @app.route("/admin/marketplace/recheck", methods=["GET", "POST"])
    @admin_required
    def admin_marketplace_recheck():
        """Bulk recheck a catalogue category against the LLM. GET shows
        the picker form (category + country/currency + cap). POST runs
        the LLM on the matching items and redirects to the review page."""
        with get_db() as c:
            categories = c.execute(
                "SELECT id, name, code FROM product_categories "
                "WHERE is_active=1 ORDER BY display_order, name"
            ).fetchall()

        if request.method == "GET":
            return render_template(
                "admin_marketplace_recheck.html",
                user=current_user(), categories=categories,
            )

        # POST -- run the LLM
        csrf_protect()
        f = request.form
        try:
            cat_id = int(f.get("category_id") or 0)
        except (TypeError, ValueError):
            cat_id = 0
        if cat_id <= 0:
            flash("Pick a category.", "warning")
            return redirect(url_for("admin_marketplace_recheck"))
        currency = (f.get("currency") or "GHS").upper().strip()[:3]
        try:
            cap = int(f.get("cap") or 30)
        except (TypeError, ValueError):
            cap = 30
        cap = max(1, min(50, cap))

        with get_db() as c:
            cat_row = c.execute(
                "SELECT id, name FROM product_categories WHERE id=?",
                (cat_id,),
            ).fetchone()
            if not cat_row:
                flash("Category not found.", "warning")
                return redirect(url_for("admin_marketplace_recheck"))
            cat_name = cat_row["name"]
            items = c.execute(
                "SELECT id, name, brand, model, spec, unit, price_usd "
                "FROM equipment_catalog "
                "WHERE category_id=? AND is_active=1 "
                "ORDER BY id LIMIT ?",
                (cat_id, cap),
            ).fetchall()

        if not items:
            flash(f"No active products in '{cat_name}'.", "warning")
            return redirect(url_for("admin_marketplace_recheck"))

        # Reuse the recheck engine from new_recheck_prices_routes.
        from new_recheck_prices_routes import (
            _recheck_build_prompt, _recheck_call_llm, _recheck_parse,
            _recheck_country_for,
        )
        country, _ = _recheck_country_for(currency)
        fx_rate = float(_CURRENCY_RATES_FROM_USD.get(currency, 1.0) or 1.0)
        if fx_rate <= 0:
            fx_rate = 1.0

        prompt_items = []
        for it in items:
            current_local = float(it["price_usd"] or 0) * fx_rate
            prompt_items.append({
                "id": int(it["id"]),
                "name": str(it["name"] or ""),
                "spec": str((it["spec"] if "spec" in it.keys() else "") or ""),
                "brand": str((it["brand"] if "brand" in it.keys() else "") or ""),
                "unit": str(it["unit"] or "No."),
                "current_price": current_local,
            })
        prompt = _recheck_build_prompt(prompt_items, country, currency)
        raw, src = _recheck_call_llm(prompt)
        if raw is None:
            flash(
                f"Bulk recheck could not reach any AI provider ({src}). "
                "Set OPENROUTER_API_KEY or OLLAMA_URL and retry.",
                "danger",
            )
            return redirect(url_for("admin_marketplace_recheck"))
        proposed = _recheck_parse(raw)
        if not proposed:
            flash(
                f"LLM ({src}) returned no usable prices. Try again later.",
                "warning",
            )
            return redirect(url_for("admin_marketplace_recheck"))

        def _anomaly(current, prop):
            if not current or current <= 0 or not prop or prop <= 0:
                return False
            return abs(prop - current) / current > 0.25

        # Stash in session keyed by category id.
        skey = f"cat_recheck_{cat_id}"
        session[skey] = {
            "currency": currency,
            "country":  country,
            "cat_id":   cat_id,
            "cat_name": cat_name,
            "source":   src,
            "items": {
                str(it["id"]): {
                    "current":   it["current_price"],
                    "current_usd": float(items[idx]["price_usd"] or 0),
                    "name":      it["name"],
                    "unit":      it["unit"],
                    "proposed":  proposed.get(it["id"], {}).get("price", 0),
                    "src_note":  proposed.get(it["id"], {}).get("source", ""),
                    "confidence":proposed.get(it["id"], {}).get("confidence", "low"),
                    "quotes":    proposed.get(it["id"], {}).get("quotes", []),
                    "anomaly":   _anomaly(it["current_price"],
                                          proposed.get(it["id"], {}).get("price", 0)),
                }
                for idx, it in enumerate(prompt_items)
            },
        }
        flash(
            f"Bulk recheck via {src}: {len(prompt_items)} items in "
            f"'{cat_name}' ({country}/{currency}). Review and tick "
            "rows to apply.",
            "info",
        )
        return redirect(url_for("admin_marketplace_recheck_review",
                                cat_id=cat_id))

    @app.route("/admin/marketplace/recheck/<int:cat_id>/review",
               methods=["GET"])
    @admin_required
    def admin_marketplace_recheck_review(cat_id):
        skey = f"cat_recheck_{cat_id}"
        proposals = session.get(skey) or {}
        if not proposals.get("items"):
            flash("No proposals in session. Run the bulk recheck first.",
                  "warning")
            return redirect(url_for("admin_marketplace_recheck"))
        rows = []
        for sid, info in proposals["items"].items():
            try:
                rows.append((int(sid), info))
            except ValueError:
                continue
        rows.sort(key=lambda r: r[0])
        return render_template(
            "admin_marketplace_recheck_review.html",
            user=current_user(), rows=rows, meta=proposals,
        )

    @app.route("/admin/marketplace/recheck/<int:cat_id>/apply",
               methods=["POST"])
    @admin_required
    def admin_marketplace_recheck_apply(cat_id):
        csrf_protect()
        skey = f"cat_recheck_{cat_id}"
        proposals = session.get(skey) or {}
        if not proposals.get("items"):
            flash("Proposals expired -- run the recheck again.", "warning")
            return redirect(url_for("admin_marketplace_recheck"))
        currency = proposals.get("currency", "GHS")
        fx_rate = float(_CURRENCY_RATES_FROM_USD.get(currency, 1.0) or 1.0)
        if fx_rate <= 0:
            fx_rate = 1.0

        ticked = set()
        for k in request.form.getlist("apply"):
            try:
                ticked.add(int(k))
            except (TypeError, ValueError):
                pass

        uid = session.get("user_id") or 0
        submitter_email = _resolve_user_email(get_db, uid)
        applied = 0
        queued = 0
        skipped = 0
        with get_db() as c:
            for sid, info in proposals["items"].items():
                try:
                    iid = int(sid)
                except ValueError:
                    continue
                if iid not in ticked:
                    skipped += 1
                    continue
                proposed_local = float(info.get("proposed") or 0)
                if proposed_local <= 0:
                    skipped += 1
                    continue
                proposed_usd = proposed_local / fx_rate
                old_usd = float(info.get("current_usd") or 0)
                is_anomaly = bool(info.get("anomaly"))

                if is_anomaly:
                    # Queue for manager review -- do NOT touch equipment_catalog.
                    _record_price_history(
                        get_db, iid, old_usd, proposed_usd, currency,
                        proposed_local,
                        f"bulk-recheck cat={cat_id} (ANOMALY)",
                        f"AI source: {proposals.get('source','?')} "
                        f"-- queued for manager approval (>+/-25% from current).",
                        uid, status="pending",
                        submitted_by_email=submitter_email,
                    )
                    queued += 1
                else:
                    try:
                        c.execute(
                            "UPDATE equipment_catalog SET price_usd=? WHERE id=?",
                            (proposed_usd, iid),
                        )
                    except Exception:
                        skipped += 1
                        continue
                    _record_price_history(
                        get_db, iid, old_usd, proposed_usd, currency,
                        proposed_local,
                        f"bulk-recheck cat={cat_id}",
                        f"AI source: {proposals.get('source','?')}",
                        uid, status="approved",
                        submitted_by_email=submitter_email,
                    )
                    applied += 1

                # Quotes are always recorded (regardless of approval state).
                for q in (info.get("quotes") or []):
                    _record_catalog_quote(
                        get_db, iid,
                        (q.get("supplier") or "")[:200], 0,
                        float(q.get("price") or 0), currency,
                        (q.get("note") or "")[:300],
                        is_anomaly, uid, status="proposed",
                    )
        # audit
        try:
            from new_boq_hierarchy_schema import boq_audit
            boq_audit(
                get_db, uid, "catalogue_bulk_recheck_applied",
                "product_category", cat_id,
                f"applied={applied} queued={queued} skipped={skipped} "
                f"cat='{proposals.get('cat_name','')}' "
                f"src={proposals.get('source','?')}",
            )
        except Exception:
            pass
        session.pop(skey, None)
        bits = [f"{applied} applied"]
        if queued:
            bits.append(f"{queued} queued for manager approval (anomalies)")
        bits.append(f"{skipped} skipped")
        flash(
            "Bulk recheck: " + ", ".join(bits) + ". "
            + ("Review the anomaly queue at the link above." if queued else
               "History + supplier quotes logged."),
            "success" if applied or queued else "info",
        )
        return redirect(url_for("admin_marketplace_recheck"))

    # ─────────── Anomaly review queue (admin-only) ───────────

    @app.route("/admin/marketplace/anomalies", methods=["GET"])
    @admin_required
    def admin_marketplace_anomalies():
        """List all pending catalogue price-change proposals (anomalies)."""
        with get_db() as c:
            rows = c.execute(
                "SELECT h.id AS history_id, h.catalog_item_id, h.old_price_usd, "
                "       h.new_price_usd, h.currency_local, h.new_price_local, "
                "       h.source, h.reason, h.set_by_user_id, "
                "       h.submitted_by_email, h.set_at, "
                "       e.name AS item_name, e.brand, e.unit, "
                "       e.price_usd AS current_price_usd "
                "FROM equipment_catalog_price_history h "
                "LEFT JOIN equipment_catalog e ON e.id=h.catalog_item_id "
                "WHERE h.approval_status='pending' "
                "ORDER BY h.set_at DESC LIMIT 500"
            ).fetchall()
        # Pre-compute delta + per-item supplier quotes around the same time.
        pending = []
        for r in rows:
            try:
                old = float(r["old_price_usd"] or 0)
                new = float(r["new_price_usd"] or 0)
                delta_pct = ((new - old) / old * 100.0) if old else 0.0
            except Exception:
                delta_pct = 0.0
            try:
                with get_db() as c:
                    quotes = c.execute(
                        "SELECT supplier_name, price_local, currency, source_note "
                        "FROM equipment_catalog_quotes "
                        "WHERE catalog_item_id=? "
                        "ORDER BY quoted_at DESC LIMIT 6",
                        (r["catalog_item_id"],),
                    ).fetchall()
            except Exception:
                quotes = []
            pending.append({"row": r, "delta_pct": delta_pct, "quotes": quotes})
        return render_template(
            "admin_anomaly_queue.html",
            user=current_user(), pending=pending,
        )

    @app.route("/admin/marketplace/anomalies/<int:history_id>/decide",
               methods=["POST"])
    @admin_required
    def admin_marketplace_anomaly_decide(history_id):
        """Approve or reject a queued anomaly. Approve writes the price to
        equipment_catalog; reject just flips the status."""
        csrf_protect()
        decision = (request.form.get("decision") or "").strip().lower()
        if decision not in ("approve", "reject"):
            flash("Invalid decision.", "warning")
            return redirect(url_for("admin_marketplace_anomalies"))
        uid = session.get("user_id") or 0
        with get_db() as c:
            row = c.execute(
                "SELECT catalog_item_id, new_price_usd, old_price_usd, "
                "       approval_status, submitted_by_email "
                "FROM equipment_catalog_price_history WHERE id=?",
                (history_id,),
            ).fetchone()
            if not row:
                flash("Queue entry not found.", "warning")
                return redirect(url_for("admin_marketplace_anomalies"))
            if row["approval_status"] != "pending":
                flash(
                    f"Already decided ({row['approval_status']}).", "info"
                )
                return redirect(url_for("admin_marketplace_anomalies"))

            if decision == "approve":
                # Apply the proposed price to the catalogue, then flip status.
                try:
                    c.execute(
                        "UPDATE equipment_catalog SET price_usd=? WHERE id=?",
                        (float(row["new_price_usd"] or 0),
                         int(row["catalog_item_id"] or 0)),
                    )
                except Exception:
                    flash("Could not update catalogue. Reverted.", "danger")
                    return redirect(url_for("admin_marketplace_anomalies"))
                try:
                    c.execute(
                        "UPDATE equipment_catalog_price_history "
                        "SET approval_status='approved', "
                        "    decided_at=CURRENT_TIMESTAMP, "
                        "    decided_by_user_id=? WHERE id=?",
                        (uid, history_id),
                    )
                except Exception:
                    # decided_at/decided_by columns may not exist on older schemas.
                    c.execute(
                        "UPDATE equipment_catalog_price_history "
                        "SET approval_status='approved' WHERE id=?",
                        (history_id,),
                    )
                flash(
                    f"Approved: USD {row['old_price_usd']:.2f} -> "
                    f"{row['new_price_usd']:.2f} applied to catalogue.",
                    "success",
                )
            else:
                try:
                    c.execute(
                        "UPDATE equipment_catalog_price_history "
                        "SET approval_status='rejected', "
                        "    decided_at=CURRENT_TIMESTAMP, "
                        "    decided_by_user_id=? WHERE id=?",
                        (uid, history_id),
                    )
                except Exception:
                    c.execute(
                        "UPDATE equipment_catalog_price_history "
                        "SET approval_status='rejected' WHERE id=?",
                        (history_id,),
                    )
                flash("Rejected. Catalogue price unchanged.", "info")
        try:
            from new_boq_hierarchy_schema import boq_audit
            boq_audit(
                get_db, uid, f"anomaly_{decision}d",
                "price_history", history_id,
                f"item={row['catalog_item_id']} new_usd={row['new_price_usd']:.2f} "
                f"submitter={row['submitted_by_email'] or 'n/a'}",
            )
        except Exception:
            pass
        return redirect(url_for("admin_marketplace_anomalies"))

    @app.route("/admin/catalogue/<int:item_id>/price-history",
               methods=["GET"])
    @admin_required
    def admin_catalogue_price_history(item_id):
        """View the full price-history trail for one catalogue item."""
        with get_db() as c:
            item = c.execute(
                "SELECT id, name, brand, unit, price_usd "
                "FROM equipment_catalog WHERE id=?", (item_id,),
            ).fetchone()
            if not item:
                flash("Catalogue item not found.", "warning")
                return redirect(url_for("procurement_catalog"))
            history = c.execute(
                "SELECT old_price_usd, new_price_usd, currency_local, "
                " new_price_local, source, reason, set_by_user_id, "
                " approval_status, set_at "
                "FROM equipment_catalog_price_history "
                "WHERE catalog_item_id=? ORDER BY set_at DESC LIMIT 200",
                (item_id,),
            ).fetchall()
            quotes = c.execute(
                "SELECT supplier_name, price_local, currency, source_note, "
                " anomaly_flag, status, quoted_at "
                "FROM equipment_catalog_quotes "
                "WHERE catalog_item_id=? ORDER BY quoted_at DESC LIMIT 200",
                (item_id,),
            ).fetchall()
        return render_template(
            "admin_catalogue_history.html",
            user=current_user(), item=item, history=history, quotes=quotes,
        )
