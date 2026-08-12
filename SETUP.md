# GenWear — automated daily Instagram posting

Once wired up, one asset goes out at **10:00 IST every day** for 11 days — 9
posters and 2 Reels — with caption and first-comment hashtags, hands-off.

This uses the **Instagram API with Instagram Login**: you connect the
Instagram account directly. No Facebook Page, no Business Manager, no System
Users. Setup is ~20 minutes.

**Why GitHub Actions:** the API needs a public HTTPS URL for every image, and
you need a daily cron. A public GitHub repo provides both for free
(`raw.githubusercontent.com` hosts the assets, Actions runs the schedule).

---

## Before you start

The Instagram account must be **Professional** (Business or Creator):
Instagram app → Settings → Account type and tools → Switch to professional
account → **Business**.

## Step 1 — Create the GitHub repo

1. Create a **public** repo called `genwear-ig` (public is required — Meta's
   servers fetch the images with no auth; these are posts you're publishing
   anyway, and the tokens live in GitHub Secrets, never in the repo).
2. Unzip `genwear-ig-repo.zip` and upload everything, keeping the layout:

```
genwear-ig/
├── assets/                      ← 9 posters + 2 reels
├── .github/workflows/daily-post.yml
├── publish_daily.py
├── schedule.json
└── SETUP.md
```

If you use the web UI ("Add file → Upload files"), upload the `.github`
folder too — drag the whole unzipped folder in so the workflow file lands at
`.github/workflows/daily-post.yml`.

## Step 2 — Create the Meta app and connect the account

1. [developers.facebook.com](https://developers.facebook.com) → **My Apps** →
   **Create App** → use case: **Other** → type: **Business**.
2. On the app dashboard, find the **Instagram** product → **Set up**.
3. Choose **API setup with Instagram login**.
4. Under **Generate access tokens** → **Add account** → log in with the
   GenWear Instagram credentials and authorise.
5. The dashboard now shows the account with its **Instagram user ID**
   (numeric) and a **Generate token** button. Click it, approve the
   permissions, and copy the token — it's long-lived (60 days).

That's both values you need: `IG_USER_ID` and `IG_ACCESS_TOKEN`.

In App settings → Permissions, the ones in play are
`instagram_business_basic`, `instagram_business_content_publish`, and
`instagram_business_manage_comments` (for the first-comment hashtags). For
posting to your own account in Development mode, no App Review is needed.

## Step 3 — Configure the repo

Repo → **Settings → Secrets and variables → Actions**.

Secrets (New repository secret):

| Name | Value |
|---|---|
| `IG_USER_ID` | numeric ID from Step 2 |
| `IG_ACCESS_TOKEN` | token from Step 2 |

Variables (Variables tab → New repository variable):

| Name | Value |
|---|---|
| `ASSET_BASE_URL` | `https://raw.githubusercontent.com/<your-username>/genwear-ig/main/assets/` |
| `CAMPAIGN_START` | the day you want Day 1 to land, e.g. `2026-08-17` |

Open the `ASSET_BASE_URL` + `day1_mon_proof-print.jpg` in a browser — if the
image loads, Meta can fetch it too.

## Step 4 — Test, then go live

Repo → **Actions** tab → **GenWear daily Instagram post** → Run workflow:

1. Run with `dry_run = 1` → the log shows the caption, nothing publishes.
2. Run with `day = 1`, `dry_run = 0` → publishes Day 1 for real. Check the
   grid, zoom in, read the caption and first comment.
3. Happy? Delete the test post on Instagram (or keep it and set
   `CAMPAIGN_START` to today so Day 2 fires tomorrow). The cron takes over
   from `CAMPAIGN_START`.

---

## How it behaves

- **04:30 UTC / 10:00 IST daily** — computes the campaign day from
  `CAMPAIGN_START`, publishes that asset.
- **Duplicate guard** — if anything already went out today, it skips instead
  of double-posting (`--force` overrides).
- **Reels** — publish as Reels with `share_to_feed`, cover thumbnail from
  the `cover` field. These files carry a subtle sound-design track (ambient +
  cues) since API posts can't use Instagram's music library.
- **Hashtags** — go in as the first comment; the caption stays clean.
- **After day 11** — exits with "Campaign finished". Extend `schedule.json`
  + drop new files in `assets/` to continue.

## Token expiry — the one maintenance task

Instagram-Login tokens last **60 days** and are refreshable. The campaign is
11 days, so you're covered — but if you keep the pipeline running, refresh
before day ~55 with:

```
curl "https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=<current-token>"
```

…and paste the returned token into the `IG_ACCESS_TOKEN` secret. (Refresh
only works on tokens that are at least 24h old and not yet expired.)

## When something breaks

| Symptom | Cause | Fix |
|---|---|---|
| `image_url` / `video_url` invalid (#100) | Repo private or URL typo | Make repo public; open the raw URL in a browser |
| Token error (#190) | Token expired (60 days) or account re-secured | Regenerate in the app dashboard, update the secret |
| Container stuck `IN_PROGRESS` | Reel transcoding | Stills retry 20×, Reels 40× — rare at these file sizes |
| First comment missing | Comments permission not granted | Re-generate token approving all permissions; posts still succeed without it |
| Nothing posts, no error | GitHub paused the cron | Schedules pause after 60 days without commits — push anything |

## Changing the schedule

Cron lives in `.github/workflows/daily-post.yml`, in UTC:

```yaml
- cron: "30 4 * * *"   # 10:00 IST daily
- cron: "30 12 * * *"  # 18:00 IST
- cron: "30 4 * * 1-5" # weekdays only
```
