#!/usr/bin/env python3
"""
Standalone test script for elliptical waveform rendering.
Tests the rendering pipeline without uploading to YouTube.
"""
import os
import subprocess
import sys

# Test configuration
TEST_AUDIO_URL = "https://quicksounds.com/uploads/tracks/528054973_948104858_1761723929.mp3"
TEST_AUDIO_FILE = "test_audio.mp3"
OUTPUT_VIDEO = "test_output.mp4"
REMAP_FILE = "ellipse_remap.ppm"

# Video settings (matching uploader.py)
VIDEO_SIZE = "720x720"
VIDEO_FPS = 12
VIDEO_CRF = 30
AUDIO_BITRATE = "64k"
BG_IMAGE = "assets/1200x1200bf.png"
FONT_FILE = "assets/IMFellEnglishSC.ttf"

# Waveform source dimensions
WAVEFORM_WIDTH = 720
WAVEFORM_HEIGHT = 40

def log(msg):
    print(f"[test] {msg}", flush=True)

def run_cmd(cmd):
    log(f"RUN: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"ERROR: {result.stderr}")
        return False
    if result.stdout:
        log(f"OUTPUT: {result.stdout}")
    return True

def download_test_audio():
    log("Downloading test audio...")
    if os.path.exists(TEST_AUDIO_FILE):
        log("Test audio already exists, skipping download")
        return True
    return run_cmd(["wget", "-O", TEST_AUDIO_FILE, TEST_AUDIO_URL])

def generate_remap_table():
    log("Generating ellipse remap table...")
    return run_cmd(["python3", "generate_ellipse_remap.py"])

def render_elliptical_waveform():
    log("Rendering elliptical waveform...")
    
    # Test metadata
    episode_title = "Test File"
    season_label = "Season 1"
    episode_number = "0"
    ticker_text = f"{season_label} EP {episode_number}: {episode_title}"
    
    # Escape special characters for FFmpeg drawtext
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
    
    # Build filter complex for elliptical waveform
    # The remap filter needs TWO inputs: [source][coordinates]remap
    filter_complex = f"""
        [0:v]scale={VIDEO_SIZE}[bg];
        [1:a]showwaves=s={WAVEFORM_WIDTH}x{WAVEFORM_HEIGHT}:mode=line:rate={VIDEO_FPS}:colors=gold:scale=lin[wave_linear];
        [wave_linear]format=gray[wave_gray];
        [2:v]format=rgb24[remap_coords];
        [wave_gray][remap_coords]remap=format=gray[wave_warped];
        [wave_warped]format=rgba,colorchannelmixer=aa=1[wave_alpha];
        [bg][wave_alpha]overlay=0:0:format=auto[bg_wave];
        [bg_wave]drawtext=fontfile={FONT_FILE}:text='{safe_episode_title}':x=(w-text_w)/2:y=120:fontsize=40:fontcolor=gold:shadowx=2:shadowy=2[bg_titleline];
        [bg_titleline]drawtext=fontfile={FONT_FILE}:text='{safe_season_ep}':x=(w-text_w)/2:y=180:fontsize=32:fontcolor=white:shadowx=2:shadowy=2[bg_ep];
        [bg_ep]drawtext=fontfile={FONT_FILE}:text='{safe_ticker}':x=w-mod(t*120\\,w+text_w):y=h-60:fontsize=26:fontcolor=white:shadowx=2:shadowy=2[final]
    """.replace("\n", " ")
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", BG_IMAGE,
        "-i", TEST_AUDIO_FILE,
        "-loop", "1", "-i", REMAP_FILE,
        "-filter_complex", filter_complex,
        "-map", "[final]",
        "-map", "1:a",
        "-r", str(VIDEO_FPS),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "stillimage",
        "-crf", str(VIDEO_CRF),
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        "-shortest",
        OUTPUT_VIDEO
    ]
    
    return run_cmd(cmd)
def main():
    log("Starting elliptical waveform test")
    
    # Step 1: Download test audio
    if not download_test_audio():
        log("Failed to download test audio")
        sys.exit(1)
    
    # Step 2: Generate remap table
    if not generate_remap_table():
        log("Failed to generate remap table")
        sys.exit(1)
    
    # Step 3: Render video
    if not render_elliptical_waveform():
        log("Failed to render video")
        sys.exit(1)
    
    # Step 4: Check output
    if os.path.exists(OUTPUT_VIDEO):
        size = os.path.getsize(OUTPUT_VIDEO)
        log(f"SUCCESS: Video created ({size} bytes)")
        log(f"Output file: {OUTPUT_VIDEO}")
    else:
        log("ERROR: Output video not created")
        sys.exit(1)

if __name__ == "__main__":
    main()
