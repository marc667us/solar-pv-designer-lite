"""Enterprise Solar Programme -- what each report IS, as a document.

WHY THIS FILE EXISTS
--------------------
Because the app was not writing reports. It was writing to-do lists.

The owner opened a "Programme Concept Note" on 2026-07-16 and called it bad. They were
right, and the reason was structural. The old model built a report out of doc 3's "Main
Activities" -- a checklist of things a PERSON must do -- and printed each one as a heading
with two to four sentences under it. So the concept note read:

    ### Register the programme idea.
    ### Identify the sponsoring institution.
    ### Define the target sector.
    ### Prepare an initial programme concept note.

The last of those is the whole defect in one line: the concept note contained a section
instructing the reader to prepare a concept note. Those are TASKS, not sections. A document
whose headings are tasks is a checklist with commentary, not a report.

The raw material was never the problem. "Identify the sponsoring institution" is the
BACKGROUND section. "Identify the energy-access problem" is the PROBLEM section. "Identify
possible funding sources" is the COST AND FUNDING section. The app had everything a concept
note needs and framed all of it as a work plan.

WHAT A REPORT IS
----------------
A document with a purpose, an argument, and a shape a reader can act on. Its headings name
PARTS OF THE DOCUMENT. It opens by saying what it is for, it makes its case in an order a
reader can follow, and it closes by asking for a decision. That is the contract this file
encodes, one template per deliverable.

HOW A SECTION GETS WRITTEN
--------------------------
Each Section carries a `brief` -- the instruction handed to the agent for THAT section of
THAT document. It is what turns "write 2-4 sentences about Budget and funding" into "set out
what the programme is expected to cost and where the money is expected to come from, and say
plainly what has not been costed yet". The brief is the difference between a caption and a
paragraph.

Each Section also carries a `topic`, which is the family of stored facts the deterministic
writer falls back to when no model is reachable (documents._facts_for_topic). The agent
writes the section properly; the fallback keeps the app honest rather than silent.

ADDING A TEMPLATE
-----------------
Author the sections the way a ministry would expect to read them, and give each a brief that
says what the section must ESTABLISH -- not what the operator must do. A deliverable with no
template here falls back to the topic-derived shape in documents._sections_for_deliverable,
which is honest but generic; the fallback is a staging post, not a destination.
"""

from __future__ import annotations

from typing import NamedTuple


class Section(NamedTuple):
    """One section of a report.

    heading -- what the reader sees. Names a part of the document, never a task.
    brief   -- what this section must establish. Handed to the agent verbatim.
    topic   -- the family of stored facts the deterministic fallback writes from
               (see documents._TOPICS / _facts_for_topic). "" = no stored facts bear on it,
               so without a model the section is honestly marked incomplete.
    """

    heading: str
    brief: str
    topic: str


# =============================================================================
# R4P1_D01 -- Programme Concept Note
# =============================================================================
# The standard ministry/DFI shape. Every section here maps onto raw material the app already
# holds -- which is exactly why the old build's failure was framing, not data.
CONCEPT_NOTE: tuple[Section, ...] = (
    Section(
        "Purpose",
        "State in two or three sentences what this note is for and what decision it asks "
        "the reader to take. Name the programme. Refer to the programme owner or sponsoring "
        "authority only if it is recorded; otherwise describe the role without naming an "
        "institution. Do not summarise the whole note here.",
        "sponsor",
    ),
    Section(
        "Background and context",
        "Set out the sector, country and reason the programme is being considered now. "
        "Ground it in the programme's own description. Where the promoting institution is "
        "not recorded, describe the public-sector or programme-owner role generically.",
        "governance",
    ),
    Section(
        "The problem",
        "State the energy-access, energy-security or energy-cost problem this programme "
        "exists to solve. Be concrete about the problem implied by the description. Where "
        "the record does not evidence the scale of the problem, use labelled assumptions "
        "rather than inventing a settled figure.",
        "",
    ),
    Section(
        "Objectives and expected benefits",
        "State what the programme is intended to achieve and the benefits expected from it. "
        "Use recorded targets where they exist; otherwise express the objectives as "
        "indicative concept-stage outcomes derived from the description.",
        "objectives",
    ),
    Section(
        "Scope and beneficiaries",
        "Define what is in scope: the beneficiary type, installation setting and geography "
        "given by the description. Use recorded beneficiary counts only where they exist; "
        "otherwise keep the scale qualitative and labelled as to be confirmed by survey.",
        "beneficiaries",
    ),
    Section(
        "Delivery approach",
        "Explain how the programme intends to deliver -- its design strategy, and what that "
        "means in practice for these sites. If no design has been selected, describe the "
        "typical concept-stage solar delivery approach without naming unrecorded suppliers "
        "or approved templates.",
        "design",
    ),
    Section(
        "Indicative cost and funding",
        "Set out the cost and funding position at concept stage. Use priced figures only if "
        "recorded; otherwise describe the cost as indicative and dependent on site surveys, "
        "energy bills, installation areas and procurement pricing. Do not name funders or "
        "say funding is approved unless recorded.",
        "money",
    ),
    Section(
        "Key stakeholders",
        "Identify stakeholder roles the programme depends on -- sponsor, owner, facility "
        "operators, technical advisers, finance reviewers and approving authority. Name a "
        "party only if it is recorded; otherwise describe the role.",
        "governance",
    ),
    Section(
        "Risks and assumptions",
        "State the principal concept-stage risks and assumptions this note rests on. Where "
        "the programme holds no risk register yet, present them as the note's initial "
        "assessment to be confirmed, not as an approved maintained register.",
        "risk",
    ),
    Section(
        "Recommendation and next steps",
        "Close with the decision requested and the immediate next steps if it is given. "
        "Name the stage gate if it is recorded by the workflow, but do not imply that the "
        "decision has already been made.",
        "schedule",
    ),
)


# =============================================================================
# The rest of the Initiation phase (owner-spec section 9)
# =============================================================================
PROBLEM_STATEMENT: tuple[Section, ...] = (
    Section(
        "Purpose",
        "State what this document establishes and who needs it.",
        "",
    ),
    Section(
        "Current situation",
        "Describe the energy situation of the intended beneficiaries today -- what they "
        "rely on, and where it fails them. Ground every claim in the record or the "
        "programme's description.",
        "beneficiaries",
    ),
    Section(
        "The problem",
        "State the problem itself, plainly and specifically. This is the sentence the whole "
        "programme answers.",
        "",
    ),
    Section(
        "Who is affected",
        "Identify who bears this problem: how many, of what type, where.",
        "sites",
    ),
    Section(
        "Consequences of inaction",
        "State what continues to happen if the programme does not proceed. Do not "
        "dramatise; state consequences that follow from the facts above.",
        "",
    ),
)

PROGRAMME_OBJECTIVES: tuple[Section, ...] = (
    Section(
        "Purpose",
        "State what this document sets out and how the objectives below will be used.",
        "",
    ),
    Section(
        "Programme goal",
        "State the single outcome this programme exists to achieve.",
        "objectives",
    ),
    Section(
        "Specific objectives",
        "List the programme's specific, measurable objectives -- capacity, coverage, "
        "beneficiaries. Use the recorded targets and no others.",
        "objectives",
    ),
    Section(
        "Expected benefits",
        "State the benefits that follow from meeting those objectives.",
        "capacity",
    ),
    Section(
        "How success will be measured",
        "State what will be measured to know whether the objectives were met. Where no "
        "monitoring plan exists yet, say that these are the proposed measures.",
        "schedule",
    ),
)

PROGRAMME_CHARTER: tuple[Section, ...] = (
    Section(
        "Purpose and authority",
        "State what this charter authorises and on whose authority it is issued.",
        "sponsor",
    ),
    Section(
        "Programme description",
        "Describe the programme: what it builds, for whom, where.",
        "objectives",
    ),
    Section(
        "Objectives and success criteria",
        "State the objectives this programme is chartered to deliver.",
        "objectives",
    ),
    Section(
        "Scope",
        "Define the boundary: what this programme covers and what it does not.",
        "beneficiaries",
    ),
    Section(
        "Governance and decision rights",
        "State who sponsors the programme, who directs it, and who signs its gates.",
        "governance",
    ),
    Section(
        "Indicative budget",
        "State the funding envelope the programme is chartered against, and its basis.",
        "money",
    ),
    Section(
        "Milestones",
        "State the programme's principal milestones. Where no schedule is recorded, say the "
        "milestones remain to be planned.",
        "schedule",
    ),
    Section(
        "Authorisation",
        "State what is being authorised and by whom, and the gate this charter opens.",
        "governance",
    ),
)

PRELIMINARY_BUDGET: tuple[Section, ...] = (
    Section(
        "Purpose",
        "State what this budget covers and its status -- preliminary, indicative, or priced.",
        "",
    ),
    Section(
        "Basis of estimate",
        "State exactly what this estimate is derived from: the capacity target, an approved "
        "reference design, or a priced Bill of Quantities. Be explicit -- a reader must know "
        "how much weight this number carries.",
        "money",
    ),
    Section(
        "Indicative cost",
        "State the expected cost and, where known, the cost per site. Do not present an "
        "estimate as a price.",
        "money",
    ),
    Section(
        "Funding sources",
        "State where the funding is expected to come from. Where no funding strategy is "
        "recorded, say the sources remain to be identified.",
        "money",
    ),
    Section(
        "Exclusions and assumptions",
        "State what this budget excludes and the assumptions it rests on.",
        "",
    ),
)

INITIAL_RISK_REGISTER: tuple[Section, ...] = (
    Section(
        "Purpose",
        "State what this register is for and its status at this stage of the programme.",
        "",
    ),
    Section(
        "Principal risks",
        "Set out the principal risks this programme faces, given what it is, where it is, "
        "and how it intends to deliver. Where the programme holds no registered risks, say "
        "plainly that these are the note's own initial assessment and are not yet a "
        "maintained register.",
        "risk",
    ),
    Section(
        "Assumptions",
        "State the assumptions the programme currently rests on.",
        "",
    ),
    Section(
        "Next steps",
        "State how this register will be maintained and by whom.",
        "governance",
    ),
)

PROGRAMME_APPROVAL_REQUEST: tuple[Section, ...] = (
    Section(
        "Purpose",
        "State plainly that this document requests approval to proceed, and name the gate.",
        "",
    ),
    Section(
        "What is being requested",
        "State exactly what decision is sought and what it authorises the programme to do "
        "next.",
        "objectives",
    ),
    Section(
        "Summary of the case",
        "Summarise the programme's case in a few sentences: the problem, the response, the "
        "scale, and the indicative cost.",
        "capacity",
    ),
    Section(
        "Cost and funding",
        "State the funding implication of approving this request.",
        "money",
    ),
    Section(
        "Risks",
        "State the risks the approver is accepting.",
        "risk",
    ),
    Section(
        "Recommendation",
        "State the recommendation and the approval sought, naming the authority who signs "
        "it. Do not hedge.",
        "governance",
    ),
)


# =============================================================================
# R4P1_D13 -- Programme Business Case
# =============================================================================
# The investment-justification document. It answers ONE question -- should the sponsor put
# money into this rather than into something else -- and everything here serves that.
#
# It is written AFTER the concept note has been accepted by both recipients (xx201 s25), so
# unlike the concept note it is not writing from a one-line description: it has an approved
# document behind it. That is why several briefs tell the writer to build on the accepted
# concept note rather than restate it. A business case that merely repeats the concept note
# at greater length is the failure mode to avoid.
BUSINESS_CASE: tuple[Section, ...] = (
    Section(
        "Executive summary",
        "State, for a sponsor who will read only this section, what is proposed, what it is "
        "expected to cost, what it is expected to return, and what decision is being asked "
        "for. Lead with the recommendation, not with background.",
        "objectives",
    ),
    Section(
        "Strategic case",
        "Explain why this programme is worth doing at all: the problem it addresses and how "
        "it fits the sponsor's or the country's energy priorities. Where an earlier concept "
        "note is on the record, build on it rather than restating it. Do NOT state or imply "
        "that any earlier document has been accepted, approved or endorsed -- you are not "
        "told the lifecycle state and an unearned acceptance is a liability.",
        "objectives",
    ),
    Section(
        "Options considered",
        "Set out the realistic options and say plainly why the recommended one is preferred. "
        "At minimum consider: do nothing and continue with grid and generators; individual "
        "unaggregated purchases by beneficiaries; a sponsor-funded grant programme; and the "
        "recommended aggregated financed programme. A business case with only one option is "
        "not a case, it is an assertion.",
        "money",
    ),
    Section(
        "Economic case",
        "Give the indicative capital and operating costs over the asset's life, and the "
        "benefits expected against them -- energy saved, expenditure avoided, generator fuel "
        "displaced. State the payback period and whether the return is positive over the "
        "asset life. Compare against the counterfactual of doing nothing. Say which "
        "assumptions the result is most sensitive to -- tariff movement, demand accuracy, "
        "financing cost -- and which way the case turns if they move against it. Where a "
        "figure is not on the record, reason to an indicative value and LABEL it as "
        "indicative or assumed. Never present a modelled figure as a confirmed one.",
        "money",
    ),
    Section(
        "Commercial and financing case",
        "Describe how the programme would be paid for and on what indicative terms: the "
        "split between grant, loan and beneficiary contribution, the currency, the indicative "
        "tenor, and what security or guarantee is envisaged. State plainly whether the "
        "expected repayment is affordable against the beneficiary's current energy "
        "expenditure -- a financing structure that costs more than the bill it replaces is "
        "not viable and must be said so. Financing institutions are PROSPECTIVE until an "
        "agreement is executed: never state or imply that any institution has committed "
        "funds, approved a facility or agreed terms.",
        "money",
    ),
    Section(
        "Management case",
        "Explain how the programme would actually be delivered and governed: who runs it, "
        "who assures the technical work independently of whoever delivers it, how delivery "
        "is procured, what the reporting cadence to the sponsor is, and how a problem gets "
        "escalated. Name roles, not people, where individuals are not on the record.",
        "governance",
    ),
    Section(
        "Risks and assumptions",
        "State the principal risks to the investment and the assumptions the case rests on, "
        "with what would be done about each. Affordability of repayments and the accuracy of "
        "the demand baseline belong here if they bear on the programme.",
        "risk",
    ),
    Section(
        "Recommendation and decision sought",
        "State the recommended option and the specific decision being asked of the sponsor, "
        "including any conditions that should attach to an approval. End with the decision, "
        "not with a summary.",
        "governance",
    ),
)


# =============================================================================
# R4P1_D14 -- Official Programme Plan
# =============================================================================
# What the programme will actually DO, written once the business case is accepted and the
# recipients have asked for a plan (xx201 s30-s32).
#
# The scope boundary matters and is deliberate: this is the plan that CLOSES Initiation, not
# the detailed Planning-phase plan. xx201 s32 says so explicitly -- "do not introduce detailed
# Planning Phase activities yet". Its job is to be complete enough to authorise a charter.
PROGRAMME_PLAN: tuple[Section, ...] = (
    Section(
        "Programme background and goal",
        "State briefly where the programme came from and what it is for, carrying forward "
        "whatever earlier programme documents are on the record. Do not re-argue the "
        "investment case here; summarise it. Do NOT state or imply that any earlier document "
        "has been accepted, approved or endorsed -- you are not told the lifecycle state.",
        "objectives",
    ),
    Section(
        "Objectives and intended outcomes",
        "State what the programme will achieve and how anyone would know it had. Prefer "
        "recorded targets; where none exist, give indicative outcomes and label them as such.",
        "objectives",
    ),
    Section(
        "Beneficiaries and scope",
        "Define who the programme serves and what is in and out of scope. Exclusions matter "
        "as much as inclusions: a plan that names no boundary has none.",
        "beneficiaries",
    ),
    Section(
        "Partnership and governance structure",
        "Set out the parties and who decides what: the programme developer, the beneficiary "
        "organisation, the sponsor institution, and the technical assurance role. For each, "
        "say what it decides, what it only advises on, and what it is accountable for. State "
        "which decisions need sponsor approval and which do not. Describe a role generically "
        "where the institution is not on the record.",
        "governance",
    ),
    Section(
        "Technical approach",
        "Describe how the systems will be designed and to what standards, including how "
        "individual installations are sized to a beneficiary's actual demand rather than "
        "assigned a uniform size, how equipment quality is specified and verified, and how "
        "installations are tested and commissioned before they are accepted. Say what "
        "happens to a site that turns out to be unsuitable.",
        "design",
    ),
    Section(
        "Financing approach",
        "Describe how delivery will be funded and how any beneficiary repayment is intended "
        "to work. Keep prospective financiers prospective -- no institution has committed "
        "anything until an agreement is executed.",
        "money",
    ),
    Section(
        "Programme phases and workstreams",
        "Set out the phases the programme will run through and the workstreams inside them, "
        "at the level of what each delivers. Do NOT expand this into detailed Planning-phase "
        "activities or a task list -- this plan closes Initiation, it does not replace the "
        "Planning phase that follows it.",
        "schedule",
    ),
    Section(
        "Indicative schedule and milestones",
        "Give the sequence and the decision points that gate it. Durations are indicative at "
        "this stage and must be labelled as such.",
        "schedule",
    ),
    Section(
        "Expected benefits",
        "State the benefits the programme is expected to deliver, WHO receives each one, and "
        "the indicator and baseline by which each would be measured once it is running. A "
        "benefit with no indicator cannot be claimed later. Carry forward anything material "
        "an earlier business case put on the record.",
        "objectives",
    ),
    Section(
        "Preliminary risks",
        "State the principal risks to delivery and what would be done about each. Carry "
        "forward anything material an earlier business case put on the record.",
        "risk",
    ),
    Section(
        "Immediate next actions",
        "State what happens next, who does it, and what each action must produce, ending at "
        "the point the Programme Charter is issued for approval. Name the decisions the "
        "recipients are being asked to take and anything the programme is waiting on.",
        "governance",
    ),
)


# deliverable code -> its document shape.
#
# ONLY the Initiation phase is authored so far, deliberately. The owner rejected two builds
# for being "made too large", and authoring 112 templates before they have read ONE real
# report would repeat exactly that mistake. Initiation is the phase in use; the shape proves
# itself there, then it rolls forward.
DOCUMENT_TEMPLATES: dict[str, tuple[Section, ...]] = {
    "R4P1_D01": CONCEPT_NOTE,
    "R4P1_D02": PROBLEM_STATEMENT,
    "R4P1_D03": PROGRAMME_OBJECTIVES,
    "R4P1_D07": INITIAL_RISK_REGISTER,
    "R4P1_D09": PROGRAMME_CHARTER,
    "R4P1_D10": PRELIMINARY_BUDGET,
    "R4P1_D12": PROGRAMME_APPROVAL_REQUEST,
    # The owner's four Initiation reports (xx201 s39) are Concept Note (D01), Business Case
    # (D13), Programme Plan (D14) and Programme Charter (D09). All four are now authored, so
    # the chain has a real document shape at every step rather than a generic fallback.
    "R4P1_D13": BUSINESS_CASE,
    "R4P1_D14": PROGRAMME_PLAN,
}


def template_for(deliverable_code: str) -> tuple[Section, ...]:
    """The document shape for a deliverable, or () when none is authored yet.

    Input:  a deliverable code, e.g. "R4P1_D01".
    Output: its sections in document order, or an empty tuple.

    An empty tuple is NOT an error -- the caller falls back to the topic-derived shape, which
    is generic but honest. It is a signal that this deliverable has not been given a real
    document shape yet.
    """
    return DOCUMENT_TEMPLATES.get(deliverable_code, ())


__all__ = ["Section", "DOCUMENT_TEMPLATES", "template_for"]
