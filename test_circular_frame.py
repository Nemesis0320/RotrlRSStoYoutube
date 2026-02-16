#!/usr/bin/env python3
"""
Test script: Generate a single circular waveform frame with realistic audio pattern.
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

# Generate REALISTIC waveform data (simulating actual audio)
num_samples = 360  # One sample per degree

# Simulate a sine wave pattern (like actual audio would look)
amplitudes = np.abs(np.sin(np.linspace(0, 4 * np.pi, num_samples))) * 0.6
# Add some variation
amplitudes += np.random.rand(num_samples) * 0.1
# Simulate clipping in one region
amplitudes[45:55] = 1.2

# Create transparent image
img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Draw reference circles (optional - to see the bounds)
# draw.ellipse([CENTER_X - RADIUS, CENTER_Y - RADIUS, 
#               CENTER_X + RADIUS, CENTER_Y + RADIUS], 
#              outline=(100, 100, 100, 100))

# Draw circular waveform
for i in range(num_samples):
    angle = (i / num_samples) * 2 * math.pi
    amplitude = amplitudes[i]
    
    # Determine color (gold or red for clipping)
    if amplitude > 0.9:
        color = (255, 0, 0, 255)  # Red for clipping
    else:
        color = (255, 215, 0, 255)  # Gold
    
    # Calculate line length based on amplitude
    line_length = amplitude * 50  # Scale factor (increased from 40)
    
    # Start point (inner circle)
    inner_r = RADIUS - 30
    x1 = CENTER_X + inner_r * math.cos(angle)
    y1 = CENTER_Y + inner_r * math.sin(angle)
    
    # End point (outer based on amplitude)
    outer_r = inner_r + line_length
    x2 = CENTER_X + outer_r * math.cos(angle)
    y2 = CENTER_Y + outer_r * math.sin(angle)
    
    # Draw line (thicker for visibility)
    draw.line([(x1, y1), (x2, y2)], fill=color, width=3)

# Save test frame
img.save('test_circular_frame.png')
print("Generated: test_circular_frame.png")
print("This should show:")
print("  - Gold radial lines forming a circular pattern")
print("  - Red spike around 45-55 degrees (simulated clipping)")
print("  - Pattern should look like a circular audio waveform")
