"""Enterprise Solar Programme -- stage gates and the 15 management controls (slice 2).

WHAT THIS IS
------------
The part of the module that says NO.

Revision 4 gives FIVE stage gates (owner-spec section 38) and doc 3's 15 "key programme
management controls" survive it unchanged. Both are phrased as prohibitions ("No beneficiary
becomes a project without qualification"). This file turns each one into a predicate that a
service MUST call before acting.

TWO RULES THAT SHAPE EVERYTHING HERE
------------------------------------
1. FAIL CLOSED. Every guard's default answer is NO. A guard whose evidence table does
   not exist yet (because its slice has not shipped) does not "pass for now" -- it
   raises, and control_summary() reports it as not-yet-enforced rather than satisfied.
   A control that quietly passes is worse than one that visibly blocks.

2. GUARDS LIVE IN SERVICES, NOT ROUTES. The route decorator is a fast fail, not the
   boundary. The queue drainer and internal calls never touch a route, and project
   generation lives exactly there -- so the guard is called again inside the worker
   path. A guard you can skip by POSTing directly to the job table is not a guard.

WHY C01 IS NOT CIRCULAR
-----------------------
The Initiation gate's approving authority IS the Programme Sponsor, and C01's exit condition
is "sponsor approval exists". Read naively that is a loop. It is not: the programme must
NAME a sponsor before the gate can even be evaluated (that is the gate's own predicate),
and the sponsor's approval OF that gate is what satisfies C01 for every later phase. So:
name a sponsor -> sponsor approves the Initiation gate -> programme may leave Initiation.
Nothing else opens that door.
"""

from __future__ import annotations

# THE GATES ARE REVISION 4's FIVE (Slice 0b-ii, 2026-07-16). What stays in constants is the
# vocabulary the six-phase model does not redefine: the 15 controls, and the status sets the
# control guards read.
from .rev4_phases import (
    DEFAULT_PHASE_CODE,
    DELIVERABLE_GATE_DOC_TYPE,
    DELIVERABLE_INDEX,
    GATE_CLOSING_PHASE,
    GATE_CODES,
    GATE_PREREQUISITE_GATES,
    GATES,
    GATES_DEFERRED_BEYOND_RELEASE_1,
    deliverable_doc_type,
)
from .constants import (
    CONTROLS,
    BENEFICIARY_STATUSES_APPROVED,
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

    Input:  gate code, e.g. 'R4G1_INITIATION'.
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

    Satisfied by an APPROVED Initiation gate whose approver actually held the sponsor role at
    the time (approve_gate enforces the role; this reads the result). Merely naming a
    sponsor is not approval.

    THE GATE CODE IS LOOKED UP, NOT SPELT OUT. It used to read `gate_code='G01'` inline. When
    Rev 4 renumbered the gates, that literal would have gone on matching nothing -- so the
    query would return no row, C01 would refuse forever, and every programme would be wedged
    at Initiation by a control that believed it was doing its job. Deriving it from the model
    means a future renumbering moves this with it, or fails loudly at import instead.
    """
    initiation_gate = GATE_CLOSING_PHASE[DEFAULT_PHASE_CODE]
    row = c.execute(
        "SELECT status FROM enterprise_stage_gates "
        " WHERE tenant_id=? AND programme_id=? AND gate_code=?",
        (tenant_id, programme_id, initiation_gate),
    ).fetchone()
    if not row or row[0] != "Approved":
        raise EnterpriseGateError(
            "C01",
            "the programme sponsor has not approved the Initiation gate",
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
    """Initiation gate entry: the programme must name a sponsor.

    Input:  connection, tenant id, programme id.
    Output: none (returns quietly when a sponsor is named).
    Raises: EnterpriseGateError.

    See 'why C01 is not circular' in the module docstring -- this predicate is the half of
    that argument which stops the sponsor's own approval from being self-referential.
    """
    row = c.execute(
        "SELECT sponsor_user_id FROM enterprise_programme_registry WHERE tenant_id=? AND id=?",
        (tenant_id, programme_id),
    ).fetchone()
    if not row or not row[0]:
        raise EnterpriseGateError(
            GATE_CLOSING_PHASE[DEFAULT_PHASE_CODE],
            "the programme must name a sponsor before the Initiation gate can be approved",
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


# WHAT A REV 4 GATE ASKS FOR, AND WHY IT IS SO MUCH LESS THAN BEFORE
# ------------------------------------------------------------------
# The old model had 14 gates and a predicate zoo behind them: per-gate evidence documents,
# cross-gate prerequisites, and two gates (G03, G06) that reached into the beneficiary
# register and the template store to check the thing itself rather than a claim about it.
# The owner rejected that model as "made too large" and Revision 4 replaced it with five
# boundaries, each phrased in the spec (section 38) as an APPROVAL BY A NAMED AUTHORITY.
#
# So a Rev 4 gate asks for exactly two things, and the second one does the real work:
#
#   1. THE PHASE'S OWN APPROVAL DOCUMENT, so the gate reads something the app actually WROTE
#      rather than opening on a typed name (the 2026-07-13 defect -- a stage gate passed by
#      TYPING A NAME while the document the app wrote counted for nothing).
#   2. THE NAMED AUTHORITY'S SIGNATURE, enforced by approve_gate against GATE_AUTHORITY.
#
# The old per-gate evidence predicates are GONE rather than remapped. They asked for
# documents that belonged to a 16-phase lifecycle -- a business case, a funding strategy, an
# issued-for-construction package -- and Rev 4's phases do not have those boundaries to
# defend. Keeping them would have been the "old map" the owner asked to have deleted, wearing
# new gate codes.
#
# Governance is advisory-by-default (flags.enterprise_governance_advisory), so a programme
# whose gate evidence is thin is TOLD, not stopped, unless the tenant turns advisory off.
GATE_PREDICATES = {
    gate_code: (
        # The Initiation gate additionally requires the programme to NAME a sponsor. See
        # "why C01 is not circular" in the module docstring: naming the sponsor is what makes
        # the sponsor's approval of this gate meaningful rather than self-referential.
        ([_gate_1_predicate] if phase_code == DEFAULT_PHASE_CODE else [])
        + [_requires_document(
            deliverable_doc_type(deliverable_code),
            gate_code,
            DELIVERABLE_INDEX[deliverable_code][1],
        )]
    )
    for gate_code, phase_code in (
        (GATE_CLOSING_PHASE[_p], _p) for _p in GATE_CLOSING_PHASE
    )
    for deliverable_code in (
        # The one deliverable in this gate's phase that is stamped as its evidence.
        next(d for d, _t in DELIVERABLE_GATE_DOC_TYPE.items()
             if DELIVERABLE_INDEX[d][0] == phase_code),
    )
}

# Every gate must have got a predicate list. A gate that silently ended up with none would
# open on authority alone -- which is a decision, not an accident, and is not the one made
# here.
assert set(GATE_PREDICATES) == set(GATE_CODES), (
    f"gates without predicates: {sorted(set(GATE_CODES) - set(GATE_PREDICATES))}"
)


# doc_type -> the gate it opens. DERIVED from the predicates above, never hand-written.
#
# The Lifecycle Documents page tells the operator, before they generate, that this particular
# deliverable is the evidence Gate 4 is waiting for. That promise is only worth making if it
# cannot go stale: a hand-kept second copy of this mapping would keep displaying "opens Gate
# 4" for a gate whose demand had since changed, and the operator would generate a document
# that opens nothing. So the UI reads it off the predicates that actually enforce it -- one
# source of truth, and a gate whose demand changes changes the page with it.
GATE_OF_DOC_TYPE: dict[str, str] = {
    p.required_doc_type: gate_code
    for gate_code, predicates in GATE_PREDICATES.items()
    for p in predicates
    if getattr(p, "required_doc_type", None)
}

# A dict keyed by doc_type SILENTLY KEEPS THE LAST BINDING. If two gates ever demanded the
# same document, the page would confidently name the wrong gate -- and it would name it to
# the one operator who is blocked on the other one. This map is derived precisely so it
# cannot go stale; this is the one remaining way it could, so it is closed at import.
_demanded = [
    p.required_doc_type
    for predicates in GATE_PREDICATES.values()
    for p in predicates
    if getattr(p, "required_doc_type", None)
]
assert len(_demanded) == len(set(_demanded)), (
    "two stage gates demand the same document type, so GATE_OF_DOC_TYPE can only name one "
    f"of them: {sorted({d for d in _demanded if _demanded.count(d) > 1})}"
)
del _demanded


# deliverable code -> the gate that deliverable opens. Five of Revision 4's 112.
DELIVERABLE_GATE: dict[str, str] = {
    code: GATE_OF_DOC_TYPE[doc_type]
    for code, doc_type in DELIVERABLE_GATE_DOC_TYPE.items()
    if doc_type in GATE_OF_DOC_TYPE
}
assert len(DELIVERABLE_GATE) == len(DELIVERABLE_GATE_DOC_TYPE), (
    "a deliverable is mapped to a gate document type that no gate actually demands"
)

# doc_type -> the title of the deliverable stored under it. What the register shows a reader
# instead of "R4P1_D12" or "programme_approval_request", neither of which means anything to
# them.
DOC_TYPE_LABELS: dict[str, str] = {
    deliverable_doc_type(code): title
    for code, (_phase, title) in DELIVERABLE_INDEX.items()
}

# Both maps are pure functions of import-time constants, so they are built ONCE here rather
# than rebuilt on every page load -- and the assertion above turns an invariant the page
# merely assumed into one that fails loudly at import if it is ever broken.


def evaluate_gate(c, tenant_id: str, programme_id: int, gate_code: str) -> None:
    """Run every predicate registered for a gate.

    Input:  connection, tenant id, programme id, gate code.
    Output: none (returns quietly when the gate may be approved).
    Raises: EnterpriseGateError / GateBlockedError.

    ALL FIVE OF REVISION 4's GATES ARE OPERABLE. The old model seeded 14 and blocked five of
    them, because their evidence came from slices that had not shipped -- a lifecycle with a
    visible end was judged better than one with a hole in the middle. Rev 4's five boundaries
    each ask only for their own phase's approval document, which the app itself writes, so
    none of them is waiting on unshipped work. GATES_DEFERRED_BEYOND_RELEASE_1 is
    consequently empty, and the guard below is kept as a no-op rather than deleted: it is the
    mechanism by which a future gate CAN be seeded-but-blocked honestly.
    """
    if gate_code not in GATE_CODES:
        raise EnterpriseGateError("GATE", f"unknown gate {gate_code!r}")
    if gate_code in GATES_DEFERRED_BEYOND_RELEASE_1:
        raise GateBlockedError(
            gate_code,
            "this gate is seeded but not yet operable",
        )

    # Gate prerequisites, checked BEFORE the gate's own evidence. Rev 4 declares none
    # (GATE_PREREQUISITE_GATES is empty): its phases are a simple forward spine, and
    # PHASE_ENTRY_REQUIRED_GATES already makes each gate transitively require the one before
    # it, so a second cross-gate table would only be a place for the two to disagree. Kept as
    # a no-op loop because the mechanism is how a genuine cross-gate dependency would be
    # expressed if the owner's model ever grows one.
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
