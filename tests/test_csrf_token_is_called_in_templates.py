"""Every `_csrf` field must render `csrf_token()` -- CALLED. A repr is not a token.

THE BUG THIS ENDS (owner, 2026-07-13: "program design and rollout page, the build the
design button don't work")
------------------------------------------------------------------------------------
`web_app.py:336` registers the token generator as a Jinja global:

    app.jinja_env.globals["csrf_token"] = generate_csrf

It is a FUNCTION. So `{{ csrf_token() }}` renders a token, and `{{ csrf_token }}` -- one
missing pair of parentheses -- renders the function's repr:

    <function generate_csrf at 0x000001C3...>

That string is then posted as `_csrf`, `csrf_protect()` compares it against
`session["_csrf"]`, and refuses. The form 403s. Every time. For everyone.

templates/enterprise_programme/design.html had it in FIVE places -- which is to say every
POST form on the Programme Design and Rollout page: Build the design, Approve, Supersede,
and Save variance. None of them had ever worked from a browser. The enterprise test suite
did not catch it because its requests post a real token directly rather than scraping the
rendered form, so the templates were never exercised as templates.

The defect is invisible on inspection -- the diff between working and broken is `()` -- and
it silently disables an entire page, so it gets a guard rather than a fix and a hope.
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

# A hidden CSRF input whose value is `{{ csrf_token }}` -- the global, NOT called.
# Matches the field by its NAME (`_csrf`, what csrf_protect actually reads) so a form is
# caught regardless of attribute order or quoting style.
_UNCALLED = re.compile(
    r'name=["\']_csrf["\'][^>]*value=["\']\{\{\s*csrf_token\s*\}\}["\']'
    r'|value=["\']\{\{\s*csrf_token\s*\}\}["\'][^>]*name=["\']_csrf["\']'
)


def test_no_template_posts_an_uncalled_csrf_token():
    offenders: list[str] = []

    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if _UNCALLED.search(line):
                offenders.append(f"{path.relative_to(TEMPLATES.parent)}:{i}")

    assert not offenders, (
        "these forms post the repr of the csrf_token FUNCTION instead of a token, so every "
        "POST from them is refused with a 403 and the button appears dead:\n  "
        + "\n  ".join(offenders)
        + "\n\nWrite `{{ csrf_token() }}` -- with the parentheses."
    )


def test_the_guard_actually_matches_the_broken_form():
    """A guard that matches nothing passes forever. This is the exact line that was live."""
    broken = '<input type="hidden" name="_csrf" value="{{ csrf_token }}">'
    assert _UNCALLED.search(broken), "the guard would not have caught the real bug"

    fixed = '<input type="hidden" name="_csrf" value="{{ csrf_token() }}">'
    assert not _UNCALLED.search(fixed), "the guard flags the CORRECT form"
