"""The engineering deliverables are written by the DESIGN ENGINE, not from ticked prose.

THE OWNER'S ASK: "the app must work to produce report" -- "using existing design options".

Eleven of doc 2's 144 Key Outputs are engineering documents: the technical and financial
feasibility reports, the programme business case, the master plan / implementation manual,
the monitoring report, the consolidated programme BOQ (constants.DELIVERABLE_ENGINE). The
capital-investment engine already writes every one of them from a real design.

Until now the deliverable picker OFFERED those eleven and then wrote them from whatever
activities the operator happened to tick -- so a "Technical feasibility report" contained no
engineering at all, while the actual kWp, inverter schedule, BOQ and cash flow sat in a table
nobody read. And four of the eleven open a stage gate, which would then have opened on the
strength of that prose.

So these tests assert the two halves of the fix:
  * an engine deliverable is written FROM THE DESIGN (and carries the programme's scale, not
    one site's), and
  * when there is no approved reference design, the app REFUSES and says what to do --
    it does NOT quietly fall back to prose and hand over a hollow document that opens a gate.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from app.enterprise_programme import (
    beneficiaries, constants, documents, reports, rollout, tenancy, workflows,
)
from app.enterprise_programme.reports import ReportError


class A:
    def __call__(self, action, **kw):
        return True


class _Conn(sqlite3.Connection):
    org: str


@pytest.fixture()
def db():
    c = sqlite3.connect(":memory:", factory=_Conn)
    # web_app's get_db sets this, and reports._load_reference_project relies on it to turn the
    # project row into a dict for the engine. sqlite3.Row still supports index access, so the
    # modules that read row[0] are unaffected -- this mirrors production rather than diverging
    # from it.
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    c.execute("INSERT INTO users (id, username) VALUES (1, 'Ministry of Health')")
    tenancy.ensure_schema(c)
    workflows.ensure_schema(c)
    beneficiaries.ensure_schema(c)
    documents.ensure_schema(c)
    rollout.ensure_schema(c)
    tenancy.get_or_create_personal_tenant(c, 1, "moh")
    org = tenancy.create_organisation(c, 1, "Ministry of Health", "ministry", "Ghana")
    c.commit()
    c.org = org
    yield c
    c.close()


@pytest.fixture()
def programme(db):
    return workflows.create_programme(
        db, db.org, 1, code="GH-CLINIC", name="Rural Clinics Solar",
        design_strategy="standard", sponsor_user_id=1, country="Ghana", audit=A(),
        description="Electrifying 200 rural clinics in the Northern region.",
    )


# --------------------------------------------------------------- the mapping is real

def test_the_owners_four_documents_are_all_engine_written():
    """"technical and financial proposal, implementation plan, ... monitor" -- their words."""
    assert reports.is_engine_written("P04_D01")      # technical feasibility report
    assert reports.is_engine_written("P04_D02")      # financial feasibility report
    assert reports.is_engine_written("P05_D01")      # programme master plan
    assert reports.is_engine_written("P15_D01")      # programme performance report

    # ...and a governance narrative is NOT: a concept note is a statement of intent about a
    # programme that has not been designed yet. The activity path is right for those.
    assert not reports.is_engine_written("P01_D01")  # concept note
    assert not reports.is_engine_written("P02_D01")  # programme charter


def test_every_engine_key_exists_in_the_engine():
    """A deliverable mapped to a report key the engine does not have is a dead deliverable."""
    from new_capital_investment_routes import REPORT_KEYS

    missing = {code: key for code, key in constants.DELIVERABLE_ENGINE.items()
               if key not in REPORT_KEYS}
    assert not missing, f"deliverables mapped to a report the engine cannot write: {missing}"


# ------------------------------------------------- no design -> REFUSE, do not fake it

def test_without_a_reference_design_the_engine_REFUSES_and_says_what_to_do(db, programme):
    """The load-bearing test.

    Silently falling back to the activity path would hand the operator a "Technical
    feasibility report" written from ticked prose, with no engineering in it -- and, for the
    business case, open Gate 4 on it. Hollow evidence that looks right is the exact failure
    this whole module exists to abolish. It must refuse, and the refusal must be actionable.
    """
    with pytest.raises(ReportError) as e:
        reports.build_engine_document(db, db.org, programme, "P04_D01")

    msg = str(e.value).lower()
    assert "reference design" in msg
    assert "design page" in msg, "the refusal must tell the operator what to do about it"


def test_generate_document_refuses_the_engine_deliverable_and_writes_NOTHING(db, programme):
    """And it refuses at the point of generation, not merely in the service."""
    before = db.execute("SELECT COUNT(*) FROM enterprise_documents").fetchone()[0]

    with pytest.raises(ReportError):
        documents.generate_document(
            db, db.org, 1, programme,
            activity_codes=["P04_A01"],          # ticked, and rightly ignored
            deliverable_code="P04_D01",
            use_ai=False, audit=A(),
        )

    after = db.execute("SELECT COUNT(*) FROM enterprise_documents").fetchone()[0]
    assert after == before, "a hollow document was written anyway"


def test_a_gate_does_NOT_open_on_a_refused_engine_deliverable(db, programme):
    """P04_D08 (the business case) opens Gate 4. A refusal must leave that gate shut."""
    from app.enterprise_programme import gates

    with pytest.raises(ReportError):
        documents.generate_document(
            db, db.org, 1, programme, activity_codes=[],
            deliverable_code="P04_D08", use_ai=False, audit=A(),
        )

    row = db.execute(
        "SELECT 1 FROM enterprise_documents WHERE tenant_id=? AND programme_id=? "
        "AND doc_type='business_case'", (db.org, programme)).fetchone()
    assert row is None, "Gate 4's evidence was written despite the engine refusing"
    assert gates.GATE_OF_DOC_TYPE["business_case"] == "G04"


# ------------------------------------------- with a design -> the engine writes it

def _give_it_a_design(db, programme, *, kwp=50.0, unit_cost=120000.0, sites=3,
                      design_path="standard"):
    """Put an approved reference design + its CI project behind the programme.

    Built by hand rather than through rollout.create_reference_design, because that path
    needs an approved template version and a full CI wizard run -- neither of which this test
    is about. What it IS about is what the adapter does with a design once one exists.
    """
    db.execute(
        "CREATE TABLE IF NOT EXISTS capital_investment_projects ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, project_name TEXT,"
        " country TEXT, region TEXT, currency TEXT, target_kwp REAL,"
        " pv_config TEXT, finance_config TEXT, facility_config TEXT,"
        " technology_config TEXT, electrical_config TEXT, site_config TEXT,"
        " regulatory_config TEXT)")
    cur = db.execute(
        "INSERT INTO capital_investment_projects "
        "(user_id, project_name, country, region, currency, target_kwp, pv_config,"
        " finance_config) VALUES (?,?,?,?,?,?,?,?)",
        (1, "Rural Clinic Reference Design", "Ghana", "Northern", "GHS", kwp,
         json.dumps({"sizing": {"kwp_input": kwp}}),
         json.dumps({"computed": {}, "fx_local_per_usd": 12.0})),
    )
    project_id = cur.lastrowid

    boq = {"items": [{"description": "PV module 550W", "unit": "No.", "qty": 90,
                      "rate": 700.0}]}
    summary = {"total_cost": unit_cost, "currency": "GHS"}

    # The design row is INSERTed directly (its real columns are boq_json / summary_json), and
    # its NOT NULL template_version_id has a live FK, so a template + version must exist.
    # Going through rollout.create_reference_design instead would mean standing up the whole
    # design engine -- which is not what these tests are about: they are about what the
    # ADAPTER does with a design once one exists.
    db.execute(
        "INSERT INTO enterprise_programme_templates "
        "(tenant_id, programme_id, code, name, beneficiary_type, design_strategy,"
        " created_by_user_id) VALUES (?,?,?,?,?,?,?)",
        (db.org, programme, "T-CLINIC", "Clinic 50 kW", "clinic", "standard", 1))
    tpl_id = db.execute("SELECT id FROM enterprise_programme_templates "
                        "WHERE tenant_id=? ORDER BY id DESC LIMIT 1", (db.org,)).fetchone()[0]
    db.execute(
        "INSERT INTO enterprise_template_versions "
        "(tenant_id, template_id, version_no, status, parameters_json, created_by_user_id) "
        "VALUES (?,?,?,?,?,?)",
        (db.org, tpl_id, 1, "Approved", "{}", 1))
    tv_id = db.execute("SELECT id FROM enterprise_template_versions "
                       "WHERE tenant_id=? ORDER BY id DESC LIMIT 1", (db.org,)).fetchone()[0]

    db.execute(
        "INSERT INTO enterprise_reference_designs "
        "(tenant_id, programme_id, template_version_id, design_path, project_kind,"
        " project_id, status, kwp, boq_json, summary_json, created_by_user_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (db.org, programme, tv_id, design_path, "capital_investment", project_id,
         "Engineering Approved", kwp, json.dumps(boq), json.dumps(summary), 1),
    )
    for i in range(sites):
        db.execute(
            "INSERT INTO enterprise_beneficiary_register "
            "(tenant_id, programme_id, code, name, beneficiary_type, status,"
            " created_by_user_id) VALUES (?,?,?,?,?,?,?)",
            (db.org, programme, f"C{i + 1:03d}", f"Clinic {i + 1}", "clinic",
             "Qualified", 1))
    db.commit()
    return project_id


def test_the_engine_writes_it_and_the_report_carries_the_PROGRAMME_scale(db, programme):
    """The subtle one. The engine writes about ONE site. The ministry funds two hundred.

    A business case showing the cost of one clinic, presented as the programme's business
    case, would be accurate in every particular and wrong in its conclusion. The programme
    header states the multiplication BEFORE the reader reaches an engineering figure.
    """
    _give_it_a_design(db, programme, unit_cost=120000.0, sites=3)

    md, title = reports.build_engine_document(db, db.org, programme, "P04_D02")

    assert title == "Financial feasibility report"
    assert "Rural Clinics Solar" in md
    assert "GH-CLINIC" in md

    # The programme scale, stated up front.
    assert "Sites in scope:** 3" in md
    assert "120,000.00" in md                      # the cost per site
    assert "360,000.00" in md                      # ...and 3 x that, the programme total
    assert "reference design" in md.lower()

    # And it really did run the ENGINE, not the activity writer: the engine's own section
    # heading is present, and no activity prose is.
    assert "To strengthen this section" not in md


def test_a_generation_station_cost_is_NOT_multiplied_by_its_beneficiaries(db, programme):
    """One plant is built once. Multiplying it by its beneficiaries is a factual error.

    rollout.funding_requirement already refuses to do this; the header must not contradict it.
    """
    _give_it_a_design(db, programme, unit_cost=5_000_000.0, sites=4,
                      design_path="generation_station")

    md, _t = reports.build_engine_document(db, db.org, programme, "P04_D08")

    assert "single generation station" in md
    assert "not** multiplied" in md or "not multiplied" in md
    assert "5,000,000.00" in md
    assert "20,000,000.00" not in md, "the plant's cost was multiplied by its beneficiaries"


def test_an_engine_document_opens_its_gate_and_records_no_activities(db, programme):
    """P04_D08 is the business case: engine-written AND Gate 4's evidence."""
    from app.enterprise_programme import gates

    _give_it_a_design(db, programme)

    with pytest.raises(gates.EnterpriseGateError):
        gates.evaluate_gate(db, db.org, programme, "G04")      # shut

    doc_id = documents.generate_document(
        db, db.org, 1, programme,
        activity_codes=[],                       # none needed, and none given
        deliverable_code="P04_D08", use_ai=False, audit=A(),
    )

    gates.evaluate_gate(db, db.org, programme, "G04")          # ...and now it opens

    doc = documents.get_document(db, db.org, doc_id)
    assert doc["doc_type"] == "business_case"
    # It must not claim to answer activities it never read.
    assert json.loads(doc["activity_codes"] or "[]") == []
    assert len(doc["markdown"]) > 200


def test_zero_qualified_sites_is_flagged_LOUDLY_in_the_document(db, programme):
    """A programme with no qualified sites cannot be scaled, and must not look like it was.

    The reader must not mistake the reference design's own cost for the programme's total.
    """
    _give_it_a_design(db, programme, sites=0)

    md, _t = reports.build_engine_document(db, db.org, programme, "P04_D02")
    assert "No sites are qualified" in md
