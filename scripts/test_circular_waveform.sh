#!/usr/bin/env bash
set -e

echo "===== DEBUG: CURRENT WORKING DIRECTORY ====="
pwd
echo "===== DEBUG: LISTING ASSETS FOLDER ====="
ls -l assets
echo "===== END DEBUG ====="

echo "Fetching test audio..."
curl -L -o assets/test_audio.mp3 "https://quicksounds.com/uploads/tracks/528054973_948104858_1761723949.mp3"

echo "Running FFmpeg high‑visibility waveform test (FFmpeg‑compatible)..."

ffmpeg -y \
  -loop 1 -i assets/1200x1200bf.webp \
  -i assets/test_audio.mp3 \
  -filter_complex "\
[0:v]scale=1200:1200,setsar=1[bg]; \
[1:a]showwaves=s=1200x300:mode=line:colors=white:scale=lin*6[wave_raw]; \
[wave_raw]scale=1200:1200:flags=neighbor[wave_scaled]; \
[wave_scaled]lut='val=max(val,120)'[wave_floor]; \
[wave_floor]format=rgba,colorchannelmixer=rr=1:rg=0.4:rb=0:gr=1:gg=0.4:gb=0:br=0.2:bg=0:bb=0[wave_color]; \
[wave_color]gblur=sigma=10[wave_glow]; \
[bg][wave_glow]overlay=0:0[outv]" \
  -map "[outv]" -map 1:a \
  -c:v libx264 -preset veryfast -crf 18 \
  -c:a aac -b:a 192k \
  -shortest output_test.mp4

echo "Cleaning up test audio..."
rm -f assets/test_audio.mp3

echo "Done! Output written to output_test.mp4"
