# homewall — HAku

A Home Assistant dashboard for the house's wall displays: Rokus around the house and a Fire 7 tablet in the kitchen. A small server on nserver (the **sidecar**) reads Home Assistant and serves ready-formatted cards; each display lays them out and draws them. Camera streams for the Rokus come from a separate go2rtc/HLS pipeline on the same host.

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

Versions: Roku channel 0.10.0 (`roku/VERSION.txt`), tablet 0.3.0 (`fire-tablet/app/build.gradle.kts`).

This repo was created on 2026-10-03 by merging `roku-homewall` (at `7b6b9ef`) and `tablet-homewall` (at `0ea7f43`) without their history, plus drift found on nserver: the deployed `sidecar/haku_sidecar/modules/timeline.py` and the `haku-hls.service` runtime-dir drop-in.
