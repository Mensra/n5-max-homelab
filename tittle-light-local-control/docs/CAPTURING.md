# How this was worked out (and how to extend it)

The goal: see exactly what the original app sends, while tapping every item once, and match messages to items by order. This is the method that worked, including the dead ends, so you can capture the part that is still missing (the Timer screen).

## What you need
- The original app on a phone or tablet that still runs it, and the cube on the same Wi-Fi.
- A place where the app's traffic to the cube is visible. What worked: **a tcpdump on the router** (any router you can run tcpdump on). It only sees the traffic if the phone and the cube are on **different** access points / the traffic crosses the router; frames between two clients on the same access point may never leave the radio.
- Python 3 for `tools/decode_capture.py`.

## What did not work
- **Capturing on a Mac through `rvictl`** (an iPhone/iPad "remote virtual interface"): it worked once, then stopped (`rvictl -l` listed no device although the iPad showed in Finder, and restarting the helper service is blocked by System Integrity Protection). Do not depend on it.
- **Filtering only `tcp port 9999` to the cube:** the app sends its control messages as **UDP broadcasts to port 11005** as well, and in some sessions *only* that. Our first captures with the TCP filter saw nothing. Use `udp port 11005 or (host <cube> and tcp port 9999)`, or simply `host <phone> or host <cube>` and look at what is there.
- A router that accelerates forwarding in hardware shows you nothing until the acceleration is switched off for the capture (and switched on again afterwards).

## The method
1. Start the capture. Wait a few seconds.
2. In the app, open one list (for example Emoji > Weather) and tap **every item once, top to bottom, left to right, about four seconds apart**. Do not skip or repeat.
3. Stop the capture, run `python3 tools/decode_capture.py capture.pcap`: one line per message the app sent (time, size, hex).
4. The select messages come out in the order you tapped. Match them to the items by position. The count must equal the number of items; if it does not, repeat the round (a stray tap shifts everything).
5. One category per recording keeps the matching trivial. This gave the 158 items in `docs/ANIMATIONS.md` in eleven short rounds.

## For pictures (Paint)
Change **one thing at a time** and capture each: an empty frame sent nothing; one dot at position 1, 2, 9, 17, 57 gave the cell-index rule; the same dot in a second frame showed how frames chain; a different interval showed where the interval lives (and that you have to edit and re-preview to send it). Check every theory by **reproducing the app's message byte for byte** with your own encoder: that is how the zero-run rule, the escape byte and the checksum were confirmed.

## For the Timer screen (done; method)
Record one action at a time: add a timer with values you write down (item, start, end, repeat), then delete it, then re-save an existing one unchanged, and decode as above (`tools/decode_capture.py` prints UDP broadcasts to port 11005 as well as TCP). The messages are type `80`. Comparing a save with a delete (one byte differs) and two saves (one field differs) identified each field. The cube stores and runs the timers itself.

## Safety while experimenting
Replay captured messages one at a time with the cube in view. Do not send unknown message types blind (the SDK documents a Wi-Fi provisioning packet that could change settings). Space large uploads out: one rapid burst made a cube stop answering on its control port until it was power-cycled.
