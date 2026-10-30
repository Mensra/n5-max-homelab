# Tittle Light cube: local network protocol

Reverse-engineered from the network traffic of the original iPad app and from the public Tittle SDK repositories, then confirmed on a real cube by replaying messages while watching it (and, for the picture format, by reproducing the app's own messages byte for byte). Nothing here needs the cloud or the app. Tested on one cube whose status reply was `60 02 0a 00 01 07 'Cube'` (firmware/version bytes `0a 00 01 07`).

What is solid and what is not is marked in every section. If you find something that differs on your cube, please open an issue.

## 1. Transport

- **Control port: TCP 9999 on the cube.** No authentication, no encryption. Every message ends `0D 0A`. The cube answers each message with a short reply (section 3).
- The app also sends the same frames as a **UDP broadcast** from its port 12345 to the LAN broadcast address, port **11005**, in parallel with the TCP connection. The cube obeys either; TCP gives you the reply.
- **Discovery beacon:** the cube broadcasts a 19-byte UDP datagram from its port 10000 to the broadcast address port 12345 about every 11 seconds: `70 04 'Cube' 00 <MAC 6 bytes> <IP 4 bytes> 0D 0A`. The SDK scans by broadcasting `70 04 <your IP 4 bytes> 0D 0A` to port 10000; the cube then connects back to your TCP 9999 and sends the same record.
- Wi-Fi provisioning (SDK, not tested here): the cube's own access point `Tittle-AP`, packet `70 07 <ssid> 00 <password> 00 <handset IP 4 bytes> 0D 0A`, stop with `70 09 0D 0A`.

Security note: anyone on your LAN can drive the cube. Keep it off networks you do not trust.

## 2. Messages (all hex, all end `0D 0A`)

| Purpose | Frame | Notes |
|---|---|---|
| Colour (the "lamp") | `10 RR GG BB II` | II = intensity 0-255, 0 = off. From the SDK; confirmed. |
| Status poll | `60 10 00` | Reply `60 02 0a 00 01 07 'Cube' 00 ...` (29 bytes). |
| Unknown poll | `70 05 00` | Reply `70 05 10 ff ff ff ff ff ff ff ff ff`. Meaning unknown. |
| Clock | `34 HH MM SS 00 00 <id 2B> ff <var 1B> YY MM DD 4c 9c 00 01 00` | 20 bytes. Sets the time (bytes 1-3) and date (bytes 10-12, year as two digits) and starts one of seven clock styles. **Selecting a clock is the only way to set the cube's clock** (it forgets it after a power failure). Bytes 13-17 are copied from a capture; their meaning is unknown and replaying them works. |
| Built-in emoji | `20 00 01 f4 00 00 <id 2B> <type 1B> ff 00 00 00 00 00 00` | 18 bytes. Select an animation by id. |
| Mood lighting | `50 00 01 f4 00 00 <id 2B> <type 1B> ff 00 00 00 00 00 00` | Same shape as emoji, type byte 50. |
| Music visualizer | `41 00 00 <id 2B> ff 64 <type 1B> 00 00 00 00 00` | 15 bytes. The cube listens with its own microphone; the app sends nothing more after the selection. |
| Constellation emoji | `20 00 <size 2B> 00 00 00 <id 1B> <x 1B> ff 00..` | These are drawn pictures; the app uploads their frames (section 5) when you tap them. Once uploaded the cube keeps them, and selecting again by this message works. |

The 158 items of the original app (clock, emoji, mood lighting, visualizer), with the exact message for each, are in [ANIMATIONS.md](ANIMATIONS.md). Ids are **not** derivable: within a list they count down in list order in groups with jumps between groups, so a table captured from the app is the only reliable source.

### Brightness
The app's brightness slider re-sends the current item's message with one byte changed: the byte that is `ff` in every captured message (full brightness). Its position depends on the type: **index 9** for types `20` and `50`, **index 8** for `34`, **index 5** for `41`. Values 0-255 are linear (a drag from low to high sent 00, 36, 57, 84, b1, dd, ff).

## 3. Replies
`00 00 <type> 00 0D 0A` means accepted (type = the type of the message you sent). Uploads: the cube answers a picture header with `00 00 90 01 01 0D 0A` (accepted, send the data) or `00 00 90 00 0D 0A` (refused: it already holds that picture, or it is busy), and each data block with `00 <index> 25 00 0D 0A`.

## 4. Orientation of the cube
Seen from the front: **layer 1 is the front, layer 8 the rear; row 1 is the top, row 8 the bottom; column 1 is the left, column 8 the right.** (Confirmed by video: a sweep of one dot at row 1, column 1 over layers 1-8 started at the front top-left corner and ran to the rear along the left side; four corner dots appeared where expected.)

## 5. Custom pictures ("Paint"): upload format
The app lets you draw a multi-frame animation and press "Preview on tittle". This is what it sends (TCP 9999 or the UDP broadcast).

**Header, 18 bytes:** `90 00 <frames> <interval> 00 00 <id 2B> <counter> ff 00 00 00 00 00 00 0D 0A`
- `<interval>` = the frame interval in **8 ms steps** (500, 999 and 1500 ms gave `3e`, `7c`, `bb`; 0 means the default).
- `<id>`: the id of the app's editing slot (a new emoji gets a new id, 0x21 higher each time; any value worked for our own uploads).
- `<counter>`: changes with every upload. **If the cube already holds the same id and counter it answers `00 00 90 00` and ignores the upload**, so use a fresh counter each time (we use the low byte of the clock).
- `<frames>`: **announce one frame fewer than you send** (section 7).

**Data blocks:** `25 00 <nblocks> 00 <index> <length 2B> <payload> <checksum> 0D 0A`, payload at most 512 bytes, `<checksum>` = sum of the payload bytes modulo 256 (verified on 40+ real blocks). The cube acknowledges each block before you send the next.
- **Pack whole frames into each block**; a new block when the next frame does not fit (a frame longer than 512 bytes is split). A frame split across two blocks made the cube flash white and play blank frames at the end of every turn.

**Frames:** the payload is the frames one after another. Each frame is its own compressed stream of **1536 bytes = 512 cells x 3 bytes RGB**, cell order = layer (front to rear) then row (top to bottom) then column (left to right), cell index = (layer-1)*64 + (row-1)*8 + (column-1).
- The frame starts with an **escape byte E**: the smallest byte value from 1 up that does not occur in the frame's colour bytes (frame 1 containing a `01` uses `02`, otherwise `01`).
- Colour bytes are copied literally. A run of zero bytes (empty LEDs) of length n >= 4 is written `E <n-1> 00`; when n-1 >= 128 it is `E <0x80 | (n-1)>>8> <(n-1) & 255> 00` (e.g. 168 zeros = `E 80 a7 00`, 1365 zeros = `E 85 54 00`). Shorter zero runs are written out literally.
- The frame ends with `ff ff ff ff`.
- **Never use 0xff in a colour byte** (cap at 254): four `ff` in a row end a frame, and two white dots side by side write six of them. A disk with a white hub flashed until this was fixed.

Verified by reproducing the app's own messages byte for byte for single dots at five positions, two-frame pictures, three intervals, and by round-tripping a 21-dot, 3-frame emoji from the app.

## 6. Behaviour you should know
- **The cube flashes every time a picture is uploaded.** Built-in items (selected by message, no upload) do not flash. Do not redraw custom pictures more often than every few seconds.
- The cube keeps **one** custom picture in memory (the app's "editing slot"). Our attempts to store several pictures under different ids and call them back by id with a header-only message were refused (`00 00 90 00`), so each custom picture is uploaded when it is wanted.
- Some of the app's animations are uploaded to the cube as program blocks (`24 00 ...`, 522 bytes each, ARM code) the first time they are used; after that, selecting them by message works. This repository does not include or document those blocks.
- The cube has **no read-back**: you cannot ask what it is showing. Remember what you last sent.
- One incident: after several large uploads in quick succession the cube kept answering ping but stopped answering on TCP 9999 until it was power-cycled. Space your uploads.

## 7. The off-by-one
The cube plays **one frame more than the frame count in the header** and shows junk from its memory for that extra frame (a speckle at the end of every turn). Announcing one fewer frame than you send removes it and the animation loops cleanly. (A one-frame picture should be sent as two identical frames announced as 1.) The original app announces the true count; why its pictures do not show junk is not known.

## 8. Timers (the app's "Timer" screen)
The cube **runs its timers on board** (confirmed by the owner: they fire with the app closed). The app pushes each timer to the cube as one record, sent as a **UDP broadcast** (port 11005) about twice, two seconds apart; no reply was seen and the app lists timers from its own storage. Every timer message also carries the **current time** (which is another way the cube's clock gets set).

```
80 00 00 <X> <id> | <now: yy mm dd hh mm ss> | <start: mm dd hh mm> | <active> <kind> <repeat> | <item> | <end: mm dd hh mm> | d7 6f 6f | 01 00 | 0D 0A
```
- `<id>`: one byte that belongs to the timer (resending it edits that timer; new timers count up). `<X>`: 0x14 on timers created recently, 0x08 and 0x09 on timers from 2020; its meaning is not understood.
- `<start>`/`<end>`: month, day, hour, minute only: a daily timer keeps its creation date. A timer with no end time showed 23:59 as the default end.
- `<active>`: 01 = on, **00 = deleted**. To delete a timer, resend its record with this byte 0.
- `<kind>`: 01 lamp, 02 play a mood or emoji item, 04 clock, 00 switch off (the cube blanks its display).
- `<repeat>`: a weekday mask; **7f = every day, 00 = once**. (Only these two values were tested; one bit per weekday is the obvious reading.)
- `<item>` for kinds 02 and 04: bytes 1-8 of that item's select message from [ANIMATIONS.md](ANIMATIONS.md) (`00 01 f4 00 00 <id 2B> <type>`) followed by the brightness byte. Lifting clock: `00 01 f4 00 00 15 0e 06 be`; Spin & Twist: `00 01 f4 00 00 17 80 04 ab`. For the lamp (kind 01) the item was `00` + RGB + `7f`.
- Observed: Lifting clock 08:30-20:00 daily; Spin & Twist 20:30-22:30 daily; a lamp timer 18:00-18:20; a Snake timer from 19:09 to 23:59.

A **Switch off** timer has no item and no end time: `<start> <active> 00 <repeat> 01 00` (created as `... 0a 1e 15 00 01 00 7f 01 00`, deleted by the same record with active 00). New timers get sequential ids (`fb`, `fc`, `fd`, `fe` in our captures).

Not known: the meaning of `d7 6f 6f` and the trailing `01 00` of the longer records; weekday bit order; whether the cube replies.

## 9. Not known / not done
- The meaning of clock bytes 13-17 and the third byte of the type field of emoji/mood messages (values 04-08 seen).
- How the music visualizer hears (the cube's own microphone according to its owner; nothing was measured).
- The Wi-Fi provisioning packets were taken from the SDK, not tested.
- The timer details listed above.

## 10. Method
See [CAPTURING.md](CAPTURING.md). In short: record the app's traffic at the router while tapping every item of a list once, in order, then match messages to items by position.
