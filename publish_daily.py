#!/usr/bin/env python3
"""
GenWear — daily Instagram publisher (Instagram Graph API).

Publishes one scheduled post per run: creates a media container from a public
image URL, waits for Meta to finish processing it, publishes it, then drops the
hashtag block in as the first comment.

Environment
-----------
IG_USER_ID        Instagram Business account ID (numeric)
IG_ACCESS_TOKEN   Long-lived Instagram-Login token (instagram_business_content_publish)
ASSET_BASE_URL    Public https base for the JPGs, e.g.
                  https://raw.githubusercontent.com/<user>/<repo>/main/assets/
CAMPAIGN_START    ISO date the campaign begins, e.g. 2026-08-17
DRY_RUN           set to "1" to print what would happen and exit

Usage
-----
    python publish_daily.py              # picks today's post from CAMPAIGN_START
    python publish_daily.py --day 3      # force a specific day
    python publish_daily.py --dry-run
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

# Instagram API with Instagram Login lives on graph.instagram.com.
# (The legacy Facebook-Page-linked flow used graph.facebook.com.)
GRAPH = os.environ.get("GRAPH_HOST", "https://graph.instagram.com/v21.0")
IST = timezone(timedelta(hours=5, minutes=30))
HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- http helpers

def _request(method, path, params):
    url = f"{GRAPH}/{path.lstrip('/')}"
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        url = f"{url}?{data.decode()}"
        req = urllib.request.Request(url, method="GET")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SystemExit(f"Graph API {e.code} on {method} {path}\n{body}")


def get(path, **params):
    return _request("GET", path, params)


def post(path, **params):
    return _request("POST", path, params)


# ---------------------------------------------------------------- campaign

def load_schedule():
    with open(os.path.join(HERE, "schedule.json")) as fh:
        return json.load(fh)


def pick_post(schedule, forced_day):
    posts = schedule["posts"]
    if forced_day:
        for p in posts:
            if p["day"] == forced_day:
                return p
        raise SystemExit(f"No post defined for day {forced_day}")

    start_raw = os.environ.get("CAMPAIGN_START")
    if not start_raw:
        raise SystemExit("CAMPAIGN_START is not set (expected e.g. 2026-08-17)")
    start = date.fromisoformat(start_raw)
    today = datetime.now(IST).date()
    offset = (today - start).days

    if offset < 0:
        raise SystemExit(f"Campaign hasn't started yet — begins {start}, today is {today}")
    if offset >= len(posts):
        raise SystemExit(f"Campaign finished — {len(posts)} days ran from {start}")
    return posts[offset]


def already_posted_today(ig_user_id, token):
    """Idempotency guard: skip if the account already published today (IST)."""
    res = get(f"{ig_user_id}/media", fields="timestamp", limit=3, access_token=token)
    today = datetime.now(IST).date()
    for item in res.get("data", []):
        ts = item.get("timestamp")
        if not ts:
            continue
        when = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(IST).date()
        if when == today:
            return True
    return False


# ---------------------------------------------------------------- publishing

def wait_until_ready(container_id, token, tries=20, delay=6):
    """Reels take substantially longer to transcode than stills."""
    for attempt in range(1, tries + 1):
        res = get(container_id, fields="status_code,status", access_token=token)
        code = res.get("status_code")
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise SystemExit(f"Container failed to process: {res.get('status')}")
        print(f"  container {code or 'PENDING'} ({attempt}/{tries})…", flush=True)
        time.sleep(delay)
    raise SystemExit("Container never reached FINISHED")


def publish(entry, ig_user_id, token, base_url):
    base = base_url.rstrip("/") + "/"
    asset_url = urllib.parse.urljoin(base, entry["file"])
    is_reel = entry.get("media_type") == "REELS"

    print(f"Day {entry['day']} — {entry['slot']}")
    print(f"  {'video' if is_reel else 'image'}: {asset_url}")

    params = dict(caption=entry["caption"], access_token=token)
    if is_reel:
        params.update(media_type="REELS", video_url=asset_url, share_to_feed="true")
        if entry.get("cover"):
            params["cover_url"] = urllib.parse.urljoin(base, entry["cover"])
    else:
        params["image_url"] = asset_url

    container = post(f"{ig_user_id}/media", **params)
    cid = container["id"]
    print(f"  container: {cid}")

    wait_until_ready(cid, token, tries=40 if is_reel else 20)

    published = post(
        f"{ig_user_id}/media_publish",
        creation_id=cid,
        access_token=token,
    )
    media_id = published["id"]
    print(f"  published: {media_id}")

    comment = entry.get("first_comment")
    if comment:
        try:
            post(f"{media_id}/comments", message=comment, access_token=token)
            print("  first comment posted")
        except SystemExit as err:
            # Never fail the run over a hashtag comment.
            print(f"  first comment skipped: {err}", file=sys.stderr)

    return media_id


# ---------------------------------------------------------------- entrypoint

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", type=int, help="force a specific campaign day")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="publish even if something already went out today")
    args = ap.parse_args()

    schedule = load_schedule()
    entry = pick_post(schedule, args.day)

    dry = args.dry_run or os.environ.get("DRY_RUN") == "1"
    if dry:
        print(f"[dry run] would publish day {entry['day']} — {entry['slot']}")
        print(f"[dry run] file: {entry['file']}")
        print(f"[dry run] caption:\n{entry['caption']}\n")
        return

    ig_user_id = os.environ["IG_USER_ID"]
    token = os.environ["IG_ACCESS_TOKEN"]
    base_url = os.environ["ASSET_BASE_URL"]

    if not args.force and already_posted_today(ig_user_id, token):
        print("Something already went out today — skipping (use --force to override).")
        return

    publish(entry, ig_user_id, token, base_url)


if __name__ == "__main__":
    main()
