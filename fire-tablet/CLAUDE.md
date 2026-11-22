# CLAUDE.md

**fire-tablet/** is the native Android app (`io.haku.tablet`, "HAku Kitchen") for the kitchen wall Fire 7: a house-status board with tap-to-expand detail panels, a photo peek you can step through, and a door camera that shows the front steps full screen for a minute after the front door opens. It is a client of the HAku sidecar, which also feeds the Roku wall. It has no controls that change house state.

- **Design:** `../docs/fire-tablet/DESIGN.md` (§8 is the v2 UI: 4×3 smoked-glass cards over rotating photos; §8.10 is the v3 touch layer: detail panels and the photo peek; §8.11 is the door camera). Exact colours, sizes, timings and JSON shapes: `../docs/superpowers/plans/2026-09-30-tablet-ui-v2-contract.md` (v2) and `../docs/superpowers/specs/2026-10-01-tablet-v3-details-contract.md` (v3: `/api/detail`, rate tiles, tones, timings). Build, install, demo mode, logs, fixtures and measurements: `README.md`.
- **Device:** Fire 7 12th gen `KFQUWI`, `192.0.2.60`, Fire OS 8 (API 30), 1024×600, ~790 MB free RAM, LAN-only (MikroTik `iot`). From the MiniPC it is reached over USB, ADB serial `$TABLET_SERIAL`; wireless adb is in `README.md` § Install. The device doc is `~/code/home-arr/docs/KITCHEN-TABLET.md`.
- **Server:** `haku-sidecar` on nserver, `http://192.0.2.20:1986` (`/api/config`, `/api/state`, `/api/detail/<id>`, `/api/backgrounds`, `/api/background/<name>`, all with `?layout=tablet`); its source and JSON contract are in `../sidecar/`. The door camera plays the stream server's HLS on `192.0.2.20:1985` (`../stream/`). Photos are curated in the NAS folder `/mnt/media/haku/kitchen` (DESIGN §8.1).
- **Fixtures:** when the sidecar's JSON changes, re-capture `app/src/test/resources/{config,state}.json` and scrub personal calendar titles before committing (`README.md` § Test fixtures). Leave `detail_weather_v1.json` alone.

## Commands

```bash
./gradlew testDebugUnitTest assembleDebug assembleRelease --offline
# The wall runs the release build (R8, debug-signed, so install -r swaps it with a debug build in place):
adb -s $TABLET_SERIAL install -r app/build/outputs/apk/release/app-release.apk
adb -s $TABLET_SERIAL shell am start -n io.haku.tablet/.MainActivity
adb -s $TABLET_SERIAL shell am broadcast -a androidx.profileinstaller.action.INSTALL_PROFILE -n io.haku.tablet/androidx.profileinstaller.ProfileInstallReceiver
adb -s $TABLET_SERIAL shell cmd package compile -f -m speed-profile io.haku.tablet
adb -s $TABLET_SERIAL shell am force-stop io.haku.tablet && adb -s $TABLET_SERIAL shell am start -n io.haku.tablet/.MainActivity
# Debug build; `--es demo quiet|busy|alert|cycle|offline|degraded|door` replays canned states (debug only):
adb -s $TABLET_SERIAL install -r app/build/outputs/apk/debug/app-debug.apk
adb -s $TABLET_SERIAL logcat -s KitchenWall
adb -s $TABLET_SERIAL exec-out screencap -p > shot.png
```

The stack is pinned to the versions in another local Android project (AGP 8.7.3, Kotlin 2.1.20, Compose BOM 2025.02.00, Gradle 8.10.2), so it resolves from the MiniPC's Gradle cache. Bump them deliberately.

## Rules

- **Don't sleep/wake the tablet to test.** Just screenshot it. Each sleep brings back the Fire lockscreen, which hides the app.
- **Fire OS 8 ignores `setShowWhenLocked`.** The fix is device-side (`locksettings set-disabled true`) plus the HOME takeover, not app code (DESIGN §4.5).
- **The sidecar owns formatting.** Cards render `tile.{hero,sub,detail,severity}`, each door's `age` and each machine's `status` as given, and take `tile.{glyph,active,level}` as state. Unknown keys and unknown `tile.type` must keep working (fall back to a `ValueCard`), the same rule as the Roku's `hkModuleKind`. Detail payloads follow it too: the blocks in `/api/detail/<id>` (`stats`, `chart`, `days`, `forecast`, `rows`, and the weather panel's `now` and `hourly`) render their strings verbatim, and an unknown or malformed block is skipped. A block's `col` (0 or 1) only chooses a column. Only chart geometry is computed on the tablet. The Calendar and Activity panels are the exception: they are built on the tablet from the `items` already in `/api/state`, with no fetch.
- **Overlays close by themselves, and nothing may hide an alert.** A detail panel closes 90 s after it opens, a photo peek 30 s after it starts or was last stepped, and the door camera at the sidecar's `until` (60 s after the door opened). Each also closes on any ALERT pulse; a peek also ends when the photo goes away, and the camera on a player error. Never add a control that changes house state (no toggles, no acknowledge): a tap only opens a panel, closes it, peeks, steps the peek's photo with ‹ › (DESIGN §8.10), or closes the camera (§8.11).
- **Keep it light.** The PSS budget is 95 MB, measured on the release build, not debug (`README.md` § Measurements). Don't add heavy dependencies (DI, image loading, WebView, a player library) without a reason. None has been added: photos decode with `BitmapFactory`, glyphs are bundled MDI path data, the frost is cut from a pre-blurred copy because API 30 has no `RenderEffect`, the charts are `drawWithCache` paths, and the camera is a framework `VideoView`.
- **Calm by default.** Nothing animates while the house is quiet; the only loop is the laundry LED bar, stepped at 10 fps or less. The door camera's video is the one exception, and only for the minute after the door opens. Detail panels and the peek add no loops: the reveal (250 ms), the peek fade (400 ms) and the peek's step cross-fade (300 ms) are one-shot tweens, and charts are static. Read animated values in draw or layout lambdas, never in composition (DESIGN §8.6).
- **State polls every 1 s** (`STATE_EVERY_MS`), so nothing logs per poll: `poll_ok` goes to logcat once a minute and on recovery.
- **API 30 only.** minSdk is 30 (Fire OS 8), so nothing may need API 31+: no `RenderEffect`, `Modifier.blur` or dynamic colour.
- **Cleartext HTTP is allowed only to the sidecar's host** (`network_security_config.xml`, generated by the `generateNetworkSecurityConfig` task in `app/build.gradle.kts` from `haku.sidecarBase` in `local.properties`): the sidecar on `:1986` and the stream server's HLS on `:1985`.
