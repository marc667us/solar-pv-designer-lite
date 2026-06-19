"""
Email broadcast: announce the Keycloak login migration to every user.

Phase 7 task 34 of docs/SECURITY_MIGRATION_KEYCLOAK.md.

Sends a single transactional email via Brevo to every active user in
the SolarPro `users` table, telling them their login is changing and
they will need to reset their password on first login after cutover.

Defaults to a 14-day lead time. Run this 14 calendar days before the
`gh workflow run "Cut Over To Keycloak"` event. After cutover the
existing `/login` form still works behind `?legacy=1` for marc667us
as the emergency channel.

Modes
-----

    --dry-run     Print the recipient list + the rendered email body;
                  no Brevo call. Use this to sanity-check the cohort.
    --send        Send for real. Requires `BREVO_API_KEY` in env.
                  Adds a `--limit N` safety cap that defaults to 5
                  (so a mistyped command doesn't fire 200 emails).

Sender + template
-----------------

  From: sales@aiappinvent.com
  Reply-To: support@aiappinvent.com
  Subject: Action needed: Your SolarPro login is changing in 14 days

The body is intentionally short -- one paragraph + a single action
("you will be asked to reset your password on first login"). No HTML
ornamentation: the plan §11.1 + the prior beta-onboarding emails
keep the same plain-text register.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


REPO_ROOT = Path(__file__).resolve().parent.parent

log = logging.getLogger("keycloak_broadcast")


SUBJECT = "Action needed: Your SolarPro login is changing in 14 days"

BODY_TEMPLATE = """\
Hi {first_name},

We are upgrading the SolarPro login system on {cutover_date} (UTC) so
your account stays secure with multi-factor authentication and single
sign-on across the AI App Invent platform.

What you need to know:

  * On or after {cutover_date}, the existing login form will redirect
    to the new sign-in page.
  * You will be asked to reset your password the first time you sign in.
  * Your projects, designs, reports, and saved data are NOT touched --
    they all carry over.

If you run into any trouble after {cutover_date}, please reply to this
email and we will help you straight away.

Thank you for being part of SolarPro.

-- SolarPro Operations
   sales@aiappinvent.com
"""


# ── Recipient sourcing ──────────────────────────────────────────────────

def _connect():
    url = os.environ.get("DATABASE_URL", "").strip()
    if url.startswith(("postgres://", "postgresql://")):
        import psycopg2
        return psycopg2.connect(url), True
    return sqlite3.connect(
        os.environ.get("DB_PATH", str(REPO_ROOT / "solar.db"))
    ), False


def _fetch_recipients() -> list[dict]:
    conn, is_pg = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT username, email, name "
            "FROM users "
            "WHERE email <> '' AND email LIKE '%@%' "
            "ORDER BY id"
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    out = []
    for r in rows:
        if is_pg:
            username, email, name = r
        else:
            username, email, name = r[0], r[1], r[2]
        out.append({
            "username": username,
            "email": email,
            "first_name": (name or username or "there").split()[0],
        })
    return out


# ── Brevo client ────────────────────────────────────────────────────────

def _send_via_brevo(*, to_email: str, to_name: str, subject: str, body: str,
                    api_key: str) -> tuple[int, str]:
    resp = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
            "accept": "application/json",
        },
        json={
            "sender": {"email": "sales@aiappinvent.com", "name": "SolarPro"},
            "to": [{"email": to_email, "name": to_name}],
            "replyTo": {"email": "support@aiappinvent.com"},
            "subject": subject,
            "textContent": body,
        },
        timeout=15.0,
    )
    return resp.status_code, resp.text[:200]


# ── CLI ─────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="Preview recipients + rendered body; no send.")
    g.add_argument("--send", action="store_true",
                   help="Actually call Brevo.")
    parser.add_argument("--cutover-date", default="",
                        help="ISO date of cutover (default: today + 14 days).")
    parser.add_argument("--limit", type=int, default=5,
                        help="Maximum recipients per run when --send "
                             "(safety cap; default 5).")
    parser.add_argument("--include-username", default="",
                        help="Comma-separated allowlist; only these "
                             "usernames are mailed (further safety).")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.cutover_date:
        cutover = args.cutover_date
    else:
        cutover = (
            datetime.now(timezone.utc) + timedelta(days=14)
        ).strftime("%Y-%m-%d")

    recipients = _fetch_recipients()
    if args.include_username:
        allow = {u.strip() for u in args.include_username.split(",")}
        recipients = [r for r in recipients if r["username"] in allow]

    log.info("Recipient cohort: %d users", len(recipients))
    if not recipients:
        log.warning("Nothing to send.")
        return 0

    if args.dry_run:
        sample_first = recipients[0]
        rendered = BODY_TEMPLATE.format(
            first_name=sample_first["first_name"],
            cutover_date=cutover,
        )
        print("=== PREVIEW: first recipient ===")
        print(f"To:   {sample_first['email']} ({sample_first['username']})")
        print(f"Subject: {SUBJECT}")
        print(rendered)
        print("=== first 10 of cohort ===")
        for r in recipients[:10]:
            print(f"  {r['username']:<24} {r['email']}")
        print(f"\nTotal cohort: {len(recipients)}")
        return 0

    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    if not api_key:
        log.error("BREVO_API_KEY not set; cannot send.")
        return 1
    if len(recipients) > args.limit:
        log.error("Cohort %d exceeds --limit %d; re-run with --limit %d to "
                  "confirm.", len(recipients), args.limit, len(recipients))
        return 2

    sent = failed = 0
    for r in recipients:
        body = BODY_TEMPLATE.format(
            first_name=r["first_name"],
            cutover_date=cutover,
        )
        status, snippet = _send_via_brevo(
            to_email=r["email"], to_name=r["first_name"],
            subject=SUBJECT, body=body, api_key=api_key,
        )
        if status in (200, 201, 202):
            log.info("ok    %s (%s)", r["email"], status)
            sent += 1
        else:
            log.warning("FAIL  %s (%s): %s", r["email"], status, snippet)
            failed += 1
    log.info("Done: sent=%d failed=%d", sent, failed)
    return 0 if failed == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
