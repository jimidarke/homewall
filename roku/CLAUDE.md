# CLAUDE.md — roku/

The **HAku Roku channel**: BrightScript + SceneGraph, packaged as `haku.zip`, sideloaded onto the wall-mounted Rokus. It turns them into a **modular, config-driven Home Assistant dashboard** (camera wall + glance cards). As of v0.11 it boots to a **read-only glass wall** in the kitchen tablet's v3 design; v0.12 lays it out as a 6×4 grid of landscape cards: Doors 2×1, the other value tiles 1×1, Calendar and Activity 2×2 each, the **front PTZ camera live** in a 2×2 square, and a 2×2 Forecast (3-day strip over the sidecar's 48 h temperature chart). Home takes no input; HA takeovers still reach the full-screen live camera.

It's one client of the sidecar (`../sidecar/`, see `../sidecar/CLAUDE.md`); camera streams come from `../stream/`. The repo-level overview is `../CLAUDE.md` and the full design is `../docs/HAKU_DESIGN.md`.

Home Assistant (mserver, 192.0.2.10) feeds HAku two ways: the **sidecar pulls** ambient glance values (HA WebSocket/REST), and HA **pushes urgent events** (door/motion/spike) via Roku ECP `/input` (`focusModule=`/`overlay=`/`severity=`) for auto-takeover.

The channel's watchdog/reconnect and stream handling are described in the design doc.

## Common commands

All `npm` scripts run from `roku/`:

```bash
cd roku
npm run lint            # bsc --noEmit (fast — runs first in every gate)
npm run build           # bsc, emits to dist/haku.zip
npm run package         # bsc --create-package — signed, for store submission
npm run test:unit       # brs runs source/Config.brs + Glyphs.brs + tests/unit/test_pure.brs; run.js parses RESULT line and exits non-zero on FAIL
npm run test:contract   # discovery_contract.py + layout_contract.py — live discovery / sidecar ?layout=roku
HAKU_FIXTURE=1 npm run test:contract   # offline mode (CI / pre-deploy): tests/fixtures/
npm run test            # lint + unit + contract (no smoke; smoke needs a Roku)
npm run deploy          # node scripts/deploy.js — sideloads dist/haku.zip via roku-deploy
npm run clean           # rm -rf dist out
```

**Smoke test (real Roku required)** — `tests/smoke/smoke.sh` runs the full lint+unit+contract chain, sideloads, cold-relaunches via ECP, drives a `Right` keypress + 4 overlay POSTs, then tails telnet `:8085` for `[HAku] event=…` lines. It asserts `event=launch`, `event=stream_start`, ≥2 `event=cam_switch` (carousel), and ≥3 distinct `event=overlay_show kind=…`. Exit codes are documented at the top of `smoke.sh`.

```bash
ROKU_IP=192.0.2.52 ROKU_DEV_PASSWORD=$ROKU_PW_FLEET tests/smoke/smoke.sh
SMOKE_TIMEOUT=60 ROKU_IP=… ROKU_DEV_PASSWORD=… tests/smoke/smoke.sh   # longer window
```

**Deploy / sideload** — needs `ROKU_IP` + `ROKU_DEV_PASSWORD` env vars (the dev password is fleet-wide `$ROKU_PW_FLEET`). `roku-deploy` zips → publishes to `http://<ROKU_IP>/plugin_install`. The 4-Roku fleet IPs are listed in `../docs/HAKU_DESIGN.md` (living `.51`, kids `.52`, master `.53`, den `.54`).

**Server-side deploy** — see `../stream/README.md`. It's a single SSH+heredoc to `root@nserver` that installs the units, drops cred env file at `/etc/haku/cam-creds.env` (mode 0640 root:media), and `systemctl enable --now`s go2rtc + haku-hls + haku-discovery + per-cam `haku-hls@{front,yard,side,backyard}.service`. The yaml never sees secrets — it references `${HAKU_CAM_USER}`/`${HAKU_CAM_PASSWORD}` from the env file.

**Sidecar** — see `../sidecar/CLAUDE.md` and `../sidecar/README.md`. **Bump `schemaVersion` in `../stream/haku-discovery.py` + the contract test + `HK_REG_CACHE_VER` together** whenever the discovery or config shape changes.

**Run a single unit assertion** — there is no individual-test runner; `tests/unit/test_pure.brs` is one BrightScript file that prints `OK …` / `FAIL …` lines and a final `RESULT pass=N fail=M`. Edit/comment cases in that file to focus, or add a new `assertEq` block.

**Tail device logs** — `nc <ROKU_IP> 8085` (Roku BrightScript console). Channel emits structured `[HAku] event=<name> k=v…` lines via `hwEvent()` in `Config.brs`; the smoke harness greps these.

**Hot deep-link (no relaunch)** — manifest sets `supports_input_launch=1`, so:
```bash
curl -X POST -d '' "http://<ROKU_IP>:8060/input?cam=front&severity=normal&banner=Test"
curl -X POST -d '' "http://<ROKU_IP>:8060/input?overlay=weather&temp=8&hi=14&cond=cloudy"
curl -X POST -d '' "http://<ROKU_IP>:8060/launch/dev?contentId=setup&haToken=$HA_TOKEN&haUrl=$HA_URL"
```
posts arrive on the running channel via `InputPumpTask` (no init() rerun, no reconnect cost). Use `/launch/dev?contentId=…` only for cold relaunches and one-time bootstraps (HA token, default-cam).

## Architecture

The channel is a small SceneGraph state machine. The boundary between threads matters:

```
main.brs  ──creates──▶ MainScene  (render thread; routes: home·live·grid·module·diag; key handling)
                            │
                            ├─ DiscoveryTask   (Task — SSDP + discovery.json fetch; reads `sidecar` block)
                            ├─ InputPumpTask   (Task — blocks on roInput, fans roInputEvent into m.top.event)
                            ├─ ModulePollTask  (Task — GET sidecar /api/config once + /api/state each poll)
                            ├─ BackgroundListTask (Task — GET sidecar /api/backgrounds → gallery image URLs)
                            ├─ DiagHealthTask  (Task — GET sidecar /api/health for the diag screen)
                            ├─ keepAwake       (hidden 16×16 silent Video — plays on module/diag, and on home
                            │                   when there's no camera card, so the OS screensaver never takes
                            │                   over; stopped under live/grid)
                            ├─ BackgroundGallery (rotating full-screen photo, 20s crossfade; behind the grid)
                            ├─ HomeGroup       (DEFAULT route — read-only glass wall: header + ModuleTiles)
                            │    └─ ModuleTile (one glass card; body by hkCardKind: ValueBody|DoorsBody|
                            │                   LaundryBody|AgendaBody|ForecastBody|CameraBody (live HLS))
                            ├─ LiveGroup       (hidden until a camera module is opened — single-cam HLS, carousel + chevrons)
                            ├─ GridGroup       (hidden; long-press OK from live — 2×2 mosaic + focus ring)
                            ├─ ModuleScreen    (hidden; old non-camera drill-down, no longer reached from home)
                            ├─ DiagScreen      (hidden; `*`/options from home — device + discovery + HA status)
                            ├─ OverlayLayer    (door / text / weather / sensor / pip — multi-zone transient alerts)
                            └─ Toast           (top-centre notifier, queue-driven)
```

**Routes** — `MainScene` is a route router (`m.route` ∈ home/live/grid/module/diag). Boots to `home`, which is **read-only** (v0.11): HomeGroup has no `onKeyEvent`, so arrows and OK do nothing; keys bubble to `MainScene.onKeyEvent`, where `*`/options → `goDiag()` and Back exits (or climbs to home from another route). Live/grid are reached only by HA takeovers (`cam=`, a camera `focusModule=`); `goModule` is kept but nothing on home calls it. **Live video is gated by `LiveGroup.cam`**: home/module/diag leave it `""` so the single H.264 decoder is free. **On home the camera card's `CameraBody` holds it** (v0.12): `MainScene.syncHomeDecoder()` (from `goHome`, and when `HomeGroup.hasCam` changes) stops the keep-awake clip and sets `HomeGroup.camActive`, which reaches the body through `ModuleTile`. Every other route clears `camActive` before anything else plays (`goLive`/`enterGrid`/`goModule`/`goDiag`). With no playable camera card, and on module/diag, a hidden **keep-awake Video** plays instead (Roku exposes no API to disable the screensaver; only active playback suppresses it). `MainScene.startKeepAwake()`/`stopKeepAwake()` toggle it alongside `setBackdrop()`; it's always stopped before the live/mosaic decoder starts, preserving the one-decoder budget. `CameraBody` plays `streams[tile.cam].hls` muted, fitted 16:9 (`hkVideoFit`), backs off on `hkNextBackoffSeconds`, and after 4 errors in a row shows "Camera offline" and rests 5 min playing the keep-awake clip on its own Video node, shrunk to 2 px (a Video punches a black hole at any opacity) (one decoder, no screensaver); it logs `event=home_cam state=…`. The rotating `BackgroundGallery` covers burn-in. `hkTileRect` (Config.brs, unit-tested) places each card from the config's `grid` pixel geometry and the module's `tile.{col,row,w,h}`.

**Visual theme (v0.11 glass)** — the tablet's v3 smoked glass, minus the frost (Roku has **no live backdrop-blur** and `Label` has **no shadow field**). Every rounded shape is a white PNG tinted at runtime (`hkTint`: `blendColor` = RGB, `opacity` = alpha): 9-patch card pieces (`images/glass/fill.9.png` tinted night at `HK_GLASS_FILL_OPACITY`, `edge.9.png` rim + top highlight, `rim.9.png` lit ring, `seg.9.png` LED segments), the glyph `chip.png`, `glow.png`, `dot.png` and the full-screen `scrim.png` over the photo. Type is **Barlow** (`fonts/`, OFL), the tablet's two faces, at ~1.375× the tablet's sizes; `source/Fonts.brs` `hkFontSet()` builds one set of Font nodes in HomeGroup and hands them to every card (an assocarray field keeps node refs). Glyphs are the tablet's MDI set as white PNGs (`images/glyphs/{32,40,56}/`) plus `source/Glyphs.brs` (`HK_GLYPHS()`, needed in every scope that includes Config.brs, since `hkGlyphFor` reads it). Card states mirror the tablet's GlassCard: lit (active, alert, or an HA `focusModule=` attention) colours chip, glyph, rim and glow in the glyph's accent (`hkAccentFor`) or coral on alert, fading 600 ms in / 1,200 ms out; stale content at 50%, offline at 45% with a "No data since …" banner. The header is the tablet's (clock + date left, `hkHeaderStatus` dot + word right, re-evaluated every 5 s since a hung poll never reports back), and the whole wall shifts ±2 px every 10 min (`hkBurnIn`). The pure logic (`hkCardKind`, `hkTileStale`, `hkDoorsShown`, `hkLedFrame`, `hkVisibleRowCount`, `hkFreshness`, …) lives in Config.brs as ports of the tablet's tested functions, with their cases ported into `tests/unit/test_pure.brs`. Backgrounds are **served by the sidecar** (`/api/backgrounds` + `/api/background/<name>` from `HAKU_BG_DIR`); `BackgroundGallery` cross-fades two Posters gated on `loadStatus=="ready"` and blanks both URIs on live/grid to free texture memory; the interval comes from the config's `background.intervalMs` (`hkBgRotateMs`).

**Asset scripts** — `scripts/gen_glass_assets.py` (Pillow) writes `images/glass/`; `scripts/gen_glyphs.py` (matplotlib + Pillow, run with `../sidecar/.venv/bin/python`) rasterizes the tablet's `GlyphData.kt` paths (plus `cctv`) into `images/glyphs/` and regenerates `source/Glyphs.brs`. Both are deterministic: re-run, never hand-edit. `bsconfig.json` and `scripts/deploy.js` must list `fonts/**/*`, or the fonts silently don't ship.

**Sidecar data flow** — `ModulePollTask` pulls the `haku-sidecar` (`hubBase` from discovery's `sidecar.base`) with **`?layout=roku`** (`HK_LAYOUT()`): `/api/config` → `HomeGroup.config` (builds cards), `/api/state` → `HomeGroup.state` (per-`feedKey` values). `layouts.roku` in `/etc/haku/dashboard.json` is built from the tablet's entries (`"ref": "tablet:<id>"`), each with its own `tile` (the ref merge is shallow, so the Roku's 6×4 positions don't follow the tablet's). The camera tile names its camera in `tile.cam`; the forecast tile's `tile.card` is the chart PNG path (`/api/card/weather_chart.png`, fetched by `ForecastBody` with `?layout=roku` every 5 min into two Posters swapped on load). Both live in `tile` because `hkSlimConfig` keeps it and drops `drill`. A sidecar without the layout answers 404, which reaches the channel as no body (`GetToString` drops 4xx bodies; on-device, `layout_fallback err=no_response`) or as `{"error": "unknown layout"}`: the config falls back to the default view (`event=layout_fallback`; `activeLayout` = ""). If a layout state fetch fails later while the default view still answers, the layout went away, and MainScene re-fetches config (`snapshot.err = "unknown_layout"`). The sidecar owns display formatting (`values.tile.{hero,sub,detail,severity,glyph,active,level}`, doors/machines/items/outlook arrays). The config is cached in the registry slimmed by `hkSlimConfig` under `hubConfigRokuV1` (the old `hubConfigV2` is deleted on boot).

**Idle / auto-takeover** — HA pushes `focusModule=<id>`/`cam=`/`severity=` via ECP. A camera takeover (`cam=`, or `focusModule=` naming the cameras module) goes live from the passive `home` route with a `returnHomeTimer`; any other `focusModule=` only lights that card for 8 s (`HomeGroup.attention`, `event=module_attention`), with no route change. Any bubbled keypress cancels the takeover; an `idleTimer` returns live/grid/module to home after `HK_IDLE_TO_HOME_MS`.

**Render-thread vs Task-thread** — anything blocking (SSDP receive, URL transfers, JPEG fetch loop) lives in a Task component (`functionName = "..."`). They communicate with the scene only by writing fields with `alwaysNotify=true` — the scene observes those fields. Never call `findNode` / `setFocus` from a Task thread.

**Focus has to be on a Group child, not the Scene** — `MainScene.init()` ends with `m.live.setFocus(true)` because `onKeyEvent` is implemented on `LiveGroup`/`GridGroup`, not the Scene. The smoke test's "Right keypress must produce a `cam_switch`" assertion is the regression catcher for this whole bug class. 

**One Video decoder budget** — Roku has a single hardware H.264 decoder. When entering GRID, `MainScene.enterGrid()` explicitly stops `LiveGroup`'s player (`livePlayer.control = "stop"`) and the home camera (`home.camActive = false`) before setting `grid.active = true`. There are four Video nodes (keepAwake, CameraBody, LiveGroup, GridGroup); never let two play at once. The streams must be H.264: the Express and Stick can't decode HEVC, which is why go2rtc transcodes the front Genbolt's HEVC PTZ lens (`../stream/go2rtc.yaml`).

**Stream pipeline contract** — `DiscoveryTask` does SSDP M-SEARCH (`urn:haku:service:dashboard:1`, `MX=2s`, `SCHEMA_VERSION_SUPPORTED=2`) → fetches `http://<host>/discovery.json` → publishes `{ ok, streams, host, sidecar, schemaVersion, version }` on `m.top.result`. `MainScene.onDiscoveryResult` mirrors `streams` to `LiveGroup`/`GridGroup`, points `ModulePollTask`/`HomeGroup` at `sidecar.base`, and caches streams in `roRegistrySection("haku")` under `discoveryCacheV2` (config under `hubConfigRokuV1`, hub base under `hubBaseV2`). **The contract test** (`tests/contract/discovery_contract.py`) protects against server↔channel drift — bump `EXPECTED_SCHEMA_VERSION`, `HK_REG_CACHE_VER()`, and the `HK_REG_KEY_DISCOVERY()` key name together if you change the JSON shape, otherwise old caches deserialize incorrectly. schema v2 added the top-level `sidecar` block; `streams` is unchanged from v1.

**Per-cam HLS fallback** — `hkStreamUrl(streams, cam)` (used by `LiveGroup.streamUrlFor` and `CameraBody`) returns `streams[cam].hls` if present, else falls back to `streams.mosaic.hls`. Phase 2 (per-cam streams) is now deployed, so the fallback is mostly historical, but it stays as a safety net for partial discovery payloads.

**Watchdog / reconnect** — `LiveGroup` runs a watchdog Timer that compares `lastPlayingTimestamp` to now; if state ≠ "playing" for >90 s it forces a restart. Per-cam retry counters in `m.retryAttempts` use the schedule in `Config.brs::hwNextBackoffSeconds`: 2 s, 5 s, 10 s, 30 s, 30 s… After `RETRY_BEFORE_REDISCOVERY` (=4) consecutive errors, `LiveGroup` clears its `streams` field — `MainScene.onLiveStreamsCleared` observes that and re-runs discovery. **Don't reset retry counters on cam switch**; the per-cam dictionary is intentional so a flaky cam doesn't keep healthy ones from backing off correctly.

**Severity routing** — `MainScene.dispatchEcp()` is the central router for ECP `/input` arriving as a roInputEvent.
- `overlay=<kind>` → `OverlayLayer.callFunc("show", e)`. **Returns immediately** — overlay= is a complete signal, no fall-through to cam swap. Forward-compat: unknown kinds noop.
- `severity=high|normal` → cam swap via `switchToLiveCam`, with optional `replay=<seconds>` and `banner=<text>`.
- `severity=low` (with `cam=`) → routes through `overlay=pip` so it doesn't yank the user away.
- `mode=grid` / `mode=briefing` are also handled here; briefing is stubbed until v0.7.

**Overlay layer (v0.5)** — `OverlayLayer.show(params)` is one entry point that fans into 5 kinds across 4 zones (`door`/`text` share the top-banner zone; `weather`, `sensor`, `pip` each have their own). Zones are independent — multiple overlays can be visible simultaneously without queuing. Each zone has its own slide-in/slide-out animation and dismiss timer. PIP refresh uses `JpegPipTask` with a ping-pong `tmp:/pip_<cam>_{a,b}.jpg` slot pair (otherwise `Poster` reads a half-written file) and cache-busts the URI by appending `?t=<ms>` so the same path triggers a refresh. Default TTLs and per-zone palette live in `Config.brs::HW_OVERLAY_*_MS()` / `hwOverlayDurationMs`.

**Brand assets** — `scripts/generate_brand_assets.py` is the single source of truth for shipped brand art (the glass and glyph art has its own scripts, above). It reads two transparent source PNGs from `../docs/brand/` (`logo_icon.png`, a 4:3 icon-only glyph; `logo_wordmark.png`, the full icon+wordmark lockup) and emits the app icons, splash screens, the reconnect-overlay wordmark, the small overlay card PNGs (scrim card, cream chip, PIP frame, top-fade gradient), the cold-boot background fallback, and one default background-rotation card (`../sidecar/backgrounds/bg_00_haku_logo.jpg`). Don't hand-edit any of these — re-run the generator.

**Registry conventions** — single section `haku`, keys via `HW_REG_KEY_*()` accessors in `Config.brs`. Audio mute is per-cam (`audioMuted_<cam>`); the discovery cache is one JSON blob (`discoveryCacheV1`); HA bootstrap stores `haUrl` + `haToken` (the latter is scrubbed from logs by `hwScrub()` and `hwEvent()` redaction).

**ECP wire format & overlay schemas** — `../docs/HAKU_DESIGN.md` § "Overlay layer (v0.5)" + § "Event-driven flows" are authoritative for what HA may send. Any change to that schema needs a matching update in `OverlayLayer` + `MainScene.dispatchEcp` + the smoke test's overlay POST list.

## Conventions

- BrightScript has no module-scope const — `Config.brs` exposes constants as zero-arg functions (`HW_FADE_MS()`, `HW_BG_CREAM()`, etc). Keep that pattern; it's grep-friendly and cheap.
- Pure helpers (`hwNextBackoffSeconds`, `hwCamIndex`, `hwParseInt`, `hwGridQuadrantPos`, `hwMotionLabel`, `hwOverlayDurationMs`, `hwSeverityColor`) live in `Config.brs` so `tests/unit/test_pure.brs` can import via the `brs` CLI without dragging in SceneGraph. New helpers belong here too — keep them dependency-free.
- All channel logging goes through `hwLog` / `hwDebug` / `hwEvent`. `hwEvent("name", { k: v })` emits `[HAku] event=name k=v` and auto-redacts keys named `haToken`/`token`/`password`. Smoke + future log scrapers depend on this format — don't `print` ad-hoc.
- `bs_const DEBUG=false` in `manifest` gates `hwDebug()` (compile-time `#if DEBUG`). Flip it to `true` for verbose telnet during dev sideloads; never commit `DEBUG=true`.
- Severity stripe / chip border colours are computed once in `hwSeverityColor()` so Toast and OverlayLayer stay visually consistent. If you add a new visible surface that has a severity, route it through this helper.
- Versioning: `VERSION.txt`, `package.json`, `manifest.major_version/minor_version` are kept in lockstep.

## Known unverified areas (noted at v0.4–v0.5, not re-checked since)

- **HUD + Toast unverified on real hardware** as of v0.4.1 — components compile but no visual confirmation; if you change them, sideload to a real Roku and eyeball it.
- **v0.4 severity routing was reportedly broken end-to-end** ("door open does not swap cam"); v0.5 reorganized the dispatcher around explicit `overlay=` so re-verify with a smoke run when touching `MainScene.dispatchEcp` or `OverlayLayer.show`.

## Secrets

No secrets are kept in the repo or locally. Camera RTSP creds live on nserver at `/etc/haku/cam-creds.env`; the sidecar's HA token is in `/etc/haku/haku.env`. A local `.env` (gitignored) is fine for dev if you need one. Never echo `haToken`, `token`, or `password` to logs; `hwScrub` and `hwEvent` already redact, but if you add a new code path don't bypass them.
