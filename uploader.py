import os
import json
import time
import subprocess
import requests
import feedparser
DEBUG = True

import re
from html import unescape

# Toggle this later when your YouTube account is allowed to post links
ALLOW_LINKS = False

# Internal project imports
from playlists import ensure_playlist, add_video_to_playlist
from logger import log
from youtube_api import youtube

def clean_description(text):
    if not text:
        return ""

    # Decode HTML entities (RSS feeds often contain them)
    text = unescape(text)

    # Remove HTML tags entirely
    text = re.sub(r"<[^>]+>", "", text)

    # Strip control characters that YouTube rejects
    text = "".join(ch for ch in text if ch.isprintable() or ch in "\n\r\t")
    
    # Strip non-ASCII (emoji, etc.) to avoid YouTube edge cases
    text = text.encode("ascii", "ignore").decode()
    
    if not ALLOW_LINKS:
        # Remove protocol so URLs are no longer clickable
        text = re.sub(r"https?://", "", text)

        # Convert markdown links: [label](url) → label (url)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)

    # YouTube hard limit is 5000 chars; stay safely under
    return text[:4900]

def log(*args):
    if DEBUG:
        print("[uploader]", *args, flush=True)
from datetime import datetime, timedelta

# Config
AUDIO_FILE = "audio.mp3"
PART1_AUDIO = "part1.mp3"
PART2_AUDIO = "part2.mp3"
PART1_VIDEO = "part1.mp4"
PART2_VIDEO = "part2.mp4"
FINAL_VIDEO = "final.mp4"
UPLOADED_FILE = "uploaded.json"
QUOTA_FILE = "quota_state.json"
STATS_FILE = "daily_stats.json"
SUMMARY_FILE = "summary.txt"
RSS_URL = os.getenv("RSS_URL")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
YOUTUBE_PLAYLIST_ID = os.getenv("YOUTUBE_PLAYLIST_ID")
RUN_INTERVAL_HOURS = 2

# Discord
def send_discord_embed(title, description="", color=0x3498DB, fields=None, thumbnail=False, ep=None):
    data = {"embeds": [{"title": title, "description": description, "color": color}]}
    if fields:
        data["embeds"][0]["fields"] = [{"name": n, "value": v, "inline": inline} for n, v, inline in fields]
    if thumbnail:
        data["embeds"][0]["thumbnail"] = {"url": "https://i.imgur.com/8QfQFQp.png"}
    if ep is not None:
        data["embeds"][0]["footer"] = {"text": f"Episode index: {ep}"}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=10)
    except:
        pass

def send_discord_summary(title, season_label, episode_number, youtube_url, thumbnail_url, render_time, upload_time):
    fields = [
        ("Season", season_label, True),
        ("Episode", str(episode_number), True),
        ("YouTube", youtube_url, False),
        ("Render Time", f"{render_time:.2f} seconds", True),
        ("Upload Time", f"{upload_time:.2f} seconds", True),
    ]

    data = {
        "content": "",  # REQUIRED so Discord doesn't drop the embed
        "embeds": [
            {
                "title": f"Upload Complete: {title}",
                "color": 0x2ECC71,
                "thumbnail": {"url": thumbnail_url},
                "fields": [
                    {"name": n, "value": v, "inline": inline}
                    for n, v, inline in fields
                ],
            }
        ]
    }

    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=10)
    except:
        pass

def write_summary(text):
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        f.write(text)

# Quota system
def load_quota_state():
    if not os.path.exists(QUOTA_FILE):
        return {"date": current_pt_date(), "used": 0}
    with open(QUOTA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_quota_state(state):
    with open(QUOTA_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)

def current_pt_date():
    now = datetime.utcnow() - timedelta(hours=8)
    return now.strftime("%Y-%m-%d")

def reset_quota_if_needed(state):
    today = current_pt_date()
    if state["date"] != today:
        state["date"] = today
        state["used"] = 0
        save_quota_state(state)
    return state

def record_quota_usage(amount):
    state = load_quota_state()
    state = reset_quota_if_needed(state)
    state["used"] += amount
    save_quota_state(state)

def get_remaining_quota():
    state = load_quota_state()
    state = reset_quota_if_needed(state)
    return 10000 - state["used"]

def check_quota_safely():
    remaining = get_remaining_quota()
    if remaining < 5000:
        send_discord_embed("Quota warning", f"Remaining quota: {remaining}", 0xE67E22)
    if remaining < 3000:
        send_discord_embed("Quota too low", f"Remaining quota: {remaining}. Aborting run.", 0xE74C3C)
        write_summary("Run aborted due to low quota.")
        return False
    return True

# Daily stats
def load_daily_stats():
    if not os.path.exists(STATS_FILE):
        return {"date": current_pt_date(), "episodes_uploaded_today": 0, "failures_today": 0, "total_runtime_today": 0.0}
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_daily_stats(stats):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f)

def reset_daily_stats_if_needed(stats):
    today = current_pt_date()
    if stats["date"] != today:
        stats["date"] = today
        stats["episodes_uploaded_today"] = 0
        stats["failures_today"] = 0
        stats["total_runtime_today"] = 0.0
        save_daily_stats(stats)
    return stats

# State files
def load_uploaded():
    if not os.path.exists(UPLOADED_FILE):
        return set()
    with open(UPLOADED_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))

def save_uploaded(uploaded):
    with open(UPLOADED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(uploaded), f)

# Utilities
def send_discord_summary(
    episode_title,
    season_label,
    episode_number,
    youtube_url,
    thumbnail_url,
    render_time,
    upload_time
):
    import requests
    import datetime

    webhook_url = DISCORD_WEBHOOK_URL

    season_ep = f"{season_label} EP {episode_number}"

    embed = {
        "title": f"{season_ep} Uploaded Successfully",
        "description": f"**{episode_title}** is now live on YouTube.",
        "url": youtube_url,
        "color": 0xFFD700,
        "thumbnail": {
            "url": thumbnail_url
        },
        "fields": [
            {
                "name": "Episode Title",
                "value": episode_title,
                "inline": False
            },
            {
                "name": "Season / Episode",
                "value": season_ep,
                "inline": True
            },
            {
                "name": "YouTube Link",
                "value": youtube_url,
                "inline": False
            },
            {
                "name": "Render Time",
                "value": f"{render_time:.2f} seconds",
                "inline": True
            },
            {
                "name": "Upload Time",
                "value": f"{upload_time:.2f} seconds",
                "inline": True
            }
        ],
        "timestamp": datetime.datetime.utcnow().isoformat()
    }

    payload = {
        "content": None,
        "embeds": [embed]
    }

    try:
        requests.post(webhook_url, json=payload, timeout=10)
    except:
        pass

def cleanup_files(*paths):
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except:
                pass

def run_cmd(cmd):
    log("RUN CMD:", " ".join(cmd))
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out_bytes, err_bytes = proc.communicate()
        out = out_bytes.decode("utf-8", "ignore")
        err = err_bytes.decode("utf-8", "ignore")

        if proc.returncode == 0:
            log("CMD OK:", " ".join(cmd))
            log("CMD OUT:", out)
            if err:
                log("CMD ERR (ignored):", err[:2000])
        else:
            log("CMD FAIL:", " ".join(cmd), "RC:", proc.returncode)
            log("CMD OUT:", out[:2000])
            log("CMD ERR:", err[:2000])

        # Return ONLY stdout — never merge stderr
        return out

    except Exception as e:
        log("CMD EXCEPTION:", " ".join(cmd), "ERR:", str(e))
        return ""

def format_seconds(sec):
    m = int(sec // 60)
    s = int(sec % 60)
    return f"{m:02d}:{s:02d}"

def get_duration(path):
    out = run_cmd(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path])
    try:
        return float(out.strip())
    except:
        return 0.0

def download_audio(url, out_path):
    log("DOWNLOAD AUDIO:", url, "->", out_path)
    cleanup_files(out_path)
    out = run_cmd(["wget", "-O", out_path, url])
    log("WGET OUT:", out[:1000])
    exists = os.path.exists(out_path)
    size = os.path.getsize(out_path) if exists else 0
    log("AUDIO EXISTS:", exists, "SIZE:", size)
    return exists and size > 0
    
# Rendering
def split_audio(in_path, p1, p2):
    cleanup_files(p1, p2)
    dur = get_duration(in_path)
    if dur <= 3600:
        run_cmd(["ffmpeg", "-y", "-i", in_path, "-c", "copy", p1])
        return dur, False
    mid = dur / 2
    run_cmd(["ffmpeg", "-y", "-i", in_path, "-t", str(mid), p1])
    run_cmd(["ffmpeg", "-y", "-i", in_path, "-ss", str(mid), p2])
    return dur, True

VIDEO_SIZE = "720x720"
VIDEO_FPS = 12
VIDEO_CRF = 30
AUDIO_BITRATE = "64k"

BG_IMAGE = "assets/1200x1200bf.png"
FONT_FILE = "assets/IMFellEnglishSC.ttf"

PODCAST_TITLE = "Clinton's Core Classics"

def render_video(audio, output, episode_title=None, season_label=None, episode_number=None):
    if episode_title is None:
        episode_title = "Untitled Episode"
    if season_label is None:
        season_label = "Season"
    log("RENDER VIDEO L3-CIRCULAR:", audio, "->", output)

    # REMOVE APOSTROPHES (FFmpeg-safe)
    episode_title = episode_title.replace("'", "")
    season_label = season_label.replace("'", "")
    # episode_number is numeric, safe

    # Canonical labels
    season_ep_label = f"{season_label} EP {episode_number}"
    ticker_text = f"{season_ep_label}: {episode_title}"

    # Escape characters for FFmpeg drawtext (double-quoted text="")
    def ffmpeg_escape(text):
        return (
            text
            .replace("\\", "\\\\")   # backslash
            .replace('"', '\\"')     # double quote
            .replace(":", "\\:")     # colon
            .replace(",", "\\,")     # comma
            .replace("[", "\\[")     # [
            .replace("]", "\\]")     # ]
            .replace("%", "\\%")     # %
            .replace("(", "\\(")     # (
            .replace(")", "\\)")     # )
        )

    safe_episode_title = ffmpeg_escape(episode_title)
    safe_season_ep_label = ffmpeg_escape(season_ep_label)
    safe_ticker_text = ffmpeg_escape(ticker_text)

    filter_complex = f"""
        [0:v]scale={VIDEO_SIZE}[bg];

        [1:a]asplit=2[a_main][a_clip];

        [a_main]showwaves=s={VIDEO_SIZE}:mode=line:rate={VIDEO_FPS}:colors=gold:scale=lin[wave_inner];

        [a_clip]showwaves=s={VIDEO_SIZE}:mode=line:rate={VIDEO_FPS}:colors=red:scale=lin[wave_clip_raw];
        [wave_clip_raw][2:v]alphamerge[wave_clip_masked];

        [wave_inner]copy[polar_inner];
        [wave_clip_masked]copy[polar_clip];

        [polar_inner][polar_clip]blend=all_mode=lighten:all_opacity=1.0[combined];

        [combined][2:v]alphamerge[circ_wave];

        [bg][circ_wave]overlay=(W-w)/2:(H-h)/2[bg_wave];

        [bg_wave]drawtext=fontfile={FONT_FILE}:text='{safe_episode_title}':x=(w-text_w)/2:y=120:fontsize=40:fontcolor=gold:shadowx=2:shadowy=2[bg_titleline];

        [bg_titleline]drawtext=fontfile={FONT_FILE}:text='{safe_season_ep_label}':x=(w-text_w)/2:y=180:fontsize=32:fontcolor=white:shadowx=2:shadowy=2[bg_ep];

        [bg_ep]drawtext=fontfile={FONT_FILE}:text='{safe_ticker_text}':x=w-mod(t*120\,w+text_w):y=h-60:fontsize=26:fontcolor=white:shadowx=2:shadowy=2[final];

        [final]fade=t=in:st=0:d=0.8[final_faded];
    """.replace("\n", " ")

    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", BG_IMAGE,
        "-i", audio,
        "-i", "assets/circle_mask_720.png",
        "-filter_complex", filter_complex,
        "-map", "[final_faded]",
        "-map", "1:a",
        "-r", str(VIDEO_FPS),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "stillimage",
        "-crf", str(VIDEO_CRF),
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        "-shortest",
        output,
    ]

    out = run_cmd(cmd)
    log("RENDER L3-CIRC OUT:", out)

    if ("Error" in out or "Invalid" in out or "No such file" in out or "failed" in out.lower()):
        log("RENDER L3-CIRC ERROR DETECTED:", out[:2000])
        return False

    exists = os.path.exists(output)
    size = os.path.getsize(output) if exists else 0
    log("RENDER L3-CIRC RESULT:", exists, "SIZE:", size)

    return exists and size > 0

def stitch_videos(v1, v2, out_path):
    cleanup_files(out_path)
    with open("concat.txt", "w", encoding="utf-8") as f:
        f.write(f"file '{v1}'\nfile '{v2}'\n")
    run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", out_path])
    return os.path.exists(out_path)
    
def full_render_pipeline(title, season_label, episode_number):
    log("RENDER PIPELINE: start")
    dur, split = split_audio(AUDIO_FILE, PART1_AUDIO, PART2_AUDIO)
    log("SPLIT RESULT:", "duration", dur, "split", split)

    if not split:
        log("SINGLE PART RENDER:", PART1_AUDIO, "->", FINAL_VIDEO)
        if not render_video(
            PART1_AUDIO,
            FINAL_VIDEO,
            episode_title=title,
            season_label=season_label,
            episode_number=episode_number
        ):
            log("RENDER FAILED: single part")
            return None, dur

        exists = os.path.exists(FINAL_VIDEO)
        size = os.path.getsize(FINAL_VIDEO) if exists else 0
        log("FINAL VIDEO EXISTS:", exists, "SIZE:", size)
        return FINAL_VIDEO, dur

    log("TWO PART RENDER:", PART1_AUDIO, "->", PART1_VIDEO, "|", PART2_AUDIO, "->", PART2_VIDEO)

    ok1 = render_video(
        PART1_AUDIO,
        PART1_VIDEO,
        episode_title=title,
        season_label=season_label,
        episode_number=episode_number
    )

    ok2 = render_video(
        PART2_AUDIO,
        PART2_VIDEO,
        episode_title=title,
        season_label=season_label,
        episode_number=episode_number
    )

    log("RENDER PART1 OK:", ok1, "EXISTS:", os.path.exists(PART1_VIDEO))
    log("RENDER PART2 OK:", ok2, "EXISTS:", os.path.exists(PART2_VIDEO))

    if not (ok1 and ok2):
        log("RENDER FAILED: one or both parts")
        return None, dur

    log("STITCH:", PART1_VIDEO, "+", PART2_VIDEO, "->", FINAL_VIDEO)
    if not stitch_videos(PART1_VIDEO, PART2_VIDEO, FINAL_VIDEO):
        log("STITCH FAILED")
        return None, dur

    exists = os.path.exists(FINAL_VIDEO)
    size = os.path.getsize(FINAL_VIDEO) if exists else 0
    log("FINAL VIDEO EXISTS:", exists, "SIZE:", size)
    return FINAL_VIDEO, dur

# Upload logic
def upload_video(path, title, description, playlist_id):
    log("UPLOAD VIDEO:", path, "TITLE:", title, "PLAYLIST:", playlist_id)

    cmd = ["python3", "upload.py", "--file", path, "--title", title, "--description", description]
    if playlist_id:
        cmd += ["--playlist", playlist_id]

    out = run_cmd(cmd)
    err = ""  # run_cmd already merges stdout+stderr, so err is unused but defined
    log("UPLOAD.PY OUT:", out[:2000])

    vid = out.strip()

    import re
    # Detect YouTube upload limit exceeded
    if "uploadLimitExceeded" in out:
        log("UPLOAD FAILED: YouTube upload limit exceeded")
        send_discord_embed(
            "Upload limit exceeded",
            "YouTube is temporarily blocking new uploads.\n"
            "The pipeline will stop until the limit resets.",
            0xE74C3C
        )
        return None

    # Detect invalid or missing VIDEO_ID
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
        log("UPLOAD FAILED: invalid VIDEO_ID format:", vid)
        return None

    # Only charge quota on a valid VIDEO_ID
    record_quota_usage(1600)

    log("UPLOAD SUCCESS: VIDEO_ID", vid)
    return vid

def poll_video(video_id):
    log("POLL VIDEO:", video_id)
    record_quota_usage(1)
    out = run_cmd(["python3", "check_status.py", "--id", video_id])
    log("CHECK_STATUS OUT:", out[:1000])
    if "LIVE" in out:
        log("VIDEO LIVE:", video_id)
        return True
    log("VIDEO NOT LIVE YET:", video_id)
    return False

def aggressive_poll(video_id):
    log("AGGRESSIVE POLL START:", video_id)
    for i in range(12):
        log("POLL ATTEMPT:", i + 1)
        if poll_video(video_id):
            log("AGGRESSIVE POLL SUCCESS:", video_id)
            return True
        time.sleep(5)
    log("AGGRESSIVE POLL FAILED:", video_id)
    return False

def upload_with_retry(path, title, description, playlist_id):
    log("UPLOAD WITH RETRY:", path, title)

    # FIRST ATTEMPT
    vid = upload_video(path, title, description, playlist_id)
    if not vid:
        log("FIRST UPLOAD FAILED (no VIDEO_ID)")
        return None

    # POLL THE FIRST VIDEO
    poll_result = aggressive_poll(vid)

    if poll_result:
        log("FIRST VIDEO LIVE — NO RETRY NEEDED")
        return vid

    log("FIRST VIDEO NOT LIVE — CHECKING IF VIDEO EXISTS BEFORE RETRY")

    exists_check = poll_video(vid)

    if exists_check:
        log("VIDEO EXISTS BUT IS STILL PROCESSING — NO RETRY")
        return vid

    log("FIRST VIDEO INVALID — RETRYING UPLOAD")
    send_discord_embed("Re-upload attempt", f"Video {vid} not acknowledged. Retrying.", 0xE67E22)

    # SECOND ATTEMPT
    vid2 = upload_video(path, title, description, playlist_id)
    if not vid2:
        log("SECOND UPLOAD FAILED (no VIDEO_ID)")
        return None

    poll_result_2 = aggressive_poll(vid2)

    if poll_result_2:
        log("SECOND VIDEO LIVE — SUCCESS")
        return vid2

    log("SECOND VIDEO NOT LIVE — GIVING UP")
    return None
    
def render_and_upload(renderer_title, youtube_title, youtube_description, season_label, episode_number=None):
    log("RENDER+UPLOAD START:", renderer_title)

    # Measure render time
    import time
    t0 = time.time()
    video_path, dur = full_render_pipeline(renderer_title, season_label, episode_number)
    render_time = time.time() - t0

    log("FIRST RENDER RESULT:", video_path, "DUR:", dur, "RENDER_TIME:", render_time)

    if not video_path:
        send_discord_embed("Render failed", "Re-rendering...", 0xE74C3C)
        log("RETRY RENDER")

        t0 = time.time()
        video_path, dur = full_render_pipeline(renderer_title, season_label, episode_number)
        render_time = time.time() - t0

        log("SECOND RENDER RESULT:", video_path, "DUR:", dur, "RENDER_TIME:", render_time)

        if not video_path:
            log("RENDER FAILED TWICE")
            return None, render_time, None

    # Measure upload time
    t1 = time.time()
    vid = upload_with_retry(video_path, youtube_title, youtube_description, YOUTUBE_PLAYLIST_ID)
    upload_time = time.time() - t1

    log("UPLOAD RESULT VIDEO_ID:", vid, "UPLOAD_TIME:", upload_time)

    return vid, render_time, upload_time, dur

# RSS + queue
def fetch_rss():
    log("FETCH RSS:", RSS_URL)
    feed = feedparser.parse(RSS_URL)
    log("RSS ENTRIES:", len(feed.entries))
    return feed

import re
def parse_season_episode(title):
    """
    Parse titles of the form:
    'Season 1 EP. 4: Title'
    Returns (season, episode) or (None, None) if not matched.
    """
    m = re.search(r"[Ss]eason\s+(\d+)\s+EP\.\s*(\d+)", title)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None

def get_episodes(feed):
    eps = []
    for e in feed.entries:
        title = getattr(e, "title", "Untitled")
        url = e.enclosures[0].href if getattr(e, "enclosures", None) else None

        # Extract description (prefer content:encoded)
        if hasattr(e, "content") and e.content:
            description = e.content[0].value
        else:
            description = getattr(e, "description", "")

        # Parse season/episode using naming convention
        season, ep = parse_season_episode(title)

        # Ignore anything that isn't a real episode
        if season is None or ep is None:
            log("IGNORING EPISODE WITH NO SEASON/EP:", title)
            continue

        # Use stable episode key instead of RSS feed ID
        eid = f"S{season}E{ep}"

        log("EP:", "ID:", eid, "TITLE:", title, "URL:", url)

        if not url:
            continue

        # Strip leading "Season X EP Y" from the title if the feed includes it
        expected_prefix = f"Season {season} EP. {ep}"
        from html import unescape
        clean_title = unescape(title)
        if clean_title.startswith(expected_prefix):
            clean_title = clean_title[len(expected_prefix):].lstrip(" :-")

        # Include description in the tuple
        eps.append((eid, clean_title, url, season, ep, description))

    # Sort by season then episode
    eps.sort(key=lambda x: (x[3], x[4]))

    # Debug print sorted order
    for eid, title, url, season, ep, description in eps:
        log("SORTED:", season, ep, title)

    log("EPISODE LIST BUILT:", len(eps))
    return eps

def next_episode(uploaded, episodes):
    log("NEXT EPISODE: uploaded count", len(uploaded), "episodes total", len(episodes))
    for eid, title, url, season, ep, description in episodes:
        log("CHECK EP:", eid, "uploaded?", eid in uploaded)
        if eid not in uploaded:
            log("NEXT EP FOUND:", eid, f"S{season}E{ep}", title)
            return eid, title, url, season, ep, description
    log("NO NEW EPISODES")
    return None, None, None, None, None, None

# Main pipeline
def process_episode(eid, title, url, season, ep, uploaded, stats, description="", episode_thumbnail_url=None):
    log("PROCESS EP:", eid, f"S{season}E{ep}", title)

    season_label = f"Season {season}"
    # Determine if this is a bonus episode (no season number)
    is_bonus = season is None or season == 0 or season == ""
    
    cleanup_files(AUDIO_FILE, PART1_AUDIO, PART2_AUDIO, PART1_VIDEO, PART2_VIDEO, FINAL_VIDEO)
    if not download_audio(url, AUDIO_FILE):
        stats["failures_today"] += 1
        save_daily_stats(stats)
        send_discord_embed("Download failed", title, 0xE74C3C)
        log("DOWNLOAD FAILED:", url)
        return False

    # Clean title from get_episodes()
    from html import unescape
    clean_title = unescape(title)

    # Canonical YouTube title (matches ticker format)
    youtube_title = f"Clinton's Core Classics - {season_label} EP {ep}: {clean_title}"

    # Full YouTube description (header + RSS description)
    youtube_description = (
        f"{season_label} EP {ep} – {clean_title}\n\n"
        f"{description.strip()}"
    )
    youtube_description = clean_description(youtube_description)

    # Render + upload with corrected argument order
    vid, render_time, upload_time, dur = render_and_upload(
        clean_title,
        youtube_title,
        youtube_description,
        season_label=season_label,
        episode_number=ep
    )

    log("PROCESS EP RESULT:", "VIDEO_ID:", vid, "RENDER:", render_time, "UPLOAD:", upload_time)

    if not vid:
        stats["failures_today"] += 1
        save_daily_stats(stats)
        send_discord_embed("Upload failed", title, 0xE74C3C)
        log("UPLOAD FAILED FOR EP:", eid)
        return False

    # Playlist automation
    if is_bonus:
        playlist_id = ensure_playlist("Bonus Episodes")
    else:
        playlist_id = ensure_playlist(season_label)

add_video_to_playlist(vid, playlist_id)
    
    youtube_url = f"https://www.youtube.com/watch?v={vid}"

    # Episode-specific thumbnail if available; fallback otherwise.
    thumbnail_url = episode_thumbnail_url or \
        "https://raw.githubusercontent.com/Nemesis0320/RotrlRSStoYoutube/main/assets/1200x1200bf.png"

    send_discord_summary(
        youtube_title,
        season_label,
        ep,
        youtube_url,
        thumbnail_url,
        render_time,
        upload_time
    )

    uploaded.add(eid)
    save_uploaded(uploaded)
    stats["episodes_uploaded_today"] += 1
    stats["total_runtime_today"] += dur
    save_daily_stats(stats)

    send_discord_embed(
        "Upload complete",
        f"{title}\nDuration: {format_seconds(dur)}",
        0x2ECC71
    )

    log("EP SUCCESS:", eid, "VIDEO_ID:", vid)
    return True
    
def write_daily_summary(stats, uploaded_count):
    text = (
        f"Date: {stats['date']}\n"
        f"Episodes uploaded today: {stats['episodes_uploaded_today']}\n"
        f"Failures today: {stats['failures_today']}\n"
        f"Total runtime today: {format_seconds(stats['total_runtime_today'])}\n"
        f"Queue remaining: {uploaded_count}\n"
    )
    write_summary(text)

def main():
    log("MAIN START")
    send_discord_embed("Heartbeat", "Run started.")
    if not check_quota_safely():
        log("ABORT: LOW QUOTA")
        return
    feed = fetch_rss()
    episodes = get_episodes(feed)
    uploaded = load_uploaded()
    stats = load_daily_stats()
    stats = reset_daily_stats_if_needed(stats)
    log("STATE:", "uploaded", len(uploaded), "stats", stats)
    eid, title, url, season, ep, description = next_episode(uploaded, episodes)
    if not eid:
        write_summary("No new episodes.")
        send_discord_embed("Idle", "No new episodes.")
        log("NO NEW EPISODES, EXIT")
        return

    ok = process_episode(eid, title, url, season, ep, uploaded, stats, description=description)
    remaining = len([e for e in episodes if e[0] not in uploaded])
    write_daily_summary(stats, remaining)
    if ok:
        send_discord_embed("Run complete", f"Remaining episodes: {remaining}", 0x2ECC71)
    else:
        send_discord_embed("Run complete with errors", f"Remaining episodes: {remaining}", 0xE74C3C)
    log("MAIN END: ok =", ok, "remaining =", remaining)


if __name__ == "__main__":
    main()
