# HAku — How It Works & How It Looks

> Sideloaded Roku channel. A wall of cameras you steer with the remote, that dives to the right one when something happens, that fades to a glance dashboard when you walk away, and that wakes up to a morning briefing if you flick the TV on before coffee.

---

## North star

**HAku is the TV-shaped client for the home.** Most of the time it is a fullscreen camera feed with whisper-quiet chrome. When the home has something to say — a door opens, a doorbell rings, a kid leaves a window open at 11 pm — HAku reacts: it cuts to the relevant camera with a 15-second pre-roll so you see *what just happened*, or it shoulders a small picture-in-picture in the corner so it doesn't yank you out of what you were watching. When nothing is happening it dims to a glance dashboard. When the morning starts it stands up a 60-second briefing and gets out of the way.

It's a Roku channel because Rokus are the box that's already in every room. Home Assistant is the brain; HAku is just one of its faces.

> **Paths in this document (checked 2026-10-03).** It was written in the `roku-homewall` repo; paths have been updated to the `homewall` monorepo layout (`roku/`, `sidecar/`, `stream/`, `fire-tablet/`, `docs/`). References to `~/code/homeController/...` are historical: that checkout no longer exists. The live HA config is on mserver at `/root/docker/homeassistantV3/config/ha/` (HA runs in Docker), with HAku-related packages `electricity_cost.yaml`, `gas_cost.yaml`, `water_cost.yaml` and `haku_water.yaml`, and HAku references in `configuration.yaml`; there is no `packages/haku.yaml` or `rest_commands.yaml` there. The status notes below are dated snapshots; the current state of each client is in its own folder's README/CLAUDE.md.

> **Status (2026-05-08, late evening).** v0.1–v0.5 **+ Phase 2 per-cam streams** shipped and running on 4 Rokus in the house: living room (192.0.2.51, Stick+), kids (192.0.2.52, Express), master bedroom (192.0.2.53, Stick), den (192.0.2.54, Express 4K). Channel source lives in `roku/`, server pipeline in `stream/`. Time-to-first-frame across the fleet 0.4–1.7 s; a 45-min soak saw zero stream errors / reconnects / watchdog kicks / BrightScript traces. Phase 2 deployed: `go2rtc.yaml` now publishes `front` / `yard` / `side` / `backyard` direct from the cameras (creds via `/etc/haku/cam-creds.env` referenced as `${HAKU_CAM_PASSWORD}` in yaml — never committed); `haku-hls@.service` template gives each cam its own deep-12s HLS sidecar. Reolink @ .32 main is HEVC 4K so we use its H.264 sub-stream for Roku compat. Roku focus bug found + fixed in MainScene (D-pad now reaches LiveGroup). Carousel verified end-to-end: a single `/launch/dev` cold-relaunch on the Stick+ rotated through all 4 cams, fetching `front.m3u8`, `yard.m3u8`, `side.m3u8`, `backyard.m3u8` server-side.

---

## Concrete inventory (this is what's actually on the LAN)

Pulled fresh from `~/code/homeController/infra/network/inventory.yaml` and `home-assistant/config/`. Replace any placeholder I had earlier with these — they're real.

**Network**: `192.0.2.0/24`, gateway `192.0.2.1`, domain `home.lan`.

**Cameras (RTSP IPs — go direct, bypass NVR HDMI-capture path)**:

Validated 2026-05-08 against Mikrotik DHCP leases + TCP-port probe:

| Friendly | LAN IP | MAC | Vendor | Open ports | RTSP URL convention |
|---|---|---|---|---|---|
| frontcam   | `192.0.2.35`  | `xx:xx:xx:xx:xx:xx` | **Amcrest** (`<serial>`) | 80, 554, 37777 | `rtsp://USER:PW@192.0.2.35:554/cam/realmonitor?channel=1&subtype=0` (main) / `subtype=1` (sub) |
| yardcam    | `192.0.2.32` | `xx:xx:xx:xx:xx:xx` | **Reolink** (host-name `Back` — *labelled "yard" but DHCP host-name "Back", confirm physical placement*) | 80, 554, 8000 | `rtsp://USER:PW@192.0.2.32:554/h264Preview_01_main` (or `_sub`) |
| sidecam    | `192.0.2.33` | `xx:xx:xx:xx:xx:xx` | **Amcrest** (`<serial>`) | 80, 554, 37777 | `rtsp://USER:PW@192.0.2.33:554/cam/realmonitor?channel=1&subtype=0` |
| backyardcam| `192.0.2.34` | `xx:xx:xx:xx:xx:xx` | **Reolink-family IPC** | 80, 443, 554, 8000 | `rtsp://USER:PW@192.0.2.34:554/h264Preview_01_main` |

**NVR (16-channel)**: `192.0.2.30` `NVR-16` (OUI `xx:xx:xx`, Lorex/Dahua family) — ports 80, 554 open. All four cams are also reachable via the NVR's own RTSP at `rtsp://USER:PW@192.0.2.30:554/cam/realmonitor?channel={1..4}&subtype=0` if the per-cam path turns out to be flaky on a given firmware.

**Other cameras seen in DHCP**:
- `192.0.2.31` `IPCAM` (Genbolt, MAC `xx:xx:xx:xx:xx:xx`) — currently `waiting`/offline; ignore for v1.0.

**Camera pipeline on nserver (deployed 2026-05-08, source-of-truth in `stream/`)**:
- NVR HDMI-out → USB3.0 capture card on `/dev/v4l/by-id/usb-MACROSILICON_USB3.0_Video_67807015-video-index0` on nserver (Macrosilicon `345f:2131`, USB 3.0 SuperSpeed).
- `go2rtc.service` runs go2rtc 1.9.14 as the `media` user. ffmpeg invocation pulls 1920×1080 MJPEG @ 20 fps from the capture device, encodes via Intel Quick Sync (`h264_qsv`, Iris Plus G1) at H.264 Main L4.0 / `yuv420p` / GOP=40 (= 2 s) / no B-frames / 2.5 Mbps CBR.
- `haku-hls.service` is an `ffmpeg -c copy` sidecar that re-muxes the RTSP into a 6×2 s = **12 s** rolling HLS in `/run/haku-hls/` (tmpfs). Addresses go2rtc's known shallow-HLS underflow ([AlexxIT/go2rtc#1699](https://github.com/AlexxIT/go2rtc/issues/1699)) — Roku consumes this, not the built-in HLS.
- `haku-discovery.service` (Python, stdlib-only) runs an SSDP responder on UDP `239.255.255.250:1900` with ST=`urn:haku:service:cams:1`, plus an HTTP server on `192.0.2.20:1985` that serves both the capability JSON and the deep-HLS files.
- All endpoints below served on `enp1s0` IP `192.0.2.20`:

| Endpoint | URL | Use |
|---|---|---|
| SSDP discovery | multicast `239.255.255.250:1900` ST=`urn:haku:service:cams:1` | Roku auto-discovers — no hard-coded IP |
| Capability JSON | `http://192.0.2.20:1985/discovery.json` | Versioned payload, points to live RTSP/HLS/MJPEG/snapshot URLs |
| **Roku channel uses** | `http://192.0.2.20:1985/hls/mosaic.m3u8` | Deep 12 s HLS, Roku's hardware H.264 decode path |
| HLS shallow | `http://192.0.2.20:1984/api/stream.m3u8?src=mosaic` | Browsers, debugging — go2rtc native (~1 s buffer) |
| RTSP | `rtsp://192.0.2.20:8554/mosaic` | HA `Stream` integration, VLC, ffmpeg |
| MJPEG | `http://192.0.2.20:1984/api/stream.mjpeg?src=mosaic` | HA `mjpeg:` legacy compat (drop-in for old camera entity) |
| WebRTC preview | `http://192.0.2.20:1984/stream.html?src=mosaic` | Sub-second-latency in-browser viewing |
| **PIP snapshot** | `http://192.0.2.20:1984/api/frame.jpeg?src=mosaic` | HAku PIP fetches this every 500 ms (~196 KB JPEG) |
| Status UI | `http://192.0.2.20:1984/` | Live consumers, bandwidth |

- One Reolink is also directly integrated in HA already (`camera.back_yard_fluent`) — proves direct RTSP / Reolink-API integration works on this LAN. The HA-named "Back Yard Fluent" actually points at `yardcam` (192.0.2.32 host-name `Back`); rename in HA when convenient.
- **Bandwidth per consumer**: ~2.56 Mbps (was 78.7 Mbps under the old MJPEG passthrough — 30× reduction). Encoder load: ~1–2% iGPU.
- **Legacy `sendHDMI.service` / mjpg_streamer at `:8090`** is **stopped + disabled**. Unit file kept on disk for one-line rollback (`systemctl enable --now sendHDMI`).
- Today's pipeline ships the `mosaic` stream only. Phase 2 appends the four direct-cam streams to `go2rtc.yaml` once cam credentials are confirmed and the `yardcam` ↔ `Back` labelling is sorted (see followup checklist).

**Roku fleet (documented)** — *only two Rokus are currently catalogued in inventory*:
| Friendly | LAN IP | Model | Notes |
|---|---|---|---|
| dev-roku | `192.0.2.55` | — | **Primary dev box**, sits with the user in the office (not part of the wall-mounted fleet). Dev mode unlocked, installer password `$ROKU_PW_FLEET` (fleet-wide), digest auth verified 2026-07-04. |
| kids-roku | `192.0.2.52` | Roku Express | USB-powered by bedroom TV; reachability = TV-power state proxy in `packages/kids_tv.yaml` |

The user has stated they own ~6 Rokus around the house. Four of them are not in `inventory.yaml` yet — **before final HA `rest_command` wiring, capture each Roku's IP, room, and model into the inventory.** Quick way: `for ip in $(seq 50 254); do timeout 1 curl -s http://192.0.2.$ip:8060/query/device-info >/dev/null 2>&1 && echo $ip; done` then `gh api`-style `curl /query/device-info` per hit.

**HA entities we'll bind to** (validated 2026-05-08 against `http://192.0.2.10:8123/api/states`):
- Weather: `weather.edmonton_forecast`
- Calendar: `calendar.family`
- Energy: `sensor.emporia_total_power`, `sensor.emporia_total_daily_energy_kwh`, `sensor.electricity_daily_cost` (or `sensor.emporia_total_daily_energy_kwh_cost`)
- Door contacts (live): `binary_sensor.front_doorcontact_contact`, `back_doorcontact_contact`, `bathroom_door_contact`
- Motion (live): `binary_sensor.front_motion_occupancy`, `backyard_motion_occupancy`, `back_yard_motion` (separate sensor — fold in as redundant outdoor trigger), `staircase_motion_occupancy`, `shed_motion_occupancy`, `my_ecobee_occupancy` (hallway)
- Presence: `sensor.jimi_phone_room` (currently `den`), `sensor.jimi_wallet_room` (currently `office`); `person.jimi`, `person.alex`; `sensor.jimi_phone_geocoded_location` for nicer labels
- Water: `sensor.water_meter_total`, `sensor.water_meter_flow`

**Stale / unavailable on 2026-05-08 — followup before v0.1 sideload** (entities probably exist in some form but are offline; battery, signal, or sensor renamed — re-validate, don't just delete):
- `binary_sensor.garage_doorcontact_contact` — unavailable; battery or radio drop suspected
- `binary_sensor.gate_doorcontact_contact` — unavailable; same
- `binary_sensor.backyard_corner_motion_occupancy` — unavailable; secondary backyard sensor
- ESPresense rooms offline: `front_door, kitchen, laundry, living_room, bedroom_2` (only `den, office` reporting). Active-Roku selector will need most rooms back online before follow-me works.

**Coverage gap** — there's no `binary_sensor.yard_motion` or `binary_sensor.side_motion`; outdoor motion is only `front` and `backyard` (+ corner). So the v0.1–v1.0 event-driven jump table can route door contacts and motion to *appropriate* cams (table below) rather than 1:1 cam-per-sensor.

---

## The four modes

HAku has exactly four user-visible modes. Everything else is an overlay or a transient state.

```
                        ┌──────────────────────────────┐
                        │    L I V E   (default)       │
                        │  one camera, fullscreen,     │
                        │  lower-third HUD             │
                        └──────────────────────────────┘
                          ↕ ↕ ↕                  ↕
       (◀ ▶ pages cams)   |  |   (long-press OK)  |  (no input 5 min)
                          |  |                    |
                          |  |                    ↓
                          |  |        ┌─────────────────────┐
                          |  |        │   G L A N C E       │
                          |  |        │   (screensaver)     │
                          |  |        └─────────────────────┘
                          |  |
                  (cold-launch ?mode=briefing or 06:00 wake automation)
                          |  |
                          ↓  ↓
        ┌──────────────────────┐    ┌──────────────────────┐
        │   B R I E F I N G    │    │     G R I D          │
        │   60-sec today view  │    │   2×2 mosaic stream  │
        └──────────────────────┘    └──────────────────────┘
```

Plus three overlays that float above any mode:
- **PIP** — small corner cam window, auto-dismisses
- **Toast** — 3-sec text strip near the top
- **Reconnect curtain** — full-screen scrim during stream errors

---

## Visual style

**Daylight palette.** Family-friendly, easy on the eyes, generally light. Warm rather than clinical (no cool greys). All text inside the title-safe rectangle. Hex format `0xRRGGBBAA` for SceneGraph; the table below shows `#RRGGBB` for human reading — convert to 8-digit at codegen time.

| Token | Hex | Use |
|---|---|---|
| `bg.cream` | `#F7F1E3` | BRIEFING / GLANCE field; Toast bg on dark; manifest `splash_color` |
| `bg.warm` | `#ECE3D0` | Card backgrounds inside BRIEFING / GLANCE |
| `bg.scrim` | `#2B2A26CC` | HUD scrim over live video (warm dark, 80% alpha — legible over any frame) |
| `text.ink` | `#2B2A26` | Primary text on light backgrounds (warm near-black) |
| `text.cream` | `#FAF6EE` | Text on `bg.scrim` (HUD, reconnect overlay) |
| `text.muted` | `#2B2A2699` | Secondary metadata on light backgrounds |
| `accent.brand` | `#5B8C7F` | Wordmark, focus rings, dot pager active dot, progress bar fill |
| `accent.live` | `#D4673E` | LIVE pip, high-severity events, replay indicator (warm coral, not fire-engine red) |
| `accent.warn` | `#D9A441` | Doorbell, PIP border, attention-required (warm amber) |
| `accent.ok` | `#6B9080` | Connected dot, "all clear" motion indicator (sage green, distinct from brand) |

**Why this works over video**: the only chrome that floats over live video is the lower-third HUD and the `[LIVE]` pip. Both sit on `bg.scrim` (warm dark 80% alpha) so legibility is unaffected by the palette shift. Every other surface (BRIEFING, GLANCE, Reconnect curtain, splash) is opaque, so the light palette shows through cleanly.

**Splash + manifest** — `splash_color=#F7F1E3` (cream), splash image is the HAku wordmark logo letterboxed into cream. The brand mark (transparent PNG, `docs/brand/logo_wordmark.png`) is reused on the in-channel reconnect overlay and the default background-rotation card; a separate 4:3 icon-only crop (`docs/brand/logo_icon.png`) drives the app icon tiles. All shipped image variants are emitted from source artwork by `roku/scripts/generate_brand_assets.py` — that script is the single source of truth for icon / splash / wordmark dimensions.

**Typography**: built-in `MediumBoldSystemFont` for all chrome (no custom TTF — keeps cold-start fast and matches Roku 10-ft UI conventions). Body text on light surfaces uses `text.ink`; on `bg.scrim` uses `text.cream`. Metadata in `SmallSystemFont` at 24 pt. Hero numerals in `LargestSystemFont`. All text inside the **title-safe rectangle**: `1534×866` centred at offset `(192, 106)` on a 1920×1080 canvas.

**Animation budget** — every transition under 250 ms or it feels broken on a 60 Hz panel:
- Fade-in / fade-out: **200 ms**
- HUD slide-in (lower-third): **180 ms** ease-out
- Camera swap crossfade: **220 ms**
- PIP appear / dismiss: **200 ms** scale + fade
- Toast slide-from-top: **180 ms** in, **150 ms** out

**Focus rings**: 4 px outline in `accent.brand` `#5B8C7F`, glow `0 0 12 #5B8C7F40`. Brand sage carries the eye on either dark or light surface.

---

## Cameras (real roster from `inventory.yaml`)

| ID | Friendly | Vendor | RTSP source (validated) | HLS at (phase 2 once added to go2rtc.yaml) | Maps to event sources |
|---|---|---|---|---|---|
| `front`    | Front Door | Amcrest | `rtsp://USER:PW@192.0.2.35:554/cam/realmonitor?channel=1&subtype=0`  | `:1985/hls/front.m3u8`    | `front_doorcontact_contact`, `front_motion_occupancy` |
| `yard`     | Yard       | Reolink | `rtsp://USER:PW@192.0.2.32:554/h264Preview_01_main`                | `:1985/hls/yard.m3u8`     | *gate_doorcontact currently unavailable — motion-only until restored* |
| `side`     | Side       | Amcrest | `rtsp://USER:PW@192.0.2.33:554/cam/realmonitor?channel=1&subtype=0` | `:1985/hls/side.m3u8`     | *garage_doorcontact currently unavailable — motion-only until restored* |
| `backyard` | Backyard   | Reolink | `rtsp://USER:PW@192.0.2.34:554/h264Preview_01_main`                | `:1985/hls/backyard.m3u8` | `back_doorcontact_contact`, `backyard_motion_occupancy`, `back_yard_motion` (corner sensor offline) |
| `mosaic`   | NVR 4-up   | (server) | NVR HDMI-out via USB capture → go2rtc QSV encode | **`:1985/hls/mosaic.m3u8` — DEPLOYED** | (rendered, not a physical cam) |

Two vendors, two URL conventions: **Amcrest** (front, side) uses Dahua-style `cam/realmonitor?channel=N&subtype=0`; **Reolink** (yard, backyard) uses `h264Preview_01_main`. Both confirmed responding on port 554. Use `_sub` / `subtype=1` for the lower-res substream when ingesting into the mosaic — saves CPU on `nserver`'s ffmpeg `xstack`. **Fallback**: if a per-cam path proves flaky on a given firmware, the same feed is reachable via the NVR at `rtsp://USER:PW@192.0.2.30:554/cam/realmonitor?channel={1..4}&subtype=0`. Credentials: pull from existing NVR config / secrets vault (do **not** hard-code).
| `mosaic` | Grid view | composed via ffmpeg `xstack` | `:1985/hls/mosaic.m3u8` | `streams.mosaic` |

Order in the carousel: `front → yard → side → backyard` (front of house first, walking the perimeter clockwise — matches how the user thinks about the property).

---

## Mode 1 — LIVE (default)

Fullscreen single-camera HLS feed. The **whole** screen is video; HUD floats over it.

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│                                                                      │
│                                                                      │
│                          ┌─────┐                                     │
│                          │     │ ◀─ [LIVE] pip (top-left, 24px)      │
│                          │  ●  │      blinks 1Hz                     │
│                          └─────┘                                     │
│                                                                      │
│                            (raw camera feed fills frame)             │
│                                                                      │
│                                                                      │
│                                                                      │
│                                                                      │
│                                                                      │
│                                                                      │
│   ┌─ FRONT DOOR ──────────────────────────────  motion 2 min ago ─┐ │
│   │ ◀  ●○○○        ▶                            connected · 0.9s  │ │
│   └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Lower-third HUD** (only chrome in default mode):
- Bar height: **96 px**, full-width, `bg.scrim` (warm dark, 80% alpha)
- Position: bottom edge, but **inside title-safe** — 106 px from canvas bottom
- Left: **CAM NAME** in `MediumBoldSystemFont` 36pt, all-caps
- Centre-left: **prev/next arrows** + **dot pager** showing position in carousel (4 cams = 4 dots, current solid)
- Right: **status row** — connected dot (`accent.ok` = green / `accent.warn` = amber if reconnecting / red if error), latency in seconds
- Right-edge: **last-motion timestamp** ("motion 2 min ago") — pulled from HA via ECP `/input?lastMotion=...`

**HUD auto-hide**: appears for **5 s** on mode entry / camera switch / any remote press, then fades. A camera with no chrome is the goal state.

**[LIVE] pip** (top-left, always visible while playing): `accent.live` coral dot pulsing at 1 Hz, "LIVE" in 18pt `text.cream`. **Inside title-safe.** This is the only persistent indicator.

**Reconnect curtain** (when player errors):
```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│                          ┌─────────────┐                             │
│                          │   [logo]    │   ◀─ brand mark, 500x100    │
│                          └─────────────┘                             │
│                                                                      │
│                       Reconnecting…                                  │
│                       attempt 2 of 4                                 │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```
`bg.cream` curtain at 95% alpha (calm pause, not alarm). Wordmark in `accent.brand`, `Reconnecting…` in `text.ink`, sub-label in `text.muted`.

---

## Mode 2 — GRID

Reached by **long-press OK** (>500 ms) from LIVE. The Roku decodes a single server-side `xstack` mosaic stream — *not* four parallel streams (Roku decoder budget = 1).

```
┌──────────────────────────────────────────────────────────────────────┐
│  ┌──────────────────────────┬──────────────────────────┐             │
│  │                          │                          │             │
│  │         FRONT            │          YARD            │             │
│  │                          │                          │             │
│  │                          │                          │             │
│  │  ●● motion 2m            │  ●  no motion 1h         │             │
│  ├──────────────────────────┼──────────────────────────┤             │
│  │                          │                          │             │
│  │         SIDE             │        BACKYARD          │             │
│  │                          │                          │             │
│  │                          │                          │             │
│  │  ●  no motion 4h         │  ●● motion 8m            │             │
│  └──────────────────────────┴──────────────────────────┘             │
│                                                                      │
│  ┌─ GRID VIEW ──────────────────────────────────  ▶ press OK to ───┐ │
│  │ ◀ ▶ ▲ ▼ select  ·  Back to return                    pick cam   │ │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

The video itself is one HLS stream from the server. The four labels and the focus ring are **client-side SceneGraph overlays** — invisible focusable hit zones aligned to each quadrant. Quadrant labels render in `text.ink` on a 60%-alpha `bg.cream` rounded chip (not on the raw video) so they read on any cam content. D-pad moves the focus ring; **OK selects** that camera and transitions to LIVE on it; **Back** returns to the previous LIVE cam. Focus ring: `accent.brand` 4 px + glow.

**Grid → Live transition**: 220 ms crossfade, ring expands to fill, mosaic stream stops fully *before* the cam stream starts (no double-decoder window).

The four motion indicators are pulled from HA (one ECP `/input` per camera with `lastMotion=`). `accent.live` (coral) double-dot for "recent motion (<5 min)", `accent.ok` (sage) single dot for "all clear" — two warm tones, no purple stranger. No client-side polling — HA pushes when state changes.

---

## Mode 3 — BRIEFING (60 sec, transient)

Cold-launch with `?mode=briefing` (the morning automation), or any-time via `/input?mode=briefing`. Auto-transitions to LIVE after 60 s.

```
┌──────────────────────────────────────────────────────────────────────┐
│   GOOD MORNING                                              7:14 AM   │
│   ────────────                                          Fri, May 8    │
│                                                                      │
│   ┌─────────────────────┐  ┌─────────────────────┐                   │
│   │   ☀  62°F  ↗ 71°    │  │   📅  T O D A Y     │                   │
│   │   partly cloudy     │  │                     │                   │
│   │                     │  │   9:00  Standup     │                   │
│   │   wind 6mph SW      │  │  11:30  Lunch w/ K  │                   │
│   │   sunset 8:14 pm    │  │   3:00  Aria pickup │                   │
│   │                     │  │   7:00  Soccer      │                   │
│   └─────────────────────┘  └─────────────────────┘                   │
│                                                                      │
│   ┌─────────────────────┐  ┌─────────────────────┐                   │
│   │   ⚡   E N E R G Y   │  │   👥  H O M E       │                   │
│   │                     │  │                     │                   │
│   │   2.4 kW now        │  │   Jimi   • office   │                   │
│   │   18 kWh today      │  │   Alex • away     │                   │
│   │   $4.12 so far      │  │   Aria   • bedroom  │                   │
│   │                     │  │                     │                   │
│   └─────────────────────┘  └─────────────────────┘                   │
│                                                                      │
│   ┌──────────────────────────────────────────────────────────────┐   │
│   │  Front Door: motion 11pm last night · Yard: clear            │   │
│   └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│                                  ────●●●○○○○────  53s to live cam    │
└──────────────────────────────────────────────────────────────────────┘
```

Four cards on a `bg.cream` field. Cards have `bg.warm` background, 1 px hairline `text.muted` border, 16 px rounded corners. Card header: `text.ink` `MediumBoldSystemFont` 32pt; body rows: `text.ink` 24pt; secondary numerics in `text.muted`. **Press OK or any button to dismiss early** (jumps to LIVE immediately). Bottom progress bar: `bg.warm` track, `accent.brand` fill, advances over 60 s.

Data sources, all polled from HA via REST every 30 s while the BriefingScene is mounted:
- `weather.edmonton_forecast` → `state`, `temperature`, `forecast[0].templow/temphigh`, `wind_speed`, `next_setting`
- `calendar.family` → next 4 events for today
- `sensor.emporia_total_power`, `sensor.emporia_total_daily_energy_kwh`, `sensor.electricity_daily_cost` (the homeController `electricity_cost` package surfaces this; alt: `sensor.emporia_total_daily_energy_kwh_cost`)
- `sensor.jimi_phone_room`, `sensor.jimi_wallet_room` (espresense) for each family member's room — Alex's phone tracker not currently reporting; add `sensor.alex_phone_room` when restored
- `binary_sensor.front_motion_occupancy` + last-trigger timestamp from HA history API

**Why 60 seconds**: long enough to read, short enough that "I just want to see the camera" doesn't get blocked. Skip-on-OK respects impatient users.

---

## Mode 4 — GLANCE (screensaver)

Roku-OS-registered screensaver, lives in the same channel package. Runs when the user has had the TV on but not interacted in ~5 min (Roku's default screensaver delay; user-overridable in OS settings).

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│           Friday                                                     │
│           May 8, 7:42 PM                              ☀  61°F        │
│                                                       partly cloudy  │
│                                                                      │
│                                                                      │
│                          H O U S E W A L L                           │
│                                                                      │
│                                                                      │
│                                                                      │
│      ┌─ home ────────────────┐    ┌─ outside ─────────────────┐      │
│      │  Jimi    office       │    │  front door  clear        │      │
│      │  Alex  away         │    │  yard        clear        │      │
│      │  Aria    bedroom      │    │  side        clear        │      │
│      │                       │    │  backyard    motion 8m    │      │
│      └───────────────────────┘    └───────────────────────────┘      │
│                                                                      │
│                                                                      │
│                  2.4 kW · sunset in 32m · 64% RH                     │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

Subtle. No video. Same `bg.cream` field + `bg.warm` cards as BRIEFING. Drifts the layout **±12 px every 60 s with 5 s ease-in/out** to prevent OLED burn-in — drift amplitude is bumped vs. dark designs because a constant-bright light field stresses the panel more uniformly. Refreshes data every 30 s. Any remote button dismisses the screensaver via Roku OS — channel resumes at last LIVE cam.

**Why this is in HAku and not a separate channel**: shared `Config.brs`, shared HA token in registry, shared visual language. One install for the whole experience.

---

## Overlay layer (v0.5)

`OverlayLayer` is a single SceneGraph component that owns every transient information surface above the live video. It exists because (a) HAku is meant to be *insight into the walls of the house*, not just camera glass, and (b) SceneGraph has no native gradient or rounded-corner Rectangle, so the cards have to be pre-rendered PNGs and we wanted exactly one place that knows about them.

Five overlay **kinds**, four on-screen **zones** — each zone has independent state and timer, so a doorbell PIP, a weather chip, an energy reading, and a "FRONT DOOR · OPENED" banner can all be visible at once without queuing.

| Kind | Zone | Position | Default TTL | Visual |
|---|---|---|---|---|
| `door` | top-banner (720×120) | top-centre below toast (600, 160) | 6 s | scrim card + severity stripe + "FRONT DOOR · OPENED" + sub-line |
| `text` | top-banner (720×120) | top-centre below toast (600, 160) | 4 s | scrim card + severity stripe + free-text banner |
| `weather` | weather-chip (360×96) | top-right (1360, 110) | 10 s | cream chip + glyph + "62°  ↗ 71°" + condition |
| `sensor` | sensor-chip (360×96) | top-right below weather (1360, 216) | 8 s | cream chip + glyph + value + label |
| `pip` | pip-box (480×302) | bottom-right (1344, 672) | 30 s | warn-tinted frame + JPEG snapshot well + cam name + countdown |

### ECP wire format

HA fires `POST /input?overlay=<kind>&…` and the input pump routes to `OverlayLayer.show(params)`. Unknown keys are ignored for forward-compat; unknown kinds noop.

| Kind | Required | Optional |
|---|---|---|
| `door` | `label`, `action` | `severity`, `detail`, `dwell` |
| `text` | `banner` | `severity`, `detail`, `dwell` |
| `weather` | `temp` | `hi`, `cond`, `dwell` |
| `sensor` | `value` | `icon` (`bolt`/`water`/`temp`/`wind`/`door`), `label`, `dwell` |
| `pip` | `cam` | `serverBase`, `duration` |

`severity` ∈ {`low`, `normal`, `high`} — drives the left-edge stripe colour using `hwSeverityColor()` (mirrors Toast). `dwell` / `duration` are seconds and override the default TTL.

### Visual + perf notes

The four card backgrounds (scrim card, cream chip, PIP frame, top-fade gradient) are emitted by `roku/scripts/generate_brand_assets.py`. Total payload ~4.6 KB. SceneGraph performance budget is the binding constraint: each zone is a small `Group` (≤6 nodes) and animations are marked `optional` so the Roku Express / Stick can drop them under load. PIP refresh uses a one-shot `JpegPipTask` with a ping-pong `tmp:` slot pair so the `Poster` never reads a half-written file.

The `severity=low` cam events from the v0.4 dispatch path now route automatically through `overlay=pip` — no separate HA wiring needed for "doorbell while watching another cam."

---

## Overlay 1 — PIP (Picture-in-Picture)

Used for **low-severity events** so they don't interrupt the user. Doorbell rings while you're watching the yard cam → small front-door cam pops up in the corner for 30 s, then auto-dismisses.

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│                                                                      │
│                  (LIVE main cam keeps playing — Yard)                │
│                                                                      │
│                                                                      │
│                                                                      │
│                                                                      │
│                                                                      │
│                                                                      │
│                                                                      │
│                                            ┌─────────────────────┐   │
│                                            │ ● FRONT DOOR        │   │
│                                            │                     │   │
│                                            │     [tiny cam]      │   │
│                                            │                     │   │
│                                            │  doorbell · 28s     │   │
│                                            └─────────────────────┘   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

- Position: bottom-right corner, **inside action-safe** (96 px margin)
- Size: **480 × 270** (16:9, exactly 1/4 size)
- Border: 4 px `accent.warn`
- Header strip: 32 px tall, `bg.scrim` (warm dark), label + countdown in `text.cream`
- Auto-dismisses at 0; user can also OK to **promote PIP to main view** (swap), or Back to dismiss (`*` is reserved for audio mute/dim — see remote map)

**Source — JPEG snapshot, canonical for v1.** The PIP fetches `http://<server>:1984/api/frame.jpeg?src=<cam>` every 500 ms via a `JpegPipTask` (off render thread; `roUrlTransfer` returns binary, write to `tmp:/pip_<cam>.jpg`, drive a `Poster` via `uri` swap). Decodes nothing on the Roku, no second Video node, no decoder-budget risk. Looks crisp at 480×270 for 30 s. Real second-decoder PIP is deferred to v2.x once the Roku fleet is fully inventoried and we know we have Ultras / Roku TVs everywhere.

---

## Overlay 2 — Toast

Brief text notification. Appears top-centre, 3-second auto-dismiss.

```
                  ┌─────────────────────────────────┐
                  │  ●  Front Door · motion         │
                  └─────────────────────────────────┘
```

- Width: auto, max 800 px
- Position: 80 px from top, horizontally centred
- 56 px tall, `bg.scrim` (warm dark), text in `text.cream`, 4 px left border in severity colour (`accent.live` high / `accent.warn` normal / `accent.ok` low)
- Slide in from top 180 ms, hold 3 s, slide out 150 ms

Used for: confirmations of camera switches that *did* happen ("Now: Front Door · jumped from motion"), low-priority HA events, mode-change feedback.

---

## Remote button map

The Roku remote has these buttons we can use. Mapping below covers every button in every mode.

| Button | LIVE | GRID | BRIEFING | GLANCE |
|---|---|---|---|---|
| **◀ Left** | prev cam (carousel wrap) | move grid focus | dismiss → LIVE | (OS) wake |
| **▶ Right** | next cam (carousel wrap) | move grid focus | dismiss → LIVE | (OS) wake |
| **▲ Up** | show HUD (if hidden) | move grid focus | dismiss → LIVE | (OS) wake |
| **▼ Down** | show HUD (if hidden) | move grid focus | dismiss → LIVE | (OS) wake |
| **OK** (tap) | toggle HUD visibility | select focused cam → LIVE | dismiss → LIVE | (OS) wake |
| **OK** (long, >500ms) | enter GRID | (n/a) | dismiss → LIVE | (OS) wake |
| **Back** | (no-op — Roku exits to home; this is fine) | return to LIVE on previous cam | dismiss → LIVE | (OS) wake |
| **Replay (↺)** | jump LIVE to `-15s` (replay last 15 s) | (n/a) | (n/a) | (OS) wake |
| **\* Options** (tap) | toggle audio mute for current cam | (n/a) | dismiss → LIVE | (OS) wake |
| **\* Options** (long, >500ms) | toggle dim mode (HUD-off, [LIVE] pip dimmed to 30%) | (n/a) | dismiss → LIVE | (OS) wake |
| **Home** | (OS) exits channel | (OS) | (OS) | (OS) |

Notable choices:
- **Replay** button is repurposed — it's the perfect button for "show me what just happened"
- **`*` overload** — tap = mute (the everyday lever); long-press = dim mode (the power-user lever). It's the only free button on the Roku Voice remote and these are the two related ambient toggles that need quick access. Tap on mute toasts "Audio on/off · Front Door"; long-press on dim toasts "Dim mode" with no follow-up after that.
- **Audio default** — every stream starts muted; per-cam mute state persists in registry, so turning on the front-cam audio sticks across sessions.
- **Back from LIVE** intentionally exits the channel (matches Roku conventions — users expect Back at top level to leave)

---

## Event-driven flows (the killer feature)

Three severities, three behaviours. HA decides the severity in the automation; HAku just reacts.

### High severity — "intruder", "fire", "panic" — full takeover with replay

```
T+0 ms    HA fires: POST :8060/input?cam=front&replay=15&severity=high&reason=motion+after+11pm&banner=ATTN+Front+Door
T+30 ms   roInput message received in InputPumpTask
T+50 ms   MainScene.lastInput field updated (observer fires)
T+60 ms   onInput() handler: severity=high → unconditional swap
T+80 ms   Toast slide-in: "● ATTN Front Door"  (red border, 5s instead of 3)
T+100 ms  player.content rebuilt with url=front.m3u8, playStart=-15
T+150 ms  220ms crossfade begins (old cam dimming)
T+370 ms  crossfade complete, replay rolling
T+15s     replay catches up to live edge (HLS LL behavior)
T+5.1s    Toast dismisses
```

### Normal severity — "door opened", "garage opened" — swap, no replay

```
T+0     POST /input?cam=front&severity=normal&reason=opened&banner=Front+Door+opened
T+~50   Toast slide-in (3s)
T+~100  cam swap, no replay (playStart=0, just live)
```

### Low severity — "doorbell pressed", "motion detected (low-traffic time)" — PIP, no swap

```
T+0     POST /input?cam=front&severity=low&duration=30&reason=doorbell&banner=Doorbell
T+~50   Toast slide-in: "● Doorbell · Front"
T+~100  PIP appears in bottom-right with cam=front (or JPEG snapshot if v0.1)
T+30s   PIP auto-dismisses
```

**Severity escalation**: if user OKs a PIP, it promotes to a full LIVE swap (with the user's intent now explicit). If user `*`s it, dismisses.

**During GRID**: any incoming event falls back to LIVE on that cam (we yield decoder budget).
**During BRIEFING**: events are queued in `MainScene.queuedEvents` and replayed on transition out.

---

## Cold-launch flows

```
roku boot
   │
   └─→ user picks HAku
          │
          └─→ Main(args)
                 │
                 ├─ args.haToken set          ─→  write registry.haToken + haUrl, toast
                 │                                  "Connected to Home Assistant" 2s,
                 │                                  fall through to default-cam path
                 │
                 ├─ args.setDefault set        ─→  write registry.defaultCam, toast,
                 │                                  proceed to LIVE on that cam
                 │
                 ├─ args.mode == "briefing"   ─→  push BriefingScene  ──60s──→  LIVE on default cam
                 │
                 ├─ args.cam set              ─→  seed lastInput, bypass discovery if cached
                 │                                       │
                 │                                       └─→ LIVE on args.cam
                 │
                 └─ otherwise                 ─→  Registry fast-path
                                                       │
                                                       ├─ cached HLS for default cam → LIVE immediately
                                                       │     (DiscoveryTask refreshes in background)
                                                       │
                                                       └─ no cache → splash + Discovery → LIVE
```

**Default cam** (when `args.cam` not provided) is per-Roku, configured in registry by a one-time deep-link `?setDefault=<cam>`: e.g. living-room Roku defaults to `yard`, bedroom Roku defaults to `front`. HA can override per event.

**HA token bootstrap**: one-time deep-link `?haToken=<token>&haUrl=http://mserver:8123` writes to the `haku` registry section, scrubbed from logs. No setup screen UI in v1. Token is plain-text in registry — for v1.1, store only a hash and re-prompt on cold launch.

---

## Home Assistant integration shape

What the user touches on the HA side to make this work:

### 1. `rest_command` (one per Roku)

`~/code/homeController/home-assistant/config/rest_commands.yaml`:

```yaml
**Source-of-truth lives in one file:** `homeController/home-assistant/config/packages/haku.yaml`. Everything below is a summary; the package is authoritative, and this section is just a guide to what's in it.

### Routing primitives (defined once at the top of the package)

- `rest_command.haku_living` / `_kids` / `_bedroom` / `_den` — one POST stanza per dev-unlocked Roku, hardcoded LAN IP.
- `sensor.haku_active_service` (template sensor) — resolves to whichever `rest_command.haku_*` matches `sensor.jimi_phone_room`. Falls through to `_living` when the room is unknown or maps to a Roku-less room.
- `script.haku_broadcast` — fires all 4 `rest_command.haku_*` in parallel with the same payload. Used for ambient pushes that should reach every room.

### Three targeting modes — pick per automation

| Mode | Service to call | When to use |
|---|---|---|
| Specific Roku | `rest_command.haku_<room>` | Room-specific events ("garage door → den TV only") |
| Active Roku (follow-me) | `"{{ states('sensor.haku_active_service') }}"` | Door alerts, replays — anything you want to *see now* |
| Broadcast | `script.haku_broadcast` | Weather, energy, water, motion-timestamp heartbeat — ambient stuff |

### Two ECP payload shapes

```
v0.4 cam-swap path  :  cam=front&severity=normal&replay=15&banner=Front+Door+opened
v0.5 overlay path   :  overlay=door&label=Front+Door&action=opened&severity=normal
```

Door alerts in the package fire **both** payloads back-to-back via the same automation — the cam-swap is the headline action when the v0.4 path works, and the overlay is the always-on visual ack that lands regardless. Severity → stripe colour: `low → ok` (sage), `normal → warn` (amber), `high → live` (coral).

The `severity=low` cam-events from the v0.4 path now route automatically to `overlay=pip` inside the channel — no separate HA wiring needed for "doorbell while watching another cam."

### Currently shipping automations (eight, as of 2026-05-09)

Cam-swap path (v0.4): front motion, front door opened, after-hours back motion, after-hours back door, motion-timestamp heartbeat. Overlay path (v0.5): the front-door + after-hours-back-door automations also fire `overlay=door` banners, plus three new ambient pushes — weather chip every 10 min (`weather.edmonton_forecast`), energy spike when whole-house draw stays >5 kW for a minute (`sensor.emporia_total_power`), water flowing for >30 s (`sensor.water_meter_flow`).

That's it on HA's side — one package file, no custom integration.

---

## Camera pipeline (server side, deployed on nserver)

**Source-of-truth lives in this repo at `stream/`** — five files (yaml + 3 systemd units + python discovery service) plus a `README.md`. Encoding uses Intel Quick Sync (`h264_qsv`) since nserver has an Iris Plus G1 iGPU rather than NVIDIA. Lessons-learned baked in from the start: deep HLS sidecar (12 s buffer, addresses [go2rtc#1699](https://github.com/AlexxIT/go2rtc/issues/1699)), SSDP discovery so clients don't hard-code IPs, dedicated `media` user with `video,render` supplementary groups for QSV access.

### Phase 1 (DEPLOYED 2026-05-08) — mosaic only

`stream/go2rtc.yaml` runs one stream, `mosaic`, sourced from the NVR HDMI-out via the USB capture device:

```yaml
streams:
  mosaic:
    - >-
      exec:ffmpeg -hide_banner -loglevel warning
      -f v4l2 -input_format mjpeg -video_size 1920x1080 -framerate 20
      -i /dev/v4l/by-id/usb-MACROSILICON_USB3.0_Video_67807015-video-index0
      -init_hw_device qsv=qsv:/dev/dri/renderD128
      -filter_hw_device qsv
      -vf "format=nv12,hwupload=extra_hw_frames=64"
      -c:v h264_qsv -preset veryfast
      -profile:v main -level:v 4.0
      -look_ahead 0 -bf 0 -g 40 -keyint_min 40
      -b:v 2500k -maxrate 3000k -bufsize 5000k -rc_mode CBR
      -an -f rtsp {output}
```

Why not pre-merge per-cam streams into our own `xstack` mosaic? Because the NVR is already doing that 4-up split rendering, and capturing its HDMI-out is one decode pass instead of four. We get the mosaic for free.

`haku-hls.service` re-muxes go2rtc's RTSP into a 6×2 s = **12 s** rolling HLS in `/run/haku-hls/` (tmpfs). `haku-discovery.service` serves both the SSDP capability JSON and those HLS files on `192.0.2.20:1985`.

Verified bandwidth on the wire: **~2.56 Mbps per consumer** (down from 78.7 Mbps under the old mjpg_streamer passthrough — ~30× reduction). iGPU encoder load: ~1–2%.

### Phase 2 (DEPLOYED 2026-05-08)

Four direct-cam RTSP streams added to `go2rtc.yaml` plus a templated `haku-hls@.service` so each cam gets its own 12 s deep HLS sidecar. Creds live in `/etc/haku/cam-creds.env` (mode 0640 root:media, never committed) and are referenced via `${HAKU_CAM_USER}`/`${HAKU_CAM_PASSWORD}` substitution in `go2rtc.yaml`. Two vendors → two URL conventions; the .32 Reolink uses its H.264 sub-stream because the main is HEVC 4K (Roku-incompatible). All 5 streams (mosaic + 4) reachable at `http://192.0.2.20:1985/hls/<name>.m3u8`:

```yaml
streams:
  mosaic:    # NVR HDMI capture, encoded h264_qsv (already deployed)
  front:     rtsp://${HAKU_CAM_USER}:${HAKU_CAM_PASSWORD}@192.0.2.35:554/cam/realmonitor?channel=1&subtype=0   # Amcrest
  yard:      rtsp://${HAKU_CAM_USER}:${HAKU_CAM_PASSWORD}@192.0.2.32:554/h264Preview_01_sub                   # Reolink — sub-stream (main is HEVC 4K)
  side:      rtsp://${HAKU_CAM_USER}:${HAKU_CAM_PASSWORD}@192.0.2.33:554/cam/realmonitor?channel=1&subtype=0  # Amcrest
  backyard:  rtsp://${HAKU_CAM_USER}:${HAKU_CAM_PASSWORD}@192.0.2.34:554/h264Preview_01_main                  # Reolink-family
```

Each direct-cam stream gets:
- a `STREAM_METADATA` entry in `haku-discovery.py` (display name, codec, resolution, audio, ptz)
- a `haku-hls@<cam>.service` instance from the templated unit, writing `<cam>.m3u8` + `<cam>_seg_NNNNN.ts` to `/run/haku-hls/`
- a corresponding `streams.<cam>.hls = http://192.0.2.20:1985/hls/<cam>.m3u8` in `/discovery.json`

---

## State machine (formally)

```
states  =  { LIVE, GRID, BRIEFING, GLANCE }
overlays = { PIP_active, TOAST_visible, RECONNECT_visible }
inputs  =  { D-Pad, OK_tap, OK_long, Back, Replay, Star, ECP_input, Timer, StreamError }

LIVE × Left/Right       → LIVE (cam = prev/next)
LIVE × OK_long          → GRID
LIVE × Replay           → LIVE (player.playStart = -15)
LIVE × Star_tap         → LIVE (mute = !mute)
LIVE × Star_long        → LIVE (dim_mode = !dim_mode)
LIVE × ECP_input(sev=high|normal)  → LIVE (cam=event.cam, replay if set)
LIVE × ECP_input(sev=low)          → LIVE +PIP_active
LIVE × ECP_input(mode=briefing)    → BRIEFING
LIVE × StreamError      → LIVE +RECONNECT_visible (backoff escalation)
LIVE × Timer(idle=5min) → GLANCE   (handed to OS screensaver)

GRID × D-Pad            → GRID (focus moves)
GRID × OK               → LIVE (cam = focused)
GRID × Back             → LIVE (cam = prev cam)
GRID × ECP_input        → LIVE (event.cam) — abandon grid

BRIEFING × Any user input → LIVE (default cam)
BRIEFING × Timer(60s)   → LIVE (default cam)
BRIEFING × ECP_input    → queued; replay on transition

GLANCE × Any user input → LIVE (resume last)  [handled by OS]
```

PIP, Toast, Reconnect are independent timers/observers — they don't affect mode.

---

## Watchdog & reconnect

Per-cam exponential backoff with re-discovery escalation:

```
attempt 1: wait 2 s, retry same URL
attempt 2: wait 5 s, retry same URL
attempt 3: wait 10 s, retry same URL
attempt 4: wait 30 s, kick DiscoveryTask (fresh SSDP), invalidate registry, retry with new URL
attempt 5+: continue at 30 s with periodic discovery refresh
```

`reconnectOverlay` shows from attempt 1, sub-label updates ("attempt 2 of 4"), hides on first successful frame (player state observer: `playing` → hide overlay).

---

## Phasing checkpoint (what we ship in what order)

| Version | Scope | Status |
|---|---|---|
| **v0.1** | Rename + retheme, single cam (`front`), ECP `/input?cam=front&banner=...` swaps URL, toast | ✅ shipped 2026-05-08 |
| **v0.2** | 4 cams, ◀▶ paging, lower-third HUD with cam name + dot pager + last-motion | ✅ shipped 2026-05-08 |
| **v0.3** | GRID via mosaic stream + long-press OK + grid focus overlay | ✅ shipped 2026-05-08 (commit `17e3596`, running on 4 Rokus) |
| **Server Phase 2** | Per-cam direct RTSP → 4 deep-HLS sidecars via templated unit | ✅ shipped 2026-05-08 (commit pending) — carousel now actually swaps cams |
| **v0.4** | Replay (`replay=N` → playStart=-N) + severity routing | ✅ shipped 2026-05-08 — channel-side wired in `LiveGroup`/`MainScene.dispatchEcp`; HA package `homeController/home-assistant/config/packages/haku.yaml` widened to all 4 Rokus with active-Roku selector (`sensor.haku_active_service`) + `script.haku_broadcast` for HUD heartbeat. HA token seeded to all 4 Rokus via deep-link. |
| **v0.5** | Info-overlay framework — PIP + door + weather + sensor + text cards, all driven by HA via ECP `/input?overlay=…` | ✅ channel shipped 2026-05-08, HA wiring 2026-05-09 — `OverlayLayer` component with 4 zones (top banner, weather chip, sensor chip, PIP), severity-coloured stripe, baked rounded-card PNGs (no native gradients/rounded rects in SceneGraph). Five kinds, independent dismiss timers, slide-in animations. Backed by `JpegPipTask` for the snapshot loop. Existing `severity=low` cam events route to PIP automatically. HA-side: door automations fire dual payloads (cam-swap + overlay banner); three new ambient pushes (weather every 10 min, energy spike >5 kW/1 min, water flow >30 s). **Caveat:** v0.4 cam-swap path is broken end-to-end (see followup) so the door-cam swap does not yet fire when the door is opened — overlay layer is unaffected and renders the banner regardless. |
| **v0.6** | Glance screensaver scene + HaPollTask | not started |
| **v0.7** | Briefing scene + morning HA automation | not started |
| **v1.0** | Multi-Roku follow-me via espresense + dim mode + polish | not started — gated on espresense rooms (most offline today) |

---

## Resolved decisions (was: Open questions)

Updated 2026-05-08 with grounded answers based on the homeController inventory + an explicit user call.

1. **PIP source** — *DECIDED: JPEG snapshot is canonical for v1.* PIP fetches `http://<server>:1984/api/frame.jpeg?src=<cam>` every 500 ms, written to `tmp:/pip_<cam>.jpg`, surfaced via a `Poster` node. Decodes nothing on the Roku, no second Video node, no decoder-budget risk. The only catalogued Roku (`kids-roku`, Roku Express) couldn't run dual decoders anyway, so this also future-proofs against fleet variability. Real second-Video PIP is deferred to v2.x once the fleet is fully inventoried and we know we have Ultras / Roku TVs everywhere.
2. **Camera count** — *DECIDED: 4 cams from inventory.* `frontcam` (192.0.2.35), `yardcam` (192.0.2.32), `sidecam` (192.0.2.33), `backyardcam` (192.0.2.34). 2×2 grid is the right shape; no paging needed.
3. **Default cam per Roku** — *PROVISIONAL until fleet inventoried:* mapping below. Stored in registry per Roku, settable via one-time deep-link `?defaultCam=front`. Active-Roku selector keys off `sensor.jimi_phone_room`.

   | espresense room | Likely Roku location | Default cam | Reasoning |
   |---|---|---|---|
   | `kitchen`        | living/kitchen TV    | `backyard`  | kitchen sliding door faces backyard |
   | `den`            | living-room Roku     | `front`     | front-door cam = "who's at the door?" — most-checked |
   | `bedroom`        | bedroom Roku         | `front`     | overnight peace-of-mind glance |
   | `office`         | office Roku          | `yard`      | side-of-house view from desk |
   | `bedroom_2`     | (kids-roku is another room — needs separate Roku) | `front` | gentle default |
   | `laundry`        | (no Roku expected)   | n/a         | |

4. **HA token bootstrapping** — *DECIDED: one-time deep-link setup screen.* Cold-launch with `?haToken=...` writes to registry under `haku.haToken`, scrubbed from logs. User generates a Long-Lived Token in HA (Profile → Security → Create Token), then on a dev machine runs `curl -d '' "http://<roku>:8060/launch/dev?contentId=setup&haToken=<token>&haUrl=http://mserver:8123"`. Channel shows a one-shot "Set up complete · token saved" toast and routes onward. Token never persisted outside `roRegistrySection` — note that registry is plain-text on disk; for additional hardening, store only a hash and re-prompt on cold launch (defer to v1.1).
5. **Brand identity** — *DECIDED: Daylight palette (cream / sage UI chrome) + the HAku house/camera-lens logo (blue/orange).* Splash colour `bg.cream` `#F7F1E3`. Two source art files: `docs/brand/logo_icon.png` (4:3, transparent, icon-only glyph) composited onto the cream 4:3 app-icon tile, and `docs/brand/logo_wordmark.png` (transparent, full icon+wordmark lockup) reused for the splash screen (letterboxed onto cream), the reconnect-overlay banner, and the default background-rotation card (`sidecar/backgrounds/bg_00_haku_logo.jpg`). The logo's own blue/orange colours are independent of the UI chrome palette below — `bg.cream`/`accent.brand`/etc. are unchanged. All opaque surfaces (BRIEFING, GLANCE, Reconnect curtain) sit on `bg.cream`. Chrome over live video uses `bg.scrim` `#2B2A26CC` (warm dark, 80% alpha) with `text.cream` text. Family-friendly, easy on the eyes; explicitly *not* the dark-navy security-console look. All shipped variants are emitted by `roku/scripts/generate_brand_assets.py` from `docs/brand/logo_icon.png` + `docs/brand/logo_wordmark.png` — that script is the source of truth for asset dimensions, formats, and palette use. Full colour token table is in §"Visual style" above.
6. **Audio** — *DECIDED: muted by default; `*` toggles per-cam audio.* Roku TVs sit in living rooms with people watching other things; auto-playing camera audio is intrusive. Toast on toggle: "Audio on · Front Door". PIP is *always* muted regardless of toggle (incoming audio under another video would be confusing). Audio policy is per-cam, persisted in registry — turning it on for the front cam stays on for that cam across sessions.
7. **Grid > 4 cams** — *DECIDED: out of scope for v1.0.* Inventory shows exactly 4 cams; no need to page. If/when the user adds outdoor cams (e.g. driveway, garage interior), v2.0 can split GRID into a paged view (◀▶ pages between 2×2 panels) or flow into a 3×3 with the centre cell as the focused-on cam.
8. **Spotlight mode** — *DECIDED: prototype as v1.1 polish, not v1.0.* Pattern: focused cam at 1280×720 left, three 320×180 thumbnails stacked right. Adds an alt-mode (D-pad up/down on LIVE = enter Spotlight) without disturbing the LIVE↔GRID relationship. Will lift cleanly once GRID is shipping.

## Deferred to v2

Three deliberate non-goals for v1, called out so they don't bleed into scope:

- **Grid > 4 cams** with paging or 3×3 layouts (today's inventory is exactly 4 cams).
- **Real second-Video PIP** (gated on full Roku-fleet inventory and a confirmed Ultra/Roku-TV majority).
- **Spotlight mode** (1280×720 + thumbnail rail; pattern is sketched but not built).

## Tablet client (kitchen Fire 7, 2026-09-30)

HAku now has a second kind of display client: a native Android app (`io.haku.tablet`) on the kitchen wall Fire 7. It lives in **`fire-tablet/`** (it had its own repo, `~/code/tablet-homewall`, from 2026-09-30 until the 2026-10-03 merge into `homewall`). It is a pure sidecar consumer: it polls `/api/config` + `/api/state` over plain HTTP, gets no ECP pushes and holds no HA token.

- **Status (2026-10-01):** the v2 UI runs on the wall as an R8 release build, using 54 to 61 MB PSS (the budget is 95 MB). It shows nine smoked-glass cards on a 4×3 grid over rotating NAS photos: doors, laundry, calendar, activity, water, energy, weather, gas and thermostat. The design is in `docs/fire-tablet/DESIGN.md` §8, and the exact JSON shapes and visual values are in `docs/superpowers/plans/2026-09-30-tablet-ui-v2-contract.md`.
- **Layouts (`?layout=`).** `dashboard.json` has an optional top-level `layouts` map, and the tablet sends `?layout=tablet` on every route it calls. A layout has its own `grid`, `nightDim` and `background`. Its module list does two things:
  - it references top-level modules by `ref`, shallow-merging its own keys over them (a different `tile`, or `runningSeverity: "normal"` for water);
  - it adds layout-only modules.

  Without the param every route serves the Roku view, and `/api/config` never contains `layouts`, which keeps it clear of the Roku's ~16 KB registry cache. An unknown layout or a bad `ref` returns a 404 JSON error.
- **Tile keys.** Every module's `tile` gains three keys:
  - `glyph`: a Material Design Icons name chosen from state;
  - `active`: always a real bool. It is true for water flowing, gas burning, heating or cooling, a door open, and laundry running, in overtime or done;
  - `level`: 0–100, for energy, water and gas only.

  Timeline event items gain `glyph` too. `tile.icon` is unchanged: it stays the Roku's cache-bust token. Per-module rules: `sidecar/README.md` § Tile keys.
- **`doors` and `laundry` modules.** Only the tablet layout uses them, and neither has an icon PNG or a card.
  - `doors` fills the kind already reserved in `HK_MODULE_KINDS()`: open or closed per contact, with "since" taken from the logbook, because HA re-stamps `last_changed` on restart.
  - `laundry` mirrors the sensors from HA's `packages/laundry.yaml` (`sensor.laundry_<m>_mode`, `_leds` and the cycle times) and never re-derives them. The tablet draws the LED bar natively.
- **Per-layout backgrounds.** `layouts.tablet.background.dir` points `/api/backgrounds?layout=tablet` and `/api/background/<name>?layout=tablet` at the NAS folder `/mnt/media/haku/kitchen` instead of `HAKU_BG_DIR`. The `dir` is never serialized. `/api/background` also gained two params:
  - `fit=cover` centre-crops to exactly w×h (the Roku keeps the default `contain`);
  - `blur` is a Gaussian radius from 0 to 40.

  The NAS mount is `hard`, so at most two requests read the layout `dir` at once and a third gets a 503; the Roku's `HAKU_BG_DIR` requests are never limited. The tablet fetches a sharp 1024×600 copy and a blurred 256×150 copy, and fakes frosted glass from the blurred one, since API 30 can't blur live.
- **What the Roku sees.** Its default responses are unchanged, with two exceptions:
  - The additive keys above appear in them. The Roku reads keys by name, so it ignores them.
  - Two sub-text fixes, approved on 2026-10-01. Gas `sub` is empty instead of "running" when the flow rounds to 0.0 m³/h (a trickle). The thermostat `sub` reads "Fan" instead of "Idle" when `hvac_action` is `fan`; a thermostat that is off still reads "Off".

  The Roku's gas icon PNG still colours for any flow above 0.
- **Contract rule:** the tablet ignores unknown keys and falls back to a value card for unknown `tile.type`, the same forward-compatibility rule as `hkModuleKind`. Any sidecar JSON change must keep both clients working. The tablet's JVM tests parse fixtures captured from the live sidecar (`fire-tablet/app/src/test/resources/`, `?layout=tablet`).

## Followup — cold-launch flash (noted 2026-05-08)

Between splash dismiss and the first video frame the user sees a brief flash — most likely either MainScene's cream `bg` Rectangle showing for one frame before LiveGroup's warm-dark `bg` paints over it, or the cream `reconnectOverlay` flashing through with "Waiting for discovery…" when SSDP returns fast enough that the curtain barely registers. Mitigation: debounce `showReconnect("Waiting for discovery…", "")` in `LiveGroup.brs:120` by ~400 ms so a fast discovery doesn't trigger the curtain at all; consider also keeping LiveGroup's bg cream (matching the splash) until the first video frame arrives, then snapping to dark. Track as v0.5.1 polish.

## Followup — sensor health (validated 2026-05-08)

Running `curl http://192.0.2.10:8123/api/states` against HA caught a handful of entities the v0.1 wiring depends on that are currently `unavailable`. They almost certainly still exist physically (battery dead, Wi-Fi/Zigbee out, ESP module hung) — re-validate before final automation wiring rather than just deleting:

- [ ] **`binary_sensor.garage_doorcontact_contact`** — door-contact battery / radio. Side-cam event routing depends on it.
- [ ] **`binary_sensor.gate_doorcontact_contact`** — door-contact battery / radio. Yard-cam event routing depends on it.
- [ ] **`binary_sensor.backyard_corner_motion_occupancy`** — secondary backyard motion. After-hours rule still works with `backyard_motion_occupancy` + `back_yard_motion`, but corner gives wider coverage.
- [ ] **ESPresense rooms `front_door, kitchen, laundry, living_room, bedroom_2`** — only `den` and `office` reporting today. Active-Roku follow-me selector needs most of these back online before the multi-Roku flow works.
- [ ] **`person.alex` / Alex's phone tracker** — currently `unknown`. BRIEFING family roster will read empty for her until restored.

## Hard requirements before v0.1 sideload

- [x] ~~**Inventory the rest of the Roku fleet.**~~ **PARTIAL 2026-05-08:** ECP scan found 5 Rokus on `192.0.2.0/24`. 4 are dev-unlocked + running HAku: `living=.51` (Stick+), `kids=.52` (Express), `bedroom=.53` (Stick), `den=.54` (Express 4K). 1 not dev-unlocked: `dad=.56` (Streaming Stick). Garage Roku not seen on the scan — likely powered off or on a different VLAN. Still need to fold these into `homeController/infra/network/inventory.yaml`.
- [x] ~~**Confirm RTSP URL paths per camera with creds.**~~ **DONE 2026-05-08:** all four cams respond on port 554 with `the shared camera login` (pulled from HA's Reolink integration). `front` (.35 Amcrest) + `side` (.33 Amcrest) = `cam/realmonitor?channel=1&subtype=0` (H.264 1920×1080 High @ 50fps). `yard` (.32 Reolink) — main is HEVC 4K (Roku-incompatible), use `h264Preview_01_sub` (H.264 640×360 @ 10fps). `backyard` (.34 Reolink-family) = `h264Preview_01_main` (H.264 2048×1536 @ 20fps). Creds in `/etc/haku/cam-creds.env` on nserver, mode 0640 root:media; referenced from `go2rtc.yaml` as `${HAKU_CAM_USER}`/`${HAKU_CAM_PASSWORD}`.
- [x] ~~**Confirm yardcam vs. "Back" labelling.**~~ **RESOLVED 2026-05-08:** physically, .32 (HA "Back Yard") is the Reolink-PTZ on the house-corner facing back yard / drive pad / fence — the wider open back area, mapped to `yard`. .34 is the no-PTZ Reolink-family behind the garage facing the playground — tucked-in spot, mapped to `backyard`. HA's "Back Yard" naming on .32 was misleading; design-doc mapping was correct.
- [x] ~~**Decide mosaic origin.**~~ **DONE 2026-05-08:** go2rtc on nserver, capturing the NVR's existing HDMI-out 4-up split via the USB capture card and encoding via Intel QSV. Configs version-controlled in `stream/`; legacy mjpg_streamer at `:8090` stopped + disabled. HA's `camera.camerafeed` (`mjpeg` integration entry `<config-entry-id>`) re-pointed at `http://192.0.2.20:1984/api/stream.mjpeg?src=mosaic` with snapshot `…/api/frame.jpeg?src=mosaic`; backup at `.storage/core.config_entries.bak-20260509-001244` on mserver.
- [x] ~~**Generate HA long-lived token**~~ **DONE 2026-05-08:** long-lived token generated in HA UI and seeded to all 4 dev-unlocked Rokus via the deep-link bootstrap (`?contentId=setup&haToken=…&haUrl=…`, URL-encoded — without encoding the `:` in `http://` Roku returns 404). Reference copy in gitignored `rokuApp/.env`. **Rotate after this conversation** — token value appeared in chat transcript.
- [ ] **Confirm the rotation order** of the 4 cams matches user mental model (currently `front → yard → side → backyard` clockwise).
