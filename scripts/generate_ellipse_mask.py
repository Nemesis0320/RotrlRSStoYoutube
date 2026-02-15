import numpy as np
from PIL import Image

# Output / map resolution
WIDTH = 1200
HEIGHT = 1200

# Ellipse geometry (your points)
CENTER_X = 600
CENTER_Y = 555

A_IN = 222.0
B_IN = 260.0
A_OUT = 240.0
B_OUT = 274.0

# Source waveform resolution (from showwaves)
W_SRC = 1200
H_SRC = 5

y, x = np.indices((HEIGHT, WIDTH))
dx = x - CENTER_X
dy = y - CENTER_Y

theta = np.arctan2(dy, dx)
cos_t = np.cos(theta)
sin_t = np.sin(theta)

r_in = 1.0 / np.sqrt((cos_t**2) / (A_IN**2) + (sin_t**2) / (B_IN**2))
r_out = 1.0 / np.sqrt((cos_t**2) / (A_OUT**2) + (sin_t**2) / (B_OUT**2))
r = np.hypot(dx, dy)

mask = (r >= r_in) & (r <= r_out)

t = (r - r_in) / (r_out - r_in)
t = np.clip(t, 0.0, 1.0)

a = (theta + np.pi) / (2.0 * np.pi)
a = np.clip(a, 0.0, 1.0)

sx = a * (W_SRC - 1)
sy = t * (H_SRC - 1)

# Normalize to 0..255 for remap (FFmpeg interprets as 0..1)
map_r = (sx / (W_SRC - 1) * 255.0).astype(np.uint8)
map_g = (sy / (H_SRC - 1) * 255.0).astype(np.uint8)

# Outside the band: send to black (0,0)
map_r[~mask] = 0
map_g[~mask] = 0

map_b = np.zeros_like(map_r, dtype=np.uint8)

remap_img = np.stack([map_r, map_g, map_b], axis=-1)
Image.fromarray(remap_img, mode="RGB").save("ellipse_remap.ppm")
