"""The Revision 4 six-phase lifecycle model.

These lock the owner's spec (enterprise-revision-4-owner-spec.txt sections 6-14, 38) against
`app/enterprise_programme/rev4_phases.py`, which is now THE lifecycle -- Slice 0b-ii repointed
every consumer onto it and deleted the old 16-phase map. Their job is to make the six-phase
contract, and the deliverable codes derived from it, impossible to drift silently.
"""

from __future__ import annotations

from app.enterprise_programme import rev4_phases as r4


def test_exactly_six_phases_in_spec_order():
    assert [c for c, _, _ in r4.PHASES] == [
        "R4_INITIATION", "R4_PLANNING", "R4_EXECUTION",
        "R4_MONITORING", "R4_VALUE", "R4_CLOSURE",
    ]
    # sequence numbers are 1..6 in order
    assert [s for _, s, _ in r4.PHASES] == [1, 2, 3, 4, 5, 6]


def test_five_gates_and_monitoring_has_none():
    # Owner spec section 38 names five gate boundaries; Monitoring runs continuously
    # (section 12) and gates nothing.
    assert len(r4.GATES) == 5
    assert "R4_MONITORING" not in r4.GATE_FOR_PHASE
    # every gate closes a real phase, and no phase but Monitoring is left ungated
    gated = set(r4.GATE_FOR_PHASE)
    assert gated == set(r4.PHASE_CODES) - {"R4_MONITORING"}


def test_deliverable_counts_match_spec_sections_9_to_14():
    # These are the owner's own button lists, authored verbatim -- not the old 144.
    assert {c: len(v) for c, v in r4.PHASE_DELIVERABLES.items()} == {
        "R4_INITIATION": 12,
        "R4_PLANNING": 27,
        "R4_EXECUTION": 21,
        "R4_MONITORING": 19,
        "R4_VALUE": 17,
        "R4_CLOSURE": 16,
    }
    assert len(r4.DELIVERABLE_INDEX) == 12 + 27 + 21 + 19 + 17 + 16


def test_specific_owner_deliverables_present_in_right_phase():
    # spot-checks straight from the spec so a reorder can't quietly move a button
    assert "Programme Charter" in r4.PHASE_DELIVERABLE_NAMES["R4_INITIATION"]       # section 9
    assert "Programme Feasibility Study" in r4.PHASE_DELIVERABLE_NAMES["R4_PLANNING"]  # s.10
    assert "Commissioning" in r4.PHASE_DELIVERABLE_NAMES["R4_EXECUTION"]            # section 11
    assert "Maintenance Handover" in r4.PHASE_DELIVERABLE_NAMES["R4_VALUE"]         # section 13
    # section 14 lists Expansion + Replication as CLOSURE deliverables -- which is why
    # Rev 4 has no separate "expansion" phase at all.
    assert "Expansion Recommendation" in r4.PHASE_DELIVERABLE_NAMES["R4_CLOSURE"]
    assert "Replication Plan" in r4.PHASE_DELIVERABLE_NAMES["R4_CLOSURE"]


def test_no_deliverable_name_repeats_within_a_phase():
    for code, names in r4.PHASE_DELIVERABLE_NAMES.items():
        assert len(names) == len(set(names)), f"duplicate deliverable in {code}"


# --- the derived coded layer (slice 0b-ii) ----------------------------------
# The codes are what every consumer actually uses: the report button's POST value, the
# document's doc_type, the engine map. These assert the derivation, because a code that
# drifts from the name it points at is a report generated under the wrong title.


def test_every_deliverable_has_a_code_that_resolves_back_to_its_own_name():
    for phase, items in r4.PHASE_DELIVERABLES.items():
        for code, title in items:
            assert r4.DELIVERABLE_INDEX[code] == (phase, title)
    assert len(r4.DELIVERABLE_CODES) == 112


def test_codes_are_positional_within_their_phase():
    # R4P<phase seq>_D<nn>. Initiation is phase 1, so its first deliverable is R4P1_D01.
    assert r4.PHASE_DELIVERABLES["R4_INITIATION"][0] == ("R4P1_D01", "Programme Concept Note")
    assert r4.PHASE_DELIVERABLES["R4_CLOSURE"][0][0] == "R4P6_D01"


def test_each_gate_is_opened_by_exactly_one_deliverable_in_its_own_phase():
    # A gate whose evidence lived in another phase could never be produced in time to open it.
    for code, doc_type in r4.DELIVERABLE_GATE_DOC_TYPE.items():
        phase, _title = r4.DELIVERABLE_INDEX[code]
        assert r4.GATE_FOR_PHASE[phase], f"{code} opens a gate for un-gated phase {phase}"
        assert r4.deliverable_doc_type(code) == doc_type
    assert len(r4.DELIVERABLE_GATE_DOC_TYPE) == len(r4.GATE_CODES) == 5


def test_a_deliverable_that_opens_no_gate_is_stored_under_its_own_code():
    # Otherwise two different reports would collide in the register under one doc_type.
    assert r4.deliverable_doc_type("R4P1_D01") == "R4P1_D01"


def test_every_engine_written_deliverable_is_a_real_deliverable():
    assert set(r4.DELIVERABLE_ENGINE) <= r4.DELIVERABLE_CODES


# The OLD -> NEW mapping tables (OLD_PHASE_TO_NEW, OLD_GATE_TO_NEW) and their three tests were
# deleted on 2026-07-16 with the rest of the old map. They remapped live rows off the 16-phase
# model; that remap never ran, because the live enterprise data was cleared to a clean slate
# first, so a programme is now born into the six-phase model with nothing to translate. The
# tables' keys were the deleted phases and gates -- keeping them would have preserved the old
# map inside the file that replaced it.


def test_status_is_defined_for_every_phase():
    assert set(r4.PHASE_STATUS) == set(r4.PHASE_CODES)


# ---- state machine (Slice 0b) ----------------------------------------------

def test_default_phase_is_initiation():
    assert r4.DEFAULT_PHASE_CODE == "R4_INITIATION"


def test_transitions_key_every_phase_and_target_valid():
    assert set(r4.TRANSITIONS) == set(r4.PHASE_CODES)
    for src, dsts in r4.TRANSITIONS.items():
        for d in dsts:
            assert d in r4.PHASE_CODES or d in r4.PSEUDO_STATES, f"{src}->{d}"


def test_forward_spine_reaches_closure():
    # Init -> Planning -> Execution -> Value -> Closure is walkable forward.
    assert "R4_PLANNING" in r4.TRANSITIONS["R4_INITIATION"]
    assert "R4_EXECUTION" in r4.TRANSITIONS["R4_PLANNING"]
    assert "R4_VALUE" in r4.TRANSITIONS["R4_EXECUTION"]
    assert "R4_CLOSURE" in r4.TRANSITIONS["R4_VALUE"]


def test_monitoring_is_continuous_not_gated():
    # Reachable from Execution, loops back / forward, and gates nothing.
    assert "R4_MONITORING" in r4.TRANSITIONS["R4_EXECUTION"]
    assert "R4_EXECUTION" in r4.TRANSITIONS["R4_MONITORING"]
    assert "R4_VALUE" in r4.TRANSITIONS["R4_MONITORING"]
    assert "R4_MONITORING" not in r4.PHASE_ENTRY_REQUIRED_GATES


def test_every_phase_is_reachable_from_start():
    reachable = {r4.DEFAULT_PHASE_CODE}
    frontier = [r4.DEFAULT_PHASE_CODE]
    while frontier:
        cur = frontier.pop()
        for d in r4.TRANSITIONS.get(cur, ()):
            if d in r4.PHASE_CODES and d not in reachable:
                reachable.add(d)
                frontier.append(d)
    assert reachable == set(r4.PHASE_CODES)


def test_phase_entry_gates_reference_real_gates():
    for reqs in r4.PHASE_ENTRY_REQUIRED_GATES.values():
        assert set(reqs) <= set(r4.GATE_CODES)
    # the gated forward steps each require the prior phase's gate
    assert r4.PHASE_ENTRY_REQUIRED_GATES["R4_PLANNING"] == ("R4G1_INITIATION",)
    assert r4.PHASE_ENTRY_REQUIRED_GATES["R4_CLOSURE"] == ("R4G4_VALUE",)


def test_gate_authority_defined_for_every_gate():
    assert set(r4.GATE_AUTHORITY) == set(r4.GATE_CODES)
    assert all(v for v in r4.GATE_AUTHORITY.values())
