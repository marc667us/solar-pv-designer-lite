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
PHASE_DELIVERABLES: dict[str, list[str]] = {
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

# Flat list of (phase_code, deliverable_name) for seeding / indexing.
DELIVERABLE_INDEX: list[tuple[str, str]] = [
    (phase, name)
    for phase in PHASE_CODES
    for name in PHASE_DELIVERABLES[phase]
]


# =============================================================================
# OLD (16-phase) -> NEW (6-phase) mapping  -- used by migration 032
# =============================================================================
# Every old phase code from constants.PHASES maps to exactly one new phase. The mapping
# is monotonic-by-intent: early old phases -> Initiation/Planning, build phases ->
# Execution, evaluation -> Monitoring, handover/operations -> Value Realisation, and
# expansion/replication -> Closure (spec section 14 lists Expansion Recommendation and
# Replication Plan as CLOSURE deliverables, which is why P16 lands in Closure).
OLD_PHASE_TO_NEW: dict[str, str] = {
    "P01_CONCEPT":       "R4_INITIATION",
    "P02_INITIATION":    "R4_INITIATION",
    "P03_NEEDS":         "R4_PLANNING",
    "P04_FEASIBILITY":   "R4_PLANNING",
    "P05_STRUCTURING":   "R4_PLANNING",
    "P06_TEMPLATES":     "R4_PLANNING",
    "P07_FUNDING":       "R4_PLANNING",
    "P08_PROCUREMENT":   "R4_PLANNING",
    "P09_ENGINEERING":   "R4_EXECUTION",
    "P10_MOBILISATION":  "R4_EXECUTION",
    "P11_CONSTRUCTION":  "R4_EXECUTION",
    "P12_COMMISSIONING": "R4_EXECUTION",
    "P13_HANDOVER":      "R4_VALUE",
    "P14_OPERATIONS":    "R4_VALUE",
    "P15_EVALUATION":    "R4_MONITORING",
    "P16_EXPANSION":     "R4_CLOSURE",
}

# OLD (14-gate) -> NEW (5-gate) mapping. Each new phase-gate is closed by the OLD gate
# that closed the LAST old phase inside it, so an in-flight programme keeps the strictest
# gate it had already reached:
#   Initiation  closed by old G02 (Programme Initiation Approval)
#   Planning    closed by old G08 (Contract Award / Notice to Proceed)
#   Execution   closed by old G12 (Commissioning / Taking-Over)
#   Value       closed by old G13 (Handover / Closeout)
#   Closure     closed by old G14 (Benefits / Performance Review)
# The remaining old gates (G01, G03-G07, G09-G11) collapse into the new gate of their
# phase -- their prior approvals are preserved read-only in the archive, not lost.
OLD_GATE_TO_NEW: dict[str, str] = {
    "G01": "R4G1_INITIATION",
    "G02": "R4G1_INITIATION",
    "G03": "R4G2_PLANNING",
    "G04": "R4G2_PLANNING",
    "G05": "R4G2_PLANNING",
    "G06": "R4G2_PLANNING",
    "G07": "R4G2_PLANNING",
    "G08": "R4G2_PLANNING",
    "G09": "R4G3_EXECUTION",
    "G10": "R4G3_EXECUTION",
    "G11": "R4G3_EXECUTION",
    "G12": "R4G3_EXECUTION",
    "G13": "R4G4_VALUE",
    "G14": "R4G5_CLOSURE",
}


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
    assert len(PHASE_DELIVERABLES[_code]) == _n, (
        f"{_code} deliverable count drifted: expected {_n}, "
        f"got {len(PHASE_DELIVERABLES[_code])}"
    )

# Every old phase and old gate MUST have a new-model target, or the migration would
# orphan a live programme sitting in the unmapped code (Codex risk G-1).
assert set(OLD_PHASE_TO_NEW.values()) <= set(PHASE_CODES)
assert set(OLD_GATE_TO_NEW.values()) <= set(GATE_CODES)


__all__ = [
    "PHASES", "PHASE_CODES", "PHASE_NAME", "PHASE_SEQ",
    "GATES", "GATE_CODES", "GATE_FOR_PHASE",
    "PHASE_DELIVERABLES", "DELIVERABLE_INDEX",
    "OLD_PHASE_TO_NEW", "OLD_GATE_TO_NEW", "PHASE_STATUS",
]
