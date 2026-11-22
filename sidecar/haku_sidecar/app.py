"""HAku sidecar HTTP service.

Serves the Roku channel three things over HTTP on :1986 (discovered via the
`sidecar` block in discovery.json):
  GET /api/config            portable module descriptors (from dashboard.json)
  GET /api/state             one composed values snapshot for all native tiles
  GET /api/module/<id>       one module's values
  GET /api/detail/<id>       one module's detail panel as typed blocks (the tablet)
  GET /api/card/<name>.png   server-rendered PNG card (matplotlib+Pillow)
  GET /api/icon/<id>.png     server-rendered home-tile accent icon (Pillow)
  GET /api/backgrounds       rotating background roster
  GET /api/background/<name> one background as an exact w x h JPEG (?fit=, ?blur=)
  GET /api/health            liveness + HA connection status

config/state/module/detail/card/icon also take `?layout=<name>`: a display's own module set
from the config's `layouts` map (config.get_layout). Without it they serve the default
(Roku) view, unchanged. An unknown layout or a bad `ref` is a 404 JSON error.
backgrounds/background take it too, to read that layout's own `background.dir`. That
dir can be a `hard` NFS mount, where a dropped NAS blocks stat()/open() forever, so at
most two such requests run at once (_LAYOUT_BG_SLOTS); a third gets a 503 straight away
and the default (Roku) background routes are never gated.

A single background poller (ha.HAClient) refreshes HA state on an interval so N Rokos
polling the sidecar cost HA at most one /api/states call per interval.
"""
import logging
import math
import os
import threading
from urllib.parse import quote

from flask import Flask, Response, jsonify

from . import backgrounds
from . import config as cfg
from . import ha as ha_mod
from . import modules
from . import net

app = Flask(__name__)
log = logging.getLogger(__name__)

HA_URL = os.environ.get("HAKU_HA_URL", "http://homeassistant.local:8123")
HA_TOKEN = os.environ.get("HAKU_HA_TOKEN", "")
POLL_INTERVAL = int(os.environ.get("HAKU_POLL_INTERVAL", "10"))
HTTP_PORT = int(os.environ.get("HAKU_SIDECAR_HTTP_PORT", "1986"))
SIDECAR_BASE = os.environ.get("HAKU_SIDECAR_BASE", "")  # e.g. http://<this host>:1986

ha = ha_mod.HAClient(HA_URL, HA_TOKEN, poll_interval=POLL_INTERVAL)

# Waitress has 8 threads and no request timeout. A hung NAS mount can strand at most
# these two; the rest stay free for the Rokus.
_LAYOUT_BG_SLOTS = threading.BoundedSemaphore(2)


def _sidecar_block():
    base = SIDECAR_BASE
    if not base:
        base = f"http://{net.lan_ip()}:{HTTP_PORT}"
    return {"base": base, "config": "/api/config", "state": "/api/state"}


def _config_for_request():
    """(config, bg_dir) for this request's `?layout=`.

    No parameter: the default (Roku) view, `cfg.public_config()`, and bg_dir None.
    Raises cfg.UnknownLayout / cfg.UnknownRef, which the handlers below turn into 404s.
    """
    from flask import request
    name = request.args.get("layout")
    if name is None:
        return cfg.public_config(), None
    return cfg.get_layout(name)


@app.errorhandler(cfg.UnknownLayout)
def _unknown_layout(e):
    return jsonify({"error": "unknown layout", "layout": e.layout}), 404


@app.errorhandler(cfg.UnknownRef)
def _unknown_ref(e):
    return jsonify({"error": "unknown ref", "ref": e.ref}), 404


@app.get("/api/health")
def health():
    st = ha.status()
    # prune: the Roku's ParseJson mishandles null, so never emit it (last_error
    # is None when healthy — drop the key rather than serialize null).
    return jsonify(modules.prune({
        "ok": True,
        "ha_connected": st["connected"],
        "ha": st,
        "modules": [m.get("id") for m in cfg.get_modules()],
        "ts": modules.now_s(),
    }))


@app.get("/api/config")
def get_config():
    c, _ = _config_for_request()
    return jsonify({**c, "sidecar": _sidecar_block()})


@app.get("/api/state")
def get_state():
    c, _ = _config_for_request()
    snapshot = modules.compose_state(ha, c)
    return jsonify(snapshot)


@app.get("/api/module/<module_id>")
def get_module(module_id):
    c, _ = _config_for_request()
    m = cfg.get_module(module_id, c)
    if not m:
        return jsonify({"error": "unknown module", "id": module_id}), 404
    return jsonify(modules.prune(modules.module_values(ha, m)))


@app.get("/api/detail/<module_id>")
def get_detail(module_id):
    """A module's detail panel (the tablet v3 contract): 404 for an unknown id or a kind
    without one. HA history/statistics failures degrade inside the body, never a 500."""
    c, _ = _config_for_request()
    m = cfg.get_module(module_id, c)
    if not m:
        return jsonify({"error": "unknown module", "id": module_id}), 404
    body = modules.module_detail(ha, m)
    if body is None:
        return jsonify({"error": "no detail", "id": module_id, "kind": m.get("kind")}), 404
    return jsonify(body)


@app.get("/api/card/<name>.png")
def get_card(name):
    from flask import request
    w = _int(request.args.get("w"), 560)
    h = _int(request.args.get("h"), 360)
    c, _ = _config_for_request()  # outside the try: a bad layout is a 404, not a 500
    try:
        png = modules.render_card(ha, name, c, w, h)
    except Exception as e:
        return jsonify({"error": f"render failed: {type(e).__name__}: {e}"}), 500
    if png is None:
        return jsonify({"error": "unknown card", "name": name}), 404
    return Response(png, mimetype="image/png",
                    headers={"Cache-Control": "no-cache"})


@app.get("/api/icon/<module_id>.png")
def get_icon(module_id):
    from flask import request
    w = _int(request.args.get("w"), 96)
    h = _int(request.args.get("h"), 96)
    c, _ = _config_for_request()  # outside the try: a bad layout is a 404, not a 500
    try:
        png = modules.render_icon(ha, module_id, c, w, h)
    except Exception as e:
        return jsonify({"error": f"render failed: {type(e).__name__}: {e}"}), 500
    if png is None:
        return jsonify({"error": "unknown icon", "id": module_id}), 404
    return Response(png, mimetype="image/png",
                    headers={"Cache-Control": "public, max-age=300"})


def _layout_bg_slot(d, fn):
    """fn(), holding one of _LAYOUT_BG_SLOTS when `d` is a layout's own background dir.

    d None (the default dir, what the Rokus read) runs fn() ungated. With both slots
    taken, return 503 without waiting and without touching the directory.
    """
    if d is None:
        return fn()
    if not _LAYOUT_BG_SLOTS.acquire(blocking=False):
        log.warning("background dir %s: both slots busy, answering 503", d)
        return jsonify({"error": "backgrounds busy"}), 503
    try:
        return fn()
    finally:
        _LAYOUT_BG_SLOTS.release()


@app.get("/api/backgrounds")
def get_backgrounds():
    from flask import request
    _, d = _config_for_request()
    base = _sidecar_block()["base"]
    layout = request.args.get("layout")
    query = "" if layout is None else "?layout=" + quote(layout, safe="")
    return _layout_bg_slot(d, lambda: jsonify({
        "images": [
            {"name": n, "url": f"{base}/api/background/{n}{query}"}
            for n in backgrounds.list_names(d)
        ]
    }))


@app.get("/api/background/<name>")
def get_background(name):
    from flask import request
    w = _int(request.args.get("w"), 1920)
    h = _int(request.args.get("h"), 1080)
    fit = request.args.get("fit", "contain")
    blur = _blur(request.args.get("blur"))
    _, d = _config_for_request()  # outside the try: a bad layout is a 404, not a 500
    if fit not in backgrounds.FITS:  # before any file is read
        return jsonify({"error": "unknown fit", "fit": fit}), 400
    return _layout_bg_slot(d, lambda: _render_background(name, w, h, fit, blur, d))


def _render_background(name, w, h, fit, blur, d):
    try:
        body = backgrounds.serve(name, w, h, fit=fit, blur=blur, d=d)
    except FileNotFoundError:
        return jsonify({"error": "unknown background", "name": name}), 404
    except backgrounds.Undecodable:
        return jsonify({"error": "undecodable background", "name": name}), 422
    return Response(body, mimetype="image/jpeg",
                    headers={"Cache-Control": "public, max-age=3600"})


def _int(v, default):
    try:
        return max(64, min(1920, int(v)))
    except (TypeError, ValueError):
        return default


def _blur(v):
    """Blur radius from a query value: a finite number, else 0 (serve() clamps the range)."""
    try:
        b = float(v)
    except (TypeError, ValueError):
        return 0
    return b if math.isfinite(b) else 0


def _bootstrap():
    ha.start()


_bootstrap()


def main():
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=HTTP_PORT, threads=8)
    except ImportError:
        app.run(host="0.0.0.0", port=HTTP_PORT)


if __name__ == "__main__":
    main()
