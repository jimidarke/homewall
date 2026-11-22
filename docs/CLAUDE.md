# CLAUDE.md — docs/

- `HAKU_DESIGN.md` — the system design (Roku channel, stream pipeline, sidecar, HA integration, tablet client). Its status note at the top is a dated snapshot.
- `fire-tablet/DESIGN.md` — the tablet design (§8 the UI, §8.10 touch, §8.11 the door camera); `fire-tablet/screens/` holds the v2 checkpoint-1 screenshots from 2026-09-30 (the app's built-in demo data on its plain background).
- `roku/screens/` — Roku wall screenshots (TODO: recapture; the earlier ones showed the house's real photo backgrounds and were removed). Take them from the device's `plugin_inspect` screenshot over a neutral background (one of `sidecar/backgrounds/bg_0*.jpg`) with fixture or demo data. Roku screenshots never capture the video plane, so the camera square is black even while it plays. Never commit real calendar entries, names, photos of the house or its surroundings.
- `superpowers/specs/`, `superpowers/plans/` — specs and plans for finished work. Keep them as written (those before 2026-10-03 use pre-merge paths; `superpowers/README.md` maps them). New specs and plans go here too, dated `YYYY-MM-DD-<topic>`.
- `brand/` — source logo art (`logo_icon.png`, `logo_wordmark.png`). `../roku/scripts/generate_brand_assets.py` reads these and writes the Roku images and the sidecar's seed background; re-run it rather than hand-editing outputs.

When a change alters the sidecar contract, the stream pipeline or a client's behaviour, update the matching design doc in the same commit.
