# HAku — Stream Pipeline (nserver)

Replaces the legacy `sendHDMI.service` (mjpg_streamer at `:8090`) with a
three-process pipeline producing simultaneous RTSP / HLS / WebRTC / MJPEG /
JPEG outputs from a single USB capture device, plus SSDP-based service
discovery so consumers don't hardcode IPs.

```
[USB HDMI capture (NVR 4-up)] → go2rtc.service ──┬─→ RTSP   :8554/mosaic
                                                 ├─→ HLS    :1984/api/...     (browsers, fallback)
                                                 ├─→ WebRTC :8555             (sub-second in-browser)
                                                 ├─→ MJPEG  :1984/api/...     (HA legacy compat)
                                                 ├─→ JPEG   :1984/api/frame.jpeg
                                                 └─→ RTSP feeds haku-hls.service
                                                                  │
                                                                  ▼
                                                     ffmpeg remux (no re-encode) →
                                                     /run/haku-hls/mosaic.m3u8 + .ts
                                                     (deep 12s rolling buffer; absorbs blips)
                                                                  │
                                                                  ▼
                                       haku-discovery.service ── HTTP :1985 ──┐
                                         ├─ /discovery.json  (versioned capability JSON)
                                         ├─ /hls/mosaic.m3u8 + segments
                                         └─ SSDP responder UDP :1900
                                                                              │
                                                       SSDP M-SEARCH ←──── Roku channel
                                                       fetch JSON ───→ pick streams.mosaic.hls
                                                                              │
                                                                              ▼
                                                                hardware H.264 decode → TV
```

## Files in this directory

| File | Deploys to (on `nserver`) | Purpose |
|---|---|---|
| `go2rtc.yaml` | `/etc/go2rtc/go2rtc.yaml` | Stream config — UVC source + Intel QSV encode + 4 per-cam direct RTSPs |
| `go2rtc.service` | `/etc/systemd/system/go2rtc.service` | go2rtc systemd unit, runs as `media` user; loads cred env file |
| `haku-hls.service` | `/etc/systemd/system/haku-hls.service` | ffmpeg remux mosaic RTSP→deep HLS (legacy single-stream unit, kept for mosaic) |
| `haku-hls@.service` | `/etc/systemd/system/haku-hls@.service` | **Templated** ffmpeg remux for per-cam streams — one instance per cam (`@front`, `@yard`, `@side`, `@backyard`) |
| `haku-discovery.py` | `/opt/stream/haku-discovery.py` | SSDP responder + JSON capability + HLS file server (stdlib-only Python) |
| `haku-discovery.service` | `/etc/systemd/system/haku-discovery.service` | systemd unit for discovery |
| `README.md` | (repo only) | This file |

**Not committed but required at deploy time:** `/etc/haku/cam-creds.env` (mode `0640`, owner `root:media`), referenced by `go2rtc.service` via `EnvironmentFile=`. Contents:

```
HAKU_CAM_USER=admin
HAKU_CAM_PASSWORD=<from HA Reolink integration / 1Password>
```

These are substituted into per-cam RTSP URLs in `go2rtc.yaml` as `${HAKU_CAM_USER}` / `${HAKU_CAM_PASSWORD}` so the yaml stays committable.

The go2rtc binary itself is at `/usr/local/bin/go2rtc` (single static
x86_64 binary downloaded from the official GitHub releases — currently
v1.9.x).

## Endpoints (served on `enp1s0` IP `192.0.2.20`)

go2rtc publishes one stream per source. The mosaic is encoded locally; the
four per-cam streams are direct RTSP forwards from the cameras themselves.

| Stream | Origin | Codec/dims | Roku-deep HLS endpoint |
|---|---|---|---|
| `mosaic` | NVR HDMI → USB → QSV-encoded H.264 | H.264 Main 4.0, 1920×1080 @ 20 fps | `:1985/hls/mosaic.m3u8` |
| `front` | Amcrest @ 192.0.2.35 | H.264 High 4.1, 1920×1080 @ 50 fps | `:1985/hls/front.m3u8` |
| `yard` | Reolink @ 192.0.2.32 (sub-stream — main is HEVC 4K) | H.264 High 5.1, 640×360 @ 10 fps | `:1985/hls/yard.m3u8` |
| `side` | Amcrest @ 192.0.2.33 | H.264 High 4.1, 1920×1080 @ 50 fps | `:1985/hls/side.m3u8` |
| `backyard` | Reolink-family @ 192.0.2.34 | H.264 Main 5.0, 2048×1536 @ 20 fps | `:1985/hls/backyard.m3u8` |

Every stream additionally exposes:

| Endpoint | URL | Use |
|---|---|---|
| **SSDP discovery** | multicast `239.255.255.250:1900` ST=`urn:haku:service:cams:1` | Roku channel auto-discovery |
| **Discovery JSON** | `http://192.0.2.20:1985/discovery.json` | Lists all 5 streams, their HLS/RTSP/MJPEG/snapshot URLs, and metadata |
| **RTSP** | `rtsp://192.0.2.20:8554/<name>` | VLC, ffmpeg, HA `generic`/`stream`, NVRs |
| **HLS shallow** | `http://192.0.2.20:1984/api/stream.m3u8?src=<name>` | Browsers, debugging (~1 s buffer; Roku underflows) |
| **MJPEG** | `http://192.0.2.20:1984/api/stream.mjpeg?src=<name>` | HA legacy compat |
| **WebRTC** | `http://192.0.2.20:1984/stream.html?src=<name>` | Sub-second-latency browser viewing |
| **JPEG snapshot** | `http://192.0.2.20:1984/api/frame.jpeg?src=<name>` | HAku PIP, single-frame thumbnails |
| **Status UI** | `http://192.0.2.20:1984/` | Live pipeline status, consumers, bandwidth |

Each per-cam HLS sidecar runs as `haku-hls@<name>.service` (systemd
template) and writes `/run/haku-hls/<name>.m3u8` plus
`/run/haku-hls/<name>_seg_NNNNN.ts` (segments are name-prefixed so all
streams share the tmpfs cleanly).

The legacy `http://192.0.2.20:8090/?action=stream` (mjpg_streamer) is **gone**
after deploy. The legacy unit file at `/etc/systemd/system/sendHDMI.service` is
left in place for fallback.

## Encode parameters (see `go2rtc.yaml`)

| Parameter | Value | Why |
|---|---|---|
| Resolution | 1920×1080 | Native HDMI EDID; NVR mosaic is 4 quadrants — preserves per-quadrant detail |
| Framerate | 20 fps | What the capture device negotiates with the NVR HDMI-out (not configurable downward — `-framerate` is a hint v4l2 ignores) |
| Codec | H.264 AVC, **Main profile, level 4.0**, `pix_fmt=yuv420p` | Universal Roku + browser hardware decode |
| GOP | 40 frames (= 2 s @ 20 fps) | Every 2 s = 1 keyframe — HLS-segment-aligned |
| B-frames | 0 | Lowest decoder latency |
| Bitrate | 2.5 Mbps CBR (3.0 Mbps cap) | NVR mosaic with 4× motion fits comfortably |
| Encoder | `h264_qsv` (Intel Quick Sync, Iris Plus G1) | ~1-2% iGPU encoder util at 1080p15 |
| Audio | none | NVR HDMI carries no audio |

Bandwidth per consumer drops from **~78.7 Mbps** (legacy MJPEG passthrough)
to **~2.5 Mbps** (this pipeline) — ~31× reduction.

## Deploy

```bash
# from the repo root, with SSH to nserver
scp stream/go2rtc.yaml                  root@nserver:/tmp/
scp stream/go2rtc.service               root@nserver:/tmp/
scp stream/haku-hls.service        root@nserver:/tmp/
scp stream/haku-hls@.service       root@nserver:/tmp/
scp stream/haku-discovery.py       root@nserver:/tmp/
scp stream/haku-discovery.service  root@nserver:/tmp/

ssh root@nserver bash -se <<'EOF'
set -euo pipefail

# 1. Install go2rtc binary (one-time)
if [ ! -x /usr/local/bin/go2rtc ]; then
  curl -fsSL https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_linux_amd64 \
    -o /usr/local/bin/go2rtc
  chmod +x /usr/local/bin/go2rtc
fi

# 2. Add media user to capture + GPU groups
usermod -aG video,render media

# 3. Camera RTSP creds (Phase 2). NOT in repo — pulled from HA Reolink
#    integration or 1Password and dropped here. Mode 0640 root:media so the
#    media user (running go2rtc) can read it.
mkdir -p /etc/haku
install -m 0640 -o root -g media /dev/stdin /etc/haku/cam-creds.env <<'CREDS'
HAKU_CAM_USER=admin
HAKU_CAM_PASSWORD=<set me>
CREDS

# 4. Install configs and units
mkdir -p /etc/go2rtc /opt/stream
install -m 0644 /tmp/go2rtc.yaml                  /etc/go2rtc/go2rtc.yaml
install -m 0644 /tmp/go2rtc.service               /etc/systemd/system/go2rtc.service
install -m 0644 /tmp/haku-hls.service        /etc/systemd/system/haku-hls.service
install -m 0644 /tmp/haku-hls@.service       /etc/systemd/system/haku-hls@.service
install -m 0755 /tmp/haku-discovery.py       /opt/stream/haku-discovery.py
install -m 0644 /tmp/haku-discovery.service  /etc/systemd/system/haku-discovery.service
chown -R media:media /opt/stream

# 5. Stop and disable the legacy mjpg_streamer
systemctl stop sendHDMI.service || true
systemctl disable sendHDMI.service || true

# 6. Bring up the new pipeline (mosaic + 4 per-cam HLS sidecars)
systemctl daemon-reload
systemctl enable --now go2rtc.service haku-hls.service haku-discovery.service
systemctl enable --now haku-hls@front.service haku-hls@yard.service \
                       haku-hls@side.service  haku-hls@backyard.service

# 6. Smoke test
sleep 5
systemctl --no-pager status go2rtc.service haku-hls.service haku-discovery.service | head -40
ffprobe -v error -rtsp_transport tcp -show_streams \
  rtsp://127.0.0.1:8554/mosaic | grep -E "codec_name|profile|width|height|pix_fmt|level|r_frame_rate"
curl -sI http://127.0.0.1:1985/hls/mosaic.m3u8
curl -s  http://127.0.0.1:1985/discovery.json | head -40
EOF
```

## Verification

```bash
# Service alive
ssh root@nserver 'systemctl --no-pager status go2rtc haku-hls haku-discovery | head'

# Codec check (expect Main L4.0 1920x1080 yuv420p 15/1)
ssh root@nserver 'ffprobe -v error -rtsp_transport tcp -show_streams \
  rtsp://127.0.0.1:8554/mosaic | grep -E "codec_name|profile|width|height|pix_fmt|level|r_frame_rate"'

# QSV engagement
ssh root@nserver 'intel_gpu_top -s 1000 | head -20'   # if intel-gpu-tools installed

# SSDP discovery from another LAN host (gssdp-discover from gupnp-tools)
gssdp-discover -t urn:haku:service:cams:1 --timeout=3
```

## Rollback to mjpg_streamer

```bash
ssh root@nserver
systemctl stop go2rtc.service haku-hls.service haku-discovery.service
systemctl disable go2rtc.service haku-hls.service haku-discovery.service
systemctl enable --now sendHDMI.service
# HA's camera.camerafeed picks the old MJPEG up automatically again.
```

The legacy `sendHDMI.service` unit file and `mjpg_streamer` binary are not
touched by deploy — rollback is a single `systemctl` flip.

## Phase 2 (deferred)

Add four direct-RTSP cam streams to `go2rtc.yaml` once camera credentials are
confirmed and the "yardcam vs `Back`" labelling question (see
`HAKU_DESIGN.md` followup checklist) is resolved:

```yaml
streams:
  mosaic:    [...as today...]
  front:     rtsp://USER:PW@192.0.2.35:554/cam/realmonitor?channel=1&subtype=0   # Amcrest
  yard:      rtsp://USER:PW@192.0.2.32:554/h264Preview_01_main                  # Reolink
  side:      rtsp://USER:PW@192.0.2.33:554/cam/realmonitor?channel=1&subtype=0  # Amcrest
  backyard:  rtsp://USER:PW@192.0.2.34:554/h264Preview_01_main                  # Reolink
```

Then add `STREAM_METADATA` entries in `haku-discovery.py` and append
matching `haku-{name}-hls.service` units (one per stream) — or convert
the HLS sidecar to a templated unit.
