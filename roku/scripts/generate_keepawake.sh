#!/usr/bin/env bash
# Generate the keep-awake loop clip — a tiny, silent, black H.264 video the
# channel plays on home/module/diag so the OS screensaver never takes over
# (Roku exposes no API to disable the screensaver). Committed as
# roku/images/keepawake.mp4; re-run only if it needs regenerating.
#
# 16x16 black, 300s @ 5fps, baseline profile, NO audio track (-an), faststart.
# Long duration keeps the manual loop (MainScene onKeepAwakeState/watchdog) from
# churning the decoder; the file stays tiny (all-black H.264 compresses to nothing).
set -euo pipefail
OUT="$(cd "$(dirname "$0")/.." && pwd)/images/keepawake.mp4"
ffmpeg -y -f lavfi -i "color=c=black:s=16x16:d=300:r=5" \
  -c:v libx264 -profile:v baseline -level 3.0 -pix_fmt yuv420p \
  -an -movflags +faststart "$OUT"
echo "wrote $OUT ($(stat -c%s "$OUT") bytes)"
