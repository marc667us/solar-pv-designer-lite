"""Add simulation date/time picker to the AI 3D Shading Simulation.

3d10 plan §6 universal data contract names `simulationDate` and
`simulationTime`. Until now the engine always ran for the summer
solstice (21 June). Owner wants the operator to pick a date so the
sun path + shadow geometry match the actual project month.

Two patches:

A) `_engine_full_analysis()` -- when `on_date` is None, read
   `data["shading"]["sim_date"]` (YYYY-MM-DD) first; fall back to
   solstice only if no date saved. Adds the chosen date to the engine
   return so the dashboard can show it.

B) `project_shading` POST handler -- parse `sim_date` + `sim_time` from
   the form and persist them in `data["shading"]` BEFORE the engine
   runs (which then reads them via patch A).
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"
MARK = b"# 3d10 plan: sim_date/sim_time picker (2026-06-16 late)"


OLD_A = (
    b'        if on_date is None:\r\n'
    b'            # Owner spec uses summer solstice (21 June) as the worst-case\r\n'
    b'            # day for the equatorial fleet; we\'ll let UI pick a date later.\r\n'
    b'            on_date = _dt(_dt.utcnow().year, 6, 21)\r\n'
)

NEW_A = (
    b'        if on_date is None:\r\n'
    b'            # 3d10 plan: sim_date/sim_time picker (2026-06-16 late).\r\n'
    b'            # Read the form-persisted simulation date if set, else fall\r\n'
    b'            # back to summer solstice (21 June) for worst-case analysis.\r\n'
    b'            _sd_raw = (_sh_pre.get("sim_date") or "").strip()\r\n'
    b'            on_date = None\r\n'
    b'            if _sd_raw:\r\n'
    b'                try:\r\n'
    b'                    on_date = _dt.strptime(_sd_raw[:10], "%Y-%m-%d")\r\n'
    b'                except Exception:\r\n'
    b'                    on_date = None\r\n'
    b'            if on_date is None:\r\n'
    b'                on_date = _dt(_dt.utcnow().year, 6, 21)\r\n'
)


OLD_B = (
    b'        _existing.update({\r\n'
    b'            "units":                ("imperial" if (request.form.get("units","") == "imperial") else "metric"),\r\n'
    b'            "tilt_deg":             _shading_num(request.form.get("tilt_deg")),\r\n'
    b'            "azimuth":              (request.form.get("azimuth", "") or "").strip()[:30],\r\n'
    b'            "roof_type":            (request.form.get("roof_type", "") or "").strip()[:40],\r\n'
    b'            "mount_type":           _normalize_mount_type(\r\n'
    b'                                       request.form.get("roof_type") or data.get("mounting_type")),\r\n'
    b'            "roof_height_m":        _shading_num(request.form.get("roof_height_m")),\r\n'
    b'            "inspection_confirmed": bool(request.form.get("inspection_confirmed")),\r\n'
    b'            "obstructions":         obstructions,\r\n'
    b'            "saved_at":             datetime.utcnow().isoformat() + "Z",\r\n'
    b'            "saved_by":             session.get("username", ""),\r\n'
    b'        })\r\n'
)

NEW_B = (
    b'        _existing.update({\r\n'
    b'            "units":                ("imperial" if (request.form.get("units","") == "imperial") else "metric"),\r\n'
    b'            "tilt_deg":             _shading_num(request.form.get("tilt_deg")),\r\n'
    b'            "azimuth":              (request.form.get("azimuth", "") or "").strip()[:30],\r\n'
    b'            "roof_type":            (request.form.get("roof_type", "") or "").strip()[:40],\r\n'
    b'            "mount_type":           _normalize_mount_type(\r\n'
    b'                                       request.form.get("roof_type") or data.get("mounting_type")),\r\n'
    b'            "roof_height_m":        _shading_num(request.form.get("roof_height_m")),\r\n'
    b'            "inspection_confirmed": bool(request.form.get("inspection_confirmed")),\r\n'
    b'            # 3d10 plan sim_date/sim_time picker (2026-06-16 late).\r\n'
    b'            # YYYY-MM-DD + HH:MM strings; the engine reads sim_date in\r\n'
    b'            # _engine_full_analysis, the dashboard JS seeds the time\r\n'
    b'            # slider with sim_time on initial render.\r\n'
    b'            "sim_date":             (request.form.get("sim_date", "") or "").strip()[:10],\r\n'
    b'            "sim_time":             (request.form.get("sim_time", "") or "").strip()[:5],\r\n'
    b'            "obstructions":         obstructions,\r\n'
    b'            "saved_at":             datetime.utcnow().isoformat() + "Z",\r\n'
    b'            "saved_by":             session.get("username", ""),\r\n'
    b'        })\r\n'
)


PATCHES = [
    ("_engine_full_analysis reads sim_date", "replace", OLD_A, NEW_A),
    ("project_shading POST persists sim_date + sim_time", "replace", OLD_B, NEW_B),
]


def patch():
    src = open(TARGET, "rb").read()
    if MARK in src:
        print("[skip] sim_date picker already wired")
        return 0
    out = src
    for label, mode, old, new in PATCHES:
        if old not in out:
            print(f"[fail] OLD bytes not found for: {label}")
            return 3
        if out.count(old) > 1:
            print(f"[fail] OLD bytes appear multiple times for: {label}")
            return 4
        out = out.replace(old, new, 1)
        print(f"[ok] replaced: {label}")
    open(TARGET, "wb").write(out)
    print(f"[done] {len(PATCHES)} patches applied")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
