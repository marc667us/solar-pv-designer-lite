"""Enterprise Solar Programme -- Revision 4 six-phase lifecycle model.

WHY THIS FILE EXISTS
--------------------
The owner REJECTED the previous 16-phase / 14-gate / 38-role build as "made too
large". Revision 4 (docs/enterprise-programme/enterprise-revision-4-owner-spec.txt,
sections 6-14 and 38) replaces it with SIX lifecycle phases, FIVE phase-gates, and
per-phase DELIVERABLE lists authored VERBATIM from the spec -- not rebucketed from the
old 144 outputs (Codex review finding F, 2026-07-15).

This module is the single source of truth for the new model. Migration 032 seeds live
rows from it; the workspace UI renders its phase buttons; the deliverable workspace
lists PHASE_DELIVERABLES; and the old->new mapping tables here are what migration 032
uses to remap every existing programme's phase/gate rows onto the six-phase model while
preserving the old evidence read-only.

Ordering is significant (sequence_no). Append only; do not reorder.

RELATIONSHIP TO constants.py
----------------------------
`constants.py` still holds the OLD 16-phase vocabulary. It is NOT deleted yet: the
transition ledger and any archived pre-032 rows still reference the old codes, and the
migration needs both vocabularies side by side to map between them. Once the migration
has shipped and the old rows are archived read-only, `constants.py`'s PHASES/GATES
become historical lookups only.
"""

from __future__ import annotations


# =============================================================================
# The six canonical lifecycle phases (owner-spec section 6, lines 434-440 + 613)
# =============================================================================
# (code, sequence_no, display name)
# NOTE the owner's phase 4 "Monitoring" runs CONTINUOUSLY across planning, execution
# and operations (spec section 12, line 591) -- it is a phase button in the bar, but it
# is not a hard sequential gate the way the other five boundaries are.
PHASES: list[tuple[str, int, str]] = [
    ("R4_INITIATION",   1, "Initiation"),
    ("R4_PLANNING",     2, "Planning"),
    ("R4_EXECUTION",    3, "Execution"),
    ("R4_MONITORING",   4, "Monitoring"),
    ("R4_VALUE",        5, "Value Realisation and Transition"),
    ("R4_CLOSURE",      6, "Closure"),
]

PHASE_CODES: list[str] = [code for code, _, _ in PHASES]
PHASE_NAME: dict[str, str] = {code: name for code, _, name in PHASES}
PHASE_SEQ: dict[str, int] = {code: seq for code, seq, _ in PHASES}


# =============================================================================
# The five phase-gates (owner-spec section 38, lines 1663-1717)
# =============================================================================
# The owner names FIVE gate boundaries: Initiation->Planning, Planning->Execution,
# Execution->Value Realisation & Transition, Value Realisation & Transition->Closure,
# and Closure. Monitoring has NO gate -- it runs alongside, it does not gate anything.
#
# (code, phase_code the gate closes, display name, approving authority role)
# Approving authority is deliberately coarse in Rev 4: the owner reduced 38 roles to a
# handful of archetypes (spec section 20). We keep sponsor/programme_director as the two
# gate authorities the spec's section-20 role functions actually name.
GATES: list[tuple[str, str, str, str]] = [
    ("R4G1_INITIATION", "R4_INITIATION", "Initiation to Planning Gate",                 "programme_sponsor"),
    ("R4G2_PLANNING",   "R4_PLANNING",   "Planning to Execution Gate",                  "programme_sponsor"),
    ("R4G3_EXECUTION",  "R4_EXECUTION",  "Execution to Value Realisation Gate",         "programme_director"),
    ("R4G4_VALUE",      "R4_VALUE",      "Value Realisation to Closure Gate",           "programme_sponsor"),
    ("R4G5_CLOSURE",    "R4_CLOSURE",    "Programme Closure Gate",                      "programme_sponsor"),
]

GATE_CODES: list[str] = [code for code, _, _, _ in GATES]
GATE_FOR_PHASE: dict[str, str] = {phase: code for code, phase, _, _ in GATES}


# =============================================================================
# Per-phase DELIVERABLE lists -- authored VERBATIM from owner-spec sections 9-14
# =============================================================================
# These are the deliverable BUTTONS the owner wants on each phase page (spec section 8).
# Clicking one opens the consistent Deliverable Workspace (spec section 15). Do NOT
# rebucket the old 144 into these -- these ARE the contract (Codex finding F).
#
# AUTHORED AS NAMES, CODED BY DERIVATION. The spec gives the owner's deliverable NAMES and
# nothing else, so the names are what this file authors verbatim -- that is the contract.
# The codes every consumer needs (the button's POST value, the document's doc_type key, the
# engine map) are DERIVED from these lists below, never hand-written beside them. A
# hand-kept second column would be one edit away from naming the wrong deliverable.
PHASE_DELIVERABLE_NAMES: dict[str, list[str]] = {
    # ---- section 9: Initiation Deliverable Buttons (12) ----
    "R4_INITIATION": [
        "Programme Concept Note",
        "Problem Statement",
        "Programme Objectives",
        "Preliminary Beneficiary Definition",
        "Preliminary Geographic Scope",
        "Stakeholder Register",
        "Initial Risk Register",
        "Programme Governance Structure",
        "Programme Charter",
        "Preliminary Budget",
        "Preliminary Schedule",
        "Programme Approval Request",
    ],
    # ---- section 10: Planning Deliverable Buttons (27) ----
    "R4_PLANNING": [
        "Beneficiary Registration Plan",
        "Beneficiary Register",
        "Site Assessment Plan",
        "Site Qualification Report",
        "Electricity Bill Analysis",
        "Energy Demand Assessment",
        "Programme Feasibility Study",
        "Standard Design Strategy",
        "Generation Station Design Strategy",
        "Programme Technical Standards",
        "Standard Design Catalogue",
        "Generation Station Design Package",
        "Programme Capacity Plan",
        "Programme Battery Plan",
        "Programme BOQ",
        "Programme Cost Plan",
        "Funding Strategy",
        "Procurement Strategy",
        "EPC Packaging Plan",
        "Programme Master Schedule",
        "Risk Management Plan",
        "Quality Management Plan",
        "Environmental and Social Plan",
        "Monitoring and Evaluation Plan",
        "Programme Implementation Plan",
        "Executive Planning Report",
        "Planning Approval Request",
    ],
    # ---- section 11: Execution Deliverable Buttons (21) ----
    "R4_EXECUTION": [
        "Beneficiary Onboarding",
        "Site Survey Execution",
        "Detailed Project Generation",
        "Detailed Engineering",
        "Design Approval",
        "Procurement Packages",
        "Tendering",
        "Contractor Appointment",
        "Site Mobilisation",
        "Material Delivery",
        "Construction",
        "Installation",
        "Quality Inspections",
        "Safety Inspections",
        "Progress Reports",
        "Payment Certification",
        "Variations",
        "Claims",
        "Testing",
        "Commissioning",
        "Handover Preparation",
    ],
    # ---- section 12: Monitoring Deliverable Buttons (19) ----
    "R4_MONITORING": [
        "Programme Dashboard",
        "Regional Performance Report",
        "Beneficiary Progress Report",
        "Project Progress Report",
        "Schedule Performance",
        "Cost Performance",
        "Risk Monitoring",
        "Issue Monitoring",
        "Contractor Performance",
        "Supplier Performance",
        "Procurement Tracking",
        "Installation Tracking",
        "Quality Monitoring",
        "Safety Monitoring",
        "Energy Generation Monitoring",
        "Battery Monitoring",
        "Fault Monitoring",
        "Carbon Reduction Monitoring",
        "Executive Status Report",
    ],
    # ---- section 13: Value Realisation and Transition Deliverable Buttons (17) ----
    "R4_VALUE": [
        "Benefits Realisation Plan",
        "Installed Capacity Verification",
        "Energy Generation Verification",
        "Grid Savings Verification",
        "Diesel Savings Verification",
        "Carbon Reduction Verification",
        "Beneficiary Acceptance",
        "User Training",
        "Operations Training",
        "Maintenance Handover",
        "Asset Register",
        "Warranty Register",
        "Spare Parts Register",
        "Operations Transition Plan",
        "O&M Contract",
        "Performance Baseline",
        "Post-Implementation Review",
    ],
    # ---- section 14: Closure Deliverable Buttons (16) ----
    "R4_CLOSURE": [
        "Final Completion Report",
        "Programme Financial Closeout",
        "Contract Closeout",
        "Final Account",
        "Final Beneficiary Register",
        "Final Asset Register",
        "Final Performance Report",
        "Lessons Learned",
        "Outstanding Defects Register",
        "Claims Closure",
        "Document Archive",
        "Programme Evaluation",
        "Sponsor Acceptance",
        "Programme Closure Certificate",
        "Expansion Recommendation",
        "Replication Plan",
    ],
}

# =============================================================================
# The coded deliverable layer -- DERIVED from the authored names above
# =============================================================================
# Codes are R4P<phase seq>_D<nn>, e.g. R4P1_D01 is Initiation's first deliverable. They are
# positional by design: the code IS the deliverable's place in the owner's own list, so a
# code cannot drift from the name it points at. This is why the lists above are append-only
# (reordering one would silently re-point every code after it, and a stored document's
# doc_type would then name a different deliverable than the one that wrote it).
#
# SHAPE IS DELIBERATELY IDENTICAL TO THE OLD constants.PHASE_DELIVERABLES:
# {phase_code: ((code, title), ...)}. The report buttons, the generator and the gate check
# all read that shape already, so the six-phase repoint is a genuine import swap rather than
# a rewrite of every consumer -- which is what makes this change reviewable.
PHASE_DELIVERABLES: dict[str, tuple[tuple[str, str], ...]] = {
    phase: tuple(
        (f"R4P{PHASE_SEQ[phase]}_D{n:02d}", name)
        for n, name in enumerate(PHASE_DELIVERABLE_NAMES[phase], start=1)
    )
    for phase in PHASE_CODES
}

# code -> (phase_code, title). One flat index so a deliverable resolves without knowing its
# phase -- the UI, the generator and the gate check all need this.
DELIVERABLE_INDEX: dict[str, tuple[str, str]] = {
    code: (phase, title)
    for phase, items in PHASE_DELIVERABLES.items()
    for code, title in items
}

DELIVERABLE_CODES: frozenset[str] = frozenset(DELIVERABLE_INDEX)


def _code_for(phase: str, name: str) -> str:
    """The code of a deliverable named verbatim from the owner's spec.

    Input:  a phase code, the deliverable's exact title.
    Output: its derived code, e.g. "R4P1_D12".
    Raises: KeyError at IMPORT time if no deliverable in that phase carries that name.

    The maps below are keyed BY NAME rather than by a hand-written code on purpose. A code
    is positional, so a typo'd "R4P1_D11" is still a perfectly valid code -- it just points
    at the wrong document, and a gate would then demand evidence nobody can produce while
    the real approval request opens nothing. A wrong NAME cannot fail that quietly: it
    raises here, on import, before a single request is served.
    """
    for code, title in PHASE_DELIVERABLES[phase]:
        if title == name:
            return code
    raise KeyError(f"{phase} has no deliverable named {name!r}")


# =============================================================================
# The five gate-opening deliverables (one per gate)
# =============================================================================
# WHAT A REV 4 GATE ASKS FOR, AND WHY IT IS ONE DOCUMENT AND NOT NINE.
#
# The old model had 14 gates, each with its own evidence-document predicate zoo. Rev 4 has
# five boundaries, and the owner's spec section 38 phrases each as an APPROVAL: the named
# authority signs the phase off. So each gate asks for exactly one thing -- the phase's own
# approval/closure document -- and the AUTHORITY's signature does the rest. That keeps the
# 2026-07-13 win (a document the app WROTE is what the gate READS, rather than a gate passed
# by typing a name) without carrying the 14-gate machinery the owner rejected as too large.
#
# deliverable code -> the doc_type it is stored under, which is what the gate reads.
DELIVERABLE_GATE_DOC_TYPE: dict[str, str] = {
    _code_for("R4_INITIATION", "Programme Approval Request"): "programme_approval_request",
    _code_for("R4_PLANNING",   "Planning Approval Request"):  "planning_approval_request",
    _code_for("R4_EXECUTION",  "Handover Preparation"):       "handover_preparation",
    _code_for("R4_VALUE",      "Post-Implementation Review"): "post_implementation_review",
    _code_for("R4_CLOSURE",    "Programme Closure Certificate"): "programme_closure_certificate",
}


def deliverable_doc_type(deliverable_code: str) -> str:
    """The `doc_type` a generated deliverable is stored under.

    Input:  a deliverable code, e.g. "R4P1_D12".
    Output: the gate's doc_type when this deliverable opens a gate
            ("programme_approval_request"), and the deliverable's own code otherwise.

    Same contract as the old constants.deliverable_doc_type: a gate predicate is a bare
    existence check on doc_type, so a deliverable that opens a gate MUST be stored under the
    type that gate reads. Everything else is stored under its own code, which keeps one
    deliverable's documents distinguishable from another's.
    """
    return DELIVERABLE_GATE_DOC_TYPE.get(deliverable_code, deliverable_code)


# =============================================================================
# The engine-written deliverables
# =============================================================================
# Some deliverables are ENGINEERING documents: the programme's approved reference design IS
# their content, and SolarPro's capital-investment engine already writes each one from a real
# design. Assembling those out of prose would produce a document with no engineering in it
# while the actual kWp, BOQ and funding figure sat one table away.
#
# Everything NOT in this map is written by the deliverable writer, which is honest about what
# it does not know. An engine-written document must never be -- so this map stays SMALL and
# only names deliverables the engine genuinely produces. When in doubt, leave it out: the
# writer path degrades to "[To be completed]", which an operator can see and fix, whereas a
# wrongly-mapped engine document would confidently print the wrong report.
#
# deliverable code -> the CI report key that writes it (see reports.py).
DELIVERABLE_ENGINE: dict[str, str] = {
    _code_for("R4_PLANNING", "Programme Feasibility Study"):   "technical",
    _code_for("R4_PLANNING", "Programme Cost Plan"):           "financial",
    _code_for("R4_PLANNING", "Programme BOQ"):                 "boq",
    _code_for("R4_PLANNING", "Funding Strategy"):              "bankability",
    _code_for("R4_PLANNING", "Programme Implementation Plan"): "implementation_plan",
    _code_for("R4_PLANNING", "Executive Planning Report"):     "investment_memo",
    _code_for("R4_MONITORING", "Executive Status Report"):     "monitoring",
}


# =============================================================================
# There is no OLD -> NEW mapping table here, deliberately
# =============================================================================
# An earlier cut of this file carried OLD_PHASE_TO_NEW (16 -> 6) and OLD_GATE_TO_NEW (14 -> 5)
# to remap live rows off the old model. That remap never happened: the live enterprise data
# was cleared to a CLEAN SLATE on 2026-07-15/16, so a programme is now simply BORN into the
# six-phase model and there is nothing to translate. Keeping the tables would have preserved
# the 16 phases and 14 gates -- as dictionary keys -- inside the very file that replaced them,
# which is the "remnant of the old map" the owner asked to have deleted. If a future import
# ever needs to read pre-Rev-4 rows, the mapping belongs in that migration, next to the data
# it converts, not in the model.

# =============================================================================
# Derived programme status from phase (Rev 4 keeps status a VIEW of the phase, never
# user-typed -- same discipline as the old model, spec section 6 / migration 026 PART 1)
# =============================================================================
PHASE_STATUS: dict[str, str] = {
    "R4_INITIATION": "Initiation",
    "R4_PLANNING":   "Planning",
    "R4_EXECUTION":  "Execution",
    "R4_MONITORING": "Monitoring",
    "R4_VALUE":      "Value Realisation",
    "R4_CLOSURE":    "Closure",
}


# =============================================================================
# The six-phase lifecycle STATE MACHINE (Slice 0b) -- the drop-in that workflows.py
# and gates.py read instead of the old 16-phase machine in constants.py
# =============================================================================
# Hold/terminal pseudo-states are model-agnostic (a suspended programme is suspended
# whether the model has 6 phases or 16), so they are reused verbatim from constants.py
# via re-export -- there is nothing six-phase-specific about them.
from .constants import (  # noqa: E402  (kept local to the state-machine section)
    HOLD_STATES,
    TERMINAL_STATES,
    PSEUDO_STATES,
    PSEUDO_STATE_STATUS,
    GATE_AUTHORITY_HOLDER_COLUMN,  # {role -> registry column naming its post holder}
)

DEFAULT_PHASE_CODE = "R4_INITIATION"

# phase_code -> the phases (or pseudo-states) it may legally move to. Rev 4 is a SIMPLE
# forward spine (owner-spec section 6): Initiation -> Planning -> Execution -> Value ->
# Closure, each guarded by its gate. MONITORING is the exception: it "must run during
# planning, execution and operations" (section 12), so it is reachable from Execution and
# loops back or forward WITHOUT a gate of its own -- it is a continuous phase, not a stop.
# Each phase also allows a one-step rollback (return for revision) and the hold/terminal
# pseudo-states. Anything not listed is an illegal transition -- no any->any escape.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "R4_INITIATION": ("R4_PLANNING", "CANCELLED", "ON_HOLD"),
    "R4_PLANNING":   ("R4_EXECUTION", "R4_INITIATION", "ON_HOLD", "CANCELLED"),
    "R4_EXECUTION":  ("R4_MONITORING", "R4_VALUE", "R4_PLANNING", "SUSPENDED"),
    "R4_MONITORING": ("R4_VALUE", "R4_EXECUTION"),
    "R4_VALUE":      ("R4_CLOSURE", "R4_EXECUTION", "SUSPENDED"),
    "R4_CLOSURE":    ("CLOSED",),
}

# The gate that closes each phase (must be Approved before leaving it forward).
# Same content as GATE_FOR_PHASE above, named to match the old constants surface so the
# consumer repoint is a pure import swap.
GATE_CLOSING_PHASE: dict[str, str] = dict(GATE_FOR_PHASE)

# What a phase demands to be ENTERED. A destination-keyed rule (not edge-keyed) so no
# routing trick can reach a phase without its predecessor's gate. Monitoring has no entry
# gate (it runs continuously); Closure needs the Value gate; the Closure gate (R4G5) is
# approved to actually close the programme.
PHASE_ENTRY_REQUIRED_GATES: dict[str, tuple[str, ...]] = {
    "R4_PLANNING":  ("R4G1_INITIATION",),
    "R4_EXECUTION": ("R4G2_PLANNING",),
    "R4_VALUE":     ("R4G3_EXECUTION",),
    "R4_CLOSURE":   ("R4G4_VALUE",),
}

# Rev 4's five gates are all ACTIVE (the owner wants the whole simple lifecycle usable),
# so nothing is deferred and there are no cross-gate prerequisites beyond what phase-entry
# already enforces transitively. These exist so the consumer import surface matches the
# old one and the guards degrade to no-ops rather than KeyError.
GATE_PREREQUISITE_GATES: dict[str, tuple[str, ...]] = {}
GATES_DEFERRED_BEYOND_RELEASE_1: frozenset[str] = frozenset()

# gate_code -> the role that alone may approve it.
GATE_AUTHORITY: dict[str, str] = {code: role for code, _, _, role in GATES}


# --- integrity checks: fail import loudly if the spec lists drift ------------
# The owner's section 9-14 counts. If a future edit changes a list, this assert is the
# canary that the deliverable contract moved.
_EXPECTED_DELIVERABLE_COUNTS = {
    "R4_INITIATION": 12,
    "R4_PLANNING":   27,
    "R4_EXECUTION":  21,
    "R4_MONITORING": 19,
    "R4_VALUE":      17,
    "R4_CLOSURE":    16,
}
for _code, _n in _EXPECTED_DELIVERABLE_COUNTS.items():
    assert len(PHASE_DELIVERABLE_NAMES[_code]) == _n, (
        f"{_code} deliverable count drifted: expected {_n}, "
        f"got {len(PHASE_DELIVERABLE_NAMES[_code])}"
    )

# The derived coded layer must not lose or duplicate a deliverable. A duplicate title inside
# one phase would make _code_for return the first of them for both, so two buttons would
# generate the same document -- silently.
assert len(DELIVERABLE_INDEX) == sum(_EXPECTED_DELIVERABLE_COUNTS.values()), (
    "the derived deliverable codes do not cover every authored deliverable"
)
for _p in PHASE_CODES:
    _titles = [t for _c, t in PHASE_DELIVERABLES[_p]]
    assert len(_titles) == len(set(_titles)), (
        f"{_p} lists the same deliverable name twice, so its codes are ambiguous: "
        f"{sorted({t for t in _titles if _titles.count(t) > 1})}"
    )

# Every gate must have exactly one deliverable that opens it, and no two gates may share a
# doc_type -- a doc_type keyed map silently keeps the last binding, so two gates reading the
# same type would mean one of them could never be told which document it was waiting for.
_gate_doc_types = list(DELIVERABLE_GATE_DOC_TYPE.values())
assert len(_gate_doc_types) == len(set(_gate_doc_types)) == len(GATE_CODES), (
    "each of the five gates needs exactly one distinct evidence document type"
)
del _gate_doc_types


# State-machine integrity: every source is a real phase; every destination is a real phase
# or a known pseudo-state; the default phase exists; every phase is reachable from the
# start (no island); and every gate authority is used by exactly one gate.
_REACHABLE = {DEFAULT_PHASE_CODE}
_frontier = [DEFAULT_PHASE_CODE]
while _frontier:
    _cur = _frontier.pop()
    for _dst in TRANSITIONS.get(_cur, ()):
        if _dst in PHASE_CODES and _dst not in _REACHABLE:
            _REACHABLE.add(_dst)
            _frontier.append(_dst)
assert set(TRANSITIONS) == set(PHASE_CODES), "TRANSITIONS must key every phase"
for _src, _dsts in TRANSITIONS.items():
    for _d in _dsts:
        assert _d in PHASE_CODES or _d in PSEUDO_STATES, f"bad transition target {_d!r}"
assert _REACHABLE == set(PHASE_CODES), (
    f"unreachable phase(s): {set(PHASE_CODES) - _REACHABLE}"
)
assert DEFAULT_PHASE_CODE in PHASE_CODES
# Every phase-entry gate requirement names a real gate.
for _reqs in PHASE_ENTRY_REQUIRED_GATES.values():
    assert set(_reqs) <= set(GATE_CODES)


__all__ = [
    "PHASES", "PHASE_CODES", "PHASE_NAME", "PHASE_SEQ",
    "GATES", "GATE_CODES", "GATE_FOR_PHASE", "GATE_AUTHORITY",
    "PHASE_DELIVERABLE_NAMES", "PHASE_DELIVERABLES", "DELIVERABLE_INDEX",
    "DELIVERABLE_CODES", "DELIVERABLE_GATE_DOC_TYPE", "deliverable_doc_type",
    "DELIVERABLE_ENGINE",
    "PHASE_STATUS",
    # state-machine drop-in (Slice 0b)
    "DEFAULT_PHASE_CODE", "TRANSITIONS", "GATE_CLOSING_PHASE",
    "PHASE_ENTRY_REQUIRED_GATES", "GATE_PREREQUISITE_GATES",
    "GATES_DEFERRED_BEYOND_RELEASE_1",
    # re-exported model-agnostic pseudo-states
    "HOLD_STATES", "TERMINAL_STATES", "PSEUDO_STATES",
    "PSEUDO_STATE_STATUS", "GATE_AUTHORITY_HOLDER_COLUMN",
]
