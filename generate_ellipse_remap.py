#!/usr/bin/env python3
"""
Generate elliptical remap tables for FFmpeg's remap filter.
Outputs TWO grayscale images: one for X coordinates, one for Y coordinates.
"""
import numpy as np
from PIL import Image

# Canvas size
WIDTH = 720
HEIGHT = 720

# Ellipse geometry
CENTER_X = 360
CENTER_Y = 360
RX_OUTER = 300
RY_OUTER = 240
RX_INNER = 260
RY_INNER = 200

# Source waveform dimensions
WAVEFORM_WIDTH = 720
WAVEFORM_HEIGHT = 40

def generate_ellipse_remap():
    """Generate X and Y remap tables for elliptical waveform transformation."""
    
    # Create coordinate grids
    y, x = np.indices((HEIGHT, WIDTH), dtype=np.float32)
    
    # Calculate distance from center
    dx = x - CENTER_X
    dy = y - CENTER_Y
    
    # Calculate angle (theta) for each pixel
    theta = np.arctan2(dy, dx)
    
    # Calculate radius for each pixel
    r = np.hypot(dx, dy)
    
    # Calculate inner and outer ellipse radii at each angle
    cos_theta = np.cos(theta)
    sin_theta = np.sin(theta)
    
    r_inner = 1.0 / np.sqrt((cos_theta**2) / (RX_INNER**2) + (sin_theta**2) / (RY_INNER**2))
    r_outer = 1.0 / np.sqrt((cos_theta**2) / (RX_OUTER**2) + (sin_theta**2) / (RY_OUTER**2))
    
    # Create mask for pixels within the elliptical ring
    mask = (r >= r_inner) & (r <= r_outer)
    
    # Map angle to horizontal position in source waveform (0 to WAVEFORM_WIDTH-1)
    theta_normalized = (theta + np.pi) / (2.0 * np.pi)
    source_x = theta_normalized * (WAVEFORM_WIDTH - 1)
    
    # Map radius to vertical position in source waveform (0 to WAVEFORM_HEIGHT-1)
    t = (r - r_inner) / (r_outer - r_inner)
    t = np.clip(t, 0.0, 1.0)
    source_y = t * (WAVEFORM_HEIGHT - 1)
    
    # FFmpeg remap expects coordinates as pixel values (0..width-1, 0..height-1)
    # scaled to 0..65535 (16-bit) or 0..255 (8-bit) depending on format
    # We'll use 16-bit for better precision
    map_x = np.clip(source_x, 0, WAVEFORM_WIDTH - 1).astype(np.float32)
    map_y = np.clip(source_y, 0, WAVEFORM_HEIGHT - 1).astype(np.float32)
    
    # Scale to 0..65535 for 16-bit gray
    map_x_scaled = (map_x / (WAVEFORM_WIDTH - 1) * 65535).astype(np.uint16)
    map_y_scaled = (map_y / (WAVEFORM_HEIGHT - 1) * 65535).astype(np.uint16)
    
    # Set pixels outside ring to 0 (will sample from 0,0 - black)
    map_x_scaled[~mask] = 0
    map_y_scaled[~mask] = 0
    
    # Save as 16-bit grayscale PGM
    Image.fromarray(map_x_scaled, mode="I;16").save("ellipse_remap_x.pgm")
    Image.fromarray(map_y_scaled, mode="I;16").save("ellipse_remap_y.pgm")
    
    print(f"Generated ellipse_remap_x.pgm and ellipse_remap_y.pgm ({WIDTH}x{HEIGHT})")

if __name__ == "__main__":
    generate_ellipse_remap()
