"""The owner's four Initiation reports must all exist and all be authored.

Revision xx201 s39 names the Initiation chain: Concept Note -> Business Case -> Programme
Plan -> Programme Charter. Two of those four had NO deliverable in the app at all, so the
chain could not be built: its middle two documents did not exist. Codex confirmed the gap
independently (2026-07-18).

These tests pin the chain end to end, and pin the one property that makes appending safe --
that no pre-existing code was re-pointed. Codes are positional, so an INSERT rather than an
append would silently make every stored document's doc_type name a different deliverable
than the one that wrote it.
"""

import pytest

from app.enterprise_programme import document_templates as templates
from app.enterprise_programme import documents, rev4_phases
from app.enterprise_programme.documents import _SETTLED_CLAIM_RE

# The owner's chain, in order (xx201 s39, s56).
CHAIN = [
    ("R4P1_D01", "Programme Concept Note"),
    ("R4P1_D13", "Programme Business Case"),
    ("R4P1_D14", "Official Programme Plan"),
    ("R4P1_D09", "Programme Charter"),
]


class TestTheChainExists:

    @pytest.mark.parametrize("code,title", CHAIN)
    def test_each_report_in_the_chain_is_a_real_deliverable(self, code, title):
        assert code in rev4_phases.DELIVERABLE_CODES
        phase, name = rev4_phases.DELIVERABLE_INDEX[code]
        assert name == title
        assert phase == "R4_INITIATION", "the whole chain closes Initiation"

    @pytest.mark.parametrize("code,title", CHAIN)
    def test_each_report_has_an_authored_shape_not_the_generic_fallback(self, code, title):
        """An empty tuple is the topic-derived fallback: honest, but generic.

        The owner rejected generic output ("what came out is bas"), so every document in the
        chain the sponsor actually reads must have a real authored shape.
        """
        sections = templates.template_for(code)
        assert sections, f"{title} ({code}) has no authored template"
        assert len(sections) >= 6, f"{title} is too thin to be a real {title.lower()}"

    @pytest.mark.parametrize("code,title", CHAIN)
    def test_no_report_repeats_a_heading(self, code, title):
        headings = [s.heading for s in templates.template_for(code)]
        assert len(headings) == len(set(headings)), f"{title} repeats a heading"

    @pytest.mark.parametrize("code,title", CHAIN)
    def test_every_section_brief_says_what_to_establish(self, code, title):
        """A brief is handed to the writer verbatim. An empty one produces an empty section.

        Codex (2026-07-18) rightly called an earlier `len(brief) > 40` check quality theatre:
        it passes on forty-one characters of nonsense. A brief steers the writer only if it
        says what the section must ESTABLISH, so assert it is instructional -- it must tell
        the writer to do something.
        """
        verbs = ("state", "explain", "describe", "set out", "give", "define")
        for section in templates.template_for(code):
            assert section.brief.strip(), f"{title} / {section.heading}: empty brief"
            assert any(v in section.brief.lower() for v in verbs), (
                f"{title} / {section.heading}: brief does not instruct the writer")

    @pytest.mark.parametrize("code,title", CHAIN)
    def test_every_topic_is_one_the_deterministic_fallback_knows(self, code, title):
        """A topic that is not in documents._TOPICS silently writes nothing when no model is
        reachable -- the section would be blank exactly when the app is already degraded.
        """
        valid = {topic for _needles, topic in documents._TOPICS}
        for section in templates.template_for(code):
            if section.topic:
                assert section.topic in valid, (
                    f"{title} / {section.heading}: unknown topic {section.topic!r}")


class TestNoBriefPresumesAnApprovalTheAppCannotKnow:
    """A brief must never tell the writer that a prior document was accepted.

    Codex (HIGH, 2026-07-18) caught this in my first draft. I had written "build on the
    ACCEPTED concept note" -- but `generate_document` enforces no chain state, so a developer
    can generate a Business Case before anything has been accepted by anyone. The brief goes
    to the writer verbatim, so it would have manufactured an endorsement that never happened
    and put it in a document a sponsor reads. That is the same liability class the concept
    note's "never state anything is approved" rule exists to prevent.

    The chain ORDER is a workflow constraint. It is not a fact any single generation can see.
    """

    # Phrases that assert a lifecycle state rather than describe a document.
    PRESUMPTIONS = (
        "accepted concept note",
        "approved concept note",
        "accepted business case",
        "approved business case",
        "accepted programme plan",
        "it has been accepted",
        "has already been approved",
    )

    @pytest.mark.parametrize("code,title", CHAIN)
    def test_no_brief_asserts_a_prior_document_was_accepted(self, code, title):
        for section in templates.template_for(code):
            low = section.brief.lower()
            for phrase in self.PRESUMPTIONS:
                if phrase not in low:
                    continue
                # A PROHIBITION containing the phrase is the point, not the defect.
                idx = low.index(phrase)
                preceding = low[max(0, idx - 120):idx]
                assert ("do not" in preceding or "never" in preceding), (
                    f"{title} / {section.heading}: brief presumes {phrase!r}. Generation "
                    "enforces no chain state, so this can manufacture an endorsement that "
                    "never happened.")

    @pytest.mark.parametrize("code", ["R4P1_D13", "R4P1_D14"])
    def test_the_downstream_reports_forbid_claiming_an_acceptance(self, code):
        """Not merely 'does not presume' -- the two documents written after the chain has
        supposedly progressed must actively TELL the writer not to claim it.
        """
        briefs = " ".join(s.brief.lower() for s in templates.template_for(code))
        assert "do not state or imply that any earlier document has been accepted" in briefs

    @pytest.mark.parametrize("code,title", CHAIN)
    def test_no_brief_weakens_the_never_assert_funding_line(self, code, title):
        """Where a brief raises financing, it must keep institutions PROSPECTIVE."""
        for section in templates.template_for(code):
            low = section.brief.lower()
            if "financing institution" in low or "financiers" in low:
                assert "prospective" in low or "never state" in low, (
                    f"{title} / {section.heading}: raises financing institutions without "
                    "holding the line that none has committed anything")


class TestTheSafetyCheckDoesNotBlockTheBusinessCase:
    """The guard must stop liability claims WITHOUT making the required options comparison
    impossible to write.

    FOUND ON LIVE, 2026-07-18, with a real model behind a real key: the Business Case's
    options section was rejected outright because it contained "sponsor-funded grant
    programme". That phrase names a CATEGORY OF OPTION -- and xx201 s6 requires exactly that
    option to be compared -- so the guard made the mandatory comparison unwritable and the
    Business Case failed every single time. The classification shipped earlier the same day is
    what identified it as OUR refusal rather than a provider outage.
    """

    @pytest.mark.parametrize("phrase", [
        "a sponsor-funded grant programme",
        "donor-funded schemes are unsustainable at scale",
        "grant-funded installations create subsidy dependence",
        "self-funded purchase by each shop",
        "the bank-financed aggregated programme is preferred",
    ])
    def test_an_option_category_is_not_a_liability_claim(self, phrase):
        assert not _SETTLED_CLAIM_RE.search(phrase), (
            f"{phrase!r} names a kind of arrangement, not a claim about this programme")

    @pytest.mark.parametrize("dash,name", [
        ("-", "ASCII hyphen-minus"),
        ("‐", "hyphen"),
        ("‑", "non-breaking hyphen"),   # THE ONE THAT ACTUALLY BIT
        ("‒", "figure dash"),
        ("–", "en dash"),
        ("—", "em dash"),
        ("−", "minus sign"),
    ])
    def test_every_dash_form_compounds_not_only_the_ascii_one(self, dash, name):
        """THE SECOND BUG, and the more instructive one.

        Fixing this with an ASCII-only `(?<!-)` did NOT work, and the live re-run proved it:
        the model writes "sponsor‑funded" with a NON-BREAKING HYPHEN. To a regex that is
        a different character entirely, so an ASCII-only exemption exempts nothing. Models
        emit typographic dashes routinely -- any guard that reasons about hyphenation has to
        know the whole family or it is guarding a form nobody writes.
        """
        assert not _SETTLED_CLAIM_RE.search(f"a sponsor{dash}funded grant programme"), (
            f"U+{ord(dash):04X} ({name}) is not treated as compounding")

    @pytest.mark.parametrize("phrase", [
        "the World Bank approved funding on 1 July 2026",
        "the programme is funded by the Ministry of Energy",
        "the facility was approved last week",
        "the sponsor decided to proceed",
        "financing was authorised",
        "the works have been contracted",
    ])
    def test_a_real_liability_claim_is_still_caught(self, phrase):
        """The exemption is a hyphen and nothing more. If this ever goes quiet, a document can
        tell a sponsor money is in place when it is not -- the failure this guard exists for.
        """
        assert _SETTLED_CLAIM_RE.search(phrase), f"{phrase!r} must not pass the guard"


class TestAppendingDidNotRepointAnything:
    """The property that makes adding deliverables safe at all."""

    @pytest.mark.parametrize("code,expected", [
        ("R4P1_D01", "Programme Concept Note"),
        ("R4P1_D02", "Problem Statement"),
        ("R4P1_D09", "Programme Charter"),
        ("R4P1_D12", "Programme Approval Request"),
    ])
    def test_pre_existing_codes_still_name_the_same_deliverable(self, code, expected):
        """If this fails, every document already stored under these codes now claims to be a
        different deliverable than the one that wrote it. That is unrecoverable without a
        data migration, which is why the lists are append-only.
        """
        assert rev4_phases.DELIVERABLE_INDEX[code][1] == expected

    def test_the_new_codes_are_at_the_end(self):
        codes = [c for c, _t in rev4_phases.PHASE_DELIVERABLES["R4_INITIATION"]]
        assert codes[-2:] == ["R4P1_D13", "R4P1_D14"], (
            "the new deliverables must be appended, never inserted")


class TestTheChainIsNotFourCopiesOfOneDocument:
    """A business case that restates the concept note is the failure mode to avoid."""

    def test_the_four_reports_have_substantially_different_shapes(self):
        shapes = {code: {s.heading for s in templates.template_for(code)}
                  for code, _t in CHAIN}
        for a_code, a in shapes.items():
            for b_code, b in shapes.items():
                if a_code >= b_code:
                    continue
                overlap = len(a & b) / min(len(a), len(b))
                assert overlap < 0.5, (
                    f"{a_code} and {b_code} share {overlap:.0%} of their headings -- "
                    "these are meant to be different documents")

    def test_the_business_case_actually_compares_options(self):
        """A business case with one option is an assertion, not a case. xx201 s6 requires the
        options comparison explicitly.
        """
        headings = " ".join(s.heading.lower()
                            for s in templates.template_for("R4P1_D13"))
        assert "option" in headings

    def test_the_business_case_ends_in_a_decision(self):
        """xx10 s15: every report must terminate in a decision."""
        last = templates.template_for("R4P1_D13")[-1]
        assert "recommend" in last.heading.lower() or "decision" in last.heading.lower()

    def test_the_programme_plan_stays_out_of_the_planning_phase(self):
        """xx201 s32: "do not introduce detailed Planning Phase activities yet". The plan
        closes Initiation; it does not replace the phase that follows it.

        Asserted on SHAPE, not on an exact sentence. Codex (2026-07-18) flagged the earlier
        substring assertion as brittle -- it would have failed on a harmless rewording while
        still passing on a plan that had genuinely sprawled into Planning-phase detail.
        """
        plan = templates.template_for("R4P1_D14")

        # A plan that had sprawled into Planning would carry that phase's own deliverables as
        # its section headings. Initiation's plan must not.
        planning_titles = {t.lower() for _c, t
                           in rev4_phases.PHASE_DELIVERABLES["R4_PLANNING"]}
        for section in plan:
            assert section.heading.lower() not in planning_titles, (
                f"{section.heading!r} is a Planning-phase deliverable, not a section of the "
                "Initiation programme plan")

        # And it must still say the schedule is indicative rather than committed.
        schedule = [s for s in plan if s.topic == "schedule"]
        assert schedule, "the plan must cover sequencing"
        assert any("indicative" in s.brief.lower() for s in schedule), (
            "the plan's schedule must be labelled indicative at Initiation stage")
