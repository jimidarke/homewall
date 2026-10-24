# CLAUDE.md — sidecar/

`haku-sidecar`: Python/Flask on `:1986`, deployed on nserver (192.0.2.20). It polls HA's `/api/states` (every second on nserver) with the long-lived token of the HA administrator user `haku` (rotation: `../ha/README.md` § Rotate) and serves the module→entity config, per-module value JSON, the tablet's detail panels, backgrounds and PNG cards. The HA binding lives in `/etc/haku/dashboard.json`, so another HA install is a config edit, not a code change. API, HA polling and caching, config and tile keys, layouts, backgrounds and env vars: `README.md`.

**Two clients read it**: the wall Rokus (`?layout=roku`, `../roku/`) and the kitchen tablet (`?layout=tablet`, `../fire-tablet/`). Any JSON change must keep both working. Without `?layout=` it serves the default view (top-level `modules`, for Roku channels before 0.11). No live display reads it, but `tests/test_roku_golden.py` pins it byte for byte, so change it only on purpose.

## Commands

```bash
cd sidecar
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest   # once
.venv/bin/python -m pytest tests -q                                         # no HA/network needed (FakeHA fixtures)
HAKU_UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/test_roku_golden.py   # only for an intended default-view change
```

Use the venv: system matplotlib is ABI-broken. Locally, point `HAKU_CONFIG` at `dashboard.json.example`. On nserver the config is `/etc/haku/dashboard.json` (mtime hot-reloaded, no restart) and the env is `/etc/haku/haku.env` (holds the token: never print it).

## Rules

- **`ref` merges are shallow.** A layout entry's `tile` or `entities` replaces the whole object, so the tablet's `ref` entries repeat `entities` in full and the Roku layout's `tablet:` refs each carry their own `tile`.
- **Contract changes.** When sidecar output changes, re-capture the tablet fixtures (`../fire-tablet/app/src/test/resources/{config,state}.json`, steps in `../fire-tablet/README.md`). When the `discovery.json` shape changes, bump `SCHEMA_VERSION` in `../stream/haku-discovery.py`, `EXPECTED_SCHEMA_VERSION` in `../roku/tests/contract/discovery_contract.py` and the `HK_REG_KEY_DISCOVERY()` key name in `../roku/source/Config.brs` together. For a config shape change the Roku can't read from its cache, bump the `hubConfigRokuV1` key name (`HK_REG_KEY_CONFIG()`).

## Deploy

Manual per-file copy to `/opt/haku/sidecar` on nserver (runs as `media`, own venv), then `systemctl restart haku-sidecar`. **The deployed code can drift ahead of the repo**, so before a deploy `md5sum` each file you'll touch against the repo, back up under `/opt/haku/`, copy with `ssh nserver "cat > path" < file` (keeps owner and mode), `py_compile` on the server, then restart. Never copy the whole directory. `charts.py` draws the Roku's `weather_chart` in Barlow from `haku_sidecar/assets/barlow_*.ttf`, so those go up with it (without them it falls back to matplotlib's default face). The background mirror is `haku-bg-sync.sh` at `/opt/haku/haku-bg-sync.sh` plus `haku-bg-sync.{service,timer}` in `/etc/systemd/system/`.
