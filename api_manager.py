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

import os, json, time, sqlite3, hashlib, logging
from datetime import datetime

import secrets_broker  # Phase 1: routes secret reads through the broker (audit + tier + future Vault)

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
                c.execute(
                    "INSERT OR REPLACE INTO api_cache (cache_key, provider, value, expires_at) "
                    "VALUES (?,?,?,?)",
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
    Fallback chain: Claude → OpenRouter → Ollama → GitHub Models → rule-based
    """

    def __init__(self, store: _Store):
        self._s = store
        self._load()

    def _load(self):
        self.anthropic_key    = os.environ.get("ANTHROPIC_API_KEY", "")
        self.openrouter_key   = os.environ.get("OPENROUTER_API_KEY", "")
        self.openrouter_model = os.environ.get("OPENROUTER_MODEL",
                                               "meta-llama/llama-3.1-8b-instruct:free")
        self.ollama_url       = os.environ.get("OLLAMA_URL", "")
        self.ollama_model     = os.environ.get("OLLAMA_MODEL", "mistral")
        self.github_token     = os.environ.get("GITHUB_TOKEN", "")
        self.github_model     = os.environ.get("GITHUB_MODEL", "openai/gpt-4.1-mini")

    def reload(self):
        self._load()

    def chat(self, messages, system="", model=None, max_tokens=800, cache_ttl=0):
        """
        Send AI chat. Returns (reply: str, provider: str).
        provider is 'claude', 'openrouter', 'ollama', 'github_models', or 'rule_based'.
        cache_ttl > 0 enables response caching (seconds).
        """
        ckey = None
        if cache_ttl > 0:
            ckey = _Store._key("ai", messages, system, model or "", max_tokens)
            cached = self._s.get(ckey)
            if cached:
                return cached["reply"], "cache"

        reply, provider = (
            self._claude(messages, system, model, max_tokens)
            or self._openrouter(messages, system, max_tokens)
            or self._ollama(messages, system, max_tokens)
            or self._github(messages, system, max_tokens)
            or ("I'm having trouble connecting to AI services right now. Please try again in a moment.", "rule_based")
        )

        if ckey and provider not in ("rule_based",):
            self._s.set(ckey, {"reply": reply, "provider": provider}, cache_ttl, "ai")

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
                    logger.warning("claude %s failed: %s", _model, me)
            self._s.log("anthropic", _m, "error", (time.time()-t)*1000, "all models failed")
            return None
        except Exception as e:
            self._s.log("anthropic", model or "claude", "error", (time.time()-t)*1000, str(e))
            return None

    def _openrouter(self, messages, system, max_tokens):
        if not self.openrouter_key:
            return None
        t = time.time()
        try:
            import urllib.request as _ur, json as _j
            msgs = ([{"role": "system", "content": system}] if system else []) + list(messages)
            payload = _j.dumps({"model": self.openrouter_model, "messages": msgs,
                                 "max_tokens": max_tokens}).encode()
            req = _ur.Request("https://openrouter.ai/api/v1/chat/completions", data=payload,
                              headers={"Authorization": f"Bearer {self.openrouter_key}",
                                       "Content-Type": "application/json",
                                       "HTTP-Referer": "https://solarpro.aiappinvent.com",
                                       "X-Title": "SolarPro"})
            with _ur.urlopen(req, timeout=30) as r:
                reply = _j.loads(r.read())["choices"][0]["message"]["content"]
            self._s.log("openrouter", self.openrouter_model, "ok", (time.time()-t)*1000)
            return reply, "openrouter"
        except Exception as e:
            self._s.log("openrouter", self.openrouter_model, "error", (time.time()-t)*1000, str(e))
            logger.warning("openrouter failed: %s", e)
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
            self._s.log("ollama", self.ollama_model, "error", (time.time()-t)*1000, str(e))
            logger.warning("ollama failed: %s", e)
            return None

    def _github(self, messages, system, max_tokens):
        if not self.github_token:
            return None
        t = time.time()
        try:
            import urllib.request as _ur, json as _j
            msgs = ([{"role": "system", "content": system}] if system else []) + list(messages)
            payload = _j.dumps({"model": self.github_model, "messages": msgs,
                                 "max_tokens": max_tokens, "temperature": 0.7}).encode()
            req = _ur.Request("https://models.inference.ai.azure.com/chat/completions",
                              data=payload,
                              headers={"Authorization": f"Bearer {self.github_token}",
                                       "Content-Type": "application/json",
                                       "Accept": "application/json",
                                       "User-Agent": "solarpro/1.0"})
            with _ur.urlopen(req, timeout=30) as r:
                reply = _j.loads(r.read())["choices"][0]["message"]["content"]
            self._s.log("github_models", self.github_model, "ok", (time.time()-t)*1000)
            return reply, "github_models"
        except Exception as e:
            self._s.log("github_models", self.github_model, "error", (time.time()-t)*1000, str(e))
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
    """DuckDuckGo search with 6-hour cache. Returns stale cache on failure."""

    TTL = 21600  # 6 hours

    def __init__(self, store: _Store):
        self._s = store

    def query(self, q, max_results=10, region="wt-wt"):
        """Returns list of {title, url, body} dicts. Never raises."""
        ckey = _Store._key("search", q, max_results, region)
        cached = self._s.get(ckey)
        if cached is not None:
            return cached
        t = time.time()
        try:
            from ddgs import DDGS
            results = []
            with DDGS() as d:
                for r in d.text(q, region=region, max_results=max_results):
                    results.append({"title": r.get("title",""),
                                    "url":   r.get("href",""),
                                    "body":  r.get("body","")})
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

    def status(self):
        """
        Return dict of provider availability and 24-h call stats.
        Safe to expose on an admin dashboard.
        """
        stats = self._store.stats()
        return {
            "providers": {
                "claude":        {"configured": bool(self.ai.anthropic_key),
                                  **stats.get("anthropic", {})},
                "openrouter":    {"configured": bool(self.ai.openrouter_key),
                                  **stats.get("openrouter", {})},
                "ollama":        {"configured": bool(self.ai.ollama_url),
                                  **stats.get("ollama", {})},
                "github_models": {"configured": bool(self.ai.github_token),
                                  **stats.get("github_models", {})},
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
