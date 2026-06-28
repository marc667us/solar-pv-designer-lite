# new_boq_section_meta_route.py
# 2026-06-28 owner directive: each BOQ section (Bill / Section letter) gets an
# editable heading + a free-text instructions cell that render above the
# section's rows in the floor view and on the Excel + PDF exports.


def _boq_section_meta_get(fid, bill_no, letter):
    """Return (custom_title, instructions) for a section, or ('', '')."""
    try:
        with get_db() as c:
            row = c.execute(
                "SELECT custom_title, instructions FROM boq_section_meta "
                "WHERE floor_id=? AND bill_no=? AND section_letter=?",
                (int(fid), int(bill_no), (letter or "").upper()[:8]),
            ).fetchone()
        if row:
            return (row["custom_title"] or "", row["instructions"] or "")
    except Exception:
        pass
    return ("", "")


def _boq_section_meta_map(fid):
    """Return {(bill_no, section_letter): (custom_title, instructions)} for
    every section meta on the floor. Used by the floor view + exports to
    overlay custom titles + render instructions inline."""
    out = {}
    try:
        with get_db() as c:
            rows = c.execute(
                "SELECT bill_no, section_letter, custom_title, instructions "
                "FROM boq_section_meta WHERE floor_id=?",
                (int(fid),),
            ).fetchall()
        for r in rows:
            out[(int(r["bill_no"] or 0), (r["section_letter"] or "").upper())] = (
                r["custom_title"] or "", r["instructions"] or ""
            )
    except Exception:
        pass
    return out


@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>/bill/<int:bill_no>/section/<letter>/meta",
           methods=["POST"])
@login_required
def boq_section_meta_save(pid, bid, fid, bill_no, letter):
    uid = session["user_id"]
    _boq_project_owned_or_404(pid, uid)
    _boq_building_owned_or_404(bid, pid)
    _boq_floor_owned_or_404(fid, bid)
    csrf_protect()
    letter = (letter or "").upper()[:8]
    f = request.form
    custom_title = (f.get("custom_title") or "").strip()[:300]
    instructions = (f.get("instructions") or "").strip()[:4000]

    # UPSERT (INSERT OR REPLACE for SQLite; manual upsert for PG).
    with get_db() as c:
        existing = c.execute(
            "SELECT id FROM boq_section_meta "
            "WHERE floor_id=? AND bill_no=? AND section_letter=?",
            (fid, bill_no, letter),
        ).fetchone()
        if existing:
            c.execute(
                "UPDATE boq_section_meta SET custom_title=?, instructions=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (custom_title, instructions, existing["id"]),
            )
        else:
            c.execute(
                "INSERT INTO boq_section_meta "
                "(floor_id, bill_no, section_letter, custom_title, instructions) "
                "VALUES (?, ?, ?, ?, ?)",
                (fid, bill_no, letter, custom_title, instructions),
            )

    try:
        from new_boq_hierarchy_schema import boq_audit
        boq_audit(get_db, uid, "boq_section_meta_saved", "boq_floor", fid,
                  f"bill={bill_no} letter={letter} title_len={len(custom_title)} instr_len={len(instructions)}")
    except Exception:
        pass

    flash(f"Section {letter} heading and instructions saved.", "success")
    # Redirect back to the section grid where the form was submitted from.
    title    = (f.get("section_title")    or "").strip()[:160]
    bill_nm  = (f.get("bill_name")        or "").strip()[:120]
    subsec   = (f.get("subsection_label") or "").strip()[:20]
    return redirect(url_for(
        "boq_section_grid",
        pid=pid, bid=bid, fid=fid, bill_no=bill_no, letter=letter,
        title=title, bill_name=bill_nm, sub=subsec,
    ))
