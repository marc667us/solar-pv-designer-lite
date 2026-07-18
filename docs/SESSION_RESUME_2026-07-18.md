# Where to start — handover from the session of 18 July 2026

Written at the close of that session, for whoever picks the work up next.

---

## Where the app stands

SolarPro is live at `solarpro.aiappinvent.com` on commit **`b5d8c9d`**, deployed at 22:03 UTC
and healthy — the boot probe reports the database ready and `/login` returns 200. The
enterprise test suite is fully green at **631 passing**. Nothing is half-applied, nothing is
sitting unpushed, and no rollback is pending. If you do nothing at all, the app keeps working.

That is worth stating plainly, because the session before this one ended with a live login
outage, and it is easy to open a session braced for a fire that is no longer burning.

---

## The problem this session was about, and what it actually turned out to be

For several sessions the owner had been reporting the same failure: they press the button to
generate an enterprise programme document, and the app tells them **"the document writer is not
available."** It had been treated as a bug in the writer more than once, and fixed more than
once, and it kept coming back.

It was not a bug. It was a **ceiling**.

The enterprise module writes documents by asking a language model to draft each section. The
provider is OpenRouter on its free tier, and that tier allows **fifty requests per day** on this
account. The provider says so in its own words when you exhaust it:

> `Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day`

with `X-RateLimit-Limit: 50` and `Remaining: 0`. All five models in the fallback chain returned
429, because the limit is on the account, not the model.

Because the code asked for **one section per call**, a ten-section concept note consumed ten of
the fifty. That put a hard ceiling of roughly **five documents a day** on the entire platform —
after which every attempt, by anyone, reported the writer as unavailable until the daily reset.
The owner, testing the module repeatedly, was hitting that ceiling most days and reading it as a
broken feature.

The writing itself was never broken. When quota was available it produced genuine
ministry-register prose with properly labelled assumptions. The owner reached the same
conclusion independently and said so: *"rate limiter blocking the writing service."*

---

## What was done about it

Paying was off the table — the zero-cost rule stands, and the owner explicitly declined the
$10-for-1000-requests option. With price fixed, the only remaining lever is to **ask for less**.

Sections are now written **four to a call**. A concept note costs three calls instead of ten,
which takes the daily ceiling from about five documents to about **sixteen** at no cost. The
business case costs two calls, the programme plan three.

It is built as a **prefetch that fills a cache the existing section loop reads from**, rather
than as a rewrite of that loop. This matters if you go near it: the deduplication guard, the
automatic retry, the visible "could not be written" markers and the precedence of uploaded
source passages all still work exactly as they did, untouched. A heading the batch fails to
return simply falls through to the old one-section-at-a-time path. The optimisation can fail
completely and the feature still works — it just costs more quota.

It is deliberately **not** one call for the whole document. Free models run at roughly 26
tokens/second against gunicorn's 300-second ceiling, so a single giant call would routinely be
killed mid-write. That would trade a quota failure for a timeout failure, which is worse
because it produces nothing at all. Four is the largest batch that fits comfortably.

---

## Three things that went wrong on the way, worth knowing about

**Codex caught a critical defect that would have shipped.** The first version populated the
batch cache and never read it. A document would have cost three batch calls *plus* ten
individual ones — strictly worse than the bug being fixed, and the exact opposite of the
change's purpose. Every one of the ten unit tests passed while this was true, because they all
tested the splitting mechanism and none of them counted calls through the real loop. The lesson
is worth carrying: **when the point of a change is a number, assert that number end to end.**
The fix added two integration tests that count provider calls through `build_markdown` itself,
and both were mutation-checked by reintroducing the bug to confirm they fail.

**The "no fake report" guarantee had sprung a leak.** The guard that refuses to save an empty
document compared the count of unwritten sections against the total. That was equivalent to
"the writer produced nothing" only while every section got its own call and its own retry. Once
the prefetch could spend part of the AI budget, a total outage burned the allowance on the early
sections, left the later ones never attempted, and let them quietly take the deterministic
fallback path — so the unwritten count came up short of the total and **a document containing no
written prose would have been saved.** That is precisely the fake report the owner rejected on
16 July, arriving through a side door. The guard now counts sections the writer actually wrote,
which does not depend on how the budget happened to be spent.

**The reply splitter could truncate silently.** It matched its section marker anywhere in the
text, so prose that merely mentioned the marker deleted the remainder of its own section with no
error. Markers are now anchored to their own line and matched only against requested headings.

---

## The honest gap

**The batching has not been confirmed against a real document generation.** The measurements are
from tests, not from live. Today's quota was in all likelihood already spent by the owner's
testing, so no clean end-to-end run was observed before the session closed.

Treat "sixteen documents a day" as *expected*, not *proven*.

---

## Start here

**Ask the owner one question before touching any code: did a report generate cleanly?**

The answer forks three ways, and they are genuinely different faults — guessing between them has
already cost a cycle on this exact feature:

- **It worked.** Close the item, note the confirmation, and pick the queue back up at CDC.
- **"Writer unavailable" again.** The quota is still the binding constraint. Check whether the
  key was rotated (a new key resets the daily allowance) before assuming a code fault. If quota
  is genuinely available and it still fails, the failure reason is now classified into nine
  specific buckets by `api_manager.classify_ai_failure` — read the actual reason rather than
  theorising.
- **It generated, but the prose is wrong or a section is missing/blank.** That is the splitter or
  the safety guard, not quota. Reach for `tests/enterprise_programme/test_batched_sections.py`
  first; it covers reordering, omission, duplicate headings and markers appearing inside prose.

**One owner action is outstanding and it is worth chasing early:** the OpenRouter key needs
rotating, because it was exposed in a transcript. It cannot be done from here — creating a key
requires authenticating as the owner, and there is no provisioning key anywhere reachable
(all 28 GitHub secrets and the live Render environment were checked). Everything downstream is
built and dry-run verified green:

```
gh secret set OPENROUTER_API_KEY -b "sk-or-v1-NEW"          # owner runs this
gh workflow run "Render Rotate Leaked Secrets" -f keys="OPENROUTER_API_KEY" -f confirm=APPLY
```

Chase it early for a second reason beyond security: **a fresh key carries a fresh fifty-request
allowance**, so rotating clears a day that is already spent and unblocks testing immediately.

---

## Then the standing queue

Once the writer question is settled, the ranked backlog resumes where the outage displaced it:

1. **CDC** — owner-requested, not started. Was the next build before this interrupted it. The
   headline constraint is that there is no write chokepoint, so capture must happen in the
   database.
2. **RLS is `ENABLE`d but never `FORCE`d** on migrations 024–029, so every enterprise policy is
   inert. A missing second line of defence rather than an open door, but the module is live.
   **Do not apply `FORCE` blind** — it needs per-command policies or onboarding breaks. The
   design is already written up; do not re-derive it.
3. **Supervisor gate was never run on slice 7** — the four-gate bar is unmet there.
4. **Migration 035** (site assignments) is written and dry-run gated but not applied; it needs
   `-f confirm=APPLY_035`.
5. **Programme-scoped role granting still has no UI.**

---

## Small traps that cost time this session

- `_brief(facts)` reads `facts["name"]`, `["code"]` and `["phase_code"]` unconditionally. A
  fixture missing any of them fails *inside* the writer, and the broad `except` swallows it into
  a silent empty result.
- The enterprise feature flag lives in `admin_settings`, not a `feature_flags` table, and tests
  must also call `register_enterprise_programme(...)`.
- It is `document_templates.template_for(code)`. There is no `sections_for`.
- Tests need `SOLARPRO_ADMIN_PASSWORD` and `SOLARPRO_OWNER_PASSWORD` set or `init_db()` raises —
  roughly 88 suite errors trace to that alone.
- There is no `OPENROUTER_API_KEY` in the local environment, so **local test runs do not consume
  the daily quota.** Worth re-confirming before running anything that exercises `use_ai=True`.
- `gh` is not on PATH in the Bash tool; use `"$USERPROFILE/bin/gh.exe"`.
