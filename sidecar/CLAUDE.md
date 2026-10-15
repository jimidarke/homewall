# CLAUDE.md — sidecar/

`haku-sidecar`: Python/Flask on `:1986`, deployed on nserver (192.0.2.20). It holds HA state (REST poller + the `rokuapp` long-lived token), serves a portable module→entity config, per-module value JSON, and matplotlib/Pillow-rendered PNG cards. This is what makes HAku portable to other HA installs (edit `/etc/haku/dashboard.json`, no code change). API, config and tile keys: `README.md`.

**Two clients read it** — the Roku channel (`../roku/`) and the tablet (`../fire-tablet/`). Any JSON change must keep both working.

## Commands

```bash
cd sidecar
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest   # once
.venv/bin/python -m pytest tests -q                                         # no HA/network needed (FakeHA fixtures)
HAKU_UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/test_roku_golden.py   # only when a Roku-visible change is intended
```

Use the venv: system matplotlib is ABI-broken. Runtime config is `/etc/haku/dashboard.json` (module→entity map, mtime hot-reloaded) + `/etc/haku/haku.env` (`HAKU_HA_TOKEN`, and `HAKU_POLL_INTERVAL=1`: HA's `/api/states` is polled every second, on a fixed cadence; measured 2026-10-14 at ~3% of one core with every client at 1 s). A failed on-demand HA read (logbook, calendar, forecast, history) is retried after 15 s, not on every request. The poller also records off→on edges (`HAClient.last_on`), which the doors module's camera `takeover` reads. Locally, point `HAKU_CONFIG` at `dashboard.json.example`.

## Layouts (`?layout=`)

In `dashboard.json`, the top-level `modules` list is the default view (Roku channels before 0.11). An optional `layouts` map gives each display (`tablet`, and `roku` for the 0.11+ wall Rokus) its own `grid`, `nightDim`, `background` and module list, whose entries either `ref` a top-level module (shallow-merging their own keys over it), `ref` another layout's entry with a qualified `"<layout>:<id>"` (one hop only; `layouts.roku` is built from `tablet:` refs, each with its own `tile`, since the merge is shallow), or define a layout-only module, such as the tablet's `doors` and `laundry` kinds. `GET /api/detail/<id>?layout=tablet` serves the tablet's detail panels; the Roku never calls it. Every route except `/api/health` takes `?layout=<name>`: config, state, module, detail, card and icon then serve that layout's modules, and backgrounds and background read its `background.dir`, which is never serialized. At most two requests read a layout's `dir` at once (it can be a `hard` NAS mount that hangs); a third gets a 503. No live layout sets a `dir`: every display reads `HAKU_BG_DIR`, which `haku-bg-sync.timer` mirrors from the NAS photo folder every 15 min (`haku-bg-sync.sh`, which skips a run when the NAS is unmounted or empty rather than wiping the copy). `/api/background/<name>` also takes `fit=contain|cover` and `blur=0–40`; renders are cached in an LRU sized for the whole photo set at every client size.

Without `?layout=` the sidecar serves the default view (pre-0.11 channels), and `/api/config` never contains `layouts` (those channels' registry cache holds about 16 KB). The default responses carry the layout clients' extra tile keys too (`glyph`, `active`, `level`, `stale` and timeline `items[].glyph`), which pre-0.11 channels ignore. The weather `outlook` (the Roku's forecast strip) is opt-in per layout entry; the Forecast card's chart is the `weather_chart` PNG card (`tile.card`), drawn by `charts.render_temp_chart` from the same `_chart_block` the tablet's weather panel serves. The rate tile style (`"tileStyle": "rate"`) is opt-in per layout (the Roku layout inherits the tablet's through `tablet:` refs). A placeholder hero (`--…`) always comes with `stale: true`, which the tablet and the wall Rokus read. `tests/test_layouts.py` and `tests/test_roku_golden.py` (byte-identical default `/api/config` and `/api/state` against `tests/golden/roku_{config,state}.json`) guard the default output.

**Contract changes:** when sidecar output changes, re-capture the tablet fixtures (`../fire-tablet/app/src/test/resources/{config,state}.json`, steps in `../fire-tablet/README.md`). When the `discovery.json` shape changes, bump `schemaVersion` in `../stream/haku-discovery.py`, `EXPECTED_SCHEMA_VERSION` in `../roku/tests/contract/discovery_contract.py` and the `HK_REG_KEY_DISCOVERY()` key name in `../roku/source/Config.brs` together. For a config shape change the Roku can't read from its cache, bump the `hubConfigRokuV1` key name (`HK_REG_KEY_CONFIG()`).

## Deploy

Manual per-file copy to `/opt/haku/sidecar` on nserver (runs as `media`, own venv), then `systemctl restart haku-sidecar`. **The deployed code can drift ahead of the repo**, so before a deploy `md5sum` each file you'll touch against the repo, back up under `/opt/haku/`, copy with `ssh nserver "cat > path" < file` (keeps owner and mode), `py_compile` on the server, then restart. Never copy the whole directory. `charts.py` draws the Roku's `weather_chart` in Barlow from `haku_sidecar/assets/barlow_*.ttf`, so those go up with it (without them it falls back to matplotlib's default face). The background mirror is `haku-bg-sync.sh` at `/opt/haku/haku-bg-sync.sh` plus `haku-bg-sync.{service,timer}` in `/etc/systemd/system/`.
