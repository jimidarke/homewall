# CLAUDE.md

**HAku** ("Home Assistant" + "Roku") is the home wall: wall-mounted displays showing a modular, config-driven Home Assistant dashboard (glance cards + camera wall). This monorepo holds every part of it. Each folder has its own `CLAUDE.md`; read the one for the part you're touching.

| Folder | What | Runs on |
|---|---|---|
| `roku/` | Roku channel (BrightScript + SceneGraph, `haku.zip`) | 4 fleet Rokus + dev Roku |
| `fire-tablet/` | Android app `io.haku.tablet` (Kotlin/Compose) | Kitchen wall Fire 7 (`192.0.2.60`) |
| `sidecar/` | `haku-sidecar`, Python/Flask `:1986`: HA state → config/state JSON + PNG cards | nserver (`192.0.2.20`) |
| `stream/` | go2rtc + ffmpeg HLS + SSDP discovery (`:1985`) systemd units | nserver |
| `ha/` | Home Assistant packages HAku depends on (byte-for-byte copies of mserver's `packages/`), deploy notes in `ha/README.md` | mserver (`192.0.2.10`) |
| `docs/` | `HAKU_DESIGN.md` (system design), `fire-tablet/DESIGN.md` (tablet design), `superpowers/` specs and plans, `brand/` source art | — |

Home Assistant is on mserver (`192.0.2.10`). The sidecar pulls from it; HA pushes urgent events straight to the Rokus over ECP.

## Cross-cutting rules

- **The sidecar has two clients.** Any change to its JSON must keep the Roku (`sidecar/tests/test_roku_golden.py` guards its default output byte for byte) and the tablet (its fixture tests in `fire-tablet/app/src/test/resources/`) working.
- **Deployed code can drift ahead of the repo.** nserver gets manual per-file copies. Before deploying, diff what's on the server against the repo for every file you'll touch (`sidecar/CLAUDE.md` § Deploy).
- **Secrets never land in the repo**: `/etc/haku/haku.env` (HA token) and `/etc/haku/cam-creds.env` (camera creds) live on nserver only, and `/etc/haku/dashboard.json` is the live config (`sidecar/dashboard.json.example` is the template).
- **Versions:** each part carries its own version; all were 1.0.0 at the `v1.0.0` tag. Where each lives: `README.md`.
- Docs under `docs/superpowers/` are historical records of finished work and keep the paths they were written with (see its `README.md`).
- Machine-local setup per part: `sidecar/.venv` (see `sidecar/CLAUDE.md`), `roku/node_modules` (`npm ci`), `fire-tablet/local.properties`. None are committed.

## Commands

```bash
cd roku && npm ci && npm test                                                 # lint + unit + contract
cd sidecar && .venv/bin/python -m pytest tests -q                             # venv setup: sidecar/CLAUDE.md
cd fire-tablet && ./gradlew testDebugUnitTest assembleDebug assembleRelease --offline
```

`fire-tablet/local.properties` is gitignored and must hold `sdk.dir=~/Android/Sdk`.
