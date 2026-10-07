# HAku sidecar (`haku-sidecar`)

The data + rendering half of HAku's server side. Runs on **nserver (192.0.2.20)**
alongside the existing stream stack (`go2rtc` + `haku-hls@` + `haku-discovery`), and
gives the Roku channel everything that isn't a camera stream:

- **`GET /api/config`** — the portable module descriptors from `dashboard.json`. This is
  the one place a HAku install is bound to its Home Assistant entities; edit it to add,
  remove, or re-map modules with no code change.
- **`GET /api/state`** — a single composed values snapshot for every native tile
  (weather temp/condition, camera roster/motion, …), `null`-pruned so the Roku's JSON
  parser never sees a `null`.
- **`GET /api/module/<id>`** — one module's values (for drill-downs).
- **`GET /api/detail/<id>`** — one module's detail panel for the kitchen tablet, as typed
  blocks (stats, an hourly 7-day chart, a 7-day strip, a forecast, rows). Read from HA
  history and long-term statistics on demand; see [Detail panels](#detail-panels-tablet).
- **`GET /api/card/<name>.png?w=&h=&v=`** — a server-rendered PNG card (matplotlib Agg +
  Pillow). Roku has no chart primitives and no webview, so charts are drawn here and
  shown as Posters. Cards render as dark, translucent "glass" panels with light text on
  a **transparent** PNG so they composite over the rotating photo background. `v=` is a
  Roku-side cache-buster; the render cache ignores it. Cards (each owned by the first
  module of its kind in the requested layout, rendered in the configured timezone):
  - `weather_forecast`: the default view's weather drill, a 6-day high/low band on a
    glass panel.
  - `weather_chart`: the wall Rokus' Forecast card (`?layout=roku&w=554&h=208`), the
    weather detail panel's 48 h outdoor temperature chart (24 h observed in ink, 24 h
    forecast in cool blue, joined at "Now") in Barlow on a fully transparent background,
    since the channel draws the glass itself. It makes the same HA reads as
    `/api/detail/weather`, so the two share HA's statistics and forecast caches, and it
    re-renders only when the chart's data changes.
- **`GET /api/icon/<module_id>.png?w=&h=&v=`** — a small (default 96×96) home-tile accent
  icon (Pillow only — no matplotlib): a Font Awesome glyph for weather's condition, and
  hand-drawn gauge shapes for energy's/water's live fill level. 404s for a module with no
  icon (calendar/timeline/cameras) or with no data yet. Unlike chart cards, `v=` here is a
  **bucketed** value computed by the module (condition string, or a 5%-stepped fill
  percentage) — it only changes when the icon would actually look different, so a Roku
  polling every 10-30s doesn't re-fetch an unchanged icon every time.
- **`GET /api/backgrounds`** — the rotating background roster: `{"images":[{"name","url"}]}`,
  sorted deterministically (= rotation order). Each `url` is absolute (same base the
  channel gets in the `sidecar` block) so the Roku fetches it verbatim.
- **`GET /api/background/<name>?w=&h=&fit=&blur=`** — one background image, opened with
  Pillow and rendered to exactly `w`×`h` (each clamped to 64–1920, default 1920×1080),
  served as JPEG with a 1-hour `Cache-Control`. `<name>` must be a bare basename in the
  backgrounds directory (path traversal → 404). With no `fit` or `blur` this is the
  Roku's letterboxed image; see [Backgrounds](#backgrounds).
- **`GET /api/health`** — liveness + HA connection status (`ha.url`, `ha.token_present` —
  never the token value).
- **`?layout=<name>`** on config/state/module/detail/card/icon serves another display's own module
  set from the `layouts` map (see [Layouts](#layouts)); without it the Roku view is unchanged.
  On backgrounds/background it selects that layout's own image directory.

A single background poller (`ha.HAClient`) refreshes HA state on an interval (default
10 s), so N Rokos polling the sidecar cost Home Assistant **one** `/api/states` call per
interval regardless of fleet size. Forecast data (which HA no longer exposes as a
`forecast` attribute) is fetched on demand via the `weather.get_forecasts` service and
cached per entity and forecast type. The detail panels' history (REST
`/api/history/period`) and long-term statistics (the websocket command
`recorder/statistics_during_period`, which needs `websocket-client`) are fetched on demand
too, and cached about 10 minutes with keep-last-good.

## Config: `dashboard.json`

Copy `dashboard.json.example` to `/etc/haku/dashboard.json` and map each module to your
HA entities. A module descriptor:

```json
{
  "id": "weather", "kind": "weather", "title": "Weather",
  "tile": { "type": "value", "col": 0, "row": 0, "w": 1, "h": 1 },
  "drill": { "type": "chart", "card": "/api/card/weather_forecast.png" },
  "feedKey": "weather", "refreshMs": 30000,
  "entities": { "forecast": "weather.edmonton_forecast", "indoor": "weather.my_ecobee" }
}
```

`tile.type` ∈ `value | chart | image | camera | agenda` selects the Roku renderer;
`entities` is the HA binding. Unknown kinds/types render a neutral tile (forward-compat).

### Tile keys

Every value module's `/api/state` entry carries a `tile` object, and the sidecar owns all
of its formatting. The Roku reads `hero`, `sub`, `detail`, `severity` and `icon`; the
kitchen tablet also reads the three keys below. They are additive, so the Roku ignores them.

| key | type | meaning |
|---|---|---|
| `glyph` | string | A [Material Design Icons](https://pictogrammers.com/library/mdi/) name, chosen from live state. |
| `active` | bool | Whether the thing is doing something right now. Always a real bool, so `false` is sent, never dropped. |
| `level` | int 0-100 | A fill level (energy, water and gas only), on the same `icons.fill_bucket_pct` scale as `icon`. Absent when the reading is unavailable. |

| module | `glyph` | `active` | `level` |
|---|---|---|---|
| weather | by HA condition (`haku_sidecar/glyphs.py`); `weather-partly-cloudy` for an unknown or stale one | `false` | none |
| energy | `flash` | `false` | `power_kw` against 5 kW |
| water | `water` while running, else `water-outline` | running (flow > 0) | `flow` against `maxFlowLpm` (default 10) |
| gas | `fire` while running, else `meter-gas` | running (displayed flow, rounded to 0.1, is above 0) | `flow` against `maxFlowM3h` (default 2) |
| climate | `hvac_action` heating `fire`, cooling `snowflake`, fan `fan`, else `thermostat` | `hvac_action` is heating or cooling (fan alone is not active) | none |
| calendar | `calendar` | `false` | none |
| timeline | `history` | `false` | none |
| doors | `door-open` if any door is open, else `door-closed` | any door open | none |
| laundry | `washing-machine` | any machine running, in overtime or done | none |

`climate` still has no `icon`.

**`stale`.** A value module (weather, energy, water, gas, climate) reports `stale: true`
whenever its tile hero is a placeholder (starts with `--`, such as `-- L` or `--°`), so the
tablet can grey the card and hold its last good value. The Roku never reads `stale`.

**`tileStyle: "rate"`** (water, energy and gas; the tablet layout sets it) words the tile as
"now · today · cost". Without it the tile is unchanged.

| module | hero | sub | detail |
|---|---|---|---|
| water | `4.2 L/min` (`0 L/min` at an exact 0), from `flow` | `412 L today`, from `daily` | `$1.24 today`, from `cost_today` |
| energy | `0.9 kW`, from `power` | `32 kWh today`, from `daily_energy` | `$6.91 today`, from `cost` (else `cost_fallback`) |
| gas | `0.8 m³/h` (`0 m³/h` when not running), from `flow` | `3.1 m³ today`, from `daily` | `$1.05 today`, from `cost_today` |

`sub` and `detail` are left out (not sent as `""`) when their entity is missing or
unavailable; HA makes a cost unavailable when its price is unknown or 0. `stale` is true
exactly when the hero's source (flow or power) is missing. `glyph`, `active`, `level` and
`severity` follow the rules above either way.

**Water `runningSeverity`.** The descriptor key `runningSeverity` (`low`, `normal` or `high`;
default `high`) is the `severity` reported while water is running. Idle is always `normal`.
The default is the Roku's behaviour. The tablet layout sets `"normal"`, so a running tap
doesn't read as an alert.

**Timeline item `glyph`.** An event item in `/api/state` may carry an MDI `glyph`, derived from
the same device class and state as the item's `sub`. An event with no mapping has no `glyph` key.

| event | `glyph` |
|---|---|
| door, garage door, window, opening | `door-open` when on, else `door-closed` |
| motion-type sensor (motion, occupancy, presence, ...) | `motion-sensor` when on or detected, else `motion-sensor-off` |
| lock | `lock-open-variant` when unlocked, else `lock` |
| person | `home-account` at home, `account-arrow-right` in any other state (away or a named zone) |

### Layouts

The top-level `modules` list is the default view (what Roku channels before 0.11 read).
An optional top-level `layouts` map gives each display its own module set. A client
selects one by adding `?layout=<name>` to `/api/config`, `/api/state`,
`/api/module/<id>`, `/api/card/<name>.png` or `/api/icon/<id>.png`. The kitchen tablet
uses `?layout=tablet` and the wall Rokus (0.11+) use `?layout=roku`; see the `layouts`
blocks in `dashboard.json.example`.

```json
"layouts": {
  "tablet": {
    "grid": { "cols": 4, "rows": 3 },
    "nightDim": { "start": "22:00", "end": "06:30", "brightness": 0.15 },
    "background": { "intervalMs": 180000 },
    "modules": [
      { "id": "doors", "kind": "doors", "feedKey": "doors",
        "tile": { "type": "value", "col": 0, "row": 0, "w": 1, "h": 1 },
        "entities": { "doors": [
          { "id": "front", "entity": "binary_sensor.front_doorcontact_contact", "label": "Front" } ] } },
      { "ref": "water", "runningSeverity": "normal",
        "tile": { "type": "value", "col": 0, "row": 1, "w": 1, "h": 1 } }
    ]
  }
}
```

- **`ref` entries.** `{"ref": "<id>", …}` is the top-level module with that id, with the
  entry's other keys laid over it. The merge is shallow: a `tile` or `entities` given
  here replaces the whole object.
- **Qualified `ref`s.** `{"ref": "<layout>:<id>", …}` is the entry with that id in
  another layout, resolved first, again with this entry's keys laid over it. The Roku
  layout is built this way from `tablet:` refs. Only one hop: the other layout's own
  entries can't be qualified refs.
- **Layout-only modules.** An entry without `ref` is a module that only this layout shows.
- **What `?layout=` returns.** The response carries `version`, `site` and `timezone`
  from the top level, plus:
  - the layout's `grid`, falling back to the top-level grid;
  - its `nightDim`;
  - `background`, with the layout's keys laid over the top-level ones (its `dir` is the
    server-side image directory, see [Backgrounds](#backgrounds), and is never sent);
  - the resolved `modules`.

  `/api/state?layout=` composes only those modules, keyed by `feedKey`.
- **Errors.**
  - Invalid modules are dropped and logged.
  - A layout `modules` that isn't a list is logged and served as no modules (`[]`).
  - A `background.dir` that isn't a non-empty string is logged and ignored, so
    `HAKU_BG_DIR` applies.
  - An unknown layout returns `404 {"error": "unknown layout", "layout": …}`.
  - A `ref` that names no module (or a qualified ref naming no layout or entry, or one
    that chains) returns `404 {"error": "unknown ref", "ref": …}` for that layout only.
- **Without `?layout=`, nothing changes.** `/api/config` serves the file minus
  `layouts`, so the Roku's ~16 KB config cache never sees it. No discovery schema bump
  is needed.

### The Roku layout (`layouts.roku`)

The wall Rokus (0.12+) show a read-only 6×4 grid at 1920×1080. The grid carries the
Roku's pixel geometry (`cellW` 289, `cellH` 220, `originX` 52, `originY` 116, `gap` 16).

```
      c0         c1       c2   c3        c4   c5
r0   [ Doors (2×1)  ]    [ Calendar ]   [ Front    ]
r1   Laundry    Water    [          ]   [ (live)   ]
r2   Energy     Gas      [ Activity ]   [ Forecast ]
r3   Weather    Thermo   [          ]   [ 3-day +  ]
                                        [ 48 h     ]
```

- **The tablet's modules come through `tablet:` refs, each with its own `tile`.** The
  merge is shallow, so the Roku's tiles don't follow tablet moves; everything else
  (kind, feedKey, entities) is the tablet's.
- **Camera:** `{"ref": "cameras", "title": "Front", "tile": {"type": "camera", …, "cam": "front"}}`,
  the live front camera in the 2×2 square.
- **Forecast:** a second weather entry (`"ref": "tablet:weather", "id": "forecast",
  "feedKey": "forecast"`) with `"outlook": true`, which adds `outlook` to its values: the
  next 3 days after today, as `[{"label": "Fri", "glyph", "cond"?, "hi"?, "lo"?, "sub"?}]`
  (the weather detail panel's compact forecast, from the daily forecast the tile already
  reads). Without `outlook` the weather values are unchanged. Its `tile.type` is
  `forecast`, and `tile.card` (`/api/card/weather_chart.png`) is the chart the 2×2 card
  shows under the 3-day strip. It lives in `tile` because the channel's slimmed registry
  cache keeps `tile` but drops `drill`.

### Doors and laundry (tablet layout)

Two kinds exist only for the kitchen tablet's layout. Neither has an `icon` PNG or a card.

**`doors`.** Descriptor: `entities.doors[]` of `{id, entity, label}` (binary_sensor
contacts), `openAlertSec` (default 300) and `lookbackHours` (default 12, the timeline's,
so both share the `entity:hours` logbook cache entry). Per door it reports `state`
(`open`, `closed` or `unknown`), `since` (epoch), `since_exact`, `age` (the timeline's
`now`/`6m`/`2h`/`3d`), `severity` and `glyph` (`door-open`, `door-closed` or `door`),
plus `open_count` and `stale` (every door unknown).

- **"since" comes from the logbook**, because HA re-stamps `last_changed` on restart. It
  is the time of the newest real open/close row. Two kinds of row don't count:
  - rows out of `unavailable` or `unknown` (Zigbee2MQTT reconnects);
  - a row repeating the previous row's state. That is how a restart shows up, since HA's
    logbook drops the restart's own row.
- If that row's state isn't the current state, the change is newer than the 30 s logbook
  cache, so `last_changed` is used instead.
- With no usable row in the window, `since` is `last_changed`. It is exact if
  `last_changed` is at most 60 s old. Otherwise `since_exact` is `false` and `age` reads
  `> 12h` (the configured `lookbackHours`).
- Known limitation: if a restart's row is the only row in the window, "since" reads as
  the restart time.
- `severity` is `high` for a door open longer than `openAlertSec`, or open with an inexact
  "since". It is `low` for unknown, otherwise `normal`.
- Tile hero: `All closed`, `Back open`, `2 open`, `Back unknown`, or `No data` when stale.

**`laundry`.** Descriptor: `machines[]` of `{id, label, color, glyph?, entities?}`. It
mirrors HA's laundry package and never re-derives it. Entity ids follow from the machine
id, and `entities` overrides any of them by key:

| key | default entity | use |
|---|---|---|
| `mode` | `sensor.laundry_<id>_mode` | `idle`, `running`, `overtime`, `done` or `done_calm` |
| `leds` | `sensor.laundry_<id>_leds` | 0-4 countdown pixels, passed through |
| `started` | `input_datetime.laundry_<id>_started` | `timestamp` attribute; below 1e9 means never set |
| `finished` | `input_datetime.laundry_<id>_finished` | (same) |
| `expected_minutes` | `input_number.laundry_<id>_expected_minutes` | expected cycle length |
| `power` | none | optional watts, e.g. `sensor.emporia_circuit_7_power` |

- Per machine: `mode`, `leds`, `power_w`, `remaining_min` (running) or `over_min`
  (overtime) with `started`/`elapsed_min`/`expected_min`, `finished`/`finished_hm` once
  done, and `glyph` (config, else `washing-machine`, or `tumble-dryer` for id `dryer`).
- `status` by mode: `idle`, `34m left`, `running 5m long`, `done`, `done 9:52 AM`. It
  reads `running` or `running long` when the start time was never set.
- A mode sensor that is unavailable, missing or not one of the five modes makes the
  machine `stale` with status `no data`, and its `mode` reads `idle`. The module is
  `stale` when every machine is.
- Tile hero by priority: done, overtime, running, done_calm, idle (`Washer 34m left`;
  `Laundry idle` when every machine is idle). The other machines go in `sub`.
  `severity` is `high` only for `done`.

### Detail panels (tablet)

`GET /api/detail/<id>?layout=tablet` answers for the kinds with a `detail()`: `water`,
`energy`, `gas`, `climate`, `weather`, `laundry` and `doors`. The JSON shape, block types,
caps and tones are the shared contract in the tablet repo,
`docs/superpowers/specs/2026-10-01-tablet-v3-details-contract.md`
(§1); this sidecar is its source of truth for the data.

```json
{"v": 1, "id": "water", "title": "Water", "ts": 1790905930, "note": "optional",
 "blocks": [{"type": "stats", "items": [{"label": "Now", "value": "4.2 L/min"}]},
            {"type": "chart", "start": 1790300000, "step": 3600, "count": 168,
             "series": [{"label": "Water", "tone": "water", "fill": true,
                         "runs": [{"i": 0, "v": [1.0, 0.0, 12.5]}]}],
             "x": {"ticks": [{"i": 7, "label": "Thu"}]},
             "y": {"min": 0, "max": 60, "ticks": [{"v": 0, "label": "0"}, {"v": 30, "label": "30 L"}]}}]}
```

- **Errors.** An unknown id, layout or ref, or a kind with no detail (calendar, timeline,
  cameras), is a `404 {"error": …}`. Without `?layout=` the top-level (Roku) module is used,
  like `/api/module`.
- **No nulls.** The body goes through `prune`. A chart gap is the space between two `runs`,
  never a null.
- **Windows.** The chart is 168 hourly buckets ending at the start of the current hour. The
  days strip is the 6 previous local days (config `timezone`) from statistics, then "Today"
  from live states. Laundry's "Last 7 days" and doors' "Today" come from state history.
- **Failure.** A failed statistics read gives a chart with `empty: "History unavailable"`
  (`"No history yet"` when HA has no rows). A failed history read gives a top-level `note`.
  A detail that raises answers `200` with `note: "Detail unavailable"` and no blocks.
- **Cost.** A cold call makes up to two websocket reads (hourly, daily) or one history read,
  a second or two. They are cached about 10 minutes (laundry and door history 60 s) with
  keep-last-good, and the tablet allows 20 s.

| module | blocks | data |
|---|---|---|
| water | stats (Now, Today + cost, This month in m³ + estimated cost) · hourly chart in L, filled · days with cost | `stat_usage` / `stat_cost` statistics, `change`, `units: {"volume": "L"}` |
| energy | stats (Now kW, Today kWh + cost, This month kWh + estimated cost) · hourly kWh chart · days | `stat_usage` / `stat_cost`, `change`, `units: {"energy": "kWh"}` |
| gas | stats (Now m³/h, Today m³, This month m³; costs when known) · hourly m³ chart · days | `stat_usage` / `stat_cost`, `change`, `units: {"volume": "m³"}` |
| climate | stats (Indoor, Outdoor, Humidity, Mode + action, Set to) · chart of Indoor (`heat`) vs Outdoor (`cool`) | `indoor_temp` / `outdoor_temp` statistics, `mean`, `units: {"temperature": "°C"}` |
| weather | two columns (`col`). Left: `now` (glyph, temp, condition, H/L, "Updated 2:05 PM") · facts `rows` (Feels like, Humidity, Wind, Pressure, Sunset, Sunrise) · compact `forecast`, next 3 days after today. Right: `hourly` (the next 8 hours) · `chart` of outdoor temperature, 24 h observed + 24 h forecast, "Now" tick. Note: the weather entity's attribution | `weather.get_forecasts` daily and hourly, `outdoor_temp` statistics (`mean`, `units: {"temperature": "°C"}`), the weather entity's attributes, `wind_chill`, `sun` |
| laundry | rows per machine (Status, Last started, Last finished, Last run length) · rows "Last 7 days" | the `input_datetime`s; `sensor.laundry_<m>_mode` history (`running`/`overtime` = a run) |
| doors | rows "Now" (state + since) · rows "Today" (each opening and how long) | the tile's logic; contact history since local midnight (`on` = open) |

**Descriptor keys** (in the tablet layout's `ref` entries; a missing key leaves that part
out). A `ref`'s `entities` replaces the top-level map, so each entry repeats it in full.

| module | `entities.*` read by `detail()` and `tileStyle` |
|---|---|
| water | `flow`, `daily`, `cost_today`, `monthly`, `monthly_cost`, `stat_usage` (`sensor.water_meter_total`), `stat_cost` (`sensor.water_meter_total_cost`) |
| energy | `power`, `daily_energy`, `cost`, `monthly`, `monthly_cost`, `stat_usage` (`sensor.emporia_total_daily_energy_kwh`), `stat_cost` (its `_cost`) |
| gas | `flow`, `daily`, `cost_today`, `monthly`, `monthly_cost`, `stat_usage` (`sensor.gas_meter_gas_meter_direct`), `stat_cost` (its `_cost`) |
| climate | `thermostat`, `indoor_temp` (`sensor.my_ecobee_temperature`), `outdoor_temp` (`sensor.edmonton_weather_temperature`) |
| weather | `forecast` (`weather.edmonton_forecast`), `outdoor_temp` (`sensor.edmonton_weather_temperature`), `sun` (`sun.sun`), `wind_chill` (`sensor.edmonton_weather_wind_chill`; leave it out and the Feels like row goes). `wind_speed` (`sensor.edmonton_weather_wind_speed`) fills in when the weather entity has no speed: EnvCan leaves it empty when calm, and a 0 shows as "Calm". `forecast`, `outdoor_temp`, `sun` and `wind_speed` default to those entities when missing. `precip` is no longer read (EnvCan's chance-of-precipitation sensor is usually `unknown`; the forecast rows carry the chance) |
| laundry, doors | their existing keys |

`dashboard.json.example`'s `layouts.tablet` has the full entries. Statistics are read with
the same long-lived token as everything else; `recorder/statistics_during_period` needs no
admin rights (the `recorder.get_statistics` service does).

## Adding a module

1. Add a descriptor to `dashboard.json`.
2. Drop `haku_sidecar/modules/<kind>.py` exposing `values(ha, descriptor)` and optional
   `CARDS = {name: render(ha, descriptor, w, h)}` and/or an optional
   `render_icon(ha, descriptor, w, h)` (home-tile accent icon, see `haku_sidecar/icons.py`)
   and/or an optional `detail(ha, descriptor, now)` returning `{"blocks": [...], "note"?}`
   (built with `haku_sidecar/blocks.py` and the pure helpers in `haku_sidecar/history.py`);
   register it in `modules/__init__.MODULES`.
3. Add the kind to the Roku's `HK_MODULE_KINDS()` (and a tile sub-renderer only if it's a
   novel `tile.type`). A kind that only a non-Roku layout uses, like `laundry`, skips this.

## Backgrounds

The sidecar serves the full-screen photo background that the tablet's and the Rokus'
glass cards composite over. Images are read at request time from **`HAKU_BG_DIR`**
(default `/etc/haku/backgrounds/`); the sorted basenames are the listing order and the
interval is config-driven (`background.intervalMs` in `dashboard.json`, default 20 s).
Each image is served at the exact size the client asks for.

**One shared folder, mirrored from the NAS.** Every display reads `HAKU_BG_DIR`. Its
photos are curated on the NAS in `/mnt/media/haku/kitchen` (an NFS `hard` mount on
nserver) and mirrored in by **`haku-bg-sync.timer`** every 15 minutes
(`haku-bg-sync.sh`: `rsync -rt --delete`, top-level images only). Displays never read
the NAS, so a stalled mount can't freeze one, and new photos appear within about 15
minutes plus the clients' list refresh (10 minutes on both the tablet and the Roku). The
script skips a run, keeping the last good copy, when `/mnt/media` isn't mounted or the
source has no images: mirroring an empty source would wipe every display. It logs one
line per run (`journalctl -u haku-bg-sync`).

```bash
sudo install -m755 haku-bg-sync.sh /opt/haku/haku-bg-sync.sh
sudo install -m644 haku-bg-sync.service haku-bg-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl start haku-bg-sync.service   # first copy now
sudo systemctl enable --now haku-bg-sync.timer
```

**Per-layout directories** (supported, unused since the mirror). A layout can read its
photos from its own directory with `layouts.<name>.background.dir`, for example an NFS
mount. `/api/backgrounds?layout=tablet` then lists that directory, and each listed `url`
carries `?layout=tablet` so it is served from there too. Without `?layout=`, or when the
layout has no `dir`, `HAKU_BG_DIR` applies as before. An unknown layout is a 404. The
`dir` itself is never serialized into `/api/config`.

A layout `dir` can be a `hard` NFS mount, where a dropped NAS blocks `stat()` and `open()`
forever. So at most two requests that read a layout `dir` run at once; a third gets
`503 {"error": "backgrounds busy"}` straight away, leaving waitress's other threads free
for the Rokus. Requests on `HAKU_BG_DIR` are never limited.

```json
"layouts": { "tablet": { "background": { "intervalMs": 180000, "dir": "/mnt/photos/drone" } } }
```

**`fit` and `blur`** (query parameters on `/api/background/<name>`):

| Param | Values |
|---|---|
| `fit` | `contain` (default): scale to fit inside `w`×`h`, letterbox onto black. Roku channels before 0.13 get this. `cover`: scale by `max(w/src_w, h/src_h)` and centre-crop to exactly `w`×`h`. Anything else is a `400`. |
| `blur` | Gaussian radius 0–40 (clamped), applied to the photo after resizing. Default 0; a value that isn't a finite number counts as 0. |

The tablet asks for `w=1024&h=600&fit=cover` (sharp) and `w=256&h=150&fit=cover&blur=8`
(soft); the Roku (0.13+) for `w=1920&h=1080&fit=cover`, since most of the drone photos
are 4:3.

**Errors.** An unlisted name is `404 {"error": "unknown background", "name": …}` and a
bad `fit` is `400 {"error": "unknown fit", "fit": …}`, checked before any file is read. A
listed file Pillow can't decode (corrupt, truncated, or a decompression bomb) is
`422 {"error": "undecodable background", "name": …}`. Names starting with `.`, such as
the AppleDouble `._*` files a Mac leaves on a share, are never listed.

Sources are decoded with Pillow's JPEG draft mode (a 12 MP photo is decoded at a reduced
scale) and an EXIF orientation is applied before resizing, so a sideways
photo comes out upright. JPEGs in MPO form (some drone cameras write them) are read as
their main frame. Rendered images are cached in memory, keyed by directory, file, mtime,
size, fit and blur. It is least-recently-used with room for 160 renders, enough for the
whole photo set at every client size (42 photos × 3 sizes, about 25 MB), so past the cap
only the oldest render goes. A directory's listing is cached against the directory's mtime, so a call costs one
`stat` until a photo is added or removed.

`sidecar/backgrounds/*` in the repo is the **seed set** for a fresh install without the
NAS mirror (the live wall no longer uses it) — copy it into `HAKU_BG_DIR`:

```bash
sudo install -d -o media -g media /etc/haku/backgrounds
sudo cp backgrounds/*.jpg /etc/haku/backgrounds/   # seed images (swap for your own)
```

`bg_01.jpg`..`bg_05.jpg` are generic CC0/placeholder landscapes — swap for your own.
`bg_00_haku_logo.jpg` is the default branded card (HAku wordmark centered on cream),
generated by `roku/scripts/generate_brand_assets.py`; it sorts first in rotation
(filename-sorted playlist). Drop in your own JPEG/PNG/WEBP files and they appear in the
roster automatically (no restart, no code change).

## Run

### systemd (parity with the stream stack)
```bash
sudo install -d -o media -g media /opt/haku/sidecar
sudo cp -r haku_sidecar /opt/haku/sidecar/
python3 -m venv /opt/haku/sidecar/venv
/opt/haku/sidecar/venv/bin/pip install -r requirements.txt   # includes websocket-client
sudo install -D -m600 dashboard.json.example /etc/haku/dashboard.json   # then edit
sudo install -D -m640 -o root -g media /dev/stdin /etc/haku/haku.env <<'ENV'
HAKU_HA_URL=http://192.0.2.10:8123
HAKU_HA_TOKEN=<rokuapp long-lived token>
HAKU_SIDECAR_HTTP_PORT=1986
HAKU_SIDECAR_BASE=http://192.0.2.20:1986
HAKU_CONFIG=/etc/haku/dashboard.json
ENV
sudo cp haku-sidecar.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now haku-sidecar
```

### Docker (portable escape hatch)
```bash
docker build -t haku-sidecar .
docker run -d --restart=always --network host --env-file /etc/haku/haku.env \
  -v /etc/haku/dashboard.json:/etc/haku/dashboard.json:ro --name haku-sidecar haku-sidecar
```

## Environment

| Var | Default | Purpose |
|---|---|---|
| `HAKU_HA_URL` | `http://192.0.2.10:8123` | Home Assistant base URL |
| `HAKU_HA_TOKEN` | — | long-lived token (`rokuapp`); never logged, never in the repo |
| `HAKU_POLL_INTERVAL` | `10` | seconds between HA `/api/states` refreshes |
| `HAKU_SIDECAR_HTTP_PORT` | `1986` | HTTP listen port |
| `HAKU_SIDECAR_BASE` | derived LAN IP | base URL advertised to the Roku in `/api/config` |
| `HAKU_CONFIG` | `/etc/haku/dashboard.json` | dashboard config path |
| `HAKU_BG_DIR` | `/etc/haku/backgrounds` | directory of rotating background images, mirrored from the NAS by `haku-bg-sync` (a layout's `background.dir` overrides it for `?layout=`) |

## Dependencies

`requirements.txt`: Flask, waitress, matplotlib, Pillow and `websocket-client`. The last
is only for the detail panels' long-term statistics: `ha.py` imports it inside the one
call that needs it, so the rest of the sidecar (and the tests) run without it. Without it
every detail chart reads "History unavailable".

## Tests

```bash
python -m pytest tests -q          # no HA/network needed (FakeHA fixtures)
```

`tests/test_roku_golden.py` pins the default (Roku) `/api/config` and `/api/state` byte for
byte against `tests/golden/`, built from `dashboard.json.example` with a frozen clock.
Regenerate them only for a change the Rokus should see:
`HAKU_UPDATE_GOLDEN=1 python -m pytest tests/test_roku_golden.py`.
