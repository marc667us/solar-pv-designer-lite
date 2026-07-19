"""
api_manager.py — Single secure source for ALL external API calls in SolarPro Global.

USAGE (in web_app.py):
    from api_manager import api

    reply, provider = api.ai.chat(messages, system_prompt)
    ok, msg         = api.email.send(to, subject, html)
    ok, data        = api.payment.initialize(email, amount_kobo, callback_url)
    ok, data        = api.payment.verify(reference)
    results         = api.search.query("solar tenders Nigeria")
    commits         = api.github.recent_commits()
    status          = api.status()          # dict of provider availability
    api.reload()                            # hot-reload all keys without restart

WHY THIS MODULE EXISTS
- All API keys read ONCE from environment at startup (single secure source)
- api.reload() updates all keys with one call — not 40
- Every provider has try/except + fallback — one API down never breaks the app
- All responses are cached in SQLite — API failure returns stale data, not a crash
- Every call is logged to api_logs table for monitoring/debugging
"""

import os, json, time, sqlite3, hashlib, logging, contextvars
from datetime import datetime

import secrets_broker  # Phase 1: routes secret reads through the broker (audit + tier + future Vault)
import ai_budget        # spend cap + per-user token cap (supervisor-approved 2026-06-10)

logger = logging.getLogger("api_manager")


# Internal helper used by the lazy properties below. Centralizes the broker call
# + the tolerant "return empty string on miss" fallback that matches the prior
# eager-load behaviour (so the existing if-key-present provider guards still work).
def _secret_field(path: str, field: str, default: str = "") -> str:
    """Fetch one field from a secret path via the broker. Returns default
    when Vault is unreachable AND no env warm-up is available, so callers
    can fall through to the next provider exactly as they did pre-broker.
    Audited per the broker's sampling policy."""
    try:
        sec = secrets_broker.get(path, tier="DEGRADED")
        return sec[field]
    except (secrets_broker.VaultUnreachable, KeyError):
        return default


# ── Helpers ───────────────────────────────────────────────────────────────────

def _db_path():
    """Return the path to solar.db. Set DB_PATH env var to override."""
    return os.environ.get("DB_PATH", "solar.db")


def _now_str():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ── Cache & Log ───────────────────────────────────────────────────────────────

class _Store:
    """SQLite cache + log. Tables auto-created. Never raises — all errors are warnings."""

    def __init__(self):
        self.db = _db_path()
        self._init()

    def _init(self):
        try:
            with sqlite3.connect(self.db) as c:
                c.executescript("""
                    CREATE TABLE IF NOT EXISTS api_cache (
                        cache_key  TEXT PRIMARY KEY,
                        provider   TEXT NOT NULL DEFAULT '',
                        value      TEXT NOT NULL,
                        expires_at REAL NOT NULL,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS api_logs (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider    TEXT NOT NULL,
                        operation   TEXT NOT NULL,
                        status      TEXT NOT NULL,
                        duration_ms INTEGER DEFAULT 0,
                        error       TEXT DEFAULT '',
                        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_api_logs_provider
                        ON api_logs(provider, created_at);
                    CREATE INDEX IF NOT EXISTS idx_api_cache_expires
                        ON api_cache(expires_at);
                """)
        except Exception as e:
            logger.warning("_Store._init: %s", e)

    # ── cache ──────────────────────────────────────────────────────────────

    @staticmethod
    def _key(prefix, *args):
        h = hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()[:20]
        return f"{prefix}:{h}"

    def get(self, key):
        try:
            with sqlite3.connect(self.db) as c:
                row = c.execute(
                    "SELECT value FROM api_cache WHERE cache_key=? AND expires_at>?",
                    (key, time.time())).fetchone()
            return json.loads(row[0]) if row else None
        except Exception:
            return None

    def get_stale(self, key):
        """Return cached value even if expired — used as fallback when live call fails."""
        try:
            with sqlite3.connect(self.db) as c:
                row = c.execute(
                    "SELECT value FROM api_cache WHERE cache_key=? ORDER BY expires_at DESC LIMIT 1",
                    (key,)).fetchone()
            return json.loads(row[0]) if row else None
        except Exception:
            return None

    def set(self, key, value, ttl, provider=""):
        try:
            with sqlite3.connect(self.db) as c:
                # Portable upsert: works on both SQLite (>=3.24, which is what
                # any Python 3.8+ ships) and Postgres. The old INSERT OR REPLACE
                # form was SQLite-only and would fail if this _Store ever moved
                # to the main DB backend.
                c.execute(
                    "INSERT INTO api_cache (cache_key, provider, value, expires_at) "
                    "VALUES (?,?,?,?) "
                    "ON CONFLICT(cache_key) DO UPDATE SET "
                    "    provider=excluded.provider, "
                    "    value=excluded.value, "
                    "    expires_at=excluded.expires_at",
                    (key, provider, json.dumps(value, default=str), time.time() + ttl))
        except Exception as e:
            logger.warning("_Store.set: %s", e)

    def clear(self, provider=None):
        try:
            with sqlite3.connect(self.db) as c:
                if provider:
                    c.execute("DELETE FROM api_cache WHERE provider=?", (provider,))
                else:
                    c.execute("DELETE FROM api_cache")
        except Exception as e:
            logger.warning("_Store.clear: %s", e)

    # ── log ────────────────────────────────────────────────────────────────

    def log(self, provider, operation, status, duration_ms=0, error=""):
        try:
            with sqlite3.connect(self.db) as c:
                c.execute(
                    "INSERT INTO api_logs (provider, operation, status, duration_ms, error) "
                    "VALUES (?,?,?,?,?)",
                    (provider, operation, status, int(duration_ms), str(error)[:500]))
        except Exception as e:
            logger.warning("_Store.log: %s", e)

    def get_logs(self, provider=None, limit=200):
        try:
            with sqlite3.connect(self.db) as c:
                if provider:
                    rows = c.execute(
                        "SELECT provider,operation,status,duration_ms,error,created_at "
                        "FROM api_logs WHERE provider=? ORDER BY id DESC LIMIT ?",
                        (provider, limit)).fetchall()
                else:
                    rows = c.execute(
                        "SELECT provider,operation,status,duration_ms,error,created_at "
                        "FROM api_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [{"provider": r[0], "operation": r[1], "status": r[2],
                     "duration_ms": r[3], "error": r[4], "created_at": r[5]} for r in rows]
        except Exception:
            return []

    def stats(self):
        """Return success/failure counts per provider (last 24 h)."""
        try:
            with sqlite3.connect(self.db) as c:
                rows = c.execute(
                    "SELECT provider, status, COUNT(*) FROM api_logs "
                    "WHERE created_at >= datetime('now','-24 hours') "
                    "GROUP BY provider, status").fetchall()
            result = {}
            for prov, status, cnt in rows:
                result.setdefault(prov, {"ok": 0, "error": 0})
                result[prov][status if status in ("ok", "error") else "other"] = (
                    result[prov].get(status if status in ("ok","error") else "other", 0) + cnt)
            return result
        except Exception:
            return {}


# ── AI Client ─────────────────────────────────────────────────────────────────

class _AIClient:
    """
    Single entry point for all AI chat.
    Fallback chain: Claude → OpenRouter → GitHub Models → Ollama → rule-based
    (github moved ahead of ollama 2026-07-19 -- see the comment in `chat`.)
    """

    def __init__(self, store: _Store):
        self._s = store
        self._load()

    def _load(self):
        self.anthropic_key    = os.environ.get("ANTHROPIC_API_KEY", "")
        self.openrouter_key   = os.environ.get("OPENROUTER_API_KEY", "")
        # A LIST, NOT A MODEL. The old default was `meta-llama/llama-3.1-8b-instruct:free`,
        # which OpenRouter RETIRED -- so every call 404'd, the chain fell through Ollama (not
        # running on Render) and GitHub Models (not configured) to `rule_based`, and every AI
        # feature in the app quietly stopped working. The enterprise document writer returns
        # None on a rule_based provider, so it wrote nothing and asked the operator a question
        # instead: the owner's "it's not writing, it's asking me questions" (2026-07-13).
        #
        # It failed SILENTLY -- the exception is caught, and /api/health/ai still says
        # "configured" because a key is set. A single hardcoded model id is a dependency on a
        # third party's deprecation schedule, so the fix is not a newer id: it is a list. One
        # retirement now costs a fallback, not the feature.
        #
        # ZERO-COST RULE (CLAUDE.md): every candidate must end in `:free`. Enforced in
        # `openrouter_models` below, not merely by convention here.
        self.openrouter_models = self._free_models()
        # Kept because the ledger, the stats store and /api/health/ai all name a single model.
        # It is the one we TRY FIRST, which is the honest answer to "which model is this app
        # using" when every call starts there.
        self.openrouter_model = self.openrouter_models[0] if self.openrouter_models else ""
        self.ollama_url       = os.environ.get("OLLAMA_URL", "")
        self.ollama_model     = os.environ.get("OLLAMA_MODEL", "mistral")
        self.github_token     = os.environ.get("GITHUB_TOKEN", "")
        self.github_model     = os.environ.get("GITHUB_MODEL", "openai/gpt-4.1-mini")
        # GitHub Models has TWO endpoints and they disagree about model NAMING:
        #   models.github.ai/inference      -> wants the PUBLISHER PREFIX ("openai/gpt-4.1-mini")
        #   models.inference.ai.azure.com   -> wants the BARE name  ("gpt-4.1-mini")
        # Until 2026-07-19 the default was the azure URL paired with the PREFIXED model, which is
        # the one combination that cannot work: measured live, it returns
        #   HTTP 400 {"code":"unknown_model","message":"Unknown model: openai/gpt-4.1-mini"}
        # on EVERY call. So this provider has never answered once in its life -- the broad
        # `except` in _github swallowed the 400 into a log line nobody reads, and /api/health/ai
        # only ever reported whether the TOKEN was present, never whether the provider WORKS.
        # Same failure shape as the 2026-07-14 "agent was dead" bug: configured != working.
        self.github_url = self._safe_github_url(os.environ.get("GITHUB_MODELS_URL", ""))

    # Free models on OpenRouter, verified live against https://openrouter.ai/api/v1/models on
    # 2026-07-14, best prose first. These write governance-document sections, so the order is
    # by quality of ordinary English, not by speed. The tail is small and fast: if the big
    # ones are rate-limited (free tiers are), a short section still gets written.
    # ORDER CHANGED 2026-07-18 after measuring all five against the live key. Four returned
    # 429 and only nemotron answered -- and it was FOURTH, so every section paid three failed
    # round trips before reaching the one model that worked. On a ten-section report that is
    # thirty wasted requests, and on a free tier the failures plausibly count against the
    # allowance too, so the old order was spending quota to discover the same thing each time.
    #
    # This order is a STARTING GUESS, not a fact. Free-tier availability rotates: today's
    # winner is tomorrow's 429. `_ordered_models` below promotes whichever model actually
    # answered last, so the chain corrects itself rather than waiting for someone to re-measure
    # and edit this tuple.
    # RE-VERIFIED LIVE 2026-07-19 against https://openrouter.ai/api/v1/models.
    # THREE OF THE FIVE IDS BELOW HAD BEEN RETIRED and every call to them 404s:
    #   meta-llama/llama-3.3-70b-instruct:free
    #   qwen/qwen3-next-80b-a3b-instruct:free
    #   meta-llama/llama-3.2-3b-instruct:free
    # So the primary provider was spending most of its attempts on models that no longer
    # exist -- on top of the 50/day account ceiling. `tests/test_openrouter_free_models.py`
    # is the canary that caught it; it queries the live catalogue, so it will go red again
    # the next time this list rots. When it does, REPLACE THE IDS -- do not skip the test.
    OPENROUTER_FREE_FALLBACKS = (
        "nvidia/nemotron-3-super-120b-a12b:free",   # the one proven to answer, 2026-07-18
        "nvidia/nemotron-3-ultra-550b-a55b:free",   # largest available; best prose when free
        "google/gemma-4-31b-it:free",               # survived the 07-19 cull
        "google/gemma-4-26b-a4b-it:free",
        "openai/gpt-oss-20b:free",                  # small and fast: a short section still lands
    )

    # The model that most recently ANSWERED, promoted to the front of the next attempt.
    #
    # Deliberately process-global, and unlike `last_failure_reason` that is the right choice
    # here: this is a performance hint about a THIRD PARTY's availability, not per-request
    # data. Every worker faces the same rate limits, so sharing the observation is the point,
    # and being wrong costs exactly one extra attempt that would have happened anyway. There is
    # no cross-request information disclosure of the kind that made the failure reason a
    # ContextVar.
    _last_good_model = ""

    @staticmethod
    def _free_models():
        """The OpenRouter models to try, in order. Free ones only.

        Input:  env OPENROUTER_MODEL (one id) and/or OPENROUTER_MODELS (comma-separated).
        Output: a de-duplicated list of `:free` model ids, the operator's choices first.

        THE `:free` FILTER IS A COST CONTROL, NOT A NAMING CONVENTION (CLAUDE.md zero-cost
        rule). An operator who set OPENROUTER_MODEL to a PAID id would otherwise start
        billing the project silently, one document at a time. A paid id is dropped here and
        the chain carries on with the free fallbacks -- refusing to spend money is never a
        reason to take the feature down.
        """
        raw = []
        for var in ("OPENROUTER_MODEL", "OPENROUTER_MODELS"):
            raw += [m.strip() for m in os.environ.get(var, "").split(",") if m.strip()]
        raw += list(_AIClient.OPENROUTER_FREE_FALLBACKS)

        out = []
        for m in raw:
            if not m.endswith(":free"):
                logger.warning("openrouter: ignoring non-free model %r (zero-cost rule)", m)
                continue
            if m not in out:
                out.append(m)
        return out

    def _ordered_models(self):
        """The models to try, best-known-first.

        Input:  none (reads self.openrouter_models and the last-good hint).
        Output: the same models, with whichever one last ANSWERED moved to the front.

        WHY THIS EXISTS: on 2026-07-18 four of five free models were rate-limited and the one
        that worked sat fourth, so every section burned three failures to rediscover the same
        fact. A static order can only ever encode the day it was written; free-tier
        availability rotates. Promoting the last success means the chain costs one wasted
        attempt after a rotation instead of three on every single call.

        No model is ever DROPPED -- a rate limit is temporary, and a model that 429s now is a
        model that may be the only one answering in an hour.
        """
        models = list(self.openrouter_models)
        good = _AIClient._last_good_model
        if good and good in models:
            models.remove(good)
            models.insert(0, good)
        return models

    def reload(self):
        self._load()

    def chat(self, messages, system="", model=None, max_tokens=800, cache_ttl=0,
             user_id=None, is_admin=False, endpoint="", deadline=None):
        """
        Send AI chat. Returns (reply: str, provider: str).
        provider is 'claude', 'openrouter', 'ollama', 'github_models', 'rule_based',
        'cache', or 'capped'.

        Cap gates (supervisor-approved 2026-06-10):
          - Pre-flight check_caps. Blocked => return ('capped', reason) tuple; no upstream call.
          - Post-call record_usage with estimated tokens + USD cost.
          - Admin bypass: is_admin=True skips gate (call still ledger-recorded).
          - Anonymous user_id=None: per-user cap skipped, org spend cap still enforced.
        """
        # Reset per call: a stale reason from a previous request would be reported against this
        # one, which is worse than no reason at all -- it would send the operator to fix a
        # problem that is already over.
        self.last_failure_reason = ""

        allowed, cap_reason = ai_budget.check_caps(user_id=user_id, is_admin=is_admin)
        if not allowed:
            # The app's OWN budget stopped this, not the provider. Codex (2026-07-18) rated an
            # exhausted internal cap a BETTER permanent-failure candidate than a daily provider
            # quota, because a daily quota resets and this does not. It must never be reported
            # as a provider fault -- the fix is config here, not a key or a model.
            self.last_failure_reason = "capped:" + str(cap_reason or "")[:80]
            _prompt_text = (system or "") + "\n".join(
                m.get("content", "") for m in (messages or []))
            ai_budget.record_usage(
                user_id=user_id, provider="capped", model="",
                prompt_tokens=ai_budget.estimate_tokens(_prompt_text),
                completion_tokens=0, endpoint=endpoint, blocked=True,
                error=cap_reason)
            return ai_budget.capped_response(cap_reason)

        ckey = None
        if cache_ttl > 0:
            ckey = _Store._key("ai", messages, system, model or "", max_tokens)
            cached = self._s.get(ckey)
            if cached:
                return cached["reply"], "cache"

        reply, provider = (
            self._claude(messages, system, model, max_tokens)
            or self._openrouter(messages, system, max_tokens, deadline)
            # github BEFORE ollama since 2026-07-19. Ollama is a tunnel to the owner's own box:
            # when that tunnel is stale the URL still resolves, so the socket hangs for the full
            # 60s timeout before we fall through -- per call. GitHub Models is a hosted endpoint
            # on a 30s timeout with its own free allowance, so it is both likelier to answer and
            # cheaper to be wrong about. Ollama stays last: it is the only provider that keeps
            # working with no internet at all, which is exactly what a last resort is for.
            or self._github(messages, system, max_tokens)
            or self._ollama(messages, system, max_tokens)
            or ("I'm having trouble connecting to AI services right now. Please try again in a moment.", "rule_based")
        )

        # Every provider failed and the chain produced the canned string. If nothing along the
        # way named a reason, say so honestly rather than inventing one.
        if provider == "rule_based" and not self.last_failure_reason:
            self.last_failure_reason = self.AI_FAIL_ERROR

        if ckey and provider not in ("rule_based",):
            self._s.set(ckey, {"reply": reply, "provider": provider}, cache_ttl, "ai")

        # Ledger every upstream call. Skip rule_based (no upstream, no tokens).
        if provider != "rule_based":
            _model_used = (model or "claude-haiku-4-5-20251001") if provider == "claude" else {
                "openrouter":    self.openrouter_model,
                "ollama":        self.ollama_model,
                "github_models": self.github_model,
            }.get(provider, "")
            _prompt_text = (system or "") + "\n".join(
                m.get("content", "") for m in (messages or []))
            ai_budget.record_usage(
                user_id=user_id, provider=provider, model=_model_used,
                prompt_tokens=ai_budget.estimate_tokens(_prompt_text),
                completion_tokens=ai_budget.estimate_tokens(reply),
                endpoint=endpoint)

        return reply, provider

    def _claude(self, messages, system, model, max_tokens):
        if not self.anthropic_key:
            return None
        t = time.time()
        try:
            import anthropic as _ant
            cl = _ant.Anthropic(api_key=self.anthropic_key)
            _m = model or "claude-haiku-4-5-20251001"
            # Try haiku first, opus as fallback
            for _model in (_m, "claude-opus-4-7") if _m == "claude-haiku-4-5-20251001" else (_m,):
                try:
                    resp = cl.messages.create(model=_model, max_tokens=max_tokens,
                                              system=system or "You are a helpful assistant.",
                                              messages=messages)
                    reply = resp.content[0].text if resp.content else None
                    if reply:
                        self._s.log("anthropic", _model, "ok", (time.time()-t)*1000)
                        return reply, "claude"
                except Exception as me:
                    # Enum, not the exception text: the same leak rule as _openrouter.
                    logger.warning("claude %s failed: %s", _model,
                                   self.classify_ai_failure(me))
            self._s.log("anthropic", _m, "error", (time.time()-t)*1000, "all models failed")
            return None
        except Exception as e:
            self._s.log("anthropic", model or "claude", "error", (time.time()-t)*1000,
                        self.classify_ai_failure(e))
            return None

    # The failure reason of the most recent AI attempt, as one of the AI_FAIL_* enums below.
    # Read by the enterprise document writer so an operator is told WHY the writer was
    # unavailable instead of being told only THAT it was. Reset at the start of every chat().
    #
    # BACKED BY A CONTEXTVAR, because `api.ai` is a SHARED SINGLETON. Codex (MEDIUM,
    # 2026-07-18): a plain instance attribute on a singleton is process-wide state, so a
    # concurrent request could overwrite this between another request's chat() returning and
    # its reason being read -- showing operator A the cause of operator B's failure. The
    # property below keeps the original `self.last_failure_reason` read/write syntax (every
    # call site and test double is unchanged) while storing per-context.
    _FAILURE_REASON: contextvars.ContextVar[str] = contextvars.ContextVar(
        "ai_last_failure_reason", default="")

    @property
    def last_failure_reason(self):
        return self._FAILURE_REASON.get()

    @last_failure_reason.setter
    def last_failure_reason(self, value):
        self._FAILURE_REASON.set(value or "")

    # Failure buckets. These are the whole vocabulary: an unrecognised failure is AI_FAIL_ERROR,
    # never a guess. Codex (HIGH, 2026-07-18): `model_deprecated` MUST be its own bucket -- two
    # of the five free fallbacks are marked "going away 2026-07-19", and a retired id returns
    # 404/400, which reads exactly like a bad key if the two are pooled. Pooling them is how a
    # retirement gets misdiagnosed as an auth problem and "fixed" by rotating a healthy key.
    AI_FAIL_AUTH        = "auth"             # 401/403 -- key missing, invalid, revoked
    AI_FAIL_RATE        = "rate_limited"     # 429 -- quota/free-tier cap
    AI_FAIL_DEPRECATED  = "model_deprecated" # 404 -- model id retired or unknown
    # 400 is SEPARATE from 404 and the distinction is the point. Codex (HIGH, 2026-07-18): a
    # 400 is most often OUR malformed payload -- a bad parameter, an unsupported field, a
    # request the provider validated and refused. Filing that under "model retired" sends the
    # operator to swap healthy model ids while the actual defect sits in our request body.
    AI_FAIL_BADREQUEST  = "bad_request"      # 400 -- the provider refused OUR request
    AI_FAIL_TIMEOUT     = "timeout"          # socket/deadline expiry
    AI_FAIL_EMPTY       = "empty_completion" # 200 with nothing usable in it
    AI_FAIL_BADRESPONSE = "bad_response"     # 200 whose JSON is not the shape we expect
    AI_FAIL_NETWORK     = "network"          # DNS/connection refused/TLS
    AI_FAIL_ERROR       = "error"            # genuinely unclassified

    @staticmethod
    def classify_ai_failure(exc):
        """Map a provider exception to one AI_FAIL_* enum.

        Input:  the exception raised while calling a provider.
        Output: a short stable enum string, safe to persist and to show an operator.

        THIS FUNCTION MUST NEVER RETURN PROVIDER TEXT. Codex (HIGH, 2026-07-18): the HTTP error
        BODY of a failed completion can echo request diagnostics and prompt fragments, and this
        repo leaked five live secrets into PUBLIC GitHub Actions logs for 35 days on 2026-07-10.
        So we read `HTTPError.code` -- an integer -- and never call `.read()` on it. The enum is
        the entire output; the body is not sampled, not truncated, not logged.
        """
        import urllib.error as _ue
        import socket as _sock

        if isinstance(exc, ValueError):
            # Raised by _openrouter itself for an empty completion; a JSON/shape failure
            # surfaces as KeyError/TypeError and is a different bucket.
            return _AIClient.AI_FAIL_EMPTY
        if isinstance(exc, (KeyError, IndexError, TypeError)):
            return _AIClient.AI_FAIL_BADRESPONSE
        if isinstance(exc, _sock.timeout) or isinstance(exc, TimeoutError):
            return _AIClient.AI_FAIL_TIMEOUT
        if isinstance(exc, _ue.HTTPError):
            code = getattr(exc, "code", 0)
            if code in (401, 403):
                return _AIClient.AI_FAIL_AUTH
            if code == 429:
                return _AIClient.AI_FAIL_RATE
            if code == 404:
                return _AIClient.AI_FAIL_DEPRECATED
            if code == 400:
                return _AIClient.AI_FAIL_BADREQUEST
            return _AIClient.AI_FAIL_ERROR
        if isinstance(exc, _ue.URLError):
            # URLError wraps socket errors; a timeout arrives here rather than bare.
            if isinstance(getattr(exc, "reason", None), (_sock.timeout, TimeoutError)):
                return _AIClient.AI_FAIL_TIMEOUT
            return _AIClient.AI_FAIL_NETWORK
        return _AIClient.AI_FAIL_ERROR

    def _openrouter(self, messages, system, max_tokens, deadline=None):
        """Try each free model in turn. One retirement must not take the chain down.

        A dead model id 404s, and a free model that is rate-limited 429s. Both are ordinary
        and both used to end the call -- the whole AI layer fell to `rule_based` because ONE
        id had been deprecated. So a per-model failure now costs the next model, and only an
        exhausted list returns None.

        `deadline` IS A HARD WALL-CLOCK CEILING (absolute time.time()), and it is not advice:
        it bounds the SOCKET TIMEOUT, not merely the loop. Codex, HIGH: with five fallbacks at
        30s each, one call could sit in here for 150 seconds -- past gunicorn's 120s timeout,
        on a single-instance free tier, hanging the whole app for every other user. A caller
        that must return in bounded time passes a deadline; without one the old per-model
        timeout stands, because a background job has no such constraint.

        `self.openrouter_model` is updated to whichever model actually ANSWERED, so the ledger
        and the stats page record the model that did the work rather than the one we hoped
        would.
        """
        if not self.openrouter_key or not self.openrouter_models:
            # No key configured at all is an auth problem, and it is the single most likely
            # cause of a PERMANENT outage on a fresh deploy -- an env var that was never set
            # looks identical, from the operator's chair, to one that is rejected. Name it.
            self.last_failure_reason = (self.AI_FAIL_AUTH if not self.openrouter_key
                                        else self.AI_FAIL_DEPRECATED)
            return None

        import urllib.request as _ur, json as _j
        msgs = ([{"role": "system", "content": system}] if system else []) + list(messages)
        last_error = None
        last_reason = ""

        for model in self._ordered_models():
            timeout = 30
            if deadline is not None:
                remaining = deadline - time.time()
                # Not enough time left to be worth opening a socket. Give up on the AI and
                # let the caller fall back -- returning late is worse than returning without.
                if remaining <= 1:
                    logger.warning("openrouter: out of time before %s; falling back", model)
                    break
                timeout = min(30, remaining)

            t = time.time()
            try:
                payload = _j.dumps({"model": model, "messages": msgs,
                                    "max_tokens": max_tokens}).encode()
                req = _ur.Request("https://openrouter.ai/api/v1/chat/completions", data=payload,
                                  headers={"Authorization": f"Bearer {self.openrouter_key}",
                                           "Content-Type": "application/json",
                                           "HTTP-Referer": "https://solarpro.aiappinvent.com",
                                           "X-Title": "SolarPro"})
                with _ur.urlopen(req, timeout=timeout) as r:
                    reply = _j.loads(r.read())["choices"][0]["message"]["content"]
                # An empty completion is a failure wearing a 200. Falling through to the next
                # model is right; returning "" would be reported to the caller as a success
                # and rendered into a document as an empty section.
                if not (reply or "").strip():
                    raise ValueError("empty completion")
                self._s.log("openrouter", model, "ok", (time.time() - t) * 1000)
                self.openrouter_model = model
                # Remember what worked so the NEXT call starts here instead of walking the
                # rate-limited models again.
                _AIClient._last_good_model = model
                return reply, "openrouter"
            except Exception as e:
                last_error = e
                # ENUM ONLY -- never `str(e)`, never the HTTP body. Codex (HIGH, 2026-07-18):
                # `str(e)` on an HTTPError, and the provider JSON behind it, can carry request
                # diagnostics and prompt fragments; api_logs is readable wherever the SQLite
                # file is, and this repo has a live-secret-leak history (2026-07-10). The enum
                # plus the model slug is everything a diagnosis needs and nothing an attacker
                # wants.
                reason = self.classify_ai_failure(e)
                last_reason = reason
                self._s.log("openrouter", model, "error", (time.time() - t) * 1000, reason)
                logger.warning("openrouter model %s failed: %s", model, reason)

        # The reason the LAST model gave is the one the operator is shown. With a homogeneous
        # failure (every model 429s, or the key is bad for all of them) that is the true cause;
        # with a mixed failure it is at least a real observed reason rather than a guess.
        self.last_failure_reason = last_reason or self.AI_FAIL_ERROR
        logger.warning("openrouter: every free model failed, last reason: %s",
                       self.last_failure_reason)
        return None

    def _ollama(self, messages, system, max_tokens):
        if not self.ollama_url:
            return None
        t = time.time()
        try:
            import urllib.request as _ur, json as _j
            msgs = ([{"role": "system", "content": system}] if system else []) + list(messages)
            payload = _j.dumps({"model": self.ollama_model, "messages": msgs,
                                 "stream": False}).encode()
            req = _ur.Request(f"{self.ollama_url}/api/chat", data=payload,
                              headers={"Content-Type": "application/json"})
            with _ur.urlopen(req, timeout=60) as r:
                reply = _j.loads(r.read())["message"]["content"].strip()
            self._s.log("ollama", self.ollama_model, "ok", (time.time()-t)*1000)
            return reply, "ollama"
        except Exception as e:
            self._s.log("ollama", self.ollama_model, "error", (time.time()-t)*1000,
                        self.classify_ai_failure(e))
            logger.warning("ollama failed: %s", e)
            return None

    # The only hosts the GitHub Models bearer token may ever be sent to.
    GITHUB_MODELS_HOSTS = ("models.github.ai", "models.inference.ai.azure.com")
    GITHUB_MODELS_DEFAULT_URL = "https://models.github.ai/inference/chat/completions"

    @classmethod
    def _safe_github_url(cls, url):
        """Resolve GITHUB_MODELS_URL, refusing to send the token anywhere unexpected.

        Input:  the raw env value (may be empty, malformed, or hostile)
        Output: that URL if it is HTTPS on a known GitHub Models host, else the default.

        WHY THIS IS NOT JUST `os.environ.get(...)`: the endpoint used to be a hard-coded
        string. Making it configurable is what the bug fix needed, but it also means a typo'd
        -- or tampered -- env var would send `Authorization: Bearer <GITHUB_TOKEN>` to a host
        of someone else's choosing, on every AI call, silently. This repo leaked five live
        secrets into PUBLIC logs for 35 days in July 2026; a config knob that can exfiltrate a
        credential is not one to ship unguarded.

        Falls back rather than raising: an operator typo must not take the AI chain down, and
        the default is always a working endpoint. `http://` is refused even on a valid host --
        the token must never cross the wire in clear text.
        """
        from urllib.parse import urlparse
        try:
            p = urlparse((url or "").strip())
        except Exception:
            return cls.GITHUB_MODELS_DEFAULT_URL
        host = (p.hostname or "").lower()
        if p.scheme == "https" and host in cls.GITHUB_MODELS_HOSTS:
            return url.strip()
        if url and url.strip():
            logger.warning(
                "GITHUB_MODELS_URL %r is not an https URL on a known GitHub Models host; "
                "using the default endpoint instead", url)
        return cls.GITHUB_MODELS_DEFAULT_URL

    @staticmethod
    def _github_model_for(url, model):
        """Match the model id to the endpoint's naming convention.

        Input:  url   -- the GitHub Models chat-completions URL actually being called
                model -- the configured model id, with or without a publisher prefix
        Output: the same model, prefixed or bare, as THAT endpoint requires.

        WHY: the two endpoints reject each other's naming with HTTP 400 unknown_model. Making
        this derived rather than configured means an operator cannot set GITHUB_MODEL and
        GITHUB_MODELS_URL to a pair that cannot work -- which is precisely the state this app
        shipped in until 2026-07-19.
        """
        # Hostname-exact, lowercased -- not a substring scan of the whole URL. A URL that
        # merely differed in case (Models.Inference.AI.Azure.com) would otherwise be read as
        # the modern endpoint and sent a prefixed model, recreating the very 400 this fixes.
        # (Codex LOW, 2026-07-19.)
        from urllib.parse import urlparse
        host = (urlparse(url or "").hostname or "").lower()
        if host == "models.inference.ai.azure.com":
            # `or model` guards a trailing-slash config ("openai/"): splitting that yields an
            # empty string, and an empty model id is a 400 that reads like an outage rather
            # than the typo it is.
            return (model.split("/", 1)[1] or model) if "/" in model else model
        if "/" in model:
            return model
        # Only OpenAI's own families get an assumed publisher. GitHub Models also hosts Phi,
        # Mistral, Llama and others, and "Phi-4" -> "openai/Phi-4" would be a confident lie
        # about who publishes it. Anything unrecognised is passed through UNCHANGED rather
        # than guessed at or rejected: a bare name may be wrong, but the endpoint says so in
        # one 400 that `_github` already logs and classifies, whereas raising here would turn
        # a config typo into a crash in a provider whose whole job is to degrade quietly.
        # (Codex MEDIUM, 2026-07-19.)
        return f"openai/{model}" if model.startswith(("gpt-", "o1", "o3", "o4")) else model

    def _github(self, messages, system, max_tokens):
        if not self.github_token:
            return None
        t = time.time()
        # Resolved BEFORE the try so the failure path can always name the model that was
        # actually sent. Computed inside, it would be unbound whenever the failure happened
        # earlier than its own assignment -- turning a handled provider error into a NameError
        # inside the handler. Same trap `_ai_write_many` documents for its `_api` import.
        _model = self._github_model_for(self.github_url, self.github_model)
        try:
            import urllib.request as _ur, json as _j
            msgs = ([{"role": "system", "content": system}] if system else []) + list(messages)
            payload = _j.dumps({"model": _model, "messages": msgs,
                                 "max_tokens": max_tokens, "temperature": 0.7}).encode()
            req = _ur.Request(self.github_url,
                              data=payload,
                              headers={"Authorization": f"Bearer {self.github_token}",
                                       "Content-Type": "application/json",
                                       "Accept": "application/json",
                                       "User-Agent": "solarpro/1.0"})
            with _ur.urlopen(req, timeout=30) as r:
                reply = _j.loads(r.read())["choices"][0]["message"]["content"]
            # Log the model actually SENT, not the one configured. They differ on the legacy
            # endpoint, and a stats page naming a model that never went over the wire sends
            # whoever debugs the next model-specific failure to the wrong place.
            self._s.log("github_models", _model, "ok", (time.time()-t)*1000)
            return reply, "github_models"
        except Exception as e:
            self._s.log("github_models", _model, "error", (time.time()-t)*1000,
                        self.classify_ai_failure(e))
            logger.warning("github_models failed: %s", e)
            return None


# ── Email Client ──────────────────────────────────────────────────────────────

class _EmailClient:
    """Resend → SMTP fallback. Single send() method."""

    def __init__(self, store: _Store):
        self._s = store
        self._load()

    def _load(self):
        # Phase 1 refactor: secret fields (RESEND/SMTP/BREVO/AXIGEN keys) are
        # served by @property methods that call the broker on each access.
        # _load() now only seeds the non-secret display-address fields, which
        # remain eager because they aren't sensitive and don't rotate.
        def _env(name, default=""):
            return os.environ.get(name, default).lstrip("﻿").strip()
        self.addr_sales    = _env("EMAIL_SALES",    "sales@aiappinvent.com")
        self.addr_support  = _env("EMAIL_SUPPORT",  "support@aiappinvent.com")
        self.addr_billing  = _env("EMAIL_BILLING",  "billing@aiappinvent.com")
        self.addr_hello    = _env("EMAIL_HELLO",    "sales@aiappinvent.com")
        self.addr_proposals= _env("EMAIL_PROPOSALS","sales@aiappinvent.com")

    def _ordered_models(self):
        """The models to try, best-known-first.

        Input:  none (reads self.openrouter_models and the last-good hint).
        Output: the same models, with whichever one last ANSWERED moved to the front.

        WHY THIS EXISTS: on 2026-07-18 four of five free models were rate-limited and the one
        that worked sat fourth, so every section burned three failures to rediscover the same
        fact. A static order can only ever encode the day it was written; free-tier
        availability rotates. Promoting the last success means the chain costs one wasted
        attempt after a rotation instead of three on every single call.

        No model is ever DROPPED -- a rate limit is temporary, and a model that 429s now is a
        model that may be the only one answering in an hour.
        """
        models = list(self.openrouter_models)
        good = _AIClient._last_good_model
        if good and good in models:
            models.remove(good)
            models.insert(0, good)
        return models

    def reload(self):
        self._load()

    # ── Phase 1 lazy properties — every read goes through secrets_broker ────
    # Returns "" (or sensible default) when Vault is unreachable AND no env
    # warm-up is available. Matches prior eager-load "" semantics, so the
    # if-key-present provider guards keep working.

    @property
    def resend_key(self) -> str:
        return _secret_field("email/resend", "api_key", "")

    @property
    def brevo_key(self) -> str:
        return _secret_field("email/brevo", "api_key", "")

    @property
    def smtp_host(self) -> str:
        return _secret_field("email/smtp", "host", "")

    @property
    def smtp_port(self) -> int:
        raw = _secret_field("email/smtp", "port", "465")
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 465

    @property
    def smtp_user(self) -> str:
        return _secret_field("email/smtp", "user", "")

    @property
    def smtp_pass(self) -> str:
        return _secret_field("email/smtp", "pass", "")

    @property
    def smtp_from(self) -> str:
        return _secret_field("email/smtp", "from", "support@aiappinvent.com")

    @property
    def smtp_tls(self) -> bool:
        raw = _secret_field("email/smtp", "tls", "false")
        return raw.lower() in ("1", "true", "yes")

    # Axigen is not in _ENV_MAP / _TIER yet — Phase 2 deliverable. For now,
    # fall through to direct env reads so the configured (unconfigured) state
    # matches pre-broker behaviour exactly. When Phase 2 adds it to _TIER,
    # flip these to _secret_field("email/axigen", ...).
    @property
    def axigen_url(self) -> str:
        return os.environ.get("AXIGEN_SERVER_URL", "").lstrip("﻿").strip()

    @property
    def axigen_user(self) -> str:
        return os.environ.get("AXIGEN_USER", "").lstrip("﻿").strip()

    @property
    def axigen_pass(self) -> str:
        return os.environ.get("AXIGEN_PASSWORD", "").lstrip("﻿").strip()

    def _send_brevo(self, _from, _to, subject, html_body, text_body, attachments=None):
        """
        Send an email through Brevo's transactional API (api.brevo.com/v3/smtp/email).

        Why Brevo:
          - Free tier: 300 emails/day forever (no card)
          - HTTPS API, works through Render/Railway free-tier SMTP block
          - Accepts custom sender once you verify the address in Brevo dashboard

        Inputs:
          _from         sender email string. MUST be verified in Brevo dashboard or
                        covered by a verified-domain SPF/DKIM. Otherwise Brevo
                        returns 400 with code "missing_credentials".
          _to           list of recipient email strings
          subject       email subject text
          html_body     HTML body string
          text_body     plain-text body string or None
          attachments   optional list of (filename, bytes, mime) tuples; encoded
                        per Brevo's spec (base64 in JSON "attachment" array).

        Output:
          (True, "sent") on HTTP 200/201, else (False, "<error detail>")

        Syntax notes:
          - Brevo uses the `api-key` header (NOT Bearer auth)
          - sender + to are objects with {email, name} — name optional
          - JSON-decoded response on success contains "messageId"
        """
        import requests, base64
        if not self.brevo_key:
            return False, "brevo not configured"
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "api-key":      self.brevo_key,
            "Content-Type": "application/json",
            "Accept":       "application/json",
        }
        payload = {
            "sender":      {"email": _from},
            "to":          [{"email": addr} for addr in _to],
            "subject":     subject,
            "htmlContent": html_body,
        }
        if text_body:
            payload["textContent"] = text_body
        if attachments:
            payload["attachment"] = [
                {"name": fname,
                 "content": base64.b64encode(data).decode("ascii")}
                for (fname, data, _mime) in attachments
            ]
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=15)
            if r.status_code in (200, 201, 202):
                return True, "sent"
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return False, str(e)

    def _send_axigen(self, _from, _to, subject, html_body, text_body, attachments=None):
        """
        Send an email through Axigen's Mailbox REST API.

        Inputs:
          _from         sender address string (must be a mailbox on the Axigen server)
          _to           list of recipient address strings
          subject       email subject text
          html_body     HTML body string
          text_body     plain-text body string or None
          attachments   optional list of (filename, bytes, mime) tuples; encoded
                        per Axigen's spec (base64 in JSON "attachments" array).
        Output:
          (True, "sent") on HTTP 200/201, else (False, "<error detail>")
        Syntax notes:
          - requests.post(..., auth=(u,p)) sends an HTTP Basic Authorization header
          - timeout=15 prevents hanging if Axigen server is unreachable
          - We POST to {AXIGEN_SERVER_URL}/mails/send per Axigen Mailbox REST API
        """
        import requests, base64
        if not (self.axigen_url and self.axigen_user and self.axigen_pass):
            return False, "axigen not configured"
        url = self.axigen_url.rstrip("/") + "/mails/send"
        # Axigen accepts a JSON body with from/to/subject/bodyText/bodyHtml
        # (mirrors the field schema documented on axigen.com)
        payload = {
            "from":     _from,
            "to":       ", ".join(_to),
            "subject":  subject,
            "bodyHtml": html_body,
        }
        if text_body:
            payload["bodyText"] = text_body
        if attachments:
            payload["attachments"] = [
                {"fileName": fname,
                 "contentType": (mime or "application/octet-stream"),
                 "content": base64.b64encode(data).decode("ascii")}
                for (fname, data, mime) in attachments
            ]
        try:
            r = requests.post(url, json=payload,
                              auth=(self.axigen_user, self.axigen_pass),
                              timeout=15)
            if r.status_code in (200, 201, 202):
                return True, "sent"
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return False, str(e)

    def send(self, to_addr, subject, html_body, text_body=None, from_addr=None,
             resend_key_override=None, attachments=None):
        """
        Send an email. Returns (ok: bool, message: str).

        Order tried: Axigen (HTTPS, primary) -> Resend (HTTPS) -> SMTP (blocked on Render free tier).
        The first provider that accepts the message wins; we never double-send.

        Inputs:
          to_addr               string or list of recipient addresses
          subject               subject line
          html_body             HTML content
          text_body             optional plain-text fallback
          from_addr             optional override for sender
          resend_key_override   optional Resend key for one-off testing
          attachments           optional list of (filename, bytes, mime) tuples
                                attached on every provider; mime defaults to
                                application/octet-stream if blank
        Output:
          (True, "sent") if any provider accepts, else (False, "<combined error>")
        Syntax notes:
          - time.time() captures ms latency we log into the api_call_log table
          - isinstance(..., str) detects single-recipient form and wraps it as a list
        """
        _from = from_addr or self.addr_support or self.smtp_from
        _to   = [to_addr] if isinstance(to_addr, str) else list(to_addr)
        _key  = resend_key_override or self.resend_key
        t     = time.time()

        # 1) Brevo primary — free 300/day HTTPS API, only runs if BREVO_API_KEY set.
        if self.brevo_key:
            ok, msg = self._send_brevo(_from, _to, subject, html_body, text_body, attachments)
            if ok:
                self._s.log("brevo", "send", "ok", (time.time()-t)*1000)
                return True, "sent"
            self._s.log("brevo", "send", "error", (time.time()-t)*1000, msg)
            logger.warning("brevo failed: %s", msg)

        # 2) Axigen — only attempts the call if AXIGEN_SERVER_URL is set,
        #    so absence of config silently falls through to next provider.
        if self.axigen_url:
            ok, msg = self._send_axigen(_from, _to, subject, html_body, text_body, attachments)
            if ok:
                self._s.log("axigen", "send", "ok", (time.time()-t)*1000)
                return True, "sent"
            self._s.log("axigen", "send", "error", (time.time()-t)*1000, msg)
            logger.warning("axigen failed: %s", msg)

        # 3) Resend fallback — uses the Resend Python SDK over HTTPS
        if _key:
            try:
                import resend as _r, base64
                _r.api_key = _key
                params = {"from": _from, "to": _to, "subject": subject, "html": html_body}
                if text_body:
                    params["text"] = text_body
                if attachments:
                    params["attachments"] = [
                        {"filename": fname,
                         "content": base64.b64encode(data).decode("ascii")}
                        for (fname, data, _mime) in attachments
                    ]
                _r.Emails.send(params)
                self._s.log("resend", "send", "ok", (time.time()-t)*1000)
                return True, "sent"
            except Exception as e:
                self._s.log("resend", "send", "error", (time.time()-t)*1000, str(e))
                logger.warning("resend failed: %s", e)

        # 4) SMTP last resort — blocked by both Render and Railway free tiers,
        #    but works locally and on any paid-tier host or self-host VPS.
        if not self.smtp_host or not self.smtp_user:
            return False, "Email not configured — set BREVO_API_KEY, AXIGEN_SERVER_URL+USER+PASSWORD, RESEND_API_KEY, or SMTP credentials."

        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText as _MT
            from email.mime.application import MIMEApplication
            # mixed wraps the alternative body + binary parts (PDF attachments).
            # alternative-only was the old shape and silently dropped files.
            outer = MIMEMultipart("mixed")
            outer["From"]    = _from
            outer["To"]      = ", ".join(_to)
            outer["Subject"] = subject
            alt = MIMEMultipart("alternative")
            if text_body:
                alt.attach(_MT(text_body, "plain"))
            alt.attach(_MT(html_body, "html"))
            outer.attach(alt)
            for (fname, data, mime) in (attachments or []):
                _sub = (mime.split("/", 1)[1] if (mime and "/" in mime) else "octet-stream")
                part = MIMEApplication(data, _subtype=_sub)
                part.add_header("Content-Disposition", "attachment", filename=fname)
                outer.attach(part)
            if self.smtp_tls:
                srv = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)
                srv.ehlo()
                srv.starttls()
            else:
                srv = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15)
            srv.login(self.smtp_user, self.smtp_pass)
            srv.sendmail(_from, _to, outer.as_string())
            srv.quit()
            self._s.log("smtp", "send", "ok", (time.time()-t)*1000)
            return True, "sent"
        except Exception as e:
            self._s.log("smtp", "send", "error", (time.time()-t)*1000, str(e))
            logger.warning("smtp failed: %s", e)
            return False, str(e)


# ── Payment Client ────────────────────────────────────────────────────────────

class _PaymentClient:
    """Paystack initialize + verify. Keys from env. Verify results cached."""

    def __init__(self, store: _Store):
        self._s = store
        self._load()

    def _load(self):
        self.secret_key = os.environ.get("PAYSTACK_SECRET_KEY", "")
        self.public_key = os.environ.get("PAYSTACK_PUBLIC_KEY", "")

    def _ordered_models(self):
        """The models to try, best-known-first.

        Input:  none (reads self.openrouter_models and the last-good hint).
        Output: the same models, with whichever one last ANSWERED moved to the front.

        WHY THIS EXISTS: on 2026-07-18 four of five free models were rate-limited and the one
        that worked sat fourth, so every section burned three failures to rediscover the same
        fact. A static order can only ever encode the day it was written; free-tier
        availability rotates. Promoting the last success means the chain costs one wasted
        attempt after a rotation instead of three on every single call.

        No model is ever DROPPED -- a rate limit is temporary, and a model that 429s now is a
        model that may be the only one answering in an hour.
        """
        models = list(self.openrouter_models)
        good = _AIClient._last_good_model
        if good and good in models:
            models.remove(good)
            models.insert(0, good)
        return models

    def reload(self):
        self._load()

    def initialize(self, email, amount_kobo, callback_url, metadata=None):
        """Returns (ok: bool, data: dict). data['authorization_url'] on success."""
        if not self.secret_key:
            return False, {"message": "Paystack not configured"}
        t = time.time()
        try:
            import urllib.request as _ur, json as _j
            payload = _j.dumps({
                "email": email, "amount": int(amount_kobo),
                "callback_url": callback_url,
                "metadata": metadata or {},
            }).encode()
            req = _ur.Request("https://api.paystack.co/transaction/initialize",
                              data=payload,
                              headers={"Authorization": f"Bearer {self.secret_key}",
                                       "Content-Type": "application/json"})
            with _ur.urlopen(req, timeout=30) as r:
                data = _j.loads(r.read())
            ok = bool(data.get("status"))
            self._s.log("paystack", "initialize", "ok" if ok else "error",
                        (time.time()-t)*1000)
            return ok, data.get("data", {})
        except Exception as e:
            self._s.log("paystack", "initialize", "error", (time.time()-t)*1000, str(e))
            logger.warning("paystack initialize failed: %s", e)
            return False, {"message": str(e)}

    def verify(self, reference):
        """Returns (ok: bool, data: dict). Successful verifications cached 24 h (idempotent)."""
        if not self.secret_key:
            return False, {"message": "Paystack not configured"}
        ckey = f"paystack_verify:{reference}"
        cached = self._s.get(ckey)
        if cached:
            return cached["ok"], cached["data"]
        t = time.time()
        try:
            import urllib.request as _ur, json as _j
            req = _ur.Request(f"https://api.paystack.co/transaction/verify/{reference}",
                              headers={"Authorization": f"Bearer {self.secret_key}"})
            with _ur.urlopen(req, timeout=30) as r:
                data = _j.loads(r.read())
            txn = data.get("data", {})
            ok  = bool(data.get("status")) and txn.get("status") == "success"
            self._s.log("paystack", "verify", "ok" if ok else "error", (time.time()-t)*1000)
            if ok:
                self._s.set(ckey, {"ok": ok, "data": txn}, 86400, "paystack")
            return ok, txn
        except Exception as e:
            self._s.log("paystack", "verify", "error", (time.time()-t)*1000, str(e))
            logger.warning("paystack verify failed: %s", e)
            return False, {"message": str(e)}


# ── Search Client ─────────────────────────────────────────────────────────────

class _SearchClient:
    """Multi-source web search with 6-hour cache. Returns stale cache on failure.

    Primary backend: Google News RSS (no API key, real journalism, current
    procurement signal, far more reliable than scraping HTML SERPs).
    Fallback: DuckDuckGo HTML via ddgs. DDG has been heavily rate-limiting
    scrapers so we only reach for it when Google News is empty.

    Return shape (stable contract): list of {title, url, body} dicts.
    """

    TTL = 21600  # 6 hours

    # Google News blocks scraper UAs with an empty 200. Must look like a browser.
    _BROWSER_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )

    def __init__(self, store: _Store):
        self._s = store

    # ─── Google News RSS backend ────────────────────────────────────────────
    def _gnews(self, q, max_results):
        """Hit news.google.com RSS for a query. Returns up to max_results dicts.
        Google News doesn't honour `site:` filters reliably -- it indexes news
        articles ABOUT a site rather than searching it, which is usually what
        we want for procurement prospecting anyway."""
        import urllib.parse, urllib.request
        import xml.etree.ElementTree as _ET, re as _re
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote_plus(q)
            + "&hl=en-US&gl=US&ceid=US:en"
        )
        req = urllib.request.Request(url, headers={
            "User-Agent": self._BROWSER_UA,
            "Accept": "application/rss+xml,application/xml,text/xml",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
        root = _ET.fromstring(body)
        channel = root.find("channel") or root
        out = []
        for it in channel.findall("item"):
            raw_title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            desc = _re.sub(r"<[^>]+>", " ", it.findtext("description") or "")
            desc = _re.sub(r"\s+", " ", desc).strip()
            # Strip the " - Publisher" suffix that news.google appends.
            title = raw_title.rsplit(" - ", 1)[0] if " - " in raw_title else raw_title
            out.append({"title": title, "url": link, "body": desc[:600]})
            if len(out) >= max_results:
                break
        return out

    # ─── DDG fallback ───────────────────────────────────────────────────────
    def _ddg(self, q, max_results, region):
        from ddgs import DDGS
        results = []
        with DDGS() as d:
            for r in d.text(q, region=region, max_results=max_results):
                results.append({"title": r.get("title",""),
                                "url":   r.get("href",""),
                                "body":  r.get("body","")})
        return results

    def query(self, q, max_results=10, region="wt-wt"):
        """Returns list of {title, url, body} dicts. Never raises."""
        ckey = _Store._key("search", q, max_results, region)
        cached = self._s.get(ckey)
        if cached is not None:
            return cached
        # ── Try Google News first ──
        t = time.time()
        try:
            results = self._gnews(q, max_results)
            self._s.log("gnews", "search", "ok", (time.time()-t)*1000)
            if results:
                self._s.set(ckey, results, self.TTL, "gnews")
                return results
        except Exception as e:
            self._s.log("gnews", "search", "error", (time.time()-t)*1000, str(e))
            logger.warning("google news search failed: %s", e)
        # ── DDG fallback ──
        t = time.time()
        try:
            results = self._ddg(q, max_results, region)
            self._s.log("ddgs", "search", "ok", (time.time()-t)*1000)
            if results:
                self._s.set(ckey, results, self.TTL, "ddgs")
            return results
        except Exception as e:
            self._s.log("ddgs", "search", "error", (time.time()-t)*1000, str(e))
            logger.warning("ddgs failed: %s", e)
            stale = self._s.get_stale(ckey)
            return stale if stale is not None else []


# ── GitHub Client ─────────────────────────────────────────────────────────────

class _GitHubClient:
    """Public GitHub API (commits etc.) with 5-minute cache."""

    REPO    = "marc667us/solar-pv-designer-lite"
    TTL     = 300

    def __init__(self, store: _Store):
        self._s = store

    def recent_commits(self, n=10):
        """Return list of recent commit message strings. Never raises."""
        ckey = f"github:commits:{n}"
        cached = self._s.get(ckey)
        if cached is not None:
            return cached
        t = time.time()
        try:
            import urllib.request as _ur, json as _j
            req = _ur.Request(
                f"https://api.github.com/repos/{self.REPO}/commits?per_page={n}",
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "solarpro/1.0"})
            with _ur.urlopen(req, timeout=10) as r:
                commits = _j.loads(r.read())
            msgs = [c["commit"]["message"].split("\n")[0] for c in commits]
            self._s.log("github", "commits", "ok", (time.time()-t)*1000)
            self._s.set(ckey, msgs, self.TTL, "github")
            return msgs
        except Exception as e:
            self._s.log("github", "commits", "error", (time.time()-t)*1000, str(e))
            logger.warning("github commits failed: %s", e)
            return self._s.get_stale(ckey) or []


# ── Facade ────────────────────────────────────────────────────────────────────

class APIManager:
    """
    Import once: from api_manager import api
    All external calls go through this object.
    """

    def __init__(self):
        self._store  = _Store()
        self.ai      = _AIClient(self._store)
        self.email   = _EmailClient(self._store)
        self.payment = _PaymentClient(self._store)
        self.search  = _SearchClient(self._store)
        self.github  = _GitHubClient(self._store)

    def reload(self):
        """Hot-reload ALL API keys from environment. No restart needed."""
        self.ai.reload()
        self.email.reload()
        self.payment.reload()
        logger.info("APIManager: all keys reloaded")

    @staticmethod
    def _provider_health(configured, s):
        """Turn 24-h call counts into a word about whether the provider actually WORKS.

        Input:  configured -- is a key/URL present at all
                s          -- that provider's {"ok": n, "error": n} counts for the last 24 h
        Output: "not_configured" | "untried" | "failing" | "degraded" | "working"

        WHY: `configured` answers "is a key set", which is NOT the question anyone asks of a
        health page. github_models reported "configured" for months while returning HTTP 400 on
        every single call, because a present token was the only thing being measured. A
        provider that has only ever errored is FAILING, and the dashboard must say so.

        Derived purely from counts already recorded by `_Store.log` -- it makes no upstream
        call, so reading the health page costs neither latency nor a slice of a free-tier
        allowance. A provider nothing has exercised yet is "untried", which is honestly
        different from one that has been tried and failed.
        """
        if not configured:
            return "not_configured"
        ok, err = int(s.get("ok", 0) or 0), int(s.get("error", 0) or 0)
        if ok == 0 and err == 0:
            return "untried"
        if ok == 0:
            return "failing"
        return "degraded" if err > ok else "working"

    def status(self):
        """
        Return dict of provider availability and 24-h call stats.
        Safe to expose on an admin dashboard.
        """
        stats = self._store.stats()

        def _p(configured, key):
            s = stats.get(key, {})
            return {"configured": bool(configured),
                    "health": self._provider_health(bool(configured), s), **s}

        return {
            "providers": {
                "claude":        _p(self.ai.anthropic_key,   "anthropic"),
                "openrouter":    _p(self.ai.openrouter_key,  "openrouter"),
                "ollama":        _p(self.ai.ollama_url,      "ollama"),
                "github_models": _p(self.ai.github_token,    "github_models"),
                "resend":        {"configured": bool(self.email.resend_key),
                                  **stats.get("resend", {})},
                "smtp":          {"configured": bool(self.email.smtp_host
                                                     and self.email.smtp_user),
                                  **stats.get("smtp", {})},
                "paystack":      {"configured": bool(self.payment.secret_key),
                                  **stats.get("paystack", {})},
                "ddgs":          {"configured": True,
                                  **stats.get("ddgs", {})},
            },
            "logs": self._store.get_logs(limit=50),
        }

    def get_logs(self, provider=None, limit=200):
        return self._store.get_logs(provider=provider, limit=limit)

    def clear_cache(self, provider=None):
        self._store.clear(provider)


# Singleton — import this symbol in web_app.py
api = APIManager()
