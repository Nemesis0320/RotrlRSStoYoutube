import numpy as np
from PIL import Image

WIDTH = 1200
HEIGHT = 1200
CENTER_X = 600
CENTER_Y = 555
R_MIN = 240
R_MAX = 280

wave = Image.open("wave_linear.png").convert("L")
wave_np = np.array(wave)
h_src, w_src = wave_np.shape

out = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)

for y in range(HEIGHT):
    for x in range(WIDTH):
        dx = x - CENTER_X
        dy = y - CENTER_Y
        r = np.sqrt(dx*dx + dy*dy)
        if r < R_MIN or r > R_MAX:
            continue
        a = (np.arctan2(dy, dx) + np.pi) / (2 * np.pi)
        sx = int(a * (w_src - 1))
        sy = int(((r - R_MIN) / (R_MAX - R_MIN)) * (h_src - 1))
        out[y, x] = wave_np[sy, sx]

Image.fromarray(out).save("wave_circle.png")
