"""Assigning installers and suppliers to a site.

OWNER, 2026-07-18: "in the planning stage the installation must be assigned to installer and
suppliers, so reuse the installer and supplier list and bidding to select and sign qualified
contractors and suppliers to a particular site."

The two properties worth protecting:

  * REUSE -- the marketplace supplier list and the existing bids are read, never copied. A
    second supplier table would drift from the first the day someone edits either.
  * ONE ANSWER PER SITE -- "who is the installer here" must have exactly one answer, or the
    record cannot be acted on.
"""

import sqlite3

import pytest

from app.enterprise_programme import site_assignments as sa
from app.enterprise_programme.site_assignments import AssignmentError

TENANT = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
PROG, SITE, SITE2 = 1, 10, 11


@pytest.fixture()
def db():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON")
    # The marketplace tables, as the app really has them -- read, never written, by this
    # module. Only the columns it touches.
    c.execute("""CREATE TABLE suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, country TEXT DEFAULT '',
        contact_name TEXT DEFAULT '', phone TEXT DEFAULT '', email TEXT DEFAULT '',
        categories TEXT DEFAULT '', lead_time_days INTEGER DEFAULT 30,
        rating INTEGER DEFAULT 5, is_active INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE rfq_responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT, rfq_id INTEGER NOT NULL,
        supplier_id INTEGER NOT NULL, total_price REAL DEFAULT 0,
        currency TEXT DEFAULT 'USD', lead_time_days INTEGER DEFAULT 30,
        valid_until TEXT DEFAULT '')""")
    c.execute("""CREATE TABLE enterprise_sites (
        id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL, programme_id INTEGER NOT NULL)""")
    for sid in (SITE, SITE2):
        c.execute("INSERT INTO enterprise_sites (id, tenant_id, programme_id) VALUES (?,?,?)",
                  (sid, TENANT, PROG))

    c.executemany("INSERT INTO suppliers (id, name, rating, is_active) VALUES (?,?,?,?)",
                  [(1, "Bright Solar EPC", 5, 1),
                   (2, "Coastal Installers", 4, 1),
                   (3, "Dormant Trading Co", 5, 0)])      # deactivated
    c.executemany("INSERT INTO rfq_responses "
                  "(id, rfq_id, supplier_id, total_price, currency, lead_time_days) "
                  "VALUES (?,?,?,?,?,?)",
                  [(100, 7, 1, 48250.0, "GHS", 45),
                   (101, 7, 2, 51000.0, "GHS", 30)])
    sa.ensure_schema(c)
    yield c
    c.close()


class TestItReusesWhatAlreadyExists:
    """The owner said "reuse". A second copy of a supplier is the failure."""

    def test_the_supplier_list_is_the_marketplace_list(self, db):
        names = [s["name"] for s in sa.qualified_suppliers(db)]
        assert "Bright Solar EPC" in names
        assert "Coastal Installers" in names

    def test_a_deactivated_company_is_never_offered_work(self, db):
        """"Select and sign QUALIFIED contractors" -- offering a company that is no longer
        trading is how a programme awards work to someone who cannot do it.
        """
        assert "Dormant Trading Co" not in [s["name"] for s in sa.qualified_suppliers(db)]

    def test_best_rated_first(self, db):
        assert sa.qualified_suppliers(db)[0]["name"] == "Bright Solar EPC"

    def test_bids_come_from_the_existing_rfq_responses(self, db):
        bids = sa.bids_for_supplier(db, 1)
        assert len(bids) == 1
        assert bids[0]["total_price"] == 48250.0
        assert bids[0]["currency"] == "GHS"
        assert bids[0]["rfq_id"] == 7

    def test_a_missing_marketplace_does_not_break_planning(self, db):
        """The marketplace tables live in the app schema, not the enterprise migration set.
        On a database without them the Planning page must still render.
        """
        db.execute("DROP TABLE suppliers")
        db.execute("DROP TABLE rfq_responses")
        assert sa.qualified_suppliers(db) == []
        assert sa.bids_for_supplier(db, 1) == []


class TestSelectThenSign:
    """The owner's two words are two decisions, usually by different people."""

    def test_the_happy_path(self, db):
        aid = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER,
                           supplier_id=1, supplier_name="Bright Solar EPC")
        bid = sa.bids_for_supplier(db, 1)[0]
        sa.award(db, TENANT, aid, response_id=bid["response_id"], rfq_id=bid["rfq_id"],
                 price=bid["total_price"], currency=bid["currency"],
                 lead_time_days=bid["lead_time_days"])
        sa.sign(db, TENANT, aid)

        got = sa.for_site(db, TENANT, SITE)[0]
        assert got["status"] == sa.SIGNED
        assert got["awarded_price"] == 48250.0
        assert got["signed_at"]

    def test_the_award_records_WHICH_BID_it_came_from(self, db):
        """An award with no bid behind it is a name with no evidence -- nobody can answer
        "on what basis was this contractor chosen, and at what price".
        """
        aid = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        bid = sa.bids_for_supplier(db, 1)[0]
        sa.award(db, TENANT, aid, response_id=bid["response_id"], rfq_id=bid["rfq_id"],
                 price=bid["total_price"], currency=bid["currency"])

        got = sa.for_site(db, TENANT, SITE)[0]
        assert got["source_response_id"] == 100
        assert got["source_rfq_id"] == 7

    def test_the_awarded_price_does_not_follow_the_supplier_s_later_quotes(self, db):
        """A quote is a point-in-time commitment. If the supplier revises their prices, what
        they were AWARDED must not silently change with it.
        """
        aid = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        sa.award(db, TENANT, aid, response_id=100, rfq_id=7, price=48250.0, currency="GHS")
        db.execute("UPDATE rfq_responses SET total_price = 99999 WHERE id = 100")
        assert sa.for_site(db, TENANT, SITE)[0]["awarded_price"] == 48250.0

    def test_a_company_cannot_be_signed_without_being_awarded(self, db):
        aid = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        with pytest.raises(AssignmentError):
            sa.sign(db, TENANT, aid)

    def test_a_signed_contract_is_not_undone_by_editing_a_status(self, db):
        """Ending a signed contract is a commercial act, not a dropdown change."""
        aid = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        sa.award(db, TENANT, aid)
        sa.sign(db, TENANT, aid)
        with pytest.raises(AssignmentError):
            sa.withdraw(db, TENANT, aid)

    def test_the_database_refuses_a_signed_row_with_no_signing_date(self, db):
        """A contract with no date is not evidence of anything, and this is the row an
        auditor reads. Enforced in the schema, not only in Python.
        """
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO enterprise_site_assignments "
                "(tenant_id, programme_id, site_id, party_role, supplier_id, status) "
                "VALUES (?,?,?,?,?,?)", (TENANT, PROG, SITE, sa.INSTALLER, 1, sa.SIGNED))


class TestOneAnswerPerSite:

    def test_a_site_cannot_have_two_awarded_installers(self, db):
        """Two awarded installers is not a richer record, it is an unanswerable question."""
        a = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        b = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=2)
        sa.award(db, TENANT, a)
        with pytest.raises(AssignmentError, match="already has an awarded"):
            sa.award(db, TENANT, b)

    def test_but_a_site_may_have_an_installer_AND_a_supplier(self, db):
        a = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        b = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.SUPPLIER, supplier_id=2)
        sa.award(db, TENANT, a)
        sa.award(db, TENANT, b)          # different role, no clash
        assert len(sa.for_site(db, TENANT, SITE)) == 2

    def test_withdrawing_the_first_frees_the_role(self, db):
        a = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        b = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=2)
        sa.award(db, TENANT, a)
        sa.withdraw(db, TENANT, a)
        sa.award(db, TENANT, b)          # now legitimate
        assert [x["status"] for x in sa.for_site(db, TENANT, SITE)
                if x["supplier_id"] == 2] == [sa.AWARDED]

    def test_the_same_company_can_work_on_two_different_sites(self, db):
        sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        sa.shortlist(db, TENANT, PROG, SITE2, party_role=sa.INSTALLER, supplier_id=1)
        assert len(sa.for_site(db, TENANT, SITE)) == 1
        assert len(sa.for_site(db, TENANT, SITE2)) == 1

    def test_shortlisting_the_same_company_twice_is_refused_not_duplicated(self, db):
        sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        with pytest.raises(AssignmentError):
            sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)


class TestTheProcurementRecordSurvives:

    def test_withdrawing_keeps_the_row(self, db):
        """Who was CONSIDERED is part of the record. Deleting it is how that disappears the
        year someone questions the decision.
        """
        aid = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        sa.withdraw(db, TENANT, aid)
        rows = sa.for_site(db, TENANT, SITE)
        assert len(rows) == 1
        assert rows[0]["status"] == sa.WITHDRAWN

    def test_someone_withdrawn_can_be_reconsidered(self, db):
        aid = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        sa.withdraw(db, TENANT, aid)
        again = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        assert again == aid, "reconsidering must reuse the row, not start a second history"
        assert sa.for_site(db, TENANT, SITE)[0]["status"] == sa.SHORTLISTED


class TestCoverage:
    """The number a planner is actually asked for."""

    def test_it_counts_sites_without_an_installer(self, db):
        aid = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        sa.award(db, TENANT, aid)
        cov = sa.coverage(db, TENANT, PROG)
        assert cov["sites"] == 2
        assert cov["sites_with_installer"] == 1
        assert cov["sites_without_installer"] == 1

    def test_a_shortlisted_company_does_not_count_as_covered(self, db):
        """Being considered is not being hired -- counting it would report a programme as
        staffed when nobody has agreed to anything.
        """
        sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        assert sa.coverage(db, TENANT, PROG)["sites_without_installer"] == 2


class TestTenantIsolation:

    def test_another_tenant_sees_none_of_it(self, db):
        sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        assert sa.for_site(db, OTHER, SITE) == []

    def test_another_tenant_cannot_move_my_assignment(self, db):
        aid = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        with pytest.raises(AssignmentError):
            sa.award(db, OTHER, aid)
        assert sa.for_site(db, TENANT, SITE)[0]["status"] == sa.SHORTLISTED

    def test_coverage_is_scoped(self, db):
        aid = sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=1)
        sa.award(db, TENANT, aid)
        assert sa.coverage(db, OTHER, PROG)["sites_with_installer"] == 0


class TestBadInput:

    @pytest.mark.parametrize("role", ["contractor", "INSTALLER", "", "vendor"])
    def test_an_unknown_role_is_refused(self, db, role):
        with pytest.raises(AssignmentError):
            sa.shortlist(db, TENANT, PROG, SITE, party_role=role, supplier_id=1)

    def test_an_assignment_with_no_supplier_is_refused(self, db):
        with pytest.raises(AssignmentError):
            sa.shortlist(db, TENANT, PROG, SITE, party_role=sa.INSTALLER, supplier_id=0)

    def test_moving_an_assignment_that_does_not_exist(self, db):
        with pytest.raises(AssignmentError):
            sa.award(db, TENANT, 99999)
