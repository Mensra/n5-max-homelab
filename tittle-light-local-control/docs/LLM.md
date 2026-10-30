# Letting a language model draw on the cube

`tittle.py draw` takes one JSON object and shows it. The vocabulary is small on purpose so that a model can write it reliably, and every mistake comes back as a plain sentence the model can read and fix.

```sh
python3 src/tittle.py draw "$(echo '{"interval_ms":120,"spin":{"frames":16,"axis":"vertical"},"frames":[[{"box":[[3,3,3],[6,6,6]],"color":"cyan","fill":false}]]}' | base64 -w0)"
```

(The JSON travels base64-encoded so that no shell or template quoting can break it.)

## The description to give the model (copy this into the tool description)

```
Draw an animation on the Tittle Light cube (8 x 8 x 8 RGB LEDs). Give the drawing as JSON.
COORDINATES: layer 1 = FRONT .. 8 = REAR (depth), row 1 = TOP .. 8 = BOTTOM, column 1 = LEFT .. 8 = RIGHT, as seen from the front. The middle of the cube is [4.5, 4.5, 4.5].
SPEC: {"interval_ms": 100, "frames": [ FRAME, FRAME, ... ]} where FRAME is a list of drawing ops, painted in order (later ops paint over earlier ones; anything outside 1-8 is clipped; a frame starts empty).
OPS: {"dot": [layer,row,col], "color": C}  {"line": [[l,r,c],[l,r,c]], "color": C}  {"box": [[l,r,c],[l,r,c]], "color": C, "fill": true|false}  {"sphere": {"center": [l,r,c], "radius": 2.5, "thickness": 1}, "color": C} (leave out thickness for a solid ball)  {"text": "HI", "layers": [4,5], "row": 1, "col": 2, "color": C} (5 x 7 letters A-Z 0-9 ! ? - + . :, one letter fits the 8 columns, so show one letter per frame or use scroll).
COLORS: red green blue white yellow orange cyan magenta purple pink black, or "#rrggbb", or [r,g,b].
SHORTCUTS: {"spin": {"frames": 16, "degrees": 360, "axis": "vertical"|"horizontal"|"depth"}, "frames": [ONE FRAME]} turns that one frame's object about the cube's middle; {"scroll": {"text": "DNS DOWN", "color": "red", "layers": [4,5]}} scrolls a message right to left.
LIMITS: 1-120 frames, interval_ms 0-2040 (steps of 8 ms), about 100 lit LEDs per frame is clear. Every upload makes the cube flash once; do not redraw more often than every few seconds. The result says "ok" or an error text that names the problem: fix the JSON and call again.
```

## Examples a model can imitate

A ball that pulses:
```json
{"interval_ms": 240, "frames": [
  [{"sphere": {"center": [4.5,4.5,4.5], "radius": 1.2}, "color": "red"}],
  [{"sphere": {"center": [4.5,4.5,4.5], "radius": 2.7, "thickness": 1}, "color": "red"}]]}
```
A hollow cyan cube turning about the vertical axis:
```json
{"interval_ms": 120, "spin": {"frames": 16, "axis": "vertical"},
 "frames": [[{"box": [[3,3,3],[6,6,6]], "color": "cyan", "fill": false}]]}
```
A message: `{"interval_ms": 110, "scroll": {"text": "DISK FULL", "color": "orange"}}`

## Tips learned the hard way
- Large uploads flash the cube once; a looping animation is uploaded once and then plays by itself.
- Keep frames to about 100 lit LEDs; a 16-frame picture with ~100 LEDs per frame uploads in a second or two.
- The cube cannot tell you what it is showing: a controlling program should remember what it sent last and avoid re-sending the same picture (see `alert` in `tittle.py`).

## As a Home Assistant tool
[homeassistant/configuration.example.yaml](../homeassistant/configuration.example.yaml) defines a `tittle_draw` shell command and script that return `ok` or the error text, so an Assist agent or any tool-calling model can use it.
