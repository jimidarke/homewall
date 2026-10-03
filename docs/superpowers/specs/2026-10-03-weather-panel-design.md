# Weather detail panel redesign (tablet + sidecar)

Approved 2026-10-03 (plan approved in the planning session; the user then said "continue"). Extends the v3 contract (`2026-10-01-tablet-v3-details-contract.md`); where they disagree on weather, this file wins. Branches: `feat/weather-panel` in both repos.

## Context

The kitchen wall tablet's Weather panel is just the generic detail body: a 6-column `stats` row over a 3-day `forecast`. Nothing weather-specific exists, the big "now" value is buried as one of six equal columns, and live today only 4 of the 6 stats populate (the wind-chill and rain-chance sensors read `unknown`). The user wants a proper weather screen: **current conditions, the forecast for the current day, a 3-day outlook, and a temperature line graph.**

Research done (3 agents + a read-only HA scan, 2026-10-03, HA 2026.9.4):
- `weather.edmonton_forecast` (EnvCan integration) supports **daily + hourly** forecasts (`supported_features=3`), not `twice_daily`. Hourly = 24 rows (temp, condition, precip %); no wind in the weather-entity forecast.
- `sensor.edmonton_weather_temperature` has hourly history (24 rows/24 h; 168/168 in long-term stats). ECCC itself publishes no observation series, so history comes from the HA recorder.
- EnvCan `wind_chill`, `wind_gust`, `chance_of_precipitation`, `current_condition` sensors are persistently `unknown`; humidity/pressure/wind come from the weather entity's attributes; no UV/dew-point/humidex exposed. `sun.sun` provides sunrise/sunset.
- Zigbee/other "temperature" sensors are integer chip readings and sun-heated (backyard motion swung 8-26 degC in 24 h; `sensor.temperature_external_average` reads 19.5 vs EnvCan 14.1). **Not used** on the weather graph.
- The sidecar already does everything needed server-side (forecast service, websocket long-term stats, tz handling, cached reads). ECCC attribution: "Data Source: Environment and Climate Change Canada".

## Settled decisions (from the user)

1. **Two-column layout** in the 960x446 dp panel body, no scrolling.
   - Left (~351 dp): big "now" hero (glyph, big temp, condition, today's H/L, updated time) -> fact rows -> 3-day outlook as compact rows.
   - Right (~585 dp): hourly strip over the temperature graph.
2. **Graph:** outdoor temperature, **24 h observed + next 24 h hourly forecast**, meeting at a strong "Now" tick. Outdoor only.
3. **Hourly strip = rolling next 8 hours** (runs past midnight; the 12 AM cell is labelled).
4. Read-only. A tap still only closes the panel. No new loops, no new dependencies, no new glyphs.

## Design

### Layout mechanism: a per-block `col` hint (additive)
Any block may carry `"col": 0|1` (default 0). `parseDetail` puts `col==0` blocks in `Detail.blocks` and `col==1` in new `Detail.right`. The tablet draws two columns only when both lists are non-empty; otherwise it stacks as today. Chosen over a `columns` container because an old APK would skip the whole unknown container (blank panel), whereas with `col` it skips only the unknown `now`/`hourly` blocks and stacks the known `rows`/`forecast`/`chart` ones. Fits CLAUDE.md: additive unknown keys; sidecar formats all strings; tablet only picks widths and chart geometry.

### Payload (`/api/detail/weather?layout=tablet`, `v` stays 1)
Block order: `now`(col 0) -> `rows` facts (col 0) -> `forecast style:"compact"` (col 0) -> `hourly` (col 1) -> `chart` (col 1).
- **`now`**: `{glyph, temp, cond, hilo, sub}`; only `temp` required (`"--°"` when the entity is down). `hilo` from the daily item whose local date is today; in the evening ("Tonight", null high) it is just `"L 3°"`. `sub` = local "Updated h:mm a" from `last_updated` (fixes the UTC `observed_hm` quirk in the *detail* only).
- **facts `rows`** (existing block, no tablet code): Feels like (wind_chill, omitted if unavailable), Humidity, Wind (+compass), Pressure (kPa, from entity attr), Sunset/Sunrise (from `sun.sun`, ordered by time, weekday prefix if not today). Usually ~5 rows. "Rain chance" fact dropped (flaky sensor).
- **`forecast` + `style:"compact"`**: next 3 local days (skip today), one 36 dp row each: weekday, 28 dp glyph, cond, hi/lo, rain % (omitted when 0/missing, since EnvCan maps missing POP to 0). Absent `style` = today's 72 dp columns.
- **`hourly`**: up to 8 cells `{label:"4 PM", glyph, temp, sub?}` (tablet clamps 12); `sub` only when POP > 0.
- **`chart`**: `start` = current UTC hour - 24 h, `step` 3600, `count` 49. Series "Observed" (tone `ink`): buckets 0..23 hourly `mean` stats + bucket 24 = live reading. Series "Forecast" (tone `cool`): bucket 24 = live reading (join), buckets 25..48 from the hourly forecast placed by datetime. Ticks every 6 local hours (midnight = weekday), sorted by `i`, ticks within 4 buckets of Now dropped, `{"i":24,"label":"Now","strong":true}`. Y axis via `history.y_scale(..., zero=False)`. Forecast series omitted if its first item is later than bucket 26 (stale keep-last-good). `empty` text if no data.
- Every block builder is individually failure-isolated (`_isolated`): a failing source drops only its block.

### Tablet changes (`~/code/tablet-homewall/app/src/main/java/io/haku/tablet/`)
- `data/Detail.kt`: `Detail.right`, `DetailBlock.Now`, `DetailBlock.Hourly` + `HourCell`, `Forecast.compact`, `XTick.strong`, `MAX_HOURLY = 12`.
- `data/DetailJson.kt`: parse `col`, `now`, `hourly`, `style`, `strong`; partition blocks.
- `ui/detail/Blocks.kt`: `DetailBody` -> pure `bodyLayout(detail)` returning `Single(blocks)` or `Two(left, right)`; shared `ColumnScope.Blocks(...)`; two-column = Row, two Columns weighted 0.375/0.625, 24 dp gap, each computes its own `hasChart`. `ForecastBlock(compact)`.
- New `ui/detail/WeatherBlocks.kt`: `NowBlock`, `HourlyBlock`, compact forecast rows (reuse `FitText` min 16 sp, `Glyph`, `hiLo`).
- `ui/detail/ChartGeometry.kt` + `ChartBlock.kt`: carry `strong` through `AxisTick`; strong tick draws ~0.35 alpha line + ink label. (Today every x tick is a 6%-alpha `DayLine`; verified at `ChartBlock.kt:47,160`.) ~10 lines + a geometry test.
- Debug demo: `DemoSource` reads `detail_<id>_<variant>.json` first (`--es demo_detail tonight|nofc`); new fixtures `detail_weather.json` (day), `_tonight`, `_nofc`.
- Budget (dp): left = now 98 + 16 + facts <=6x32 + 16 + outlook 3x36 = ~430/446; right = hourly 112 + 16 + chart 318 (plot ~262 high x ~537 wide = ~11 dp/bucket, 66 dp between 6 h ticks). Type floor 16 sp held. **Verify the left-column total and the 18 sp fact text on the real device** (these are the agent's estimates).

### Sidecar changes (`~/code/roku-homewall/server/sidecar/haku_sidecar/`)
- `modules/weather.py`: `detail()` becomes a thin assembler; builders `_now_block`, `_facts_block`, `_outlook_block`, `_hourly_block`, `_chart_block`. Cold reads (daily forecast, hourly forecast, one stats call `ttl=300`) run in a 3-thread pool (worst case ~10 s vs the tablet's 20 s timeout). New entity keys default in code (`ents.get("outdoor_temp","sensor.edmonton_weather_temperature")`, `sun` = `sun.sun`), so **no `/etc/haku/dashboard.json` edit**. **`values()` is not touched** (Roku golden `tests/test_roku_golden.py` and `test_sidecar.py:202`'s pinned UTC `observed_hm` stay green).
- `blocks.py`: `now()`, `hourly()`, `forecast(days, style)`, `col(block, n)`. `blocks.chart` keeps its 168 h window; the weather chart is assembled in `weather.py`.
- `history.py`: `hour_label`, `clock_ticks` (local-clock based, so DST needs no special case), `splice_point`.
- `tests/conftest.py`: `FakeHA(forecast=...)` accepts per-type `{"daily":..., "hourly":...}` or a per-type FAIL (legacy list still serves every type; today `get_forecast` ignores `ftype`); `assert_detail_contract` allows `now`/`hourly`, checks `col`/`style`, keeps the null-free rule.
- New tests: full day payload (order + `col`); evening "Tonight" null-high -> `"L 3°"`; missing wind_chill/sun/pressure; hourly/daily/stats failures singly and combined; stale hourly list; cells across midnight; DST (now = 2026-11-01 00:30 local); junk forecast rows; one builder raising; ticks near Now dropped and increasing; spy test that `values()`/`compose_state` still request only `daily`. Update the four existing weather tests (zero-POP `sub:"0%"` expectation changes) and the kinds list at `test_detail_route.py:86`.

### Docs
v3 contract (`docs/superpowers/specs/2026-10-01-tablet-v3-details-contract.md`: `col`, `now`, `hourly`, `forecast.style`, `XTick.strong`, weather module row, descriptor keys), `docs/DESIGN.md` §8.10 weather row, tablet `README.md` + `CLAUDE.md` block list, sidecar `README.md`, `dashboard.json.example`, `weather.py` docstring.

## Order of work (feature branch in each repo; both on `main`, clean)

0. **This file is the written spec.** The contract doc update (`col`, `now`, `hourly`, `forecast.style`, `XTick.strong`) lands with the code that implements it.
1. Sidecar (TDD): (a) `conftest` + `history` helpers + tests; (b) `blocks` + `weather.detail` + tests; (c) docs + example config.
2. Generate real payload fixtures (day, tonight, forecast-down) from the sidecar harness -> `app/src/test/resources/detail_weather_*.json` + a frozen v1 payload `detail_weather_v1.json`. (Generated, not scraped live; no personal data.)
3. Tablet (TDD): (a) model + parse; (b) `bodyLayout` + `Blocks.kt`; (c) `WeatherBlocks.kt` + `strong` tick; (d) demo fixtures + `DemoSource` variant; (e) docs.
4. Release build -> install on tablet -> deploy sidecar (**tablet first**: a new tablet renders the old payload correctly; then the sidecar).

## Verification

- Sidecar: `cd ~/code/roku-homewall/server/sidecar && .venv/bin/python -m pytest tests -q` (Roku golden must stay green).
- Tablet: `./gradlew testDebugUnitTest assembleDebug assembleRelease --offline`. Old v1 payload must parse to `[Stats, Forecast]`, `right` empty, `bodyLayout == Single`.
- On-device screenshots (debug build, `$TABLET_SERIAL`, no sleep/wake): demo `--es demo quiet --es demo_detail tonight|nofc` + the day fixture; tap Weather, `exec-out screencap -p`. Check: no clipped text/rows, hero H/L, "L 3°"-only evening case, full-height observed-only chart when the forecast is down, strong Now line visible.
- Memory: release build + speed-profile compile, ~20 weather opens, `dumpsys meminfo io.haku.tablet` vs the 95 MB budget (v3 settled ~65 MB).
- Live: `curl -s 'http://192.0.2.20:1986/api/detail/weather?layout=tablet'` -> block order, no nulls, cold/warm `%{time_total}`; confirm an evening capture has "Tonight"; check hourly night glyphs (does EnvCan hourly emit `clear-night`? if not, add a `sun.sun`-based swap).

## Outward-facing steps needing explicit confirmation at execution time
Installing the APK on the wall tablet; copying the sidecar to `/opt/haku/sidecar` on nserver and restarting `haku-sidecar` (back up the old dir first; keep the previous APK for rollback); any `/etc/haku/dashboard.json` edit (not required); any preview copy of the sidecar on another port.

## Validation log (kept current while building)

- 2026-10-03: live `/api/detail/weather` was still `stats` + `forecast`; deployed `weather.py`, `blocks.py`, `history.py` were byte-identical to the sidecar repo.
- 2026-10-03: **deployed `modules/timeline.py` on nserver is ahead of the repo** (door/window opening coalescing from the 2026-10-03 audit, uncommitted here). So the sidecar deploy copies **only the files this work changes** (never the whole directory) after diffing each against the deployed copy, and backs them up first.

- 2026-10-03 (built): verified against real data. EnvCan hourly rows are exactly `datetime` (UTC ISO), `condition`, `precipitation_probability`, `temperature` (float), 24 rows an hour apart starting at the next full hour, and the conditions include `clear-night` (so no `sun.sun` glyph swap is needed). The weather entity's `wind_speed` is `None` when the wind is calm while `sensor.edmonton_weather_wind_speed` reads 0, so the Wind fact asks the entity, then the sensor, and says "Calm" for 0. The rain chance was 0 in every hourly row, which the strip omits. Pressure arrives in hPa (HA converts), hence the unit-aware formatter.
- 2026-10-03 (built): on the tablet, the 56 sp hero temperature measures ~68 dp, which clipped the condition line in the first build; fixed with a 92 dp hero row and an unbounded-height column, outlook rows cut to 32 dp (facts get 202 dp for six 32 dp rows). Release build PSS: 47.9 MB fresh, 59.9 MB after 20 weather opens (budget 95 MB).
- 2026-10-03 (deployed): tablet release build installed first and rendered the old stats+forecast payload unchanged; then weather.py, blocks.py and history.py only were copied to nserver (originals in `/opt/haku/weather-panel-backup-20261003/`), and haku-sidecar restarted. The live payload is two-column, 200 OK in ~20 ms warm, no nulls.

## Notes / residual risks
- "Now" is plotted at the top of the current hour (up to ~11 dp left of true time); observed points are hourly means, the last is the live reading.
- Forecast vs observed is distinguished by tone + legend + strong Now line, not dashes (the chart has no dashed lines; a `dash` flag is a possible later add-on).
- Feels-like only appears when EnvCan reports wind chill (cold weather); in warm months the fact list is ~5 rows.
- Not fixed here: the UTC `observed_hm` in `values()` (pinned by the Roku golden).
- The 37.5/62.5 column split is a tablet constant; make it a contract value only if it needs to vary.
- Token handling during research: HA token was read over `ssh mserver` into a shell variable (not printed or stored); the dev-notes alias `arr-stack` is stale (host is `mserver`) - worth correcting in `~/.claude/projects/-home-jimi-code-roku-homewall/memory/haku-sidecar-dev-notes.md`.
