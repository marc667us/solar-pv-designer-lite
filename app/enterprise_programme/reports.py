"""Enterprise Solar Programme -- the ADAPTER onto the design-report engine.

THE OWNER'S ASK
---------------
"the app must work to produce report" -- and, on how: "using existing design options".

That second half is the whole design of this module. The Generation Station (capital-
investment) engine ALREADY writes the reports the owner wants: a technical report, a
financial report, an investment memorandum, an implementation plan, a monitoring strategy,
a bankability report, a BOQ, an economic-impact report. `new_capital_investment_routes.
_build_report_markdown` has a branch for every one of them, and it writes them from a REAL
DESIGN -- its sizing, its finance model, its bill of quantities.

So nothing here writes a report. This module RESOLVES a programme to the design it has
already approved, and hands that design to the engine that already exists. It is an adapter,
and it is deliberately thin.

WHY THIS IS NOT THE ACTIVITY PATH
---------------------------------
documents.py writes a document by assembling the lifecycle activities the operator ticked.
That is the right way to produce a governance narrative -- a concept note, a charter -- which
is a statement of intent about a programme that may not have been designed yet.

It is the WRONG way to produce a technical feasibility report. A technical report assembled
from ticked activities would be a document whose engineering content came from prose, while
the actual engineering -- the kWp, the inverter schedule, the BOQ, the cash flow -- sat in a
table nobody read. Eleven of doc 2's Key Outputs are engineering documents
(constants.DELIVERABLE_ENGINE), and for those the design IS the content.

THE PROGRAMME IS NOT THE PROJECT (and this is the subtle part)
--------------------------------------------------------------
The engine writes about ONE project: the programme's reference design. But the deliverable is
a PROGRAMME document -- the ministry is not funding one clinic, it is funding two hundred of
them. So the engine's report is wrapped in a programme header that states the multiplication:
how many sites, the total funding requirement, the scaled BOQ -- and says plainly that the
engineering below is the reference design that is replicated at each site.

Without that header the report would be true and profoundly misleading: a business case
showing the cost of one clinic, presented as the business case for the programme.

AUTHORITY COMES FROM THE PROGRAMME, NOT FROM THE PROJECT
-------------------------------------------------------
The reference design is instantiated as a real `capital_investment_projects` row, owned by
whoever created it. The route helper that normally loads such a row is scoped
`WHERE id=? AND user_id=?` -- the SESSION user. Reusing it here would mean a programme
manager could not read a report from a design their colleague created, which is absurd for a
ministry-scale programme.

So this module loads the project row by id ALONE -- and that is safe precisely because the id
is not user-supplied: it is read off `enterprise_reference_designs`, which is itself
tenant-scoped (C13). The caller's right to be here was already established by rbac against
the PROGRAMME. There is no IDOR: no path lets a caller name a project id.
"""

from __future__ import annotations

from . import rollout
from .constants import DELIVERABLE_ENGINE, DELIVERABLE_INDEX
from .gates import EnterpriseGateError


class ReportError(EnterpriseGateError):
    """The engine could not write this deliverable, and says why."""


def is_engine_written(deliverable_code: str) -> bool:
    """Is this deliverable produced by the design engine rather than by the activity path?"""
    return deliverable_code in DELIVERABLE_ENGINE


def engine_report_key(deliverable_code: str) -> str | None:
    """The CI report key that writes this deliverable, or None."""
    return DELIVERABLE_ENGINE.get(deliverable_code)


def _load_reference_project(c, project_id: int) -> dict:
    """The capital-investment project row behind a programme's reference design.

    Input:  connection, the project id RECORDED ON THE DESIGN (never user-supplied).
    Output: the project row as a dict.
    Raises: ReportError when the row is gone.

    Deliberately NOT scoped by `user_id`. See the module docstring: the caller's authority
    was established against the PROGRAMME, and the id came from a tenant-scoped table, so
    scoping again by the session user would only break colleagues reading each other's work.
    """
    row = c.execute(
        "SELECT * FROM capital_investment_projects WHERE id=?", (project_id,)
    ).fetchone()
    if row is None:
        raise ReportError(
            "REPORT",
            "the programme's reference design points at a project that no longer exists",
        )
    return dict(row)


def _programme_header(programme: dict, design: dict, funding: dict, boq: dict,
                      report_title: str) -> str:
    """The programme context the engine's project-level report cannot know about.

    Input:  the programme facts, its reference design, its funding requirement, its scaled
            BOQ, and the engine's own title for the report.
    Output: a markdown header.

    THIS IS THE HONESTY OF THE WHOLE MODULE. The engine writes about one site. The programme
    buys many. Presenting a one-site cost as a programme business case would be a document
    that is accurate in every particular and wrong in its conclusion -- the most dangerous
    kind. So the multiplication is stated before the reader reaches a single engineering
    figure, and where the app does not know a total it says so rather than implying the
    unit figure is the total.
    """
    sites = funding.get("sites") or 0
    one_plant = design.get("design_path") == "generation_station"
    cur = funding.get("currency") or ""

    def _money(v):
        return f"{cur} {float(v):,.2f}" if v not in (None, "") else "not yet costed"

    md = [
        f"# {report_title}",
        "",
        f"**Programme:** {programme.get('name')} ({programme.get('code')})  ",
        f"**Country:** {programme.get('country') or 'not recorded'}  ",
        f"**Reference design:** {design.get('design_path') or 'standard'} · "
        f"{design.get('kwp') or 'unsized'} kWp · status {design.get('status')}  ",
        "",
        "## Programme scope",
        "",
    ]

    if one_plant:
        # A generation station is ONE plant. Multiplying its cost by its beneficiaries would
        # be a straightforward factual error, and rollout.funding_requirement already refuses
        # to do it -- this text must not contradict that.
        md += [
            "This programme is delivered as a **single generation station** serving "
            f"**{sites:,} beneficiary site(s)**. It is built once: the cost and quantities "
            "below are the cost and quantities of the plant itself, and are **not** "
            "multiplied by the number of beneficiaries.",
            "",
            f"- **Total funding requirement:** {_money(funding.get('total'))}",
            f"- **Installed capacity:** {design.get('kwp') or 'unsized'} kWp",
        ]
    else:
        md += [
            "This programme replicates **one approved reference design** across every "
            f"qualified site. The engineering set out below is that reference design; the "
            f"programme installs it **{sites:,} time(s)**.",
            "",
            f"- **Sites in scope:** {sites:,}",
            f"- **Cost per site:** {_money(funding.get('unit_cost'))}",
            f"- **Total funding requirement:** {_money(funding.get('total'))}",
            f"- **Programme capacity:** "
            + (f"{funding['kwp_total']:,.1f} kWp" if funding.get("kwp_total")
               else "not yet sized"),
        ]

    lines = boq.get("lines") or []
    if lines:
        priced = [ln for ln in lines if ln.get("total_cost") is not None]
        md += [
            "",
            f"- **Programme bill of quantities:** {len(lines):,} line(s)"
            + (f", {len(priced):,} of them priced" if priced else ", none priced yet"),
        ]

    if not sites:
        # Fail LOUD, in the document. A funding requirement of zero sites is not a small
        # number, it is a programme that has not qualified anybody yet -- and a reader must
        # not mistake the reference design's own cost for the programme's.
        md += [
            "",
            "> **No sites are qualified for this programme yet.** The totals above are "
            "therefore incomplete: they cannot be scaled until beneficiaries have been "
            "qualified on the Beneficiaries page. Read the engineering below as the "
            "reference design only.",
        ]

    md += [
        "",
        "---",
        "",
        "*The remainder of this document is written by SolarPro's design engine from the "
        "programme's approved reference design.*",
        "",
    ]
    return "\n".join(md)


def build_engine_document(c, tenant_id: str, programme_id: int,
                          deliverable_code: str) -> tuple[str, str]:
    """Write an engine-backed deliverable from the programme's approved reference design.

    Input:  connection, tenant, programme, the deliverable code.
    Output: (markdown, title).
    Raises: ReportError -- always with an instruction the operator can act on.

    The caller (documents.generate_document) has ALREADY enforced C13 and the permission.
    This does not re-authorise; it resolves and adapts.
    """
    key = engine_report_key(deliverable_code)
    if not key:
        raise ReportError(
            "REPORT",
            f"{deliverable_code} is not written by the design engine",
        )

    design = rollout.current_design(c, tenant_id, programme_id)
    if design is None:
        # FAIL CLOSED, WITH AN INSTRUCTION. The alternative -- quietly falling back to the
        # activity path -- would hand the operator a "Technical feasibility report" written
        # from ticked prose, containing no engineering, and (for the four gate deliverables
        # in this set) open a stage gate on it. A document that looks right and is hollow is
        # exactly what this module exists to abolish.
        raise ReportError(
            "REPORT",
            "this deliverable is written by the design engine from the programme's "
            "reference design, and this programme does not have one yet — create and "
            "approve a reference design on the programme's Design page, then generate it",
        )
    if not design.get("project_id"):
        raise ReportError(
            "REPORT",
            "the programme's reference design has not been instantiated as a project yet, "
            "so there is no engineering for the report to draw on",
        )

    programme = rollout._load_programme(c, tenant_id, programme_id)
    proj = _load_reference_project(c, design["project_id"])
    funding = rollout.funding_requirement(c, tenant_id, programme_id)
    boq = rollout.scaled_boq(c, tenant_id, programme_id)

    # The engine. Imported HERE, not at module import: new_capital_investment_routes is a
    # large route module that pulls in web_app, and importing it at the top of an
    # app.enterprise_programme module would create an import cycle through the app factory.
    try:
        from new_capital_investment_routes import _build_report_markdown
    except Exception as e:                      # pragma: no cover - deployment breakage
        raise ReportError(
            "REPORT", "the design-report engine is unavailable on this server") from e

    # `opp` is a CRM opportunity and belongs to a single project's sales pipeline; a
    # programme has none, and the engine does not read it (it is unused in the builder).
    body, engine_title = _build_report_markdown(key, proj, None, None)

    _phase, deliverable_title = DELIVERABLE_INDEX[deliverable_code]
    header = _programme_header(programme, design, funding, boq, deliverable_title)

    # The engine's markdown opens with its own `# Title`. It is demoted rather than dropped:
    # dropping it would lose the engine's own framing of what the report is, and leaving it
    # as an H1 would give the document two competing titles.
    body = body.replace(f"# {engine_title}", f"## {engine_title}", 1)

    return header + body, deliverable_title
