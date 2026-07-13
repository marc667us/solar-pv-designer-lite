"""Slice 7 -- ONE design, scaled to every site.

The owner said four things, and every test in this file pins one of them:

  1. "when you are in planning the programme must open into standard or generation station
      design"                                         -> the design path comes from the
                                                         APPROVED template, and Initiation
                                                         cannot design at all.

  2. "the BOQ and everything is the same for each site"
                                                      -> a site project is a COPY of the
                                                         reference design, not a re-design.
                                                         This is the property the whole
                                                         slice exists to protect, and it is
                                                         the one a future refactor is most
                                                         likely to break, because re-running
                                                         the engine per site LOOKS more
                                                         thorough.

  3. "field assessment to be applied at each location shading"
                                                      -> the survey is RECORDED against the
                                                         site and does not touch its BOQ. If
                                                         it ever does, (2) is dead and the
                                                         sponsor's total is wrong.

  4. "funding will be sought by the programme for all the locations"
                                                      -> one number, at programme level:
                                                         reference cost x sites.

Plus the governance the module already owed: C03 (approved template), C04 (engineering
approval before ANY site is generated), C02 re-checked PER SITE on the worker path, and
C14's traceability chain.

THE ENGINES ARE FAKED HERE, ON PURPOSE. web_app cannot be imported without a Flask app, and
these tests are about the PROGRAMME's rules, not about whether calc_pv can size an array --
which has its own tests. The fake records what it was asked to do, which is precisely what
lets test_a_site_is_a_copy_not_a_redesign assert that the engine was never re-run.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from app.enterprise_programme import (
    beneficiaries, constants, gates, rollout, site_qualification, templates, tenancy,
    workflows,
)
from app.enterprise_programme.gates import EnterpriseGateError
from app.enterprise_programme.rbac import EnterprisePermissionError
from app.enterprise_programme.rollout import RolloutError
from app.security import audit as audit_mod


class _Conn(sqlite3.Connection):
    """sqlite3.Connection has no __dict__, so a plain attribute cannot be attached."""


OWNER = 1       # enterprise_owner -- onboards, holds the operational bundle
ENGINEER = 2    # engineering_manager -- engineering.approve (C04)
SURVEYOR = 3    # surveyor -- qualification.score
MANAGER = 4     # programme_manager -- qualification.approve
OUTSIDER = 5    # another organisation entirely


# --- the fake engines --------------------------------------------------------


class FakeEngines:
    """Stands in for web_app + the Generation Station module.

    It COUNTS its calls. That counter is the evidence for the slice's central claim: when a
    programme rolls out to 3 sites, `standard_designs` must still be 1. If a future change
    re-runs the design per site, that number becomes 4 and the test that asserts it is 1
    fails -- which is the only way a test can catch "the BOQ silently stopped being the same
    at every site", because both versions still produce a BOQ.
    """

    def __init__(self):
        self.standard_designs = 0
        self.station_designs = 0
        self.clones: list[dict] = []
        self._next_project_id = 100

    def _pid(self) -> int:
        self._next_project_id += 1
        return self._next_project_id

    def standard_seed(self, *, monthly_kwh, country, region, system_configuration,
                      chemistry="LiFePO4", autonomy=1):
        kwh = float(monthly_kwh or 0)
        if kwh <= 0:
            from app.enterprise_programme.engines import EngineError
            raise EngineError("the typical monthly consumption must be greater than zero")
        return ({"country": country, "region": region,
                 "system_type": "grid-tied", "monthly_kwh": kwh}, [{"wattage": 1000.0}])

    def build_standard_design(self, *, user_id, project_name, initial_data, loads):
        self.standard_designs += 1
        return {
            "project_kind": "standard",
            "project_id": self._pid(),
            "kwp": 5.0,
            "boq": {"items": [
                {"description": "PV module 550Wp", "unit": "No.", "qty": 10, "rate": 900.0},
                {"description": "Mounting rail", "unit": "m", "qty": 24, "rate": 45.0},
            ]},
            "summary": {"design_path": "standard", "pv_kw": 5.0, "num_panels": 10,
                        "total_cost": 42000.0, "currency": "GHS"},
        }

    def build_generation_station_design(self, *, user_id, project_name, kwp, country,
                                        region, currency="GHS", psh_daily=None):
        self.station_designs += 1
        return {
            "project_kind": "generation_station",
            "project_id": self._pid(),
            "kwp": float(kwp),
            "boq": {"items": [{"description": "PV module 550Wp", "unit": "No.",
                               "qty": 1818, "rate": 900.0}]},
            "summary": {"design_path": "generation_station", "pv_kw": float(kwp),
                        "total_cost": 4_500_000.0, "currency": "GHS"},
        }

    def clone_standard_to_site(self, *, user_id, project_name, reference_project_id, site,
                               conn=None):
        # `conn` is not decoration. The drainer holds a connection open across the chunk; a
        # clone that opens its own is `database is locked` on SQLite and a lock wait on
        # Postgres. The fake records it so test_the_drainer_hands_its_connection_to_the_clone
        # can assert the drainer really passes it.
        self.clones.append({"reference": reference_project_id, "site": site,
                            "name": project_name, "conn": conn})
        return self._pid()


# --- fixture -----------------------------------------------------------------


@pytest.fixture()
def db():
    os.environ.pop("DATABASE_URL", None)
    audit_mod.reset_schema_probe()

    c = sqlite3.connect(":memory:", factory=_Conn)
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    names = ((OWNER, "owen"), (ENGINEER, "edna"), (SURVEYOR, "sam"),
             (MANAGER, "musa"), (OUTSIDER, "olu"))
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
    rollout.ensure_schema(c)
    for uid, name in names:
        tenancy.get_or_create_personal_tenant(c, uid, name)

    org = tenancy.create_organisation(c, OWNER, "Ministry of Energy", "ministry")
    other = tenancy.create_organisation(c, OUTSIDER, "Rival Ministry", "ministry")
    tenancy.add_member(c, org, ENGINEER, "engineering_manager", OWNER)
    tenancy.add_member(c, org, SURVEYOR, "surveyor", OWNER)
    tenancy.add_member(c, org, MANAGER, "programme_manager", OWNER)

    pid = workflows.create_programme(c, org, OWNER, code="GH-SCH", name="Ghana Schools",
                                     sponsor_user_id=OWNER, audit=_audit(c))
    # A programme opens into design at PLANNING. Put it there.
    c.execute(
        "UPDATE enterprise_programme_registry SET current_phase_code='P03_NEEDS' "
        " WHERE tenant_id=? AND id=?", (org, pid))
    c.commit()
    yield c, org, other, pid
    c.close()
    audit_mod.reset_schema_probe()


def _audit(c):
    def _hook(action, **kw):
        return audit_mod.write_audit_event(action, conn=c, **kw)
    return _hook


BASE_PARAMS = {
    "system_configuration": "grid_tied",
    "typical_load_profile": "daytime_only",
    "standard_pv_capacities_kw": [5, 10, 2000],
    "required_beneficiary_fields": ["name"],
}


_TEMPLATE_SEQ = [0]


def _approved_template(c, org, pid, *, design_path="standard"):
    """A template version that has actually been through approval. Returns its version id.

    The code is sequenced because a template code is unique per tenant -- a test that wants
    a SECOND template would otherwise trip the uniqueness rule and report that as its
    result, which would be a test passing for the wrong reason.
    """
    _TEMPLATE_SEQ[0] += 1
    _tpl, version_id = templates.create_template(
        c, org, OWNER, code=f"T-{design_path[:4]}-{_TEMPLATE_SEQ[0]}",
        name="Standard school", beneficiary_type="school", programme_id=pid,
        audit=_audit(c))
    params = dict(BASE_PARAMS, design_path=design_path)
    templates.save_draft_parameters(c, org, OWNER, version_id, params, audit=_audit(c))
    templates.submit_for_review(c, org, OWNER, version_id, audit=_audit(c))
    templates.approve_version(c, org, OWNER, version_id, audit=_audit(c))
    return version_id


def _qualified_site(c, org, pid, code, name):
    """A beneficiary that has genuinely been surveyed AND decided. C02 asks for both."""
    bid = beneficiaries.create_beneficiary(
        c, org, OWNER, pid, code=code, name=name, beneficiary_type="school",
        fields={"name": name}, audit=_audit(c))
    beneficiaries.transition_beneficiary(
        c, org, MANAGER, bid, "Qualification Pending", audit=_audit(c))
    site_qualification.score_site(
        c, org, SURVEYOR, bid,
        scores={k: 80 for k in constants.QUALIFICATION_CRITERION_KEYS},
        audit=_audit(c))
    site_qualification.decide(c, org, MANAGER, bid, decision="Qualified",
                              audit=_audit(c))
    return bid


def _design(c, org, pid, engine, *, design_path="standard", **kw):
    version_id = _approved_template(c, org, pid, design_path=design_path)
    defaults = {"monthly_kwh": 350} if design_path == "standard" else {"design_kwp": 2000}
    defaults.update(kw)
    return rollout.create_reference_design(
        c, org, OWNER, pid, template_version_id=version_id, audit=_audit(c),
        engine=engine, **defaults)


# ---------------------------------------------------------------------------
# 1. THE DESIGN PATH COMES FROM THE APPROVED TEMPLATE
# ---------------------------------------------------------------------------


def test_a_programme_in_initiation_cannot_design_yet(db):
    """"when you are in PLANNING the programme must open into ... design"."""
    c, org, _other, pid = db
    c.execute("UPDATE enterprise_programme_registry SET current_phase_code='P01_CONCEPT' "
              " WHERE tenant_id=? AND id=?", (org, pid))
    version_id = _approved_template(c, org, pid)

    with pytest.raises(RolloutError, match="still in Initiation"):
        rollout.create_reference_design(c, org, OWNER, pid,
                                        template_version_id=version_id,
                                        monthly_kwh=350, audit=_audit(c),
                                        engine=FakeEngines())


def test_an_unapproved_template_cannot_build_anything(db):
    """C03. A Draft is a standard nobody certified; 400 sites is the wrong place to find out."""
    c, org, _other, pid = db
    _tpl, version_id = templates.create_template(
        c, org, OWNER, code="T-D", name="Draft one", beneficiary_type="school",
        programme_id=pid, audit=_audit(c))
    templates.save_draft_parameters(c, org, OWNER, version_id,
                                    dict(BASE_PARAMS, design_path="standard"),
                                    audit=_audit(c))

    with pytest.raises(EnterpriseGateError) as e:
        rollout.create_reference_design(c, org, OWNER, pid,
                                        template_version_id=version_id,
                                        monthly_kwh=350, audit=_audit(c),
                                        engine=FakeEngines())
    assert e.value.control == "C03"


def test_the_standard_path_runs_the_standard_engine(db):
    c, org, _other, pid = db
    engine = FakeEngines()
    design = _design(c, org, pid, engine, design_path="standard")

    assert engine.standard_designs == 1
    assert engine.station_designs == 0
    assert design["design_path"] == "standard"
    assert design["project_kind"] == "standard"
    assert design["status"] == "Draft"          # NOT issued until engineering says so


def test_the_generation_station_path_runs_the_generation_station_engine(db):
    """"where the programme is building a generating station use the whole generation
    station design approach with all the outputs"."""
    c, org, _other, pid = db
    engine = FakeEngines()
    design = _design(c, org, pid, engine, design_path="generation_station")

    assert engine.station_designs == 1
    assert engine.standard_designs == 0
    assert design["design_path"] == "generation_station"
    # A row in capital_investment_projects is what makes the plant open in the Generation
    # Station's own 14-step wizard, with its own SLD, twin, agents and 18 reports.
    assert design["project_kind"] == "generation_station"


def test_a_plant_capacity_must_be_one_the_template_offered(db):
    """The number the sponsor is asked to fund cannot be free text on a form."""
    c, org, _other, pid = db
    version_id = _approved_template(c, org, pid, design_path="generation_station")

    with pytest.raises(RolloutError, match="not one this template offers"):
        rollout.create_reference_design(c, org, OWNER, pid,
                                        template_version_id=version_id,
                                        design_kwp=1234, audit=_audit(c),
                                        engine=FakeEngines())


def test_a_template_from_another_programme_cannot_build_this_one(db):
    """An APPROVED template is approved for SOMETHING. C03 alone does not say for what."""
    c, org, _other, pid = db
    other_pid = workflows.create_programme(c, org, OWNER, code="GH-CLINIC",
                                           name="Clinics", sponsor_user_id=OWNER,
                                           audit=_audit(c))
    foreign_version = _approved_template(c, org, other_pid)

    with pytest.raises(RolloutError, match="different programme"):
        rollout.create_reference_design(c, org, OWNER, pid,
                                        template_version_id=foreign_version,
                                        monthly_kwh=350, audit=_audit(c),
                                        engine=FakeEngines())


def test_a_programme_holds_exactly_one_live_design(db):
    """Two live designs is not untidiness. It is 'what are we building' having two answers."""
    c, org, _other, pid = db
    engine = FakeEngines()
    _design(c, org, pid, engine)

    with pytest.raises(RolloutError, match="already has a reference design"):
        _design(c, org, pid, engine)


# ---------------------------------------------------------------------------
# 2. C04 -- NOTHING IS ISSUED WITHOUT ENGINEERING APPROVAL
# ---------------------------------------------------------------------------


def test_an_unapproved_design_rolls_out_to_nobody(db):
    """The single most expensive mistake this module could make, made impossible."""
    c, org, _other, pid = db
    engine = FakeEngines()
    design = _design(c, org, pid, engine)
    _qualified_site(c, org, pid, "KP-01", "Kpando SHS")

    with pytest.raises(RolloutError) as e:
        rollout.queue_rollout(c, org, OWNER, pid, design_id=design["id"],
                              audit=_audit(c))
    assert e.value.control == "C04"


def test_only_engineering_may_approve_a_design(db):
    c, org, _other, pid = db
    design = _design(c, org, pid, FakeEngines())

    with pytest.raises(EnterprisePermissionError):
        rollout.approve_reference_design(c, org, SURVEYOR, design["id"],
                                         audit=_audit(c))

    approved = rollout.approve_reference_design(c, org, ENGINEER, design["id"],
                                                audit=_audit(c))
    assert approved["approved"] is True
    assert approved["approved_by_user_id"] == ENGINEER


def test_approving_twice_is_not_an_error(db):
    """A double-click is not a governance event."""
    c, org, _other, pid = db
    design = _design(c, org, pid, FakeEngines())
    rollout.approve_reference_design(c, org, ENGINEER, design["id"], audit=_audit(c))
    again = rollout.approve_reference_design(c, org, ENGINEER, design["id"],
                                             audit=_audit(c))
    assert again["approved"] is True


# ---------------------------------------------------------------------------
# 3. THE HEART OF THE SLICE -- ONE DESIGN, COPIED, NOT N DESIGNS
# ---------------------------------------------------------------------------


def _rolled_out(c, org, pid, engine, n_sites=3):
    design = _design(c, org, pid, engine)
    rollout.approve_reference_design(c, org, ENGINEER, design["id"], audit=_audit(c))
    for i in range(n_sites):
        _qualified_site(c, org, pid, f"S-{i:02d}", f"School {i}")
    job_id = rollout.queue_rollout(c, org, OWNER, pid, design_id=design["id"],
                                   audit=_audit(c))
    result = rollout.drain_job(c, job_id, audit=_audit(c), engine=engine)
    return design, job_id, result


def test_a_site_is_a_copy_not_a_redesign(db):
    """THE test. "the BOQ and everything is the same for each site".

    Three sites roll out. The design engine must have run ONCE -- for the reference design --
    and three CLONES must have been taken from it. If a future refactor re-runs the engine
    per site (which will look like an improvement, because each site would get its own
    shading and its own field data), standard_designs becomes 4 and this fails.

    That is the whole point. Both versions produce a BOQ; only one produces the SAME BOQ.
    """
    c, org, _other, pid = db
    engine = FakeEngines()
    design, _job, result = _rolled_out(c, org, pid, engine, n_sites=3)

    assert engine.standard_designs == 1          # ONE design. Not four.
    assert len(engine.clones) == 3               # copied to three addresses
    assert all(cl["reference"] == design["project_id"] for cl in engine.clones)
    assert result["done"] == 3
    assert result["failed"] == 0


def test_the_scaled_boq_is_the_reference_boq_times_the_sites(db):
    """The procurement number, and C15's traceability: every quantity has ONE source line."""
    c, org, _other, pid = db
    engine = FakeEngines()
    _rolled_out(c, org, pid, engine, n_sites=3)

    boq = rollout.scaled_boq(c, org, pid)
    assert boq["sites"] == 3
    assert boq["multiplier"] == 3
    modules = next(ln for ln in boq["lines"] if "module" in ln["description"].lower())
    assert modules["unit_qty"] == 10
    assert modules["total_qty"] == 30            # 10 per site x 3 sites. Not 31, not 29.


def test_a_generation_station_is_built_once_not_once_per_beneficiary(db):
    """A programme building a power station builds ONE power station.

    Its beneficiaries are the offtakers who receive its power. Cloning the plant per offtaker
    would claim the programme is building N power stations -- and, worse, would multiply its
    cost by N in the funding total the sponsor is asked to approve.
    """
    c, org, _other, pid = db
    engine = FakeEngines()
    design = _design(c, org, pid, engine, design_path="generation_station")
    rollout.approve_reference_design(c, org, ENGINEER, design["id"], audit=_audit(c))
    for i in range(3):
        _qualified_site(c, org, pid, f"O-{i:02d}", f"Offtaker {i}")

    job_id = rollout.queue_rollout(c, org, OWNER, pid, design_id=design["id"],
                                   audit=_audit(c))
    rollout.drain_job(c, job_id, audit=_audit(c), engine=engine)

    assert engine.station_designs == 1
    assert engine.clones == []                   # nothing was cloned
    links = rollout.site_projects(c, org, pid)
    assert len(links) == 3
    # All three offtakers point at the SAME plant.
    assert {ln["project_id"] for ln in links} == {design["project_id"]}

    boq = rollout.scaled_boq(c, org, pid)
    assert boq["multiplier"] == 1                # NOT multiplied
    funding = rollout.funding_requirement(c, org, pid)
    assert funding["total"] == 4_500_000.0       # the plant's cost, not 3x it


# ---------------------------------------------------------------------------
# 4. FUNDING -- SOUGHT ONCE, BY THE PROGRAMME, FOR ALL LOCATIONS
# ---------------------------------------------------------------------------


def test_funding_is_a_programme_number_not_a_per_building_one(db):
    """"this time funding will be sought by the programme for all the locations"."""
    c, org, _other, pid = db
    engine = FakeEngines()
    _rolled_out(c, org, pid, engine, n_sites=3)

    funding = rollout.funding_requirement(c, org, pid)
    assert funding["sites"] == 3
    assert funding["unit_cost"] == 42000.0
    assert funding["total"] == 126000.0          # 42,000 x 3. ONE ask, for all of them.
    assert funding["currency"] == "GHS"
    assert funding["kwp_total"] == 15.0          # 5 kWp x 3


# ---------------------------------------------------------------------------
# 5. THE SURVEY IS EVIDENCE, NOT AN INPUT
# ---------------------------------------------------------------------------


def test_a_shading_survey_is_recorded_and_does_not_resize_the_site(db):
    """The reconciliation of the owner's two rules, pinned.

    "field assessment to be applied at each location shading" AND "the BOQ is the same for
    each site" are only both true if the survey is EVIDENCE. Site 1 comes back with 20%
    shading loss. Its BOQ must not move -- but somebody must be told.
    """
    c, org, _other, pid = db
    engine = FakeEngines()
    _rolled_out(c, org, pid, engine, n_sites=2)
    before = rollout.scaled_boq(c, org, pid)

    site = rollout.site_projects(c, org, pid)[0]
    rollout.record_site_variance(c, org, SURVEYOR, pid, site["link_id"],
                                 shading_factor=0.80,
                                 field_notes="Mango tree on the north-west roof edge.",
                                 audit=_audit(c))

    after = rollout.scaled_boq(c, org, pid)
    assert after["lines"] == before["lines"]     # the BOQ did NOT move

    surveyed = next(s for s in rollout.site_projects(c, org, pid)
                    if s["link_id"] == site["link_id"])
    assert surveyed["variance"]["shading_factor"] == 0.80
    assert surveyed["flags"], "a 20% yield loss must not pass in silence"
    assert "20%" in surveyed["flags"][0]
    assert "engineering" in surveyed["flags"][0].lower()

    # The engine was never asked to re-design anything.
    assert engine.standard_designs == 1


def test_a_survey_within_the_design_raises_no_flag(db):
    """A control that fires on everything is a control nobody reads."""
    c, org, _other, pid = db
    engine = FakeEngines()
    _rolled_out(c, org, pid, engine, n_sites=1)
    site = rollout.site_projects(c, org, pid)[0]

    rollout.record_site_variance(c, org, SURVEYOR, pid, site["link_id"],
                                 shading_factor=0.98, audit=_audit(c))
    surveyed = rollout.site_projects(c, org, pid)[0]
    assert surveyed["flags"] == []


def test_an_impossible_shading_factor_is_refused(db):
    c, org, _other, pid = db
    engine = FakeEngines()
    _rolled_out(c, org, pid, engine, n_sites=1)
    link_id = rollout.site_projects(c, org, pid)[0]["link_id"]

    for bad in (0, -0.5, 1.4, "nonsense"):
        with pytest.raises(RolloutError):
            rollout.record_site_variance(c, org, SURVEYOR, pid, link_id,
                                         shading_factor=bad, audit=_audit(c))


# ---------------------------------------------------------------------------
# 6. THE WORKER PATH RE-CHECKS EVERY GUARD
# ---------------------------------------------------------------------------


def test_a_site_unqualified_after_queueing_gets_no_project(db):
    """A site can be un-qualified between queueing a rollout and draining it.

    The queue is a statement of intent, not a licence. Whatever happens in between, the
    drainer must build only what is qualified AT THE MOMENT IT BUILDS.
    """
    c, org, _other, pid = db
    engine = FakeEngines()
    design = _design(c, org, pid, engine)
    rollout.approve_reference_design(c, org, ENGINEER, design["id"], audit=_audit(c))
    good = _qualified_site(c, org, pid, "OK-01", "Good School")
    revoked = _qualified_site(c, org, pid, "NO-01", "Revoked School")

    job_id = rollout.queue_rollout(c, org, OWNER, pid, design_id=design["id"],
                                   audit=_audit(c))

    c.execute("UPDATE enterprise_beneficiary_register SET status='Not Qualified' "
              " WHERE tenant_id=? AND id=?", (org, revoked))
    c.commit()

    rollout.drain_job(c, job_id, audit=_audit(c), engine=engine)

    generated = {s["beneficiary_id"] for s in rollout.site_projects(c, org, pid)}
    assert generated == {good}          # the revoked school got nothing


def test_the_drainer_rechecks_c02_itself_and_not_just_the_status_column(db):
    """C02 ON THE WORKER PATH -- and this is the case that needs the guard, not the query.

    `_pending_sites` selects on the beneficiary's STATUS column. That column is one UPDATE
    away from being wrong, which is exactly why C02 does not trust it: the control demands
    BOTH a Qualified status AND a scorecard carrying decision='Qualified' -- the evidence
    that a human with `qualification.approve` actually looked.

    So the dangerous row is the one whose status still SAYS Qualified while its decision has
    been withdrawn. The query happily hands that site to the drainer. Only the per-site C02
    re-check stops it -- and if somebody ever deletes that re-check as "redundant, the query
    already filters", this test is what fails.
    """
    c, org, _other, pid = db
    engine = FakeEngines()
    design = _design(c, org, pid, engine)
    rollout.approve_reference_design(c, org, ENGINEER, design["id"], audit=_audit(c))
    good = _qualified_site(c, org, pid, "OK-01", "Good School")
    withdrawn = _qualified_site(c, org, pid, "NO-01", "Withdrawn School")

    job_id = rollout.queue_rollout(c, org, OWNER, pid, design_id=design["id"],
                                   audit=_audit(c))

    # The DECISION is withdrawn; the status column is left saying Qualified. This is what a
    # half-finished revocation, or a bad UPDATE, actually looks like in a live database.
    c.execute("UPDATE enterprise_site_qualifications SET decision='Not Qualified' "
              " WHERE tenant_id=? AND beneficiary_id=?", (org, withdrawn))
    c.commit()

    # The query still offers it -- proving the guard, not the filter, is what does the work.
    offered = {s["id"] for s in rollout._pending_sites(c, org, pid, 10)}
    assert withdrawn in offered

    result = rollout.drain_job(c, job_id, audit=_audit(c), engine=engine)
    assert result["done"] == 1
    assert result["failed"] == 1

    generated = {s["beneficiary_id"] for s in rollout.site_projects(c, org, pid)}
    assert generated == {good}


def test_the_drainer_refuses_a_design_whose_template_was_superseded(db):
    """C03, re-checked on the worker path. Templates move; a queued job does not notice."""
    c, org, _other, pid = db
    engine = FakeEngines()
    design = _design(c, org, pid, engine)
    rollout.approve_reference_design(c, org, ENGINEER, design["id"], audit=_audit(c))
    _qualified_site(c, org, pid, "KP-01", "Kpando SHS")
    job_id = rollout.queue_rollout(c, org, OWNER, pid, design_id=design["id"],
                                   audit=_audit(c))

    c.execute("UPDATE enterprise_template_versions SET status='Superseded' "
              " WHERE tenant_id=? AND id=?", (org, design["template_version_id"]))
    c.commit()

    result = rollout.drain_job(c, job_id, audit=_audit(c), engine=engine)
    assert result["status"] == "Failed"
    assert rollout.site_projects(c, org, pid) == []


def test_draining_twice_does_not_build_the_same_school_twice(db):
    """The cron WILL retry -- GitHub's free scheduler drops fires and doubles them.

    A retry that builds a second project for the same school is a duplicate somebody has to
    find and delete by hand, in a register of four thousand.
    """
    c, org, _other, pid = db
    engine = FakeEngines()
    design, job_id, first = _rolled_out(c, org, pid, engine, n_sites=2)
    assert first["done"] == 2

    second = rollout.drain_job(c, job_id, audit=_audit(c), engine=engine)
    assert second["generated_now"] == 0
    assert len(rollout.site_projects(c, org, pid)) == 2
    assert len(engine.clones) == 2               # no extra clone was taken


def test_a_rollout_cannot_be_queued_twice(db):
    c, org, _other, pid = db
    engine = FakeEngines()
    design = _design(c, org, pid, engine)
    rollout.approve_reference_design(c, org, ENGINEER, design["id"], audit=_audit(c))
    _qualified_site(c, org, pid, "KP-01", "Kpando SHS")
    rollout.queue_rollout(c, org, OWNER, pid, design_id=design["id"], audit=_audit(c))

    with pytest.raises(RolloutError, match="already queued"):
        rollout.queue_rollout(c, org, OWNER, pid, design_id=design["id"],
                              audit=_audit(c))


def test_the_drainer_hands_its_connection_to_the_clone(db):
    """Found by the end-to-end route test, and it broke EVERY site.

    The drainer holds a connection open across the whole chunk. The clone used to open its
    own -- which on SQLite is `database is locked` on every single site, and on Postgres is
    two connections contending for the same rows. The chunk did not partially fail; it
    entirely failed.
    """
    c, org, _other, pid = db
    engine = FakeEngines()
    _rolled_out(c, org, pid, engine, n_sites=2)

    assert engine.clones, "nothing was cloned"
    for clone in engine.clones:
        assert clone["conn"] is not None, \
            "the drainer did not hand its connection to the clone -- this deadlocks"


def test_a_rollout_that_builds_nothing_is_FAILED_not_COMPLETED(db):
    """The second half of the same incident, and the more dangerous half.

    When every site failed, the job still reported `Completed` -- because the status logic
    said "generated == 0, so there is nothing left to do". A total failure wearing a
    success's clothes is the worst outcome available: a Failed job gets investigated, and a
    Completed one gets believed. The rollout showed green with zero projects behind it.
    """
    c, org, _other, pid = db

    class BrokenEngine(FakeEngines):
        def clone_standard_to_site(self, **kw):
            raise RuntimeError("database is locked")

    engine = BrokenEngine()
    design = _design(c, org, pid, engine)
    rollout.approve_reference_design(c, org, ENGINEER, design["id"], audit=_audit(c))
    _qualified_site(c, org, pid, "KP-01", "Kpando SHS")
    job_id = rollout.queue_rollout(c, org, OWNER, pid, design_id=design["id"],
                                   audit=_audit(c))

    result = rollout.drain_job(c, job_id, audit=_audit(c), engine=engine)

    assert result["status"] == "Failed"          # NOT "Completed"
    assert result["done"] == 0
    assert result["failed"] == 1
    assert "locked" in (result["error"] or ""), "the reason must survive, not be swallowed"

    # And the reason is on the job, where an operator will actually read it.
    job = rollout.get_job(c, org, job_id)
    assert job["status"] == "Failed"
    assert "locked" in (job["last_error"] or "")


def test_a_rollout_with_no_qualified_sites_is_refused(db):
    c, org, _other, pid = db
    engine = FakeEngines()
    design = _design(c, org, pid, engine)
    rollout.approve_reference_design(c, org, ENGINEER, design["id"], audit=_audit(c))

    with pytest.raises(RolloutError, match="no qualified sites"):
        rollout.queue_rollout(c, org, OWNER, pid, design_id=design["id"],
                              audit=_audit(c))


# ---------------------------------------------------------------------------
# 7. THE CONTROLS THIS SLICE WAS SUPPOSED TO TURN ON
# ---------------------------------------------------------------------------


def test_c04_and_c14_are_no_longer_deferred(db):
    """Both guards said "ships in slice 7". This is slice 7.

    control_summary() reads `is_deferred` off the function, so the compliance dashboard and
    the code cannot drift: if these were still stubs, the dashboard would still be telling an
    auditor the controls are not enforced -- while the module happily generated projects.
    """
    assert not getattr(gates.require_engineering_approval, "is_deferred", False)
    assert not getattr(gates.require_project_traceability, "is_deferred", False)

    live = {row["code"]: row for row in gates.control_summary()}
    assert live["C04"]["enforced_now"] is True
    assert live["C14"]["enforced_now"] is True


def test_c14_walks_the_whole_chain(db):
    """site project -> reference design -> template version -> programme, and -> beneficiary."""
    c, org, _other, pid = db
    engine = FakeEngines()
    _rolled_out(c, org, pid, engine, n_sites=1)
    link_id = rollout.site_projects(c, org, pid)[0]["link_id"]

    gates.require_project_traceability(c, org, link_id)          # does not raise

    # Break one link in the chain and it must be caught. A nullable column is nullable, and a
    # future caller that forgets it satisfies every foreign key in the database.
    c.execute("UPDATE enterprise_project_links SET reference_design_id=NULL "
              " WHERE tenant_id=? AND id=?", (org, link_id))
    with pytest.raises(EnterpriseGateError) as e:
        gates.require_project_traceability(c, org, link_id)
    assert e.value.control == "C14"
    assert "reference design" in str(e.value)


def test_c04_asks_the_design_not_the_site(db):
    c, org, _other, pid = db
    engine = FakeEngines()
    _rolled_out(c, org, pid, engine, n_sites=1)
    link_id = rollout.site_projects(c, org, pid)[0]["link_id"]

    gates.require_engineering_approval(c, org, link_id)          # approved -> passes

    design = rollout.current_design(c, org, pid)
    c.execute("UPDATE enterprise_reference_designs SET status='Draft' "
              " WHERE tenant_id=? AND id=?", (org, design["id"]))
    with pytest.raises(EnterpriseGateError) as e:
        gates.require_engineering_approval(c, org, link_id)
    assert e.value.control == "C04"


# ---------------------------------------------------------------------------
# 7b. THE CODEX SLICE-7 FINDINGS -- pinned so they cannot come back
# ---------------------------------------------------------------------------


def test_a_programme_scoped_engineer_can_actually_approve(db):
    """Codex HIGH. The button was visible and the click was refused.

    The screen decides what to render with `has_permission(..., programme_id=...)`, so an
    engineering manager granted only on THIS programme sees the Approve button. The service
    was checking tenant-wide, so the very same click came back 403. A button that is shown
    and then refuses is worse than one that was never shown: the user believes the system is
    broken, and they are right.
    """
    c, org, _other, pid = db
    scoped = 6
    c.execute("INSERT INTO users (id, username) VALUES (?,?)", (scoped, "gale"))
    tenancy.get_or_create_personal_tenant(c, scoped, "gale")
    tenancy.add_member(c, org, scoped, "surveyor", OWNER)      # tenant-wide: harmless

    # A PROGRAMME-SCOPED grant. rbac.roles_for_user has honoured scope_type='programme'
    # since slice 1 -- the schema supports it and the permission check reads it. Inserted
    # directly here because no service grants a programme-scoped role yet (members.grant is
    # tenant-wide only): a real gap, but a separate one, and it does not make this scoped
    # grant any less real to the permission layer.
    c.execute(
        "INSERT INTO enterprise_role_assignments "
        " (tenant_id, user_id, role_code, scope_type, scope_id, created_by_user_id) "
        " VALUES (?,?,?,?,?,?)",
        (org, scoped, "engineering_manager", "programme", pid, OWNER),
    )

    design = _design(c, org, pid, FakeEngines())

    # The screen would show the button...
    from app.enterprise_programme import rbac as _rbac
    assert _rbac.has_permission(c, org, scoped, "engineering.approve", programme_id=pid)

    # ...and now the click works.
    approved = rollout.approve_reference_design(c, org, scoped, design["id"],
                                                audit=_audit(c))
    assert approved["approved"] is True


def test_a_survey_cannot_reach_across_into_another_programme(db):
    """Codex MED. One tenant, two programmes -- a Ministry runs schools AND clinics.

    Scoping the survey by tenant alone let a POST made under programme A mutate a site
    belonging to programme B. Same organisation, so no tenant guard fires; different
    programme, so it is somebody else's site entirely.
    """
    c, org, _other, pid = db
    engine = FakeEngines()
    _rolled_out(c, org, pid, engine, n_sites=1)
    victim = rollout.site_projects(c, org, pid)[0]

    other_pid = workflows.create_programme(c, org, OWNER, code="GH-CLIN", name="Clinics",
                                           sponsor_user_id=OWNER, audit=_audit(c))

    # The surveyor is acting in the CLINICS programme and names the SCHOOLS site.
    with pytest.raises(RolloutError) as e:
        rollout.record_site_variance(c, org, SURVEYOR, other_pid, victim["link_id"],
                                     shading_factor=0.5, audit=_audit(c))
    assert e.value.control == "C13"

    untouched = rollout.site_projects(c, org, pid)[0]
    assert untouched["variance"] == {}, "another programme reached in and wrote to this site"


def test_the_database_refuses_a_second_active_rollout(db):
    """Codex MED. The service's look-before-insert is a race; the index is the control.

    Two operators clicking at the same moment each see no existing job, and both insert.
    They would not duplicate any PROJECT (the beneficiary link index forbids that) -- they
    would fight over the same sites, fail each other's rows, and leave two job records that
    each misreport what happened.
    """
    c, org, _other, pid = db
    engine = FakeEngines()
    design = _design(c, org, pid, engine)
    rollout.approve_reference_design(c, org, ENGINEER, design["id"], audit=_audit(c))
    _qualified_site(c, org, pid, "KP-01", "Kpando SHS")
    rollout.queue_rollout(c, org, OWNER, pid, design_id=design["id"], audit=_audit(c))

    # Bypass the service's courtesy check entirely -- go straight at the database, which is
    # exactly what the losing half of the race does.
    with pytest.raises(sqlite3.IntegrityError):
        c.execute(
            "INSERT INTO enterprise_jobs "
            " (tenant_id, programme_id, job_type, status, payload_json, total_items) "
            " VALUES (?,?,?,?,?,?)",
            (org, pid, "generate_projects", "Queued", "{}", 1),
        )


# ---------------------------------------------------------------------------
# 8. TENANT SCOPE (C13)
# ---------------------------------------------------------------------------


def test_another_organisation_cannot_see_or_touch_this_design(db):
    """C13: not-yours and not-there are the SAME answer. The routes turn both into a 404."""
    c, org, other, pid = db
    design = _design(c, org, pid, FakeEngines())

    with pytest.raises(RolloutError) as e:
        rollout.get_design(c, other, design["id"])
    assert e.value.control == "C13"

    assert rollout.current_design(c, other, pid) is None
    assert rollout.site_projects(c, other, pid) == []


def test_an_outsider_cannot_design_in_this_programme(db):
    c, org, _other, pid = db
    version_id = _approved_template(c, org, pid)

    with pytest.raises(EnterprisePermissionError):
        rollout.create_reference_design(c, org, OUTSIDER, pid,
                                        template_version_id=version_id,
                                        monthly_kwh=350, audit=_audit(c),
                                        engine=FakeEngines())


# ---------------------------------------------------------------------------
# 9. AUDIT -- C12, audit or nothing
# ---------------------------------------------------------------------------


def test_every_step_of_the_rollout_is_in_the_audit_trail(db):
    c, org, _other, pid = db
    engine = FakeEngines()
    _rolled_out(c, org, pid, engine, n_sites=2)

    actions = [r[0] for r in c.execute(
        "SELECT action FROM audit_logs WHERE action LIKE 'ENTERPRISE_%' "
        " AND (action LIKE '%DESIGN%' OR action LIKE '%ROLLOUT%' "
        "      OR action LIKE '%SITE_PROJECT%') ORDER BY id")]

    assert "ENTERPRISE_REFERENCE_DESIGN_CREATED" in actions
    assert "ENTERPRISE_DESIGN_APPROVED" in actions
    assert "ENTERPRISE_ROLLOUT_QUEUED" in actions
    assert actions.count("ENTERPRISE_SITE_PROJECT_GENERATED") == 2
    assert "ENTERPRISE_ROLLOUT_COMPLETED" in actions
