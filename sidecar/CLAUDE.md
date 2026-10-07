# CLAUDE.md — sidecar/

`haku-sidecar`: Python/Flask on `:1986`, deployed on nserver (192.0.2.20). It holds HA state (REST poller + the `rokuapp` long-lived token), serves a portable module→entity config, per-module value JSON, and matplotlib/Pillow-rendered PNG cards. This is what makes HAku portable to other HA installs (edit `/etc/haku/dashboard.json`, no code change). API, config and tile keys: `README.md`.

**Two clients read it** — the Roku channel (`../roku/`) and the Fire tablet (`../fire-tablet/`). Any JSON change must keep both working.

## Commands

```bash
cd sidecar
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest   # once
.venv/bin/python -m pytest tests -q                                         # no HA/network needed (FakeHA fixtures)
HAKU_UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/test_roku_golden.py   # only when a Roku-visible change is intended
```

Use the venv: system matplotlib is ABI-broken. Runtime config is `/etc/haku/dashboard.json` (module→entity map, mtime hot-reloaded) + `/etc/haku/haku.env` (`HAKU_HA_TOKEN`). Locally, point `HAKU_CONFIG` at `dashboard.json.example`.

## Layouts (`?layout=`)

In `dashboard.json`, the top-level `modules` list is the default view (Roku channels before 0.11). An optional `layouts` map gives each display (`tablet`, and `roku` for the 0.11+ wall Rokus) its own `grid`, `nightDim`, `background` and module list, whose entries either `ref` a top-level module (shallow-merging their own keys over it), `ref` another layout's entry with a qualified `"<layout>:<id>"` (one hop only; `layouts.roku` is built from `tablet:` refs), or define a layout-only module, such as the tablet's `doors` and `laundry` kinds. `GET /api/detail/<id>?layout=tablet` serves the tablet's detail panels; the Roku never calls it. Every route except `/api/health` takes `?layout=<name>`: config, state, module, detail, card and icon then serve that layout's modules, and backgrounds and background read its `background.dir`, which is never serialized. At most two requests read a layout's `dir` at once (it is a `hard` NAS mount that can hang); a third gets a 503. `/api/background/<name>` also takes `fit=contain|cover` and `blur=0–40`.

Without `?layout=` the default view is unchanged, and `/api/config` never contains `layouts` (the Roku's registry cache holds about 16 KB). Layout work adds only tile keys to the default responses (`glyph`, `active`, `level` and timeline `items[].glyph`), which pre-0.11 channels ignore. The weather `outlook` (the Roku's forecast strip) is opt-in per layout entry. The rate tile style (`"tileStyle": "rate"`) is opt-in per layout. A placeholder hero (`--…`) always comes with `stale: true`, which the Roku never reads. `tests/test_layouts.py` and `tests/test_roku_golden.py` (byte-identical default `/api/config` and `/api/state` against `tests/golden/roku_{config,state}.json`) guard the default output.

**Contract changes:** when sidecar output changes, re-capture the tablet fixtures (`../fire-tablet/app/src/test/resources/{config,state}.json`, steps in `../fire-tablet/README.md`). When the discovery or config shape changes, bump `schemaVersion` in `../stream/haku-discovery.py` + the Roku contract test + `HK_REG_CACHE_VER` together.

## Deploy

Manual per-file copy to `/opt/haku/sidecar` on nserver (runs as `media`, own venv), then `systemctl restart haku-sidecar`. **The deployed code can drift ahead of the repo**, so before a deploy `md5sum` each file you'll touch against the repo, back up under `/opt/haku/`, copy with `ssh nserver "cat > path" < file` (keeps owner and mode), `py_compile` on the server, then restart. Never copy the whole directory.
