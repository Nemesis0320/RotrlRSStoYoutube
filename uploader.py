import os
import json
import feedparser
import requests
import subprocess
import re
from html import unescape
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

RSS_FEED = "https://castopod.aroah.website/@ClintonsCoreClassics/feed.xml"
BACKGROUND = "assets/1200x1200bf.png"
UPLOADED_DB = "uploaded.json"
PLAYLIST_ID = os.environ.get("YOUTUBE_PLAYLIST_ID")

SPLIT_THRESHOLD_SECONDS = 90 * 60  # 90 minutes

TMPDIR = os.environ.get("TMPDIR", "/dev/shm")
AUDIO_FILE = os.path.join(TMPDIR, "temp.mp3")
PART1_AUDIO = os.path.join(TMPDIR, "part1.mp3")
PART2_AUDIO = os.path.join(TMPDIR, "part2.mp3")
PART1_VIDEO = os.path.join(TMPDIR, "part1.mp4")
PART2_VIDEO = os.path.join(TMPDIR, "part2.mp4")
FINAL_VIDEO = os.path.join(TMPDIR, "output.mp4")


# -----------------------------
# Discord Notifications
# -----------------------------
def notify_discord(message):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        return
    try:
        requests.post(url, json={"content": message})
    except Exception:
        pass


# -----------------------------
# GitHub Summary Writer
# -----------------------------
def write_summary(text):
    with open("summary.txt", "w") as f:
        f.write(text)


# -----------------------------
# Utility Functions
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
    notify_discord(f"🎛 Rendering waveform for `{os.path.basename(audio_file)}`…")

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
    notify_discord("🔗 Stitching video parts…")

    list_file = os.path.join(TMPDIR, "concat_list.txt")
    with open(list_file, "w") as f:
        f.write(f"file '{part1_video}'\n")
        f.write(f"file '{part2_video}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c", "copy", output_file
    ], check=True)

    os.remove(list_file)


def upload_to_youtube(title, description, video_file):
    notify_discord(f"📤 Uploading `{title}` to YouTube…")

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


def load_uploaded():
    if not os.path.exists(UPLOADED_DB):
        return set()
    with open(UPLOADED_DB, "r") as f:
        return set(json.load(f))


def save_uploaded(uploaded):
    with open(UPLOADED_DB, "w") as f:
        json.dump(list(uploaded), f)


def download_audio(url, filename):
    notify_discord(f"⬇️ Downloading audio…")
    r = requests.get(url, stream=True)
    r.raise_for_status()
    with open(filename, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)


def cleanup_files(*paths):
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


def main():
    uploaded = load_uploaded()
    feed = feedparser.parse(RSS_FEED)

    episodes = list(reversed(feed.entries))

    for ep in episodes:
        guid = ep.get("guid", ep.link)
        if guid in uploaded:
            continue

        title = ep.title
        raw_description = ep.get("description", "")
        description = clean_description(raw_description)
        audio_url = ep.enclosures[0].href

        notify_discord(f"🎬 Starting upload: **{title}**")

        cleanup_files(AUDIO_FILE, PART1_AUDIO, PART2_AUDIO, PART1_VIDEO, PART2_VIDEO, FINAL_VIDEO)

        download_audio(audio_url, AUDIO_FILE)
        duration = get_duration(AUDIO_FILE)

        if duration > SPLIT_THRESHOLD_SECONDS:
            notify_discord("✂️ Episode is long — splitting into two parts…")

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

        try:
            video_id = upload_to_youtube(title, description, FINAL_VIDEO)
            url = f"https://youtu.be/{video_id}"
            notify_discord(f"✅ Uploaded **{title}** — {url}")

            write_summary(f"""
## Podcast Upload Summary

**Episode:** {title}  
**Uploaded:** {url}  
**Status:** Success  
""")

        except Exception as e:
            notify_discord(f"❌ Upload failed: **{title}**\nError: `{e}`")
            write_summary(f"""
## Podcast Upload Summary

❌ Upload failed  
**Episode:** {title}  
**Error:** {e}  
""")
            raise

        uploaded.add(guid)
        save_uploaded(uploaded)

        cleanup_files(AUDIO_FILE, FINAL_VIDEO)

        break  # Only one episode per run

    else:
        notify_discord("✔️ No new episodes found. Pipeline idle.")
        write_summary("## Podcast Upload Summary\n\nNo new episodes found.\n")


if __name__ == "__main__":
    main()
