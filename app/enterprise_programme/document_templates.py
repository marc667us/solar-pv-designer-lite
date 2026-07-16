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
