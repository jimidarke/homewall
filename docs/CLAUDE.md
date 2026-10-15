# CLAUDE.md — docs/

- `HAKU_DESIGN.md` — the system design (Roku channel, stream pipeline, sidecar, HA integration, tablet client). Its status note at the top is a dated snapshot.
- `fire-tablet/DESIGN.md` — the tablet design (§8 the UI, §8.10 touch, §8.11 the door camera); `fire-tablet/screens/` are the v2 checkpoint screenshots from 2026-09-30.
- `roku/screens/home.png` — the Roku wall baseline: the 6×4 home on the office Roku (Roku 1.2.1, 2026-10-14), from the device's `plugin_inspect` screenshot. Roku screenshots never capture the video plane, so the camera square is black even while it plays. Blur calendar titles (and anything else personal) before committing a new one.
- `superpowers/specs/`, `superpowers/plans/` — specs and plans for finished work. Keep them as written (those before 2026-10-03 use pre-merge paths; `superpowers/README.md` maps them). New specs and plans go here too, dated `YYYY-MM-DD-<topic>`.
- `brand/` — source logo art (`logo_icon.png`, `logo_wordmark.png`). `../roku/scripts/generate_brand_assets.py` reads these and writes the Roku images and the sidecar's seed background; re-run it rather than hand-editing outputs.

When a change alters the sidecar contract, the stream pipeline or a client's behaviour, update the matching design doc in the same commit.
