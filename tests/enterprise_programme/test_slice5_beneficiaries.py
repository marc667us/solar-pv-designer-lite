"""Slice 5 -- the beneficiary register and the bulk importer.

Two properties carry this slice, and the tests are grouped around them:

  1. REGISTERING IS NOT APPROVING. A field officer with `beneficiary.import` can put 4000
     rows into the register. Only `beneficiary.approve` decides the programme will actually
     serve any of them. Gate 3 wants evidence of the SECOND act, not the first.

  2. AN IMPORT IS STAGED, NEVER APPLIED. Nothing reaches the register until an operator has
     seen exactly what would happen -- which rows are broken, which are already there, and
     why. A 4000-row spreadsheet with 12 bad rows must not be a choice between importing
     nothing and importing the mess.
"""

from __future__ import annotations

import io
import os
import sqlite3

import pytest

from app.enterprise_programme import (
    beneficiaries, imports, tenancy, workflows,
)
from app.enterprise_programme.beneficiaries import BeneficiaryError
from app.enterprise_programme.constants import BENEFICIARY_FIELD_SPEC, BENEFICIARY_FIELDS
from app.enterprise_programme.gates import EnterpriseGateError
from app.enterprise_programme.imports import ImportError_
from app.enterprise_programme.rbac import EnterprisePermissionError
from app.security import audit as audit_mod


class _Conn(sqlite3.Connection):
    """sqlite3.Connection has no __dict__, so a plain attribute cannot be attached."""


OFFICER = 1    # beneficiary.import  (beneficiary_officer) -- collects the data
MANAGER = 2    # beneficiary.approve (programme_manager)   -- decides who is served
OUTSIDER = 3   # a member of another organisation entirely
OWNER = 4      # created the org, so holds every Release-1 role (ONBOARDING_OWNER_ROLES)


@pytest.fixture()
def db():
    """SQLite with the enterprise schema, two orgs, a programme, three users."""
    os.environ.pop("DATABASE_URL", None)
    audit_mod.reset_schema_probe()

    c = sqlite3.connect(":memory:", factory=_Conn)
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    for uid, name in ((OFFICER, "olivia"), (MANAGER, "musa"), (OUTSIDER, "olu"),
                      (OWNER, "owen")):
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
    for uid, name in ((OFFICER, "olivia"), (MANAGER, "musa"), (OUTSIDER, "olu"),
                      (OWNER, "owen")):
        tenancy.get_or_create_personal_tenant(c, uid, name)

    # THE ORG CREATOR IS NOT A USABLE SoD ACTOR (slice 6.5). Onboarding grants the creator
    # every Release-1 role (constants.ONBOARDING_OWNER_ROLES), because a one-person
    # organisation IS every authority in it. So OWNER creates the org, and the officer who
    # registers and the manager who approves are ordinary members holding one role each --
    # otherwise "the officer who registers cannot approve" would only be passing because
    # the creator happened to be powerless, which is the bug this slice fixes.
    org = tenancy.create_organisation(c, OWNER, "Ministry of Energy", "ministry")
    other = tenancy.create_organisation(c, OUTSIDER, "Rival Ministry", "ministry")

    tenancy.add_member(c, org, OFFICER, "beneficiary_officer", OWNER)
    tenancy.add_member(c, org, MANAGER, "programme_manager", OWNER)

    pid = workflows.create_programme(c, org, OWNER, code="GH-SCH", name="Ghana Schools",
                                     sponsor_user_id=OWNER, audit=_audit(c))
    c.commit()
    yield c, org, other, pid
    c.close()
    audit_mod.reset_schema_probe()


def _audit(c):
    def _hook(action, **kw):
        return audit_mod.write_audit_event(action, conn=c, **kw)
    return _hook


GOOD_FIELDS = {
    "region": "Volta",
    "district": "Kpando",
    "community": "Kpando",
    "gps_coordinates": "6.9986, 0.2926",
    "ownership": "government",
    "building_type": "compound",
    "occupancy": "820",
    "existing_energy_source": "grid_generator",
    "electricity_consumption": "1450",
    "roof_area": "900",
    "social_impact_class": "high",
}


def _site(c, org, pid, *, code="KPANDO-SHS", name="Kpando Senior High", **overrides):
    fields = dict(GOOD_FIELDS)
    fields.update(overrides)
    return beneficiaries.create_beneficiary(
        c, org, OFFICER, pid, code=code, name=name, beneficiary_type="school",
        fields=fields, audit=_audit(c),
    )


# --- registering is not approving -------------------------------------------


def test_a_site_enters_the_register_unapproved(db):
    c, org, _other, pid = db
    bid = _site(c, org, pid)
    site = beneficiaries.get_beneficiary(c, org, bid)
    assert site["status"] == "Beneficiary Registered"
    assert site["approved_by_user_id"] is None


def test_the_officer_who_registers_cannot_approve(db):
    """The person who collects the data does not decide the programme will serve the site."""
    c, org, _other, pid = db
    bid = _site(c, org, pid)
    with pytest.raises(EnterprisePermissionError):
        beneficiaries.transition_beneficiary(
            c, org, OFFICER, bid, "Qualification Pending", audit=_audit(c)
        )

    beneficiaries.transition_beneficiary(
        c, org, MANAGER, bid, "Qualification Pending", audit=_audit(c)
    )
    site = beneficiaries.get_beneficiary(c, org, bid)
    assert site["status"] == "Qualification Pending"
    assert site["approved_by_user_id"] == MANAGER


def test_the_manager_who_approves_cannot_register(db):
    c, org, _other, pid = db
    with pytest.raises(EnterprisePermissionError):
        beneficiaries.create_beneficiary(
            c, org, MANAGER, pid, code="X", name="X", beneficiary_type="school",
            audit=_audit(c),
        )


def test_an_ai_recommendation_cannot_admit_a_site(db):
    """C11 -- an AI recommendation is evidence, never the decision."""
    c, org, _other, pid = db
    bid = _site(c, org, pid)
    with pytest.raises(EnterpriseGateError) as e:
        beneficiaries.transition_beneficiary(
            c, org, None, bid, "Qualification Pending", ai_recommendation_id=7,
            audit=_audit(c),
        )
    assert e.value.control == "C11"


def test_a_site_cannot_be_hand_waved_into_qualified(db):
    """Slice 6 owns qualification. Until it ships, marking a site Qualified by hand would
    walk straight around control C02 before C02 has anything to say."""
    c, org, _other, pid = db
    bid = _site(c, org, pid)
    beneficiaries.transition_beneficiary(
        c, org, MANAGER, bid, "Qualification Pending", audit=_audit(c)
    )
    with pytest.raises(EnterpriseGateError) as e:
        beneficiaries.transition_beneficiary(
            c, org, MANAGER, bid, "Qualified", audit=_audit(c)
        )
    assert e.value.control == "C02"


def test_an_illegal_transition_is_refused(db):
    c, org, _other, pid = db
    bid = _site(c, org, pid)
    beneficiaries.transition_beneficiary(c, org, MANAGER, bid, "Rejected",
                                         audit=_audit(c))
    with pytest.raises(BeneficiaryError, match="cannot become"):
        beneficiaries.transition_beneficiary(
            c, org, MANAGER, bid, "Qualification Pending", audit=_audit(c)
        )


# THE OLD GATE 3 TEST WAS DELETED HERE (Rev 4, 2026-07-16).
#
# `test_gate_3_demands_an_approved_beneficiary_not_just_a_document` asserted that the old
# G03 (Needs Assessment Approval) reached into the beneficiary register and refused to open
# while it held no APPROVED site -- "importing 4000 rows is not a decision to serve them".
#
# Revision 4 has no such gate and no such predicate. Its five gates each demand exactly one
# thing -- their phase's own approval document -- plus the named authority's signature
# (gates.GATE_PREDICATES, and the comment above it says so explicitly: the old per-gate
# evidence predicates "are GONE rather than remapped"). There is no Rev 4 gate to repoint
# this test at, so the property it guarded no longer exists rather than having moved.
#
# The register's own rules are untouched and still tested above: a site cannot skip
# Qualification Pending, an illegal transition is refused, and only the qualifying role may
# make one. What is gone is a GATE consulting the register.


# --- the field spec is the field spec ---------------------------------------


def test_the_register_can_hold_every_field_a_template_may_demand(db):
    """A template declares `required_beneficiary_fields` from BENEFICIARY_FIELDS. If the
    register could not HOLD one of them, that template would produce a site that can never
    qualify, with nothing in the UI to explain why."""
    spec_keys = {f["key"] for f in BENEFICIARY_FIELD_SPEC}
    template_keys = {code for code, _ in BENEFICIARY_FIELDS}
    assert spec_keys == template_keys

    c, _org, _other, _pid = db
    columns = {r[1] for r in c.execute(
        "PRAGMA table_info(enterprise_beneficiary_register)").fetchall()}
    assert spec_keys <= columns, f"the register cannot hold: {spec_keys - columns}"


# --- validation --------------------------------------------------------------


def test_a_value_that_was_never_offered_is_refused(db):
    c, org, _other, pid = db
    with pytest.raises(BeneficiaryError, match="ownership"):
        _site(c, org, pid, ownership="belongs_to_the_crown")


def test_gps_is_parsed_into_real_numbers(db):
    c, org, _other, pid = db
    bid = _site(c, org, pid)
    site = beneficiaries.get_beneficiary(c, org, bid)
    assert site["latitude"] == pytest.approx(6.9986)
    assert site["longitude"] == pytest.approx(0.2926)


def test_an_impossible_coordinate_is_refused(db):
    c, org, _other, pid = db
    with pytest.raises(BeneficiaryError, match="not a coordinate"):
        _site(c, org, pid, gps_coordinates="91.0, 0.0")      # latitude > 90
    with pytest.raises(BeneficiaryError, match="not a coordinate"):
        _site(c, org, pid, gps_coordinates="Kpando")


def test_nan_is_not_a_roof_area(db):
    """float('NaN') SUCCEEDS and NaN < 0 is False -- the same hole Codex found in slice 4."""
    c, org, _other, pid = db
    with pytest.raises(BeneficiaryError, match="not a finite number"):
        _site(c, org, pid, roof_area="NaN")


def test_a_duplicate_code_is_refused(db):
    c, org, _other, pid = db
    _site(c, org, pid)
    with pytest.raises(BeneficiaryError, match="already in this programme"):
        _site(c, org, pid)


# --- editing -----------------------------------------------------------------


def test_a_registered_site_can_be_corrected(db):
    c, org, _other, pid = db
    bid = _site(c, org, pid)
    updated = beneficiaries.update_beneficiary(
        c, org, OFFICER, bid, {"roof_area": "1200"}, audit=_audit(c)
    )
    assert updated["roof_area"] == 1200


def test_a_generated_site_can_no_longer_be_edited(db):
    """Once a project exists, the record is the specification of something being built."""
    c, org, _other, pid = db
    bid = _site(c, org, pid)
    c.execute("UPDATE enterprise_beneficiary_register SET status='Project Generated' WHERE id=?",
              (bid,))
    with pytest.raises(BeneficiaryError, match="can no longer be edited"):
        beneficiaries.update_beneficiary(c, org, OFFICER, bid, {"roof_area": "1"},
                                         audit=_audit(c))


# --- tenant scope (C13) ------------------------------------------------------


def test_another_tenants_beneficiary_does_not_exist_for_you(db):
    c, org, other, pid = db
    bid = _site(c, org, pid)
    with pytest.raises(BeneficiaryError) as e:
        beneficiaries.get_beneficiary(c, other, bid)
    assert e.value.control == "C13"


def test_a_cross_tenant_write_is_404_shaped_even_without_permission(db):
    """C13 is decided BEFORE authz: a 403 would confirm the record exists."""
    c, org, other, pid = db
    bid = _site(c, org, pid)
    with pytest.raises(BeneficiaryError) as e:
        beneficiaries.update_beneficiary(c, other, OUTSIDER, bid, {"roof_area": "1"},
                                         audit=_audit(c))
    assert e.value.control == "C13"


def test_registering_into_another_tenants_programme_is_404_shaped(db):
    c, org, other, pid = db
    with pytest.raises(BeneficiaryError) as e:
        beneficiaries.create_beneficiary(
            c, other, OUTSIDER, pid, code="X", name="X", beneficiary_type="school",
            audit=_audit(c),
        )
    assert e.value.control == "C13"


def test_the_register_never_leaks_across_tenants(db):
    c, org, other, pid = db
    _site(c, org, pid)
    assert len(beneficiaries.list_beneficiaries(c, org, pid)) == 1
    assert beneficiaries.list_beneficiaries(c, other, pid) == []


# --- C12 ---------------------------------------------------------------------


def test_a_failed_audit_rolls_the_registration_back(db):
    c, org, _other, pid = db

    def broken(action, **kw):
        return False

    with pytest.raises(EnterpriseGateError) as e:
        beneficiaries.create_beneficiary(
            c, org, OFFICER, pid, code="NOPE", name="Nope", beneficiary_type="school",
            audit=broken,
        )
    assert e.value.control == "C12"
    assert c.execute(
        "SELECT COUNT(*) FROM enterprise_beneficiary_register WHERE code='NOPE'"
    ).fetchone()[0] == 0


# =============================================================================
# THE IMPORTER
# =============================================================================


CSV = (
    "School Name,Site Code,Region,District,Town,Students,Monthly kWh,Roof Area (m2),GPS\n"
    "Kpando Senior High,KP-01,Volta,Kpando,Kpando,820,1450,900,\"6.9986, 0.2926\"\n"
    "Hohoe Technical,HO-02,Volta,Hohoe,Hohoe,610,980,700,\"7.1519, 0.4736\"\n"
    "Ho Presbyterian,HO-03,Volta,Ho,Ho,450,720,540,\"6.6110, 0.4710\"\n"
).encode()


def _upload(c, org, pid, data=CSV, filename="schools.csv", default_type="school"):
    headers, rows = imports.parse_file(filename, data)
    return imports.stage_import(
        c, org, OFFICER, pid, filename=filename, headers=headers, rows=rows,
        mapping=imports.auto_map(headers), default_type=default_type, audit=_audit(c),
    )


def test_staging_writes_nothing_to_the_register(db):
    """THE property. An operator must see what would happen before any of it happens."""
    c, org, _other, pid = db
    batch_id = _upload(c, org, pid)

    assert c.execute(
        "SELECT COUNT(*) FROM enterprise_beneficiary_register").fetchone()[0] == 0

    batch = imports.get_batch(c, org, batch_id)
    assert batch["total_rows"] == 3
    assert batch["valid_rows"] == 3
    assert batch["error_rows"] == 0
    assert batch["status"] == "Staged"


def test_the_headers_are_auto_mapped(db):
    """'School Name' -> name, 'Town' -> community, 'Roof Area (m2)' -> roof_area."""
    headers, _rows = imports.parse_file("schools.csv", CSV)
    mapping = imports.auto_map(headers)
    assert mapping["School Name"] == "name"
    assert mapping["Site Code"] == "code"
    assert mapping["Town"] == "community"
    assert mapping["Students"] == "occupancy"
    assert mapping["Monthly kWh"] == "electricity_consumption"
    assert mapping["Roof Area (m2)"] == "roof_area"
    assert mapping["GPS"] == "gps_coordinates"


def test_committing_creates_the_beneficiaries(db):
    c, org, _other, pid = db
    batch_id = _upload(c, org, pid)
    result = imports.commit_batch(c, org, OFFICER, batch_id, audit=_audit(c))

    assert result["imported"] == 3
    register = beneficiaries.list_beneficiaries(c, org, pid)
    assert {b["code"] for b in register} == {"KP-01", "HO-02", "HO-03"}

    kpando = next(b for b in register if b["code"] == "KP-01")
    assert kpando["community"] == "Kpando"
    assert kpando["occupancy"] == 820
    assert kpando["roof_area"] == 900
    assert kpando["latitude"] == pytest.approx(6.9986)
    # ...and imported is not approved.
    assert kpando["status"] == "Beneficiary Registered"
    assert kpando["import_batch_id"] == batch_id


def test_a_bad_row_does_not_take_the_file_down_with_it(db):
    """The whole reason for staging: 1 broken row out of 3 must not cost the other 2."""
    c, org, _other, pid = db
    bad = (
        "School Name,Site Code,Roof Area (m2)\n"
        "Good School,GS-01,900\n"
        "Broken School,BS-02,not-a-number\n"
        "Other School,OS-03,700\n"
    ).encode()
    batch_id = _upload(c, org, pid, data=bad, filename="mixed.csv")

    batch = imports.get_batch(c, org, batch_id)
    assert batch["valid_rows"] == 2
    assert batch["error_rows"] == 1

    broken = next(r for r in batch["rows"] if r["status"] == "Error")
    assert broken["row_no"] == 2
    assert "roof area" in " ".join(broken["errors"]).lower()

    result = imports.commit_batch(c, org, OFFICER, batch_id, audit=_audit(c))
    assert result["imported"] == 2
    assert {b["code"] for b in beneficiaries.list_beneficiaries(c, org, pid)} == {
        "GS-01", "OS-03"}


def test_re_importing_the_same_file_is_not_a_second_register(db):
    """The unique code is what makes this safe. Every row comes back Duplicate."""
    c, org, _other, pid = db
    imports.commit_batch(c, org, OFFICER, _upload(c, org, pid), audit=_audit(c))

    second = _upload(c, org, pid)
    batch = imports.get_batch(c, org, second)
    assert batch["duplicate_rows"] == 3
    assert batch["valid_rows"] == 0

    result = imports.commit_batch(c, org, OFFICER, second, audit=_audit(c))
    assert result["imported"] == 0
    assert len(beneficiaries.list_beneficiaries(c, org, pid)) == 3


def test_duplicates_can_be_imported_deliberately(db):
    """Skipped by DEFAULT, not forbidden -- the operator has seen them and may insist."""
    c, org, _other, pid = db
    imports.commit_batch(c, org, OFFICER, _upload(c, org, pid), audit=_audit(c))

    second = _upload(c, org, pid)
    result = imports.commit_batch(c, org, OFFICER, second, include_duplicates=True,
                                  audit=_audit(c))
    # The unique code still refuses them at the database -- which is the point: the register
    # is protected even when the operator overrides the warning. They are reported as
    # failures, with the reason, not silently dropped.
    assert result["imported"] == 0
    assert result["failed"] == 3
    assert len(beneficiaries.list_beneficiaries(c, org, pid)) == 3


def test_a_row_with_no_code_gets_a_stable_one_derived_from_its_content(db):
    """Stable MATTERS: derived from the row's POSITION, a sorted spreadsheet would import
    twice. Derived from its content, it is the same code every time."""
    c, org, _other, pid = db
    no_code = (
        "School Name,Town\n"
        "Kpando Senior High,Kpando\n"
    ).encode()
    first = imports.get_batch(c, org, _upload(c, org, pid, data=no_code))
    assert first["rows"][0]["mapped"]["code"] == "KPANDO-KPANDO-SENIOR-HIGH"

    imports.commit_batch(c, org, OFFICER, first["id"], audit=_audit(c))

    # The same file again -- and the derived code catches it as a duplicate.
    second = imports.get_batch(c, org, _upload(c, org, pid, data=no_code))
    assert second["duplicate_rows"] == 1


def test_a_remap_re_checks_every_row_against_the_original_file(db):
    """The operator argues with the mapping, not with the spreadsheet. The raw row is kept
    precisely so they never have to re-upload."""
    c, org, _other, pid = db
    ambiguous = (
        "School Name,Location\n"
        "Kpando Senior High,Kpando\n"
    ).encode()
    batch_id = _upload(c, org, pid, data=ambiguous)

    # 'Location' is not auto-mapped -- it is genuinely ambiguous, so we do not guess.
    batch = imports.get_batch(c, org, batch_id)
    assert "Location" not in batch["column_mapping"]
    assert batch["rows"][0]["mapped"].get("community") is None

    imports.restage_batch(
        c, org, OFFICER, batch_id,
        mapping={"School Name": "name", "Location": "community"},
        default_type="school", audit=_audit(c),
    )
    batch = imports.get_batch(c, org, batch_id)
    assert batch["rows"][0]["mapped"]["community"] == "Kpando"
    assert batch["valid_rows"] == 1


def test_a_committed_batch_cannot_be_committed_again(db):
    c, org, _other, pid = db
    batch_id = _upload(c, org, pid)
    imports.commit_batch(c, org, OFFICER, batch_id, audit=_audit(c))
    with pytest.raises(ImportError_, match="already Committed"):
        imports.commit_batch(c, org, OFFICER, batch_id, audit=_audit(c))
    assert len(beneficiaries.list_beneficiaries(c, org, pid)) == 3


def test_a_committed_batch_cannot_be_remapped(db):
    """Its rows are now the provenance of real beneficiaries. Rewriting them would make the
    register's history a fiction."""
    c, org, _other, pid = db
    batch_id = _upload(c, org, pid)
    imports.commit_batch(c, org, OFFICER, batch_id, audit=_audit(c))
    with pytest.raises(ImportError_, match="no longer be changed"):
        imports.restage_batch(c, org, OFFICER, batch_id, mapping={}, audit=_audit(c))


def test_cancelling_writes_nothing(db):
    c, org, _other, pid = db
    batch_id = _upload(c, org, pid)
    imports.cancel_batch(c, org, OFFICER, batch_id, audit=_audit(c))
    assert imports.get_batch(c, org, batch_id)["status"] == "Cancelled"
    assert beneficiaries.list_beneficiaries(c, org, pid) == []
    with pytest.raises(ImportError_):
        imports.commit_batch(c, org, OFFICER, batch_id, audit=_audit(c))


def test_a_manager_cannot_import(db):
    """`beneficiary.approve` is not `beneficiary.import`. They are different jobs."""
    c, org, _other, pid = db
    headers, rows = imports.parse_file("schools.csv", CSV)
    with pytest.raises(EnterprisePermissionError):
        imports.stage_import(c, org, MANAGER, pid, filename="s.csv", headers=headers,
                             rows=rows, mapping=imports.auto_map(headers),
                             default_type="school", audit=_audit(c))


def test_another_tenants_import_does_not_exist_for_you(db):
    c, org, other, pid = db
    batch_id = _upload(c, org, pid)
    with pytest.raises(ImportError_) as e:
        imports.get_batch(c, other, batch_id)
    assert e.value.control == "C13"


def test_an_oversized_file_is_refused_not_truncated(db):
    """Importing the first 2000 rows of a 5000-row file and reporting success is the worst
    possible outcome: nobody would go looking for the other 3000."""
    big = "Name\n" + "".join(f"School {i}\n" for i in range(2500))
    with pytest.raises(ImportError_, match="limit is 2000"):
        imports.parse_file("big.csv", big.encode())


def test_an_unsupported_file_type_is_refused(db):
    with pytest.raises(ImportError_, match="unsupported file type"):
        imports.parse_file("schools.pdf", b"%PDF-1.4")


def test_an_xlsx_imports_too(db):
    c, org, _other, pid = db
    openpyxl = pytest.importorskip("openpyxl")

    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["School Name", "Site Code", "Town", "Students"])
    sheet.append(["Kpando Senior High", "KP-01", "Kpando", 820])
    buffer = io.BytesIO()
    book.save(buffer)

    batch_id = _upload(c, org, pid, data=buffer.getvalue(), filename="schools.xlsx")
    result = imports.commit_batch(c, org, OFFICER, batch_id, audit=_audit(c))
    assert result["imported"] == 1
    site = beneficiaries.list_beneficiaries(c, org, pid)[0]
    assert site["name"] == "Kpando Senior High"
    assert site["occupancy"] == 820      # Excel hands this back as a float; coerced once


def test_a_mapping_onto_an_unknown_field_is_refused(db):
    """The operator chose it, so the operator is told -- rather than the column silently
    vanishing."""
    c, org, _other, pid = db
    headers, rows = imports.parse_file("schools.csv", CSV)
    with pytest.raises(ImportError_, match="unknown field"):
        imports.stage_import(c, org, OFFICER, pid, filename="s.csv", headers=headers,
                             rows=rows, mapping={"School Name": "favourite_colour"},
                             audit=_audit(c))


def test_an_import_writes_ONE_audit_row_for_the_batch_not_one_per_row(db):
    """C12 for a bulk import is satisfied per BATCH, and it must be (Supervisor 6.5, HIGH).

    This test asserted 3 x ENTERPRISE_BENEFICIARY_REGISTERED until slice 6.5, and that
    per-row audit was a live production hazard: on Postgres every audit write takes
    `pg_advisory_xact_lock` on a CONSTANT key shared by every audit writer in SolarPro, and
    the lock is transaction-scoped. The first row of a 2000-row import took an app-wide
    lock; the import then held it across ~12,000 round trips to a remote Postgres, blocking
    every login and admin action in the product for the duration.

    C12 is NOT weakened by the change. The batch still commits audit-or-nothing, and the
    per-row provenance an auditor actually needs -- which spreadsheet row became which
    beneficiary -- lives durably in `enterprise_import_rows` (beneficiary_id, raw, mapped),
    written in this same transaction. The audit row is the last write before the commit,
    which is exactly what app/security/audit.py's caller contract demands.
    """
    c, org, _other, pid = db
    c.execute("DELETE FROM audit_logs")
    batch_id = _upload(c, org, pid)
    imports.commit_batch(c, org, OFFICER, batch_id, audit=_audit(c))

    actions = [r[0] for r in c.execute(
        "SELECT action FROM audit_logs ORDER BY id").fetchall()]
    assert actions == ["ENTERPRISE_IMPORT_STAGED", "ENTERPRISE_IMPORT_COMMITTED"]

    # The provenance the per-row audit rows used to carry is still here, and still exact.
    linked = c.execute(
        "SELECT COUNT(*) FROM enterprise_import_rows "
        " WHERE tenant_id=? AND batch_id=? AND status='Imported' "
        "   AND beneficiary_id IS NOT NULL",
        (org, batch_id),
    ).fetchone()[0]
    assert linked == 3


# ---------------------------------------------------------------------------
# Regressions pinning the five findings from the Codex review of this slice.
# Each one was a real hole; each test fails against the code as first written.
# ---------------------------------------------------------------------------

def test_a_site_code_is_compared_in_canonical_form_not_as_typed(db):
    """HIGH -- idempotency was defeated by punctuation and case.

    An import re-run that spells the same school "kp-01", "KP 01" or "KP–01" (en-dash,
    which is what a spreadsheet autocorrects a hyphen into) must recognise the row it
    already registered. Otherwise the second run duplicates the whole register.
    """
    c, org, _other, pid = db
    beneficiaries.create_beneficiary(
        c, org, OFFICER, pid, code="KP-01", name="Kpando Senior High",
        beneficiary_type="school", audit=_audit(c))

    for spelling in ("kp-01", "KP 01", "  KP--01  ", "kp–01", "Kｐ-01".upper()):
        assert beneficiaries.find_duplicate(
            c, org, pid, code=spelling, name=None, community=None) is not None, spelling

    assert beneficiaries.find_duplicate(
        c, org, pid, code="KP-02", name=None, community=None) is None


def test_canonicalisation_never_produces_a_collision_out_of_thin_air():
    """The normaliser folds punctuation, not identity: two genuinely different codes must
    not canonicalise onto one another."""
    assert beneficiaries.canonical_code("KP-01") != beneficiaries.canonical_code("KP-02")
    assert beneficiaries.canonical_code("") == ""
    assert beneficiaries.canonical_code(None) == ""
    assert len(beneficiaries.canonical_code("X" * 400)) <= 80


def test_an_upload_larger_than_the_cap_is_refused_before_it_is_parsed(db):
    """MED -- the row cap was applied AFTER parsing, so a 500 MB CSV was fully materialised
    in memory first. The byte cap has to bite before the parser sees a single row."""
    oversized = b"School Name,Site Code\n" + (b"a,b\n" * 1)
    oversized += b"#" * (imports.MAX_UPLOAD_BYTES + 1)
    with pytest.raises(ImportError_, match="(?i)the limit is"):
        imports.parse_file("schools.csv", oversized)


def test_a_duplicate_column_header_is_refused_rather_than_silently_dropped(db):
    """MED -- two columns called "Region" collapsed onto one dict key, so whichever came
    last silently won. The operator is told instead."""
    doubled = (
        "School Name,Region,Region\n"
        "Kpando Senior High,Volta,Ashanti\n"
    ).encode()
    with pytest.raises(ImportError_, match="(?i)more than one column"):
        imports.parse_file("schools.csv", doubled)


def test_two_columns_mapped_onto_one_field_is_refused(db):
    """MED -- same data loss, reached the other way: distinct headers, one target field."""
    c, org, _other, pid = db
    headers, rows = imports.parse_file("schools.csv", CSV)
    with pytest.raises(ImportError_, match="(?i)are mapped to"):
        imports.stage_import(
            c, org, OFFICER, pid, filename="s.csv", headers=headers, rows=rows,
            mapping={"School Name": "name", "Town": "name"}, audit=_audit(c))


# ---------------------------------------------------------------------------
# Regressions pinning the Codex ROUND-2 findings (defects in the round-1 fixes,
# plus two the first pass missed).
# ---------------------------------------------------------------------------

def _xlsx(rows: list[list]) -> bytes:
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_a_blank_column_in_the_xlsx_header_does_not_shift_the_data(db):
    """HIGH -- the header list was compacted, then read back BY POSITION IN THE COMPACTED
    LIST. A spacer column between "School Name" and "Site Code" made every later column read
    one to the left: the site code came back empty and the preview looked perfectly fine.
    """
    _c, _org, _other, _pid = db
    data = _xlsx([
        ["School Name", None, "Site Code", "Region"],
        ["Kpando Senior High", None, "KP-01", "Volta"],
    ])
    headers, rows = imports.parse_file("schools.xlsx", data)

    assert headers == ["School Name", "Site Code", "Region"]   # the blank is not a column
    assert rows[0]["School Name"] == "Kpando Senior High"
    assert rows[0]["Site Code"] == "KP-01"                     # NOT "" -- this was the bug
    assert rows[0]["Region"] == "Volta"


def test_a_remap_keeps_the_default_type_chosen_at_upload(db):
    """MED -- the default type was passed at upload and never stored, so correcting one
    unrelated column re-staged every row WITHOUT it. Rows that were valid failed with
    "beneficiary type is required" -- an error about something the operator never touched.
    """
    c, org, _other, pid = db
    no_type_column = (
        "School Name,Site Code\n"
        "Kpando Senior High,KP-01\n"
        "Hohoe Technical,HO-02\n"
    ).encode()
    batch_id = _upload(c, org, pid, data=no_type_column, default_type="school")
    assert imports.get_batch(c, org, batch_id)["valid_rows"] == 2

    # The operator fixes the mapping and says nothing about the default type.
    counts = imports.restage_batch(
        c, org, OFFICER, batch_id,
        mapping={"School Name": "name", "Site Code": "code"}, audit=_audit(c))

    assert counts["Error"] == 0, "the upload-time default must survive a re-map"
    assert counts["Valid"] == 2
    assert imports.get_batch(c, org, batch_id)["default_type"] == "school"


def test_a_remap_can_still_deliberately_clear_the_default_type(db):
    """The other half of the same rule: "" is an instruction, None is silence."""
    c, org, _other, pid = db
    no_type_column = b"School Name,Site Code\nKpando Senior High,KP-01\n"
    batch_id = _upload(c, org, pid, data=no_type_column, default_type="school")

    counts = imports.restage_batch(
        c, org, OFFICER, batch_id, default_type="",
        mapping={"School Name": "name", "Site Code": "code"}, audit=_audit(c))

    assert counts["Error"] == 1          # nothing now says what type this site is
    assert imports.get_batch(c, org, batch_id)["default_type"] == ""


# ---------------------------------------------------------------------------
# Regressions pinning the SUPERVISOR findings -- the defects that survived both
# Codex rounds.
# ---------------------------------------------------------------------------

def test_a_school_listed_twice_in_one_file_is_caught_on_the_second_listing(db):
    """HIGH -- duplicate detection only ever looked at the REGISTER, and nothing from the
    current file is in the register until commit. So the exact case this module exists for --
    two districts both claiming Kpando Senior High -- staged both rows Valid and registered
    the school twice.
    """
    c, org, _other, pid = db
    twice = (
        "School Name,Site Code,Town\n"
        "Kpando Senior High,GE-SHS-01,Kpando\n"
        "Hohoe Technical,HO-02,Hohoe\n"
        "Kpando Senior High,VR-SHS-01,Kpando\n"     # same school, other district's code
    ).encode()
    batch_id = _upload(c, org, pid, data=twice)

    batch = imports.get_batch(c, org, batch_id)
    assert batch["valid_rows"] == 2
    assert batch["duplicate_rows"] == 1
    row3 = [r for r in batch["rows"] if r["row_no"] == 3][0]
    assert row3["status"] == "Duplicate"
    assert "row 1" in " ".join(row3["errors"])     # names WHICH row, not just "duplicate"

    imports.commit_batch(c, org, OFFICER, batch_id, audit=_audit(c))
    names = [b["name"] for b in beneficiaries.list_beneficiaries(c, org, pid)]
    assert names.count("Kpando Senior High") == 1


def test_two_rows_sharing_a_code_do_not_make_the_preview_lie(db):
    """The nastier half of the same bug: with a SHARED code the preview promised "0
    duplicates", and the second row then died on the unique index at commit and was reported
    as a FAILURE -- for a row the preview had just vouched for."""
    c, org, _other, pid = db
    same_code = (
        "School Name,Site Code\n"
        "Kpando Senior High,KP-01\n"
        "Kpando Annex,kp-01\n"                      # same code, different spelling
    ).encode()
    batch_id = _upload(c, org, pid, data=same_code)

    batch = imports.get_batch(c, org, batch_id)
    assert batch["duplicate_rows"] == 1, "the preview must say so BEFORE the commit"
    result = imports.commit_batch(c, org, OFFICER, batch_id, audit=_audit(c))
    assert result["failed"] == 0, "nothing should reach the database only to be refused"
    assert result["imported"] == 1
    assert result["skipped"] == 1


def test_the_batch_counters_still_add_up_after_a_commit(db):
    """MED -- error_rows was incremented for a row that failed at the database while
    valid_rows still counted it as valid, so the four numbers stopped summing to total_rows
    and the preview screen showed more valid rows than existed."""
    c, org, _other, pid = db
    batch_id = _upload(c, org, pid)                          # 3 valid rows
    # Somebody else registers one of them between the preview and the commit.
    beneficiaries.create_beneficiary(
        c, org, OFFICER, pid, code="HO-02", name="Hohoe Technical",
        beneficiary_type="school", audit=_audit(c))

    imports.commit_batch(c, org, OFFICER, batch_id, audit=_audit(c))

    b = imports.get_batch(c, org, batch_id)
    assert b["valid_rows"] + b["error_rows"] + b["duplicate_rows"] + b["imported_rows"] \
        == b["total_rows"]
    assert b["imported_rows"] == 2 and b["error_rows"] == 1   # the raced row, honestly named


def test_a_total_audit_failure_aborts_the_import_instead_of_blaming_the_file(db):
    """MED (C12) -- _require_audit raises C12 when the AUDIT TRAIL cannot be written. The
    commit loop caught it per row, so an audit outage rewrote all 2000 rows as "Error", marked
    the batch Committed with 0 imported, and told the operator their spreadsheet was bad.
    """
    c, org, _other, pid = db
    batch_id = _upload(c, org, pid)

    def _broken_audit(*_a, **_kw):
        return None            # the hook reports it wrote nothing -> _require_audit raises C12

    with pytest.raises(EnterpriseGateError) as caught:
        imports.commit_batch(c, org, OFFICER, batch_id, audit=_broken_audit)
    assert caught.value.control == "C12"

    # And the import did NOT half-happen.
    assert beneficiaries.list_beneficiaries(c, org, pid) == []
    assert imports.get_batch(c, org, batch_id)["status"] == "Staged"


def test_update_still_enforces_a_second_required_field_if_one_is_ever_added(db):
    """LOW (latent) -- `require_name` was written as `required and require_name`, which
    suppressed EVERY required field, not just the name. Correct today only because `name` is
    the sole required field. Pin the intent so the next one added is still enforced."""
    _c, _org, _other, _pid = db
    _clean, problems = beneficiaries.validate_fields({"region": "Volta"}, require_name=False)
    assert problems == []                                   # name may be absent on a patch

    _clean, problems = beneficiaries.validate_fields({"region": "Volta"}, require_name=True)
    assert any("name" in p for p in problems)
