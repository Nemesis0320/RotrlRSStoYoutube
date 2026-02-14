import argparse
import json
import os
import sys

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

from playlists import update_playlist_id

def upload_video(file_path, title, description, playlist_id=None, playlist_name=None):
    # Load OAuth token.json
    if not os.path.exists("token.json"):
        print("ERROR: token.json not found", file=sys.stderr)
        return None

    creds = Credentials.from_authorized_user_file(
        "token.json",
        [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube",
        ],
    )

    youtube = build("youtube", "v3", credentials=creds)

    # If playlist_id is None, create the playlist now
    if playlist_id is None and playlist_name is not None:
        try:
            request = youtube.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": playlist_name,
                        "description": f"All episodes from {playlist_name}",
                    },
                    "status": {"privacyStatus": "public"},
                },
            )
            response = request.execute()
            playlist_id = response["id"]
            update_playlist_id(playlist_name, playlist_id)
        except Exception as e:
            print(f"WARNING: Could not create playlist: {e}", file=sys.stderr)

    # Prepare upload request
    body = {
        "snippet": {
            "title": title,
            "description": description,
        },
        "status": {"privacyStatus": "public"},
    }

    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    # Upload
    response = None
    try:
        while response is None:
            status, response = request.next_chunk()
    except Exception as e:
        print(f"ERROR during upload: {e}", file=sys.stderr)
        return None

    # Extract videoId
    video_id = response.get("id")
    if not video_id:
        print("ERROR: No videoId returned", file=sys.stderr)
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
                            "videoId": video_id,
                        },
                    }
                },
            ).execute()
        except Exception as e:
            print(f"WARNING: Could not add to playlist: {e}", file=sys.stderr)

    return video_id

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
        # stdout must contain ONLY the video ID
        print(vid)
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
