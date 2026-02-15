#!/usr/bin/env python3
"""
Generate elliptical remap table for FFmpeg's remap filter.
Maps a linear waveform to an elliptical ring around the emblem.
"""
import numpy as np
from PIL import Image

# Canvas size (720x720 to match video)
WIDTH = 720
HEIGHT = 720

# Ellipse geometry (from your measurements)
CENTER_X = 360
CENTER_Y = 360
RX_OUTER = 300  # Horizontal radius of outer ellipse
RY_OUTER = 240  # Vertical radius of outer ellipse
RX_INNER = 260  # Horizontal radius of inner ellipse
RY_INNER = 200  # Vertical radius of inner ellipse

# Source waveform dimensions (from showwaves)
WAVEFORM_WIDTH = 720
WAVEFORM_HEIGHT = 40  # Height of the waveform strip

def generate_ellipse_remap():
    """Generate the remap table for elliptical waveform transformation."""
    
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
    
    # Map angle to horizontal position in source waveform (0 to WAVEFORM_WIDTH)
    # Normalize theta from [-π, π] to [0, 1]
    theta_normalized = (theta + np.pi) / (2.0 * np.pi)
    source_x = theta_normalized * (WAVEFORM_WIDTH - 1)
    
    # Map radius to vertical position in source waveform (0 to WAVEFORM_HEIGHT)
    # t = 0 at inner ellipse, t = 1 at outer ellipse
    t = (r - r_inner) / (r_outer - r_inner)
    t = np.clip(t, 0.0, 1.0)
    source_y = t * (WAVEFORM_HEIGHT - 1)
    
    # Normalize coordinates to 0..255 for FFmpeg remap
    # FFmpeg interprets remap values as normalized 0..1 coordinates
    map_x = (source_x / (WAVEFORM_WIDTH - 1) * 255.0).astype(np.uint8)
    map_y = (source_y / (WAVEFORM_HEIGHT - 1) * 255.0).astype(np.uint8)
    
    # Pixels outside the elliptical ring map to (0, 0) - black
    map_x[~mask] = 0
    map_y[~mask] = 0
    
    # Create RGB image (R=x coordinate, G=y coordinate, B=unused)
    map_b = np.zeros_like(map_x, dtype=np.uint8)
    remap_image = np.stack([map_x, map_y, map_b], axis=-1)
    
    # Save as PPM (raw format that FFmpeg can read efficiently)
    Image.fromarray(remap_image, mode="RGB").save("ellipse_remap.ppm")
    print(f"Generated ellipse_remap.ppm ({WIDTH}x{HEIGHT})")

if __name__ == "__main__":
    generate_ellipse_remap()
