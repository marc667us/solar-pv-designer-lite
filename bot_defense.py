"""Bot / automated-abuse defense for the login + payment paths (revenue-leakage guard).

Owner ask (2026-07-24): "include bot / ai bot trying to login or access payment
system and block them, prevent revenue leakage."

DESIGN -- deterministic, conservative, FAIL-OPEN:
  * Blocks only UNAMBIGUOUS bots on money/auth POST endpoints:
      - a filled HONEYPOT field (a hidden input humans never fill -> zero false
        positives), and
      - a User-Agent that is an automation client a real browser never sends
        (python-requests, curl, scrapy, headless, selenium, ...).
  * FLAGS (records, does not block) softer signals (empty UA) -- a rare privacy
    user could send those, so we watch but don't lock them out.
  * Records every decision to `bot_events` for the admin + Billing Agent.
  * NEVER blocks a normal browser, and any error in the check ALLOWS the request
    -- auth and payments must never break because of this layer.

It is NOT a replacement for the existing brute-force lockout + rate limits
(velocity); it adds the honeypot + client-identity signals those don't cover.
Webhooks (/paystack/webhook, /stripe/webhook) are DELIBERATELY out of scope --
they are server-to-server, HMAC-verified, and carry non-browser UAs by design.
"""

from __future__ import annotations

from datetime import datetime

# Hidden form field rendered invisibly in the login/register/upgrade forms. A
# human never fills it; an auto-filling bot does.
HONEYPOT_FIELD = "company_website"

# Trusted internal automation -- our own monitoring/rotation crons POST to
# /login etc. and must NEVER be blocked. They send a "SolarPro-*" User-Agent.
# Matched case-insensitively as a prefix.
_ALLOW_UA_PREFIX = ("solarpro",)

# Automation clients a real browser never sends (case-insensitive substrings).
# DELIBERATELY EXCLUDES broad tokens like bare "bot"/"spider"/"crawler": those
# match legitimate labelled clients (e.g. "Mozilla/5.0 (e2e-bot)") and search
# crawlers, which do not POST login/payment forms anyway. Only explicit
# HTTP-library / automation-tool signatures are listed.
_BOT_UA = (
    "python-requests", "aiohttp", "httpx", "python-urllib", "urllib/", "curl/",
    "wget", "libwww", "go-http-client", "okhttp", "java/", "jakarta",
    "apache-httpclient", "scrapy", "mechanize", "node-fetch", "axios", "got (",
    "phantomjs", "headlesschrome", "puppeteer", "playwright",
    "selenium", "webdriver", "httpclient", "restsharp", "postmanruntime",
    "insomnia", "libcurl", "guzzlehttp",
)

# POST endpoints where a bot causes account abuse / revenue leakage.
_SENSITIVE_PREFIXES = (
    "/login", "/register", "/forgot-password", "/reset-password",
    "/upgrade/checkout", "/upgrade/redeem", "/paystack/verify",
    "/supplier/register", "/installer/register",
)


def is_sensitive(method: str, path: str) -> bool:
    if method != "POST":
        return False
    return any(path == p or path.startswith(p) for p in _SENSITIVE_PREFIXES)


def classify(ua, honeypot_value):
    """Return (kind, reason). Pure; never raises.

    kind:
      "allow"    -- normal browser or trusted internal automation; do nothing.
      "honeypot" -- a filled hidden field == a bot; ALWAYS safe to block (no
                    legitimate client fills it).
      "ua"       -- an automation-client User-Agent; block ONLY under enforce
                    (a stray internal tool could share such a UA), else monitor.
      "empty"    -- empty User-Agent; suspicious -> flag only, never block.
    """
    try:
        u = (ua or "").strip().lower()
        # HONEYPOT IS CHECKED FIRST -- ahead of the internal allow-list below.
        # The User-Agent is an attacker-controlled request header, so an
        # allow-list keyed on it must never be able to wave through a request
        # that has ALREADY proven itself a bot by filling the hidden field.
        # Checking the allow-list first let anyone bypass the whole layer with
        # `User-Agent: SolarPro-x` (the prefix is public -- the repo is public).
        # Safe to reorder: our own crons POST real forms and never populate
        # `company_website`, and no legitimate form field shares that name
        # (real website inputs are named `website`), so internal automation
        # cannot trip this.
        if honeypot_value and str(honeypot_value).strip():
            return "honeypot", "honeypot"
        # Trusted internal automation bypasses the UA heuristics below.
        if any(u.startswith(p) for p in _ALLOW_UA_PREFIX):
            return "allow", "internal"
        if not u:
            return "empty", "empty-ua"
        for tok in _BOT_UA:
            if tok in u:
                return "ua", "ua:" + tok
        return "allow", ""
    except Exception:
        return "allow", "error"      # fail-open


def ensure_bot_events_schema(conn, is_postgres: bool = False) -> None:
    """Create the bot_events ledger idempotently. Safe on every cold start."""
    if is_postgres:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_events (
                id         SERIAL PRIMARY KEY,
                path       TEXT DEFAULT '',
                method     TEXT DEFAULT '',
                action     TEXT DEFAULT '',
                reason     TEXT DEFAULT '',
                ip         TEXT DEFAULT '',
                ua_sample  TEXT DEFAULT '',
                created_at TEXT DEFAULT ''
            )
            """
        )
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                path       TEXT DEFAULT '',
                method     TEXT DEFAULT '',
                action     TEXT DEFAULT '',
                reason     TEXT DEFAULT '',
                ip         TEXT DEFAULT '',
                ua_sample  TEXT DEFAULT '',
                created_at TEXT DEFAULT ''
            )
            """
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bot_events_created ON bot_events(created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bot_events_action ON bot_events(action)")


def record_bot_event(conn, *, path="", method="", action="", reason="",
                     ip="", ua="") -> None:
    """Append one row to the ledger. NEVER raises. UA is truncated (no PII beyond
    the client string, which is not personal data)."""
    try:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO bot_events (path, method, action, reason, ip, ua_sample, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (str(path)[:200], str(method)[:8], str(action)[:16], str(reason)[:60],
             str(ip)[:64], str(ua)[:200], now),
        )
    except Exception:
        pass
