#!/usr/bin/env bash
set -e

# -----------------------------------------
# Test Script: Circular Waveform Visualizer
# -----------------------------------------

# Ensure assets directory exists
mkdir -p assets

echo "Fetching test audio from YouTube..."
yt-dlp -f bestaudio --extract-audio --audio-format mp3 --audio-quality 0 -o assets/test_audio.%(ext)s "https://www.youtube.com/watch?v=6aXFNtEm7Hc"

echo "Running FFmpeg circular waveform test..."
ffmpeg -y \
  -i assets/background.png \
  -i assets/test_audio.mp3 \
  -filter_complex_script assets/circular_waveform.ffgraph \
  -map "[outv]" -map 1:a \
  -c:v libx264 -preset veryfast -crf 18 \
  -c:a aac -b:a 192k \
  output_test.mp4

echo "Cleaning up test audio..."
rm -f assets/test_audio.mp3

echo "Done! Output written to output_test.mp4"
