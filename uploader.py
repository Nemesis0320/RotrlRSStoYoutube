#!/usr/bin/env python3
import os
import sys
import subprocess
import feedparser
import requests

LOG_PREFIX = "[uploader]"

def log(*args):
    print(LOG_PREFIX, *args, flush=True)

# ------------------------------------------------------------
# RSS FETCH
# ------------------------------------------------------------
def get_latest_enclosure_url(rss_url: str) -> str:
    log("FETCHING RSS FEED VIA FEEDPARSER:", rss_url)
    feed = feedparser.parse(rss_url)

    if feed.bozo:
        log("ERROR PARSING RSS FEED:", feed.bozo_exception)
        sys.exit(1)

    if not feed.entries:
        log("ERROR: RSS FEED HAS NO ENTRIES")
        sys.exit(1)

    entry = feed.entries[0]

    if not entry.enclosures:
        log("ERROR: LATEST ENTRY HAS NO ENCLOSURES")
        sys.exit(1)

    url = entry.enclosures[0].href
    log("FOUND ENCLOSURE URL:", url)
    return url

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
        with requests.get(url, headers=headers, stream=True, timeout=30) as r:
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
# FILTERGRAPH GENERATOR (FEATHERED MASK)
# ------------------------------------------------------------
def build_filtergraph(podcast_title, season_label, episode_title):
    title_text = (
        podcast_title.replace("'", r"\'") +
        r"\n" +
        season_label.replace("'", r"\'") +
        r"\n" +
        episode_title.replace("'", r"\'")
    )

    return (
        "[0:v]scale=720:720:force_original_aspect_ratio=cover,"
        "crop=720:720,format=rgba[art];\n"

        "color=size=720x720:color=black@0[mask_base];\n"
        "[mask_base]drawbox=x=30:y=30:w=660:h=660:color=white@1.0:radius=330[mask_circle];\n"
        "[mask_circle]boxblur=20:20[mask_feather];\n"

        "[1:a]showwavespic=s=720x40:mode=line:rate=12:colors=gold,format=rgba[vis_gold];\n"
        "[1:a]showwavespic=s=720x40:mode=line:rate=12:colors=red,format=rgba[vis_red];\n"
        "[vis_gold][vis_red]blend=all_mode=lighten:all_opacity=1.0[vis];\n"

        "[mask_feather][vis]alphamerge[vis_masked];\n"

        "[vis_masked][art]overlay=x=(W-w)/2:y=(H-h)/2[pre_fisheye];\n"
        "[pre_fisheye]v360=input=rectilinear:output=fisheye[fisheye];\n"

        f"[fisheye]drawtext=fontfile=assets/IMFellEnglishSC.ttf:"
        f"text='{title_text}':x=(w-text_w)/2:y=60:fontsize=32:"
        f"line_spacing=10:fontcolor=white[final];\n"

        "[final]fade=t=in:st=0:d=0.8[final_faded]\n"
    )

# ------------------------------------------------------------
# DEBUG DUMP
# ------------------------------------------------------------
def debug_filtergraph(path: str, content: str):
    log("FINAL FILTERGRAPH:", repr(content))

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

    log("WROTE FILTERGRAPH TO:", os.path.abspath(path))

    log("---- FILTERGRAPH.TXT CONTENTS ----")
    with open(path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            log(f"{idx:03d}:", repr(line))
    log("---- END FILTERGRAPH.TXT ----")

    log("---- FILTERGRAPH.TXT RAW BYTES ----")
    with open(path, "rb") as f:
        log(f.read())
    log("---- END RAW BYTES ----")

# ------------------------------------------------------------
# RUN FFMPEG
# ------------------------------------------------------------
def run_ffmpeg():
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
        "final.mp4",
    ]

    log("USING FILTERGRAPH SCRIPT:", os.path.abspath("filtergraph.txt"))
    log("FILTERGRAPH EXISTS:", os.path.exists("filtergraph.txt"))
    if os.path.exists("filtergraph.txt"):
        log("FILTERGRAPH SIZE:", os.path.getsize("filtergraph.txt"))
    log("CURRENT WORKING DIRECTORY:", os.getcwd())
    log("CMD LIST:", cmd)

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    log("CMD STDOUT:", proc.stdout)
    log("CMD STDERR:", proc.stderr)

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with code {proc.returncode}")

# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def main():
    podcast_title = "Clintons Core Classics"
    season_label = "Season 6"
    episode_title = "Season 6 Spires of Xin-Shalast Teaser"

    rss_url = os.environ.get("RSS_URL")
    if not rss_url:
        log("ERROR: RSS_URL environment variable not set")
        sys.exit(1)

    enclosure_url = get_latest_enclosure_url(rss_url)
    download_audio(enclosure_url, "part1.mp3")

    for path in ("assets/1200x1200bf.png", "part1.mp3", "assets/IMFellEnglishSC.ttf"):
        if not os.path.exists(path):
            log("ERROR: Missing required file:", path)
            sys.exit(1)

    filtergraph = build_filtergraph(
        podcast_title,
        season_label,
        episode_title,
    )

    debug_filtergraph("filtergraph.txt", filtergraph)
    run_ffmpeg()

    log("Rendering complete: final.mp4")

if __name__ == "__main__":
    main()
