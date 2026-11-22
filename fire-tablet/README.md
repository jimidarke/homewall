# fire-tablet: HAku tablet (`io.haku.tablet`)

A native Android client for the HAku sidecar, built for the kitchen wall Fire 7 (`KFQUWI`, Fire OS 8 / API 30, `192.0.2.60`). It is the sidecar's second client, next to the Roku channel: it reads the same `/api/config` + `/api/state` contract and asks for its own layout with `?layout=tablet`. The sidecar owns all formatting; the tablet lays out and draws the cards.

Design: [docs/fire-tablet/DESIGN.md](../docs/fire-tablet/DESIGN.md) (§8 is the v2 UI, §8.10 the v3 touch layer and §8.11 the door camera; exact values are in the [v2 contract](../docs/superpowers/plans/2026-09-30-tablet-ui-v2-contract.md) and the [v3 contract](../docs/superpowers/specs/2026-10-01-tablet-v3-details-contract.md)). Device notes (specs, debloat, network, setup plan): `~/code/home-arr/docs/KITCHEN-TABLET.md`. The server side (the sidecar this app reads) lives in `../sidecar/`.

**Status: 1.1.1. The wall runs the R8 release build.** Nine smoked-glass cards on a 4×3 grid (doors, laundry, calendar, activity, water, energy, weather, gas, thermostat) over a rotating photo with fake frosted glass, and a night dim. The photos are the sidecar's backgrounds, the same set the wall Rokus show (DESIGN §8.1). State is polled every 1 s. A card tap opens its detail panel, a header tap peeks at the bare photo, and ‹ › during a peek step through the photos. When the front door opens, the front-steps camera plays full screen for a minute (DESIGN §8.11). Stale values are held with a "degraded" header, and water, energy and gas show rate tiles. It has no controls that change house state. Not built yet: the HOME-launcher takeover and the crash-restart handler ([DESIGN §4.5](../docs/fire-tablet/DESIGN.md#45-kiosk-behaviour)).

## Build

Requires JDK 17+ and the Android SDK. `local.properties` (gitignored) holds `sdk.dir=<path to the SDK>` and `haku.sidecarBase=http://<nserver>:1986`, the sidecar the build talks to (`HAKU_SIDECAR_BASE` in the environment also works; without either the build uses the placeholder `http://192.0.2.20:1986`, fine for tests). The toolchain resolves from the local Gradle cache, so build with `--offline`.

```bash
./gradlew testDebugUnitTest --offline   # JVM unit tests (what they cover: DESIGN §4.6)
./gradlew assembleDebug --offline       # -> app/build/outputs/apk/debug/app-debug.apk
./gradlew assembleRelease --offline     # -> app/build/outputs/apk/release/app-release.apk
```

The release build is shrunk with R8 (`isMinifyEnabled`, `isShrinkResources`; rules in `app/proguard-rules.pro`) and signed with the debug key. Both builds therefore carry the same signature, so `install -r` swaps one for the other in place.

## Install the wall build (release)

The commands here use the tablet's USB connection to the MiniPC (serial `$TABLET_SERIAL`). Wireless adb (`adb tcpip 5555`) was turned on on 2026-10-14, but only nserver can reach `192.0.2.60:5555`: `iot` blocks the MiniPC. It also resets when the tablet reboots.

```bash
adb -s $TABLET_SERIAL install -r app/build/outputs/apk/release/app-release.apk
adb -s $TABLET_SERIAL shell am start -n io.haku.tablet/.MainActivity
# Compile the bundled baseline profile ahead of time:
adb -s $TABLET_SERIAL shell am broadcast -a androidx.profileinstaller.action.INSTALL_PROFILE -n io.haku.tablet/androidx.profileinstaller.ProfileInstallReceiver
adb -s $TABLET_SERIAL shell cmd package compile -f -m speed-profile io.haku.tablet
# The compile leaves the running process on the old code; relaunch onto the compiled one:
adb -s $TABLET_SERIAL shell am force-stop io.haku.tablet
adb -s $TABLET_SERIAL shell am start -n io.haku.tablet/.MainActivity
```

The broadcast should answer `result=1`, and `adb shell dumpsys package dexopt | grep -A2 '\[io.haku.tablet\]'` should then show `status=speed-profile`.

## Debug build and demo mode

```bash
adb -s $TABLET_SERIAL install -r app/build/outputs/apk/debug/app-debug.apk
adb -s $TABLET_SERIAL shell am start -n io.haku.tablet/.MainActivity --es demo busy
```

A debug build started with `--es demo <scenario>` replays canned config and state from `app/src/debug/assets/demo/` instead of the sidecar. The photos stay real. Every detail panel opens in demo mode, from `app/src/debug/assets/demo/detail_{water,energy,gas,climate,weather,laundry,doors}.json` (Calendar and Activity are built from the demo state). The weather panel has variants, picked with `--es demo_detail tonight` (the evening, when the day's high is gone) or `--es demo_detail nofc` (the forecast down), from `detail_weather_{tonight,nofc}.json`. The three weather files are generated from the sidecar code, not hand-written. The scenarios:

- `quiet`, `busy` and `alert` show one state each.
- `cycle` rotates through those three every 10 s.
- `offline` shows the quiet state for 5 s, then fails every state fetch, so the lagging dot and the offline banner appear on their real timers.
- `degraded` shows the quiet state for 5 s, then marks water stale. Water keeps its last reading as live for the 5-minute hold grace, then greys with "as of" and the header says "degraded · Water".
- `door` shows the quiet state for 5 s, then the front door open with the doors module's `takeover` (`door.json`), so the door camera plays the real `front_steps` stream full screen for about a minute. A tap or Back closes it.

To leave demo mode, force-stop and start again without the extra. Demo mode exists only when `BuildConfig.DEBUG` is true. A release build ignores the extra and logs `event=source demo=none`.

## Logs and checks

```bash
adb -s $TABLET_SERIAL logcat -s KitchenWall                  # the event lines below
adb -s $TABLET_SERIAL logcat -b crash -d                     # nothing for io.haku.tablet
adb -s $TABLET_SERIAL exec-out screencap -p > shot.png       # check the screen this way, never by sleeping or waking it
adb -s $TABLET_SERIAL shell dumpsys meminfo io.haku.tablet   # TOTAL PSS
adb -s $TABLET_SERIAL shell dumpsys gfxinfo io.haku.tablet reset   # then dump again (no reset) 60 s later
```

Each `KitchenWall` line is `event=<name> k=v`, and a failure ends `err=<reason>`, the same reason the offline banner shows (`http 502`, `network: …`, `parse: …`):

- `source` (the demo scenario, or `none`), `config_loaded`, `config_fail`;
- `poll_ok` once a minute and on the first good poll after a failure, not on every 1 s poll; `poll_fail` on every failed poll; `pulse` when a card rings;
- `detail_open`, `detail_close`, `detail_fail`;
- `cam_open` (the camera and its seconds left), `cam_close`; a player error logs `cam_error` (MediaPlayer's `what` and `extra`), then `cam_fail` and `cam_close`;
- `bg_list`, `bg_list_fail`, `bg_photo`, `bg_miss`, `bg_step`, `bg_step_miss` from the photo backdrop.

Live screenshots show real calendar titles, so keep them out of git.

## Detail panels and peek

Tap coordinates for scripted checks (1024×600, density 1, so px = dp). They are the card centres, the header, a point on a panel, and the peek's ‹ › buttons:

| Tap | x, y |
|---|---|
| Doors | 135, 140 |
| Laundry | 388, 140 |
| Calendar | 640, 230 |
| Activity | 893, 320 |
| Water | 135, 320 |
| Energy | 388, 320 |
| Weather | 135, 500 |
| Gas | 388, 500 |
| Thermostat | 640, 500 |
| Header (peek) | 300, 28 |
| Close (tap the panel) | 500, 300 |
| Peek back ‹ | 48, 300 |
| Peek forward › | 976, 300 |

```bash
adb -s $TABLET_SERIAL shell input tap 388 320                  # open Energy
# wait about a second: the reveal takes 250 ms, and taps are ignored while it runs
adb -s $TABLET_SERIAL exec-out screencap -p > energy.png       # the panel; repeat for each card
adb -s $TABLET_SERIAL shell input tap 500 300                  # close it (also: Back, the header, or 90 s)
adb -s $TABLET_SERIAL shell input tap 300 28                   # peek: the photo bare; any other tap, Back or 30 s ends it
adb -s $TABLET_SERIAL shell input tap 976 300                  # during a peek: the next photo (48 300 goes back)
```

- Check every panel in demo mode (`--es demo busy`) and then live. A live panel needs `/api/detail/<id>?layout=tablet` on the sidecar; if it is down, the panel shows its tile with "Couldn't load the details. Trying again in a minute."
- An ALERT pulse must close an open panel or peek. The `cycle` demo reaches its alert state every 30 s, so open a panel in `--es demo cycle` and watch it close.
- With no photo (backgrounds off, an empty photo folder) a header tap does nothing. Photos keep rotating through the night window, so the peek works at any hour.
- The door camera covers the whole screen and takes every tap: a tap anywhere closes it. Check it with `--es demo door`.
- Live screenshots of Calendar and Activity show real titles, so keep them out of git.

## Measurements

All on the wall, from the release build after the speed-profile compile, with live data. The PSS budget is 95 MB (DESIGN §8.9). Up to 1.0.0 the tablet polled state every 5 s; 1.1.0 polls every 1 s.

**v2 (0.2.0), 2026-10-01.** The debug figures are from the same morning.

| | Release | Debug |
|---|---|---|
| APK size | 1.96 MB (1,962,531 bytes) | 24.7 MB (24,713,885 bytes) |
| TOTAL PSS (`dumpsys meminfo`) | 54.0 to 61.1 MB, 18 samples from 07:57 to 09:07 | 91.2 MB at 07:52; 80 to 94 MB during the v2 build |
| Quiet house, 60 s of `gfxinfo` | 8 and 9 frames in two event-free windows (09:03, 09:06), all janky, p90 27 and 28 ms | 6 frames, all janky, p90 38 ms (07:52) |
| Photo cross-fade (`gfxinfo framestats`, the 1.6 s fade only) | 94 to 99 frames, all janky; p50 29 to 45 ms, p90 30 to 46 ms | not measured |

- **Memory.** Most of the saving over debug is code (25.1 MB → 4.8 MB) and the Java heap (15.0 MB → 6.6 to 12.3 MB). Graphics stays at about 14 MB.
- **Frames.** "Janky" is `gfxinfo`'s count of frames that take longer than 16.7 ms from vsync to completion. During a cross-fade the app still starts a frame on every vsync (about 60 fps), but each one takes two to three vsync periods to finish. While it fades, it draws both photos, every card's frost crop of both soft copies, and the scrim. The v2 wall took no input, so the latency was never felt; v3 takes taps, and its open and close are measured below.
- **A busy house.** From about 07:55 to 09:00 the water meter flapped between 0.0 and 0.4 L/min every 10 to 20 s (a trickle somewhere), so the quiet windows had to wait until it stopped. Each flip turned the Water card on or off, with a pulse each time it came on, two or three times a minute. Those 60 s windows rendered 254 to 808 frames (p90 16 to 31 ms). A card that stopped less than 120 s earlier doesn't ring again when it restarts (the re-pulse cooldown, DESIGN §8.6), so such a run rings once; the accent still fades on every flip.
- The cold start onto the compiled profile took 548 ms (`am start -W`, TotalTime).

**v3 (0.3.0), 2026-10-01.**

| | Release |
|---|---|
| TOTAL PSS at rest | 51.0 MB |
| After 20 panel opens | 63.7 MB |
| After 10 peeks | 62.0 MB |
| After 40 more panel opens | 72.2 MB, then 68.4 MB |
| Settled, one minute idle | 64.8 MB (Java heap 11.7 MB, native 21.3 MB, graphics 14.4 MB) |
| Panel open, house quiet, 30 s | 3 frames |
| Open and close (`gfxinfo framestats`) | 33 frames: p50 12 ms, p90 21 ms, p99 32 ms |
| Live `/api/detail/*` calls | under 90 ms cold, about 2 ms warm |

- **Memory.** PSS peaked at 72.2 MB during the 40 extra opens and came back to 64.8 MB, so it is within budget and not climbing. A 24 h soak with panels is still to do (DESIGN §7).
- **Contrast.** On the lighter glass, 16 sp muted text fell to 6.5:1 on the brightest photo in rotation, so `inkMuted` was raised (DESIGN §8.3).

**Two-column weather panel, 2026-10-03.** PSS 47.9 MB fresh and 59.9 MB after 20 weather panel opens.

**Peek stepping (0.4.0), 2026-10-05.**

- PSS was 57.1 MB at rest, 77.9 MB just after 30 steps (15 forward, 15 back), and 57.7 MB once the peek had ended and the app sat idle for 45 s: within budget and not climbing.
- A step's photo (both variants fetched and decoded) lands about 0.2 s after the tap. Three taps sent at once showed as `d=1` then a combined `d=2`, with one load for the pair.
- A rotation that fell due mid-peek was held and came one full interval later. A step 20 s into a peek kept it up at 40 s, and it ended by 53 s.

**Door camera and 1 s polling (1.1.0), 2026-10-14.**

- Idle at 1 s polling: 49 to 62 MB PSS, and 0 to 5 frames per 10 s with nobody touching it. The only bursts came from someone opening detail panels.
- End to end: HA logged the front door at 19:00:58.6, the tablet opened the camera about 1.5 s later, and it closed 59 s after that. PSS was 63.6 to 65.7 MB during the video and 66 MB after.

## How it works

The design is in DESIGN.md; this is where it lives in the code, under `app/src/main/java/io/haku/tablet/`.

| Code | Does | DESIGN |
|---|---|---|
| `data/SidecarClient`, `data/Models`, `data/Detail*` | HTTP to `BuildConfig.SIDECAR_BASE` with `?layout=` `BuildConfig.LAYOUT`. Every call returns a `Fetch` (Ok / HttpError / NetworkError / ParseError) and never throws. The models ignore unknown keys, so a newer sidecar never breaks an older APK | §4.2 |
| `data/DemoSource` | The debug demo scenarios (above) | |
| `ui/DashboardViewModel` | Config at start and every 10 min, state every 1 s (30 s after 3 straight failures); owns the detail panel, the peek and the door camera (`cam`), and closes all three on an alert | §4.2, §8.10, §8.11 |
| `ui/model/` | Each good poll projected off the main thread into card models (`Project`), pulses and their baselines (`Pulses`, `PollTracker`), held values (`TileHold`) | §8.5, §8.6 |
| `ui/Dashboard`, `ui/Layout`, `ui/Header` | Placement from `tile.{col,row,w,h}`, the header and its freshness dot, the offline banner | §8.2, §8.5 |
| `ui/cards/` | The four cards, the glass and the frost, the laundry LED frames | §4.4, §8.3, §8.4, §8.7 |
| `ui/backdrop/` | Photo rotation, the scrim, the peek's reel | §8.7, §8.10 |
| `ui/detail/` | The detail panels | §8.10 |
| `ui/cam/CamLayer` | The door camera: a `VideoView` on the stream server's HLS | §8.11 |
| `ui/BurnIn`, `ui/Night`, `MainActivity` | The ±2 dp burn-in shift, the night dim, keep-screen-on and immersive mode | §4.5, §8.6 |

## Test fixtures

`app/src/test/resources/` holds three fixtures:

- `config.json` and `state.json` are the live sidecar's `?layout=tablet` responses, last captured on 2026-10-01 (with the v3 rate tiles). On 2026-10-14 the doors module in `config.json` gained its `camera` key by hand, not by a re-capture. Re-capture both whenever the sidecar's output changes (below).
- `detail_weather_v1.json` is a frozen one-column weather detail payload from before the two-column panel (2026-10-03), generated from the sidecar code, not captured live. `DetailParseTest` checks it still parses as one column. Never re-capture it.

To re-capture `config.json` and `state.json`:

```bash
curl -s 'http://192.0.2.20:1986/api/config?layout=tablet'
curl -s 'http://192.0.2.20:1986/api/state?layout=tablet'
```

Before committing:

1. Rename every calendar event `title` to "Sample event N", and rewrite the calendar tile's hero and sub, which quote titles.
2. Replace timeline place or zone names in subs ("→ <zone>") with "→ Away", and a person's name in the activity feed with "Alex".
3. Grep the result for the original titles.
4. Pretty-print with sorted keys (`python3 -m json.tool --sort-keys`).

## Known Fire OS behaviour

Fire OS 8 ignores `setShowWhenLocked`, so once the screen sleeps the swipe lockscreen comes back in front of the app. Stay-awake-while-charging keeps the screen on in normal use. The device-side fix, and whether it has been applied, are in [DESIGN §4.5](../docs/fire-tablet/DESIGN.md#45-kiosk-behaviour).
