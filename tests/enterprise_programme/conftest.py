"""Governance is ADVISORY in the app, and STRICT in most of these tests. Both are real.

OWNER, 2026-07-14: "reduce and loosen governance"; "the owner must be able to walk through
without blocks"; "user must be able to work at any phase"; "we don't need to do proving to
any entity".

So the SHIPPED DEFAULT is advisory: a stage gate whose evidence does not exist can still be
approved, and a programme can move to any phase. Nothing refuses the operator.

STRICT MODE DID NOT GO AWAY. It is one admin_settings flag (`enterprise_governance_advisory`
= '0'), and it is the mode a ministry that DOES have to answer to a funder would run in. The
~230 tests in this package were written against it and they still describe it exactly, so
they keep testing it -- that is what this fixture is for. Deleting them would have thrown away
the specification of a mode the app still supports and can be switched back to in one row.

Tests of the NEW default mark themselves `@pytest.mark.advisory` and opt out.

The two modes differ in exactly one way, and it is worth saying plainly: in advisory mode the
app does not BLOCK. It still RECORDS. An approval made without its evidence is written to the
approvals table as "APPROVED WITHOUT EVIDENCE: ...", and a phase moved past an unapproved gate
says so on the transition. Loosening governance means the app stops standing in the operator's
way; it never means the app starts saying something untrue.
"""

from __future__ import annotations

import pytest

from app.enterprise_programme import flags


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "advisory: this test exercises ADVISORY governance (the shipped default), "
        "rather than the strict mode the rest of this package describes",
    )


@pytest.fixture(autouse=True)
def _strict_unless_marked_advisory(monkeypatch, request):
    """Default these tests to STRICT governance, which is what they were written against."""
    if "advisory" in request.keywords:
        return
    monkeypatch.setattr(flags, "advisory_governance", lambda c: False)
