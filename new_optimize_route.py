

# ---------------------------------------------------------------------------
# Auto-adjust to bankable (owner 2026-07-05). "Update Project" on the economic
# recommendations page: automatically tune the FINANCIAL parameters (cost/kWp,
# install rate, supply markup, funding mode) so a not-bankable / conditional /
# rejected standard project reaches APPROVED + BANKABLE where feasible. The
# engineering sizing is never changed; the recompute reuses calc_boq +
# calc_economics. Reversible via the stashed data['optimize_backup'].
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
    try:
        new_data, changes, achieved, before, after = optimize_bankability(
            project["data"], calc_boq, calc_economics)
    except Exception as e:
        flash("Could not auto-adjust the project (%s). No changes were saved."
              % type(e).__name__, "danger")
        return redirect(url_for("report_economic", pid=pid))
    if not new_data or not changes:
        flash("This project is already at its best bankability for the current "
              "design - cost and financing tuning alone can't improve it further. "
              "See the recommendations below (e.g. right-size loads, revisit the "
              "tariff or add grant funding).", "info")
        return redirect(url_for("report_economic", pid=pid))
    # Reversible: stash the ORIGINAL levers + verdict once (keeps the first backup
    # across repeated runs).
    new_data.setdefault("optimize_backup", {
        "at": datetime.now().isoformat(timespec="seconds"),
        "cost_usd_kwp": (project["data"] or {}).get("cost_usd_kwp"),
        "install_rate_pct": (project["data"] or {}).get("install_rate_pct"),
        "supply_markup_pct": (project["data"] or {}).get("supply_markup_pct"),
        "funding_mode": (project["data"] or {}).get("funding_mode"),
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
        flash("Project automatically adjusted to APPROVED / BANKABLE. What "
              "changed: %s. The economic & energy reports and any funding "
              "application now use these figures." % joined, "success")
    else:
        flash("Project improved to %s / %s (not yet fully bankable). What "
              "changed: %s. Further gains need design changes below." % (
                  after.get("verdict"), after.get("bankability"), joined),
              "warning")
    return redirect(url_for("report_economic", pid=pid))
