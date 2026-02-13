import os
import json
from upload import youtube
from logger import log

PLAYLISTS_FILE = "playlists.json"

def load_playlists():
    if not os.path.exists(PLAYLISTS_FILE):
        return {}
    try:
        with open(PLAYLISTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log("ERROR LOADING PLAYLISTS:", str(e))
        return {}

def save_playlists(data):
    try:
        with open(PLAYLISTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log("ERROR SAVING PLAYLISTS:", str(e))

def ensure_playlist(season_label):
    """
    season_label = "Season 1"
    playlist_name = "Clinton's Core Classics – Season 1"
    """
    playlists = load_playlists()

    # Long-form playlist name
    playlist_name = f"Clinton's Core Classics – {season_label}"

    # Already exists?
    if playlist_name in playlists:
        return playlists[playlist_name]

    log("PLAYLIST NOT FOUND — CREATING:", playlist_name)

    # Create playlist via YouTube API
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

    log("PLAYLIST CREATED:", playlist_name, playlist_id)

    # Save to file
    playlists[playlist_name] = playlist_id
    save_playlists(playlists)

    return playlist_id

def add_video_to_playlist(video_id, playlist_id):
    log("ADDING VIDEO TO PLAYLIST:", video_id, playlist_id)

    request = youtube.playlistItems().insert(
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
    )

    response = request.execute()
    log("PLAYLIST ADD RESPONSE:", str(response))
