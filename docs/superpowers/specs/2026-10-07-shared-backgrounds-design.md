# Shared drone-photo backgrounds for the tablet and the Rokus

Date: 2026-10-07. Sidecar `HAKU_BG_DIR` mirror, Roku channel 0.13.0. This resolves the "Drone-photo backgrounds" follow-up in `2026-10-07-roku-glass-design.md`. Plan: `../plans/2026-10-07-shared-backgrounds.md`.

## Why

The tablet and the wall Rokus showed different photos:
- **The tablet** rotated the 42 drone photos from the NAS folder `/mnt/media/haku/kitchen` (its layout's `background.dir`).
- **The Rokus** rotated the 6 old images in `HAKU_BG_DIR` (`/etc/haku/backgrounds`).

The user wants both pulling from the same folder of pictures.

## Decisions

- **One curated folder, mirrored locally.**
  - The user keeps curating `/mnt/media/haku/kitchen` on the NAS.
  - A `haku-bg-sync` timer on nserver mirrors it into `/etc/haku/backgrounds` every 15 min (`rsync -rt --delete`).
  - The tablet and every Roku read that local copy through the default background routes.
  - Displays never read the NFS `hard` mount, so a stalled NAS can't freeze one. The sidecar's limit of two concurrent readers per layout folder never applies, because the default folder has no limit.
  - New photos show up within about 15 min, plus the clients' own list refresh.
- **The sync job never mirrors an empty or unmounted source.** `--delete` against an empty source would wipe every display's photos, so the job skips the run instead.
- **The six old images are dropped.** They were the HAku logo card and 5 older photos. The repo keeps them in `sidecar/backgrounds/` as the seed set for a fresh install.
- **The tablet's `layouts.tablet.background.dir` is removed,** so `?layout=tablet` lists the default folder. The per-layout `dir` feature stays in the sidecar, unused.
- **The Roku asks for `fit=cover`.** 34 of the 42 photos are 4:3. The previous `contain` pillarboxed them with black bars; `cover` centre-crops to 1920×1080, as the tablet does at its own size.
- **The sidecar's render cache becomes an LRU of 160.** It was 32 entries and emptied completely when full, while 42 photos at 3 sizes is 126 renders.
- **The Roku refreshes its photo list every 10 min,** like the tablet. Before, it only fetched the list at startup and discovery.
  - A failed or empty refresh keeps the photos it has.
  - A changed list carries on rotating from where it was, with no jump back to the first photo.

## Not changed

- The tablet app and its requests (1024×600 cover, and 256×150 blur 8).
- The background endpoints' contract.
- The default `/api/config`.
