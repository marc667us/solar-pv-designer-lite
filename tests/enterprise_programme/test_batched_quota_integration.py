"""The batching claim, measured end-to-end through build_markdown.

WHY THIS EXISTS SEPARATELY FROM THE UNIT TESTS. The unit tests proved `_ai_write_many` splits
a reply correctly. They could ALL pass while the feature made things worse -- and they did:
the first version of this change populated the batch cache and never read it, so a 10-section
document would have cost 3 batch calls PLUS 10 single-section calls. Codex caught it, not the
unit tests, because no unit test counted calls through the real loop.

So this file counts PROVIDER CALLS through `build_markdown` itself. That is the number the
whole change exists to reduce -- OpenRouter's free tier allows 50 a day, and one call per
section capped the platform at about five documents a day.
"""
import os
import sqlite3
import tempfile

import pytest

import web_app as _wa
from enterprise_programme_routes import register_enterprise_programme
from app.enterprise_programme import documents, flags
from app.security import audit as audit_mod

if "enterprise_home" not in _wa.app.view_functions:
    register_enterprise_programme(
        _wa.app, get_db=_wa.get_db, login_required=_wa.login_required,
        csrf_protect=_wa.csrf_protect, current_user=_wa.current_user,
    )

DESCRIPTION = (
    "A programme to install solar photovoltaic systems at rural health clinics across "
    "Ghana, providing reliable power for cold chain, lighting and diagnostics."
)


def _flag(wa, on):
    """The enterprise flag lives in `admin_settings`, not a feature_flags table."""
    with wa.get_db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS admin_settings "
                  "(key TEXT PRIMARY KEY, value TEXT NOT NULL, "
                  " updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        c.execute("INSERT OR REPLACE INTO admin_settings (key, value) VALUES (?,?)",
                  (flags.FLAG_ENABLED, "1" if on else "0"))
    flags.clear_cache()


@pytest.fixture(scope="module")
def ent():
    os.environ.pop("DATABASE_URL", None)
    os.environ.setdefault("SECRET_KEY", "test-secret-key-batch-quota")
    # init_db() seeds the admin and owner accounts and REFUSES to invent passwords for them.
    os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "test-admin-pw")
    os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "test-owner-pw")
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    wa = _wa
    original_db = wa.DB_PATH
    wa.DB_PATH = db_path
    wa.init_db()
    audit_mod.reset_schema_probe()
    wa.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, email, password_hash, email_verified,"
        " plan, is_admin, name) VALUES ('quota','quota@example.com','',1,'free',0,'Quota')")
    conn.commit()
    uid = conn.execute("SELECT id FROM users WHERE username='quota'").fetchone()[0]
    conn.close()

    with wa.app.test_client() as client:
        yield client, wa, uid

    wa.DB_PATH = original_db
    flags.clear_cache()


@pytest.fixture(scope="module")
def programme(ent):
    client, wa, uid = ent
    _flag(wa, True)
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["_csrf"] = "testtoken"
    client.post("/enterprise/onboarding", data={
        "_csrf": "testtoken", "legal_name": "Ministry of Health",
        "organisation_type": "ministry", "country": "Ghana",
    }, follow_redirects=True)
    client.post("/enterprise/programmes/new", data={
        "_csrf": "testtoken", "code": "GH-QUOTA", "name": "Rural Clinics Solar",
        "description": DESCRIPTION,
        "design_strategy": "standard", "sponsor_user_id": str(uid),
    }, follow_redirects=True)
    with wa.get_db() as c:
        return c.execute(
            "SELECT id FROM enterprise_programme_registry WHERE code='GH-QUOTA'"
        ).fetchone()[0]


CONCEPT_NOTE = "R4P1_D01"


class _CallCounter:
    """Counts calls at the api.ai.chat boundary -- the thing OpenRouter actually meters."""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, **kw):
        self.calls += 1
        content = messages[0]["content"]
        # Answer a BATCH prompt in the batch format; answer a single-section prompt plainly.
        marks = [ln.strip() for ln in content.splitlines()
                 if ln.strip().startswith("<<<SECTION:") and ln.strip().endswith(">>>")]
        if marks:
            parts = []
            for m in marks:
                heading = m[len("<<<SECTION:"):-len(">>>")]
                parts.append(f"{m}\nIndicative prose covering {heading} for this programme, "
                             f"assumed pending survey.")
            return "\n\n".join(parts), "openrouter"
        return ("Indicative prose for this section of the programme, assumed pending "
                "survey."), "openrouter"


def _generate(wa, uid, programme):
    with wa.get_db() as c:
        tenant = c.execute(
            "SELECT tenant_id FROM enterprise_programme_registry WHERE id=?", (programme,)
        ).fetchone()[0]
        return documents.generate_document(
            c, tenant, uid, programme, deliverable_code=CONCEPT_NOTE, use_ai=True)


def test_a_document_costs_far_fewer_calls_than_it_has_sections(ent, programme, monkeypatch):
    """THE POINT OF THE CHANGE, measured.

    Batching at 4 sections a call must cost roughly a quarter of the calls, not more. The
    exact number depends on the concept note's section count, so this asserts the RELATIONSHIP
    -- calls must be well under the section count -- rather than a magic number that would
    have to be edited every time a section is added to the template.
    """
    client, wa, uid = ent
    import api_manager
    counter = _CallCounter()
    monkeypatch.setattr(api_manager.api.ai, "chat", counter.chat)

    md = _generate(wa, uid, programme)
    assert md, "the document must actually be produced"

    # How many sections the concept note declares.
    from app.enterprise_programme import document_templates
    n_sections = len(document_templates.template_for(CONCEPT_NOTE))

    assert n_sections >= 4, "this test is meaningless on a document with < 4 sections"
    # Batching at 4/call, with a little slack for sections written individually.
    ceiling = -(-n_sections // documents.AI_BATCH_SECTIONS) + 2
    assert counter.calls <= ceiling, (
        f"{n_sections} sections cost {counter.calls} provider calls; batching at "
        f"{documents.AI_BATCH_SECTIONS}/call should have cost at most {ceiling}. "
        f"If this exceeds the section count the prefetch is ADDING calls, not saving them."
    )


def test_the_prefetched_sections_are_not_rewritten_individually(ent, programme, monkeypatch):
    """The exact bug Codex caught: cache populated, never read.

    If the loop ignores the cache, total calls climb ABOVE the section count -- the batch
    calls plus a single call for every section. Asserting strictly below the section count is
    what makes that regression impossible to reintroduce silently.
    """
    client, wa, uid = ent
    import api_manager
    counter = _CallCounter()
    monkeypatch.setattr(api_manager.api.ai, "chat", counter.chat)

    _generate(wa, uid, programme)

    from app.enterprise_programme import document_templates
    n_sections = len(document_templates.template_for(CONCEPT_NOTE))
    assert counter.calls < n_sections, (
        f"{counter.calls} calls for {n_sections} sections -- the prefetch result is being "
        f"discarded and every section rewritten individually."
    )
