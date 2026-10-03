# Tablet v3 contract: detail panels, rate tiles, held values

Approved 2026-10-01. This is the shared contract between the sidecar (`~/code/roku-homewall/server/sidecar`) and the tablet (`io.haku.tablet`) for v3. The plan is in `~/.claude/plans/lets-make-some-ui-distributed-treehouse.md`. Where this file and the plan disagree, this file wins.

## 1. `GET /api/detail/<module_id>?layout=tablet`

- **200** with the JSON below for any module whose kind has a `detail()`: `water`, `energy`, `gas`, `climate`, `weather`, `laundry` and `doors`.
- **404** `{"error": "..."}` for an unknown id, an unknown layout or ref, or a kind with no `detail()`.
- Calendar and timeline have **no** sidecar detail. The tablet builds those from the `items` it already has in `/api/state`.
- Output goes through `store.prune()`, so **no key ever carries `null`**. Optional keys are left out instead. Lists never contain nulls; gaps in a chart are expressed with `runs` (below).
- Every string is display-ready. The tablet shows labels, values and subs verbatim and never formats numbers from this payload. The one exception is chart geometry: the tablet scales raw floats into pixels.
- Cache: HA statistics and history calls are cached about 10 min with keep-last-good, so a repeat call is fast. A cold call may take a few seconds. The tablet allows 20 s.

```jsonc
{
  "v": 1,
  "id": "water",                 // module id
  "title": "Water",              // module title
  "ts": 1790905930,              // epoch seconds when built
  "note": "History unavailable", // optional, shown small under the panel header
  "blocks": [ /* zero or more, in display order */ ]
}
```

### Block types

Each block is an object with a `"type"` key. The tablet skips unknown types and malformed blocks silently.

Any block may carry **`"col": 0 | 1`** (default 0; anything else is clamped, and a non-integer is 0). When both columns have blocks the tablet draws two columns (3:5, with the `note` under the right one); otherwise it stacks everything in one, so a payload without `col` renders as before. Added 2026-10-03 for the weather panel ([design](2026-10-03-weather-panel-design.md)).

**`stats`**: a row of up to 6 label/value pairs (the tablet clamps to 6).
```jsonc
{"type": "stats", "items": [{"label": "Now", "value": "4.2 L/min"}, {"label": "Today", "value": "412 L", "sub": "$1.24"}]}
```

**`chart`**: a time-series line chart over uniform buckets.
```jsonc
{
  "type": "chart",
  "title": "Per hour · last 7 days",       // optional
  "start": 1790300000,                     // epoch seconds of bucket 0's start (UTC hour boundary for hourly)
  "step": 3600,                            // seconds per bucket
  "count": 168,                            // number of buckets on the x axis
  "series": [                              // 1..4 series (tablet clamps to 4)
    {
      "label": "Water",                    // legend text (legend shown when there are 2 or more series)
      "tone": "water",                     // token key, see §4
      "fill": true,                        // optional, default false: soft area fill under the line
      "runs": [                            // contiguous stretches of real data; gaps are what's between runs
        {"i": 0,  "v": [1.0, 0.0, 12.5]},  // v[k] is the value of bucket i+k
        {"i": 41, "v": [3.2, 4.0]}
      ]
    }
  ],
  "x": {"ticks": [{"i": 7, "label": "Thu"}]},                         // bucket index of each local midnight, weekday label; "strong": true on a tick (the weather chart's "Now") draws a firmer line and a full-ink label that wins when labels overlap
  "y": {"min": 0, "max": 60, "ticks": [{"v": 0, "label": "0"}, {"v": 30, "label": "30 L"}, {"v": 60, "label": "60 L"}]},
  "empty": "No history yet"                // optional: shown instead of the plot when no series has any run
}
```
- Rules: `0 <= i`, `i + len(v) <= count`, and runs within a series are in increasing `i` and don't overlap.
- The tablet treats a non-number in `v` as a gap and clamps the total to 2000 points.
- If `y` is missing or `max <= min`, the tablet computes a scale from the data and draws no y labels.
- The tablet draws a line, plus an area fill when `fill` is true. It joins consecutive buckets within a run and never across a gap. A run of one bucket is drawn as a dot.

**`days`**: a strip of per-day totals, oldest first, up to 8 items (the tablet clamps to 8).
```jsonc
{"type": "days", "items": [{"label": "Thu", "value": "412 L", "sub": "$1.24"}, {"label": "Today", "value": "88 L", "sub": "$0.27"}]}
```

**`forecast`**: forecast days, up to 5 (the tablet clamps to 5; the sidecar sends 3).
```jsonc
{"type": "forecast", "style": "compact", "days": [{"label": "Fri", "glyph": "weather-rainy", "cond": "Rain", "hi": "12°", "lo": "4°", "sub": "40%"}]}
```
- `glyph` is an MDI name from `glyphs.WEATHER_GLYPHS`.
- `hi`, `lo` and `sub` are each optional.
- `style: "compact"` draws one 32 dp line a day (weekday, glyph, condition, "hi / lo", rain chance). Absent or anything else is the original column per day.

**`now`**: the weather panel's hero. Only `temp` is required.
```jsonc
{"type": "now", "col": 0, "glyph": "weather-partly-cloudy", "temp": "16°", "cond": "Partly Cloudy", "hilo": "H 16°  L 2°", "sub": "Updated 3:04 PM"}
```
- `temp` is `"--°"` when the weather entity is down. `glyph` and `cond` are left out then.
- `hilo` is today's high and low; in the evening EnvCan's first daily row is "Tonight" with no high, so it is just `"L 2°"`.
- `sub` is the weather entity's last update in local time, so a stale source shows.

**`hourly`**: a strip of up to 12 cells (the sidecar sends the next 8 hours, from the next full hour and across midnight; cells are 1/8 of the width).
```jsonc
{"type": "hourly", "col": 1, "items": [{"label": "4 PM", "glyph": "weather-partly-cloudy", "temp": "15°", "sub": "40%"}]}
```
- `label` and `temp` are required; `glyph` and `sub` (the rain chance, left out when 0 because EnvCan reports a missing chance as 0) are optional.

**`rows`**: a titled list of rows. The tablet shows as many whole rows as fit and clamps to 30.
```jsonc
{"type": "rows", "title": "Last 7 days", "items": [
  {"glyph": "washing-machine", "tone": "washer", "label": "Washer", "value": "Thu Oct 1 · 6:05 PM", "sub": "58m"}
]}
```
- `title`, `glyph`, `tone` and `sub` are optional.

### What each module returns

The sidecar builds these. The tablet doesn't depend on block order or presence.

| Module | Blocks |
|---|---|
| water | `stats` (Now L/min · Today L + cost · This month m³ + estimated cost) · `chart` hourly use in L, 7 days, `fill` · `days` last 7 local days (today last, labelled "Today") with L and cost |
| energy | `stats` (Now kW · Today kWh + cost · This month kWh + estimated cost) · `chart` hourly kWh, 7 days, `fill` · `days` kWh and cost |
| gas | `stats` (Now m³/h · Today m³ + cost if known · This month m³ + cost if known) · `chart` hourly m³, 7 days, `fill` · `days` m³ and cost if known |
| climate | `stats` (Indoor · Outdoor · Humidity · Mode/action · Set to) · `chart` 2 series: Indoor (`heat`) and Outdoor (`cool`), hourly mean °C, 7 days, no fill |
| weather | two columns. Left (`col` 0): `now` · facts `rows` (Feels like, Humidity, Wind or "Calm", Pressure, Sunset, Sunrise; each only when it has a source) · compact `forecast`, the next 3 days. Right (`col` 1): `hourly` · `chart` of outdoor temperature on 49 hourly buckets: 24 h observed (`ink`, hourly means, the live reading on the last bucket) and 24 h forecast (`cool`), meeting at a strong "Now" tick on bucket 24, whole-degree y ticks. `note` is the weather entity's attribution |
| laundry | `rows` "Washer" (Status · Last started · Last finished · Last run length) · `rows` "Dryer" (same) · `rows` "Last 7 days" (each run: machine, start, length) |
| doors | `rows` "Now" (each door: state + since) · `rows` "Today" (each open: door, opened h:mm, open length) |

**Data sources (all in HA):**
- **Hourly and daily series:** HA long-term statistics via the websocket `recorder/statistics_during_period`:
  - `change` for counters;
  - `mean` for temperatures;
  - `units: {"volume": "L"}` for water.
- **Laundry runs and door opens:** REST `/api/history/period` with `minimal_response&no_attributes`.
- **Today and month values:** live states.

### Descriptor keys the sidecar reads for detail and the rate style

These go in the tablet layout's `ref` entries. A missing key means that part is left out.

| Module | `entities.*` |
|---|---|
| water | `flow` `sensor.water_flow_lpm`, `daily` `sensor.water_daily_usage`, `cost_today` `sensor.water_cost_today`, `monthly` `sensor.water_monthly_usage`, `monthly_cost` `sensor.water_monthly_estimated_cost`, `stat_usage` `sensor.water_meter_total`, `stat_cost` `sensor.water_meter_total_cost` (plus the existing `hourly` and `total`) |
| energy | `power`, `daily_energy`, `cost` (existing), `monthly` `sensor.electricity_monthly_usage`, `monthly_cost` `sensor.electricity_monthly_estimated_cost`, `stat_usage` `sensor.emporia_total_daily_energy_kwh`, `stat_cost` `sensor.emporia_total_daily_energy_kwh_cost` |
| gas | `flow` `sensor.gas_flow`, `total` `sensor.gas_meter_total` (both from HA `packages/gas_cost.yaml`, replacing the Roku's `sensor.home_gas_usage` and raw meter on the tablet), `daily` `sensor.gas_daily_usage`, `cost_today` `sensor.gas_cost_today`, `monthly` `sensor.gas_monthly_usage`, `monthly_cost` `sensor.gas_monthly_cost`, `stat_usage` `sensor.gas_meter_gas_meter_direct`, `stat_cost` `sensor.gas_meter_gas_meter_direct_cost` |
| climate | `thermostat` (existing), `indoor_temp` `sensor.my_ecobee_temperature`, `outdoor_temp` `sensor.edmonton_weather_temperature` |
| weather | `forecast` `weather.edmonton_forecast`, `outdoor_temp` `sensor.edmonton_weather_temperature`, `sun` `sun.sun`, `wind_speed` `sensor.edmonton_weather_wind_speed` (when the entity has none), `wind_chill` `sensor.edmonton_weather_wind_chill`, `indoor` (existing, tile only). `forecast`, `outdoor_temp`, `sun` and `wind_speed` default to those ids; `precip` is no longer read |
| laundry | existing per-machine entities; mode history from `sensor.laundry_<m>_mode` (modes `running` and `overtime` mean a run) |
| doors | existing `entities.doors[].entity` (binary_sensor, `on` = open) |

## 2. Rate tiles (`"tileStyle": "rate"` on water, energy and gas)

With the flag set:

| Line | Water | Energy | Gas |
|---|---|---|---|
| hero | `4.2 L/min` (`0 L/min` when idle) | `0.9 kW` | `0.8 m³/h` (`0 m³/h` when idle) |
| sub | `412 L today` | `32 kWh today` | `3.1 m³ today` |
| detail | `$1.24 today` | `$6.91 today` | `$1.05 today` |

- `sub` is left out when its "today" entity is missing; `detail` is left out when its cost entity is missing or unavailable. HA makes a cost unavailable when its price is unknown or 0.
- Number formats:
  - water: L/min to 1 decimal, except an exact 0 shows `0`; litres as integers;
  - gas: 1 decimal;
  - energy: kW to 1 decimal, kWh as an integer;
  - cost: `$` and 2 decimals.
- `stale` is true exactly when the hero's source (flow or power) is missing, and then the hero is the placeholder (`-- L/min` and so on).
- `active`, `level`, `glyph` and `severity` keep today's rules.
- **Without the flag**, output is byte-identical to before v3, apart from the `stale` truth fix below.

**Stale truth fix (all layouts).** A value module's `stale` must be `true` whenever its tile hero is a placeholder (starts with `--`). The Roku never reads `stale`.

## 3. Tablet behaviour constants

| Name | Value |
|---|---|
| Detail reveal (clip grows from the card rect) | 250 ms tween, FastOutSlowIn |
| Grid fade under the panel | follows the reveal: grid alpha = 1 − reveal |
| Detail refresh while open | 60 s |
| Detail auto-close | 90 s after opening |
| Peek fade (UI out, scrim out) | 400 ms |
| Peek auto-return | 30 s |
| Held value | kept until the module recovers, dropped at local midnight; for the first 5 min after the last good reading (`HOLD_GRACE_MS`) it shows as live, then the card greys (stale styling), the detail line reads `as of h:mm a`, and the header says degraded |
| Header degraded | priority connecting > offline > lagging > degraded > live; amber dot; label `degraded · Water`, `degraded · Water, Gas`, `degraded · 3` for 3 or more |
| Glass tint | `glassTint(luma)` ramp, about 0.32 (dark photo) to about 0.48 (bright); 0.55 with no photo; tuned on the wall to keep text of 32 sp or less at 7:1 or better |

## 4. Tones

`tone` keys map to existing tokens:

| Key | Token |
|---|---|
| `water` | `Haku.water` |
| `heat` | `Haku.heat` |
| `cool` | `Haku.cool` |
| `washer` | `Haku.washer` |
| `dryer` | `Haku.dryer` |
| `sage` | `Haku.sage` |
| `ink` | `Haku.ink` |
| `muted` | `Haku.inkMuted` |
| `amber` | `Haku.amber` |
| `coral` | `Haku.coral` |

Any other key falls back to ink.
