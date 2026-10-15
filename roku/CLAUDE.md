# CLAUDE.md — roku/

The **HAku Roku channel**: BrightScript + SceneGraph, packaged as `haku.zip` and sideloaded onto the wall Rokus. It boots to a **read-only glass wall** in the kitchen tablet's v3 design: a 6×4 grid of landscape cards (Doors 2×1, the other value tiles 1×1, Calendar and Activity 2×2, a 2×2 Forecast with the sidecar's 48 h temperature chart, and a 2×2 square playing the **front PTZ camera live**). Home takes no input; HA pushes can take over the screen with a full-screen live camera.

Data comes two ways from Home Assistant (mserver, 192.0.2.10): the **sidecar** (`../sidecar/`, `../sidecar/CLAUDE.md`) pulls the glance values and serves config/state JSON and PNG cards, and HA **pushes events** straight to each Roku over ECP `/input` (see HA push side). Camera streams and discovery come from `../stream/`. Repo overview: `../CLAUDE.md`; full design: `../docs/HAKU_DESIGN.md`.

## Commands

All `npm` scripts run from `roku/`:

```bash
npm run lint            # bsc --noEmit (first step of every gate)
npm run build           # bsc: stage + transpile into out/.staging (no zip)
npm run package         # bsc --create-package -> dist/haku.zip (unsigned)
npm run test:unit       # brs runs source/Config.brs + Glyphs.brs + tests/unit/test_pure.brs; run.js fails on any FAIL
npm run test:contract   # discovery_contract.py + layout_contract.py against live discovery / sidecar ?layout=roku
HAKU_FIXTURE=1 npm run test:contract   # offline, against tests/fixtures/
npm test                # lint + unit + contract (no smoke: smoke needs a Roku)
npm run test:smoke      # tests/smoke/smoke.sh (below)
npm run deploy          # scripts/deploy.js: roku-deploy zips to dist/haku.zip and sideloads it
npm run clean           # rm -rf dist out
```

**Unit tests**: `tests/unit/test_pure.brs` is one file printing `OK …`/`FAIL …` and a final `RESULT pass=N fail=M`; there is no single-test runner, so comment cases out to focus or add an `assertEq` block.

**Smoke test (real Roku)**: `tests/smoke/smoke.sh` runs lint + unit + the fixture discovery contract, sideloads, cold-relaunches, then over ECP drives a camera takeover (`focusModule=cameras&cam=front&severity=high`), a `Right` keypress on the live view, HA's real door-open (`cam=…&replay=15`) and heartbeat (`lastMotion=`) payloads, four overlays (weather/door/sensor/text), `mode=home`, and `homeCam=front_steps` then `homeCam=default`, while tailing the console. It asserts `event=launch`, `route to=home`, `route … to=live`, `stream_start`, ≥2 `cam_switch`, ≥3 distinct `overlay_show kind=`, `home_cam_override cam=front_steps`, and no BrightScript runtime error (a crashed sideload freezes in the debugger). Exit codes are listed at the top of the script.

```bash
ROKU_IP=192.0.2.55 ROKU_DEV_PASSWORD=$ROKU_PW_OFFICE tests/smoke/smoke.sh
SMOKE_TIMEOUT=60 ROKU_IP=… ROKU_DEV_PASSWORD=… tests/smoke/smoke.sh   # longer window
```

**Console**: `nc <ROKU_IP> 8085`. It takes one client at a time; if a capture is empty, look for a stray reader (`ss -tnp | grep 8085`). The channel logs structured `[HAku] event=<name> k=v…` lines (`hkEvent()`), which smoke greps.

**Hot deep-link**: the manifest sets `supports_input_launch=1`, so ECP `/input` reaches the running channel through `InputPumpTask` with no relaunch:

```bash
curl -X POST -d '' "http://<ROKU_IP>:8060/input?cam=front&severity=normal&banner=Test"
curl -X POST -d '' "http://<ROKU_IP>:8060/input?overlay=weather&temp=8&hi=14&cond=cloudy"
curl -X POST -d '' "http://<ROKU_IP>:8060/launch/dev?haToken=$HA_TOKEN&haUrl=$HA_URL"   # cold launch only
```

Launch args (`haToken`/`haUrl`, `hubBase`, `setDefault`) are read only on a cold `/launch/dev`; sent to a running channel they arrive as input and are ignored. A discovered `sidecar.base` overrides `hubBase` anyway.

## Deploy

`ROKU_IP=<ip> ROKU_DEV_PASSWORD=<pw> npm run deploy` (roku-deploy posts to `http://<ip>/plugin_install` as `rokudev`).

| Roku | IP | Model note |
|---|---|---|
| living | `192.0.2.51` | Stick+ |
| kids | `192.0.2.52` | Express 3930 (polls at 2 s) |
| master (HA: `bedroom`) | `192.0.2.53` | Stick |
| den | `192.0.2.54` | Express 4K |
| office (dev) | `192.0.2.55` | Premiere+, also a wall |

- The dev password is `$ROKU_PW_FLEET` on every Roku except the office `.55`, which uses `$ROKU_PW_OFFICE`.
- **Before sideloading a wall Roku, check what it's showing**: `curl -s http://<ip>:8060/query/active-app`. Skip any TV not on HAku (`<app id="dev" …>HAku</app>`): a sideload relaunches the channel over whatever is playing.
- Nothing auto-updates: each Roku runs whatever was last sideloaded. Check `/query/apps` (or the console's `event=launch`) rather than assuming.
- Stream server deploy: `../stream/README.md` § Deploy. Sidecar deploy: `../sidecar/CLAUDE.md`.

## Architecture

A small SceneGraph state machine. The thread boundary matters:

```
main.brs  ──creates──▶ MainScene  (render thread; routes: home·live·grid·module·diag; key handling)
                            │
                            ├─ DiscoveryTask      (SSDP + discovery.json fetch, incl. the `sidecar` block)
                            ├─ InputPumpTask      (blocks on roInput, fans roInputEvent into m.top.event)
                            ├─ ModulePollTask     (sidecar /api/config while pending + /api/state every poll)
                            ├─ BackgroundListTask (sidecar /api/backgrounds -> photo URLs)
                            ├─ DiagHealthTask     (sidecar /api/health for the diag screen)
                            ├─ keepAwake          (hidden 16×16 silent Video; holds off the OS screensaver)
                            ├─ BackgroundGallery  (rotating full-screen photo behind the cards)
                            ├─ HomeGroup          (DEFAULT route: header + ModuleTiles)
                            │    └─ ModuleTile    (one glass card; body by hkCardKind: ValueBody|DoorsBody|
                            │                      LaundryBody|AgendaBody|ForecastBody|CameraBody (live HLS))
                            ├─ LiveGroup          (HA camera takeovers: single-cam HLS, carousel + chevrons, Hud)
                            ├─ GridGroup          (long-press OK from live: 2×2 mosaic + focus ring)
                            ├─ ModuleScreen       (old drill-down; nothing routes to it)
                            ├─ DiagScreen         (`*`/options from home: device, discovery, HA status)
                            ├─ OverlayLayer       (door / text / weather / sensor / pip transient alerts)
                            └─ Toast              (top-centre notifier, queued)
```

**Render thread vs Task thread**: anything blocking (SSDP, URL transfers, the JPEG loop) lives in a Task component. Tasks talk to the scene only through `alwaysNotify=true` fields the scene observes; never call `findNode`/`setFocus` from a Task.

### Routes

`MainScene` routes between `m.route` ∈ home/live/grid/module/diag and boots to `home`. Home is **read-only**: `HomeGroup` has no `onKeyEvent`, so keys bubble to `MainScene.onKeyEvent`, where `*`/options → `goDiag()` and Back exits (or climbs to home from another route). Live/grid are reached only by HA takeovers; `goModule` exists but nothing calls it.

Each transition focuses its own group (`goHome` → `m.home`, `goLive` → `m.live`, `enterGrid` → `m.grid`, `goDiag` → `m.diag`), because live/grid/diag keys are handled by `onKeyEvent` on `LiveGroup`/`GridGroup`/`DiagScreen`. Focus left on the Scene breaks them; smoke's "Right after the takeover must `cam_switch`" assertion catches that.

**Idle / auto-takeover**: a camera takeover (`cam=`, or a `focusModule=` naming the cameras module) goes live from home and `returnHomeTimer` brings it back after `HK_RETURN_HOME_MS` (60 s); any other `focusModule=` only lights that card for 8 s (`HomeGroup.attention`, `event=module_attention`). Any bubbled keypress cancels the takeover; `idleTimer` returns live/grid/module/diag to home after `HK_IDLE_TO_HOME_MS` (5 min).

### One video decoder

Roku has a single hardware H.264 decoder and four Video nodes (keepAwake, CameraBody, LiveGroup, GridGroup); never let two play at once. Live video is gated by `LiveGroup.cam`, which home/module/diag leave `""`. On home, `CameraBody` owns the decoder: `MainScene.syncHomeDecoder()` (from `goHome` and when `HomeGroup.hasCam` changes) stops the keep-awake clip and sets `HomeGroup.camActive`, which reaches the body through `ModuleTile`. `goLive`/`enterGrid`/`goModule`/`goDiag` clear `camActive` first, and `enterGrid()` also stops the live player (`stopLivePlayer()`) before `grid.active = true`.

Roku has no API to disable the screensaver; only playback holds it off. So with no playable camera card on home, and on module/diag, the hidden keep-awake Video plays (`startKeepAwake()`/`stopKeepAwake()`, toggled with `setBackdrop()`); it's stopped before any live/mosaic stream starts.

Streams must be H.264: the Express and Stick can't decode HEVC, which is why go2rtc transcodes both Genbolt lenses (`../stream/go2rtc.yaml`).

### Home camera

`CameraBody` plays `streams[cam].hls` muted, fitted 16:9 (`hkVideoFit`), backing off on `hkNextBackoffSeconds`. After 4 errors in a row it shows "Camera offline" and rests 5 min playing the keep-awake clip on its own Video node, shrunk to 2 px (a Video punches a black hole at any opacity), so there's still one decoder and no screensaver. It logs `event=home_cam state=…`.

HA's `homeCam=<cam>` push (front motion → `front_steps`) sets `HomeGroup.homeCam`, which reaches the body as `camOverride`. `hkHomeCam` honours it only for a stream discovery lists, else uses the tile's own `tile.cam`. The override survives route changes; `homeCam=default` clears it, and `homeCamTimer` clears it after `HK_HOME_CAM_MAX_MS` (15 min) if that revert never arrives.

### Visual theme

The tablet's v3 smoked glass, minus the frost: Roku has **no live backdrop-blur** and `Label` has **no shadow field**.

- Every rounded shape is a white PNG tinted at runtime (`hkTint`: `blendColor` = RGB, `opacity` = alpha): 9-patch card pieces in `images/glass/` (`fill.9.png` tinted night at `HK_GLASS_FILL_OPACITY`, `edge.9.png` rim + top highlight, `rim.9.png` lit ring, `seg.9.png` LED segments), plus `chip.png`, `glow.png`, `dot.png` and the full-screen `scrim.png` over the photo.
- Type is **Barlow** (`fonts/`, OFL) at ~1.375× the tablet's sizes. `hkFontSet()` (`source/Fonts.brs`) builds one set of Font nodes in HomeGroup and hands it to every card. Glyphs are the tablet's MDI set as white PNGs (`images/glyphs/{32,40,56}/`) indexed by `HK_GLYPHS()` in `source/Glyphs.brs`, which every scope that includes Config.brs needs (`hkGlyphFor` reads it).
- Card states mirror the tablet's GlassCard: lit (active, alert, or an HA `focusModule=` attention) tints chip, glyph, rim and glow in the glyph's accent (`hkAccentFor`) or coral on alert, fading 600 ms in / 1,200 ms out; stale content at 50%, offline at 45% with a "No data since …" banner.
- The header is the tablet's: clock + date left, `hkHeaderStatus` dot + word right, re-evaluated every 5 s because a hung poll never reports back. The whole wall shifts ±2 px every 10 min (`hkBurnIn`).
- The pure logic (`hkCardKind`, `hkTileStale`, `hkDoorsShown`, `hkLedFrame`, `hkVisibleRowCount`, `hkFreshness`, `hkTileRect`, …) is ported from the tablet's tested functions into Config.brs, with their cases in `tests/unit/test_pure.brs`. `hkTileRect` places each card from the config's `grid` geometry and the module's `tile.{col,row,w,h}`.

**Backgrounds** are served by the sidecar (`/api/backgrounds`, `/api/background/<name>` from `HAKU_BG_DIR`), the same photos the tablet shows; nserver mirrors the curated NAS folder into it every 15 min (`../sidecar/haku-bg-sync.sh`). The channel asks for `w=1920&h=1080&fit=cover` (most photos are 4:3) and re-reads the list every `HK_BG_LIST_MS` (10 min, `bgListTimer`). `BackgroundGallery` cross-fades two Posters gated on `loadStatus=="ready"`, blanks both on live/grid to free texture memory, and dwells per `background.intervalMs` from the config (`hkBgRotateMs`, 20 s default). `hkBgListUpdate` keeps the current photos when a refresh fails or comes back empty, and applies a changed list between transitions.

### Asset scripts

All generated art is deterministic: re-run the script, never hand-edit the output.

- `scripts/generate_brand_assets.py`: app icons, splash screens, the reconnect-overlay wordmark, overlay card PNGs (scrim card, cream chip, PIP frame, top fade), carousel chevrons, the cold-boot background fallback, and the sidecar's default background card (`../sidecar/backgrounds/bg_00_haku_logo.jpg`), from `../docs/brand/logo_icon.png` and `logo_wordmark.png`.
- `scripts/gen_glass_assets.py` (Pillow): `images/glass/`.
- `scripts/gen_glyphs.py` (matplotlib + Pillow; run with `../sidecar/.venv/bin/python`): rasterizes the tablet's `GlyphData.kt` paths (plus `cctv`) into `images/glyphs/` and regenerates `source/Glyphs.brs`.
- `scripts/generate_keepawake.sh` (ffmpeg): `images/keepawake.mp4`.

`bsconfig.json` and `scripts/deploy.js` must both list `fonts/**/*`, or the fonts silently don't ship.

### Sidecar data flow

`ModulePollTask` pulls the sidecar at `hubBase` (discovery's `sidecar.base`) with `?layout=roku` (`HK_LAYOUT()`), driven by `stateTimer`:

- **Poll rate**: every `HK_STATE_POLL_MS` (1 s); `hkStatePollMsFor` gives the Express 3930 2 s, because at 1 s its camera square rebuffered and drifted up to 30 s behind live.
- **Deadline**: each state fetch gets 3 s (`hkHttpGetJsonTimeout` with `HK_STATE_TIMEOUT_MS`), so a hung sidecar can't hold the Task.
- **Config**: `/api/config` → `HomeGroup.config` (builds the cards). The fetch stays pending in `m.configPending` until a config arrives, because a `RUN` sent while the Task is busy is dropped.
- **State**: `/api/state` → `HomeGroup.state` (values per `feedKey`). `ModuleTile.onValues` skips the repaint when a tile's values are unchanged (`FormatJson`). `poll_ok` is logged on the first good poll, on recovery and then once a minute (`hkPollLogDue`); `poll_fail` once per outage.
- **Layout fallback**: a sidecar without the layout answers 404, which reaches the channel as no body (`GetToString` drops 4xx bodies) or as `{"error": "unknown layout"}`; the config falls back to the default view (`event=layout_fallback`, `activeLayout` = ""). If a layout state fetch later fails while the default view still answers, the layout went away and MainScene re-fetches config (`snapshot.err = "unknown_layout"`). After a fallback the wall stays on the default view until the next config fetch (relaunch or rediscovery).

The sidecar owns display formatting (`values.tile.{hero,sub,detail,severity,glyph,active,level}`, doors/machines/items/outlook arrays). `layouts.roku` in the live `/etc/haku/dashboard.json` is built from the tablet's entries (`"ref": "tablet:<id>"`), each with its own `tile`, since the ref merge is shallow and the Roku's 6×4 positions differ. The camera tile names its camera in `tile.cam`; the forecast tile's `tile.card` is the chart PNG path (`/api/card/weather_chart.png`, which `ForecastBody` fetches with `?layout=roku` every 5 min into two Posters swapped on load). Both live in `tile` because `hkSlimConfig`, which slims the config for the registry cache, keeps `tile` and drops `drill`.

### Stream pipeline contract

`DiscoveryTask` sends an SSDP M-SEARCH (`urn:haku:service:dashboard:1`, `MX=2s`, `SCHEMA_VERSION_SUPPORTED=2`), fetches `http://<host>/discovery.json` and publishes `{ ok, streams, host, sidecar, schemaVersion, version }`. `MainScene.onDiscoveryResult` hands `streams` to `LiveGroup`/`GridGroup`/`HomeGroup`, points `ModulePollTask` and `HomeGroup` at `sidecar.base`, and caches both. Schema 2 is schema 1's `streams` plus the top-level `sidecar` block.

**If the discovery JSON shape changes**, bump together: `schemaVersion` in `../stream/haku-discovery.py`, `EXPECTED_SCHEMA_VERSION` in `tests/contract/discovery_contract.py`, and the `HK_REG_KEY_DISCOVERY()` key name. The key name is what stops the Roku reading back an old cache (`HK_REG_CACHE_VER()` is defined but nothing reads it).

`hkStreamUrl(streams, cam)` (used by `LiveGroup.streamUrlFor` and `CameraBody`) returns `streams[cam].hls`, falling back to `streams.mosaic.hls` for a partial discovery payload.

### Watchdog / reconnect

`LiveGroup` runs a watchdog Timer comparing `lastPlayingTimestamp` to now and restarts the stream if it hasn't been "playing" for over 90 s. Per-cam retry counters (`m.retryAttempts`) follow `hkNextBackoffSeconds`: 2, 5, 10, 30, 30… s. Past `RETRY_BEFORE_REDISCOVERY` (4) consecutive errors, `LiveGroup` clears its `streams` field and `MainScene.onLiveStreamsCleared` re-runs discovery. **Don't reset retry counters on cam switch**: the per-cam dictionary keeps a flaky cam from resetting a healthy one's backoff.

### Severity routing

`MainScene.dispatchEcp()` routes every ECP `/input` (arriving as a roInputEvent) and the routing keys of a cold launch, in this order:

- `homeCam=<cam>` / `homeCam=default` → `setHomeCam` (see Home camera). Checked first and doesn't return, so it can ride along with any other key. No route change.
- `overlay=<kind>` → `OverlayLayer.callFunc("show", e)`, then **returns**: an overlay never falls through to a cam swap. Unknown kinds are a no-op.
- `focusModule=<id>` → `takeoverModule` (see Idle / auto-takeover), then returns.
- `cam=` with `severity=high|normal` (default `normal`) → `goLive`, with `replay=<s>` (seek back that far; the HLS window holds only ~6 s) and `banner=<text>` as a toast coloured by severity.
- `cam=` with `severity=low` → a PIP overlay (`overlay=pip`), no route change.
- `mode=home` / `mode=grid`; `mode=briefing` only toasts "coming soon".
- `lastMotion=<cam>&lastMotionAt=<unix>` (HA's heartbeat) → the "motion N min ago" label on `LiveGroup`'s Hud and `GridGroup`.

### Overlay layer

`OverlayLayer.show(params)` fans 5 kinds into 4 independent zones (`door`/`text` share the top banner; `weather`, `sensor`, `pip` each have their own), so several overlays can show at once without queuing. Each zone has its own slide animation and dismiss timer. Default TTLs are `HK_OVERLAY_*_MS()` via `hkOverlayDurationMs` (callers override with `dwell=`/`duration=` seconds); severity colours come from `hkSeverityColor`. The PIP refresh (`JpegPipTask`) writes ping-pong `tmp:/pip_<cam>_{a,b}.jpg` slots (or `Poster` reads a half-written file) and appends `?t=<ms>` so the same path reloads.

### ECP wire format

`../docs/HAKU_DESIGN.md` § "Overlay layer" and § "Event-driven flows" are authoritative for what HA may send. Facts that bite:

- ECP `/input` reads **only the URL's query string**; a POST body is ignored.
- Two POSTs landing on one Roku at the same instant can arrive as one request's params twice (the other is lost). HA's package therefore queues its broadcasts.
- ECP values are strings, but MainScene hands components integers (`hkParseInt`). Read them with `hkParseInt`, never `.toInt()`, which is a runtime error on an integer.

A schema change needs matching updates in `OverlayLayer`, `MainScene.dispatchEcp` and smoke's POST list.

### HA push side

`ha-housewall.yaml` is a byte-for-byte copy of mserver's `/root/docker/homeassistantV3/config/ha/packages/housewall.yaml`: one `rest_command` per Roku, the active-Roku selector, `script.housewall_broadcast` and the automations (its header comments describe each). Its entities are `housewall_*` because the package predates the HAku name. To change it: edit here, `md5sum` the live file against the repo first, back the live file up next to itself, copy over, run HA's config check (`POST /api/config/core/check_config`), then reload what changed (`automation.reload`, `script.reload`, `rest_command.reload`, `template.reload`).

### Registry

One section, `haku`, with keys from the `HK_REG_KEY_*()` accessors in Config.brs: `discoveryCacheV2` (the streams JSON), `hubConfigRokuV1` (the `hkSlimConfig`-slimmed config; the pre-0.11 `hubConfigV2` is deleted on boot), `hubBaseV2`, `defaultCam`, per-cam `audioMuted_<cam>`, and the HA bootstrap's `haUrl` + `haToken`.

## Conventions

- BrightScript has no module-scope const, so `Config.brs` exposes constants as zero-arg functions (`HK_FADE_MS()`, `HK_BG_CREAM()`, …). Keep that pattern.
- Pure helpers (`hkNextBackoffSeconds`, `hkCamIndex`, `hkParseInt`, `hkGridQuadrantPos`, `hkMotionLabel`, `hkOverlayDurationMs`, `hkSeverityColor`, `hkHomeCam`, `hkStatePollMsFor`, `hkPollLogDue`, the glass helpers) live in `Config.brs` so `test_pure.brs` can run them under `brs` without SceneGraph. New helpers go there too, dependency-free.
- Log only through `hkLog` / `hkDebug` / `hkEvent`, never ad-hoc `print`. `hkEvent("name", { k: v })` emits `[HAku] event=name k=v` and redacts keys named `haToken`/`token`/`password`; smoke depends on the format.
- `bs_const DEBUG=false` in `manifest` compiles out `hkDebug()`. Flip it for verbose dev sideloads; never commit `DEBUG=true`.
- Surfaces with a severity take their colour from `hkSeverityColor()` (`Toast.brs` still hardcodes the same three).
- **Versioning**: `VERSION.txt` and `package.json` hold `X.Y.Z`; the manifest holds `major_version=X`, `minor_version=Y`, `build_version=0000Z`. Keep all three in lockstep: the device reports `major.minor.build`.

## Known unverified areas

- **HUD and Toast** have no recorded visual check on real hardware; after changing them, sideload and look.
- **Smoke sends but doesn't separately assert** the plain `cam=` + `severity=` swap (its `route … to=live` already comes from the `focusModule=` takeover), and never shows a PIP (it needs the snapshot endpoint). Exercise both by hand when touching `dispatchEcp` or `OverlayLayer.show`.

## Secrets

None in the repo or on this machine. Camera RTSP creds live on nserver in `/etc/haku/cam-creds.env`, the sidecar's HA token in `/etc/haku/haku.env`. A gitignored local `.env` is fine for dev. Never log `haToken`, `token` or `password`; `hkScrub` and `hkEvent` redact them, so don't bypass them in a new code path.
