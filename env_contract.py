"""THE ENVIRONMENT CONTRACT -- the single list of env vars this app is allowed to read.

WHY THIS EXISTS
---------------
OWNER, 2026-07-19: "env kept drifting no guard rails."

He is describing the root cause of four separate production faults found that same day, and
this file is the guard rail. The app reads 90 distinct environment variables across 317
read sites, spread over web_app.py, api_manager.py, dozens of new_*.py route modules and the
app/ package. Until now NOTHING anywhere listed them, so nothing could notice when a name
drifted.

What drift actually cost:

  * /api/health/ai tested GITHUB_MODELS_TOKEN while the AI chain reads GITHUB_TOKEN. Nothing
    on earth sets GITHUB_MODELS_TOKEN, so that provider would have reported "not_configured"
    forever no matter how correctly it was configured -- on the one endpoint used to diagnose
    it. Months of a 100%-failing provider looked like a configuration choice.
  * A diagnostic workflow carried its own copy of the AI model list, drifted from the code's,
    so it reported on models the app never calls and stayed silent about three that had been
    retired.
  * Keycloak's admin password drifted from the app's copy; the local .env drifted from the
    GitHub Secrets.

Every one is the same shape: TWO places named the same thing differently, and nothing
compared them. A name is a contract, and an uncontrolled contract drifts.

HOW THIS IS ENFORCED
--------------------
`test_env_contract.py` scans the source for os.environ reads and fails when:

  1. a name is in FORBIDDEN                -- a known-wrong name is being read again;
  2. a name is in neither list             -- a new variable arrived undeclared.

Rule 2 is the ratchet: adding an env var now requires naming it here, which is the moment
someone must decide what sets it, in which environment, and whether it is a secret. That
decision used to be made implicitly by whoever typed os.environ.get first.

ADDING A VARIABLE: add it to ALLOWED with a comment saying what sets it. That is the whole
process -- the point is that it cannot happen silently.
"""

# Every env var the code is permitted to read. Baselined 2026-07-19 from the code as it
# actually stood; presence here means "declared", not "audited" -- see FORBIDDEN for the ones
# actively known to be wrong.
ALLOWED: frozenset[str] = frozenset({
    "AI_SPEND_CAP_USD_MONTHLY",
    "AI_USER_TOKEN_CAP_24H",
    "ANTHROPIC_API_KEY",
    "APP_ENV",
    "APP_VERSION",
    "AXIGEN_PASSWORD",
    "AXIGEN_SERVER_URL",
    "AXIGEN_USER",
    "BROKER_AUDIT_SAMPLE_N",
    "CELERY_BROKER_URL",
    "CI_BANK_DSCR_MIN",
    "CI_BANK_DSCR_STRONG",
    "CI_BANK_IRR_MIN",
    "CI_BANK_IRR_STRONG",
    "CI_MAX_AUTOBUILD_FLOORS",
    "CI_MAX_ITEMS_PER_FLOOR",
    "CI_STEP9_PREPRICE",
    "CORS_ALLOWED_ORIGINS",
    "DATABASE_URL",
    "DB_PATH",
    "DEMO_DAYS",
    "DEMO_MODE",
    "EMAIL_BILLING",
    "EMAIL_HELLO",
    "EMAIL_PROPOSALS",
    "EMAIL_SALES",
    "EMAIL_SUPPORT",
    "ENTERPRISE_JOB_TOKEN",
    "FLASK_ENV",
    "FORCE_HTTPS_COOKIES",
    "FORCE_SECURE_COOKIES",
    "FX_RATES_AS_OF",
    "GITHUB_MODEL",
    "GITHUB_MODELS_URL",
    "GITHUB_TOKEN",
    "HOSTNAME",
    "KEYCLOAK_AUDIENCE",
    "KEYCLOAK_CLIENT_ID",
    "KEYCLOAK_ENABLED",
    "KEYCLOAK_EVENT_DEDUPE_TTL",
    "KEYCLOAK_ISSUER",
    "KEYCLOAK_JWKS_TTL",
    "KEYCLOAK_ORIGIN",
    "KEYCLOAK_POST_LOGOUT_URI",
    "KEYCLOAK_REDIRECT_URI",
    "KEYCLOAK_RT_COOKIE_DOMAIN",
    "KEYCLOAK_RT_COOKIE_NAME",
    "KEYCLOAK_TOKEN_ENDPOINT",
    "KEYCLOAK_WEBHOOK_SECRET",
    "LOGS_DIR",
    "LOG_DIR",
    "METRICS_BEARER",
    "OLLAMA_MODEL",
    "OLLAMA_URL",
    "OPENROUTER_API_KEY",
    "PAYSTACK_PUBLIC_KEY",
    "PAYSTACK_SECRET_KEY",
    "PAYSTACK_SUPPORTED_CURRENCIES",
    "PGSSLMODE",
    "PG_CONNECT_TIMEOUT",
    "PORT",
    "REDIS_URL",
    "RENDER",
    "RENDER_BUILD_TIME",
    "RENDER_GIT_COMMIT",
    "RENDER_SERVICE_NAME",
    "RESEND_API_KEY",
    "SECRET_KEY",
    "SENTRY_DSN",
    "SENTRY_TRACES_SAMPLE_RATE",
    "SMTP_FROM",
    "SMTP_HOST",
    "SMTP_PASS",
    "SMTP_PORT",
    "SMTP_TLS",
    "SMTP_USER",
    "SOLARPRO_ADMIN_PASSWORD",
    "SOLARPRO_BASE",
    "SQLITE_PATH",
    "STRIPE_PRICE_BASIC",
    "STRIPE_PRICE_ENTERPRISE",
    "STRIPE_PRICE_PROFESSIONAL",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "TRUSTED_PROXY_HOPS",
    "TRUST_PROXY_HEADERS",
    "VAULT_ADDR",
    "VAULT_ROLE_ID",
    "VAULT_SECRET_ID",
    "VAULT_TOKEN"
})

# Names that must NEVER be read, and what to use instead.
#
# These are not hypothetical. Each one was read by shipped code, set by nothing, and produced
# a silent wrong answer rather than an error -- which is the worst possible failure mode for
# configuration, because the system keeps running and keeps lying.
FORBIDDEN: dict[str, str] = {
    "GITHUB_MODELS_TOKEN":
        "Nothing sets this. The AI chain reads GITHUB_TOKEN (api_manager._AIClient). "
        "/api/health/ai read this phantom name and would have reported github_models as "
        "not_configured forever. Use GITHUB_TOKEN. See scripts/oneshot/patch_health.py, "
        "which still contains the original defect and must not be re-run as-is.",
}


def check(names) -> list[str]:
    """Return a list of human-readable violations for the given env var names.

    Input:  an iterable of env var names found in the source.
    Output: [] when every name is declared and none is forbidden.

    Kept as a plain function so the test, a CI step and an ops script can all share one
    definition of "violation" -- a second copy of this logic would be the very drift the
    file exists to prevent.
    """
    out = []
    for n in sorted(set(names)):
        if n in FORBIDDEN:
            out.append(f"{n}: FORBIDDEN -- {FORBIDDEN[n]}")
        elif n not in ALLOWED:
            out.append(
                f"{n}: UNDECLARED -- add it to ALLOWED in env_contract.py with a note on "
                f"what sets it (Render env, GitHub Secret, local .env, or the Vault broker). "
                f"If it is a secret it should be served via secrets_broker, not read directly from "
                f"os.environ.")
    return out
