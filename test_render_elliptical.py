#!/usr/bin/env python3
"""
Standalone test script for elliptical waveform rendering.
Tests the rendering pipeline without uploading to YouTube.
"""
import os
import subprocess
import sys

# Test configuration
TEST_AUDIO_FILE = "test_audio.mp3"
OUTPUT_VIDEO = "test_output.mp4"
REMAP_X_FILE = "ellipse_remap_x.pgm"
REMAP_Y_FILE = "ellipse_remap_y.pgm"

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

def generate_test_audio():
    """Generate a test audio file with FFmpeg."""
    log("Generating test audio...")
    if os.path.exists(TEST_AUDIO_FILE):
        log("Test audio already exists, skipping generation")
        return True
    
    # Generate 7 seconds of 440Hz sine wave
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "sine=frequency=440:duration=7",
        "-ar", "44100",
        "-ac", "2",
        TEST_AUDIO_FILE
    ]
    return run_cmd(cmd)

def generate_remap_table():
    log("Generating ellipse remap tables...")
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
    
    # CORRECTED FILTERGRAPH WITH PROPER REMAP USAGE
    filter_complex = f"""
        [0:v]scale={VIDEO_SIZE}[bg];
        [1:a]showwaves=s={WAVEFORM_WIDTH}x{WAVEFORM_HEIGHT}:mode=line:rate={VIDEO_FPS}:colors=gold:scale=lin[wave_linear];
        [wave_linear]format=gray[wave_gray];
        [wave_gray][2:v][3:v]remap[wave_warped];
        [wave_warped]format=rgba,colorchannelmixer=aa=1[wave_rgba];
        [bg][wave_rgba]overlay=0:0[bg_wave];
        [bg_wave]drawtext=fontfile={FONT_FILE}:text='{safe_episode_title}':x=(w-text_w)/2:y=120:fontsize=40:fontcolor=gold:shadowx=2:shadowy=2[bg_titleline];
        [bg_titleline]drawtext=fontfile={FONT_FILE}:text='{safe_season_ep}':x=(w-text_w)/2:y=180:fontsize=32:fontcolor=white:shadowx=2:shadowy=2[bg_ep];
        [bg_ep]drawtext=fontfile={FONT_FILE}:text='{safe_ticker}':x=w-mod(t*120\\,w+text_w):y=h-60:fontsize=26:fontcolor=white:shadowx=2:shadowy=2[final]
    """.replace("\n", " ")
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", BG_IMAGE,      # input 0: background
        "-i", TEST_AUDIO_FILE,             # input 1: audio
        "-loop", "1", "-i", REMAP_X_FILE,  # input 2: X coordinates
        "-loop", "1", "-i", REMAP_Y_FILE,  # input 3: Y coordinates
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
    
    return run_cmd(cmd, capture=False)  # Show full FFmpeg output for debugging

def main():
    log("Starting elliptical waveform test")
    
    # Step 1: Generate test audio
    if not generate_test_audio():
        log("Failed to generate test audio")
        sys.exit(1)
    
    # Step 2: Generate remap tables
    if not generate_remap_table():
        log("Failed to generate remap tables")
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
