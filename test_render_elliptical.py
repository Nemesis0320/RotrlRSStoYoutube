#!/usr/bin/env python3
"""
Test script: Generate ELLIPTICAL waveform video from real audio.
Extracts audio samples and renders them in an ELLIPSE pattern matching the background ring.
"""
import os
import sys
import math
import subprocess
import numpy as np
from PIL import Image, ImageDraw

# Test configuration
TEST_AUDIO_FILE = "test_audio.mp3"
OUTPUT_VIDEO = "test_output.mp4"

# Canvas settings - ELLIPTICAL ALIGNMENT TO BACKGROUND RING
WIDTH = 720
HEIGHT = 720

# Background ring measurements - ELLIPSE (not circle!)
SCALE = 720.0 / 1200.0
CENTER_X = int(600 * SCALE)  # 360
CENTER_Y = int(555 * SCALE)  # 333

# Ellipse radii - different for X and Y axes
OUTER_RADIUS_X = int(300 * SCALE)  # 180 (horizontal - wider)
OUTER_RADIUS_Y = int(240 * SCALE)  # 144 (vertical - shorter)
INNER_RADIUS_X = int(260 * SCALE)  # 156 (horizontal)
INNER_RADIUS_Y = int(200 * SCALE)  # 120 (vertical)

# Waveform amplification
AMPLITUDE_MULTIPLIER = 3.5  # Dramatic waveforms!

FPS = 12

# Video settings
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

def download_test_audio():
    """Download test audio file."""
    log("Downloading test audio...")
    if os.path.exists(TEST_AUDIO_FILE):
        log("Test audio already exists, skipping download")
        return True
    
    TEST_URL = "https://quicksounds.com/uploads/tracks/528054973_948104858_1761723949.mp3"
    cmd = ["wget", "-O", TEST_AUDIO_FILE, TEST_URL]
    return run_cmd(cmd)

def extract_audio_samples(audio_path, target_fps=12):
    """
    Extract audio amplitude data for elliptical waveform.
    Returns list of frames, each containing 360 amplitude values (one per degree).
    """
    log(f"Extracting audio samples from {audio_path}")
    
    # Convert MP3 to WAV for processing
    wav_path = "temp_audio.wav"
    subprocess.run([
        'ffmpeg', '-y', '-i', audio_path,
        '-ar', '44100', '-ac', '1',  # Mono, 44.1kHz
        wav_path
    ], capture_output=True)
    
    # Read WAV file with numpy
    cmd = [
        'ffmpeg', '-i', wav_path,
        '-f', 's16le',  # 16-bit signed little-endian PCM
        '-acodec', 'pcm_s16le',
        '-'
    ]
    result = subprocess.run(cmd, capture_output=True)
    audio_data = np.frombuffer(result.stdout, dtype=np.int16)
    
    # Normalize to 0.0-1.0 range
    audio_data = np.abs(audio_data.astype(np.float32) / 32768.0)
    
    # Calculate samples per frame
    sample_rate = 44100
    samples_per_frame = int(sample_rate / target_fps)
    num_frames = len(audio_data) // samples_per_frame
    
    # Create circular samples (360 points per frame)
    num_angles = 360
    frame_data = []
    
    for frame_idx in range(num_frames):
        start_sample = frame_idx * samples_per_frame
        end_sample = start_sample + samples_per_frame
        frame_samples = audio_data[start_sample:end_sample]
        
        # Downsample to 360 points
        step = max(1, len(frame_samples) // num_angles)
        
        circular_samples = []
        for i in range(num_angles):
            sample_idx = i * step
            if sample_idx < len(frame_samples):
                circular_samples.append(float(frame_samples[sample_idx]))
            else:
                circular_samples.append(0.0)
        
        frame_data.append(circular_samples)
    
    # Cleanup
    if os.path.exists(wav_path):
        os.remove(wav_path)
    
    log(f"Extracted {len(frame_data)} frames with {num_angles} samples each")
    return frame_data

def draw_elliptical_frame(frame_idx, amplitudes, output_path):
    """
    Draw a single ELLIPTICAL waveform frame with clipping detection.
    Gold for normal audio, red for clipping (amplitude > 0.9).
    USES ELLIPSE MATH - different radii for X and Y axes!
    """
    img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    num_samples = len(amplitudes)
    
    for i in range(num_samples):
        angle = (i / num_samples) * 2 * math.pi
        amplitude = amplitudes[i]
        
        # Clipping detection: red if > 0.9, gold otherwise
        if amplitude > 0.9:
            color = (255, 0, 0, 255)  # Red
        else:
            color = (255, 215, 0, 255)  # Gold
        
        # ELLIPSE MATH: Calculate radius at this angle for inner and outer ellipses
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        
        # Inner ellipse radius at this angle
        inner_r = math.sqrt(
            (INNER_RADIUS_X * INNER_RADIUS_Y) ** 2 /
            ((INNER_RADIUS_Y * cos_a) ** 2 + (INNER_RADIUS_X * sin_a) ** 2)
        )
        
        # Outer ellipse radius at this angle
        outer_r = math.sqrt(
            (OUTER_RADIUS_X * OUTER_RADIUS_Y) ** 2 /
            ((OUTER_RADIUS_Y * cos_a) ** 2 + (OUTER_RADIUS_X * sin_a) ** 2)
        )
        
        # Ring thickness at this angle
        ring_thickness = outer_r - inner_r
        
        # Scale amplitude to ring thickness WITH MULTIPLIER
        line_length = amplitude * ring_thickness * AMPLITUDE_MULTIPLIER
        
        # Inner ellipse point (start of waveform)
        x1 = CENTER_X + inner_r * cos_a
        y1 = CENTER_Y + inner_r * sin_a
        
        # Outer point (extends radially based on amplitude)
        final_r = inner_r + line_length
        x2 = CENTER_X + final_r * cos_a
        y2 = CENTER_Y + final_r * sin_a
        
        # Draw radial line
        draw.line([(x1, y1), (x2, y2)], fill=color, width=4)
    
    img.save(output_path)

def generate_elliptical_waveform_video():
    """Generate elliptical waveform video frames."""
    log("Generating ELLIPTICAL waveform frames...")
    
    # Extract audio samples
    frame_data = extract_audio_samples(TEST_AUDIO_FILE, target_fps=FPS)
    
    # Create frames directory
    frames_dir = "elliptical_frames"
    os.makedirs(frames_dir, exist_ok=True)
    
    # Generate frames
    for idx, amplitudes in enumerate(frame_data):
        frame_path = os.path.join(frames_dir, f"frame_{idx:05d}.png")
        draw_elliptical_frame(idx, amplitudes, frame_path)
        
        if idx % 50 == 0:
            log(f"Generated frame {idx}/{len(frame_data)}")
    
    log(f"All {len(frame_data)} ELLIPTICAL frames generated")
    return frames_dir, len(frame_data)

def composite_final_video(frames_dir, num_frames):
    """Composite waveform frames with background and text."""
    log("Compositing final video...")
    
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
    
    # Composite: background + waveform frames + text overlays
    filter_complex = f"""
        [0:v]scale={VIDEO_SIZE}[bg];
        [1:v]format=yuva420p[wave];
        [bg][wave]overlay=(W-w)/2:(H-h)/2[bg_wave];
        [bg_wave]drawtext=fontfile={FONT_FILE}:text='{safe_episode_title}':x=(w-text_w)/2:y=120:fontsize=40:fontcolor=gold:shadowx=2:shadowy=2[bg_titleline];
        [bg_titleline]drawtext=fontfile={FONT_FILE}:text='{safe_season_ep}':x=(w-text_w)/2:y=180:fontsize=32:fontcolor=white:shadowx=2:shadowy=2[bg_ep];
        [bg_ep]drawtext=fontfile={FONT_FILE}:text='{safe_ticker}':x=w-mod(t*120\\,w+text_w):y=h-60:fontsize=26:fontcolor=white:shadowx=2:shadowy=2[final]
    """.replace("\n", " ")
    
    cmd = [
        'ffmpeg', '-y',
        '-loop', '1', '-i', BG_IMAGE,
        '-framerate', str(FPS), '-i', os.path.join(frames_dir, 'frame_%05d.png'),
        '-i', TEST_AUDIO_FILE,
        '-filter_complex', filter_complex,
        '-map', '[final]',
        '-map', '2:a',
        '-r', str(FPS),
        '-c:v', 'libx264',
        '-preset', 'veryfast',
        '-tune', 'stillimage',
        '-crf', str(VIDEO_CRF),
        '-c:a', 'aac',
        '-b:a', AUDIO_BITRATE,
        '-shortest',
        OUTPUT_VIDEO
    ]
    
    result = run_cmd(cmd, capture=False)
    
    # Cleanup frames
    log("Cleaning up frames...")
    for f in os.listdir(frames_dir):
        os.remove(os.path.join(frames_dir, f))
    os.rmdir(frames_dir)
    
    return result

def main():
    log("🎯 ELLIPTICAL WAVEFORM RENDERER - TRUE ELLIPSE VERSION 🎯")
    log(f"Ellipse center: ({CENTER_X}, {CENTER_Y})")
    log(f"Outer radii: X={OUTER_RADIUS_X}, Y={OUTER_RADIUS_Y}")
    log(f"Inner radii: X={INNER_RADIUS_X}, Y={INNER_RADIUS_Y}")
    
    if not download_test_audio():
        log("Failed to download test audio")
        sys.exit(1)
    
    # Generate elliptical waveform frames
    frames_dir, num_frames = generate_elliptical_waveform_video()
    
    # Composite with background and text
    if not composite_final_video(frames_dir, num_frames):
        log("Failed to composite video")
        sys.exit(1)
    
    if os.path.exists(OUTPUT_VIDEO):
        size = os.path.getsize(OUTPUT_VIDEO)
        log(f"✅ SUCCESS: ELLIPTICAL waveform video created ({size} bytes)")
        log(f"Output file: {OUTPUT_VIDEO}")
    else:
        log("ERROR: Output video not created")
        sys.exit(1)

if __name__ == "__main__":
    main()
