"""Wire engine.shading_engine into web_app.py without breaking the legacy
shading route. Adds a helper `_engine_full_analysis(project, obstructions)`
and patches the project_shading route to persist a richer result under
data["shading"]["engine"]. Legacy keys (factor/label/loss_pct/...) keep
the exact same shape so the existing template + the loads handler keep
working unchanged.

Run with: python patch_wire_shading_engine.py
"""
from __future__ import annotations
import io
import sys

TARGET = "web_app.py"

# Block to insert RIGHT BEFORE the project_shading route. Reads project
# context (region, country, tilt, azimuth, num_panels), looks up lat/lng
# from config.global_solar_data, builds engine inputs, runs the pipeline,
# and returns a dict ready to merge into data["shading"]["engine"]. Any
# failure returns None so the route falls back to the legacy heuristic.
HELPER_BLOCK = ('''

def _engine_full_analysis(project, obstructions, on_date=None,
                          step_minutes=30, mitigation_default="Bypass diodes"):
    """Run the deterministic shading engine for a project.

    Returns the engine.run_full_analysis() dict on success, or None if
    project context is incomplete or the engine raises. Never propagates
    exceptions to the route — falling back to the legacy heuristic keeps
    the page working if the engine path is broken.
    """
    try:
        # Import lazily so a missing engine module never crashes app startup.
        from engine.shading_engine import Obstruction, run_full_analysis
        from config.global_solar_data import GLOBAL_DATA
        from datetime import datetime as _dt

        data = project.get("data", {}) or {}
        country = (data.get("country") or "").strip()
        region  = (data.get("region")  or "").strip()
        tilt    = float(data.get("tilt_angle") or 15.0)
        azimuth = float(data.get("azimuth") or 180.0)
        results = data.get("results", {}) or {}
        n_panels = int(results.get("num_panels") or 0)

        # Without a panel count there is nothing to project shadows onto.
        if n_panels <= 0:
            return None

        # Lat/lon — try region table then fall back to country first-region.
        info = (GLOBAL_DATA.get(country) or {}).get("regions", {}).get(region)
        if not info:
            for v in (GLOBAL_DATA.get(country) or {}).get("regions", {}).values():
                info = v
                break
        if not info or "lat" not in info or "lon" not in info:
            return None

        lat = float(info["lat"])
        lon = float(info["lon"])

        # Pick the first non-None mitigation across obstructions; default
        # to Bypass diodes (covers the typical modern module).
        mitigation = mitigation_default
        for o in obstructions:
            m = (o.get("mitigation") or "").strip()
            if m and m.lower() != "none":
                mitigation = m
                break

        # Build engine Obstruction objects. The form gives us height +
        # width + distance + direction; depth is unknown, so we mirror the
        # width (square footprint) as a safe v1 default.
        engine_obs = []
        for i, o in enumerate(obstructions or []):
            try:
                engine_obs.append(Obstruction(
                    obs_id=i + 1,
                    type=str(o.get("type") or "obstruction"),
                    height_m=float(o.get("height") or 0),
                    width_m=float(o.get("width") or 0),
                    depth_m=float(o.get("width") or 0),
                    distance_m=float(o.get("distance") or 0),
                    direction=str(o.get("direction") or "South"),
                    mitigation=str(o.get("mitigation") or "None"),
                    notes=str(o.get("notes") or ""),
                ))
            except Exception:
                continue

        if on_date is None:
            # Owner spec uses summer solstice (21 June) as the worst-case
            # day for the equatorial fleet; we'll let UI pick a date later.
            on_date = _dt(_dt.utcnow().year, 6, 21)

        result = run_full_analysis(
            lat_deg=lat, lon_deg=lon, on_date=on_date,
            tz_offset_h=0.0,
            num_panels=n_panels, tilt_deg=tilt,
            array_azimuth_deg=azimuth,
            mount_height_m=float(data.get("shading", {}).get("roof_height_m") or 1.0),
            obstructions=engine_obs,
            mitigation=mitigation,
            step_minutes=step_minutes,
        )

        # Strip non-JSON-serialisable bits (Panel/TimeStepResult are dataclasses
        # containing tuples — fine for json.dumps in Python 3, but we still
        # shape it for the UI so the template stays simple).
        return {
            "lat":                lat,
            "lon":                lon,
            "on_date":            on_date.strftime("%Y-%m-%d"),
            "tilt_deg":           tilt,
            "array_azimuth_deg":  azimuth,
            "total_panels":       result["total_panels"],
            "affected_panels":    result["affected_panels"],
            "heavily_affected":   result["heavily_affected"],
            "shading_start":      result["shading_start"],
            "shading_end":        result["shading_end"],
            "shading_duration_h": result["shading_duration_h"],
            "system_loss_pct":    result["energy"]["system_loss_pct"],
            "peak_step_loss_pct": result["energy"]["peak_step_loss_pct"],
            "weighted_avg_fraction": result["energy"]["weighted_avg_fraction"],
            "bucket_label":       result["bucket_label"],
            "bucket_loss_pct":    result["bucket_loss_pct"],
            "bucket_factor":      result["bucket_factor"],
            "mitigation":         result["mitigation"],
            "n_strings":          result["n_strings"],
            # Snapshot of per-step shading for the time slider.
            # Each entry: {time, alt, az, avg_frac, partially, fully}.
            "series": [
                {
                    "time": s.when.strftime("%H:%M"),
                    "alt":  round(s.altitude_deg, 1),
                    "az":   round(s.azimuth_deg, 1),
                    "avg_frac": round(s.avg_fraction, 4),
                    "partially": s.panels_partially_shaded,
                    "fully":     s.panels_fully_shaded,
                }
                for s in result["series"]
            ],
            # Per-panel max shaded fraction across the day (for grid heatmap).
            "per_panel_max_frac": [
                round(max((s.per_panel_fraction[i] for s in result["series"]), default=0.0), 3)
                for i in range(result["total_panels"])
            ],
            # Engine version stamp — bump when the algorithm changes so we
            # can detect stale persisted results.
            "engine_version": "shading-engine-v1-2026-06-14",
        }
    except Exception as _e:
        try:
            app.logger.warning("shading engine failure (falling back): %s", _e)
        except Exception:
            pass
        return None


''').encode("utf-8")

# Find the route definition line — we insert HELPER_BLOCK right before it.
ROUTE_ANCHOR = b'@app.route("/project/<int:pid>/shading", methods=["GET", "POST"])'

# Inside the route, RIGHT AFTER the analysis dict is built, we also run
# the engine and stash it under data["shading"]["engine"]. We insert the
# new lines before the existing save_project_data call.
ENGINE_CALL_ANCHOR = b'        save_project_data(pid, data)'
ENGINE_CALL_INSERT = ('''        # Day-1 wiring: also run the deterministic engine. Adds rich
        # output under data["shading"]["engine"]; legacy keys above are
        # preserved unchanged so this is a pure additive change.
        _eng = _engine_full_analysis(project, obstructions)
        if _eng:
            data["shading"]["engine"] = _eng
''').encode("utf-8")


def patch():
    with open(TARGET, "rb") as f:
        src = f.read()

    if b"_engine_full_analysis" in src:
        print("[skip] helper already present — nothing to do")
        return 0

    if ROUTE_ANCHOR not in src:
        print(f"[fail] route anchor not found: {ROUTE_ANCHOR!r}")
        return 2

    # Insert helper RIGHT BEFORE the route anchor. The route is preceded by
    # a "\n\n\n" or similar — we don't strip those, we just inject our block.
    idx = src.rfind(ROUTE_ANCHOR)
    # Walk back to the start of the line so the helper lands cleanly.
    line_start = src.rfind(b"\n", 0, idx) + 1
    new_src = src[:line_start] + HELPER_BLOCK + src[line_start:]

    # Now patch the route body to call _engine_full_analysis after the
    # legacy analysis is computed.
    if ENGINE_CALL_ANCHOR not in new_src:
        print(f"[fail] route body anchor not found: {ENGINE_CALL_ANCHOR!r}")
        return 3
    new_src = new_src.replace(ENGINE_CALL_ANCHOR,
                              ENGINE_CALL_INSERT + ENGINE_CALL_ANCHOR, 1)

    # CRLF preservation: the existing file is CRLF; our HELPER_BLOCK is LF.
    # Re-CRLF only the new bytes to keep diffs minimal.
    # Simpler: re-CRLF the whole new payload — but that would rewrite every
    # existing LF too. Instead, convert HELPER_BLOCK to CRLF before insertion.
    # We already inserted with LF; do a targeted replacement of our own
    # LF-only sentinels back to CRLF.
    # Pragmatic approach: split, walk, re-emit.
    out = io.BytesIO()
    # Both blocks contain only our LF. We re-encode by replacing standalone
    # LF that are NOT preceded by CR with CRLF, but ONLY inside the new
    # inserted bytes. Since we just appended HELPER_BLOCK and ENGINE_CALL_INSERT
    # verbatim, we can simply locate them and rewrite those substrings.
    def to_crlf(b: bytes) -> bytes:
        return b.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

    helper_crlf = to_crlf(HELPER_BLOCK)
    insert_crlf = to_crlf(ENGINE_CALL_INSERT)
    new_src = new_src.replace(HELPER_BLOCK, helper_crlf, 1)
    new_src = new_src.replace(ENGINE_CALL_INSERT, insert_crlf, 1)

    out.write(new_src)
    payload = out.getvalue()

    # Smoke: confirm both pieces are present.
    if b"_engine_full_analysis" not in payload:
        print("[fail] helper missing after patch")
        return 4
    if b'data["shading"]["engine"] = _eng' not in payload:
        print("[fail] route insert missing after patch")
        return 5

    with open(TARGET, "wb") as f:
        f.write(payload)
    print(f"[ok] wired engine into {TARGET} ({len(src)} -> {len(payload)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
