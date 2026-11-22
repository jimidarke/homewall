# Roku screenshots

TODO (owner): recapture the 6×4 home wall here as `home.png`.

The earlier baseline screenshots were taken over the house's own photo backgrounds and
were removed before the repo went public. To retake one without anything personal in it:

1. Point the sidecar's background directory at the generated seeds
   (`HAKU_BG_DIR=sidecar/backgrounds`, or a layout's `background.dir`).
2. Run the sidecar against `sidecar/dashboard.json.example` and a fake or demo HA, or
   blank the calendar and activity cards.
3. Screenshot through the dev Roku's `plugin_inspect` page (`http://<roku>/plugin_inspect`,
   "Screenshot"). The video plane never shows up in these, so the camera square is black.
