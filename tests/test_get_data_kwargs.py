"""
Guard: request.get_data() must only be called with kwargs it actually has.

THE BUG THIS PREVENTS
    Werkzeug's signature is:
        Request.get_data(cache=True, as_text=False, parse_form_data=False)
    There is NO `raw` parameter. `request.get_data(raw=True)` raises
    TypeError at runtime -- and because it is the FIRST thing a webhook does,
    it kills the handler before any signature check runs.

    This was not hypothetical. Both payment webhooks shipped with
    `get_data(raw=True)` in 86eadc2 and neither has EVER processed an event:
      - /paystack/webhook returned 500 on every push (TypeError escaped)
      - /stripe/webhook   returned 400 on every push (TypeError caught by
                          its own try/except, so it failed silently)

    Static analysis would not flag it -- the kwarg name is only wrong at
    call time. It was found by probing the DEPLOYED app.

WHY A TEST AND NOT JUST A FIX
    The fix is one word. The value is stopping it coming back: this typo
    survived from the repo's first security commit to 2026-07-20 precisely
    because nothing asserted it.
"""

from __future__ import annotations

import inspect
import os
import re

import pytest
from werkzeug.wrappers import Request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Known-broken call sites, accepted for now and tracked. Each entry is
#: "<file>:<the offending kwarg>". These are the ONLY tolerated failures --
#: fixing one means deleting its line here, which tightens the test.
#:
#: stripe_webhook still passes raw=True. It cannot simply be switched on:
#: unlike the Paystack handler it has NO `SELECT ... WHERE reference=?`
#: dedupe, so Stripe's automatic retries could double-record a payment.
#: It needs that guard added at the same time -- tracked as a follow-up.
KNOWN_BROKEN = {
    "web_app.py:stripe_webhook",
}


def _valid_kwargs() -> set[str]:
    """The kwargs werkzeug's get_data actually accepts, read from werkzeug
    itself rather than hardcoded -- so a werkzeug upgrade cannot make this
    test assert a stale contract."""
    params = inspect.signature(Request.get_data).parameters
    return {n for n in params if n != "self"}


def _iter_py_files():
    """Live repo-root modules (skip tests, archived copies, patch scripts,
    and .bak snapshots)."""
    skip = ("_legacy_", "_pre_v2swap_", "patch_", ".bak")
    for name in sorted(os.listdir(REPO_ROOT)):
        if not name.endswith(".py") or name.startswith("test_"):
            continue
        if any(s in name for s in skip):
            continue
        yield name


def test_werkzeug_has_no_raw_kwarg():
    """Pin the premise. If werkzeug ever gains a `raw` kwarg, the guard
    below becomes pointless and should be revisited rather than trusted."""
    assert "raw" not in _valid_kwargs(), (
        "werkzeug's get_data now accepts `raw`; this guard needs rewriting."
    )


def test_get_data_calls_use_only_real_kwargs():
    """Every get_data(...) call must use only werkzeug's real kwargs."""
    valid = _valid_kwargs()
    offenders: list[str] = []

    for name in _iter_py_files():
        with open(os.path.join(REPO_ROOT, name), "rb") as fh:
            src = fh.read().decode("latin-1")

        for m in re.finditer(r"\.get_data\(([^)]*)\)", src):
            args = m.group(1)
            line_no = src[: m.start()].count("\n") + 1
            for kw in re.findall(r"(\w+)\s*=", args):
                if kw in valid:
                    continue
                # Identify the enclosing def so the exemption key is stable
                # across edits that shift line numbers.
                before = src[: m.start()]
                fn = "?"
                fm = list(re.finditer(r"^\s*def\s+(\w+)", before, re.M))
                if fm:
                    fn = fm[-1].group(1)
                key = f"{name}:{fn}"
                if key in KNOWN_BROKEN:
                    continue
                offenders.append(
                    f"{name}:{line_no} in {fn}() -- get_data({kw}=...) "
                    f"is not a real kwarg (valid: {', '.join(sorted(valid))})"
                )

    assert not offenders, (
        "get_data() called with a kwarg it does not accept. This raises "
        "TypeError at RUNTIME and will kill the handler:\n\n"
        + "\n".join(f"    {o}" for o in offenders)
    )


@pytest.mark.parametrize("key", sorted(KNOWN_BROKEN))
def test_known_broken_entries_are_still_real(key):
    """Stop the exemption list going stale.

    If a known-broken site gets fixed, its entry here must be deleted --
    otherwise it silently pre-authorises a future regression in the same
    function.
    """
    filename, fn = key.split(":", 1)
    with open(os.path.join(REPO_ROOT, filename), "rb") as fh:
        src = fh.read().decode("latin-1")

    valid = _valid_kwargs()
    m = re.search(rf"^\s*def\s+{re.escape(fn)}\b", src, re.M)
    assert m, f"{key}: function no longer exists -- remove it from KNOWN_BROKEN"

    body = src[m.start(): m.start() + 4000]
    bad = [
        kw
        for call in re.findall(r"\.get_data\(([^)]*)\)", body)
        for kw in re.findall(r"(\w+)\s*=", call)
        if kw not in valid
    ]
    assert bad, (
        f"{key} no longer has an invalid get_data kwarg -- it appears FIXED. "
        "Delete it from KNOWN_BROKEN so the guard tightens."
    )
