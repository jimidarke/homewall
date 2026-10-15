# Door camera on the tablet + office Roku, and 1 s polling — design (HAku 1.2)

Date: 2026-10-14. Status: shipped. Roku 1.2.1 is on the four fleet Rokus that were on HAku; the Den runs Netflix (see Rollout). The tablet is on 1.1.0 (versionCode 6) and the sidecar on 1.1.0. HA is live. Plan: `docs/superpowers/plans/2026-10-14-door-camera-and-1s-polling.md`.

## Asked for

1. Opening the front door shows the Genbolt fixed lens (`front_steps`), not the PTZ. The full-screen takeover goes to the **office Roku only**.
2. Poll every 1 s everywhere: sidecar → HA, Rokus → sidecar, tablet → sidecar. Validate it, and back off a few seconds where needed.
3. The kitchen tablet shows the same camera **full screen for the same minute** when the door opens. Tap to close. Idle otherwise.

## Design

**HA.** `housewall_front_door_opened` sends `cam=front_steps&severity=normal&reason=opened&banner=Front+Door+opened` to `rest_command.housewall_office`. `replay=15` was dropped: it never gave extra pre-roll.

**Sidecar (1.1.0).**
- **Polling:** HA's `/api/states` is polled every second (`HAKU_POLL_INTERVAL=1`; the floor is 1, was 2). The cadence is fixed, so the fetch counts toward the interval.
- **Failure backoff:** a failed on-demand read (logbook, calendar, forecast, history) is held back for 15 s instead of being retried on every request.
- **Door openings:** the poller records off→on edges (`HAClient.last_on`), dated by HA's `last_changed`.
- **Takeover:** the doors module's new `camera` key, `{door, cam, sec, label}`, adds `takeover: {cam, hls, label, until}` for `sec` after that door opens. `hls` comes from `HAKU_HLS_BASE`. The key appears only in layout views, and only while active, so the default view and its golden test are untouched.

**Roku (1.2.1).**
- **Poll interval:** 1 s (`HK_STATE_POLL_MS`), except **2 s on the Roku Express 3930** (`hkStatePollMsFor`).
- **Timeout:** a 3 s deadline on each state fetch (`hkHttpGetJsonTimeout`).
- **Config refresh:** a sticky `configPending` flag, so a dropped `RUN` can't lose a config refresh.
- **Repaints:** `ModuleTile` skips repainting unchanged values.
- **Logging:** `poll_ok` once a minute and on recovery; `poll_fail` once per outage.

**Tablet (1.1.0).**
- **Polling:** state every 1 s; `poll_ok` once a minute and on recovery.
- **Opening:** `HubState.takeover()` → `DashboardViewModel.cam`, which opens once per `until`. It runs for `until − ts` on the sidecar's clock and ends any peek or panel.
- **Closing:** at `until`, on a tap or Back, on any ALERT, or on a player error.
- **Player:** `CamLayer` is a framework `VideoView` in an `AndroidView` (no new dependency; Media3 isn't in the offline Gradle cache), muted, with no audio focus, fitted 16:9, with a label chip and "Connecting…".
- **Demo:** `--es demo door`.
- **Design rules:** DESIGN §8.11; §8.6 gains the one calm-by-default exception.

## Measurements (2026-10-14)

**Servers, every client at 1 s:**
- The sidecar averages 2.9% of one core (max 3.2%).
- HA serves its 302 KB `/api/states` in 5 ms. The container sits around 1% CPU, with two one-off spikes in 20 samples, likely HA's own work.

**Rokus, 20 min at 1 s:**

| Roku | Behind live (median) | Stalls |
|---|---|---|
| `.55`, `.53`, `.51`, `.54` | 5.2–5.8 s | none |
| Kids Express `.52` | 10.1 s (peaks of 32 s) | 15 bad samples |

At 2 s the Express measured 6.6 s median, 10.5 s worst, which is why it polls at 2 s.

**Tablet release:**
- Idle at 1 s: 49–62 MB PSS, 0–5 frames per 10 s untouched. Bursts only came from someone opening detail panels.
- **End to end:** HA logged the front door at 19:00:58.6. The tablet opened the camera about 1.5 s later (watcher time) and closed it after 59 s. PSS was 63.6–65.7 MB during the video and 66 MB after (budget 95 MB). The office Roku was playing `front_steps`.

## Rollout

The Roku 1.2.1 sideload interrupted Apple TV on `.53` (relaunched afterwards) and Netflix on `.54`, which was left alone at the user's request. Fleet deploys now check `/query/active-app` first.

## Not done

- Wireless adb is on (port 5555), but only nserver can reach the tablet. The MiniPC is blocked by `iot`, and the setting resets on reboot.
- The tablet test fixtures got the doors `camera` key added, not a full re-capture.
- `refreshMs` is still dead config.
