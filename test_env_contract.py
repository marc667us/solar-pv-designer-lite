"""Guard rail against environment-variable drift.

OWNER, 2026-07-19: "env kept drifting no guard rails."

This is the guard rail. It scans the source for every os.environ read and fails when a name
is forbidden or undeclared. See env_contract.py for why -- four production faults in one day
traced to two places naming the same thing differently with nothing comparing them.

THE TEST THAT WOULD HAVE CAUGHT TODAY'S BUG is
`test_no_forbidden_env_names_are_read`: /api/health/ai read GITHUB_MODELS_TOKEN, a name
nothing sets, and reported the AI provider as unconfigured forever as a result.

Run: python -m pytest test_env_contract.py -q
"""
import re
import pathlib

import pytest

import env_contract

# The read pattern used everywhere in this codebase: os.environ.get("X") / os.environ["X"].
_ENV_RE = re.compile(r'os\.environ(?:\.get\(\s*|\[\s*)["\']([A-Z0-9_]+)["\']')

# Scanned: application code. NOT scanned, and each exclusion is deliberate:
#   * test_*        -- tests legitimately set phantom names to prove they are rejected.
#   * patch_*       -- byte-splice scripts quote the OLD source they are replacing, so the
#                      defective string appears in them by necessity.
#   * scripts/oneshot/ -- historical one-shot scripts, kept as a record of what was run.
_SKIP_PREFIXES = ("test_", "patch_", "_patch_")


def _source_files():
    roots = list(pathlib.Path(".").glob("*.py")) + list(pathlib.Path("app").rglob("*.py"))
    for p in roots:
        if any(p.name.startswith(pref) for pref in _SKIP_PREFIXES):
            continue
        if "oneshot" in p.parts:
            continue
        yield p


def _names_by_file():
    found = {}
    for p in _source_files():
        try:
            s = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in _ENV_RE.finditer(s):
            found.setdefault(m.group(1), set()).add(str(p))
    return found


def test_no_forbidden_env_names_are_read():
    """THE REGRESSION GUARD. A known-wrong name must never reappear in shipped code."""
    found = _names_by_file()
    bad = {n: sorted(f) for n, f in found.items() if n in env_contract.FORBIDDEN}
    assert not bad, (
        "Forbidden environment variable(s) read in application code:\n"
        + "\n".join(f"  {n} in {files}\n    -> {env_contract.FORBIDDEN[n]}"
                    for n, files in bad.items()))


def test_every_env_name_is_declared():
    """The ratchet: a NEW env var must be declared, which forces the question of what sets it.

    This is what makes drift visible at the moment it is introduced rather than months later
    on a production dashboard that is quietly reporting the wrong answer.
    """
    found = _names_by_file()
    undeclared = {n: sorted(f) for n, f in found.items()
                  if n not in env_contract.ALLOWED and n not in env_contract.FORBIDDEN}
    assert not undeclared, (
        "Undeclared environment variable(s). Add each to ALLOWED in env_contract.py with a "
        "note on what sets it (Render env / GitHub Secret / local .env / Vault broker):\n"
        + "\n".join(f"  {n} in {files}" for n, files in undeclared.items()))


def test_contract_check_helper_agrees_with_the_tests():
    """env_contract.check() is the shared definition of a violation.

    A second copy of this logic living only in the tests would be exactly the drift this
    file exists to prevent, so the helper is exercised on the real scan.
    """
    assert env_contract.check(_names_by_file().keys()) == []


def test_the_contract_itself_is_not_empty():
    """A contract that silently emptied would pass every other test in this file."""
    assert len(env_contract.ALLOWED) > 50, "the contract looks truncated"
    assert "GITHUB_TOKEN" in env_contract.ALLOWED
    assert "GITHUB_MODELS_TOKEN" not in env_contract.ALLOWED


def test_forbidden_entries_explain_themselves():
    """A guard rail that fails without saying what to do instead just gets deleted."""
    for name, reason in env_contract.FORBIDDEN.items():
        assert len(reason) > 40, f"{name} needs a real explanation"


@pytest.mark.parametrize("name", ["GITHUB_TOKEN", "OPENROUTER_API_KEY", "DATABASE_URL"])
def test_load_bearing_names_stay_declared(name):
    """Names the app cannot run without. Their removal from the contract is a red flag."""
    assert name in env_contract.ALLOWED
