"""The Enterprise tutorials point at controls that actually exist.

WHY THIS FILE EXISTS
--------------------
The tutorial engine degrades QUIETLY. A step whose `targetSelector` matches nothing does not
error -- it shows its fallbackMessage and walks on. A `navigate` step whose `hrefFromSelector`
finds no anchor does the same. So a scenario can look complete, pass every schema test, ship,
and teach the user nothing at all.

`scripts/sync_tutorials.py --check` is meant to catch that (its DEAD-selector pass), but it
renders through `web_app.app.test_client()` with NO SESSION, and every /enterprise page is
login-gated -- so they render as 302, land in its "could not be rendered" bucket, and their
selectors are never linted. Codex caught this. The scenarios were therefore unverified.

This closes it: the pages are rendered as a REAL LOGGED-IN OWNER of a REAL organisation with a
REAL programme, and the scenarios' selectors and navigation anchors are checked against the
actual DOM.

The navigation chains are the sharp end -- a nav() hop is what makes a multi-screen tour a
tour, and `covers` (which silences the coverage gate) is a CLAIM that the flow really walks
there. A covers entry with no working anchor is a lie the gate cannot see.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import web_app as _wa                                                    # noqa: E402
from enterprise_programme_routes import register_enterprise_programme    # noqa: E402
from app.security import audit as audit_mod                              # noqa: E402
from app.enterprise_programme import (                                     # noqa: E402
    beneficiaries, documents, flags, rollout, tenancy, templates as tmpl, workflows,
)

if "enterprise_home" not in _wa.app.view_functions:
    register_enterprise_programme(
        _wa.app, get_db=_wa.get_db, login_required=_wa.login_required,
        csrf_protect=_wa.csrf_protect, current_user=_wa.current_user,
    )

SCEN = os.path.join(ROOT, "static", "tutorial", "scenarios")


def _scenario(page_id: str) -> dict:
    with open(os.path.join(SCEN, f"{page_id}.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    """A logged-in owner, a real organisation, and a real programme with a site."""
    db_path = str(tmp_path_factory.mktemp("enttut") / "ent.db")
    os.environ.pop("DATABASE_URL", None)
    # The audit module CACHES a column probe of audit_logs. A sibling test module leaves
    # one cached against ITS schema, and the stale probe makes every audited write fail
    # here with "C12: audit write failed" -- so this file passes alone and dies in a full
    # run. Every other enterprise test module resets it for the same reason.
    audit_mod.reset_schema_probe()
    os.environ.setdefault("SECRET_KEY", "test-secret-key-enterprise-tut")

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
    conn.execute(
        "INSERT OR IGNORE INTO users (username, email, password_hash, email_verified,"
        " plan, is_admin, name) VALUES ('owen','owen@example.com','',1,'free',0,'Owen')"
    )
    conn.commit()
    uid = conn.execute("SELECT id FROM users WHERE username='owen'").fetchone()[0]
    conn.close()

    with wa.get_db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS admin_settings "
                  "(key TEXT PRIMARY KEY, value TEXT NOT NULL, "
                  " updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        c.execute("INSERT OR REPLACE INTO admin_settings (key, value) VALUES (?,?)",
                  (flags.FLAG_ENABLED, "1"))
    flags.clear_cache()

    with wa.get_db() as c:
        # The routes build the SQLite mirror on first request (_ensure_schema_once); we call
        # the services directly to seed, so we have to build it ourselves first.
        tenancy.ensure_schema(c)
        workflows.ensure_schema(c)
        beneficiaries.ensure_schema(c)
        documents.ensure_schema(c)
        rollout.ensure_schema(c)

    with wa.get_db() as c:
        tenancy.get_or_create_personal_tenant(c, uid, "owen")
        # create_organisation grants ONBOARDING_OWNER_ROLES, so this owner can really
        # reach the screens the tutorials describe -- exactly like a live owner.
        tid = tenancy.create_organisation(c, uid, "Ministry of Energy", "ministry")
        pid = workflows.create_programme(
            c, tid, uid, code="TUT-1", name="Tutorial Programme",
            design_strategy="standard", sponsor_user_id=uid,
        )
        tmpl.create_template(c, tid, uid, code="TUT-TPL", name="School Package",
                             beneficiary_type="school")
        # A REGISTERED SITE. Without one the priority list is empty, and the per-site
        # "qualify" link -- which the tutorial navigates to -- is not on the page at all.
        # A tutorial verified against an empty programme proves nothing about the real one.
        beneficiaries.create_beneficiary(
            c, tid, uid, pid, code="TUT-SITE-1", name="Kpando Senior High",
            beneficiary_type="school", fields={"community": "Kpando"},
        )
        # A GENERATED DOCUMENT, for the same reason as the site above. The register table --
        # and the "View" link the tutorial navigates to in order to reach the report page --
        # only exists once the programme HAS a document. Verified against a programme that
        # has never generated one, the documents tutorial proves nothing about the real page.
        documents.generate_document(
            c, tid, uid, pid, activity_codes=["P01_A01"],
            deliverable_code="P01_D01", use_ai=False,
        )

    with wa.app.test_client() as client:
        with client.session_transaction() as s:
            s["user_id"] = uid
            s["_csrf"] = "testtoken"
        yield client, pid

    wa.DB_PATH = original_db


# pageId -> the URL that renders it
def _urls(pid: int) -> dict[str, str]:
    return {
        "enterprise_home":            "/enterprise",
        "enterprise_onboarding":      "/enterprise/onboarding",
        "enterprise_programme_new":   "/enterprise/programmes/new",
        "enterprise_templates":       "/enterprise/templates",
        "enterprise_members":         "/enterprise/members",
        "enterprise_programme_detail": f"/enterprise/programmes/{pid}",
        "enterprise_priority_list":   f"/enterprise/programmes/{pid}/priority",
        "enterprise_beneficiaries":   f"/enterprise/programmes/{pid}/beneficiaries",
        "enterprise_design":          f"/enterprise/programmes/{pid}/design",
        "enterprise_lifecycle_documents": f"/enterprise/programmes/{pid}/lifecycle-documents",
    }


PAGES = list(_urls(1).keys())


@pytest.mark.parametrize("page_id", PAGES)
def test_the_page_the_tutorial_describes_actually_renders(live, page_id):
    client, pid = live
    r = client.get(_urls(pid)[page_id])
    assert r.status_code == 200, (
        f"{page_id}: the tutorial describes a page that returns {r.status_code}"
    )


# --- navigation: the sharp end ------------------------------------------------

# Every nav() hop in the enterprise scenarios, as (from_page, the href it must find).
# A static `href` must be a real anchor on the page; an `hrefFromSelector` must match one.
NAV_CHAINS = [
    ("enterprise_home",             "/enterprise/templates"),
    ("enterprise_home",             "/enterprise/members"),
    ("enterprise_templates",        "/enterprise/templates/new"),
    ("enterprise_programme_detail", "/design"),
    ("enterprise_priority_list",    "/qualify"),
]


@pytest.mark.parametrize("page_id, href_fragment", NAV_CHAINS)
def test_every_nav_hop_finds_a_real_anchor(live, page_id, href_fragment):
    """A nav step whose anchor is absent shows a fallback and walks on -- silently.

    So a multi-screen tour can 'pass' every schema test while never leaving screen one.
    """
    client, pid = live
    html = client.get(_urls(pid)[page_id]).get_data(as_text=True)
    anchors = re.findall(r'<a\b[^>]*href="([^"]+)"', html, flags=re.I)
    assert any(href_fragment in a for a in anchors), (
        f"{page_id}: the tutorial navigates to an anchor containing {href_fragment!r}, "
        f"but no such link is on the page. The tour would stop here and say nothing. "
        f"Anchors present: {sorted(set(anchors))[:15]}"
    )


def test_covers_is_not_a_lie(live):
    """`covers` silences the coverage gate. It must correspond to a real nav() step."""
    for page_id in PAGES:
        doc = _scenario(page_id)
        covered = doc.get("covers") or []
        if not covered:
            continue
        navs = [s for s in doc["steps"] if s.get("action") == "navigate"]
        assert len(navs) >= len(covered), (
            f"{page_id}: covers {covered} but has only {len(navs)} navigate step(s). "
            f"covers is a claim the flow WALKS there -- not a way to silence the gate."
        )


# --- selectors ----------------------------------------------------------------

def _selector_matches(html: str, selector: str) -> bool:
    """Does any comma-separated alternative in `selector` plausibly appear in the HTML?

    Deliberately a substring/attribute check, not a real CSS engine (no lxml/bs4 dependency
    in this repo). It is enough to catch the failure that matters: a selector naming a class,
    id, tag or attribute that appears NOWHERE on the page.
    """
    for alt in [a.strip() for a in selector.split(",") if a.strip()]:
        # attribute selector, e.g. a[href*="/design"] or input[name="code"]
        m = re.match(r'^(\w+)?\[(\w+)[\^\$\*]?="?([^"\]]+)"?\]$', alt)
        if m:
            _tag, attr, val = m.groups()
            if re.search(rf'{attr}="[^"]*{re.escape(val)}', html, flags=re.I):
                return True
            continue
        # A compound `tag.class` / `tag#id` (e.g. `a.js-doc-view`) is a perfectly ordinary
        # selector, and without this the tag prefix fell through to the bare-tag branch
        # below -- which then hunted for the literal string "<a.js-doc-view" and reported a
        # live control as dead. The class/id is the discriminating half, so match on that.
        m = re.match(r'^\w+([.#][\w-]+)$', alt)
        if m:
            alt = m.group(1)
        if alt.startswith("."):
            if re.search(rf'class="[^"]*\b{re.escape(alt[1:])}\b', html):
                return True
            continue
        if alt.startswith("#"):
            if f'id="{alt[1:]}"' in html:
                return True
            continue
        if re.search(rf"<{re.escape(alt)}\b", html, flags=re.I):
            return True
    return False


@pytest.mark.parametrize("page_id", PAGES)
def test_no_step_targets_a_control_that_is_not_there(live, page_id):
    """A dead selector is a step that silently teaches nothing."""
    client, pid = live
    html = client.get(_urls(pid)[page_id]).get_data(as_text=True)
    doc = _scenario(page_id)

    dead = []
    for s in doc["steps"]:
        sel = s.get("targetSelector") or ""
        if not sel or s.get("dynamic"):
            continue          # injected by JS; not in the server-rendered HTML
        if s.get("action") == "navigate" and s.get("href"):
            continue          # a static href is verified by the nav test above
        if not _selector_matches(html, sel):
            dead.append((s["stepNumber"], s["title"], sel))

    assert not dead, (
        f"{page_id}: step(s) target controls that do not exist on the page, so they would "
        f"silently show a fallback instead of teaching anything: {dead}"
    )
