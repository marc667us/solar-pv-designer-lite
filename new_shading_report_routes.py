# Shading Report routes — added 2026-06-14. Three routes:
#   GET  /project/<pid>/report/shading      → HTML (printable)
#   GET  /project/<pid>/report/shading/pdf  → PDF via markdown-pdf
# Email is handled through the existing /project/<pid>/email pipeline
# (REPORT_OPTIONS gets a new entry below).


@app.route("/project/<int:pid>/report/shading")
@login_required
def report_shading(pid):
    """HTML view of the AI 3D Shading Simulation report — printable +
    standalone link the operator can hand to a client or attach to a
    drawing pack."""
    project = get_project(pid)
    if not project:
        flash("Project not found.", "warning")
        return redirect(url_for("dashboard"))
    return render_template("report_shading.html",
                           user=current_user(),
                           project=project,
                           d=project["data"],
                           shading=project["data"].get("shading", {}) or {},
                           r=project["data"].get("results", {}) or {})


@app.route("/project/<int:pid>/report/shading/pdf")
@login_required
@limiter.limit("5 per minute")
def export_pdf_shading(pid):
    """PDF export — Shading Analysis Report."""
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project:
        flash("Project not found.", "warning")
        return redirect(url_for("dashboard"))
    d   = project["data"]
    r   = d.get("results", {}) or {}
    sh  = d.get("shading", {}) or {}
    eng = sh.get("engine", {}) or {}
    ag  = sh.get("agent_v2", {}) or {}
    sym = d.get("symbol", "$")

    factor       = float(sh.get("factor") or eng.get("bucket_factor") or 1.0)
    label        = sh.get("label") or eng.get("bucket_label") or "No shading"
    loss_pct     = float(sh.get("loss_pct") or eng.get("bucket_loss_pct") or 0.0)
    source       = sh.get("factor_source") or ("agent" if ag else "engine")
    pv_base      = float(r.get("pv_kw_base") or r.get("pv_kw") or 0)
    pv_corrected = (pv_base / factor) if factor and factor > 0 else pv_base
    pv_recommended = math.ceil(pv_corrected) if pv_corrected else 0

    obstructions = sh.get("obstructions", []) or []

    # ── Header ──────────────────────────────────────────────────────────
    md = f"""# Shading Analysis Report — {project["name"]}

**{d.get("region","")}, {d.get("country","")}** · {d.get("system_type","off-grid").title()} System

Prepared by: SolarPro Global · BS 7671:2018 · IEC 61853 · IEC 62446

---

## 1. Executive Summary

This report documents the AI 3D Shading Simulation performed on the
**{project["name"]}** site. The shading factor was determined from
on-site obstruction geometry (height, distance, direction), the site's
solar geometry (latitude {eng.get("lat","--")}°, longitude
{eng.get("lon","--")}°), and the electrical-string behaviour of the PV
modules under partial shade.

| Metric | Value |
|---|---|
| **AI selected shading factor** | **{factor:.2f}** |
| **Severity bucket** | {label} |
| **Estimated energy loss** | {loss_pct:.1f}% |
| **Affected panels (peak step)** | {eng.get("affected_panels","--")} of {eng.get("total_panels","--")} |
| **Daily shading window** | {eng.get("shading_start","--")} – {eng.get("shading_end","--")} ({eng.get("shading_duration_h","--")} hours) |
| **Mitigation in place** | {eng.get("mitigation", sh.get("mitigation", "Bypass diodes"))} |
| **Factor source** | {source} |

---

## 2. Site Geometry

| Parameter | Value |
|---|---|
| Latitude | {eng.get("lat","--")}° N |
| Longitude | {eng.get("lon","--")}° E |
| Analysis date | {eng.get("on_date","21 June (summer solstice)")} |
| Array tilt | {eng.get("tilt_deg","--")}° |
| Array azimuth | {eng.get("array_azimuth_deg","--")}° |
| Total panels | {eng.get("total_panels","--")} |
| Strings | {eng.get("n_strings","--")} |

---

## 3. Obstruction Register

"""
    if obstructions:
        md += "| # | Type | Height (m) | Width (m) | Distance (m) | Direction | Mitigation |\n"
        md += "|---|---|---|---|---|---|---|\n"
        for i, o in enumerate(obstructions, 1):
            md += (f"| {i} | {o.get('type','—')} | {float(o.get('height',0)):.1f} | "
                   f"{float(o.get('width',0)):.1f} | {float(o.get('distance',0)):.1f} | "
                   f"{o.get('direction','—')} | {o.get('mitigation','None')} |\n")
    else:
        md += "_No obstructions recorded on this project._\n"

    md += """

---

## 4. AI Shading Agent — Narrative Analysis

"""
    if ag and ag.get("narrative"):
        md += f"{ag.get('narrative')}\n\n"
    else:
        md += (f"The deterministic shading engine computed a factor of "
               f"**{factor:.2f}** ({label}, {loss_pct:.1f}% loss) for this "
               f"site. See the per-obstruction table above and the system "
               f"recommendation in section 6.\n\n")

    if ag and ag.get("per_obstruction"):
        md += "### Per-obstruction impact\n\n"
        md += "| Obstruction | Impact | Mitigation recommendation |\n"
        md += "|---|---|---|\n"
        for r2 in ag["per_obstruction"]:
            md += (f"| {r2.get('ref','—')} | {r2.get('impact','—')} | "
                   f"{r2.get('mitigation','—')} |\n")
        md += "\n"

    if ag and ag.get("factor_reasoning"):
        md += f"**Factor reasoning:** {ag['factor_reasoning']}\n\n"

    if ag and ag.get("what_ifs"):
        md += "### Mitigation what-ifs\n\nIf you change the mitigation strategy, the agent estimates:\n\n"
        md += "| Scenario | Expected factor | Expected loss | Reasoning |\n"
        md += "|---|---|---|---|\n"
        for w in ag["what_ifs"]:
            md += (f"| {w.get('scenario','—')} | "
                   f"{w.get('expected_factor','—')} | "
                   f"{w.get('expected_loss_pct','—')}% | "
                   f"{w.get('reasoning','—')} |\n")
        md += "\n"

    md += f"""---

## 5. PV System Sizing — With Shading Correction

The corrected PV array size is the base size divided by the shading
factor. This ensures that even with the modelled shading loss, the
system still delivers the design daily energy demand.

| Step | Value |
|---|---|
| Base PV size (no shading) | **{pv_base:.2f} kWp** |
| AI selected shading factor | **{factor:.2f}** ({label}) |
| Corrected PV size | **{pv_corrected:.2f} kWp** |
| Recommended PV size (rounded up) | **{pv_recommended} kWp** |

Formula: `Corrected PV Size = Base PV Size ÷ Shading Factor`

For this project: `{pv_base:.2f} ÷ {factor:.2f} = {pv_corrected:.2f} kWp` → rounded to **{pv_recommended} kWp**.

---

## 6. Recommendations

"""
    if factor >= 0.999:
        md += ("- No additional PV capacity is required for shading.\n"
               "- Re-confirm during commissioning that the site stays free "
               "of new obstructions (trees, mast retrofits, neighbour builds).\n")
    elif factor >= 0.90:
        md += ("- Light shading detected. Standard module-level bypass diodes "
               "are sufficient — no per-panel electronics required.\n"
               "- Re-confirm panel layout avoids the morning/evening shadow "
               "windows where possible.\n"
               f"- Use the recommended {pv_recommended} kWp array size.\n")
    elif factor >= 0.80:
        md += ("- Moderate to significant shading. Consider DC optimisers "
               "(Tigo, SolarEdge HD-Wave) on the affected string(s) to "
               "eliminate string-mismatch losses.\n"
               "- If practical, increase row spacing or relocate the array "
               "away from the dominant obstruction.\n"
               f"- Use the recommended {pv_recommended} kWp array size.\n")
    else:
        md += ("- Heavy or severe shading. Strongly recommend DC optimisers "
               "OR micro-inverters (Enphase IQ8) on the entire array to "
               "decouple per-panel MPPT.\n"
               "- If the dominant obstruction is removable (tree pruning, "
               "antenna relocation), the financial case for removal is "
               "typically 18-36 months payback.\n"
               f"- Use the recommended {pv_recommended} kWp array size.\n"
               "- Add a performance-monitoring system (e.g. Solar-Log, Tigo "
               "TS4) so the array's daily yield is tracked against the "
               "shading model post-installation.\n")

    md += f"""

---

## 7. Methodology

The AI 3D Shading Simulation Agent uses:

1. **Sun position** via the NOAA Solar Position Algorithm (≈0.1°
   accuracy) at the site GPS coordinates.
2. **3D ray-cast shadow projection** from each obstruction's bounding
   geometry onto the panel array plane.
3. **Per-panel intersection** via convex polygon clipping
   (Sutherland-Hodgman) at 30-minute intervals across the day.
4. **Electrical-string model** that applies the correct loss formula
   per mitigation strategy: None / Bypass diodes (3 substrings per
   panel + Kirchhoff string penalty) / DC optimisers / Micro-inverters
   (per-panel MPPT).
5. **8-bucket conservative pick** matching the project's
   `SHADING_FACTORS` table; if computed loss falls between bands, the
   conservative (higher-loss) bucket is selected.
6. **Narrative explanation** from a Google-ADK `LlmAgent` whose system
   prompt carries NREL solar geometry, IEC 61853 string-electrical
   behaviour, and common site patterns.

---

*Shading Analysis Report — {project["name"]}*
*Generated by SolarPro Global · AI 3D Shading Simulation Agent v1*
"""
    fname = f"Shading_Report_{project['name'].replace(' ','_')}.pdf"
    return _render_pdf(f"Shading Analysis Report — {project['name']}", md, fname)
