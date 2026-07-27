# Using QR Chores

Family guide for parents and kids. For developers and deploy, see [AGENTS.md](../AGENTS.md) and [DEPLOY.md](./DEPLOY.md).

**In the running app:** open **Help** (top bar, login page, or `/help`) for a mobile-friendly version of this guide.

---

## Getting started

### Accounts

QR Chores uses **username + password** logins (often an email-shaped username; the app does not require a real mailbox). There are two roles:

| Role | Who | What they can do |
|------|-----|------------------|
| **Parent** | Mom and Dad (separate logins) | Manage **children**, chores, QR codes, rewards, today board, history |
| **Child** | One or more kids | See their chores, complete them via QR, earn points and achievements |

There is **no public “sign up” page**. Parent logins are provided for your household. Parents create and manage **child** accounts in the app under **Children**.

### Log in

1. Open the app URL (for example `https://chores.indecline.ca` or your local/dev URL).
2. Enter username and password.
3. Parents land on **Today**; each child lands on **Home** (their points, achievements, and chores only).

Use **Log out** in the top bar when switching people on a shared phone.

### Install as an app

QR Chores works best **added to your home screen** (full-screen, easy to find — no App Store or Play Store).

| Platform | Steps |
|----------|--------|
| **Chrome on Android** | Open the site → **⋮** menu → **Add to Home screen** / **Install app** → confirm |
| **Safari on iPhone / iPad** | Open the site in **Safari** → **Share** → **Add to Home Screen** → **Add** |

On iOS, “Add to Home Screen” only appears in Safari (not Chrome). After installing, open from the home-screen icon. More detail is in the in-app **Help** (`/help`).

---

## Parent guide

### Today

The **Today** board shows chores scheduled for this calendar day (for your children):

| Status | Meaning |
|--------|---------|
| **Pending** | Not done yet |
| **Done** | Completed (may also say early / late) |
| **Late** | Still open and past due + grace, or completed late |

Tap through the nav: **Today · History · Children · Chores · Rewards**.

### Children

Use **Children** to add and manage kids who will complete chores.

**Add child** (or edit an existing one):

| Field | Notes |
|-------|--------|
| **First name / last name** | Shown in the app (chore lists, assignee picker) |
| **Username** | What they type at login (not verified as a real email) |
| **Password** | Required when creating; optional when editing (leave blank to keep the current password) |

Tips:

- Add at least one child **before** creating chores — every chore must be assigned to someone.
- **Edit** updates name, username, or password.
- **Deactivate** stops that child from logging in as an active user (and they won’t appear as an assignee for new chores). History for past work stays.
- **Activate** turns them back on.

Each child has their own login. Siblings cannot complete each other’s chores.

### Creating and editing chores

On **Chores** → **New chore** (or edit an existing one):

| Field | Notes |
|-------|--------|
| **Title / description** | What needs doing |
| **Assigned to** | **Required** — which child owns this chore (and its QR) |
| **Due time** | Local wall-clock time (app timezone, usually America/Chicago) |
| **Schedule days** | Which weekdays this chore appears |
| **Base points** | Awarded once per day when completed |
| **Photo policy** | **Required**, **optional**, or **none** |

Tips:

- One chore = one stable QR for as long as the chore is active.
- Only the **assigned** child can complete that QR while logged in.
- **Deactivate** stops the QR without wiping history.
- **Delete** permanently removes the chore, completions, and proof photos.

### QR codes

- Each chore has **one QR code forever** while it’s active (token does not rotate daily).
- Open **QR** on a chore to view or download the PNG.
- Use **Print** for a sticker sheet of all active chores.
- Completing still requires the **assigned child** to be logged in after scanning.

**Important:** Stickers encode the public site URL. Don’t change that URL after you print, or the stickers break.

### Rewards

On **Rewards** you configure:

1. **Timing bonuses** — extra points for Early / On time / Late (see [Timing](#timing-early-on-time-late) below). These stack on top of each chore’s base points. **Late bonus may be negative** (for example `-2`) if you want a small penalty for finishing after the grace window; use `0` for no late adjustment.
2. **Achievements** — badges with criteria such as streak days, on-time counts, photo completions, total completions. Points for unlocks are set per achievement.

Awards are calculated **on the server** when a child completes a chore. The app never trusts the phone for point totals. Points and achievements are tracked **per child**.

### History

**History** lists recent completions with timing, points, and proof photos (when provided). Open a photo from the list while logged in.

---

## Child guide

### Home

After login you see:

- Total points and points earned today
- Awarded and Not yet awarded achievements

You only complete chores **assigned to you**. To finish one, scan its physical QR code sticker.

### Completing a chore

1. **Scan the QR** on the sticker.
2. Confirm the name and due time.
3. If a **photo** is required or optional, take or choose a picture (JPEG, PNG, or WebP; size limit applies).
4. Tap **I did it**.

You’ll get a celebration screen with:

- Total points for this completion
- Breakdown: base points, timing bonus (if any), achievement points
- New achievements, if any

If the QR belongs to a sibling’s chore, you’ll see that it isn’t yours — log in with the correct child’s account.

### Rules that matter

- **Once per chore per day.** If you already finished it, you’ll see “already done” with the earlier result.
- **Late is OK the same day.** After the due time + grace you can still complete; it counts as late.
- **Photos:** required chores won’t complete without a valid image.
- **Achievements:** open **See all achievements** (or `/me/achievements`) for progress and unlocks.

---

## Timing: Early, On time, Late

Timing is based on the chore’s **due time** on the **local calendar day** (app timezone). Defaults:

| Status | When it applies (defaults) |
|--------|----------------------------|
| **Early** | More than **60 minutes** before due |
| **On time** | From 60 minutes before due **through** due time plus **15 minutes** grace |
| **Late** | After due + 15 minutes grace |

**Example** — chore due **6:00 PM**:

| Status | Clock window |
|--------|----------------|
| Early | Before **5:00 PM** |
| On time | **5:00 PM** through **6:15 PM** |
| Late | After **6:15 PM** |

Parents set **how many bonus points** each status is worth on **Rewards**. Completing late is still allowed the same day; base points still apply. The **Late** field can be **negative** to take points away when a chore is late (a late penalty), or `0` to leave base points alone.

The same rules appear in the app on:

- Parent **Rewards** (general rules)
- Child confirm and celebration screens (with that chore’s due time)

---

## Photos and privacy

- Proof photos are stored securely (local disk in development; cloud storage in production).
- The database only keeps a reference key, not the image bytes.
- Photos are available only to **logged-in** users through the app (`/photos/…`), not as public links.
- Deleting a chore also removes its proof photos.
- Photo retention / automatic cleanup of old images may be added later.

---

## Points (quick reference)

| Source | When |
|--------|------|
| **Base points** | Once per day when the chore is completed |
| **Timing bonus** | Early / on-time / late amount from Rewards |
| **Achievement points** | When a new achievement unlocks on complete |

Your balance is the sum of the points ledger (server-side), not a number the phone invents. Each child has their own balance.

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| QR opens wrong site or fails | Stickers may have been printed with an old public URL; re-print after the site address is final |
| “Wrong account” when completing | Log out and log in as a **child**, not a parent |
| “Not your chore” / assigned to someone else | Log in as the child this chore is assigned to (siblings can’t finish each other’s QRs) |
| Can’t create a chore / no assignee | Add a child under **Children** first |
| Can’t complete without photo | Chore photo policy is **required** — attach JPEG/PNG/WebP |
| Already done | Same chore can only be completed once per local day |
| Session keeps logging out | Cookie sessions; after a secret key change everyone must log in again |

---

## What’s intentionally not in the app (yet)

- Push or SMS reminders  
- Points shop / redemption  
- Public self-serve signup for new households  
- Native mobile apps  
- Parent “mark done for them” override  

---

*Product rules in this guide match the app’s canonical behavior in [AGENTS.md](../AGENTS.md). If something here disagrees with the running app, prefer the app and update this file.*
