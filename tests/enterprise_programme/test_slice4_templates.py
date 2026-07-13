"""Slice 4 -- the programme template engine.

The property this whole slice exists to protect is IMMUTABILITY: a version freezes the
moment it leaves Draft, and a project generated from version N must still be able to ask
what version N said. Everything else -- the state machine, the separation of duties, C03 --
is in service of that, so the tests are grouped the same way.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from app.enterprise_programme import gates, rbac, tenancy, templates, workflows
from app.enterprise_programme.gates import EnterpriseGateError
from app.enterprise_programme.rbac import EnterprisePermissionError
from app.enterprise_programme.templates import TemplateError
from app.security import audit as audit_mod


class _Conn(sqlite3.Connection):
    """sqlite3.Connection has no __dict__, so a plain attribute cannot be attached."""


ENGINEER = 1     # holds template.manage  (programme_engineer)
DIRECTOR = 2     # holds template.approve (technical_director)
OUTSIDER = 3     # a member of ANOTHER organisation entirely
OWNER    = 4     # created the org, so holds every Release-1 role (ONBOARDING_OWNER_ROLES)

# A complete, legal parameter set. Every required field present.
GOOD = {
    "system_configuration": "hybrid",
    "typical_load_profile": "daytime_only",
    "standard_pv_capacities_kw": [20, 50, 100],
    "battery_options_kwh": [30, 60],
    "generator_integration": True,
    "required_beneficiary_fields": ["name", "region", "roof_area"],
    "required_documents": ["site_survey", "load_assessment"],
    "funding_model": "grant",
    "om_model": "contracted_om",
    "warranty_years": 10,
}


@pytest.fixture()
def db():
    """SQLite with the enterprise schema, an audit table, two orgs, three users."""
    os.environ.pop("DATABASE_URL", None)
    audit_mod.reset_schema_probe()

    c = sqlite3.connect(":memory:", factory=_Conn)
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    for uid, name in ((ENGINEER, "erica"), (DIRECTOR, "dan"), (OUTSIDER, "olu")):
        c.execute("INSERT INTO users (id, username) VALUES (?,?)", (uid, name))
    c.execute(
        "CREATE TABLE audit_logs ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT DEFAULT '',"
        " action TEXT NOT NULL, ip_address TEXT DEFAULT '', details TEXT DEFAULT '',"
        " tenant_id TEXT, agent_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        " prev_hash TEXT, row_hash TEXT)"
    )
    # The marketplace product register the equipment picker validates against. Shaped like
    # the live table (web_app.py:544) -- `category` is NOT NULL there, and a fixture that
    # omits it inserts nothing, which makes the picker look broken when it is not.
    c.execute(
        "CREATE TABLE equipment_catalog ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, name TEXT NOT NULL,"
        " brand TEXT DEFAULT '', unit TEXT DEFAULT 'No.')"
    )
    c.executemany(
        "INSERT INTO equipment_catalog (id, category, name, brand, unit) VALUES (?,?,?,?,?)",
        [(11, "pv_panel", "550W Mono Panel", "Jinko", "No."),
         (12, "inverter", "50kW Inverter", "Huawei", "No.")],
    )

    tenancy.ensure_schema(c)
    workflows.ensure_schema(c)
    for uid, name in ((OWNER, "owen"), (ENGINEER, "erica"), (DIRECTOR, "dan"),
                      (OUTSIDER, "olu")):
        tenancy.get_or_create_personal_tenant(c, uid, name)

    # THE ORG CREATOR IS NOT A USABLE SoD ACTOR (slice 6.5). Onboarding grants the creator
    # every Release-1 role -- constants.ONBOARDING_OWNER_ROLES -- because a one-person
    # organisation IS every authority in it. So the org is created by OWNER, and the two
    # people whose duties must stay separate are ordinary members holding exactly one role
    # each. Before slice 6.5 these tests used the creator as "the engineer", which passed
    # only because the creator was accidentally powerless -- the very bug being fixed.
    org = tenancy.create_organisation(c, OWNER, "Ministry of Energy", "ministry")
    other = tenancy.create_organisation(c, OUTSIDER, "Rival Ministry", "ministry")

    tenancy.add_member(c, org, ENGINEER, "programme_engineer", OWNER)
    tenancy.add_member(c, org, DIRECTOR, "technical_director", OWNER)

    c.commit()
    yield c, org, other
    c.close()
    audit_mod.reset_schema_probe()


def _audit(c):
    def _hook(action, **kw):
        return audit_mod.write_audit_event(action, conn=c, **kw)
    return _hook


def _new_template(c, org, **overrides):
    """A template with version 1 filled in and ready to submit."""
    kwargs = dict(code="SCH-50", name="School 50 kW", beneficiary_type="school",
                  design_strategy="standard", parameters=dict(GOOD), audit=_audit(c))
    kwargs.update(overrides)
    return templates.create_template(c, org, ENGINEER, **kwargs)


def _approved(c, org):
    """A template whose version 1 is Approved -- the state slice 7 needs."""
    tid, vid = _new_template(c, org)
    templates.submit_for_review(c, org, ENGINEER, vid, audit=_audit(c))
    templates.approve_version(c, org, DIRECTOR, vid, audit=_audit(c))
    return tid, vid


# --- the immutability rule --------------------------------------------------


def test_a_draft_can_be_edited(db):
    c, org, _ = db
    _tid, vid = _new_template(c, org, parameters=None)
    stored = templates.save_draft_parameters(c, org, ENGINEER, vid, GOOD, audit=_audit(c))
    assert stored["system_configuration"] == "hybrid"
    assert stored["standard_pv_capacities_kw"] == [20, 50, 100]


def test_submitting_freezes_the_parameters_forever(db):
    """THE rule. After Draft, no write ever touches this version's parameters again."""
    c, org, _ = db
    _tid, vid = _new_template(c, org)
    templates.submit_for_review(c, org, ENGINEER, vid, audit=_audit(c))

    with pytest.raises(TemplateError) as e:
        templates.save_draft_parameters(
            c, org, ENGINEER, vid, dict(GOOD, warranty_years=1), audit=_audit(c)
        )
    assert e.value.control == "C03"

    # And it really is unchanged on disk, not merely refused at the door.
    assert templates.get_version_state(c, org, vid)["parameters"]["warranty_years"] == 10


def test_an_approved_version_cannot_be_edited_either(db):
    c, org, _ = db
    _tid, vid = _approved(c, org)
    with pytest.raises(TemplateError):
        templates.save_draft_parameters(c, org, ENGINEER, vid, GOOD, audit=_audit(c))


def test_changing_a_template_means_a_new_version_and_the_old_one_survives(db):
    """The whole point: v1 keeps saying what it said when a project was built from it."""
    c, org, _ = db
    tid, v1 = _approved(c, org)

    v2 = templates.create_version(c, org, ENGINEER, tid, audit=_audit(c))
    templates.save_draft_parameters(
        c, org, ENGINEER, v2, dict(GOOD, standard_pv_capacities_kw=[75]), audit=_audit(c)
    )

    assert templates.get_version_state(c, org, v1)["parameters"][
        "standard_pv_capacities_kw"] == [20, 50, 100]
    assert templates.get_version_state(c, org, v2)["parameters"][
        "standard_pv_capacities_kw"] == [75]
    assert templates.get_version_state(c, org, v2)["version_no"] == 2


def test_a_new_version_copies_the_last_one(db):
    """Byte-for-byte what v1 holds -- compared against the STORED v1, not the raw input,
    because the validator normalises (multiselects come back sorted)."""
    c, org, _ = db
    tid, v1 = _approved(c, org)
    v2 = templates.create_version(c, org, ENGINEER, tid, audit=_audit(c))
    assert (templates.get_version_state(c, org, v2)["parameters"]
            == templates.get_version_state(c, org, v1)["parameters"])


def test_only_one_open_draft_at_a_time(db):
    """Two concurrent drafts of one standard is two people about to overwrite each other."""
    c, org, _ = db
    tid, _v1 = _approved(c, org)
    templates.create_version(c, org, ENGINEER, tid, audit=_audit(c))
    with pytest.raises(TemplateError, match="still a Draft"):
        templates.create_version(c, org, ENGINEER, tid, audit=_audit(c))


def test_a_rejected_version_becomes_editable_again(db):
    """The ONE way back to editable -- and only before approval, when nothing was built."""
    c, org, _ = db
    _tid, vid = _new_template(c, org)
    templates.submit_for_review(c, org, ENGINEER, vid, audit=_audit(c))
    templates.reject_version(c, org, DIRECTOR, vid, comment="no battery sizing",
                             audit=_audit(c))

    state = templates.get_version_state(c, org, vid)
    assert state["status"] == "Draft" and state["editable"]
    templates.save_draft_parameters(c, org, ENGINEER, vid, GOOD, audit=_audit(c))


# --- separation of duties ---------------------------------------------------


def test_the_author_cannot_approve_their_own_template(db):
    """template.manage builds; template.approve certifies. Different roles, on purpose."""
    c, org, _ = db
    _tid, vid = _new_template(c, org)
    templates.submit_for_review(c, org, ENGINEER, vid, audit=_audit(c))
    with pytest.raises(EnterprisePermissionError):
        templates.approve_version(c, org, ENGINEER, vid, audit=_audit(c))


def test_the_director_cannot_author(db):
    c, org, _ = db
    with pytest.raises(EnterprisePermissionError):
        templates.create_template(c, org, DIRECTOR, code="X", name="X",
                                  beneficiary_type="school", audit=_audit(c))


def test_an_ai_recommendation_cannot_approve_a_template(db):
    """C11 -- an AI recommendation is evidence, never the decision."""
    c, org, _ = db
    _tid, vid = _new_template(c, org)
    templates.submit_for_review(c, org, ENGINEER, vid, audit=_audit(c))
    with pytest.raises(EnterpriseGateError) as e:
        templates.approve_version(c, org, None, vid, ai_recommendation_id=7,
                                  audit=_audit(c))
    assert e.value.control == "C11"


def test_an_engineer_can_abandon_their_own_draft(db):
    """Otherwise they are stuck: create_version refuses to open a second draft while one is
    open, so an unfinished draft nobody has reviewed could only be cleared by interrupting
    the Technical Director."""
    c, org, _ = db
    tid, v1 = _approved(c, org)
    v2 = templates.create_version(c, org, ENGINEER, tid, audit=_audit(c))

    templates.archive_version(c, org, ENGINEER, v2, audit=_audit(c))
    assert templates.get_version_state(c, org, v2)["status"] == "Archived"

    # ...and with the draft gone, they can start again.
    v3 = templates.create_version(c, org, ENGINEER, tid, audit=_audit(c))
    assert templates.get_version_state(c, org, v3)["status"] == "Draft"


def test_an_engineer_cannot_archive_an_approved_version(db):
    """Retiring a CERTIFIED standard is a governance act, not the author's call --
    something may have been built from it."""
    c, org, _ = db
    _tid, vid = _approved(c, org)
    with pytest.raises(EnterprisePermissionError):
        templates.archive_version(c, org, ENGINEER, vid, audit=_audit(c))
    templates.archive_version(c, org, DIRECTOR, vid, audit=_audit(c))  # the director may


# --- the state machine ------------------------------------------------------


def test_a_draft_cannot_jump_straight_to_approved(db):
    c, org, _ = db
    _tid, vid = _new_template(c, org)
    with pytest.raises(TemplateError, match="cannot become Approved"):
        templates.approve_version(c, org, DIRECTOR, vid, audit=_audit(c))


def test_publishing_supersedes_the_previous_published_version(db):
    """Exactly one Published version. The incumbent is superseded, never rewritten."""
    c, org, _ = db
    tid, v1 = _approved(c, org)
    templates.publish_version(c, org, DIRECTOR, v1, audit=_audit(c))

    v2 = templates.create_version(c, org, ENGINEER, tid, audit=_audit(c))
    templates.submit_for_review(c, org, ENGINEER, v2, audit=_audit(c))
    templates.approve_version(c, org, DIRECTOR, v2, audit=_audit(c))
    templates.publish_version(c, org, DIRECTOR, v2, audit=_audit(c))

    assert templates.get_version_state(c, org, v1)["status"] == "Superseded"
    assert templates.get_version_state(c, org, v2)["status"] == "Published"
    assert templates.generative_version(c, org, tid)["id"] == v2


def test_a_published_version_can_never_be_edited_or_unfrozen(db):
    c, org, _ = db
    _tid, vid = _approved(c, org)
    templates.publish_version(c, org, DIRECTOR, vid, audit=_audit(c))
    assert "Draft" not in templates.get_version_state(c, org, vid)["next_states"]
    with pytest.raises(TemplateError):
        templates.save_draft_parameters(c, org, ENGINEER, vid, GOOD, audit=_audit(c))


def test_an_incomplete_draft_cannot_be_submitted(db):
    """A Draft may be half-finished. The moment it is offered for approval, it may not."""
    c, org, _ = db
    _tid, vid = _new_template(c, org, parameters=None)
    with pytest.raises(TemplateError) as e:
        templates.submit_for_review(c, org, ENGINEER, vid, audit=_audit(c))
    assert "System configuration is required" in str(e.value)


# --- control C03 ------------------------------------------------------------


def test_c03_refuses_a_draft_version(db):
    """No project is generated without an approved template. This is slice 7's guard."""
    c, org, _ = db
    _tid, vid = _new_template(c, org)
    with pytest.raises(EnterpriseGateError) as e:
        gates.require_approved_template_version(c, org, vid)
    assert e.value.control == "C03"


def test_c03_admits_approved_and_published(db):
    c, org, _ = db
    _tid, vid = _approved(c, org)
    gates.require_approved_template_version(c, org, vid)   # Approved: fine
    templates.publish_version(c, org, DIRECTOR, vid, audit=_audit(c))
    gates.require_approved_template_version(c, org, vid)   # Published: fine


def test_c03_is_no_longer_advertised_as_deferred(db):
    """The dashboard must stop claiming C03 is blocked, now that it is enforced."""
    c03 = next(x for x in gates.control_summary() if x["code"] == "C03")
    assert c03["enforced_now"] is True


def test_c03_refuses_another_tenants_version_as_absent_not_unapproved(db):
    c, org, other = db
    _tid, vid = _approved(c, org)
    with pytest.raises(EnterpriseGateError, match="no such template version"):
        gates.require_approved_template_version(c, other, vid)


# --- tenant scope (C13) -----------------------------------------------------


def test_another_tenants_template_does_not_exist_for_you(db):
    c, org, other = db
    tid, vid = _approved(c, org)

    with pytest.raises(TemplateError) as e:
        templates.get_template(c, other, tid)
    assert e.value.control == "C13"

    with pytest.raises(TemplateError) as e:
        templates.get_version_state(c, other, vid)
    assert e.value.control == "C13"


def test_a_cross_tenant_write_is_404_shaped_even_without_permission(db):
    """C13 is decided BEFORE authz: a 403 would confirm the template exists."""
    c, org, other = db
    _tid, vid = _new_template(c, org)
    # OUTSIDER holds nothing at all in `other` -- so a permission-first check would 403.
    with pytest.raises(TemplateError) as e:
        templates.save_draft_parameters(c, other, OUTSIDER, vid, GOOD, audit=_audit(c))
    assert e.value.control == "C13"


def test_list_templates_never_leaks_across_tenants(db):
    c, org, other = db
    _approved(c, org)
    assert len(templates.list_templates(c, org)) == 1
    assert templates.list_templates(c, other) == []


# --- validation -------------------------------------------------------------


def test_a_value_that_was_never_offered_is_refused(db):
    c, org, _ = db
    with pytest.raises(TemplateError, match="not one of the offered options"):
        templates.validate_parameters(
            c, org, dict(GOOD, system_configuration="perpetual_motion")
        )


def test_every_problem_is_reported_at_once(db):
    """A form that rejects one field per round trip is a form people work around."""
    c, org, _ = db
    with pytest.raises(TemplateError) as e:
        templates.validate_parameters(c, org, {
            "system_configuration": "nonsense",
            "standard_pv_capacities_kw": ["big"],
        })
    message = str(e.value)
    assert "System configuration" in message
    assert "Standard PV capacities" in message
    assert "Typical load profile is required" in message


def test_equipment_is_validated_against_the_live_catalogue(db):
    c, org, _ = db
    ok = templates.validate_parameters(
        c, org, dict(GOOD, standard_equipment_ids=[11, 12])
    )
    assert ok["standard_equipment_ids"] == [11, 12]

    with pytest.raises(TemplateError, match="not in the catalogue"):
        templates.validate_parameters(
            c, org, dict(GOOD, standard_equipment_ids=[11, 999])
        )


def test_a_comma_separated_size_list_is_parsed(db):
    """How the form actually posts it: one text input, not a checkbox group."""
    c, org, _ = db
    ok = templates.validate_parameters(
        c, org, dict(GOOD, standard_pv_capacities_kw=["5, 10, 20"])
    )
    assert ok["standard_pv_capacities_kw"] == [5, 10, 20]


def test_sizes_must_be_positive_numbers(db):
    c, org, _ = db
    with pytest.raises(TemplateError, match="greater than zero"):
        templates.validate_parameters(c, org, dict(GOOD, standard_pv_capacities_kw=[0]))


def test_unknown_keys_are_dropped_not_rejected(db):
    """A stale form field should not brick a save; a bad value for a KNOWN key still errors."""
    c, org, _ = db
    ok = templates.validate_parameters(c, org, dict(GOOD, favourite_colour="green"))
    assert "favourite_colour" not in ok


def test_a_duplicate_code_is_refused(db):
    c, org, _ = db
    _new_template(c, org)
    with pytest.raises(TemplateError, match="already used"):
        _new_template(c, org)


# --- C12: audit-or-nothing --------------------------------------------------


def test_a_failed_audit_rolls_the_whole_template_back(db):
    c, org, _ = db

    def broken(action, **kw):
        return False

    with pytest.raises(EnterpriseGateError) as e:
        _new_template(c, org, code="NOPE", audit=broken)
    assert e.value.control == "C12"
    assert c.execute(
        "SELECT COUNT(*) FROM enterprise_programme_templates WHERE code='NOPE'"
    ).fetchone()[0] == 0
    # ...and no orphan version either: they were one transaction.
    assert c.execute(
        "SELECT COUNT(*) FROM enterprise_template_versions"
    ).fetchone()[0] == 0


def test_every_template_action_writes_an_audit_row(db):
    c, org, _ = db
    tid, vid = _new_template(c, org)
    templates.submit_for_review(c, org, ENGINEER, vid, audit=_audit(c))
    templates.approve_version(c, org, DIRECTOR, vid, audit=_audit(c))
    templates.publish_version(c, org, DIRECTOR, vid, audit=_audit(c))

    actions = [r[0] for r in c.execute(
        "SELECT action FROM audit_logs ORDER BY id").fetchall()]
    assert actions == [
        "ENTERPRISE_TEMPLATE_CREATED",
        "ENTERPRISE_TEMPLATE_VERSION_SUBMITTED",
        "ENTERPRISE_TEMPLATE_VERSION_APPROVED",
        "ENTERPRISE_TEMPLATE_VERSION_PUBLISHED",
    ]


# --- the Codex slice-4 findings, each pinned -------------------------------


def test_the_database_itself_refuses_to_edit_a_frozen_version(db):
    """HIGH. The service guard protects the app's write paths. It does nothing about a
    fix-up script, a migration, an admin console or a future slice reaching this table with
    a plain UPDATE -- and that is the quiet failure the whole slice exists to prevent:
    a school built to v3, v3 later edited, and no event anywhere saying which one moved."""
    c, org, _ = db
    _tid, vid = _approved(c, org)
    with pytest.raises(sqlite3.IntegrityError, match="frozen"):
        c.execute(
            "UPDATE enterprise_template_versions SET parameters_json='{\"hacked\":1}' "
            " WHERE id=?", (vid,)
        )


def test_the_database_itself_refuses_to_resurrect_an_approved_version_as_draft(db):
    """HIGH. Editable-again is how a frozen version gets edited. The DB says no."""
    c, org, _ = db
    _tid, vid = _approved(c, org)
    with pytest.raises(sqlite3.IntegrityError, match="cannot return to Draft"):
        c.execute("UPDATE enterprise_template_versions SET status='Draft' WHERE id=?",
                  (vid,))


def test_a_draft_may_still_be_edited_by_the_database(db):
    """The trigger must not be so eager that it breaks the legal path."""
    c, org, _ = db
    _tid, vid = _new_template(c, org)
    c.execute("UPDATE enterprise_template_versions SET parameters_json='{}' WHERE id=?",
              (vid,))
    assert templates.get_version_state(c, org, vid)["parameters"] == {}


def test_a_rejected_version_may_still_return_to_draft(db):
    """Review -> Draft is the one legal unfreeze, and the trigger must permit it."""
    c, org, _ = db
    _tid, vid = _new_template(c, org)
    templates.submit_for_review(c, org, ENGINEER, vid, audit=_audit(c))
    templates.reject_version(c, org, DIRECTOR, vid, audit=_audit(c))
    assert templates.get_version_state(c, org, vid)["status"] == "Draft"


def test_two_published_versions_are_unrepresentable(db):
    """HIGH. Concurrent publishes each supersede an incumbent the other cannot see yet.
    The unique index makes the outcome impossible rather than merely unlikely."""
    c, org, _ = db
    tid, v1 = _approved(c, org)
    templates.publish_version(c, org, DIRECTOR, v1, audit=_audit(c))

    v2 = templates.create_version(c, org, ENGINEER, tid, audit=_audit(c))
    templates.submit_for_review(c, org, ENGINEER, v2, audit=_audit(c))
    templates.approve_version(c, org, DIRECTOR, v2, audit=_audit(c))

    # Force the racing outcome: publish v2 WITHOUT superseding v1.
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("UPDATE enterprise_template_versions SET status='Published' WHERE id=?",
                  (v2,))


def test_two_open_drafts_are_unrepresentable(db):
    """MED. The service checks, and the database enforces."""
    c, org, _ = db
    tid, _v1 = _approved(c, org)
    templates.create_version(c, org, ENGINEER, tid, audit=_audit(c))   # v2, Draft
    with pytest.raises(sqlite3.IntegrityError):
        c.execute(
            "INSERT INTO enterprise_template_versions "
            "(tenant_id, template_id, version_no, status) VALUES (?,?,?,'Draft')",
            (org, tid, 99),
        )


def test_a_status_outside_the_vocabulary_is_refused(db):
    """A status nothing can reason about is worse than a wrong one -- it fails open."""
    c, org, _ = db
    _tid, vid = _new_template(c, org)
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("UPDATE enterprise_template_versions SET status='Definitely Fine' "
                  " WHERE id=?", (vid,))


def test_a_status_change_under_us_aborts_the_write(db):
    """HIGH. The check-then-write race: the version left Draft between our read and our
    write. The UPDATE is conditioned on the status we checked, so it hits zero rows."""
    c, org, _ = db
    _tid, vid = _new_template(c, org)

    real_validate = templates.validate_parameters

    def submit_behind_our_back(conn, tenant, params):
        # Stand in for a concurrent request that submits the version while we validate.
        conn.execute("UPDATE enterprise_template_versions SET status='Review' WHERE id=?",
                     (vid,))
        return real_validate(conn, tenant, params)

    templates.validate_parameters = submit_behind_our_back
    try:
        with pytest.raises(TemplateError, match="no longer Draft"):
            templates.save_draft_parameters(
                c, org, ENGINEER, vid, dict(GOOD, warranty_years=99), audit=_audit(c)
            )
    finally:
        templates.validate_parameters = real_validate

    # And nothing was written: not the parameters, and not an audit row claiming they were.
    assert templates.get_version_state(c, org, vid)["parameters"]["warranty_years"] == 10


def test_nan_and_infinity_are_not_valid_sizes(db):
    """MED. float('NaN') SUCCEEDS, and `NaN <= 0` is False -- so it sails through a naive
    range check and lands in the standard, where slice 7 would size an array to it."""
    c, org, _ = db
    for bad in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(TemplateError, match="not a finite number"):
            templates.validate_parameters(
                c, org, dict(GOOD, standard_pv_capacities_kw=[bad])
            )
    with pytest.raises(TemplateError, match="not a finite number"):
        templates.validate_parameters(c, org, dict(GOOD, warranty_years="NaN"))


def test_equipment_validation_fails_closed_when_the_catalogue_is_unreachable(db):
    """MED. A validator that stops validating when it cannot see the data has stopped
    being a validator -- and that is exactly the moment it matters."""
    c, org, _ = db
    c.execute("DROP TABLE equipment_catalog")
    with pytest.raises(TemplateError, match="catalogue is unavailable"):
        templates.validate_parameters(c, org, dict(GOOD, standard_equipment_ids=[999]))

    # ...but a template with NO equipment is still saveable: nothing is being asserted.
    ok = templates.validate_parameters(c, org, dict(GOOD, standard_equipment_ids=[]))
    assert "standard_equipment_ids" not in ok


# --- gate 6 ----------------------------------------------------------------


def test_gate_6_now_demands_a_real_approved_template(db):
    """Standardisation Approval used to accept a document CLAIMING a standard existed."""
    c, org, _ = db
    # OWNER registers the programme: programme.create is the Enterprise Owner's, not the
    # Programme Engineer's. (Before slice 6.5 the engineer WAS the org creator, so this
    # read as though an engineer could open a programme. They cannot, and should not.)
    pid = workflows.create_programme(c, org, OWNER, code="P1", name="Schools",
                                     sponsor_user_id=OWNER, audit=_audit(c))
    workflows.register_document(c, org, OWNER, pid, doc_type="template_version_pack",
                                title="Pack", audit=_audit(c))

    with pytest.raises(EnterpriseGateError, match="no approved programme template"):
        gates.evaluate_gate(c, org, pid, "G06")

    _approved(c, org)                      # a tenant-wide approved template
    gates.evaluate_gate(c, org, pid, "G06")  # now the gate has something real to point at
