# CLAUDE.md — docs/

- `HAKU_DESIGN.md` — the system design (Roku channel, stream pipeline, sidecar, HA integration, tablet client). Its status notes are dated snapshots.
- `fire-tablet/DESIGN.md` — the tablet design (§8 v2 UI, §8.10 v3 touch); `fire-tablet/screens/` are checkpoint screenshots.
- `superpowers/specs/`, `superpowers/plans/` — specs and plans for finished work. Keep them as written (paths are pre-merge; `superpowers/README.md` maps them). New specs and plans go here too, dated `YYYY-MM-DD-<topic>`.
- `brand/` — source logo art (`logo_icon.png`, `logo_wordmark.png`). `../roku/scripts/generate_brand_assets.py` reads these and writes the Roku images and the sidecar's seed background; re-run it rather than hand-editing outputs.

When a change alters the sidecar contract, the stream pipeline or a client's behaviour, update the matching design doc in the same commit.
