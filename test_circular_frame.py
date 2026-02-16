#!/usr/bin/env python3
"""
Test script: Generate a single circular waveform frame.
"""
import numpy as np
from PIL import Image, ImageDraw
import math

# Canvas settings
WIDTH = 720
HEIGHT = 720
CENTER_X = 360
CENTER_Y = 360
RADIUS = 280

# Generate fake waveform data (replace with real audio later)
num_samples = 360  # One sample per degree
amplitudes = np.random.rand(num_samples) * 0.8  # Random amplitudes 0.0-0.8
amplitudes[45:55] = 1.2  # Simulate clipping in one region

# Create image
img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Draw circular waveform
for i in range(num_samples):
    angle = (i / num_samples) * 2 * math.pi
    amplitude = amplitudes[i]
    
    # Determine color (gold or red for clipping)
    color = (255, 0, 0, 255) if amplitude > 0.9 else (255, 215, 0, 255)  # Red or gold
    
    # Calculate line length based on amplitude
    line_length = amplitude * 40  # Scale factor
    
    # Start point (inner circle)
    inner_r = RADIUS - 20
    x1 = CENTER_X + inner_r * math.cos(angle)
    y1 = CENTER_Y + inner_r * math.sin(angle)
    
    # End point (outer based on amplitude)
    outer_r = inner_r + line_length
    x2 = CENTER_X + outer_r * math.cos(angle)
    y2 = CENTER_Y + outer_r * math.sin(angle)
    
    # Draw line
    draw.line([(x1, y1), (x2, y2)], fill=color, width=2)

# Save test frame
img.save('test_circular_frame.png')
print("Generated: test_circular_frame.png")
