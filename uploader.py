#!/usr/bin/env python3
import os
import sys
import subprocess
import urllib.request

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
VIDEO_SIZE = "720x720"
VIDEO_FPS = 12
FONT_FILE = "assets/IMFellEnglishSC.ttf"
BG_IMAGE = "assets/1200x1200bf.png"
AUDIO_FILE = "part1.mp3"
FILTERGRAPH_PATH = "filtergraph.txt"

LOG_PREFIX = "[uploader]"

def log(*args):
    print(LOG_PREFIX, *args, flush=True)

# ----------------------------------------------------------------------
# Audio download: ensures part1.mp3 always exists
# ----------------------------------------------------------------------
def download_audio(url: str, output_path: str):
    log("DOWNLOADING AUDIO FROM:", url)
    try:
        urllib.request.urlretrieve(url, output_path)
        log("AUDIO DOWNLOADED TO:", output_path)
    except Exception as e:
        log("ERROR DOWNLOADING AUDIO:", str(e))
        sys.exit(1)

# ----------------------------------------------------------------------
# Text escaping for drawtext inside a filtergraph script
# ----------------------------------------------------------------------
def _ff_escape_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\\", "\\\\")   # literal backslash
    s = s.replace(":", r"\:")     # drawtext option separator
    s = s.replace("\n", r"\n")    # newlines inside text
    return s

# ----------------------------------------------------------------------
# Unified debug exporter for filtergraph
# ----------------------------------------------------------------------
def debug_filtergraph(path: str, content: str):
    log("FINAL FILTERGRAPH:", repr(content))

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

    log("WROTE FILTERGRAPH TO:", os.path.abspath(path))

    log("---- FILTERGRAPH.TXT CONTENTS ----")
    with open(path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            log(f"{idx:03d}:", repr(line))
    log("---- END FILTERGRAPH.TXT ----")

    log("---- FILTERGRAPH.TXT RAW BYTES ----")
    with open(path, "rb") as f:
        log(f.read())
    log("---- END RAW BYTES ----")

# ----------------------------------------------------------------------
# Build filtergraph script content
# ----------------------------------------------------------------------
def build_filtergraph(podcast_title, season_label, episode_title, ticker_text):
    title_text = _ff_escape_text(
        f"{podcast_title}\n{season_label}\n{episode_title}"
    )
    ticker_text = _ff_escape_text(ticker_text)

    # Only one escaped comma needed in the x-expression: '\,'
    filter_complex = (
        f"[0:v]scale={VIDEO_SIZE}[bg];\n"
        "color=black@0:s=720x720[mask_base];\n"
        "[mask_base]format=rgba[mask_rgba];\n"
        "[mask_rgba]geq=if((X-360)*(X-360)+(Y-360)*(Y-360)<330*330\\,255\\,0):128:128:"
        "if((X-360)*(X-360)+(Y-360)*(Y-360)<330*330\\,255\\,0)[mask];\n"
        "[1:a]asplit=2[a_main][a_clip];\n"
        f"[a_main]showwaves=s=720x40:mode=line:rate={VIDEO_FPS}:colors=gold:scale=lin[wave_inner_raw];\n"
        "[wave_inner_raw]pad=720:720:0:720-40:black@0[wave_inner];\n"
        f"[a_clip]showwaves=s=720x40:mode=line:rate={VIDEO_FPS}:colors=red:scale=lin[wave_clip_raw_raw];\n"
        "[wave_clip_raw_raw]pad=720:720:0:720-40:black@0[wave_clip_raw];\n"
        "[wave_clip_raw][mask]alphamerge[wave_clip_masked];\n"
        "[wave_inner]v360=input=rectilinear:output=fisheye[polar_inner];\n"
        "[wave_clip_masked]v360=input=rectilinear:output=fisheye[polar_clip];\n"
        "[polar_inner][polar_clip]blend=all_mode=lighten:all_opacity=1.0[combined];\n"
        "[combined][mask]alphamerge[circ_wave];\n"
        "[bg][circ_wave]overlay=(W-w)/2:(H-h)/2[bg_wave];\n"
        f"[bg_wave]drawtext=fontfile={FONT_FILE}:text=\"{title_text}\":"
        "x=(w-text_w)/2:y=60:fontsize=32:line_spacing=10:fontcolor=white[bg_text];\n"
        f"[bg_text]drawtext=fontfile={FONT_FILE}:text=\"{ticker_text}\":"
        "x=w-mod(t*120\\,w+text_w):y=h-60:fontsize=26:fontcolor=white[final];\n"
        "[final]fade=t=in:st=0:d=0.8[final_faded]\n"
    )

    return filter_complex

# ----------------------------------------------------------------------
# Run ffmpeg with the generated filtergraph script
# ----------------------------------------------------------------------
def run_ffmpeg():
    cmd = [
        "ffmpeg",
        "-loglevel", "debug",
        "-y",
        "-loop", "1",
        "-i", BG_IMAGE,
        "-i", AUDIO_FILE,
        "-filter_complex_script", os.path.abspath(FILTERGRAPH_PATH),
        "-map", "[final_faded]",
        "-map", "1:a",
        "-r", str(VIDEO_FPS),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "stillimage",
        "-crf", "30",
        "-c:a", "aac",
        "-b:a", "64k",
        "-shortest",
        "final.mp4",
    ]

    log("USING FILTERGRAPH SCRIPT:", os.path.abspath(FILTERGRAPH_PATH))
    log("FILTERGRAPH EXISTS:", os.path.exists(FILTERGRAPH_PATH))
    if os.path.exists(FILTERGRAPH_PATH):
        log("FILTERGRAPH SIZE:", os.path.getsize(FILTERGRAPH_PATH))
    log("CURRENT WORKING DIRECTORY:", os.getcwd())
    log("CMD LIST:", cmd)

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    log("CMD STDOUT:", proc.stdout)
    log("CMD STDERR:", proc.stderr)

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with code {proc.returncode}")

# ----------------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------------
def main():
    podcast_title = "Clintons Core Classics"
    season_label = "Season 6"
    episode_title = "Season 6 Spires of Xin-Shalast Teaser"
    ticker_text = f"Now Playing: {episode_title}"

    # Download audio first
    audio_url = os.environ.get("RSS_URL")
    if not audio_url:
        log("ERROR: RSS_URL environment variable not set")
        sys.exit(1)

    download_audio(audio_url, AUDIO_FILE)

    # Validate required files
    for path in (BG_IMAGE, AUDIO_FILE, FONT_FILE):
        if not os.path.exists(path):
            log("ERROR: Missing required file:", path)
            sys.exit(1)

    filtergraph = build_filtergraph(
        podcast_title,
        season_label,
        episode_title,
        ticker_text,
    )

    debug_filtergraph(FILTERGRAPH_PATH, filtergraph)
    run_ffmpeg()

    log("Rendering complete: final.mp4")

if __name__ == "__main__":
    main()
