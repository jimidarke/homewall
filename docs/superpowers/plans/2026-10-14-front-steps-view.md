# Front steps view on motion (HAku 1.1) — plan

Approved 2026-10-14 and executed the same day; what changed during execution (the ECP body bug, the `.toInt()` crashes, queued broadcasts, Roku 1.1.2) is recorded in `docs/superpowers/specs/2026-10-14-front-steps-view-design.md`.

## Context

The wall's live camera square shows the Genbolt PTZ lens (`front`), which is mounted sideways and can't see the front steps. A delivery or someone waiting at the door is invisible. The Genbolt's second, fixed lens does see the steps, and `binary_sensor.front_motion_occupancy` ("Front Entrance") fires when someone is there.

**Goal:** when front motion has been on for 5 s, every Roku's home square switches to the fixed lens; when the sensor clears, it switches back to the PTZ. The sensor holds itself on until 90 s after the last movement, so no extra hold is needed.

**Decisions made (user, 2026-10-14):**
- Source: the Genbolt fixed lens read directly, not a mosaic crop.
- Drop the existing "HouseWall · Front motion" full-screen takeover.
- Switch 5 s after motion starts; revert when the sensor clears.
- Delivery: HA pushes over ECP, not via the sidecar. The sidecar path adds 0–20 s.

**Expected timing:** the switch lands about T+7 to T+9. The video then runs ~5 s behind real life (after the HLS tuning in `27608d6`), so the first steps frames show about T+2 to T+4.

## Design

### 1. Stream: `front_steps` (nserver)

**Probe the Genbolt first (read-only).**
- On nserver, `ffprobe` its RTSP paths (`/11`, `/12`; `/21` and `/22` are known) using `HAKU_FRONT_*` from `/etc/haku/cam-creds.env`. Credentials are never printed.
- Grab one frame from each and compare it with mosaic quadrant 2 to confirm which path is the fixed lens, and its codec, resolution and fps.
- **If no path reaches the fixed lens, stop and ask.** The fallback is a QSV crop of mosaic quadrant 2.

**`stream/go2rtc.yaml`:** add a `front_steps` producer, copied from the `front` exec block (lines ~78-97):
- QSV decode, then `vpp_qsv` scaled to 1280×720 (or kept native if smaller), then `h264_qsv` Main.
- `-g` = 2 × fps, so chunks are 2 s, the same rule as `front`.
- ~2 Mbps, no audio.
- Comment why it's transcoded and that it's always on.

**`stream/haku-discovery.py`:** add a `STREAM_METADATA["front_steps"]` entry, without which the contract test fails on a missing `displayName`:
- `displayName` "Front Steps", vendor Genbolt, `ptz` False, codec h264, the resolution and fps from the probe, `audio` False, and a `note`.
- No `schemaVersion` bump: an extra stream key doesn't change the shape.

**HLS:** a new `haku-hls@front_steps` instance from the existing template; no unit change. It runs all the time, so a switch never waits for the stream to start.

### 2. Roku channel → 1.1.0

**New pure helper** in `roku/source/Config.brs`, next to `hkTileCam` / `hkStreamUrl` (~l.218-233):
- `hkHomeCam(tile, override, streams) as string` returns `override` when it's non-empty and `streams[override].hls` exists. Otherwise it returns `hkTileCam(tile)`.
- This guards against `hkStreamUrl`'s silent mosaic fallback: an override for a stream the Roku hasn't discovered keeps showing `front`.
- Add `front_steps` → "Front Steps" to `HK_CAM_DISPLAY_NAME` (~l.127).
- Add `HK_HOME_CAM_MAX_MS()` = 15 min (safety revert).

**Plumbing**, following the existing `camActive` / `streams` pattern:
- **`components/CameraBody.xml`/`.brs`:** new field `camOverride` (string, `onChange="sync"`). `sync()` uses `hkHomeCam(tile, m.top.camOverride, m.top.streams)` instead of `hkTileCam(tile)`. The rest of `sync()` already restarts on a URL change: it resets attempts and calls `startCam`, even mid-rest.
- **`components/ModuleTile.xml`/`.brs`:** new field `camOverride` (`onChange="passDown"`), plus a `hasField` line in `passDown()` (~l.103-109).
- **`components/HomeGroup.xml`/`.brs`:**
  - New field `homeCam`.
  - `onHomeCam` pushes it to every tile, like `onCamActive` (~l.100-104).
  - Also set it when tiles are created in `onConfig` (~l.70), because a config refresh rebuilds every tile.
- **`components/MainScene.brs` `dispatchEcp()` (~l.627):** a new first, non-returning branch, so the param can travel with any other.
  - `homeCam=<cam>` sets `m.home.homeCam = cam` and restarts `homeCamTimer`.
  - `homeCam=default` (a sentinel; an empty value isn't reliable) clears the override and stops the timer.
  - Log `hkEvent("home_cam_override", {cam})`.
  - Add `homeCam` to the cold-launch param list in `onArgs` (~l.150).
- **`homeCamTimer`** (MainScene) clears the override after `HK_HOME_CAM_MAX_MS`. That covers a Roku that hears "switch" but misses "switch back". The override lives on HomeGroup, so it survives takeovers and diag, and applies on return home (`stopAll`/`sync` already handle that).
- **Card title** stays "Front", deliberately.
- **Version:** `VERSION.txt`, `package.json` (+ lock) → 1.1.0; manifest minor 1, build 00001.

**Tests:**
- `tests/unit/test_pure.brs`: add `test_hkHomeCam`, covering no override, a valid override, an override missing from streams, a stream entry without `hls`, and invalid tile/streams. Register it in `Main()` next to `test_hkStreamUrl` / `test_hkTileCam`.
- `tests/contract/discovery_contract.py`: add `front_steps` to `EXPECTED_STREAMS`.
- `tests/fixtures/discovery.json`: add the `front_steps` entry.

### 3. Home Assistant (mserver, `packages/housewall.yaml`)

- Back up the file first: `housewall.yaml.bak-20261014`.
- Add `rest_command.housewall_office` (the dev/office Roku, `192.0.2.55`) and add it to `script.housewall_broadcast`, so the office wall switches too. The motion-timestamp heartbeat then also reaches the office, which is harmless.
- **New automation "HouseWall · Front steps view"** (`id: housewall_front_steps_view`), `mode: queued`, with trigger ids:
  - `front_motion_occupancy` to `on` for `00:00:05` → `script.housewall_broadcast` with `homeCam=front_steps`.
  - Clearing (to `off`) → broadcast `homeCam=default`.
  - Going `unavailable`, or HA starting, → also broadcast `homeCam=default`.
- **Remove the `housewall_front_motion` automation.** Door-open and back-yard automations are untouched.
- Validate with a config check, then reload through the API (`automation.reload`, `script.reload`, `rest_command.reload`). If `rest_command` can't reload, ask before restarting the HA container.

### 4. Docs

- **`docs/superpowers/`:** write the spec (`specs/2026-10-14-front-steps-view-design.md`) and plan (`plans/2026-10-14-front-steps-view.md`) from this file, as the repo's record convention requires.
- **`stream/README.md`:** stream table row, file table, deploy-script instance lists (`enable --now`, rollback `disable`), the "5 streams" line.
- **`stream/CLAUDE.md`:** stream list.
- **`roku/CLAUDE.md`:** severity routing list (`homeCam=`), the CameraBody paragraph.
- **`docs/HAKU_DESIGN.md`:**
  - Cameras table
  - the `go2rtc.yaml` stream list
  - "Other ECP keys" (`homeCam`)
  - the HA automations section: new automation, removed takeover, office rest_command
  - a status-table row

## Execution order

Each step is checked before the next; stop on any failure.

1. **Probe** the Genbolt (read-only) and confirm the fixed-lens path. Stop and ask if it can't be found.
2. **Repo changes.** stream (go2rtc yaml, discovery metadata), roku (helper, plumbing, tests, 1.1.0), docs. Then:
   - `cd roku && npm test` (lint + unit + contract against the fixture)
   - `cd sidecar && .venv/bin/python -m pytest tests -q`, as a sanity check; no sidecar change is expected.
3. **Deploy the stream.**
   - Drift check: md5 of `go2rtc.yaml` and `haku-discovery.py` against the repo.
   - Back up to `/root/haku-stream-backup-<date>-frontsteps/`.
   - Copy, restart go2rtc + discovery, `systemctl enable --now haku-hls@front_steps`.
   - Restarting go2rtc can leave the Rokus on "Camera offline" for up to 5 min; that's expected.
   - Verify: the `front_steps.m3u8` window is 3 × 2 s, H.264; discovery lists `front_steps`; the live contract test (`npm run test:contract` without `HAKU_FIXTURE`) passes.
4. **Sideload 1.1.0 to the dev Roku `.55` and test by hand there.** Sideloading relaunches the channel, which re-runs discovery and picks up `front_steps`.
   - `curl -X POST ".../input?homeCam=front_steps"` → `/query/media-player` shows a new stream on `front_steps`; screenshot the wall.
   - `homeCam=default` → back to `front`.
   - `homeCam=bogus` → stays on `front`.
   - Override during a takeover, then return home → the override applies.
   - Run the smoke test on `.55` (`ROKU_DEV_PASSWORD=$ROKU_PW_OFFICE`).
5. **Sideload 1.1.0 to the four fleet Rokus**, checked with `/query/apps` and `/query/media-player`, like the 1.0 rollout.
6. **HA changes** (step 3 of Design), config check, reload. End-to-end test by calling `script.housewall_broadcast` with `homeCam=front_steps`, then `default`: all five Rokus switch and switch back. Then watch the next real front-motion event:
   - the HA logbook shows the automation firing at T+5;
   - every Roku's media-player switches to `front_steps` and back after clear.
7. **Commit** the repo changes (stream, roku 1.1.0, docs/spec/plan) on main and tag `v1.1.0`. Update memory (`reference-stream-latency`, fleet status).

## Verification summary

- **Unit:** `test_hkHomeCam` cases pass. `npm test` green.
- **Live contract:** discovery has `front_steps` with H.264 and a reachable HLS URL.
- **Dev Roku:** manual ECP checks (switch, revert, bogus cam, across a takeover), smoke passes.
- **Fleet:** all five Rokus on 1.1.x and playing.
- **End to end:** a real front-motion event switches every wall square to the steps after about 5 s and back after the sensor clears; no full-screen takeover on the living-room TV.

## Rollback

- **Roku:** re-sideload the `v1.0.1` tag.
- **Stream:** restore the backups, then `systemctl disable --now haku-hls@front_steps`.
- **HA:** restore `housewall.yaml.bak-20261014` and reload.

The Roku 1.1 helper falls back to `front` whenever `front_steps` is missing, so the parts can be rolled back independently.
