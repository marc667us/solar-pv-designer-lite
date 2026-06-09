"""
Contract tests for secrets_broker.py (Phase 0 of the dynamic secrets engine).

Covers the 7 behaviours documented in SECRETS_ENGINE_PROPOSAL_v3.md §2.7:
  1. tier="CRITICAL"  raises VaultUnreachable when Vault is down.
  2. tier="DEGRADED"  warms from env at boot; once Vault has served the path,
                      env fallthrough is locked out for that path.
  3. tier="DEV"       falls through to env var in dev mode.
  4. tier="DEV"       raises BrokerProductionRefusal in production mode.
  5. AccessLoggedSecret.get_value() / __getitem__ raise SecretExpired after TTL.
  6. Audit deque drains via the background flush worker within ~2s.
  7. Sampling: N reads of the same secret produce roughly N/BROKER_AUDIT_SAMPLE_N
                rows plus the always-logged first-of-minute row.

Plus one happy-path smoke for the _FakeVault test short-circuit.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time

import pytest

# Make the project root importable so `import secrets_broker` works
# regardless of pytest's working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import secrets_broker as sb  # noqa: E402


# ── Shared fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Per-test: temp audit DB, clean module state, neutral env."""
    db = tmp_path / "audit.db"
    monkeypatch.setenv("DB_PATH", str(db))
    # Default to dev mode unless a test sets otherwise.
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("FLASK_ENV", raising=False)
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    # Snapshot + wipe broker state.
    sb._reset_for_tests()
    yield
    sb._reset_for_tests()


def _audit_count(db_path: str, path_filter: str | None = None) -> int:
    """Helper: count rows in secret_audit, optionally filtered by path."""
    conn = sqlite3.connect(db_path)
    try:
        if path_filter:
            cur = conn.execute(
                "SELECT COUNT(*) FROM secret_audit WHERE path = ?", (path_filter,))
        else:
            cur = conn.execute("SELECT COUNT(*) FROM secret_audit")
        return cur.fetchone()[0]
    finally:
        conn.close()


# ── Happy path ───────────────────────────────────────────────────────────────

def test_fake_vault_read_returns_dict_and_audits(monkeypatch):
    """Happy path: VAULT_ADDR=test://memory + seed -> get() returns wrapper, audit fires."""
    monkeypatch.setenv("VAULT_ADDR", "test://memory")
    sb._TEST_SEED[sb._vault_path("email/brevo")] = {"api_key": "fake-brevo-xyz"}

    s = sb.get("email/brevo")
    assert isinstance(s, sb.AccessLoggedSecret)
    assert s["api_key"] == "fake-brevo-xyz"
    assert "api_key" in s

    sb._flush_now()
    db = os.environ["DB_PATH"]
    # at least 2 audit rows: vault_read + field-read
    assert _audit_count(db) >= 2


# ── Contract 1: tier=CRITICAL hard-fails when Vault is unreachable ──────────

def test_critical_tier_raises_when_vault_unreachable():
    """No VAULT_ADDR, no cache -> CRITICAL must raise VaultUnreachable."""
    with pytest.raises(sb.VaultUnreachable):
        sb.get("payment/paystack", tier="CRITICAL")


def test_critical_tier_default_tier_for_payment(monkeypatch):
    """Default tier for payment/paystack is CRITICAL per _TIER -> still raises."""
    with pytest.raises(sb.VaultUnreachable):
        sb.get("payment/paystack")  # no explicit tier


# ── Contract 2: tier=DEGRADED warms from env at boot, then locks ───────────

def test_degraded_warms_from_env_when_no_vault(monkeypatch):
    """No Vault, env has BREVO_API_KEY -> DEGRADED returns env-warmed."""
    monkeypatch.setenv("BREVO_API_KEY", "env-warmed-brevo")
    s = sb.get("email/brevo", tier="DEGRADED")
    assert s["api_key"] == "env-warmed-brevo"


def test_degraded_locks_out_env_after_vault_success(monkeypatch):
    """First serve from env, then Vault becomes available and serves a different value,
    then Vault becomes unreachable again -> we get the CACHED Vault value, not env."""
    # Step 1: No Vault. env has stale value. DEGRADED serves env warm.
    monkeypatch.setenv("BREVO_API_KEY", "env-stale")
    s1 = sb.get("email/brevo", tier="DEGRADED")
    assert s1["api_key"] == "env-stale"

    # Step 2: Vault becomes available with the canonical value.
    monkeypatch.setenv("VAULT_ADDR", "test://memory")
    sb._TEST_SEED[sb._vault_path("email/brevo")] = {"api_key": "vault-canonical"}
    s2 = sb.get("email/brevo", tier="DEGRADED")
    assert s2["api_key"] == "vault-canonical"

    # Step 3: Vault unreachable again. Env still has stale. We must NOT serve env;
    # the cached vault value should be returned.
    monkeypatch.delenv("VAULT_ADDR")
    s3 = sb.get("email/brevo", tier="DEGRADED")
    assert s3["api_key"] == "vault-canonical", \
        "env fallthrough must be locked once Vault has served the path"


# ── Contract 3: tier=DEV falls through to env in dev mode ───────────────────

def test_dev_tier_falls_through_in_dev_mode(monkeypatch):
    """No production signals, no Vault -> DEV returns env-warmed."""
    monkeypatch.setenv("SECRET_KEY", "dev-secret-key")
    s = sb.get("flask/secret_key", tier="DEV")
    assert s["secret_key"] == "dev-secret-key"


# ── Contract 4: tier=DEV refuses in production mode ─────────────────────────

def test_dev_tier_raises_in_production_render(monkeypatch):
    """RENDER=true -> DEV must refuse env fallthrough."""
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("SECRET_KEY", "would-leak-from-env")
    with pytest.raises(sb.BrokerProductionRefusal):
        sb.get("flask/secret_key", tier="DEV")


def test_dev_tier_raises_in_production_flask_env(monkeypatch):
    """FLASK_ENV=production -> DEV must refuse env fallthrough."""
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "would-leak-from-env")
    with pytest.raises(sb.BrokerProductionRefusal):
        sb.get("flask/secret_key", tier="DEV")


# ── Contract 5: TTL expiry raises SecretExpired ─────────────────────────────

def test_access_logged_secret_raises_after_ttl(monkeypatch):
    """ttl_seconds=1 -> after 1.5s, access raises SecretExpired."""
    monkeypatch.setenv("VAULT_ADDR", "test://memory")
    sb._TEST_SEED[sb._vault_path("email/brevo")] = {"api_key": "x"}
    s = sb.get("email/brevo", ttl_seconds=1)
    time.sleep(1.5)
    with pytest.raises(sb.SecretExpired):
        s.get_value()
    with pytest.raises(sb.SecretExpired):
        _ = s["api_key"]


# ── Contract 6: audit flush worker drains the deque ─────────────────────────

def test_audit_worker_drains_within_2s(monkeypatch):
    """Trigger a few reads, wait ~2s for the worker, then assert table populated."""
    monkeypatch.setenv("VAULT_ADDR", "test://memory")
    sb._TEST_SEED[sb._vault_path("email/brevo")] = {"api_key": "x"}
    for _ in range(3):
        s = sb.get("email/brevo")
        _ = s["api_key"]
    time.sleep(2.0)  # > one flush tick
    db = os.environ["DB_PATH"]
    n = _audit_count(db, path_filter="email/brevo")
    # 3 vault_reads + at least the first-of-minute for ["api_key"]
    assert n >= 3, f"expected at least 3 audit rows, got {n}"


# ── Contract 7: sampling produces ~N/N rows + first-of-minute ───────────────

def test_sampling_emits_expected_row_count(monkeypatch):
    """100 field reads of the same secret -> roughly 100/SAMPLE_N rows,
    plus the first-of-minute always-emit row. Statistical tolerance applied."""
    monkeypatch.setenv("VAULT_ADDR", "test://memory")
    monkeypatch.setenv("BROKER_AUDIT_SAMPLE_N", "10")
    # The constant is read at import time; reload not feasible mid-test.
    # Instead, monkey-patch the module-level constant directly.
    monkeypatch.setattr(sb, "BROKER_AUDIT_SAMPLE_N", 10)
    sb._TEST_SEED[sb._vault_path("email/brevo")] = {"api_key": "x"}

    # Single fetch (1 vault_read audit row), then 100 field reads.
    s = sb.get("email/brevo")
    for _ in range(100):
        _ = s["api_key"]

    sb._flush_now()
    db = os.environ["DB_PATH"]
    # The field path is "email/brevo#api_key" — separate from "email/brevo".
    n_field = _audit_count(db, path_filter="email/brevo#api_key")
    # Expected: ~10 sampled + 1 first-of-minute = ~11. Allow 5..30 for noise.
    assert 5 <= n_field <= 30, (
        f"expected ~10 sampled audit rows for #api_key, got {n_field} "
        f"(BROKER_AUDIT_SAMPLE_N=10)"
    )

    # And the vault_read of email/brevo itself should also be recorded.
    n_vault = _audit_count(db, path_filter="email/brevo")
    assert n_vault >= 1, f"expected at least 1 vault_read row, got {n_vault}"
