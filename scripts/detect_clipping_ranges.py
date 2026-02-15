#!/usr/bin/env python3
import re
import sys
import subprocess

if len(sys.argv) < 2:
    print("Usage: detect_clipping_ranges.py INPUT_AUDIO.mp3 [threshold_db]")
    sys.exit(1)

audio = sys.argv[1]
threshold_db = float(sys.argv[2]) if len(sys.argv) > 2 else -1.0
rate = 12.0  # must match showwaves rate

cmd = [
    "ffmpeg", "-hide_banner", "-nostats", "-i", audio,
    "-af", "astats=metadata=1:reset=1",
    "-f", "null", "-"
]
proc = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
log = proc.stderr

pattern = re.compile(r"lavfi\.astats\.Overall\.Peak_level=([-\d\.]+) dB")
vals = [float(m) for m in pattern.findall(log)]

ranges = []
in_range = False
start_idx = None

for i, peak in enumerate(vals):
    if peak >= threshold_db:
        if not in_range:
            in_range = True
            start_idx = i
    else:
        if in_range:
            ranges.append((start_idx, i - 1))
            in_range = False

if in_range:
    ranges.append((start_idx, len(vals) - 1))

for s, e in ranges:
    t0 = s / rate
    t1 = (e + 1) / rate
    print(f"{t0:.3f},{t1:.3f}")
