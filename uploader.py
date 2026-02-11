#!/usr/bin/env python3
import os
import sys
import re
import subprocess
import feedparser
import requests
from typing import List, Optional, Tuple

LOG_PREFIX = "[uploader]"

def log(*args):
    print(LOG_PREFIX, *args, flush=True)

# ------------------------------------------------------------
# EPISODE MODEL
# ------------------------------------------------------------
class Episode:
    def __init__(self, guid, title, enclosure_url, pubdate, season, episode):
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
# RSS PARSING
# ------------------------------------------------------------
SEASON_EPISODE_REGEXES = [
    re.compile(r"Season\s+(\d+)\s*[,:\- ]+\s*Episode\s+(\d+)", re.IGNORECASE),
    re.compile(r"S(\d+)\s*E(\d+)", re.IGNORECASE),
    re.compile(r"Season\s+(\d+)\s+Episode\s+(\d+)", re.IGNORECASE),
]

def parse_season_episode(title: str):
    for rx in SEASON_EPISODE_REGEXES:
        m = rx.search(title)
        if m:
            try:
                return int(m.group(1)), int(m.group(2))
            except ValueError:
                pass
    return None, None

def get_episodes_from_rss(rss_url: str):
    log("FETCHING RSS FEED:", rss_url)
    feed = feedparser.parse(rss_url)

    if feed.bozo:
        log("ERROR PARSING RSS:", feed.bozo_exception)
        sys.exit(1)

    episodes = []
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

        episodes.append(Episode(
            guid=guid,
            title=title,
            enclosure_url=enclosure_url,
            pubdate=pubdate,
            season=season,
            episode=ep,
        ))

    if not episodes:
        log("ERROR: NO EPISODES FOUND")
        sys.exit(1)

    episodes.sort(key=lambda e: e.sort_key())
    log(f"FOUND {len(episodes)} EPISODES")
    return episodes

# ------------------------------------------------------------
# PROCESSED TRACKING
# ------------------------------------------------------------
PROCESSED_FILE = "processed_episodes.txt"

def load_processed_guids():
    if not os.path.exists(PROCESSED_FILE):
        return set()
    with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}

def save_processed_guid(guid: str):
    with open(PROCESSED_FILE, "a", encoding="utf-8") as f:
        f.write(guid + "\n")

def pick_next_episode(episodes):
    processed = load_processed_guids()
    for ep in episodes:
        if ep.guid not in processed:
            log("NEXT EPISODE:", ep.title)
            return ep
    log("NO UNPROCESSED EPISODES")
    return None

# ------------------------------------------------------------
# AUDIO DOWNLOAD
# ------------------------------------------------------------
def download_audio(url: str, output_path: str):
    log("DOWNLOADING AUDIO:", url)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Referer": url.rsplit("/", 1)[0] + "/",
    }

    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        if r.status_code != 200:
            log("ERROR DOWNLOADING AUDIO:", r.status_code)
            sys.exit(1)

        with open(output_path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)

    log("AUDIO SAVED:", output_path)

# ------------------------------------------------------------
# FILTERGRAPH (FIXED VERSION)
# ------------------------------------------------------------
def build_filtergraph(podcast_title: str, season_label: str, episode_title: str) -> str:
    title_text = (
        podcast_title.replace("'", r"\'") + r"\n" +
        season_label.replace("'", r"\'") + r"\n" +
        episode_title.replace("'", r"\'")
    )

    return (
        "[0:v]scale=720:-1, crop=720:720, format=rgba[art];\n"
        "[1:a:0]showwavespic=s=720x120,format=rgba[vis_raw];\n"
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
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    log("FILTERGRAPH WRITTEN:", os.path.abspath(path))

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
        "-map", "1:a:0",
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

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    log(proc.stderr)

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with code {proc.returncode}")

# ------------------------------------------------------------
# UPLOAD STUB
# ------------------------------------------------------------
def upload_to_youtube(video_path: str, title: str, description: str):
    log("UPLOAD STUB:", video_path, title)

# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def main():
    podcast_title = "Clintons Core Classics"

    rss_url = os.environ.get("RSS_URL")
    if not rss_url:
        log("ERROR: RSS_URL not set")
        sys.exit(1)

    episodes = get_episodes_from_rss(rss_url)
    next_ep = pick_next_episode(episodes)
    if not next_ep:
        sys.exit(0)

    season_label = f"Season {next_ep.season}" if next_ep.season else "Season ?"
    episode_title = next_ep.title

    download_audio(next_ep.enclosure_url, "part1.mp3")

    required = [
        "assets/1200x1200bf.png",
        "assets/IMFellEnglishSC.ttf",
        "part1.mp3",
    ]
    for path in required:
        if not os.path.exists(path):
            log("ERROR: Missing file:", path)
            sys.exit(1)

    filtergraph = build_filtergraph(podcast_title, season_label, episode_title)
    debug_filtergraph("filtergraph.txt", filtergraph)

    safe_title = re.sub(r"[^\w\-]+", "_", next_ep.title).strip("_")
    output_video = f"{safe_title or 'episode'}.mp4"

    run_ffmpeg(output_video)

    save_processed_guid(next_ep.guid)

    upload_to_youtube(output_video, next_ep.title, next_ep.title)

    log("DONE:", next_ep.title)

if __name__ == "__main__":
    main()
