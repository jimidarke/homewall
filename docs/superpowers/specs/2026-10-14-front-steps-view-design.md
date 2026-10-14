# Front steps view on motion — design (HAku 1.1)

Date: 2026-10-14. Status: shipped (Roku 1.1.2 on all five Rokus, stream and HA live). Plan: `docs/superpowers/plans/2026-10-14-front-steps-view.md`.

## Problem

The wall's live camera square plays the Genbolt PTZ lens (`front`, `/21`). It is mounted sideways and doesn't see the front steps, so a delivery or someone waiting at the door doesn't show. The Genbolt's fixed lens (`/11`) looks straight down at the steps, and `binary_sensor.front_motion_occupancy` ("Front Entrance") fires when someone is there.

## Decisions (user)

- Source: the Genbolt fixed lens read directly (`/11`), not a crop of the NVR mosaic.
- When front motion has been on for **5 s**, every Roku's home square shows the steps. When the sensor clears, it goes back to the PTZ. The sensor already holds `on` for 90 s after the last movement (7 days of history: every activation ≥ 90 s), so there's no extra hold.
- Drop the old "HouseWall · Front motion" full-screen takeover.
- Deliver by HA push over ECP, not via the sidecar. The sidecar path stacks its 10 s HA poll on the Roku's 10 s state poll (0–20 s, different per TV).

## Design

**Stream (nserver).**
- `front_steps` in `stream/go2rtc.yaml` is the same QSV transcode as `front`: HEVC 1080p15 → H.264 Main 720p, GOP 30 (2 s chunks), about 2 Mbps.
- `haku-hls@front_steps` keeps it running all the time, so a switch never waits for a cold start.
- Discovery lists it automatically (from go2rtc). Its `STREAM_METADATA` entry supplies `displayName` "Front Steps".
- No `schemaVersion` change.

**Roku (1.1).**
- `homeCam=<cam>` / `homeCam=default` is a new ECP key. `MainScene.dispatchEcp` checks it first and never returns, so it can ride with any other key.
- It sets `HomeGroup.homeCam`, which reaches `CameraBody.camOverride` through `ModuleTile.camOverride`.
- `CameraBody.sync()` picks its camera with the pure helper `hkHomeCam(tile, override, streams)`. It honours the override only when discovery has an HLS stream for it, otherwise uses `tile.cam`. This keeps `hkStreamUrl`'s mosaic fallback from turning an unknown name into the grid.
- The override lives on HomeGroup, so it survives takeovers and diag.
- `homeCamTimer` clears it after `HK_HOME_CAM_MAX_MS` (15 min), for a Roku that misses the revert.
- The card title stays "Front".

**HA (`packages/housewall.yaml` on mserver).**
- `housewall_front_steps_view`, `mode: queued`:
  - motion `on` for 5 s → broadcast `homeCam=front_steps`;
  - motion `off`, `unavailable`/`unknown`, or HA start → broadcast `homeCam=default`.
- `housewall_front_motion` is removed.
- `rest_command.housewall_office` (`.55`) joins the broadcast script.

## Findings while shipping

All three were on the HA push path, which had never worked:

1. **ECP `/input` reads only the URL query string; a POST body is ignored.** The package sent every payload as a form body, so **no HA push had ever reached a Roku**. That covers the door-open takeover, the after-hours back alerts and the motion heartbeat. The `rest_command`s now use `url: ".../input?{{ payload }}"`. The user chose to fix all of them and keep every automation, so the dormant takeovers are now live.
2. **The first real pushes crashed the channel.** `LiveGroup.onMotionPushed`, `LiveGroup` replay handling and `GridGroup`'s motion dots called `.toInt()` on integers that MainScene had already parsed. That's a BrightScript runtime error. A sideloaded channel stops in the debugger and freezes: the video keeps playing, nothing else responds. The three call sites now use `hkParseInt`. The smoke test now sends HA's real `replay=` and `lastMotion=` payloads and fails on any runtime error. This shipped as 1.1.2.
3. **Concurrent ECP POSTs to one Roku lose a message.** When motion clears, the heartbeat and the revert broadcast at the same instant.
   - `mode: single` dropped the second call.
   - `mode: parallel` let two POSTs land on one Roku together, which sometimes delivered one request's params twice and lost the other.
   - The broadcast script is now `mode: queued`.

## Measurements (2026-10-14)

- **Switch time:** about 1.2 s from the push to video playing on the office Premiere+. The Kids Express (`.52`, weakest link) can take ~30 s.
- **First real event:** motion on 23:21:03.8; the automation fired 23:21:08.8; every Roku fetched `front_steps`.
- **Video lag:** ~5 s behind live (3 × 2 s HLS window, `27608d6`).

## Not done

- The card title doesn't change to "Front Steps".
- The office Roku isn't a target of the active-Roku selector.
- LiveGroup's watchdog logs "pipeline stuck" every 60 s on home; it's harmless, because `startStream` returns when `cam` is empty.
- PTZ rotation.
