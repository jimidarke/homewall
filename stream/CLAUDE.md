# CLAUDE.md — stream/

The camera pipeline on nserver (192.0.2.20) that feeds the Rokus, in three stages:

1. **`go2rtc`** (`:1984`, config `go2rtc.yaml`): the NVR's HDMI-out mosaic (USB capture, Intel QSV encode) plus 5 camera streams. `yard`/`side`/`backyard` are forwarded as-is; the Genbolt's two HEVC lenses are QSV-transcoded to H.264: `front` (PTZ, `/21`) and `front_steps` (fixed lens on the steps, `/11`, which the Rokus' home square switches to on front motion).
2. **`haku-hls.service`** (mosaic) and **`haku-hls@<cam>`** (per camera): ffmpeg remux into a 3 × 2 s HLS window in tmpfs `/run/haku-hls`, ~5 s behind live on the Rokus.
3. **`haku-discovery.py`** (`:1985`): SSDP responder, `discovery.json`, HLS file server.

Streams, endpoints, encode settings, the latency measurements and the deploy script: `README.md`.

Boot order: `go2rtc` → `haku-hls*` (`After=`/`Requires=go2rtc`) → `haku-discovery` (`After=go2rtc haku-hls`, `PartOf=go2rtc`). All run as `media`.

## Rules

- **Deploy is a manual copy** (`README.md` § Deploy). Diff each deployed file against the repo first: nserver has drifted before.
- **Never commit camera creds.** `go2rtc.yaml` reads `${HAKU_CAM_USER}`/`${HAKU_CAM_PASSWORD}` and the Genbolt's `${HAKU_FRONT_USER}`/`${HAKU_FRONT_PASSWORD}` from `/etc/haku/cam-creds.env` (0640 `root:media`, nserver only).
- **Discovery is a contract with the Roku channel.** If the `discovery.json` shape changes, bump together: `SCHEMA_VERSION` in `haku-discovery.py` (currently 2), `EXPECTED_SCHEMA_VERSION` in `../roku/tests/contract/discovery_contract.py`, and the `HK_REG_KEY_DISCOVERY()` key name in `../roku/source/Config.brs` (the key name is what stops the Roku reading back an old cache).
- **Rokus need H.264.** The Express and Stick can't decode HEVC, so any HEVC camera gets a QSV transcode like `front`.
- `haku-hls.service` and `haku-hls@.service` share `RuntimeDirectory=haku-hls`; both must keep `RuntimeDirectoryPreserve=yes`, or one unit stopping deletes every camera's segments.
- **The HLS window is the Roku's latency** (it plays from the oldest listed segment). Keep 2 s segments: 1 s ones broke the Kids Express (`README.md` § "HLS window and latency").
- Restarting `go2rtc` restarts every stream and can leave Rokus on "Camera offline" for their 5-minute rest; restarting one `haku-hls@<cam>` costs a few seconds.
- QSV on nserver's Ice Lake GPU under Ubuntu 24.04 needs `libmfx1` (not `libmfx-gen1.2`), installed by hand, not by the deploy script.
