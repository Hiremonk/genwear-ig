#!/usr/bin/env python3
"""
GenWear — Instagram publisher with a flexible queue.

Nothing publishes by itself. The workflow has no cron, and every post sits at
status "hold" until you approve it:

  APPROVE   `--now <id>`  publishes that post immediately. This is the gate.
  REVIEW    `--list`      shows the queue, publishes nothing.
  PREVIEW   `--dry-run`   prints the caption that would go out.

If you later want unattended posting, set a post's status to "scheduled" with
a `publish_at`, and re-enable the cron in the workflow. Until then `--now` is
the only path to a live post.

State lives in queue.json; the workflow commits it back after each publish so
a post can't silently go out twice.

Environment
-----------
IG_USER_ID        Instagram Business account ID (numeric)
IG_ACCESS_TOKEN   Instagram-Login token with instagram_business_content_publish
ASSET_BASE_URL    Public https base for the media files

Usage
-----
    python publish.py --list             # show the queue
    python publish.py --now zari-proof   # publish that post (approval)
    python publish.py --now zari-proof --dry-run
    python publish.py                    # publishes only "scheduled" + due
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

GRAPH = os.environ.get("GRAPH_HOST", "https://graph.instagram.com/v21.0")
IST = timezone(timedelta(hours=5, minutes=30))
HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(HERE, "queue.json")


# ---------------------------------------------------------------- http

def _request(method, path, params):
    url = f"{GRAPH}/{path.lstrip('/')}"
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}", method="GET")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Graph API {e.code} on {method} {path}\n"
                         f"{e.read().decode(errors='replace')}")


def get(path, **p):
    return _request("GET", path, p)


def post(path, **p):
    return _request("POST", path, p)


# ---------------------------------------------------------------- queue

def load_queue():
    with open(QUEUE) as fh:
        return json.load(fh)


def save_queue(q):
    with open(QUEUE, "w") as fh:
        json.dump(q, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def parse_when(s):
    """Accept 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD' (defaults to 10:00 IST)."""
    s = s.strip()
    fmt = "%Y-%m-%d %H:%M" if " " in s else "%Y-%m-%d"
    dt = datetime.strptime(s, fmt)
    if " " not in s:
        dt = dt.replace(hour=10, minute=0)
    return dt.replace(tzinfo=IST)


def find(q, post_id):
    for p in q["posts"]:
        if p["id"] == post_id:
            return p
    raise SystemExit(f"No post with id '{post_id}'. Use --list to see the queue.")


def next_due(q, now):
    """Oldest scheduled post whose time has arrived. None if nothing is due.

    Only posts explicitly marked "scheduled" are eligible. Anything on "hold"
    is invisible here and can only go out via --now, which is the approval gate.
    """
    due = [p for p in q["posts"]
           if p.get("status", "hold") == "scheduled"
           and p.get("publish_at") and parse_when(p["publish_at"]) <= now]
    due.sort(key=lambda p: parse_when(p["publish_at"]))
    return due[0] if due else None


def show(q):
    now = datetime.now(IST)
    print(f"{'ID':<22} {'STATUS':<10} {'WHEN':<18} FILE")
    for p in q["posts"]:
        st = p.get("status", "scheduled")
        when = p.get("publish_at", "—")
        if st == "scheduled" and p.get("publish_at") and parse_when(when) <= now:
            st = "DUE"
        print(f"{p['id']:<22} {st:<10} {when:<18} {p['file']}")


# ---------------------------------------------------------------- publish

def wait_ready(cid, token, tries, delay=6):
    for i in range(1, tries + 1):
        res = get(cid, fields="status_code,status", access_token=token)
        code = res.get("status_code")
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise SystemExit(f"Container failed: {res.get('status')}")
        print(f"  {code or 'PENDING'} ({i}/{tries})…", flush=True)
        time.sleep(delay)
    raise SystemExit("Container never reached FINISHED")


def publish(entry, ig_id, token, base_url):
    base = base_url.rstrip("/") + "/"
    url = urllib.parse.urljoin(base, entry["file"])
    is_reel = entry.get("media_type") == "REELS"

    print(f"[{entry['id']}] {entry.get('slot', '')}")
    print(f"  {'video' if is_reel else 'image'}: {url}")

    params = dict(caption=entry["caption"], access_token=token)
    if is_reel:
        params.update(media_type="REELS", video_url=url, share_to_feed="true")
        if entry.get("cover"):
            params["cover_url"] = urllib.parse.urljoin(base, entry["cover"])
    else:
        params["image_url"] = url

    cid = post(f"{ig_id}/media", **params)["id"]
    print(f"  container: {cid}")
    wait_ready(cid, token, tries=40 if is_reel else 20)

    media_id = post(f"{ig_id}/media_publish", creation_id=cid,
                    access_token=token)["id"]
    print(f"  published: {media_id}")

    if entry.get("first_comment"):
        try:
            post(f"{media_id}/comments", message=entry["first_comment"],
                 access_token=token)
            print("  first comment posted")
        except SystemExit as err:
            print(f"  first comment skipped: {err}", file=sys.stderr)

    return media_id


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", metavar="ID", help="publish this post immediately")
    ap.add_argument("--list", action="store_true", help="show the queue")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    q = load_queue()

    if args.list:
        show(q)
        return

    now = datetime.now(IST)
    entry = find(q, args.now) if args.now else next_due(q, now)

    if entry is None:
        print(f"Nothing due at {now:%Y-%m-%d %H:%M} IST. Queue unchanged.")
        return

    if args.dry_run or os.environ.get("DRY_RUN") == "1":
        print(f"[dry run] would publish '{entry['id']}' — {entry.get('slot','')}")
        print(f"[dry run] file: {entry['file']}")
        print(f"[dry run] caption:\n{entry['caption']}\n")
        return

    if entry.get("status") == "posted":
        if not args.now:
            print(f"'{entry['id']}' already posted; skipping.")
            return
        print(f"WARNING: '{entry['id']}' was already posted "
              f"{entry.get('posted_at','?')} — publishing again because --now was given.")

    media_id = publish(entry, os.environ["IG_USER_ID"],
                       os.environ["IG_ACCESS_TOKEN"],
                       os.environ["ASSET_BASE_URL"])

    entry["status"] = "posted"
    entry["posted_at"] = now.strftime("%Y-%m-%d %H:%M")
    entry["media_id"] = media_id
    save_queue(q)
    print("queue.json updated")


if __name__ == "__main__":
    main()
