# Roku home: the tablet's v3 glass look and tile layout (read-only)

Date: 2026-10-07. Roku channel 0.11.0, sidecar `layouts.roku`.

## Why

The kitchen tablet got a v3 "smoked glass" redesign: a 4×3 grid over photos, Barlow type, MDI glyph chips, accent and alert states, and doors, laundry, activity and calendar cards. The Roku home screen was still the v0.7 design: square alpha Rectangles on a 4×2 grid, system fonts, a focus ring and OK drill-downs. The goal is for the wall Rokus to look and lay out like the tablet.

## Decisions

- **Read-only glass pane.** Home takes no input: no focus ring, no D-pad navigation, no drill-downs, no OK→live. `*`/options still opens diag for maintenance, and Back still exits. The live, grid and module screens stay in the code. HA camera takeovers (`cam=`, a camera `focusModule=`) still go live; the smoke test depends on that. Any other `focusModule=` lights that card for 8 s instead of drilling in.
- **Layout: 6×3 at 1920×1080.**
  - The left four columns are the tablet's tiles, in the same places.
  - Columns 4–5, rows 0–1: a 2×2 camera square. It's a placeholder for the video feed, which is later work; for now it's a titled empty card.
  - Columns 4–5, row 2: a 2×1 native 3-day forecast strip.
  - Geometry: cells 286×292, gap 20, origin (52, 124), so the grid ends at x 1868 and y 1040. It sits outside strict title-safe, like the old layout did. Because it lives in the config, it can be tuned without a rebuild.
- **Tinted glass, no frost.** Roku has no backdrop blur. Cards are rounded 9-patch PNGs tinted night at 0.62 over the photo and a night scrim gradient.
  - The tablet's frosted glass manages with 0.32–0.48, but 0.55 let busy photos crowd small muted text.

```
 9:17 PM  Wednesday, October 7                        ● live
 Doors   | Laundry | Calendar | Activity | Cameras (2x2 placeholder)
 Water   | Energy  | Calendar | Activity |
 Weather | Gas     | Thermo   | Activity | Forecast (2x1: 3 days)
```

## Sidecar

- **`layouts.roku`** in `dashboard.json` carries the grid's pixel geometry and 11 entries:
  - 9 qualified refs, `{"ref": "tablet:<id>"}`;
  - `cameras` with a 2×2 camera tile;
  - a second weather entry: `"id": "forecast"`, `"feedKey": "forecast"`, `"outlook": true`, tile type `forecast`.
- **Qualified refs** (`config.get_layout`):
  - `"<layout>:<id>"` resolves to the other layout's already-resolved entry, with this entry's keys shallow-merged over it.
  - Only one hop: the other layout's own entries may not be qualified.
  - A bad layout or id is a 404 `unknown ref` for that layout only.
  - Moving a tablet tile moves the Roku's too, which is intended.
- **`outlook`** (`weather.values`, opt-in per entry): the detail panel's compact next-3-days, `[{label, glyph, cond?, hi?, lo?, sub?}]`. It is computed from the daily forecast the tile already fetches, so there's no extra HA call.
- **Unchanged outputs.** The default `/api/config` and `/api/state` stay byte-identical (`test_roku_golden.py`), and the tablet's output is unchanged.

## Channel

**Requests**
- `ModulePollTask` asks for `?layout=roku` (`HK_LAYOUT()`).
- A sidecar without the layout answers 404. On the device that arrives as no body at all, because `GetToString` drops 4xx bodies, so a missing or `error` body means falling back to the default view (`event=layout_fallback`).
- If a layout state fetch fails later but the default view still answers, the layout has gone away, and MainScene re-fetches the config.

**Registry**
- The config is cached slimmed (`hkSlimConfig`) under `hubConfigRokuV1`.
- `hubConfigV2` is deleted on boot.

**Assets**
- `images/glass/`, from `scripts/gen_glass_assets.py`: the 9-patch fill, edge, rim and LED segment, plus chip, dot, glow and scrim. They are white, tinted at runtime: `blendColor` carries the RGB and `opacity` the alpha.
- `images/glyphs/{32,40,56}/`, from `scripts/gen_glyphs.py`: the tablet's MDI paths (plus `cctv`), rasterized with matplotlib. It also writes `source/Glyphs.brs`.
- `fonts/`: Barlow Medium and Semi Condensed SemiBold (OFL).

**Type** is the tablet's sizes × ~1.375, in px:

| Role | Size |
|---|---|
| clock | 56 |
| date | 28 |
| title, detail | 24 |
| hero | 64, stepping to 54 then 46 to fit |
| sub | 28 |
| door state | 36 |
| laundry status | 28, stepping to 24 then 20; then the label gives way |
| agenda title | 26 |
| forecast high | 32 |

**Components**
- **`HomeGroup`**
  - Header: clock and date left; `hkHeaderStatus` dot and word right, re-evaluated every 5 s.
  - Offline: content dims to 45% with a "No data since …" banner.
  - The whole wall shifts ±2 px every 10 min.
- **`ModuleTile`** is the glass shell: title, glyph chip, lit rim and glow, and fades of 600 ms in and 1,200 ms out.
- Bodies are picked by `hkCardKind`, which mirrors the tablet's `Project.kt`:
  - `ValueBody`
  - `DoorsBody`
  - `LaundryBody`, with the LED bar from `hkLedFrame`
  - `AgendaBody`
  - `ForecastBody`
  - The camera card is the shell alone.
- **Pure logic** sits in `Config.brs` as ports of the tablet's tested functions, and the tablet's test cases are ported into `tests/unit/test_pure.brs`:
  - `hkFreshness`, `hkHeaderStatus`, `hkBurnIn`
  - `hkCardKind`, `hkTileStale`, `hkDoorsShown`
  - `hkLedFrame`, `hkVisibleRowCount`, `hkDayLabel`
  - `hkAccentFor`, `hkItemAccent`, `hkHexToRoku`

**Tests**
- `tests/contract/layout_contract.py` checks the `?layout=roku` shape against the live sidecar, or against `tests/fixtures/{config,state}_roku.json`.
- A live sidecar without the layout is a WARN, not a FAIL.

## Not carried over

- The tablet's frost blur.
- Pulse rings on HA events.
- The hero slide animation.
- "as of" held values.
- The new-activity highlight.
- Night dim.
- The tap-to-open detail panels and photo peek, since the Roku is read-only.

## Rollout

1. Deploy the sidecar's `config.py` and `modules/weather.py`. Drift-check against nserver first, and confirm the default and `?layout=tablet` config md5s are unchanged.
2. Add `layouts.roku` to `/etc/haku/dashboard.json`.
3. Sideload 0.11 to the dev Roku, then the fleet, starting with the Express (`.52`), which has the least memory.

## Open follow-ups (2026-10-07, parked)

### Drone-photo backgrounds

The tablet shows the 42 drone photos from `/mnt/media/haku/kitchen`, its layout's `background.dir`. The wall Rokus still read the 6 local images in `HAKU_BG_DIR` (`/etc/haku/backgrounds`). This is deliberate for now: `layouts.roku` has no `background.dir`, and `BackgroundListTask` doesn't send `?layout=`. Three reasons:

- **The two-request limit.** The kitchen dir is a `hard` NFS mount that can hang a reader, so the sidecar lets at most two requests read a layout's `dir` at once (`_LAYOUT_BG_SLOTS`), and a third gets 503. Four Rokus plus the tablet would compete for those two slots.
- **The photo list is fetched once.** The Roku gets its list only at startup (`runBgList`), so a 503 there means no photos until the channel is relaunched.
- **The cache is too small.** The sidecar's resized-image cache (`backgrounds._CACHE_MAX = 32`) empties completely when full. 42 photos at the Roku's 1920×1080 plus the tablet's sizes would keep it churning, so most requests would go back to the NAS.

Options when we come back to it:

1. **Sync locally (preferred).** A systemd timer on nserver rsyncs the drone dir into `/etc/haku/backgrounds` every hour or so.
   - The Rokus read local disk: no NAS dependency and no slot contention.
   - No code change.
   - Pre-0.11 channels see the drone photos too.
   - Decide whether `bg_00_haku_logo.jpg` stays in the rotation.
2. **Point `layouts.roku` at the NAS dir.** Set `background.dir` to the kitchen dir and have the channel send `?layout=roku` to `/api/backgrounds`. This also needs:
   - the channel to retry the list after a 503 or empty answer;
   - `_CACHE_MAX` sized for 42 photos × every client size;
   - acceptance that a stalled mount takes photos off every wall.

### Camera feed in the 2×2 square

The square is an empty placeholder with no snapshot polling. Options:

1. **Live video in the square (preferred).** A `Video` node sized to the square, playing the mosaic or a single camera.
   - It would take over the keep-awake clip's decoder; Roku has one H.264 decoder. Live playback also keeps the screensaver away, so the keep-awake clip can go.
   - Stop it for HA live and grid takeovers, and resume it on home.
   - Check HLS lag (~10 s) and memory on the Express Rokus.
2. **Snapshots.** go2rtc `frame.jpeg` refreshed with each state poll, as the v0.10 camera tile did.

Open questions:
- Mosaic or a single camera in the square?
- On 2026-10-07 nserver answered 404 for the `front` and `backyard` HLS streams. The mosaic, `yard` and `side` were fine. That needs fixing on the stream side first.

### Retrying the layout after a fallback

After a `layout_fallback`, the channel stays on the default view until it is relaunched. It never asks for `?layout=roku` again. This showed up on 2026-10-07: the dev Roku booted before the sidecar had the layout. The fix is to retry the layout config every few minutes while `activeLayout` is "", in `ModulePollTask` or with a MainScene timer.
