#!/usr/bin/env python3
"""make_pictures.py : writes alert-dns.json, alert-drive.json and door-walker.json for tittle.py paint (coordinates: layer 1 front..8 rear, row 1 top..8 bottom, column 1 left..8 right).
alert-dns   = the letters D, N, S (white, 0.5 s each) then the red/blue beacon of alert-beacon.json (16 frames).
alert-drive = a floppy disk (blue body, silver shutter, white label) turning slowly about the vertical axis (16 frames, 250 ms = 4 s a turn).
door-walker = a person walks from the front to a door at the rear, the door lights up (20 frames, 150 ms)."""
import json, math
WHITE, BLUE, RED, SILVER, ORANGE, YELLOW, SKIN = [255, 255, 255], [0, 80, 255], [255, 0, 0], [190, 190, 200], [255, 110, 0], [255, 220, 0], [255, 200, 160]
FONT = {"D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
        "N": ["10001", "11001", "10101", "10101", "10011", "10001", "10001"],
        "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"]}
def letter(ch):
    return [[l, r + 1, 2 + c, WHITE] for r, row in enumerate(FONT[ch]) for c, v in enumerate(row) if v == "1" for l in (4, 5)]
beacon = json.load(open("alert-beacon.json"))
INTERVAL = 100                                    # the picture has one interval: letters are held by repeating the frame
dns = [letter(ch) for ch in "DNS" for _ in range(5)] + beacon["frames"]
json.dump({"interval_ms": INTERVAL, "frames": dns}, open("alert-dns.json", "w"))

def disk(theta):
    """A spinning hard-disk platter facing the front (layers 4-5): a blue ring, a white hub and a red arm that sweeps round, like a drive reading."""
    dots = []
    for layer in (4, 5):
        for row in range(1, 9):
            for col in range(1, 9):
                x, y = col - 4.5, 4.5 - row
                d = math.hypot(x, y)
                along, across = x * math.cos(theta) + y * math.sin(theta), -x * math.sin(theta) + y * math.cos(theta)
                if d <= 0.9:
                    colour = WHITE                                   # the hub
                elif 1.0 <= along <= 3.7 and abs(across) <= 0.55:
                    colour = RED                                     # the arm
                elif 2.7 <= d <= 3.9:
                    colour = BLUE                                    # the platter's rim
                else:
                    continue
                dots.append([layer, row, col, colour])
    return dots
json.dump({"interval_ms": 200, "frames": [disk(2 * math.pi * f / 16) for f in range(16)]}, open("alert-drive.json", "w"))

def door(lit):
    d = [[8, r, c, ORANGE] for r in range(2, 9) for c in (3, 6)] + [[8, 2, c, ORANGE] for c in (4, 5)]
    if lit:
        d += [[8, r, c, YELLOW] for r in range(3, 9) for c in (4, 5)]
    else:
        d += [[8, 6, 5, YELLOW]]                  # the knob
    return d
CYAN = [0, 200, 255]
def person(layer, stride):
    """7 rows tall: a 2 x 2 white head, a cyan body with swinging arms, striding legs."""
    p = [[layer, r, c, WHITE] for r in (2, 3) for c in (4, 5)]
    p += [[layer, r, c, CYAN] for r in (4, 5) for c in (4, 5)]
    p += [[layer, 4, 3, CYAN], [layer, 5, 6, CYAN]] if stride == 0 else [[layer, 5, 3, CYAN], [layer, 4, 6, CYAN]]
    if stride == 0:
        p += [[layer, r, c, WHITE] for r in (6, 7, 8) for c in (4, 5)]
    else:
        p += [[layer, 6, c, WHITE] for c in (4, 5)] + [[layer, r, c, WHITE] for r in (7, 8) for c in (3, 6)]
    return p
frames = []
for layer in range(1, 8):
    for stride in (0, 1):
        frames.append(door(False) + person(layer, stride))
frames += [door(True) + person(7, 0)] * 6
json.dump({"interval_ms": 150, "frames": frames}, open("door-walker.json", "w"))
print("frames", len(dns), 16, len(frames))
