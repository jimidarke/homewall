# CLAUDE.md — stream/

The camera pipeline on nserver (192.0.2.20) that feeds the Rokus: go2rtc (`:1984`, NVR HDMI-out mosaic via USB capture + Intel QSV, plus 4 per-camera streams: `yard`/`side`/`backyard` direct RTSP, `front` (Genbolt PTZ) transcoded HEVC→H.264 via QSV) → ffmpeg remux to deep 12 s HLS (`haku-hls.service` for the mosaic, `haku-hls@<cam>` per camera, into tmpfs `/run/haku-hls`) → `haku-discovery.py` (`:1985`: SSDP responder, `discovery.json`, HLS file server). Endpoints, encode settings and the full deploy script: `README.md`.

Boot order: `go2rtc` → `haku-hls*` (`After=`/`Requires=go2rtc`) → `haku-discovery` (`After=go2rtc haku-hls`, `PartOf=go2rtc`). Units run as `media`.

## Rules

- **Deploy is a manual copy** (`README.md` § Deploy: `scp stream/<file>` from the repo root, then install on nserver). Diff the deployed file against the repo first: nserver has drifted before.
- **Never commit camera creds.** `go2rtc.yaml` references `${HAKU_CAM_USER}`/`${HAKU_CAM_PASSWORD}` (and `${HAKU_FRONT_USER}`/`${HAKU_FRONT_PASSWORD}` for the Genbolt) from `/etc/haku/cam-creds.env` (0640 `root:media`, nserver only).
- **Discovery is a contract with the Roku channel.** If the `discovery.json` shape changes, bump `schemaVersion` in `haku-discovery.py` (currently 2), `EXPECTED_SCHEMA_VERSION` in `../roku/tests/contract/discovery_contract.py`, and the `HK_REG_KEY_DISCOVERY()` key name in `../roku/source/Config.brs` together (the key name is what stops the Roku reading back an old cache).
- `haku-hls.service` and `haku-hls@.service` share `RuntimeDirectory=haku-hls`; both must keep `RuntimeDirectoryPreserve=yes`, or one unit stopping deletes every camera's segments. nserver's deployed `haku-hls.service` predates that line and gets it from the older drop-in `/etc/systemd/system/haku-hls.service.d/10-preserve-runtime-dir.conf` instead; remove the drop-in when the repo unit is next deployed.
- nserver needs `libmfx1` (not `libmfx-gen1.2`) for QSV on its Ice Lake GPU under Ubuntu 24.04; it's installed by hand, not by the deploy script.
