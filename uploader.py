import os
import json
import feedparser
import requests
import subprocess
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

RSS_FEED = "https://castopod.aroah.website/@ClintonsCoreClassics/feed.xml"
BACKGROUND = "assets/1200x1200bf.webp"
UPLOADED_DB = "uploaded.json"
PLAYLIST_ID = os.environ.get("YOUTUBE_PLAYLIST_ID")

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

def generate_video(audio_file, output_file):
    # Circular waveform mask parameters for 720x720
    # Center: (360, 360)
    # Radius: 225px

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

ffmpeg_cmd = [
    "ffmpeg",
    "-i", audio_file,
    "-loop", "1",
    "-i", BACKGROUND,
    "-filter_complex",
    (
        "aformat=channel_layouts=mono,"
        "showwavespic=s=720x720:colors=gold|0.6,"
        "format=rgba,"
        "geq='r=255:g=215:b=0:a=if(lte((X-360)*(X-360)+(Y-360)*(Y-360),225*225),255,0)',"
        "scale=720:720[wave];"
        "[1][wave]overlay=0:0"
    ),
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "18",
    "-c:a", "aac",
    "-shortest",
    output_file
]

    subprocess.run(ffmpeg_cmd, check=True)

def upload_to_youtube(title, description, video_file):
    creds = Credentials.from_authorized_user_file("token.json", ["https://www.googleapis.com/auth/youtube.upload"])
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

def main():
    uploaded = load_uploaded()
    feed = feedparser.parse(RSS_FEED)

    # Reverse order so oldest uploads first
    episodes = list(reversed(feed.entries))

    for ep in episodes:
        guid = ep.get("guid", ep.link)
        if guid in uploaded:
            continue

        title = ep.title
        description = ep.get("description", "")
        audio_url = ep.enclosures[0].href

        audio_file = "temp.mp3"
        video_file = "output.mp4"

        download_audio(audio_url, audio_file)
        generate_video(audio_file, video_file)
        upload_to_youtube(title, description, video_file)

        uploaded.add(guid)
        save_uploaded(uploaded)

        os.remove(audio_file)
        os.remove(video_file)

if __name__ == "__main__":
    main()
