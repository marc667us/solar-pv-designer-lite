"""Inject Growth Layer / Marketplace / Procurement KB entries into the
helpline assistant's rule-based fallback so even when the LLM chain is
down (which is the live state right now -- responses are coming from
_rule_reply), users still get sensible new-feature answers.

The pattern is a list-of-tuples _KB = [ (keywords_list, answer_string), ... ].
Order matters: more specific entries should appear before generic ones so
they win the first-match scan. We insert NEW entries right after the
"thank/ok" ack block and right after "fault/alarm" -- BEFORE the older
catch-all entries that have been accidentally matching new-feature questions.

Idempotent via SENTINEL.
"""
from __future__ import annotations
from pathlib import Path
import sys

TARGET = Path(__file__).parent / "web_app.py"
SENTINEL = b"# kb-growth-marketplace-2026-06-27"

# Anchor: the first entry after acknowledgements (the maintenance/alarm tuple)
ANCHOR = (
    b'        # Monitoring/alarms before project (both mention "dashboard")\r\n'
    b'        (["maintenance","service","fault","alarm","monitoring","alert"],'
)

NEW_ENTRIES = (
    b'        ' + SENTINEL + b'\r\n'
    b'        # --GROWTH LAYER (Share button + /growth dashboard + /s/<slug>) --\r\n'
    b'        (["share","whatsapp","facebook","linkedin","twitter","social","qr code","share link","share button","share to","post on"],\r\n'
    b'         "Two ways to share. (1) PER PROJECT: open any project -> Results page -> click the gold **Share** button -> pick a card type (Solar Savings, Energy Score, BOQ Summary, Proposal Preview) -> click Generate -> get a public share URL + QR code. Buttons for WhatsApp/Facebook/LinkedIn/X are right there. (2) PLATFORM: click the **Share** megaphone in the navbar (visible to everyone) -> opens a modal with WhatsApp/Facebook/LinkedIn/X/Email + QR. Logged-in users get their referral code baked in automatically."),\r\n'
    b'        (["growth","growth dashboard","share dashboard","viral","share asset"],\r\n'
    b'         "The **Growth Dashboard** is at /growth. It shows: share cards you have created, public visits to those cards, leads captured from them, visit-to-lead conversion %, and the pipeline-stage distribution. You can revoke any share asset from this page -- the public URL then returns 410."),\r\n'
    b'        (["referral","ref code","invite","credit","earn","reward"],\r\n'
    b'         "Every account has an 8-character referral code. Share your link from /referrals -- visitors get a 30-day cookie, signups credit you in the referrals table. You earn 20% credit per paid referral; new users get 20% off their first paid month. The platform Share button in the navbar automatically uses your code when you are logged in."),\r\n'
    b'        # --MARKETPLACE + PROCUREMENT --\r\n'
    b'        (["marketplace","supplier","supplier portal","product catalog","catalogue","product catalogue","equipment catalog","brand"],\r\n'
    b'         "The **Marketplace** at /marketplace is FREE to browse for anyone (no signup). 21 categories (PV modules, inverters, batteries, cables, switchgear, structures, sockets, lighting, BMS, power systems with RMU/UPS/Generators, etc.), 437+ products across 140+ brands with live supplier pricing. Suppliers can self-register at /supplier/register and manage products at /supplier/products. Admins verify submissions at /admin/marketplace/pending."),\r\n'
    b'        (["procurement","procurement center","price sheet","bom","cost estimate","boq","bill of quantities","quotation"],\r\n'
    b'         "**Procurement Center** at /procurement-center is a checkbox-grid picker. Tick the products you want, choose a currency (USD/EUR/GBP/GHS/NGN/KES/...), pick a document type: Basic Price Sheet (reference list), BOM (Bill of Materials / Cost Estimate), or BOQ (Bill of Quantities for tender submission). Saved documents live at /price-sheets, /boms, and /boq-projects respectively. BOM and BOQ include cost roll-up; Basic Price Sheet is qty=1 reference only."),\r\n'
    b'        (["rfq","rfqs","request for quote","request for quotation","quote request","tender request"],\r\n'
    b'         "Create an **RFQ** at /rfqs/new. Pick the products + quantities + delivery deadline + budget, choose the suppliers to invite. They respond in their /supplier/rfqs/inbox. You see all responses at /rfqs/<id>. Suppliers are auto-suggested based on your BOQ catalogue."),\r\n'
    b'        (["proposal","proposal beautified","co-brand","installer logo","client proposal","branded proposal"],\r\n'
    b'         "Two proposal surfaces. The standard report at /project/<id>/report/proposal is the engineering-grade document. The **beautified, co-brandable** version is at /project/<id>/proposal/beautified -- it picks up installer logo, brand colour, contact details for a polished client-facing handover. Use the Share button at the top of either to send to clients."),\r\n'
    b'        # --PROSPECTING (admin) --\r\n'
    b'        (["opportunities","solar opportunities","rfp listing","tender feed","find tenders","procurement notice"],\r\n'
    b'         "Admins: /admin/opportunities lists live solar RFPs/RFQs/IPPs pulled from Google News across 8 procurement-language queries (500+ items typical). Filter by country / type / source. Click **Add to leads** to copy an opportunity into the CRM. Add ?refresh=1 to bust the 1-hour cache."),\r\n'
    b'        # --KEYCLOAK AUTH --\r\n'
    b'        (["keycloak","kc","oidc","sso","auth.aiappinvent","auth redirect","login redirect"],\r\n'
    b'         "Login redirects to **Keycloak** at auth.aiappinvent.com -- that is expected. Use the email + password you set when you registered. KC uses email-as-username (search by EMAIL in the KC admin console, not by username). Forgot password = click \\"Forgot password\\" on the KC login form."),\r\n'
    b'        ' + ANCHOR
)


def main() -> int:
    src = TARGET.read_bytes()
    if SENTINEL in src:
        print("[skip] KB entries already added"); return 0
    if ANCHOR not in src:
        print("[fail] KB anchor not found"); return 2
    new_src = src.replace(ANCHOR, NEW_ENTRIES, 1)
    TARGET.write_bytes(new_src)
    added = NEW_ENTRIES.count(b'(["')
    print(f"[ok] inserted {added} new KB entries before the maintenance/alarm anchor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
