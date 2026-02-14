#!/usr/bin/env bash
set -e
# Test Script: Circular Waveform Visualizer
# Ensure assets directory exists
mkdir -p assets
echo "Fetching test audio..."
curl -L -o assets/test_audio.mp3 "https://quicksounds.com/uploads/tracks/528054973_948104858_1761723949.mp3"
echo "Running FFmpeg circular waveform test..."
echo "===== DEBUG: PRINTING FILTERGRAPH FILE ====="
cat assets/circular_waveform.ffgraph
echo "===== END DEBUG ====="
ffmpeg -y -loop 1 -i assets/1200x1200bf.png -i assets/test_audio.mp3 -filter_complex_script assets/circular_waveform.ffgraph -map "[outv]" -map 1:a -c:v libx264 -preset veryfast -crf 18 -c:a aac -b:a 192k -shortest output_test.mp4
echo "Cleaning up test audio..."
rm -f assets/test_audio.mp3
echo "Done! Output written to output_test.mp4"
