

# ---------------------------------------------------------------------------
# Auto-adjust to bankable (owner 2026-07-05). "Update Project" on the economic
# recommendations page: automatically tune the FINANCIAL parameters (cost/kWp,
# install rate, supply markup, funding mode) so a not-bankable / conditional /
# rejected standard project reaches APPROVED + BANKABLE where feasible. The
# engineering sizing is never changed; the recompute reuses calc_boq +
# calc_economics. Fully reversible via /optimize/undo (restores the snapshot
# stashed in data['optimize_backup']).
# ---------------------------------------------------------------------------
@app.route("/project/<int:pid>/optimize", methods=["POST"])
@login_required
def project_optimize_bankability(pid):
    gate = _paid_only(pid)
    if gate:
        return gate
    csrf_protect()
    project = get_project(pid)
    if not project or "results" not in (project.get("data") or {}):
        return redirect(url_for("project_results", pid=pid))
    from bankability_optimizer import optimize_bankability
    orig = project["data"]
    orig_results = orig.get("results") or {}
    try:
        new_data, changes, achieved, before, after = optimize_bankability(
            orig, calc_boq, calc_economics)
    except Exception:
        flash("Could not auto-adjust the project. No changes were saved.",
              "danger")
        return redirect(url_for("report_economic", pid=pid))
    if not new_data or not changes:
        flash("This project is already at its best bankability for the current "
              "design - cost and financing tuning alone can't improve it further. "
              "See the recommendations below (e.g. right-size loads, revisit the "
              "tariff or add grant funding).", "info")
        return redirect(url_for("report_economic", pid=pid))
    # Fully-restorable snapshot, stored ONCE (first optimisation wins) so repeated
    # runs never lose the true original. Holds the original economics + BOQ so the
    # undo is a direct restore (no recompute).
    new_data.setdefault("optimize_backup", {
        "at": datetime.now().isoformat(timespec="seconds"),
        "cost_usd_kwp": orig.get("cost_usd_kwp"),
        "install_rate_pct": orig.get("install_rate_pct"),
        "supply_markup_pct": orig.get("supply_markup_pct"),
        "funding_mode": orig.get("funding_mode"),
        "economics": orig_results.get("economics"),
        "boq_rows": orig_results.get("boq_rows"),
        "boq_grand": orig_results.get("boq_grand"),
        "verdict": before.get("verdict"),
        "bankability": before.get("bankability"),
    })
    save_project_data(pid, new_data)
    try:
        _log_marketplace_action(
            "project_bankability_optimized", "project", pid,
            "%s/%s -> %s/%s" % (before.get("verdict"), before.get("bankability"),
                                after.get("verdict"), after.get("bankability")))
    except Exception:
        pass
    joined = "; ".join(changes)
    if achieved:
        flash("Project automatically adjusted to APPROVED / %s. What changed: %s. "
              "The economic & energy reports and any funding application now use "
              "these figures. Use Undo on the report to revert." % (
                  after.get("bankability") or "BANKABLE", joined), "success")
    else:
        flash("Project improved to %s / %s (not yet fully bankable). What "
              "changed: %s. Further gains need design changes below." % (
                  after.get("verdict"), after.get("bankability"), joined),
              "warning")
    return redirect(url_for("report_economic", pid=pid))


@app.route("/project/<int:pid>/optimize/undo", methods=["POST"])
@login_required
def project_optimize_undo(pid):
    """Restore the pre-optimisation levers + economics + BOQ from the snapshot
    stashed by /optimize, then clear the backup."""
    gate = _paid_only(pid)
    if gate:
        return gate
    csrf_protect()
    project = get_project(pid)
    if not project:
        return redirect(url_for("project_results", pid=pid))
    data = project["data"] or {}
    bk = data.get("optimize_backup")
    if not bk:
        flash("Nothing to undo - this project has not been auto-adjusted.", "info")
        return redirect(url_for("report_economic", pid=pid))
    for k in ("cost_usd_kwp", "install_rate_pct", "supply_markup_pct",
              "funding_mode"):
        if bk.get(k) is not None:
            data[k] = bk[k]
    results = dict(data.get("results") or {})
    if bk.get("economics") is not None:
        results["economics"] = bk["economics"]
    if bk.get("boq_rows") is not None:
        results["boq_rows"] = bk["boq_rows"]
    if bk.get("boq_grand") is not None:
        results["boq_grand"] = bk["boq_grand"]
    data["results"] = results
    data.pop("optimize_backup", None)
    save_project_data(pid, data)
    flash("Reverted to the original project figures (%s / %s)." % (
        bk.get("verdict") or "original", bk.get("bankability") or ""), "success")
    return redirect(url_for("report_economic", pid=pid))
