# Tablet v3: tap-to-expand details, photo peek, lighter glass, held values, clearer tiles

> **Status: implemented 2026-10-01 and merged to `main` in both repos; the `feat/tablet-details` branches are deleted.** This plan is the record of what was approved. Where the shipped behaviour differs (the 5-minute hold grace, `inkMuted` 0.78, the gas sensors), DESIGN §8 and the v3 contract are current.

## Context

The kitchen tablet (`io.haku.tablet`) is a glance-only, 4×3 board of smoked-glass cards over NAS photos. The user wants:
- **Detail panels.** Tapping a card expands it to a full-width panel with more data:
  - weather: a 3-day forecast with condition icons;
  - water, energy and gas: 7-day usage graphs;
  - thermostat: a 7-day indoor vs outdoor temperature graph;
  - laundry: last start and finish dates;
  - calendar and activity: the same lists, full width.
- **Photo peek.** Tapping the clock/date bar hides the UI so the photo shows clearly.
- **Lighter glass.** The cards become more see-through.
- **Clearer tiles.** Water, energy and gas each show a period label and today's cost.
- **Held values.** A value that goes null or blank keeps its last good reading, greyed out, and the header shows "degraded".

**Hard constraint:** all data lives in Home Assistant. The sidecar stores nothing.

### Findings that shape the plan
- **Water blanking happens upstream.** The ESP meter (`esp-watermeter` @ 192.0.2.41) fails its API handshake over and over. That gave 12 outages in 7 days, 5 of them in the hour checked, and it was down while I checked. When the meter drops, every water helper derived from it goes unavailable. The sidecar's water `stale` flag is also wrong: a hero of "-- L" can arrive with `stale:false`. Fixing the ESP itself (WiFi or power) is a follow-up outside this plan.
- **HA (2026.8.3, mserver, `/root/docker/homeassistantV3/config/ha`):**
  - Recorder keeps 14 days. Long-term statistics (LTS) are kept forever.
  - LTS exists for `sensor.water_meter_total` (since May), `sensor.water_meter_total_cost`, `sensor.emporia_total_daily_energy_kwh` and its `_cost`, `sensor.electricity_daily_cost`, `sensor.my_ecobee_temperature`, `sensor.edmonton_weather_temperature`, and `sensor.gas_meter_gas_meter_direct`. Gas LTS only starts 2026-10-01, so its graph fills in over a week.
  - `sensor.laundry_*_mode` and the door contacts are recorded.
  - Water and electricity prices exist (`packages/water_cost.yaml`, `electricity_cost.yaml`). There is **no gas price and no gas daily meter**.
- **How to read the statistics.** `recorder.get_statistics` is admin-only, so the sidecar uses the websocket command `recorder/statistics_during_period`. It's the Energy dashboard's call, any HA user can make it, and HA handles meter resets and unit conversion. This adds one sidecar dependency, `websocket-client`. Laundry runs and door events (small) use REST `/api/history/period`.
- **nserver deploy.** The sidecar is at `/opt/haku/sidecar` (owned by media, systemd `haku-sidecar`), and the precedent is a dated `haku_sidecar.bak-*` copy. `/etc/haku/dashboard.json` reloads on mtime. SSH to mserver and nserver is approved by the user.

### Decisions (user)
- **Tiles: "now · today · cost".** For example: `4.2 L/min` / `412 L today` / `$1.24 today`. The same shape applies to energy (`kW`, `kWh today`) and gas (`m³/h`, `m³ today`). A cost line is hidden when its price is missing or 0. Tablet layout only; the Roku is unchanged.
- **Glass:** lighter tint, same frost (blur stays 8), tuned on the wall.
- **Hold:** keep the last good value until it recovers, greyed, with "as of 7:41 PM". Drop it at local midnight. Value cards only.
- **HA changes:** I make them over SSH. Gas price comes from a bill-based `gas_cost.yaml` with placeholders until the user supplies the figures.
- **Degraded indicator:** an amber dot (the wall's existing warning yellow, also used by "lagging") with the words "degraded · Water". The word tells the states apart.

## Architecture

**HA**
- Packages add a gas daily meter, today's-cost templates, and `always_available` on the water meters.
- LTS is the single source for every 7-day series.

**Sidecar**
- A new `GET /api/detail/<id>?layout=tablet` returns generic typed **blocks**: `stats`, `chart`, `days`, `forecast` and `rows`. The sidecar formats every string. The tablet renders blocks without knowing which module they came from, and skips unknown block types.
- Chart gaps are `runs`, not nulls, because `store.prune()` drops `None` inside lists and would shift every point after a gap.

```json
{"v":1,"id":"water","title":"Water","ts":0,"blocks":[
 {"type":"stats","items":[{"label":"Now","value":"0 L/min"},{"label":"Today","value":"412 L","sub":"$1.24"}]},
 {"type":"chart","title":"Per hour, last 7 days","start":0,"step":3600,"count":168,
  "series":[{"label":"Water","tone":"water","fill":true,"runs":[{"i":0,"v":[1.0,0.0]}]}],
  "x":{"ticks":[{"i":7,"label":"Thu"}]},"y":{"min":0,"max":60,"ticks":[{"v":30,"label":"30 L"}]},"empty":"No history yet"},
 {"type":"days","items":[{"label":"Thu","value":"412 L","sub":"$1.24"}]},
 {"type":"forecast","days":[{"label":"Fri","glyph":"weather-rainy","hi":"12°","lo":"4°","cond":"Rain","sub":"40%"}]},
 {"type":"rows","title":"Last 7 days","items":[{"glyph":"washing-machine","tone":"washer","label":"Washer","value":"Thu 9:12 AM","sub":"58m"}]}]}
```

- `tone` is a token key (`water`, `heat`, `cool`, `ink`, `muted`, `washer`, `dryer`). An unknown key falls back to ink.

**Tablet**
- **Panel position.** A detail overlay sits inside the burn-in-shifted UI `Box`, so `LocalBackdrop` frost works. The panel is placed once at its final rect, the grid area below the header (about 1000×532 dp).
- **Opening.** It opens with a **draw-phase clip reveal** that grows from the tapped card's `tileRect` over about 250 ms. Nothing re-lays-out per frame, and the frost stays aligned.
- **The grid behind it** fades out through `graphicsLayer { alpha; compositingStrategy = ModulateAlpha }`. That avoids offscreen buffers and fixes night mode, where there is no photo and the frost is transparent.
- **Panel content.** The header comes from the live `CardModel` (5 s polls). The body comes from the fetched detail, refreshed every 60 s.
- **Local details.** Calendar and activity build their detail from state items the tablet already has, with no fetch. A 404 or failed fetch falls back to the tile, shown big.
- **Closing.** Tap anywhere on the panel, press Back, or wait 90 s. An ALERT pulse closes the panel and peek, so an overlay never hides an alert. There is no scrolling.

## Phases

Work on branch `feat/tablet-details` in both repos and commit at the end of each phase. Each phase finishes green and is checked on the wall.

Paths: `T` = `app/src/main/java/io/haku/tablet`, `S` = `~/code/roku-homewall/server/sidecar`.

### Phase 0: safety nets
- Add `S/tests/test_roku_golden.py` and `S/tests/golden/roku_{config,state}.json`, captured before any change from `dashboard.json.example`, a rich FakeHA and a frozen `now`. From then on, the Roku output must not change byte for byte.
- Capture the live Roku `/api/config` and `/api/state` (no layout) from nserver to diff after each deploy.

### Phase 1: held values and "degraded" (tablet), truthful `stale` (sidecar)
**Sidecar**
- In `modules/{water,gas,climate,weather}.py`, a placeholder hero always comes with `stale:true`.
- Add `S/tests/test_stale_invariant.py`, parametrized over the value modules with empty and partial FakeHA states.

**Tablet**
- `data/Models.kt`: add `HubState.error(key)`.
- `ui/model/Project.kt`: a missing tile, a blank hero or an `error` key also means `stale`.
- New `ui/model/TileHold.kt`, pure:
  - It remembers each value card's last good `ValueModel` and when it was good.
  - A stale card is replaced by the held copy with `stale=true`, `active/alert=false`, `pulseCount=0`, and an `asOf` text.
  - Held copies are dropped at local midnight. A config reload prunes ids that no longer exist.
  - Doors, laundry and agenda cards are never held.
- `ValueModel`: add `asOf: String?`. `ValueCard` shows it in place of the detail line.
- `ui/model/PollTracker.kt`:
  - Project once, then hold, then signals, then decorate pulses with `copy()`.
  - Return `PollResult(cards, degraded: List<String>)`, titles in config order.
  - `onFail` keeps the hold memory and still resets the pulse baselines.
- `DashboardViewModel.kt`: add `UiState.degraded`.
- `ui/Header.kt`: `headerStatus(fresh, fetched, degraded)`.
  - Priority: connecting > offline > lagging > degraded > live.
  - Labels: "degraded · Water", "degraded · Water, Gas", or "degraded · 3".
- Demo: add a `degraded` scenario (`app/src/debug/assets/demo/degraded.json`, `DemoSource.kt`).

**Tests**
- `TileHoldTest`: holds, recovers, midnight drop, never holds doors or laundry, survives `onFail`, prunes on reload.
- `PollTrackerTest` additions: no ring entering or leaving a hold, `pulseSeq` kept.
- `OfflineTest` / `headerStatus` cases.

**Wall:** `--es demo degraded`, then live. The water card is greyed with "as of" while the ESP is out.

### Phase 2: lighter glass and header photo peek (tablet)
**Glass**
- Add `glassTint(luma)` in `ui/theme/Tokens.kt` (or `Scrim.kt`), a pure ramp in the style of `scrimAlpha`. Start at about 0.32 on dark photos and about 0.48 on bright ones. Keep 0.55 with no photo.
- `GlassCard.kt` reads the luma in draw from `BackdropState`, cross-faded.
- Extract `Modifier.glass(backdrop, origin, tint)` (frost, tint, rim, highlight) from `GlassCard` so the panel can reuse it.
- Tune on the wall with screenshots. Check contrast on the brightest photo: at least 7:1 for text of 32 sp or less. If it falls short, raise the bright end of the ramp.

**Peek**
- `ui/backdrop/BackdropState`: add a `veil` Animatable. `Backdrop.kt` and `Frost.kt` scale the scrim by `1 - veil`, read in draw only.
- VM: a `peek` StateFlow, `startPeek()` (no-op without a photo), `endPeek()`, return after 30 s, and end when night starts.
- `Dashboard.kt`:
  - the UI `Box` gets `graphicsLayer { alpha = 1 - veil; ModulateAlpha }`;
  - while peeking, a full-screen tap catcher sits last in the `Box`.
- `Header.kt`: `clickable(interactionSource = null, indication = null)`. A pure `headerTapAction(detailOpen, peeking, hasPhoto)` decides: a tap closes an open detail, otherwise it toggles peek.
- Back button: `BackHandler(enabled = peeking || detailOpen)` (activity-compose is already a dependency).

**Tests:** `GlassTintTest`, `PeekTest` (virtual time, no photo, night), `HeaderTapTest`.

**Wall:**
- screenshots of the glass on several photos;
- tap the header with `adb shell input tap 300 28`;
- `dumpsys meminfo` after 10 peeks;
- `setprop debug.hwui.show_layers_updates true` shows no offscreen layers.

### Phase 3: HA packages and tile wording (mserver, sidecar)
**HA, via SSH to mserver**
- First back up `configuration.yaml` and `packages/`.
- `S/ha-water-helpers.yaml` (→ `packages/haku_water.yaml`):
  - add `always_available: true` to `haku_water_hourly` and `haku_water_daily`;
  - add a template `sensor.water_cost_today`: `water_daily_usage` / 1000 × `sensor.water_marginal_cost_per_m3`.
- New `S/ha-gas-cost.yaml` (→ `packages/gas_cost.yaml`), in the style of `water_cost.yaml`:
  - the bill breakdown as **placeholders** (energy $/GJ, delivery $/GJ, riders, GJ/m³) feeding `sensor.gas_marginal_cost_per_m3`, which reads 0 until filled;
  - `utility_meter` `gas_daily` (`always_available`) → `sensor.gas_daily_usage`, and `gas_monthly`;
  - `sensor.gas_cost_today`;
  - a comment explaining how to set the price entity in the Energy dashboard, so HA auto-creates the gas cost statistic used by the per-day costs.
- Add the include to `configuration.yaml`.
- Run `docker exec homeassistant python -m homeassistant --script check_config -c /config`, then `docker restart homeassistant`. That's a brief HA restart.
- Confirm the new entities with a read-only DB query, or through the sidecar.

**Sidecar**
- `tileStyle: "rate"` descriptor flag in `water.py`, `energy.py` and `gas.py`, following the `runningSeverity` precedent:
  - hero = the rate now; sub = "412 L today"; detail = "$1.24 today", dropped when the cost is missing or 0;
  - stale when the rate source is missing;
  - with the flag absent, output is byte-identical to today's.
- The tablet layout's `ref` entries in `dashboard.json.example` and the live `/etc/haku/dashboard.json` get `tileStyle` and full `entities` maps. Water gains `cost_today`; gas gains `daily` and `cost_today`.
- `S/tests/test_tile_style.py`; the golden test stays green.

**Deploy to nserver**
- Back up to `haku_sidecar.bak-<ts>`, copy the code, restart `haku-sidecar`.
- Diff the Roku `/api/config` and `/api/state` (no layout) against the Phase 0 capture.

**Tablet:** no code. Re-capture `app/src/test/resources/{config,state}.json`, then scrub per the README.

### Phase 4: history and `/api/detail` (sidecar)
**`ha.py`**
- `get_statistics(ids, start, end, period, types, units=None, ttl=600)` over the websocket (`websocket-client`, imported lazily):
  - auth → `recorder/statistics_during_period` → close;
  - goes through `_cached` (keep last good, per-key lock).
- `get_history(ids, start, end, ttl=600)` over REST with `minimal_response&no_attributes`.
- Fix the forecast cache key to `(entity_id, ftype)` and share a `_service_response()` helper.

**New `history.py`**, all pure:
- statistics rows → gap-safe `runs` over UTC hour buckets;
- local-midnight x ticks and day labels (from config `timezone`);
- nice y ticks and labels;
- laundry mode history → runs (start, end, length);
- contact history → open intervals.

**`detail(ha, desc, now)` per module**
- **water, energy, gas:**
  - stats: now, today and cost, this month and cost (from the existing monthly usage and estimated-cost sensors);
  - an hourly 7-day line with a soft fill (LTS `change`; water in L via `units`);
  - a 7-day `days` strip: daily `change` plus cost per day from the Energy-dashboard cost statistics.
- **climate:**
  - stats: indoor, outdoor, humidity, mode and action, setpoint;
  - two hourly `mean` lines, `sensor.my_ecobee_temperature` (heat) vs `sensor.edmonton_weather_temperature` (cool).
- **weather:**
  - stats: temperature, condition, wind chill, humidity, wind, chance of rain;
  - a forecast of the next 3 days from `get_forecasts` daily: glyph via `glyphs.weather_glyph`, high/low, chance of rain.
- **laundry:**
  - rows per machine: status, last started (date and time), last finished, length (from the `input_datetime`s);
  - a "Last 7 days" list of runs from mode history.
- **doors:** each door's state and since, and today's opens with their durations.

**Route and tests**
- `modules.module_detail()` and `app.py` `GET /api/detail/<id>`, passed through `prune`. 404 for an unknown id or a kind with no `detail`.
- FakeHA gains `get_statistics` and `get_history`.
- Tests: `test_history.py` (DST, gaps, window edges), `test_detail_route.py` (404s, no `null` anywhere, Roku routes untouched), `test_detail_modules.py`, `test_ha_client.py`.

**Deploy:** `venv/bin/pip install websocket-client`, update `requirements.txt`, then deploy as in Phase 3. Curl every `/api/detail/<id>?layout=tablet` and time a cold call.

### Phase 5: detail panels (tablet)
**Data**
- `data/Detail.kt`: the model.
- `data/DetailJson.kt`: a tolerant parser:
  - each block in its own `runCatching`; unknown blocks are skipped;
  - clamps: at most 4 series, 2000 points, 14 items and 30 rows;
  - a non-number in a run counts as a gap.
- `data/JsonRead.kt`: the shared `str`, `bool` and `long` helpers, moved out of `Models.kt`.
- `HubSource.detail(id)`.
- `SidecarClient.detail`: a `newBuilder()` client with a 15 s read and 20 s call timeout.
- `DemoSource`: reads `demo/detail_<id>.json` and returns 404 when the asset is missing.

**VM**
- `openDetail(id)`, `closeDetail()`, and a `detail` StateFlow (id plus Loading, Loaded or Failed).
- Refresh every 60 s while open, auto-close after 90 s, and close on an ALERT pulse (through `PollTracker.onPulse`).

**UI, in `ui/detail/`**
- `DetailLayer.kt`:
  - the only reader of `vm.detail`;
  - keeps a held shown id so the close animation still has content;
  - a `reveal` Animatable;
  - the grid fade;
  - ignores taps while animating.
- `DetailPanel.kt`:
  - placed at `detailRect(area)`, with a clip reveal from the tapped card's `tileRect`;
  - `Modifier.glass`;
  - a header (title, chip, the live hero/sub/detail, held styling);
  - the block stack, with the chart taking `weight(1f)`.
- `StatsBlock`, `DaysBlock`, `ForecastBlock` (bundled `weather-*` glyphs), `RowsBlock` (whole rows that fit).
- `ChartGeometry.kt` (pure: runs → polylines, scale, ticks) and `ChartBlock.kt`:
  - `drawWithCache` Paths, `drawText` labels at 16 sp or more, a legend for 2 or more series;
  - no animation.
- `LocalDetail.kt`:
  - `flowColumns(items, rowsPerCol, cols)` for calendar and activity: about 4 columns, and a day header is never left alone at the bottom of a column;
  - `localDetail(ValueModel)` as the fallback.
- `AgendaCard`'s row composables become `internal` so the panel can reuse them.

**Taps:** `Grid` (`Dashboard.kt`) cells get `clickable(interactionSource = null, indication = null) { openDetail(id) }`.

**Tests:** `DetailParseTest`, `ChartGeometryTest`, `FlowColumnsTest`, `DetailRectTest`, `DetailVmTest`, plus additions to `SidecarClientTest` and `DemoSourceTest`.

**Wall:**
- `adb shell input tap` each card, screenshot every panel, and close each one by tap, Back and timeout;
- `gfxinfo framestats` during open and close, and about 0 fps with a panel open while the house is quiet.

### Phase 6: docs, fixtures, measurement
- **`CLAUDE.md`:** no longer read-only; add the touch and overlay rules and the `/api/detail` contract.
- **`docs/DESIGN.md`:**
  - a new §8.10 on touch, detail panels and peek;
  - the glass tint ramp in §8.3;
  - hold and degraded in §8.5;
  - update the "glance-only" lines (:13, :417).
- **Contract doc:** the detail JSON, tones, timings (reveal 250 ms, peek fade about 400 ms, auto-close 90 s and 30 s, held "as of").
- **`README.md`:** the demo scenarios and the new measurements.
- **Sidecar `README.md`:** `/api/detail`, `tileStyle`, the HA packages, the websocket dependency.
- Bump to version 0.3.0.
- Measure the release build: PSS at baseline, after 20 panel opens and after 10 peeks. It must stay at or under 95 MB and flat.
- Leave the branches for the user to review before merging or pushing.

## Verification (end to end)
- **Tablet:** `./gradlew testDebugUnitTest assembleDebug assembleRelease --offline`, then install the release build per CLAUDE.md (install → profile → compile → restart).
- **Sidecar:** `.venv/bin/python -m pytest tests -q` (golden, stale invariant, tile style, history, detail).
- **Live:**
  - `curl 'http://192.0.2.20:1986/api/state?layout=tablet'` shows the new wording and costs;
  - `/api/detail/{water,energy,gas,climate,weather,laundry,doors}?layout=tablet` all return blocks;
  - Roku `/api/config` and `/api/state` (no layout) match the pre-change capture.
- **On the wall** (screenshots only; never sleep or wake the device):
  - lighter glass is legible on bright photos;
  - a header tap shows the photo, and a tap or 30 s brings the UI back;
  - every card opens its panel, and the panel closes by tap, Back and 90 s;
  - water greyed with "as of" and "degraded · Water" while the ESP is out;
  - demo `degraded` and `alert`: an alert closes an open panel.
- **Memory and smoothness:** release `dumpsys meminfo` at or under 95 MB; `gfxinfo` shows no idle redraws.

## Follow-ups (not in this plan)
- Stabilise `esp-watermeter` (.41): its WiFi signal, power, or ESPHome API keepalive.
- Fill the gas bill figures into `gas_cost.yaml` and set the gas price entity in HA's Energy dashboard. The gas cost lines and per-day costs then appear without any code change.
