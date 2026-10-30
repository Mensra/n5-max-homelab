#!/usr/bin/env python3
"""alert_beacon.py > alert-beacon.json : a red blob and a blue blob (about 2 dots across, 8 dots each) orbiting the middle of the 8x8x8 cube on opposite sides of the vertical axis, like a police beacon.
Coordinates as tittle.py paint: layer 1 front..8 rear, row 1 top..8 bottom, column 1 left..8 right. 16 frames = 22.5 degrees each, 100 ms per frame (1.6 s per turn)."""
import json, math
FRAMES, ORBIT, BLOB, MS = 16, 2.3, 1.15, 100
RED, BLUE = [255, 0, 0], [0, 0, 255]
frames = []
for f in range(FRAMES):
    a = 2 * math.pi * f / FRAMES
    dots = []
    for colour, shift in ((RED, 0.0), (BLUE, math.pi)):
        cx, cz = ORBIT * math.cos(a + shift), ORBIT * math.sin(a + shift)      # offset from the middle: x right, z toward the rear
        for layer in range(1, 9):
            for row in range(1, 9):
                for col in range(1, 9):
                    x, y, z = col - 4.5 - cx, 4.5 - row, layer - 4.5 - cz    # y = 0 at the middle height (rows 4 and 5 are +-0.5)
                    if math.sqrt(x * x + y * y + z * z) <= BLOB:
                        dots.append([layer, row, col, colour])
    frames.append(dots)
print(json.dumps({"interval_ms": MS, "frames": frames}))
