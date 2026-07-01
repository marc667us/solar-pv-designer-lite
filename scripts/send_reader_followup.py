"""Send a personal follow-up to invitees who opened the launch email.

Reads data/beta_outreach/readers_to_follow_up.json (produced by
list_beta_readers.py), filters to invitees who opened but didn't
sign up, and sends a short candid follow-up via Brevo's REST API.

Safety:
  --dry-run (default): print plan, do not send.
  --send: actually send.

Idempotency:
  Maintains data/beta_outreach/followup_sent_log.json so re-runs
  skip recipients already contacted today.

Env:
  BREVO_API_KEY        required for --send
  SMTP_FROM            default sales@aiappinvent.com
  FOLLOWUP_REPLY_TO    default marc@aiappinvent.com — replies route here
"""
from __future__ import annotations
import argparse, datetime as dt, json, os, sys, time
import urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READERS_PATH = ROOT / "data" / "beta_outreach" / "readers_to_follow_up.json"
LOG_PATH     = ROOT / "data" / "beta_outreach" / "followup_sent_log.json"

SUBJECT = "Quick question — did SolarPro miss the mark?"
FROM_NAME = "Marc — SolarPro Design"
DEFAULT_FROM     = "sales@aiappinvent.com"
DEFAULT_REPLY_TO = "marc@aiappinvent.com"

# Plain-text version for clients that prefer it + accessibility.
TEXT_BODY = """\
Hi {greeting},

I noticed you opened our SolarPro Design beta invitation a few days
back — thanks for taking a look.

I'm Marc, the founder. We're seeing a great open rate but no signups
yet, which tells me something about the offer isn't quite landing.

Could I ask — what stopped you?

  • Trial felt like too much commitment?
  • Couldn't see what the tool does without signing up?
  • Worried it doesn't fit your workflow?
  • Something else?

A one-line reply would genuinely help us figure out what to fix. No
sales pitch, no follow-up funnel — I'm just trying to learn.

If a quick demo is easier, I'll do a 10-minute screen-share of the
tender radar + one design end-to-end. Reply with a time that works.

Thanks,
Marc

https://solarpro.aiappinvent.com
"""

# HTML version is the same content, lightly styled.
HTML_BODY = """\
<!DOCTYPE html><html><body style="font-family:-apple-system,Segoe UI,Arial,sans-serif;font-size:15px;line-height:1.6;color:#222;max-width:560px">
<p>Hi {greeting},</p>
<p>I noticed you opened our SolarPro Design beta invitation a few days
back — thanks for taking a look.</p>
<p>I'm Marc, the founder. We're seeing a great open rate but no
signups yet, which tells me something about the offer isn't quite
landing.</p>
<p><strong>Could I ask — what stopped you?</strong></p>
<ul>
  <li>Trial felt like too much commitment?</li>
  <li>Couldn't see what the tool does without signing up?</li>
  <li>Worried it doesn't fit your workflow?</li>
  <li>Something else?</li>
</ul>
<p>A one-line reply would genuinely help us figure out what to fix.
No sales pitch, no follow-up funnel — I'm just trying to learn.</p>
<p>If a quick demo is easier, I'll do a 10-minute screen-share of the
tender radar + one design end-to-end. Reply with a time that works.</p>
<p>Thanks,<br>Marc<br><a href="https://solarpro.aiappinvent.com?utm_source=followup&amp;utm_medium=email&amp;utm_campaign=reader_followup">solarpro.aiappinvent.com</a></p>
</body></html>
"""


def load_readers(invitees_only: bool, include_owner_preview: bool) -> list[dict]:
    if not READERS_PATH.exists():
        sys.exit(f"missing {READERS_PATH} — run list_beta_readers.py first "
                 f"(or trigger the List beta readers workflow)")
    doc = json.loads(READERS_PATH.read_text(encoding="utf-8"))
    openers = doc.get("openers", [])
    if invitees_only:
        openers = [r for r in openers if r.get("in_invitee_list")]
    if not include_owner_preview:
        # Default: skip owner's own preview accounts — they don't get a
        # "what stopped you?" email from themselves.
        openers = [r for r in openers
                   if (r.get("invitee_country") or "").lower() != "owner preview"]
    return openers


def load_sent_log() -> dict:
    if LOG_PATH.exists():
        return json.loads(LOG_PATH.read_text(encoding="utf-8"))
    return {"sent": {}}


def save_sent_log(log: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")


def first_name_from(invitee_name: str) -> str:
    """Heuristic — the invitee_name is usually a company, not a person."""
    if not invitee_name or invitee_name == "?":
        return "there"
    return invitee_name.split()[0] if " " not in invitee_name else invitee_name


def send_one(api_key: str, sender_addr: str, reply_to: str,
             email: str, greeting: str) -> tuple[bool, str]:
    body = json.dumps({
        "sender":   {"email": sender_addr, "name": FROM_NAME},
        "to":       [{"email": email}],
        "replyTo":  {"email": reply_to, "name": "Marc"},
        "subject":  SUBJECT,
        "htmlContent": HTML_BODY.format(greeting=greeting),
        "textContent": TEXT_BODY.format(greeting=greeting),
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=body,
        headers={
            "api-key": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return True, data.get("messageId", "ok")
    except urllib.error.HTTPError as e:
        return False, f"http {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true",
                    help="actually send (default is dry-run)")
    ap.add_argument("--all-openers", action="store_true",
                    help="include non-invitee openers too (default: invitees only)")
    ap.add_argument("--include-owner-preview", action="store_true",
                    help="include owner's preview accounts (default: exclude)")
    args = ap.parse_args()

    readers = load_readers(
        invitees_only=not args.all_openers,
        include_owner_preview=args.include_owner_preview,
    )
    log = load_sent_log()
    today = dt.date.today().isoformat()

    plan = []
    for r in readers:
        email = r["email"]
        if email in log["sent"]:
            continue  # already sent — skip
        greeting = first_name_from(r.get("invitee_name", "there"))
        plan.append({"email": email, "greeting": greeting,
                     "company": r.get("invitee_name", "?"),
                     "country": r.get("invitee_country", "?")})

    print(f"plan: {len(plan)} recipient(s), {len(readers) - len(plan)} skipped (already sent)")
    for p in plan:
        print(f"  - {p['email']:<40s}  ({p['country']:<14s})  greet={p['greeting']!r}")

    if not args.send:
        print("\nDRY-RUN — nothing was sent. Re-run with --send to fire.")
        return 0

    api_key = os.environ.get("BREVO_API_KEY")
    if not api_key:
        sys.exit("BREVO_API_KEY env var required for --send")
    sender_addr = os.environ.get("SMTP_FROM", DEFAULT_FROM)
    reply_to    = os.environ.get("FOLLOWUP_REPLY_TO", DEFAULT_REPLY_TO)

    sent, failed = 0, 0
    for p in plan:
        ok, info = send_one(api_key, sender_addr, reply_to,
                            p["email"], p["greeting"])
        if ok:
            log["sent"][p["email"]] = {"sent_at": dt.datetime.now(
                dt.timezone.utc).isoformat(), "messageId": info,
                "company": p["company"]}
            sent += 1
            print(f"  SENT  {p['email']:<40s}  msg={info}")
        else:
            failed += 1
            print(f"  FAIL  {p['email']:<40s}  err={info}")
        time.sleep(1)  # stay under Brevo 300/day cap

    save_sent_log(log)
    print(f"\n=== sent={sent}  failed={failed} ===")
    return 0 if failed == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
