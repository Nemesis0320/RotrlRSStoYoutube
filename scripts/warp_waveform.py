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

out = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)

for y in range(HEIGHT):
    dy = y - CENTER_Y
    for x in range(WIDTH):
        dx = x - CENTER_X

        theta = np.arctan2(dy, dx)
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)

        r = np.hypot(dx, dy)

        r_in = 1.0 / np.sqrt(
            (cos_t * cos_t) / (A_IN * A_IN) +
            (sin_t * sin_t) / (B_IN * B_IN)
        )
        r_out = 1.0 / np.sqrt(
            (cos_t * cos_t) / (A_OUT * A_OUT) +
            (sin_t * sin_t) / (B_OUT * B_OUT)
        )

        if r < r_in or r > r_out:
            continue

        t = (r - r_in) / (r_out - r_in)
        if t < 0.0 or t > 1.0:
            continue

        a = (theta + np.pi) / (2.0 * np.pi)
        sx = int(a * (w_src - 1))
        sy = int(t * (h_src - 1))

        out[y, x] = wave_np[sy, sx]

Image.fromarray(out).save("wave_circle.png")
