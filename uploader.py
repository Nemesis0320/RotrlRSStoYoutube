import os
import json
import time
import subprocess
import requests
import feedparser
DEBUG = True

def log(*args):
    if DEBUG:
        print("[uploader]", *args, flush=True)
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
    log("RUN CMD:", " ".join(cmd))
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode("utf-8", "ignore")
        log("CMD OK:", " ".join(cmd))
        log("CMD OUT:", out)
        return out
    except subprocess.CalledProcessError as e:
        out = e.output.decode("utf-8", "ignore")
        log("CMD FAIL:", " ".join(cmd))
        log("CMD OUT:", out[:2000])
        return out

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
    log("DOWNLOAD AUDIO:", url, "->", out_path)
    cleanup_files(out_path)
    out = run_cmd(["wget", "-O", out_path, url])
    log("WGET OUT:", out[:1000])
    exists = os.path.exists(out_path)
    size = os.path.getsize(out_path) if exists else 0
    log("AUDIO EXISTS:", exists, "SIZE:", size)
    return exists and size > 0
    
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

VIDEO_SIZE = "720x720"
VIDEO_FPS = 12
VIDEO_CRF = 30
AUDIO_BITRATE = "64k"

BG_IMAGE = "assets/1200x1200bf.png"
FONT_FILE = "assets/IMFellEnglishSC.ttf"

PODCAST_TITLE = "Clinton's Core Classics"

def render_video(audio, output, episode_title=None, season_label=None):
    if episode_title is None:
        episode_title = "Untitled Episode"
    if season_label is None:
        season_label = SEASON_LABEL  # fallback
    log("RENDER VIDEO L3-CIRCULAR:", audio, "->", output)

    ticker_text = f"Now Playing: {episode_title}"
    
    safe_podcast_title = PODCAST_TITLE.replace("'", r"\'")
    safe_season_label = season_label.replace("'", r"\'")
    safe_episode_title = episode_title.replace("'", r"\'")
    safe_ticker_text = ticker_text.replace("'", r"\'")
    
    filter_complex = f"""
        [0:v]scale={VIDEO_SIZE}[bg];

        [1:a]asplit=3[a_main][a_glow][a_clip];

        [a_main]showwaves=s={VIDEO_SIZE}:mode=line:rate={VIDEO_FPS}:colors=gold:scale=lin[wave_inner];

        [a_glow]compand=attacks=0:decays=0:points=-80/-80|-40/-40|-20/-10|0/0[a_glow_soft];
        [a_glow_soft]showwaves=s={VIDEO_SIZE}:mode=line:rate={VIDEO_FPS}:colors=red:scale=lin[wave_glow];

        [a_glow]compand=attacks=0:decays=0:points=-80/-80|-30/-20|-10/0|0/10[a_glow_hot];
        [a_glow_hot]showwaves=s={VIDEO_SIZE}:mode=line:rate={VIDEO_FPS}:colors=yellow:scale=lin[wave_glow_hot];

        [a_clip]showwaves=s={VIDEO_SIZE}:mode=line:rate={VIDEO_FPS}:colors=red:scale=lin[wave_clip_raw];
        [wave_clip_raw]geq=lum='if(p(X,Y)/255>0.90,p(X,Y),0)':cb='128':cr='128':a='if(p(X,Y)/255>0.90,255,0)'[wave_clip_masked];

        [wave_inner]copy[polar_inner];
        [wave_glow]copy[polar_glow];
        [wave_glow_hot]copy[polar_glow_hot];
        [wave_clip_masked]copy[polar_clip];

        [polar_glow]gblur=sigma=10[glow_soft];
        [polar_glow_hot]gblur=sigma=15[glow_hot];

        [polar_inner][glow_soft]blend=all_mode=screen:all_opacity=0.7[tmp1];
        [tmp1][glow_hot]blend=all_mode=screen:all_opacity=0.8[tmp2];
        [tmp2][polar_clip]blend=all_mode=lighten:all_opacity=1.0[combined];

        [combined][2:v]alphamerge[circ_wave];

        [bg][circ_wave]overlay=(W-w)/2:(H-h)/2[bg_wave];

        [bg_wave]drawtext=fontfile={FONT_FILE}:text="{safe_podcast_title}":x=(w-text_w)/2:y=60:fontsize=40:fontcolor=white:shadowx=2:shadowy=2[bg_title];

        [bg_title]drawtext=fontfile={FONT_FILE}:text="{safe_season_label}":x=(w-text_w)/2:y=120:fontsize=32:fontcolor=gold:shadowx=2:shadowy=2[bg_season];

        [bg_season]drawtext=fontfile={FONT_FILE}:text="{safe_episode_title}":x=(w-text_w)/2:y=180:fontsize=30:fontcolor=white:shadowx=2:shadowy=2[bg_ep];

        [bg_ep]drawtext=fontfile={FONT_FILE}:text="{safe_ticker_text}":x=w-mod(t*120\\,w+text_w):y=h-60:fontsize=26:fontcolor=white:shadowx=2:shadowy=2[final];

        [final]fade=t=in:st=0:d=0.8[final_faded];
    """.replace("\n", " ")

    # TEMP: print full v360 help (no truncation)
    v360_help = run_cmd(["ffmpeg", "-h", "filter=v360"])
    log("V360 HELP FULL:", v360_help)

    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", BG_IMAGE,
        "-i", audio,
        "-i", "assets/circle_mask_720.png",
        "-filter_complex", filter_complex,
        "-map", "[final_faded]",
        "-map", "1:a",
        "-r", str(VIDEO_FPS),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "stillimage",
        "-crf", str(VIDEO_CRF),
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        "-shortest",
        output,
    ]

    out = run_cmd(cmd)
    log("RENDER L3-CIRC OUT:", out)
    exists = os.path.exists(output)
    size = os.path.getsize(output) if exists else 0
    log("RENDER L3-CIRC RESULT:", exists, "SIZE:", size)
    return exists and size > 0

def stitch_videos(v1, v2, out_path):
    cleanup_files(out_path)
    with open("concat.txt", "w", encoding="utf-8") as f:
        f.write(f"file '{v1}'\nfile '{v2}'\n")
    run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", out_path])
    return os.path.exists(out_path)
def full_render_pipeline(title, season_label):
    log("RENDER PIPELINE: start")
    dur, split = split_audio(AUDIO_FILE, PART1_AUDIO, PART2_AUDIO)
    log("SPLIT RESULT:", "duration", dur, "split", split)
    if not split:
        log("SINGLE PART RENDER:", PART1_AUDIO, "->", FINAL_VIDEO)
        if not render_video(PART1_AUDIO, FINAL_VIDEO, episode_title=title, season_label=season_label):
            log("RENDER FAILED: single part")
            return None, dur
        exists = os.path.exists(FINAL_VIDEO)
        size = os.path.getsize(FINAL_VIDEO) if exists else 0
        log("FINAL VIDEO EXISTS:", exists, "SIZE:", size)
        return FINAL_VIDEO, dur
    log("TWO PART RENDER:", PART1_AUDIO, "->", PART1_VIDEO, "|", PART2_AUDIO, "->", PART2_VIDEO)
    ok1 = render_video(PART1_AUDIO, PART1_VIDEO, episode_title=title, season_label=season_label)
    ok2 = render_video(PART2_AUDIO, PART2_VIDEO, episode_title=title, season_label=season_label)
    log("RENDER PART1 OK:", ok1, "EXISTS:", os.path.exists(PART1_VIDEO))
    log("RENDER PART2 OK:", ok2, "EXISTS:", os.path.exists(PART2_VIDEO))
    if not (ok1 and ok2):
        log("RENDER FAILED: one or both parts")
        return None, dur
    log("STITCH:", PART1_VIDEO, "+", PART2_VIDEO, "->", FINAL_VIDEO)
    if not stitch_videos(PART1_VIDEO, PART2_VIDEO, FINAL_VIDEO):
        log("STITCH FAILED")
        return None, dur
    exists = os.path.exists(FINAL_VIDEO)
    size = os.path.getsize(FINAL_VIDEO) if exists else 0
    log("FINAL VIDEO EXISTS:", exists, "SIZE:", size)
    return FINAL_VIDEO, dur

# Upload logic
def upload_video(path, title, description, playlist_id):
    log("UPLOAD VIDEO:", path, "TITLE:", title, "PLAYLIST:", playlist_id)
    record_quota_usage(1600)
    cmd = ["python3", "upload.py", "--file", path, "--title", title, "--description", description]
    if playlist_id:
        cmd += ["--playlist", playlist_id]
    out = run_cmd(cmd)
    log("UPLOAD.PY OUT:", out[:2000])
    if "VIDEO_ID=" not in out:
        log("UPLOAD FAILED: no VIDEO_ID in output")
        return None
    vid = out.strip().split("VIDEO_ID=")[-1].strip()
    log("UPLOAD SUCCESS: VIDEO_ID", vid)
    return vid

def poll_video(video_id):
    log("POLL VIDEO:", video_id)
    record_quota_usage(1)
    out = run_cmd(["python3", "check_status.py", "--id", video_id])
    log("CHECK_STATUS OUT:", out[:1000])
    if "LIVE" in out:
        log("VIDEO LIVE:", video_id)
        return True
    log("VIDEO NOT LIVE YET:", video_id)
    return False

def aggressive_poll(video_id):
    log("AGGRESSIVE POLL START:", video_id)
    for i in range(12):
        log("POLL ATTEMPT:", i + 1)
        if poll_video(video_id):
            log("AGGRESSIVE POLL SUCCESS:", video_id)
            return True
        time.sleep(5)
    log("AGGRESSIVE POLL FAILED:", video_id)
    return False

def upload_with_retry(path, title, description, playlist_id):
    log("UPLOAD WITH RETRY:", path, title)
    vid = upload_video(path, title, description, playlist_id)
    if not vid:
        log("FIRST UPLOAD FAILED")
        return None
    if aggressive_poll(vid):
        return vid
    log("FIRST VIDEO NOT LIVE, RETRYING UPLOAD")
    send_discord_embed("Re-upload attempt", f"Video {vid} not acknowledged. Retrying.", 0xE67E22)
    vid2 = upload_video(path, title, description, playlist_id)
    if not vid2:
        log("SECOND UPLOAD FAILED")
        return None
    if aggressive_poll(vid2):
        return vid2
    log("SECOND VIDEO NOT LIVE, GIVING UP")
    return None

def render_and_upload(title, description, season_label):
    log("RENDER+UPLOAD START:", title)
    video_path, dur = full_render_pipeline(title, season_label)
    log("FIRST RENDER RESULT:", video_path, "DUR:", dur)
    if not video_path:
        send_discord_embed("Render failed", "Re-rendering...", 0xE74C3C)
        log("RETRY RENDER")
        video_path, dur = full_render_pipeline(title, season_label)
        log("SECOND RENDER RESULT:", video_path, "DUR:", dur)
        if not video_path:
            log("RENDER FAILED TWICE")
            return None, dur
    vid = upload_with_retry(video_path, title, description, YOUTUBE_PLAYLIST_ID)
    log("UPLOAD RESULT VIDEO_ID:", vid)
    return vid, dur

# RSS + queue
def fetch_rss():
    log("FETCH RSS:", RSS_URL)
    feed = feedparser.parse(RSS_URL)
    log("RSS ENTRIES:", len(feed.entries))
    return feed


def get_episodes(feed):
    eps = []
    for e in feed.entries:
        eid = getattr(e, "id", None)
        title = getattr(e, "title", "Untitled")
        url = e.enclosures[0].href if getattr(e, "enclosures", None) else None
        log("EP:", "ID:", eid, "TITLE:", title, "URL:", url)
        if eid and url:
            eps.append((eid, title, url))
    log("EPISODE LIST BUILT:", len(eps))
    return eps

def next_episode(uploaded, episodes):
    log("NEXT EPISODE: uploaded count", len(uploaded), "episodes total", len(episodes))
    for eid, title, url in episodes:
        log("CHECK EP:", eid, "uploaded?", eid in uploaded)
        if eid not in uploaded:
            log("NEXT EP FOUND:", eid, title)
            return eid, title, url
    log("NO NEW EPISODES")
    return None, None, None

# Main pipeline
def process_episode(eid, title, url, uploaded, stats):
    log("PROCESS EP:", eid, title, url)
    # Extract season number from title
    # Expected formats:
    #   "Season 6 - Episode 12: Title"
    #   "S6E12: Title"
    #   "Season 6 Episode 12: Title"
    import re
    m = re.search(r"[Ss]eason\s+(\d+)", title)
    if not m:
        m = re.search(r"[Ss](\d+)[Ee]\d+", title)
    season_num = int(m.group(1)) if m else 0
    season_label = f"Season {season_num}"
    cleanup_files(AUDIO_FILE, PART1_AUDIO, PART2_AUDIO, PART1_VIDEO, PART2_VIDEO, FINAL_VIDEO)
    if not download_audio(url, AUDIO_FILE):
        stats["failures_today"] += 1
        save_daily_stats(stats)
        send_discord_embed("Download failed", title, 0xE74C3C)
        log("DOWNLOAD FAILED:", url)
        return False
    vid, dur = render_and_upload(title, title, season_label=season_label)
    log("PROCESS EP RESULT:", "VIDEO_ID:", vid, "DUR:", dur)
    if not vid:
        stats["failures_today"] += 1
        save_daily_stats(stats)
        send_discord_embed("Upload failed", title, 0xE74C3C)
        log("UPLOAD FAILED FOR EP:", eid)
        return False
    uploaded.add(eid)
    save_uploaded(uploaded)
    stats["episodes_uploaded_today"] += 1
    stats["total_runtime_today"] += dur
    save_daily_stats(stats)
    send_discord_embed("Upload complete", f"{title}\nDuration: {format_seconds(dur)}", 0x2ECC71)
    log("EP SUCCESS:", eid, "VIDEO_ID:", vid)
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
    log("MAIN START")
    send_discord_embed("Heartbeat", "Run started.")
    if not check_quota_safely():
        log("ABORT: LOW QUOTA")
        return
    feed = fetch_rss()
    episodes = get_episodes(feed)
    uploaded = load_uploaded()
    stats = load_daily_stats()
    stats = reset_daily_stats_if_needed(stats)
    log("STATE:", "uploaded", len(uploaded), "stats", stats)
    eid, title, url = next_episode(uploaded, episodes)
    if not eid:
        write_summary("No new episodes.")
        send_discord_embed("Idle", "No new episodes.")
        log("NO NEW EPISODES, EXIT")
        return
    ok = process_episode(eid, title, url, uploaded, stats)
    remaining = len([e for e in episodes if e[0] not in uploaded])
    write_daily_summary(stats, remaining)
    if ok:
        send_discord_embed("Run complete", f"Remaining episodes: {remaining}", 0x2ECC71)
    else:
        send_discord_embed("Run complete with errors", f"Remaining episodes: {remaining}", 0xE74C3C)
    log("MAIN END: ok =", ok, "remaining =", remaining)


if __name__ == "__main__":
    main()
