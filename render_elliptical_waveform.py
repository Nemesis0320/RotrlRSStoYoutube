#!/usr/bin/env python3
"""
Production elliptical waveform renderer for podcast videos.
Generates elliptical waveform frames from audio, then composites with background and text.
"""
import os
import sys
import math
import subprocess
import numpy as np
from PIL import Image, ImageDraw

# Canvas settings - ELLIPTICAL ALIGNMENT
WIDTH = 720
HEIGHT = 720

# Background ring measurements - ELLIPSE
SCALE = 720.0 / 1200.0
CENTER_X = int(600 * SCALE)  # 360
CENTER_Y = int(555 * SCALE)  # 333

# Ellipse radii - VERTICAL orientation
OUTER_RADIUS_X = int(250 * SCALE)  # 150 (horizontal)
OUTER_RADIUS_Y = int(310 * SCALE)  # 186 (vertical)
INNER_RADIUS_X = int(210 * SCALE)  # 126 (horizontal)
INNER_RADIUS_Y = int(270 * SCALE)  # 162 (vertical)

# Waveform appearance
AMPLITUDE_MULTIPLIER = 3.5
WAVEFORM_OPACITY = 230  # 90% opacity

FPS = 12

# Video settings
VIDEO_SIZE = "720x720"
VIDEO_FPS = 12
VIDEO_CRF = 30
AUDIO_BITRATE = "64k"
BG_IMAGE = "assets/1200x1200bf.png"
FONT_FILE = "assets/IMFellEnglishSC.ttf"

def log(msg):
    print(f"[elliptical] {msg}", flush=True)

def extract_audio_samples(audio_path, target_fps=12):
    """
    Extract audio amplitude data for elliptical waveform.
    Returns list of frames, each containing 360 amplitude values.
    """
    log(f"Extracting audio samples from {audio_path}")
    
    # Convert MP3 to WAV for processing
    wav_path = "temp_audio.wav"
    subprocess.run([
        'ffmpeg', '-y', '-i', audio_path,
        '-ar', '44100', '-ac', '1',
        wav_path
    ], capture_output=True)
    
    # Read WAV file with numpy
    cmd = [
        'ffmpeg', '-i', wav_path,
        '-f', 's16le',
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
    """
    img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    num_samples = len(amplitudes)
    
    for i in range(num_samples):
        angle = (i / num_samples) * 2 * math.pi
        amplitude = amplitudes[i]
        
        # Clipping detection with opacity
        if amplitude > 0.9:
            color = (255, 0, 0, WAVEFORM_OPACITY)  # Red
        else:
            color = (255, 215, 0, WAVEFORM_OPACITY)  # Gold
        
        # ELLIPSE MATH: Calculate radius at this angle
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
        
        # Scale amplitude with multiplier
        line_length = amplitude * ring_thickness * AMPLITUDE_MULTIPLIER
        
        # Inner ellipse point
        x1 = CENTER_X + inner_r * cos_a
        y1 = CENTER_Y + inner_r * sin_a
        
        # Outer point
        final_r = inner_r + line_length
        x2 = CENTER_X + final_r * cos_a
        y2 = CENTER_Y + final_r * sin_a
        
        # Draw radial line
        draw.line([(x1, y1), (x2, y2)], fill=color, width=4)
    
    img.save(output_path)

def render_elliptical_waveform_video(audio, output, episode_title=None, season_label=None, episode_number=None):
    """
    Main function: Generate complete elliptical waveform video with background and text.
    This replaces the render_video() function in uploader.py.
    """
    if episode_title is None:
        episode_title = "Untitled Episode"
    if season_label is None:
        season_label = "Season"
    
    log(f"RENDER ELLIPTICAL: {audio} -> {output}")
    
    # Remove apostrophes (FFmpeg-safe)
    episode_title = episode_title.replace("'", "")
    season_label = season_label.replace("'", "")
    
    # Canonical labels
    season_ep_label = f"{season_label} EP {episode_number}"
    ticker_text = f"{season_ep_label}: {episode_title}"
    
    # Escape for FFmpeg
    def ffmpeg_escape(text):
        return (
            text
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace(":", "\\:")
            .replace(",", "\\,")
        )
    
    safe_episode_title = ffmpeg_escape(episode_title)
    safe_season_ep_label = ffmpeg_escape(season_ep_label)
    safe_ticker_text = ffmpeg_escape(ticker_text)
    
    # Generate elliptical waveform frames
    log("Generating elliptical waveform frames...")
    frame_data = extract_audio_samples(audio, target_fps=FPS)
    
    frames_dir = "elliptical_frames"
    os.makedirs(frames_dir, exist_ok=True)
    
    for idx, amplitudes in enumerate(frame_data):
        frame_path = os.path.join(frames_dir, f"frame_{idx:05d}.png")
        draw_elliptical_frame(idx, amplitudes, frame_path)
        
        if idx % 100 == 0:
            log(f"Generated frame {idx}/{len(frame_data)}")
    
    log(f"All {len(frame_data)} frames generated, compositing...")
    
    # Composite with background and text
    filter_complex = f"""
        [0:v]scale={VIDEO_SIZE}[bg];
        [1:v]format=yuva420p[wave];
        [bg][wave]overlay=(W-w)/2:(H-h)/2[bg_wave];
        [bg_wave]drawtext=fontfile={FONT_FILE}:text='{safe_episode_title}':x=(w-text_w)/2:y=120:fontsize=40:fontcolor=gold:shadowx=2:shadowy=2[bg_titleline];
        [bg_titleline]drawtext=fontfile={FONT_FILE}:text='{safe_season_ep_label}':x=(w-text_w)/2:y=180:fontsize=32:fontcolor=white:shadowx=2:shadowy=2[bg_ep];
        [bg_ep]drawtext=fontfile={FONT_FILE}:text='{safe_ticker_text}':x=w-mod(t*120\\,w+text_w):y=h-60:fontsize=26:fontcolor=white:shadowx=2:shadowy=2[final]
    """.replace("\n", " ")
    
    cmd = [
        'ffmpeg', '-y',
        '-loop', '1', '-i', BG_IMAGE,
        '-framerate', str(FPS), '-i', os.path.join(frames_dir, 'frame_%05d.png'),
        '-i', audio,
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
        output
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Cleanup frames
    log("Cleaning up frames...")
    for f in os.listdir(frames_dir):
        os.remove(os.path.join(frames_dir, f))
    os.rmdir(frames_dir)
    
    exists = os.path.exists(output)
    size = os.path.getsize(output) if exists else 0
    log(f"RENDER RESULT: exists={exists}, size={size}")
    
    return exists and size > 0

if __name__ == "__main__":
    # Standalone usage for testing
    if len(sys.argv) < 3:
        print("Usage: python3 render_elliptical_waveform.py <audio> <output> [title] [season] [episode_num]")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    output_file = sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else "Test Episode"
    season = sys.argv[4] if len(sys.argv) > 4 else "Season 1"
    ep_num = sys.argv[5] if len(sys.argv) > 5 else "0"
    
    success = render_elliptical_waveform_video(audio_file, output_file, title, season, ep_num)
    sys.exit(0 if success else 1)
