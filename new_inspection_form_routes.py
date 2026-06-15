# Site Inspection Form routes — added 2026-06-15. Replaces the manual
# fill-in flow on the /shading page by letting the operator capture
# shading observations + site photos + roof drawings during inspection.
# Submitted data is mirrored into project.data["shading"] so the
# /shading page picks the inputs up automatically.
#
# Four routes:
#   GET  /project/<pid>/inspection                          → render form
#   POST /project/<pid>/inspection                          → save form + uploads
#   GET  /project/<pid>/inspection/upload/<filename>        → serve uploaded file
#   POST /project/<pid>/inspection/upload/<filename>/delete → remove an upload


_INSP_ALLOWED_PHOTO_EXT = {"jpg", "jpeg", "png", "webp", "gif"}
_INSP_ALLOWED_DRAWING_EXT = {"jpg", "jpeg", "png", "webp", "pdf"}
_INSP_MAX_FILE_MB = 8
_INSP_MAX_FILES   = 12


def _insp_upload_dir(pid):
    """Per-project upload directory. Uses /app/data when present (Render
    persistent disk), else falls back to the app dir. Created on first
    write."""
    import os
    db_path = os.environ.get("DB_PATH", "solar.db")
    base = os.path.dirname(os.path.abspath(db_path)) or "."
    d = os.path.join(base, "inspection_uploads", str(pid))
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        # Render-free disk write may fail; caller surfaces a flash.
        pass
    return d


def _insp_safe_filename(orig):
    """Generate a safe randomised filename keeping the original extension.
    Never trust the client-supplied filename for the on-disk name."""
    import os, secrets
    ext = ""
    if "." in orig:
        ext = orig.rsplit(".", 1)[-1].lower()
        ext = "".join(c for c in ext if c.isalnum())[:6]
    return secrets.token_hex(10) + (("." + ext) if ext else "")


def _parse_insp_obstructions(form):
    """Parse the cloneable obstruction cards on the inspection form into
    a list of dicts with the SAME shape the /shading engine consumes.
    Empty trailing rows are dropped."""
    out = []
    n = len(form.getlist("obs_type"))
    types     = form.getlist("obs_type")
    heights   = form.getlist("obs_height")
    widths    = form.getlist("obs_width")
    distances = form.getlist("obs_distance")
    directions = form.getlist("obs_direction")
    mitigations = form.getlist("obs_mitigation")
    notes     = form.getlist("obs_notes")
    for i in range(n):
        t = (types[i] if i < len(types) else "").strip()
        h_raw = heights[i] if i < len(heights) else ""
        d_raw = distances[i] if i < len(distances) else ""
        if not t and not h_raw and not d_raw:
            continue  # skip blank rows
        try:    h = float(h_raw or 0)
        except Exception: h = 0.0
        try:    w = float((widths[i] if i < len(widths) else "") or 0)
        except Exception: w = 0.0
        try:    dist = float(d_raw or 0)
        except Exception: dist = 0.0
        out.append({
            "type":       (t or "obstruction")[:60],
            "height":     h,
            "width":      w,
            "distance":   dist,
            "direction":  (directions[i] if i < len(directions) else "South").strip()[:20],
            "mitigation": (mitigations[i] if i < len(mitigations) else "None").strip()[:40],
            "notes":      (notes[i] if i < len(notes) else "").strip()[:240],
        })
    return out


@app.route("/project/<int:pid>/inspection", methods=["GET", "POST"])
@login_required
@limiter.limit("30 per hour")
def inspection_form(pid):
    """Editable site-inspection form. On POST, persists to
    project.data["inspection"] AND mirrors shading-relevant fields into
    project.data["shading"] so the existing /shading page consumes the
    inspection inputs automatically (no double entry).
    """
    import os
    from datetime import datetime as _dt
    project = get_project(pid)
    if not project:
        flash("Project not found.", "warning")
        return redirect(url_for("dashboard"))

    data = project["data"]
    inspection = data.get("inspection", {}) or {}
    shading    = data.get("shading", {}) or {}

    if request.method == "POST":
        csrf_protect()

        # ── 1. Free-text + shading-presence flag ───────────────────────
        shading_present = (request.form.get("shading_present") or "no").strip().lower()
        if shading_present not in ("yes", "no", "partial"):
            shading_present = "no"
        site_notes  = (request.form.get("site_notes")  or "").strip()[:4000]
        roof_type   = (request.form.get("roof_type")   or "").strip()[:40]
        roof_height = (request.form.get("roof_height") or "").strip()[:20]
        tilt_deg    = (request.form.get("tilt_deg")    or "").strip()[:10]
        azimuth     = (request.form.get("azimuth")     or "").strip()[:30]
        units       = (request.form.get("units")       or "metric").strip()[:10]
        if units not in ("metric", "imperial"):
            units = "metric"

        # ── 2. Obstructions (shading source list) ──────────────────────
        obstructions = _parse_insp_obstructions(request.form)

        # ── 3. File uploads (site photos + roof drawings) ──────────────
        upload_dir = _insp_upload_dir(pid)
        existing_photos   = list(inspection.get("photos") or [])
        existing_drawings = list(inspection.get("roof_drawings") or [])

        def _accept(fileset, allowed_ext, kind):
            kept = []
            try:
                files = request.files.getlist(fileset)
            except Exception:
                files = []
            for f in files:
                if not f or not f.filename:
                    continue
                if len(existing_photos) + len(existing_drawings) + len(kept) >= _INSP_MAX_FILES:
                    flash(f"Upload cap reached ({_INSP_MAX_FILES} files max).", "warning")
                    break
                orig = f.filename
                ext  = (orig.rsplit(".", 1)[-1] or "").lower()
                if ext not in allowed_ext:
                    flash(f"Skipped {orig}: extension .{ext} not allowed for {kind}.",
                          "warning")
                    continue
                # Read into memory once so we can size-check then write.
                blob = f.read()
                size_mb = len(blob) / (1024 * 1024)
                if size_mb > _INSP_MAX_FILE_MB:
                    flash(f"Skipped {orig}: {size_mb:.1f} MB exceeds "
                          f"{_INSP_MAX_FILE_MB} MB cap.", "warning")
                    continue
                fname = _insp_safe_filename(orig)
                try:
                    with open(os.path.join(upload_dir, fname), "wb") as outp:
                        outp.write(blob)
                except Exception as _e:
                    flash(f"Could not save {orig}: {_e}", "warning")
                    continue
                kept.append({
                    "filename":      fname,
                    "original_name": orig[:120],
                    "kind":          kind,
                    "size_kb":       round(size_mb * 1024, 1),
                    "uploaded_at":   _dt.utcnow().isoformat() + "Z",
                    "uploaded_by":   session.get("username", ""),
                })
            return kept

        new_photos   = _accept("site_photos",   _INSP_ALLOWED_PHOTO_EXT,   "photo")
        new_drawings = _accept("roof_drawings", _INSP_ALLOWED_DRAWING_EXT, "drawing")

        # ── 4. Persist to data["inspection"] ───────────────────────────
        data["inspection"] = {
            "shading_present": shading_present,
            "site_notes":      site_notes,
            "roof_type":       roof_type,
            "roof_height_m":   roof_height,
            "tilt_deg":        tilt_deg,
            "azimuth":         azimuth,
            "units":           units,
            "obstructions":    obstructions,
            "photos":          existing_photos   + new_photos,
            "roof_drawings":   existing_drawings + new_drawings,
            "saved_at":        _dt.utcnow().isoformat() + "Z",
            "saved_by":        session.get("username", ""),
        }

        # ── 5. Mirror shading-relevant inputs into data["shading"] ─────
        # The /shading page reads from data["shading"]; by mirroring here
        # we make the inspection form the single source of truth for
        # shading inputs (per owner spec: "must pass shading input
        # information collected to the shading model to limit human
        # filling the shading form").
        mirrored = dict(shading)
        mirrored["obstructions"]        = obstructions
        mirrored["units"]               = units
        mirrored["roof_type"]           = roof_type
        mirrored["roof_height_m"]       = (float(roof_height) if roof_height.replace(".","",1).isdigit() else None)
        mirrored["tilt_deg"]            = (float(tilt_deg)    if tilt_deg.replace(".","",1).isdigit()    else None)
        mirrored["azimuth"]             = azimuth
        mirrored["inspection_confirmed"] = (shading_present in ("yes", "partial"))
        mirrored["source"]              = "inspection_form"
        # Clear stale engine output so /shading recomputes against new
        # obstructions on next GET.
        mirrored.pop("engine", None)
        data["shading"] = mirrored

        save_project_data(pid, data)

        # Audit log.
        try:
            with get_db() as c:
                c.execute(
                    "INSERT INTO audit_logs (user_id, username, action, ip_address, details) "
                    "VALUES (?,?,?,?,?)",
                    (session.get("user_id"), session.get("username", ""),
                     "inspection_form_save", _get_real_ip(),
                     f"pid={pid} shading={shading_present} "
                     f"obs={len(obstructions)} photos={len(new_photos)} "
                     f"drawings={len(new_drawings)}"))
        except Exception:
            pass

        flash(f"Site inspection saved. {len(obstructions)} obstruction(s), "
              f"{len(new_photos)} new photo(s), {len(new_drawings)} new drawing(s). "
              f"Shading inputs passed to the AI 3D Shading Simulation model.",
              "success")

        # Route the operator to the next logical step: if shading was
        # confirmed, send them straight to /shading so they can review
        # the agent pick + run the simulation; otherwise back to Loads.
        if shading_present in ("yes", "partial"):
            return redirect(url_for("project_shading", pid=pid))
        return redirect(url_for("project_loads", pid=pid))

    # GET — render the form pre-filled from current state.
    return render_template("inspection_form.html",
                           user=current_user(),
                           project=project,
                           inspection=inspection,
                           shading=shading,
                           max_file_mb=_INSP_MAX_FILE_MB,
                           max_files=_INSP_MAX_FILES)


@app.route("/project/<int:pid>/inspection/upload/<path:filename>")
@login_required
def inspection_upload_serve(pid, filename):
    """Serve a single uploaded site-photo / roof-drawing file."""
    import os
    project = get_project(pid)
    if not project:
        flash("Project not found.", "warning")
        return redirect(url_for("dashboard"))
    # Whitelist: only files recorded in inspection metadata are served.
    inspection = (project["data"].get("inspection") or {})
    known = set()
    for entry in (inspection.get("photos") or []):
        known.add(entry.get("filename"))
    for entry in (inspection.get("roof_drawings") or []):
        known.add(entry.get("filename"))
    if filename not in known:
        return ("Not found", 404)
    # Defence-in-depth: refuse any traversal.
    safe = os.path.basename(filename)
    if safe != filename:
        return ("Not found", 404)
    upload_dir = _insp_upload_dir(pid)
    fp = os.path.join(upload_dir, safe)
    if not os.path.isfile(fp):
        return ("Not found", 404)
    from flask import send_file
    return send_file(fp)


@app.route("/project/<int:pid>/inspection/upload/<path:filename>/delete",
           methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def inspection_upload_delete(pid, filename):
    """Remove a single uploaded file + drop it from the inspection record."""
    import os
    csrf_protect()
    project = get_project(pid)
    if not project:
        flash("Project not found.", "warning")
        return redirect(url_for("dashboard"))
    data = project["data"]
    inspection = data.get("inspection") or {}
    photos    = list(inspection.get("photos") or [])
    drawings  = list(inspection.get("roof_drawings") or [])
    safe = os.path.basename(filename)
    photos   = [p for p in photos   if p.get("filename") != safe]
    drawings = [d for d in drawings if d.get("filename") != safe]
    inspection["photos"] = photos
    inspection["roof_drawings"] = drawings
    data["inspection"] = inspection
    save_project_data(pid, data)
    try:
        fp = os.path.join(_insp_upload_dir(pid), safe)
        if os.path.isfile(fp):
            os.unlink(fp)
    except Exception:
        pass
    flash("Removed.", "info")
    return redirect(url_for("inspection_form", pid=pid))
