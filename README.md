# homewall — HAku

A Home Assistant dashboard for the house's wall displays: Rokus around the house and a Fire 7 tablet in the kitchen. A small server on nserver (the **sidecar**) reads Home Assistant and serves ready-formatted cards; each display lays them out and draws them. Camera streams for the Rokus come from a separate go2rtc/HLS pipeline on the same host.

Baseline: `tools/baseline.sh [seconds]` measures the live system and prints a Markdown report; dated runs live in `docs/baseline/`.

Remote: private GitHub `jimidarke/homewall`. nserver holds a read-only clone at `/opt/haku/homewall` (deploy key `nserver-haku-deploy`); v2's deploy script will run from it.

```
Home Assistant (mserver) ──► sidecar :1986 (nserver) ──► roku/         (Roku channel)
                                                    └──► fire-tablet/  (Android app)
NVR / cameras ──► stream/ go2rtc + HLS + discovery (nserver) ──► roku/
```

| Folder | Contents | Start with |
|---|---|---|
| [`roku/`](roku/) | Roku channel (BrightScript) | [`roku/CLAUDE.md`](roku/CLAUDE.md) |
| [`fire-tablet/`](fire-tablet/) | Kitchen tablet app (Kotlin/Compose) | [`fire-tablet/README.md`](fire-tablet/README.md) |
| [`sidecar/`](sidecar/) | HA aggregator + card renderer (Python/Flask) | [`sidecar/README.md`](sidecar/README.md) |
| [`stream/`](stream/) | Camera stream units and config | [`stream/README.md`](stream/README.md) |
| [`docs/`](docs/) | System design, tablet design, specs and plans, brand art | [`docs/HAKU_DESIGN.md`](docs/HAKU_DESIGN.md) |

Release 1.0.0 (git tag `v1.0.0`) set every part to 1.0.0; they version independently from there. Each part's version lives in `roku/VERSION.txt` (with `roku/manifest` and `roku/package.json`), `fire-tablet/app/build.gradle.kts`, `sidecar/haku_sidecar/__init__.py` and `stream/haku-discovery.py` (`SERVICE_VERSION`). The devices run whatever was last deployed to them, so a display can lag the repo.
