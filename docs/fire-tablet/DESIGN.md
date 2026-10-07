# Kitchen Tablet Display: Design

> Date: 2026-09-30
> Status: **Approved and built.** The APK proof of concept was verified on the device on 2026-09-30 (now `~/code/homewall/fire-tablet`). The sidecar changes (§3, refined in §8.8) are deployed on nserver, and since 2026-10-01 the v2 UI (§8) runs on the wall as the R8 release build. The kiosk takeover in §4.5 is not built yet. Results: [KITCHEN-TABLET.md § Display App](../../../home-arr/docs/KITCHEN-TABLET.md#display-app-haku-tablet).
> **v2 (the UI/UX build) was approved on 2026-09-30.** It is specified in [§8](#8-ui-v2-2026-09-30) and supersedes the lines marked "(superseded by §8)" below.
> **v3 (touch) was built on 2026-10-01 (0.3.0).** Tap-to-expand detail panels and a photo peek are in [§8.10](#810-touch-detail-panels-and-photo-peek-v3-2026-10-01). v3 also lightens the glass (§8.3) and holds stale values (§8.5).
> **0.4.0 (2026-10-05)** adds back and forward buttons to the photo peek, to browse the photos the wall has shown and deal new ones (§8.10, "Browsing the photos").
> Device: Fire 7 `KFQUWI` at `192.0.2.60` (see [home-arr KITCHEN-TABLET.md](../../../home-arr/docs/KITCHEN-TABLET.md))
> Data source: HAku sidecar on nserver, `http://192.0.2.20:1986` (`~/code/homewall/sidecar`)

---

## 1. Goal

A wall-mounted kitchen display that shows the house's current activity at a glance. It has no controls that change house state; since v3 a tap opens a detail panel or peeks at the photo, and since 0.4.0 steps through the photos while peeking (§8.10). One screen shows:

| Panel | Shows |
|-------|-------|
| Doors | Front and back door contact: open/closed, and how long ago each last changed |
| Laundry | Washer and dryer state, with the same five states and colours as the kitchen laundry notifier's LED bar |
| Weather | Current temperature and condition, today's high/low |
| Power | Live house draw, kWh and cost today |
| Water | Usage this hour, flow state, 24 h and 30 d totals |
| Gas | Gas flow rate and meter total (see §7.1) |
| Activity | The curated "Recent Activity" feed that already runs on the Roku wall |

The structure and content follow HAku, the Roku home wall (`~/code/homewall/roku`): a grid of glass cards, each fed by a sidecar module.

**Success criteria**

- Every panel is readable from across the kitchen on a 7" 1024×600 screen.
- A door change shows on the tablet within about 15 s.
- The tablet runs for weeks unattended without freezing or dropping back to the Fire launcher.
- The Roku fleet sees no change.

**Out of scope for v1:** controls (toggles, acknowledging laundry), cameras, the calendar, push or voice alerts, charge management (planned separately as a smart plug), and HA notifications (the HA Companion app keeps doing those). (Superseded by §8: the calendar is now in scope; cameras stay out.)

## 2. Architecture

```
Home Assistant (mserver .10)
        │  REST /api/states every 10 s + logbook (TTL-cached)
        ▼
haku-sidecar (nserver .20:1986)
   ├─ existing modules: weather, energy, water, gas, timeline, …
   ├─ NEW modules: doors, laundry
   └─ NEW: per-display layouts  →  /api/config?layout=tablet
        │                           /api/state?layout=tablet
        │  plain HTTP over LAN (tablet is in iot: LAN-only)
        ├──────────────────────────────┐
        ▼                              ▼
4× Roku HAku channel            Kitchen tablet APK (NEW)
(default layout, unchanged)     native Kotlin kiosk, HOME launcher
```

**Why the sidecar** (decided 2026-09-30):

- No HA token lives on the tablet.
- HA load stays at one `/api/states` poll regardless of how many displays there are.
- Formatting and the activity feed's noise filtering are written once and shared with the Rokus.

**Cost:** the tablet depends on nserver being up, and a change shows up after 10 s (sidecar poll) plus the tablet's own poll interval. Both are acceptable for a status display.

**Verified 2026-09-30:** the tablet reaches `192.0.2.20:1986` through the quarantine (an `/api/health` GET from the tablet returned `ha_connected: true`).

## 3. Sidecar changes (`sidecar/`)

### 3.1 Per-display layouts

**The problem.** The live `/etc/haku/dashboard.json` already fills the Roku's 4×2 grid. `/api/config` returns the file almost unchanged, and the Roku builds a tile for every entry in `modules`. Adding `doors` and `laundry` there would push them onto every Roku.

**The fix.** Add an optional top-level `layouts` map. Each layout has its own grid, and its module list can do two things:

- reference existing modules by id, optionally with a different `tile` position;
- define modules that only that layout uses.

```jsonc
{
  "modules": [ /* unchanged — the Roku layout */ ],
  "layouts": {
    "tablet": {
      "grid": { "cols": 4, "rows": 2, "width": 1024, "height": 600 },
      "header": { "clock": true },
      "nightDim": { "start": "22:00", "end": "06:30", "brightness": 0.15 },
      "modules": [
        { "id": "doors",   "kind": "doors",   "feedKey": "doors",   "refreshMs": 5000,
          "tile": { "type": "value", "col": 0, "row": 0, "w": 1, "h": 1 },
          "openAlertSec": 300, "lookbackHours": 24,
          "entities": { "doors": [
            { "id": "front", "entity": "binary_sensor.front_doorcontact_contact", "label": "Front" },
            { "id": "back",  "entity": "binary_sensor.back_doorcontact_contact",  "label": "Back"  } ] } },
        { "id": "laundry", "kind": "laundry", "feedKey": "laundry", "refreshMs": 5000,
          "tile": { "type": "value", "col": 1, "row": 0, "w": 1, "h": 1 },
          "machines": [
            { "id": "washer", "label": "Washer", "color": "#00AAFF" },
            { "id": "dryer",  "label": "Dryer",  "color": "#FF6900" } ] },
        { "ref": "weather",  "tile": { "type": "value",  "col": 2, "row": 0, "w": 1, "h": 1 } },
        { "ref": "energy",   "tile": { "type": "value",  "col": 0, "row": 1, "w": 1, "h": 1 } },
        { "ref": "water",    "tile": { "type": "value",  "col": 1, "row": 1, "w": 1, "h": 1 } },
        { "ref": "gas",      "tile": { "type": "value",  "col": 2, "row": 1, "w": 1, "h": 1 } },
        { "ref": "timeline", "tile": { "type": "agenda", "col": 3, "row": 0, "w": 1, "h": 2 } }
      ]
    }
  }
}
```

(Superseded by §8: the live block is a 4×3 grid with no `header` key, it adds `background`, and `lookbackHours` is 12. The exact shape is in the [v2 contract](../superpowers/plans/2026-09-30-tablet-ui-v2-contract.md) §1.1.)

**How the endpoints behave:**

| Request | Response |
|---------|----------|
| `GET /api/config` (no param) | Same as today, minus the `layouts` key. **What the Roku receives is unchanged.** |
| `GET /api/config?layout=tablet` | `version`, `site`, `timezone`, the `sidecar` block, plus the layout's `grid`, `header`, `nightDim` and its **resolved** modules. Each `ref` entry becomes the referenced module's full descriptor with `tile` (and any other keys given on the entry) overridden. (Superseded by §8: there is no `header`; the response also carries `background`, laid over the top-level block, without its server-side `dir`.) |
| `GET /api/state` (no param) | Unchanged. |
| `GET /api/state?layout=tablet` | `compose_state` over the resolved modules only, keyed by `feedKey`. |
| `GET /api/module/<id>` | Also finds modules defined only in a layout. (Superseded by §8: it looks in a layout only when the request carries an explicit `?layout=`.) |
| Unknown layout, or a `ref` that doesn't exist | `404 {"error": "unknown layout"}` or `{"error": "unknown ref", "ref": …}`. The tablet shows this as a config error and doesn't render a blank screen. |

**Code touched:**

- `config.py`: `get_layout(name)` and ref resolution.
- `app.py`: read the `layout` query param on `/api/config`, `/api/state` and `/api/module`.
- `modules/__init__.py`: register `doors` and `laundry`.

`compose_state` itself doesn't change; it receives the resolved list.

**No discovery schema bump.** `discovery.json` and its contract test are untouched.

### 3.2 `doors` module (`modules/doors.py`)

The Roku's `HK_MODULE_KINDS()` already reserves `doors` (tile `value`, drill `agenda`), so this fills a planned slot.

**Inputs:** `entities.doors[]`, each with `{id, entity, label}`. `openAlertSec` defaults to 300 and `lookbackHours` to 24. (Superseded by §8: `lookbackHours` now defaults to 12, so the logbook cache entry is shared with the timeline. §8.8 also refines the "since" rule below.)

**"Last changed" has to come from the logbook, not `last_changed`.** The contacts are Zigbee2MQTT entities, and HA re-stamps `last_changed` when it restarts. A restart would make the doors look like they changed "2 m ago". The module therefore uses the time of the newest open/close row from `ha.get_logbook(entity, lookbackHours)`, which is already TTL-cached for 30 s and shared with `timeline`. Only when the logbook has no row in that window does it fall back to `last_changed`, with `since_exact: false` so the tile can show "> 12h" (the sidecar sends the age `> {lookbackHours}h`, and `lookbackHours` is 12).

**State mapping:** `on` → `open`, `off` → `closed`, anything else (`unavailable`/`unknown`) → `unknown`.

**Output:**

```jsonc
{
  "doors": [
    { "id": "front", "label": "Front", "state": "closed", "since": 1790821800,
      "since_exact": true, "age": "12m", "severity": "normal" },
    { "id": "back",  "label": "Back",  "state": "open",   "since": 1790822400,
      "since_exact": true, "age": "6m",  "severity": "high" }
  ],
  "open_count": 1,
  "stale": false,
  "tile": { "hero": "Back open", "sub": "6m", "detail": "Front closed · 12m",
            "severity": "high", "icon": "open" }
}
```

**Severity:** a door gets `high` once it has been open longer than `openAlertSec`. A door opened briefly stays `normal`, so routine entries don't flash red. A door in the `unknown` state gets `low` and grey styling.

**Hero text:**
- all closed → "All closed";
- one open → "Back open";
- both open → "2 open";
- every door unknown → `stale: true`.

`age` uses the same compact format as the timeline ("now", "6m", "2h", "3d").

### 3.3 `laundry` module (`modules/laundry.py`)

The module reproduces the **kitchen laundry notifier** (`esp-laundry`) on screen. All the state logic already lives in HA (`/root/docker/homeassistantV3/config/ha/packages/laundry.yaml`). The ESPs render purely from these sensors, and the sidecar does the same: it **mirrors** the sensors and never re-derives them.

**HA contract it reads, per machine `m` ∈ washer, dryer:**

| Entity | Use |
|--------|-----|
| `sensor.laundry_<m>_mode` | `idle` / `running` / `overtime` / `done` / `done_calm` |
| `sensor.laundry_<m>_leds` | 0–4 pixels, a countdown of remaining time. Only meaningful while `running` |
| `input_datetime.laundry_<m>_started` | Cycle start (`timestamp` attribute, epoch seconds; < 1e9 means never set) |
| `input_datetime.laundry_<m>_finished` | Cycle end (same) |
| `input_number.laundry_<m>_expected_minutes` | 55 washer / 45 dryer today |
| `sensor.emporia_circuit_7_power` / `_8_power` | Washer / dryer watts (optional; mapped by descriptor) |

**Entity naming.** The entity ids follow from `machines[].id` by convention, as `laundry.yaml` does. A machine may override any of them with an `entities` map, for example `"power": "sensor.emporia_circuit_7_power"`.

**Output:**

```jsonc
{
  "machines": [
    { "id": "washer", "label": "Washer", "color": "#00AAFF", "mode": "running", "leds": 3,
      "started": 1790817982, "elapsed_min": 21, "expected_min": 55, "remaining_min": 34,
      "power_w": 186, "stale": false },
    { "id": "dryer",  "label": "Dryer",  "color": "#FF6900", "mode": "done_calm", "leds": 0,
      "finished": 1790799176, "finished_hm": "9:52 AM", "stale": false }
  ],
  "stale": false,
  "tile": { "hero": "Washer 34m left", "sub": "Dryer done 9:52 AM", "detail": "",
            "severity": "normal", "icon": "running:3|done_calm:0" }
}
```

**Edge cases:**

- **Remaining time** is `remaining_min = max(0, expected − elapsed)`. It's only set while `running`. In `overtime`, the module reports `over_min` instead.
- **Unavailable sensors.** A machine whose mode sensor is unavailable gets `stale: true`. That's the equivalent of the LED bar's violet "NO DATA".

**Hero text, by priority:**
1. any machine `done` or `done_calm` → "Washer done";
2. any `overtime` → "Dryer running long";
3. any `running` → "Washer 34m left";
4. otherwise → "Laundry idle".

The second machine's status goes in `sub`.

**Severity:** `high` for `done` (the box's loud phase, the first 3 minutes), `normal` for everything else. `done_calm` is shown with an accent on the tablet, not as an alarm.

**No `render_icon` for v1.** The tablet draws the indicator natively (§4.4). Laundry isn't in any Roku layout, so the Roku has nothing to render.

### 3.4 Sidecar tests (`sidecar/tests/`)

These use the existing FakeHA pattern, with no HA and no network.

**Layouts**
- No `layout` param → `/api/config` and `/api/state` are byte-identical to today's output, apart from the dropped `layouts` key. This is the Roku regression guard.
- `?layout=tablet` resolves refs and overrides tiles.
- An unknown layout or a bad ref returns 404.

**Doors**
- all closed;
- one open under and over `openAlertSec`;
- unavailable → `unknown`;
- logbook empty → `last_changed` fallback with `since_exact=false`;
- `last_changed` newer than the logbook row (HA restart) → the logbook wins. (Corrected 2026-09-30: the earlier wording had the two reversed.)

**Laundry**
- each of the five modes;
- `leds` passed through;
- remaining and overtime minutes;
- started never set (< 1e9);
- mode unavailable → stale;
- hero priority when the two machines differ.

The existing `contract`/`unit` suites must still pass unchanged.

## 4. Tablet APK

### 4.1 Approach: native Kotlin

Three approaches were considered:

| Option | Verdict |
|--------|---------|
| **Native Kotlin app polling the sidecar** | **Chosen.** Light on a 2 GB / A53 device. Draws the laundry LED animations natively. Same pattern as the Roku channel: a thin client over the sidecar. |
| Kiosk WebView of a sidecar-served HTML page | UI changes wouldn't need a reinstall, but a Chromium renderer costs about 150 MB+ on a device with ~790 MB free, and the sidecar would need a web frontend. Reinstalling over WiFi ADB is cheap anyway. |
| HA Lovelace dashboard in a kiosk browser | Needs an HA login or token on the tablet, can't reuse HAku's curation, and has the known Fully Kiosk Fire 7 issues (see KITCHEN-TABLET.md). |

**Stack:**
- Kotlin and Jetpack Compose, in a single Activity;
- `minSdk 30` (Fire OS 8 is API 30), `targetSdk 34`;
- built with the Gradle wrapper and SDK build-tools that are already on the MiniPC (`~/Android/Sdk`, JDK 21).

**Dependencies:** OkHttp and kotlinx.serialization only. There's no DI framework, no database and no analytics.

**Where it lives:** `fire-tablet/` in the `~/code/homewall` monorepo. It started as `roku-homewall/tablet/`, had its own repo `~/code/tablet-homewall` from 2026-09-30, and was merged into `homewall` (without history) on 2026-10-03. The sidecar JSON contract it consumes is still defined and tested in `sidecar/`, so a sidecar change needs a matching tablet change here. The tablet's fixture tests (`app/src/test/resources/`, captured from the live sidecar) are what catch drift: re-capture them whenever the sidecar's output changes.

### 4.2 Components

| Unit | Responsibility | Depends on |
|------|----------------|-----------|
| `SidecarClient` | GET `/api/config`, `/api/state`, `/api/backgrounds` and `/api/background/<name>`, each with `?layout=tablet`. Returns a parsed value or a typed error (`Fetch`), never throws | OkHttp, models |
| `Models` | `@Serializable` mirrors of the config JSON; state is kept as raw JSON and read per module. Unknown keys are ignored so newer sidecars stay compatible | kotlinx.serialization |
| `DashboardViewModel` | Owns the poll loop (`viewModelScope`): config at start and every 10 min, state every 5 s. Backs off to 30 s after 3 consecutive failures. Exposes `UiState {sidecar, config, cards, error, stateFetched}` plus `lastOkAt`, `freshness`, `night` and `photo` flows | `HubSource` (`SidecarClient`) |
| `Dashboard` (Compose) | Header (clock, date, connection dot) plus a grid of cards placed from `tile.{col,row,w,h}` over `grid.{cols,rows}` | `UiState` |
| `ValueCard` | Generic hero/sub/detail/severity card. Used for weather, energy, water, gas and the thermostat | — |
| `DoorsCard` | One row per door: the state word plus the age | doors state |
| `LaundryCard` | One row per machine: a label, a status line and a 4-segment bar (§4.4) | laundry state |
| `AgendaCard` | The activity feed (a newest-first list of `items`, headers dropped as on the Roku via `dropHeaders`) and the calendar | timeline and calendar state |
| `MainActivity` | Keep-screen-on, immersive mode and the night-dim window brightness. The HOME intent filter (§4.5) is not built yet | — |

(Renamed in v2: the `*Tile` composables are now `ValueCard`, `DoorsCard`, `LaundryCard` and `AgendaCard`, each drawn inside a `GlassCard`; see §8.4.)

(Added in v3: `SidecarClient.detail(id)` for `GET /api/detail/<id>?layout=tablet`, the panels in `ui/detail/`, and `ui/model/TileHold.kt`; see §8.5 and §8.10.)

**Card choice.** The `kind` picks the card (`doors` → `DoorsCard`, `laundry` → `LaundryCard`). For any other kind, `tile.type` decides: `value` → `ValueCard`, `agenda` → `AgendaCard`. Anything unknown falls back to `ValueCard` using `tile.hero/sub/detail`, the same forward-compatibility rule as the Roku's `hkModuleKind`.

### 4.3 Layout and look

**Screen.** It assumes **1024×600 landscape**. A 4×2 grid with an 8 dp gap leaves about 245×265 dp per cell under a 40 dp header (density 160, so dp = px). The activity feed takes the right-hand column at full height. (The 4×2 grid and the sketch below are superseded by §8: the layout is now 4×3.)

```
┌─────────────────────────────────────────────────────────────┐
│ 8:42 PM   Wed Sep 30                                  ● live │
├──────────────┬──────────────┬──────────────┬────────────────┤
│ DOORS        │ LAUNDRY      │ WEATHER      │ RECENT         │
│ Front CLOSED │ Washer ▮▮▮▯  │   9°         │ Back Door      │
│        12m   │  34m left    │ Clear        │  closed · 11m  │
│ Back  CLOSED │ Dryer  ◆done │ H 15 / L 0   │ Front Door     │
│        11m   │  9:52 AM     │              │  closed · 12m  │
├──────────────┼──────────────┼──────────────┤ Front Entrance │
│ POWER        │ WATER        │ GAS          │  motion · 12m  │
│ 1.4 kW       │ 27 L         │ —            │ …              │
│ 23 kWh today │ idle         │ 18 m³ total  │                │
│ $4.82        │ 24h 368 L    │              │                │
└──────────────┴──────────────┴──────────────┴────────────────┘
```

**Visual style.** Dark theme only, since it hangs on a wall day and night. HAku's smoked-glass look is approximated with flat translucent cards; there's no photo background in v1, to keep it cheap. (Superseded by §8: v2 adds a photo backdrop from a NAS folder, with frosted-glass cards.)

**Severity colours** match HAku's `hwSeverityColor()`:
- `high`: red edge and red hero;
- `normal`: neutral;
- `low` or `stale`: dimmed grey.

(Superseded by §8.3 and §8.5: an alert is coral, `low` renders as normal, and stale dims the card's content to 50%.)

**Text size.** Hero text is at least 28 sp and labels at least 14 sp, so the screen reads from about 3 m. (Superseded by §8: labels are now at least 16 sp, and the hero is 44 sp stepping down to no less than 30 sp.)

### 4.4 Laundry indicator (on-screen version of the LED bar)

Each machine gets a 4-segment horizontal bar in its colour: washer cyan `#00AAFF`, dryer amber `#FF6900`. These are taken from the `esp-laundry` firmware (`/root/docker/esphome/config/.laundry-base.yaml` on nserver). The firmware's display legend:

| Mode | LED bar (firmware) | Tablet |
|------|--------------------|--------|
| `idle` | one dim red pixel | first segment dim red, status "idle" |
| `running` | `leds` pixels solid | `leds` segments solid, "34m left" |
| `overtime` | one pixel breathing | first segment breathing (sine, ~2.5 s), "running 8m long" |
| `done` | fast full-brightness bounce, 120 ms/step | segment bounce at 120 ms/step, tile severity high, "done" |
| `done_calm` | slow 60% bounce + trail, 450 ms/step | bounce at 450 ms/step at 60%, "done 9:52 AM" |
| stale / no data | violet comet | violet sweep, "no data" |

The mapping from mode to segment frames is a **pure function** of `(mode, leds, tMillis)` returning four brightness values, so it can be unit-tested without a device. Animations run only while their tile is in one of the animated modes. Idle and running are static, so no frames are drawn when nothing is happening.

### 4.5 Kiosk behaviour

**Status (2026-10-01).** Built: keep-screen-on, immersive mode, the night-dim window brightness, the cleartext rule, the status screen and the offline banner. Not built yet: the HOME takeover, the crash-restart handler and the `--es sidecar` override. The device lockscreen is still enabled (`locksettings get-disabled` reads `false`).

**Lockscreen (found in the proof of concept).** Fire OS 8 ignores `setShowWhenLocked`/`setTurnScreenOn`: after a screen sleep the swipe keyguard stays in front (`occluded=false`). The app keeps both calls, but the real fix is device-side: `adb shell locksettings set-disabled true` (the tablet has no PIN), applied together with the HOME takeover below.

**Taking over from the Fire launcher.** The activity declares `MAIN` + `HOME` + `DEFAULT`, and it's chosen as the home app with `adb shell cmd package set-home-activity`. Only after that is verified does `com.amazon.firelauncher` get disabled (setup-plan step 3). `com.android.launcher3` stays as a fallback.

**Screen.**
- Fullscreen immersive mode and `FLAG_KEEP_SCREEN_ON`.
- Stay-awake while plugged in is already `7`.
- Brightness is set per window (`WindowManager.LayoutParams.screenBrightness`), which needs no `WRITE_SETTINGS` permission.

**Night dim.** Between `nightDim.start` and `nightDim.end`, the window brightness drops to `nightDim.brightness`. The schedule comes from the layout config, so it can change without reinstalling. This is needed because the tablet has no light sensor.

**Network.** A `network_security_config` allows cleartext HTTP to `192.0.2.20` only. The sidecar address defaults to `http://192.0.2.20:1986`. It can be overridden over ADB with `am start -n <pkg>/.MainActivity --es sidecar http://…`, which is stored in SharedPreferences. There's no settings screen in v1. (Not built: the address is the build constant `BuildConfig.SIDECAR_BASE`, and the app keeps no SharedPreferences.)

**Failure modes.**

| Situation | Behaviour |
|-----------|-----------|
| State older than 30 s | Header dot turns amber |
| Older than 2 min | Grey banner "No data since 8:42 PM"; tiles dimmed, last values kept |
| Config error (404, unknown layout or ref) | Full-screen message naming the error and the sidecar URL |
| Module returns `error` | That tile shows "—" and the error is logged. (As built: a module with no tile or a blank hero shows "—"; nothing is logged per module. Since v3 a value card holds its last good reading instead, §8.5.) |
| App crash | It's the home activity, so Android relaunches it on the next home event. A `Thread.setDefaultUncaughtExceptionHandler` that restarts the activity via `AlarmManager` covers the case where nothing presses home. (Not built yet, see the status above.) |

**Logging.** Structured `logcat` lines tagged `KitchenWall` for `adb logcat -s KitchenWall`, each `event=<name> k=v`: `event=source`, `config_loaded`, `config_fail`, `poll_ok`, `poll_fail` and `pulse`, plus `bg_list`, `bg_list_fail`, `bg_photo` and `bg_miss` from the photo backdrop, and (v3) `detail_open`, `detail_close` and `detail_fail` for the detail panels. A failure ends `err=<reason>`, the same reason the offline banner shows (`http 502`, `network: …`, `parse: …`).

### 4.6 APK tests

**JVM unit tests (no device):**
- parse fixture JSON captured from the live sidecar for `config?layout=tablet` and `state?layout=tablet`, including unknown keys and missing optional fields;
- tile choice by kind and type;
- the laundry frame function for every mode;
- the night-dim window, including the midnight wrap;
- stale thresholds.

**On-device checklist (manual, over ADB):**
1. Install, set as home, reboot. It must come back to the dashboard.
2. Run `script.laundry_sim_cycle` for washer and dryer. Every mode must render (running 4→1, done, done_calm, idle).
3. Open and close the back door. The tile and the feed must update within about 15 s; past 5 min open, the tile must turn red.
4. Stop `haku-sidecar` on nserver. The amber dot must appear at 30 s and the banner at 2 min. Restart it and confirm recovery without touching the tablet.
5. Night dim: temporarily set `nightDim.start` to a few minutes from now. It must dim, then restore at `end`.
6. Soak test for 72 h with Smart Suspend off. No freeze, no return to the launcher, and no memory growth in `dumpsys meminfo` (start vs end).

## 5. Tablet prerequisites (from KITCHEN-TABLET.md)

- **Turn off Smart Suspend.** Found still on during the 2026-09-30 validation (`smartsuspend_enabled=1`). It's the documented cause of Fire 7 freezes every 2–3 days, and has to be off before the soak test. Low Power Mode is already off (`low_power=0`).
- **Enable WiFi ADB** (`adb tcpip 5555`) before mounting, so reinstalls don't need USB.
- **Mount orientation:** this design assumes landscape (§7.2).

## 6. Rollout order

1. Sidecar: layouts, `doors`, `laundry`, and tests. Deploy to nserver and add a `layouts.tablet` block to `/etc/haku/dashboard.json`.
2. Confirm the Rokus are unaffected: `GET /api/config` is unchanged and one Roku is checked visually.
3. Capture the live `?layout=tablet` JSON as fixtures for the APK.
4. Build the APK, install it over USB and run the on-device checklist.
5. Make it the home app, disable `com.amazon.firelauncher`, turn Smart Suspend off, enable WiFi ADB, mount, then run the 72 h soak.
6. Update KITCHEN-TABLET.md (setup plan steps 3–4) and the HAku docs (`HAKU_DESIGN.md`, sidecar README: layouts + new kinds).

## 7. Open items

1. ~~**Gas rate is broken.**~~ Fixed 2026-10-01 (v3). `sensor.home_gas_usage` held the last burn's rate and was unknown after every HA restart. The gas tile now reads `sensor.gas_flow`, which falls to 0 when the furnace is idle, and `sensor.gas_meter_total`, which keeps the last meter reading across restarts; a daily utility meter gives "today's gas" (HA `packages/gas_cost.yaml`, repo copy `sidecar/ha-gas-cost.yaml`).
2. **Mount orientation:** landscape is assumed. Portrait would be a second layout (2×4), configured in `dashboard.json` with no code change.
3. **Alex is missing from the activity feed.** `person.alex` is `unknown`, so she never appears. This is an HA and phone issue, separate from this work.
4. **HA Companion app:** it stays for now. It provides battery and charging sensors, which the charge-management plan will need, at a cost of about 96 MB of RAM. Revisit once charging is solved.
5. **Laundry acknowledge on tap:** deferred. It would need a POST endpoint on the sidecar (it's read-only today) or an HA token on the tablet, and v1 is read-only.
6. **Lockscreen:** `locksettings set-disabled true` is not yet applied or verified (see §4.5). If Fire OS overrides it, the fallback is device-owner mode, which needs a factory reset with no Amazon account.
7. **Charger:** the PC USB port is a low-power charger (Fire OS warns it may not charge while in use). The mount needs a 2 A+ supply.
8. **Faster recovery:** after WiFi returns, the app can take up to 30 s (the backoff) to go live again. A connectivity callback that polls right away would remove that delay. Minor.
9. **Water `active` flaps at a trickle.** On 2026-10-01, from about 07:55 to 09:00, the water flow alternated between 0.0 and 0.4 L/min every 10 to 20 s. Each flip turns the Water card on or off, and each turn-on pulsed, so the wall was never still. Since 0.2.0 the tablet holds back the ring for 120 s after a card stops (§8.6), so a run of flips rings once, but the accent still fades in and out on every flip. A hold time or hysteresis on `running` in the sidecar's water module, like the displayed-rate rule for gas, would fix it at the source. Not built.
10. **The ESP water meter keeps dropping off.** `esp-watermeter` (`192.0.2.41`) fails its ESPHome API handshake several times a day (12 outages in 7 days, 5 of them in one hour checked). v3 stops the wall from blanking (HA `always_available` on the water meters, held values, §8.5, §8.10), but the meter itself is not fixed. Stabilise its WiFi, its power or the ESPHome API keepalive.
11. **Gas has no price.** The bill figures in `packages/gas_cost.yaml` are placeholders (0), so `sensor.gas_marginal_cost_per_m3` reads 0 and the gas cost lines are left out. Fill them in and set `sensor.gas_marginal_cost_per_m3` as the gas price in HA's Energy dashboard. The gas cost lines and per-day costs then appear with no code change. Gas history also only starts on 2026-10-01, so its graph fills in over a week.
12. **The Emporia daily energy counter reset to 0 at 8:32 PM on 2026-10-01**, likely a device restart. Consider `restore: true` on its `total_daily_energy` in ESPHome.
13. **24 h soak with panels.** The v3 release build has been measured over minutes, not a day (§8.9). Run the 24 h PSS soak with panel opens and peeks.

## 8. UI v2 (2026-09-30)

v2 replaces the v0.1.0 look. The POC drew the Roku's layout: 8 equal flat cards, an empty "Cameras" card, no icons, no imagery, no motion, and labels below the size floor in §4.3. This section is the approved v2 design. Where it conflicts with §1 to §7, §8 wins, and the superseded lines are marked in place. §8.10 adds the v3 touch layer on 2026-10-01; where v3 changes a v2 value (§8.3, §8.5), the line says so.

The exact JSON shapes, glyph names, colours, sizes and timings are pinned in the [v2 contract](../superpowers/plans/2026-09-30-tablet-ui-v2-contract.md). If this section and the contract disagree on a value, the contract wins. The v3 values are in the [v3 contract](../superpowers/specs/2026-10-01-tablet-v3-details-contract.md). The build steps are in the [v2 plan](../superpowers/plans/2026-09-30-tablet-ui-v2.md), and the reference code sketches are in the [sketches](../superpowers/plans/2026-09-30-tablet-ui-v2-sketches.md).

### 8.1 Decisions

| Topic | Decision |
|-------|----------|
| Priority | **House activity first.** Doors, laundry, water and power lead. |
| Layout | **Even 4×3 grid.** Calendar spans 2 rows and Activity takes the full right column; every other card is one cell. Positions are fixed; cards **light up** when active instead of moving. |
| Photos | Full-bleed behind translucent smoked-glass cards. |
| Photo source | A new curated NAS folder, `/mnt/media/haku/kitchen` (NAS `192.0.2.5:/volume2/media`, already NFS-mounted on nserver), seeded from `/mnt/media/Drone`. The sidecar proxies the images, because the tablet can only reach `.20`. *Since 2026-10-07 nserver mirrors this folder into `HAKU_BG_DIR` every 15 min (`haku-bg-sync`), and the tablet and the wall Rokus both read the mirror; the folder is still where photos are curated.* |
| Modules | Doors, laundry, water, energy, thermostat, weather, gas, calendar and activity. **No cameras.** |
| Touch | v2 was glance-only, with no interaction. **Since v3 (2026-10-01):** tap a card for its detail panel, tap the header to peek at the photo, and (0.4.0) tap ‹ or › during the peek to step through the photos. No controls that change house state (§8.10). |
| Identity | **HAku family, refined**: the Roku's smoked glass, sage, coral and warm ink. |
| Typeface and icons | Barlow and a Material Design Icons subset, both bundled. Fire OS has no Play Services, so nothing is downloaded. |
| Motion | Calm by default, one-shot on change (§8.6). |
| Weight | No new libraries. No Coil, icon packs, Haze or Palette. |

### 8.2 Layout

1024×600 dp (mdpi, so dp = px).

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 9:17 PM   Wednesday, September 30                                ● live  │ header 56
├─────────────────┬──────────────────┬─────────────────┬───────────────────┤
│ Doors      [▣]  │ Laundry    [▣]   │ Calendar   [▣]  │ Activity     [▣]  │
│ ▯ Front Closed  │ ◘ Washer 34m left│ Today           │ ▢ Back Door       │
│            12m  │ ▮▮▮▯             │ ● Swim     all  │   closed · 6m     │
│ ▯ Back    Open  │ ◘ Dryer      done│ Tomorrow        │ ▢ Front Entrance  │
│             6m  │ ▯▮▯▯ (bounce)    │ ● Piano   3:30  │   motion · 7m     │
├─────────────────┼──────────────────┤ Fri · Oct 2     │ ▢ Bathroom door   │
│ Water      [▣]  │ Energy     [▣]   │ ● Soccer  5:00  │   opened · 17m    │
│ 57 L            │ 1.4 kW           │ Mon · Oct 5     │ ▢ Back Door       │
│ flowing 5.7 L/m │ 23 kWh today     │ ● Recital 7:00  │   closed · 45m    │
│ 24h 424 L       │ $4.99 so far     │                 │ …                 │
│ ▰▰▰▰▰           │ ▰▰▰              │                 │                   │
├─────────────────┼──────────────────┼─────────────────┤                   │
│ Weather    [☾]  │ Gas        [▣]   │ Thermostat [▣]  │                   │
│ 6°              │ 0.8 m³/h         │ 21°             │                   │
│ Clear           │ running          │ Heating         │                   │
└─────────────────┴──────────────────┴─────────────────┴───────────────────┘
```

- Insets are top 56 (the header), left, right and bottom 12, with a 10 dp gap.
- Each cell is about **242×171 dp**, Laundry included. Calendar is 2 cells tall (about 242×351 dp) and Activity takes the full column (about 532 dp tall).
- Inside a card, 74 dp go to padding and the title row, which leaves about 97 dp for a 1×1 card's body (2 door rows, or 2 laundry machines of a status line and a bar each), 277 dp for the Calendar (whole rows of 22 dp day headers and 26 dp events, 10 or 11 rows) and 458 dp for Activity (9 rows of 48 dp).
- Placement still comes from the sidecar's `tile.{col,row,w,h}`. `tileRect()` takes explicit insets so the grid sits under the header.
- The grid and the module list come from `layouts.tablet` in the sidecar (§3.1), so the layout can change without a reinstall.

### 8.3 Visual system

**Distance principle**
- **State** reads from 2 to 3 m, through colour, icon shape and fixed position.
- **Numbers** read from about 1 to 1.5 m. Detail is for walk-up reading.
- Size is spent on glyph chips and heroes.
- Normal is quiet and neutral (the ISA-101 rule). Only active or abnormal things get colour.
- `fontScale` is locked to 1.

**Colour tokens.** `ui/theme/Tokens.kt` replaces `Palette.kt`. The Roku values are kept.

| Token | Value | Use |
|-------|-------|-----|
| `ink` | `#FAF6EE` | Text. `inkMuted` is ink at 78% (72% until v3, see the glass notes below), `inkFaint` at 48% |
| `night` | `#0C1211` | Scrim and glass base |
| `sage` | `#5B8C7F` | Brand, live dot, default calendar dot, "arrived home" rows |
| `coral` | `#D4673E` | **Alert only** (`severity: high` on value, doors and laundry cards) |
| `amber` | `#D9A441` | Lagging data, door open (below the alert threshold) |
| `offline` | `#6E7471` | Offline, unknown and stale states, and the header's "connecting" dot |

**Activity accents** appear only while a card is active, and only on the chip, glyph, rim, glow and level bar: water `#4FB3E8`, heat and gas `#F2994A`, cool `#7CCBF2`, washer `#00AAFF`, dryer `#FF6900`, door `amber`.

**Colour rules**
- Only an **alert** colours the hero text (coral). Active cards keep ink text.
- `low` severity renders as plain normal.
- "Unknown" comes from state fields, never from severity.
- `parseColor()` accepts `#RRGGBB`, `#AARRGGBB` and the Roku's `0xRRGGBBAA` (the calendar `dot`), case-insensitive, and falls back to sage.

**Glass card**
1. The frosted photo crop, aligned to the card's position in the root (§8.7).
2. A `night` tint, tuned on the device for at least 4.5:1 contrast, or 7:1 for text of 32 sp or less. In v2 it was a fixed 55%. **Since v3** it follows the photo (below) and is 55% only when there is no photo.
3. A 1 dp rim of ink at 8%, plus a top-edge highlight at 12%.
4. Radius 20 dp. The glyph chip is 48 dp with a radius of 14 dp. Bars have a 3 dp radius.
5. No elevation shadows, because they show through translucent glass.

**Lighter glass (v3).** The frost already carries its slice of the scrim (§8.7), so the tint can be lighter than v2's.
- `glassTint(luma)` (`ui/backdrop/Scrim.kt`) ramps the tint from 0.32 on a dark photo to 0.48 on a bright one, with the scrim's brightness: clamp((luma − 0.15) / 0.45). With no photo (an empty NAS) the glass sits on the plain `night` gradient and keeps 0.55.
- The tint cross-fades with the photo (`fadedGlassTint`), read in draw, so it lightens and darkens the way the scrim does.
- `Modifier.glass` (`ui/cards/Glass.kt`) is the shared clip, frost, tint, rim and highlight. The cards and the detail panel (§8.10) both use it.
- The frost is unchanged: the soft copy is still blurred at 8 (`SOFT_BLUR`).
- **Muted ink (v3).** `inkMuted` went from ink × 0.72 to ink × 0.78. Measured on the wall, 16 sp muted text on the lighter glass fell to 6.5:1 on the brightest photo in rotation (forest, luma 0.43, tint 0.42). Raising the tint barely helps (0.50 still gives 6.95:1); the muted ink's alpha does. At 0.78 every measured card is at least 7.3:1. Ink text measures 11 to 15:1.

**Typeface: Barlow** (OFL). Two static files in `res/font/`: Medium and Semi Condensed SemiBold (about 105 KB each). It has road-signage lineage and true tabular figures (`fontFeatureSettings = "tnum"`), and its semi-condensed width keeps long sidecar strings large. No Light or Thin weights. Check on the device that the figures really are equal width. The fallback is Inter.

**Type scale.** The floor is **16 sp** everywhere.

| Role | Style |
|------|-------|
| Clock | Semi Condensed SemiBold 40 sp, tnum |
| Date | Medium 20 sp |
| Hero | Semi Condensed SemiBold 44 sp, tnum. `FitText` measures once and steps down to 30 sp to keep one line |
| Door state | Semi Condensed SemiBold 26 sp |
| Laundry status | Semi Condensed SemiBold 20 sp, `FitText` down to 16 sp |
| Sub, agenda title | Medium 20 sp, Medium 18 sp |
| Detail, agenda meta | Medium 16 sp |
| Card title | Medium 16 sp, sentence case |

**Icons.** 37 single-path glyphs from Material Design Icons (the set HA uses, Apache-2.0), stored as path data in `ui/glyph/GlyphData.kt` and drawn by `ui/glyph/Glyphs.kt`. Each is parsed once into a cached `ImageVector`, with no icon library. Weather uses HA's condition-to-`weather-*` map, plus `clear-night` → `weather-night` and `exceptional` → `alert-circle-outline`. An unknown glyph falls back to a per-kind default, and with no default the card renders without one.

**Motion tokens.** Hand-written from the M3 springs: `effectsSlow = spring(1f, 800f)` for colour and alpha (never bounce), `spatialStandard = spring(0.9f, 700f)`, and tweens of 350 to 1,600 ms where exact timing matters.

### 8.4 Cards

| Card | Chosen by | Body |
|------|-----------|------|
| `ValueCard` | `tile.type == "value"`, or **anything unknown** (the fallback) | Hero, sub, detail and an optional `tile.level` bar. Weather uses the same card with its condition glyph |
| `DoorsCard` | `kind == "doors"` | One row per door, up to three, as many whole rows as fit: a 1×1 tile shows 2. Open and unknown doors come before closed ones (a stable sort, so each group keeps the sidecar's order), so a short tile never hides an open door. Each row has a glyph, the label, and the state word (26 sp) over its age. Open is amber, coral once the sidecar marks the door `high` (open past `openAlertSec`, or open since before the logbook window), unknown is grey |
| `LaundryCard` | `kind == "laundry"` | One row per machine, stacked on the 1×1 tile and side by side when the card is 400 dp or wider. Each has a glyph in the machine colour, the label and status on one line, and a 4-segment LED bar (§4.4 frames) under them |
| `AgendaCard` | `tile.type == "agenda"` | Rows with a per-item glyph or `dot`, a title and "sub · time". Activity is newest-first. Calendar is 2 cells tall, keeps day headers and shows as many whole rows as fit. **It never takes alert or active styling**: rows get their accent from the glyph |

The `kind` is checked first, then `tile.type`, then the `ValueCard` fallback. This keeps the rule from §4.2 that unknown keys and unknown types keep working.

A value card's vertical budget is 171 dp: 14 pad, a 48 header row (title left, glyph chip right), a 44 hero, 24 sub, 20 detail and 12 pad. An optional 4 dp `level` bar sits on the bottom edge.

### 8.5 State to visuals

This applies to the value, doors and laundry cards.

| State | Visual |
|-------|--------|
| Normal, inactive | Glass, ink text, muted glyph. **No motion.** |
| `active` | Accent chip fill, glyph tint, rim, soft inner glow and level bar. Ink text |
| `severity: high` | Coral hero, a 2 dp coral rim, and the chip, glyph and glow in coral, whether or not the card is also active. Overrides active |
| `stale` | Content at 50%, no accent or alert colour, no pulses. A stale laundry card's LED bars hold their first frame |
| Connecting (cold start) | Until the first state fetch finishes, the header reads "connecting" beside a grey (`offline` token) dot, not "offline". After it, success or not, the dot reads live, lagging or offline |
| Offline (whole app) | The banner slides up. The **content layer** dims to 45% over 600 ms (`graphicsLayer` alpha) but the frost and tint stay opaque. Accent chrome is muted as for stale: the accent, glow, rim and alert coral fade out, and the laundry LED bars stop on their first frame. The banner and the dimming wait for the first state fetch to finish, so a cold start never flashes "No data" |
| Held value (v3, value cards only) | When a value module goes stale (the sidecar's `stale: true`, a missing tile, a blank hero or an `error` key), the card keeps its last good reading with the `stale` styling above (content 0.5, no accent, alert or pulse) and its detail line replaced by "as of h:mm a". For the first 5 minutes after the last good reading (`HOLD_GRACE_MS`) the held copy shows as live, ungreyed and not counted as degraded, so a source that drops for a minute or two (the water meter's WiFi, 2026-10-01: up 2 to 4 min, down 1.5 min and more, several times an hour) never flickers the card or the header. It holds until the module recovers and is dropped at local midnight, because a "today" total from yesterday would be wrong. Entering or leaving a hold never rings |
| Degraded (header, v3) | An amber dot (the wall's existing warning yellow, as for lagging) and the label "degraded · Water", "degraded · Water, Gas", or "degraded · 3" for three or more. It lists every stale value, doors or laundry card, titles in config order. Priority: connecting > offline > lagging > degraded > live |

**Held values (v3).** `ui/model/TileHold.kt` is a pure function over the projected cards. Doors, laundry and agenda cards are never held: a greyed "All closed" would mislead. A config reload drops held copies for ids that no longer exist. A failed poll keeps the hold memory. The sidecar now marks a module stale whenever its hero is a placeholder ("--…"), so a blank water reading can no longer arrive as live. The cause on the wall was the ESP water meter, which drops off the ESPHome API several times a day, and every water helper in HA went unavailable with it (§8.10).

Card content is drawn with `CompositingStrategy.ModulateAlpha`: the stale and offline alpha applies per draw call, not through an offscreen buffer per card. Card content barely overlaps itself, and the buffers HWUI kept cached cost about 9 to 11 MB PSS on the Fire.

### 8.6 Motion: calm by default, one-shot on change

**Rule:** nothing animates while the house is quiet. The only looping animation is the laundry LED bar in its animated modes, stepped at 10 fps or less, and only while its card has live data.

| Moment | Treatment |
|--------|-----------|
| Card becomes active | Chip, rim and glow animate in over 600 ms, and **one** ring pulse expands from the chip over 1.4 s, starting with them. No ring if the card went inactive less than 120 s before (the re-pulse cooldown below); the chip, rim and glow still animate |
| Card becomes inactive | Fades out over 1,200 ms. Stops are slower than starts |
| Severity becomes high | The hero, chip, glyph, glow and rim cross-fade to coral over 600 ms, and 2 ring pulses (1.4 s each) start with them |
| Hero value changes | Only when the hero's shape changes: what is left once digits, `.` and `,` are removed ("Back open" → "All closed", "Washer 1m left" → "Washer done"). It then slides 12 dp and fades over 350 ms (`AnimatedContent`). A digit-only change ("1.1 kW" → "1.2 kW") swaps in place with no transition, so live readings that wobble between polls never move the wall |
| New activity row | Enters at the top with an accent highlight (20%) that fades over 4 s |
| Laundry LEDs | §4.4: breathing (stepped at 100 ms), bounce at 120 ms or 450 ms per step, violet sweep for a stale machine (150 ms per step). A pure `(mode, leds, t)` function. While the app is offline or the whole laundry card is stale, every bar holds its t = 0 frame (`ledAnimates`). A single machine with no data still sweeps on a live card, because there "no data" is news |
| Photo rotation | The sharp and frosted layers cross-fade together over 1.6 s, every `background.intervalMs` (3 min live; never under 1 min). No Ken Burns and no zoom. Held while the peek shows (0.4.0) |
| Night (`nightDim`) | Window brightness goes to the configured level, and the photos keep rotating (until v3 they faded out to plain `night` and rotation paused; v3 keeps them so the header peek works at any hour, 2026-10-01). Cards stay, so it is still glanceable. Schedule-based, because the tablet has no confirmed light sensor |
| Image retention | The whole UI layer (header and cards, not the backdrop) steps around a ±2 dp ring of 8 positions every 10 min through `Modifier.offset {}` (so `onPlaced` and the frost follow), with no animation |
| Detail panel (v3) | Opens with a 250 ms clip reveal from the tapped card and closes the same way. One-shot, started by a tap (§8.10) |
| Photo peek (v3) | The UI layer and the scrim fade out over 400 ms, and back in over 400 ms. One-shot, started by a tap (§8.10) |
| Peek step (0.4.0) | A photo stepped to with ‹ or › cross-fades in 300 ms, not 1.6 s. One-shot, started by a tap (§8.10) |

**Pulse detection** is a pure function (`ui/model/Pulses.kt`), run by the ViewModel's poll loop through `PollTracker`.
- `pulses(prev, next)` compares only **two consecutive successful polls**. `prev` is `null` after a failure or a cold start, which re-baselines.
- It skips stale↔fresh flips, modules that are new after a config reload, and agenda cards.
- **Re-pulse cooldown.** `PollTracker` holds back an ACTIVE ring for a card that went from active to inactive less than 120 s earlier (`REPULSE_COOLDOWN_MS`, timed by the poll's wall clock). ALERT rings are never held back. Only the ring is throttled: the card's `active`, and so its accent fade, follows every poll. A water meter flapping between 0.0 and 0.4 L/min therefore rings once at the start of the run, then again only after it has stayed off for 120 s.
- The UI's `rememberPulse(seq)` sets its baseline at first composition, so recreating the activity doesn't replay pulses.

### 8.7 Backdrop and frosted glass

API 30 has no `RenderEffect`, so `Modifier.blur` and Haze can't blur here. The frost is faked from a pre-blurred copy of the photo, with no new dependencies.

**Loader** (`ui/backdrop/BackdropLoader.kt`, in `viewModelScope`)
- `combine(bgSettings, night)` feeds `collectLatest`.
- A `ShuffleBag` covers every image once per round with no immediate repeat. The list is refreshed every 10 min.
- **Decode before swap.** Sharp is `1024×600 fit=cover`, decoded with `BitmapFactory` and `inPreferredConfig = HARDWARE` (falling back to ARGB_8888, never RGB_565). Soft is `256×150 fit=cover blur=8` as a software bitmap. The loader then emits `Photo(sharp, soft, luma)`.
- `meanLuma` takes the larger of the whole frame and the header band.
- **Failures:** a bad file keeps the current photo, and an empty NAS gives the gradient. Backoff is 1 to 5 min.
- No `recycle()`. Old pairs become unreachable and the GC frees their native memory. Add a delayed recycle only if the soak shows growth.

**Backdrop** (`BackdropState.kt`, `Backdrop.kt`)
- A `@Stable` holder with `front`, `back` and a single `fade: Animatable`, provided through `staticCompositionLocalOf`.
- One full-screen `drawWithCache` draws the fallback radial gradient, then `back`, then `front` at alpha p, then the scrim.
- The scrim is a vertical `night` gradient whose alpha comes from a pure `scrimAlpha(luma)`: brighter photos get more. It runs from 0.40 to 0.75 at the top (behind the header) and from 0.25 to a ceiling of 0.40 at the bottom.
- All animated reads happen in the **draw phase**, so cards never recompose during a cross-fade.

**Frost** (`Modifier.frost(bd, origin, radius)`)
- `onPlaced { positionInRoot }` feeds `drawWithCache`.
- Clipped to the round rect, it draws the matching `srcOffset`/`srcSize` region of each soft bitmap (`FilterQuality.Low`), scaled to the card.
- It then draws its own slice of the backdrop scrim over that, so the glass is as dark as the backdrop around it. Measured on the worst photo, this took ink-on-glass contrast from 3.9:1 to 7.8:1. The card's `night` tint goes on top (§8.3: 0.32 to 0.48 with a photo since v3, 0.55 in v2 and with no photo).
- The source rect is in quarter-scale pixels, an error that is invisible under the blur.

### 8.8 Sidecar changes for v2

The work is additive and ships in three small deploys, each followed by a Roku check. `/api/config` without `?layout=` must never contain `layouts`, because the Roku caches that response in its registry (about 16 KB cap; today's config is 6.5 KB).

| Deploy | Contents |
|--------|----------|
| A | Layouts (§3.1) with explicit `?layout=` on every route, and the new tile keys below |
| B | `doors` and `laundry` (§3.2, §3.3, with the fixes below) |
| C | Backgrounds: `/api/backgrounds` and `/api/background/<name>`, with `fit=cover` and `blur` |

**New tile keys** (every module, additive; the Roku reads keys by name, so it is unaffected)

| Key | Meaning |
|-----|---------|
| `tile.glyph` | An MDI name chosen from state, for example `door-open`, `water`, `fire`, `washing-machine`, `weather-*` |
| `tile.active` | Always a real bool. True for water flowing, gas burning (the *displayed* rate, rounded to 0.1, is above 0.0), HVAC heating or cooling (fan-only is not active; its `sub` reads "Fan"), a door open, laundry running, overtime or done |
| `tile.level` | 0 to 100 for energy, water and gas. Pruned elsewhere |
| `items[].glyph` | Timeline rows: `door-open`, `door-closed`, `motion-sensor`, `home-account` and similar |

`tile.icon` stays as it is, because it is the Roku's cache-bust token. There is no "active" field today: `severity` means "needs attention", so water is `high` whenever it flows. The water descriptor therefore gets a `runningSeverity` option, which defaults to `"high"` (the Roku is unchanged) and which the tablet layout sets to `"normal"`.

**Doors "since"** (refines §3.2, which only said "newest logbook row")
- If the newest logbook row's state differs from the current state, use `last_changed`. This is a fresh change that the 30 s logbook cache hasn't seen yet.
- Otherwise use the logbook row, which survives HA restarts.
- Skip transitions out of `unavailable` (Zigbee2MQTT reconnect rows).
- If the logbook has no row in the window, fall back to `last_changed` with `since_exact: false`, as in §3.2.
- `lookbackHours` is 12, so the logbook cache entry (keyed `entity:hours`) is actually shared with the timeline.

**Backgrounds**
- `cover` centre-crops to the exact w×h. The Roku keeps `contain`. `blur` is a Gaussian radius clamped to 0 to 40, applied after resizing.
- Decoding uses `Image.draft` so the 12 MP drone files decode quickly (about 0.13 s each), and `ImageOps.exif_transpose` fixes orientation.
- The directory listing is cached against the directory's `st_mtime`. An empty or unmounted directory returns `images: []`, not an error.
- The NAS folder was seeded on 2026-09-30 with 42 images: one or two per day of Drone footage, re-encoded as 2560 px JPEGs (about 48 MB). The user prunes it later.

### 8.9 Budgets and checks

- **Memory:** PSS at most 95 MB (70.8 MB at v0.1.0) and flat over 24 h. Bitmaps peak at about 5 MB during a cross-fade. The only additions are about 210 KB of fonts and the glyph strings. v3 adds no libraries: the charts are `drawWithCache` paths.
- **Quiet frames:** about 0 frames per second while the house is quiet, measured with `gfxinfo`. A detail panel left open on a quiet house meets the same budget (3 frames in 30 s).
- **Release build for the wall:** R8 (`isMinifyEnabled`), signed with the debug key. After installing, trigger the profile installer with `am broadcast -a androidx.profileinstaller.action.INSTALL_PROFILE -n io.haku.tablet/androidx.profileinstaller.ProfileInstallReceiver`, then run `cmd package compile -f -m speed-profile io.haku.tablet`.
- **Verification:** the sidecar tests, the tablet unit tests and the on-device checks (screenshots only, no sleep or wake) are listed in the v2 plan. The v2 ship step ends with a 24 h soak that checks PSS stays flat. The v3 soak, with panels, is still to do (§7).
- **Measured on 2026-10-01, v2 (0.2.0)** (release build with the speed-profile compile, live data; the full table is in the README):
  - PSS is 54.0 to 61.1 MB over 18 samples in 70 minutes (debug: 91.2 MB the same morning).
  - With the house quiet, two 60 s windows rendered 8 and 9 frames (about 0.15 fps), within the quiet-frames budget above.
  - A photo cross-fade draws 94 to 99 frames over its 1.6 s. That is a frame on every vsync, but each takes two to three vsync periods to complete, so `gfxinfo` counts all of them janky (p90 30 to 46 ms).
  - The APK is 1.96 MB (debug: 24.7 MB).
  - A water meter flapping between 0.0 and 0.4 L/min turns the Water card on and off two or three times a minute, at 254 to 808 frames per minute. Since 0.2.0 the re-pulse cooldown (§8.6) rings only the first start of such a run, but the accent still fades on every flip. Debouncing `active` in the sidecar would quiet it fully (§7).
- **Measured on 2026-10-01, v3 (0.3.0)** (release build on the wall; the full table is in the README):
  - PSS is 51.0 MB at rest, 63.7 MB after 20 panel opens and 62.0 MB after 10 peeks. After 40 more opens it read 72.2 MB, then 68.4 MB, and it settled at 64.8 MB after a minute idle (Java heap 11.7 MB, native 21.3 MB, graphics 14.4 MB). That is within the 95 MB budget and not climbing. A 24 h soak is still to do.
  - A panel left open while the house is quiet drew 3 frames in 30 s.
  - Open then close drew 33 frames: p50 12 ms, p90 21 ms, p99 32 ms.
  - Live `/api/detail/*` calls took under 90 ms cold and about 2 ms warm.
- **Measured on 2026-10-05, 0.4.0** (release build on the wall, peek stepping):
  - PSS is 57.1 MB at rest, 77.9 MB just after 30 steps (15 forward, 15 back), and 57.7 MB once the peek had ended and the app sat idle for 45 s. That is within the 95 MB budget and not climbing.
  - A step's photo (both variants fetched and decoded) lands about 0.2 s after the tap. Three taps sent at once showed as `d=1` then a combined `d=2`, with one load for the pair.
  - A rotation that fell due mid-peek was held and came one full interval later. A step 20 s into a peek kept it up at 40 s, and it ended by 53 s.

### 8.10 Touch: detail panels and photo peek (v3, 2026-10-01)

v3 adds touch. It supersedes the glance-only lines in §1 and §8.1. The wall still has no controls that change house state: a tap opens a panel, closes it, peeks at the photo, or (0.4.0) steps the peek's photo. The JSON shapes (`/api/detail`, rate tiles), the tone keys and the timings are in the [v3 contract](../superpowers/specs/2026-10-01-tablet-v3-details-contract.md); if this section and the contract disagree on a value, the contract wins. The build steps are in the [v3 plan](../superpowers/plans/2026-10-01-tablet-v3-details.md).

**Rule: an overlay never hides an alert, and always closes by itself.** The panel closes after 90 s and the peek ends after 30 s, and any ALERT pulse closes both. The wall always goes back to the glance.

#### Detail panels

A tap on a card opens a full-width glass panel over the card grid. The panel covers the grid area (1000×532 dp, below the 56 dp header and inside the 12 dp margins), so the header stays live. Every card is tappable, including cards whose module has no sidecar detail.

| Part | Behaviour |
|------|-----------|
| Reveal | The panel grows from the tapped card's rect with a draw-phase clip reveal: 250 ms, `FastOutSlowIn`, the same on close. The panel is placed once, at its final rect, and only the clip animates, so nothing re-lays-out per frame and the frost (`positionInRoot`) stays aligned. |
| Grid fade | The grid fades out underneath: alpha = 1 − reveal, through `graphicsLayer` with `CompositingStrategy.ModulateAlpha` (no offscreen buffer). With no photo (backgrounds off, an empty NAS) there is no frost, which would let the cards show through the panel; the fade means nothing does. |
| Content fade | The panel's content fades in over the last 60% of the reveal. |
| Glass | `Modifier.glass` (§8.3), the same as a card. The panel sits inside the burn-in-shifted UI layer (§8.6), so it moves with the cards and the frost follows. |
| Panel header | The module glyph and title, and "Tap to close". When the card is holding a stale value it also says "Live data unavailable · as of h:mm a" in amber. The live card (5 s polls) only fills the body: its hero, sub and detail show big while the detail loads, or for good when the module has no detail. |
| Closes on | A tap anywhere on the panel, a header tap, Back (`BackHandler`), 90 s after opening, or any ALERT pulse. Taps are ignored while the reveal animates. There is no scrolling. |

**Why a clip reveal.** Animating the panel's size would re-lay-out its whole content every frame, and would move it away from its frost source. A clip changes only what is drawn.

**What each panel shows.**

| Panel | Body |
|-------|------|
| Water, Energy, Gas | Stats (Now, Today with its cost, This month with its estimated cost), an hourly line chart of the last 7 days with a soft fill (litres, kWh, m³), and a 7-day strip of daily use and cost, with today last and labelled "Today". Gas cost lines appear once a gas price is set (§7) |
| Thermostat | Stats (Indoor, Outdoor, Humidity, Mode, Set to) and a 7-day hourly chart of indoor (heat) against outdoor (cool) temperature, with a legend |
| Weather | Two columns ([weather panel design](../superpowers/specs/2026-10-03-weather-panel-design.md)). Left: the hero (glyph, big temperature, condition, high/low, "Updated" time), facts (feels-like, humidity, wind, pressure, sunset, sunrise) and the next 3 days, a line each. Right: the next 8 hours (glyph, temperature, rain chance) over a 24 h observed + 24 h forecast temperature chart with a "Now" marker. The attribution sits under the chart |
| Laundry | A washer list and a dryer list (each: status, last started, last finished, last run length), then "Last 7 days" runs |
| Doors | "Now" (each door's state and since), then "Today" (each open, with its duration) |
| Activity | The `items` from `/api/state`, in 4 columns. No fetch |
| Calendar | The `items` from `/api/state`, in at least 2 wide columns so titles aren't truncated, balanced, and a day header is never left alone at the foot of a column. No fetch |

**Data.** Water, energy, gas, thermostat, weather, laundry and doors panels fetch `GET /api/detail/<id>?layout=tablet`. All history comes from Home Assistant, and the sidecar stores nothing:
- series: long-term statistics over the websocket `recorder/statistics_during_period` (kept forever; the recorder keeps only 14 days);
- laundry runs and door opens: REST history;
- today and month values: live states.

The body renders the sidecar's typed blocks (`stats`, `chart`, `days`, `forecast`, `rows`, and the weather panel's `now` and `hourly`) verbatim, in one column or, when a block says `col: 1`, in two (3:5), and skips unknown or malformed ones. The chart is a line, with an optional soft fill, drawn from `drawWithCache` paths. It does not animate, and it never joins buckets across a gap. The code is in `ui/detail/` (`DetailLayer.kt`, `DetailState.kt`, `Blocks.kt`, `WeatherBlocks.kt`, `ChartBlock.kt`, `ChartGeometry.kt`, `LocalDetail.kt`, `Tones.kt`), `data/Detail.kt` and `data/DetailJson.kt`, with `DashboardViewModel.openDetail`, `closeDetail` and `detail`.

**Refresh and failure.** While a panel is open, the detail is refetched every 60 s. `SidecarClient` allows 15 s to read and 20 s for the whole call, because a cold history query can take seconds.

| Situation | Panel shows |
|-----------|-------------|
| Loading | The live tile, big |
| 404 (the module has no detail) | The live tile, big, for good. It is not retried |
| Any other failure, nothing loaded yet | The tile, with "Couldn't load the details. Trying again in a minute." It keeps retrying every 60 s |
| A refresh fails after a good load | The detail already loaded stays |

#### Photo peek

A tap on the header (the clock and date bar) fades the UI layer and the backdrop scrim out over 400 ms, so the photo shows bare. The fade reads `BackdropState.veil` only in draw, and the UI layer uses `ModulateAlpha`, so there is no offscreen buffer. A full-screen tap catcher sits on top while the UI is veiled.

| Part | Behaviour |
|------|-----------|
| Ends on | Any tap outside the ‹ › buttons, Back, 30 s after the peek started or was last stepped, the photo going away, or any ALERT pulse. The UI and the scrim fade back over 400 ms |
| No photo | With backgrounds off or an empty NAS a header tap does nothing. Photos keep rotating through the night window, so the peek works at any hour |
| Panel open | A header tap closes the panel instead of peeking. The rule is the pure `headerTapAction(detailOpen, peeking, hasPhoto)` |
| Opening a panel | Ends any peek |

**Browsing the photos (0.4.0, 2026-10-05).** While the peek shows, a ‹ button sits on the left edge and a › on the right, centred vertically. Each is a 56 dp smoked-glass disc (`night` at 45 %) with an `ink` MDI chevron, in a 72 dp touch target. They fade with the peek (`veil`, read in draw).

| Part | Behaviour |
|------|-----------|
| The reel | `BackdropLoader` keeps the names of the last 20 photos shown, with a cursor on the current one. ‹ moves back along it, › moves forward and, past its end, deals new names from the shuffle bag, so the wall's random order stays as it is. Only names are kept: a step back fetches its photo again |
| Oldest end | ‹ at the oldest photo kept does nothing |
| Rapid taps | Taps that queue up while a photo loads are summed, and only the photo they land on is fetched. The photos skipped over stay on the reel |
| A failed load | Keeps the current photo and drops the failed name from the reel |
| Rotation | Held while the peek shows: the timer re-arms instead of advancing. A step restarts the full interval, so a chosen photo stays up for one interval after the peek. When rotation next advances it drops whatever is ahead of the cursor (browser-history semantics) |
| Timeout | Each step restarts the peek's 30 s. An ALERT still ends the peek at once, buttons and all |

#### Sidecar and Home Assistant side

- **Rate tiles.** The tablet layout's water, energy and gas refs set `"tileStyle": "rate"`: hero = the rate now (`4.2 L/min`, `0.9 kW`, `0.8 m³/h`), sub = today's total (`412 L today`, `32 kWh today`, `3.1 m³ today`) and detail = today's cost (`$1.24 today`). The detail line is left out when the cost entity is missing or unavailable, and gas cost is unavailable until a price is set. The flag is opt-in per layout, and the Roku's output is byte-identical (a golden test guards it).
- **Truthful `stale`.** The sidecar now marks a value module stale whenever its hero is a placeholder ("--…"), which is what lets the tablet hold the last good value (§8.5).
- **HA packages (mserver).**
  - `packages/haku_water.yaml`: both water utility meters get `always_available: true`, so a drop-out of the ESP water meter no longer makes every water helper unavailable; and `sensor.water_cost_today`.
  - `packages/water_cost.yaml`: `water_monthly` is also `always_available`.
  - `packages/gas_cost.yaml` (new): the gas daily and monthly utility meters, `sensor.gas_marginal_cost_per_m3` (the bill figures are placeholders, 0, until filled in), `sensor.gas_cost_today` and `sensor.gas_monthly_cost`.
  - The repo copies are `~/code/homewall/sidecar/ha-water-helpers.yaml` and `ha-gas-cost.yaml`.
