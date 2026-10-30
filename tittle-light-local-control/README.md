# Tittle Light: local control

Take back control of your **Tittle Light** (the 8 x 8 x 8 RGB LED cube by Spin-R / Clarity HK). If the original app has disappeared from the store, your phone no longer runs it, or the cloud behind it is gone, the cube itself still works: it listens on your local network with no account and no cloud. This repository documents how, and ships a small tool that does everything the app's main screens did, plus things the app never did.

> Not affiliated with, or endorsed by, the makers of the Tittle Light. "Tittle" is their name. This is interoperability work on a device its owner bought, based on the public SDK repositories (<https://github.com/TittleLight>) and on the owner's own network traffic.

## What works (tested on a real cube)

- **Colour / lamp:** any RGB colour and intensity.
- **All 158 built-in items of the app by name:** 7 clocks, 76 emoji (weather, festive, food, expressions, others, 12 constellations), 50 mood-lighting scenes and games, 12 music-visualizer modes. See [docs/ANIMATIONS.md](docs/ANIMATIONS.md).
- **The clock:** selecting a clock also sets the cube's time and date, which it forgets after a power failure.
- **Brightness** of any built-in item.
- **A two-level pick in Home Assistant:** one drop-down for the group (Clock, Emoji: Weather, Mood lighting: Game, My pictures, ...) and one for the item, so 158 items are not one long list (see `homeassistant/configuration.example.yaml`; `tittle.py list` prints the groups).
- **A display you pick by hand is held** until the next daily-plan boundary or an alert, so the plan (which runs every minute) does not undo it. The cube's own timers reset it to a known state when they fire, so the plan's windows mirror them.
- **Your own animations:** the app's "Paint" format is decoded: up to 120 frames of an 8 x 8 x 8 picture with any colours and a frame interval. Pictures are plain JSON files (see `src/pictures/`).
- **A drawing vocabulary for language models** (dots, lines, boxes, spheres, text, scrolling text, spin): see [docs/LLM.md](docs/LLM.md).
- **Alerts:** a small rules file maps "what is wrong" to "what the cube shows" (for example DNS down = the letters D N S then a flashing red and blue beacon; a drive alert = a slowly spinning disk; a person at the door at night = a figure walking up to a door), with the clock as the idle display. An example Home Assistant integration is in [homeassistant/](homeassistant/).

## Quick start

You need Python 3 (standard library only) and the cube's IP address.

```sh
cd src
echo CUBE_IP > tittle.host                 # your cube's address (or set TITTLE_HOST)
python3 tittle.py ping                     # prints "on" when the cube answers
python3 tittle.py 255 0 0 120              # red at intensity 120; "0 0 0 0" = off
python3 tittle.py list                     # every item by name
python3 tittle.py show "Emoji: Weather / Sunny" 200
python3 tittle.py show "Clock / Digital" 255 $(date +'%H %M %S %y %m %d')   # a clock needs the local time
python3 tittle.py paint pictures/alert-beacon.json
python3 tittle.py draw $(echo '{"interval_ms":110,"scroll":{"text":"HELLO","color":"green"}}' | base64 -w0)
```

Reserve the cube's address on your router (it gets its address by DHCP) or update `tittle.host`.

## What is documented

| File | What |
|---|---|
| [docs/PROTOCOL.md](docs/PROTOCOL.md) | Every message we know, the picture upload format in full, the quirks (a flash on every upload, the off-by-one frame, the 0xff rule), and what is still unknown |
| [docs/ANIMATIONS.md](docs/ANIMATIONS.md) | The 158 items with the exact message for each |
| [docs/CAPTURING.md](docs/CAPTURING.md) | How this was worked out, so you can repeat it for the parts still missing (timers) |
| [docs/LLM.md](docs/LLM.md) | The drawing vocabulary and how to give it to a language model as a tool |
| `src/tittle.py` | The tool (one file, standard library only) |
| `src/pictures/`, `tools/` | Example pictures and the scripts that generate them |

## Still missing (help wanted)

The app's **Timer** records are decoded (see section 8 of the protocol document) but the tool does not create timers yet, and a few bytes are unexplained. See "Not known" in the protocol document.

## Licence

MIT for the code and documents in this repository (see `LICENSE`). The SDK repositories this builds on carry no licence of their own; nothing from them is copied here beyond the colour message format they document.
