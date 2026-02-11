#!/usr/bin/env python3
import os
import sys
import re
import json
import base64
import subprocess
from typing import List, Optional, Tuple

import feedparser
import requests

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

LOG_PREFIX = "[uploader]"

def log(*args):
    print(LOG_PREFIX, *args, flush=True)

# ------------------------------------------------------------
# EPISODE MODEL
# ------------------------------------------------------------
class Episode:
    def __init__(
        self,
        guid: str,
        title: str,
        enclosure_url: str,
        pubdate: Optional[str],
        season: Optional[int],
        episode: Optional[int],
    ):
        self.guid = guid
        self.title = title
        self.enclosure_url = enclosure_url
        self.pubdate = pubdate
        self.season = season
        self.episode = episode

    def sort_key(self):
        s = self.season if self.season is not None else 9999
        e = self.episode if self.episode is not None else 9999
        return (s, e, self.pubdate or "", self.title)

# ------------------------------------------------------------
# RSS / EPISODE DISCOVERY
# ------------------------------------------------------------
SEASON_EPISODE_REGEXES = [
    re.compile(r"Season\s+(\d+)\s*[,:\- ]+\s*Episode\s+(\d+)", re.IGNORECASE),
    re.compile(r"S(\d+)\s*E(\d+)", re.IGNORECASE),
    re.compile(r"Season\s+(\d+)\s+Episode\s+(\d+)", re.IGNORECASE),
]

def parse_season_episode(title: str) -> Tuple[Optional[int], Optional[int]]:
    for rx in SEASON_EPISODE_REGEXES:
        m = rx.search(title)
        if m:
            try:
                season = int(m.group(1))
                episode = int(m.group(2))
                return season, episode
            except ValueError:
                continue
    return None, None

def get_episodes_from_rss(rss_url: str) -> List[Episode]:
    log("FETCHING RSS FEED:", rss_url)
    feed = feedparser.parse(rss_url)

    if feed.bozo:
        log("ERROR PARSING RSS FEED:", feed.bozo_exception)
        sys.exit(1)

    if not feed.entries:
        log("ERROR: RSS FEED HAS NO ENTRIES")
        sys.exit(1)

    episodes: List[Episode] = []

    for entry in feed.entries:
        title = getattr(entry, "title", "").strip()
        guid = getattr(entry, "id", "") or getattr(entry, "guid", "") or title
        pubdate = getattr(entry, "published", None)

        if not getattr(entry, "enclosures", None):
            continue

        enclosure = entry.enclosures[0]
        enclosure_url = getattr(enclosure, "href", None)
        if not enclosure_url:
            continue

        season, ep = parse_season_episode(title)

        episodes.append(
            Episode(
                guid=guid,
                title=title,
                enclosure_url=enclosure_url,
                pubdate=pubdate,
                season=season,
                episode=ep,
            )
        )

    if not episodes:
        log("ERROR: NO VALID EPISODES FOUND IN RSS")
        sys.exit(1)

    episodes.sort(key=lambda e: e.sort_key())
    log(f"FOUND {len(episodes)} EPISODES AFTER PARSING/SORTING")
    return episodes

# ------------------------------------------------------------
# PROCESSED EPISODE TRACKING
# ------------------------------------------------------------
PROCESSED_FILE = "processed_episodes.txt"

def load_processed_guids() -> set:
    if not os.path.exists(PROCESSED_FILE):
        return set()
    with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}

def save_processed_guid(guid: str):
    with open(PROCESSED_FILE, "a", encoding="utf-8") as f:
        f.write(guid + "\n")

def pick_next_episode(episodes: List[Episode]) -> Optional[Episode]:
    processed = load_processed_guids()
    for ep in episodes:
        if ep.guid not in processed:
            log("NEXT EPISODE TO PROCESS:", ep.title)
            if ep.season is not None and ep.episode is not None:
                log(f"  Parsed as Season {ep.season}, Episode {ep.episode}")
            return ep
    log("NO UNPROCESSED EPISODES LEFT")
    return None

# ------------------------------------------------------------
# AUDIO DOWNLOAD
# ------------------------------------------------------------
def download_audio(url: str, output_path: str):
    log("DOWNLOADING AUDIO FROM:", url)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": url.rsplit("/", 1)[0] + "/",
    }

    try:
        with requests.get(url, headers=headers, stream=True, timeout=60) as r:
            if r.status_code != 200:
                log("ERROR DOWNLOADING AUDIO: HTTP", r.status_code)
                sys.exit(1)

            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        log("AUDIO DOWNLOADED TO:", output_path)

    except Exception as e:
        log("ERROR DOWNLOADING AUDIO:", str(e))
        sys.exit(1)

# ------------------------------------------------------------
# FILTERGRAPH (MINIMAL, STABLE)
# ------------------------------------------------------------
def build_filtergraph(podcast_title: str, season_label: str, episode_title: str) -> str:
    title_text = (
        podcast_title.replace("'", r"\'") +
        r"\n" +
        season_label.replace("'", r"\'") +
        r"\n" +
        episode_title.replace("'", r"\'")
    )

    return (
        "[0:v]scale=720:-1, crop=720:720, format=rgba[art];\n"
        "[1:a]showwavespic=s=720x120,format=rgba[vis_raw];\n"
        "[vis_raw]colorchannelmixer=rr=1:gg=0:bb=0[vis_red];\n"
        "[vis_raw]colorchannelmixer=rr=1:gg=0.84:bb=0[vis_gold];\n"
        "[vis_red][vis_gold]blend=all_mode=lighten:all_opacity=1.0[vis];\n"
        "[art][vis]overlay=x=0:y=600[with_vis];\n"
        f"[with_vis]drawtext=fontfile=assets/IMFellEnglishSC.ttf:"
        f"text='{title_text}':x=(w-text_w)/2:y=40:fontsize=32:"
        f"line_spacing=10:fontcolor=white[with_text];\n"
        "[with_text]fade=t=in:st=0:d=0.8[final_faded]\n"
    )

def debug_filtergraph(path: str, content: str):
    log("FINAL FILTERGRAPH:", repr(content))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    log("WROTE FILTERGRAPH TO:", os.path.abspath(path))

# ------------------------------------------------------------
# FFMPEG RENDER
# ------------------------------------------------------------
def run_ffmpeg(output_path: str):
    cmd = [
        "ffmpeg",
        "-loglevel", "debug",
        "-y",
        "-loop", "1",
        "-i", "assets/1200x1200bf.png",
        "-i", "part1.mp3",
        "-filter_complex_script", os.path.abspath("filtergraph.txt"),
        "-map", "[final_faded]",
        "-map", "1:a",
        "-r", "12",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "stillimage",
        "-crf", "30",
        "-c:a", "aac",
        "-b:a", "64k",
        "-shortest",
        output_path,
    ]

    log("RUNNING FFMPEG:", " ".join(cmd))
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    log("FFMPEG STDERR:", proc.stderr)

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with code {proc.returncode}")

# ------------------------------------------------------------
# YOUTUBE AUTH / UPLOAD
# ------------------------------------------------------------
def load_youtube_credentials() -> Credentials:
    token_json = os.environ.get("YOUTUBE_TOKEN_JSON")
    token_b64 = os.environ.get("YOUTUBE_TOKEN_JSON_B64")

    if token_b64 and not token_json:
        token_json = base64.b64decode(token_b64).decode("utf-8")

    if not token_json:
        log("ERROR: YOUTUBE_TOKEN_JSON or YOUTUBE_TOKEN_JSON_B64 not set")
        sys.exit(1)

    info = json.loads(token_json)
    creds = Credentials.from_authorized_user_info(info, scopes=["https://www.googleapis.com/auth/youtube.upload"])
    return creds

def upload_to_youtube(video_path: str, title: str, description: str):
    creds = load_youtube_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "22",  # People & Blogs (adjust if you like)
        },
        "status": {
            "privacyStatus": "public",
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")

    log("STARTING YOUTUBE UPLOAD:", video_path)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log(f"UPLOAD PROGRESS: {int(status.progress() * 100)}%")

    log("YOUTUBE UPLOAD COMPLETE:", response.get("id"))

# ------------------------------------------------------------
# DISCORD NOTIFY (OPTIONAL)
# ------------------------------------------------------------
def notify_discord(message: str):
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        return
    try:
        requests.post(webhook, json={"content": message}, timeout=10)
    except Exception as e:
        log("DISCORD NOTIFY FAILED:", str(e))

# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def main():
    podcast_title = "Clintons Core Classics"

    rss_url = os.environ.get("RSS_URL")
    if not rss_url:
        log("ERROR: RSS_URL environment variable not set")
        sys.exit(1)

    episodes = get_episodes_from_rss(rss_url)
    next_ep = pick_next_episode(episodes)
    if not next_ep:
        notify_discord("No unprocessed episodes left.")
        sys.exit(0)

    if next_ep.season is not None:
        season_label = f"Season {next_ep.season}"
    else:
        season_label = "Season ?"

    episode_title = next_ep.title

    download_audio(next_ep.enclosure_url, "part1.mp3")

    required = [
        "assets/1200x1200bf.png",
        "part1.mp3",
        "assets/IMFellEnglishSC.ttf",
    ]
    for path in required:
        if not os.path.exists(path):
            log("ERROR: Missing required file:", path)
            sys.exit(1)

    filtergraph = build_filtergraph(
        podcast_title=podcast_title,
        season_label=season_label,
        episode_title=episode_title,
    )
    debug_filtergraph("filtergraph.txt", filtergraph)

    safe_title = re.sub(r"[^\w\-]+", "_", next_ep.title).strip("_")
    output_video = f"{safe_title or 'episode'}.mp4"

    run_ffmpeg(output_video)

    upload_to_youtube(
        video_path=output_video,
        title=next_ep.title,
        description=next_ep.title,
    )

    save_processed_guid(next_ep.guid)
    notify_discord(f"Uploaded episode: {next_ep.title}")

    log("DONE WITH EPISODE:", next_ep.title)

if __name__ == "__main__":
    main()
