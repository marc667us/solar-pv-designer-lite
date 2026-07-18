"""
secrets_broker.py — Phase 0 of the SolarPro dynamic-secrets engine.

Implements the v3 proposal contract WITHOUT a live Vault dependency.
All real Vault calls are stubbed (`_FakeVault` short-circuit or hard-coded
"unreachable" responses) so this module compiles, runs, and tests cleanly
on a dev box that doesn't yet have Vault stood up.

Phase 1 will: add `hvac` as a real client, populate `_FakeVault` with the
production Vault address, and wire callers into `secrets.get(...)`.

==============================================================================
CONTRACT (frozen — v3 §2.5 + §2.6 + §2.7)
==============================================================================

Production detection (v3 N8):
    "production" = os.environ.get("RENDER") == "true"
                OR os.environ.get("FLASK_ENV") == "production"
    tier="DEV" fallthrough is REFUSED in production.

Fork / thread safety (v3 N13):
    The module-level Vault client is created lazily under a threading.Lock.
    Gunicorn workers fork — each worker initializes its own client on first
    use. No shared state between workers; no shared state between processes.

Test contract (v3 N9):
    If VAULT_ADDR == "test://memory" (re-checked PER CALL, never cached),
    fall through to _FakeVault reading from `_TEST_SEED`.
    Tests populate _TEST_SEED before invoking get().

Audit policy (v3 N14):
    - writes / failures / first-read-per-path-per-minute: ALWAYS logged
    - other reads: sampled 1-in-N (BROKER_AUDIT_SAMPLE_N, env override)
    - drop counter exported as `broker.audit_drops` metric for monitoring

Audit transport (v3 N4, N7):
    - In-process: collections.deque(maxlen=10_000) — explicit oldest-drop
    - Background _audit_flush_worker: 1s tick, batched INSERT to secret_audit
    - Drop event logged as a single audit row per minute

Tiered fallback (v3 §2.6):
    - CRITICAL: hard-fail if Vault unreachable, boot OR runtime
    - DEGRADED: warm-from-env one-shot at boot; refuse env after first
                successful Vault read; serve last-cached value mid-life
    - DEV: warm-from-env any time in dev mode; REFUSED if production
==============================================================================
"""

from __future__ import annotations

import collections
import json
import os
import random
import sqlite3
import threading
import time
import uuid
import secrets_file          # encrypted-at-rest store; env still wins (see _env_warm)
from dataclasses import dataclass, asdict
from typing import Any


# ── Exceptions ───────────────────────────────────────────────────────────────

class SecretExpired(Exception):
    """Raised when an AccessLoggedSecret is read after its TTL has elapsed."""

class VaultUnreachable(Exception):
    """Raised when a CRITICAL secret cannot be served — Vault is down and no fallback applies."""

class BrokerProductionRefusal(Exception):
    """Raised when tier=DEV fallthrough is attempted in production mode."""


# ── Constants ────────────────────────────────────────────────────────────────

BROKER_AUDIT_SAMPLE_N = int(os.environ.get("BROKER_AUDIT_SAMPLE_N", "10"))
_AUDIT_BUF_MAX = 10_000
_AUDIT_FLUSH_INTERVAL_S = 1.0

# Logical path -> tier. v3 §2.6 (N5 re-tiered).
_TIER: dict[str, str] = {
    "payment/paystack":        "CRITICAL",
    "payment/stripe":          "CRITICAL",
    "flask/secret_key":        "CRITICAL",
    "database/connection_url": "CRITICAL",   # Phase 3.1+
    "seed/admin":              "CRITICAL",
    "seed/marc667us":          "CRITICAL",
    "email/brevo":             "DEGRADED",
    "email/resend":            "DEGRADED",
    "email/smtp":              "DEGRADED",
    "ai/openrouter":           "DEGRADED",
    "ai/ollama":               "DEGRADED",
    # users/<id>/resend is templated at lookup time
}

# Logical path -> env var name per field. The "warm from env" map.
_ENV_MAP: dict[str, dict[str, str]] = {
    "email/brevo":      {"api_key": "BREVO_API_KEY"},
    "email/resend":     {"api_key": "RESEND_API_KEY"},
    "email/smtp":       {"host": "SMTP_HOST", "port": "SMTP_PORT",
                         "user": "SMTP_USER", "pass": "SMTP_PASS",
                         "from": "SMTP_FROM", "tls": "SMTP_TLS"},
    "ai/openrouter":    {"api_key": "OPENROUTER_API_KEY"},
    "ai/ollama":        {"url": "OLLAMA_URL", "model": "OLLAMA_MODEL"},
    "payment/paystack": {"secret": "PAYSTACK_SECRET_KEY",
                         "public": "PAYSTACK_PUBLIC_KEY"},
    "payment/stripe":   {"secret": "STRIPE_SECRET_KEY",
                         "webhook_secret": "STRIPE_WEBHOOK_SECRET"},
    "flask/secret_key": {"secret_key": "SECRET_KEY"},
    "seed/admin":       {"password": "SOLARPRO_ADMIN_PASSWORD"},
    "seed/marc667us":   {"password": "SOLARPRO_OWNER_PASSWORD"},
}


# ── Module state ─────────────────────────────────────────────────────────────

# Last-known-good cache from successful Vault reads (per path).
_warm_cache: dict[str, dict] = {}
_warm_cache_lock = threading.Lock()

# Paths that have been served by Vault successfully — env fallthrough locked out for these.
_env_disabled_for_paths: set[str] = set()

# Test seed — populated by tests when VAULT_ADDR="test://memory".
_TEST_SEED: dict[str, dict] = {}

# Audit pipeline.
_audit_buf: collections.deque = collections.deque(maxlen=_AUDIT_BUF_MAX)
_audit_drops_total: int = 0
_audit_lock = threading.Lock()
_audit_worker_started = False
_audit_worker_lock = threading.Lock()

# First-of-minute-per-path tracker for the always-log signal.
_first_seen_minute: dict[str, int] = {}
_first_seen_lock = threading.Lock()

# Vault client (lazy init). _get_client() handles both real hvac and FakeVault.
_client: Any | None = None
_client_lock = threading.Lock()


def _get_client():
    """Return a Vault client. Thread-safe + fork-safe lazy init.
    Real hvac.Client when VAULT_ADDR points at a real URL.
    Test path (VAULT_ADDR=test://memory) is handled in _vault_read directly."""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        import hvac  # lazy — keeps Phase 0 working without hvac installed
        vault_addr = os.environ["VAULT_ADDR"]
        c = hvac.Client(url=vault_addr)
        # AppRole login
        role_id   = os.environ.get("VAULT_ROLE_ID", "")
        secret_id = os.environ.get("VAULT_SECRET_ID", "")
        if role_id and secret_id:
            c.auth.approle.login(role_id=role_id, secret_id=secret_id)
        elif os.environ.get("VAULT_TOKEN"):
            c.token = os.environ["VAULT_TOKEN"]
        if not c.is_authenticated():
            raise VaultUnreachable("AppRole/token auth failed; Vault client not authenticated")
        _client = c
        return _client


# ── Public API ───────────────────────────────────────────────────────────────

def get(path: str, tier: str | None = None, ttl_seconds: int = 300) -> "AccessLoggedSecret":
    """
    Fetch a secret by logical path. Returns AccessLoggedSecret with TTL.

    Inputs:
      path         logical path (e.g. "email/brevo"). Maps to Vault path
                   "kv/data/solarpro/<path>" or env-var set via _ENV_MAP.
      tier         "CRITICAL" | "DEGRADED" | "DEV". Defaults to _TIER mapping
                   (caller can override for paths not in _TIER, e.g. per-user).
      ttl_seconds  Wrapper TTL — after this, .get_value()/.__getitem__() raises
                   SecretExpired and the caller must re-call get(). Allows
                   callers to bound how long they hold a value in memory.

    Output:
      AccessLoggedSecret. Use ["field"] to pull a specific field; .get_value()
      to get the whole dict. Both audit-log on access.

    Tiered fallback (per v3 §2.6):
      Vault reachable        -> serve from Vault, cache, lock-out env for path
      Vault unreachable boot -> CRITICAL raises VaultUnreachable
                                DEGRADED warms from env once (if no Vault hit yet)
                                DEV warms from env (or fails in production)
      Vault unreachable mid  -> CRITICAL raises VaultUnreachable
                                DEGRADED/DEV serve from _warm_cache; WARN log
    """
    tier = tier or _TIER.get(path, "DEGRADED")
    if tier not in ("CRITICAL", "DEGRADED", "DEV"):
        raise ValueError(f"unknown tier: {tier!r}")

    vault_req_id = ""

    try:
        data, vault_req_id = _vault_read(path)
        with _warm_cache_lock:
            _warm_cache[path] = data
            _env_disabled_for_paths.add(path)
        _audit_enqueue(_AuditRow(
            occurred_at=time.time(),
            vault_req_id=vault_req_id,
            app_req_id=_get_app_req_id(),
            auth_method="approle",
            accessor="phase0-stub",
            display_name="phase0-broker",
            operation="vault_read",
            path=path,
            sampled=_should_sample(path),
            error=None,
        ))
        return AccessLoggedSecret(data, path, ttl_seconds, vault_req_id)

    except VaultUnreachable as exc:
        if tier == "CRITICAL":
            _audit_enqueue(_AuditRow(
                occurred_at=time.time(), vault_req_id="", app_req_id=_get_app_req_id(),
                auth_method="approle", accessor="phase0-stub", display_name="phase0-broker",
                operation="vault_read", path=path, sampled=1, error=str(exc),
            ))
            raise

        # DEGRADED / DEV: cache hit?
        with _warm_cache_lock:
            cached = _warm_cache.get(path)
        if cached is not None:
            _audit_enqueue(_AuditRow(
                occurred_at=time.time(), vault_req_id="", app_req_id=_get_app_req_id(),
                auth_method="cache", accessor="phase0-stub", display_name="phase0-broker",
                operation="cache_read", path=path, sampled=1, error="vault unreachable",
            ))
            return AccessLoggedSecret(cached, path, ttl_seconds, vault_req_id="")

        # Cold start, no cache yet — env warm-up.
        # DEGRADED: allow one-shot warm ONLY if Vault has never served this path.
        # DEV: refused in production; allowed in dev.
        if tier == "DEV" and _is_production():
            raise BrokerProductionRefusal(
                f"tier=DEV fallthrough refused in production for path {path!r}"
            )
        if tier == "DEGRADED" and path in _env_disabled_for_paths:
            # Vault served this path at some point — env warm is permanently locked.
            raise VaultUnreachable(
                f"path {path!r} previously served by Vault; env fallthrough locked out"
            )
        warmed = _env_warm(path)
        if warmed is None:
            raise VaultUnreachable(
                f"no Vault, no warm cache, no env warmup available for path {path!r}"
            )
        with _warm_cache_lock:
            _warm_cache[path] = warmed
        _audit_enqueue(_AuditRow(
            occurred_at=time.time(), vault_req_id="", app_req_id=_get_app_req_id(),
            auth_method="env", accessor="phase0-stub", display_name="phase0-broker",
            operation="env_warm", path=path, sampled=1,
            error=f"vault unreachable, tier={tier} warm-from-env",
        ))
        return AccessLoggedSecret(warmed, path, ttl_seconds, vault_req_id="")


def set_secret(path: str, value: dict) -> None:
    """
    Write a secret via Vault (Phase 1+). In Phase 0 this updates _TEST_SEED
    when VAULT_ADDR="test://memory", else raises. Writes are ALWAYS audited.
    """
    if os.environ.get("VAULT_ADDR") != "test://memory":
        raise NotImplementedError("Phase 0 supports writes only via _FakeVault")
    _TEST_SEED[_vault_path(path)] = value
    _audit_enqueue(_AuditRow(
        occurred_at=time.time(), vault_req_id=_new_req_id(), app_req_id=_get_app_req_id(),
        auth_method="approle", accessor="phase0-stub", display_name="phase0-broker",
        operation="write", path=path, sampled=1, error=None,
    ))


def audit_drops() -> int:
    """Expose dropped-row count for monitoring."""
    return _audit_drops_total


# ── AccessLoggedSecret ───────────────────────────────────────────────────────

class AccessLoggedSecret:
    """
    Audit wrapper around a secret dict. NOT a security primitive.

    In-process callers can bypass via __dict__ (this is Python, after all).
    Sole purpose: every legitimate use of .get_value() / __getitem__ is
    recorded with timestamps + request IDs joining the app and Vault audit
    logs.

    TTL is advisory only — after expiry, access raises SecretExpired so
    callers MUST re-call secrets.get() (forcing a fresh audit trail), but
    the underlying string is unchanged.
    """
    __slots__ = ("_value", "_path", "_issued_at", "_ttl", "_vault_req_id")

    def __init__(self, value: dict, path: str, ttl_seconds: int, vault_req_id: str = ""):
        self._value = dict(value) if isinstance(value, dict) else {"value": value}
        self._path = path
        self._issued_at = time.time()
        self._ttl = max(1, int(ttl_seconds))
        self._vault_req_id = vault_req_id

    def get_value(self) -> dict:
        """Return the underlying dict. Audited subject to sampling policy
        (writes/errors/first-of-minute always logged; rest 1-in-N)."""
        self._check_ttl()
        if _should_sample(self._path):
            _audit_enqueue(_AuditRow(
                occurred_at=time.time(), vault_req_id=self._vault_req_id,
                app_req_id=_get_app_req_id(), auth_method="wrapper",
                accessor="phase0-stub", display_name="phase0-broker",
                operation="read", path=self._path,
                sampled=1, error=None,
            ))
        return dict(self._value)

    def __getitem__(self, key: str):
        """Pull a single field. Audited subject to sampling policy."""
        self._check_ttl()
        field_path = f"{self._path}#{key}"
        if _should_sample(field_path):
            _audit_enqueue(_AuditRow(
                occurred_at=time.time(), vault_req_id=self._vault_req_id,
                app_req_id=_get_app_req_id(), auth_method="wrapper",
                accessor="phase0-stub", display_name="phase0-broker",
                operation="read", path=field_path,
                sampled=1, error=None,
            ))
        return self._value[key]

    def __contains__(self, key: str) -> bool:
        return key in self._value

    def _check_ttl(self) -> None:
        if time.time() > self._issued_at + self._ttl:
            raise SecretExpired(self._path)


# ── Internals ────────────────────────────────────────────────────────────────

@dataclass
class _AuditRow:
    occurred_at: float
    vault_req_id: str
    app_req_id: str | None
    auth_method: str
    accessor: str
    display_name: str
    operation: str
    path: str
    sampled: int  # 1 = this row was sampled-or-always-logged; 0 = N/A
    error: str | None


def _vault_path(logical: str) -> str:
    return f"kv/data/solarpro/{logical}"


def _vault_read(logical_path: str) -> tuple[dict, str]:
    """
    Read from Vault.
      - VAULT_ADDR=="test://memory"  -> read from _TEST_SEED (in-process)
      - VAULT_ADDR set to a URL      -> real hvac call, KV v2 read
      - VAULT_ADDR unset/empty       -> raise VaultUnreachable (caller falls back per tier)
    Returns (data dict, vault_req_id).
    """
    vault_addr = os.environ.get("VAULT_ADDR", "")
    if vault_addr == "test://memory":
        full_path = _vault_path(logical_path)
        if full_path not in _TEST_SEED:
            raise VaultUnreachable(f"{logical_path!r} not in _TEST_SEED")
        return dict(_TEST_SEED[full_path]), _new_req_id()
    if not vault_addr:
        raise VaultUnreachable(f"VAULT_ADDR unset; no Vault client to call")

    # Real Vault path — Phase 1+. hvac is an optional dep; import lazily so the
    # broker module imports cleanly even if hvac isn't installed.
    try:
        client = _get_client()
        # KV v2: data lives under <mount>/data/<path>; .read_secret_version
        # handles the path construction. We strip the "kv/data/" prefix since
        # hvac wants the logical path under the mount.
        mount, _, sub = _vault_path(logical_path).partition("/data/")
        resp = client.secrets.kv.v2.read_secret_version(
            mount_point=mount, path=sub, raise_on_deleted_version=False)
        data = resp.get("data", {}).get("data", {}) or {}
        if not data:
            raise VaultUnreachable(
                f"Vault returned empty data for {logical_path!r}")
        return dict(data), resp.get("request_id", "")
    except VaultUnreachable:
        raise
    except Exception as exc:
        raise VaultUnreachable(f"Vault call failed for {logical_path!r}: {exc}")


def _env_warm(logical_path: str) -> dict | None:
    """Build a dict from env vars per _ENV_MAP. Returns None if the path
    isn't mapped or no env var values exist."""
    fields = _ENV_MAP.get(logical_path)
    if not fields:
        return None
    out: dict[str, str] = {}
    for field_name, env_name in fields.items():
        # PRECEDENCE: the real environment first, the encrypted store only as a filler.
        #
        # On Render every secret arrives as a dashboard environment variable and there is no
        # `.env` at all, so this order leaves production behaviour byte-for-byte unchanged --
        # the encrypted store can only supply a value the environment did not already have.
        # A security change that can take the site down is not a security improvement.
        val = os.environ.get(env_name, "")
        if not val:
            val = secrets_file.get(env_name, "")
        if val:
            out[field_name] = val
    return out if out else None


def _is_production() -> bool:
    return (os.environ.get("RENDER") == "true"
            or os.environ.get("FLASK_ENV") == "production")


def _new_req_id() -> str:
    return uuid.uuid4().hex


def _get_app_req_id() -> str | None:
    """Best-effort: pull Flask's per-request id if we're in a request context."""
    try:
        from flask import g, has_request_context
        if has_request_context():
            return getattr(g, "request_id", None)
    except Exception:
        pass
    return None


def _should_sample(path: str) -> bool:
    """Decide whether to emit an audit row for a non-write/non-error read.
    Always logged: first-of-minute-per-path. Otherwise: 1-in-N."""
    minute = int(time.time() // 60)
    with _first_seen_lock:
        last = _first_seen_minute.get(path)
        if last != minute:
            _first_seen_minute[path] = minute
            return True
    return random.randint(1, BROKER_AUDIT_SAMPLE_N) == 1


def _audit_enqueue(row: _AuditRow) -> None:
    """Append to bounded deque; oldest dropped on overflow. Thread-safe."""
    global _audit_drops_total
    _ensure_audit_worker()
    with _audit_lock:
        if len(_audit_buf) == _audit_buf.maxlen:
            _audit_drops_total += 1
        _audit_buf.append(row)


def _ensure_audit_worker() -> None:
    """Start the flush worker lazily on first audit. Thread-safe."""
    global _audit_worker_started
    if _audit_worker_started:
        return
    with _audit_worker_lock:
        if _audit_worker_started:
            return
        _ensure_audit_table()
        t = threading.Thread(target=_audit_flush_worker,
                             name="secrets_broker.audit_flush",
                             daemon=True)
        t.start()
        _audit_worker_started = True


def _audit_flush_worker() -> None:
    while True:
        time.sleep(_AUDIT_FLUSH_INTERVAL_S)
        with _audit_lock:
            if not _audit_buf:
                continue
            batch = list(_audit_buf)
            _audit_buf.clear()
        try:
            _batched_insert(batch)
        except Exception:
            # Audit must never crash the worker. Log and continue.
            # Worst case: rows lost; drop counter unchanged.
            pass


def _batched_insert(batch: list[_AuditRow]) -> None:
    """Single transaction insert of a batch into secret_audit.
    Self-heals: ensures the table exists for the current DB_PATH on every
    call. Cheap (CREATE TABLE IF NOT EXISTS) and covers DB_PATH changes
    that happen across processes / across test fixtures."""
    _ensure_audit_table()
    db_path = os.environ.get("DB_PATH", "solar.db")
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        conn.executemany(
            "INSERT INTO secret_audit ("
            " occurred_at, vault_req_id, app_req_id, auth_method, accessor,"
            " display_name, operation, path, sampled, error"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(r.occurred_at, r.vault_req_id, r.app_req_id, r.auth_method, r.accessor,
              r.display_name, r.operation, r.path, r.sampled, r.error)
             for r in batch]
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_audit_table() -> None:
    """Create secret_audit if it doesn't already exist. Idempotent."""
    db_path = os.environ.get("DB_PATH", "solar.db")
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS secret_audit (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at   REAL    NOT NULL,
                vault_req_id  TEXT,
                app_req_id    TEXT,
                auth_method   TEXT    NOT NULL,
                accessor      TEXT    NOT NULL,
                display_name  TEXT,
                operation     TEXT    NOT NULL,
                path          TEXT    NOT NULL,
                sampled       INTEGER NOT NULL DEFAULT 0,
                error         TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_secret_audit_path
                ON secret_audit(path);
            CREATE INDEX IF NOT EXISTS idx_secret_audit_occurred
                ON secret_audit(occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_secret_audit_app_req
                ON secret_audit(app_req_id);
        """)
        conn.commit()
    finally:
        conn.close()


# ── Test helpers (exposed for the test suite, NOT for app code) ─────────────

def _reset_for_tests() -> None:
    """Wipe module state so tests start cleanly. Tests only — do not call from app."""
    global _audit_drops_total, _audit_worker_started
    with _warm_cache_lock:
        _warm_cache.clear()
        _env_disabled_for_paths.clear()
    with _audit_lock:
        _audit_buf.clear()
    with _first_seen_lock:
        _first_seen_minute.clear()
    _TEST_SEED.clear()
    _audit_drops_total = 0
    # Don't restart the worker thread; it just polls the now-cleared buffer.


def _flush_now() -> None:
    """Force an immediate flush of buffered audit rows. Tests only."""
    with _audit_lock:
        if not _audit_buf:
            return
        batch = list(_audit_buf)
        _audit_buf.clear()
    _batched_insert(batch)
