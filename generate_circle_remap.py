#!/usr/bin/env python3
import numpy as np
from PIL import Image

# Canvas size
WIDTH = 720
HEIGHT = 720

# Circle geometry
CENTER_X = WIDTH // 2
CENTER_Y = HEIGHT // 2
R_OUTER = 300      # outer radius of ring
R_INNER = 260      # inner radius of ring

# Source waveform dimensions
WAVEFORM_WIDTH = 720
WAVEFORM_HEIGHT = 40

def generate_circle_remap():
    # Coordinate grid
    y, x = np.indices((HEIGHT, WIDTH), dtype=np.float32)

    dx = x - CENTER_X
    dy = y - CENTER_Y

    # Polar coordinates
    theta = np.arctan2(dy, dx)
    r = np.hypot(dx, dy)

    # Mask: pixels within circular ring
    mask = (r >= R_INNER) & (r <= R_OUTER)

    # Map angle to horizontal position in source waveform
    theta_norm = (theta + np.pi) / (2 * np.pi)  # 0..1
    source_x = theta_norm * (WAVEFORM_WIDTH - 1)

    # Map radius to vertical position in source waveform
    t = (r - R_INNER) / (R_OUTER - R_INNER)
    t = np.clip(t, 0.0, 1.0)
    source_y = t * (WAVEFORM_HEIGHT - 1)

    # Convert to 8-bit RGB remap image
    map_x = (source_x / (WAVEFORM_WIDTH - 1) * 255).astype(np.uint8)
    map_y = (source_y / (WAVEFORM_HEIGHT - 1) * 255).astype(np.uint8)
    map_b = np.zeros_like(map_x, dtype=np.uint8)

    # Outside ring → sample from (0,0) = black
    map_x[~mask] = 0
    map_y[~mask] = 0

    remap = np.stack([map_x, map_y, map_b], axis=-1)

    Image.fromarray(remap, mode="RGB").save("ellipse_remap.ppm")
    print("Generated ellipse_remap.ppm (circular remap)")

if __name__ == "__main__":
    generate_circle_remap()
