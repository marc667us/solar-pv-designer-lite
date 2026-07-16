"""Enterprise Solar Programme -- ONE design, scaled to every site (rebuild, slice 7).

WHAT THE OWNER ASKED FOR
------------------------
    "the programme is a collection of multiple residential or commercial buildings
     benefiting from the sponsorship of a government or bank or other institution"
    "when you are in planning the programme must open into standard or generation station
     design; the output report is the plans of the programme for the number of programme
     sites"
    "the implementation must be built up from the design but scaled to all programme sites"
    "the BOQ and everything is the same for each site"
    "the reusable components for a residential programme will be standard design, including
     check my bill, field assessment to be applied at each location, shading and funding --
     this time funding will be sought by the programme for all the locations"

THE SHAPE THAT FOLLOWS FROM THAT
--------------------------------
    Planning        -> ONE reference design       (create_reference_design)
                       built by the approved template's design path, on the app's own
                       engines. Not N designs. One.
    Engineering     -> that design is APPROVED     (approve_reference_design)   [C04]
    Implementation  -> it is INSTANTIATED at each qualified site  (queue_rollout / drain)
                       Same BOQ. Same equipment. Same everything. Only the address changes.
    Funding         -> reference cost x number of sites, ONCE, at programme level
                       (funding_requirement) -- never per building.

THE ONE PLACE THIS GETS SUBTLE, SAID OUT LOUD
---------------------------------------------
The owner asked for BOTH "field assessment and shading at each location" AND "the BOQ is
the same for each site". Taken naively those contradict: if each site's shading re-sizes its
own array, you get N different BOQs.

They are reconciled, and only reconciled, like this: the reference BOQ is what gets BUILT.
A location whose survey disagrees with it produces a VARIANCE -- recorded against that
site's link row (record_site_variance), visible to engineering, and never applied silently.
That keeps the sponsor's arithmetic true (programme cost really is reference x N) while
still capturing the thing a surveyor actually found. The alternative -- quietly designing
around each site's shading -- breaks the sponsor's total and nobody notices until the
containers land.

WHY THERE IS A JOB TABLE AND NOT A LOOP
---------------------------------------
A 400-school rollout is 400 project designs. Doing that inside one HTTP request against
gunicorn's 120s timeout, on Render's free tier, is not slow -- it is a 502 with a
half-generated programme behind it. So rollout QUEUES (enterprise_jobs, migration 027) and a
drainer works the queue in bounded chunks. Supervisor R1 settled what the drainer is: there
is no worker process and there cannot be one (Render's free tier caps this account at ONE
instance; a second service was already refused on 2026-07-10). It is a GitHub-Actions cron
calling an authenticated admin endpoint.

Which forces the rule that the rest of this module is built around:

    EVERY GUARD IS RE-CHECKED ON THE WORKER PATH.

A guard that lives in the route is a guard the drainer skips. C02 (qualified beneficiary),
C03 (approved template) and C13 (tenant scope) are therefore checked when the job is queued
AND again for every single site as it is generated -- because a site can be un-qualified, and
a template can be superseded, in the minutes or hours between the two.
"""

from __future__ import annotations

import json
import math

from . import beneficiaries, engines, gates, rbac, templates, txn
from .constants import DESIGN_PATH_CODES
from .rev4_phases import DEFAULT_PHASE_CODE, PHASE_SEQ
from .gates import EnterpriseGateError

# Design may not begin before Planning. The owner's lifecycle says the programme "opens
# into" design when it reaches Planning -- so a programme still in Initiation has, by
# definition, not yet decided what it is building.
#
# ASKED OF THE PHASE, NOT OF A "STAGE". This used to index into LIFECYCLE_STAGES and compare
# against "S2_PLANNING" -- the old 16-phase model grouped its phases into five stages because
# sixteen of them were unreadable otherwise. Revision 4 has six phases and no stages, so the
# rule is now stated as what it always meant: the phase after Initiation is Planning, and
# design opens there.
_DESIGN_FROM_SEQ = PHASE_SEQ[DEFAULT_PHASE_CODE] + 1

# How many sites one drain pass will generate. Each site is a full design pass plus two
# inserts; 25 keeps a drain comfortably inside a 120s request even when the standard engine
# is doing real work, and the cron simply comes back for the rest.
DRAIN_CHUNK = 25

# The rollout must not be queued against a register nobody has finished qualifying. This is
# not a performance cap -- it is the ceiling on how much can go wrong in one click.
MAX_ROLLOUT_SITES = 5000


class RolloutError(EnterpriseGateError):
    """A rollout rule was broken. Carries a control code, so a route can 404 a C13."""


# ---------------------------------------------------------------------------
# schema (SQLite mirror of migration 029 -- Postgres owns the real thing)
# ---------------------------------------------------------------------------

_SQLITE_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS enterprise_reference_designs (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id           TEXT NOT NULL,
        programme_id        INTEGER NOT NULL,
        template_version_id INTEGER NOT NULL,
        design_path         TEXT NOT NULL,
        project_kind        TEXT NOT NULL,
        project_id          INTEGER NOT NULL,
        status              TEXT NOT NULL DEFAULT 'Draft',
        kwp                 REAL,
        boq_json            TEXT NOT NULL DEFAULT '{}',
        summary_json        TEXT NOT NULL DEFAULT '{}',
        approved_by_user_id INTEGER,
        approved_at         TEXT,
        created_by_user_id  INTEGER,
        created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id, programme_id)
            REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id, template_version_id)
            REFERENCES enterprise_template_versions (tenant_id, id),
        UNIQUE (tenant_id, id),
        CONSTRAINT ck_ent_refdesign_path CHECK (design_path IN
            ('standard', 'generation_station')),
        CONSTRAINT ck_ent_refdesign_status CHECK (status IN
            ('Draft', 'Engineering Approved', 'Superseded'))
    )
    """,
    # The partial unique index IS the "one live design per programme" rule. SQLite supports
    # partial indexes, so the mirror can carry the real constraint rather than a weaker
    # lookalike -- a test suite that cannot reproduce production's constraints is a test
    # suite that green-lights what production will reject.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_refdesign_current "
    "  ON enterprise_reference_designs (tenant_id, programme_id) "
    "  WHERE status <> 'Superseded'",
    "CREATE INDEX IF NOT EXISTS ix_ent_refdesign_programme "
    "  ON enterprise_reference_designs (tenant_id, programme_id, status)",
    # ONE ACTIVE ROLLOUT PER PROGRAMME. See queue_rollout: the application's look-first is a
    # courtesy, THIS is the control. Mirrored here so the unit suite exercises the same
    # constraint production has, rather than a weaker lookalike that lets the race through.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_job_active "
    "  ON enterprise_jobs (tenant_id, programme_id, job_type) "
    "  WHERE status IN ('Queued','Running')",
]

# The two columns migration 029 ADDs to a table slice 5 already created. On SQLite the table
# may already exist WITHOUT them (a developer's solar.db from before this slice), and
# CREATE TABLE IF NOT EXISTS will not widen it -- that is the exact schema-drift trap that
# has bitten this project before. So they are added by inspection, not by hope.
_LINK_COLUMNS = [
    ("reference_design_id", "INTEGER"),
    ("site_variance_json", "TEXT NOT NULL DEFAULT '{}'"),
]


def ensure_schema(c) -> None:
    """Create the slice-7 table on SQLite. No-op on Postgres (migration 029 owns it)."""
    if txn.is_postgres():
        return
    for stmt in _SQLITE_SCHEMA:
        c.execute(stmt)

    have = {r[1] for r in c.execute(
        "PRAGMA table_info(enterprise_project_links)").fetchall()}
    for name, decl in _LINK_COLUMNS:
        if name not in have:
            c.execute(
                f"ALTER TABLE enterprise_project_links ADD COLUMN {name} {decl}")


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------


def _load_programme(c, tenant_id: str, programme_id: int) -> dict:
    """The programme, tenant-scoped. C13 -> the routes turn this into a 404."""
    row = c.execute(
        "SELECT id, code, name, description, current_phase_code, status, country, "
        "       target_beneficiaries "
        "  FROM enterprise_programme_registry WHERE tenant_id=? AND id=?",
        (tenant_id, programme_id),
    ).fetchone()
    if row is None:
        raise RolloutError("C13", "no such programme in this organisation")
    keys = ["id", "code", "name", "description", "current_phase_code", "status",
            "country", "target_beneficiaries"]
    return dict(zip(keys, row))


def _require_planning_or_later(programme: dict) -> None:
    """The design opens at Planning. Before that there is nothing to design.

    Raises RolloutError("PLANNING") when the programme is still in Initiation.
    """
    seq = PHASE_SEQ.get(programme["current_phase_code"])
    if seq is None:
        # A hold or terminal pseudo-state (SUSPENDED, CLOSED, ...) has no sequence number, and
        # neither has an unknown phase. Both refuse, and refusing is right: a suspended
        # programme has no business starting a design either.
        raise RolloutError(
            "PLANNING", "this programme is not in a phase that can open a design"
        )
    if seq < _DESIGN_FROM_SEQ:
        raise RolloutError(
            "PLANNING",
            "the programme is still in Initiation. A programme opens into its design at "
            "the Planning phase -- move it to Planning first.",
        )


def _decode(raw) -> dict:
    """jsonb (Postgres, already a dict) or TEXT (SQLite) -> dict. Never raises."""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        out = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return out if isinstance(out, dict) else {}


_DESIGN_COLUMNS = (
    "id, programme_id, template_version_id, design_path, project_kind, project_id, "
    "status, kwp, boq_json, summary_json, approved_by_user_id, approved_at, "
    "created_by_user_id, created_at"
)


def _design_row(row) -> dict:
    keys = ["id", "programme_id", "template_version_id", "design_path", "project_kind",
            "project_id", "status", "kwp", "boq", "summary", "approved_by_user_id",
            "approved_at", "created_by_user_id", "created_at"]
    out = dict(zip(keys, row))
    out["boq"] = _decode(out["boq"])
    out["summary"] = _decode(out["summary"])
    out["approved"] = out["status"] == "Engineering Approved"
    return out


def current_design(c, tenant_id: str, programme_id: int) -> dict | None:
    """The programme's live reference design, or None. Superseded revisions are excluded."""
    row = c.execute(
        f"SELECT {_DESIGN_COLUMNS} FROM enterprise_reference_designs "
        " WHERE tenant_id=? AND programme_id=? AND status <> 'Superseded'",
        (tenant_id, programme_id),
    ).fetchone()
    return _design_row(row) if row else None


def get_design(c, tenant_id: str, design_id: int) -> dict:
    """One reference design, tenant-scoped. Raises RolloutError(C13) -> 404."""
    row = c.execute(
        f"SELECT {_DESIGN_COLUMNS} FROM enterprise_reference_designs "
        " WHERE tenant_id=? AND id=?",
        (tenant_id, design_id),
    ).fetchone()
    if row is None:
        raise RolloutError("C13", "no such design in this organisation")
    return _design_row(row)


def design_options(c, tenant_id: str, programme_id: int) -> list[dict]:
    """The approved template versions this programme may design from.

    Output: [{version_id, template_id, template_name, version_no, status, design_path,
              capacities, system_configuration}]

    Only GENERATIVE versions (Approved / Published) are offered, because only those may
    build anything (C03). Offering a Draft in the dropdown and refusing it on submit is a
    form that lies to the person filling it in.

    A version whose parameters carry no design_path is SKIPPED rather than defaulted. The
    design path decides which engine runs against every site in the programme; guessing it
    would be guessing the most consequential field on the form.
    """
    rows = c.execute(
        "SELECT v.id, t.id, t.name, v.version_no, v.status, v.parameters_json "
        "  FROM enterprise_template_versions v "
        "  JOIN enterprise_programme_templates t "
        "    ON t.tenant_id = v.tenant_id AND t.id = v.template_id "
        " WHERE v.tenant_id = ? "
        "   AND v.status IN ('Approved','Published') "
        "   AND (t.programme_id = ? OR t.programme_id IS NULL) "
        " ORDER BY t.name, v.version_no DESC",
        (tenant_id, programme_id),
    ).fetchall()

    out: list[dict] = []
    for vid, tid, tname, vno, status, params in rows:
        p = _decode(params)
        path = p.get("design_path")
        if path not in DESIGN_PATH_CODES:
            continue
        out.append({
            "version_id":           int(vid),
            "template_id":          int(tid),
            "template_name":        tname,
            "version_no":           int(vno),
            "status":               status,
            "design_path":          path,
            "capacities":           list(p.get("standard_pv_capacities_kw") or []),
            "system_configuration": p.get("system_configuration") or "grid_tied",
            "parameters":           p,
        })
    return out


def _load_template_version(c, tenant_id: str, programme_id: int,
                           template_version_id: int) -> dict:
    """The version, checked for C03 AND for belonging to THIS programme.

    C03 alone is not enough. An Approved version belonging to a DIFFERENT programme in the
    same tenant is approved -- it is simply approved for something else, and building this
    programme's 400 schools from another programme's clinic template would pass every gate
    and produce 400 wrong buildings.
    """
    gates.require_approved_template_version(c, tenant_id, template_version_id)

    row = c.execute(
        "SELECT v.parameters_json, t.programme_id "
        "  FROM enterprise_template_versions v "
        "  JOIN enterprise_programme_templates t "
        "    ON t.tenant_id = v.tenant_id AND t.id = v.template_id "
        " WHERE v.tenant_id=? AND v.id=?",
        (tenant_id, template_version_id),
    ).fetchone()
    if row is None:
        raise RolloutError("C13", "no such template version in this organisation")

    params, owner_programme = _decode(row[0]), row[1]
    if owner_programme is not None and int(owner_programme) != int(programme_id):
        raise RolloutError(
            "C03",
            "that template belongs to a different programme. A programme may only build "
            "from its own template, or from one shared across the organisation.",
        )

    path = params.get("design_path")
    if path not in DESIGN_PATH_CODES:
        raise RolloutError(
            "C03",
            "this template version does not say whether it is a Standard or a Generation "
            "Station design. Open a new draft, choose a design path, and approve it.",
        )
    params["design_path"] = path
    return params


# ---------------------------------------------------------------------------
# THE ONE DESIGN
# ---------------------------------------------------------------------------


def create_reference_design(c, tenant_id: str, user_id: int, programme_id: int, *,
                            template_version_id: int,
                            monthly_kwh: float | None = None,
                            design_kwp: float | None = None,
                            region: str = "",
                            audit=None, engine=None) -> dict:
    """Build the programme's ONE design -- the thing every site will be.

    Input:  connection, tenant, the acting user, the programme.
            template_version_id -- the APPROVED template that decides the design path.
            monthly_kwh         -- standard path: the typical building's monthly consumption
                                   (Check-My-Bill's own basis).
            design_kwp          -- generation-station path: the plant's nameplate capacity.
            region              -- optional; defaults to the programme's country default.
    Output: the reference design dict.
    Raises: RolloutError, EnterprisePermissionError, engines.EngineError.

    ORDERING MATTERS AND IS NOT INCIDENTAL.
    The design engine takes its OWN database connection (web_app.get_db()). Running it while
    holding this module's transaction open would put two connections in contention for the
    same rows -- on Postgres that is a lock wait, and in the wrong interleaving a deadlock.
    So the sequence is strictly:

        1. read + guard          (no transaction held)
        2. run the engine        (no transaction held -- it takes its own)
        3. open a transaction, record the design, write the audit row  (C12)

    A crash between 2 and 3 leaves an orphan project in `projects` and no reference design.
    That is the RIGHT failure: an unreferenced project is inert and visible, whereas a
    reference design pointing at a project that was never built would send the rollout to
    copy something that does not exist.
    """
    # PROGRAMME-SCOPED, not tenant-wide (Codex slice-7, HIGH). The screen already decides
    # what to render with `has_permission(..., programme_id=...)`, so a role granted only on
    # THIS programme sees the button. Enforcing tenant-wide here would 403 that same click --
    # a button that is visible and refuses is worse than one that was never shown.
    rbac.require_permission(c, tenant_id, user_id, "design.generate",
                            programme_id=programme_id)
    programme = _load_programme(c, tenant_id, programme_id)
    _require_planning_or_later(programme)

    if current_design(c, tenant_id, programme_id) is not None:
        raise RolloutError(
            "DESIGN",
            "this programme already has a reference design. Supersede it before creating "
            "another -- two live designs means two answers to 'what are we building'.",
        )

    params = _load_template_version(c, tenant_id, programme_id, template_version_id)
    path = params["design_path"]
    engine = engine or engines

    country = programme.get("country") or "Ghana"
    region = (region or "").strip() or _default_region(country)
    name = f"{programme['code']} -- reference design"

    if path == "standard":
        initial, loads = engine.standard_seed(
            monthly_kwh=monthly_kwh,
            country=country,
            region=region,
            system_configuration=params.get("system_configuration") or "grid_tied",
        )
        built = engine.build_standard_design(
            user_id=user_id, project_name=name, initial_data=initial, loads=loads)
    else:
        kwp = _require_offered_capacity(design_kwp, params)
        built = engine.build_generation_station_design(
            user_id=user_id, project_name=name, kwp=kwp,
            country=country, region=region)

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        cur = c.execute(
            "INSERT INTO enterprise_reference_designs "
            " (tenant_id, programme_id, template_version_id, design_path, project_kind, "
            "  project_id, status, kwp, boq_json, summary_json, created_by_user_id) "
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (tenant_id, programme_id, template_version_id, path,
             built["project_kind"], built["project_id"], "Draft",
             built.get("kwp"), json.dumps(built.get("boq") or {}),
             json.dumps(built.get("summary") or {}), user_id),
        )
        design_id = txn.inserted_id(c, cur)

        gates.require_audit_written(
            audit("ENTERPRISE_REFERENCE_DESIGN_CREATED", user_id=user_id,
                  tenant_id=tenant_id,
                  details={"programme_id": programme_id, "design_id": design_id,
                           "design_path": path,
                           "template_version_id": template_version_id,
                           "project_kind": built["project_kind"],
                           "project_id": built["project_id"],
                           "kwp": built.get("kwp")}),
            "ENTERPRISE_REFERENCE_DESIGN_CREATED",
        )

    return get_design(c, tenant_id, design_id)


def _require_offered_capacity(design_kwp, params: dict) -> float:
    """The plant size must be one the APPROVED template offered.

    A free-text kWp on this form would mean the number that sizes the whole programme -- the
    one the sponsor is asked to fund -- never passed through anybody's approval. The template
    lists the standard capacities; the design picks one of them.
    """
    offered = [float(v) for v in (params.get("standard_pv_capacities_kw") or [])]
    if not offered:
        raise RolloutError(
            "C03", "this template offers no standard capacities to build from")
    try:
        kwp = float(design_kwp)
    except (TypeError, ValueError):
        raise RolloutError("DESIGN", "choose a plant capacity") from None
    if not math.isfinite(kwp) or not any(abs(kwp - o) < 1e-9 for o in offered):
        raise RolloutError(
            "C03",
            "that capacity is not one this template offers ("
            + ", ".join(f"{o:g} kWp" for o in offered) + ")",
        )
    return kwp


def _default_region(country: str) -> str:
    """The platform's home-market default. Ghana / Greater Accra, same as Check-My-Bill."""
    return "Greater Accra" if country == "Ghana" else ""


def approve_reference_design(c, tenant_id: str, user_id: int, design_id: int, *,
                             audit=None) -> dict:
    """C04 -- no design is issued without engineering approval.

    Input:  connection, tenant, the approving engineer, the design.
    Output: the approved design.
    Raises: RolloutError, EnterprisePermissionError.

    C11: the approver is a HUMAN with `engineering.approve`. Nothing about this decision is
    automatable, and the audit row carries the person's user id, not a service account's.

    This is the gate the whole rollout hangs on: a Draft design generates nothing. It is
    also the LAST point at which an error is cheap -- after this, it is replicated N times.
    """
    # Read first (tenant-scoped -> C13), THEN scope the permission to the design's own
    # programme. The other order cannot work: until the row is read there is no programme to
    # scope to, and a tenant-wide check would refuse a programme-scoped engineering manager.
    design = get_design(c, tenant_id, design_id)
    rbac.require_permission(c, tenant_id, user_id, "engineering.approve",
                            programme_id=design["programme_id"])

    if design["status"] == "Superseded":
        raise RolloutError("C04", "this design has been superseded")
    if design["approved"]:
        return design  # idempotent: a second click is not an error

    gates.require_human_approval_actor(user_id)

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        cur = c.execute(
            "UPDATE enterprise_reference_designs "
            "   SET status='Engineering Approved', approved_by_user_id=?, "
            "       approved_at=CURRENT_TIMESTAMP "
            " WHERE tenant_id=? AND id=? AND status='Draft'",
            (user_id, tenant_id, design_id),
        )
        if int(getattr(cur, "rowcount", 0) or 0) != 1:
            # Somebody else moved it between the read and the write. Refuse rather than
            # report success on a row we did not change.
            raise RolloutError(
                "C04", "the design changed while you were approving it; reload and retry")

        gates.require_audit_written(
            audit("ENTERPRISE_DESIGN_APPROVED", user_id=user_id, tenant_id=tenant_id,
                  details={"design_id": design_id,
                           "programme_id": design["programme_id"],
                           "design_path": design["design_path"],
                           "project_id": design["project_id"],
                           "kwp": design["kwp"]}),
            "ENTERPRISE_DESIGN_APPROVED",
        )

    return get_design(c, tenant_id, design_id)


def supersede_reference_design(c, tenant_id: str, user_id: int, design_id: int, *,
                               audit=None) -> None:
    """Retire a design so a revised one can be issued.

    The sites already generated from it KEEP pointing at it -- that is what makes the record
    of what each site was actually built to survive a revision. Superseding is not deletion.
    """
    design = get_design(c, tenant_id, design_id)
    rbac.require_permission(c, tenant_id, user_id, "engineering.approve",
                            programme_id=design["programme_id"])

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        c.execute(
            "UPDATE enterprise_reference_designs SET status='Superseded' "
            " WHERE tenant_id=? AND id=? AND status <> 'Superseded'",
            (tenant_id, design_id),
        )
        gates.require_audit_written(
            audit("ENTERPRISE_DESIGN_SUPERSEDED", user_id=user_id, tenant_id=tenant_id,
                  details={"design_id": design_id,
                           "programme_id": design["programme_id"]}),
            "ENTERPRISE_DESIGN_SUPERSEDED",
        )


# ---------------------------------------------------------------------------
# SCALING IT TO EVERY SITE
# ---------------------------------------------------------------------------


def rollout_scope(c, tenant_id: str, programme_id: int, design_id: int) -> dict:
    """What a rollout WOULD do, without doing it. The number the operator confirms against.

    Output: {"qualified", "already_generated", "to_generate", "sites": [...]}

    `to_generate` is qualified-minus-already-linked, computed by the DATABASE. Counting a
    truncated page in Python and calling it the rollout size is how a 4000-school programme
    silently rolls out 500 schools.
    """
    qualified = int(c.execute(
        "SELECT COUNT(*) FROM enterprise_beneficiary_register "
        " WHERE tenant_id=? AND programme_id=? "
        "   AND status IN ('Qualified','Template Assigned','Project Generated')",
        (tenant_id, programme_id),
    ).fetchone()[0])

    linked = int(c.execute(
        "SELECT COUNT(*) FROM enterprise_project_links "
        " WHERE tenant_id=? AND programme_id=?",
        (tenant_id, programme_id),
    ).fetchone()[0])

    return {
        "design_id":         design_id,
        "qualified":         qualified,
        "already_generated": linked,
        "to_generate":       max(0, qualified - linked),
    }


def _pending_sites(c, tenant_id: str, programme_id: int, limit: int) -> list[dict]:
    """Qualified beneficiaries with no project yet. The unit of work for one drain pass."""
    rows = c.execute(
        "SELECT b.id FROM enterprise_beneficiary_register b "
        "  LEFT JOIN enterprise_project_links l "
        "         ON l.tenant_id = b.tenant_id AND l.beneficiary_id = b.id "
        " WHERE b.tenant_id=? AND b.programme_id=? "
        "   AND b.status IN ('Qualified','Template Assigned') "
        "   AND l.id IS NULL "
        " ORDER BY b.id LIMIT ?",
        (tenant_id, programme_id, int(limit)),
    ).fetchall()
    return [beneficiaries.get_beneficiary(c, tenant_id, int(r[0])) for r in rows]


def queue_rollout(c, tenant_id: str, user_id: int, programme_id: int, *,
                  design_id: int, audit=None) -> int:
    """Queue the generation of one project per qualified site. Returns the job id.

    Input:  connection, tenant, the acting user, the programme, the APPROVED design.
    Output: the enterprise_jobs id.
    Raises: RolloutError, EnterprisePermissionError.

    This does NOT generate anything. It records the INTENT to generate, and returns. See the
    module docstring: 400 designs do not fit in one HTTP request, and pretending they do
    produces a 502 with a half-built programme behind it.
    """
    rbac.require_permission(c, tenant_id, user_id, "design.generate",
                            programme_id=programme_id)
    _load_programme(c, tenant_id, programme_id)

    design = get_design(c, tenant_id, design_id)
    if int(design["programme_id"]) != int(programme_id):
        raise RolloutError("C13", "that design belongs to a different programme")
    if not design["approved"]:
        raise RolloutError(
            "C04",
            "this design has not been approved by engineering. No design is issued -- let "
            "alone replicated across every site -- until an engineer has signed it off.",
        )

    # C03, re-checked HERE and not merely at design time: a template version can be
    # superseded or archived in the days between designing and rolling out.
    gates.require_approved_template_version(c, tenant_id, design["template_version_id"])

    scope = rollout_scope(c, tenant_id, programme_id, design_id)
    if scope["to_generate"] <= 0:
        raise RolloutError(
            "ROLLOUT",
            "there are no qualified sites left to generate. Qualify some sites first.",
        )
    if scope["to_generate"] > MAX_ROLLOUT_SITES:
        raise RolloutError(
            "ROLLOUT",
            f"{scope['to_generate']} sites exceeds the {MAX_ROLLOUT_SITES}-site cap for a "
            "single rollout.",
        )

    # An already-Running or Queued job for this programme means somebody clicked twice, or
    # two operators clicked at once. Either way a second job would race the first for the
    # same sites -- they would not duplicate (the unique index forbids it) but they would
    # both fight, fail rows, and produce a job record that lies about what happened.
    # ONE ACTIVE ROLLOUT PER PROGRAMME, ENFORCED BY THE DATABASE (Codex slice-7, MED).
    #
    # The SELECT below is a COURTESY -- it produces a sentence a human can act on. It is not
    # the control. Two operators clicking at the same moment each see no existing job and
    # both insert: a check-then-insert is a race, and "the application looked first" is a
    # habit, not a constraint. `ux_ent_job_active` (migration 029) makes the second insert
    # impossible; the catch below turns that collision back into the same sentence.
    existing = c.execute(
        "SELECT id FROM enterprise_jobs "
        " WHERE tenant_id=? AND programme_id=? AND job_type='generate_projects' "
        "   AND status IN ('Queued','Running')",
        (tenant_id, programme_id),
    ).fetchone()
    if existing:
        raise RolloutError(
            "ROLLOUT",
            "a rollout is already queued for this programme. Wait for it to finish.",
        )

    audit = audit or txn.audit_on(c)
    try:
        with txn.atomic(c):
            cur = c.execute(
                "INSERT INTO enterprise_jobs "
                " (tenant_id, programme_id, job_type, status, payload_json, total_items, "
                "  created_by_user_id) VALUES (?,?,?,?,?,?,?)",
                (tenant_id, programme_id, "generate_projects", "Queued",
                 json.dumps({"design_id": int(design_id)}), scope["to_generate"], user_id),
            )
            job_id = txn.inserted_id(c, cur)

            gates.require_audit_written(
                audit("ENTERPRISE_ROLLOUT_QUEUED", user_id=user_id, tenant_id=tenant_id,
                      details={"programme_id": programme_id, "job_id": job_id,
                               "design_id": design_id,
                               "sites_to_generate": scope["to_generate"]}),
                "ENTERPRISE_ROLLOUT_QUEUED",
            )
    except Exception as e:                     # noqa: BLE001
        if _is_integrity_error(e):
            raise RolloutError(
                "ROLLOUT",
                "a rollout is already queued for this programme. Wait for it to finish.",
            ) from e
        raise
    return job_id


def _is_integrity_error(e: Exception) -> bool:
    """A uniqueness collision, on either backend, without importing psycopg2 here.

    sqlite3.IntegrityError and psycopg2.errors.UniqueViolation share no base class, and this
    module must import cleanly with NO Postgres driver installed -- the entire unit suite
    runs that way. So the check is by name, which is ugly and correct; the tidy alternative
    is an import that fails on a developer's machine.
    """
    name = type(e).__name__
    if name in ("IntegrityError", "UniqueViolation"):
        return True
    text = str(e).lower()
    return "unique" in text and "constraint" in text


def get_job(c, tenant_id: str, job_id: int) -> dict:
    """One job, tenant-scoped."""
    row = c.execute(
        "SELECT id, programme_id, job_type, status, payload_json, total_items, done_items, "
        "       failed_items, last_error, attempts, created_at, started_at, finished_at "
        "  FROM enterprise_jobs WHERE tenant_id=? AND id=?",
        (tenant_id, job_id),
    ).fetchone()
    if row is None:
        raise RolloutError("C13", "no such job in this organisation")
    keys = ["id", "programme_id", "job_type", "status", "payload", "total_items",
            "done_items", "failed_items", "last_error", "attempts", "created_at",
            "started_at", "finished_at"]
    out = dict(zip(keys, row))
    out["payload"] = _decode(out["payload"])
    return out


def latest_job(c, tenant_id: str, programme_id: int) -> dict | None:
    """The most recent rollout job for a programme, for the status panel."""
    row = c.execute(
        "SELECT id FROM enterprise_jobs "
        " WHERE tenant_id=? AND programme_id=? AND job_type='generate_projects' "
        " ORDER BY id DESC LIMIT 1",
        (tenant_id, programme_id),
    ).fetchone()
    return get_job(c, tenant_id, int(row[0])) if row else None


def drain_job(c, job_id: int, *, chunk: int = DRAIN_CHUNK, audit=None,
              engine=None) -> dict:
    """Generate up to `chunk` site projects for one queued job. Returns its progress.

    Input:  connection, the job id, how many sites to do in this pass.
    Output: {"job_id", "status", "done", "failed", "total", "generated_now"}.

    THIS IS THE WORKER PATH, AND IT RE-CHECKS EVERY GUARD.
    The route that queued this job checked C02, C03, C04 and C13. That was minutes or hours
    ago. In between, a site can be un-qualified, a template can be superseded, and a design
    can be withdrawn. So all four are checked AGAIN here -- per job for the design and the
    template, and PER SITE for qualification. A guard that lives only in a route is a guard
    the drainer skips, and bulk generation is exactly where skipping one does the most harm.

    IT IS ALSO IDEMPOTENT. The cron will retry -- GitHub's free scheduler is best-effort and
    both drops fires and doubles them. A retry that builds a second project for the same
    school is a duplicate somebody has to find and delete by hand, so the per-site work sits
    behind `ux_ent_project_link_beneficiary` (one link per beneficiary, enforced by the
    database) and a collision is treated as "already done", not as an error.

    ONE BAD SITE MUST NOT KILL THE BATCH. Each site is wrapped in its own SAVEPOINT: on
    Postgres a failed statement poisons the entire transaction, so without one, a single
    duplicate or a single bad row would take down the other 24 and roll back the lot.
    (That is not hypothetical -- it is exactly the defect the Supervisor found in the
    beneficiary importer, and this is the same shape of loop.)
    """
    engine = engine or engines
    audit = audit or txn.audit_on(c)

    row = c.execute(
        "SELECT tenant_id, programme_id, payload_json, status, total_items, done_items, "
        "       failed_items FROM enterprise_jobs WHERE id=? AND job_type='generate_projects'",
        (job_id,),
    ).fetchone()
    if row is None:
        raise RolloutError("ROLLOUT", "no such rollout job")

    tenant_id, programme_id, payload, status = row[0], int(row[1]), _decode(row[2]), row[3]
    if status in ("Completed", "Failed", "Cancelled"):
        return {"job_id": job_id, "status": status, "done": int(row[5]),
                "failed": int(row[6]), "total": int(row[4]), "generated_now": 0}

    design_id = int(payload.get("design_id") or 0)
    design = get_design(c, tenant_id, design_id)          # C13
    programme = _load_programme(c, tenant_id, programme_id)

    # --- the guards, re-checked on the worker path ---------------------------
    if not design["approved"]:
        return _fail_job(c, job_id, audit, tenant_id, programme_id,
                         "the reference design is no longer approved")
    try:
        gates.require_approved_template_version(       # C03
            c, tenant_id, design["template_version_id"])
    except EnterpriseGateError as e:
        return _fail_job(c, job_id, audit, tenant_id, programme_id, str(e))

    c.execute(
        "UPDATE enterprise_jobs SET status='Running', attempts = attempts + 1, "
        "       started_at = COALESCE(started_at, CURRENT_TIMESTAMP) WHERE id=?",
        (job_id,),
    )

    sites = _pending_sites(c, tenant_id, programme_id, chunk)
    generated = 0
    failed = 0
    last_error: str | None = None

    for site in sites:
        try:
            gates.require_qualified_beneficiary(c, tenant_id, site["id"])   # C02, per site
        except EnterpriseGateError as e:
            failed += 1
            last_error = f"{site.get('code')}: {e}"
            continue

        # ONE SAVEPOINT PER SITE, AND THE PROJECT IS INSIDE IT.
        #
        # Two reasons, and both were learned the hard way in this module:
        #
        #  * On Postgres a single failed INSERT poisons the WHOLE transaction. Without a
        #    savepoint, one duplicate site would take down the other 24 in the chunk and the
        #    statement that tried to record the failure would raise as well. (Same shape of
        #    loop, same defect, as the beneficiary importer.)
        #
        #  * The copied project and the link row that points at it belong together. Insert
        #    the project outside the savepoint and a failure on the link leaves a project no
        #    programme knows about -- invisible, and indistinguishable from a real one.
        try:
            with txn.atomic(c):
                project_id = _instantiate(c, tenant_id, programme, design, site,
                                          user_id=int(design["created_by_user_id"] or 0),
                                          engine=engine)
                cur = c.execute(
                    "INSERT INTO enterprise_project_links "
                    " (tenant_id, programme_id, beneficiary_id, template_version_id, "
                    "  reference_design_id, project_kind, project_id, status, "
                    "  generated_by_user_id) VALUES (?,?,?,?,?,?,?,?,?)",
                    (tenant_id, programme_id, site["id"], design["template_version_id"],
                     design_id, design["project_kind"], project_id, "Project Generated",
                     design["created_by_user_id"]),
                )
                link_id = txn.inserted_id(c, cur)
                c.execute(
                    "UPDATE enterprise_beneficiary_register "
                    "   SET status='Project Generated' WHERE tenant_id=? AND id=?",
                    (tenant_id, site["id"]),
                )
                gates.require_audit_written(
                    audit("ENTERPRISE_SITE_PROJECT_GENERATED",
                          user_id=design["created_by_user_id"], tenant_id=tenant_id,
                          details={"programme_id": programme_id, "job_id": job_id,
                                   "design_id": design_id, "link_id": link_id,
                                   "beneficiary_id": site["id"],
                                   "beneficiary_code": site.get("code"),
                                   "project_kind": design["project_kind"],
                                   "project_id": project_id}),
                    "ENTERPRISE_SITE_PROJECT_GENERATED",
                )
            generated += 1
        except Exception as e:                 # noqa: BLE001 -- one site, not the batch
            # The design engine refused, or the unique index fired (this site already has a
            # project -- a retry), or the audit refused. Either way: not this site's
            # project, not this batch's problem. But it IS recorded -- see the status logic
            # below for why a silently swallowed failure is the dangerous kind.
            failed += 1
            last_error = f"{site.get('code')}: {type(e).__name__}: {e}"

    done = int(row[5]) + generated
    total_failed = int(row[6]) + failed
    remaining = rollout_scope(c, tenant_id, programme_id, design_id)["to_generate"]

    # THE STATUS MUST TELL THE TRUTH, AND "Completed" IS A STRONG CLAIM.
    #
    # An earlier version said `Completed if generated == 0` -- reasoning that a pass which
    # built nothing has nothing left to do. That was exactly backwards. A pass that offered
    # 25 sites and built none of them has not finished; it has FAILED, and calling it
    # Completed hides the only signal anybody would have acted on. (It is how a locked
    # database turned into a green rollout with no projects in it.)
    #
    #   nothing was pending          -> Completed. There was genuinely nothing to do.
    #   built some, none left        -> Completed.
    #   built some, more to come     -> Queued. The cron comes back.
    #   offered sites, built NONE    -> Failed, with the reason. Do not retry forever, and
    #                                   do not pretend.
    if not sites:
        new_status = "Completed"
    elif generated > 0:
        new_status = "Completed" if remaining <= 0 else "Queued"
    else:
        new_status = "Failed"

    c.execute(
        "UPDATE enterprise_jobs SET status=?, done_items=?, failed_items=?, last_error=?, "
        "       finished_at = CASE WHEN ? IN ('Completed','Failed') THEN CURRENT_TIMESTAMP "
        "                          ELSE finished_at END "
        " WHERE id=?",
        (new_status, done, total_failed, (last_error or "")[:500] or None,
         new_status, job_id),
    )
    if new_status == "Failed":
        audit("ENTERPRISE_ROLLOUT_FAILED", user_id=design["created_by_user_id"],
              tenant_id=tenant_id,
              details={"programme_id": programme_id, "job_id": job_id,
                       "failed": total_failed, "reason": last_error})
    if new_status == "Completed":
        audit("ENTERPRISE_ROLLOUT_COMPLETED", user_id=design["created_by_user_id"],
              tenant_id=tenant_id,
              details={"programme_id": programme_id, "job_id": job_id,
                       "generated": done, "failed": total_failed})
    if hasattr(c, "commit"):
        c.commit()

    return {"job_id": job_id, "status": new_status, "done": done,
            "failed": total_failed, "total": int(row[4]), "generated_now": generated,
            "error": last_error}


def _fail_job(c, job_id: int, audit, tenant_id: str, programme_id: int,
              reason: str) -> dict:
    """Stop a job that can no longer legally do what it was queued to do."""
    c.execute(
        "UPDATE enterprise_jobs SET status='Failed', last_error=?, "
        "       finished_at=CURRENT_TIMESTAMP WHERE id=?",
        (reason[:500], job_id),
    )
    audit("ENTERPRISE_ROLLOUT_FAILED", user_id=None, tenant_id=tenant_id,
          details={"programme_id": programme_id, "job_id": job_id, "reason": reason})
    if hasattr(c, "commit"):
        c.commit()
    return {"job_id": job_id, "status": "Failed", "done": 0, "failed": 0,
            "total": 0, "generated_now": 0, "error": reason}


def _instantiate(c, tenant_id: str, programme: dict, design: dict, site: dict, *,
                 user_id: int, engine) -> int:
    """The reference design, at ONE address. Returns the new project id.

    A COPY. Not a re-design. See engines.clone_standard_to_site and the module docstring:
    "the BOQ and everything is the same for each site" is only true if nothing here re-runs
    the engine with this site's own numbers.

    THE GENERATION-STATION PATH DOES NOT INSTANTIATE. A generation station is ONE plant --
    the programme builds it once, not once per beneficiary. Its beneficiaries are the
    offtakers who receive its power, and cloning the plant per offtaker would claim the
    programme is building N power stations when it is building one. So the rollout for a
    generation-station programme links every qualified site to the SAME plant project.
    """
    if design["design_path"] == "generation_station":
        return int(design["project_id"])

    label = site.get("name") or site.get("code") or f"Site {site['id']}"
    project_name = f"{programme['code']} -- {site.get('code') or ''} {label}".strip()
    return engine.clone_standard_to_site(
        user_id=user_id,
        project_name=project_name,
        reference_project_id=int(design["project_id"]),
        # THE DRAINER'S OWN CONNECTION. Not passing it means the clone opens a SECOND
        # connection while this one is held -- `database is locked` on SQLite, a lock wait
        # on Postgres, and every site in the chunk failing. It also puts the copied project
        # and its link row in one transaction, so a crash cannot orphan a project.
        conn=c,
        site={
            "code":      site.get("code"),
            "name":      site.get("name"),
            "community": site.get("community"),
            "district":  site.get("district"),
            "region":    site.get("region"),
            "latitude":  site.get("latitude"),
            "longitude": site.get("longitude"),
        },
    )


# ---------------------------------------------------------------------------
# the per-location survey -- recorded, never silently designed around
# ---------------------------------------------------------------------------


def record_site_variance(c, tenant_id: str, user_id: int, programme_id: int,
                         link_id: int, *,
                         shading_factor: float | None = None,
                         field_notes: str = "", audit=None) -> None:
    """The field assessment and shading survey for ONE location.

    Input:  connection, tenant, the surveyor, the PROGRAMME, the site's project link.
            shading_factor -- 1.0 = no shading; below 1.0 loses yield.
    Output: none.
    Raises: RolloutError, EnterprisePermissionError.

    THE PROGRAMME ID IS PART OF THE KEY, NOT DECORATION (Codex slice-7, MED). Scoping only
    by tenant would let a POST made under programme A mutate a site belonging to programme B
    in the same organisation -- and a Ministry running a schools programme AND a clinics
    programme is one tenant, whose surveyors are routinely scoped to one of them. The URL
    says which programme this act belongs to; the WHERE clause must agree with the URL, or
    the URL is decoration too.

    IT IS STORED, AND IT DOES NOT RE-SIZE THE ARRAY. That is the whole design decision of
    this slice, and it deserves to be said where somebody will read it before changing it:

    The owner asked for a field assessment and a shading survey at each location, AND for
    the BOQ to be the same at every site. Both, at once, are only possible if the survey is
    EVIDENCE rather than an INPUT. If site 214's shading quietly shrank site 214's array,
    the programme would hold 400 different BOQs, the sponsor's total would no longer be
    (reference x 400), and nobody would find out until procurement.

    So a bad survey result raises a flag an engineer must look at. It never reaches for the
    calculator on its own.
    """
    rbac.require_permission(c, tenant_id, user_id, "qualification.score",
                            programme_id=programme_id)

    row = c.execute(
        "SELECT id, programme_id, reference_design_id, site_variance_json "
        "  FROM enterprise_project_links "
        " WHERE tenant_id=? AND programme_id=? AND id=?",
        (tenant_id, programme_id, link_id),
    ).fetchone()
    if row is None:
        # C13. A link in another organisation, a link in another PROGRAMME, and a link that
        # never existed are all the same answer -- and the route turns all three into a 404.
        raise RolloutError("C13", "no such site project in this programme")

    variance = _decode(row[3])
    flags: list[str] = []

    if shading_factor is not None:
        try:
            factor = float(shading_factor)
        except (TypeError, ValueError):
            raise RolloutError("SURVEY", "the shading factor must be a number") from None
        if not math.isfinite(factor) or not (0.0 < factor <= 1.0):
            raise RolloutError(
                "SURVEY", "the shading factor must be greater than 0 and at most 1.0")
        variance["shading_factor"] = factor
        if factor < 0.95:
            flags.append(
                f"shading loses {(1 - factor) * 100:.0f}% of this site's yield; the "
                "reference design assumes none. Engineering must decide whether this site "
                "needs a variation."
            )

    if field_notes.strip():
        variance["field_notes"] = field_notes.strip()[:4000]
    variance["flags"] = flags
    variance["surveyed_by_user_id"] = user_id

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        c.execute(
            "UPDATE enterprise_project_links SET site_variance_json=? "
            " WHERE tenant_id=? AND programme_id=? AND id=?",
            (json.dumps(variance), tenant_id, programme_id, link_id),
        )
        gates.require_audit_written(
            audit("ENTERPRISE_SITE_SURVEY_RECORDED", user_id=user_id, tenant_id=tenant_id,
                  details={"link_id": link_id, "programme_id": row[1],
                           "shading_factor": variance.get("shading_factor"),
                           "flags": flags}),
            "ENTERPRISE_SITE_SURVEY_RECORDED",
        )


def site_projects(c, tenant_id: str, programme_id: int, limit: int = 500) -> list[dict]:
    """Every generated site project in the programme, with its survey variance."""
    rows = c.execute(
        "SELECT l.id, l.beneficiary_id, b.code, b.name, l.project_kind, l.project_id, "
        "       l.status, l.site_variance_json "
        "  FROM enterprise_project_links l "
        "  JOIN enterprise_beneficiary_register b "
        "    ON b.tenant_id = l.tenant_id AND b.id = l.beneficiary_id "
        " WHERE l.tenant_id=? AND l.programme_id=? "
        " ORDER BY l.id LIMIT ?",
        (tenant_id, programme_id, int(limit)),
    ).fetchall()
    out = []
    for r in rows:
        variance = _decode(r[7])
        out.append({
            "link_id":        int(r[0]),
            "beneficiary_id": int(r[1]),
            "code":           r[2],
            "name":           r[3],
            "project_kind":   r[4],
            "project_id":     int(r[5]),
            "status":         r[6],
            "variance":       variance,
            "flags":          variance.get("flags") or [],
        })
    return out


# ---------------------------------------------------------------------------
# FUNDING -- sought ONCE, by the programme, for all the locations
# ---------------------------------------------------------------------------


def funding_requirement(c, tenant_id: str, programme_id: int) -> dict:
    """What the programme must raise, in total, for every site at once.

    Output: {"design_path", "sites", "unit_cost", "currency", "total", "kwp_total"}

    "this time funding will be sought by the programme for all the locations" -- so this is
    a PROGRAMME number, not a per-building one. It is (the reference design's cost) x (the
    number of sites), and it is that simple ONLY because the BOQ is the same at every site.
    The moment somebody lets a site re-size itself, this arithmetic silently stops being
    true -- which is the strongest practical argument for the variance rule above.

    A generation station is ONE plant: its cost is not multiplied by its beneficiaries.
    """
    design = current_design(c, tenant_id, programme_id)
    if design is None:
        return {"design_path": None, "sites": 0, "unit_cost": None, "currency": None,
                "total": None, "kwp_total": None}

    summary = design["summary"] or {}
    unit_cost = summary.get("total_cost")
    currency = summary.get("currency")

    scope = rollout_scope(c, tenant_id, programme_id, design["id"])
    sites = max(scope["qualified"], scope["already_generated"])

    if design["design_path"] == "generation_station":
        # One plant. Its funding requirement is its own cost, full stop.
        return {"design_path": "generation_station", "sites": sites,
                "unit_cost": unit_cost, "currency": currency,
                "total": unit_cost, "kwp_total": design["kwp"]}

    total = (float(unit_cost) * sites) if (unit_cost and sites) else None
    kwp_total = (float(design["kwp"]) * sites) if (design["kwp"] and sites) else None
    return {"design_path": "standard", "sites": sites, "unit_cost": unit_cost,
            "currency": currency, "total": total, "kwp_total": kwp_total}


def scaled_boq(c, tenant_id: str, programme_id: int) -> dict:
    """The reference BOQ, multiplied out across every site. The procurement number.

    Output: {"sites", "lines": [{description, unit, unit_qty, total_qty, ...}], ...}

    C15 in spirit: every aggregated quantity here traces to exactly one line of exactly one
    BOQ -- the reference design's. That traceability is not a nicety; it is what lets a
    procurement officer answer "where did 12,000 mounting rails come from" with an answer
    rather than a shrug.
    """
    design = current_design(c, tenant_id, programme_id)
    if design is None:
        return {"sites": 0, "lines": [], "design_path": None}

    scope = rollout_scope(c, tenant_id, programme_id, design["id"])
    sites = max(scope["qualified"], scope["already_generated"]) or 0
    # A generation station is built once, so its quantities are NOT multiplied.
    multiplier = 1 if design["design_path"] == "generation_station" else sites

    boq = design["boq"] or {}
    items = boq.get("items") if isinstance(boq, dict) else None
    lines = []
    for item in (items or []):
        if not isinstance(item, dict):
            continue
        qty = _f(item.get("qty") if "qty" in item else item.get("quantity"))
        lines.append({
            "description": item.get("description") or item.get("item") or item.get("name"),
            "unit":        item.get("unit") or "No.",
            "unit_qty":    qty,
            "total_qty":   (qty * multiplier) if qty is not None else None,
            "unit_rate":   _f(item.get("rate") or item.get("unit_rate")),
        })
    for line in lines:
        rate, total_qty = line["unit_rate"], line["total_qty"]
        line["total_cost"] = (rate * total_qty) if (rate and total_qty) else None

    return {"sites": sites, "multiplier": multiplier, "lines": lines,
            "design_path": design["design_path"], "design_id": design["id"]}


def _f(value):
    """A finite float, or None. Same reasoning as engines._num."""
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None
