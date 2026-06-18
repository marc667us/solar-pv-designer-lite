# ─── Routes — Marketplace Price-List Upload ───────────────────────────────────
# Slice 2B: suppliers bulk-add products via CSV or XLSX upload.
#
# Phase 1 design — single-step upload with canonical column names. A 3-step
# wizard (Upload → Map → Review) lands when real suppliers show up with
# non-standard column headers. For now: download the template, fill in,
# upload — done.
#
# Required columns: name, category, brand, model, spec, unit, price_usd,
# lead_time_days, subcategory (subcategory optional, others required).
# `category` is matched case-insensitively against product_categories.name
# or product_categories.code.

_UPLOAD_REQUIRED_COLS = ["name", "category", "price_usd"]
_UPLOAD_OPTIONAL_COLS = ["brand", "model", "spec", "unit", "lead_time_days", "subcategory"]
_UPLOAD_MAX_BYTES = 2 * 1024 * 1024   # 2 MB cap — Phase 1 keeps free-tier disk safe
_UPLOAD_MAX_ROWS = 1000


def _normalise_header(h: str) -> str:
    return (h or "").strip().lower().replace(" ", "_").replace("-", "_")


def _row_to_dict(headers: list, row: list) -> dict:
    out = {}
    for i, h in enumerate(headers):
        out[h] = row[i] if i < len(row) else ""
    return out


def _parse_csv(stream) -> tuple[list, list]:
    import csv as _csv
    text = stream.read().decode("utf-8-sig", errors="replace")
    reader = _csv.reader(text.splitlines())
    rows = list(reader)
    if not rows:
        return [], []
    headers = [_normalise_header(h) for h in rows[0]]
    data_rows = [r for r in rows[1:] if any((cell or "").strip() for cell in r)]
    return headers, data_rows


def _parse_xlsx(stream) -> tuple[list, list]:
    import openpyxl as _ox
    wb = _ox.load_workbook(stream, data_only=True, read_only=True)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(values_only=True):
        rows.append(["" if v is None else str(v) for v in row])
    if not rows:
        return [], []
    headers = [_normalise_header(h) for h in rows[0]]
    data_rows = [r for r in rows[1:] if any((cell or "").strip() for cell in r)]
    return headers, data_rows


@app.route("/supplier/upload/template")
@supplier_required
def supplier_upload_template():
    """Download a starter CSV template with the canonical columns + one example row."""
    import io as _io
    buf = _io.StringIO()
    buf.write(",".join(_UPLOAD_REQUIRED_COLS + _UPLOAD_OPTIONAL_COLS) + "\n")
    buf.write(
        '"ABB 500 kVA Distribution Transformer","Transformers",9800,'
        '"ABB","TRF-500-DT","500 kVA, 11/0.433 kV, Dyn11","No.",60,"Distribution"\n'
    )
    return (
        buf.getvalue(),
        200,
        {
            "Content-Type": "text/csv",
            "Content-Disposition": "attachment; filename=marketplace_template.csv",
        },
    )


@app.route("/supplier/upload", methods=["GET", "POST"])
@supplier_required
def supplier_upload():
    s = _current_supplier()
    if not s:
        return redirect(url_for("supplier_dashboard"))
    if request.method == "GET":
        return render_template(
            "supplier_upload.html", user=current_user(), supplier=s
        )
    csrf_protect()

    f = request.files.get("file")
    if not f or not f.filename:
        flash("Please select a CSV or XLSX file to upload.", "danger")
        return redirect(url_for("supplier_upload"))

    # Size check before parsing (defence against oversize uploads on free tier).
    f.stream.seek(0, 2)
    size = f.stream.tell()
    f.stream.seek(0)
    if size > _UPLOAD_MAX_BYTES:
        flash(f"File too large ({size//1024} KB). Limit is {_UPLOAD_MAX_BYTES//1024} KB.", "danger")
        return redirect(url_for("supplier_upload"))

    name_lower = (f.filename or "").lower()
    try:
        if name_lower.endswith(".csv"):
            headers, data_rows = _parse_csv(f.stream)
        elif name_lower.endswith(".xlsx"):
            headers, data_rows = _parse_xlsx(f.stream)
        else:
            flash("Unsupported file type. Use .csv or .xlsx.", "danger")
            return redirect(url_for("supplier_upload"))
    except Exception as e:
        app.logger.warning("supplier_upload parse failed: %s", e)
        flash("The file could not be parsed. Check the format against the template.", "danger")
        return redirect(url_for("supplier_upload"))

    if not headers:
        flash("The file appears empty.", "danger")
        return redirect(url_for("supplier_upload"))

    missing_required = [c for c in _UPLOAD_REQUIRED_COLS if c not in headers]
    if missing_required:
        flash(
            f"Missing required columns: {', '.join(missing_required)}. "
            "Download the template to see the expected layout.",
            "danger",
        )
        return redirect(url_for("supplier_upload"))

    if len(data_rows) > _UPLOAD_MAX_ROWS:
        flash(
            f"File has {len(data_rows)} rows — limit is {_UPLOAD_MAX_ROWS}. "
            "Split into smaller batches.",
            "danger",
        )
        return redirect(url_for("supplier_upload"))

    # Build category lookup (case-insensitive on name OR code).
    with get_db() as c:
        cat_rows = c.execute(
            "SELECT id, code, name FROM product_categories WHERE is_active=1"
        ).fetchall()
    cat_by_key = {}
    for cr in cat_rows:
        cat_by_key[(cr["name"] or "").lower()] = (cr["id"], cr["name"])
        cat_by_key[(cr["code"] or "").lower()] = (cr["id"], cr["name"])

    accepted = 0
    rejected: list[dict] = []
    with get_db() as c:
        for idx, raw in enumerate(data_rows, start=2):  # row 1 was headers
            d = _row_to_dict(headers, raw)
            name = (d.get("name") or "").strip()
            cat_text = (d.get("category") or "").strip().lower()
            price_raw = (d.get("price_usd") or "").strip()
            try:
                price = float(price_raw) if price_raw else 0.0
            except ValueError:
                price = -1
            if not name:
                rejected.append({"row": idx, "reason": "name is blank"})
                continue
            if not cat_text or cat_text not in cat_by_key:
                rejected.append({"row": idx, "reason": f"unknown category '{d.get('category', '')}'"})
                continue
            if price < 0:
                rejected.append({"row": idx, "reason": f"invalid price '{price_raw}'"})
                continue
            cat_id, cat_label = cat_by_key[cat_text]
            c.execute(
                "INSERT INTO equipment_catalog (category, name, brand, model, spec, unit, "
                "price_usd, supplier_id, lead_time_days, category_id, subcategory, "
                "is_public_visible, is_verified) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    cat_label, name,
                    (d.get("brand") or "").strip(),
                    (d.get("model") or "").strip(),
                    (d.get("spec") or "").strip(),
                    (d.get("unit") or "No.").strip(),
                    price,
                    s["id"],
                    _safe_int(d.get("lead_time_days"), 30),
                    cat_id,
                    (d.get("subcategory") or "").strip(),
                    1 if s["is_verified"] else 0,
                    0,  # uploaded items start pending verification
                ),
            )
            accepted += 1

    msg_parts = [f"Imported {accepted} product{'s' if accepted != 1 else ''}."]
    if rejected:
        first_few = "; ".join(f"row {r['row']}: {r['reason']}" for r in rejected[:5])
        more = f" ... and {len(rejected) - 5} more" if len(rejected) > 5 else ""
        msg_parts.append(f"Skipped {len(rejected)}: {first_few}{more}.")
    flash(" ".join(msg_parts), "success" if accepted else "warning")
    return redirect(url_for("supplier_products"))
