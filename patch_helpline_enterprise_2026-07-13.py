"""Teach the Helpline assistant every feature shipped since 2026-06-28.

web_app.py is CRLF + mojibake and must NEVER be opened with the Edit tool, so this is a
byte-level splice, following the house pattern of patch_helpline_kb_new_features.py and
patch_helpline_topic_training_2026-06-28.py.

WHAT WAS MISSING
----------------
The assistant's knowledge was frozen at 2026-06-28. It knew nothing about:
  * the Enterprise Programme module (slices 1-7, LIVE 2026-07-13)
  * the Generation Station / utility-scale wizard (2026-07-02)
  * the 3D Digital Twin
  * Project Funding ("Sponsor a project")
  * the in-app tutorial engine itself

THE FALSE POSITIVE THIS FIXES
-----------------------------
_KB is scanned in order, FIRST MATCH WINS. The word "enterprise" already belongs to the
PRICING-PLAN tuple:

    (["plan","professional","enterprise","subscription","limit","feature"], ...)

So today "how do I run an enterprise programme?" is answered with subscription-tier copy.
The new entries are therefore inserted BEFORE that tuple.

But note what is deliberately NOT done: the new entries do NOT claim the bare word
"enterprise". If they did, the false positive would simply reverse -- "what does the
Enterprise plan cost?" would start returning programme-management copy. The new keys are
PHRASES ("enterprise programme", "beneficiar", "stage gate", "site register") that a
pricing question cannot trip, so both questions now reach the right answer.

Idempotent: both splices are guarded by a sentinel comment.

Input:  none (rewrites web_app.py in place).
Output: exit 0 on success or when already applied; 2 if an anchor is missing.
"""
from pathlib import Path

TARGET = Path(__file__).parent / "web_app.py"

SYS_SENTINEL = b"# helpline-prompt-2026-07-13-enterprise"
KB_SENTINEL = b"# kb-enterprise-programme-2026-07-13"

# --- 1. the LLM's feature knowledge (_ASSISTANT_SYSTEM) -----------------------
# Anchored on the PLANS section, so the new feature sections sit with the other
# feature sections and ahead of the commercial/plan copy.
SYS_ANCHOR = b"\r\n=== PLANS ===\r\n"

SYS_NEW = (
    b"\r\n" + SYS_SENTINEL + b"\r\n"
    b"\r\n=== ENTERPRISE PROGRAMME (since 2026-07-13, LIVE) ===\r\n"
    b"\r\n"
    b"The biggest module on the platform. It runs a NATIONAL or MULTI-SITE programme --\r\n"
    b"a ministry electrifying 400 schools, a utility rolling out clinics -- as opposed to\r\n"
    b"a single design for a single customer.\r\n"
    b"\r\n"
    b"The core idea, and the thing to explain first: a programme holds ONE reference\r\n"
    b"design, and EVERY site is an instance of that same design. The bill of quantities is\r\n"
    b"therefore the same at every site, and the funding requirement is that cost multiplied\r\n"
    b"by the number of sites. A site whose survey disagrees with the reference does NOT get\r\n"
    b"redesigned -- it raises a variance flag for engineering. (If each site were\r\n"
    b"redesigned you would have as many different BOQs as you have sites, and the programme\r\n"
    b"could not be funded as one thing.)\r\n"
    b"\r\n"
    b"Routes (all under /enterprise, all require login):\r\n"
    b"/enterprise -- portfolio: your organisations and their programmes.\r\n"
    b"/enterprise/onboarding -- create the organisation (ministry, agency, utility, NGO,\r\n"
    b"    donor). The creator becomes its owner AND is granted the operational roles needed\r\n"
    b"    to run it single-handed until colleagues are added.\r\n"
    b"/enterprise/members -- invite people; grant and revoke roles.\r\n"
    b"/enterprise/programmes/new -- register a programme.\r\n"
    b"/enterprise/programmes/<id> -- the lifecycle command centre.\r\n"
    b"/enterprise/programmes/<id>/design -- the ONE reference design; approve it; roll it out.\r\n"
    b"/enterprise/programmes/<id>/beneficiaries -- the site register.\r\n"
    b"/enterprise/programmes/<id>/import -- bulk-import sites from a spreadsheet.\r\n"
    b"/enterprise/programmes/<id>/priority -- score and rank the sites.\r\n"
    b"/enterprise/programmes/<id>/lifecycle-documents -- generate the phase's documents.\r\n"
    b"/enterprise/templates -- versioned programme templates.\r\n"
    b"\r\n"
    b"How it works, in order:\r\n"
    b"1. Create an ORGANISATION. A programme belongs to an organisation, not a person.\r\n"
    b"2. Author a TEMPLATE (one per beneficiary type: school, clinic, household). Templates\r\n"
    b"   are VERSIONED: a version is Drafted, Submitted, Approved, then Published. An\r\n"
    b"   approved version is FROZEN and can never be edited -- you raise a new version. That\r\n"
    b"   is what makes a programme built two years ago still explicable.\r\n"
    b"3. Register the PROGRAMME. It is born at Phase 1 (Concept) with all 16 lifecycle\r\n"
    b"   phases and 14 STAGE GATES seeded.\r\n"
    b"4. Load the SITES (beneficiaries) -- by hand, or bulk-import a spreadsheet. The import\r\n"
    b"   is STAGED: nothing is written to the register until you commit. Duplicates (the same\r\n"
    b"   school listed twice, even under two codes) and invalid rows are caught in the preview.\r\n"
    b"5. QUALIFY the sites: score each one (access, roof, load, risk) on the priority list.\r\n"
    b"   An UNSCORED site is shown as a QUESTION, never as a zero -- a zero would quietly sink\r\n"
    b"   it to the bottom and it would never be built. On the risk scale 100 means NO risk.\r\n"
    b"   Scoring is NOT deciding: somebody else decides on the evidence of the score.\r\n"
    b"6. Build the REFERENCE DESIGN from an approved template version, approve it, and roll\r\n"
    b"   it out. Every qualified site is then built as a COPY of that one design.\r\n"
    b"\r\n"
    b"Authority: the 14 stage gates each demand a NAMED ROLE (programme sponsor, steering\r\n"
    b"committee, programme manager, technical director, engineering manager...), not merely a\r\n"
    b"permission. Roles are granted on /enterprise/members and each is a separate, revocable\r\n"
    b"row. Separation of duties relaxes for a ONE-PERSON organisation (it is a deadlock, not a\r\n"
    b"control, when there is only one person) and the audit record says so explicitly.\r\n"
    b"\r\n"
    b"Design paths: 'standard' builds a system at every site. 'generation station' builds ONE\r\n"
    b"plant that supplies them all (built once, not once per beneficiary).\r\n"
    b"\r\n"
    b"NOTE: 'Enterprise Programme' (this module) is NOT the same thing as the 'Enterprise'\r\n"
    b"PRICING PLAN. If the user is asking about cost, tiers or subscriptions, they mean the\r\n"
    b"plan -- see PLANS below.\r\n"
    b"\r\n=== GENERATION STATION / UTILITY-SCALE (since 2026-07-02) ===\r\n"
    b"\r\n"
    b"/large-scale-solar -- utility-scale solar farm design. A 14-step wizard: site, yield,\r\n"
    b"layout, electrical, grid connection, finance, BOQ, reports. Produces 18 downloadable\r\n"
    b"report PDFs at step 13, a single-line diagram, an equipment arrangement drawing, and a\r\n"
    b"full solar-farm equipment BOQ priced from the marketplace.\r\n"
    b"There is a worked DEMO project to explore without building one.\r\n"
    b"\r\n=== 3D DIGITAL TWIN ===\r\n"
    b"\r\n"
    b"/large-scale-solar/<id>/digital-twin -- a 3D model that is an EXACT copy of the\r\n"
    b"committed design, not an illustration: the module count, inverter count and transformer\r\n"
    b"count in the twin equal the design's. Real vehicle roads, a substation compound, night\r\n"
    b"lighting, sun-path and shadow analysis. Also /equipment-layout (GA drawings) and\r\n"
    b"/electrical-sld (the single-line diagram).\r\n"
    b"\r\n=== PROJECT FUNDING -- 'Sponsor a project' ===\r\n"
    b"\r\n"
    b"A project can seek funding rather than be paid for outright. Institutions register,\r\n"
    b"projects are listed, and sponsors fund them. Admin views: /admin/funding/institutions,\r\n"
    b"/admin/funding/revenue. In an enterprise programme, funding is sought BY THE PROGRAMME\r\n"
    b"for all its locations at once -- which is only possible because every site is the same\r\n"
    b"design and therefore the same cost.\r\n"
    b"\r\n=== IN-APP TUTORIALS ===\r\n"
    b"\r\n"
    b"EVERY page teaches itself. The floating 'Help & Tutorial' button runs a guided,\r\n"
    b"narrated walkthrough of the screen the user is on, moving a cursor to each control. It\r\n"
    b"has four modes: guided (step at your own pace), auto (plays itself), watch (read-only,\r\n"
    b"never clicks anything), and explain (asks me about the step). Multi-screen tours walk\r\n"
    b"the user across screens. Written guides live at /guides -- each is readable, narrated\r\n"
    b"aloud by the browser, downloadable as PDF, or playable as a live walkthrough.\r\n"
    b"If a user is lost on a page, tell them to press 'Help & Tutorial' on THAT page.\r\n"
    + SYS_ANCHOR                      # re-emit, so .replace() inserts BEFORE it
)

# --- 2. the rule-based fallback table (_KB) -----------------------------------
# Anchored on the PRICING-PLAN tuple. First match wins, so these MUST precede it.
KB_ANCHOR = (
    b'        (["plan","professional","enterprise","subscription","limit","feature"],\r\n'
)

KB_NEW = (
    b"        " + KB_SENTINEL + b"\r\n"
    b"        # -- ENTERPRISE PROGRAMME (live 2026-07-13) --\r\n"
    b"        # NOTE: these MUST sit above the plan tuple below, which owns the bare word\r\n"
    b'        # "enterprise". They use PHRASES, never bare "enterprise", so a pricing\r\n'
    b"        # question still reaches the plan answer instead of this one.\r\n"
    b'        (["enterprise programme","enterprise program","national programme",'
    b'"national program","multi-site","many sites","hundreds of sites","rollout",'
    b'"roll out to all"],\r\n'
    b'         "The **Enterprise Programme** module (/enterprise) runs a national or '
    b'multi-site programme -- a ministry electrifying 400 schools, say. The key idea: the '
    b'programme holds **ONE reference design**, and every site is an instance of it, so the '
    b'BOQ is the same at every site and funding can be sought for all of them at once. Flow: '
    b'create your organisation (/enterprise/onboarding) -> author a versioned template -> '
    b'register the programme (16 phases, 14 stage gates) -> load the sites -> score and '
    b'qualify them -> build the reference design and roll it out. Press **Help & Tutorial** '
    b'on any /enterprise page for a guided walkthrough."),\r\n'
    b'        (["beneficiar","site register","import sites","upload sites",'
    b'"spreadsheet of sites","bulk import","csv of schools"],\r\n'
    b'         "Sites (beneficiaries) live in the programme\'s register. Add one by hand, or '
    b'bulk-import a spreadsheet at /enterprise/programmes/<id>/import. The import is '
    b'**staged**: nothing is written to the register until you commit it. The preview catches '
    b'duplicates -- the same school listed twice, even under two different codes -- and '
    b'rejects invalid rows rather than quietly coercing them."),\r\n'
    b'        (["stage gate","gates","phase gate","16 phases","14 gates","lifecycle phase",'
    b'"programme lifecycle"],\r\n'
    b'         "A programme carries **16 lifecycle phases and 14 stage gates**, seeded when '
    b'you register it. Each gate must be signed by a **named role** -- programme sponsor, '
    b'steering committee, technical director, engineering manager -- not merely by somebody '
    b'holding an approval permission. Grant roles on /enterprise/members; each is a separate, '
    b'revocable row."),\r\n'
    b'        (["qualification","qualify a site","priority list","score a site","scorecard",'
    b'"which site first","which site","build first","rank the sites"],\r\n'
    b'         "The priority list (/enterprise/programmes/<id>/priority) scores and ranks '
    b'every site. Two things to know: an **unscored site is shown as a question, never as a '
    b'zero** (a zero would sink it to the bottom and it would never get built), and on the '
    b'risk scale **100 means NO risk**. Scoring is not deciding -- somebody else decides on '
    b'the evidence of the score."),\r\n'
    b'        (["programme template","reference design","one design","same design",'
    b'"template version","approve a template"],\r\n'
    b'         "A **programme template** defines what every site receives, and it is '
    b'versioned: Draft -> Submitted -> Approved -> Published. An approved version is **frozen '
    b'and can never be edited** -- you raise a new version instead, which is what keeps a '
    b'programme built two years ago explicable. The programme then builds **one reference '
    b'design** from an approved version, and every site is a copy of it. A site whose survey '
    b'disagrees raises a variance flag for engineering; it is never silently resized."),\r\n'
    b"        # -- GENERATION STATION / UTILITY-SCALE + DIGITAL TWIN --\r\n"
    b'        (["generation station","utility scale","utility-scale","solar farm","large scale '
    b'solar","large-scale","power plant","mw plant"],\r\n'
    b'         "**Generation Station** (/large-scale-solar) designs utility-scale solar farms '
    b'through a 14-step wizard: site, yield, layout, electrical, grid connection, finance and '
    b'BOQ. It produces 18 report PDFs, a single-line diagram, equipment arrangement drawings, '
    b'and a full solar-farm BOQ priced from the marketplace. There is a worked demo project '
    b'you can explore without building one."),\r\n'
    b'        (["digital twin","3d twin","3d model","3d view","walk the site","sun path",'
    b'"shadow analysis"],\r\n'
    b'         "The **3D Digital Twin** (/large-scale-solar/<id>/digital-twin) is an exact '
    b'copy of your committed design, not an illustration -- the module, inverter and '
    b'transformer counts in the twin equal the design\'s. It has real vehicle roads, a '
    b'substation compound, night lighting, and sun-path shadow analysis. The equipment layout '
    b'drawings and the single-line diagram are alongside it."),\r\n'
    b"        # -- THE TUTORIAL ENGINE ITSELF --\r\n"
    b'        (["tutorial","walkthrough","walk me through","guided tour","how do i use this '
    b'page","show me how","demo of this page"],\r\n'
    b'         "Every page teaches itself. Press the floating **Help & Tutorial** button on '
    b'the page you are stuck on and it runs a narrated walkthrough of that screen, moving a '
    b'cursor to each control. Four modes: guided, auto (plays itself), watch (never clicks '
    b'anything), and explain (ask me about a step). Written guides are at **/guides** -- '
    b'readable, read aloud by your browser, downloadable as PDF, or playable live."),\r\n'
    + KB_ANCHOR                       # re-emit, so .replace() inserts BEFORE it
)


def main() -> int:
    src = TARGET.read_bytes()

    if SYS_SENTINEL in src and KB_SENTINEL in src:
        print("[skip] already applied")
        return 0

    if SYS_ANCHOR not in src:
        print("[fail] _ASSISTANT_SYSTEM anchor '=== PLANS ===' not found")
        return 2
    if KB_ANCHOR not in src:
        print("[fail] _KB plan-tuple anchor not found")
        return 2

    if SYS_SENTINEL not in src:
        src = src.replace(SYS_ANCHOR, SYS_NEW, 1)
        print("[ok] _ASSISTANT_SYSTEM: 5 feature sections inserted before === PLANS ===")

    if KB_SENTINEL not in src:
        src = src.replace(KB_ANCHOR, KB_NEW, 1)
        print(f"[ok] _KB: {KB_NEW.count(chr(40).encode() + b'[')} entries inserted "
              f"BEFORE the pricing-plan tuple")

    TARGET.write_bytes(src)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
