# ─────────────────────────────────────────────────────────────────────────────
# Lighting & Fan Circuit Schedule (owner directive 2026-07-06).
#
# What it does:
#   Groups a project's Lighting and Cooling(fan) loads onto final sub-circuits of
#   up to 7 points each (owner rule: "7 lights per circuit breaker"). For each
#   circuit the grouped connected wattage is SUMMED, the design current is derived
#   at 230 V single-phase, and the smallest standard MCB >= that current is picked
#   ("their loads are added together to fix the capacity of the breaker"). Each
#   circuit also carries the category timer (lights 14 h, fans 10 h per the
#   DEFAULT_HOURS table) so the group shares one timer.
#
# Scope (deliberately additive / non-destructive):
#   * This produces an electrical CIRCUIT SCHEDULE + breaker bill-of-materials for
#     the operator. It DOES NOT modify the solar/energy sizing (calc_loads/calc_pv)
#     or the costed BOQ engine — those remain exactly as they were. If the owner
#     wants these breaker quantities folded into the priced BOQ later, that is a
#     separate, explicitly-gated change.
#   * Other appliance categories keep their hours attached directly and are not
#     circuit-grouped here (owner: "other appliances have their time attached
#     directly").
#
# Inputs:  project["data"]["loads"] — list of {name,category,wattage,quantity,hours,...}
# Output:  a dict rendered by templates/circuit_schedule.html
# ─────────────────────────────────────────────────────────────────────────────

# Standard single-pole MCB ratings (amps) — IEC 60898 / BS EN 60898 preferred values.
_MCB_STANDARD_A = [6, 10, 16, 20, 25, 32, 40, 50, 63]

# Load categories that are grouped onto lighting/fan final circuits + their label.
_CIRCUIT_GROUPS = [
    ("Lighting", "Lighting", "LTG"),   # (load category, display type, circuit ref prefix)
    ("Cooling",  "Fans",     "FAN"),   # Cooling category = fans/AC per the load library
]

# Max points (fixtures) per final sub-circuit — owner rule "7 lights per breaker".
_MAX_POINTS_PER_CIRCUIT = 7

# Safety cap on the number of points expanded per category. Circuits are built
# arithmetically (not one object per fixture), but this still bounds how many
# circuit rows a single malformed / malicious quantity can generate, so the
# report can never exhaust memory or CPU. Far above any real building.
_MAX_POINTS_PER_GROUP = 20000


def _pick_mcb(current_a):
    """Smallest standard MCB rating (A) that is >= the circuit design current.
    Returns (rating, overloaded): overloaded is True when even the largest
    standard single-pole MCB (63 A) cannot cover the current — a signal that the
    circuit must be split further or moved to a dedicated feeder."""
    for rating in _MCB_STANDARD_A:
        if rating >= current_a:
            return rating, False
    return _MCB_STANDARD_A[-1], True


def _circuit_row(prefix, disp, timer_h, cur, count, voltage, cnum):
    """Build one circuit dict from an aggregated {(name,watt): qty} map.
    Pure: derives summed load, design current, MCB, and a per-fixture breakdown."""
    total_w = round(sum(w * q for (_n, w), q in cur.items()), 1)
    current_a = round(total_w / voltage, 2) if voltage else 0.0
    breaker_a, overloaded = _pick_mcb(current_a)
    breakdown = [{"name": n, "qty": q, "watt_each": w} for (n, w), q in cur.items()]
    return {
        "ref":        "%s-%02d" % (prefix, cnum),
        "type":       disp,
        "points":     count,
        "total_w":    total_w,
        "current_a":  current_a,
        "breaker_a":  breaker_a,
        "timer_h":    timer_h,
        "overloaded": overloaded,
        "breakdown":  breakdown,
    }


def _circuit_schedule(loads, voltage=230.0):
    """Build a lighting/fan circuit schedule from a project's load list.

    loads:   list of load dicts (name, category, wattage, quantity, ...).
    voltage: single-phase line voltage used to derive current (default 230 V).

    Returns a dict: {circuits, summary, voltage, max_points, mcb_sizes}.
    Circuits are filled arithmetically (no per-fixture object explosion) and the
    per-category point count is capped at _MAX_POINTS_PER_GROUP for safety.
    Never raises on malformed load rows — bad values are coerced to 0/1."""
    try:
        voltage = float(voltage) or 230.0
    except (TypeError, ValueError):
        voltage = 230.0

    cap = _MAX_POINTS_PER_CIRCUIT
    circuits = []
    truncated = False

    for cat, disp, prefix in _CIRCUIT_GROUPS:
        # Collect (name, watt, qty) for this category, clamping quantity so a
        # single load cannot push the group past the safety cap.
        items = []
        group_total = 0
        for ld in (loads or []):
            if (ld or {}).get("category") != cat:
                continue
            try:
                watt = float(ld.get("wattage", 0) or 0)
            except (TypeError, ValueError):
                watt = 0.0
            try:
                qty = int(round(float(ld.get("quantity", 1) or 1)))
            except (TypeError, ValueError):
                qty = 1
            qty = max(1, qty)
            if group_total + qty > _MAX_POINTS_PER_GROUP:
                qty = _MAX_POINTS_PER_GROUP - group_total
                truncated = True
            if qty <= 0:
                continue
            group_total += qty
            items.append((str(ld.get("name") or disp), watt, qty))

        if not items:
            continue

        timer_h = _default_hours_for(cat)
        cnum = 0
        cur = {}        # (name, watt) -> count in the circuit currently being filled
        cur_count = 0
        # Fill circuits arithmetically: take min(space, remaining) at a time so a
        # quantity of 10 000 costs O(circuits), not O(fixtures).
        for name, watt, qty in items:
            remaining = qty
            while remaining > 0:
                take = min(cap - cur_count, remaining)
                key = (name, watt)
                cur[key] = cur.get(key, 0) + take
                cur_count += take
                remaining -= take
                if cur_count >= cap:
                    cnum += 1
                    circuits.append(_circuit_row(prefix, disp, timer_h, cur, cur_count, voltage, cnum))
                    cur = {}
                    cur_count = 0
        if cur_count > 0:
            cnum += 1
            circuits.append(_circuit_row(prefix, disp, timer_h, cur, cur_count, voltage, cnum))

    # Summary: breaker bill-of-materials (rating -> count) + totals.
    breaker_bom = {}
    for c in circuits:
        breaker_bom[c["breaker_a"]] = breaker_bom.get(c["breaker_a"], 0) + 1
    summary = {
        "circuit_count": len(circuits),
        "total_points":  sum(c["points"] for c in circuits),
        "total_w":       round(sum(c["total_w"] for c in circuits), 1),
        "overloaded":    any(c["overloaded"] for c in circuits),
        "truncated":     truncated,
        "breaker_bom":   [{"rating": r, "count": breaker_bom[r]}
                          for r in sorted(breaker_bom)],
    }
    return {
        "circuits":   circuits,
        "summary":    summary,
        "voltage":    voltage,
        "max_points": _MAX_POINTS_PER_CIRCUIT,
        "mcb_sizes":  _MCB_STANDARD_A,
    }


@app.route("/project/<int:pid>/report/circuits")
@login_required
def report_circuits(pid):
    # Lighting & fan circuit schedule. Paid feature, consistent with the other
    # engineering reports. Read-only: derives circuits from the saved loads and
    # never mutates the project or its results.
    gate = _paid_only(pid)
    if gate:
        return gate
    project = get_project(pid)
    if not project:
        return redirect(url_for("dashboard"))
    loads = (project.get("data") or {}).get("loads") or []
    sched = _circuit_schedule(loads)
    return render_template("circuit_schedule.html", user=current_user(),
                           project=project, sched=sched)
