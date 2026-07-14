# The beneficiary application flow — owner spec, 2026-07-14

Captured verbatim from the owner, then read back as a design. **Nothing here is built yet.**

## The owner's words

> "we don't need to do proving to any entity rather the beneficiaries must register for the
> program and track progress from when they submit app to when their approved"

> "sample flow is the programme developer must invite the beneficiary organisation to
> register, the program initiation must be submitted to the contact person to approve the
> program, same thing must be done to the programme sponsor. The users of the beneficiary must
> register via their organisation platform and applications must be submitted through the
> organisation. the first level of application is the beneficiary organisation, the programme
> level approval and finally sponsor level approval"

> "users must select their preferred sponsors"

> "check my bill must be run for each user automatically after their application to make sure
> they can pay load"

> "all approvals must be set by the individual approving entities"

## Each entity approves for itself — and ONLY for itself

A **hard rule**, and the exact opposite of the stage-gate owner override (`5417e53`, where the
owner may sign a gate in another post's place). That override is scoped to **stage gates** and
must **not** leak into this chain.

- **Level 1** may be set only by the **beneficiary organisation**.
- **Level 2** may be set only by the **programme**.
- **Level 3** may be set only by the **sponsor**.

Nobody approves on another entity's behalf — not the programme developer, not the platform
owner. An approval chain in which one party can set all three levels is not a chain; it is one
signature wearing three hats. A sponsor who later asks "did the beneficiary organisation
actually vouch for this applicant?" would get an answer that means nothing.

## What that is, structurally

This **re-centres the module**. The lifecycle/gates machinery was built to prove a programme's
governance to an auditor. The owner has now said that is not the job. The job is a
**three-party application pipeline**, and the thing that must be tracked is **an applicant's
progress from submission to approval**.

### The parties

| Party | Who they are | What they do |
|---|---|---|
| **Programme developer** | the organisation running the programme (today's `enterprise_tenants` owner) | invites beneficiary organisations; approves at programme level |
| **Beneficiary organisation** | a school district, a hospital group, a co-operative | registers on invitation; its **contact person** approves the programme; approves its own users' applications |
| **Beneficiary user** | an individual household/site inside that organisation | registers **via their organisation**; submits an application |
| **Sponsor** | a funding institution, from the EXISTING `financial_institutions` registry | approves the programme; gives **final** approval on applications |

### The two approval chains

**1. Approving the PROGRAMME itself** (runs once, at initiation)

```
programme developer  ──invites──▶  beneficiary organisation
        │                                   │
        │                          contact person APPROVES the programme
        │
        └──submits initiation──▶  sponsor  APPROVES the programme
```

**2. Approving an APPLICATION** (runs per beneficiary user)

```
beneficiary user submits application
        │  (through their organisation — not directly to the programme)
        ▼
  LEVEL 1  beneficiary organisation approves
        ▼
  LEVEL 2  programme approves
        ▼
  LEVEL 3  sponsor approves        ── final
```

The applicant can **see exactly where they are** in that chain at any moment. That tracking
view is the feature, not a by-product of it.

### The automatic affordability check

> "check my bill must be run for each user automatically after their application to make sure
> they can pay load"

On submission, the existing **Check-My-Bill** engine runs against the applicant's stated load
and tariff, and the result is attached to the application. It is **evidence for the level-1
reviewer**, not a gate: an applicant who cannot afford the load is flagged, not silently
rejected. (Check-My-Bill already exists at `/bill-check` — reuse it, do not rebuild it.)

## What already exists and MUST be reused

The owner was explicit: *"look, check and reuse the funding in the standard design and reuse."*

| Need | Reuse | Do NOT build |
|---|---|---|
| Sponsor register | `financial_institutions` (Project Funding module, 2026-07-05) — already has `loan_min`, `loan_max`, `tenor_months`, `interest_min/max`, `fee_pct`, `status='approved'` | a second `enterprise_sponsors` table (one was written and deleted) |
| Affordability | the Check-My-Bill engine behind `/bill-check` | a new affordability calculator |
| Beneficiary/site records | `enterprise_beneficiary_register` + qualification + priority list | a parallel applicant table, if the existing one can carry an application status |
| Sponsor selection | `app/enterprise_programme/sponsors.py` (written, not yet wired) — first/second/third sponsor, chosen from the approved registry | |

## Open questions to settle before building

1. **Does a beneficiary user get a SolarPro login?** "register via their organisation platform"
   suggests yes — a user account scoped to the beneficiary organisation's tenant. That means
   the beneficiary organisation is itself an `enterprise_tenant`, and the programme developer's
   invitation creates it. Needs confirming: it decides the whole permission model.
2. **Can an application be rejected at level 1, or only returned for more information?**
3. **Does the sponsor see the applicant's affordability result?** (Probably yes — it is why the
   check is run.)
4. **What does the applicant see while waiting** — the level they are at, or also who is
   sitting on it?

## Status

- ✅ Governance loosened to advisory (`ff954a7`+) — this flow needs the gates out of the way.
- ✅ `sponsors.py` written: first/second/third sponsor from the approved funding registry.
  **Not yet wired to a route.**
- ✅ `migrations/030_enterprise_programme_sponsors.sql` — three TEXT columns on the registry.
  **Not yet applied.**
- ⬜ Everything above.
