"""
Regression guard: every shared-secret comparison must compare BYTES.

THE BUG THIS PREVENTS
    `hmac.compare_digest` raises TypeError when either operand is a str
    containing non-ASCII. Every guarded endpoint here takes one half of the
    comparison from an HTTP header, and WSGI decodes headers as latin-1 --
    so any byte 0x80-0xFF arrives as a non-ASCII character. Comparing str
    therefore converts a garbage header into an UNHANDLED 500 instead of an
    honest 401/400.

    It has already happened once in production: a BOM-corrupted secret 500'd
    the CDC drain (2026-07-19). Three more instances were found on
    2026-07-20 -- and unlike the CDC case, these are triggerable by ANY
    caller, because the attacker controls the header rather than needing the
    stored secret to be corrupt.

WHAT THIS FILE CHECKS
    1. The language behaviour itself, so the reason is documented and cannot
       be "fixed" away by someone who does not believe it.
    2. That each known call site encodes BOTH operands.

    Check 2 is a source assertion, not a request-level test. That is a
    deliberate limitation: web_app.py cannot be imported without production
    env (SystemExit: Set SOLARPRO_ADMIN_PASSWORD) and the guarded handlers
    are module-level splices that need a live Flask app plus real secrets.
    The request-level proof is done against the deployed app instead -- send
    an Authorization header of b'\\xff\\xfe' and assert 401, not 500.
"""

from __future__ import annotations

import hmac
import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: (file, the call that MUST appear encoded). One entry per known
#: shared-secret comparison that reads from an attacker-controlled header.
GUARDED_SITES = [
    ("web_app.py", "_hmac.compare_digest"),            # paystack_webhook
    ("web_app.py", "_soc_hmac.compare_digest"),        # _soc_ingest_authorized
    ("new_soc_slice1.py", "_soc_hmac.compare_digest"),
    ("new_cdc_drain_routes.py", "hmac.compare_digest"),
    ("enterprise_programme_routes.py", "hmac.compare_digest"),
]


def _read(name: str) -> str:
    """Read a source file. latin-1 because web_app.py is CRLF + mojibake."""
    with open(os.path.join(REPO_ROOT, name), "rb") as fh:
        return fh.read().decode("latin-1")


def _strip_prose(src: str) -> str:
    """Blank out docstrings and # comments, preserving line numbering.

    Necessary because these modules DISCUSS compare_digest in their
    docstrings -- new_cdc_drain_routes.py:180 explains the very bug this
    file guards. Scanning raw text matched that prose and reported the
    correctly-fixed call site as broken. Replacing with newlines rather
    than deleting keeps reported line numbers honest.
    """
    def _blank(m: re.Match) -> str:
        return "\n" * m.group(0).count("\n")

    # Triple-quoted blocks first (they can contain # and quotes).
    src = re.sub(r'"""[\s\S]*?"""', _blank, src)
    src = re.sub(r"'''[\s\S]*?'''", _blank, src)
    # Then line comments.
    src = re.sub(r"#[^\n]*", "", src)
    return src


def test_compare_digest_raises_on_non_ascii_str():
    """Document the language behaviour that makes this a real bug.

    If this ever stops raising, the guards below become unnecessary -- but
    until then, a str comparison is a latent 500.
    """
    attacker_controlled = "ÿþ"  # what b'\xff\xfe' becomes via latin-1
    with pytest.raises(TypeError):
        hmac.compare_digest(attacker_controlled, "real-secret")

    # And the fix genuinely works: a wrong token compares False, not raises.
    assert hmac.compare_digest(
        attacker_controlled.encode("utf-8"), b"real-secret"
    ) is False


@pytest.mark.parametrize("filename,call", GUARDED_SITES)
def test_secret_comparisons_encode_both_operands(filename, call):
    """Every guarded compare_digest call must encode BOTH sides.

    Matches the call and its argument list (which may wrap across lines),
    then asserts two .encode( appear inside it.
    """
    src = _strip_prose(_read(filename))
    pattern = re.escape(call) + r"\s*\((?P<args>[^)]*\)?[^)]*)\)"

    found = [m for m in re.finditer(pattern, src)]
    assert found, f"{filename}: no {call}( call found -- did it move or get renamed?"

    for m in found:
        args = m.group("args")
        line_no = src[: m.start()].count("\n") + 1
        assert args.count(".encode(") >= 2, (
            f"{filename}:{line_no} -- {call} compares un-encoded operands:\n"
            f"    {args.strip()}\n"
            "Both sides must be bytes. A str holding non-ASCII raises "
            "TypeError, turning a bad header into a 500 instead of a 401."
        )


def test_keycloak_events_compare_is_exception_guarded():
    """app/security/keycloak_events.py compares str, which is SAFE here only
    because it is wrapped in try/except -> return False.

    That file is part of the Keycloak auth flow and is OFF-LIMITS by owner
    instruction, so we assert the property that makes it safe rather than
    changing it. If the try/except is ever removed, this fails and the site
    must then be converted to a bytes comparison like the others.
    """
    path = os.path.join(REPO_ROOT, "app", "security", "keycloak_events.py")
    if not os.path.exists(path):
        pytest.skip("keycloak_events.py not present")
    src = _strip_prose(_read(os.path.join("app", "security", "keycloak_events.py")))

    m = re.search(
        r"try:\s*\n\s*return hmac\.compare_digest\([^)]*\)\s*\n\s*except",
        src,
    )
    assert m, (
        "keycloak_events.py: hmac.compare_digest is no longer wrapped in "
        "try/except. It compares str, so an unguarded call would 500 on a "
        "non-ASCII signature header. Either restore the guard or encode "
        "both operands."
    )
