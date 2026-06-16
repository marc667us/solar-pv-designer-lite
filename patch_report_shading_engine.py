"""Ensure the report routes have a populated engine block (2026-06-16).

PID 21/23 had no shading.engine on disk because the engine block had only
ever been patched in transiently by /shading GET, never persisted. The
report HTML + PDF read shading.engine directly, so all the angles
(lat / lon / tilt / azimuth / panel count / shading window) rendered as
"--" on those projects.

This patch:
  1) Adds _ensure_engine_block(project, pid) which runs
     _engine_full_analysis() and persists the result when the block is
     missing. Safe to call multiple times; no-op once persisted.
  2) Calls it at the top of report_shading() and export_pdf_shading()
     so the report always has the engine numbers, regardless of which
     URL the operator visited first.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"
MARK = b"def _ensure_engine_block(project, pid):"


ANCHOR_HELPER_BEFORE = b"def _compute_shading_factor(obstructions):\r\n"

INSERT_HELPER = (
    b"def _ensure_engine_block(project, pid):\r\n"
    b'    """Populate data["shading"]["engine"] if it is missing.\r\n'
    b"\r\n"
    b"    The /shading GET handler patches the engine in transiently so the\r\n"
    b"    dashboard always renders, but never saves it. As a result, routes\r\n"
    b"    that read directly from disk (the standalone shading report HTML +\r\n"
    b"    PDF) saw an empty engine block on any project that had never been\r\n"
    b"    saved through a POST. This helper runs the engine and persists.\r\n"
    b'    """\r\n'
    b"    try:\r\n"
    b'        data = project.get("data") or {}\r\n'
    b'        sh = data.get("shading", {}) or {}\r\n'
    b'        if sh.get("engine"):\r\n'
    b"            return\r\n"
    b'        eng = _engine_full_analysis(project, sh.get("obstructions") or [])\r\n'
    b"        if not eng:\r\n"
    b"            return\r\n"
    b"        sh = dict(sh)\r\n"
    b'        sh["engine"] = eng\r\n'
    b'        data["shading"] = sh\r\n'
    b"        save_project_data(pid, data)\r\n"
    b'        project["data"] = data\r\n'
    b"    except Exception as _e:\r\n"
    b"        try:\r\n"
    b'            app.logger.warning("engine-block backfill failed: %s", _e)\r\n'
    b"        except Exception:\r\n"
    b"            pass\r\n"
    b"\r\n"
    b"\r\n"
)


OLD_REPORT = (
    b'def report_shading(pid):\r\n'
    b'    """HTML view of the AI 3D Shading Simulation report \xe2\x80\x94 printable +\r\n'
    b'    standalone link the operator can hand to a client or attach to a\r\n'
    b'    drawing pack."""\r\n'
    b'    project = get_project(pid)\r\n'
    b'    if not project:\r\n'
    b'        flash("Project not found.", "warning")\r\n'
    b'        return redirect(url_for("dashboard"))\r\n'
    b'    return render_template("report_shading.html",\r\n'
)

NEW_REPORT = (
    b'def report_shading(pid):\r\n'
    b'    """HTML view of the AI 3D Shading Simulation report \xe2\x80\x94 printable +\r\n'
    b'    standalone link the operator can hand to a client or attach to a\r\n'
    b'    drawing pack."""\r\n'
    b'    project = get_project(pid)\r\n'
    b'    if not project:\r\n'
    b'        flash("Project not found.", "warning")\r\n'
    b'        return redirect(url_for("dashboard"))\r\n'
    b'    # Ensure engine angles are present even on projects that were last\r\n'
    b'    # touched before the engine-first fix. Persists, so subsequent loads\r\n'
    b'    # are a no-op.\r\n'
    b'    _ensure_engine_block(project, pid)\r\n'
    b'    return render_template("report_shading.html",\r\n'
)


OLD_PDF = (
    b'def export_pdf_shading(pid):\r\n'
    b'    """PDF export \xe2\x80\x94 Shading Analysis Report."""\r\n'
    b'    gate = _paid_only(pid)\r\n'
    b'    if gate: return gate\r\n'
    b'    project = get_project(pid)\r\n'
    b'    if not project:\r\n'
    b'        flash("Project not found.", "warning")\r\n'
    b'        return redirect(url_for("dashboard"))\r\n'
    b'    d   = project["data"]\r\n'
)

NEW_PDF = (
    b'def export_pdf_shading(pid):\r\n'
    b'    """PDF export \xe2\x80\x94 Shading Analysis Report."""\r\n'
    b'    gate = _paid_only(pid)\r\n'
    b'    if gate: return gate\r\n'
    b'    project = get_project(pid)\r\n'
    b'    if not project:\r\n'
    b'        flash("Project not found.", "warning")\r\n'
    b'        return redirect(url_for("dashboard"))\r\n'
    b'    # Backfill engine block if missing so the PDF carries angles.\r\n'
    b'    _ensure_engine_block(project, pid)\r\n'
    b'    d   = project["data"]\r\n'
)


PATCHES = [
    ("_ensure_engine_block helper (insert before _compute_shading_factor)",
     "insert_before", ANCHOR_HELPER_BEFORE, INSERT_HELPER),
    ("report_shading runs _ensure_engine_block",
     "replace", OLD_REPORT, NEW_REPORT),
    ("export_pdf_shading runs _ensure_engine_block",
     "replace", OLD_PDF, NEW_PDF),
]


def patch():
    src = open(TARGET, "rb").read()
    if MARK in src:
        print("[skip] _ensure_engine_block already wired")
        return 0
    out = src
    for label, mode, old, new in PATCHES:
        if mode == "insert_before":
            idx = out.find(old)
            if idx < 0:
                print(f"[fail] anchor not found for: {label}")
                return 2
            out = out[:idx] + new + out[idx:]
            print(f"[ok] inserted: {label}")
        elif mode == "replace":
            if old not in out:
                print(f"[fail] OLD bytes not found for: {label}")
                return 3
            count = out.count(old)
            if count > 1:
                print(f"[fail] OLD bytes appear {count} times for: {label}")
                return 4
            out = out.replace(old, new, 1)
            print(f"[ok] replaced: {label}")
    open(TARGET, "wb").write(out)
    print(f"[done] {len(PATCHES)} patches applied")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
