import os
import json
import time
import subprocess
import requests
import feedparser
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
def cleanup_files(*paths):
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except:
                pass

def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode("utf-8", "ignore")
    except subprocess.CalledProcessError as e:
        return e.output.decode("utf-8", "ignore")

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
    cleanup_files(out_path)
    run_cmd(["wget", "-O", out_path, url])
    return os.path.exists(out_path)
    
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

def render_video(audio_path, out_path):
    cleanup_files(out_path)
    cmd = [
        "ffmpeg","-y","-loop","1","-i","cover.png","-i",audio_path,
        "-c:v","libx264","-preset","veryfast","-tune","stillimage",
        "-c:a","aac","-b:a","192k","-shortest",out_path
    ]
    run_cmd(cmd)
    return os.path.exists(out_path)

def stitch_videos(v1, v2, out_path):
    cleanup_files(out_path)
    with open("concat.txt", "w", encoding="utf-8") as f:
        f.write(f"file '{v1}'\nfile '{v2}'\n")
    run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", out_path])
    return os.path.exists(out_path)

def full_render_pipeline():
    dur, split = split_audio(AUDIO_FILE, PART1_AUDIO, PART2_AUDIO)
    if not split:
        if not render_video(PART1_AUDIO, FINAL_VIDEO):
            return None, dur
        return FINAL_VIDEO, dur
    ok1 = render_video(PART1_AUDIO, PART1_VIDEO)
    ok2 = render_video(PART2_AUDIO, PART2_VIDEO)
    if not (ok1 and ok2):
        return None, dur
    if not stitch_videos(PART1_VIDEO, PART2_VIDEO, FINAL_VIDEO):
        return None, dur
    return FINAL_VIDEO, dur

# Upload logic
def upload_video(path, title, description, playlist_id):
    record_quota_usage(1600)
    out = run_cmd(["python3","upload.py","--file",path,"--title",title,"--description",description,"--playlist",playlist_id])
    if "VIDEO_ID=" not in out:
        return None
    return out.strip().split("VIDEO_ID=")[-1].strip()

def poll_video(video_id):
    record_quota_usage(1)
    out = run_cmd(["python3","check_status.py","--id",video_id])
    if "LIVE" in out:
        return True
    return False

def aggressive_poll(video_id):
    for _ in range(12):
        if poll_video(video_id):
            return True
        time.sleep(5)
    return False

def upload_with_retry(path, title, description, playlist_id):
    vid = upload_video(path, title, description, playlist_id)
    if not vid:
        return None
    if aggressive_poll(vid):
        return vid
    send_discord_embed("Re-upload attempt", f"Video {vid} not acknowledged. Retrying.", 0xE67E22)
    vid2 = upload_video(path, title, description, playlist_id)
    if not vid2:
        return None
    if aggressive_poll(vid2):
        return vid2
    return None

def render_and_upload(title, description):
    video_path, dur = full_render_pipeline()
    if not video_path:
        send_discord_embed("Render failed", "Re-rendering...", 0xE74C3C)
        video_path, dur = full_render_pipeline()
        if not video_path:
            return None, dur
    vid = upload_with_retry(video_path, title, description, YOUTUBE_PLAYLIST_ID)
    return vid, dur

# RSS + queue
def fetch_rss():
    return feedparser.parse(RSS_URL)

def get_episodes(feed):
    eps = []
    for e in feed.entries:
        if hasattr(e, "id"):
            eps.append((e.id, e.title, e.enclosures[0].href if e.enclosures else None))
    return eps

def next_episode(uploaded, episodes):
    for eid, title, url in episodes:
        if eid not in uploaded:
            return eid, title, url
    return None, None, None

# Main pipeline
def process_episode(eid, title, url, uploaded, stats):
    cleanup_files(AUDIO_FILE, PART1_AUDIO, PART2_AUDIO, PART1_VIDEO, PART2_VIDEO, FINAL_VIDEO)
    if not download_audio(url, AUDIO_FILE):
        stats["failures_today"] += 1
        save_daily_stats(stats)
        send_discord_embed("Download failed", title, 0xE74C3C)
        return False
    vid, dur = render_and_upload(title, title)
    if not vid:
        stats["failures_today"] += 1
        save_daily_stats(stats)
        send_discord_embed("Upload failed", title, 0xE74C3C)
        return False
    uploaded.add(eid)
    save_uploaded(uploaded)
    stats["episodes_uploaded_today"] += 1
    stats["total_runtime_today"] += dur
    save_daily_stats(stats)
    send_discord_embed("Upload complete", f"{title}\nDuration: {format_seconds(dur)}", 0x2ECC71)
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
    send_discord_embed("Heartbeat", "Run started.")
    if not check_quota_safely():
        return
    feed = fetch_rss()
    episodes = get_episodes(feed)
    uploaded = load_uploaded()
    stats = load_daily_stats()
    stats = reset_daily_stats_if_needed(stats)
    eid, title, url = next_episode(uploaded, episodes)
    if not eid:
        write_summary("No new episodes.")
        send_discord_embed("Idle", "No new episodes.")
        return
    ok = process_episode(eid, title, url, uploaded, stats)
    remaining = len([e for e in episodes if e[0] not in uploaded])
    write_daily_summary(stats, remaining)
    if ok:
        send_discord_embed("Run complete", f"Remaining episodes: {remaining}", 0x2ECC71)
    else:
        send_discord_embed("Run complete with errors", f"Remaining episodes: {remaining}", 0xE74C3C)

if __name__ == "__main__":
    main()
