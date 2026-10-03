# Tablet UI v2: shared contract reference

Every task in `2026-09-30-tablet-ui-v2.md` relies on this file. It pins down the exact values: the JSON shapes, glyph names, colours, sizes and timings. Approved design: `~/.claude/plans/lets-take-this-to-curious-phoenix.md`.

## 1. Sidecar JSON contract v2

### 1.1 `GET /api/config?layout=tablet`

```json
{
  "version": 1, "site": "home", "timezone": "America/Edmonton",
  "grid": { "cols": 4, "rows": 3 },
  "nightDim": { "start": "22:00", "end": "06:30", "brightness": 0.15 },
  "background": { "enabled": true, "intervalMs": 180000 },
  "modules": [
    { "id": "doors",    "kind": "doors",    "title": "Doors",      "feedKey": "doors",    "tile": { "type": "value",  "col": 0, "row": 0, "w": 1, "h": 1 } },
    { "id": "laundry",  "kind": "laundry",  "title": "Laundry",    "feedKey": "laundry",  "tile": { "type": "value",  "col": 1, "row": 0, "w": 1, "h": 1 } },
    { "id": "timeline", "kind": "timeline", "title": "Activity",   "feedKey": "timeline", "tile": { "type": "agenda", "col": 3, "row": 0, "w": 1, "h": 3, "dropHeaders": true } },
    { "id": "water",    "kind": "water",    "title": "Water",      "feedKey": "water",    "tile": { "type": "value",  "col": 0, "row": 1, "w": 1, "h": 1 } },
    { "id": "energy",   "kind": "energy",   "title": "Energy",     "feedKey": "energy",   "tile": { "type": "value",  "col": 1, "row": 1, "w": 1, "h": 1 } },
    { "id": "climate",  "kind": "climate",  "title": "Thermostat", "feedKey": "climate",  "tile": { "type": "value",  "col": 2, "row": 2, "w": 1, "h": 1 } },
    { "id": "weather",  "kind": "weather",  "title": "Weather",    "feedKey": "weather",  "tile": { "type": "value",  "col": 0, "row": 2, "w": 1, "h": 1 } },
    { "id": "gas",      "kind": "gas",      "title": "Gas",        "feedKey": "gas",      "tile": { "type": "value",  "col": 1, "row": 2, "w": 1, "h": 1 } },
    { "id": "calendar", "kind": "calendar", "title": "Calendar",   "feedKey": "calendar", "tile": { "type": "agenda", "col": 2, "row": 0, "w": 1, "h": 2, "dropHeaders": false } }
  ],
  "sidecar": { "base": "http://192.0.2.20:1986", "config": "/api/config", "state": "/api/state" }
}
```

**What the response may and may not contain**
- Real descriptors also carry `entities`, `icon`, `drill`, `refreshMs` and other keys. The tablet ignores unknown keys.
- `background.dir` exists only in the sidecar's config file and **never** appears in a response.
- `/api/config` without `?layout` (the Roku) never contains `layouts`.

### 1.2 `GET /api/state?layout=tablet`

The response is `{ "v": 1, "ts": <epoch s>, "<feedKey>": <values>, ... }`, with all `None` values pruned.

**Every value module** (weather, energy, water, gas, climate) carries a `tile` object and `stale`:

```json
"water": {
  "running": true, "stale": false, "...raw fields...": "...",
  "tile": {
    "hero": "57 L", "sub": "flowing 5.7 L/min", "detail": "24h 424.9 L   30d 19.1 m³",
    "severity": "normal",
    "icon": "55",
    "glyph": "water",
    "active": true,
    "level": 55
  }
}
```

**Tile keys**
- `hero`, `sub`, `detail` and `severity` (`low | normal | high`) are unchanged. `icon` is the Roku's cache-bust token; the tablet ignores it.
- **New:**
  - `glyph`: an MDI name (§2), chosen from state.
  - `active`: always a real bool.
  - `level`: 0–100 for energy, water and gas; absent elsewhere.

**Per-module rules** (sidecar side)

| kind | glyph | active | level |
|---|---|---|---|
| weather | HA condition map (§2.2) | false | — |
| energy | `flash` | false | `fill_bucket_pct(power_kw, 5.0)` |
| water | `water` if running, else `water-outline` | `running` | `fill_bucket_pct(flow, maxFlowLpm)` |
| gas | `fire` if running, else `meter-gas` | running: displayed flow `round(flow, 1)` > 0 | `fill_bucket_pct(flow, maxFlowM3h)` |
| climate | heating `fire`, cooling `snowflake`, fan `fan`, else `thermostat` | hvac_action ∈ {heating, cooling}; fan-only is not active (`sub` reads "Fan") | — |
| calendar | `calendar` | false | — |
| timeline | `history` | false | — |
| doors | `door-open` if any door is open, else `door-closed` | any door open | — |
| laundry | `washing-machine` | any machine is `running`, `overtime` or `done` | — |

**Water:** the descriptor option `runningSeverity` defaults to `"high"`, which is today's Roku behaviour. The tablet layout sets `"normal"`.

**Agenda modules** (timeline, calendar): `{ "count": N, "items": [...], "tile": {...} }`.
- A header item is `{ "kind": "header", "title": "TODAY" }`.
- An event item is `{ "kind": "event", "title", "sub"?, "time", "severity", "when"?, "dot"?, "glyph"? }`.
- `dot` is a colour in the Roku's `0xRRGGBBAA` format (calendar).

**Timeline `items[].glyph`**

| Event | Glyph |
|---|---|
| openable (door, window, garage, opening) | on → `door-open`, off → `door-closed` |
| motion / occupancy / presence | on or detected → `motion-sensor`, clear → `motion-sensor-off` |
| lock | unlocked → `lock-open-variant`, locked → `lock` |
| person | home → `home-account`, away → `account-arrow-right` |
| anything else | no glyph (key omitted) |

**Doors** (`kind: doors`). This is DESIGN.md §3.2 plus a per-door `glyph`:

```json
"doors": {
  "doors": [
    { "id": "front", "label": "Front", "state": "closed", "since": 1790821800, "since_exact": true, "age": "12m", "severity": "normal", "glyph": "door-closed" },
    { "id": "back",  "label": "Back",  "state": "open",   "since": 1790822400, "since_exact": true, "age": "6m",  "severity": "high",   "glyph": "door-open" }
  ],
  "open_count": 1, "stale": false,
  "tile": { "hero": "Back open", "sub": "6m", "detail": "Front closed · 12m", "severity": "high", "glyph": "door-open", "active": true }
}
```

- `state` is one of `open | closed | unknown`.
- An unknown door has glyph `door`.

**Laundry** (`kind: laundry`). This is DESIGN.md §3.3 plus a per-machine `status` and `glyph`:

```json
"laundry": {
  "machines": [
    { "id": "washer", "label": "Washer", "color": "#00AAFF", "mode": "running", "leds": 3, "remaining_min": 34, "status": "34m left", "glyph": "washing-machine", "stale": false },
    { "id": "dryer",  "label": "Dryer",  "color": "#FF6900", "mode": "done_calm", "leds": 0, "finished_hm": "9:52 AM", "status": "done 9:52 AM", "glyph": "tumble-dryer", "stale": false }
  ],
  "stale": false,
  "tile": { "hero": "Washer 34m left", "sub": "Dryer done 9:52 AM", "detail": "", "severity": "normal", "glyph": "washing-machine", "active": true }
}
```

- `mode` is one of `idle | running | overtime | done | done_calm`.
- `status` text by mode:

  | mode | status |
  |---|---|
  | idle | `idle` |
  | running | `<remaining_min>m left` |
  | overtime | `running <over_min>m long` |
  | done | `done` |
  | done_calm | `done <finished_hm>` |
  | stale machine | `no data` |

- A machine's `glyph` comes from `machines[].glyph` in config. If that is absent, it is `washing-machine` for id `washer` and `tumble-dryer` for id `dryer`; any other id gets `washing-machine`.

### 1.3 Backgrounds

**Listing:** `GET /api/backgrounds?layout=tablet` returns `{ "images": [ { "name": "drone_001.jpg", "url": "<absolute>" } ] }`.
- The tablet uses only `name`.
- An empty or missing directory gives `{ "images": [] }`.

**Image:** `GET /api/background/<name>?layout=tablet&w=1024&h=600&fit=cover&blur=0` returns `image/jpeg`.

| Param | Values |
|---|---|
| `fit` | `contain` (default, letterbox; what the Roku uses) or `cover` (centre-crop to exactly w×h) |
| `blur` | 0–40 Gaussian radius, applied after resizing; default 0 |
| `w`, `h` | clamped to 64–1920 |

**Requests the tablet makes:**
- sharp: `w=1024&h=600&fit=cover`
- soft: `w=256&h=150&fit=cover&blur=8`

## 2. Glyph vocabulary (MDI names; path data from `@mdi/svg` 7.4.47, Apache-2.0)

### 2.1 Full set (37)

| Group | Glyphs |
|---|---|
| Doors | `door-open`, `door-closed`, `door` |
| Laundry | `washing-machine`, `tumble-dryer` |
| Water, energy, gas | `water`, `water-outline`, `flash`, `fire`, `meter-gas` |
| Climate | `snowflake`, `fan`, `thermostat` |
| Cards | `calendar`, `history` |
| Activity | `motion-sensor`, `motion-sensor-off`, `lock`, `lock-open-variant`, `home-account`, `account-arrow-right` |
| Weather | `alert-circle-outline`, `weather-sunny`, `weather-night`, `weather-partly-cloudy`, `weather-night-partly-cloudy`, `weather-cloudy`, `weather-fog`, `weather-hail`, `weather-lightning`, `weather-lightning-rainy`, `weather-pouring`, `weather-rainy`, `weather-snowy`, `weather-snowy-rainy`, `weather-windy`, `weather-windy-variant` |

### 2.2 HA weather condition → glyph (sidecar)

| Condition | Glyph |
|---|---|
| clear-night | weather-night |
| cloudy | weather-cloudy |
| exceptional | alert-circle-outline |
| fog | weather-fog |
| hail | weather-hail |
| lightning | weather-lightning |
| lightning-rainy | weather-lightning-rainy |
| partlycloudy | weather-partly-cloudy |
| pouring | weather-pouring |
| rainy | weather-rainy |
| snowy | weather-snowy |
| snowy-rainy | weather-snowy-rainy |
| sunny | weather-sunny |
| windy | weather-windy |
| windy-variant | weather-windy-variant |
| anything else, or stale | `weather-partly-cloudy` |

### 2.3 Tablet fallback: kind → default glyph

Used when `tile.glyph` is empty, or names a glyph the tablet doesn't ship.

| Kind | Default glyph |
|---|---|
| doors | door |
| laundry | washing-machine |
| water | water-outline |
| energy | flash |
| gas | meter-gas |
| climate | thermostat |
| weather | weather-partly-cloudy |
| calendar | calendar |
| timeline | history |
| any other kind | no glyph |

## 3. Visual tokens (tablet)

### 3.1 Colours

**Base**

| Token | Value |
|---|---|
| ink | `#FAF6EE` |
| inkMuted | ink at alpha 0.78 (0.72 until v3: on the lighter v3 glass, 16 sp muted text fell to 6.5:1 on the brightest photo; at 0.78 every measured card is at least 7.3:1) |
| inkFaint | ink at alpha 0.48 |
| night | `#0C1211` |
| sage | `#5B8C7F` |
| coral | `#D4673E` |
| amber | `#D9A441` |
| offline | `#6E7471` |

**Accents**

| Token | Value |
|---|---|
| water | `#4FB3E8` |
| heat | `#F2994A` |
| cool | `#7CCBF2` |
| washer | `#00AAFF` |
| dryer | `#FF6900` |
| ledIdleRed | `#E5484D` |
| ledStaleViolet | `#9B7BEA` |

**Card accent from glyph**

| Glyph | Accent |
|---|---|
| door-open | amber |
| water | water |
| fire | heat |
| snowflake | cool |
| fan | sage |
| washing-machine | washer |
| tumble-dryer | dryer |
| anything else | sage |

**Agenda row accent from item glyph**

| Glyph | Accent |
|---|---|
| door-open | amber |
| lock-open-variant | amber |
| home-account | sage |
| anything else | inkMuted |

Calendar rows use `parseColor(dot)` instead.

**`parseColor(s, fallback = sage)`** accepts `#RRGGBB`, `#AARRGGBB` and `0xRRGGBBAA` (case-insensitive). Anything else returns `fallback`.

### 3.2 Glass and geometry

**Glass:**
- tint `night` at alpha 0.55 (since v3 only with no photo; with a photo, `glassTint(luma)` gives 0.32 to 0.48, DESIGN §8.3);
- rim 1 dp, ink at alpha 0.08;
- top highlight 1 dp, ink at alpha 0.12;
- corner radius 20 dp;
- glyph chip 48 dp (radius 14 dp, icon 30 dp);
- level bar 4 dp high (radius 3 dp);
- no shadows.

**Active card:**
- chip fill accent at 0.28;
- rim 1.5 dp, accent at 0.85;
- inner glow: a radial gradient of accent at 0.18 from the chip's centre, fading to 0 at 70% of the card's width.

**Alert card:**
- rim 2 dp coral;
- the hero text turns coral;
- overrides active.

**Stale card:** content alpha 0.5, no accent.

**Screen:**
- 1024×600 dp;
- header 56 dp;
- grid insets: left 12, top 56, right 12, bottom 12;
- gap 10;
- 4×3 cells are about 242.5×170.7 dp.

### 3.3 Type

**Faces:** Barlow (OFL) from `res/font/`: `barlow_medium.ttf` (500) and `barlow_semi_condensed_semibold.ttf` (600). No other weights. (`barlow_semibold.ttf` shipped in Task 10 but no style used it; Task 11 removed it.)

**Rules:**
- Every numeric style sets `fontFeatureSettings = "tnum"`.
- `fontScale` is locked to 1.
- **Minimum size 16 sp.**

| Style | Face, size |
|---|---|
| clock | semi-condensed 600, 40 sp |
| date | medium 20 sp |
| hero | semi-condensed 600, 44 sp, `lineHeight` 44 sp, `LineHeightStyle(Center, Trim.Both)`, `FitText` min 30 sp |
| state | semi-condensed 600, 26 sp (door state word, laundry status) |
| sub | medium 20 sp |
| agendaTitle | medium 18 sp |
| detail | medium 16 sp |
| cardTitle | medium 16 sp, colour inkMuted, sentence case (never upper-cased) |

### 3.4 Motion

**Springs:**
- `effectsSlow = spring(dampingRatio = 1f, stiffness = 800f)`
- `spatialStandard = spring(dampingRatio = 0.9f, stiffness = 700f)`

**Timings**

| Moment | Timing |
|---|---|
| Activate | tween 600 ms |
| Deactivate | tween 1,200 ms |
| Alert | tween 600 ms |
| Ring pulse | 1,400 ms each, FastOutSlowIn. 1 on becoming active, 2 on alert. |
| Re-pulse cooldown | no active ring for a card that went inactive < 120,000 ms before; alert rings are never held back |
| Hero change | `AnimatedContent`, 12 dp vertical slide + fade, 350 ms |
| New activity row | accent highlight fades over 4,000 ms |
| Background cross-fade | 1,600 ms `LinearOutSlowInEasing`; no zoom |
| Burn-in shift | ±2 dp every 10 min, no animation |

**Laundry LEDs:** stepped at ≤ 10 fps, and only while in an animated mode on a live card: offline, or a stale laundry card, holds the t = 0 frame. Nothing else loops.
