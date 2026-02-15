#!/usr/bin/env python3
"""
Standalone test script for waveform rendering with clipping detection.
Tests the rendering pipeline without uploading to YouTube.
"""
import os
import subprocess
import sys

# Test configuration
TEST_AUDIO_FILE = "test_audio.mp3"
OUTPUT_VIDEO = "test_output.mp4"

# Video settings (matching uploader.py)
VIDEO_SIZE = "720x720"
VIDEO_FPS = 12
VIDEO_CRF = 30
AUDIO_BITRATE = "64k"
BG_IMAGE = "assets/1200x1200bf.png"
FONT_FILE = "assets/IMFellEnglishSC.ttf"

def log(msg):
    print(f"[test] {msg}", flush=True)

def run_cmd(cmd, capture=True):
    log(f"RUN: {' '.join(cmd)}")
    if capture:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log(f"ERROR: {result.stderr}")
            return False
        if result.stdout:
            log(f"OUTPUT: {result.stdout}")
        return True
    else:
        result = subprocess.run(cmd)
        return result.returncode == 0

def get_audio_duration(path):
    """Get duration of audio file in seconds."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except:
        return 10.0

def download_test_audio():
    """Download test audio file."""
    log("Downloading test audio...")
    if os.path.exists(TEST_AUDIO_FILE):
        log("Test audio already exists, skipping download")
        return True
    
    TEST_URL = "https://quicksounds.com/uploads/tracks/528054973_948104858_1761723949.mp3"
    cmd = ["wget", "-O", TEST_AUDIO_FILE, TEST_URL]
    return run_cmd(cmd)

def render_waveform():
    log("Rendering waveform with clipping detection...")
    
    duration = get_audio_duration(TEST_AUDIO_FILE)
    log(f"Audio duration: {duration:.2f} seconds")
    
    episode_title = "Test File"
    season_label = "Season 1"
    episode_number = "0"
    ticker_text = f"{season_label} EP {episode_number}: {episode_title}"
    
    def ffmpeg_escape(text):
        return (
            text
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace(":", "\\:")
            .replace(",", "\\,")
        )
    
    safe_episode_title = ffmpeg_escape(episode_title)
    safe_season_ep = ffmpeg_escape(f"{season_label} EP {episode_number}")
    safe_ticker = ffmpeg_escape(ticker_text)
    
    # FIXED: Split audio into 3 streams (output + 2 for waveforms)
    filter_complex = f"""
        [0:v]scale={VIDEO_SIZE}[bg];
        [1:a]asplit=3[a_out][a_wave_gold][a_wave_red];
        [a_wave_gold]showwaves=s={VIDEO_SIZE}:mode=line:rate={VIDEO_FPS}:colors=gold:scale=lin[wave_gold];
        [a_wave_red]showwaves=s={VIDEO_SIZE}:mode=line:rate={VIDEO_FPS}:colors=red:scale=lin:draw=scale[wave_red];
        [wave_gold][wave_red]blend=all_expr='if(gt(A,0.9*255),B,A)'[wave_combined];
        [bg][wave_combined]overlay=0:0:format=auto[bg_wave];
        [bg_wave]drawtext=fontfile={FONT_FILE}:text='{safe_episode_title}':x=(w-text_w)/2:y=120:fontsize=40:fontcolor=gold:shadowx=2:shadowy=2[bg_titleline];
        [bg_titleline]drawtext=fontfile={FONT_FILE}:text='{safe_season_ep}':x=(w-text_w)/2:y=180:fontsize=32:fontcolor=white:shadowx=2:shadowy=2[bg_ep];
        [bg_ep]drawtext=fontfile={FONT_FILE}:text='{safe_ticker}':x=w-mod(t*120\\,w+text_w):y=h-60:fontsize=26:fontcolor=white:shadowx=2:shadowy=2[final]
    """.replace("\n", " ")
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", str(duration), "-i", BG_IMAGE,
        "-i", TEST_AUDIO_FILE,
        "-filter_complex", filter_complex,
        "-map", "[final]",
        "-map", "[a_out]",
        "-r", str(VIDEO_FPS),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "stillimage",
        "-crf", str(VIDEO_CRF),
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        OUTPUT_VIDEO
    ]
    
    return run_cmd(cmd, capture=False)

def main():
    log("Starting waveform render test")
    
    if not download_test_audio():
        log("Failed to download test audio")
        sys.exit(1)
    
    if not render_waveform():
        log("Failed to render video")
        sys.exit(1)
    
    if os.path.exists(OUTPUT_VIDEO):
        size = os.path.getsize(OUTPUT_VIDEO)
        log(f"SUCCESS: Video created ({size} bytes)")
        log(f"Output file: {OUTPUT_VIDEO}")
    else:
        log("ERROR: Output video not created")
        sys.exit(1)

if __name__ == "__main__":
    main()
