# SolarPro Beta Launch — Social Posts v1

Use with: `docs/SolarPro_Beta_Flyer_1080.png` (FB / IG) and `docs/SolarPro_Beta_Flyer_1200x628.png` (LinkedIn, link previews).
Landing URL: `https://solarpro.aiappinvent.com`

---

## Facebook (Page post)

**Image:** 1080×1080 flyer
**Caption (≈290 chars):**

```
SolarPro Global beta is live 🌞

Find live solar tenders and RFPs across 22+ countries — then auto-generate the engineering design, BOQ, and a bankable proposal in 30 minutes.

Built for installers, EPCs, and consultants who want to win more contracts and stop losing weekends to spreadsheets.

14 days free. No card needed.

→ https://solarpro.aiappinvent.com

#SolarPV #RenewableEnergy #SolarTenders #EPC #OffGrid #Ghana #Africa #PVDesign
```

---

## Instagram (feed post)

**Image:** 1080×1080 flyer
**Caption (≈250 chars + hashtags as first comment):**

```
SolarPro Global beta is live 🌞⚡

Find live solar RFPs across 22+ countries → auto-design the system → bankable proposal in 30 minutes.

Built for installers, EPCs, and consultants who want to win contracts faster.

14 days free. No card. Link in bio. ☀️
```

**First comment (hashtags):**

```
#SolarPV #SolarPower #RenewableEnergy #SolarTenders #SolarEPC #SolarDesign #PVDesign #SolarInstaller #OffGridSolar #SolarAfrica #Ghana #Nigeria #Kenya #SolarBusiness #SolarTech #CleanEnergy #BatteryStorage #SolarProGlobal #BetaLaunch #StartupLife
```

**Bio link to set:** `https://solarpro.aiappinvent.com`

---

## LinkedIn (personal or company page)

**Image:** 1200×628 flyer (better aspect for LinkedIn feed)
**Post (≈980 chars — within the sweet spot):**

```
SolarPro Global is now in public beta.

The problem: solar installers and EPCs spend more time hunting tenders and rebuilding the same engineering math than they spend winning contracts.

What we built:
• A tender + RFP radar that watches 22+ countries for live solar opportunities
• Auto PV / battery / inverter / cable sizing — BS 7671 & IEC 60364 compliant
• A Bill of Quantities + financial proposal generator that produces bankable docs in 30 minutes

Already used by installers across Ghana, Nigeria, Kenya, the UK, and the US in our 35-invitee preview round.

14-day free trial. No credit card.

We're looking for 50 more installers, EPCs, and consultants to put it through hell during beta. If you sell solar systems for a living, this is for you.

→ https://solarpro.aiappinvent.com

#SolarEnergy #RenewableEnergy #SolarPV #EPC #SolarTenders #PVDesign #Africa #CleanTech #BetaLaunch
```

---

## Posting order + timing

Codex recommends queueing all three via Buffer with `customScheduled` 5–10 minutes ahead so they all land near-simultaneously. Schedule for a weekday 09:00 or 13:00 local-time of the largest installer audience (Ghana / West Africa).

## Tracking

Add UTM parameters per channel when actually posting (Buffer GraphQL allows this in the asset URL):
- FB: `?utm_source=facebook&utm_medium=social&utm_campaign=beta_launch`
- IG: `?utm_source=instagram&utm_medium=social&utm_campaign=beta_launch`
- LI: `?utm_source=linkedin&utm_medium=social&utm_campaign=beta_launch`

The Flask landing already exposes a `_utm_capture()` cookie hook (registered same as `REF_COOKIE_CAPTURE_v1`); confirm before launch.
