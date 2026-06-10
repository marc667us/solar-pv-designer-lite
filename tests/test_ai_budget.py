"""
Contract tests for ai_budget.py — supervisor-approved spec 2026-06-10.

Covers:
  1. record_usage inserts a row
  2. calc_cost_usd: known Anthropic models priced correctly; unknown = $0
  3. estimate_tokens: empty -> 0; non-empty -> >=1; chars/4 ratio
  4. check_caps admin bypass: always allowed even with massive spend recorded
  5. check_caps org spend cap blocks non-admin when sum >= cap
  6. check_caps per-user token cap blocks user when 24h sum >= cap
  7. check_caps anonymous (user_id=None) gets org cap only, not per-user
  8. get_user_remaining: zero usage returns full cap, reset=0
  9. get_org_spend_this_month: only includes current calendar month, excludes blocked
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_budget as ab  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    db = tmp_path / "budget.db"
    monkeypatch.setenv("DB_PATH", str(db))
    yield


# ── 1. record_usage inserts ──────────────────────────────────────────────────

def test_record_usage_inserts_row():
    ab.record_usage(user_id=1, provider="openrouter", model="llama-3.1",
                    prompt_tokens=100, completion_tokens=50,
                    endpoint="/api/assistant/chat")
    with sqlite3.connect(os.environ["DB_PATH"]) as c:
        row = c.execute(
            "SELECT user_id, provider, prompt_tokens, completion_tokens, "
            "total_tokens, cost_usd, blocked FROM ai_usage_ledger"
        ).fetchone()
    assert row == (1, "openrouter", 100, 50, 150, 0.0, 0)


def test_record_usage_never_raises_on_bad_input():
    """Best-effort: even garbage input must not crash AI calls."""
    ab.record_usage(user_id=None, provider=None, model=None,
                    prompt_tokens=None, completion_tokens=None)
    # If we got here, contract met.


# ── 2. calc_cost_usd ─────────────────────────────────────────────────────────

def test_calc_cost_claude_haiku_1m_in_1m_out_equals_6_usd():
    cost = ab.calc_cost_usd("anthropic", "claude-haiku-4-5-20251001",
                            1_000_000, 1_000_000)
    assert cost == pytest.approx(6.00)


def test_calc_cost_claude_opus_1m_in_1m_out_equals_90_usd():
    cost = ab.calc_cost_usd("anthropic", "claude-opus-4-7",
                            1_000_000, 1_000_000)
    assert cost == pytest.approx(90.00)


def test_calc_cost_unknown_provider_is_zero():
    assert ab.calc_cost_usd("openrouter", "llama-3.1", 1_000_000, 1_000_000) == 0.0
    assert ab.calc_cost_usd("ollama", "mistral", 999, 999) == 0.0


# ── 3. estimate_tokens ──────────────────────────────────────────────────────

def test_estimate_tokens_empty_is_zero():
    assert ab.estimate_tokens("") == 0
    assert ab.estimate_tokens(None) == 0


def test_estimate_tokens_chars_div_4():
    assert ab.estimate_tokens("a" * 400) == 100


def test_estimate_tokens_min_1_for_nonempty():
    assert ab.estimate_tokens("hi") == 1  # 2 chars // 4 = 0 -> max(1, 0) = 1


# ── 4. Admin bypass ─────────────────────────────────────────────────────────

def test_admin_always_allowed_even_over_spend_cap():
    """Pre-populate ledger with $999 spend; admin still gets through."""
    # Force a row that would push over cap if checked.
    ab.record_usage(user_id=1, provider="anthropic", model="claude-opus-4-7",
                    prompt_tokens=2_000_000, completion_tokens=2_000_000)
    # $15*2 + $75*2 = $180. Way over $10 cap.
    assert ab.get_org_spend_this_month() > ab.SPEND_CAP_USD_MONTHLY
    allowed, reason = ab.check_caps(user_id=1, is_admin=True)
    assert allowed is True
    assert reason is None


# ── 5. Org spend cap blocks ─────────────────────────────────────────────────

def test_org_spend_cap_blocks_non_admin(monkeypatch):
    monkeypatch.setattr(ab, "SPEND_CAP_USD_MONTHLY", 5.0)
    # Spend = $6 on Claude opus
    ab.record_usage(user_id=99, provider="anthropic", model="claude-opus-4-7",
                    prompt_tokens=400_000, completion_tokens=0)  # $6
    allowed, reason = ab.check_caps(user_id=99, is_admin=False)
    assert allowed is False
    assert "Monthly AI spend cap" in reason
    assert "$6.00" in reason or "$6.0" in reason


# ── 6. Per-user token cap blocks ────────────────────────────────────────────

def test_user_token_cap_blocks_user_over_24h(monkeypatch):
    monkeypatch.setattr(ab, "USER_TOKEN_CAP_24H", 1000)
    ab.record_usage(user_id=5, provider="openrouter", model="free",
                    prompt_tokens=600, completion_tokens=500)  # total 1100
    allowed, reason = ab.check_caps(user_id=5, is_admin=False)
    assert allowed is False
    assert "Daily AI quota" in reason
    assert "1,100" in reason or "1100" in reason


def test_user_token_cap_other_user_unaffected(monkeypatch):
    """User A burns their cap; user B still has full quota."""
    monkeypatch.setattr(ab, "USER_TOKEN_CAP_24H", 1000)
    ab.record_usage(user_id=5, provider="openrouter", model="free",
                    prompt_tokens=2000, completion_tokens=0)
    # User 6 has no usage.
    allowed, reason = ab.check_caps(user_id=6, is_admin=False)
    assert allowed is True
    assert reason is None


# ── 7. Anonymous (user_id=None) ─────────────────────────────────────────────

def test_anonymous_allowed_when_org_under_cap():
    """No user_id -> per-user cap skipped, org spend cap still applies."""
    allowed, reason = ab.check_caps(user_id=None, is_admin=False)
    assert allowed is True


def test_anonymous_blocked_when_org_over_cap(monkeypatch):
    monkeypatch.setattr(ab, "SPEND_CAP_USD_MONTHLY", 1.0)
    ab.record_usage(user_id=99, provider="anthropic", model="claude-opus-4-7",
                    prompt_tokens=200_000, completion_tokens=0)  # $3
    allowed, reason = ab.check_caps(user_id=None, is_admin=False)
    assert allowed is False
    assert "Monthly AI spend cap" in reason


# ── 8. get_user_remaining ───────────────────────────────────────────────────

def test_get_user_remaining_no_usage():
    remaining, reset_s, used = ab.get_user_remaining(user_id=42)
    assert remaining == ab.USER_TOKEN_CAP_24H
    assert used == 0
    assert reset_s == 0


def test_get_user_remaining_partial_usage():
    ab.record_usage(user_id=42, provider="openrouter", model="free",
                    prompt_tokens=10_000, completion_tokens=5_000)
    remaining, reset_s, used = ab.get_user_remaining(user_id=42)
    assert used == 15_000
    assert remaining == ab.USER_TOKEN_CAP_24H - 15_000
    assert reset_s > 0
    assert reset_s <= 86400


# ── 9. get_org_spend_this_month ─────────────────────────────────────────────

def test_org_spend_excludes_blocked_rows(monkeypatch):
    """Blocked rows (cap-rejected calls) must not count toward spend."""
    ab.record_usage(user_id=1, provider="anthropic", model="claude-opus-4-7",
                    prompt_tokens=100_000, completion_tokens=0,
                    blocked=True)  # would be $1.50 but blocked
    assert ab.get_org_spend_this_month() == 0.0


def test_org_spend_only_current_month():
    """Inject a row dated last month — it should not count."""
    ab._ensure_table()
    last_month = datetime.now(timezone.utc) - timedelta(days=45)
    with sqlite3.connect(os.environ["DB_PATH"]) as c:
        c.execute(
            "INSERT INTO ai_usage_ledger ("
            " occurred_at, user_id, provider, model,"
            " prompt_tokens, completion_tokens, total_tokens, cost_usd, blocked"
            ") VALUES (?, 1, 'anthropic', 'claude-opus-4-7', 100, 100, 200, 99.99, 0)",
            (last_month.timestamp(),))
    assert ab.get_org_spend_this_month() == 0.0
