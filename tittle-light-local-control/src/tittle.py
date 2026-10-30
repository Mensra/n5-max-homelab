#!/usr/bin/env python3
"""tittle.py R G B INTENSITY            set the Tittle Light cube (8x8x8 LEDs) to one colour; intensity 0 = off. Values 0-255.
tittle.py show "SECTION / NAME" BRIGHTNESS [HH MM SS YY MM DD]   show one of the app's clock, emoji, mood or visualizer items by name (names from modes.tsv); BRIGHTNESS 0-255; the six numbers = the LOCAL time and date, needed by the clock items
tittle.py paint FILE.json [BRIGHTNESS]   draw a custom picture (the app's Paint format): {"interval_ms": 500, "frames": [[[layer,row,col,[r,g,b]], ...], ...]}; layer 1-8, row 1-8, column 1-8
tittle.py alert KEYS BRIGHTNESS HH MM SS YY MM DD [force]   show what the open alert keys (comma list) call for per alerts.json, else its idle item; does nothing when that is already showing
tittle.py ping                          print "on" when the cube answers on its port, else "off" (for the HA reachability sensor)
tittle.py draw BASE64JSON [BRIGHTNESS]   draw from a JSON drawing (dot/line/box/sphere/text ops, frames, spin, scroll; see render() below), the form a language model uses
tittle.py list                          print {"names": [...]} for Home Assistant (the select entity's options come from here, so modes.tsv is the one list)
Called by Home Assistant's shell_command tittle_set / tittle_show and a command_line sensor (configuration.yaml). Exit 0 = the cube acknowledged.
Protocol (TCP to the cube, port 9999; colour from github.com/TittleLight/tittle-sdk-android 2018, the rest read from the original iPad app's own network traffic, see docs/PROTOCOL.md): colour = 10 R G B I 0D 0A, reply 00 00 10 00 0D 0A. A mode is the app's own 18-20 byte message (type 20 emoji, 50 mood, 34 clock),
reply 00 00 <type> 00 0D 0A. Brightness = the one byte that is ff in every captured message (round 13: the app's slider re-sends the message with that byte changed): index 9 for types 20 and 50, 8 for 34, 5 for 41. modes.tsv = the labelled table (round, section, position, name, message hex[, flag]); a row with a flag (custom or uploaded pictures) is not shown by this script.
Paint upload (decoded from the original app's network traffic, see docs/PROTOCOL.md): header 90 00 <frames> <interval/8 ms> 00 00 <id> <counter> ff.. then 25 data blocks of at most 512 bytes (checksum = byte sum mod 256); each frame = an escape byte E (smallest byte not used by its colours), the 8x8x8 cells as RGB bytes with zero runs written E <n-1> 00 (E (80|n>>8) <n-1 low> 00 above 128), then ff ff ff ff.
The clock message holds the time (bytes 1-3) and the date (bytes 10-12), filled from the six arguments because the caller (for example a Home Assistant container running in UTC) knows the local time.
The cube has no read-back command, so Home Assistant shows an assumed state. The cube's address comes from $TITTLE_HOST or the file tittle.host next to this script (the cube also broadcasts a beacon from UDP port 10000 to port 12345 every ~11 s; its payload holds the IP)."""
import base64, csv, json, math, os, socket, sys, time

def _host():
    """The cube's address: $TITTLE_HOST, else the first line of tittle.host next to this script (one editable place; the cube gets its address by DHCP, so reserve it on your router or update the file)."""
    h = os.environ.get("TITTLE_HOST")
    if not h:
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tittle.host")) as f:
                h = f.readline().strip()
        except OSError:
            pass
    return h or "unset"


CUBE = _host()
PORT = 9999
BRIGHT_AT = {0x20: 9, 0x50: 9, 0x34: 8, 0x41: 5}   # index of the brightness byte per message type (round 13)
TABLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modes.tsv")


PICTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pictures")   # one FILE.json per custom picture; each is listed as "My pictures / NAME"
PIC_ID = 0x23D6   # the emoji id of the app's editing slot; the cube keeps ONE upload in memory, a new counter makes it take a repeat


def encode_frame(cells):
    """cells: 1536 bytes (512 cells x RGB, layer 1 first, row-major) -> the app's compressed frame."""
    used = set(cells)
    esc = next(b for b in range(1, 256) if b not in used)
    out, i = bytearray([esc]), 0
    while i < len(cells):
        if cells[i] == 0:
            j = i
            while j < len(cells) and cells[j] == 0:
                j += 1
            n = j - i
            if n >= 4:                              # a run of 3 zero bytes is no shorter than the token, the app writes it out
                m = n - 1
                out += bytes([esc, m, 0]) if m < 0x80 else bytes([esc, 0x80 | (m >> 8), m & 255, 0])
            else:
                out += bytes(n)
            i = j
        else:
            out.append(cells[i]); i += 1
    return bytes(out) + b"\xff\xff\xff\xff"


def build_picture(spec, level=255, counter=None, pic_id=None, announce_less=True):
    """spec = {"interval_ms": n, "frames": [[[layer,row,col,[r,g,b]], ...], ...]} -> list of message bytes (header, then the blocks).
    announce_less: the header announces ONE FRAME FEWER than the data holds, because the cube plays one frame more than the announced count and shows junk from its memory for that extra frame
    (measured 2026-10-30 on a 16-frame disk: 16 announced = junk once per turn, 15 announced = clean; the app's own previews announce the true count, why they show no junk is not known). False = the app's exact messages."""
    frames = list(spec["frames"])
    if not 1 <= len(frames) <= 255:
        raise ValueError("1-255 frames")
    if announce_less and len(frames) == 1:
        frames = frames * 2                           # a one-frame picture is sent twice (announced as 1)
    chunks, cur = [], b""
    for dots in frames:
        cells = bytearray(1536)
        for layer, row, col, rgb in dots:
            if not (1 <= layer <= 8 and 1 <= row <= 8 and 1 <= col <= 8):
                raise ValueError(f"dot {layer},{row},{col} is outside 1-8")
            at = 3 * ((layer - 1) * 64 + (row - 1) * 8 + (col - 1))
            cells[at:at + 3] = bytes(min(254, round(c * level / 255)) for c in rgb)   # never 0xff: four 0xff in a row ends a frame, and white dots side by side would write four
        fb = encode_frame(cells)
        if cur and len(cur) + len(fb) > 512:          # a block carries whole frames where it can (hypothesis: the cube plays blank frames when a frame spans two blocks)
            chunks.append(cur)
            cur = b""
        cur += fb
        while len(cur) > 512:                         # a frame longer than one block has to be split
            chunks.append(cur[:512])
            cur = cur[512:]
    if cur:
        chunks.append(cur)
    interval = max(0, min(255, int(spec.get("interval_ms", 0)) // 8))     # the byte is the interval in 8 ms steps (round 12: 500, 999, 1500 ms gave 3e, 7c, bb)
    counter = int(time.time()) & 255 if counter is None else counter
    msgs = [bytes([0x90, 0, len(frames) - (1 if announce_less else 0), interval, 0, 0, (pic_id or PIC_ID) >> 8, (pic_id or PIC_ID) & 255, counter, 0xFF]) + bytes(6) + b"\r\n"]
    for idx, ch in enumerate(chunks):
        msgs.append(bytes([0x25, 0, len(chunks), 0, idx]) + len(ch).to_bytes(2, "big") + ch + bytes([sum(ch) & 255]) + b"\r\n")
    return msgs


def send_picture(msgs):
    try:
        with socket.create_connection((CUBE, PORT), timeout=4) as s:
            s.settimeout(4)
            for k, m in enumerate(msgs):
                s.sendall(m)
                ack = s.recv(64)
                if k == 0 and ack[:3] != b"\x00\x00\x90":
                    sys.exit(f"tittle: unexpected reply {ack.hex()}")
                if k == 0 and ack[3:4] == b"\x00":
                    sys.exit("tittle: the cube refused the upload (it already holds this picture? change it or retry)")
    except OSError as e:
        sys.exit(f"tittle: cannot reach the cube at {CUBE}:{PORT}: {e}")


# ---- drawing vocabulary for language models (and people): tittle.py draw <base64 JSON> ---------------------------------------------------------------------------------------------
COLOURS = {"red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255), "white": (255, 255, 255), "yellow": (255, 220, 0), "orange": (255, 110, 0), "cyan": (0, 220, 255),
           "magenta": (255, 0, 255), "purple": (150, 0, 255), "pink": (255, 80, 160), "black": (0, 0, 0), "off": (0, 0, 0)}
FONT = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!?-+.: ", [l.split(",") for l in (
    "01110,10001,10001,11111,10001,10001,10001|11110,10001,10001,11110,10001,10001,11110|01110,10001,10000,10000,10000,10001,01110|11110,10001,10001,10001,10001,10001,11110|"
    "11111,10000,10000,11110,10000,10000,11111|11111,10000,10000,11110,10000,10000,10000|01110,10001,10000,10111,10001,10001,01111|10001,10001,10001,11111,10001,10001,10001|"
    "01110,00100,00100,00100,00100,00100,01110|00111,00010,00010,00010,00010,10010,01100|10001,10010,10100,11000,10100,10010,10001|10000,10000,10000,10000,10000,10000,11111|"
    "10001,11011,10101,10101,10001,10001,10001|10001,11001,10101,10101,10011,10001,10001|01110,10001,10001,10001,10001,10001,01110|11110,10001,10001,11110,10000,10000,10000|"
    "01110,10001,10001,10001,10101,10010,01101|11110,10001,10001,11110,10100,10010,10001|01111,10000,10000,01110,00001,00001,11110|11111,00100,00100,00100,00100,00100,00100|"
    "10001,10001,10001,10001,10001,10001,01110|10001,10001,10001,10001,10001,01010,00100|10001,10001,10001,10101,10101,11011,10001|10001,10001,01010,00100,01010,10001,10001|"
    "10001,10001,01010,00100,00100,00100,00100|11111,00001,00010,00100,01000,10000,11111|01110,10001,10011,10101,11001,10001,01110|00100,01100,00100,00100,00100,00100,01110|"
    "01110,10001,00001,00010,00100,01000,11111|11110,00001,00001,01110,00001,00001,11110|00010,00110,01010,10010,11111,00010,00010|11111,10000,11110,00001,00001,10001,01110|"
    "00110,01000,10000,11110,10001,10001,01110|11111,00001,00010,00100,01000,01000,01000|01110,10001,10001,01110,10001,10001,01110|01110,10001,10001,01111,00001,00010,01100|"
    "00100,00100,00100,00100,00100,00000,00100|01110,10001,00010,00100,00100,00000,00100|00000,00000,00000,11111,00000,00000,00000|00000,00100,00100,11111,00100,00100,00000|"
    "00000,00000,00000,00000,00000,00110,00110|00000,00110,00110,00000,00110,00110,00000|00000,00000,00000,00000,00000,00000,00000").split("|")]))


def _rgb(c):
    if isinstance(c, str):
        if c.lower() in COLOURS:
            return COLOURS[c.lower()]
        if len(c) == 7 and c[0] == "#":
            return tuple(int(c[k:k + 2], 16) for k in (1, 3, 5))
    elif isinstance(c, (list, tuple)) and len(c) == 3 and all(isinstance(v, int) and 0 <= v <= 255 for v in c):
        return tuple(c)
    raise ValueError(f"colour {c!r}: use a name ({', '.join(sorted(set(COLOURS) - {'off'}))}), '#rrggbb' or [r,g,b]")


def _ops_to_dots(ops):
    """The drawing vocabulary: each op paints voxels (layer 1 front..8 rear, row 1 top..8 bottom, column 1 left..8 right; later ops paint over earlier ones)."""
    cells = {}
    for op in ops:
        rgb = _rgb(op.get("color", "white"))
        if "dot" in op:
            pts = [tuple(op["dot"])]
        elif "line" in op:
            (a, b) = op["line"]
            n = max(abs(x - y) for x, y in zip(a, b)) or 1
            pts = [tuple(round(x + (y - x) * k / n) for x, y in zip(a, b)) for k in range(n + 1)]
        elif "box" in op:
            (a, b) = op["box"]
            lo, hi = [min(x, y) for x, y in zip(a, b)], [max(x, y) for x, y in zip(a, b)]
            pts = [(l, r, c) for l in range(lo[0], hi[0] + 1) for r in range(lo[1], hi[1] + 1) for c in range(lo[2], hi[2] + 1)
                   if op.get("fill", True) or any(v in (lo[k], hi[k]) for k, v in enumerate((l, r, c)))]
        elif "sphere" in op:
            sp = op["sphere"]
            (cl, cr, cc), rad, th = sp["center"], float(sp["radius"]), sp.get("thickness")
            pts = [(l, r, c) for l in range(1, 9) for r in range(1, 9) for c in range(1, 9)
                   if (rad - (th if th else rad)) <= ((l - cl) ** 2 + (r - cr) ** 2 + (c - cc) ** 2) ** 0.5 <= rad]
        elif "text" in op:
            layers = op.get("layers", [op.get("layer", 4)])
            col0, row0 = op.get("col", 1), op.get("row", 1)
            pts = []
            for k, ch in enumerate(str(op["text"]).upper()):
                for r, line in enumerate(FONT.get(ch, FONT[" "])):
                    for c, v in enumerate(line):
                        if v == "1":
                            pts += [(l, row0 + r, col0 + 6 * k + c) for l in layers]
        else:
            raise ValueError(f"unknown drawing op {sorted(op)}: use dot, line, box, sphere or text")
        for p in pts:
            if all(1 <= v <= 8 for v in p):
                cells[p] = rgb                           # points outside the 8 x 8 x 8 cube are clipped
    return [[l, r, c, list(rgb)] for (l, r, c), rgb in sorted(cells.items())]


def _spin(dots, frames, degrees, axis):
    out = []
    for f in range(frames):
        a = math.radians(degrees * f / frames)
        ca, sa = math.cos(a), math.sin(a)
        cells = {}
        for l, r, c, rgb in dots:
            x, y, z = c - 4.5, 4.5 - r, l - 4.5                      # x right, y up, z toward the rear
            if axis == "vertical":
                x, z = x * ca + z * sa, -x * sa + z * ca
            elif axis == "horizontal":                               # about the left-right axis
                y, z = y * ca - z * sa, y * sa + z * ca
            else:                                                    # "depth": about the front-rear axis, like a clock hand
                x, y = x * ca - y * sa, x * sa + y * ca
            p = (round(z + 4.5), round(4.5 - y), round(x + 4.5))
            if all(1 <= v <= 8 for v in p):
                cells[p] = rgb
        out.append([[l, r, c, rgb] for (l, r, c), rgb in sorted(cells.items())])
    return out


def render(spec):
    """spec -> the picture dict build_picture takes. Keys: interval_ms (0-2040, default 100); frames = [[op, ...], ...]; or spin = {frames, degrees (default 360), axis vertical|horizontal|depth}
    which turns the FIRST frame as one object; or scroll = {text, color, layers (default [4, 5]), row (default 1)} which scrolls a message right to left."""
    if not isinstance(spec, dict):
        raise ValueError("the drawing must be a JSON object")
    ms = int(spec.get("interval_ms", 100))
    if "scroll" in spec:
        sc = spec["scroll"]
        txt = str(sc["text"]).upper()
        width = 6 * len(txt)
        frames = []
        for shift in range(width + 8):
            dots = _ops_to_dots([{"text": txt, "col": 9 - shift, "row": sc.get("row", 1), "layers": sc.get("layers", [4, 5]), "color": sc.get("color", "white")}])
            frames.append(dots)
    else:
        frames = [_ops_to_dots(f) for f in spec.get("frames", [])]
        if "spin" in spec:
            sp = spec["spin"]
            frames = _spin(frames[0], int(sp.get("frames", 16)), float(sp.get("degrees", 360)), sp.get("axis", "vertical"))
    if not 1 <= len(frames) <= 120:
        raise ValueError("a drawing needs 1-120 frames")
    return {"interval_ms": ms, "frames": frames}


def draw(b64, level=255):
    try:
        spec = json.loads(base64.b64decode(b64))
        pic = render(spec)
        msgs = build_picture(pic, level)
    except (ValueError, KeyError, TypeError, IndexError) as e:
        sys.exit(f"tittle: bad drawing: {type(e).__name__}: {e}")
    send_picture(msgs)


def rows():
    with open(TABLE, newline="") as f:
        for r in csv.reader(f, delimiter="\t"):
            if len(r) == 5:                       # a sixth column = flag: custom or uploaded pictures, not replayable by a plain select
                yield f"{r[1]} / {r[3]}", r[4]
    if os.path.isdir(PICTURES):
        for f in sorted(os.listdir(PICTURES)):
            if f.endswith(".json"):
                yield f"My pictures / {f[:-5]}", "paint:" + os.path.join(PICTURES, f)


def send(msg, kind):
    try:
        with socket.create_connection((CUBE, PORT), timeout=4) as s:
            s.settimeout(4)
            s.sendall(msg)
            ack = s.recv(64)
    except OSError as e:
        sys.exit(f"tittle: cannot reach the cube at {CUBE}:{PORT}: {e}")
    if ack[:2] != b"\x00\x00" or ack[2] != kind:
        sys.exit(f"tittle: unexpected reply {ack.hex()}")


def paint(path, level=255):
    try:
        with open(path) as f:
            msgs = build_picture(json.load(f), level)
    except (OSError, ValueError, KeyError, TypeError) as e:
        sys.exit(f"tittle: bad picture file {path}: {e}")
    send_picture(msgs)


ALERTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alerts.json")   # editable: {"idle": "Clock / Lifting", "rules": [{"match": ["dns"], "picture": "alert-dns"}, ...]}, the first rule that matches an open alert key wins
LAST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last-alert-display")  # the item the alert logic showed last (the cube has no read-back), so an unchanged alert set never re-uploads (every upload flashes the cube)


def show_named(name, lvl, tm):
    """Show one item of the select by name; tm = [HH, MM, SS, YY, MM, DD] (the local time, needed by the clock items)."""
    hexmsg = dict(rows()).get(name)
    if hexmsg is None:
        sys.exit(f"tittle: no such item {name!r} (see: tittle.py list)")
    if hexmsg.startswith("paint:"):
        paint(hexmsg[6:], lvl)
        return
    m = bytearray.fromhex(hexmsg)
    m[BRIGHT_AT[m[0]]] = lvl
    if m[0] == 0x34:                              # clock: time (bytes 1-3) and date (bytes 10-12) are the owner's local now
        if len(tm) != 6:
            sys.exit("tittle: a clock item needs the six numbers HH MM SS YY MM DD")
        m[1:4] = bytes(tm[0:3])
        m[10:13] = bytes(tm[3:6])
    send(bytes(m), m[0])


def alert(keys, lvl, tm, force):
    """Show what the open alert keys call for (the rules file), else the idle item; only when it differs from what was shown last (or force)."""
    try:
        with open(ALERTS) as f:
            cfg = json.load(f)
        want = cfg["idle"]
        for rule in cfg["rules"]:
            if any(p in k for k in keys.split(",") for p in rule["match"]):
                want = "My pictures / " + rule["picture"]
                break
    except (OSError, ValueError, KeyError, TypeError) as e:
        sys.exit(f"tittle: bad alerts file {ALERTS}: {e}")
    try:
        last = open(LAST).read()
    except OSError:
        last = ""
    if want == last and not force:
        return
    show_named(want, lvl, tm)
    with open(LAST, "w") as f:
        f.write(want)


def main():
    a = sys.argv[1:]
    if a[:1] == ["ping"]:
        try:
            socket.create_connection((CUBE, PORT), timeout=3).close()
            print("on")
        except OSError:
            print("off")
        return
    if a[:1] == ["draw"] and len(a) in (2, 3):
        draw(a[1], int(a[2]) if len(a) == 3 else 255)
        open(LAST, "w").write("(a drawing)")
        return
    if a[:1] == ["paint"] and len(a) in (2, 3):
        paint(a[1], int(a[2]) if len(a) == 3 else 255)
        open(LAST, "w").write("(a picture)")
        return
    if a[:1] == ["list"]:
        print(json.dumps({"names": [n for n, _ in rows()]}))
        return
    if a[:1] in (["show"], ["alert"]):
        try:
            tm = [int(x) for x in a[3:9]]
            lvl = int(a[2])
            assert 0 <= lvl <= 255 and len(a) in (3, 9, 10)
        except (ValueError, AssertionError, IndexError):
            sys.exit("tittle: usage: show NAME BRIGHTNESS [HH MM SS YY MM DD]  |  alert KEYS BRIGHTNESS HH MM SS YY MM DD [force]")
        if a[0] == "show":
            show_named(a[1], lvl, tm)
            open(LAST, "w").write(a[1])               # the alert logic must know what is on the cube now
        else:
            alert(a[1], lvl, tm, a[9:10] == ["force"])
        return
    try:
        r, g, b, i = (int(x) for x in a[:4])
        if len(a) != 4 or not all(0 <= v <= 255 for v in (r, g, b, i)):
            raise ValueError
    except ValueError:
        sys.exit(__doc__.split("\n")[0] + "\n" + __doc__.split("\n")[1])
    send(bytes([0x10, r, g, b, i, 0x0D, 0x0A]), 0x10)


main()
