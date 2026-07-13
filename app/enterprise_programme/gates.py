"""Enterprise Solar Programme -- stage gates and the 15 management controls (slice 2).

WHAT THIS IS
------------
The part of the module that says NO.

Doc 3 gives 14 stage gates and 15 "key programme management controls". Both are
phrased as prohibitions ("No beneficiary becomes a project without qualification").
This file turns each one into a predicate that a service MUST call before acting.

TWO RULES THAT SHAPE EVERYTHING HERE
------------------------------------
1. FAIL CLOSED. Every guard's default answer is NO. A guard whose evidence table does
   not exist yet (because its slice has not shipped) does not "pass for now" -- it
   raises. Release 1 delivers a complete lifecycle through Gate 9; Gates 10-14 are
   seeded and visibly BLOCKED. A lifecycle with a hole in the middle is worse than a
   shorter one that cannot be bypassed (Supervisor adjudication, doc 09).

2. GUARDS LIVE IN SERVICES, NOT ROUTES. The route decorator is a fast fail, not the
   boundary. The queue drainer and internal calls never touch a route, and project
   generation lives exactly there -- so the guard is called again inside the worker
   path. A guard you can skip by POSTing directly to the job table is not a guard.

WHY C01 IS NOT CIRCULAR
-----------------------
Gate 1's approving authority IS the Programme Sponsor, and Gate 1's exit condition is
"sponsor approval exists". Read naively that is a loop. It is not: the programme must
NAME a sponsor before Gate 1 can even be evaluated (that is the gate's own predicate),
and the sponsor's approval OF Gate 1 is what satisfies C01 for every later phase. So:
name a sponsor -> sponsor approves G01 -> programme may leave Concept. Nothing else
opens that door.
"""

from __future__ import annotations

from .constants import (
    CONTROLS,
    GATE_CODES,
    GATE_PREREQUISITE_GATES,
    GATES,
    BENEFICIARY_STATUSES_APPROVED,
    GATES_DEFERRED_BEYOND_RELEASE_1,
    TEMPLATE_STATUSES_GENERATIVE,
)


class EnterpriseGateError(Exception):
    """A control or gate predicate refused the action.

    Callers should turn this into a 409 Conflict (the request was well-formed and the
    caller was authorised -- the programme is simply not in a state where the action is
    legal). Deliberately distinct from EnterprisePermissionError (403), because
    conflating "you may not" with "not yet" makes both impossible to debug.
    """

    def __init__(self, control: str, message: str):
        self.control = control
        super().__init__(f"{control}: {message}")


class GateBlockedError(EnterpriseGateError):
    """The gate exists and is seeded, but its evidence slice has not shipped.

    Distinct from a plain refusal so the UI can say "not available in this release"
    rather than "you failed a check", and so tests can assert deferred gates are
    blocked rather than silently passable.
    """


# --- gate authority ---------------------------------------------------------

_GATE_AUTHORITY: dict[str, str] = {g[0]: g[3] for g in GATES}


def gate_authority(gate_code: str) -> str:
    """The role code that alone may approve this gate.

    Input:  gate code, e.g. 'G01'.
    Output: role code, e.g. 'programme_sponsor'.
    Raises: EnterpriseGateError on an unknown gate (fail closed -- an unknown gate must
            never resolve to "anyone may approve it").
    """
    if gate_code not in _GATE_AUTHORITY:
        raise EnterpriseGateError("GATE", f"unknown gate {gate_code!r}")
    return _GATE_AUTHORITY[gate_code]


def _deferred(fn):
    """Mark a guard whose evidence slice has not shipped, so it FAILS CLOSED.

    Input:  a guard function.
    Output: the same function, tagged `is_deferred = True`.

    The tag is the single source of truth for "is this control live yet". control_summary()
    reads it, so the compliance dashboard cannot drift out of step with the code: when the
    slice ships and you delete this decorator, the dashboard starts reporting the control
    as enforced on the same commit. Nothing else to remember to update.
    """
    fn.is_deferred = True
    return fn


# --- the 15 controls (doc 3) ------------------------------------------------
# Each function name here is named in constants.CONTROLS, and a test asserts the
# mapping is total. A control cannot be quietly dropped by deleting its guard.


def require_approved_sponsor(c, tenant_id: str, programme_id: int) -> None:
    """C01 -- no programme proceeds without an approved sponsor.

    Input:  connection, tenant id, programme id.
    Output: none (returns quietly when satisfied).
    Raises: EnterpriseGateError.

    Satisfied by an APPROVED Gate 1 whose approver actually held the sponsor role at
    the time (approve_gate enforces the role; this reads the result). Merely naming a
    sponsor is not approval.
    """
    row = c.execute(
        "SELECT status FROM enterprise_stage_gates "
        " WHERE tenant_id=? AND programme_id=? AND gate_code='G01'",
        (tenant_id, programme_id),
    ).fetchone()
    if not row or row[0] != "Approved":
        raise EnterpriseGateError(
            "C01", "the programme sponsor has not approved Gate 1 (Programme Concept)"
        )


def require_qualified_beneficiary(c, tenant_id: str, beneficiary_id: int) -> None:
    """C02 -- no beneficiary becomes a project without qualification. LIVE since slice 6.

    Input:  connection, tenant id, beneficiary id.
    Output: none.
    Raises: EnterpriseGateError("C02") unless the site has been DECIDED Qualified.

    Two conditions, and BOTH are checked, because either alone can be true while the site is
    not actually qualified:

      1. The beneficiary's status is Qualified (or past it -- a site with a template already
         assigned, or a project already generated, was qualified to get there).
      2. A scorecard exists carrying decision='Qualified'.

    Belt and braces on purpose. The status is what everything else reads and it is one UPDATE
    away from being wrong; the scorecard is the evidence that a human with
    `qualification.approve` actually looked. C02 is the control that stops money being spent
    on a site nobody assessed, so it asks for the evidence, not just the label.

    Wired into project_generation in slice 7 on BOTH the queue path and the worker path -- a
    guard that lives only in the route is a guard the queue drainer skips.
    """
    row = c.execute(
        "SELECT b.status, q.decision "
        "  FROM enterprise_beneficiary_register b "
        "  LEFT JOIN enterprise_site_qualifications q "
        "         ON q.tenant_id = b.tenant_id AND q.beneficiary_id = b.id "
        " WHERE b.tenant_id=? AND b.id=?",
        (tenant_id, beneficiary_id),
    ).fetchone()
    if row is None:
        # C13, not C02: a site in another tenant is not "unqualified", it is not ours to
        # discuss. The routes turn this into a 404.
        raise EnterpriseGateError("C13", "no such beneficiary in this organisation")

    status, decision = row[0], row[1]
    if status not in ("Qualified", "Template Assigned", "Project Generated"):
        raise EnterpriseGateError(
            "C02",
            f"this site is {status}: no beneficiary becomes a project without qualification",
        )
    if decision != "Qualified":
        raise EnterpriseGateError(
            "C02",
            "this site is marked Qualified but carries no qualification decision to show "
            "for it",
        )


def require_approved_template_version(c, tenant_id: str, template_version_id: int) -> None:
    """C03 -- no project is generated without an approved template.

    Input:  connection, tenant id, template version id.
    Output: none (returns quietly when the version may generate).
    Raises: EnterpriseGateError.

    LIVE since slice 4. Status must be Approved or Published
    (constants.TEMPLATE_STATUSES_GENERATIVE). A Draft never builds anything: it is by
    definition a standard nobody has certified, and a project generated from one would
    carry a specification that the Technical Director never saw.

    The tenant id is in the WHERE clause, so a version in ANOTHER organisation reads as
    absent rather than as unapproved. Both refuse; only one of them tells a stranger that
    somebody else's template exists.

    Slice 7 calls this on BOTH the request path and the worker path. A guard that lives
    only in a route is a guard the queue drainer skips, and bulk generation is exactly
    where an unapproved template would do the most damage.
    """
    row = c.execute(
        "SELECT status FROM enterprise_template_versions WHERE tenant_id=? AND id=?",
        (tenant_id, template_version_id),
    ).fetchone()
    if row is None:
        raise EnterpriseGateError(
            "C03", "no such template version in this organisation"
        )
    if row[0] not in TEMPLATE_STATUSES_GENERATIVE:
        raise EnterpriseGateError(
            "C03",
            f"template version is {row[0]}; only an Approved or Published version may "
            "generate a project",
        )


def require_engineering_approval(c, tenant_id: str, project_link_id: int) -> None:
    """C04 -- no design is issued without engineering approval. LIVE since slice 7.

    Input:  connection, tenant id, project link id.
    Output: none.
    Raises: EnterpriseGateError("C04") unless the design this site was built from has been
            approved by an engineer; EnterpriseGateError("C13") if the link is not ours.

    THE APPROVAL IS ASKED OF THE DESIGN, NOT OF THE SITE, and that is the point of the whole
    slice. A programme holds ONE design and every site IS that design -- so approving it once
    approves all of them, and there is exactly one place where an engineer's judgement is
    applied to what gets built. Asking for a signature per site would not be 400 times more
    rigorous; it would be one signature, repeated 400 times by a tired person, which is less
    rigorous.

    A site whose survey disagrees with the approved design does not fail this gate -- it
    carries a VARIANCE (rollout.record_site_variance) that an engineer must resolve. The
    distinction is deliberate: an unapproved design is a governance failure, whereas an
    awkward site is engineering work.
    """
    row = c.execute(
        "SELECT d.status "
        "  FROM enterprise_project_links l "
        "  LEFT JOIN enterprise_reference_designs d "
        "         ON d.tenant_id = l.tenant_id AND d.id = l.reference_design_id "
        " WHERE l.tenant_id=? AND l.id=?",
        (tenant_id, project_link_id),
    ).fetchone()
    if row is None:
        raise EnterpriseGateError("C13", "no such site project in this organisation")
    if row[0] is None:
        raise EnterpriseGateError(
            "C04",
            "this site project is not linked to a reference design, so there is no design "
            "for an engineer to have approved",
        )
    if row[0] != "Engineering Approved":
        raise EnterpriseGateError(
            "C04",
            f"the reference design this site was built from is {row[0]}: no design is "
            "issued without engineering approval",
        )


@_deferred
def require_approved_boq_snapshot(c, tenant_id: str, project_link_ids) -> None:
    """C05 -- no procurement package is created without an approved BOQ.

    Input:  connection, tenant id, iterable of project link ids.
    Output: none.
    Raises: GateBlockedError until slice 8 (BOQ approval + procurement) ships.
    """
    raise GateBlockedError(
        "C05", "BOQ approval ships in slice 8; no BOQ snapshot can be approved yet"
    )


@_deferred
def require_executed_contract(c, tenant_id: str, epc_package_id: int) -> None:
    """C06 -- no contractor mobilises without contract approval.

    Input:  connection, tenant id, EPC package id.
    Output: none.
    Raises: GateBlockedError -- contracts are Release 2.
    """
    raise GateBlockedError("C06", "EPC/FIDIC contracts are Release 2")


@_deferred
def require_site_readiness_approval(c, tenant_id: str, project_link_id: int) -> None:
    """C07 -- no installation begins without site-readiness approval.

    Input:  connection, tenant id, project link id.
    Output: none.
    Raises: GateBlockedError -- construction is Release 3.
    """
    raise GateBlockedError("C07", "construction is Release 3")


@_deferred
def require_required_tests_passed(c, tenant_id: str, project_link_id: int) -> None:
    """C08 -- no system is commissioned without required tests.

    Input:  connection, tenant id, project link id.
    Output: none.
    Raises: GateBlockedError -- commissioning is Release 3.
    """
    raise GateBlockedError("C08", "commissioning is Release 3")


@_deferred
def require_handover_dossier_complete(c, tenant_id: str, project_link_id: int) -> None:
    """C09 -- no asset is handed over without complete documentation.

    Input:  connection, tenant id, project link id.
    Output: none.
    Raises: GateBlockedError -- handover is Release 3.
    """
    raise GateBlockedError("C09", "handover is Release 3")


@_deferred
def require_kpi_data_source(c, tenant_id: str, kpi_definition_id: int) -> None:
    """C10 -- no operational KPI is reported without a defined data source.

    Input:  connection, tenant id, KPI definition id.
    Output: none.
    Raises: GateBlockedError -- O&M telemetry is Release 4.

    This one matters commercially: a dashboard that invents a number a donor then
    reports to a ministry is worse than a dashboard with a gap in it.
    """
    raise GateBlockedError("C10", "O&M KPI telemetry is Release 4")


def require_human_approval_actor(decision_by_user_id, ai_recommendation_id=None) -> None:
    """C11 -- no AI recommendation becomes an approval automatically.

    Input:  the deciding user's id (may be None -- that is the case we are catching),
            optional AI recommendation id offered as supporting evidence.
    Output: none.
    Raises: EnterpriseGateError.

    An AI recommendation may be ATTACHED to an approval as evidence. It can never BE
    the approver. There is no service account, no automation flag, and no "system"
    pseudo-user that satisfies this -- a human id or nothing.
    """
    if not decision_by_user_id:
        raise EnterpriseGateError(
            "C11",
            "an approval requires a human decision-maker; an AI recommendation may be "
            "attached as evidence but can never be the approver",
        )


def require_audit_written(audit_ok: bool, action: str = "") -> None:
    """C12 -- every material action must be auditable.

    Input:  the boolean returned by app.security.audit.write_audit_event, action name.
    Output: none.
    Raises: EnterpriseGateError -- and the caller MUST let that abort its transaction.

    write_audit_event is non-raising by contract (it returns False on failure). That is
    right for a login page and wrong here: a gate approval that happened but left no
    trace is exactly the record an auditor asks for and we cannot produce. So the
    material actions in this module treat a failed audit write as a failed action and
    roll the whole transition back. Losing the transition is recoverable; losing the
    evidence is not.
    """
    if not audit_ok:
        raise EnterpriseGateError(
            "C12", f"audit write failed for {action or 'action'}; the action was rolled back"
        )


def require_tenant_scope(row, tenant_id: str) -> None:
    """C13 -- every programme record must be tenant-scoped.

    Input:  a fetched row (or None), the caller's ACTIVE tenant id.
    Output: none.
    Raises: EnterpriseGateError.

    Note what this does NOT do: it does not tell the caller whether the row exists.
    A missing row and another tenant's row produce the same error, because
    distinguishing them leaks the existence of other tenants' programmes.
    """
    if row is None:
        raise EnterpriseGateError("C13", "no such programme in this organisation")
    row_tenant = row["tenant_id"] if hasattr(row, "keys") else row[0]
    if str(row_tenant) != str(tenant_id):
        raise EnterpriseGateError("C13", "no such programme in this organisation")


def require_project_traceability(c, tenant_id: str, project_link_id: int) -> None:
    """C14 -- a generated project must retain traceability to its beneficiary+template.

    Input:  connection, tenant id, project link id.
    Output: none.
    Raises: EnterpriseGateError("C14") when any link in the chain is missing; C13 when the
            project link does not belong to this organisation.

    The chain slice 7 built, and the one this walks:

        site project -> reference design -> template version -> programme
                     -> beneficiary

    Most of it is already guaranteed by composite foreign keys in migrations 027 and 029 --
    which is exactly why this guard is worth having rather than redundant. The FKs make the
    chain UNBREAKABLE once written; this asserts it was WRITTEN. A link row inserted by some
    future caller that forgot `reference_design_id` would satisfy every constraint in the
    database and still be untraceable, because a nullable column is nullable.
    """
    row = c.execute(
        "SELECT l.beneficiary_id, l.template_version_id, l.reference_design_id, "
        "       l.project_id, l.programme_id "
        "  FROM enterprise_project_links l WHERE l.tenant_id=? AND l.id=?",
        (tenant_id, project_link_id),
    ).fetchone()
    if row is None:
        raise EnterpriseGateError("C13", "no such site project in this organisation")

    missing = [name for name, value in (
        ("originating beneficiary", row[0]),
        ("template version",        row[1]),
        ("reference design",        row[2]),
        ("design project",          row[3]),
        ("programme",               row[4]),
    ) if value is None]
    if missing:
        raise EnterpriseGateError(
            "C14",
            "this project cannot be traced back to its " + ", ".join(missing),
        )


@_deferred
def require_procurement_source_lines(c, tenant_id: str, package_id: int) -> None:
    """C15 -- every aggregated procurement quantity stays traceable to a source BOQ.

    Input:  connection, tenant id, procurement package id.
    Output: none.
    Raises: GateBlockedError until slice 8 (procurement) ships.
    """
    raise GateBlockedError("C15", "procurement consolidation ships in slice 8")


# The registry the test suite asserts is total against constants.CONTROLS. If you add a
# control to the spec, you add a guard here -- there is no path that lets a control be
# declared and then not enforced.
CONTROL_GUARDS = {
    "C01": require_approved_sponsor,
    "C02": require_qualified_beneficiary,
    "C03": require_approved_template_version,
    "C04": require_engineering_approval,
    "C05": require_approved_boq_snapshot,
    "C06": require_executed_contract,
    "C07": require_site_readiness_approval,
    "C08": require_required_tests_passed,
    "C09": require_handover_dossier_complete,
    "C10": require_kpi_data_source,
    "C11": require_human_approval_actor,
    "C12": require_audit_written,
    "C13": require_tenant_scope,
    "C14": require_project_traceability,
    "C15": require_procurement_source_lines,
}


# --- gate predicates --------------------------------------------------------
# What each gate demands BEFORE its authority is even allowed to approve it.
# Slices 4-9 register their own evidence checks here as they ship; a gate whose
# evidence does not exist yet is BLOCKED, never auto-passed.


def _gate_1_predicate(c, tenant_id: str, programme_id: int) -> None:
    """G01 entry: the programme must name a sponsor (see 'why C01 is not circular')."""
    row = c.execute(
        "SELECT sponsor_user_id FROM enterprise_programme_registry WHERE tenant_id=? AND id=?",
        (tenant_id, programme_id),
    ).fetchone()
    if not row or not row[0]:
        raise EnterpriseGateError(
            "G01", "the programme must name a sponsor before Gate 1 can be approved"
        )


def _requires_document(doc_type: str, gate_code: str, human: str):
    """Build a predicate demanding one document type be registered on the programme.

    Input:  the document type key, the gate it guards, a human-readable name.
    Output: a predicate function (c, tenant_id, programme_id) -> None.

    Doc 3 lists required documents per gate. Registering the document is what the
    module can actually verify; whether its CONTENT is any good is the named
    authority's job -- which is precisely why a human with a specific role has to sign.
    """

    def _predicate(c, tenant_id: str, programme_id: int) -> None:
        row = c.execute(
            "SELECT 1 FROM enterprise_documents "
            " WHERE tenant_id=? AND programme_id=? AND doc_type=? LIMIT 1",
            (tenant_id, programme_id, doc_type),
        ).fetchone()
        if not row:
            raise EnterpriseGateError(
                gate_code, f"required document missing: {human}"
            )

    # The demand is published on the predicate, not buried in this closure, so the rest of
    # the system can ASK a gate what it wants. A test asserts that every doc_type demanded
    # here is one some deliverable can actually produce -- without this attribute that test
    # can only inspect an empty set and passes vacuously, which is how a gate demanding an
    # unwritable document would slip back in unnoticed.
    _predicate.required_doc_type = doc_type          # type: ignore[attr-defined]
    _predicate.gate_code = gate_code                 # type: ignore[attr-defined]

    return _predicate


def _gate_3_predicate(c, tenant_id: str, programme_id: int) -> None:
    """G03 entry: the programme must actually HAVE an approved beneficiary (slice 5).

    Gate 3 is "Beneficiary Register Approval". Before slice 5 the only thing it could check
    was that somebody had registered a document called a beneficiary register -- which is a
    claim about a register, not a register. Now that the register exists, the gate asks for
    the thing itself: at least one beneficiary admitted to the programme (approved out of
    "Beneficiary Registered" and into the qualification queue).

    Merely IMPORTING beneficiaries is not enough, and that is the whole point. A District
    Coordinator can put 4000 rows into the register; a Programme Manager decides which of
    them the programme will actually serve. The gate wants evidence of the second act.
    """
    placeholders = ",".join("?" for _ in BENEFICIARY_STATUSES_APPROVED)
    row = c.execute(
        "SELECT 1 FROM enterprise_beneficiary_register "
        f" WHERE tenant_id=? AND programme_id=? AND status IN ({placeholders}) LIMIT 1",
        tuple([tenant_id, programme_id] + sorted(BENEFICIARY_STATUSES_APPROVED)),
    ).fetchone()
    if not row:
        raise EnterpriseGateError(
            "G03",
            "the beneficiary register is empty of APPROVED sites: import or enter "
            "beneficiaries, then approve at least one into the programme",
        )


def _gate_6_predicate(c, tenant_id: str, programme_id: int) -> None:
    """G06 entry: the programme must actually HAVE an approved standard (slice 4).

    Gate 6 is "Standardisation Approval". Before slice 4 the only thing it could check was
    that somebody had registered a document called a template version pack -- which is a
    claim, not a standard. Now that templates exist, the gate asks for the thing itself: at
    least one template version, on this programme or tenant-wide, in a generative state.

    Tenant-wide templates count. A ministry that standardises "School 50 kW" once and reuses
    it across every programme is doing exactly what a template engine is for; demanding a
    programme-local copy would force a duplicate per programme, which is the drift this
    module exists to prevent.
    """
    row = c.execute(
        "SELECT 1 FROM enterprise_template_versions v "
        "  JOIN enterprise_programme_templates t "
        "    ON t.tenant_id = v.tenant_id AND t.id = v.template_id "
        " WHERE v.tenant_id=? AND v.status IN ('Approved','Published') "
        "   AND (t.programme_id IS NULL OR t.programme_id=?) LIMIT 1",
        (tenant_id, programme_id),
    ).fetchone()
    if not row:
        raise EnterpriseGateError(
            "G06",
            "no approved programme template: at least one template version must be "
            "Approved or Published before standardisation can be signed off",
        )


GATE_PREDICATES = {
    "G01": [_gate_1_predicate, _requires_document("concept_note", "G01", "concept note")],
    "G02": [_requires_document("programme_charter", "G02", "programme charter")],
    "G03": [_gate_3_predicate,
            _requires_document("beneficiary_register", "G03", "beneficiary register")],
    "G04": [_requires_document("business_case", "G04", "business case")],
    "G05": [_requires_document("master_plan", "G05", "programme master plan")],
    "G06": [_gate_6_predicate,
            _requires_document("template_version_pack", "G06", "template version pack")],
    "G07": [_requires_document("funding_strategy", "G07", "funding strategy")],
    "G08": [_requires_document("signed_contract", "G08", "signed contract")],
    "G09": [_requires_document("ifc_package", "G09", "issued-for-construction package")],
}


def evaluate_gate(c, tenant_id: str, programme_id: int, gate_code: str) -> None:
    """Run every predicate registered for a gate.

    Input:  connection, tenant id, programme id, gate code.
    Output: none (returns quietly when the gate may be approved).
    Raises: EnterpriseGateError / GateBlockedError.

    Gates 10-14 are deliberately blocked in Release 1 -- their evidence (construction
    reports, test results, handover dossiers) is produced by slices that have not
    shipped. They are seeded and visible so the lifecycle is honest about where it ends.
    """
    if gate_code not in GATE_CODES:
        raise EnterpriseGateError("GATE", f"unknown gate {gate_code!r}")
    if gate_code in GATES_DEFERRED_BEYOND_RELEASE_1:
        raise GateBlockedError(
            gate_code,
            "this gate is seeded but not yet operable; Release 1 delivers the "
            "lifecycle through Gate 9",
        )

    # Gate prerequisites, checked BEFORE the gate's own evidence. Awarding a contract
    # (G08) before financial close (G07) is not a routing mistake to be caught on some
    # edge -- it is the thing Gate 7 exists to prevent, so the dependency lives on the
    # GATE. With it here, mobilisation transitively requires funding no matter which path
    # a programme takes to reach it.
    for prerequisite in GATE_PREREQUISITE_GATES.get(gate_code, ()):
        row = c.execute(
            "SELECT status FROM enterprise_stage_gates "
            " WHERE tenant_id=? AND programme_id=? AND gate_code=?",
            (tenant_id, programme_id, prerequisite),
        ).fetchone()
        if not row or row[0] != "Approved":
            raise EnterpriseGateError(
                gate_code,
                f"{prerequisite} must be approved before {gate_code} can be",
            )

    for predicate in GATE_PREDICATES.get(gate_code, []):
        predicate(c, tenant_id, programme_id)


def control_summary() -> list[dict]:
    """The 15 controls with their live enforcement status, for the UI and for docs.

    Input:  none.
    Output: list of {code, requirement, guard, enforced_now} dicts.

    `enforced_now` False means the guard exists and FAILS CLOSED -- the action it guards
    is impossible, not unguarded. The dashboard shows this so nobody mistakes a blocked
    control for a satisfied one.

    The flag is DERIVED from the guard itself (the @_deferred marker), not from a second
    hand-maintained list. A separate list would drift the first time a slice shipped
    without updating it, and the dashboard would then either under-report enforcement to
    an auditor or -- far worse -- claim a control is enforced when it is not.
    """
    return [
        {
            "code": code,
            "requirement": requirement,
            "guard": guard_name,
            "enforced_now": not getattr(CONTROL_GUARDS[code], "is_deferred", False),
        }
        for code, requirement, guard_name in CONTROLS
    ]
