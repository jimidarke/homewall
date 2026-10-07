# Shared drone-photo backgrounds for the tablet and the Rokus

> **Status: deployed 2026-10-07.** `haku-bg-sync.timer` live on nserver (42 photos mirrored; the old six backed up in `/root/haku-bg-backup-20261007/`), sidecar LRU cache deployed, tablet `dir` removed from the live config, channel 0.13 on the office Roku and `.53` (`.52`/`.51`/`.54` were off). Design: `../specs/2026-10-07-shared-backgrounds-design.md`.

## Context

The tablet and the wall Rokus show different photos today:
- **Tablet:** the 42 drone photos. Its layout's `background.dir` points at the NAS folder `/mnt/media/haku/kitchen`, an NFS `hard` mount.
- **Rokus:** the 6 old images in `HAKU_BG_DIR` (`/etc/haku/backgrounds`): the HAku logo card and 5 older photos.

The user wants both pulling from the same folder of pictures.

**User decisions:**
- The NAS kitchen folder stays the one the user curates. nserver mirrors it every 15 min into `/etc/haku/backgrounds`, and the tablet and every Roku read that local copy. So no NFS stall can freeze a display, and the sidecar's 2-reader limit doesn't apply, since the default folder has no reader limit.
- The six old images are dropped.

**Findings:**
- **Photo shape:** 34 of 42 photos are 4:3 (2560×1920), 7 are 16:9 and 1 is wider. The Roku asks for `fit=contain` (the default), which would pillarbox the 4:3 photos with black bars. It must ask for `fit=cover`, as the tablet does.
- **Sidecar render cache:** `_CACHE_MAX = 32`, and it is emptied completely when full. 42 photos × 3 sizes is 126 renders: Roku 1920×1080, tablet 1024×600, and tablet 256×150 with blur. With the cache that small, almost nothing would stay cached.
- **The Roku fetches the photo list only at startup or discovery,** so new photos wouldn't appear until a relaunch. A failed or empty fetch also replaces a good list with the fallback image.
- **The tablet needs no code change.** Once `layouts.tablet.background.dir` is removed, `?layout=tablet` resolves to `HAKU_BG_DIR`.
- **nserver:** `rsync` and `mountpoint` exist, and the `media` user can read the NAS folder. `/etc/haku/backgrounds` is `media:media`.

**Step 0:** write the spec `docs/superpowers/specs/2026-10-07-shared-backgrounds-design.md` and the plan `docs/superpowers/plans/2026-10-07-shared-backgrounds.md`, and commit them.

## 1. Mirror job (new, `sidecar/`)

**`sidecar/haku-bg-sync.sh`** (installed to `/opt/haku/haku-bg-sync.sh`):
- Exit 0 without touching anything when `/mnt/media` isn't a mountpoint, or the source has no image files. This guard matters: `--delete` against an empty or unmounted source would wipe every display's photos.
- Otherwise: `timeout 600 rsync -rt --delete --exclude='.*' --chmod=D755,F644 /mnt/media/haku/kitchen/ /etc/haku/backgrounds/`.
  - `-rt` rather than `-a`, because `media` can't chown.
  - rsync's temporary dotfiles are skipped by the sidecar's listing.
  - The folder's mtime changes on any add or remove, which invalidates the sidecar's listing cache.
- Log a one-line count (files present, files transferred).

**`sidecar/haku-bg-sync.service`:**
- `Type=oneshot`, `User=media`, `Nice=10`, `IOSchedulingClass=idle`.
- `ExecStart=/opt/haku/haku-bg-sync.sh`.

**`sidecar/haku-bg-sync.timer`:** `OnBootSec=2min`, `OnUnitActiveSec=15min`, `Persistent=true`.

## 2. Sidecar render cache (`sidecar/haku_sidecar/backgrounds.py`)

- Replace the clear-all `_cache` dict with an LRU (`collections.OrderedDict`): `move_to_end` on a hit, `popitem(last=False)` past `_CACHE_MAX`.
- Raise `_CACHE_MAX` to 160, enough for 42 photos × 3 sizes plus headroom. That's about 25 MB of JPEG bytes.
- Keep the existing key `(d, name, mtime, w, h, fit, blur)` and the locking pattern.
- Tests in `sidecar/tests/test_backgrounds.py`:
  - a hit refreshes recency;
  - past the cap only the oldest entry is evicted, not everything;
  - existing tests still pass.
- Update the README "Backgrounds" section (the "holds up to 33 renders, then empties completely" text).

## 3. Roku channel 0.13.0 (`roku/`)

- **`BackgroundListTask.brs`:** append `&fit=cover` to the per-image size parameters (`w=1920&h=1080&fit=cover`).
- **`MainScene`:** add a repeating `bgListTimer` every 10 min, matching the tablet's `LIST_EVERY_MS`, that calls `runBgList()` when the hub base is known. Start it in `init`.
- **`BackgroundGallery.onImages`:**
  - First list, from nothing: as today (show `list[0]`, start rotating).
  - An empty or failed list while it already has photos: keep the current list, and log `event=bg_list_kept`.
  - The same list again: do nothing.
  - A different list while it has photos: swap `m.list`, keep the photo on screen, clamp `m.idx` into range, and carry on rotating, with no jump back to photo 0.
  - The fallback image shows only when it has never had a list.
  - If any of this decision logic can be pure (for example `hkSameList(a, b)`), put it in `Config.brs` with unit tests.
- **Version 0.13.0** in `VERSION.txt`, `package.json` and `manifest`.
- **`roku/CLAUDE.md`:** the backgrounds sentence (the shared mirrored folder, `fit=cover`, the 10-min refresh).

## 4. Config and docs

- **Live `/etc/haku/dashboard.json`:** delete `layouts.tablet.background.dir`, keeping `enabled` and `intervalMs`. Back the file up first.
- **`sidecar/dashboard.json.example`:** check that no layout carries `dir`. The README and CLAUDE examples should describe the mirror rather than a per-layout NAS `dir`. The `dir` feature itself stays supported.
- **Docs:**
  - `sidecar/README.md` (Backgrounds, and deploy of the timer) and `sidecar/CLAUDE.md`;
  - `docs/HAKU_DESIGN.md` (per-layout backgrounds);
  - `docs/fire-tablet/DESIGN.md` §8.8 source line: the kitchen folder is now mirrored into `HAKU_BG_DIR`.
  - The 0.11 spec stays as written; the new spec records how its follow-up was resolved.

## Rollout

1. **Mirror job:**
   - Install the script and units on nserver.
   - Run the service once, then check that `/etc/haku/backgrounds` holds exactly the 42 drone files with the old 6 gone, and that `/api/backgrounds` returns 42.
   - Enable the timer.
2. **Sidecar:** compare `backgrounds.py` with the deployed copy, back up the package folder, copy, `py_compile`, restart.
3. **Config:** remove the tablet `dir`. `/api/backgrounds?layout=tablet` should then list the same 42 names as the default route, and the default and tablet config md5s stay unchanged, because `dir` is never serialized.
4. **Rokus:**
   - Sideload 0.13 to the office Roku and `.53` (`.52`/`.51`/`.54` when they're on).
   - Exit and launch the channel fresh, so config and list load.
   - Take a screenshot: a drone photo filling the screen, no side bars.
5. **Tablet:** nothing to deploy. It picks up the list within 10 min. Check the sidecar log, or `/api/backgrounds?layout=tablet`, for the 42 names.

## Verification

- `cd sidecar && .venv/bin/python -m pytest tests -q` (golden included).
- `cd roku && npm run lint && npm run test:unit && HAKU_FIXTURE=1 npm run test:contract`; then `tests/smoke/smoke.sh` on the office Roku (`.55`, password `$ROKU_PW_OFFICE`).
- **On nserver:**
  - `systemctl list-timers haku-bg-sync*`;
  - `journalctl -u haku-bg-sync` shows the count;
  - touch a test file in the kitchen folder, run the service, and it appears in `/api/backgrounds`; remove it and it disappears.
  - Do this test only with a harmless file, removed afterwards.
- **On the office Roku:**
  - photos fill the screen;
  - after 10 min, the console shows the list refresh with no jump;
  - the dev screenshot shows a drone photo behind the glass.
