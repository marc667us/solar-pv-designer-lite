"""
ai_budget.py — AI spend + per-user token cap enforcement.

DESIGN (frozen — supervisor-approved 2026-06-10)
- One SQLite table `ai_usage_ledger` records every AI call with tokens + estimated cost.
- Org-wide spend cap: AI_SPEND_CAP_USD_MONTHLY (default $10). Sum of cost_usd for the
  current UTC calendar month; if at-or-over, next non-admin call is blocked.
- Per-user token cap: AI_USER_TOKEN_CAP_24H (default 50,000). Sum of total_tokens for
  the last 24h rolling window per user_id; if at-or-over, blocked.
- Admin bypass: is_admin=True users skip both checks (calls still ledger-recorded).
- Hard block: blocked calls return ("Quota...", "capped") and do NOT hit upstream.
- Anonymous (user_id=None): per-user cap skipped, org spend cap still applies.

PROVIDER COST TABLE (USD per million tokens, prompt/completion)
- OpenRouter free models: $0
- Ollama (local): $0
- GitHub Models free tier: $0
- Anthropic claude-haiku-4-5: $1 / $5
- Anthropic claude-opus-4-7:  $15 / $75
- Unknown: $0 (defensive — never assume cost we can't justify)

TOKEN ESTIMATION — len(text)/4 heuristic when provider returns no usage.

NOT YET WIRED — multi-tenant tenant_id. Users table is single-tenant in current
schema; add when org_id lands on users.
"""

import os
import sqlite3
import time
from datetime import datetime, timezone

# Caps — env-overrideable so admin can tune without code redeploy.
SPEND_CAP_USD_MONTHLY = float(os.environ.get("AI_SPEND_CAP_USD_MONTHLY", "10"))
USER_TOKEN_CAP_24H    = int(os.environ.get("AI_USER_TOKEN_CAP_24H", "50000"))

# USD per million tokens: (prompt_rate, completion_rate). Missing key => (0, 0).
_PROVIDER_COSTS = {
    ("anthropic", "claude-opus-4-7"):           (15.00, 75.00),
    ("anthropic", "claude-haiku-4-5-20251001"): ( 1.00,  5.00),
    ("anthropic", "claude-haiku-4-5"):          ( 1.00,  5.00),
}


def _db():
    return os.environ.get("DB_PATH", "solar.db")


# Per-DB-path guard: skip the no-op CREATE IF NOT EXISTS after the first call
# against a given DB path. Keyed by path so DB_PATH changes (tests / multi-DB)
# still trigger a fresh ensure.
_ensured_paths: set[str] = set()


def _ensure_table():
    """Idempotent. Self-heals across DB_PATH changes; skips after first call per path."""
    path = _db()
    if path in _ensured_paths:
        return
    with sqlite3.connect(path, timeout=5) as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS ai_usage_ledger (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at       REAL    NOT NULL,
                user_id           INTEGER,
                provider          TEXT    NOT NULL,
                model             TEXT    NOT NULL DEFAULT '',
                prompt_tokens     INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens      INTEGER NOT NULL DEFAULT 0,
                cost_usd          REAL    NOT NULL DEFAULT 0,
                endpoint          TEXT    DEFAULT '',
                request_id        TEXT    DEFAULT '',
                blocked           INTEGER NOT NULL DEFAULT 0,
                error             TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_ai_usage_user_time
                ON ai_usage_ledger(user_id, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_ai_usage_occurred
                ON ai_usage_ledger(occurred_at DESC);
        """)
    _ensured_paths.add(path)


def estimate_tokens(text):
    """English chars/4 heuristic. Returns >=1 for any non-empty input."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def calc_cost_usd(provider, model, prompt_tokens, completion_tokens):
    """USD cost for one call. Unknown provider/model => $0 (assume free)."""
    rates = _PROVIDER_COSTS.get((provider, model), (0.0, 0.0))
    return (prompt_tokens * rates[0] + completion_tokens * rates[1]) / 1_000_000.0


def get_org_spend_this_month():
    """Sum cost_usd for the current UTC calendar month (blocked rows excluded)."""
    _ensure_table()
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp()
    with sqlite3.connect(_db(), timeout=5) as c:
        row = c.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) FROM ai_usage_ledger "
            "WHERE occurred_at >= ? AND blocked = 0",
            (month_start,)).fetchone()
        return float(row[0] or 0.0)


def get_user_tokens_24h(user_id):
    """Sum total_tokens for last 24h for this user. user_id=None => 0."""
    if user_id is None:
        return 0
    _ensure_table()
    cutoff = time.time() - 86400
    with sqlite3.connect(_db(), timeout=5) as c:
        row = c.execute(
            "SELECT COALESCE(SUM(total_tokens), 0) FROM ai_usage_ledger "
            "WHERE user_id = ? AND occurred_at >= ? AND blocked = 0",
            (user_id, cutoff)).fetchone()
        return int(row[0] or 0)


def get_user_remaining(user_id):
    """Return (remaining_tokens, reset_seconds, used_24h)."""
    used = get_user_tokens_24h(user_id)
    remaining = max(0, USER_TOKEN_CAP_24H - used)
    cutoff = time.time() - 86400
    oldest = None
    if user_id is not None:
        with sqlite3.connect(_db(), timeout=5) as c:
            row = c.execute(
                "SELECT MIN(occurred_at) FROM ai_usage_ledger "
                "WHERE user_id = ? AND occurred_at >= ? AND blocked = 0",
                (user_id, cutoff)).fetchone()
            oldest = row[0]
    reset_seconds = max(0, int((oldest + 86400) - time.time())) if oldest else 0
    return remaining, reset_seconds, used


def check_caps(user_id, is_admin=False):
    """
    Pre-flight cap gate.
    Returns (allowed: bool, reason: str | None).

    Admin: always allowed (bypass). Anonymous (user_id=None): org cap only.
    Cap order: org spend first (cheaper to check, kills calls for everyone),
    then per-user token cap.
    """
    if is_admin:
        return True, None
    _ensure_table()
    spend = get_org_spend_this_month()
    if spend >= SPEND_CAP_USD_MONTHLY:
        return False, (
            f"Monthly AI spend cap reached "
            f"(${spend:.2f} / ${SPEND_CAP_USD_MONTHLY:.2f}). "
            f"Service will resume on the 1st of next month."
        )
    if user_id is None:
        return True, None
    remaining, reset_s, used = get_user_remaining(user_id)
    if remaining <= 0:
        hours = reset_s // 3600
        mins  = (reset_s % 3600) // 60
        return False, (
            f"Daily AI quota used ({used:,} / {USER_TOKEN_CAP_24H:,} tokens). "
            f"Resets in {hours}h {mins}m."
        )
    return True, None


def record_usage(user_id, provider, model,
                 prompt_tokens=0, completion_tokens=0,
                 endpoint="", request_id="", blocked=False, error=None):
    """Insert one ledger row. NEVER raises — budget ledger must not crash AI calls."""
    try:
        _ensure_table()
        prompt_tokens     = max(0, int(prompt_tokens or 0))
        completion_tokens = max(0, int(completion_tokens or 0))
        total = prompt_tokens + completion_tokens
        cost  = calc_cost_usd(provider, model, prompt_tokens, completion_tokens)
        with sqlite3.connect(_db(), timeout=5) as c:
            c.execute(
                "INSERT INTO ai_usage_ledger ("
                " occurred_at, user_id, provider, model,"
                " prompt_tokens, completion_tokens, total_tokens,"
                " cost_usd, endpoint, request_id, blocked, error"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (time.time(), user_id, provider or "", model or "",
                 prompt_tokens, completion_tokens, total,
                 cost, endpoint or "", request_id or "",
                 1 if blocked else 0, error))
    except Exception:
        pass


def capped_response(reason):
    """Standard tuple to return from a capped AI client call."""
    return (reason, "capped")
