# GenWear Instagram publisher

A queue, not a fixed calendar. Every post carries its own `publish_at` time and
its own status, so you can:

- **schedule** — set a time, the hourly cron publishes it when it comes due
- **post now** — fire any post immediately, whatever its scheduled time says
- **hold** — set `"status": "hold"` and it never publishes until you change it

Nothing is tied to a campaign start date, and nothing double-posts: the
workflow commits the updated `queue.json` back after each successful publish.

---

## Daily use

### See what's in the queue

Actions → **GenWear Instagram publisher** → Run workflow → `list = 1`.
Prints every post with status and time. `DUE` means the cron will take it on
its next hourly run.

### Post something right now

Run workflow → put the post's **id** in the `now` field (e.g. `zari-proof`) →
Run. Live in about 30 seconds; Reels take a little longer to transcode.

Works whether the post was scheduled for next week or has no time at all.

### Schedule something

Edit `queue.json`, set `publish_at`, commit. Format is `YYYY-MM-DD HH:MM` in
IST — or just `YYYY-MM-DD`, which defaults to 10:00.

```json
{
  "id": "fabric-macro",
  "slot": "Editorial — fabric study",
  "publish_at": "2026-08-15 18:30",
  "status": "scheduled",
  "file": "fabric_macro.jpg",
  "caption": "…",
  "first_comment": "#genwear …"
}
```

### Pause everything

Change the dates, or set posts to `"status": "hold"`. To stop the cron
entirely: Actions → ··· → **Disable workflow**.

---

## Adding new content

1. Drop the JPG/MP4 into `assets/` (drag onto the GitHub page, commit).
2. Add an entry to `queue.json` with a matching `file`.
3. Either set `publish_at`, or leave it out and fire it with `now` when ready.

A post with no `publish_at` will never auto-publish — it only goes out on
demand. That's the safest way to stage content you haven't decided on.

---

## Media requirements

| | |
|---|---|
| Feed image | JPG, 4:5 (1080×1350) or 1:1 |
| Reel | MP4 h264, 9:16 (1080×1920), 3–90s |
| Caption | under 2,200 characters |
| Hashtags | go in `first_comment`, not the caption |

Reels published through the API can't use Instagram's music library — that's
app-only. The two campaign reels carry their own sound design instead. If you
want trending audio on something, post it manually from the phone.

---

## First-time setup

Already done for this repo, kept here for reference.

**Secrets** (Settings → Secrets and variables → Actions → Secrets):

| Name | Value |
|---|---|
| `IG_USER_ID` | `17841434769252266` |
| `IG_ACCESS_TOKEN` | Instagram-Login token |

**Variables** (same page, Variables tab):

| Name | Value |
|---|---|
| `ASSET_BASE_URL` | `https://raw.githubusercontent.com/Hiremonk/genwear-ig/main/assets/` |

The repo must stay **public** — Meta fetches media over plain HTTPS with no
auth. Tokens live in Secrets and are never in the repo.

Connected account: **@genwear.studios**, via Instagram API with Instagram
Login (no Facebook Page needed). The account is an accepted Instagram Tester
on the *GenWear Publisher* app (App ID `2029006404395712`).

---

## When something breaks

| Symptom | Cause | Fix |
|---|---|---|
| "Nothing due" but you expected a post | `publish_at` in the future, or status isn't `scheduled` | Run with `list = 1` to see actual state |
| `(#100) image_url` invalid | Repo went private, or filename typo | Confirm the raw URL loads in a browser |
| `(#190)` token error | Token expired (60 days) | Regenerate in the Meta app dashboard, update the secret |
| Container stuck `IN_PROGRESS` | Reel transcoding | Stills retry 20×, Reels 40× |
| Cron stopped firing | GitHub pauses schedules after 60 days of no commits | Push anything |
| Queue state didn't save | Workflow lacks write permission | `permissions: contents: write` must be in the workflow |

### Token refresh

Instagram-Login tokens last 60 days and are refreshable:

```
curl "https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=<current>"
```

Paste the result into the `IG_ACCESS_TOKEN` secret. Only works on tokens at
least 24h old and not yet expired.
