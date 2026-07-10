"""Tests for the OIDC post-login open-redirect guard (_safe_relative_next).

Security audit 2026-07-10: the callback used the session `next` target verbatim,
allowing "?next=https://attacker.example". The guard now admits only same-origin
relative paths and rejects protocol-relative, backslash, and control-char tricks
(Codex flagged the "/\t//evil" browser-strip bypass).
Run: python -m pytest test_oidc_safe_next.py -q
"""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "oidc_routes", Path(__file__).resolve().parent / "app" / "auth" / "oidc_routes.py")
oidc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oidc)
safe = oidc._safe_relative_next


@pytest.mark.parametrize("good", [
    "/dashboard",
    "/",
    "/project/5",
    "/dashboard?tab=1&x=2",
    "/large-scale-solar/42/report/pv.pdf",
])
def test_relative_paths_allowed(good):
    assert safe(good) == good


@pytest.mark.parametrize("bad", [
    "https://attacker.example",          # absolute
    "http://attacker.example/",
    "//attacker.example",                # protocol-relative
    "/\\attacker.example",               # backslash trick
    "/\t//evil.example",                 # tab -> browser strips -> //evil
    "/\n//evil.example",                 # newline strip
    "/ //evil.example",                  # leading space after slash
    "javascript:alert(1)",               # no leading slash
    "",                                  # empty
    "dashboard",                         # relative but no leading slash
])
def test_malicious_targets_fall_back(bad):
    assert safe(bad) == "/dashboard"


def test_non_string_falls_back():
    assert safe(None) == "/dashboard"
    assert safe(123) == "/dashboard"


def test_custom_default():
    assert safe("//evil", default="/home") == "/home"
