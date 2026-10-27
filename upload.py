#!/usr/bin/env python3
"""Upload queued Shorts from shorts/<slug>/ to the Dadi Ke Kisse YouTube channel.

Each folder holds video.mp4, cover.png and meta.json:
  {"slug", "character", "title", "description", "tags": [...], "playlist", "publish_at": ISO-8601 with offset,
   "made_for_kids": false, "category_id": "1", "language": "hi"}
A Short is uploaded as private with a scheduled publish time (YouTube makes it public at publish_at).
If publish_at is already past (or within 15 minutes), it is scheduled a few minutes from now instead.
After a successful upload, meta.json gets youtube_id / url / uploaded_at / scheduled_for, and video.mp4 is deleted
from the repo (the cover and meta stay) so the repo stays small.

Needs the repo secrets YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN (see README.md).
"""
import datetime as dt, glob, json, os, sys, time

MAX_PER_RUN = int(os.environ.get("MAX_PER_RUN", "20"))
ROOT = os.environ.get("GITHUB_WORKSPACE") or os.getcwd()


def creds():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    cid, sec, tok = (os.environ.get(k, "").strip() for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))
    if not (cid and sec and tok):
        print("::warning::YouTube secrets are not set yet (YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN). Nothing uploaded.")
        sys.exit(0)
    c = Credentials(None, refresh_token=tok, token_uri="https://oauth2.googleapis.com/token", client_id=cid, client_secret=sec,
                    scopes=["https://www.googleapis.com/auth/youtube"])
    c.refresh(Request())
    return c


def all_metas():
    """Both layouts: shorts/<slug>/meta.json + video.mp4 + cover.png, or flat <slug>.json + <slug>.mp4 + <slug>.png
    (in the repo root or in shorts/)."""
    out = []
    for m in glob.glob(os.path.join(ROOT, "shorts", "*", "meta.json")):
        d = os.path.dirname(m); out.append((m, os.path.join(d, "video.mp4"), os.path.join(d, "cover.png")))
    for m in glob.glob(os.path.join(ROOT, "*.json")) + glob.glob(os.path.join(ROOT, "shorts", "*.json")):
        base = os.path.basename(m)[:-5]
        try:
            meta = json.load(open(m, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(meta, dict) and meta.get("slug") == base and "title" in meta:
            d = os.path.dirname(m); out.append((m, os.path.join(d, base + ".mp4"), os.path.join(d, base + ".png")))
    return out


def pending():
    out = []
    for m, video, cover in all_metas():
        meta = json.load(open(m, encoding="utf-8"))
        if meta.get("youtube_id"):
            continue
        if not os.path.exists(video):
            print(f"::warning::{meta.get('slug')}: no video file ({os.path.basename(video)}), skipped")
            continue
        out.append((meta.get("publish_at", ""), m, video, cover, meta))
    return [x[1:] for x in sorted(out, key=lambda x: x[0])]


def playlist_id(yt, title, cache):
    if not title:
        return None
    if not cache:
        req = yt.playlists().list(part="snippet", mine=True, maxResults=50)
        while req is not None:
            res = req.execute()
            for p in res.get("items", []):
                cache[p["snippet"]["title"]] = p["id"]
            req = yt.playlists().list_next(req, res)
    if title not in cache:
        p = yt.playlists().insert(part="snippet,status", body={"snippet": {"title": title, "defaultLanguage": "hi"},
                                                               "status": {"privacyStatus": "public"}}).execute()
        cache[title] = p["id"]; print(f"created playlist: {title}")
    return cache[title]


def thumb_retries():
    out = []
    for m, video, cover in all_metas():
        meta = json.load(open(m, encoding="utf-8"))
        if meta.get("youtube_id") and any("thumbnail" in n for n in meta.get("notes", [])) and os.path.exists(cover):
            out.append((m, cover, meta))
    return out


def main():
    items = pending(); thumbs = thumb_retries()
    if not items and not thumbs:
        print("Nothing to upload."); return
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    yt = build("youtube", "v3", credentials=creds(), cache_discovery=False)
    want = os.environ.get("YT_CHANNEL_ID", "UCx70naO0DMEATXMUHYWaP6Q")
    mine = [c["id"] for c in yt.channels().list(part="id", mine=True).execute().get("items", [])]
    if want not in mine:   # safety: never upload to the wrong channel (e.g. That's The Trick)
        print(f"::error::The Google login is for channel {mine}, not Dadi Ke Kisse ({want}). Redo README step 4 and pick the Dadi Ke Kisse channel.")
        sys.exit(1)
    now = dt.datetime.now(dt.timezone.utc); bump = 0; done = 0; cache = {}; failed = []; limited = False
    for path, cover, meta in thumbs:   # covers that could not be set before (e.g. channel not phone-verified yet)
        try:
            yt.thumbnails().set(videoId=meta["youtube_id"], media_body=MediaFileUpload(cover, mimetype="image/png")).execute()
            meta["notes"] = [n for n in meta.get("notes", []) if "thumbnail" not in n]
            json.dump(meta, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"thumbnail set for {meta['slug']}")
        except HttpError as e:
            print(f"::warning::{meta['slug']}: thumbnail still not allowed ({e.resp.status}); verify the channel's phone number in YouTube Studio")
            break
    for path, video, cover, meta in items[:MAX_PER_RUN]:
        slug = meta["slug"]
        when = dt.datetime.fromisoformat(meta["publish_at"]).astimezone(dt.timezone.utc) if meta.get("publish_at") else now
        if when < now + dt.timedelta(minutes=15):          # slot already passed: publish a few minutes from now, spaced out
            bump += 1; when = now + dt.timedelta(minutes=15 + 20 * (bump - 1))
        status = {"privacyStatus": "private", "publishAt": when.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                  "selfDeclaredMadeForKids": bool(meta.get("made_for_kids", False)), "embeddable": True, "license": "youtube"}
        body = {"snippet": {"title": meta["title"][:100], "description": meta["description"][:4900], "tags": meta.get("tags", [])[:15],
                            "categoryId": str(meta.get("category_id", "1")), "defaultLanguage": meta.get("language", "hi"),
                            "defaultAudioLanguage": meta.get("language", "hi")}, "status": status}
        try:
            media = MediaFileUpload(video, mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
            req = yt.videos().insert(part="snippet,status", body=body, media_body=media, notifySubscribers=True)
            res = None
            while res is None:
                _, res = req.next_chunk()
            vid = res["id"]
        except HttpError as e:
            body_txt = (e.content or b"").lower()
            if b"uploadlimitexceeded" in body_txt or b"quotaexceeded" in body_txt:
                limited = True
                print(f"::warning::YouTube's daily upload limit for this channel is reached; {slug} and the rest wait for the next run (every 6 hours).")
                break
            print(f"::error::{slug}: upload failed: {e}"); failed.append(slug)
            continue
        print(f"uploaded {slug}: https://youtube.com/shorts/{vid}  (goes public {when.isoformat()})")
        notes = []
        if os.path.exists(cover):
            try:
                yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(cover, mimetype="image/png")).execute()
            except HttpError as e:
                notes.append("thumbnail skipped (verify the channel's phone number to allow custom thumbnails)")
                print(f"::warning::{slug}: thumbnail not set: {e}")
        try:
            pid = playlist_id(yt, meta.get("playlist"), cache)
            if pid:
                yt.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
        except HttpError as e:
            notes.append("playlist not set"); print(f"::warning::{slug}: playlist not set: {e}")
        meta.update(youtube_id=vid, url=f"https://youtube.com/shorts/{vid}", uploaded_at=now.isoformat(timespec="seconds"),
                    scheduled_for=when.isoformat(timespec="seconds"), notes=notes)
        json.dump(meta, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.remove(video)
        done += 1
        time.sleep(2)
    # human-readable log
    rows = []
    for m, _, _ in all_metas():
        x = json.load(open(m, encoding="utf-8"))
        rows.append((x.get("scheduled_for") or x.get("publish_at", ""), x["slug"], x.get("character", ""), x.get("url", "waiting"), x["title"]))
    with open(os.path.join(ROOT, "UPLOADS.md"), "w", encoding="utf-8") as f:
        f.write("# Dadi Ke Kisse uploads\n\nUpdated automatically by the upload workflow.\n\n| Goes public (UTC) | Slug | Character | YouTube | Title |\n|---|---|---|---|---|\n")
        for r in sorted(rows):
            f.write(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4].replace('|', '/')} |\n")
    waiting = len(pending())
    print(f"done: {done} uploaded, {len(failed)} failed {failed}, {waiting} still waiting" + (" (daily upload limit reached)" if limited else ""))
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
