# CLAUDE.md

**fire-tablet/** is the native Android app (`io.haku.tablet`, "HAku Kitchen") for the kitchen wall Fire 7. It is a house-status board with tap-to-expand detail panels and a photo peek you can step through, and a client of the HAku sidecar that also feeds the Roku wall. It has no controls that change house state.

- **Design:** `../docs/fire-tablet/DESIGN.md` (§8 is the v2 UI: 4×3 smoked-glass cards over NAS photos, built 2026-09-30 to 2026-10-01; §8.10 is v3 touch: detail panels and the photo peek, 2026-10-01). Exact colours, sizes, timings and JSON shapes: `../docs/superpowers/plans/2026-09-30-tablet-ui-v2-contract.md` (v2) and `../docs/superpowers/specs/2026-10-01-tablet-v3-details-contract.md` (v3: `/api/detail`, rate tiles, tones, timings). The peek's back and forward buttons (0.4.0) are in §8.10 "Browsing the photos". Build, install, logs and measurements: `README.md`.
- **Device:** Fire 7 12th gen `KFQUWI`, ADB serial `$TABLET_SERIAL`, `192.0.2.60`, Fire OS 8 (API 30), 1024×600, ~790 MB free RAM. It is LAN-only (MikroTik `iot`). The device doc is `~/code/home-arr/docs/KITCHEN-TABLET.md`.
- **Server:** `haku-sidecar` on nserver, `http://192.0.2.20:1986` (`/api/config`, `/api/state`, `/api/detail/<id>`, `/api/backgrounds`, `/api/background/<name>`, all with `?layout=tablet`). Its source and its JSON contract live in `../sidecar/`. When that output changes, re-capture `app/src/test/resources/{config,state}.json` with `curl`, and scrub personal calendar titles before committing (steps in `README.md`).

## Commands

```bash
./gradlew testDebugUnitTest assembleDebug assembleRelease --offline
# The wall runs the release build (R8, debug-signed, so install -r swaps it with a debug build in place):
adb -s $TABLET_SERIAL install -r app/build/outputs/apk/release/app-release.apk
adb -s $TABLET_SERIAL shell am start -n io.haku.tablet/.MainActivity
adb -s $TABLET_SERIAL shell am broadcast -a androidx.profileinstaller.action.INSTALL_PROFILE -n io.haku.tablet/androidx.profileinstaller.ProfileInstallReceiver
adb -s $TABLET_SERIAL shell cmd package compile -f -m speed-profile io.haku.tablet
adb -s $TABLET_SERIAL shell am force-stop io.haku.tablet && adb -s $TABLET_SERIAL shell am start -n io.haku.tablet/.MainActivity
# Debug build; `--es demo quiet|busy|alert|cycle|offline|degraded` replays canned states (debug only):
adb -s $TABLET_SERIAL install -r app/build/outputs/apk/debug/app-debug.apk
adb -s $TABLET_SERIAL logcat -s KitchenWall
adb -s $TABLET_SERIAL exec-out screencap -p > shot.png
```

The stack is pinned to the versions in another local Android project (AGP 8.7.3, Kotlin 2.1.20, Compose BOM 2025.02.00, Gradle 8.10.2), so it resolves from the MiniPC's Gradle cache. Bump them deliberately.

## Rules

- **Don't sleep/wake the tablet to test.** Just screenshot it. Each sleep brings back the Fire lockscreen, which hides the app.
- **Fire OS 8 ignores `setShowWhenLocked`.** The fix is device-side (`locksettings set-disabled true`) plus the HOME takeover, not app code.
- **The sidecar owns formatting.** Cards render `tile.{hero,sub,detail,severity}`, each door's `age` and each machine's `status` as given, and take `tile.{glyph,active,level}` as state. Unknown keys and unknown `tile.type` must keep working (fall back to a `ValueCard`), the same rule as the Roku's `hkModuleKind`. Detail payloads follow it too: the blocks in `/api/detail/<id>` (`stats`, `chart`, `days`, `forecast`, `rows`, and the weather panel's `now` and `hourly`) render their strings verbatim, and an unknown or malformed block is skipped. A block's `col` (0 or 1) only chooses a column. Only chart geometry is computed on the tablet. The Calendar and Activity panels are the exception: they are built on the tablet from the `items` already in `/api/state`, with no fetch.
- **Overlays close by themselves, and nothing may hide an alert.** A detail panel closes 90 s after it opens and a photo peek ends after 30 s. Either one also closes on any ALERT pulse, and a peek ends when the photo goes away. Never add a control that changes house state (no toggles, no acknowledge): a tap only opens a panel, closes it, peeks, or steps the peek's photo with ‹ › (DESIGN §8.10).
- **Keep it light.** The v3 release build settled at 51 to 65 MB PSS on 2026-10-01 (72.2 MB at the peak, during 40 panel opens; the budget is 95 MB). The two-column weather panel measured 47.9 MB fresh and 59.9 MB after 20 weather opens on 2026-10-03. The v2 release build measured 54 to 61 MB the same day, the debug build ran 80 to 94 MB, and v0.1.0 was 70.8 MB. Measure the release build, not debug. Don't add heavy dependencies (DI, image loading, WebView) without a reason. v2 and v3 added none: photos decode with `BitmapFactory`, glyphs are bundled MDI path data, the frost is cut from a pre-blurred copy because API 30 has no `RenderEffect`, and the charts are `drawWithCache` paths with no chart library.
- **Calm by default.** Nothing animates while the house is quiet; the only loop is the laundry LED bar, stepped at 10 fps or less. Detail panels and the peek add no loops: the reveal (250 ms), the peek fade (400 ms) and the peek's step cross-fade (300 ms) are one-shot tweens, and charts are static. Read animated values in draw or layout lambdas, never in composition (DESIGN §8.6).
- **API 30 only.** minSdk is 30 (Fire OS 8), so nothing may need API 31+: no `RenderEffect`, `Modifier.blur` or dynamic colour.
- **Cleartext HTTP is allowed only to `192.0.2.20`** (`res/xml/network_security_config.xml`).
