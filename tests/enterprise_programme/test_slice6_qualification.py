"""Slice 6 -- site qualification.

One property carries this slice, and it is control C02:

    NO BENEFICIARY BECOMES A PROJECT WITHOUT QUALIFICATION.

Which in code means three separable things, and the tests are grouped around them:

  1. SCORING IS NOT DECIDING. The surveyor who goes and looks (`qualification.score`) is not
     the manager who commits the programme's money (`qualification.approve`). The person who
     measures must not be the person who chooses.

  2. A DECISION NEEDS A SCORECARD. `decide()` refuses a site nobody has surveyed. That refusal
     IS C02 -- without it, "Qualified" is a word anyone with the right role can type.

  3. HIGHER IS ALWAYS BETTER -- including the two categories doc 3 calls "risk", where 100
     means NO risk. Invert those two and the priority list ranks the most dangerous, least
     accessible sites at the top, and nothing looks wrong: the money just goes to the wrong
     villages.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from app.enterprise_programme import (
    beneficiaries, gates, site_qualification, tenancy, workflows,
)
from app.enterprise_programme.constants import (
    QUALIFICATION_CRITERIA, QUALIFICATION_CRITERION_KEYS,
)
from app.enterprise_programme.gates import EnterpriseGateError
from app.enterprise_programme.rbac import EnterprisePermissionError
from app.enterprise_programme.site_qualification import QualificationError
from app.security import audit as audit_mod


class _Conn(sqlite3.Connection):
    """sqlite3.Connection has no __dict__, so a plain attribute cannot be attached."""


OFFICER = 1    # beneficiary_officer   -- registers sites; may NOT score and may NOT decide
SURVEYOR = 2   # surveyor              -- qualification.score:  goes and looks
MANAGER = 3    # programme_manager     -- qualification.approve: decides. Also may NOT score.
OUTSIDER = 4   # another organisation entirely


@pytest.fixture()
def db():
    os.environ.pop("DATABASE_URL", None)
    audit_mod.reset_schema_probe()

    c = sqlite3.connect(":memory:", factory=_Conn)
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    names = ((OFFICER, "olivia"), (SURVEYOR, "sam"), (MANAGER, "musa"), (OUTSIDER, "olu"))
    for uid, name in names:
        c.execute("INSERT INTO users (id, username) VALUES (?,?)", (uid, name))
    c.execute(
        "CREATE TABLE audit_logs ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT DEFAULT '',"
        " action TEXT NOT NULL, ip_address TEXT DEFAULT '', details TEXT DEFAULT '',"
        " tenant_id TEXT, agent_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        " prev_hash TEXT, row_hash TEXT)"
    )

    tenancy.ensure_schema(c)
    workflows.ensure_schema(c)
    beneficiaries.ensure_schema(c)
    for uid, name in names:
        tenancy.get_or_create_personal_tenant(c, uid, name)

    org = tenancy.create_organisation(c, OFFICER, "Ministry of Energy", "ministry")
    other = tenancy.create_organisation(c, OUTSIDER, "Rival Ministry", "ministry")
    tenancy.add_member(c, org, OFFICER, "beneficiary_officer", OFFICER)
    tenancy.add_member(c, org, SURVEYOR, "surveyor", OFFICER)
    tenancy.add_member(c, org, MANAGER, "programme_manager", OFFICER)

    pid = workflows.create_programme(c, org, OFFICER, code="GH-SCH", name="Ghana Schools",
                                     sponsor_user_id=OFFICER, audit=_audit(c))
    c.commit()
    yield c, org, other, pid
    c.close()
    audit_mod.reset_schema_probe()


def _audit(c):
    def _hook(action, **kw):
        return audit_mod.write_audit_event(action, conn=c, **kw)
    return _hook


GOOD_SCORES = {
    "technical_suitability": 80, "energy_need": 90, "financial_suitability": 70,
    "social_impact": 85, "implementation_readiness": 60, "security_risk": 100,
    "environmental_risk": 90, "funding_eligibility": 75,
}


def _pending_site(c, org, pid, *, code="KPANDO-SHS", name="Kpando Senior High"):
    """A site registered AND admitted to the programme -- i.e. awaiting a decision."""
    bid = beneficiaries.create_beneficiary(
        c, org, OFFICER, pid, code=code, name=name, beneficiary_type="school",
        fields={"community": "Kpando", "district": "Kpando"}, audit=_audit(c))
    beneficiaries.transition_beneficiary(
        c, org, MANAGER, bid, "Qualification Pending", audit=_audit(c))
    return bid


# --- 1. scoring is not deciding ---------------------------------------------


def test_the_surveyor_scores_and_that_is_all_they_do(db):
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)

    card = site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                         notes="Good roof, easy access.", audit=_audit(c))

    # 80*20 + 90*20 + 70*15 + 85*15 + 60*10 + 100*5 + 90*5 + 75*10 = 8025, / 100 = 80.25
    assert card["total_score"] == pytest.approx(80.25)
    assert card["decision"] is None, "scoring must not decide anything"
    assert beneficiaries.get_beneficiary(c, org, bid)["status"] == "Qualification Pending"


def test_a_surveyor_cannot_decide(db):
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)
    site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                  audit=_audit(c))

    with pytest.raises(EnterprisePermissionError):
        site_qualification.decide(c, org, SURVEYOR, bid, decision="Qualified",
                                  audit=_audit(c))


def test_a_manager_cannot_score(db):
    """The person who commits the money does not also get to write the evidence for it."""
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)

    with pytest.raises(EnterprisePermissionError):
        site_qualification.score_site(c, org, MANAGER, bid, scores=GOOD_SCORES,
                                      audit=_audit(c))


def test_the_manager_decides_and_the_status_follows_in_the_same_breath(db):
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)
    site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                  audit=_audit(c))

    card = site_qualification.decide(c, org, MANAGER, bid, decision="Qualified",
                                     notes="Approved by committee.", audit=_audit(c))

    assert card["decision"] == "Qualified"
    assert card["decided_by_user_id"] == MANAGER
    assert beneficiaries.get_beneficiary(c, org, bid)["status"] == "Qualified"


# --- 2. C02: a decision needs a scorecard ------------------------------------


def test_a_site_nobody_scored_cannot_be_qualified(db):
    """THE CONTROL. Without this refusal, C02 is a word anyone with the role can type."""
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)

    with pytest.raises(QualificationError) as caught:
        site_qualification.decide(c, org, MANAGER, bid, decision="Qualified",
                                  audit=_audit(c))
    assert caught.value.control == "C02"
    assert beneficiaries.get_beneficiary(c, org, bid)["status"] == "Qualification Pending"


def test_the_status_cannot_be_hand_waved_into_qualified(db):
    """The other door into the same room: setting the status directly, bypassing the survey."""
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)

    with pytest.raises(EnterpriseGateError) as caught:
        beneficiaries.transition_beneficiary(c, org, MANAGER, bid, "Qualified",
                                             audit=_audit(c))
    assert caught.value.control == "C02"


def test_c02_gate_refuses_an_unqualified_site_and_admits_a_qualified_one(db):
    """gates.require_qualified_beneficiary is what slice 7 will call before generating."""
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)

    with pytest.raises(EnterpriseGateError) as caught:
        gates.require_qualified_beneficiary(c, org, bid)
    assert caught.value.control == "C02"

    site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                  audit=_audit(c))
    site_qualification.decide(c, org, MANAGER, bid, decision="Qualified", audit=_audit(c))

    gates.require_qualified_beneficiary(c, org, bid)      # no longer raises


def test_c02_is_not_satisfied_by_a_status_with_no_decision_behind_it(db):
    """Belt and braces: the status is one UPDATE away from being wrong, so the gate also
    demands the scorecard that justifies it."""
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)
    # Forge the status directly in the database, exactly as a stray UPDATE would.
    c.execute("UPDATE enterprise_beneficiary_register SET status='Qualified' WHERE id=?", (bid,))

    with pytest.raises(EnterpriseGateError) as caught:
        gates.require_qualified_beneficiary(c, org, bid)
    assert caught.value.control == "C02"


def test_a_refused_site_can_be_resurveyed_but_not_silently_requalified(db):
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)
    site_qualification.score_site(c, org, SURVEYOR, bid, scores=dict(GOOD_SCORES,
                                  implementation_readiness=5), audit=_audit(c))
    site_qualification.decide(c, org, MANAGER, bid, decision="Not Qualified",
                              notes="No access road.", audit=_audit(c))
    assert beneficiaries.get_beneficiary(c, org, bid)["status"] == "Not Qualified"

    # A road gets built. The site goes back into the queue and is surveyed again.
    beneficiaries.transition_beneficiary(c, org, MANAGER, bid, "Qualification Pending",
                                         audit=_audit(c))
    # ...but the OLD decision must not still be sitting there qualifying it by accident.
    with pytest.raises(EnterpriseGateError):
        gates.require_qualified_beneficiary(c, org, bid)


def test_a_decided_site_is_frozen(db):
    """The scorecard is the evidence for a decision already acted on. Changing it would make
    the register disagree with what is being built -- the same freeze as a template version."""
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)
    site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                  audit=_audit(c))
    site_qualification.decide(c, org, MANAGER, bid, decision="Qualified", audit=_audit(c))

    with pytest.raises(QualificationError, match="(?i)can be scored|Qualified"):
        site_qualification.score_site(c, org, SURVEYOR, bid,
                                      scores=dict(GOOD_SCORES, energy_need=10),
                                      audit=_audit(c))


def test_deciding_twice_is_refused(db):
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)
    site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                  audit=_audit(c))
    site_qualification.decide(c, org, MANAGER, bid, decision="Qualified", audit=_audit(c))

    with pytest.raises(QualificationError):
        site_qualification.decide(c, org, MANAGER, bid, decision="Not Qualified",
                                  audit=_audit(c))
    assert beneficiaries.get_beneficiary(c, org, bid)["status"] == "Qualified"


# --- 3. the scoring itself ---------------------------------------------------


def test_all_eight_criteria_are_required(db):
    """A site scored on three categories out of eight is not "37 out of 100", it is UNSCORED
    -- and it would then be ranked against sites that were fully assessed."""
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)

    with pytest.raises(QualificationError) as caught:
        site_qualification.score_site(
            c, org, SURVEYOR, bid,
            scores={"technical_suitability": 80, "energy_need": 90}, audit=_audit(c))
    message = str(caught.value)
    assert "Financial suitability" in message and "Social impact" in message


def test_every_problem_is_reported_at_once_not_one_per_round_trip(db):
    _c, _org, _other, _pid = db
    clean, problems = site_qualification.validate_scores(
        {"technical_suitability": 500, "energy_need": "abc", "social_impact": -1})
    assert clean == {}
    assert len(problems) >= 3            # out of range, not a number, and the five missing


def test_a_junk_score_cannot_scramble_the_ranking(db):
    """NaN is a float and sails through a bare range check -- and a NaN total sorts
    unpredictably, so one junk cell would quietly reorder the whole priority list."""
    _c, _org, _other, _pid = db
    for junk in (float("nan"), float("inf"), float("-inf")):
        _clean, problems = site_qualification.validate_scores(dict(GOOD_SCORES,
                                                                   energy_need=junk))
        assert problems, f"{junk!r} was accepted as a score"


def test_the_weights_make_the_total_a_real_percentage(db):
    _c, _org, _other, _pid = db
    assert sum(crit["weight"] for crit in QUALIFICATION_CRITERIA) == 100
    assert site_qualification.total_of({k: 100 for k in QUALIFICATION_CRITERION_KEYS}) == 100.0
    assert site_qualification.total_of({k: 0 for k in QUALIFICATION_CRITERION_KEYS}) == 0.0


def test_higher_is_better_on_the_risk_rows_too(db):
    """THE SIGN TRAP. If a "risk" score were read the intuitive way round (100 = lots of
    risk), the dangerous site would out-rank the safe one and nothing on the page would look
    wrong. Pin the direction: 100 = NO risk = a BETTER site."""
    _c, _org, _other, _pid = db
    safe = site_qualification.total_of(dict(GOOD_SCORES, security_risk=100,
                                            environmental_risk=100))
    dangerous = site_qualification.total_of(dict(GOOD_SCORES, security_risk=0,
                                                 environmental_risk=0))
    assert safe > dangerous, "a safe site must score HIGHER than a dangerous one"

    # And the labels must say so, because the code alone cannot tell the surveyor.
    for crit in QUALIFICATION_CRITERIA:
        if crit["key"].endswith("_risk"):
            assert "100" in crit["label"] and "NO risk" in crit["label"]


def test_an_unknown_criterion_is_refused_rather_than_silently_dropped(db):
    _c, _org, _other, _pid = db
    _clean, problems = site_qualification.validate_scores(
        dict(GOOD_SCORES, vibes=100))
    assert any("vibes" in p for p in problems)


# --- the priority list --------------------------------------------------------


def test_the_priority_list_ranks_by_score_and_puts_the_unvisited_last(db):
    c, org, _other, pid = db
    weak = _pending_site(c, org, pid, code="WEAK", name="Weak Site")
    strong = _pending_site(c, org, pid, code="STRONG", name="Strong Site")
    unvisited = _pending_site(c, org, pid, code="UNSEEN", name="Never Surveyed")

    site_qualification.score_site(c, org, SURVEYOR, weak,
                                  scores={k: 20 for k in QUALIFICATION_CRITERION_KEYS},
                                  audit=_audit(c))
    site_qualification.score_site(c, org, SURVEYOR, strong,
                                  scores={k: 95 for k in QUALIFICATION_CRITERION_KEYS},
                                  audit=_audit(c))

    listed, capped = site_qualification.priority_list(c, org, pid)
    assert capped is False
    assert [s["id"] for s in listed] == [strong, weak, unvisited]
    assert listed[0]["rank"] == 1
    # A site nobody has been to is a QUESTION, not a score of zero -- ranking it as
    # "assessed and hopeless" is how it stays unvisited forever.
    assert listed[-1]["total_score"] is None
    assert listed[-1]["rank"] is None


# --- tenancy + audit ----------------------------------------------------------


def test_another_tenants_site_is_a_c13_not_a_403(db):
    c, org, other, pid = db
    bid = _pending_site(c, org, pid)

    for call in (
        lambda: site_qualification.get_qualification(c, other, bid),
        lambda: site_qualification.score_site(c, other, SURVEYOR, bid, scores=GOOD_SCORES,
                                              audit=_audit(c)),
        lambda: site_qualification.decide(c, other, MANAGER, bid, decision="Qualified",
                                          audit=_audit(c)),
        lambda: gates.require_qualified_beneficiary(c, other, bid),
    ):
        with pytest.raises(EnterpriseGateError) as caught:
            call()
        assert caught.value.control == "C13"


def test_an_ai_cannot_qualify_a_site(db):
    """C11 -- an AI may recommend; only a human decides. Checked BEFORE anything is loaded."""
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)
    site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                  audit=_audit(c))

    with pytest.raises(EnterpriseGateError) as caught:
        site_qualification.decide(c, org, None, bid, decision="Qualified",
                                  ai_recommendation_id="rec-1", audit=_audit(c))
    assert caught.value.control == "C11"


def test_scoring_and_deciding_each_write_an_audit_row(db):
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)
    c.execute("DELETE FROM audit_logs")

    site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                  audit=_audit(c))
    site_qualification.decide(c, org, MANAGER, bid, decision="Qualified", audit=_audit(c))

    actions = [r[0] for r in c.execute(
        "SELECT action FROM audit_logs ORDER BY id").fetchall()]
    assert actions == ["ENTERPRISE_SITE_SCORED", "ENTERPRISE_SITE_QUALIFIED"]


def test_nothing_is_written_when_the_audit_write_fails(db):
    """C12 -- audit or nothing. The scorecard and its audit row commit together or not at
    all, so a Qualified site always has a trail behind it."""
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)

    def _broken_audit(*_a, **_kw):
        return None

    with pytest.raises(EnterpriseGateError) as caught:
        site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                      audit=_broken_audit)
    assert caught.value.control == "C12"
    assert site_qualification.get_qualification(c, org, bid) is None


def test_one_site_has_exactly_one_scorecard(db):
    """A re-survey UPDATES the scorecard. Two rows would be two answers to "is this site
    qualified?" and the priority list, Gate 3 and C02 could each pick a different one."""
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)

    site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                  audit=_audit(c))
    site_qualification.score_site(c, org, SURVEYOR, bid,
                                  scores=dict(GOOD_SCORES, energy_need=10),
                                  audit=_audit(c))

    n = c.execute("SELECT COUNT(*) FROM enterprise_site_qualifications "
                  " WHERE tenant_id=? AND beneficiary_id=?", (org, bid)).fetchone()[0]
    assert n == 1
    assert site_qualification.get_qualification(c, org, bid)["scores"]["energy_need"] == 10


# ---------------------------------------------------------------------------
# Regressions pinning the four findings from the Codex review of this slice.
# ---------------------------------------------------------------------------

def test_a_refused_site_can_be_surveyed_again_AND_decided_again(db):
    """Codex LOW -- and it was worse than low: the re-survey path was a DEAD END.

    A refused site kept its old decision, so `decide()`'s "already decided" guard matched the
    dead refusal and the site could never be decided again, no matter how many times it was
    re-surveyed. The road gets built, the surveyor goes back, the manager tries to approve --
    and the system says "already decided" forever. A fresh survey now clears the stale
    refusal.
    """
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)

    site_qualification.score_site(c, org, SURVEYOR, bid,
                                  scores=dict(GOOD_SCORES, implementation_readiness=5),
                                  audit=_audit(c))
    site_qualification.decide(c, org, MANAGER, bid, decision="Not Qualified",
                              notes="No access road.", audit=_audit(c))
    assert beneficiaries.get_beneficiary(c, org, bid)["status"] == "Not Qualified"

    # The road is built. Back into the queue, and surveyed afresh.
    beneficiaries.transition_beneficiary(c, org, MANAGER, bid, "Qualification Pending",
                                         audit=_audit(c))
    card = site_qualification.score_site(c, org, SURVEYOR, bid,
                                         scores=dict(GOOD_SCORES,
                                                     implementation_readiness=95),
                                         audit=_audit(c))
    assert card["decision"] is None, "a fresh survey must supersede the stale refusal"

    # ...and THIS time it can actually be approved.
    site_qualification.decide(c, org, MANAGER, bid, decision="Qualified", audit=_audit(c))
    assert beneficiaries.get_beneficiary(c, org, bid)["status"] == "Qualified"
    gates.require_qualified_beneficiary(c, org, bid)          # C02 now admits it


def test_a_scorecard_cannot_be_rewritten_underneath_an_approval(db):
    """Codex HIGH -- the status check ran BEFORE the transaction, and the UPDATE was
    unguarded. A survey saved in the gap after a manager approved the site would rewrite the
    evidence underneath the decision, leaving a Qualified site whose scorecard is not the one
    anybody approved. The write itself now refuses a Qualified card.
    """
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)
    site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                  audit=_audit(c))
    site_qualification.decide(c, org, MANAGER, bid, decision="Qualified", audit=_audit(c))

    # Simulate the race: the beneficiary status check that guards score_site is made to pass
    # (as it would have, moments before the manager committed), but the scorecard is already
    # approved. The WRITE must still refuse.
    c.execute("UPDATE enterprise_beneficiary_register SET status='Qualification Pending' "
              " WHERE id=?", (bid,))

    with pytest.raises(QualificationError, match="(?i)approved|no longer be changed"):
        site_qualification.score_site(c, org, SURVEYOR, bid,
                                      scores=dict(GOOD_SCORES, energy_need=1),
                                      audit=_audit(c))

    card = site_qualification.get_qualification(c, org, bid)
    assert card["scores"]["energy_need"] == 90, "the approved evidence must be untouched"
    assert card["decision"] == "Qualified"


def test_a_total_score_is_not_a_scorecard(db):
    """Codex MED -- C02 accepted any row with a non-NULL total, so a row carrying
    total_score=50 over an empty scores_json would qualify a site on the strength of its own
    summary. C02 exists to stop money being spent on a site nobody assessed: it asks to SEE
    the assessment."""
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)
    # A row that claims a total but shows no work.
    c.execute(
        "INSERT INTO enterprise_site_qualifications "
        "(tenant_id, beneficiary_id, scores_json, total_score) VALUES (?,?,'{}',50)",
        (org, bid),
    )

    with pytest.raises(QualificationError) as caught:
        site_qualification.decide(c, org, MANAGER, bid, decision="Qualified",
                                  audit=_audit(c))
    assert caught.value.control == "C02"
    assert "incomplete" in str(caught.value)
    assert beneficiaries.get_beneficiary(c, org, bid)["status"] == "Qualification Pending"


def test_two_surveyors_saving_the_first_scorecard_at_once_is_not_a_500(db):
    """Codex MED -- both UPDATEs matched nothing, both fell through to INSERT, and the loser
    hit the unique index as an unhandled IntegrityError. The unique index is doing its job;
    the code just has to cope with it."""
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)

    # The other surveyor's row lands between our UPDATE (0 rows) and our INSERT.
    c.execute(
        "INSERT INTO enterprise_site_qualifications "
        "(tenant_id, beneficiary_id, scores_json, total_score, scored_by_user_id) "
        "VALUES (?,?,?,?,?)",
        (org, bid, '{"technical_suitability": 1}', 1.0, SURVEYOR),
    )

    # Ours must still land, as a clean overwrite -- not an unhandled database error.
    card = site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                         audit=_audit(c))
    assert card["total_score"] == pytest.approx(80.25)
    n = c.execute("SELECT COUNT(*) FROM enterprise_site_qualifications "
                  " WHERE tenant_id=? AND beneficiary_id=?", (org, bid)).fetchone()[0]
    assert n == 1


# ---------------------------------------------------------------------------
# Regressions pinning the SUPERVISOR findings -- what the Codex pass missed.
# ---------------------------------------------------------------------------

def test_a_resurvey_landing_mid_decision_does_not_qualify_a_site_nobody_looked_at(db):
    """HIGH -- the scorecard was read OUTSIDE the transaction and the write was guarded only
    on `decision IS NULL`.

    The manager opens a scorecard showing 80.25 and presses Qualify. In the gap, the surveyor
    posts a re-survey -- perfectly legal, the site is still Pending and undecided -- dropping
    it to 12.0. The old UPDATE still matched, so the site was QUALIFIED ON EVIDENCE NO
    APPROVER EVER SAW, while the audit row faithfully recorded the 80.25 the approver did
    see. The database and its own audit trail would disagree forever about why the site was
    approved.
    """
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)
    site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                  audit=_audit(c))
    seen = site_qualification.get_qualification(c, org, bid)
    assert seen["total_score"] == pytest.approx(80.25)

    # The re-survey lands between the manager's read and the manager's write.
    site_qualification.score_site(c, org, SURVEYOR, bid,
                                  scores={k: 10 for k in QUALIFICATION_CRITERION_KEYS},
                                  audit=_audit(c))

    # Make decide() hold the STALE scorecard -- which is precisely what the race does: it
    # read 80.25 before the re-survey landed. The guarded UPDATE names the card it is
    # approving, so it must now match nothing and refuse.
    real_get = site_qualification.get_qualification
    calls = {"n": 0}

    def _stale(conn, tid, ben_id):
        calls["n"] += 1
        return seen if calls["n"] == 1 else real_get(conn, tid, ben_id)

    site_qualification.get_qualification = _stale
    try:
        with pytest.raises(QualificationError, match="(?i)re-surveyed|look again"):
            site_qualification.decide(c, org, MANAGER, bid, decision="Qualified",
                                      audit=_audit(c))
    finally:
        site_qualification.get_qualification = real_get

    assert beneficiaries.get_beneficiary(c, org, bid)["status"] == "Qualification Pending"
    assert site_qualification.get_qualification(c, org, bid)["decision"] is None


def test_the_person_who_scored_a_site_may_not_also_decide_it(db):
    """MED -- separation of duties held only because the DEFAULT role map is disjoint. A user
    granted both district_coordinator (score) and programme_manager (approve) could score a
    site 95/100 and instantly approve their own assessment, with every guard passing."""
    c, org, _other, pid = db
    # Exactly the configuration an org_admin can create today.
    tenancy.add_member(c, org, MANAGER, "district_coordinator", OFFICER)
    bid = _pending_site(c, org, pid)

    site_qualification.score_site(c, org, MANAGER, bid, scores=GOOD_SCORES, audit=_audit(c))

    with pytest.raises(QualificationError, match="(?i)you scored this site"):
        site_qualification.decide(c, org, MANAGER, bid, decision="Qualified",
                                  audit=_audit(c))
    assert beneficiaries.get_beneficiary(c, org, bid)["status"] == "Qualification Pending"


def test_the_refusal_reason_survives_a_resurvey_in_the_audit_trail(db):
    """MED (C14) -- `notes` was ONE column written by TWO acts. The manager's refusal reason
    overwrote the survey notes; the re-survey then overwrote the refusal reason. The record of
    why the programme originally turned the site away -- the exact question an appeal asks --
    was destroyed by the act of re-surveying it."""
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)
    site_qualification.score_site(c, org, SURVEYOR, bid,
                                  scores=dict(GOOD_SCORES, implementation_readiness=5),
                                  notes="Roof sound.", audit=_audit(c))
    site_qualification.decide(c, org, MANAGER, bid, decision="Not Qualified",
                              notes="No access road.", audit=_audit(c))

    card = site_qualification.get_qualification(c, org, bid)
    assert card["survey_notes"] == "Roof sound."          # two acts...
    assert card["decision_notes"] == "No access road."    # ...two columns

    # Re-survey. The row's decision is cleared -- but the reason must still be recoverable.
    beneficiaries.transition_beneficiary(c, org, MANAGER, bid, "Qualification Pending",
                                         audit=_audit(c))
    site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                  notes="Road now built.", audit=_audit(c))

    trail = c.execute(
        "SELECT details FROM audit_logs WHERE action='ENTERPRISE_SITE_NOT_QUALIFIED'"
    ).fetchone()
    assert "No access road." in str(trail[0]),         "why the programme refused the site must survive the re-survey"


def test_the_priority_list_admits_when_it_is_truncated(db):
    """MED -- the cap and the sort order COMPOUND: unscored sites sort last, so a truncated
    list drops the lowest-ranked sites AND every unvisited one -- exactly the rows the page
    exists to surface -- while looking complete."""
    c, org, _other, pid = db
    for i in range(5):
        _pending_site(c, org, pid, code=f"S{i}", name=f"Site {i}")

    listed, capped = site_qualification.priority_list(c, org, pid, limit=3)
    assert capped is True and len(listed) == 3

    listed, capped = site_qualification.priority_list(c, org, pid, limit=50)
    assert capped is False and len(listed) == 5


def test_a_score_of_zero_is_a_score_not_a_blank(db):
    """The classic falsy-zero bug: `if not value` would turn a legitimate 0 -- a site with NO
    access road at all -- into "has no score", and the suite would stay green."""
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)

    card = site_qualification.score_site(
        c, org, SURVEYOR, bid,
        scores=dict(GOOD_SCORES, implementation_readiness=0, security_risk=0),
        audit=_audit(c))

    assert card["scores"]["implementation_readiness"] == 0
    assert card["scores"]["security_risk"] == 0
    # ...and it is a COMPLETE scorecard, so C02 admits a decision on it.
    site_qualification.decide(c, org, MANAGER, bid, decision="Not Qualified",
                              audit=_audit(c))


def test_a_site_that_was_never_admitted_cannot_be_decided(db):
    """decide()'s status guard: a site still sitting at Beneficiary Registered has not been
    admitted to the programme, so there is nothing to qualify."""
    c, org, _other, pid = db
    bid = beneficiaries.create_beneficiary(
        c, org, OFFICER, pid, code="RAW", name="Unadmitted", beneficiary_type="school",
        audit=_audit(c))

    with pytest.raises(QualificationError, match="(?i)Qualification Pending"):
        site_qualification.decide(c, org, MANAGER, bid, decision="Qualified",
                                  audit=_audit(c))


# ---------------------------------------------------------------------------
# Regressions pinning the Codex ROUND-2 findings (defects in the fixes above).
# ---------------------------------------------------------------------------

def test_a_refused_site_must_be_readmitted_before_it_is_surveyed_again(db):
    """Codex round 2 -- score_site used to accept a still-`Not Qualified` site. The new scores
    cleared the refusal, but the STATUS stayed Not Qualified, and decide() only acts on a
    Pending site -- so it refused to touch it. The site ended in LIMBO: refused, with no record
    of why, and no way to ever decide it again.

    Re-admission takes `beneficiary.approve`. It is a deliberate act by somebody entitled to
    make it, not paperwork to be routed around by whoever holds the survey clipboard.
    """
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)
    site_qualification.score_site(c, org, SURVEYOR, bid,
                                  scores=dict(GOOD_SCORES, implementation_readiness=5),
                                  notes="No road.", audit=_audit(c))
    site_qualification.decide(c, org, MANAGER, bid, decision="Not Qualified",
                              notes="No access road.", audit=_audit(c))

    # The surveyor cannot simply write over the refusal.
    with pytest.raises(QualificationError, match="(?i)Qualification Pending"):
        site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                      audit=_audit(c))

    # The refusal, and the reason for it, are still there.
    card = site_qualification.get_qualification(c, org, bid)
    assert card["decision"] == "Not Qualified"
    assert card["decision_notes"] == "No access road."

    # Re-admit it -- and NOW it can be surveyed and decided again.
    beneficiaries.transition_beneficiary(c, org, MANAGER, bid, "Qualification Pending",
                                         audit=_audit(c))
    site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                  audit=_audit(c))
    site_qualification.decide(c, org, MANAGER, bid, decision="Qualified", audit=_audit(c))
    assert beneficiaries.get_beneficiary(c, org, bid)["status"] == "Qualified"


def test_the_approval_names_a_revision_not_a_timestamp(db):
    """Codex round 2 -- the optimistic lock guarded on (total_score, scored_at). SQLite's
    CURRENT_TIMESTAMP is SECOND-resolution, and eight criteria can be shuffled to the same
    weighted mean -- so a re-score within the same second, to different scores that happen to
    total the same, slipped straight through. A counter cannot be confused by either.
    """
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)

    # Two genuinely different scorecards with an IDENTICAL total.
    a = dict(GOOD_SCORES, technical_suitability=80, energy_need=90)
    b = dict(GOOD_SCORES, technical_suitability=90, energy_need=80)   # same weight (20/20)
    assert site_qualification.total_of(a) == site_qualification.total_of(b)

    site_qualification.score_site(c, org, SURVEYOR, bid, scores=a, audit=_audit(c))
    seen = site_qualification.get_qualification(c, org, bid)

    # The re-score lands in the same second, with the same total.
    site_qualification.score_site(c, org, SURVEYOR, bid, scores=b, audit=_audit(c))
    assert site_qualification.get_qualification(c, org, bid)["revision"] > seen["revision"]

    real_get = site_qualification.get_qualification
    calls = {"n": 0}

    def _stale(conn, tid, ben_id):
        calls["n"] += 1
        return seen if calls["n"] == 1 else real_get(conn, tid, ben_id)

    site_qualification.get_qualification = _stale
    try:
        with pytest.raises(QualificationError, match="(?i)re-surveyed|look again"):
            site_qualification.decide(c, org, MANAGER, bid, decision="Qualified",
                                      audit=_audit(c))
    finally:
        site_qualification.get_qualification = real_get

    assert site_qualification.get_qualification(c, org, bid)["decision"] is None


def test_a_racing_first_scorecard_is_resolved_not_left_as_a_dead_transaction(db):
    """Codex round 2 -- the IntegrityError retry ran another statement in the SAME transaction.
    On Postgres a unique violation ABORTS the transaction, so the retry would have died with
    "current transaction is aborted" and taken the audit row with it. The INSERT now sits in a
    SAVEPOINT, which un-aborts the transaction and lets the retry run.

    SQLite cannot reproduce the abort, so this pins the OUTCOME the savepoint exists to
    protect: the loser of the race still lands its survey, exactly once.
    """
    c, org, _other, pid = db
    bid = _pending_site(c, org, pid)

    # The other surveyor's row lands between our UPDATE (0 rows) and our INSERT.
    c.execute(
        "INSERT INTO enterprise_site_qualifications "
        "(tenant_id, beneficiary_id, scores_json, total_score, scored_by_user_id, revision) "
        "VALUES (?,?,?,?,?,1)",
        (org, bid, '{"technical_suitability": 1}', 1.0, SURVEYOR),
    )

    card = site_qualification.score_site(c, org, SURVEYOR, bid, scores=GOOD_SCORES,
                                         audit=_audit(c))
    assert card["total_score"] == pytest.approx(80.25)
    assert card["revision"] == 2, "the retry must bump the revision it found, not reset it"
    n = c.execute("SELECT COUNT(*) FROM enterprise_site_qualifications "
                  " WHERE tenant_id=? AND beneficiary_id=?", (org, bid)).fetchone()[0]
    assert n == 1
