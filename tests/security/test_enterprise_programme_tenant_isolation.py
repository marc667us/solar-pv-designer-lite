"""Enterprise Programme Module -- tenant isolation + IDOR tests.

Phase 1's tenant boundary is enforced in the APPLICATION layer
(enterprise_programme_repository), because Postgres RLS on the enterprise tables
is ENABLE-not-FORCE and is therefore defence in depth only. That makes these
tests the actual proof of isolation, not a formality. If they fail, the module
is not safe to enable.

Proven here:
  1. User B cannot read user A's programme (org-scoped SELECT).
  2. User B cannot mutate user A's programme, phases, or beneficiaries.
  3. User B cannot LINK user A's project -- the IDOR that would turn the
     enterprise module into a back door into someone else's design.
  4. A user with no membership reaches no programme at all.
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import enterprise_programme_repository as repo    # noqa: E402
import enterprise_programme_services as svc       # noqa: E402

# Registered at IMPORT time -- Flask rejects new routes/context processors once the
# app has served a request, which it will have if another test module ran first.
import web_app as _wa                             # noqa: E402
from enterprise_programme_routes import register_enterprise_programme  # noqa: E402

if "enterprise_home" not in _wa.app.view_functions:
    register_enterprise_programme(
        _wa.app, get_db=_wa.get_db, login_required=_wa.login_required,
        csrf_protect=_wa.csrf_protect, current_user=_wa.current_user,
    )


@pytest.fixture(scope="module")
def two_tenants(tmp_path_factory):
    """Two users, each in their OWN organisation, each with their own project."""
    db_path = str(tmp_path_factory.mktemp("entiso") / "iso.db")
    os.environ.pop("DATABASE_URL", None)
    os.environ.setdefault("SECRET_KEY", "test-secret-key-enterprise-iso")

    wa = _wa
    _original_db = wa.DB_PATH
    wa.DB_PATH = db_path
    wa.init_db()
    wa.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    repo.ensure_enterprise_schema(wa.get_db)

    conn = sqlite3.connect(db_path)
    ids = {}
    for name in ("alice", "bob", "carol"):
        conn.execute(
            "INSERT OR IGNORE INTO users (username, email, password_hash, "
            "email_verified, plan, is_admin, name) VALUES (?,?,'',1,'free',0,?)",
            (name, f"{name}@example.com", name.title()),
        )
    conn.commit()
    for name in ("alice", "bob", "carol"):
        ids[name] = conn.execute(
            "SELECT id FROM users WHERE username=?", (name,)
        ).fetchone()[0]

    # Each of alice/bob owns one standard project.
    projects = {}
    for name in ("alice", "bob"):
        cur = conn.execute(
            "INSERT INTO projects (user_id, name, data_json) VALUES (?,?,?)",
            (ids[name], f"{name}'s project", "{}"),
        )
        projects[name] = cur.lastrowid
    conn.commit()
    conn.close()

    # Alice and Bob each bootstrap their own organisation. Carol has none.
    org_a = repo.bootstrap_organisation(wa.get_db, ids["alice"], "Alice Ministry")
    org_b = repo.bootstrap_organisation(wa.get_db, ids["bob"], "Bob Utility")
    assert org_a != org_b

    prog_a = repo.create_programme(wa.get_db, org_a, ids["alice"], {
        "programme_code": "A-001", "name": "Alice Secret Programme",
        "design_strategy": "standard",
    })

    yield {
        "wa": wa, "ids": ids, "projects": projects,
        "org_a": org_a, "org_b": org_b, "prog_a": prog_a,
    }

    # Restore the shared global so a later suite doesn't inherit our temp DB.
    wa.DB_PATH = _original_db


# --- 1. cross-tenant READ ---------------------------------------------------

def test_other_tenant_cannot_read_programme(two_tenants):
    t = two_tenants
    wa, ids = t["wa"], t["ids"]

    # Bob, scoped to HIS org, asking for Alice's programme id.
    assert repo.get_programme(wa.get_db, t["org_b"], ids["bob"], t["prog_a"]) is None

    # And the dashboard refuses to assemble it.
    assert svc.programme_dashboard(wa.get_db, t["org_b"], ids["bob"], t["prog_a"]) is None


def test_other_tenant_programme_list_does_not_leak(two_tenants):
    t = two_tenants
    wa, ids = t["wa"], t["ids"]

    rows, total = repo.list_programmes(wa.get_db, t["org_b"], ids["bob"])
    assert total == 0
    assert rows == []


# --- 2. cross-tenant WRITE --------------------------------------------------

def test_other_tenant_cannot_mutate_programme(two_tenants):
    t = two_tenants
    wa, ids = t["wa"], t["ids"]

    assert repo.update_programme(
        wa.get_db, t["org_b"], ids["bob"], t["prog_a"], {"name": "PWNED"}
    ) is False

    # Alice's programme is untouched.
    p = repo.get_programme(wa.get_db, t["org_a"], ids["alice"], t["prog_a"])
    assert p["name"] == "Alice Secret Programme"


def test_other_tenant_cannot_add_phase_or_beneficiary(two_tenants):
    t = two_tenants
    wa, ids = t["wa"], t["ids"]

    assert repo.add_phase(
        wa.get_db, t["org_b"], ids["bob"], t["prog_a"], {"name": "Injected phase"}
    ) is None
    assert repo.add_beneficiary(
        wa.get_db, t["org_b"], ids["bob"], t["prog_a"], {"name": "Injected beneficiary"}
    ) is None


# --- 3. THE IDOR: linking someone else's project ----------------------------

def test_user_cannot_link_another_users_project(two_tenants):
    """The one that matters.

    Bob owns a programme. Alice owns project #N. Bob must NOT be able to pull
    Alice's project into his programme by guessing its integer id -- that would
    make the enterprise module a back door into another user's design, BOQ and
    financials.
    """
    t = two_tenants
    wa, ids, projects = t["wa"], t["ids"], t["projects"]

    prog_b = repo.create_programme(wa.get_db, t["org_b"], ids["bob"], {
        "programme_code": "B-001", "name": "Bob Programme",
        "design_strategy": "standard",
    })

    ok, message = repo.link_project(
        wa.get_db, t["org_b"], ids["bob"], prog_b, "standard",
        projects["alice"],            # <-- Alice's project id
    )
    assert ok is False
    assert "own" in message.lower()

    assert repo.list_links(wa.get_db, t["org_b"], ids["bob"], prog_b) == []


def test_user_can_link_their_own_project(two_tenants):
    """The positive control -- the guard must not block the legitimate case."""
    t = two_tenants
    wa, ids, projects = t["wa"], t["ids"], t["projects"]

    prog_b2 = repo.create_programme(wa.get_db, t["org_b"], ids["bob"], {
        "programme_code": "B-002", "name": "Bob Programme 2",
        "design_strategy": "standard",
    })

    ok, _ = repo.link_project(
        wa.get_db, t["org_b"], ids["bob"], prog_b2, "standard", projects["bob"],
    )
    assert ok is True
    assert len(repo.list_links(wa.get_db, t["org_b"], ids["bob"], prog_b2)) == 1


def test_ownership_predicate_itself(two_tenants):
    """user_owns_project reuses the app's existing ownership contract."""
    t = two_tenants
    wa, ids, projects = t["wa"], t["ids"], t["projects"]

    assert repo.user_owns_project(wa.get_db, ids["bob"], "standard", projects["bob"])
    assert not repo.user_owns_project(wa.get_db, ids["bob"], "standard", projects["alice"])
    # an unknown project kind is refused rather than guessed at
    assert not repo.user_owns_project(wa.get_db, ids["bob"], "wat", projects["bob"])


# --- 3b. cross-reference IDOR (Codex gate 1, 2x HIGH) -----------------------
# A foreign key proves an id EXISTS. It does NOT prove the row is YOURS. These
# two tests exist because the first implementation validated project ownership
# but trusted the optional phase_id / beneficiary_id straight from the form.

def test_cannot_attach_beneficiary_to_another_orgs_phase(two_tenants):
    """Bob must not be able to point his beneficiary at Alice's phase."""
    t = two_tenants
    wa, ids = t["wa"], t["ids"]

    alice_phase = repo.add_phase(
        wa.get_db, t["org_a"], ids["alice"], t["prog_a"], {"name": "Alice Phase 1"}
    )
    assert alice_phase is not None

    prog_b = repo.create_programme(wa.get_db, t["org_b"], ids["bob"], {
        "programme_code": "B-XREF1", "name": "Bob XRef Programme",
        "design_strategy": "standard",
    })

    # Bob's own programme, but Alice's phase id smuggled in via the form.
    bid = repo.add_beneficiary(wa.get_db, t["org_b"], ids["bob"], prog_b, {
        "name": "Crafted Beneficiary", "phase_id": alice_phase,
    })
    assert bid is None, "must refuse a phase_id belonging to another organisation"

    rows, total = repo.list_beneficiaries(wa.get_db, t["org_b"], ids["bob"], prog_b)
    assert total == 0

    # sanity: the guard itself
    assert not repo.phase_belongs_to(wa.get_db, t["org_b"], prog_b, alice_phase)
    assert repo.phase_belongs_to(wa.get_db, t["org_a"], t["prog_a"], alice_phase)


def test_cannot_link_project_against_another_orgs_beneficiary(two_tenants):
    """Bob links HIS OWN project, but names Alice's beneficiary. Must be refused."""
    t = two_tenants
    wa, ids, projects = t["wa"], t["ids"], t["projects"]

    alice_ben = repo.add_beneficiary(
        wa.get_db, t["org_a"], ids["alice"], t["prog_a"], {"name": "Alice School"}
    )
    assert alice_ben is not None

    prog_b = repo.create_programme(wa.get_db, t["org_b"], ids["bob"], {
        "programme_code": "B-XREF2", "name": "Bob XRef Programme 2",
        "design_strategy": "standard",
    })

    ok, message = repo.link_project(
        wa.get_db, t["org_b"], ids["bob"], prog_b, "standard",
        projects["bob"],                 # Bob's own project -- ownership is fine
        beneficiary_id=alice_ben,        # ...but Alice's beneficiary
    )
    assert ok is False
    assert "beneficiary" in message.lower()
    assert repo.list_links(wa.get_db, t["org_b"], ids["bob"], prog_b) == []


# --- 4. no membership = no access ------------------------------------------

def test_user_without_membership_has_no_organisation(two_tenants):
    t = two_tenants
    wa, ids = t["wa"], t["ids"]

    assert repo.get_active_membership(wa.get_db, ids["carol"]) is None


def test_unlink_cannot_touch_another_tenants_link(two_tenants):
    t = two_tenants
    wa, ids = t["wa"], t["ids"]

    prog_a_link = repo.create_programme(wa.get_db, t["org_a"], ids["alice"], {
        "programme_code": "A-LINK", "name": "Alice Linked Programme",
        "design_strategy": "standard",
    })
    ok, _ = repo.link_project(
        wa.get_db, t["org_a"], ids["alice"], prog_a_link, "standard",
        t["projects"]["alice"],
    )
    assert ok
    link_id = repo.list_links(wa.get_db, t["org_a"], ids["alice"], prog_a_link)[0]["id"]

    # Bob tries to delete Alice's link.
    assert repo.unlink_project(
        wa.get_db, t["org_b"], ids["bob"], prog_a_link, link_id
    ) is False
    assert len(repo.list_links(wa.get_db, t["org_a"], ids["alice"], prog_a_link)) == 1
