# Door camera on the tablet + office Roku, and 1 s polling — plan

Approved and executed 2026-10-14. What changed in execution (2 s polling on the Express via `hkStatePollMsFor`, Roku 1.2.1, the fixture patch, the measurements) is in `docs/superpowers/specs/2026-10-14-door-camera-and-1s-polling-design.md`.

## Context

**What the user asked for, 2026-10-14:**
1. Opening the front door should show the Genbolt **fixed lens** (`front_steps`), not the PTZ. The full-screen door takeover goes to the **office Roku (.55) only**.
2. Poll every **1 s** everywhere: sidecar → HA, Rokus → sidecar, tablet → sidecar. The network can take it; validate the servers and devices with testing, and back off a few seconds only if needed.
3. The **kitchen tablet** gets video too. It stays idle normally. When the front door opens it shows the fixed lens **full screen for the same 60 s** the Roku takeover lasts. Tap to close; reached over network adb (`adb connect 192.0.2.60:5555`).

**Baseline measured:**
- HA `/api/states` is 302 KB and answers in 5 ms; the HA container idles at 0.2% CPU.
- The sidecar `/api/state?layout=roku|tablet` is ~11 KB and answers in 3–5 ms.
- Both hosts have 8 cores and are nearly idle.
- 1 s is plausible; the soak tests below decide.

**What exploration found that the plan must handle:**
- **The sidecar clamps the HA poll to ≥ 2 s** (`ha.py:69`, with no recorded reason). Its loop sleeps after each poll, so the real period is the fetch time plus the interval.
- **The sidecar retries a failing on-demand HA fetch** (logbook/calendar/forecast) **on every request.** At 1 s × 6 clients that could hammer a struggling HA.
- **Roku `ModulePollTask` has no timeout.** A `RUN` sent while it's busy is dropped, so at 1 s the state timer can wipe a pending `fetchConfig=true`. That's a lost config refresh.
- **Roku repaints every tile on each poll even when nothing changed.** It's label re-measuring; that's CPU on the Express, not flicker.
- Every poll logs `poll_ok`, on both clients.
- **Freshness thresholds are absolute seconds** (30 s lagging, 120 s offline) on both clients, so polling faster doesn't change them. `refreshMs` is dead config.
- **The tablet has no per-door "opened" edge**, and its design doc says "no cameras". There's no video library offline (Media3 isn't in the Gradle cache), but framework `VideoView`/`MediaPlayer` plays HLS on API 30 with no new dependency.

## Design

### 1. Door open → fixed lens (HA, mserver `packages/housewall.yaml`)
- `housewall_front_door_opened` sends `cam=front_steps&severity=normal&reason=opened&banner=Front+Door+opened` to `rest_command.housewall_office` instead of the active-Roku selector.
- `replay=15` is dropped: it never gave extra pre-roll.
- After-hours back automations are unchanged.
- Back up the file first; validate with `check_config`, then `automation.reload`.

### 2. 1 s polling

**Sidecar (→ 1.1.0):**
- `ha.py`: change the clamp to `max(1, …)` and keep a fixed cadence: sleep `interval − elapsed`, so a 1 s setting really means ~1 s.
- **Negative cache for on-demand fetches:** a failed fetch is remembered for a short backoff (~15 s), so a failing HA endpoint is retried at most every 15 s, not on every request. Keep-last-good behaviour is unchanged. Add tests in `tests/test_ha_client.py`.
- Live `HAKU_POLL_INTERVAL=1` in `/etc/haku/haku.env`: edit that one line in place, never print the file.
- README env table and docs.

**Roku (→ 1.2.0):**
- `HK_STATE_POLL_MS()` = 1000 and `stateTimer` = 1 s.
- **Config-fetch race:** MainScene keeps a `m.configPending` flag. `startHubPoll(true)` sets it. `onStateTimer` passes `fetchConfig = m.configPending`, and the flag is cleared only when a snapshot arrives with a config result, so a dropped `RUN` can't lose it.
- **Timeout:** the state fetch in `ModulePollTask` uses an async `roUrlTransfer` with a ~3 s timeout, so a hung sidecar can't wedge the task. Reuse `Http.brs`; add a timeout variant there.
- **Skip unchanged repaints:** `ModuleTile.onValues` stores `FormatJson(values)` and returns when it's unchanged.
- Log `poll_ok` only on failure → recovery and once a minute, not every second.
- Unit tests for any new pure helper in `Config.brs` (e.g. a `hkPollLogDue`-style throttle, if it ends up pure).

**Tablet (→ 1.1.0, versionCode 6):**
- `STATE_EVERY_MS = 1_000L`. Same throttle on the `poll_ok` log.
- Update the virtual-time tests: `DashboardViewModelTest` call times, and `PeekTest`/`DetailVmTest` `advance(5_000)` → 1 s cadence.

### 3. Door camera takeover on the tablet

**Sidecar** (tablet layout only; the default view and golden are untouched):
- **Exact open time:** `ha.py` `_poll_once` records **rising edges**. When an entity's state goes `off→on` between two snapshots, it stores `last_on[entity] = epoch`. At 1 s polling this catches a 3 s door open, and the state survives the door closing again.
- **`doors` module:** a new optional descriptor key on the tablet layout's doors entry:
  `"camera": {"door": "front", "cam": "front_steps", "sec": 60, "label": "Front Steps"}`.
  When the named door opened less than `sec` ago, the module's values carry
  `takeover: {cam, hls, label, until}`, where `until` = open epoch + `sec`.
- **HLS URL:** `hls` is built from a new env var `HAKU_HLS_BASE` (default `http://192.0.2.20:1985/hls`) as `{base}/{cam}.m3u8`.
- **Roku layout:** it inherits the key through its `tablet:doors` ref and ignores it. The `test_roku_layout` equality still holds, and no `null` is emitted.
- **Tests** in `tests/test_doors.py`: an edge inside / outside the window, a door closed again within the window, no `camera` key → no `takeover`, and the default view unchanged (golden).
- Add the key to the live `/etc/haku/dashboard.json` (backup first) and to `dashboard.json.example`.

**Tablet:**
- **Parse:** `HubState` reads `takeover` from the doors feed. `DoorTakeover(cam, hls, label, until)` goes in `data/Models.kt`, read through raw `JsonObject` like `doors()`.
- **VM:** `DashboardViewModel` gets `_cam: MutableStateFlow<CamUi?>`. When a poll carries a takeover whose `until` is ahead of the state's `ts` and that hasn't been shown yet (keyed on `until`), it opens one:
  - it ends any peek or detail panel, as `openDetail` does;
  - a `camJob` closes it after `until − ts` seconds (sidecar time, so clock skew doesn't matter);
  - it also closes on a tap or Back, on any ALERT (added to `closeOverlays()`), and on a stream error;
  - a takeover the user closed isn't reopened for the same `until`.
- **UI:** a new `CamLayer` drawn last in `Dashboard`'s root `Box`:
  - `AndroidView` of a framework `VideoView` (SurfaceView-backed, so app frame cost stays low), full-screen 1024×600, fitted 16:9;
  - muted, with no audio focus (`setAudioFocusRequest(AUDIOFOCUS_NONE)`);
  - an `OnErrorListener` returning `true`, so there's no system dialog;
  - `stopPlayback()` in `onRelease`;
  - a small glass label with the sidecar's `label`, and a "Connecting…" state until the first frame;
  - `TapCatcher` closes it; `BackHandler` and `headerTapAction` gain the camera case.
- **Fallback:** if `VideoView` can't play the HLS on Fire OS, stop and ask. The fallback is Media3, which needs one online Gradle fetch.
- **Debug demo:** a `door` scenario in `app/src/debug/assets/demo/` (quiet, then the front door open with a `takeover` block after 5 s), so the overlay can be driven without opening the real door.
- **Tests:** `CamTakeoverTest` (opens on a new takeover, auto-closes at `until`, closes on ALERT, tap-close not reopened, no reopen on the same `until`), plus parsing in `ModelsTest`.
- **Design rules:**
  - `docs/fire-tablet/DESIGN.md`: "No cameras" becomes "one door camera takeover"; add a §8.11 for the overlay; note the §8.6 calm-by-default exception (video plays for 60 s after a door event only).
  - `fire-tablet/CLAUDE.md` allowed taps: + "close the camera".
  - Re-capture `app/src/test/resources/{config,state}.json` (scrub calendar titles).

### 4. Versions and docs
- Roku 1.2.0, tablet 1.1.0 (versionCode 6), sidecar 1.1.0.
- **Docs:**
  - `sidecar/README.md` (doors `camera`/`takeover`, `HAKU_HLS_BASE`, the poll interval);
  - `roku/CLAUDE.md` (poll, timeout, config pending);
  - `docs/HAKU_DESIGN.md` (HA automations table, polling, the tablet camera);
  - tablet README/DESIGN/CLAUDE;
  - spec + plan records in `docs/superpowers/` (`2026-10-14-door-camera-and-1s-polling`).

## Execution order

Each step is verified before the next; stop on failure.

1. **HA door change** (small, independent). Verify by having the user open the front door: the office Roku goes full-screen on `front_steps`. Check the HA logbook and the `.55` console.
2. **Sidecar:** code + tests (`pytest`), then drift check, backup, deploy per file, `HAKU_POLL_INTERVAL=1`, restart.
   - **Load soak (10 min):** sidecar CPU with `pidstat -p <pid> 10`, HA container CPU with `docker stats`, nserver↔mserver traffic. Confirm the poll period is about 1 s from the sidecar's `/api/health` `last_ok` age.
   - Pass: sidecar < 15% of one core, HA < 5%, no errors.
3. **Roku 1.2:** code + `npm test`, sideload to `.55`, smoke.
   - **20 min soak on all five Rokus:** reuse the latency logger (media-player state, behind-live, no stalls) and console sampling for `poll` failures. Pay attention to the Kids Express `.52`.
   - Pass: the camera square never stalls more than in the earlier baseline, and HomeGroup values update every ~1 s.
   - If the Express struggles, raise the Roku poll to 2 s (or 3 s) and retest.
4. **Tablet 1.1:** code + unit tests + debug build.
   - `adb connect 192.0.2.60:5555`; debug install with `--es demo door` to check the overlay, the tap-close and that nothing hides an alert.
   - Then the release build: install, speed-profile compile, measure PSS (`dumpsys meminfo`) and frames (`gfxinfo`) at idle at 1 s polling, and during a takeover. Budget 95 MB.
5. **End to end:** the user opens the front door.
   - The tablet shows the steps full-screen within a few seconds and closes after 60 s.
   - The office Roku takes over to the steps.
   - The wall squares keep the motion-driven steps view.
6. **Docs, commit, tag** (`v1.2.0`), update memory.

## Rollback

- **HA:** restore `housewall.yaml.bak-<date>` and reload.
- **Sidecar:** restore the per-file backups, set `HAKU_POLL_INTERVAL` back to 10, restart.
- **Roku:** re-sideload `v1.1.2`.
- **Tablet:** reinstall the 0.4.0/1.0.0 release APK from git (`git checkout v1.0.1 -- fire-tablet && ./gradlew assembleRelease`).

Each part also degrades on its own: the poll interval is an env var or a constant, and a tablet without a `takeover` block never opens the camera.
