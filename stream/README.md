# HAku — Stream Pipeline (nserver)

Three services on nserver (`192.0.2.20`) turn the NVR's HDMI-out (via a USB capture device) and five camera feeds into H.264 streams the Rokus can play, and advertise them over SSDP so no consumer hardcodes an IP:

- **`go2rtc`** encodes the NVR mosaic and serves every stream as RTSP / HLS / WebRTC / MJPEG / JPEG.
- **`haku-hls`** (mosaic) and **`haku-hls@<cam>`** (one per camera) remux go2rtc's RTSP into a deeper HLS window on tmpfs, because go2rtc's own HLS underflows the Roku.
- **`haku-discovery`** answers SSDP, serves `discovery.json`, and serves the HLS files on `:1985`.

```
[USB HDMI capture (NVR 4-up)] ─┐
[5 camera RTSP feeds]  ────────┴─→ go2rtc.service ──┬─→ RTSP   :8554/<name>
                                                    ├─→ HLS    :1984/api/stream.m3u8   (shallow: browsers, debugging)
                                                    ├─→ WebRTC :8555
                                                    ├─→ MJPEG  :1984/api/stream.mjpeg
                                                    ├─→ JPEG   :1984/api/frame.jpeg
                                                    └─→ RTSP feeds haku-hls.service + haku-hls@<cam>.service
                                                                     │
                                                                     ▼
                                                        ffmpeg remux (no re-encode) →
                                                        /run/haku-hls/<name>.m3u8 + .ts
                                                        (3 × 2 s window, ~5 s behind live)
                                                                     │
                                                                     ▼
                                          haku-discovery.service ── HTTP :1985
                                            ├─ /discovery.json  (versioned capability JSON)
                                            ├─ /hls/<name>.m3u8 + segments
                                            └─ SSDP responder UDP :1900
                                                                     │
                                          Roku: SSDP M-SEARCH → fetch discovery.json
                                                → play streams.<cam>.hls (hardware H.264 decode)
```

## Files in this directory

| File | Deploys to (on nserver) | Purpose |
|---|---|---|
| `go2rtc.yaml` | `/etc/go2rtc/go2rtc.yaml` | Stream config: UVC mosaic encoded by Intel QSV, plus 4 live camera streams (`backyard` disabled 2026-10-24, camera offline) (`yard`/`side`/`backyard` forwarded as-is; the Genbolt's `front` and `front_steps` lenses QSV-transcoded HEVC → H.264) |
| `go2rtc.service` | `/etc/systemd/system/go2rtc.service` | go2rtc unit; runs as `media`, loads the cred env file |
| `haku-hls.service` | `/etc/systemd/system/haku-hls.service` | ffmpeg remux of the mosaic RTSP into HLS |
| `haku-hls@.service` | `/etc/systemd/system/haku-hls@.service` | Templated ffmpeg remux, one instance per camera (`@front`, `@front_steps`, `@yard`, `@side`, `@backyard`) |
| `haku-discovery.py` | `/opt/stream/haku-discovery.py` | SSDP responder + capability JSON + HLS file server (stdlib-only Python) |
| `haku-discovery.service` | `/etc/systemd/system/haku-discovery.service` | Discovery unit |

The go2rtc binary is `/usr/local/bin/go2rtc`, a static x86_64 build from the GitHub releases (1.9.14 on nserver). QSV on nserver's Ice Lake GPU under Ubuntu 24.04 needs `libmfx1` (not `libmfx-gen1.2`), installed by hand.

### Camera credentials and addresses (never committed)

`go2rtc.service` loads `/etc/haku/cam-creds.env` (mode `0640`, `root:media`) with `EnvironmentFile=`, and `go2rtc.yaml` references the values as `${VAR}`, so the yaml stays committable:

```
HAKU_CAM_USER=<shared camera login>
HAKU_CAM_PASSWORD=<from HA Reolink integration / password manager>
HAKU_FRONT_USER=<the Genbolt's login: HA secrets.yaml genbolt_ptz_stream>
HAKU_FRONT_PASSWORD=<...>
HAKU_CAM_FRONT_HOST=<front camera LAN address>
HAKU_CAM_YARD_HOST=<...>
HAKU_CAM_SIDE_HOST=<...>
HAKU_CAM_BACKYARD_HOST=<...>
```

`haku-discovery` detects the address it advertises; to pin it, put `HAKU_DISCOVERY_HOST` / `HAKU_DISCOVERY_BIND_IP` in the optional `/etc/haku/discovery.env`.

To add a key, append to the live file.

Addresses below are `192.0.2.0/24` documentation placeholders (nserver is `192.0.2.20`); the real ones are in `/etc/haku/cam-creds.env` and the gitignored `PRIVATE.md`.

## Streams

go2rtc publishes one stream per source. `discovery.json` lists whatever go2rtc reports (six today), with static metadata from `STREAM_METADATA` in `haku-discovery.py`.

| Stream | Source | Roku-facing codec | Roku HLS |
|---|---|---|---|
| `mosaic` | NVR HDMI → USB capture → QSV H.264 | H.264 Main 4.0, 1920×1080 @ 20 fps | `:1985/hls/mosaic.m3u8` |
| `front` | Genbolt `192.0.2.31` PTZ lens `/21` (HEVC 1080p15) → QSV transcode | H.264 Main 3.2, 1280×720 @ 15 fps | `:1985/hls/front.m3u8` |
| `front_steps` | Genbolt `192.0.2.31` fixed lens `/11` on the front steps (HEVC 1080p15) → QSV transcode | H.264 Main 3.2, 1280×720 @ 15 fps | `:1985/hls/front_steps.m3u8` |
| `yard` | Reolink `192.0.2.32` sub-stream (main is HEVC 4K) | H.264 High 5.1, 640×360 @ 10 fps | `:1985/hls/yard.m3u8` |
| `side` | Amcrest `192.0.2.33` | H.264 High 4.1, 1920×1080 @ 30 fps | `:1985/hls/side.m3u8` |
| `backyard` _(disabled 2026-10-24: camera `.34` offline; re-enable steps in `docs/HAKU_DESIGN.md` § Open items)_ | Reolink-family `192.0.2.34` main stream | H.264 Main 5.0, 2048×1536 @ 20 fps | `:1985/hls/backyard.m3u8` |

The Rokus' home square plays `front`, and switches to `front_steps` on HA's `homeCam=front_steps` push (front motion); `haku-hls@front_steps` keeps that stream warm so the switch never waits for a cold start. The Genbolt has its own login (`HAKU_FRONT_*`). The two transcodes run GOP 30 (2 s at 15 fps) at ~2 Mbps; the Express and Stick Rokus can't decode HEVC.

### Other endpoints

`<name>` is any stream above. All bind `enp1s0` (`192.0.2.20`).

| Endpoint | URL | Use |
|---|---|---|
| SSDP discovery | multicast `239.255.255.250:1900`, ST `urn:haku:service:dashboard:1` | Roku auto-discovery |
| Discovery JSON | `http://192.0.2.20:1985/discovery.json` | `schemaVersion` 2: every stream's HLS/RTSP/MJPEG/snapshot URLs + metadata, and the sidecar base (`:1986`) |
| RTSP | `rtsp://192.0.2.20:8554/<name>` | VLC, ffmpeg, HA `generic`/`stream`, NVRs |
| HLS (shallow) | `http://192.0.2.20:1984/api/stream.m3u8?src=<name>` | Browsers, debugging (~1 s buffer; the Roku underflows on it) |
| MJPEG | `http://192.0.2.20:1984/api/stream.mjpeg?src=<name>` | HA legacy compat |
| WebRTC | `http://192.0.2.20:1984/stream.html?src=<name>` | Sub-second browser viewing |
| JPEG snapshot | `http://192.0.2.20:1984/api/frame.jpeg?src=<name>` | Roku PIP overlay, thumbnails |
| Status UI | `http://192.0.2.20:1984/` | go2rtc pipeline status, consumers, bandwidth |

### HLS window and latency

The remux units write into the shared tmpfs `/run/haku-hls/`: the mosaic as `mosaic.m3u8` + `seg_NNNNN.ts`, each camera as `<cam>.m3u8` + `<cam>_seg_NNNNN.ts`. Both units set `RuntimeDirectoryPreserve=yes`; without it, one unit stopping deletes every camera's segments.

**Latency.** A Roku plays from the oldest segment in the playlist, so the window is the delay. The units list 3 segments of 2 s (`-hls_list_size 3`, `-hls_time 2`) and keep 4 more on disk after they leave the playlist (`-hls_delete_threshold 4`) for a Roku that slips behind. Segments cut only on keyframes, so `yard`'s ~4 s camera GOP gives ~4 s segments. Measured 2026-10-14: `front`, `side` and `mosaic` play ~5 s behind live, `yard` ~11 s; the camera-to-nserver leg is under 1 s. A 6 × 2 s window was ~12 s. 3 × 1 s segments (`front` at GOP 15) gained only ~1 s and made the Kids Express restart its player and drift ~30 s behind, so segments stay at 2 s.

## Mosaic encode parameters (`go2rtc.yaml`)

| Parameter | Value | Why |
|---|---|---|
| Resolution | 1920×1080 | Native HDMI EDID; keeps per-quadrant detail of the 4-up mosaic |
| Framerate | 20 fps | What the capture device negotiates with the NVR; it ignores a lower `-framerate` |
| Codec | H.264 **Main, level 4.0**, `yuv420p` | Universal Roku + browser hardware decode |
| GOP | 40 frames (2 s @ 20 fps) | One keyframe per HLS segment |
| B-frames | 0 | Lowest decoder latency |
| Bitrate | 2.5 Mbps CBR (3.0 Mbps cap) | Fits four quadrants of motion |
| Encoder | `h264_qsv` (Intel Quick Sync, Iris Plus G1) | ~1–2% iGPU at 1080p |
| Audio | none | NVR HDMI carries none |

Per consumer this is ~2.5 Mbps, against ~78.7 Mbps for the legacy MJPEG passthrough it replaced.

## Deploy

Deploy is a manual copy. Diff each deployed file against the repo first (`md5sum`); nserver has drifted before.

```bash
# from the repo root, with SSH to nserver
scp stream/go2rtc.yaml stream/go2rtc.service stream/haku-hls.service stream/haku-hls@.service \
    stream/haku-discovery.py stream/haku-discovery.service root@nserver:/tmp/

ssh root@nserver bash -se <<'EOF'
set -euo pipefail

# 1. go2rtc binary (first install only)
if [ ! -x /usr/local/bin/go2rtc ]; then
  curl -fsSL https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_linux_amd64 \
    -o /usr/local/bin/go2rtc
  chmod +x /usr/local/bin/go2rtc
fi

# 2. media user needs the capture + GPU groups
usermod -aG video,render media

# 3. Camera creds (first install only: never overwrite the live file).
#    Fill in the values from HA / 1Password afterwards.
mkdir -p /etc/haku
if [ ! -e /etc/haku/cam-creds.env ]; then
  install -m 0640 -o root -g media /dev/stdin /etc/haku/cam-creds.env <<'CREDS'
HAKU_CAM_USER=<set me>
HAKU_CAM_PASSWORD=<set me>
HAKU_FRONT_USER=<set me>
HAKU_FRONT_PASSWORD=<set me>
HAKU_CAM_FRONT_HOST=<set me>
HAKU_CAM_YARD_HOST=<set me>
HAKU_CAM_SIDE_HOST=<set me>
HAKU_CAM_BACKYARD_HOST=<set me>
CREDS
fi

# 4. Configs and units
mkdir -p /etc/go2rtc /opt/stream
install -m 0644 /tmp/go2rtc.yaml             /etc/go2rtc/go2rtc.yaml
install -m 0644 /tmp/go2rtc.service          /etc/systemd/system/go2rtc.service
install -m 0644 /tmp/haku-hls.service        /etc/systemd/system/haku-hls.service
install -m 0644 /tmp/haku-hls@.service       /etc/systemd/system/haku-hls@.service
install -m 0755 /tmp/haku-discovery.py       /opt/stream/haku-discovery.py
install -m 0644 /tmp/haku-discovery.service  /etc/systemd/system/haku-discovery.service
chown -R media:media /opt/stream

# 5. Legacy mjpg_streamer off (go2rtc.service also Conflicts= it)
systemctl stop sendHDMI.service || true
systemctl disable sendHDMI.service || true

# 6. Bring up the pipeline: mosaic + one HLS remux per camera
systemctl daemon-reload
systemctl enable --now go2rtc.service haku-hls.service haku-discovery.service
systemctl enable --now haku-hls@front.service haku-hls@front_steps.service haku-hls@yard.service \
                       haku-hls@side.service

# 7. Smoke test
sleep 5
systemctl --no-pager status go2rtc.service haku-hls.service haku-discovery.service | head -40
ffprobe -v error -rtsp_transport tcp -show_streams \
  rtsp://127.0.0.1:8554/mosaic | grep -E "codec_name|profile|width|height|pix_fmt|level|r_frame_rate"
curl -sI http://192.0.2.20:1985/hls/mosaic.m3u8      # discovery binds the LAN IP, not loopback
curl -s  http://192.0.2.20:1985/discovery.json | head -40
EOF
```

To change one file, copy just that file and restart only what uses it. Restarting `go2rtc` restarts every stream and can leave Rokus on "Camera offline" for their 5-minute rest; restarting one `haku-hls@<cam>` costs a few seconds. `haku-discovery` re-reads go2rtc's stream list every 60 s, so a new stream in `go2rtc.yaml` reaches `discovery.json` without restarting it.

## Verification

```bash
# Services alive
ssh root@nserver 'systemctl --no-pager status go2rtc haku-hls haku-discovery "haku-hls@*" | head -60'

# Codec check (mosaic: expect Main, level 40, 1920x1080, yuv420p, 20/1)
ssh root@nserver 'ffprobe -v error -rtsp_transport tcp -show_streams \
  rtsp://127.0.0.1:8554/mosaic | grep -E "codec_name|profile|width|height|pix_fmt|level|r_frame_rate"'

# QSV engagement (if intel-gpu-tools is installed)
ssh root@nserver 'intel_gpu_top -s 1000 | head -20'

# SSDP discovery from another LAN host (gssdp-discover is in gupnp-tools)
gssdp-discover -t urn:haku:service:dashboard:1 --timeout=3
```

## Rollback to mjpg_streamer

The legacy `sendHDMI.service` unit (mjpg_streamer on `:8090`) is left installed, disabled, so rollback is a `systemctl` flip:

```bash
ssh root@nserver
systemctl stop go2rtc.service haku-hls.service haku-discovery.service 'haku-hls@*.service'
systemctl disable go2rtc.service haku-hls.service haku-discovery.service \
  haku-hls@front.service haku-hls@front_steps.service haku-hls@yard.service haku-hls@side.service
systemctl enable --now sendHDMI.service
# HA's camera.camerafeed picks the old MJPEG up again.
```
