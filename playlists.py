import os
import json
import sys
def log(*args):
    print("[playlists]", *args, file=sys.stderr, flush=True)
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
    playlists = load_playlists()
    playlist_name = f"Clinton's Core Classics - {season_label}"
    # Already exists?
    if playlist_name in playlists:
        return playlists[playlist_name]
    # Not found — create placeholder entry
    log("PLAYLIST NOT FOUND — INITIALIZING:", playlist_name)
    # Placeholder None means "needs creation on next upload"
    playlists[playlist_name] = None
    save_playlists(playlists)
    return None

def update_playlist_id(playlist_name, playlist_id):
    playlists = load_playlists()
    playlists[playlist_name] = playlist_id
    save_playlists(playlists)
    log("PLAYLIST ID UPDATED:", playlist_name, playlist_id)
