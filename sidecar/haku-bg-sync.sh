#!/bin/sh
# haku-bg-sync — mirror the curated photo folder into HAKU_BG_DIR, which every display
# (the kitchen tablet and the wall Rokus) reads through the sidecar's default background
# routes. The folder lives on the NAS (an NFS `hard` mount); mirroring it keeps the NAS
# off every request path, so a stalled mount can't freeze a display.
#
# Run by haku-bg-sync.timer as `media`. Installed to /opt/haku/haku-bg-sync.sh.
#
# Never mirrors an unmounted or empty source: `--delete` would then wipe every
# display's photos. Such a run logs why and exits 0, keeping the last good copy.
set -u
SRC="${HAKU_BG_SRC:-/mnt/media/haku/kitchen}"
DST="${HAKU_BG_DIR:-/etc/haku/backgrounds}"
MOUNT="${HAKU_BG_SRC_MOUNT:-/mnt/media}"

if ! mountpoint -q "$MOUNT"; then
    echo "skip: $MOUNT is not mounted"
    exit 0
fi
# The same extensions the sidecar lists (backgrounds.ALLOWED). `timeout` because a
# dropped NAS blocks a `hard` mount's reads forever.
first=$(timeout 60 find "$SRC" -maxdepth 1 -type f ! -name '.*' \
    \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' \) -print -quit)
if [ -z "$first" ]; then
    echo "skip: no images in $SRC (unreachable or empty)"
    exit 0
fi

# Images only, top level only; anything else in DST goes (--delete-excluded). -rt, not
# -a: media can't chown. Temp files rsync writes are dotfiles, which the sidecar never
# lists. --omit-dir-times leaves DST's mtime as its real last change, so it moves
# whenever a photo comes or goes, which is what invalidates the sidecar's listing cache.
out=$(timeout 600 rsync -rt --omit-dir-times --delete --delete-excluded --chmod=D755,F644 \
    --exclude='.*' --exclude='*/' \
    --include='*.[jJ][pP][gG]' --include='*.[jJ][pP][eE][gG]' \
    --include='*.[pP][nN][gG]' --include='*.[wW][eE][bB][pP]' --exclude='*' \
    --stats "$SRC/" "$DST/" 2>&1) || { echo "rsync failed: $out"; exit 1; }
sent=$(printf '%s\n' "$out" | sed -n 's/^Number of regular files transferred: *//p')
gone=$(printf '%s\n' "$out" | sed -n 's/^Number of deleted files: *\([0-9,]*\).*/\1/p')
have=$(find "$DST" -maxdepth 1 -type f ! -name '.*' | wc -l)
echo "ok: $have photos in $DST (copied ${sent:-0}, removed ${gone:-0})"
