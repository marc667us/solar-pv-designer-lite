# aiappinvent Sales Campaign Portal — Tutorial

**Audience:** Marc (admin) + first sales reps onboarded for the SolarPro Global — Ghana campaign.
**Goal:** by the end of this guide you can sign in, invite staff, approve them, assign entities, and run a full sales conversation from invitation to PAID.

> The portal also has an in-app guided tour. Click **"Take the tour"** (red button bottom-right) any time you want a clickable walkthrough.

---

## 1. Sign in (admin)

1. Open https://campaign.aiappinvent.com (or https://marc667us.github.io/campaign-portal/ if DNS hasn't propagated yet)
2. You land on the **Sign in** card
3. Enter:
   - Email: the address your administrator gave you (typically your work email).
   - Password: the one-time password your administrator shared with you out-of-band (e.g. password manager invite). It is **not** committed to this repo; ask the administrator if you don't have it.
4. Click **Sign in**

> **Security:** The portal admin password is held only in your password manager and the deploy's GitHub Secret (`CAMPAIGN_ADMIN_PASSWORD`). It must never be written into this tutorial, source code, or chat. Section 2 below walks through changing it immediately on first login.

If you see "Network error", the backend (Railway) is still building — wait 2 minutes and retry.

---

## 2. Change your admin password immediately

1. After sign-in, pick the SolarPro Global — Ghana product → **Connect to app**
2. Click the **Staff** tab (top nav, admin only)
3. Scroll to **Current staff** → find your row → click **Reset PW**
4. Enter a strong password → confirm
5. Sign out → sign in with the new password

---

## 3. Invite your first sales rep

1. Staff tab → **Invite a staff member** section
2. Type a note ("Akua at Ozo Solar — Wed call")
3. Pick expiry (default 7 days)
4. Click **Generate link**
5. The URL appears below: `https://campaign.aiappinvent.com/?invite=AbC1d2EfGh…`
6. Click **Copy** — the URL is on your clipboard
7. Open WhatsApp → paste → send to the invitee

The link expires after the chosen number of days OR after one use, whichever comes first.

---

## 4. The invitee's experience

When Akua taps the WhatsApp link:

1. Portal opens with the URL `?invite=…` recognized automatically
2. She sees an **Accept your invitation** form
3. She fills:
   - Full name
   - Email
   - Profession ("Sales Engineer")
   - Password ×2
4. Click **Submit for approval**
5. She sees: *"Account submitted — waiting for admin approval"*
6. **She cannot sign in yet** — login is blocked with 403 until you approve

---

## 5. Approve the pending sales rep (admin)

1. The **Staff** tab now shows a yellow badge counter
2. Scroll to **Pending approvals**
3. Find Akua's row — review name, email, profession
4. Choose:
   - Product (SolarPro Global — Ghana)
   - Role (Sales / Manager / Admin — default Sales)
5. Click **Approve**
6. Her row disappears from Pending and appears in **Current staff** with status `active`
7. By default, Approve assigns her **all 15 entities**. If you want a subset, edit her assignments after approval

She can now sign in immediately.

---

## 6. The sales rep's first session

Akua signs in → picks the product → lands on the dashboard:

- She sees **only her assigned entities** (15 of 15 by default, or whatever subset you picked)
- Each entity row shows when she was assigned it and by whom (audit trail)
- The interactive tour runs automatically on first login — guides her through every tab

She can:
- Click **Call** → her phone dialer opens with the customer's +233 number
- Click **Email** → her email client opens with the invite body pre-filled
- Click **Lit** → log that she sent literature (status auto-advances to CONTACTED)
- Click **Sign up** → opens SolarPro registration in a new tab
- Update **Status** dropdown → cloud-synced immediately
- Type **Notes** → debounced 600 ms, cloud-synced
- Set **Next-action date** → cloud-synced
- All changes appear in every other rep's browser within 30 seconds (polling)

---

## 7. Capturing feedback from a customer

When the customer (e.g. Akua's contact at Ozo Solar) reports a bug or feature need:

1. Feedback tab → pick the customer → type the issue → set severity/type → **Add feedback**
2. Customer is auto-advanced to FEEDBACK stage
3. Feedback persists in the cloud — every rep + admin sees it

---

## 8. Submitting the consolidated feedback report (sales / manager)

1. Reports tab → **Build report from current feedback**
2. Two downloads appear:
   - **Markdown** — for admin review
   - **Claude Code prompt** — structured task list with file paths and acceptance criteria
3. **Mark as submitted to admin** moves all open items to triaged

---

## 9. Admin acts on the report

1. Admin downloads the Claude Code prompt
2. Opens a fresh `claude code` session in `solar-pv-designer-lite/`
3. Pastes the prompt
4. Claude patches each bug, runs tests, commits, pushes — Railway auto-redeploys
5. Admin marks the feedback items as fixed in the portal Feedback tab
6. Customer can retest on the live SolarPro app

---

## 10. Tracking — who did what, when

Every assignment carries audit metadata:

| Event | Tracked by |
|---|---|
| Staff invited | `campaign_invites.created_by`, `created_at` |
| Invite used | `used_by_email`, `used_at` |
| Account approved | `campaign_users.product_assigned_at`, `product_assigned_by` |
| Entity assigned | `campaign_assignments.assigned_at`, `assigned_by` |
| Pipeline change | `campaign_pipeline.last_updated`, `last_updated_by` |
| Feedback captured | `campaign_feedback.captured_by`, `date` |

All visible in the portal's `Data` tab JSON export.

---

## 11. Daily rep workflow (the routine to share with the team)

| Time | Action |
|---|---|
| 09:00 | Open portal → check the dashboard's "Today's priorities" list |
| 09:15 | Call any entity flagged for follow-up. Update Status + Notes after each call. |
| 11:00 | Move any new responses to CONTACTED. Send literature where missing. |
| 14:00 | Help any SIGNED UP customers complete their first SolarPro design — capture feedback. |
| 16:00 | Push NURTURED customers toward Pro plan. |
| 17:00 | Update notes on every entity touched today. Close laptop. |

The portal auto-polls so multi-rep sessions stay in sync.

---

## 12. Re-launching the tour

Anytime, click the red **"Take the tour"** floating button in the bottom-right of any tab. It walks you through every section, highlighting the real UI as you go.

---

## 13. Troubleshooting

| Symptom | Fix |
|---|---|
| "Network error" on sign-in | Backend (Railway) is rebuilding — wait 2 min |
| "Wrong email or password" | Check email lowercase; passwords are case-sensitive |
| "Account pending admin approval" | You haven't approved them on the Staff tab |
| Invitation link says "expired" | Generate a new one — old links auto-expire |
| Dashboard shows old data | Refresh the page; the 30s polling will sync |
| Need a video tour? | Click "Take the tour" — that's better than a video because you can pause |

---

## 14. What's new (June 17, 2026)

Four user-visible changes shipped today. None changes the navigation; they all make the existing pages clearer or more accurate.

### 14.1 3D shading dashboard — right-rail cards + visible sun-arc waypoints

Open any project → **Shading**. Above the existing Obstruction Summary, the right rail now carries three new cards lifted from the 3d10 reference design:

| Card | Shows |
|---|---|
| **Obstruction Details** | The primary obstruction (name, type, height, distance, direction) plus an impact chip — colour-coded green / amber / orange / red. |
| **Shading Summary** | Four KPIs: total shading hours, average shading index, peak shading hour, energy loss percentage. |
| **Shading Impact (PV Modules)** | Five-colour heatmap legend (None → Severe) and a row × column module grid showing per-panel impact, biased to the NE wedge where shadows actually fall. |

The main viewport now also shows five labelled time markers along the dashed yellow sun-path arc — 07:00, 09:30, 12:00, 14:30, 17:00 — and the moving sun disk lands exactly on each marker as you scrub the timeline slider. The shadow-timeline strip at the bottom extends to 18:00 (was 17:00).

### 14.2 Manual factor override now visibly wins

When you click one of the gold "Save as manual factor" pill buttons under the shading dashboard, the chosen factor was always being saved — but the dashboard's big numbers used to keep showing the engine's pick, which made it look like nothing happened. As of today every visible factor (top stat strip, banner, summary cards, AGENT PICK row highlight) tracks the actually-saved factor, and the label is suffixed `· MANUAL` so the operator can see immediately which source is active.

The downstream loads / sizing step always used the saved factor, so nothing changes downstream — this is purely a "what you see matches what you saved" fix.

### 14.3 Installation Drawings — mount-aware string + wiring diagram

Open any project's results → **Installation Diagrams** → Page 2. Between the existing PV-panel internal wiring diagram and the battery-bank diagram, you'll find a new **Drawing 1B — String Cable Routing & Combiner**. Its SVG switches to one of three layouts depending on the project's mounting type:

- **Sloped roof** (pitched / hip / gable / metal) — cables under aluminium rails, EPDM-flashed roof penetration, IP65 conduit drop to indoor utility wall.
- **Flat roof** (flat / membrane / concrete) — galvanised cable tray on ballast stands, parapet transition to UV-rated rigid conduit, drop to plant room.
- **Ground** (ground_fixed / ground_tracking) — IP67 armoured conduit buried ≥ 600 mm with draw pits every 20 m, combiner on equipment shelter.

The notes column cites the relevant standard for cable derating in each case (BS 7671 Table 4D4A for buried, IEC 60364-5-52 for cable-tray fill, Method B for in-roof).

### 14.4 Sun-on-track sanity (engineering note)

The sun disk's animation Bézier is now anchored to `M 60 460 Q 500 -340 940 460`, the exact curve the dashed yellow sun-path arc is drawn from. The two share a single mathematical formula, so the disk no longer drifts off the line at dawn / noon / dusk — it travels exactly through the 5 marker circles. If a client questions the simulation's accuracy, this is what to point to.

---

## 15. Recording your own video (if you really want one)

If you must have a video, the cheapest way is to record the in-app tour yourself:

1. Install **Loom** (free, https://loom.com)
2. Open the portal, log in as admin
3. Hit Record in Loom → click "Take the tour" in the portal
4. Narrate each step as Loom captures
5. Stop recording → Loom uploads + gives you a share link
6. Total time: ~5 minutes
7. Share the Loom URL with your team

That gives every new rep a 5-minute video walkthrough done with zero editing.
