# fire-tablet: HAku tablet (`io.haku.tablet`)

A native Android client for the HAku sidecar, built for the kitchen wall Fire 7 (`KFQUWI`, Fire OS 8 / API 30, `192.0.2.60`). It is the sidecar's second client, next to the Roku channel: it reads the same `/api/config` + `/api/state` contract and asks for its own layout with `?layout=tablet`. The sidecar owns all formatting; the tablet lays out and draws the cards.

Design: [docs/fire-tablet/DESIGN.md](../docs/fire-tablet/DESIGN.md) (§8 is the v2 UI and §8.10 the v3 touch layer; exact values are in the [v2 contract](../docs/superpowers/plans/2026-09-30-tablet-ui-v2-contract.md) and the [v3 contract](../docs/superpowers/specs/2026-10-01-tablet-v3-details-contract.md)). Device notes (specs, debloat, network, setup plan): `~/code/home-arr/docs/KITCHEN-TABLET.md`. The server side (the sidecar this app reads) lives in `../sidecar/`.

**Status: 1.0.0. The wall runs the R8 release build.** Nine smoked-glass cards on a 4×3 grid (doors, laundry, calendar, activity, water, energy, weather, gas, thermostat) over a rotating photo with fake frosted glass. The photos are the sidecar's backgrounds (`HAKU_BG_DIR`, which nserver mirrors from the NAS folder `/mnt/media/haku/kitchen` every 15 min; the wall Rokus show the same set). Barlow type, Material Design Icons glyphs, one-shot motion when something changes, and a night dim. A card tap opens its detail panel, a header tap peeks at the bare photo, and ‹ › during a peek step through the photos. Stale values are held with a "degraded" header, and water, energy and gas show rate tiles. It has no controls that change house state. Not built yet: the HOME-launcher takeover and the crash-restart handler ([DESIGN §4.5](../docs/fire-tablet/DESIGN.md#45-kiosk-behaviour)).

## Build

Requires JDK 17+ and the Android SDK at `~/Android/Sdk` (`local.properties`, gitignored: `sdk.dir=~/Android/Sdk`). The toolchain resolves from the local Gradle cache, so build with `--offline`.

```bash
./gradlew testDebugUnitTest --offline   # JVM unit tests (fixtures captured from the live sidecar)
./gradlew assembleDebug --offline       # -> app/build/outputs/apk/debug/app-debug.apk
./gradlew assembleRelease --offline     # -> app/build/outputs/apk/release/app-release.apk
```

The release build is shrunk with R8 (`isMinifyEnabled`, `isShrinkResources`; rules in `app/proguard-rules.pro`) and signed with the debug key. Both builds therefore carry the same signature, so `install -r` swaps one for the other in place.

## Install the wall build (release)

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
- `door` shows the quiet state for 5 s, then the front door open with the doors module's camera `takeover`, so the door camera plays the real `front_steps` stream full screen for about a minute (DESIGN §8.11). A tap closes it.

To leave demo mode, force-stop and start again without the extra. Demo mode exists only when `BuildConfig.DEBUG` is true. A release build ignores the extra and logs `event=source demo=none`.

## Logs and checks

```bash
adb -s $TABLET_SERIAL logcat -s KitchenWall                  # event=source, config_loaded, poll_ok, poll_fail, pulse, detail_open, detail_close, detail_fail, bg_photo, bg_step, ...
adb -s $TABLET_SERIAL logcat -b crash -d                     # nothing for io.haku.tablet
adb -s $TABLET_SERIAL exec-out screencap -p > shot.png       # check the screen this way, never by sleeping or waking it
adb -s $TABLET_SERIAL shell dumpsys meminfo io.haku.tablet   # TOTAL PSS
adb -s $TABLET_SERIAL shell dumpsys gfxinfo io.haku.tablet reset   # then dump again (no reset) 60 s later
```

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
- Live screenshots of Calendar and Activity show real titles, so keep them out of git.

## Measurements (2026-10-01)

These are from the release build after the speed-profile compile, on the wall with live data. The debug figures are from the same morning. This table and the notes under it are v2 (0.2.0); the v3 figures follow.

| | Release | Debug |
|---|---|---|
| APK size | 1.96 MB (1,962,531 bytes) | 24.7 MB (24,713,885 bytes) |
| TOTAL PSS (`dumpsys meminfo`) | 54.0 to 61.1 MB, 18 samples from 07:57 to 09:07 | 91.2 MB at 07:52; 80 to 94 MB during the v2 build |
| Quiet house, 60 s of `gfxinfo` | 8 and 9 frames in two event-free windows (09:03, 09:06), all janky, p90 27 and 28 ms | 6 frames, all janky, p90 38 ms (07:52) |
| Photo cross-fade (`gfxinfo framestats`, the 1.6 s fade only) | 94 to 99 frames, all janky; p50 29 to 45 ms, p90 30 to 46 ms | not measured |

- **Memory.** The budget is 95 MB. Most of the saving over debug is code (25.1 MB → 4.8 MB) and the Java heap (15.0 MB → 6.6 to 12.3 MB). Graphics stays at about 14 MB.
- **Frames.** "Janky" is `gfxinfo`'s count of frames that take longer than 16.7 ms from vsync to completion. During a cross-fade the app still starts a frame on every vsync (about 60 fps), but each one takes two to three vsync periods to finish. While it fades, it draws both photos, every card's frost crop of both soft copies, and the scrim. The v2 wall took no input, so the latency was never felt; v3 takes taps, and its open and close are measured below.
- **A busy house.** From about 07:55 to 09:00 the water meter flapped between 0.0 and 0.4 L/min every 10 to 20 s (a trickle somewhere), so the quiet windows had to wait until it stopped. Each flip turned the Water card on or off, with a pulse each time it came on, two or three times a minute. Those 60 s windows rendered 254 to 808 frames (p90 16 to 31 ms). A card that stopped less than 120 s earlier doesn't ring again when it restarts (the re-pulse cooldown), so such a run rings once; the accent still fades on every flip.
- The cold start onto the compiled profile took 548 ms (`am start -W`, TotalTime).

**v3 (0.3.0).** The release build on the wall, 2026-10-01, with live data.

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

- **Memory.** The budget is 95 MB. PSS peaked at 72.2 MB during the 40 extra opens and came back to 64.8 MB, so it is within budget and not climbing. A 24 h soak with panels is still to do.
- **Contrast.** On the lighter glass, 16 sp muted text fell to 6.5:1 on the brightest photo in rotation (forest, luma 0.43), so `inkMuted` went from ink × 0.72 to ink × 0.78. Every measured card is now at least 7.3:1, and ink text measures 11 to 15:1 (DESIGN §8.3).

## How it works

- `data/SidecarClient` GETs `/api/config`, `/api/state`, `/api/detail/<id>`, `/api/backgrounds` and `/api/background/<name>`, each with `?layout=tablet`. The detail call allows 15 s to read and 20 s overall. Every call returns a `Fetch` (Ok / HttpError / NetworkError / ParseError) and never throws. The base URL is `BuildConfig.SIDECAR_BASE` and the layout name is `BuildConfig.LAYOUT`.
- `data/Models` mirrors the contract with unknown keys ignored, so a newer sidecar never breaks an older APK. Config is `@Serializable`. State stays raw JSON and is read per module: `tile` (with `glyph`, `active` and `level`), `items`, `doors` and `machines`.
- `ui/DashboardViewModel` polls config at start and every 10 min, and state every 1 s, backing off to 30 s after 3 straight failures. Each good poll is projected off the main thread into immutable card models (`ui/model/Project.kt`). `PollTracker` carries the pulse and new-row baselines from one good poll to the next.
- `ui/Layout.tileRect` places each module's `tile.{col,row,w,h}` on the config grid, below the 56 dp header, with 12 dp margins and 10 dp gaps. The header reads "connecting" until the first state fetch finishes; after that, `freshness()` drives its dot: live up to 30 s, lagging up to 2 min, then offline. When offline, the "No data since" banner slides up, the cards dim and lose their accents, and the laundry LED bars hold still. The banner and the dimming wait for the first state fetch to finish, so a cold start doesn't flash them. When a value module goes stale, `ui/model/TileHold` keeps its last good reading, shown as live for 5 minutes and then greyed and marked "as of h:mm a" (dropped at local midnight), and the header reads "degraded · Water" (priority: connecting, offline, lagging, degraded, live).
- Card choice: kind `doors` → `DoorsCard`, kind `laundry` → `LaundryCard` (each falls back to a value card if its array is missing), tile type `agenda` → `AgendaCard`. Everything else gets a `ValueCard` showing hero/sub/detail and an optional level bar. This is the same fallback rule as the Roku's `hkModuleKind`.
- `ui/backdrop` rotates the sidecar's photos every `background.intervalMs` (3 min live), in a shuffled order with the list re-read every 10 min. It decodes a sharp 1024×600 copy and a pre-blurred 256×150 copy before swapping; the cards' frost is cut from the blurred copy. During the config's `nightDim` window the window brightness drops to `nightDim.brightness`; the photos keep rotating.
- A card tap opens a detail panel (`ui/detail/`, `DashboardViewModel.openDetail`): the sidecar's `/api/detail/<id>` blocks, refreshed every 60 s, or, for Calendar and Activity, the items already in the state. It closes on a tap, Back, 90 s, or any alert. A header tap peeks at the photo for up to 30 s, and ‹ › step back through the last 20 photos shown or on to new ones. See DESIGN §8.10.
- Against burn-in, the UI layer (header and cards, not the photo) steps around a ±2 dp ring every 10 min.
- Cleartext HTTP is allowed only to `192.0.2.20` (`res/xml/network_security_config.xml`).

## Test fixtures

`app/src/test/resources/` holds three fixtures:

- `config.json` and `state.json` are the live sidecar's `?layout=tablet` responses, last captured on 2026-10-01 (re-captured with the v3 rate tiles). Re-capture them whenever the sidecar's output changes (below).
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

Fire OS 8 ignores `setShowWhenLocked`. Once the screen sleeps, the swipe lockscreen comes back in front of the app. Stay-awake-while-charging keeps the screen on in normal use. The fix is device-side: `adb shell locksettings set-disabled true` (the tablet has no PIN; undo with `set-disabled false`), together with the HOME takeover in the kiosk phase. As of 2026-10-01 this has not been applied (`locksettings get-disabled` reads `false`), so it still has to be run by hand.
