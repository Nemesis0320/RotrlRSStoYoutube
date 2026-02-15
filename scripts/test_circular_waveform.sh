#!/usr/bin/env bash
set -e

echo "===== DEBUG: CURRENT WORKING DIRECTORY ====="
pwd
echo "===== DEBUG: LISTING ASSETS FOLDER ====="
ls -l assets
echo "===== END DEBUG ====="

echo "Fetching test audio..."
curl -L -o assets/test_audio.mp3 "https://quicksounds.com/uploads/tracks/528054973_948104858_1761723949.mp3"

echo "Running FFmpeg circular masked waveform test..."

ffmpeg -y \
  -loop 1 -i assets/1200x1200bf.webp \
  -i assets/test_audio.mp3 \
  -i assets/circle_mask_720.png \
  -filter_complex "\
[0:v]scale=1200:1200,setsar=1[bg]; \
[1:a]showwaves=s=1200x300:mode=line:colors=white:scale=lin*8[wave_raw]; \
[wave_raw]scale=1200:1200:flags=neighbor[wave_thick]; \
[wave_thick]gblur=sigma=12[wave_glow]; \
[2:v]scale=1200:1200:format=gray[mask]; \
[wave_glow][mask]alphamerge[wave_circle]; \
[bg][wave_circle]overlay=0:0[outv]" \
  -map "[outv]" -map 1:a \
  -c:v libx264 -preset veryfast -crf 18 \
  -c:a aac -b:a 192k \
  -shortest output_test.mp4

echo "Cleaning up test audio..."
rm -f assets/test_audio.mp3

echo "Done! Output written to output_test.mp4"
