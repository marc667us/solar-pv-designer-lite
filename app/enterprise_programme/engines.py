"""Enterprise Solar Programme -- the bridge to the app's two design engines (slice 7).

THE OWNER'S RULE, WHICH THIS MODULE EXISTS TO OBEY
--------------------------------------------------
    "when you are in planning the programme must open into standard or generation station
     design"
    "where the programme is building a generating station use the whole generation station
     design approach with all the outputs"
    "the reusable components for a residential programme will be standard design, including
     check my bill, field assessment to be applied at each location, shading and funding"

So there is nothing new to invent here. Both engines already exist, are already live, and
are already the thing the owner trusts. This module's entire job is to CALL them -- not to
reimplement, wrap, improve, or fork them.

    standard            -> web_app._run_project_design       (calc_loads -> calc_pv ->
                           calc_battery -> calc_inverter -> calc_mppt -> size_all_cables ->
                           calc_boq -> calc_economics), seeded from Check-My-Bill's own
                           web_app._bc_synthetic_loads. That is the "including check my bill"
                           in the owner's sentence, and it is a REUSE, not a lookalike: the
                           programme's typical bill goes through the same inversion the
                           consumer landing page uses, so a programme design and a
                           walk-in customer's design agree.
    generation_station  -> new_capital_investment_routes.size_utility_pv +
                           _ci_solar_boq_rows -- the Generation Station module's own sizing
                           and its own BOQ, with its own outputs.

WHY THE IMPORTS ARE LAZY, AND WHY THAT IS NOT A STYLE CHOICE
------------------------------------------------------------
`web_app` imports half the platform at module scope and, at the bottom, registers routes.
`app.enterprise_programme` is imported BY the route module that web_app's entrypoint loads.
A module-scope `import web_app` here would therefore be a genuine import cycle, not a
theoretical one. It would also make the whole enterprise package unimportable without a
Flask app -- which would take 274 unit tests offline and, worse, make this module the one
part of the programme rebuild that could not be tested at all.

So the engines are resolved INSIDE the functions, and every function accepts an optional
override, which the tests use to inject a fake. That override is also the seam that keeps
this package honest against the reusability rule (CLAUDE.md s0.3): nothing outside this file
knows that `web_app` exists.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-----------------------------------------
It does not open a transaction and it does not write an audit row. The engines call
`get_db()` and take their OWN connection -- so calling one while holding the enterprise
transaction open would have two connections contending for the same rows, which on Postgres
is a lock wait and, in the worst ordering, a deadlock. The caller (rollout.py) runs the
engine FIRST, outside its transaction, and only then opens a transaction to record what the
engine produced. Read the ordering comment in rollout.create_reference_design before
changing anything here.
"""

from __future__ import annotations

import json
import math

# The system_configuration codes the TEMPLATE offers (constants.SYSTEM_CONFIGURATIONS) are
# not the system_type strings the DESIGN ENGINE understands (web_app's "grid-tied" /
# "off-grid" / "hybrid"). Two vocabularies, one mapping, in one place. Without this the
# translation gets done ad hoc at each callsite and drifts.
_SYSTEM_TYPE_BY_CONFIG: dict[str, str] = {
    "grid_tied":   "grid-tied",
    "off_grid":    "off-grid",
    "hybrid":      "hybrid",
    "grid_backup": "hybrid",
}

# A month, in days. The same constant web_app._bc_synthetic_loads divides by -- named here
# rather than repeated as a bare 30.44, because a programme's monthly bill and a walk-in
# customer's monthly bill must convert to a daily figure IDENTICALLY or the two designs
# quietly disagree by a few percent and nobody can say why.
DAYS_PER_MONTH = 30.44


class EngineError(Exception):
    """A design engine could not produce a design. Carries a message fit for an operator."""


# ---------------------------------------------------------------------------
# resolving the real engines (lazily -- see the module docstring)
# ---------------------------------------------------------------------------


def _app():
    """The live `web_app` module. Imported on use, never at module scope."""
    import web_app  # noqa: PLC0415 -- deliberate: see module docstring
    return web_app


def _ci():
    """The live Generation Station module. Imported on use, never at module scope."""
    import new_capital_investment_routes as ci  # noqa: PLC0415
    return ci


# ---------------------------------------------------------------------------
# the standard path -- residential / commercial buildings
# ---------------------------------------------------------------------------


def standard_seed(*, monthly_kwh: float, country: str, region: str,
                  system_configuration: str, chemistry: str = "LiFePO4",
                  autonomy: int = 1, app=None) -> tuple[dict, list[dict]]:
    """Build the (project data, loads) pair a standard design starts from.

    Input:  the programme's TYPICAL monthly consumption for one building, its location, and
            the approved template's system configuration.
    Output: (initial_data, loads) -- exactly the two things _run_project_design consumes.
    Raises: EngineError when the consumption is not a usable number.

    The loads come from web_app._bc_synthetic_loads -- Check-My-Bill's own load synthesiser.
    That is the reuse the owner asked for by name. A programme's "typical building" and a
    Check-My-Bill walk-in with the same bill therefore get the same load schedule, the same
    array, and the same BOQ, which is the only defensible answer: a sponsor cannot be quoted
    one number and a retail customer another for the same house.

    A zero or negative consumption is REFUSED rather than defaulted. web_app's own bill-check
    route refuses it too ("a zero bill inverts to 0 kWh, which would seed a degenerate
    zero-panel design"), and a degenerate design replicated across 400 sites is 400 wrong
    answers issued with total confidence.
    """
    app = app or _app()

    try:
        kwh = float(monthly_kwh)
    except (TypeError, ValueError):
        raise EngineError("the typical monthly consumption must be a number") from None
    if not math.isfinite(kwh) or kwh <= 0:
        raise EngineError(
            "the typical monthly consumption must be greater than zero -- a zero "
            "consumption designs a zero-panel system, and this design is about to be "
            "replicated across every site in the programme"
        )

    loads = app._bc_synthetic_loads(kwh)
    if not loads or float(loads[0].get("wattage") or 0) <= 0:
        raise EngineError(
            "that consumption did not produce a usable load schedule; check the figure"
        )

    sd = app.get_solar_data(country, region) or {}
    system_type = _SYSTEM_TYPE_BY_CONFIG.get(system_configuration, "grid-tied")

    initial_data = {
        "country":       country,
        "region":        region,
        "psh":           sd.get("psh", 5.3),
        "avg_temp":      sd.get("avg_temp", 28.0),
        "tariff":        sd.get("tariff", 2.0),
        "currency":      sd.get("currency", "GHS"),
        "symbol":        sd.get("symbol", "GHS "),
        "cost_usd_kwp":  sd.get("cost_usd_kwp", 850),
        "fx_usd":        float(sd.get("fx_usd", 12.0) or 12.0),
        "system_type":   system_type,
        "phase":         "single",     # _run_project_design overrides from the peak load
        "voltage":       48,
        "autonomy":      int(autonomy or 1),
        "chemistry":     chemistry,
        "building_type": "Residential",
        # Provenance, carried on the project itself so that opening it in the ordinary
        # project UI still says where it came from.
        "from_enterprise_programme": True,
        "loads":         loads,
    }
    return initial_data, loads


def build_standard_design(*, user_id: int, project_name: str, initial_data: dict,
                          loads: list[dict], app=None) -> dict:
    """Create a SolarPro project and run the app's standard design engine over it.

    Input:  the owning user, a project name, the seed produced by standard_seed().
    Output: {"project_kind", "project_id", "kwp", "boq", "summary"}.
    Raises: EngineError.

    NOTE ON THE PLAN LIMIT. web_app._bc_create_and_design refuses to create a project when
    the user is at their plan's project cap. This does NOT apply that check, on purpose: an
    enterprise programme's reference design is not a personal project against a personal
    quota, and refusing to design a Ministry's 400-school rollout because the operator's
    free plan allows one project would be an absurdity. Enterprise access is gated by the
    programme module's own RBAC, which is the control that actually belongs here.
    """
    app = app or _app()

    with app.get_db() as c:
        cur = c.execute(
            "INSERT INTO projects (user_id, name, data_json) VALUES (?,?,?) RETURNING id",
            (user_id, project_name[:200], json.dumps(initial_data)),
        )
        row = cur.fetchone()
        project_id = int(row[0]) if row else 0
    if project_id <= 0:
        raise EngineError("the design project could not be created")

    # Re-load through get_project so the engine runs against the SAME data shape the rest of
    # the app persists -- this is exactly what _bc_create_and_design does, and departing from
    # it would mean the programme's designs differ subtly from every other design in the app.
    proj = app.get_project(project_id)
    data = (proj.get("data") if proj else None) or initial_data
    app._run_project_design(project_id, data, loads)

    proj = app.get_project(project_id) or {}
    data = proj.get("data") or {}
    results = data.get("results") or {}

    return {
        "project_kind": "standard",
        "project_id":   project_id,
        "kwp":          _num(results.get("pv_kw")),
        # THE SHAPE IS THE ENGINE'S, TRANSLATED ONCE, HERE.
        # calc_boq returns a LIST of rows keyed desc/qty/unit/total_r/amount. The generation
        # -station engine returns something else again. Normalising both to {"items": [...]}
        # at this boundary is what lets everything downstream -- the scaled quantities, the
        # procurement total, the programme report -- read ONE shape and never branch on which
        # engine produced it. A per-callsite translation would drift, and the first symptom
        # would be a BOQ table with empty cells in a document a sponsor is reading.
        "boq":          {"items": _normalise_boq(results.get("boq_rows"))},
        "summary":      _standard_summary(data, results),
    }


def _normalise_boq(rows) -> list[dict]:
    """web_app's BOQ rows -> the module's common line shape.

    calc_boq's row: {no, desc, spec, qty, unit, basic, total_r, amount}
      total_r -- the marked-up unit rate (what a site actually pays per unit)
      amount  -- qty x total_r (what a site actually pays for the line)
    """
    out: list[dict] = []
    for row in (rows or []):
        if not isinstance(row, dict):
            continue
        out.append({
            "description": row.get("desc"),
            "spec":        row.get("spec"),
            "unit":        row.get("unit") or "No.",
            "qty":         _num(row.get("qty")),
            "rate":        _num(row.get("total_r")),
            "amount":      _num(row.get("amount")),
        })
    return out


def _standard_summary(data: dict, results: dict) -> dict:
    """The handful of numbers the programme's reports quote. Read once, frozen forever.

    The keys are the ENGINE's keys (inv_kw, bat_kwh, boq_grand, economics.total_local) --
    not what a reasonable person would guess they are called. Guessing them silently yields
    None, which renders as an empty cell rather than as an error, and an empty cell in a
    funding document is a number nobody notices is missing.
    """
    econ = results.get("economics") or {}
    return {
        "design_path":   "standard",
        "system_type":   data.get("system_type"),
        "phase":         data.get("phase"),
        "pv_kw":         _num(results.get("pv_kw")),
        "num_panels":    _num(results.get("num_panels")),
        "panel_wp":      _num(results.get("panel_wp")),
        "battery_kwh":   _num(results.get("bat_kwh")),
        "inverter_kw":   _num(results.get("inv_kw")),
        "daily_kwh":     _num(results.get("daily_kwh")),
        "currency":      econ.get("currency") or data.get("currency"),
        # The BOQ grand total, in local currency -- the number a site actually costs, and
        # therefore the number the programme's funding requirement is a multiple of.
        "total_cost":    _num(results.get("boq_grand") or econ.get("total_local")),
        "payback_years": _num(econ.get("payback")),
        "annual_kwh":    _num(econ.get("annual_kwh")),
    }


# ---------------------------------------------------------------------------
# the generation-station path -- one utility-scale plant
# ---------------------------------------------------------------------------


def build_generation_station_design(*, user_id: int, project_name: str, kwp: float,
                                    country: str, region: str, currency: str = "GHS",
                                    psh_daily: float | None = None,
                                    app=None, ci=None) -> dict:
    """Register a Generation Station project and run ITS sizing engine and ITS BOQ.

    Input:  the owning user, a project name, the plant's nameplate kWp, its location.
    Output: {"project_kind", "project_id", "kwp", "boq", "summary"}.
    Raises: EngineError.

    "use the whole generation station design approach with all the outputs" -- so this does
    NOT run the standard engine with a big number in it. It creates a row in
    `capital_investment_projects`, which is what makes the project open in the Generation
    Station's own 14-step wizard, with its own SLD, its own digital twin, its own 15 AI
    agents and its own 18 report PDFs. All of that is already built and already live; the
    programme's job is to hand the plant to it, not to duplicate it.

    Slice 7 runs the SIZING (size_utility_pv) and the SOLAR-FARM BOQ (_ci_solar_boq_rows)
    here so that a programme has a costed plant the moment it is created. The wizard's later
    steps refine it in place -- they are not bypassed, they are pre-seeded.
    """
    app = app or _app()
    ci = ci or _ci()

    try:
        kwp = float(kwp)
    except (TypeError, ValueError):
        raise EngineError("the plant capacity must be a number") from None
    if not math.isfinite(kwp) or kwp <= 0:
        raise EngineError("the plant capacity must be greater than zero")

    sd = app.get_solar_data(country, region) or {}
    psh = float(psh_daily or sd.get("psh", 5.4) or 5.4)

    sizing = ci.size_utility_pv(kwp=kwp, psh_daily=psh)
    if not isinstance(sizing, dict) or sizing.get("error"):
        raise EngineError(
            "the generation-station sizing engine refused this plant: "
            + str((sizing or {}).get("error", "unknown reason"))
        )

    rows = ci._ci_solar_boq_rows(sizing) or []

    with app.get_db() as c:
        cur = c.execute(
            "INSERT INTO capital_investment_projects "
            "(user_id, project_name, country, region, description, project_status, "
            " target_kwp, currency) VALUES (?,?,?,?,?,?,?,?) RETURNING id",
            (user_id, project_name[:200], country, region,
             "Programme reference design (enterprise programme module).",
             "concept", kwp, currency),
        )
        row = cur.fetchone()
        project_id = int(row[0]) if row else 0
    if project_id <= 0:
        raise EngineError("the generation-station project could not be created")

    # _ci_solar_boq_rows returns {bill_no, bill_name, section, service_code, desc, unit,
    # qty, basic} -- CLOSE to calc_boq's row but not the same: `basic` is the unit rate and
    # there is no pre-computed amount. Normalised here, through the same door, so the two
    # engines converge on one shape before anything downstream reads them.
    items = [
        {"description": r.get("desc"), "spec": r.get("section"),
         "unit": r.get("unit") or "No.", "qty": _num(r.get("qty")),
         "rate": _num(r.get("basic")),
         "amount": (_num(r.get("qty")) or 0) * (_num(r.get("basic")) or 0)}
        for r in rows if isinstance(r, dict)
    ]
    total_cost = sum(i["amount"] for i in items) or None

    return {
        "project_kind": "generation_station",
        "project_id":   project_id,
        "kwp":          kwp,
        # Shaped like the standard path's BOQ ({"items": [...]}) so that everything
        # downstream -- the scaled quantities, the programme report, the funding total --
        # reads ONE shape and does not branch on the design path. The scaling arithmetic
        # must not care which engine produced the bill of quantities.
        "boq":          {"items": items},
        "summary": {
            "design_path":     "generation_station",
            "pv_kw":           kwp,
            "num_panels":      _num(sizing.get("n_modules")),
            "module_wp":       _num(sizing.get("module_wp")),
            "inverter_kw":     _num(sizing.get("inverter_ac_kw")),
            "annual_gen_mwh":  _num(sizing.get("annual_generation_mwh")),
            "n_inverters":     _num(sizing.get("n_central_inverters")),
            "currency":        currency,
            "psh_daily":       psh,
            # The plant's own cost. NOT multiplied by the number of offtakers -- a
            # programme building a power station builds ONE power station.
            "total_cost":      total_cost,
        },
    }


# ---------------------------------------------------------------------------
# instantiating the reference design at ONE site
# ---------------------------------------------------------------------------


def clone_standard_to_site(*, user_id: int, project_name: str, reference_project_id: int,
                           site: dict, conn=None, app=None) -> int:
    """Instantiate the reference design at one location. Returns the new project id.

    Input:  the owning user, the site's project name, the reference project to copy,
            `site` -- {code, name, latitude, longitude, community, district, region}, and
            optionally `conn` -- a connection the CALLER already holds.
    Output: the new project's id.
    Raises: EngineError.

    PASS `conn` FROM THE DRAINER. It is not an optimisation; it is the difference between
    working and not. The drainer holds a connection open across the whole chunk, and this
    function used to open a SECOND one -- on SQLite that is `database is locked` on every
    single site, and on Postgres it is two connections contending for the same rows with a
    real chance of deadlock. Sharing the caller's connection also means the copied project
    and the link row that points at it land in ONE transaction: a crash halfway can no
    longer leave a project that no programme knows about.

    (build_standard_design cannot do this -- web_app's design engine reaches for its own
    connection internally -- which is exactly why create_reference_design runs it BEFORE
    opening a transaction. Read the ordering comment there.)

    THIS IS A COPY, NOT A RE-DESIGN, AND THAT IS THE WHOLE POINT.
    The owner: "the BOQ and everything is the same for each site". So the reference project's
    data -- loads, array, battery, inverter, cables, BOQ, economics -- is copied VERBATIM.
    The engine is not re-run. Only the site's IDENTITY is overwritten: its name, its code,
    its coordinates.

    It would be very easy, and quite wrong, to re-run the design here with the site's own
    shading factor and its own field-assessment numbers. That produces N different BOQs --
    the exact thing the owner ruled out -- and it does so silently, so that the programme's
    procurement total no longer equals (reference BOQ x number of sites) and nobody notices
    until the containers arrive. A site whose survey disagrees with the reference is a
    VARIANCE. rollout.record_site_variance stores it against the link row, where an engineer
    has to look at it. It is never quietly designed around.
    """
    app = app or _app()

    data = _read_project_data(app, reference_project_id, conn)
    if data is None:
        raise EngineError("the reference design's project could not be read")

    data["enterprise_site"] = {
        "code":      site.get("code"),
        "name":      site.get("name"),
        "community": site.get("community"),
        "district":  site.get("district"),
    }
    data["from_enterprise_programme"] = True
    data["reference_project_id"] = int(reference_project_id)
    if site.get("latitude") is not None:
        data["latitude"] = site["latitude"]
    if site.get("longitude") is not None:
        data["longitude"] = site["longitude"]
    if site.get("region"):
        data["region"] = site["region"]

    project_id = _insert_project(app, conn, user_id, project_name, data)
    if project_id <= 0:
        raise EngineError("the site project could not be created")
    return project_id


def _read_project_data(app, project_id: int, conn) -> dict | None:
    """The project's data dict, read on the CALLER's connection when there is one.

    app.get_project() opens its own connection. That is fine from a request, and fatal from
    inside a drain that already holds one -- see clone_standard_to_site's docstring.
    """
    if conn is None:
        proj = app.get_project(project_id)
        return dict(proj.get("data") or {}) if proj else None

    row = conn.execute(
        "SELECT data_json FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        return None
    try:
        data = json.loads(row[0] or "{}")
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else {}


def _insert_project(app, conn, user_id: int, project_name: str, data: dict) -> int:
    """One INSERT, on the caller's connection if it gave us one."""
    sql = "INSERT INTO projects (user_id, name, data_json) VALUES (?,?,?) RETURNING id"
    params = (user_id, project_name[:200], json.dumps(data))

    if conn is not None:
        row = conn.execute(sql, params).fetchone()
        return int(row[0]) if row else 0

    with app.get_db() as c:
        row = c.execute(sql, params).fetchone()
        return int(row[0]) if row else 0


def _num(value):
    """A float, or None. Never a NaN, never a string, never an exception.

    Every number in this module ends up in a jsonb snapshot that a report reads back months
    later. A NaN survives json.dumps in Python and then fails to parse as JSON in Postgres;
    a string "12.5" compares as greater than 100. Both are quiet, and both are found in the
    report rather than in the code.
    """
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None
