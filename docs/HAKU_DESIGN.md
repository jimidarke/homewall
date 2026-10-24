# HAku — How It Works & How It Looks

> Sideloaded Roku channel. A glass wall of the home's numbers with the front camera playing live in one square, that cuts to the right camera full-screen when something happens and drifts back to the wall when it's over.

---

## North star

**HAku is the TV-shaped client for the home.** Most of the time it is a read-only wall of glass cards (doors, laundry, water, energy, gas, weather, thermostat, calendar, activity, a 3-day forecast with a 48 h temperature chart) over a rotating drone photo, with the front camera playing live in a 2×2 square. When the home has something to say, Home Assistant pushes it to the Rokus and HAku reacts: front motion turns every wall's camera square to the front steps, the front door opening puts the steps full-screen on every Roku, and the back door or backyard motion after hours cuts the active Roku to the backyard camera. A minute later, untouched, a takeover goes back to the wall. Lesser events can shoulder a small picture-in-picture into a corner instead of yanking you out of what you were watching.

It's a Roku channel because Rokus are the box that's already in every room. Home Assistant is the brain; HAku is just one of its faces. The kitchen wall's Fire 7 tablet is the other ([Tablet client](#tablet-client-kitchen-fire-7)).

> **Paths in this document.** Paths are in the `homewall` monorepo layout (`roku/`, `sidecar/`, `stream/`, `fire-tablet/`, `docs/`). The live HA config is on mserver at `/root/docker/homeassistantV3/config/ha/` (HA runs in Docker). HAku's push side is the package `packages/housewall.yaml` there ([Home Assistant integration shape](#home-assistant-integration-shape)); it predates the HAku name, so its entities are `housewall_*`. The sidecar-side helper packages are `electricity_cost.yaml`, `gas_cost.yaml`, `water_cost.yaml` and `haku_water.yaml`. There is no `packages/haku.yaml` or `rest_commands.yaml`. The current state of each part is in its own folder's README/CLAUDE.md.

> **Status (2026-10-14).** Roku 1.2.1 on all five Rokus (the four fleet Rokus and the office dev Roku), tablet 1.1.1, sidecar 1.1.0. The Rokus boot to the read-only 6×4 glass wall (spec `docs/superpowers/specs/2026-10-07-roku-wall-6x4-design.md`, baseline `docs/roku/screens/home.png`) over the shared drone photos (`…/2026-10-07-shared-backgrounds-design.md`). Front motion switches the camera square to the steps (`…/2026-10-14-front-steps-view-design.md`); the front door takes the office Roku and the kitchen tablet to the steps for a minute, and polling is 1 s end to end (`…/2026-10-14-door-camera-and-1s-polling-design.md`). The tablet runs its v3 touch UI.

> **v2 in progress (2026-10-24):** the next generation is designed in [superpowers/specs/2026-10-24-haku-v2-design.md](superpowers/specs/2026-10-24-haku-v2-design.md). This document describes v1, which stays live until the v2 cutover.

---

## Inventory (what's actually on the LAN)

**Network**: `192.0.2.0/24`, gateway `192.0.2.1`, domain `home.lan`.

**Cameras** (RTSP direct, bypassing the NVR's HDMI-capture path; URLs in [Cameras](#cameras)). Validated 2026-05-08 against Mikrotik DHCP leases and a TCP-port probe; port 554 re-probed 2026-10-14:

| Friendly | LAN IP | MAC | Vendor | Open ports | Notes |
|---|---|---|---|---|---|
| frontcam   | `192.0.2.31` | `xx:xx:xx:xx:xx:xx` | **Genbolt** dual-lens (XiongMai), WAN-blocked | 80, 554, 8080 (ONVIF) | PTZ lens `/21` (HEVC 1080p15, mounted sideways; `/22` sub) → `front`; fixed lens on the steps `/11` → `front_steps`. Own login (`HAKU_FRONT_*`). |
| yardcam    | `192.0.2.32` | `xx:xx:xx:xx:xx:xx` | **Reolink** PTZ (DHCP host-name `Back`) | 80, 554, 8000 | Main stream is HEVC 4K, so HAku uses the H.264 sub-stream |
| sidecam    | `192.0.2.33` | `xx:xx:xx:xx:xx:xx` | **Amcrest** (`<serial>`) | 80, 554, 37777 | |
| backyardcam| `192.0.2.34` | `xx:xx:xx:xx:xx:xx` | **Reolink-family IPC** | 80, 443, 554, 8000 | **Offline** (554 closed 2026-10-14; the NVR can't reach it either) |

Physical placement (confirmed 2026-05-08): .32 (HA's "Back Yard") is the Reolink PTZ on the house corner facing the back yard / drive pad / fence, mapped to `yard`; .34 is the no-PTZ Reolink-family behind the garage facing the playground, mapped to `backyard`. The old front Amcrest at `.35` is gone.

**NVR (16-channel)**: `192.0.2.30` `NVR-16` (OUI `xx:xx:xx`, Lorex/Dahua family) — ports 80, 554 open. Its HDMI-out 4-up split is the source of the `mosaic` stream. Its own RTSP (`rtsp://USER:PW@192.0.2.30:554/cam/realmonitor?channel={1..4}&subtype=0`) is a fallback if a per-cam path turns out to be flaky on a given firmware.

**nserver** (`192.0.2.20`) runs the camera pipeline ([Camera pipeline](#camera-pipeline-server-side-nserver)) and the sidecar ([Sidecar](#sidecar-haku-sidecar)). HA's `camera.camerafeed` (`mjpeg` integration entry `<config-entry-id>`) points at go2rtc's mosaic MJPEG, with snapshot `…/api/frame.jpeg?src=mosaic`. One Reolink is also integrated in HA directly (`camera.back_yard_fluent`); despite the name it is `yardcam` (.32).

**Roku fleet** — six Rokus run HAku, all dev-unlocked. The fleet doesn't auto-update: each runs whatever was last sideloaded.

| Friendly | LAN IP | Model | Notes |
|---|---|---|---|
| living | `192.0.2.51` | Roku Streaming Stick+ | HA's `media_player.living_room_roku`; `housewall_living_relaunch` brings HAku back from the home screen. |
| kids | `192.0.2.52` | Roku Express (3930) | USB-powered by the bedroom TV; reachability = TV-power state proxy in HA `packages/kids_tv.yaml`; `housewall_kids_relaunch` (via `media_player.kids_roku`) brings HAku back from the home screen |
| master | `192.0.2.53` | Roku Streaming Stick | HA calls it `bedroom` (`rest_command.housewall_bedroom`); `housewall_master_relaunch` (via `media_player.primary_bedroom_master_bedroom`) brings HAku back from the home screen. |
| den | `192.0.2.54` | Roku Express 4K (3940) | HA's `media_player.media_room_denroku`; `housewall_den_relaunch` brings HAku back from the home screen, like the office. |
| office | `192.0.2.55` | Roku Premiere+ | Dev box in the office, also a wall; HA's `housewall_office`, reached by the broadcasts. Its own dev password; the fleet's is `$ROKU_PW_FLEET`. |
| dad | `192.0.2.56` | Roku Streaming Stick (3840CA) | Added 2026-10-23 on 1.3.1. Dev password `$ROKU_PW_OFFICE`, like the office. ECP is in Limited mode: `/input`, `/launch` and `/query/active-app` work, but `/query/media-player` and `/keypress` are refused. Not in HA's Roku integration; `housewall_dad_relaunch` polls ECP to bring HAku back from the home screen. |

Not running HAku: a garage Roku was never seen on a scan.

**Kitchen tablet**: Fire 7 at `192.0.2.60` ([Tablet client](#tablet-client-kitchen-fire-7)).

**HA entities.** The sidecar's module→entity map is `/etc/haku/dashboard.json` on nserver (template `sidecar/dashboard.json.example`): weather (`weather.edmonton_forecast`), calendar (`calendar.family`), Emporia energy, the gas and water meter packages, the ecobee, door contacts and people. The push side (`housewall.yaml`) keys off:
- Door contacts: `binary_sensor.front_doorcontact_contact`, `back_doorcontact_contact`
- Motion: `binary_sensor.front_motion_occupancy`, `backyard_motion_occupancy`
- Presence (follow-me): `sensor.jimi_phone_room` (ESPresense)

**Coverage gap** — there's no `binary_sensor.yard_motion` or `binary_sensor.side_motion`; outdoor motion is only `front` and `backyard`. So door contacts and motion route to the *appropriate* cams rather than 1:1 cam-per-sensor.

---

## Routes

HAku has one resting screen and a few places HA (or the remote) can take it. Everything else is an overlay or a transient state.

```
        ┌──────────────────────────────────────┐
        │   H O M E   (default)                │
        │   6×4 glass wall + live front cam    │
        └──────────────────────────────────────┘
          │  ▲              │  ▲            │  ▲
 HA cam=  │  │ Back · 60 s  │  │ Back ·     │  │ Back
 takeover │  │ after a      OK │ 5 min      *  │
          │  │ takeover ·   │  │ idle       │  │
          │  │ 5 min idle   ▼  │            ▼  │
          │  │      ┌──────────────────┐ ┌──────────────────┐
          │  │      │   P I C K E R    │ │   D I A G        │
          │  │      │   camera list    │ │   device +       │
          │  │      │   over home      │ │   discovery + HA │
          │  │      └──────────────────┘ └──────────────────┘
          │  │               │
          │  │               │ OK: the picked camera
          ▼  │               │ (stays until Back, no idle)
  ┌──────────────────────┐   │
  │   L I V E            │ ◀─┘
  │   one camera,        │
  │   fullscreen, HUD    │
  └──────────────────────┘
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
| `bg.warm` | `#ECE3D0` | Warm card fill (defined, barely used) |
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

| ID | Friendly | Vendor | RTSP source | HLS | Event sources |
|---|---|---|---|---|---|
| `front`    | Front Door | Genbolt | `rtsp://USER:PW@192.0.2.31:554/21` (PTZ lens; HEVC → QSV H.264 720p) | `:1985/hls/front.m3u8`    | `front_motion_occupancy` (HUD/GRID motion label) |
| `front_steps` | Front Steps | Genbolt | `rtsp://USER:PW@192.0.2.31:554/11` (fixed lens; HEVC → QSV H.264 720p) | `:1985/hls/front_steps.m3u8` | `front_motion_occupancy` (home square, see [Home](#home--the-glass-wall)), `front_doorcontact_contact` (office Roku and tablet door camera) |
| `yard`     | Yard       | Reolink | `rtsp://USER:PW@192.0.2.32:554/h264Preview_01_sub` | `:1985/hls/yard.m3u8`     | *none — no yard sensor in HA* |
| `side`     | Side Gate  | Amcrest | `rtsp://USER:PW@192.0.2.33:554/cam/realmonitor?channel=1&subtype=0` | `:1985/hls/side.m3u8`     | *none — no side sensor in HA* |
| `backyard` | Backyard   | Reolink | `rtsp://USER:PW@192.0.2.34:554/h264Preview_01_main` (2048×1536)    | `:1985/hls/backyard.m3u8` | `back_doorcontact_contact`, `backyard_motion_occupancy` (camera offline, see [Open items](#open-items)) |
| `mosaic`   | NVR 4-up   | (server) | NVR HDMI-out via USB capture → go2rtc QSV encode                     | `:1985/hls/mosaic.m3u8`   | (rendered, not a physical cam; GRID) |

Three URL conventions: the **Genbolt** uses `/21` for the PTZ lens (`front`, mounted sideways, so it can't see the steps) and `/11` for the fixed lens on the steps (`front_steps`); the **Amcrest** (side) uses Dahua-style `cam/realmonitor?channel=N&subtype=0`; the **Reolinks** (yard, backyard) use `h264Preview_01_{main,sub}`. Every stream the Roku plays is H.264. Credentials come from `/etc/haku/cam-creds.env` on nserver (do **not** hard-code).

Carousel order (`HK_CAMS()`): `front → yard → side → backyard` — front of house first, walking the perimeter clockwise, which matches how the user thinks about the property. The same order is the GRID quadrant order. `front_steps` isn't in the carousel; it plays only in the home square or on an explicit `cam=front_steps`.

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
- **Front steps on motion.** HA's `homeCam=front_steps` broadcast (front motion on for 5 s) points the square at the Genbolt's fixed lens; `homeCam=default` (motion clears) points it back. The switch takes ~1 s on most Rokus (the kids Express can take ~30 s). The override lives on `HomeGroup.homeCam`, so it survives takeovers, is ignored for a stream discovery doesn't list (`hkHomeCam`), and clears itself after 15 min (`HK_HOME_CAM_MAX_MS`) if the revert never arrives.
- **Forecast.** A 3-day strip (`outlook`) over the sidecar's `weather_chart` PNG (48 h outdoor temperature: 24 h observed, 24 h forecast), re-fetched every 5 min.
- **Backgrounds.** The shared drone photos ([Sidecar](#sidecar-haku-sidecar)). The Roku asks `w=1920&h=1080&fit=cover`, rotates every 20 s by default (`background.intervalMs`) and re-reads the list every 10 min.
- **Almost read-only.** Home takes three keys: OK (the camera picker, below), `*` (diag) and Back (exit). An HA `focusModule=<id>` naming a non-camera card lights that card for 8 s instead of navigating.

### PICKER

OK on home opens a camera list over the wall (`CameraPicker`): every discovery stream with an HLS URL, in wall order (Front Door, Front Steps, Yard, Side Gate, Backyard), then any other stream alphabetically, then the NVR mosaic last; names come from discovery's `displayName` (`hkPickerCams`). The home camera square keeps playing behind it. Up/Down moves, OK plays that stream in LIVE, Back closes it. A camera picked here stays up until Back: the 5 min idle return is off for it (and for GRID reached from it) until the next return home. A forgotten open picker closes after 5 min. An HA takeover over the open picker behaves as one over home (back to the wall after 60 s).

---

## LIVE

Fullscreen single-camera HLS feed, reached by an HA camera takeover (`cam=…` or a camera `focusModule=`), a pick from the PICKER (including the NVR mosaic, full screen), `mode=grid` → OK, or from GRID. The **whole** screen is video; HUD floats over it.

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
- Right-edge: **last-motion timestamp** ("motion 2 min ago") from HA's `lastMotion=` broadcast (front and backyard only; no other cams have motion sensors)

**HUD auto-hide**: appears for **5 s** on camera switch / any remote press, then fades. A camera with no chrome is the goal state.

**[LIVE] pip** (top-left, always visible while playing): `accent.live` coral dot pulsing at 1 Hz, "LIVE" in `text.cream`. **Inside title-safe.** This is the only persistent indicator.

**Leaving LIVE**: Back returns home. A takeover goes back on its own after **60 s** (`HK_RETURN_HOME_MS`) unless a key is pressed, to the view it interrupted: home, or the camera (or GRID) being watched, so a camera picked by hand comes back after a door-open takeover (1.3.1, `hkTakeoverReturn`). A takeover landing on a takeover keeps the first view. Any route other than home returns home after **5 min** without input (`HK_IDLE_TO_HOME_MS`), except a camera picked from the picker.

**4 h stream stop**: Roku OS drops a channel to its home screen 4 h 00 m 31 s after the last stream start with no remote input (Bandwidth Saver; seen on the office Roku 2026-10-15..17, exit reason `EXIT_USER_NAV`). Every player (home square, LIVE, GRID) therefore starts its stream afresh after `HK_STREAM_REFRESH_S` (3 h) of playing, a ~1 s blip.

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
`bg.cream` curtain at 95% alpha (calm pause, not alarm). Wordmark in `accent.brand`, label in `text.ink`, sub-label in `text.muted`. With no stream URL yet it reads "Waiting for discovery…". Retry schedule: [Watchdog & reconnect](#watchdog--reconnect).

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

`severity=low` cam events (`cam=…&severity=low`) route through `overlay=pip` automatically, so "doorbell while watching another cam" needs no separate HA wiring.

The live HA package sends no `overlay=` pushes; the kinds are exercised by the smoke test and available to any automation. The ones once planned for HA (door banners alongside the cam swap, a weather chip every 10 min, an energy spike >5 kW for a minute, water flowing >30 s) are covered by the wall's cards.

### Visual + perf notes

The four card backgrounds (scrim card, cream chip, PIP frame, top-fade gradient) are emitted by `roku/scripts/generate_brand_assets.py`. Total payload ~4.6 KB. SceneGraph performance budget is the binding constraint: each zone is a small `Group` (≤6 nodes) and animations are marked `optional` so the Roku Express / Stick can drop them under load. PIP refresh uses a one-shot `JpegPipTask` with a ping-pong `tmp:` slot pair so the `Poster` never reads a half-written file.

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

**Source — JPEG snapshot.** The PIP fetches `http://<server>:1984/api/frame.jpeg?src=<cam>` every 500 ms via a `JpegPipTask` (off render thread; `roUrlTransfer` returns binary, written to `tmp:/pip_<cam>_{a,b}.jpg`, driving a `Poster` via `uri` swap). Decodes nothing on the Roku, no second Video node, no decoder-budget risk — which matters because the home camera card already holds the decoder. Looks crisp at 480×270 for 30 s.

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

On home the remote opens the camera picker or diag; it matters most once a camera is up.

| Button | HOME | PICKER | LIVE | GRID | DIAG |
|---|---|---|---|---|---|
| **◀ Left / ▶ Right** | — | — | prev / next cam (carousel wrap) | move grid focus | — |
| **▲ Up / ▼ Down** | — | move list focus | show HUD | move grid focus | — |
| **OK** (tap) | → PICKER | play focused cam → LIVE | toggle HUD visibility | select focused cam → LIVE | — |
| **OK** (long, >500ms) | — | — | enter GRID | — | — |
| **Back** | (OS) exits channel | → HOME | → HOME | → LIVE on previous cam | → HOME |
| **Replay (↺)** | — | — | restart at `-15 s` (in practice the oldest HLS segment, see [Event-driven flows](#event-driven-flows)) | — | — |
| **\* Options** | → DIAG | — | toggle audio mute for current cam | — | close |
| **Info** | — | — | toggle dim mode (HUD off, [LIVE] pip at 30%) | — | — |
| **Home** | (OS) exits channel | (OS) | (OS) | (OS) | (OS) |

Any key that reaches `MainScene` cancels a takeover's automatic return home and restarts the idle timer.

Notable choices:
- **`*` = mute** in LIVE (the everyday lever). Toast-on-toggle was designed but the toggle only re-shows the HUD.
- **Audio** — every stream starts muted; per-cam mute persists in the registry (`audioMuted_<cam>`); the home camera card is always muted ([Resolved decisions](#resolved-decisions) 6).
- **Back from HOME** exits the channel (matches Roku conventions — users expect Back at top level to leave)

---

## Event-driven flows

HA decides the severity in the automation; HAku reacts. `high` and `normal` take the screen (LIVE on that camera); `low` shows a PIP and leaves the screen alone. A takeover goes back to the view it interrupted (home, or the camera or GRID being watched) after 60 s untouched; from GRID, a camera event drops to LIVE on that cam (one decoder). Which automation sends what to which Roku: [Live automations](#live-automations).

### High severity — after-hours back door or backyard motion

```
T+0 ms    HA → active Roku: POST :8060/input?cam=backyard&severity=high&replay=15&reason=after+hours+door&banner=ATTN+Back+Door
T+30 ms   roInput message received in InputPumpTask
T+50 ms   MainScene.onInputEvent → dispatchEcp
T+60 ms   takeover (return-home timer armed if we were on home)
T+80 ms   Toast slide-in: "● ATTN Back Door"  (coral border, 5 s instead of 3)
T+100 ms  home camera card releases the decoder; LiveGroup plays backyard.m3u8 with playStart=-15
T+~1 s    playing, ~5 s behind live
T+5.1 s   Toast dismisses
T+60 s    back to the home wall, unless someone pressed a key
```

`replay=N` (like the Replay key) asks for `playStart=-N`, but the Roku starts at the oldest segment of the 3 × 2 s HLS window whatever it asks, so there is no pre-roll beyond the ~5 s the stream is already behind ([Camera pipeline](#camera-pipeline-server-side-nserver)).

### Normal severity — front door opened

```
T+0     HA → every Roku (broadcast): POST /input?cam=front_steps&severity=normal&reason=opened&banner=Front+Door+opened
T+~50   Toast slide-in (3 s)
T+~100  LIVE on front_steps at the live edge
T+60 s  back to the view it interrupted, unless someone pressed a key
```

The kitchen tablet shows the same camera for the same minute through the sidecar, not a push ([Sidecar](#sidecar-haku-sidecar)).

### Low severity — PIP, no swap

No live automation sends one. The wire format:

```
T+0     POST /input?cam=front&severity=low&duration=30&banner=Doorbell
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
| `homeCam=<cam>` / `homeCam=default` | Points the home camera card at another discovery stream / back at its own `tile.cam` ([Home](#home--the-glass-wall)). No route change; can ride with any other key. |

`reason=` is informational (HA-side readability); the channel ignores it. Every value arrives as a string; the channel parses numbers with `hkParseInt`.

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
                       └─ cam / overlay / severity / mode / focusModule / homeCam  ─→  dispatchEcp (as above)
```

**Default cam** (`?setDefault=<cam>`, per Roku, default `front`) is the camera LIVE opens on when a takeover names none (a camera `focusModule=` without `cam=`), and where GRID's Back lands before any cam has been shown.

**HA token bootstrap**: one-time deep-link `?contentId=setup&haToken=<token>&haUrl=http://mserver:8123` (URL-encoded — without encoding the `:` in `http://` the Roku returns 404) writes to the `haku` registry section, scrubbed from logs. Nothing in the channel reads the token any more: the sidecar is the only HAku part that talks to HA, with its own token in `/etc/haku/haku.env`.

---

## Home Assistant integration shape

HA talks to HAku two ways:

- **The sidecar pulls** everything the wall shows: one REST poll of `/api/states` every second for all clients, plus on-demand forecast, history, logbook and statistics reads ([Sidecar](#sidecar-haku-sidecar)). The Rokus poll the sidecar every 1 s, except the Roku Express 3930 (kids) at 2 s: at 1 s its camera square rebuffered and drifted up to 30 s behind live. The tablet polls every 1 s.
- **HA pushes events** to the Rokus over ECP `/input`. The push side is one package on mserver, `packages/housewall.yaml` (byte-for-byte copy in the repo at `roku/ha-housewall.yaml`; deploy steps in `roku/CLAUDE.md` § HA push side); everything below summarizes it. One package file, no custom integration.

### Routing primitives

- `rest_command.housewall_living` / `_kids` / `_bedroom` / `_den` / `_office` — one POST to `http://<roku>:8060/input?{{ payload }}` per Roku, hardcoded LAN IP. **The payload goes in the URL:** ECP `/input` ignores a POST body. `_office` (`.55`) is never picked by the active-Roku selector.
- `sensor.housewall_active_service` (template sensor) — resolves to the `rest_command.housewall_*` for `sensor.jimi_phone_room`: `bedroom` → bedroom, `den` → den, everything else (kitchen, living, unknown, `not_home`) → living. With most ESPresense rooms offline it nearly always says living.
- `script.housewall_broadcast` — fires all 5 `rest_command.housewall_*` in parallel with the same payload (`continue_on_error`, so an off TV doesn't block the rest). It is `mode: queued`: two broadcasts in the same instant (the heartbeat and the front-steps revert both fire when motion clears) run back to back. `single` would drop the second, and two POSTs landing on one Roku at once can reach the channel as one request's params twice.

### Three targeting modes — pick per automation

| Mode | Service to call | When to use |
|---|---|---|
| Specific Roku | `rest_command.housewall_<room>` | Room-specific events (none live) |
| Active Roku (follow-me) | `"{{ states('sensor.housewall_active_service') }}"` | Alerts you want to *see now* |
| Broadcast | `script.housewall_broadcast` | What every wall shares: ambient state (`homeCam=`, `lastMotion=`) and the front door takeover |

### Live automations

| Automation | Trigger | Target | Payload |
|---|---|---|---|
| `housewall_front_steps_view` | front motion on for 5 s / clears, unavailable or HA start | broadcast | `homeCam=front_steps` / `homeCam=default` |
| `housewall_front_door_opened` | front door opens | broadcast | `cam=front_steps&severity=normal&reason=opened&banner=Front+Door+opened` |
| `housewall_after_hours_back_motion` | backyard motion, 22:00–06:00 | active Roku | `cam=backyard&severity=high&replay=15&…&banner=ATTN+Backyard` |
| `housewall_after_hours_back_door` | back door opens, 22:00–06:00 | active Roku | `cam=backyard&severity=high&replay=15&…&banner=ATTN+Back+Door` |
| `housewall_push_motion_timestamps` | front/backyard motion clears | broadcast | `lastMotion=<cam>&lastMotionAt=<unix>` |

Severity → stripe colour: `low → ok` (sage), `normal → warn` (amber), `high → live` (coral).

---

## Sidecar (`haku-sidecar`)

Python/Flask on nserver `:1986`, the data and rendering half of the server side; source and full API in `sidecar/` (`README.md`). Discovery's `sidecar.base` points the Rokus at it; the tablet has the address built in.

- **Routes**: `/api/config` (module descriptors from `/etc/haku/dashboard.json`), `/api/state` (one composed values snapshot), `/api/module/<id>`, `/api/detail/<id>` (tablet detail panels), `/api/card/<name>.png` (matplotlib/Pillow cards, e.g. `weather_chart`), `/api/icon/<id>.png`, `/api/backgrounds` + `/api/background/<name>`, `/api/health`.
- **The sidecar owns formatting.** Each module's `tile` carries display-ready `hero`/`sub`/`detail`/`severity` plus `glyph`, `active` and `level`; the clients lay out and draw. Unknown keys are ignored by both clients.
- **Layouts (`?layout=`).** The top-level `modules` list is the default view, served without the param to Roku channels before 0.11 and guarded byte-for-byte by `sidecar/tests/test_roku_golden.py`. The `layouts` map gives `tablet` and `roku` their own `grid`, `nightDim`, `background` and module list (`ref`s with shallow-merged overrides, plus layout-only modules such as `doors` and `laundry`). `/api/config` without the param never contains `layouts`, which keeps it clear of the Roku's ~16 KB registry cache. An unknown layout is a 404.
- **HA poll and edges.** One poller (`HAKU_POLL_INTERVAL=1`) refreshes the whole `/api/states` snapshot every second, whatever the number of clients, and records each entity's off→on edges between snapshots (`HAClient.last_on`, dated by HA's `last_changed`).
- **Door camera takeover.** The tablet layout's `doors` module has a `camera` key (`{door: front, cam: front_steps, sec: 60}`): for 60 s after the front door's last off→on edge its values carry `takeover: {cam, hls, label, until}`. A door that opens and closes inside one poll is missed, one reason the poll runs every second. The Roku layout inherits the key through its `tablet:` ref and ignores it.
- **Backgrounds.** Every display reads `HAKU_BG_DIR` (`/etc/haku/backgrounds`), mirrored from the NAS folder `/mnt/media/haku/kitchen` every 15 min by `haku-bg-sync.timer` (`rsync --delete`; a run is skipped when the NAS is unmounted or empty). `/api/background/<name>` renders to the client's `w`×`h` with `fit=contain|cover` and `blur=0–40`, from an LRU sized for the whole photo set at every client size. Per-layout `background.dir` is still supported but unused.
- **Contract rule:** any change to its JSON must keep both clients working: the Roku golden test above, the Roku's `layout_contract.py`, and the tablet's fixture tests (`fire-tablet/app/src/test/resources/`).

---

## Camera pipeline (server side, nserver)

**Source of truth lives in this repo at `stream/`** — `go2rtc.yaml`, the `go2rtc`, `haku-hls` and `haku-discovery` units plus the `haku-hls@` template, and the Python discovery service, with a `README.md` holding the deploy script. Encoding uses Intel Quick Sync (`h264_qsv`) since nserver has an Iris Plus G1 iGPU rather than NVIDIA. go2rtc 1.9.x runs as a dedicated `media` user with `video,render` supplementary groups for QSV. Boot order: `go2rtc` → `haku-hls*` → `haku-discovery`.

- **Capture.** NVR HDMI-out → USB 3.0 capture card at `/dev/v4l/by-id/usb-MACROSILICON_USB3.0_Video_67807015-video-index0` (Macrosilicon `345f:2131`).
- **go2rtc** encodes the mosaic and serves every camera over RTSP (below).
- **Deep HLS.** `haku-hls.service` (mosaic) and `haku-hls@<cam>.service` (one per camera) are `ffmpeg -c copy` remuxes of go2rtc's RTSP into a 3 × 2 s rolling window in `/run/haku-hls/` (tmpfs; both units keep `RuntimeDirectoryPreserve=yes` so one stopping doesn't delete the others' segments). The Roku plays from the oldest listed segment, so the window is the latency: ~5 s behind live (`yard`, with a ~4 s camera GOP, ~11 s); measured 2026-10-14, see `stream/README.md`. This works around go2rtc's shallow-HLS underflow ([AlexxIT/go2rtc#1699](https://github.com/AlexxIT/go2rtc/issues/1699)); the Roku never plays go2rtc's built-in HLS.
- **Discovery.** `haku-discovery.service` (Python, stdlib-only) answers SSDP on UDP `239.255.255.250:1900` with ST=`urn:haku:service:dashboard:1`, and its HTTP server on `192.0.2.20:1985` serves the capability JSON (schema v2, with a `sidecar` block pointing at `:1986`) and the deep-HLS files.
- **Bandwidth.** ~2.56 Mbps per consumer for the mosaic (the old MJPEG passthrough was 78.7 Mbps); encoder load ~1–2% iGPU. The legacy `sendHDMI.service` / mjpg_streamer on `:8090` is stopped and disabled; its unit file stays on disk for a one-line rollback (`systemctl enable --now sendHDMI`).

`go2rtc.yaml` runs six streams:

```yaml
streams:
  mosaic:      exec:ffmpeg … v4l2 MJPEG 1080p20 from the USB capture … h264_qsv main 4.0, GOP 40 (2 s), no B-frames, 2.5 Mbps CBR
  front:       exec:ffmpeg … rtsp://${HAKU_FRONT_USER}:${HAKU_FRONT_PASSWORD}@192.0.2.31:554/21 … hevc_qsv → vpp_qsv 1280x720 → h264_qsv, GOP 30, ~2 Mbps
  front_steps: exec:ffmpeg … rtsp://${HAKU_FRONT_USER}:${HAKU_FRONT_PASSWORD}@192.0.2.31:554/11 … same transcode as front
  yard:        rtsp://${HAKU_CAM_USER}:${HAKU_CAM_PASSWORD}@192.0.2.32:554/h264Preview_01_sub                   # Reolink — sub-stream (main is HEVC 4K)
  side:        rtsp://${HAKU_CAM_USER}:${HAKU_CAM_PASSWORD}@192.0.2.33:554/cam/realmonitor?channel=1&subtype=0  # Amcrest
  backyard:    rtsp://${HAKU_CAM_USER}:${HAKU_CAM_PASSWORD}@192.0.2.34:554/h264Preview_01_main                  # Reolink-family
```

All endpoints are served on `enp1s0` IP `192.0.2.20` (`<cam>` ∈ `mosaic`, `front`, `front_steps`, `yard`, `side`, `backyard`):

| Endpoint | URL | Use |
|---|---|---|
| SSDP discovery | multicast `239.255.255.250:1900` ST=`urn:haku:service:dashboard:1` | Roku auto-discovers — no hard-coded IP |
| Capability JSON | `http://192.0.2.20:1985/discovery.json` | Versioned payload: per-stream RTSP/HLS/MJPEG/snapshot URLs + the sidecar base |
| **Roku channel uses** | `http://192.0.2.20:1985/hls/<cam>.m3u8` | Deep HLS, Roku's hardware H.264 decode path (per-cam for the camera card and LIVE, `mosaic` for GRID) |
| HLS shallow | `http://192.0.2.20:1984/api/stream.m3u8?src=<cam>` | Browsers, debugging — go2rtc native (~1 s buffer) |
| RTSP | `rtsp://192.0.2.20:8554/<cam>` | HA `Stream` integration, VLC, ffmpeg |
| MJPEG | `http://192.0.2.20:1984/api/stream.mjpeg?src=<cam>` | HA `mjpeg:` (`camera.camerafeed`) |
| WebRTC preview | `http://192.0.2.20:1984/stream.html?src=<cam>` | Sub-second-latency in-browser viewing |
| **PIP snapshot** | `http://192.0.2.20:1984/api/frame.jpeg?src=<cam>` | HAku PIP fetches this every 500 ms (~196 KB JPEG for the mosaic) |
| Status UI | `http://192.0.2.20:1984/` | Live consumers, bandwidth |

Why not pre-merge per-cam streams into our own `xstack` mosaic? Because the NVR is already doing that 4-up split rendering, and capturing its HDMI-out is one decode pass instead of four. We get the mosaic for free.

Why transcode the Genbolt? Both its lenses only offer HEVC, which the Express and Stick can't decode; QSV decodes it, scales to 720p (which also feeds the full-screen takeover) and re-encodes to H.264 Main. Each stream reads the camera directly, since an intermediate raw stream would show up in discovery. `haku-hls@front_steps` keeps the steps stream running so a `homeCam=` switch never waits for a cold start.

Creds live in `/etc/haku/cam-creds.env` (mode 0640 root:media, never committed) and are substituted as `${HAKU_CAM_*}` / `${HAKU_FRONT_*}` in `go2rtc.yaml`. Each stream also gets:
- a `STREAM_METADATA` entry in `haku-discovery.py` (display name, vendor, codec, resolution, audio, ptz)
- a deep-HLS remux: `haku-hls.service` for the mosaic, a `haku-hls@<cam>.service` instance for each camera, writing `<cam>.m3u8` + segments to `/run/haku-hls/`
- a `streams.<cam>.hls = http://192.0.2.20:1985/hls/<cam>.m3u8` in `/discovery.json`

**Discovery is a contract with the Roku channel**: a shape change bumps `schemaVersion` in `haku-discovery.py`, `EXPECTED_SCHEMA_VERSION` in `roku/tests/contract/discovery_contract.py` and the `HK_REG_KEY_DISCOVERY()` registry key name in `roku/source/Config.brs` together.

---

## State machine (formally)

```
routes   = { HOME, PICKER, LIVE, GRID, DIAG }        (MODULE exists but is unreachable)
overlays = { PIP_active, TOAST_visible, RECONNECT_visible }
inputs   = { D-Pad, OK_tap, OK_long, Back, Replay, Star, Info, ECP_input, Timer, StreamError }

HOME × Star             → DIAG
HOME × OK               → PICKER (no cameras discovered: toast, stay HOME)
PICKER × D-Pad          → PICKER (list focus moves)
PICKER × OK             → LIVE (cam = focused), no idle return until HOME
PICKER × Back           → HOME
PICKER × ECP(cam, sev=high|normal) → LIVE + return-home timer (as from HOME)
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
any  × ECP(homeCam=…)    → same route; home camera card's stream changes
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

## Feature status

| Feature | Status |
|---|---|
| Home glass wall (6×4, sidecar `?layout=roku`, live front camera, forecast chart) | ✅ |
| Shared drone-photo backgrounds (`HAKU_BG_DIR` + `haku-bg-sync`, `fit=cover`) | ✅ |
| Front steps view on front motion (`front_steps`, `homeCam=`) | ✅ |
| Door camera: front door → steps full screen on every Roku and the kitchen tablet | ✅ |
| 1 s polling end to end (2 s on the Roku Express) | ✅ |
| LIVE: 4-cam carousel, HUD with dot pager + last-motion, per-cam audio, Replay (limited to the HLS window) | ✅ |
| GRID via the NVR mosaic + long-press OK + focus overlay | ✅ |
| Camera picker: OK on home → list of every camera + the NVR mosaic → full screen until Back | ✅ (Roku 1.3.0) |
| Per-cam direct RTSP → deep HLS, discovery schema v2 | ✅ (backyard camera offline) |
| ECP severity routing + `focusModule=` takeovers with return-home | ✅ |
| HA push package (`housewall.yaml`, 6 Rokus, active-Roku selector, queued broadcast) | ✅; follow-me effectively always "living" ([Open items](#open-items)) |
| Overlay layer (door / text / weather / sensor / pip) | ✅ in the channel; HA sends none |
| Dim mode | built (bound to the Info key); never tuned |

Dropped or never built: BRIEFING and GLANCE ([Routes](#routes)), PIP promote/dismiss keys ([PIP](#overlay-1--pip-picture-in-picture)), Spotlight ([Out of scope](#out-of-scope)).

---

## Resolved decisions

1. **PIP source** — *JPEG snapshot*, not a second Video node ([PIP](#overlay-1--pip-picture-in-picture)). The Express and Stick couldn't run dual decoders anyway, and the home camera card already holds the one decoder.
2. **Camera count** — *4 cams* in the carousel and GRID: `front`, `yard`, `side`, `backyard`. 2×2 is the right shape; no paging needed. `front_steps` is the front camera's second lens, used by the home square, the door takeover and the OK picker (which also lists the mosaic).
3. **Default cam per Roku** — stored in the registry per Roku via one-time deep-link `?setDefault=<cam>`; unset means `front`. With the wall showing front live, it only matters for camera takeovers that name no cam.
4. **HA token bootstrapping** — the one-time deep-link ([Cold-launch flows](#cold-launch-flows)) is kept for compatibility, but unused: the sidecar does all HA reads.
5. **Brand identity** — *Daylight palette (cream / sage UI chrome) + the HAku house/camera-lens logo (blue/orange)* for the splash, icons, LIVE/GRID chrome and overlays; the home wall uses the tablet's glass instead. Family-friendly, easy on the eyes; explicitly *not* the dark-navy security-console look. Assets and dimensions: [Visual style](#visual-style). The seed background card (`sidecar/backgrounds/bg_00_haku_logo.jpg`) is not in the live rotation, which comes from the NAS mirror.
6. **Audio** — *muted by default; `*` toggles per-cam audio in LIVE.* Roku TVs sit in living rooms with people watching other things; auto-playing camera audio is intrusive. PIP and the home camera card are *always* muted. Audio policy is per-cam, persisted in registry — turning it on for the front cam stays on for that cam across sessions.
7. **Read-only home** — the wall takes no navigation; cameras are reached by HA events or the OK camera picker (1.3.0), and otherwise the remote only matters once a camera is up. Matches the tablet's "no controls that change house state" rule.

## Out of scope

Deliberate non-goals, called out so they don't bleed into scope:

- **Grid > 4 cams** with paging or 3×3 layouts (the inventory is exactly 4 cams).
- **Real second-Video PIP** (the Express/Stick fleet has one decoder, and the home camera card uses it).
- **Spotlight mode** (focused cam at 1280×720 + thumbnail rail; sketched, never built, dropped).

## Tablet client (kitchen Fire 7)

HAku's second kind of display client is a native Android app (`io.haku.tablet`) on the kitchen wall Fire 7 (`192.0.2.60`), in **`fire-tablet/`**. It is a pure sidecar consumer: it polls `/api/config` + `/api/state` (and `/api/detail/<id>` for its panels) with `?layout=tablet` over plain HTTP, gets no ECP pushes and holds no HA token. Its one video is the door camera: while the doors module carries a `takeover` ([Sidecar](#sidecar-haku-sidecar)), it plays `front_steps` full screen with a framework `VideoView` (`docs/fire-tablet/DESIGN.md` §8.11).

- **What it shows:** nine smoked-glass cards on a 4×3 grid over the shared drone photos, with fake frosted glass cut from a blurred copy (API 30 can't blur live): doors, laundry, calendar, activity, water, energy, weather, gas and thermostat. Taps open detail panels and a photo peek; nothing changes house state. Design: `docs/fire-tablet/DESIGN.md` (§8 v2 UI, §8.10 v3 touch); exact JSON shapes and visual values: `docs/superpowers/plans/2026-09-30-tablet-ui-v2-contract.md` and `docs/superpowers/specs/2026-10-01-tablet-v3-details-contract.md`.
- **Layout-only modules.** `doors` (open or closed per contact, with "since" taken from the logbook, because HA re-stamps `last_changed` on restart) and `laundry` (mirrors HA's `packages/laundry.yaml` sensors; the tablet draws the LED bar natively). The Roku wall reuses both through `tablet:` refs.
- **Backgrounds.** The tablet fetches a sharp `w=1024&h=600&fit=cover` copy and a soft `w=256&h=150&fit=cover&blur=8` copy of each photo from the same `HAKU_BG_DIR` the Rokus read.
- **Contract rule:** the tablet ignores unknown keys and falls back to a value card for unknown `tile.type`, the same forward-compatibility rule as the Roku's `hkModuleKind`. The tablet's JVM tests parse fixtures captured from the live sidecar (`fire-tablet/app/src/test/resources/`, `?layout=tablet`).

## Open items

Checked 2026-10-14 against HA's `/api/states`, a port probe and nserver's units:

- [ ] **`backyard` camera (.34) offline** — RTSP closed; the NVR can't reach it either, and `haku-hls@backyard` restarts in a loop until it returns. Both after-hours back automations and GRID's bottom-right quadrant point at it.
- [ ] **ESPresense rooms** — only `office` reports, and `sensor.jimi_phone_room` is `not_home`/unmapped most of the time, so follow-me always lands on the living-room Roku.
- [ ] **`person.alex`** — `unknown`; that phone's tracker isn't reporting.
- [ ] **Gate, garage and backyard-corner sensors** — `binary_sensor.gate_doorcontact_contact`, `garage_doorcontact_contact` and `backyard_corner_motion_occupancy` no longer exist in HA, so yard and side have no event source.
- [ ] **Orphaned `automation.housewall_front_motion`** — the removed front-motion takeover still has an `unavailable` entry in HA's entity registry; delete it.
- [ ] **Layout retry** — after a `layout_fallback` (sidecar answered 404 for `?layout=roku`) the channel stays on the default view until the next config fetch; retrying the layout on its own is parked.
- [ ] **Reconnect curtain on a fast takeover** — LIVE shows "Waiting for discovery…" at once when it has no stream URL yet; a ~400 ms debounce was suggested and never done.
- [ ] **HA token rotation** — the long-lived token seeded to the Rokus in May 2026 appeared in a chat transcript; rotate it in HA if that hasn't happened (nothing on the Roku reads it now).
- [ ] **Rotation order** — confirm `front → yard → side → backyard` matches the user's mental model and the NVR's quadrant order.
