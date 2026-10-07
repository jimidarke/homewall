# Roku wall 0.12: 6×4 grid, 48 h temperature chart, live front PTZ camera

Date: 2026-10-07. Roku channel 0.12.0, sidecar `layouts.roku`, `weather_chart` card, go2rtc `front`. Builds on `2026-10-07-roku-glass-design.md` (0.11). Plan: `../plans/2026-10-07-roku-wall-6x4.md`.

## Why

On the 0.11 wall, things look stretched vertically, and Calendar is squeezed horizontally.
- The 6×3 grid's cells are 286×292, about square. The tablet's cards are landscape: 242×171 dp, about 1.4:1.
- Calendar is a 286×604 sliver. Activity is 1×3.

The user asked for:
- a 6×4 grid;
- Calendar and Activity at 2×2 each, stacked;
- Doors at 2×1;
- Activity at one line per row;
- the tablet's 48 h outdoor temperature line chart in the Forecast card;
- the front PTZ camera playing live in the camera square, which in 0.11 was an empty placeholder.

## Layout

The grid is `{cols 6, rows 4, cellW 289, cellH 220, originX 52, originY 116, gap 16}`:
- It ends at x 1866 and y 1044. The clock's bottom edge is at y 106.
- Cells are about 1.3:1, close to the tablet's shape.

```
      c0         c1       c2   c3        c4   c5
r0   [ Doors (2×1)  ]    [ Calendar ]   [ Front    ]
r1   Laundry    Water    [          ]   [ (live)   ]
r2   Energy     Gas      [ Activity ]   [ Forecast ]
r3   Weather    Thermo   [          ]   [ 3-day +  ]
                                        [ 48 h     ]
```

**Card chrome.** The card chrome shrinks to body top 84 and bottom padding 12 (it was 88 and 16), which gives the body:

| Tile | Body |
|---|---|
| 1×1 | 249×124 |
| 2×1 | 554×124 |
| 2×2 | 554×360 |

**Bodies at the shorter height:**
- **Value cards** use compact slots (hero 64, sub 32, detail 28). At 0.11's slot sizes, the hero would run into the title row.
- **Doors** goes 2×1, two doors side by side. Two stacked door rows need 136 px.
- **Laundry** stays 1×1, with two compact machines in 108 px. The tile count rules out 2×1: 25 cells won't fit in 24.
- **Activity** rows become one line of 40 px: glyph, title, muted sub, and the time right-aligned. That's about 9 rows in a 2×2. **Calendar** fits about 10.

**Config.** Each `layouts.roku` entry now carries its own `tile`. The ref merge is shallow, so the Roku's tiles no longer follow tablet moves. That was accepted, because the tablet's 1×3 Activity doesn't fit a 6×4 wall.

## The forecast chart

The Forecast card is 2×2:
- the 3-day strip on top (140 px);
- below it, the outdoor temperature chart from the tablet's weather panel: 24 h observed plus 24 h forecast, joined at "Now".

**Where it's drawn.** SceneGraph can't draw lines, so the sidecar draws the chart as an image (`GET /api/card/weather_chart.png?layout=roku&w=&h=`).
- It is transparent, with Barlow type, observed in ink and the forecast in cool blue.
- It uses the same `_chart_block` data as the tablet panel, with the same HA reads, so the statistics and forecast caches are shared.
- Card renders now get the configured timezone. Without it, nserver, which runs on UTC, would label the hours wrong.

**Fetching.** The card path lives in `tile.card`, because the channel's slimmed registry cache drops `drill`. The channel refetches every 5 minutes, flipping between two images only once the new one has loaded, so the chart never blanks. The sidecar re-renders only when the data changes.

**Compatibility.** The sidecar's JSON doesn't change, so the default view's golden output and the tablet are unaffected.

## The camera square

**Which camera.** HA's front PTZ camera is a Genbolt dual-lens camera at `192.0.2.31`.
- Its PTZ lens is RTSP `/21`, HEVC 1920×1080 at 15 fps. It is WAN-blocked, and HA reaches it with its own credentials.
- HAku's `front` stream still pointed at an Amcrest at `.35`, which is gone ("no route to host"). That's why `front` answered 404.
- Backyard (`.34`) is offline, and the NVR can't reach it either. Its fix is out of scope.

**The stream.** go2rtc's `front` now re-encodes `/21` to H.264 at 1280×720 with QSV:
- 2 s GOP, to match the HLS segments; no audio.
- It has its own `HAKU_FRONT_USER`/`HAKU_FRONT_PASSWORD` in `/etc/haku/cam-creds.env`.
- It re-encodes because the Rokus need H.264: the Express and the Stick can't decode HEVC.
- 720p rather than the 640×360 substream, because the same stream also feeds the full-screen takeover.
- The discovery metadata changes values only (Genbolt, h264, 1280x720, no audio), so there's no schema bump.

**On the Roku.** A new `CameraBody` plays the stream muted in the square, fitted to 16:9 (554×312), under the card's rim.

**Decoder ownership.** Roku has one H.264 decoder:
- On home with a camera, the square owns it, and the hidden keep-awake clip stays stopped. Live playback keeps the screensaver away.
- Every other route (live, grid, module, diag) stops the square before it plays anything.
- `goHome` hands the decoder back.

**Failure handling:**
- Errors back off on the live view's 2/5/10/30 s schedule.
- After 4 errors, the card says "Camera offline" and rests for 5 minutes. During the rest, the same Video node plays the keep-awake clip invisibly: there's still one decoder, and no screensaver.
- A 90 s stall watchdog restarts playback.

**What the square doesn't do.** It's read-only and only shows where the lens points. Moving the lens stays in HA (`script.front_cam_ptz_nudge`).

## Not changed

- Camera takeovers, the overlays, diag and the smoke test's flows.
- The tablet's layout and JSON.
- The default view's output.
- Background photos, which are still the 0.11 follow-up.

## Rollout

1. **Stream:** `front` → Genbolt.
2. **Sidecar:** the chart card. The live config is untouched for now.
3. **Dev Roku `.55`,** against a local sidecar serving the new layout.
4. **The live `layouts.roku`,** then the fleet straight after: 0.11's bodies overlap at 6×4. The Express (`.52`) goes first, to watch memory with video playing.
