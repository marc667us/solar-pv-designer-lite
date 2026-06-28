# new_boq_edit_and_learn_routes.py
# Two owner-driven additions:
#
#   A. Edit existing BOQ floor item -- per-row Edit button on floor view
#      opens an in-place form that updates description / unit / qty /
#      basic_price + remarks, recomputes final_built_up_rate + total_amount,
#      and updates the linked boq_floor_rate_buildup row.
#
#   B. Learn from owner edits -- every time the owner saves an edit we
#      store a (user_id, description_signature, unit, basic_price)
#      override. The next time the same description appears in the
#      section grid catalogue or a template, we use the owner's basic
#      price + unit as the default (a 1-call personalisation layer
#      around the static catalogues).


_BOQ_USER_OVERRIDES_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS boq_user_item_overrides (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            INTEGER NOT NULL,
    description_key    TEXT NOT NULL,
    unit               TEXT DEFAULT '',
    basic_price        REAL DEFAULT 0,
    last_description   TEXT DEFAULT '',
    updated_at         TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, description_key)
);
CREATE INDEX IF NOT EXISTS idx_boq_user_overrides_user
    ON boq_user_item_overrides(user_id);
"""

_BOQ_USER_OVERRIDES_DDL_PG = """
CREATE TABLE IF NOT EXISTS boq_user_item_overrides (
    id                 SERIAL PRIMARY KEY,
    user_id            INTEGER NOT NULL,
    description_key    VARCHAR(500) NOT NULL,
    unit               VARCHAR(20) DEFAULT '',
    basic_price        REAL DEFAULT 0,
    last_description   VARCHAR(500) DEFAULT '',
    updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, description_key)
);
CREATE INDEX IF NOT EXISTS idx_boq_user_overrides_user
    ON boq_user_item_overrides(user_id);
"""


_BOQ_USER_OVERRIDES_ALTERS = [
    # 2026-06-28: extend overrides to carry the full rate-builder + qty so
    # the next project derived from the same template starts with what the
    # owner LAST set (not the static template defaults).
    "ALTER TABLE boq_user_item_overrides ADD COLUMN supply_pct REAL DEFAULT 0",
    "ALTER TABLE boq_user_item_overrides ADD COLUMN install_pct REAL DEFAULT 0",
    "ALTER TABLE boq_user_item_overrides ADD COLUMN last_qty REAL DEFAULT 0",
]

_BOQ_USER_OVERRIDES_ALTERS_PG = [
    "ALTER TABLE boq_user_item_overrides ADD COLUMN IF NOT EXISTS supply_pct REAL DEFAULT 0",
    "ALTER TABLE boq_user_item_overrides ADD COLUMN IF NOT EXISTS install_pct REAL DEFAULT 0",
    "ALTER TABLE boq_user_item_overrides ADD COLUMN IF NOT EXISTS last_qty REAL DEFAULT 0",
]


def _boq_ensure_overrides_table():
    """Idempotent bootstrap. Same pattern as ensure_boq_hierarchy_schema."""
    try:
        is_pg = bool(os.environ.get("DATABASE_URL"))
        with get_db() as c:
            if is_pg:
                for stmt in _BOQ_USER_OVERRIDES_DDL_PG.strip().split(";"):
                    s = stmt.strip()
                    if s:
                        try: c.execute(s)
                        except Exception: pass
                for stmt in _BOQ_USER_OVERRIDES_ALTERS_PG:
                    try: c.execute(stmt)
                    except Exception: pass
            else:
                c.executescript(_BOQ_USER_OVERRIDES_DDL_SQLITE)
                for stmt in _BOQ_USER_OVERRIDES_ALTERS:
                    try: c.execute(stmt)
                    except Exception: pass
    except Exception:
        pass


def _boq_desc_key(desc: str) -> str:
    """Description -> stable key. Lowercase, collapse whitespace, take
    first 240 chars so 'Supply and install 6-way TPN MCB DB' matches the
    same item across catalogue + template + edit variants."""
    s = (desc or "").lower()
    s = " ".join(s.split())
    return s[:240]


def _boq_record_override(uid: int, desc: str, unit: str, basic: float,
                         supply_pct: float = 0.0, install_pct: float = 0.0,
                         qty: float = 0.0) -> None:
    """Save / update the user's preferred values for this description.
    2026-06-28: extended to carry supply_pct + install_pct + last_qty so the
    library `learns` the full rate-builder context. Non-raising."""
    try:
        _boq_ensure_overrides_table()
        key = _boq_desc_key(desc)
        if not key:
            return
        with get_db() as c:
            c.execute(
                "INSERT OR REPLACE INTO boq_user_item_overrides "
                "(user_id, description_key, unit, basic_price, last_description, "
                " supply_pct, install_pct, last_qty) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (int(uid), key, (unit or "").strip()[:20],
                 float(basic or 0), (desc or "").strip()[:500],
                 float(supply_pct or 0), float(install_pct or 0),
                 float(qty or 0)),
            )
    except Exception:
        pass


def _boq_lookup_overrides_for_user(uid: int) -> dict:
    """Return {description_key: (unit, basic_price, supply_pct, install_pct, last_qty)}."""
    try:
        _boq_ensure_overrides_table()
        with get_db() as c:
            rows = c.execute(
                "SELECT description_key, unit, basic_price, "
                "       supply_pct, install_pct, last_qty "
                "FROM boq_user_item_overrides WHERE user_id=?",
                (int(uid),),
            ).fetchall()
        return {
            r["description_key"]: (
                r["unit"] or "",
                float(r["basic_price"] or 0),
                float(r["supply_pct"] or 0),
                float(r["install_pct"] or 0),
                float(r["last_qty"] or 0),
            )
            for r in rows
        }
    except Exception:
        return {}


def _boq_template_lines_with_overrides(uid: int, template: dict):
    """Yield template lines overlaid with the user's recorded overrides.
    Wraps _boq_template_iter_lines from new_boq_project_templates so the
    static templates `learn` from prior projects.

    Yields the same 11-tuple shape:
      (bill_no, bill_name, sect_letter, sect_title, subsec, idx,
       desc, unit, qty, basic, spec)
    where unit / qty / basic come from the override when present.
    """
    from new_boq_project_templates import _boq_template_iter_lines
    ov = _boq_lookup_overrides_for_user(uid)
    for (bill_no, bill_name, sect_letter, sect_title, subsec, idx,
         desc, unit, qty, basic, spec) in _boq_template_iter_lines(template):
        key = _boq_desc_key(desc)
        if key in ov:
            ov_unit, ov_basic, _ov_sp, _ov_ip, ov_qty = ov[key]
            unit = ov_unit or unit
            if ov_basic > 0:
                basic = ov_basic
            if ov_qty > 0:
                qty = ov_qty
        yield (bill_no, bill_name, sect_letter, sect_title, subsec, idx,
               desc, unit, qty, basic, spec)


def _boq_apply_overrides(uid: int, catalog_rows: list) -> list:
    """Given a list of (desc, unit, basic) tuples (the section grid
    catalogue), overlay the user's recorded overrides so the dropdown
    defaults to the owner's last-used values."""
    try:
        _boq_ensure_overrides_table()
        with get_db() as c:
            rows = c.execute(
                "SELECT description_key, unit, basic_price FROM boq_user_item_overrides "
                "WHERE user_id=?",
                (int(uid),),
            ).fetchall()
        by_key = {r["description_key"]: (r["unit"], r["basic_price"]) for r in rows}
    except Exception:
        return catalog_rows
    out = []
    for (desc, unit, basic) in catalog_rows:
        key = _boq_desc_key(desc)
        if key in by_key:
            u, b = by_key[key]
            out.append((desc, (u or unit), (float(b) if b else basic)))
        else:
            out.append((desc, unit, basic))
    return out


# ---- Edit existing item ---------------------------------------------------

@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/items/<int:iid>/edit", methods=["GET", "POST"])
@login_required
def boq_floor_item_edit(pid, bid, fid, iid):
    uid = session["user_id"]
    project = _boq_project_owned_or_404(pid, uid)
    building = _boq_building_owned_or_404(bid, pid)
    floor = _boq_floor_owned_or_404(fid, bid)
    with get_db() as c:
        item = c.execute(
            "SELECT i.*, rb.basic_price AS bu_basic, rb.supply_rate AS bu_supply, "
            "       rb.install_rate AS bu_install, rb.overhead_pct AS bu_oh, "
            "       rb.profit_pct AS bu_profit, rb.contingency_pct AS bu_cont, "
            "       rb.vat_pct AS bu_vat, rb.supply_pct AS bu_supply_pct, "
            "       rb.install_pct AS bu_install_pct, rb.vat_in_basic AS bu_vat_in_basic "
            "FROM boq_floor_items i "
            "LEFT JOIN boq_floor_rate_buildup rb ON rb.floor_item_id=i.id "
            "WHERE i.id=? AND i.floor_id=?",
            (iid, fid),
        ).fetchone()
    if not item:
        abort(404)

    if request.method == "POST":
        csrf_protect()
        f = request.form
        desc = (f.get("description") or "").strip()[:500]
        unit = (f.get("unit") or "No.").strip()[:20]
        spec = (f.get("specification") or "").strip()
        remarks = (f.get("remarks") or "").strip()[:500]
        try:
            qty = max(0.0, float(f.get("qty") or 0))
        except ValueError:
            qty = 0.0
        try:
            basic = max(0.0, float(f.get("basic_price") or 0))
        except ValueError:
            basic = 0.0
        def _pct(name):
            try:
                v = f.get(name, "")
                return max(0.0, min(100.0, float(v))) if v not in (None, "",) else 0.0
            except (TypeError, ValueError):
                return 0.0
        # Rate engine v3 (2026-06-28): supply_pct + install_pct are PERCENTAGES.
        oh, prf, vat = _pct("overhead_pct"), _pct("profit_pct"), _pct("vat_pct")
        supply_pct  = _pct("supply_pct")
        install_pct = _pct("install_pct")
        vat_in_basic = 1 if f.get("vat_in_basic") else 0
        if not desc or qty <= 0 or basic <= 0:
            flash("Description, qty and basic price are all required.", "warning")
            return redirect(url_for("boq_floor_item_edit", pid=pid, bid=bid, fid=fid, iid=iid))
        from boq_rate_v3 import boq_rate_v3
        supply, install, final_rate = boq_rate_v3(
            basic, supply_pct, install_pct, oh, prf, vat,
            vat_in_basic=bool(vat_in_basic))
        total = qty * final_rate
        with get_db() as c:
            c.execute(
                "UPDATE boq_floor_items SET description=?, specification=?, "
                "unit=?, qty=?, remarks=?, final_built_up_rate=?, total_amount=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=? AND floor_id=?",
                (desc, spec, unit, qty, remarks, final_rate, total, iid, fid),
            )
            c.execute(
                "UPDATE boq_floor_rate_buildup SET basic_price=?, "
                "supply_pct=?, install_pct=?, supply_rate=?, install_rate=?, "
                "overhead_pct=?, profit_pct=?, contingency_pct=?, "
                "vat_pct=?, vat_in_basic=?, final_built_up_rate=?, total_amount=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE floor_item_id=?",
                (basic, supply_pct, install_pct, supply, install,
                 oh, prf, 0, vat, vat_in_basic, final_rate, total, iid),
            )
            c.execute("UPDATE boq_floors SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (fid,))
        # LEARN: record the user's preferred values for this description
        # so the library applies them to future projects derived from
        # any template that contains this line.
        _boq_record_override(uid, desc, unit, basic,
                             supply_pct=supply_pct, install_pct=install_pct,
                             qty=qty)
        try:
            from new_boq_hierarchy_schema import boq_audit
            boq_audit(get_db, uid, "boq_floor_item_edited", "boq_floor_item", iid,
                      f"rate={final_rate:.2f} total={total:.2f}")
        except Exception:
            pass
        flash(f"Item updated. Future BOQs will default to {basic:.2f}/{unit} for this item.", "success")
        return redirect(url_for("boq_floor_view", pid=pid, bid=bid, fid=fid))

    # GET -- render the edit form.
    return render_template(
        "boq_floor_item_edit.html",
        user=current_user(),
        project=project, building=building, floor=floor, item=item,
    )
