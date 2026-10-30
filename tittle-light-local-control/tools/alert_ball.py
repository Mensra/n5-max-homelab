#!/usr/bin/env python3
"""alert_ball.py > alert-ball.json : a hollow ball in the middle of the 8x8x8 cube, half red and half blue, turning about the vertical axis (a police-light look).
Coordinates as tittle.py paint: layer 1 front..8 rear, row 1 top..8 bottom, column 1 left..8 right. 16 frames = 22.5 degrees each, 100 ms per frame (1.6 s per turn)."""
import json, math
FRAMES, R_IN, R_OUT, MS = 16, 2.4, 3.5, 100
RED, BLUE = [255, 0, 0], [0, 0, 255]
frames = []
for f in range(FRAMES):
    phase = 2 * math.pi * f / FRAMES
    dots = []
    for layer in range(1, 9):
        for row in range(1, 9):
            for col in range(1, 9):
                x, y, z = col - 4.5, 4.5 - row, layer - 4.5          # x right, y up, z toward the rear
                if not R_IN <= math.sqrt(x * x + y * y + z * z) <= R_OUT:
                    continue
                dots.append([layer, row, col, RED if math.cos(math.atan2(z, x) - phase) >= 0 else BLUE])
    frames.append(dots)
print(json.dumps({"interval_ms": MS, "frames": frames}))
