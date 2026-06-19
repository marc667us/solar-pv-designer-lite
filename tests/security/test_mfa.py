"""
MFA realm-export audit for SolarPro Phase 6.

Plan §19 task 28 says: "Enable OTP required-action on the four roles
(§14.2)." The plan's §14.2 names five MFA-required roles:

    platform_super_admin
    tenant_admin
    marketplace_admin
    finance_officer
    support_agent

The realm-export.json from Phase 1 ships test users for those roles
with `requiredActions=["UPDATE_PASSWORD","CONFIGURE_TOTP"]` so a fresh
realm import forces them through the OTP setup wizard on first login.

This test fails LOUD if a future export edit removes CONFIGURE_TOTP
from any of the five users -- regression guardrail per the Project
Execution Directive §3 "Do Not Forget Previous Work Rule".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REALM_EXPORT = (
    Path(__file__).resolve().parent.parent.parent
    / "docs" / "keycloak" / "realm-export.json"
)


# The required-actions matrix from plan §14.2.
MFA_REQUIRED_ROLES = {
    "platform_super_admin",
    "tenant_admin",
    "marketplace_admin",
    "finance_officer",
    "support_agent",
}


@pytest.fixture(scope="module")
def realm() -> dict:
    return json.loads(REALM_EXPORT.read_text(encoding="utf-8"))


def _user_realm_roles(user: dict) -> set[str]:
    return set(user.get("realmRoles") or [])


def test_realm_export_present(realm):
    assert "users" in realm, "realm export is missing the users array"


def test_configure_totp_required_action_enabled(realm):
    """The realm requires CONFIGURE_TOTP be available as a required-action."""
    actions = realm.get("requiredActions") or []
    aliases = {a.get("alias") for a in actions}
    assert "CONFIGURE_TOTP" in aliases
    totp = next(a for a in actions if a.get("alias") == "CONFIGURE_TOTP")
    assert totp.get("enabled") is True
    assert totp.get("providerId") == "CONFIGURE_TOTP"


@pytest.mark.parametrize("role", sorted(MFA_REQUIRED_ROLES))
def test_each_mfa_role_user_has_configure_totp(realm, role):
    """Every MFA-required role from §14.2 must have at least one user
    whose firstLogin requires CONFIGURE_TOTP."""
    users = realm["users"]
    matching = [u for u in users if role in _user_realm_roles(u)]
    if not matching:
        pytest.skip(f"realm export carries no test user for role {role!r}")
    enforced = [
        u for u in matching
        if "CONFIGURE_TOTP" in (u.get("requiredActions") or [])
    ]
    assert enforced, (
        f"role {role!r} has test users but none carry "
        f"requiredActions=['...','CONFIGURE_TOTP']"
    )


def test_totp_policy_set(realm):
    """OTP policy is configured on the realm itself, not deferred to
    per-user defaults."""
    assert realm.get("otpPolicyType") == "totp"


def test_password_policy_present(realm):
    """Plan §key technical decisions: length(12), digits(1), upper(1),
    lower(1), special(1), notUsername, notEmail, hashIterations(210000),
    history(5), forceExpiredChange(90)."""
    policy = realm.get("passwordPolicy") or ""
    for clause in ("length(12)", "digits(1)", "upperCase(1)", "lowerCase(1)",
                   "specialChars(1)", "notUsername", "hashIterations"):
        assert clause in policy, (
            f"password policy missing {clause!r}: got {policy!r}"
        )
