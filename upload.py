import argparse
import json
import os
import sys
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials


def upload_video(file_path, title, description, tags, playlist_id=None):
    # Load OAuth token.json
    if not os.path.exists("token.json"):
        print("[upload] ERROR: token.json not found")
        return None

    creds = Credentials.from_authorized_user_file(
        "token.json",
        [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube"
        ]
    )

    youtube = build("youtube", "v3", credentials=creds)

    # Prepare upload request
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags.split(",") if tags else []
        },
        "status": {
            "privacyStatus": "public"
        }
    }

    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    # Upload
    response = None
    try:
        while response is None:
            status, response = request.next_chunk()
    except Exception as e:
        print(f"[upload] ERROR during upload: {e}")
        return None

    # Extract videoId
    video_id = response.get("id")
    if not video_id:
        print("[upload] ERROR: No videoId returned")
        return None

    # Add to playlist if provided
    if playlist_id:
        try:
            youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id
                        }
                    }
                }
            ).execute()
        except Exception as e:
            print(f"[upload] WARNING: Could not add to playlist: {e}")

    return video_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--tags", default="")
    parser.add_argument("--playlist", default=None)
    args = parser.parse_args()

    vid = upload_video(
        args.file,
        args.title,
        args.description,
        args.tags,
        args.playlist
    )

    if vid:
        print(f"VIDEO_ID: {vid}")
        sys.exit(0)
    else:
        print("[upload] ERROR: Upload failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
