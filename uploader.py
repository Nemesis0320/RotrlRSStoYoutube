import os
import json
import time
import re
import feedparser
import requests
import subprocess
from html import unescape
from datetime import datetime, timezone, date
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# -----------------------------
# Config
# -----------------------------
RSS_FEED = "https://castopod.aroah.website/@ClintonsCoreClassics/feed.xml"
BACKGROUND = "assets/1200x1200bf.png"
UPLOADED_DB = "uploaded.json"
DAILY_STATS_DB = "daily_stats.json"
PLAYLIST_ID = os.environ.get("YOUTUBE_PLAYLIST_ID")

SPLIT_THRESHOLD_SECONDS = 90 * 60  # 90 minutes
RUN_INTERVAL_HOURS = 2            # for ETA calculations

TMPDIR = os.environ.get("TMPDIR", "/dev/shm")
AUDIO_FILE = os.path.join(TMPDIR, "temp.mp3")
PART1_AUDIO = os.path.join(TMPDIR, "part1.mp3")
PART2_AUDIO = os.path.join(TMPDIR, "part2.mp3")
PART1_VIDEO = os.path.join(TMPDIR, "part1.mp4")
PART2_VIDEO = os.path.join(TMPDIR, "part2.mp4")
FINAL_VIDEO = os.path.join(TMPDIR, "output.mp4")

# Fallback thumbnail (GitHub raw URL)
FALLBACK_THUMBNAIL_URL = (
    "https://raw.githubusercontent.com/"
    "Nemesis0320/RotrlRSStoYoutube/main/assets/1200x1200bf.png"
)


# -----------------------------
# Discord helpers
# -----------------------------
def build_thumbnail(ep):
    # Try RSS episode image first
    url = None
    image = getattr(ep, "image", None)
    if image and getattr(image, "href", None):
        url = image.href
    # Fallback to static background
    if not url:
        url = FALLBACK_THUMBNAIL_URL
    return {"url": url}


def send_discord_embed(title, description=None, color=0x5865F2,
                       fields=None, thumbnail=False, ep=None):
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        return

    embed = {
        "title": title,
        "description": description or "",
        "color": color,
    }

    if fields:
        embed["fields"] = [
            {"name": name, "value": value, "inline": inline}
            for (name, value, inline) in fields
        ]

    if thumbnail:
        embed["thumbnail"] = build_thumbnail(ep)

    payload = {"embeds": [embed]}
    try:
        requests.post(webhook, json=payload, timeout=10)
    except Exception:
        pass


def heartbeat(message, queue_length=None, next_title=None, eta_hours=None):
    fields = []
    if queue_length is not None:
        fields.append(("Queue length", str(queue_length), True))
    if next_title:
        fields.append(("Next episode", next_title, False))
    if eta_hours is not None:
        fields.append(("Estimated completion", f"~{eta_hours:.1f} hours", True))

    send_discord_embed(
        "🫀 Heartbeat",
        description=message,
        color=0x2ECC71,
        fields=fields,
        thumbnail=False,
    )


# -----------------------------
# GitHub summary writer
# -----------------------------
def write_summary(text):
    with open("summary.txt", "w") as f:
        f.write(text)


# -----------------------------
# Utility functions
# -----------------------------
def clean_description(text):
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = "".join(ch for ch in text if ch.isprintable() or ch in "\n\r\t")
    return text[:4900]


def run_cmd(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout.strip()


def get_duration(audio_file):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of",
        "default=noprint_wrappers=1:nokey=1", audio_file
    ]
    output = run_cmd(cmd)
    return float(output)


def split_audio(audio_file):
    duration = get_duration(audio_file)
    half = duration / 2

    subprocess.run([
        "ffmpeg", "-y", "-i", audio_file, "-t", str(half),
        "-acodec", "copy", PART1_AUDIO
    ], check=True)

    subprocess.run([
        "ffmpeg", "-y", "-i", audio_file, "-ss", str(half),
        "-acodec", "copy", PART2_AUDIO
    ], check=True)

    return PART1_AUDIO, PART2_AUDIO, half


def generate_video(audio_file, output_file):
    send_discord_embed(
        "🎛 Rendering waveform",
        description=f"Source: `{os.path.basename(audio_file)}`",
        color=0xF1C40F,
        thumbnail=False,
    )

    filter_complex = (
        "aformat=channel_layouts=mono,"
        "showwavespic=s=480x480:colors=gold|0.6,"
        "format=rgba,"
        "geq='r=255:g=215:b=0:a=if(lte((X-240)*(X-240)+(Y-240)*(Y-240),150*150),255,0)',"
        "scale=480:480[wave];"
        "[1][wave]overlay=0:0"
    )

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-i", audio_file,
        "-loop", "1",
        "-i", BACKGROUND,
        "-filter_complex", filter_complex,
        "-c:v", "libx264",
        "-preset", "faster",
        "-crf", "20",
        "-c:a", "aac",
        "-shortest",
        "-movflags", "+faststart",
        output_file
    ]

    subprocess.run(ffmpeg_cmd, check=True)


def stitch_videos(part1_video, part2_video, output_file):
    send_discord_embed(
        "🔗 Stitching video parts",
        description="Combining part 1 and part 2 into final video.",
        color=0x9B59B6,
        thumbnail=False,
    )

    list_file = os.path.join(TMPDIR, "concat_list.txt")
    with open(list_file, "w") as f:
        f.write(f"file '{part1_video}'\n")
        f.write(f"file '{part2_video}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_file, "-c", "copy", output_file
    ], check=True)

    os.remove(list_file)


def upload_to_youtube_with_retry(title, description, video_file, max_retries=3):
    attempt = 0
    last_error = None

    while attempt < max_retries:
        attempt += 1
        send_discord_embed(
            "📤 Uploading to YouTube",
            description=f"Attempt {attempt} for **{title}**",
            color=0x3498DB,
            thumbnail=False,
        )
        try:
            creds = Credentials.from_authorized_user_file(
                "token.json",
                ["https://www.googleapis.com/auth/youtube.upload"]
            )
            youtube = build("youtube", "v3", credentials=creds)

            request_body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "categoryId": "22"
                },
                "status": {
                    "privacyStatus": "public"
                }
            }

            media = MediaFileUpload(video_file, chunksize=-1, resumable=True)
            request = youtube.videos().insert(
                part="snippet,status",
                body=request_body,
                media_body=media
            )
            response = request.execute()

            video_id = response["id"]

            if PLAYLIST_ID:
                youtube.playlistItems().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": PLAYLIST_ID,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": video_id
                            }
                        }
                    }
                ).execute()

            return video_id

        except Exception as e:
            last_error = e
            if attempt < max_retries:
                time.sleep(10 * attempt)
            else:
                raise last_error


def download_audio(url, filename, max_retries=3):
    attempt = 0
    last_error = None

    while attempt < max_retries:
        attempt += 1
        send_discord_embed(
            "⬇️ Downloading audio",
            description=f"Attempt {attempt}\nURL: {url}",
            color=0x1ABC9C,
            thumbnail=False,
        )
        try:
            r = requests.get(url, stream=True, timeout=60)
            r.raise_for_status()
            with open(filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                time.sleep(5 * attempt)
            else:
                raise last_error


def cleanup_files(*paths):
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


def format_seconds(sec):
    sec = int(sec)
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def parse_episode_numbers(title):
    """
    Parse 'Season X - Episode Y' from title.
    Returns (season, episode) or (None, None).
    """
    m = re.search(r"Season\s+(\d+)\s*-\s*Episode\s+(\d+)", title, re.IGNORECASE)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


# -----------------------------
# Uploaded + daily stats
# -----------------------------
def load_uploaded():
    if not os.path.exists(UPLOADED_DB):
        return set()
    with open(UPLOADED_DB, "r") as f:
        return set(json.load(f))


def save_uploaded(uploaded):
    with open(UPLOADED_DB, "w") as f:
        json.dump(list(uploaded), f)


def load_daily_stats():
    if not os.path.exists(DAILY_STATS_DB):
        return {
            "last_digest_date": None,
            "episodes_uploaded_today": 0,
            "total_runtime_today": 0.0,
            "failures_today": 0,
        }
    with open(DAILY_STATS_DB, "r") as f:
        return json.load(f)


def save_daily_stats(stats):
    with open(DAILY_STATS_DB, "w") as f:
        json.dump(stats, f)


def maybe_send_daily_digest(stats, queue_length):
    # Compare stored date with today (UTC)
    today_str = date.today().isoformat()
    last = stats.get("last_digest_date")

    if last == today_str:
        return  # already sent today

    # Only send if we have any activity
    episodes = stats.get("episodes_uploaded_today", 0)
    runtime = stats.get("total_runtime_today", 0.0)
    failures = stats.get("failures_today", 0)

    if episodes == 0 and failures == 0:
        # Still update date so we don't spam empty digests
        stats["last_digest_date"] = today_str
        save_daily_stats(stats)
        return

    eta_hours = queue_length * RUN_INTERVAL_HOURS

    send_discord_embed(
        "📅 Daily Digest",
        description="Summary of pipeline activity for today.",
        color=0x8E44AD,
        fields=[
            ("Episodes uploaded today", str(episodes), True),
            ("Total runtime processed", format_seconds(runtime), True),
            ("Failures today", str(failures), True),
            ("Queue remaining", str(queue_length), True),
            ("Estimated completion", f"~{eta_hours:.1f} hours", True),
        ],
        thumbnail=True,
        ep=None,
    )

    stats["last_digest_date"] = today_str
    stats["episodes_uploaded_today"] = 0
    stats["total_runtime_today"] = 0.0
    stats["failures_today"] = 0
    save_daily_stats(stats)


# -----------------------------
# Main pipeline
# -----------------------------
def main():
    uploaded = load_uploaded()
    daily_stats = load_daily_stats()

    feed = feedparser.parse(RSS_FEED)
    episodes = list(reversed(feed.entries))

    # Determine queue length and next episode for heartbeat
    remaining = [ep for ep in episodes if ep.get("guid", ep.link) not in uploaded]
    queue_length = len(remaining)
    next_title = remaining[0].title if remaining else "None"
    eta_hours = queue_length * RUN_INTERVAL_HOURS

    heartbeat(
        "Pipeline run started. Checking for new episodes…",
        queue_length=queue_length,
        next_title=next_title,
        eta_hours=eta_hours,
    )

    # Daily digest check (once per day)
    maybe_send_daily_digest(daily_stats, queue_length)

    if not remaining:
        send_discord_embed(
            "✔️ No new episodes",
            description="No new episodes found. Pipeline idle until next run.",
            color=0x95A5A6,
            thumbnail=False,
        )
        write_summary("## Podcast Upload Summary\n\nNo new episodes found.\n")
        return

    start_run = time.time()

    # Process only ONE new episode per run
    ep = remaining[0]
    guid = ep.get("guid", ep.link)
    title = ep.title
    raw_description = ep.get("description", "")
    description = clean_description(raw_description)
    audio_url = ep.enclosures[0].href

    season_num, episode_num = parse_episode_numbers(title)
    absolute_index = episodes.index(ep) + 1  # 1-based index

    fields = [
        ("GUID", guid, False),
        ("Audio URL", audio_url, False),
        ("Queue length", str(queue_length), True),
        ("Absolute index", str(absolute_index), True),
    ]
    if season_num is not None and episode_num is not None:
        fields.insert(0, ("Season", str(season_num), True))
        fields.insert(1, ("Episode", str(episode_num), True))

    send_discord_embed(
        "🎬 Starting episode processing",
        description=f"**{title}**",
        color=0xE67E22,
        fields=fields,
        thumbnail=True,
        ep=ep,
    )

    cleanup_files(AUDIO_FILE, PART1_AUDIO, PART2_AUDIO, PART1_VIDEO, PART2_VIDEO, FINAL_VIDEO)

    t_download_start = time.time()
    download_audio(audio_url, AUDIO_FILE)
    t_download_end = time.time()

    duration = get_duration(AUDIO_FILE)
    long_episode = duration > SPLIT_THRESHOLD_SECONDS

    t_render_start = time.time()

    if long_episode:
        send_discord_embed(
            "✂️ Long episode detected",
            description=f"Duration: {format_seconds(duration)}\nSplitting into two parts.",
            color=0xC0392B,
            thumbnail=False,
        )

        part1_audio, part2_audio, split_point = split_audio(AUDIO_FILE)

        generate_video(part1_audio, PART1_VIDEO)
        generate_video(part2_audio, PART2_VIDEO)

        stitch_videos(PART1_VIDEO, PART2_VIDEO, FINAL_VIDEO)

        minutes = int(split_point // 60)
        seconds = int(split_point % 60)
        timestamp = f"{minutes:02d}:{seconds:02d}"
        description += f"\n\n00:00 Part 1\n{timestamp} Part 2\n"

        cleanup_files(part1_audio, part2_audio, PART1_VIDEO, PART2_VIDEO)
    else:
        generate_video(AUDIO_FILE, FINAL_VIDEO)

    t_render_end = time.time()

    t_upload_start = time.time()
    try:
        video_id = upload_to_youtube_with_retry(title, description, FINAL_VIDEO)
        t_upload_end = time.time()

        url = f"https://youtu.be/{video_id}"

        total_time = time.time() - start_run
        download_time = t_download_end - t_download_start
        render_time = t_render_end - t_render_start
        upload_time = t_upload_end - t_upload_start

        # Update daily stats
        daily_stats["episodes_uploaded_today"] = daily_stats.get("episodes_uploaded_today", 0) + 1
        daily_stats["total_runtime_today"] = daily_stats.get("total_runtime_today", 0.0) + duration
        save_daily_stats(daily_stats)

        queue_remaining = queue_length - 1
        eta_hours_remaining = queue_remaining * RUN_INTERVAL_HOURS

        success_fields = [
            ("Duration", format_seconds(duration), True),
            ("Split", "Yes" if long_episode else "No", True),
            ("Download time", format_seconds(download_time), True),
            ("Render time", format_seconds(render_time), True),
            ("Upload time", format_seconds(upload_time), True),
            ("Total run time", format_seconds(total_time), True),
            ("Queue remaining", str(queue_remaining), True),
            ("Estimated completion", f"~{eta_hours_remaining:.1f} hours", True),
        ]
        if season_num is not None and episode_num is not None:
            success_fields.insert(0, ("Season", str(season_num), True))
            success_fields.insert(1, ("Episode", str(episode_num), True))
            success_fields.insert(2, ("Absolute index", str(absolute_index), True))

        send_discord_embed(
            "✅ Episode uploaded",
            description=f"**{title}**\n{url}",
            color=0x2ECC71,
            fields=success_fields,
            thumbnail=True,
            ep=ep,
        )

        # Per-run summary embed
        send_discord_embed(
            "📊 Run Summary",
            description=f"Run completed for **{title}**",
            color=0x2980B9,
            fields=[
                ("Duration", format_seconds(duration), True),
                ("Split", "Yes" if long_episode else "No", True),
                ("Download time", format_seconds(download_time), True),
                ("Render time", format_seconds(render_time), True),
                ("Upload time", format_seconds(upload_time), True),
                ("Total run time", format_seconds(total_time), True),
                ("Queue remaining", str(queue_remaining), True),
            ],
            thumbnail=True,
            ep=ep,
        )

        write_summary(f"""
## Podcast Upload Summary

**Episode:** {title}  
**URL:** {url}  

**Duration:** {format_seconds(duration)}  
**Split:** {"Yes" if long_episode else "No"}  

**Download time:** {format_seconds(download_time)}  
**Render time:** {format_seconds(render_time)}  
**Upload time:** {format_seconds(upload_time)}  
**Total run time:** {format_seconds(total_time)}  

**Queue remaining:** {queue_remaining}  

**Status:** Success  
""")

    except Exception as e:
        t_upload_end = time.time()
        upload_time = t_upload_end - t_upload_start

        daily_stats["failures_today"] = daily_stats.get("failures_today", 0) + 1
        save_daily_stats(daily_stats)

        failure_fields = [
            ("Error", f"`{e}`", False),
            ("Duration", format_seconds(duration), True),
            ("Upload time", format_seconds(upload_time), True),
            ("Queue remaining", str(queue_length), True),
        ]
        if season_num is not None and episode_num is not None:
            failure_fields.insert(0, ("Season", str(season_num), True))
            failure_fields.insert(1, ("Episode", str(episode_num), True))
            failure_fields.insert(2, ("Absolute index", str(absolute_index), True))

        send_discord_embed(
            "❌ Upload failed",
            description=f"**{title}**",
            color=0xE74C3C,
            fields=failure_fields,
            thumbnail=True,
            ep=ep,
        )

        write_summary(f"""
## Podcast Upload Summary

❌ Upload failed  

**Episode:** {title}  
**Error:** {e}  

**Duration:** {format_seconds(duration)}  
**Upload time:** {format_seconds(upload_time)}  
""")
        raise

    uploaded.add(guid)
    save_uploaded(uploaded)

    cleanup_files(AUDIO_FILE, FINAL_VIDEO)


if __name__ == "__main__":
    main()
