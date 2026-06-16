"""Engine-first shading source of truth (2026-06-16).

Three problems this fixes:

1) The agent / 3D model / obstruction-form display showed different shading
   numbers because two different calculators were running in parallel:
       - _compute_shading_factor()   (heuristic, missing per-obstruction inputs)
       - _engine_full_analysis()     (real sun-position engine)
   This patch makes the engine the single source of truth — both POST
   handlers (project_shading + inspection_form) now run the engine first
   and store its output as data["shading"]["factor"|"label"|"loss_pct"].
   The heuristic remains as a fallback inside _apply_shading_factor() in
   case the engine cannot run (e.g. missing lat/lon on a brand-new project).

2) The engine ignored the inspection form's tilt_deg / azimuth string and
   pulled from data["tilt_angle"] / data["azimuth"] (set during Location).
   This patch makes the engine prefer the shading-form values, with the
   project-level values as the fallback. Azimuth may arrive as a compass
   label ("South" / "South-East") or a number — both are accepted.

3) Mount type was never threaded into the engine output, so the 3D scene
   always drew a hip-roof house even for ground-mounted projects. This
   patch normalizes inspection.roof_type / project.mounting_type into a
   single "mount_type" field (ground | rooftop_flat | rooftop_sloped)
   and puts it on the engine block so the Three.js scene can branch on it.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"

MARK = b"# Engine-first shading source of truth (2026-06-16)"


# ─────────────────────────────────────────────────────────────────────
# Block A — helpers + _apply_shading_factor, inserted just before
# _compute_shading_factor(). Anchored on the def line so we keep idempotency.
# ─────────────────────────────────────────────────────────────────────

ANCHOR_A = b"def _compute_shading_factor(obstructions):\r\n"

INSERT_A = (
    b"# Engine-first shading source of truth (2026-06-16) -- helpers below.\r\n"
    b"_AZIMUTH_LABEL_DEG = {\r\n"
    b'    "N": 0.0, "NORTH": 0.0,\r\n'
    b'    "NE": 45.0, "NORTH-EAST": 45.0, "NORTHEAST": 45.0,\r\n'
    b'    "E": 90.0, "EAST": 90.0,\r\n'
    b'    "SE": 135.0, "SOUTH-EAST": 135.0, "SOUTHEAST": 135.0,\r\n'
    b'    "S": 180.0, "SOUTH": 180.0,\r\n'
    b'    "SW": 225.0, "SOUTH-WEST": 225.0, "SOUTHWEST": 225.0,\r\n'
    b'    "W": 270.0, "WEST": 270.0,\r\n'
    b'    "NW": 315.0, "NORTH-WEST": 315.0, "NORTHWEST": 315.0,\r\n'
    b"}\r\n"
    b"\r\n"
    b"def _coerce_float(value, default):\r\n"
    b"    # Tolerant float() that returns `default` on None/''/garbage.\r\n"
    b"    try:\r\n"
    b'        if value is None or value == "":\r\n'
    b"            return float(default)\r\n"
    b"        return float(value)\r\n"
    b"    except (TypeError, ValueError):\r\n"
    b"        return float(default)\r\n"
    b"\r\n"
    b"def _azimuth_to_deg(value, default=180.0):\r\n"
    b'    # Accept compass labels ("South"/"South-East"/"S") OR numbers.\r\n'
    b"    if value is None:\r\n"
    b"        return float(default)\r\n"
    b"    if isinstance(value, (int, float)):\r\n"
    b"        return float(value)\r\n"
    b"    s = str(value).strip()\r\n"
    b"    if not s:\r\n"
    b"        return float(default)\r\n"
    b"    deg = _AZIMUTH_LABEL_DEG.get(s.upper())\r\n"
    b"    if deg is not None:\r\n"
    b"        return float(deg)\r\n"
    b"    try:\r\n"
    b"        return float(s)\r\n"
    b"    except ValueError:\r\n"
    b"        return float(default)\r\n"
    b"\r\n"
    b"def _normalize_mount_type(raw):\r\n"
    b'    # Map any of the eight roof_type / mounting_type values down to\r\n'
    b'    # the three buckets the 3D scene actually branches on.\r\n'
    b'    # Inputs accepted: flat / pitched / hip / gable / metal / concrete /\r\n'
    b'    # ground / rooftop_pitched / rooftop_flat / rooftop_metal /\r\n'
    b'    # rooftop_membrane / ground_fixed / ground_tracking.\r\n'
    b'    s = (raw or "").strip().lower()\r\n'
    b'    if not s:\r\n'
    b'        return "rooftop_sloped"\r\n'
    b'    if "ground" in s:\r\n'
    b'        return "ground"\r\n'
    b'    if s in ("flat", "membrane", "concrete",\r\n'
    b'             "rooftop_flat", "rooftop_membrane"):\r\n'
    b'        return "rooftop_flat"\r\n'
    b'    # pitched / hip / gable / metal / rooftop_pitched / rooftop_metal\r\n'
    b'    return "rooftop_sloped"\r\n'
    b"\r\n"
    b"def _apply_shading_factor(project, obstructions, base_shading=None):\r\n"
    b'    """Single source of truth for the shading factor.\r\n'
    b"\r\n"
    b"    Runs _engine_full_analysis() first (real sun-position math). On\r\n"
    b"    engine success: writes the engine bucket into\r\n"
    b'    shading["factor"|"label"|"loss_pct"] and stores the full engine\r\n'
    b'    block at shading["engine"]. On engine failure (missing lat/lon\r\n'
    b'    etc.): falls back to the legacy heuristic so the page keeps\r\n'
    b'    working. Never raises.\r\n'
    b'    """\r\n'
    b"    out = dict(base_shading or {})\r\n"
    b'    out["obstructions"] = obstructions or []\r\n'
    b"    eng = None\r\n"
    b"    try:\r\n"
    b"        eng = _engine_full_analysis(project, out['obstructions'])\r\n"
    b"    except Exception:\r\n"
    b"        eng = None\r\n"
    b"    if eng:\r\n"
    b'        out["factor"]        = eng["bucket_factor"]\r\n'
    b'        out["label"]         = eng["bucket_label"]\r\n'
    b'        out["loss_pct"]      = eng["bucket_loss_pct"]\r\n'
    b'        out["engine"]        = eng\r\n'
    b'        out["factor_source"] = "engine"\r\n'
    b'        out["agent_version"] = "shading-engine-v1-2026-06-16"\r\n'
    b'        out["agent_summary"] = (\r\n'
    b"            f\"Engine: {eng['bucket_label']} (factor {eng['bucket_factor']:.2f}, \"\r\n"
    b"            f\"{eng['bucket_loss_pct']:.1f}% loss) across {eng['affected_panels']} \"\r\n"
    b"            f\"of {eng['total_panels']} panels.\"\r\n"
    b"        )\r\n"
    b'        # Engine result has its own per-step series; clear the legacy\r\n'
    b'        # per-obstruction heuristic payload to avoid confusing the UI.\r\n'
    b'        out["per_obstruction"] = []\r\n'
    b"    elif obstructions:\r\n"
    b"        h = _compute_shading_factor(obstructions)\r\n"
    b'        out["factor"]            = h["factor"]\r\n'
    b'        out["label"]             = h["label"]\r\n'
    b'        out["loss_pct"]          = h["loss_pct"]\r\n'
    b'        out["combined_severity"] = h.get("combined_severity")\r\n'
    b'        out["per_obstruction"]   = h.get("per_obstruction", [])\r\n'
    b'        out["factor_source"]     = "heuristic_fallback"\r\n'
    b'        out["agent_version"]     = "phase1-deterministic-v1"\r\n'
    b'        out["agent_summary"]     = h.get("summary", "")\r\n'
    b'        out.pop("engine", None)\r\n'
    b"    else:\r\n"
    b'        out["factor"]            = 1.00\r\n'
    b'        out["label"]             = "No shading"\r\n'
    b'        out["loss_pct"]          = 0.0\r\n'
    b'        out["factor_source"]     = "no_obstructions"\r\n'
    b'        out["agent_version"]     = "shading-engine-v1-2026-06-16"\r\n'
    b'        out["agent_summary"]     = "No obstructions recorded -- shading factor 1.00 applied."\r\n'
    b'        out["per_obstruction"]   = []\r\n'
    b'        out.pop("engine", None)\r\n'
    b"    return out\r\n"
    b"\r\n"
    b"\r\n"
)


# ─────────────────────────────────────────────────────────────────────
# Block B — _engine_full_analysis tilt/azimuth source change.
# ─────────────────────────────────────────────────────────────────────

OLD_B = (
    b'        tilt    = float(data.get("tilt_angle") or 15.0)\r\n'
    b'        azimuth = float(data.get("azimuth") or 180.0)\r\n'
)

NEW_B = (
    b'        # Prefer shading-form tilt/azimuth (set via inspection form or\r\n'
    b'        # /shading page), fall back to project-level Location values.\r\n'
    b'        # Azimuth may arrive as a compass label ("South") or a number.\r\n'
    b'        _sh_pre = data.get("shading") or {}\r\n'
    b'        tilt = _coerce_float(_sh_pre.get("tilt_deg"),\r\n'
    b'                             float(data.get("tilt_angle") or 15.0))\r\n'
    b'        azimuth = _azimuth_to_deg(\r\n'
    b'            _sh_pre.get("azimuth") if _sh_pre.get("azimuth") not in (None, "", 0)\r\n'
    b'            else data.get("azimuth"),\r\n'
    b'            180.0,\r\n'
    b'        )\r\n'
    b'        # Single mount-type value the 3D scene can branch on.\r\n'
    b'        mount_type = _normalize_mount_type(\r\n'
    b'            _sh_pre.get("roof_type") or data.get("mounting_type"))\r\n'
)


# ─────────────────────────────────────────────────────────────────────
# Block C — _engine_full_analysis return dict gets mount_type.
# ─────────────────────────────────────────────────────────────────────

OLD_C = (
    b'            "tilt_deg":           tilt,\r\n'
    b'            "array_azimuth_deg":  azimuth,\r\n'
    b'            "total_panels":       result["total_panels"],\r\n'
)

NEW_C = (
    b'            "tilt_deg":           tilt,\r\n'
    b'            "array_azimuth_deg":  azimuth,\r\n'
    b'            "mount_type":         mount_type,\r\n'
    b'            "total_panels":       result["total_panels"],\r\n'
)


# ─────────────────────────────────────────────────────────────────────
# Block D — project_shading POST: heuristic -> engine-first.
# ─────────────────────────────────────────────────────────────────────

OLD_D = (
    b'        obstructions = _parse_obstructions(request.form)\r\n'
    b'        analysis = _compute_shading_factor(obstructions)\r\n'
    b'        factor = analysis["factor"]\r\n'
    b'\r\n'
    b'        data = project["data"]\r\n'
    b'        data["shading"] = {\r\n'
    b'            "factor":               factor,\r\n'
    b'            "label":                analysis["label"],\r\n'
    b'            "loss_pct":             analysis["loss_pct"],\r\n'
    b'            "combined_severity":   analysis["combined_severity"],\r\n'
    b'            "per_obstruction":     analysis["per_obstruction"],\r\n'
    b'            "agent_summary":       analysis["summary"],\r\n'
    b'            "agent_version":       "phase1-deterministic-v1",\r\n'
    b'            # Units: "metric" (m, default) or "imperial" (ft). Per-project\r\n'
    b'            # owner choice; numeric fields are stored as-typed.\r\n'
    b'            "units":                ("imperial" if (request.form.get("units","") == "imperial") else "metric"),\r\n'
    b'            # Site-level fields (apply to whole project, not per obstruction).\r\n'
    b'            "tilt_deg":             _shading_num(request.form.get("tilt_deg")),\r\n'
    b'            "azimuth":              (request.form.get("azimuth", "") or "").strip()[:30],\r\n'
    b'            "roof_type":            (request.form.get("roof_type", "") or "").strip()[:40],\r\n'
    b'            "roof_height_m":        _shading_num(request.form.get("roof_height_m")),\r\n'
    b'            "inspection_confirmed": bool(request.form.get("inspection_confirmed")),\r\n'
    b'            # Obstructions: parallel arrays from the cloneable cards. We\r\n'
    b'            # zip into a list of dicts. Empty trailing rows are dropped.\r\n'
    b'            "obstructions":         obstructions,\r\n'
    b'            "saved_at":             datetime.utcnow().isoformat() + "Z",\r\n'
    b'            "saved_by":             session.get("username", ""),\r\n'
    b'        }\r\n'
    b'        save_project_data(pid, data)\r\n'
)

NEW_D = (
    b'        obstructions = _parse_obstructions(request.form)\r\n'
    b'        data = project["data"]\r\n'
    b'        # Engine-first source of truth (fix 2026-06-16): build the\r\n'
    b'        # shading scalars from the form, then run the deterministic\r\n'
    b'        # engine via _apply_shading_factor. The engine drives factor /\r\n'
    b'        # label / loss_pct so the dashboard banner, the 3D scene, the\r\n'
    b'        # agent narrative, and the PV-sizing card all agree.\r\n'
    b'        _existing = data.get("shading", {}) or {}\r\n'
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
    b'        # Clear stale engine output so the helper re-runs on this save.\r\n'
    b'        _existing.pop("engine", None)\r\n'
    b'        data["shading"] = _existing\r\n'
    b'        project["data"] = data\r\n'
    b'        data["shading"] = _apply_shading_factor(\r\n'
    b'            project, obstructions, base_shading=data["shading"])\r\n'
    b'        factor = data["shading"]["factor"]\r\n'
    b'        save_project_data(pid, data)\r\n'
)


# ─────────────────────────────────────────────────────────────────────
# Block E — project_shading POST flash message: drop the `analysis[...]`
# references that no longer exist after Block D.
# ─────────────────────────────────────────────────────────────────────

OLD_E = (
    b'            flash(f"Shading agent picked factor {factor:.2f} ({analysis[\'label\']}, "\r\n'
    b'                  f"{analysis[\'loss_pct\']:.1f}% loss) from {len(obstructions)} obstruction(s). "\r\n'
    b'                  f"Re-run the loads step to apply.",\r\n'
    b'                  "success")\r\n'
)

NEW_E = (
    b'            flash(f"Shading agent picked factor {factor:.2f} ({data[\'shading\'].get(\'label\',\'\')}, "\r\n'
    b'                  f"{data[\'shading\'].get(\'loss_pct\',0):.1f}% loss) from {len(obstructions)} obstruction(s). "\r\n'
    b'                  f"Re-run the loads step to apply.",\r\n'
    b'                  "success")\r\n'
)


# ─────────────────────────────────────────────────────────────────────
# Block F — inspection_form POST: heuristic -> engine-first.
# ─────────────────────────────────────────────────────────────────────

OLD_F = (
    b'        # \xe2\x94\x80\xe2\x94\x80 5. Mirror shading-relevant inputs into data["shading"] \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\r\n'
    b'        # The /shading page reads from data["shading"]; by mirroring here\r\n'
    b'        # we make the inspection form the single source of truth for\r\n'
    b'        # shading inputs (per owner spec: "must pass shading input\r\n'
    b'        # information collected to the shading model to limit human\r\n'
    b'        # filling the shading form").\r\n'
    b'        mirrored = dict(shading)\r\n'
    b'        mirrored["obstructions"]        = obstructions\r\n'
    b'        mirrored["units"]               = units\r\n'
    b'        mirrored["roof_type"]           = roof_type\r\n'
    b'        mirrored["roof_height_m"]       = (float(roof_height) if roof_height.replace(".","",1).isdigit() else None)\r\n'
    b'        mirrored["tilt_deg"]            = (float(tilt_deg)    if tilt_deg.replace(".","",1).isdigit()    else None)\r\n'
    b'        mirrored["azimuth"]             = azimuth\r\n'
    b'        mirrored["inspection_confirmed"] = (shading_present in ("yes", "partial"))\r\n'
    b'        mirrored["source"]              = "inspection_form"\r\n'
    b'\r\n'
    b'        # -- 5b. Compute the shading factor immediately so /loads\r\n'
    b'        #        can use it on the very next calc, without forcing a\r\n'
    b'        #        detour through /shading. Per owner 2026-06-15:\r\n'
    b'        #        "need to capture shading information and persist it\r\n'
    b'        #        and pass it to the load calculation [first time\r\n'
    b'        #        around]".\r\n'
    b'        try:\r\n'
    b'            if shading_present in ("yes", "partial") and obstructions:\r\n'
    b'                _analysis = _compute_shading_factor(obstructions)\r\n'
    b'                mirrored["factor"]            = _analysis["factor"]\r\n'
    b'                mirrored["label"]             = _analysis["label"]\r\n'
    b'                mirrored["loss_pct"]          = _analysis["loss_pct"]\r\n'
    b'                mirrored["combined_severity"] = _analysis.get("combined_severity")\r\n'
    b'                mirrored["per_obstruction"]   = _analysis.get("per_obstruction") or []\r\n'
    b'                mirrored["agent_summary"]     = _analysis.get("summary", "")\r\n'
    b'                mirrored["agent_version"]     = "inspection-form-deterministic-v1"\r\n'
    b'                mirrored["factor_source"]     = "inspection_form_deterministic"\r\n'
    b'            else:\r\n'
    b'                mirrored["factor"]        = 1.0\r\n'
    b'                mirrored["label"]         = "No shading"\r\n'
    b'                mirrored["loss_pct"]      = 0.0\r\n'
    b'                mirrored["factor_source"] = "inspection_form_no_shading"\r\n'
    b'        except Exception as _e:\r\n'
    b'            try:\r\n'
    b'                app.logger.warning(\r\n'
    b'                    "inspection deterministic factor compute failed: %s", _e)\r\n'
    b'            except Exception:\r\n'
    b'                pass\r\n'
    b'\r\n'
    b'        # Clear stale engine output so /shading recomputes against new\r\n'
    b'        # obstructions on next GET.\r\n'
    b'        mirrored.pop("engine", None)\r\n'
    b'        data["shading"] = mirrored\r\n'
)

NEW_F = (
    b'        # \xe2\x94\x80\xe2\x94\x80 5. Mirror shading-relevant inputs into data["shading"] AND\r\n'
    b'        #      run the deterministic engine now so /loads has the\r\n'
    b'        #      canonical factor on the very next calc. Engine-first\r\n'
    b'        #      source of truth (fix 2026-06-16) -- the 3D scene, the\r\n'
    b'        #      agent narrative, the obstruction-form badge, and the\r\n'
    b'        #      PV-sizing card all read the same numbers.\r\n'
    b'        mirrored = dict(shading)\r\n'
    b'        mirrored["obstructions"]         = obstructions\r\n'
    b'        mirrored["units"]                = units\r\n'
    b'        mirrored["roof_type"]            = roof_type\r\n'
    b'        mirrored["mount_type"]           = _normalize_mount_type(\r\n'
    b'                                              roof_type or data.get("mounting_type"))\r\n'
    b'        mirrored["roof_height_m"]        = (float(roof_height) if roof_height.replace(".","",1).isdigit() else None)\r\n'
    b'        mirrored["tilt_deg"]             = (float(tilt_deg)    if tilt_deg.replace(".","",1).isdigit()    else None)\r\n'
    b'        mirrored["azimuth"]              = azimuth\r\n'
    b'        mirrored["inspection_confirmed"] = (shading_present in ("yes", "partial"))\r\n'
    b'        mirrored["source"]               = "inspection_form"\r\n'
    b'        # Clear stale engine output so the helper re-runs on this save.\r\n'
    b'        mirrored.pop("engine", None)\r\n'
    b'        data["shading"] = mirrored\r\n'
    b'        project["data"] = data\r\n'
    b'        try:\r\n'
    b'            if shading_present in ("yes", "partial"):\r\n'
    b'                data["shading"] = _apply_shading_factor(\r\n'
    b'                    project, obstructions, base_shading=data["shading"])\r\n'
    b'            else:\r\n'
    b'                data["shading"]["factor"]        = 1.0\r\n'
    b'                data["shading"]["label"]         = "No shading"\r\n'
    b'                data["shading"]["loss_pct"]      = 0.0\r\n'
    b'                data["shading"]["factor_source"] = "inspection_form_no_shading"\r\n'
    b'        except Exception as _e:\r\n'
    b'            try:\r\n'
    b'                app.logger.warning(\r\n'
    b'                    "inspection engine compute failed: %s", _e)\r\n'
    b'            except Exception:\r\n'
    b'                pass\r\n'
)


PATCHES = [
    ("helpers + _apply_shading_factor (insert before _compute_shading_factor)",
     "insert_before", ANCHOR_A, INSERT_A),
    ("_engine_full_analysis tilt/azimuth/mount_type read",
     "replace", OLD_B, NEW_B),
    ("_engine_full_analysis return dict gets mount_type",
     "replace", OLD_C, NEW_C),
    ("project_shading POST -> engine-first",
     "replace", OLD_D, NEW_D),
    ("project_shading POST flash message uses data['shading']",
     "replace", OLD_E, NEW_E),
    ("inspection_form POST -> engine-first",
     "replace", OLD_F, NEW_F),
]


def patch():
    src = open(TARGET, "rb").read()
    if MARK in src:
        print("[skip] engine-first shading source-of-truth already wired")
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
