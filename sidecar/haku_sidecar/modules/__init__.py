"""Module registry — the server twin of the Roku's HK_MODULE_KINDS() table.

Registering a new module = drop a `<kind>.py` here exposing `values(ha, descriptor)`
(and optional `CARDS = {name: render(ha, descriptor, w, h)}` and/or an optional
`render_icon(ha, descriptor, w, h)` for a home-tile accent icon) and add it to
MODULES. That plus a config entry and the Roku-side kind row is the whole
"add a module" recipe. An optional `detail(ha, descriptor, now)` returning
{"blocks": [...], "note"?} serves the tablet's detail panel (GET /api/detail/<id>).
"""
import logging

from .. import config as cfg
from ..store import now_s, prune
from . import calendar, cameras, climate, doors, energy, gas, laundry, timeline, water, weather

MODULES = {
    "weather": weather,
    "cameras": cameras,
    "energy": energy,
    "water": water,
    "gas": gas,
    "climate": climate,
    "calendar": calendar,
    "timeline": timeline,
    "doors": doors,        # tablet layout (the Roku reserves the kind; no Roku layout uses it)
    "laundry": laundry,    # tablet layout only; the Roku has no laundry kind
}


log = logging.getLogger(__name__)


def _with_timezone(descriptor):
    # Every module gets the configured timezone for free (a module's own
    # `timezone` key, if it ever sets one, wins) so date-boundary math
    # (timeline/calendar sectioning) never has to fall back to the host's clock.
    return descriptor if "timezone" in descriptor else {**descriptor, "timezone": cfg.get_timezone()}


def module_values(ha, descriptor):
    mod = MODULES.get(descriptor.get("kind"))
    if not mod or not hasattr(mod, "values"):
        return {}
    d = _with_timezone(descriptor)
    try:
        return mod.values(ha, d)
    except Exception as e:  # never let one module break the whole snapshot
        return {"error": f"{type(e).__name__}: {str(e)[:80]}"}


def module_detail(ha, descriptor, now=None):
    """The /api/detail/<id> body for one module (tablet contract §1), None-pruned.

    {"v": 1, "id", "title", "ts", "note"?, "blocks": [...]}, or None when the kind has
    no `detail()`. A detail that raises still answers, with no blocks and a note, so one
    bad HA reply is never a 500.
    """
    mod = MODULES.get(descriptor.get("kind"))
    fn = getattr(mod, "detail", None) if mod else None
    if fn is None:
        return None
    now = now_s() if now is None else now
    try:
        body = fn(ha, _with_timezone(descriptor), now) or {}
    except Exception:  # never let one module's detail 500 the panel
        log.exception("detail %r failed", descriptor.get("id"))
        body = {"note": "Detail unavailable", "blocks": []}
    mid = descriptor.get("id")
    return prune({
        "v": 1,
        "id": mid,
        "title": descriptor.get("title") or str(mid).title(),
        "ts": now,
        "note": body.get("note"),
        "blocks": body.get("blocks") or [],
    })


def compose_state(ha, config):
    """Build the single /api/state snapshot the Roku polls (None-pruned)."""
    out = {"v": 1, "ts": now_s()}
    for m in config.get("modules", []):
        feed_key = m.get("feedKey") or m.get("id")
        out[feed_key] = module_values(ha, m)
    return prune(out)


def render_card(ha, name, config, w, h):
    """Render the PNG card `name` by finding the config module that owns it."""
    for m in config.get("modules", []):
        mod = MODULES.get(m.get("kind"))
        cards = getattr(mod, "CARDS", {}) if mod else {}
        if name in cards:
            return cards[name](ha, m, w, h)
    return None


def render_icon(ha, module_id, config, w, h):
    """Render module `module_id`'s home-tile accent icon.

    Returns None for an unknown module id or a kind whose module has no
    `render_icon` (e.g. calendar/timeline/cameras — no icon by design).
    """
    m = next((mm for mm in config.get("modules", []) if mm.get("id") == module_id), None)
    if not m:
        return None
    mod = MODULES.get(m.get("kind"))
    fn = getattr(mod, "render_icon", None) if mod else None
    return fn(ha, m, w, h) if fn else None
