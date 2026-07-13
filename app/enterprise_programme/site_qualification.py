"""Enterprise Solar Programme -- site qualification (rebuild, slice 6).

WHAT QUALIFICATION IS
---------------------
The act that turns "this school is in our register" into "this school will get a system".
Doc 3 (Phase 3, Gate 3) scores every candidate site on eight categories and ranks them into a
priority list, because a programme has a budget and a register that always exceeds it. The
scores are how a ministry answers the only question that matters politically: *why that
village and not mine?*

SCORING AND DECIDING ARE TWO DIFFERENT ACTS BY TWO DIFFERENT PEOPLE
-------------------------------------------------------------------
`qualification.score`   -- a surveyor, a GIS specialist, a district coordinator. They went and
                           looked. They record what they found.
`qualification.approve` -- a programme manager, a regional manager. They decide the programme
                           will serve it.

The same separation as register-vs-approve in slice 5, for the same reason: the person who
measures must not be the person who chooses, or the measurement becomes an argument for a
choice already made. Concretely, `decide()` refuses to act on a site nobody has scored -- and
THAT is the whole substance of control C02 ("no beneficiary becomes a project without
qualification"). Without it, C02 would be a status anyone could type.

THE DECISION IS THE ONLY WAY INTO "Qualified"
---------------------------------------------
`beneficiaries.transition_beneficiary` still refuses to hand-wave a site into Qualified or Not
Qualified. This module is the sole writer of those two statuses, and it writes them in the
same transaction as the scorecard that justifies them. So a Qualified beneficiary always has a
scorecard behind it, and slice 7's C02 check can trust the status.

WHY HIGHER IS ALWAYS BETTER
---------------------------
All eight scores are 0-100 and higher is always more favourable -- including the two doc 3
calls "risk", where 100 means NO risk. Reading those two the other way round would rank the
most dangerous and least accessible sites at the TOP of the priority list, and nothing would
look wrong: the list would just quietly send the money to the wrong villages. See
constants.QUALIFICATION_CRITERIA.
"""

from __future__ import annotations

import json

from . import rbac, tenancy, txn
from .constants import (
    QUALIFICATION_CRITERIA,
    QUALIFICATION_CRITERION_KEYS,
    QUALIFICATION_DECISIONS,
    QUALIFICATION_SCORE_MAX,
    QUALIFICATION_SCORE_MIN,
)
from .gates import EnterpriseGateError

_CRITERION_KEYS = frozenset(QUALIFICATION_CRITERION_KEYS)
_WEIGHTS: dict[str, int] = {c["key"]: c["weight"] for c in QUALIFICATION_CRITERIA}

# ONLY a site awaiting a decision may be scored -- Qualification Pending, and nothing else.
#
# A REFUSED site must be RE-ADMITTED before it is re-surveyed (BENEFICIARY_TRANSITIONS sends
# Not Qualified -> Qualification Pending, and that transition needs `beneficiary.approve`).
# Letting a scorer write straight onto a Not Qualified site looked like a convenience and was
# a trap (Codex slice-6 round 2): the new scores cleared the refusal, but the STATUS stayed
# Not Qualified -- and decide() only acts on a Pending site, so it refused to touch it. The
# site ended in limbo: refused, with no record of WHY it was refused, and no way to decide it
# again. Re-admission is a deliberate act by somebody entitled to make it, not paperwork to be
# routed around.
#
# A QUALIFIED site may never be re-scored: a template may already be assigned and a project
# being generated from it, and changing the justification underneath a decision already being
# acted on is how the register comes to disagree with what is actually being built. Same
# freeze reasoning as a template version leaving Draft (slice 4).
_SCOREABLE_STATUSES = frozenset({"Qualification Pending"})


class QualificationError(EnterpriseGateError):
    """A qualification rule was broken. Carries a control code so a route can 404 a C13."""


def _is_integrity_error(e: Exception) -> bool:
    """Is this a UNIQUE / CHECK / FK violation, on either driver?

    Matched by CLASS NAME rather than by importing psycopg2.IntegrityError, which is not
    installed in the SQLite dev environment. Both drivers name it `IntegrityError`
    (DB-API 2.0 requires it).
    """
    return any(k.__name__ == "IntegrityError" for k in type(e).__mro__)


def _require_audit(wrote, what: str) -> None:
    """C12 -- audit or nothing. The audit row commits in the same transaction as the act."""
    if not wrote:
        raise QualificationError(
            "C12", f"the {what} was not written because its audit record could not be"
        )


# --- reading -----------------------------------------------------------------


def _load_beneficiary(c, tenant_id: str, beneficiary_id: int) -> dict:
    """The site, IN THIS TENANT, or C13 (which the routes turn into a 404, never a 403)."""
    row = c.execute(
        "SELECT id, programme_id, code, name, status FROM enterprise_beneficiary_register "
        " WHERE tenant_id=? AND id=?",
        (tenant_id, beneficiary_id),
    ).fetchone()
    if row is None:
        raise QualificationError("C13", "no such beneficiary in this organisation")
    return {"id": row[0], "programme_id": row[1], "code": row[2], "name": row[3],
            "status": row[4]}


def _decode(raw, fallback):
    """psycopg2 hands back a decoded jsonb; SQLite hands back the TEXT we stored."""
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw) if raw else fallback
    except (TypeError, ValueError):
        return fallback


def get_qualification(c, tenant_id: str, beneficiary_id: int) -> dict | None:
    """The site's scorecard, or None if nobody has surveyed it yet."""
    _load_beneficiary(c, tenant_id, beneficiary_id)          # C13 FIRST
    row = c.execute(
        "SELECT id, beneficiary_id, scores_json, total_score, decision, survey_notes, "
        "       scored_by_user_id, scored_at, decided_by_user_id, decided_at, "
        "       decision_notes, revision "
        "  FROM enterprise_site_qualifications "
        " WHERE tenant_id=? AND beneficiary_id=?",
        (tenant_id, beneficiary_id),
    ).fetchone()
    if row is None:
        return None
    scores = _decode(row[2], {})
    return {
        "id": row[0], "beneficiary_id": row[1], "scores": scores,
        "total_score": float(row[3]) if row[3] is not None else None,
        "decision": row[4],
        "survey_notes": row[5] or "",
        "decision_notes": row[10] or "",
        "revision": row[11],
        "scored_by_user_id": row[6], "scored_at": row[7],
        "decided_by_user_id": row[8], "decided_at": row[9],
        # Rendered for the form: every criterion, in doc-3 order, with what was recorded.
        "rows": [dict(crit, score=scores.get(crit["key"])) for crit in QUALIFICATION_CRITERIA],
    }


def priority_list(c, tenant_id: str, programme_id: int, *,
                  limit: int = 500) -> tuple[list[dict], bool]:
    """The programme's sites, best-scoring first -- doc 3's "Priority list" deliverable.

    Input:  connection, tenant id, programme id, a row cap.
    Output: (list of dicts -- beneficiary + total_score + decision, highest score first;
             whether the list was CAPPED).

    Unscored sites sort LAST rather than being hidden: a site nobody has been to is not the
    same as a site that scored zero, and dropping it from the list is how it stays unvisited
    forever. It appears at the bottom with no score, which is a question, not an answer.

    WHICH IS EXACTLY WHY THE CAP IS RETURNED, NOT SWALLOWED (Supervisor slice-6, MED). The
    cap and the sort order compound: because unscored sites sort last, a 4000-site programme
    rendering its first 500 rows drops the lowest-ranked sites AND EVERY UNVISITED ONE -- the
    precise rows this page exists to make visible -- while looking complete. The caller is
    told, and the page says so.
    """
    rows = c.execute(
        "SELECT b.id, b.code, b.name, b.beneficiary_type, b.status, b.community, b.district, "
        "       q.total_score, q.decision "
        "  FROM enterprise_beneficiary_register b "
        "  LEFT JOIN enterprise_site_qualifications q "
        "         ON q.tenant_id = b.tenant_id AND q.beneficiary_id = b.id "
        " WHERE b.tenant_id=? AND b.programme_id=? "
        # NULLs last, without relying on NULLS LAST (Postgres has it; SQLite does not).
        " ORDER BY CASE WHEN q.total_score IS NULL THEN 1 ELSE 0 END, "
        "          q.total_score DESC, b.id ASC "
        " LIMIT ?",
        # One more than asked for, so "there is more" is a fact rather than a guess: at
        # exactly `limit` rows, len(rows) == limit is indistinguishable from a full list.
        (tenant_id, programme_id, int(limit) + 1),
    ).fetchall()
    capped = len(rows) > int(limit)
    rows = rows[:int(limit)]
    out = []
    for i, r in enumerate(rows, start=1):
        out.append({
            "rank": i if r[7] is not None else None,
            "id": r[0], "code": r[1], "name": r[2], "beneficiary_type": r[3],
            "status": r[4], "community": r[5] or "", "district": r[6] or "",
            "total_score": float(r[7]) if r[7] is not None else None,
            "decision": r[8],
        })
    return out, capped


def count_qualified(c, tenant_id: str, programme_id: int) -> int:
    """How many sites the programme has actually decided to serve. Gate 3 evidence."""
    row = c.execute(
        "SELECT COUNT(*) FROM enterprise_beneficiary_register "
        " WHERE tenant_id=? AND programme_id=? AND status IN "
        "       ('Qualified', 'Template Assigned', 'Project Generated')",
        (tenant_id, programme_id),
    ).fetchone()
    return int(row[0]) if row else 0


# --- validation --------------------------------------------------------------


def validate_scores(raw: dict) -> tuple[dict, list[str]]:
    """Coerce and check the eight scores. Reports EVERY problem at once; never raises.

    Input:  {criterion key -> value} as it came off a form (so: strings, blanks, junk).
    Output: (clean scores, problems). Clean is complete -- all eight keys -- or problems
            is non-empty.

    ALL EIGHT ARE REQUIRED. A partial scorecard would produce a total score that looks like
    every other total score while meaning something else entirely (a site scored on three
    categories out of eight is not "37 out of 100", it is unscored), and it would then be
    ranked against sites that were fully assessed.
    """
    clean: dict[str, float] = {}
    problems: list[str] = []

    unknown = sorted(set(raw or {}) - _CRITERION_KEYS)
    for key in unknown:
        problems.append(f"{key!r} is not a qualification criterion")

    for crit in QUALIFICATION_CRITERIA:
        key = crit["key"]
        value = (raw or {}).get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            problems.append(f"{crit['label']} has no score")
            continue
        try:
            score = float(value)
        except (TypeError, ValueError):
            problems.append(f"{crit['label']}: {value!r} is not a number")
            continue
        # NaN and Infinity are floats and would sail through a bare range check -- and a NaN
        # total sorts unpredictably, so one junk cell would scramble the priority list.
        if score != score or score in (float("inf"), float("-inf")):
            problems.append(f"{crit['label']}: {value!r} is not a number")
            continue
        if not (QUALIFICATION_SCORE_MIN <= score <= QUALIFICATION_SCORE_MAX):
            problems.append(
                f"{crit['label']}: {score:g} is outside "
                f"{QUALIFICATION_SCORE_MIN}-{QUALIFICATION_SCORE_MAX}"
            )
            continue
        clean[key] = score

    return clean, problems


def total_of(scores: dict) -> float:
    """The overall priority score: the weighted mean, 0-100.

    The weights sum to 100 (asserted at import), so this IS a percentage and can be printed
    as one without further apology.
    """
    return round(
        sum(float(scores[k]) * _WEIGHTS[k] for k in QUALIFICATION_CRITERION_KEYS) / 100.0, 2
    )


# --- writing -----------------------------------------------------------------


def score_site(c, tenant_id: str, user_id: int, beneficiary_id: int, *,
               scores: dict, notes: str = "", audit=None) -> dict:
    """Record what the survey found. Does NOT decide anything.

    Input:  connection, tenant id, acting user, beneficiary id, the eight scores, notes.
    Output: the saved scorecard.
    Raises: EnterprisePermissionError (403), QualificationError (409 / C13).

    Scoring a site again OVERWRITES its scorecard -- one site, one answer (the unique index on
    (tenant_id, beneficiary_id) makes that structural, not a convention). The previous scores
    are not lost: every score writes an audit row carrying them.

    A RE-SURVEY SUPERSEDES A STALE REFUSAL. If the site was refused, sent back (its status is
    Qualification Pending again) and surveyed afresh, the new scorecard clears the old
    decision -- otherwise `decide()`'s "already decided" guard would match the dead refusal
    and the site could NEVER be decided again. The documented re-survey path would be a
    dead end that looks like a permissions problem (Codex slice-6, and it is why the
    guarded UPDATE below admits a 'Not Qualified' card but never a 'Qualified' one).
    """
    site = _load_beneficiary(c, tenant_id, beneficiary_id)        # C13 FIRST, before authz
    rbac.require_permission(c, tenant_id, user_id, "qualification.score",
                            programme_id=site["programme_id"])

    if site["status"] not in _SCOREABLE_STATUSES:
        raise QualificationError(
            "QUALIFICATION",
            f"this site is {site['status']}; only a site awaiting a decision can be scored "
            f"({', '.join(sorted(_SCOREABLE_STATUSES))})",
        )

    clean, problems = validate_scores(scores)
    if problems:
        raise QualificationError("QUALIFICATION", "; ".join(problems))

    total = total_of(clean)
    notes = (notes or "").strip()
    audit = audit or txn.audit_on(c)
    params = (json.dumps(clean), total, notes, user_id, tenant_id, beneficiary_id)

    def _guarded_update():
        """The survey write. Refuses a QUALIFIED card, and bumps the revision.

        A stale 'Not Qualified' card IS admitted here, and its decision cleared -- but only
        because the status check above has already proved the site was RE-ADMITTED to
        Qualification Pending, and that transition takes `beneficiary.approve`. So the refusal
        being cleared is one a manager has already agreed to revisit. WITHOUT that status
        check this clause was the limbo Codex found (scores rewritten on a still-refused site,
        decision erased, and decide() then refusing to touch it because it was not Pending).
        WITH it, this is simply the re-survey path.

        A 'Qualified' card is never touched: a project may already be being generated from it.
        """
        return c.execute(
            "UPDATE enterprise_site_qualifications "
            "   SET scores_json=?, total_score=?, survey_notes=?, scored_by_user_id=?, "
            "       scored_at=CURRENT_TIMESTAMP, revision=revision+1, "
            "       decision=NULL, decided_by_user_id=NULL, decision_notes=NULL, "
            "       decided_at=NULL "
            " WHERE tenant_id=? AND beneficiary_id=? "
            "   AND (decision IS NULL OR decision='Not Qualified')",
            params,
        )

    with txn.atomic(c):
        # THE WHERE CLAUSE IS THE LOCK (Codex slice-6, HIGH). The status check above ran
        # BEFORE the transaction, so a manager can approve the site in the gap between it and
        # this write -- and an unguarded UPDATE would then rewrite the scorecard UNDERNEATH a
        # decision already made, leaving a Qualified site whose evidence is not the evidence
        # anybody approved. So the write itself refuses to touch a card that has been
        # Qualified, and we check that it actually landed.
        #
        # 'Not Qualified' IS admitted, and the decision is cleared: that is a re-survey of a
        # site the programme previously turned away, which is exactly what doc 3's re-entry
        # path is for.
        cur = _guarded_update()
        if getattr(cur, "rowcount", 0) == 0:
            # Either there is no scorecard yet, or there is one that has been Qualified. Tell
            # those two apart before deciding what to do -- one is an INSERT, the other is a
            # conflict we must refuse.
            existing = c.execute(
                "SELECT decision FROM enterprise_site_qualifications "
                " WHERE tenant_id=? AND beneficiary_id=?",
                (tenant_id, beneficiary_id),
            ).fetchone()
            if existing is not None:
                raise QualificationError(
                    "QUALIFICATION",
                    "this site was approved while the survey was being saved; its scorecard "
                    "is the evidence for that decision and can no longer be changed",
                )
            try:
                # A SAVEPOINT, NOT A BARE INSERT (Codex slice-6 round 2, MED). On PostgreSQL an
                # IntegrityError ABORTS THE WHOLE TRANSACTION: every later statement then fails
                # with "current transaction is aborted", so the retry below would have died
                # instead of resolving the race -- and taken the audit row down with it.
                # Rolling back to a savepoint un-aborts the transaction, which is the only
                # reason the retry can run at all. SQLite does not need this. Postgres does,
                # and this module has to be identical on both.
                with txn.atomic(c):
                    c.execute(
                        "INSERT INTO enterprise_site_qualifications "
                        "(tenant_id, beneficiary_id, scores_json, total_score, survey_notes, "
                        " scored_by_user_id, scored_at, revision) "
                        "VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP,1)",
                        (tenant_id, beneficiary_id, json.dumps(clean), total, notes, user_id),
                    )
            except Exception as e:
                # Two surveyors saved the first scorecard for the same site at the same
                # moment. One INSERT wins; the other must not be a 500 (Codex slice-6, MED).
                # The unique index did its job -- retry the guarded UPDATE against the row
                # that now exists, and if THAT is refused it is because the winner's card has
                # already been approved, which is the conflict above.
                if not _is_integrity_error(e):
                    raise
                cur = _guarded_update()
                if getattr(cur, "rowcount", 0) == 0:
                    raise QualificationError(
                        "QUALIFICATION",
                        "this site was scored and approved by somebody else while this "
                        "survey was being saved",
                    ) from e

        _require_audit(
            audit("ENTERPRISE_SITE_SCORED", user_id=user_id, tenant_id=tenant_id,
                  details={"programme_id": site["programme_id"],
                           "beneficiary_id": beneficiary_id, "code": site["code"],
                           "scores": clean, "total_score": total}),
            "site score",
        )

    return get_qualification(c, tenant_id, beneficiary_id)


def decide(c, tenant_id: str, user_id: int, beneficiary_id: int, *,
           decision: str, notes: str = "", ai_recommendation_id: str | None = None,
           audit=None) -> dict:
    """Qualify a site, or refuse it. THE ONLY way a beneficiary reaches those two statuses.

    Input:  connection, tenant id, acting HUMAN, beneficiary id, "Qualified"/"Not Qualified",
            notes, the id of any AI recommendation being acted on.
    Output: the scorecard, now decided.
    Raises: EnterprisePermissionError (403), QualificationError (409 / C11 / C13 / C02).

    CONTROL C02 LIVES HERE. A decision on a site nobody has scored is refused -- that is what
    "no beneficiary becomes a project without qualification" actually means in code, and it is
    the reason slice 7 can trust the Qualified status without re-litigating it.

    CONTROL C11: an AI may recommend a decision and a human may act on it, but the human is
    the decider and their user id is what goes in the audit row. Checked FIRST, before the
    record is even loaded: it touches no database and leaks nothing.

    The scorecard and the beneficiary's status are written in ONE transaction. If they could
    drift apart, "Qualified" would stop meaning "has a scorecard saying so".
    """
    from . import gates as gates_mod
    gates_mod.require_human_approval_actor(user_id, ai_recommendation_id)     # C11 FIRST

    site = _load_beneficiary(c, tenant_id, beneficiary_id)                    # C13 next
    rbac.require_permission(c, tenant_id, user_id, "qualification.approve",
                            programme_id=site["programme_id"])

    if decision not in QUALIFICATION_DECISIONS:
        raise QualificationError(
            "QUALIFICATION",
            f"{decision!r} is not a decision ({', '.join(QUALIFICATION_DECISIONS)})",
        )

    if site["status"] != "Qualification Pending":
        raise QualificationError(
            "QUALIFICATION",
            f"this site is {site['status']}; only a site that is Qualification Pending "
            "can be decided",
        )

    existing = get_qualification(c, tenant_id, beneficiary_id)
    if existing is None or existing["total_score"] is None:
        raise QualificationError(
            "C02",
            "this site has not been scored: no beneficiary becomes a project without "
            "qualification, so there is nothing here to approve",
        )

    # A TOTAL IS NOT A SCORECARD (Codex slice-6, MED). C02 is the control that stops money
    # being spent on a site nobody assessed, so it asks to SEE the assessment rather than
    # trusting a number that claims one happened. A row carrying total_score=50 over an empty
    # scores_json would otherwise qualify a site on the strength of its own summary.
    missing = [k for k in QUALIFICATION_CRITERION_KEYS if existing["scores"].get(k) is None]
    if missing:
        raise QualificationError(
            "C02",
            "this site's scorecard is incomplete ("
            + ", ".join(sorted(missing))
            + "): a partial assessment is not an assessment",
        )

    # SEPARATION OF DUTIES IS A CONTROL, NOT A CONVENTION (Supervisor slice-6, MED).
    # "The person who measures must not be the person who chooses" was true only because the
    # DEFAULT role map happens to be disjoint -- surveyor scores, programme_manager approves.
    # But a user holds the UNION of their role assignments, and nothing stops an org_admin
    # granting one person both district_coordinator (qualification.score) and
    # programme_manager (qualification.approve). That person could then score a site 95/100
    # and immediately approve their own assessment, with every guard passing and the audit
    # trail showing scored_by == decided_by. The slice's headline guarantee would be a
    # configuration accident. So the rule is enforced on the ACT, where it cannot be
    # configured away.
    # ...EXCEPT THAT A CONTROL NEEDING TWO PEOPLE IS A DEADLOCK WHEN THERE IS ONE.
    #
    # In a tenant with exactly one active member, "ask another approver" names nobody. The
    # solo operator is the only person who can score a site and the only person who could
    # decide it, so the rule above does not separate two duties -- it stops the module
    # working at all. The live suite hit exactly this wall, and no permission or role grant
    # can get past it, because the wall is the actor's IDENTITY, not their authority.
    #
    # So the rule relaxes for a one-member tenant, and ONLY there. Note what does NOT
    # relax: C02 still demands a complete scorecard (checked above), C11 still demands a
    # human decision-maker, C12 still demands the audit row, C13 still demands the site be
    # in this tenant. The substance of C02 -- "no beneficiary becomes a project without a
    # qualification somebody is accountable for" -- is untouched. What is waived is a
    # two-person rule in an organisation that has one person, which was never a control
    # there in the first place. Both the Codex and Supervisor reviews independently
    # confirmed this is the one SoD rule that is safe to relax, and that the gate
    # authorities' named-role checks are NOT.
    #
    # It is computed from LIVE membership, never stored as a setting: the moment a second
    # person joins, this is False and the rule binds again, with nothing to remember to
    # turn back on. A tenant cannot configure its way out of separation of duties.
    sod_waived = False
    if existing["scored_by_user_id"] is not None \
            and existing["scored_by_user_id"] == user_id:
        if tenancy.is_solo_tenant(c, tenant_id):
            sod_waived = True
        else:
            raise QualificationError(
                "QUALIFICATION",
                "you scored this site, so you may not also decide it: the person who "
                "surveys a site is not the person who commits the programme to serving it. "
                "Ask another approver.",
            )

    decision_notes = (notes or "").strip()
    audit = audit or txn.audit_on(c)

    # THE APPROVAL IS PINNED TO THE SCORECARD THAT WAS READ (Supervisor slice-6, HIGH).
    # `existing` was read OUTSIDE the transaction. Guarding the write on `decision IS NULL`
    # alone leaves the mirror of the race Codex found: a surveyor's re-score can land in the
    # gap -- entirely legally, since the site is still Qualification Pending and undecided --
    # and the UPDATE would still match, qualifying the site on evidence NO APPROVER EVER SAW,
    # while the audit row below faithfully records the scores the approver DID see. The
    # database and its own audit trail would permanently disagree about why a site was
    # approved. So the write also NAMES the scorecard it is approving; if the evidence moved,
    # nothing matches and the manager is told to look again.
    #
    # It names it by REVISION, not by (total_score, scored_at) (Codex slice-6 round 2, MED):
    # SQLite's CURRENT_TIMESTAMP is second-resolution, and two different scorecards can share
    # a total -- 8 criteria can be shuffled to the same weighted mean. A re-score within the
    # same second, to different scores that happen to total the same, would have slipped
    # straight through a timestamp+total guard. A counter cannot be confused by either.
    seen_revision = existing["revision"]

    with txn.atomic(c):
        cur = c.execute(
            "UPDATE enterprise_site_qualifications "
            "   SET decision=?, decision_notes=?, decided_by_user_id=?, "
            "       decided_at=CURRENT_TIMESTAMP "
            " WHERE tenant_id=? AND beneficiary_id=? AND decision IS NULL "
            "   AND revision=?",
            (decision, decision_notes, user_id, tenant_id, beneficiary_id, seen_revision),
        )
        if getattr(cur, "rowcount", -1) == 0:
            # Either somebody decided it first, or the site was re-surveyed underneath us.
            # Both mean: what you are approving is not what you looked at.
            raise QualificationError(
                "QUALIFICATION",
                "this site was decided or re-surveyed while the decision was being "
                "recorded -- reload the scorecard and look again before approving it",
            )

        # The status moves in the SAME transaction, and only FROM the status we checked --
        # so two managers pressing Qualify and Reject at the same moment cannot both win.
        cur = c.execute(
            "UPDATE enterprise_beneficiary_register "
            "   SET status=?, updated_at=CURRENT_TIMESTAMP "
            " WHERE tenant_id=? AND id=? AND status='Qualification Pending'",
            (decision, tenant_id, beneficiary_id),
        )
        if getattr(cur, "rowcount", -1) == 0:
            raise QualificationError(
                "QUALIFICATION", "this site moved on while the decision was being recorded"
            )

        # THE APPROVALS LEDGER IS WHERE APPROVALS LIVE (Supervisor slice-6, MED). Every other
        # human approval in the module files one -- gate approvals, phase advances, template
        # versions, the register admission itself. This is the module's most consequential
        # approval (it is the moment a programme commits to spending money on a place), and it
        # was visible only inside an audit `details` blob. An auditor asking "who committed us
        # to this site, and on whose AI recommendation?" queries enterprise_approvals, where
        # ai_recommendation_id is a first-class column -- and would have found nothing.
        c.execute(
            "INSERT INTO enterprise_approvals "
            "(tenant_id, programme_id, subject_type, subject_id, approval_type, "
            " decision, decided_by_user_id, ai_recommendation_id, comment) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (tenant_id, site["programme_id"], "beneficiary", str(beneficiary_id),
             "site_qualification", decision, user_id, ai_recommendation_id,
             decision_notes),
        )

        _require_audit(
            audit("ENTERPRISE_SITE_QUALIFIED" if decision == "Qualified"
                  else "ENTERPRISE_SITE_NOT_QUALIFIED",
                  user_id=user_id, tenant_id=tenant_id,
                  details={"programme_id": site["programme_id"],
                           "beneficiary_id": beneficiary_id, "code": site["code"],
                           "decision": decision,
                           # The guarded UPDATE matched on exactly these, so this is not the
                           # scorecard we HOPE was approved -- it is the one that was.
                           "total_score": existing["total_score"],
                           "scores": existing["scores"],
                           "revision": seen_revision,
                           # WHY the programme turned a site away is the question an appeal
                           # asks, and a re-survey clears the column. Keep it in the trail.
                           "decision_notes": decision_notes,
                           "survey_notes": existing["survey_notes"],
                           "ai_recommendation_id": ai_recommendation_id,
                           # THE WAIVER IS PART OF THE RECORD, NOT A SILENT BRANCH.
                           # An auditor reading this row must be able to see that the same
                           # person scored and decided, and that the system knowingly
                           # permitted it because there was nobody else in the tenant. A
                           # control that quietly stops applying is indistinguishable from
                           # one that was never there; a control that says "waived, and
                           # here is why" is still doing its job.
                           "sod_waived": sod_waived,
                           "scored_by_user_id": existing["scored_by_user_id"]}),
            "qualification decision",
        )

    return get_qualification(c, tenant_id, beneficiary_id)
