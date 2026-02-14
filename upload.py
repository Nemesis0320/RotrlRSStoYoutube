import argparse
import json
import os
import sys
import time

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

from playlists import update_playlist_id

def log(*args):
    print("[upload]", *args, file=sys.stderr, flush=True)

def build_youtube_client():
    if not os.path.exists("token.json"):
        log("ERROR: token.json not found")
        return None

    creds = Credentials.from_authorized_user_file(
        "token.json",
        [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube",
        ],
    )

    try:
        youtube = build("youtube", "v3", credentials=creds)
        return youtube
    except Exception as e:
        log("ERROR: Failed to build YouTube client:", str(e))
        return None

def create_playlist_with_retry(youtube, playlist_name, max_retries=3):
    """
    Create a playlist on YouTube with retry logic.
    Returns playlist_id or None.
    """
    if not playlist_name:
        return None

    body = {
        "snippet": {
            "title": playlist_name,
            "description": f"All episodes from {playlist_name}",
        },
        "status": {"privacyStatus": "public"},
    }

    backoff = 2
    for attempt in range(1, max_retries + 1):
        try:
            log(f"PLAYLIST CREATE ATTEMPT {attempt}/{max_retries}:", playlist_name)
            request = youtube.playlists().insert(part="snippet,status", body=body)
            response = request.execute()
            playlist_id = response.get("id")
            if not playlist_id:
                raise Exception("No playlist ID returned from YouTube")
            log("PLAYLIST CREATED:", playlist_name, playlist_id)
            update_playlist_id(playlist_name, playlist_id)
            return playlist_id
        except Exception as e:
            log(f"WARNING: Playlist creation failed on attempt {attempt}:", str(e))
            if attempt == max_retries:
                log("PLAYLIST CREATION FAILED AFTER MAX RETRIES:", playlist_name)
                return None
            log(f"Retrying playlist creation in {backoff} seconds...")
            time.sleep(backoff)
            backoff *= 2

def add_to_playlist_with_retry(youtube, playlist_id, video_id, max_retries=3):
    """
    Add a video to a playlist with retry logic.
    """
    if not playlist_id or not video_id:
        return

    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {
                "kind": "youtube#video",
                "videoId": video_id,
            },
        }
    }

    backoff = 2
    for attempt in range(1, max_retries + 1):
        try:
            log(
                f"PLAYLIST INSERT ATTEMPT {attempt}/{max_retries}:",
                playlist_id,
                video_id,
            )
            youtube.playlistItems().insert(part="snippet", body=body).execute()
            log("PLAYLIST INSERT OK:", playlist_id, video_id)
            return
        except Exception as e:
            log(
                f"WARNING: Could not add video to playlist on attempt {attempt}:",
                str(e),
            )
            if attempt == max_retries:
                log(
                    "PLAYLIST INSERT FAILED AFTER MAX RETRIES:",
                    playlist_id,
                    video_id,
                )
                return
            log(f"Retrying playlist insert in {backoff} seconds...")
            time.sleep(backoff)
            backoff *= 2

def upload_video(file_path, title, description, playlist_id=None, playlist_name=None):
    youtube = build_youtube_client()
    if youtube is None:
        return None

    # If playlist_id is None, create the playlist now (with retry)
    if playlist_id is None and playlist_name is not None:
        playlist_id = create_playlist_with_retry(youtube, playlist_name)

    body = {
        "snippet": {
            "title": title,
            "description": description,
        },
        "status": {"privacyStatus": "public"},
    }

    media = MediaFileUpload(file_path, chunksize=1024 * 1024, resumable=True)

    MAX_RETRIES = 3
    backoff = 2

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log(f"UPLOAD ATTEMPT {attempt}/{MAX_RETRIES}:", file_path, title)

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

            video_id = response.get("id")
            if not video_id:
                log("ERROR: No videoId returned from YouTube")
                raise Exception("Missing videoId")

            log("UPLOAD COMPLETE:", video_id)

            if playlist_id:
                add_to_playlist_with_retry(youtube, playlist_id, video_id)

            # stdout must contain ONLY the video ID
            print(video_id, flush=True)
            return video_id

        except Exception as e:
            log(f"ERROR during upload on attempt {attempt}:", str(e))
            if attempt == MAX_RETRIES:
                log("UPLOAD FAILED AFTER MAX RETRIES")
                return None
            log(f"Retrying upload in {backoff} seconds...")
            time.sleep(backoff)
            backoff *= 2

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--playlist", default=None)
    parser.add_argument("--playlist_name", default=None)
    args = parser.parse_args()

    vid = upload_video(
        args.file,
        args.title,
        args.description,
        args.playlist,
        args.playlist_name,
    )

    if vid:
        # stdout already printed ONLY the video ID in upload_video
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
