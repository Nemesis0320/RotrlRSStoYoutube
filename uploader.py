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
BACKGROUND = "assets/1200x1200bf.webp"
UPLOADED_DB = "uploaded.json"
PLAYLIST_ID = os.environ.get("YOUTUBE_PLAYLIST_ID")

SPLIT_THRESHOLD_SECONDS = 90 * 60  # 90 minutes


def clean_description(text):
    """Strip HTML, decode entities, remove invalid chars, trim length."""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Decode HTML entities (&amp;, &quot;, etc.)
    text = unescape(text)

    # Remove control characters
    text = "".join(ch for ch in text if ch.isprintable() or ch in "\n\r\t")

    # Trim to YouTube's max allowed length
    return text[:4900]


def run_cmd(cmd):
    """Run a shell command and return output."""
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout.strip()


def get_duration(audio_file):
    """Return duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of",
        "default=noprint_wrappers=1:nokey=1", audio_file
    ]
    output = run_cmd(cmd)
    return float(output)


def split_audio(audio_file):
    """Split audio into two halves and return filenames + split timestamp."""
    duration = get_duration(audio_file)
    half = duration / 2

    part1 = "part1.mp3"
    part2 = "part2.mp3"

    # First half
    subprocess.run([
        "ffmpeg", "-i", audio_file, "-t", str(half), "-acodec", "copy", part1
    ], check=True)

    # Second half
    subprocess.run([
        "ffmpeg", "-i", audio_file, "-ss", str(half), "-acodec", "copy", part2
    ], check=True)

    return part1, part2, half


def generate_video(audio_file, output_file):
    """Render a 720x720 circular waveform video."""
    filter_complex = (
        "aformat=channel_layouts=mono,"
        "showwavespic=s=720x720:colors=gold|0.6,"
        "format=rgba,"
        "geq='r=255:g=215:b=0:a=if(lte((X-360)*(X-360)+(Y-360)*(Y-360),225*225),255,0)',"
        "scale=720:720[wave];"
        "[1][wave]overlay=0:0"
    )

    ffmpeg_cmd = [
        "ffmpeg",
        "-i", audio_file,
        "-loop", "1",
        "-i", BACKGROUND,
        "-filter_complex", filter_complex,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-c:a", "aac",
        "-shortest",
        output_file
    ]

    subprocess.run(ffmpeg_cmd, check=True)


def stitch_videos(part1_video, part2_video, output_file):
    """Stitch two videos using concat demuxer."""
    list_file = "concat_list.txt"
    with open(list_file, "w") as f:
        f.write(f"file '{part1_video}'\n")
        f.write(f"file '{part2_video}'\n")

    subprocess.run([
        "ffmpeg", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c", "copy", output_file
    ], check=True)

    os.remove(list_file)


def upload_to_youtube(title, description, video_file):
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
    r = requests.get(url, stream=True)
    with open(filename, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)


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

        audio_file = "temp.mp3"
        final_video = "output.mp4"

        download_audio(audio_url, audio_file)
        duration = get_duration(audio_file)

        if duration > SPLIT_THRESHOLD_SECONDS:
            # Split
            part1_audio, part2_audio, split_point = split_audio(audio_file)

            # Render each half
            part1_video = "part1.mp4"
            part2_video = "part2.mp4"
            generate_video(part1_audio, part1_video)
            generate_video(part2_audio, part2_video)

            # Stitch
            stitch_videos(part1_video, part2_video, final_video)

            # Add chapter markers
            minutes = int(split_point // 60)
            seconds = int(split_point % 60)
            timestamp = f"{minutes:02d}:{seconds:02d}"

            description += f"\n\n00:00 Part 1\n{timestamp} Part 2\n"

            # Cleanup
            for f in [part1_audio, part2_audio, part1_video, part2_video]:
                if os.path.exists(f):
                    os.remove(f)

        else:
            # No split needed
            generate_video(audio_file, final_video)

        upload_to_youtube(title, description, final_video)

        uploaded.add(guid)
        save_uploaded(uploaded)

        # Cleanup
        if os.path.exists(audio_file):
            os.remove(audio_file)
        if os.path.exists(final_video):
            os.remove(final_video)


if __name__ == "__main__":
    main()
