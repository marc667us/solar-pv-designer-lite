"""Slice 0 foundation tests -- the Revision 4 six-phase lifecycle model.

These lock the owner's spec (enterprise-revision-4-owner-spec.txt sections 6-14, 38)
against `app/enterprise_programme/rev4_phases.py`. They do NOT touch the app, the DB, or
the (still 16-phase) live lifecycle code -- that wiring is Slice 0b. Their job is to make
the six-phase contract and the old->new migration mapping impossible to drift silently.
"""

from __future__ import annotations

from app.enterprise_programme import rev4_phases as r4
from app.enterprise_programme import constants as old


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
    assert "Programme Charter" in r4.PHASE_DELIVERABLES["R4_INITIATION"]       # section 9
    assert "Programme Feasibility Study" in r4.PHASE_DELIVERABLES["R4_PLANNING"]  # section 10
    assert "Commissioning" in r4.PHASE_DELIVERABLES["R4_EXECUTION"]            # section 11
    assert "Maintenance Handover" in r4.PHASE_DELIVERABLES["R4_VALUE"]         # section 13
    # section 14 lists Expansion + Replication as CLOSURE deliverables -- the reason
    # old P16_EXPANSION maps to Closure, not a sixth "expansion" phase.
    assert "Expansion Recommendation" in r4.PHASE_DELIVERABLES["R4_CLOSURE"]
    assert "Replication Plan" in r4.PHASE_DELIVERABLES["R4_CLOSURE"]


def test_no_deliverable_name_repeats_within_a_phase():
    for code, names in r4.PHASE_DELIVERABLES.items():
        assert len(names) == len(set(names)), f"duplicate deliverable in {code}"


def test_every_old_phase_maps_to_a_real_new_phase():
    # Migration 032 must not orphan a live programme sitting in any old phase (Codex G-1).
    old_codes = {code for code, _, _ in old.PHASES}
    assert set(r4.OLD_PHASE_TO_NEW) == old_codes, "an old phase has no new-model target"
    assert set(r4.OLD_PHASE_TO_NEW.values()) <= set(r4.PHASE_CODES)


def test_every_old_gate_maps_to_a_real_new_gate():
    old_gates = {code for code, _, _, _ in old.GATES}
    assert set(r4.OLD_GATE_TO_NEW) == old_gates, "an old gate has no new-model target"
    assert set(r4.OLD_GATE_TO_NEW.values()) <= set(r4.GATE_CODES)


def test_phase_mapping_is_forward_only():
    # A programme must never be mapped BACKWARDS into an earlier phase than its old one
    # implies -- that would resurrect a gate it had already passed. We assert the mapping
    # is non-decreasing in sequence: old phase i -> new phase whose seq >= a sane floor.
    # Concretely: the first two old phases -> Initiation, the last -> Closure.
    assert r4.OLD_PHASE_TO_NEW["P01_CONCEPT"] == "R4_INITIATION"
    assert r4.OLD_PHASE_TO_NEW["P02_INITIATION"] == "R4_INITIATION"
    assert r4.OLD_PHASE_TO_NEW["P16_EXPANSION"] == "R4_CLOSURE"
    # planning band
    for pc in ("P03_NEEDS", "P04_FEASIBILITY", "P05_STRUCTURING",
               "P06_TEMPLATES", "P07_FUNDING", "P08_PROCUREMENT"):
        assert r4.OLD_PHASE_TO_NEW[pc] == "R4_PLANNING"
    # execution band
    for pc in ("P09_ENGINEERING", "P10_MOBILISATION",
               "P11_CONSTRUCTION", "P12_COMMISSIONING"):
        assert r4.OLD_PHASE_TO_NEW[pc] == "R4_EXECUTION"


def test_status_is_defined_for_every_phase():
    assert set(r4.PHASE_STATUS) == set(r4.PHASE_CODES)
