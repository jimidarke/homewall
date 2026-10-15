# HAku — How It Works & How It Looks

> Sideloaded Roku channel. A glass wall of the home's numbers with the front camera playing live in one square, that cuts to the right camera full-screen when something happens and drifts back to the wall when it's over.

---

## North star

**HAku is the TV-shaped client for the home.** Most of the time it is a read-only wall of glass cards (doors, laundry, water, energy, gas, weather, thermostat, calendar, activity, a 3-day forecast with a 48 h temperature chart) over a rotating drone photo, with the front camera playing live in a 2×2 square. When the home has something to say — a door opens, motion at the front walk, the back door at 2 am — Home Assistant pushes it to the Roku and HAku reacts: it cuts to the relevant camera full-screen (with a 15-second pre-roll for the serious ones, so you see *what just happened*), or it shoulders a small picture-in-picture in the corner so it doesn't yank you out of what you were watching. A minute later, untouched, it goes back to the wall.

It's a Roku channel because Rokus are the box that's already in every room. Home Assistant is the brain; HAku is just one of its faces. The kitchen wall's Fire 7 tablet is the other ([Tablet client](#tablet-client-kitchen-fire-7)).

> **Paths in this document (checked 2026-10-14).** Paths are in the `homewall` monorepo layout (`roku/`, `sidecar/`, `stream/`, `fire-tablet/`, `docs/`). The live HA config is on mserver at `/root/docker/homeassistantV3/config/ha/` (HA runs in Docker). HAku's push side is the package `packages/housewall.yaml` there (repo copy: `roku/ha-housewall.yaml`) (it predates the HAku name, so its entities are `housewall_*`); the sidecar-side helper packages are `electricity_cost.yaml`, `gas_cost.yaml`, `water_cost.yaml` and `haku_water.yaml`. There is no `packages/haku.yaml` or `rest_commands.yaml`. Status notes below are dated snapshots; the current state of each part is in its own folder's README/CLAUDE.md.

> **Status (1.2, 2026-10-14).** The Roku channel boots to the read-only 6×4 glass wall (spec `docs/superpowers/specs/2026-10-07-roku-wall-6x4-design.md`, baseline `docs/roku/screens/v0.12-home.png`), served by the sidecar's `?layout=roku`; backgrounds are the shared drone photos (spec `docs/superpowers/specs/2026-10-07-shared-backgrounds-design.md`). HA takeovers still reach the full-screen live camera and the grid. All five Rokus (the four fleet Rokus and the dev Roku) run 1.2.1 since 2026-10-14, verified playing the front camera on the wall; front motion switches the square to the steps (spec `docs/superpowers/specs/2026-10-14-front-steps-view-design.md`), the front door takes the office Roku and the kitchen tablet to the steps for a minute, and everything polls every second (spec `docs/superpowers/specs/2026-10-14-door-camera-and-1s-polling-design.md`). The fleet doesn't auto-update, so each Roku runs whatever was last sideloaded. The tablet runs its v3 touch UI.

---

## Inventory (what's actually on the LAN)

**Network**: `192.0.2.0/24`, gateway `192.0.2.1`, domain `home.lan`.

**Cameras (RTSP — go direct, bypass the NVR's HDMI-capture path)**. Validated 2026-05-08 against Mikrotik DHCP leases + a TCP-port probe; front re-pointed 2026-10-07; port 554 re-probed 2026-10-14:

| Friendly | LAN IP | MAC | Vendor | Open ports | RTSP URL convention |
|---|---|---|---|---|---|
| frontcam   | `192.0.2.31` | `xx:xx:xx:xx:xx:xx` | **Genbolt** dual-lens (XiongMai), WAN-blocked | 80, 554, 8080 (ONVIF) | `rtsp://USER:PW@192.0.2.31:554/21` PTZ lens (HEVC 1080p15; `/22` sub, `/11` fixed lens). Own login (`HAKU_FRONT_*`). HAku transcodes `/21` to H.264 720p. |
| yardcam    | `192.0.2.32` | `xx:xx:xx:xx:xx:xx` | **Reolink** PTZ (DHCP host-name `Back`) | 80, 554, 8000 | `rtsp://USER:PW@192.0.2.32:554/h264Preview_01_sub` (main is HEVC 4K) |
| sidecam    | `192.0.2.33` | `xx:xx:xx:xx:xx:xx` | **Amcrest** (`<serial>`) | 80, 554, 37777 | `rtsp://USER:PW@192.0.2.33:554/cam/realmonitor?channel=1&subtype=0` |
| backyardcam| `192.0.2.34` | `xx:xx:xx:xx:xx:xx` | **Reolink-family IPC** | 80, 443, 554, 8000 | `rtsp://USER:PW@192.0.2.34:554/h264Preview_01_main` — **offline** (554 closed 2026-10-14; the NVR can't reach it either) |

Physical placement (confirmed 2026-05-08): .32 (HA's "Back Yard") is the Reolink PTZ on the house corner facing the back yard / drive pad / fence, mapped to `yard`; .34 is the no-PTZ Reolink-family behind the garage facing the playground, mapped to `backyard`. The old front Amcrest at `.35` is gone.

**NVR (16-channel)**: `192.0.2.30` `NVR-16` (OUI `xx:xx:xx`, Lorex/Dahua family) — ports 80, 554 open. Its HDMI-out 4-up split is the source of the `mosaic` stream. Its own RTSP (`rtsp://USER:PW@192.0.2.30:554/cam/realmonitor?channel={1..4}&subtype=0`) is a fallback if a per-cam path turns out to be flaky on a given firmware.

**Camera pipeline on nserver (source of truth in `stream/`)**:
- NVR HDMI-out → USB3.0 capture card on `/dev/v4l/by-id/usb-MACROSILICON_USB3.0_Video_67807015-video-index0` on nserver (Macrosilicon `345f:2131`, USB 3.0 SuperSpeed).
- `go2rtc.service` runs go2rtc 1.9.x as the `media` user. The mosaic pulls 1920×1080 MJPEG @ 20 fps from the capture device and encodes via Intel Quick Sync (`h264_qsv`, Iris Plus G1) at H.264 Main L4.0 / `yuv420p` / GOP=40 (= 2 s) / no B-frames / 2.5 Mbps CBR. The four cameras are direct RTSP streams (front transcoded, see [Camera pipeline](#camera-pipeline-server-side-nserver)).
- `haku-hls.service` (mosaic) and `haku-hls@<cam>.service` (one per camera) are `ffmpeg -c copy` remuxes of go2rtc's RTSP into a 3 × 2 s rolling HLS window in `/run/haku-hls/` (tmpfs). The Roku plays from the oldest listed segment, so the window is the latency: ~5 s behind live (`yard`, with a ~4 s camera GOP, ~11 s); measured 2026-10-14, see `stream/README.md`. Addresses go2rtc's known shallow-HLS underflow ([AlexxIT/go2rtc#1699](https://github.com/AlexxIT/go2rtc/issues/1699)) — the Roku consumes this, not the built-in HLS.
- `haku-discovery.service` (Python, stdlib-only) runs an SSDP responder on UDP `239.255.255.250:1900` with ST=`urn:haku:service:dashboard:1`, plus an HTTP server on `192.0.2.20:1985` that serves both the capability JSON (schema v2, with a `sidecar` block pointing at `:1986`) and the deep-HLS files.
- All endpoints below are served on `enp1s0` IP `192.0.2.20` (`<cam>` ∈ `mosaic`, `front`, `yard`, `side`, `backyard`):

| Endpoint | URL | Use |
|---|---|---|
| SSDP discovery | multicast `239.255.255.250:1900` ST=`urn:haku:service:dashboard:1` | Roku auto-discovers — no hard-coded IP |
| Capability JSON | `http://192.0.2.20:1985/discovery.json` | Versioned payload: per-stream RTSP/HLS/MJPEG/snapshot URLs + the sidecar base |
| **Roku channel uses** | `http://192.0.2.20:1985/hls/<cam>.m3u8` | 3 × 2 s HLS (~5 s behind live), Roku's hardware H.264 decode path (per-cam for the camera card and LIVE, `mosaic` for GRID) |
| HLS shallow | `http://192.0.2.20:1984/api/stream.m3u8?src=<cam>` | Browsers, debugging — go2rtc native (~1 s buffer) |
| RTSP | `rtsp://192.0.2.20:8554/<cam>` | HA `Stream` integration, VLC, ffmpeg |
| MJPEG | `http://192.0.2.20:1984/api/stream.mjpeg?src=<cam>` | HA `mjpeg:` legacy compat |
| WebRTC preview | `http://192.0.2.20:1984/stream.html?src=<cam>` | Sub-second-latency in-browser viewing |
| **PIP snapshot** | `http://192.0.2.20:1984/api/frame.jpeg?src=<cam>` | HAku PIP fetches this every 500 ms (~196 KB JPEG for the mosaic) |
| Status UI | `http://192.0.2.20:1984/` | Live consumers, bandwidth |

- HA's `camera.camerafeed` (`mjpeg` integration entry `<config-entry-id>`) points at `http://192.0.2.20:1984/api/stream.mjpeg?src=mosaic` with snapshot `…/api/frame.jpeg?src=mosaic`. One Reolink is also integrated in HA directly (`camera.back_yard_fluent`); despite the name it is `yardcam` (.32).
- **Bandwidth per consumer**: ~2.56 Mbps for the mosaic (was 78.7 Mbps under the old MJPEG passthrough — 30× reduction). Encoder load: ~1–2% iGPU.
- **Legacy `sendHDMI.service` / mjpg_streamer at `:8090`** is **stopped + disabled**. Unit file kept on disk for one-line rollback (`systemctl enable --now sendHDMI`).

**Roku fleet** — all dev-unlocked and running HAku (the fleet doesn't auto-update; each runs whatever was last sideloaded):

| Friendly | LAN IP | Model | Notes |
|---|---|---|---|
| living | `192.0.2.51` | Roku Streaming Stick+ | |
| kids | `192.0.2.52` | Roku Express | USB-powered by the bedroom TV; reachability = TV-power state proxy in HA `packages/kids_tv.yaml` |
| master | `192.0.2.53` | Roku Streaming Stick | HA calls it `bedroom` (`rest_command.housewall_bedroom`) |
| den | `192.0.2.54` | Roku Express 4K | |
| dev | `192.0.2.55` | Roku Premiere+ | **Dev box** in the office, not part of the wall fleet. Its own dev password; the fleet's is `$ROKU_PW_FLEET`. |

Not running HAku: `dad=.56` (Streaming Stick, not dev-unlocked); a garage Roku was never seen on a scan.

**Kitchen tablet**: Fire 7 at `192.0.2.60` ([Tablet client](#tablet-client-kitchen-fire-7)).

**HA entities.** The sidecar's module→entity map is `/etc/haku/dashboard.json` on nserver (template `sidecar/dashboard.json.example`): weather (`weather.edmonton_forecast`), calendar (`calendar.family`), Emporia energy, the gas and water meter packages, the ecobee, door contacts and people. The push side (`housewall.yaml`) keys off:
- Door contacts: `binary_sensor.front_doorcontact_contact`, `back_doorcontact_contact`
- Motion: `binary_sensor.front_motion_occupancy`, `backyard_motion_occupancy`
- Presence (follow-me): `sensor.jimi_phone_room` (ESPresense)

**Coverage gap** — there's no `binary_sensor.yard_motion` or `binary_sensor.side_motion`; outdoor motion is only `front` and `backyard`. So the event-driven jump table routes door contacts and motion to *appropriate* cams rather than 1:1 cam-per-sensor.

---

## Routes

HAku has one resting screen and a few places HA (or the remote) can take it. Everything else is an overlay or a transient state.

```
        ┌──────────────────────────────────────┐
        │   H O M E   (default, read-only)     │
        │   6×4 glass wall + live front cam    │
        └──────────────────────────────────────┘
          │  ▲                         │  ▲
 HA cam=  │  │ Back · 60 s after a     │  │ Back
 takeover │  │ takeover · 5 min idle   *  │
          ▼  │                         ▼  │
  ┌──────────────────────┐      ┌──────────────────┐
  │   L I V E            │      │   D I A G        │
  │   one camera,        │      │   device +       │
  │   fullscreen, HUD    │      │   discovery + HA │
  └──────────────────────┘      └──────────────────┘
       │  ▲
 long  │  │ OK (pick cam) · Back
 OK    ▼  │
  ┌──────────────────────┐
  │   G R I D            │
  │   2×2 mosaic stream  │
  └──────────────────────┘
```

Plus three overlays that float above any route:
- **PIP** — small corner cam window, auto-dismisses
- **Toast** — 3-sec text strip near the top
- **Reconnect curtain** — full-screen scrim during stream errors (LIVE only)

`MainScene` also keeps a `module` route (the old per-card drill-down screen); nothing reaches it any more.

**Not built: BRIEFING and GLANCE.** The original design had a 60-second morning briefing scene (`?mode=briefing`) and a Roku-OS screensaver glance dashboard. Neither was built, and the home wall now does both jobs. `mode=briefing` only shows a "Briefing — coming soon" toast. The channel keeps the OS screensaver *away* instead: on home the camera card's live video (or a hidden 16×16 keep-awake clip when there is no camera card) counts as playback.

---

## Visual style

The home wall uses the tablet's v3 **smoked glass** (Barlow, MDI glyphs, night-tinted rounded cards, accent and alert states); see [Home](#home--the-glass-wall). Everything else — the LIVE and GRID chrome, overlays, toasts, splash and reconnect curtain — uses the original daylight palette below.

**Daylight palette.** Family-friendly, easy on the eyes, generally light. Warm rather than clinical (no cool greys). All text inside the title-safe rectangle. Hex format `0xRRGGBBAA` for SceneGraph (`HK_*()` in `roku/source/Config.brs`); the table below shows `#RRGGBB` for human reading.

| Token | Hex | Use |
|---|---|---|
| `bg.cream` | `#F7F1E3` | Reconnect curtain, overlay chips, grid labels; manifest `splash_color` |
| `bg.warm` | `#ECE3D0` | Warm card fill (defined; little used since BRIEFING/GLANCE were dropped) |
| `bg.scrim` | `#2B2A26CC` | HUD scrim over live video (warm dark, 80% alpha — legible over any frame) |
| `text.ink` | `#2B2A26` | Primary text on light backgrounds (warm near-black) |
| `text.cream` | `#FAF6EE` | Text on `bg.scrim` (HUD, toast) |
| `text.muted` | `#2B2A2699` | Secondary metadata on light backgrounds |
| `accent.brand` | `#5B8C7F` | Wordmark, focus rings, dot pager active dot |
| `accent.live` | `#D4673E` | LIVE pip, high-severity events (warm coral, not fire-engine red) |
| `accent.warn` | `#D9A441` | Doorbell, PIP border, attention-required (warm amber) |
| `accent.ok` | `#6B9080` | Connected dot, "all clear" motion indicator (sage green, distinct from brand) |

**Why this works over video**: the only chrome that floats over live video is the lower-third HUD and the `[LIVE]` pip. Both sit on `bg.scrim` (warm dark 80% alpha) so legibility is unaffected by the palette. The opaque surfaces (reconnect curtain, splash) are cream, so the light palette shows through cleanly.

**Splash + manifest** — `splash_color=#F7F1E3` (cream), splash image is the HAku wordmark logo letterboxed into cream. The brand mark (transparent PNG, `docs/brand/logo_wordmark.png`) is reused on the reconnect overlay and the seed background card; a separate 4:3 icon-only crop (`docs/brand/logo_icon.png`) drives the app icon tiles. All shipped brand image variants are emitted from source artwork by `roku/scripts/generate_brand_assets.py` — that script is the single source of truth for icon / splash / wordmark dimensions. (The glass and glyph art have their own generators; see `roku/CLAUDE.md`.)

**Typography (LIVE/GRID/overlays)**: built-in `MediumBoldSystemFont` for chrome (keeps cold-start fast and matches Roku 10-ft UI conventions); metadata in `SmallSystemFont`. Body text on light surfaces uses `text.ink`; on `bg.scrim` uses `text.cream`. All text inside the **title-safe rectangle**: `1534×866` centred at offset `(192, 106)` on a 1920×1080 canvas. The home wall uses bundled Barlow instead.

**Animation budget** — every transition under 250 ms or it feels broken on a 60 Hz panel:
- Fade-in / fade-out: **200 ms**
- HUD slide-in (lower-third): **180 ms** ease-out
- Camera swap crossfade: **220 ms**
- Overlay / PIP slide-in: **200 ms**
- Toast slide-from-top: **180 ms** in, **150 ms** out

**Focus rings**: 4 px outline in `accent.brand` `#5B8C7F`, glow `0 0 12 #5B8C7F40`. Brand sage carries the eye on either dark or light surface.

---

## Cameras

| ID | Friendly | Vendor | RTSP source | HLS | Maps to event sources |
|---|---|---|---|---|---|
| `front`    | Front Door | Genbolt | `rtsp://USER:PW@192.0.2.31:554/21` (HEVC → QSV H.264 720p) | `:1985/hls/front.m3u8`    | `front_doorcontact_contact`, `front_motion_occupancy` |
| `front_steps` | Front Steps | Genbolt | `rtsp://USER:PW@192.0.2.31:554/11` (fixed lens; HEVC → QSV H.264 720p) | `:1985/hls/front_steps.m3u8` | `front_motion_occupancy` (the home square switches to it, see [Home](#home--the-glass-wall)) |
| `yard`     | Yard       | Reolink | `rtsp://USER:PW@192.0.2.32:554/h264Preview_01_sub` | `:1985/hls/yard.m3u8`     | *none — no yard sensor in HA* |
| `side`     | Side Gate  | Amcrest | `rtsp://USER:PW@192.0.2.33:554/cam/realmonitor?channel=1&subtype=0` | `:1985/hls/side.m3u8`     | *none — no side sensor in HA* |
| `backyard` | Backyard   | Reolink | `rtsp://USER:PW@192.0.2.34:554/h264Preview_01_main` (2048×1536)    | `:1985/hls/backyard.m3u8` | `back_doorcontact_contact`, `backyard_motion_occupancy` (camera offline, see [Open items](#open-items)) |
| `mosaic`   | NVR 4-up   | (server) | NVR HDMI-out via USB capture → go2rtc QSV encode                     | `:1985/hls/mosaic.m3u8`   | (rendered, not a physical cam; GRID) |

Three URL conventions: the **Genbolt** uses `/21` for the PTZ lens (`front`, mounted sideways) and `/11` for the fixed lens on the steps (`front_steps`), both transcoded because the Express and Stick can't decode HEVC (see `stream/go2rtc.yaml`); the **Amcrest** (side) uses Dahua-style `cam/realmonitor?channel=N&subtype=0`; the **Reolinks** (yard, backyard) use `h264Preview_01_{main,sub}`. Every stream the Roku plays is H.264. Credentials come from `/etc/haku/cam-creds.env` on nserver (do **not** hard-code).

Order in the carousel (`HK_CAMS()`): `front → yard → side → backyard` (`front_steps` isn't in it; it only plays in the home square or on an explicit `cam=front_steps`) (front of house first, walking the perimeter clockwise — matches how the user thinks about the property). The same order is the GRID quadrant order.

---

## Home — the glass wall

The default route. A read-only 6×4 grid at 1920×1080 matching the kitchen tablet's v3 design, under a header (clock + date left, a status dot + word right). The layout is the sidecar's `layouts.roku` (`?layout=roku`), built from the tablet's modules by `tablet:` refs, each with its own `tile` position:

```
      c0         c1       c2   c3        c4   c5
r0   [ Doors (2×1)  ]    [ Calendar ]   [ Front    ]
r1   Laundry    Water    [          ]   [ (live)   ]
r2   Energy     Gas      [ Activity ]   [ Forecast ]
r3   Weather    Thermo   [          ]   [ 3-day +  ]
                                        [ 48 h     ]
```

- **Glass, minus the frost.** Roku has no live backdrop-blur, so each card is a night-tinted 9-patch over a sharp photo, with the tablet's glyphs, accents, lit/alert states, stale and offline treatments. The whole wall shifts ±2 px every 10 min against burn-in. Details: `roku/CLAUDE.md` § Visual theme.
- **Front camera, live.** The camera card (`tile.cam = "front"`) plays `streams.front.hls` muted in the 2×2 square and holds the Roku's one H.264 decoder while home is on screen. Every other route frees it first. After 4 errors in a row it shows "Camera offline" and rests for 5 min.
- **Front steps on motion.** HA's `homeCam=front_steps` push (front motion on for 5 s) points the square at the Genbolt's fixed lens; `homeCam=default` (motion clears) points it back. The switch takes ~1 s on most Rokus (the Kids Express can take ~30 s). The override lives on `HomeGroup.homeCam`, so it survives takeovers, is ignored for a stream discovery doesn't list (`hkHomeCam`), and clears itself after 15 min (`HK_HOME_CAM_MAX_MS`) if the revert never arrives.
- **Forecast.** A 3-day strip (`outlook`) over the sidecar's `weather_chart` PNG (48 h outdoor temperature: 24 h observed, 24 h forecast), re-fetched every 5 min.
- **Backgrounds.** Shared drone photos served by the sidecar from `HAKU_BG_DIR`, which `haku-bg-sync.timer` mirrors from the NAS every 15 min. The Roku asks `w=1920&h=1080&fit=cover`, rotates every 20 s by default (`background.intervalMs`) and re-reads the list every 10 min.
- **Read-only.** Home takes no remote input except `*` (diag) and Back (exit). An HA `focusModule=<id>` naming a non-camera card lights that card for 8 s instead of navigating.
- **Compatibility.** A Roku on 0.11 draws the same `layouts.roku` with 0.11's card bodies (the camera square is a placeholder), and channels before 0.13 ask for letterboxed (`contain`) photos. Channels before 0.11 use the sidecar's default view (no `?layout=`), which the sidecar keeps byte-for-byte stable.

---

## LIVE

Fullscreen single-camera HLS feed, reached by an HA camera takeover (`cam=…` or a camera `focusModule=`), `mode=grid` → OK, or from GRID. The **whole** screen is video; HUD floats over it.

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

**Lower-third HUD** (only chrome in LIVE):
- Bar height: **96 px**, full-width, `bg.scrim` (warm dark, 80% alpha)
- Left: **CAM NAME** in `MediumBoldSystemFont`, all-caps
- Centre-left: **prev/next arrows** + **dot pager** showing position in carousel (4 cams = 4 dots, current solid)
- Right: **status row** — connected dot (`accent.ok` = green / `accent.warn` = amber if buffering or reconnecting), latency in seconds
- Right-edge: **last-motion timestamp** ("motion 2 min ago") — pushed by HA via ECP `/input?lastMotion=<cam>&lastMotionAt=<unix>` (front and backyard only; no other cams have motion sensors)

**HUD auto-hide**: appears for **5 s** on camera switch / any remote press, then fades. A camera with no chrome is the goal state.

**[LIVE] pip** (top-left, always visible while playing): `accent.live` coral dot pulsing at 1 Hz, "LIVE" in `text.cream`. **Inside title-safe.** This is the only persistent indicator.

**Leaving LIVE**: Back returns home. A takeover that interrupted the home wall returns home on its own after **60 s** (`HK_RETURN_HOME_MS`) unless a key is pressed; any route other than home returns home after **5 min** without input (`HK_IDLE_TO_HOME_MS`).

**Reconnect curtain** (when player errors):
```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│                          ┌─────────────┐                             │
│                          │   [logo]    │   ◀─ brand mark, 500x100    │
│                          └─────────────┘                             │
│                                                                      │
│                       Stream error — retrying                        │
│                       attempt 2 in 5s                                │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```
`bg.cream` curtain at 95% alpha (calm pause, not alarm). Wordmark in `accent.brand`, label in `text.ink`, sub-label in `text.muted`. With no stream URL yet it reads "Waiting for discovery…".

---

## GRID

Reached by **long-press OK** (>500 ms) from LIVE, or `mode=grid` over ECP. The Roku decodes a single server-side mosaic stream (the NVR's own 4-up HDMI-out, captured and encoded on nserver) — *not* four parallel streams (Roku decoder budget = 1).

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

The video itself is one HLS stream from the server. The four labels and the focus ring are **client-side SceneGraph overlays** aligned to each quadrant. Quadrant labels render in `text.ink` on a 60%-alpha `bg.cream` rounded chip (not on the raw video) so they read on any cam content. D-pad moves the focus ring; **OK selects** that camera and transitions to LIVE on it; **Back** returns to LIVE on the previous cam. Focus ring: `accent.brand` 4 px + glow. The quadrant order assumes the NVR's split matches `HK_CAMS()`.

**Grid → Live transition**: the mosaic stream stops fully *before* the cam stream starts (no double-decoder window).

The motion indicators come from the same HA `lastMotion=` pushes as the HUD. `accent.live` (coral) double-dot for "recent motion (<5 min)", `accent.ok` (sage) single dot for "all clear". No client-side polling — HA pushes when state changes.

---

## Overlay layer

`OverlayLayer` is a single SceneGraph component that owns every transient information surface above the current route. It exists because (a) HAku is meant to be *insight into the walls of the house*, not just camera glass, and (b) SceneGraph has no native gradient or rounded-corner Rectangle, so the cards have to be pre-rendered PNGs and we wanted exactly one place that knows about them.

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

`severity` ∈ {`low`, `normal`, `high`} — drives the left-edge stripe colour using `hkSeverityColor()` (mirrors Toast). `dwell` / `duration` are seconds and override the default TTL.

The live HA config sends no `overlay=` pushes today (2026-10-14); the overlay kinds are exercised by the smoke test and available to any automation.

### Visual + perf notes

The four card backgrounds (scrim card, cream chip, PIP frame, top-fade gradient) are emitted by `roku/scripts/generate_brand_assets.py`. Total payload ~4.6 KB. SceneGraph performance budget is the binding constraint: each zone is a small `Group` (≤6 nodes) and animations are marked `optional` so the Roku Express / Stick can drop them under load. PIP refresh uses a one-shot `JpegPipTask` with a ping-pong `tmp:` slot pair so the `Poster` never reads a half-written file.

`severity=low` cam events (`cam=…&severity=low`) route automatically through `overlay=pip` — no separate HA wiring needed for "doorbell while watching another cam."

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

- Position: bottom-right corner, **inside action-safe**
- Size: **480 × 302** frame around a 472 × 266 image well (16:9)
- Border: `accent.warn`
- Header strip: 32 px tall, label + countdown
- Auto-dismisses at 0. It takes no keys: OK-to-promote and a dismiss key were designed but never built.

**Source — JPEG snapshot.** The PIP fetches `http://<server>:1984/api/frame.jpeg?src=<cam>` every 500 ms via a `JpegPipTask` (off render thread; `roUrlTransfer` returns binary, written to `tmp:/pip_<cam>_{a,b}.jpg`, driving a `Poster` via `uri` swap). Decodes nothing on the Roku, no second Video node, no decoder-budget risk — which matters more now that the home camera card already holds the decoder. Looks crisp at 480×270 for 30 s.

---

## Overlay 2 — Toast

Brief text notification. Appears top-centre, 3-second auto-dismiss (5 s minimum for `high`).

```
                  ┌─────────────────────────────────┐
                  │  ●  Front Door · motion         │
                  └─────────────────────────────────┘
```

- Width: 800 px, horizontally centred
- Position: 80 px from top
- 56 px tall, `bg.scrim` (warm dark), text in `text.cream`, 4 px left border in severity colour (`accent.live` high / `accent.warn` normal / `accent.ok` low)
- Slide in from top 180 ms, hold 3 s, slide out 150 ms

Used for: the banner of an HA camera takeover ("ATTN Back Door"), low-priority HA events, bootstrap confirmations ("Connected to Home Assistant", "Default cam: Front Door").

---

## Remote button map

Home is read-only, so the remote mostly matters once HA has put a camera up.

| Button | HOME | LIVE | GRID | DIAG |
|---|---|---|---|---|
| **◀ Left / ▶ Right** | — | prev / next cam (carousel wrap) | move grid focus | — |
| **▲ Up / ▼ Down** | — | show HUD | move grid focus | — |
| **OK** (tap) | — | toggle HUD visibility | select focused cam → LIVE | — |
| **OK** (long, >500ms) | — | enter GRID | — | — |
| **Back** | (OS) exits channel | → HOME | → LIVE on previous cam | → HOME |
| **Replay (↺)** | — | jump LIVE to `-15s` (replay) | — | — |
| **\* Options** | → DIAG | toggle audio mute for current cam | — | close |
| **Info** | — | toggle dim mode (HUD off, [LIVE] pip at 30%) | — | — |
| **Home** | (OS) exits channel | (OS) | (OS) | (OS) |

Any key that reaches `MainScene` cancels a takeover's automatic return home and restarts the idle timer.

Notable choices:
- **Replay** button is repurposed — it's the perfect button for "show me what just happened"
- **`*` = mute** in LIVE (the everyday lever). Toast-on-toggle was designed but the toggle only re-shows the HUD.
- **Audio default** — every stream starts muted; per-cam mute state persists in registry (`audioMuted_<cam>`), so turning on the front-cam audio sticks across sessions. The home camera card is always muted.
- **Back from HOME** exits the channel (matches Roku conventions — users expect Back at top level to leave)

---

## Event-driven flows

Three severities, three behaviours. HA decides the severity in the automation; HAku just reacts. A takeover from the home wall returns home after 60 s untouched; from GRID, any camera event falls back to LIVE on that cam (we yield decoder budget).

### High severity — "intruder", "back door at 2 am" — full takeover with replay

```
T+0 ms    HA fires: POST :8060/input?cam=backyard&replay=15&severity=high&reason=after+hours+door&banner=ATTN+Back+Door
T+30 ms   roInput message received in InputPumpTask
T+50 ms   MainScene.onInputEvent → dispatchEcp
T+60 ms   severity=high → takeover (return-home timer armed if we were on home)
T+80 ms   Toast slide-in: "● ATTN Back Door"  (coral border, 5s instead of 3)
T+100 ms  home camera card releases the decoder; LiveGroup content rebuilt with url=backyard.m3u8, playStart=-15
T+~1 s    playing, ~5 s behind live: the HLS window holds ~6 s, and the Roku starts at its oldest segment whatever playStart asks, so replay=15 gives no more pre-roll than a plain takeover
T+5.1s    Toast dismisses
T+60s     back to the home wall, unless someone pressed a key
```

### Normal severity — "door opened" — swap

```
T+0     POST /input?cam=front&severity=normal&replay=15&reason=opened&banner=Front+Door+opened
T+~50   Toast slide-in (3s)
T+~100  cam swap (playStart=-replay if given, else the live edge)
```

### Low severity — "doorbell pressed", "motion detected (low-traffic time)" — PIP, no swap

```
T+0     POST /input?cam=front&severity=low&duration=30&reason=doorbell&banner=Doorbell
T+~50   Toast slide-in: "● Doorbell"
T+~100  PIP (JPEG snapshot loop) appears in bottom-right with cam=front
T+30s   PIP auto-dismisses
```

### Other ECP keys

| Payload | Effect |
|---|---|
| `focusModule=<id>` (+ optional `cam`, `replay`) | A camera module takes over like `cam=`; any other module lights its home card for 8 s (`event=module_attention`); an unknown id with `cam=` still goes live. |
| `overlay=<kind>&…` | [Overlay layer](#overlay-layer); a complete signal, no fall-through to a cam swap. |
| `lastMotion=<cam>&lastMotionAt=<unix>` | Updates the HUD's and GRID's "motion N min ago". |
| `mode=home` / `mode=grid` | Go home / enter GRID. `mode=briefing` shows a "coming soon" toast. |
| `homeCam=<cam>` / `homeCam=default` | Points the home camera card at another discovery stream (`front_steps`) / back at its own `tile.cam`. No route change; can ride with any other key. |

`reason=` is informational (HA-side readability); the channel ignores it.

---

## Cold-launch flows

```
roku boot
   │
   └─→ user picks HAku (or /launch/dev from a dev box)
          │
          └─→ Main(args) → MainScene
                 │
                 ├─ registry fast-path: cached discovery streams, sidecar base and slimmed
                 │   config → the home wall paints immediately; DiscoveryTask (SSDP) runs
                 │   in the background and refreshes streams + sidecar base
                 │
                 ├─ → HOME
                 │
                 └─ then args, in order:
                       ├─ haToken (+ haUrl)  ─→  write registry, toast "Connected to Home Assistant"
                       ├─ hubBase            ─→  point the poller at another sidecar (cold launch only;
                       │                          a later discovery result wins)
                       ├─ setDefault=<cam>   ─→  write registry.defaultCam, toast
                       └─ cam / overlay / severity / mode / focusModule  ─→  dispatchEcp (as above)
```

**Default cam** (`?setDefault=<cam>`, per Roku, default `front`) is the camera LIVE opens on when a takeover names none (a camera `focusModule=` without `cam=`), and where GRID's Back lands before any cam has been shown.

**HA token bootstrap**: one-time deep-link `?contentId=setup&haToken=<token>&haUrl=http://mserver:8123` (URL-encoded — without encoding the `:` in `http://` the Roku returns 404) writes to the `haku` registry section, scrubbed from logs. Nothing in the channel reads the token any more: the sidecar is the only HAku part that talks to HA, with its own token in `/etc/haku/haku.env`.

---

## Home Assistant integration shape

HA talks to HAku two ways: the **sidecar pulls** everything the wall shows (one REST poll of `/api/states` every 1 s for the whole fleet, which the Rokus read every 1 s (2 s on the Express) and the tablet every 1 s, plus on-demand forecast, history and statistics reads), and HA **pushes events** to the Rokus over ECP `/input`. The push side is one package on mserver, `packages/housewall.yaml` (byte-for-byte copy in the repo at `roku/ha-housewall.yaml`); everything below summarizes it.

### Routing primitives

- `rest_command.housewall_living` / `_kids` / `_bedroom` / `_den` / `_office` — one POST to `http://<roku>:8060/input?{{ payload }}` per Roku, hardcoded LAN IP. **The payload goes in the URL:** ECP `/input` ignores a POST body. Until 2026-10-14 the package sent it as the body, so no HA push had ever reached a Roku. `_office` (the dev Roku `.55`) is broadcast-only.
- `sensor.housewall_active_service` (template sensor) — resolves to the `rest_command.housewall_*` for `sensor.jimi_phone_room`: `bedroom` → bedroom, `den` → den, everything else (kitchen, living, unknown, `not_home`) → living. With most ESPresense rooms offline it nearly always says living.
- `script.housewall_broadcast` — fires all 5 `rest_command.housewall_*` in parallel with the same payload (`continue_on_error`, so an off TV doesn't block the rest). The script is `mode: queued`: two broadcasts in the same instant (the heartbeat and the front-steps revert both fire when motion clears) run back to back. `single` drops the second, and overlapping POSTs to one Roku can reach the channel as one request's params twice.

### Three targeting modes — pick per automation

| Mode | Service to call | When to use |
|---|---|---|
| Specific Roku | `rest_command.housewall_<room>` | Room-specific events ("garage door → den TV only") |
| Active Roku (follow-me) | `"{{ states('sensor.housewall_active_service') }}"` | Door alerts, replays — anything you want to *see now* |
| Broadcast | `script.housewall_broadcast` | Ambient stuff, e.g. the motion-timestamp heartbeat |

### Live automations (five, checked 2026-10-14)

| Automation | Trigger | Payload (to the active Roku unless noted) |
|---|---|---|
| `housewall_front_steps_view` | front motion on for 5 s / clears, unavailable or HA start | `homeCam=front_steps` / `homeCam=default`, broadcast |
| `housewall_front_door_opened` | front door opens | `cam=front_steps&severity=normal&reason=opened&banner=Front+Door+opened`, to the **office Roku** only (`rest_command.housewall_office`). The tablet shows the same camera for the same minute through the sidecar's doors `takeover`, not a push |
| `housewall_after_hours_back_motion` | backyard motion, 22:00–06:00 | `cam=backyard&severity=high&replay=15&…&banner=ATTN+Backyard` |
| `housewall_after_hours_back_door` | back door opens, 22:00–06:00 | `cam=backyard&severity=high&replay=15&…&banner=ATTN+Back+Door` |
| `housewall_push_motion_timestamps` | front/backyard motion clears | `lastMotion=<cam>&lastMotionAt=<unix>`, broadcast |

Severity → stripe colour: `low → ok` (sage), `normal → warn` (amber), `high → live` (coral). The overlay pushes once planned for HA (door banners alongside the cam swap, a weather chip every 10 min, an energy spike >5 kW for a minute, water flowing >30 s) are not in the live config; the wall's cards now carry that information. Note that both `backyard` automations target a camera that is currently offline.

That's it on HA's side — one package file, no custom integration.

---

## Sidecar (`haku-sidecar`)

Python/Flask on nserver `:1986`, the data and rendering half of the server side; source and full API in `sidecar/` (`README.md`). Discovery's `sidecar.base` points the Rokus at it; the tablet has the address built in.

- **Routes**: `/api/config` (module descriptors from `/etc/haku/dashboard.json`), `/api/state` (one composed values snapshot), `/api/module/<id>`, `/api/detail/<id>` (tablet detail panels), `/api/card/<name>.png` (matplotlib/Pillow cards, e.g. `weather_chart`), `/api/icon/<id>.png`, `/api/backgrounds` + `/api/background/<name>`, `/api/health`.
- **The sidecar owns formatting.** Each module's `tile` carries display-ready `hero`/`sub`/`detail`/`severity` plus `glyph`, `active` and `level`; the clients lay out and draw. Unknown keys are ignored by both clients.
- **Layouts (`?layout=`).** The top-level `modules` list is the default view, served without the param to Roku channels before 0.11 and guarded byte-for-byte by `sidecar/tests/test_roku_golden.py`. The `layouts` map gives `tablet` and `roku` their own `grid`, `nightDim`, `background` and module list (`ref`s with shallow-merged overrides, plus layout-only modules such as `doors` and `laundry`). `/api/config` without the param never contains `layouts`, which keeps it clear of the Roku's ~16 KB registry cache. An unknown layout is a 404.
- **Backgrounds.** Every display reads `HAKU_BG_DIR` (`/etc/haku/backgrounds`), mirrored from the NAS folder `/mnt/media/haku/kitchen` every 15 min by `haku-bg-sync.timer` (`rsync --delete`; a run is skipped when the NAS is unmounted or empty). `/api/background/<name>` renders to the client's `w`×`h` with `fit=contain|cover` and `blur=0–40`, from an LRU sized for the whole photo set at every client size. Per-layout `background.dir` is still supported but unused.
- **Contract rule:** any change to its JSON must keep both clients working: the Roku golden test above, the Roku's `layout_contract.py`, and the tablet's fixture tests (`fire-tablet/app/src/test/resources/`).

---

## Camera pipeline (server side, nserver)

**Source of truth lives in this repo at `stream/`** — `go2rtc.yaml`, three systemd units plus the `haku-hls@` template, and the Python discovery service, with a `README.md` holding the deploy script. Encoding uses Intel Quick Sync (`h264_qsv`) since nserver has an Iris Plus G1 iGPU rather than NVIDIA. Lessons-learned baked in from the start: HLS remux sidecar (a 3 × 2 s window, addresses [go2rtc#1699](https://github.com/AlexxIT/go2rtc/issues/1699)), SSDP discovery so clients don't hard-code IPs, dedicated `media` user with `video,render` supplementary groups for QSV access. Boot order: `go2rtc` → `haku-hls*` → `haku-discovery`.

`go2rtc.yaml` runs five streams:

```yaml
streams:
  mosaic:    exec:ffmpeg … v4l2 MJPEG 1080p20 from the USB capture … h264_qsv main 4.0, GOP 40, 2.5 Mbps CBR
  front:     exec:ffmpeg … rtsp://${HAKU_FRONT_USER}:${HAKU_FRONT_PASSWORD}@192.0.2.31:554/21 … hevc_qsv → vpp_qsv 1280x720 → h264_qsv, GOP 30, ~2 Mbps
  yard:      rtsp://${HAKU_CAM_USER}:${HAKU_CAM_PASSWORD}@192.0.2.32:554/h264Preview_01_sub                   # Reolink — sub-stream (main is HEVC 4K)
  side:      rtsp://${HAKU_CAM_USER}:${HAKU_CAM_PASSWORD}@192.0.2.33:554/cam/realmonitor?channel=1&subtype=0  # Amcrest
  backyard:  rtsp://${HAKU_CAM_USER}:${HAKU_CAM_PASSWORD}@192.0.2.34:554/h264Preview_01_main                  # Reolink-family
```

Why not pre-merge per-cam streams into our own `xstack` mosaic? Because the NVR is already doing that 4-up split rendering, and capturing its HDMI-out is one decode pass instead of four. We get the mosaic for free.

Why transcode `front`? The Genbolt's PTZ lens only offers HEVC, which the Express and Stick can't decode; QSV decodes it, scales to 720p (which also feeds the full-screen takeover) and re-encodes to H.264 Main. It reads the camera directly, since an intermediate raw stream would show up in discovery.

Creds live in `/etc/haku/cam-creds.env` (mode 0640 root:media, never committed) and are substituted as `${HAKU_CAM_*}` / `${HAKU_FRONT_*}` in `go2rtc.yaml`. Each stream also gets:
- a `STREAM_METADATA` entry in `haku-discovery.py` (display name, vendor, codec, resolution, audio, ptz)
- a deep-HLS remux: `haku-hls.service` for the mosaic, a `haku-hls@<cam>.service` instance from the template for each camera, writing `<cam>.m3u8` + segments to `/run/haku-hls/` (both units keep `RuntimeDirectoryPreserve=yes` so one stopping doesn't delete the others' segments)
- a `streams.<cam>.hls = http://192.0.2.20:1985/hls/<cam>.m3u8` in `/discovery.json`

**Discovery is a contract with the Roku channel**: a shape change bumps `schemaVersion` in `haku-discovery.py`, `EXPECTED_SCHEMA_VERSION` in `roku/tests/contract/discovery_contract.py` and `HK_REG_CACHE_VER()` in `roku/source/Config.brs` together.

---

## State machine (formally)

```
routes   = { HOME, LIVE, GRID, DIAG }        (MODULE exists but is unreachable)
overlays = { PIP_active, TOAST_visible, RECONNECT_visible }
inputs   = { D-Pad, OK_tap, OK_long, Back, Replay, Star, Info, ECP_input, Timer, StreamError }

HOME × Star             → DIAG
HOME × Back             → (exit channel)
HOME × ECP(cam, sev=high|normal)   → LIVE (cam, replay if set) + return-home timer
HOME × ECP(focusModule=camera)     → LIVE + return-home timer
HOME × ECP(focusModule=other)      → HOME (card lit 8 s)

LIVE × Left/Right       → LIVE (cam = prev/next)
LIVE × OK_long          → GRID
LIVE × Replay           → LIVE (playStart = -15)
LIVE × Star             → LIVE (mute = !mute)
LIVE × Info             → LIVE (dim_mode = !dim_mode)
LIVE × Back             → HOME
LIVE × ECP(cam, sev=high|normal)   → LIVE (cam=event.cam, replay if set)
LIVE × StreamError      → LIVE +RECONNECT_visible (backoff escalation)

GRID × D-Pad            → GRID (focus moves)
GRID × OK               → LIVE (cam = focused)
GRID × Back             → LIVE (cam = previous)
GRID × ECP(cam)         → LIVE (event.cam) — abandon grid

DIAG × Star             → (dismiss)
DIAG × Back             → HOME

any  × ECP(sev=low, cam) → same route +PIP_active
any  × ECP(overlay=…)    → same route + overlay
any  × ECP(mode=home|grid) → HOME | GRID
LIVE|GRID|DIAG × Timer(idle 5 min)      → HOME
LIVE × Timer(60 s after a takeover from HOME, no key pressed) → HOME
```

PIP, Toast, Reconnect are independent timers/observers — they don't affect the route.

---

## Watchdog & reconnect

Per-cam exponential backoff with re-discovery escalation (`hkNextBackoffSeconds`), in `LiveGroup`:

```
error 1: wait 2 s, retry same URL
error 2: wait 5 s, retry same URL
error 3: wait 10 s, retry same URL
error 4: wait 30 s, retry same URL
error 5: clear streams → MainScene re-runs discovery (fresh SSDP), drops the registry cache, retries with the new URL
```

`reconnectOverlay` shows from the first error, sub-label "attempt N in Ns", and hides on the first `playing` state. Retry counters are per cam and survive cam switches, so a flaky cam doesn't keep healthy ones from backing off correctly. A separate watchdog restarts a stream stuck out of `playing` for >90 s.

The home camera card has its own simpler loop: the same backoff, then after 4 errors in a row "Camera offline" and a 5-minute rest before trying again.

---

## Status at 1.2

| Feature | Status |
|---|---|
| Home glass wall (6×4, sidecar `?layout=roku`, live front camera, forecast chart) | ✅ shipped |
| Shared drone-photo backgrounds (`HAKU_BG_DIR` + `haku-bg-sync`, `fit=cover`) | ✅ shipped |
| LIVE: 4-cam carousel, HUD with dot pager + last-motion, per-cam audio, replay | ✅ shipped |
| GRID via the NVR mosaic + long-press OK + focus overlay | ✅ shipped |
| Per-cam direct RTSP → deep HLS, discovery schema v2 | ✅ shipped (backyard camera offline) |
| ECP severity routing + replay + `focusModule=` takeovers with return-home | ✅ shipped |
| Overlay layer (door / text / weather / sensor / pip) | ✅ shipped in the channel; HA sends none today |
| HA push package (`housewall.yaml`, 5 Rokus, active-Roku selector, broadcast) | ✅ live since 2026-10-14 (before that no push reached a Roku); follow-me effectively always "living" until ESPresense rooms return |
| Front steps view on front motion (`front_steps`, `homeCam=`) | ✅ shipped (1.1) |
| Door open → steps full screen on the office Roku and the kitchen tablet; 1 s polling end to end | ✅ shipped (1.2) |
| Dim mode | built (bound to the Info key); never tuned |
| BRIEFING scene + morning automation | ❌ dropped (the home wall covers it) |
| GLANCE screensaver | ❌ dropped (the channel keeps the screensaver away instead) |
| PIP promote/dismiss keys | ❌ not built |
| Spotlight mode | ❌ dropped |

---

## Resolved decisions

1. **PIP source** — *JPEG snapshot.* PIP fetches `http://<server>:1984/api/frame.jpeg?src=<cam>` every 500 ms, written to `tmp:`, surfaced via a `Poster` node. Decodes nothing on the Roku, no second Video node, no decoder-budget risk. The Express and Stick couldn't run dual decoders anyway, and the home camera card already holds the one decoder.
2. **Camera count** — *4 cams.* `front` (192.0.2.31), `yard` (192.0.2.32), `side` (192.0.2.33), `backyard` (192.0.2.34). 2×2 grid is the right shape; no paging needed.
3. **Default cam per Roku** — stored in registry per Roku via one-time deep-link `?setDefault=<cam>`; unset means `front`. With the wall showing front live, it only matters for camera takeovers that name no cam.
4. **HA token bootstrapping** — one-time deep-link `?contentId=setup&haToken=…&haUrl=…`, written to `roRegistrySection("haku")`, scrubbed from logs. Kept for compatibility, but unused since the sidecar took over all HA reads.
5. **Brand identity** — *Daylight palette (cream / sage UI chrome) + the HAku house/camera-lens logo (blue/orange)* for the splash, icons, LIVE/GRID chrome and overlays; the home wall uses the tablet's glass instead. Splash colour `bg.cream` `#F7F1E3`. Two source art files: `docs/brand/logo_icon.png` (4:3, transparent, icon-only glyph) composited onto the cream 4:3 app-icon tile, and `docs/brand/logo_wordmark.png` (transparent, full icon+wordmark lockup) reused for the splash screen (letterboxed onto cream), the reconnect-overlay banner, and the seed background card (`sidecar/backgrounds/bg_00_haku_logo.jpg`, no longer in the live rotation since the NAS mirror). Family-friendly, easy on the eyes; explicitly *not* the dark-navy security-console look. `roku/scripts/generate_brand_assets.py` is the source of truth for asset dimensions, formats, and palette use.
6. **Audio** — *muted by default; `*` toggles per-cam audio in LIVE.* Roku TVs sit in living rooms with people watching other things; auto-playing camera audio is intrusive. PIP and the home camera card are *always* muted. Audio policy is per-cam, persisted in registry — turning it on for the front cam stays on for that cam across sessions.
7. **Read-only home** — the wall takes no navigation; cameras are reached by HA events, and the remote only matters once a camera is up. Matches the tablet's "no controls that change house state" rule.

## Out of scope

Deliberate non-goals, called out so they don't bleed into scope:

- **Grid > 4 cams** with paging or 3×3 layouts (the inventory is exactly 4 cams).
- **Real second-Video PIP** (the Express/Stick fleet has one decoder, and the home camera card uses it).
- **Spotlight mode** (focused cam at 1280×720 + thumbnail rail; sketched, never built, dropped).

## Tablet client (kitchen Fire 7)

HAku's second kind of display client is a native Android app (`io.haku.tablet`) on the kitchen wall Fire 7 (`192.0.2.60`), in **`fire-tablet/`**. It is a pure sidecar consumer: it polls `/api/config` + `/api/state` every 1 s (and `/api/detail/<id>` for its panels) with `?layout=tablet` over plain HTTP, gets no ECP pushes and holds no HA token. Its one video is the door camera: when the doors module carries a `takeover` (60 s after the front door opens), it plays `front_steps` full screen with a framework `VideoView` (`docs/fire-tablet/DESIGN.md` §8.11).

- **What it shows:** nine smoked-glass cards on a 4×3 grid over the shared drone photos, with fake frosted glass cut from a blurred copy (API 30 can't blur live): doors, laundry, calendar, activity, water, energy, weather, gas and thermostat. Taps open detail panels and a photo peek; nothing changes house state. Design: `docs/fire-tablet/DESIGN.md` (§8 v2 UI, §8.10 v3 touch); exact JSON shapes and visual values: `docs/superpowers/plans/2026-09-30-tablet-ui-v2-contract.md` and `docs/superpowers/specs/2026-10-01-tablet-v3-details-contract.md`.
- **Layout-only modules.** `doors` (open or closed per contact, with "since" taken from the logbook, because HA re-stamps `last_changed` on restart) and `laundry` (mirrors HA's `packages/laundry.yaml` sensors; the tablet draws the LED bar natively). The Roku wall reuses both through `tablet:` refs.
- **Backgrounds.** The tablet fetches a sharp `w=1024&h=600&fit=cover` copy and a soft `w=256&h=150&fit=cover&blur=8` copy of each photo from the same `HAKU_BG_DIR` the Rokus read.
- **Contract rule:** the tablet ignores unknown keys and falls back to a value card for unknown `tile.type`, the same forward-compatibility rule as the Roku's `hkModuleKind`. Any sidecar JSON change must keep both clients working. The tablet's JVM tests parse fixtures captured from the live sidecar (`fire-tablet/app/src/test/resources/`, `?layout=tablet`).

## Open items

Checked 2026-10-14 against HA's `/api/states` and a port probe:

- [ ] **`backyard` camera (.34) offline** — RTSP closed; the NVR can't reach it either. The after-hours back automations and GRID's bottom-right quadrant point at it.
- [ ] **ESPresense rooms** — only `office` reports, and `sensor.jimi_phone_room` is `not_home`/unmapped most of the time, so follow-me always lands on the living-room Roku.
- [ ] **`person.alex`** — `unknown`; that phone's tracker isn't reporting.
- [ ] **Gate, garage and backyard-corner sensors** — `binary_sensor.gate_doorcontact_contact`, `garage_doorcontact_contact` and `backyard_corner_motion_occupancy` no longer exist in HA, so yard and side have no event source.
- [ ] **Layout retry** — after a `layout_fallback` (sidecar answered 404 for `?layout=roku`) the channel stays on the default view until the next config fetch; retrying the layout on its own is parked.
- [ ] **Reconnect curtain on a fast takeover** — LIVE shows "Waiting for discovery…" at once when it has no stream URL yet; a ~400 ms debounce was suggested and never done.
- [ ] **HA token rotation** — the long-lived token seeded to the Rokus in May 2026 appeared in a chat transcript; rotate it in HA if that hasn't happened (nothing on the Roku reads it now).
- [ ] **Rotation order** — confirm `front → yard → side → backyard` matches the user's mental model and the NVR's quadrant order.
