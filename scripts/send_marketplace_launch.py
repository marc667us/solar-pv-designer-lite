"""Send the marketplace soft-launch email to the existing beta reader list.

Reads every data/beta_outreach/<region>_beta_invitees.json file, dedupes
on email, skips owner_preview_*, and sends a short launch announcement
via Brevo's REST API.

Safety:
  --dry-run (default): print plan + first 3 sample emails, do not send.
  --send: actually send.

Idempotency:
  Maintains data/beta_outreach/marketplace_launch_sent_log.json so a
  re-run skips recipients already contacted in this launch.

Env:
  BREVO_API_KEY        required for --send
  SMTP_FROM            default sales@aiappinvent.com
  REPLY_TO             default marc@aiappinvent.com
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVITEE_DIR = ROOT / "data" / "beta_outreach"
LOG_PATH = INVITEE_DIR / "marketplace_launch_sent_log.json"

SUBJECT = "Electrical pricing live on SolarPro — free to browse"
FROM_NAME = "Marc — SolarPro Design"
DEFAULT_FROM = "sales@aiappinvent.com"
DEFAULT_REPLY_TO = "marc@aiappinvent.com"

UTM = "?utm_source=launch&utm_medium=email&utm_campaign=marketplace_softlaunch"

TEXT_BODY = """\
Hi {greeting},

Quick update from SolarPro Design.

We just launched a free Electrical Pricing Marketplace as part of the
platform. You can browse live supplier prices for transformers, cables,
distribution boards, sockets, switchgear, earthing, ICT/ELV — and pull
those products straight into a BOM with labour + overhead + profit + VAT
markups baked in. Excel and PDF export of the finished BOQ are one click.

  Browse free: https://solarpro.aiappinvent.com/marketplace{utm}
  Build a BOQ: https://solarpro.aiappinvent.com/register{utm}

Why we built it: cost engineers and electricians were telling us the
hardest part of a tender wasn't the engineering — it was getting current
supplier prices fast. So we made one.

Supplier? List your products free and reach buyers globally:
  https://solarpro.aiappinvent.com/supplier/register{utm}

No credit card, no trial timer. Reply to this email if anything is
unclear or if there's a product category we're missing.

Thanks for being an early supporter.

Marc Owusu
SolarPro Design
"""

HTML_BODY = """\
<!DOCTYPE html><html><body style="font-family:-apple-system,Segoe UI,Arial,sans-serif;font-size:15px;line-height:1.6;color:#222;max-width:580px">
<p>Hi {greeting},</p>
<p>Quick update from SolarPro Design.</p>
<p>We just launched a free <strong>Electrical Pricing Marketplace</strong>
as part of the platform. You can browse live supplier prices for
transformers, cables, distribution boards, sockets, switchgear, earthing,
ICT/ELV — and pull those products straight into a BOM with labour +
overhead + profit + VAT markups baked in. <strong>Excel and PDF
export</strong> of the finished BOQ are one click.</p>
<p style="padding:14px 18px;background:#fef3c7;border-left:4px solid #f59e0b;border-radius:4px">
  ➤ <strong>Browse free:</strong>
  <a href="https://solarpro.aiappinvent.com/marketplace{utm}">solarpro.aiappinvent.com/marketplace</a><br>
  ➤ <strong>Build a BOQ:</strong>
  <a href="https://solarpro.aiappinvent.com/register{utm}">solarpro.aiappinvent.com/register</a>
</p>
<p><em>Why we built it:</em> cost engineers and electricians were telling
us the hardest part of a tender wasn't the engineering — it was getting
current supplier prices fast. So we made one.</p>
<p><strong>Supplier?</strong> List your products free and reach buyers
globally:
<a href="https://solarpro.aiappinvent.com/supplier/register{utm}">
solarpro.aiappinvent.com/supplier/register</a></p>
<p>No credit card, no trial timer. Reply to this email if anything is
unclear or if there's a product category we're missing.</p>
<p>Thanks for being an early supporter.</p>
<p>Marc Owusu<br>SolarPro Design</p>
</body></html>
"""


def load_recipients() -> list[dict]:
    """Walk every *_beta_invitees.json, dedupe on lowercased email, skip
    owner_preview accounts (they're you)."""
    seen: set[str] = set()
    out: list[dict] = []
    for path in sorted(INVITEE_DIR.glob("*_beta_invitees.json")):
        if path.stem.startswith("owner_preview"):
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[skip] {path.name}: parse error {e}", file=sys.stderr)
            continue
        # JSON shape can be either [..] or {"entities": [..]} or {"invitees": [..]}.
        if isinstance(doc, list):
            rows = doc
        elif isinstance(doc, dict):
            rows = doc.get("entities") or doc.get("invitees") or []
        else:
            rows = []
        if not isinstance(rows, list):
            continue
        for r in rows:
            email = (r.get("email") or "").strip().lower()
            if not email or "@" not in email or email in seen:
                continue
            seen.add(email)
            out.append({
                "email": email,
                "name": (r.get("name") or "").strip(),
                "country": (r.get("country") or path.stem.replace("_beta_invitees", "")).title(),
            })
    return out


def first_name_from(name: str) -> str:
    if not name:
        return "there"
    cleaned = name.replace("Ltd", "").replace("Limited", "").strip()
    if not cleaned:
        return "there"
    return cleaned.split()[0]


def load_sent_log() -> dict:
    if LOG_PATH.exists():
        return json.loads(LOG_PATH.read_text(encoding="utf-8"))
    return {"sent": {}}


def save_sent_log(log: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")


def send_brevo(api_key: str, to_email: str, to_name: str, subject: str,
               html: str, text: str, from_email: str, reply_to: str,
               from_name: str = FROM_NAME) -> tuple[bool, str]:
    payload = {
        "sender": {"name": from_name, "email": from_email},
        "to": [{"email": to_email, "name": to_name or to_email}],
        "replyTo": {"email": reply_to, "name": from_name},
        "subject": subject,
        "htmlContent": html,
        "textContent": text,
    }
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
        return True, body
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=False)
    g.add_argument("--dry-run", action="store_true", default=True,
                   help="Plan only. Default.")
    g.add_argument("--send", action="store_true", default=False,
                   help="Actually send via Brevo.")
    ap.add_argument("--from", dest="from_email",
                    default=os.environ.get("SMTP_FROM", DEFAULT_FROM))
    ap.add_argument("--reply-to", default=os.environ.get("REPLY_TO", DEFAULT_REPLY_TO))
    ap.add_argument("--max", type=int, default=300,
                    help="Brevo free daily cap. Stop after N sends.")
    args = ap.parse_args()

    recipients = load_recipients()
    log = load_sent_log()
    sent_log = log["sent"]

    pending = [r for r in recipients if r["email"] not in sent_log]
    skipped = len(recipients) - len(pending)

    print(f"--- Marketplace soft-launch - {dt.datetime.utcnow().isoformat()}Z ---")
    print(f"  Total invitees on file : {len(recipients)}")
    print(f"  Already sent (skip)    : {skipped}")
    print(f"  Pending this run       : {len(pending)}")
    print(f"  Mode                   : {'SEND' if args.send else 'DRY-RUN'}")
    print(f"  From / Reply-To        : {args.from_email} / {args.reply_to}")
    print()

    print("First 3 sample recipients (preview):")
    for r in pending[:3]:
        greeting = first_name_from(r["name"])
        print(f"  * {r['email']}  ({r['country']})  greeting=\"{greeting}\"")
    print()

    if args.dry_run and not args.send:
        print("Dry-run complete. Re-run with --send to actually send.")
        return 0

    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    if not api_key:
        sys.exit("BREVO_API_KEY env var required for --send")

    ok_n = fail_n = 0
    for i, r in enumerate(pending[:args.max], 1):
        greeting = first_name_from(r["name"])
        fmt = {"greeting": greeting, "utm": UTM}
        ok, info = send_brevo(
            api_key, r["email"], r["name"], SUBJECT,
            HTML_BODY.format(**fmt), TEXT_BODY.format(**fmt),
            args.from_email, args.reply_to,
        )
        if ok:
            sent_log[r["email"]] = {
                "sent_at": dt.datetime.utcnow().isoformat() + "Z",
                "country": r["country"],
            }
            ok_n += 1
            print(f"  [{i:3d}] OK  {r['email']}")
        else:
            fail_n += 1
            print(f"  [{i:3d}] FAIL {r['email']} — {info}")
        # Small delay to be polite to Brevo's rate window.
        time.sleep(0.4)

    save_sent_log(log)
    print()
    print(f"Done — {ok_n} sent, {fail_n} failed. Log: {LOG_PATH}")
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
