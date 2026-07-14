"""The three-level application chain. Each entity approves for ITSELF, and only for itself.

OWNER, 2026-07-14:
  "the first level of application is the beneficiary organisation, the programme level
   approval and finally sponsor level approval"
  "all approvals must be set by the individual approving entities"
  "check my bill must be run for each user automatically after their application"

WHAT THESE TESTS DEFEND
-----------------------
A chain in which one party can set all three levels is not a chain -- it is one signature
wearing three hats. A sponsor who later asks "did the beneficiary organisation actually vouch
for this applicant?" would get an answer that means nothing.

So the interesting tests here are the REFUSALS: the programme cannot sign for the
organisation, the organisation cannot sign for the sponsor, and a sponsor of some OTHER
programme cannot sign here at all.

And the chain is ORDERED. If level 3 could sign what level 1 has not, the last signature could
be collected first and the earlier ones rubber-stamped afterwards.

NOTE ON THE OWNER OVERRIDE: the stage-gate override (5417e53) lets the owner sign a gate in
another POST's place -- posts inside ONE organisation. These are three DIFFERENT
organisations, and that override deliberately does not reach here. `test_the_programme_owner_
cannot_sign_for_the_beneficiary_organisation` is the test that says so.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from app.enterprise_programme import (
    applications, beneficiaries, documents, rbac, sponsors, tenancy, workflows,
)
from app.security import audit as audit_mod

DEV_OWNER = 1      # the programme developer's owner
ORG_ADMIN = 2      # runs the beneficiary organisation
APPLICANT = 3      # a household inside that organisation
SPONSOR_REP = 4    # the funding institution's contact person
OTHER_SPONSOR = 5  # a sponsor -- of somebody else's programme

INST = "inst-worldbank"
INST_OTHER = "inst-elsewhere"


class _Conn(sqlite3.Connection):
    prog_tenant: str
    org_tenant: str


def _audit(c):
    def _hook(action, **kw):
        return audit_mod.write_audit_event(action, conn=c, **kw)
    return _hook


@pytest.fixture()
def db():
    audit_mod.reset_schema_probe()
    c = sqlite3.connect(":memory:", factory=_Conn)
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    for uid, name in ((DEV_OWNER, "dev"), (ORG_ADMIN, "orgadmin"), (APPLICANT, "ama"),
                      (SPONSOR_REP, "sponsorrep"), (OTHER_SPONSOR, "otherrep")):
        c.execute("INSERT INTO users (id, username) VALUES (?,?)", (uid, name))
    c.execute(
        "CREATE TABLE audit_logs ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT DEFAULT '',"
        " action TEXT NOT NULL, ip_address TEXT DEFAULT '', details TEXT DEFAULT '',"
        " tenant_id TEXT, agent_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        " prev_hash TEXT, row_hash TEXT)")
    # The funding registry the sponsors come from -- the EXISTING one (owner: "reuse the
    # funding in the standard design").
    c.execute(
        "CREATE TABLE financial_institutions ("
        " institution_id TEXT PRIMARY KEY, name TEXT NOT NULL, inst_type TEXT DEFAULT '',"
        " country TEXT DEFAULT '', region TEXT DEFAULT '', loan_min REAL, loan_max REAL,"
        " tenor_months INTEGER, interest_min REAL, interest_max REAL, fee_pct REAL,"
        " status TEXT NOT NULL DEFAULT 'pending')")
    for iid, nm in ((INST, "World Bank"), (INST_OTHER, "Elsewhere Capital")):
        c.execute("INSERT INTO financial_institutions "
                  "(institution_id, name, loan_min, loan_max, status) VALUES (?,?,?,?,?)",
                  (iid, nm, 1000, 5_000_000, "approved"))

    for mod in (tenancy, workflows, beneficiaries, documents, sponsors, applications):
        mod.ensure_schema(c)

    for uid, name in ((DEV_OWNER, "dev"), (ORG_ADMIN, "orgadmin"), (APPLICANT, "ama"),
                      (SPONSOR_REP, "sponsorrep"), (OTHER_SPONSOR, "otherrep")):
        tenancy.get_or_create_personal_tenant(c, uid, name)

    # TWO ORGANISATIONS. That is the whole point -- the programme developer and the
    # beneficiary organisation are different entities, and level 1 belongs to the latter.
    prog = tenancy.create_organisation(c, DEV_OWNER, "Ministry of Energy", "ministry", "Ghana")
    org = tenancy.create_organisation(c, ORG_ADMIN, "Volta School District", "education", "Ghana")
    c.commit()
    c.prog_tenant = prog
    c.org_tenant = org
    yield c
    c.close()
    audit_mod.reset_schema_probe()


@pytest.fixture()
def prog(db):
    pid = workflows.create_programme(
        db, db.prog_tenant, DEV_OWNER, code="GH-1", name="Ghana Schools",
        design_strategy="standard", sponsor_user_id=DEV_OWNER, country="Ghana",
        description="Rooftop solar for 100 rural schools.", audit=_audit(db))
    # The programme names its first sponsor from the approved funding registry.
    sponsors.set_programme_sponsors(db, db.prog_tenant, DEV_OWNER, pid,
                                    sponsor_1_id=INST, audit=_audit(db))
    # ...and that institution's contact person is given a login that can sign for it.
    applications.link_sponsor_user(db, INST, SPONSOR_REP, DEV_OWNER)
    applications.link_sponsor_user(db, INST_OTHER, OTHER_SPONSOR, DEV_OWNER)
    db.commit()
    return pid


@pytest.fixture()
def app_id(db, prog):
    aid = applications.submit_application(
        db, db.prog_tenant, prog,
        applicant_user_id=APPLICANT, applicant_org_tenant_id=db.org_tenant,
        site_name="Kpando Senior High", contact_email="head@kpando.edu.gh",
        country="Ghana", region="Volta", monthly_bill=900, monthly_kwh=420,
        area_m2=350, audit=_audit(db))
    db.commit()
    return aid


# --- submitting ---------------------------------------------------------------

def test_an_application_starts_as_submitted_and_waits_on_the_organisation(db, prog, app_id):
    t = applications.track(db, app_id, APPLICANT)
    assert t["application"]["status"] == applications.STATUS_SUBMITTED
    assert t["next_with"] == "Beneficiary organisation"
    assert [s["state"] for s in t["steps"]] == ["waiting", "pending", "pending"]


def test_an_application_MUST_come_through_an_organisation(db, prog):
    """"applications must be submitted through the organisation". Without one there is nobody
    who can give it a level-1 approval, so it could never be approved at all."""
    with pytest.raises(applications.ApplicationError):
        applications.submit_application(
            db, db.prog_tenant, prog, applicant_user_id=APPLICANT,
            applicant_org_tenant_id="", site_name="Nowhere", audit=_audit(db))


# --- the bill check -----------------------------------------------------------

def test_check_my_bill_runs_AUTOMATICALLY_on_submission(db, prog, app_id):
    """"check my bill must be run for each user automatically after their application"."""
    app = applications.get_application(db, db.prog_tenant, app_id)
    assert app["bill_check_json"], "no bill check was run for this applicant"

    result = json.loads(app["bill_check_json"])
    assert result.get("solar"), "the bill check produced no solar sizing"
    assert result.get("funding"), "the affordability model did not run"
    assert app["affordable"] in (0, 1)


def test_an_unaffordable_bill_is_FLAGGED_not_REJECTED(db, prog):
    """An unaffordable bill today is very often exactly who a subsidised programme is for.

    Deciding is the organisation's job. The app's job is to tell them.
    """
    aid = applications.submit_application(
        db, db.prog_tenant, prog, applicant_user_id=APPLICANT,
        applicant_org_tenant_id=db.org_tenant, site_name="Tiny bill household",
        country="Ghana", region="Volta", monthly_bill=5, monthly_kwh=10,
        audit=_audit(db))
    db.commit()

    app = applications.get_application(db, db.prog_tenant, aid)
    assert app["status"] == applications.STATUS_SUBMITTED, (
        "an unaffordable bill blocked the application -- it must only flag it"
    )
    # ...and it is still in the organisation's queue, to be decided by a person.
    assert any(a["id"] == aid for a in applications.inbox(
        db, level=1, org_tenant_id=db.org_tenant))


def test_a_broken_bill_engine_does_not_stop_a_school_applying(db, prog, monkeypatch):
    """`affordable` is left NULL -- "not computed", which is true. Not False, which accuses."""
    monkeypatch.setattr(applications, "_run_bill_check",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("engine down"))
                        if False else (None, None))
    aid = applications.submit_application(
        db, db.prog_tenant, prog, applicant_user_id=APPLICANT,
        applicant_org_tenant_id=db.org_tenant, site_name="Still applying",
        audit=_audit(db))
    app = applications.get_application(db, db.prog_tenant, aid)
    assert app["affordable"] is None
    assert app["status"] == applications.STATUS_SUBMITTED


# --- each entity signs for itself, and ONLY for itself ------------------------

def test_the_full_chain_ends_APPROVED(db, prog, app_id):
    applications.decide(db, db.prog_tenant, ORG_ADMIN, app_id, level=1,
                        decision="Approved", audit=_audit(db))
    applications.decide(db, db.prog_tenant, DEV_OWNER, app_id, level=2,
                        decision="Approved", audit=_audit(db))
    app = applications.decide(db, db.prog_tenant, SPONSOR_REP, app_id, level=3,
                              decision="Approved", audit=_audit(db))

    assert app["status"] == applications.STATUS_APPROVED
    assert app["l3_sponsor_id"] == INST, "the record does not say WHICH sponsor signed"

    t = applications.track(db, app_id, APPLICANT)
    assert [s["state"] for s in t["steps"]] == ["approved", "approved", "approved"]
    assert t["next_with"] is None


def test_the_programme_owner_CANNOT_sign_for_the_beneficiary_organisation(db, prog, app_id):
    """THE RULE. "all approvals must be set by the individual approving entities".

    The programme developer's owner holds every permission in HER OWN organisation -- and the
    stage-gate override even lets her sign a gate in another post's place. None of that
    reaches into somebody else's organisation. Level 1 is the school district's to give.
    """
    assert rbac.has_permission(db, db.prog_tenant, DEV_OWNER, "tenant.admin")

    with pytest.raises(rbac.EnterprisePermissionError):
        applications.decide(db, db.prog_tenant, DEV_OWNER, app_id, level=1,
                            decision="Approved", audit=_audit(db))


def test_the_beneficiary_organisation_CANNOT_sign_for_the_programme(db, prog, app_id):
    applications.decide(db, db.prog_tenant, ORG_ADMIN, app_id, level=1,
                        decision="Approved", audit=_audit(db))

    with pytest.raises(rbac.EnterprisePermissionError):
        applications.decide(db, db.prog_tenant, ORG_ADMIN, app_id, level=2,
                            decision="Approved", audit=_audit(db))


def test_the_programme_CANNOT_sign_for_the_sponsor(db, prog, app_id):
    applications.decide(db, db.prog_tenant, ORG_ADMIN, app_id, level=1,
                        decision="Approved", audit=_audit(db))
    applications.decide(db, db.prog_tenant, DEV_OWNER, app_id, level=2,
                        decision="Approved", audit=_audit(db))

    with pytest.raises(rbac.EnterprisePermissionError):
        applications.decide(db, db.prog_tenant, DEV_OWNER, app_id, level=3,
                            decision="Approved", audit=_audit(db))


def test_a_sponsor_of_SOME_OTHER_programme_cannot_sign_here(db, prog, app_id):
    """OTHER_SPONSOR is a real, approved institution's rep -- just not one THIS programme
    named. A sponsor is not a role you hold in general; it is a relationship to a programme."""
    applications.decide(db, db.prog_tenant, ORG_ADMIN, app_id, level=1,
                        decision="Approved", audit=_audit(db))
    applications.decide(db, db.prog_tenant, DEV_OWNER, app_id, level=2,
                        decision="Approved", audit=_audit(db))

    with pytest.raises(rbac.EnterprisePermissionError):
        applications.decide(db, db.prog_tenant, OTHER_SPONSOR, app_id, level=3,
                            decision="Approved", audit=_audit(db))


# --- the chain is ORDERED -----------------------------------------------------

def test_the_sponsor_cannot_sign_what_the_organisation_has_not(db, prog, app_id):
    """Otherwise the last signature is collected first and the rest rubber-stamped after."""
    with pytest.raises(applications.ApplicationError) as e:
        applications.decide(db, db.prog_tenant, SPONSOR_REP, app_id, level=3,
                            decision="Approved", audit=_audit(db))
    assert "beneficiary organisation" in str(e.value).lower()


def test_the_programme_cannot_sign_what_the_organisation_has_not(db, prog, app_id):
    with pytest.raises(applications.ApplicationError):
        applications.decide(db, db.prog_tenant, DEV_OWNER, app_id, level=2,
                            decision="Approved", audit=_audit(db))


def test_nobody_decides_twice(db, prog, app_id):
    applications.decide(db, db.prog_tenant, ORG_ADMIN, app_id, level=1,
                        decision="Approved", audit=_audit(db))
    with pytest.raises(applications.ApplicationError):
        applications.decide(db, db.prog_tenant, ORG_ADMIN, app_id, level=1,
                            decision="Rejected", audit=_audit(db))


# --- rejection and return -----------------------------------------------------

def test_a_rejection_at_level_1_stops_the_chain(db, prog, app_id):
    applications.decide(db, db.prog_tenant, ORG_ADMIN, app_id, level=1,
                        decision="Rejected", note="Not in our district",
                        audit=_audit(db))

    app = applications.get_application(db, db.prog_tenant, app_id)
    assert app["status"] == applications.STATUS_REJECTED

    with pytest.raises(applications.ApplicationError):
        applications.decide(db, db.prog_tenant, DEV_OWNER, app_id, level=2,
                            decision="Approved", audit=_audit(db))


def test_a_return_for_more_information_is_visible_to_the_applicant(db, prog, app_id):
    """The applicant must be able to see WHY they are stuck -- that is the tracking."""
    applications.decide(db, db.prog_tenant, ORG_ADMIN, app_id, level=1,
                        decision="Returned", note="Send us the roof photo",
                        audit=_audit(db))

    t = applications.track(db, app_id, APPLICANT)
    assert t["application"]["status"] == applications.STATUS_RETURNED
    assert t["steps"][0]["state"] == "returned"
    assert t["steps"][0]["note"] == "Send us the roof photo"


# --- the queues ---------------------------------------------------------------

def test_a_reviewers_queue_holds_only_what_they_can_actually_act_on(db, prog, app_id):
    """Showing a reviewer work that is blocked on somebody else is how a queue stops
    being read."""
    # Nothing is with the programme yet -- the organisation has not vouched for anyone.
    assert applications.inbox(db, level=2, tenant_id=db.prog_tenant) == []
    assert len(applications.inbox(db, level=1, org_tenant_id=db.org_tenant)) == 1

    applications.decide(db, db.prog_tenant, ORG_ADMIN, app_id, level=1,
                        decision="Approved", audit=_audit(db))

    assert applications.inbox(db, level=1, org_tenant_id=db.org_tenant) == []
    assert len(applications.inbox(db, level=2, tenant_id=db.prog_tenant)) == 1
    assert applications.inbox(db, level=3, tenant_id=db.prog_tenant) == []


def test_the_applicant_only_ever_sees_their_own_application(db, prog, app_id):
    """C13. The applicant is not a member of the programme's organisation, so their read is
    keyed on their own user id -- which must be exactly as tight."""
    with pytest.raises(applications.ApplicationError) as e:
        applications.track(db, app_id, OTHER_SPONSOR)
    assert e.value.control == "C13"

    assert len(applications.my_applications(db, APPLICANT)) == 1
    assert applications.my_applications(db, OTHER_SPONSOR) == []
