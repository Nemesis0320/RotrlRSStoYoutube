import numpy as np
from PIL import Image

WIDTH = 1200
HEIGHT = 1200

CENTER_X = 600
CENTER_Y = 555

A_IN = 222.0
B_IN = 260.0
A_OUT = 240.0
B_OUT = 274.0

wave = Image.open("wave_linear.png").convert("L")
wave_np = np.array(wave)
h_src, w_src = wave_np.shape

# Create coordinate grid
y, x = np.indices((HEIGHT, WIDTH))
dx = x - CENTER_X
dy = y - CENTER_Y

theta = np.arctan2(dy, dx)
cos_t = np.cos(theta)
sin_t = np.sin(theta)

# Ellipse radii at each angle
r_in = 1.0 / np.sqrt((cos_t**2) / (A_IN**2) + (sin_t**2) / (B_IN**2))
r_out = 1.0 / np.sqrt((cos_t**2) / (A_OUT**2) + (sin_t**2) / (B_OUT**2))

# Actual radius
r = np.hypot(dx, dy)

# Mask of pixels inside elliptical band
mask = (r >= r_in) & (r <= r_out)

# Normalized radial position 0..1
t = (r - r_in) / (r_out - r_in)
t = np.clip(t, 0.0, 1.0)

# Angular position 0..1
a = (theta + np.pi) / (2.0 * np.pi)
a = np.clip(a, 0.0, 1.0)

# Map to waveform coordinates
sx = (a * (w_src - 1)).astype(int)
sy = (t * (h_src - 1)).astype(int)

# Output image
out = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
out[mask] = wave_np[sy[mask], sx[mask]]

Image.fromarray(out).save("wave_circle.png")
