# Using QR Chores

Family guide for parents and kids. For developers and deploy, see [AGENTS.md](../AGENTS.md) and [DEPLOY.md](./DEPLOY.md).

**In the running app:** open **Help** (top bar, login page, or `/help`) for a mobile-friendly version of this guide.

---

## Getting started

### Accounts

QR Chores uses **email + password** logins. There are two roles:

| Role | Who | What they can do |
|------|-----|------------------|
| **Parent** | Mom and Dad (separate logins) | Manage chores, QR codes, rewards, today board, history |
| **Child** | Daughter | See today’s chores, complete them, earn points and achievements |

There is **no public “sign up” page**. Accounts are created by seed (local/bootstrap) or by an admin. A future update will let parents create child accounts in the app.

### Log in

1. Open the app URL (for example `https://chores.indecline.ca` or your local/dev URL).
2. Enter email and password.
3. Parents land on **Today**; the child lands on **Home**.

Use **Log out** in the top bar when switching people on a shared phone.

---

## Parent guide

### Today

The **Today** board shows chores scheduled for this calendar day:

| Status | Meaning |
|--------|---------|
| **Pending** | Not done yet |
| **Done** | Completed (may also say early / late) |
| **Late** | Still open and past due + grace, or completed late |

Tap through the nav: **Today · Chores · History · Rewards**.

### Creating and editing chores

On **Chores** → **Add chore** (or edit an existing one):

| Field | Notes |
|-------|--------|
| **Title / description** | What she needs to do |
| **Due time** | Local wall-clock time (app timezone, usually America/Chicago) |
| **Schedule days** | Which weekdays this chore appears |
| **Base points** | Awarded once per day when completed |
| **Photo policy** | **Required**, **optional**, or **none** |

Tips:

- One chore = one stable QR for as long as the chore is active.
- **Deactivate** stops the QR without wiping history.
- **Delete** permanently removes the chore, completions, and proof photos.

### QR codes

- Each chore has **one QR code forever** while it’s active (token does not rotate daily).
- Open **QR** on a chore to view or download the PNG.
- Use **Print** for a sticker sheet of all active chores.
- Completing still requires the **child** to be logged in after scanning.

**Important:** Stickers encode the public site URL (`BASE_URL`). Don’t change that URL after you print, or the stickers break.

### Rewards

On **Rewards** you configure:

1. **Timing bonuses** — extra points for Early / On time / Late (see [Timing](#timing-early-on-time-late) below). These stack on top of each chore’s base points.
2. **Achievements** — badges with criteria such as streak days, on-time counts, photo completions, total completions. Points for unlocks are set per achievement.

Awards are calculated **on the server** when she completes a chore. The app never trusts the phone for point totals.

### History

**History** lists recent completions with timing, points, and proof photos (when provided). Open a photo from the list while logged in.

---

## Child guide

### Home

After login you see:

- Total points and points earned today
- Awarded and Not yet awarded achievements

To complete a chore, scan its physical QR code sticker.

### Completing a chore

1. **Scan the QR** on the sticker.
2. Confirm the name and due time.
3. If a **photo** is required or optional, take or choose a picture (JPEG, PNG, or WebP; size limit applies).
4. Tap **I did it**.

You’ll get a celebration screen with:

- Total points for this completion
- Breakdown: base points, timing bonus (if any), achievement points
- New achievements, if any

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

Parents set **how many bonus points** each status is worth on **Rewards**. Completing late is still allowed the same day; base points still apply.

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

Your balance is the sum of the points ledger (server-side), not a number the phone invents.

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| QR opens wrong site or fails | Stickers may have been printed with an old `BASE_URL`; re-print after the URL is final |
| “Wrong account” when completing | Log out and log in as the **child** |
| Can’t complete without photo | Chore photo policy is **required** — attach JPEG/PNG/WebP |
| Already done | Same chore can only be completed once per local day |
| Session keeps logging out | Cookie sessions; after a secret key change everyone must log in again |

---

## What’s intentionally not in the app (yet)

- Push or SMS reminders  
- Points shop / redemption  
- Self-serve signup and parent-created child accounts (planned)  
- Multi-child first-class household UI  
- Native mobile apps  
- Parent “mark done for her” override  

---

*Product rules in this guide match the app’s canonical behavior in [AGENTS.md](../AGENTS.md). If something here disagrees with the running app, prefer the app and update this file.*
