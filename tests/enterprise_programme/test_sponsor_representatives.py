"""Who may sign for a funding institution — the missing half of level-3 approval.

THE DEFECT THESE PIN (found 2026-07-25 by querying the live DB, not by reading code):
`enterprise_sponsor_users` was EMPTY on production and `link_sponsor_user()` had no caller
outside tests — no route, no UI. Both readers hard-gate on that table (`sponsor_inbox` and
`_sponsor_institution_for` return early on an empty result), so the sponsor approval tier
could never fire for anybody. Applications would reach level 3 and stall there forever.

The security property that matters most here is NOT that granting works — it is WHO may
grant. A signing right is platform-wide (migration 031: "the same bank may sponsor two
ministries' programmes"), so its holder can approve applications belonging to OTHER
organisations. If a programme owner could appoint a signatory for a bank their own programme
names, they could self-approve their own level 3.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.enterprise_programme import applications

# IMPORTED AT MODULE SCOPE, ON PURPOSE -- the same trap test_ops_support.py documents.
# wsgi.py registers the enterprise routes onto the SHARED Flask app, and Flask refuses to add
# a route once that app has served its first request. Test modules are imported during
# COLLECTION, before any test runs, so this is the only point where registration is
# guaranteed to succeed. Importing it inside a test made these pass alone and fail in the
# full suite with "The setup method 'route' can no longer be called on the application" --
# which is worse than a plain failure, because the route genuinely is absent at that point
# and an `assert != 200` would have PASSED for the wrong reason.
import wsgi as _wsgi


@pytest.fixture
def db():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)")
    c.executemany("INSERT INTO users (id, username) VALUES (?,?)",
                  [(1, "admin"), (2, "bank_rep"), (3, "ministry_owner")])
    c.execute(
        "CREATE TABLE enterprise_sponsor_users ("
        "  institution_id TEXT NOT NULL, user_id INTEGER NOT NULL,"
        "  added_by_user_id INTEGER, created_at TEXT DEFAULT '2026-07-25',"
        "  PRIMARY KEY (institution_id, user_id))"
    )
    return c


class TestTheLinkTableCanFinallyBeManaged:
    """Before this, the only writer was a test. That is what made level 3 unreachable."""

    def test_granting_makes_a_signatory_visible(self, db):
        applications.link_sponsor_user(db, "INST-1", 2, added_by_user_id=1)
        rows = applications.list_sponsor_users(db)
        assert len(rows) == 1
        assert rows[0]["institution_id"] == "INST-1"
        assert rows[0]["user_id"] == 2
        assert rows[0]["username"] == "bank_rep"
        assert rows[0]["added_by_user_id"] == 1

    def test_granting_twice_updates_rather_than_duplicating(self, db):
        """ON CONFLICT, not a second row: a person signs for an institution once."""
        applications.link_sponsor_user(db, "INST-1", 2, added_by_user_id=1)
        applications.link_sponsor_user(db, "INST-1", 2, added_by_user_id=3)
        rows = applications.list_sponsor_users(db)
        assert len(rows) == 1
        assert rows[0]["added_by_user_id"] == 3, "the re-grant should record the new granter"

    def test_revoking_removes_exactly_one_link(self, db):
        """Authority you cannot take back is not an authorisation model."""
        applications.link_sponsor_user(db, "INST-1", 2, added_by_user_id=1)
        applications.link_sponsor_user(db, "INST-2", 2, added_by_user_id=1)
        applications.unlink_sponsor_user(db, "INST-1", 2)
        left = applications.list_sponsor_users(db)
        assert [r["institution_id"] for r in left] == ["INST-2"], \
            "revoking one institution must not revoke the other"

    def test_revoking_something_that_is_not_there_is_harmless(self, db):
        applications.unlink_sponsor_user(db, "INST-NOPE", 999)
        assert applications.list_sponsor_users(db) == []

    def test_a_link_to_a_deleted_user_is_still_listed(self, db):
        """LEFT JOIN on purpose. An inner join would HIDE the stale grants an operator most
        needs to see — the signing right outlives the account and must remain revocable.
        """
        applications.link_sponsor_user(db, "INST-1", 2, added_by_user_id=1)
        db.execute("DELETE FROM users WHERE id=2")
        rows = applications.list_sponsor_users(db)
        assert len(rows) == 1, "a dangling grant must not disappear from the screen"
        assert rows[0]["user_id"] == 2
        assert rows[0]["username"] is None

    def test_listing_survives_a_missing_table(self):
        """A database where the module was never used returns [], not a 500."""
        bare = sqlite3.connect(":memory:")
        assert applications.list_sponsor_users(bare) == []


class TestTheRouteIsAdminOnlyAndFailsClosed:
    """The guard is the point of this feature, not a detail of it."""

    def test_the_route_is_registered(self):
        rules = {str(r.rule) for r in _wsgi.app.url_map.iter_rules()}
        assert "/enterprise/sponsors/representatives" in rules, \
            "the capability must exist — its absence is the bug being fixed"

    def test_an_anonymous_caller_cannot_reach_it(self):
        r = _wsgi.app.test_client().get("/enterprise/sponsors/representatives")
        assert r.status_code != 200

    def test_a_logged_in_non_admin_cannot_reach_it(self):
        """The escalation this prevents: a programme owner appointing the person who
        approves their own programme's funding.
        """
        c = _wsgi.app.test_client()
        with c.session_transaction() as s:
            s.update({"user_id": 3, "username": "ministry_owner", "is_admin": False})
        assert c.get("/enterprise/sponsors/representatives").status_code != 200

    def test_a_missing_admin_guard_denies_rather_than_opens(self):
        """wsgi.py swallows registration errors and only logs, so this dependency is
        OPTIONAL — but optional must mean DENY, never "no guard". A wiring mistake has to
        cost the feature, not the boundary.
        """
        from flask import Flask
        import enterprise_programme_routes as epr

        probe = Flask(__name__)
        epr.register_enterprise_programme(
            probe,
            get_db=lambda: (_ for _ in ()).throw(AssertionError("must not reach the DB")),
            login_required=lambda fn: fn,
            csrf_protect=lambda: None,
            current_user=lambda: {"id": 1, "is_admin": True},
            # admin_required deliberately NOT passed
        )
        r = probe.test_client().get("/enterprise/sponsors/representatives")
        assert r.status_code == 403, "a missing guard must fail closed"


class TestRevocationIsNeverBlockedByGrantTimeValidation:
    """Codex HIGH against the first version of this route.

    The approved-institution check ran BEFORE the action branch, so it blocked REVOKE as
    well as GRANT. That mattered because sponsor authorisation keys on
    `enterprise_sponsor_users` against the programme's NAMED sponsors, NOT against current
    approval status: de-approving a bank does not disarm a signing right it already holds.
    So an institution that was later un-approved left its signatory with authority the admin
    could see on screen and could never remove — permanent authority.

    The rule these pin: a check that guards handing OUT authority must never block TAKING IT
    BACK. Removing authority cannot escalate anything.
    """

    def _post(self, client, **form):
        return client.post("/enterprise/sponsors/representatives",
                           data=form, follow_redirects=False)

    def test_revoke_path_does_not_consult_the_approved_list(self):
        """Asserted at the source: the revoke branch must return BEFORE approved_sponsors()
        is consulted, so a de-approved institution is still revocable.
        """
        import inspect
        import enterprise_programme_routes as epr
        src = inspect.getsource(epr.register_enterprise_programme)
        start = src.index("def enterprise_sponsor_representatives")
        body = src[start:start + 4000]
        revoke_at = body.index('action == "revoke"')
        approved_at = body.index("approved_sponsors(c)")
        assert revoke_at < approved_at, (
            "the revoke branch must be reached BEFORE the approved-institution check; "
            "otherwise a de-approved institution's signing right can never be removed"
        )

    def test_unlink_itself_imposes_no_approval_precondition(self, db):
        """The data layer must stay unconditional — the safety property lives here too."""
        applications.link_sponsor_user(db, "INST-GONE", 2, added_by_user_id=1)
        # No institution registry involved at all; revocation simply works.
        applications.unlink_sponsor_user(db, "INST-GONE", 2)
        assert applications.list_sponsor_users(db) == []

    def test_a_grant_to_a_deleted_user_can_still_be_revoked(self, db):
        """Revoke must not require the user to exist: the dangling row is exactly the one
        that most needs cleaning up.
        """
        applications.link_sponsor_user(db, "INST-1", 2, added_by_user_id=1)
        db.execute("DELETE FROM users WHERE id=2")
        applications.unlink_sponsor_user(db, "INST-1", 2)
        assert applications.list_sponsor_users(db) == []


    def test_an_unknown_action_grants_nothing(self):
        """Codex MED: `else: grant` is fail-open dispatch.

        A typo'd or crafted action reaching the branch that HANDS OUT authority is the wrong
        default for an authorisation surface. Asserted at the source: the allow-list check
        must precede both the revoke branch and link_sponsor_user().
        """
        import inspect
        import enterprise_programme_routes as epr
        src = inspect.getsource(epr.register_enterprise_programme)
        start = src.index("def enterprise_sponsor_representatives")
        body = src[start:start + 4000]
        guard_at = body.index('action not in ("grant", "revoke")')
        link_at = body.index("link_sponsor_user(c, inst, target, uid)")
        revoke_at = body.index('action == "revoke"')
        assert guard_at < revoke_at < link_at, (
            "an unrecognised action must be rejected before either branch can run"
        )
