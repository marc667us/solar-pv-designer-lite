"""Slice 3 -- the /enterprise routes on the rebuilt module.

This file REPLACES tests/test_enterprise_programme_foundation.py, whose route assertions
targeted the Phase-1 module that this rebuild supersedes. The old module's data layer is
still covered by tests/security/test_enterprise_programme_tenant_isolation.py.

WHAT THESE PROVE, beyond "the page renders"
-------------------------------------------
  * DARK by default -- a 404, not a 403, so a disabled module is indistinguishable from
    one that was never deployed.
  * A tenant id in the SESSION is a hint, not an authority: tamper with it and you land in
    your own tenant, never someone else's.
  * Another tenant's programme is a 404 through the HTTP surface too (control C13).
  * The gate button is not the guard: POSTing the approve URL directly still fails unless
    you are the sponsor the programme NAMED.
  * The dropdown never offers a move the server would refuse.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

# Register at IMPORT time, not in a fixture: Flask refuses new routes once the app has
# handled its first request, and another test module may already have issued one.
import web_app as _wa  # noqa: E402
from enterprise_programme_routes import register_enterprise_programme  # noqa: E402

from app.enterprise_programme import flags, tenancy, workflows  # noqa: E402

if "enterprise_home" not in _wa.app.view_functions:
    register_enterprise_programme(
        _wa.app, get_db=_wa.get_db, login_required=_wa.login_required,
        csrf_protect=_wa.csrf_protect, current_user=_wa.current_user,
    )


@pytest.fixture(scope="module")
def ent(tmp_path_factory):
    """Flask test client on a temp SQLite DB, with two real users."""
    db_path = str(tmp_path_factory.mktemp("ent3") / "ent.db")
    os.environ.pop("DATABASE_URL", None)  # force the SQLite path
    os.environ.setdefault("SECRET_KEY", "test-secret-key-enterprise-3")

    wa = _wa
    original_db = wa.DB_PATH
    wa.DB_PATH = db_path
    wa.init_db()
    wa.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    if hasattr(wa, "limiter"):
        try:
            wa.limiter.enabled = False
        except Exception:
            pass

    conn = sqlite3.connect(db_path)
    for name in ("alice", "mallory"):
        conn.execute(
            "INSERT OR IGNORE INTO users (username, email, password_hash, email_verified,"
            " plan, is_admin, name) VALUES (?,?,'',1,'free',0,?)",
            (name, f"{name}@example.com", name.title()),
        )
    conn.commit()
    ids = {
        n: conn.execute("SELECT id FROM users WHERE username=?", (n,)).fetchone()[0]
        for n in ("alice", "mallory")
    }
    conn.close()

    with wa.app.test_client() as client:
        yield client, wa, ids

    # DB_PATH is a module global shared with every other test module. Put it back, or
    # whichever suite runs next silently talks to our temp database.
    wa.DB_PATH = original_db


def _login(client, uid):
    with client.session_transaction() as s:
        s.clear()
        s["user_id"] = uid
        s["_csrf"] = "testtoken"


def _flag(wa, on: bool):
    """Flip the rebuild's flag directly. module_enabled() caches for 60s, so drop it."""
    with wa.get_db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS admin_settings "
                  "(key TEXT PRIMARY KEY, value TEXT NOT NULL, "
                  " updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        c.execute("INSERT OR REPLACE INTO admin_settings (key, value) VALUES (?,?)",
                  (flags.FLAG_ENABLED, "1" if on else "0"))
    flags.clear_cache()


# --- the flag ---------------------------------------------------------------


def test_module_is_dark_by_default(ent):
    """A 404, not a 403: a disabled module must look like one that was never deployed."""
    client, wa, ids = ent
    _flag(wa, False)
    _login(client, ids["alice"])
    assert client.get("/enterprise").status_code == 404
    assert client.get("/enterprise/programmes/new").status_code == 404


def test_home_renders_when_the_flag_is_on(ent):
    client, wa, ids = ent
    _flag(wa, True)
    _login(client, ids["alice"])
    r = client.get("/enterprise")
    assert r.status_code == 200
    # Every user has a personal workspace, so the switcher is never empty.
    assert b"personal workspace" in r.data


# --- onboarding + programme registration ------------------------------------


def test_create_organisation_then_programme_seeds_the_whole_lifecycle(ent):
    client, wa, ids = ent
    _flag(wa, True)
    _login(client, ids["alice"])

    r = client.post("/enterprise/onboarding", data={
        "_csrf": "testtoken", "legal_name": "Ministry of Energy",
        "organisation_type": "ministry", "country": "Ghana",
    }, follow_redirects=True)
    assert r.status_code == 200

    r = client.post("/enterprise/programmes/new", data={
        "_csrf": "testtoken", "code": "GH-SCHOOLS-01",
        "name": "Ghana Schools Solar", "design_strategy": "standard",
        "sponsor_user_id": str(ids["alice"]), "country": "Ghana",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"Ghana Schools Solar" in r.data

    with wa.get_db() as c:
        pid, tenant = c.execute(
            "SELECT id, tenant_id FROM enterprise_programme_registry "
            " WHERE code='GH-SCHOOLS-01'"
        ).fetchone()
        # Born at Concept, with the whole road already laid.
        assert c.execute(
            "SELECT status FROM enterprise_programme_registry WHERE id=?", (pid,)
        ).fetchone()[0] == "Concept"
        assert c.execute(
            "SELECT COUNT(*) FROM enterprise_programme_phase_states WHERE programme_id=?",
            (pid,)).fetchone()[0] == 16
        assert c.execute(
            "SELECT COUNT(*) FROM enterprise_stage_gates WHERE programme_id=?",
            (pid,)).fetchone()[0] == 14

    r = client.get(f"/enterprise/programmes/{pid}")
    assert r.status_code == 200
    assert b"Programme Concept Approval" in r.data      # gate board rendered
    assert b"Management Controls" in r.data             # the 15 controls are shown


def test_a_programme_cannot_be_registered_for_a_stranger_as_sponsor(ent):
    """The sponsor dropdown lists members only; posting a non-member is refused."""
    client, wa, ids = ent
    _flag(wa, True)
    _login(client, ids["alice"])
    r = client.post("/enterprise/programmes/new", data={
        "_csrf": "testtoken", "code": "BAD-SPONSOR", "name": "Bad",
        "design_strategy": "standard", "sponsor_user_id": str(ids["mallory"]),
    }, follow_redirects=True)
    assert r.status_code == 200
    with wa.get_db() as c:
        assert c.execute(
            "SELECT COUNT(*) FROM enterprise_programme_registry WHERE code='BAD-SPONSOR'"
        ).fetchone()[0] == 0


# --- the HTTP surface enforces the same rules as the services ----------------


def test_another_tenants_programme_is_a_404(ent):
    """Control C13 through HTTP. Mallory belongs to no organisation; Alice's programme
    must not merely be forbidden to her -- it must not appear to exist."""
    client, wa, ids = ent
    _flag(wa, True)
    with wa.get_db() as c:
        pid = c.execute(
            "SELECT id FROM enterprise_programme_registry WHERE code='GH-SCHOOLS-01'"
        ).fetchone()[0]

    _login(client, ids["mallory"])
    assert client.get(f"/enterprise/programmes/{pid}").status_code == 404


def test_a_tampered_session_tenant_does_not_grant_access(ent):
    """The session CARRIES a tenant id; it never GRANTS one.

    Mallory pastes Alice's organisation id into her session. resolve_active_tenant re-checks
    membership on every request, so she is silently put back in her own personal tenant --
    and Alice's programme still 404s.
    """
    client, wa, ids = ent
    _flag(wa, True)
    with wa.get_db() as c:
        pid, alice_org = c.execute(
            "SELECT id, tenant_id FROM enterprise_programme_registry "
            " WHERE code='GH-SCHOOLS-01'"
        ).fetchone()

    _login(client, ids["mallory"])
    with client.session_transaction() as s:
        s["enterprise_active_tenant"] = alice_org  # the forgery

    assert client.get(f"/enterprise/programmes/{pid}").status_code == 404
    client.get("/enterprise")
    with client.session_transaction() as s:
        assert s["enterprise_active_tenant"] == tenancy.personal_tenant_id(ids["mallory"])


def test_posting_the_approve_url_directly_is_not_a_way_round_the_gate(ent):
    """The hidden button is not the guard.

    Mallory is not a member at all, so she gets a 404 (the programme does not exist for
    her). The gate cannot be approved by URL.
    """
    client, wa, ids = ent
    _flag(wa, True)
    with wa.get_db() as c:
        pid = c.execute(
            "SELECT id FROM enterprise_programme_registry WHERE code='GH-SCHOOLS-01'"
        ).fetchone()[0]

    _login(client, ids["mallory"])
    r = client.post(f"/enterprise/programmes/{pid}/gates/G01/approve",
                    data={"_csrf": "testtoken"})
    assert r.status_code in (403, 404)

    with wa.get_db() as c:
        assert c.execute(
            "SELECT status FROM enterprise_stage_gates "
            " WHERE programme_id=? AND gate_code='G01'", (pid,)
        ).fetchone()[0] == "Pending"


def test_gate_1_needs_its_document_then_the_sponsor_signs_and_the_phase_moves(ent):
    """The whole slice, end to end, through HTTP: document -> gate -> transition.

    Alice is the named sponsor AND the enterprise owner, so she can do all three. Gate 1
    is refused until the concept note exists, and the phase will not move until Gate 1 is
    signed (control C01).
    """
    client, wa, ids = ent
    _flag(wa, True)
    _login(client, ids["alice"])
    with wa.get_db() as c:
        pid = c.execute(
            "SELECT id FROM enterprise_programme_registry WHERE code='GH-SCHOOLS-01'"
        ).fetchone()[0]

    # No concept note yet -> the gate refuses, and the phase cannot advance.
    client.post(f"/enterprise/programmes/{pid}/gates/G01/approve", data={"_csrf": "testtoken"})
    client.post(f"/enterprise/programmes/{pid}/transition",
                data={"_csrf": "testtoken", "target": "P02_INITIATION"})
    with wa.get_db() as c:
        assert c.execute(
            "SELECT current_phase_code FROM enterprise_programme_registry WHERE id=?", (pid,)
        ).fetchone()[0] == "P01_CONCEPT"

    # Register the concept note, sign Gate 1, then advance.
    client.post(f"/enterprise/programmes/{pid}/documents", data={
        "_csrf": "testtoken", "doc_type": "concept_note", "title": "Concept Note v1"})
    client.post(f"/enterprise/programmes/{pid}/gates/G01/approve", data={"_csrf": "testtoken"})
    with wa.get_db() as c:
        assert c.execute(
            "SELECT status FROM enterprise_stage_gates "
            " WHERE programme_id=? AND gate_code='G01'", (pid,)
        ).fetchone()[0] == "Approved"

    client.post(f"/enterprise/programmes/{pid}/transition",
                data={"_csrf": "testtoken", "target": "P02_INITIATION", "note": "charter next"})
    with wa.get_db() as c:
        phase, status = c.execute(
            "SELECT current_phase_code, status FROM enterprise_programme_registry WHERE id=?",
            (pid,)).fetchone()
        assert (phase, status) == ("P02_INITIATION", "Under Initiation")


def test_an_unknown_document_type_is_rejected(ent):
    """The doc type is a dropdown because the gate predicates look for a SPECIFIC type --
    free text would leave a gate quietly un-passable with no explanation."""
    client, wa, ids = ent
    _flag(wa, True)
    _login(client, ids["alice"])
    with wa.get_db() as c:
        pid = c.execute(
            "SELECT id FROM enterprise_programme_registry WHERE code='GH-SCHOOLS-01'"
        ).fetchone()[0]

    r = client.post(f"/enterprise/programmes/{pid}/documents", data={
        "_csrf": "testtoken", "doc_type": "concept note", "title": "typo"})
    assert r.status_code == 400


def test_the_dropdown_never_offers_a_move_the_server_would_refuse(ent):
    """The transition dropdown is rendered from allowed_transitions(), which is the same
    list transition_programme_phase() enforces. Offering an illegal move would be a lie."""
    client, wa, ids = ent
    _flag(wa, True)
    _login(client, ids["alice"])
    with wa.get_db() as c:
        pid = c.execute(
            "SELECT id FROM enterprise_programme_registry WHERE code='GH-SCHOOLS-01'"
        ).fetchone()[0]
        tenant = c.execute(
            "SELECT tenant_id FROM enterprise_programme_registry WHERE id=?", (pid,)
        ).fetchone()[0]
        state = workflows.get_programme_state(c, tenant, pid)

    r = client.get(f"/enterprise/programmes/{pid}")
    body = r.data.decode()
    for target in state["allowed_transitions"]:
        assert f'value="{target}"' in body
    # P11 is not reachable from here and must not be on offer.
    assert 'value="P11_CONSTRUCTION"' not in body
