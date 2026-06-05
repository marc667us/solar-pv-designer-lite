# SolarPro Global — Inbound Sales Call Pitch
## Ghana solar suppliers & installers — beta invitation campaign

**Audience:** Internal sales reps fielding return calls from Ghana solar companies who received the beta invite.
**Goal of the call:** Get the prospect to (a) create a free account, (b) book a 20-min onboarding demo, (c) name one live project we can design together as the first-touch deliverable.
**Average call length:** 8–12 minutes.

---

## 1. Before you dial — 90-second prep

Open the prospect's row in `data/ghana_beta_invitees.json` and skim:

| Field | Why it matters on the call |
|---|---|
| `roles` | Both supplier + installer? Lead with BOQ + design value. Installer only? Lead with design time-savings. Supplier only? Lead with referrals + catalog visibility. |
| `services` | Mirror their language — say "hybrid inverters" if they sell hybrid; say "lithium" if they push lithium. |
| `city` | "I see you're in Tesano / Madina / Lashibi — are you taking site visits in Ashanti this month?" creates instant rapport. |
| `notes` | Often holds the strongest hook — e.g. Deep Solar Ghana already has a quote app → they understand why a design SaaS matters. |

---

## 2. Opening (30 seconds)

> **"Hi, this is [name] from SolarPro Global. Thanks for calling back about the beta invite. Quick context before I take any of your time — we built SolarPro because solar designers in Ghana spend 4 to 6 hours per proposal on PV sizing, BOQ, and bankable reports. We've cut that to under 30 minutes, and we're inviting 15 Ghana companies into a free beta. Have you got 8 minutes for me to walk you through what's in it for [Company Name]?"**

**Why this works:**
- Names a number (4–6 hours → 30 min) — concrete, falsifiable, memorable.
- Names "Ghana" — signals we are not selling a generic global tool.
- Asks for time explicitly — respects them, gives them an out, increases commit when they say yes.

---

## 3. Diagnostic (2 minutes) — listen more than you speak

Ask 3 questions, write down every word of the answer:

1. **"Today, when a customer asks for a solar proposal, who at [Company] actually builds it — and what tools do they use?"**
2. **"What's the most painful part of that workflow — sizing, BOQ pricing, or producing the final document?"**
3. **"How many proposals does [Company] put out per month, and how many close?"**

The answer to (1) tells you whether they are a one-person engineering shop or a team. Answer to (2) tells you which value prop to lead with. Answer to (3) gives you the upgrade math at the end.

---

## 4. The pitch (3 minutes) — match the answer

### Hook A — they said "sizing takes forever"
> "SolarPro takes location, loads, and mounting type and returns PV array size, battery autonomy, inverter rating, MPPT match, and AC + DC cable sizes — in under 30 seconds. Every value is computed against BS 7671 derating tables and IEC 62548 voltage windows. You can override any of them by typing, but you start from a defensible answer."

### Hook B — they said "BOQ is a nightmare"
> "Our BOQ engine takes the sized system and pulls quantities for panels, inverters, batteries, MC4s, fuses, isolators, combiners, mounting structure, earthing rods, and cable lengths. We're integrating with Nocheski and Ozo Solar pricing this quarter so the BOQ comes pre-priced in Cedis. You stop hand-typing schedules into Word."

### Hook C — they said "final documents look amateur"
> "Every project produces 7 reports: PV sizing, BOQ, cable schedule, economic analysis, installation method, energy analysis, and a bankable proposal — branded with your logo, ready for the bank or the client. PDF, one click."

### Hook D — they said "I lose customers because pricing is unclear"
> "Built-in economic engine — payback, IRR, NPV, lifetime savings — using the actual Ghana ECG tariff for the prospect's region. Customers see the financial case in their own currency, with their own utility tariff, on page 1."

---

## 5. The beta offer (1 minute)

> "Here's why we're inviting 15 Ghana companies and not 1,500: we want to learn what your workflow needs before we scale. Beta means:
>
> 1. **Free during beta** — no credit card, full access to all 7 reports.
> 2. **Direct line to the engineering team** — your feedback shapes the next two releases.
> 3. **Branded co-marketing** — your logo on the platform's 'Trusted by Ghana installers' wall once you've completed 3 projects.
> 4. **Your supplier catalog integrated first** — if you're a supplier, we wire your products into the BOQ procurement screen before public launch.
>
> Beta closes on **2026-07-15**. After that we move to paid plans starting at $49/month, but everyone in beta keeps a 50% lifetime discount."

---

## 6. Objection handling

| Objection | What they really mean | Your response |
|---|---|---|
| "We already design with Excel / hand-calcs." | "We don't think your tool is worth changing habits." | "That's exactly who beta is for. Excel doesn't give you a bankable IRR report or a BOQ that matches your supplier's stock. Try one project on us — keep your Excel for the next one, and tell us which won." |
| "Sounds expensive." | They haven't heard a price; they're testing. | "Beta is free. Paid plans after beta start at $49/month — a quarter of what one wasted site visit costs. The 50% beta lifetime discount means $24.50/month if you sign up this month." |
| "Is this for Ghana, or just a global app?" | They've been burned by foreign software that doesn't know ECG tariffs. | "Ghana-first. We use ECG tariff zones, BoG currency, BS 7671 wiring rules (UK standard, used here), Ghanaian region names — Greater Accra, Ashanti, Northern, Volta, Western. We're adding Kumasi-specific irradiance next sprint." |
| "What about my customer data?" | Trust / data residency. | "Each company gets its own tenant — row-level database isolation, audit log, GDPR-style data export. Hosted in Europe right now; moving to a Lagos edge node Q4 to reduce latency further." |
| "I'm one person, I don't need a SaaS." | Fear of complexity. | "Most of our beta companies are 1–3 people. The dashboard hides everything you don't need on a given day. If you can fill in a 5-row form, you can size a system." |
| "Can I export, in case I leave?" | Vendor lock-in fear. | "Every project exports as PDF (the reports) and JSON (raw engineering data). You walk in and out whenever you want." |
| "What if the internet drops?" — Ghana ECG outage context | Real practical concern. | "Browser caches the current project locally — you can finish sizing offline; the BOQ refresh and report PDF need a brief reconnect. We're shipping full offline mode for the proposal step next quarter." |

---

## 7. Close (60 seconds)

Pick one of three closes based on engagement signal:

**Warm signal — they're nodding, asking implementation questions:**
> "Great — let me get you set up while we're on the call. What's the best email for [Company]'s lead designer? I'll send you the account link now and we'll do a 20-minute screen-share next Tuesday or Wednesday to walk through your first project."

**Neutral signal — interested but reserved:**
> "Here's what I'd like to do: I send you an email today with the account link and a 3-minute video. You try it on one project — even an old one, no pressure. We talk Friday for 10 minutes — yes or no. Fair?"

**Cold signal — they're polite but not engaged:**
> "I won't take more of your time. Can I send you the user guide and the technical brief as a PDF — read it on your own, and if it's interesting, reply with the word YES and I'll set you up. No follow-up calls without your permission. Sound OK?"

Whatever the close — **always book the next touch in your CRM before you hang up.** No exceptions.

---

## 8. After the call — 5 minutes

In `data/ghana_beta_invitees.json`, update the entity's `notes` field with:
- Date called
- Person reached + role
- Verbatim answers to your three diagnostic questions
- Hook used (A / B / C / D)
- Outcome (signed up / demo booked / re-call date / declined + reason)

These notes feed the weekly sales review and become the catalog of objections we update this pitch with.

---

## 9. Daily targets during beta campaign (2026-06-08 → 2026-07-15)

| Metric | Daily target | Why |
|---|---|---|
| Inbound calls returned same-day | 100% | Cold leads decay 50% in 24h. |
| Diagnostic questions asked | 3/3 every call | This pitch only works with their words, not yours. |
| Demos booked | 2/day | At 60% show-up + 40% sign-up = ~10 customers/week. |
| CRM notes within 5 min of hang-up | 100% | Untracked calls don't exist. |

---

## 10. Numbers to memorise (you will be asked)

| Stat | Source |
|---|---|
| Design time: 4–6h → <30 min | Beta benchmark |
| Reports per project: 7 | PV, BOQ, cable, economic, installation, energy, proposal |
| Panel sizes supported: 110 / 250 / 330 / 400 / 450 / 500 / 550 Wp | Commit `27b2492` |
| Standards: BS 7671 (UK wiring), IEC 62548 (PV), NEC 690 (USA fallback) | `SPEC.md` |
| Mounting types: rooftop pitched, flat, metal, membrane, ground fixed, ground tracking | Engineering doc |
| Plans (post-beta): Free trial 14d → Professional $49 → Business $99 → Enterprise custom | `basicprice.txt` |
| Beta discount: 50% lifetime | This pitch |
| Beta closes: 2026-07-15 | This pitch |
