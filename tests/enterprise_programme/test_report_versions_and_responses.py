"""Report versions and per-recipient responses (xx201 s42-s43).

The rule these tests exist to protect: a report is accepted ONLY when BOTH the beneficiary
organisation and the sponsor institution have accepted it. One acceptance and one silence is
not an acceptance. A report that displays as accepted when the sponsor has not accepted it
would let a programme advance on an endorsement nobody gave.

The acceptance rule is a PURE function of the answers on record, so most of it is tested
without a database at all -- including the cases a database test would find it awkward to
reach, like "nobody has answered yet".
"""

import sqlite3

import pytest

from app.enterprise_programme import report_responses as rr
from app.enterprise_programme.report_responses import ReportResponseError

A, M, R = rr.ACCEPTED, rr.MODIFICATION_REQUESTED, rr.REJECTED
TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"
DOC = 7          # belongs to TENANT
OTHER_DOC = 8    # belongs to OTHER_TENANT
#
# Two DIFFERENT ids, because document ids are globally unique in production too -- 026 gives
# enterprise_documents `id bigserial PRIMARY KEY`. Two tenants sharing a document id is not a
# state the system can reach, so testing it would have been testing fiction. The isolation
# tests below instead do the thing that IS reachable and dangerous: read a document id that
# exists, while passing the WRONG tenant.


def _answers(beneficiary=None, sponsor=None):
    out = {}
    if beneficiary:
        out[rr.BENEFICIARY] = {"response": beneficiary}
    if sponsor:
        out[rr.SPONSOR] = {"response": sponsor}
    return out


@pytest.fixture()
def db():
    c = sqlite3.connect(":memory:")
    # SQLite ignores FOREIGN KEY clauses unless this is ON, per connection. Codex (Q4,
    # 2026-07-18): without it the mirror declares constraints it never enforces, so the FK
    # protection looked tested and was not. Production is Postgres, which always enforces.
    c.execute("PRAGMA foreign_keys=ON")

    # The PARENT table, because versions are subordinate to it. Standing this up in the
    # fixture is what makes the FK real here: with FKs enforced and no parent, a version
    # cannot be stored at all -- which is precisely the protection production relies on.
    # Only the columns this slice's constraints touch; the real table (migration 026 + 028)
    # is much wider and none of the rest bears on these tests.
    c.execute("""
        CREATE TABLE enterprise_documents (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id    TEXT NOT NULL,
            programme_id INTEGER,
            doc_type     TEXT,
            markdown     TEXT,
            UNIQUE (tenant_id, id)
        )
    """)
    rr.ensure_schema(c)

    for doc_id, tenant in ((DOC, TENANT), (OTHER_DOC, OTHER_TENANT)):
        c.execute("INSERT INTO enterprise_documents (id, tenant_id) VALUES (?,?)",
                  (doc_id, tenant))
    yield c
    c.close()


class TestTheAcceptanceRule:
    """xx201 s24/s29/s35: accepted only when BOTH accept."""

    @pytest.mark.parametrize("beneficiary,sponsor,expected", [
        # Nobody has answered. The dangerous case: `all()` over an empty collection is
        # vacuously TRUE, so a naive implementation reports this as accepted by both.
        (None, None, rr.AWAITING_RESPONSES),
        # One side accepted, the other is silent. Silence is not consent.
        (A,    None, rr.AWAITING_RESPONSES),
        (None, A,    rr.AWAITING_RESPONSES),
        # Both accepted -- the only route to acceptance.
        (A,    A,    rr.ACCEPTED_BY_BOTH),
        # Work is owed.
        (A,    M,    rr.MODIFICATION_REQUIRED),
        (M,    A,    rr.MODIFICATION_REQUIRED),
        (M,    M,    rr.MODIFICATION_REQUIRED),
        # A rejection is decisive and outranks everything else.
        (A,    R,    rr.REJECTED),
        (R,    A,    rr.REJECTED),
        (M,    R,    rr.REJECTED),
        (R,    M,    rr.REJECTED),
        (R,    R,    rr.REJECTED),
        # A pending side cannot rescue a rejection either.
        (R,    None, rr.REJECTED),
        (None, M,    rr.MODIFICATION_REQUIRED),
    ])
    def test_the_status_table(self, beneficiary, sponsor, expected):
        assert rr.overall_status(_answers(beneficiary, sponsor)) == expected

    def test_no_answers_is_never_accepted(self):
        """Called out separately because it is the failure mode with teeth.

        `all(... for kind in [])` is True. An implementation that iterated the RESPONSES
        PRESENT rather than the recipients REQUIRED would mark a report nobody had opened as
        accepted by both, and the workflow would advance to the Business Case on it.
        """
        assert rr.overall_status({}) != rr.ACCEPTED_BY_BOTH
        assert rr.overall_status({}) == rr.AWAITING_RESPONSES

    def test_one_acceptance_is_never_enough(self):
        for kind in rr.RECIPIENT_KINDS:
            assert rr.overall_status({kind: {"response": A}}) == rr.AWAITING_RESPONSES

    def test_an_unknown_recipient_cannot_manufacture_an_acceptance(self):
        """A third party answering ACCEPTED must not satisfy the rule on its own -- the two
        required recipients are still required.
        """
        assert rr.overall_status({"auditor": {"response": A}}) == rr.AWAITING_RESPONSES
        assert rr.overall_status(
            {rr.BENEFICIARY: {"response": A}, "auditor": {"response": A}}
        ) == rr.AWAITING_RESPONSES


class TestVersions:

    def test_versions_start_at_one_and_increment(self, db):
        assert rr.next_version_number(db, TENANT, DOC) == 1
        assert rr.save_version(db, TENANT, DOC, "# v1") == 1
        assert rr.save_version(db, TENANT, DOC, "# v2") == 2
        assert rr.next_version_number(db, TENANT, DOC) == 3

    def test_a_version_never_overwrites_the_one_a_recipient_answered(self, db):
        """Append-only is the point: an acceptance names a version, so overwriting that
        version would silently transfer the acceptance to text nobody saw.
        """
        rr.save_version(db, TENANT, DOC, "# original")
        rr.record_response(db, TENANT, DOC, version_number=1,
                           recipient_kind=rr.SPONSOR, response=A)
        rr.save_version(db, TENANT, DOC, "# revised", change_summary="financing reworded")

        assert rr.get_version(db, TENANT, DOC, 1)["markdown"] == "# original"
        assert rr.get_version(db, TENANT, DOC, 2)["markdown"] == "# revised"
        # The acceptance still belongs to v1, and v2 is unanswered.
        assert rr.status_for(db, TENANT, DOC, 1) == rr.AWAITING_RESPONSES
        assert rr.responses_for(db, TENANT, DOC, 2) == {}

    def test_an_empty_version_is_refused(self, db):
        with pytest.raises(ReportResponseError):
            rr.save_version(db, TENANT, DOC, "   ")

    def test_versions_are_per_document(self, db):
        db.execute("INSERT INTO enterprise_documents (id, tenant_id) VALUES (?,?)",
                   (99, TENANT))
        assert rr.save_version(db, TENANT, DOC, "# a") == 1
        assert rr.save_version(db, TENANT, 99, "# b") == 1, (
            "a second document starts its own numbering")

    def test_the_same_version_number_cannot_be_claimed_twice(self, db):
        rr.save_version(db, TENANT, DOC, "# v1")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO enterprise_document_versions "
                "(tenant_id, document_id, version_number, markdown) VALUES (?,?,?,?)",
                (TENANT, DOC, 1, "# impostor"))


class TestResponses:

    def test_each_recipient_is_tracked_separately(self, db):
        rr.save_version(db, TENANT, DOC, "# v1")
        rr.record_response(db, TENANT, DOC, version_number=1,
                           recipient_kind=rr.BENEFICIARY, response=A)
        rr.record_response(db, TENANT, DOC, version_number=1,
                           recipient_kind=rr.SPONSOR, response=M,
                           comments="clarify the financing section")

        got = rr.responses_for(db, TENANT, DOC, 1)
        assert got[rr.BENEFICIARY]["response"] == A
        assert got[rr.SPONSOR]["response"] == M
        assert got[rr.SPONSOR]["comments"] == "clarify the financing section"
        assert rr.status_for(db, TENANT, DOC, 1) == rr.MODIFICATION_REQUIRED

    def test_a_recipient_who_has_not_answered_is_absent_not_blank(self, db):
        """"Has not answered" and "answered neutrally" are different facts, and the
        acceptance rule turns on the difference.
        """
        rr.save_version(db, TENANT, DOC, "# v1")
        rr.record_response(db, TENANT, DOC, version_number=1,
                           recipient_kind=rr.BENEFICIARY, response=A)
        assert rr.SPONSOR not in rr.responses_for(db, TENANT, DOC, 1)

    def test_a_changed_answer_carries_its_own_timestamp(self, db):
        """This row is the evidence for whether a programme was authorised to proceed, so its
        clock has to be right. Codex (Q7, 2026-07-18): the upsert kept the ORIGINAL
        responded_at, so the record said the sponsor answered before they actually did.
        """
        rr.save_version(db, TENANT, DOC, "# v1")
        rr.record_response(db, TENANT, DOC, version_number=1,
                           recipient_kind=rr.SPONSOR, response=M)
        first = db.execute("SELECT responded_at FROM enterprise_report_responses").fetchone()[0]

        # SQLite's CURRENT_TIMESTAMP has one-second resolution, so move the stored value back
        # rather than sleeping through a real second in the suite.
        db.execute("UPDATE enterprise_report_responses "
                   "SET responded_at = datetime(responded_at, '-1 hour')")
        rr.record_response(db, TENANT, DOC, version_number=1,
                           recipient_kind=rr.SPONSOR, response=A)

        second = db.execute(
            "SELECT responded_at FROM enterprise_report_responses").fetchone()[0]
        assert second > db.execute("SELECT datetime(?, '-1 hour')",
                                   (first,)).fetchone()[0], (
            "a changed answer must be stamped when it was actually given")

    def test_changing_your_mind_supersedes_rather_than_accumulates(self, db):
        rr.save_version(db, TENANT, DOC, "# v1")
        rr.record_response(db, TENANT, DOC, version_number=1,
                           recipient_kind=rr.SPONSOR, response=M)
        rr.record_response(db, TENANT, DOC, version_number=1,
                           recipient_kind=rr.SPONSOR, response=A)

        got = rr.responses_for(db, TENANT, DOC, 1)
        assert got[rr.SPONSOR]["response"] == A
        rows = db.execute(
            "SELECT COUNT(*) FROM enterprise_report_responses "
            "WHERE tenant_id=? AND document_id=? AND version_number=? AND recipient_kind=?",
            (TENANT, DOC, 1, rr.SPONSOR)).fetchone()[0]
        assert rows == 1, "two contradictory answers would make the rule unevaluable"

    def test_responses_are_scoped_to_their_version(self, db):
        rr.save_version(db, TENANT, DOC, "# v1")
        rr.save_version(db, TENANT, DOC, "# v2")
        rr.record_response(db, TENANT, DOC, version_number=1,
                           recipient_kind=rr.BENEFICIARY, response=A)
        rr.record_response(db, TENANT, DOC, version_number=1,
                           recipient_kind=rr.SPONSOR, response=A)

        assert rr.status_for(db, TENANT, DOC, 1) == rr.ACCEPTED_BY_BOTH
        assert rr.status_for(db, TENANT, DOC, 2) == rr.AWAITING_RESPONSES, (
            "accepting v1 must not accept the revision that followed it")

    @pytest.mark.parametrize("bad", ["approved", "accepted", "ACCEPT", "", "YES"])
    def test_an_unknown_response_is_refused(self, db, bad):
        rr.save_version(db, TENANT, DOC, "# v1")
        with pytest.raises(ReportResponseError):
            rr.record_response(db, TENANT, DOC, version_number=1,
                               recipient_kind=rr.SPONSOR, response=bad)

    @pytest.mark.parametrize("bad", ["auditor", "developer", "", "Sponsor"])
    def test_an_unknown_recipient_is_refused(self, db, bad):
        rr.save_version(db, TENANT, DOC, "# v1")
        with pytest.raises(ReportResponseError):
            rr.record_response(db, TENANT, DOC, version_number=1,
                               recipient_kind=bad, response=A)

    def test_the_database_refuses_a_bad_value_too_not_only_python(self, db):
        rr.save_version(db, TENANT, DOC, "# v1")   # so the CHECK is what fails, not the FK
        """The vocabulary is closed at the DATABASE, not merely in the helper.

        A future route writing this table directly must not be able to store a response the
        acceptance rule cannot evaluate.
        """
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO enterprise_report_responses "
                "(tenant_id, document_id, version_number, recipient_kind, response) "
                "VALUES (?,?,?,?,?)", (TENANT, DOC, 1, rr.SPONSOR, "MAYBE"))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO enterprise_report_responses "
                "(tenant_id, document_id, version_number, recipient_kind, response) "
                "VALUES (?,?,?,?,?)", (TENANT, DOC, 1, "auditor", A))


class TestTheDefectsCodexFound:
    """Each of these passed before the 2026-07-18 review and should not have."""

    @pytest.mark.parametrize("verdict", [rr.REJECTED, rr.MODIFICATION_REQUESTED])
    def test_a_party_with_no_standing_cannot_kill_a_report(self, verdict):
        """Codex (MEDIUM): reading every value in the mapping let an unknown third party swing
        the status. An acceptance could not be forged that way -- but a REJECTION could, which
        is the same defect wearing the opposite sign.
        """
        assert rr.overall_status({"auditor": {"response": verdict}}) == rr.AWAITING_RESPONSES

    def test_an_outsider_cannot_overturn_a_genuine_acceptance(self):
        both = {rr.BENEFICIARY: {"response": A}, rr.SPONSOR: {"response": A}}
        assert rr.overall_status({**both, "auditor": {"response": R}}) == rr.ACCEPTED_BY_BOTH

    def test_a_response_cannot_name_a_version_that_does_not_exist(self, db):
        """Codex (HIGH): otherwise the app records "the sponsor accepted version 3" with no
        version 3 to show for it -- an acceptance that cannot be evidenced.
        """
        rr.save_version(db, TENANT, DOC, "# v1")
        with pytest.raises(ReportResponseError):
            rr.record_response(db, TENANT, DOC, version_number=2,
                               recipient_kind=rr.SPONSOR, response=A)

    def test_a_response_cannot_be_recorded_before_any_version_exists(self, db):
        with pytest.raises(ReportResponseError):
            rr.record_response(db, TENANT, DOC, version_number=1,
                               recipient_kind=rr.SPONSOR, response=A)

    def test_the_database_enforces_the_version_reference_too(self, db):
        """Not merely the Python guard: a future route writing this table directly must also
        be unable to record an unevidenced acceptance.
        """
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO enterprise_report_responses "
                "(tenant_id, document_id, version_number, recipient_kind, response) "
                "VALUES (?,?,?,?,?)", (TENANT, DOC, 99, rr.SPONSOR, A))

    def test_one_tenants_update_leaves_another_tenants_answer_alone(self, db):
        """Codex (MEDIUM): the update ran `WHERE id = ?` with no tenant_id.

        HONEST LIMIT OF THIS TEST, recorded rather than glossed: it does NOT prove the
        tenant filter is present. Mutation-testing it (2026-07-18) showed the test still
        passes with the filter removed, because the preceding lookup is already tenant-scoped
        and row ids are globally unique -- so no cross-tenant collision can be constructed to
        expose the difference. The filter is defence-in-depth for a future refactor that
        drops or widens that lookup, and Directive s6 asks for it on every protected write.
        What this test DOES prove is the outcome that matters: two tenants holding answers on
        the same document id do not disturb each other.
        """
        rr.save_version(db, TENANT, DOC, "# v1")
        rr.save_version(db, OTHER_TENANT, OTHER_DOC, "# theirs")
        rr.record_response(db, TENANT, DOC, version_number=1,
                           recipient_kind=rr.SPONSOR, response=M)
        rr.record_response(db, OTHER_TENANT, OTHER_DOC, version_number=1,
                           recipient_kind=rr.SPONSOR, response=M)

        rr.record_response(db, TENANT, DOC, version_number=1,
                           recipient_kind=rr.SPONSOR, response=A)

        assert rr.responses_for(db, TENANT, DOC, 1)[rr.SPONSOR]["response"] == A
        assert rr.responses_for(db, OTHER_TENANT, OTHER_DOC, 1)[rr.SPONSOR]["response"] == M, (
            "one tenant's update must not touch another tenant's row")


class TestTheCascade:
    """documents -> versions -> responses, proven where the suite actually runs.

    Codex (MEDIUM, 2026-07-18) noted the SQLite mirror could not demonstrate this because it
    had no parent table and no enforced FKs. Both are fixed, so the chain is now testable --
    a deleted document must not leave orphaned versions or, worse, orphaned ACCEPTANCES
    floating in the database with nothing to attach to.
    """

    def test_deleting_a_document_removes_its_versions_and_their_responses(self, db):
        rr.save_version(db, TENANT, DOC, "# v1")
        rr.record_response(db, TENANT, DOC, version_number=1,
                           recipient_kind=rr.SPONSOR, response=A)
        assert rr.list_versions(db, TENANT, DOC)
        assert rr.responses_for(db, TENANT, DOC, 1)

        db.execute("DELETE FROM enterprise_documents WHERE tenant_id = ? AND id = ?",
                   (TENANT, DOC))

        assert rr.list_versions(db, TENANT, DOC) == []
        assert rr.responses_for(db, TENANT, DOC, 1) == {}, (
            "an acceptance must not outlive the document it accepted")

    def test_a_version_cannot_be_stored_for_a_document_that_does_not_exist(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            rr.save_version(db, TENANT, 12345, "# orphan")

    def test_a_version_cannot_attach_to_another_tenants_document(self, db):
        """The composite FK carries tenant_id precisely so this is impossible at the database,
        not merely discouraged in application code.
        """
        with pytest.raises(sqlite3.IntegrityError):
            rr.save_version(db, TENANT, OTHER_DOC, "# not mine")


class TestTenantIsolation:
    """Directive s6: every protected read filters by tenant_id."""

    def test_one_tenant_cannot_see_another_tenants_versions(self, db):
        rr.save_version(db, TENANT, DOC, "# mine")
        assert rr.list_versions(db, OTHER_TENANT, DOC) == []
        assert rr.get_version(db, OTHER_TENANT, DOC, 1) is None

    def test_one_tenant_cannot_see_another_tenants_responses(self, db):
        rr.save_version(db, TENANT, DOC, "# mine")
        rr.record_response(db, TENANT, DOC, version_number=1,
                           recipient_kind=rr.SPONSOR, response=A)
        assert rr.responses_for(db, OTHER_TENANT, DOC, 1) == {}

    def test_another_tenants_acceptance_cannot_advance_my_report(self, db):
        """The isolation failure with real consequences: if tenant scoping leaked, another
        tenant's acceptances would satisfy MY report's acceptance rule.
        """
        rr.save_version(db, OTHER_TENANT, OTHER_DOC, "# theirs")
        for kind in rr.RECIPIENT_KINDS:
            rr.record_response(db, OTHER_TENANT, OTHER_DOC, version_number=1,
                               recipient_kind=kind, response=A)
        rr.save_version(db, TENANT, DOC, "# mine")

        assert rr.status_for(db, OTHER_TENANT, OTHER_DOC, 1) == rr.ACCEPTED_BY_BOTH
        assert rr.status_for(db, TENANT, DOC, 1) == rr.AWAITING_RESPONSES

    def test_reading_a_real_document_with_the_wrong_tenant_returns_nothing(self, db):
        """The reachable attack shape: the id is real, the tenant is not yours."""
        rr.save_version(db, OTHER_TENANT, OTHER_DOC, "# theirs")
        assert rr.get_version(db, TENANT, OTHER_DOC, 1) is None
        assert rr.list_versions(db, TENANT, OTHER_DOC) == []
        assert rr.responses_for(db, TENANT, OTHER_DOC, 1) == {}

    def test_two_tenants_number_their_versions_independently(self, db):
        assert rr.save_version(db, TENANT, DOC, "# a") == 1
        assert rr.save_version(db, OTHER_TENANT, OTHER_DOC, "# b") == 1
