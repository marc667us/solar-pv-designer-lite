"""
Beta invite sender — emails the 8 Ghana solar installer/supplier contacts
identified in Desktop/ghana_beta_invitees.json. Sends through the app's
own _send_email helper (Brevo -> Resend -> SMTP chain in
api_manager.email.send) so the audit trail + bounce handling stay
centralised.

Also renders the email body to a PDF copy on the owner's Desktop for
the records request: "send me copy of what you send to them on my
desktop as pdf".

Safety:
  * --dry-run (default): does NOT send. Renders the PDF, lists what
    would be sent, exits.
  * --send: actually sends. Requires the operator to set
    BREVO_API_KEY in the environment (the send chain falls back to
    Resend/SMTP if Brevo is unset, but on Render that's blocked).
  * One-second sleep between sends to stay well under Brevo's 300/day
    free-tier cap.

Required env vars:
  BREVO_API_KEY            — primary send provider
  SMTP_FROM (optional)     — sender address; default sales@aiappinvent.com

The attachment is SolarPro_Sales_Pitch.pdf from the owner's Desktop.
Change the SALES_PDF constant below if a different PDF should ship.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

# Repo root + Desktop path
ROOT    = Path(__file__).resolve().parents[1]
DESKTOP = Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / "Desktop"

INVITEES_JSON = DESKTOP / "ghana_beta_invitees.json"
SALES_PDF     = DESKTOP / "SolarPro_Sales_Pitch.pdf"
COPY_PDF_OUT  = DESKTOP / "SolarPro_Beta_Invite_Email_Copy.pdf"

# Make the repo's modules importable so we can use api_manager.email.send.
sys.path.insert(0, str(ROOT))

SUBJECT = "Try SolarPro Design — free beta access for your design team"

# Body is composed in Markdown so we can both (a) convert to HTML for the
# actual sends and (b) render the same text to PDF for the owner's copy.
# Two Jinja-style placeholders: {company} + {first_name}.
BODY_MD_TEMPLATE = """\
# SolarPro Design - Public Beta Invitation

Dear {company} team,

I'm Marc - founder of **AI App Invent** and the engineer behind
[SolarPro Design](https://solarpro.aiappinvent.com), a new web app that
turns a customer's daily load schedule into a full pv solar design
package in under five minutes:

- BS 7671 / IEC 60364 compliant sizing for PV, battery, inverter and MPPT
- AC cable sizing with per-circuit voltage drop working
- Bill of Quantities with CAPEX, financing and 25-year cashflow
- Single-line diagram, system topology and mounting plan
- One-click PDF export of the complete technical and financial proposal

You and your team are exactly the kind of operator we want feedback from.
**The public beta is live now and free** to use through the rest of the
year while we polish the platform.

## How to join

1. Visit **https://solarpro.aiappinvent.com**
2. Sign up with your work email (no credit card required)
3. Create a project, run a design, download the proposal PDF
4. Email me back with anything that surprised you - bugs, missing
   features, copy that did not make sense, anything

The current beta runs on free-tier infrastructure that may be reset
between deployments while we cut over to the production database. We
post the cut-over date in the in-app banner; for now, please keep a
local copy of any project you cannot afford to recreate.

Attached you will find our short sales-pitch PDF for context. The
release notes (with what works, what is in beta, and what is coming
in v0.9.1) live at:

https://github.com/marc667us/solar-pv-designer-lite/releases/tag/v0.9.0-beta.1

## How to send feedback

Two channels — pick whichever is easier:

- **In-app feedback** — every page has a feedback link in the footer.
  Submissions land in our admin queue and get acted on the same day.
- **Open a ticket** — visit `/tickets` after logging in to file a
  bug or request. We track these alongside feature work.

You can also just reply to this email.

## What I want back

If the design output for one of your real projects is wrong, off by a
margin you would not accept, or simply confusing - please tell me.
That is what I want to fix before we open the gates wider.

Best regards,

**Marc**
Founder, AI App Invent
sales@aiappinvent.com
https://aiappinvent.com
"""

# Same text rendered as HTML for the email send. Keeps the same wording
# but flattens the headers and uses inline styling.
BODY_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;color:#1a1a1a;line-height:1.55">
<h2 style="color:#0a2d47">SolarPro Design - Public Beta Invitation</h2>

<p>Dear <strong>{company}</strong> team,</p>

<p>I'm Marc - founder of <strong>AI App Invent</strong> and the engineer behind
<a href="https://solarpro.aiappinvent.com">SolarPro Design</a>, a new web app
that turns a customer's daily load schedule into a full pv solar design
package in under five minutes:</p>

<ul>
  <li>BS 7671 / IEC 60364 compliant sizing for PV, battery, inverter and MPPT</li>
  <li>AC cable sizing with per-circuit voltage drop working</li>
  <li>Bill of Quantities with CAPEX, financing and 25-year cashflow</li>
  <li>Single-line diagram, system topology and mounting plan</li>
  <li>One-click PDF export of the complete technical and financial proposal</li>
</ul>

<p>You and your team are exactly the kind of operator we want feedback from.
<strong>The public beta is live now and free</strong> to use through the rest
of the year while we polish the platform.</p>

<h3 style="color:#0a2d47">How to join</h3>
<ol>
  <li>Visit <a href="https://solarpro.aiappinvent.com">https://solarpro.aiappinvent.com</a></li>
  <li>Sign up with your work email (no credit card required)</li>
  <li>Create a project, run a design, download the proposal PDF</li>
  <li>Email me back with anything that surprised you - bugs, missing features,
      copy that did not make sense, anything</li>
</ol>

<p style="background:#fef3c7;border-left:4px solid #f59e0b;padding:10px 14px;font-size:14px">
The current beta runs on free-tier infrastructure that may be reset between
deployments while we cut over to the production database. We post the cut-over
date in the in-app banner; for now, please keep a local copy of any project
you cannot afford to recreate.
</p>

<p>Attached you will find our short sales-pitch PDF for context. The release
notes (with what works, what is in beta, and what is coming in v0.9.1) live at:</p>
<p><a href="https://github.com/marc667us/solar-pv-designer-lite/releases/tag/v0.9.0-beta.1">
github.com/marc667us/solar-pv-designer-lite/releases/tag/v0.9.0-beta.1</a></p>

<h3 style="color:#0a2d47">How to send feedback</h3>
<p>Two channels — pick whichever is easier:</p>
<ul>
  <li><strong>In-app feedback</strong> — every page has a feedback link in the footer.
      Submissions land in our admin queue and get acted on the same day.</li>
  <li><strong>Open a ticket</strong> — visit <a href="https://solarpro.aiappinvent.com/tickets">solarpro.aiappinvent.com/tickets</a>
      after logging in to file a bug or request. We track these alongside feature work.</li>
</ul>
<p>You can also just reply to this email.</p>

<h3 style="color:#0a2d47">What I want back</h3>
<p>If the design output for one of your real projects is wrong, off by a margin
you would not accept, or simply confusing - please tell me. That is what I want
to fix before we open the gates wider.</p>

<p>Best regards,<br>
<strong>Marc</strong><br>
Founder, AI App Invent<br>
<a href="mailto:sales@aiappinvent.com">sales@aiappinvent.com</a><br>
<a href="https://aiappinvent.com">aiappinvent.com</a>
</p>
</body></html>
"""


def load_recipients() -> list[dict]:
    """Read ghana_beta_invitees.json, return the entities with usable emails.

    A few entries carry "first@.../second@..." — we split those and take
    just the first address to avoid the same org getting two emails."""
    data = json.load(open(INVITEES_JSON, "r", encoding="utf-8"))
    out = []
    for e in data["entities"]:
        em = (e.get("email") or "").strip()
        if not em:
            continue
        # Sanitise "foo@... / bar@..." composites
        em = em.split("/")[0].strip()
        em = em.split(",")[0].strip()
        if "@" not in em:
            continue
        out.append({
            "name":   e["name"],
            "email":  em,
            "city":   e.get("city", ""),
            "phones": e.get("phones", []),
        })
    return out


def render_copy_pdf(recipients: list[dict], out_path: Path) -> None:
    """Write a single-PDF audit copy of the exact body that will be sent,
    using the markdown-pdf Python package per CLAUDE.md's ref_pdf_toolchain
    rule ('pandoc/wkhtmltopdf/reportlab NOT installed')."""
    from markdown_pdf import MarkdownPdf, Section  # type: ignore

    pdf = MarkdownPdf(toc_level=2)
    # Cover page — operator-facing summary
    summary = f"""# Beta Invitation Email — Sent Copy

**Date generated:** {time.strftime('%Y-%m-%d %H:%M:%S UTC')}
**Sent from:** sales@aiappinvent.com (Brevo HTTPS API)
**Attachment:** SolarPro_Sales_Pitch.pdf
**Subject line:** {SUBJECT}
**Number of recipients:** {len(recipients)}

## Recipient list

| # | Organisation | Email | City |
|---|---|---|---|
""" + "\n".join(
        f"| {i+1} | {r['name']} | {r['email']} | {r['city']} |"
        for i, r in enumerate(recipients)
    ) + "\n\n---\n\n"
    pdf.add_section(Section(summary, toc=False))
    # The template body, rendered once for archive purposes with a generic
    # placeholder. Each actual send personalises {company}.
    body = BODY_MD_TEMPLATE.format(company="<company>")
    pdf.add_section(Section(body))
    pdf.meta["title"]  = "SolarPro Beta Invite — Email Copy"
    pdf.meta["author"] = "Marc — AI App Invent"
    pdf.save(str(out_path))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true",
                        help="ACTUALLY SEND. Without this flag the script is dry-run.")
    args = parser.parse_args()

    if not INVITEES_JSON.exists():
        print(f"ERROR: invitee list missing at {INVITEES_JSON}", file=sys.stderr)
        return 2
    if not SALES_PDF.exists():
        print(f"ERROR: attachment PDF missing at {SALES_PDF}", file=sys.stderr)
        return 3

    recipients = load_recipients()
    print(f"Loaded {len(recipients)} recipients with valid emails:")
    for r in recipients:
        print(f"  - {r['name']:<45}  {r['email']}")
    print()

    # Always render the copy PDF — owner asked for it whether or not we send.
    print(f"Rendering email copy PDF -> {COPY_PDF_OUT}")
    render_copy_pdf(recipients, COPY_PDF_OUT)
    print(f"OK  copy PDF written ({COPY_PDF_OUT.stat().st_size:,} bytes)")
    print()

    if not args.send:
        print("DRY-RUN — no email was sent. Re-run with --send to actually fire.")
        return 0

    # Lazy import so the dry-run path doesn't need Flask context.
    import api_manager  # noqa: E402
    sender_addr = os.environ.get("SMTP_FROM", "sales@aiappinvent.com")
    attachment_bytes = SALES_PDF.read_bytes()
    attachments = [("SolarPro_Sales_Pitch.pdf", attachment_bytes,
                    "application/pdf")]

    sent  = []
    failed = []
    for r in recipients:
        company = r["name"]
        # Personalise just the {company} placeholder; first_name not used in
        # the current template but kept in the dict for future expansion.
        html_body = BODY_HTML_TEMPLATE.format(company=company)
        text_body = BODY_MD_TEMPLATE.format(company=company)
        try:
            result = api_manager.api.email.send(
                r["email"], SUBJECT, html_body,
                text_body=text_body, from_addr=sender_addr,
                attachments=attachments,
            )
            print(f"  SENT  {r['email']:<40}  result={result!r}")
            sent.append(r)
        except Exception as e:
            print(f"  FAIL  {r['email']:<40}  err={e!r}")
            failed.append((r, str(e)))
        # Pace ourselves under Brevo's 300/day cap.
        time.sleep(1)

    print()
    print(f"=== RESULT: sent={len(sent)} failed={len(failed)} ===")
    return 0 if not failed else 4


if __name__ == "__main__":
    sys.exit(main())
