"""Dashboard config loader for the HAku sidecar.

The portable config (default /etc/haku/dashboard.json) is the ONE place a HAku
install is bound to its Home Assistant entities. It is served near-verbatim at
/api/config so the Roku renders whatever is declared here — moving to another HA
install is a config edit, no code change. mtime-cached so edits apply without a
restart.

An optional top-level `layouts` map gives each display its own module set (`tablet`
for the kitchen tablet, `roku` for the wall Rokus): `?layout=<name>` serves
`get_layout(name)` instead. The default view (`public_config()`) never carries
`layouts`, so what an older Roku channel caches is unchanged.
"""
import logging
import os
from datetime import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .store import CachedJson, prune

log = logging.getLogger(__name__)

CONFIG_PATH = os.environ.get("HAKU_CONFIG", "/etc/haku/dashboard.json")

# This install's home; day-boundary math (timeline/calendar sectioning) must use
# this, not whatever tz the sidecar host's OS happens to be set to (nserver runs
# UTC while the house is Edmonton — that mismatch is what caused the day-section
# headers to flip mid-evening). Overridable per-install via the top-level
# `timezone` key so moving to another HA install is a config edit, no code change.
DEFAULT_TIMEZONE = "America/Edmonton"

# Minimal fallback so the sidecar serves something coherent before a config is
# dropped in place (keeps /api/config non-empty during first boot / CI).
DEFAULT_CONFIG = {
    "version": 1,
    "site": "home",
    "grid": {"cols": 3, "rows": 2, "cellW": 600, "cellH": 440,
             "originX": 60, "originY": 160, "gap": 24},
    "background": {"intervalMs": 20000, "enabled": True},
    "modules": [],
    "timezone": DEFAULT_TIMEZONE,
}

_cache = CachedJson(CONFIG_PATH, DEFAULT_CONFIG)

# tile.type values the Roku knows how to render (forward-compat: unknown → neutral).
KNOWN_TILE_TYPES = {"value", "chart", "image", "camera", "agenda", "forecast"}


def _valid_module(m):
    return (
        isinstance(m, dict)
        and isinstance(m.get("id"), str) and m["id"]
        and isinstance(m.get("kind"), str) and m["kind"]
        and isinstance(m.get("tile"), dict)
    )


class UnknownLayout(KeyError):
    """`?layout=` named a layout that isn't in the config's `layouts` map."""

    def __init__(self, layout):
        super().__init__(layout)
        self.layout = layout


class UnknownRef(KeyError):
    """A layout module's `ref` names no valid top-level module id."""

    def __init__(self, ref):
        super().__init__(ref)
        self.ref = ref


def get_config():
    """Return the config dict (fallback to DEFAULT_CONFIG on any read error).

    This is the CACHED dict every request shares: read it, never mutate it.
    """
    cfg = _cache.get() or DEFAULT_CONFIG
    return cfg


def public_config():
    """The default /api/config body: a top-level copy of the config minus `layouts`."""
    return {k: v for k, v in get_config().items() if k != "layouts"}


def get_modules(config=None):
    """Return the list of valid module descriptors (of `config`, default the dashboard's)."""
    cfg = get_config() if config is None else config
    mods = cfg.get("modules", [])
    return [m for m in mods if _valid_module(m)]


def get_module(module_id, config=None):
    for m in get_modules(config):
        if m.get("id") == module_id:
            return m
    return None


def get_layout(name):
    """(public_cfg, bg_dir) for display layout `name`, built fresh from the config.

    public_cfg is a new, None-pruned dict {version, site, timezone, grid, nightDim?,
    background?, modules}; nothing in it aliases the cached config. A layout module
    with `ref` is that top-level module shallow-merged with the entry's other keys
    (a `tile` or `entities` override replaces the whole sub-object), or, for a qualified
    `"<layout>:<id>"` ref, that other layout's resolved entry; one without `ref` is a
    layout-only module. Modules that fail `_valid_module` are dropped and
    logged, and a `modules` that isn't a list is logged and served as no modules. The
    layout `background` is shallow-merged over the top-level one, and its `dir` is popped
    out and returned as bg_dir (None: use HAKU_BG_DIR as today), so a server path never
    reaches a client; a `dir` that isn't a non-empty string is logged and ignored. `grid`
    falls back to the top-level grid.

    Raises UnknownLayout (no such layout) or UnknownRef (a `ref` names no module).
    """
    base = get_config()
    layouts = base.get("layouts")
    layout = layouts.get(name) if isinstance(layouts, dict) else None
    if not isinstance(layout, dict):
        raise UnknownLayout(name)

    by_id = {}
    for m in get_modules(base):
        by_id.setdefault(m["id"], m)  # first wins, as in get_module()

    resolved = _resolve_entries(name, layout, by_id, layouts)

    background = {**_as_dict(base.get("background")), **_as_dict(layout.get("background"))}
    bg_dir = background.pop("dir", None)
    if bg_dir is not None and not (isinstance(bg_dir, str) and bg_dir):
        log.warning("layout %r: ignoring background.dir %r, not a non-empty string", name, bg_dir)
        bg_dir = None
    # prune() rebuilds every dict/list it walks, so the result shares no container
    # with the cache even though the ref merge above is shallow.
    public = prune({
        "version": base.get("version"),
        "site": base.get("site"),
        "timezone": base.get("timezone"),
        "grid": layout.get("grid") or base.get("grid"),
        "nightDim": layout.get("nightDim"),
        "background": background or None,
        "modules": resolved,
    })
    return public, bg_dir


def _resolve_entries(name, layout, by_id, layouts, qualified=True):
    """Layout `name`'s module entries, each `ref` merged over what it names.

    A bare `ref` names a top-level module id. A qualified one, "<layout>:<id>", names
    the entry with that id in another layout, resolved first (the Roku's wall layout
    reuses the tablet's tiles that way). Only one hop: the other layout's own entries
    may not be qualified, so there are no chains or cycles (`qualified=False`).
    """
    entries = layout.get("modules")
    if entries is None:
        entries = []
    elif not isinstance(entries, list):
        log.warning("layout %r: modules is not a list (%s), serving no modules",
                    name, type(entries).__name__)
        entries = []

    others = {}  # other layout name -> its resolved entries, resolved once per call
    resolved = []
    for entry in entries:
        ref = entry.get("ref") if isinstance(entry, dict) else None
        if ref is not None:
            entry = {**_ref_target(ref, by_id, layouts, others, qualified),
                     **{k: v for k, v in entry.items() if k != "ref"}}
        if not _valid_module(entry):
            label = entry.get("id", ref) if isinstance(entry, dict) else entry
            log.warning("layout %r: dropping invalid module %r", name, label)
            continue
        resolved.append(entry)
    return resolved


def _ref_target(ref, by_id, layouts, others, qualified):
    """The module a `ref` names (see _resolve_entries); UnknownRef when it names none."""
    if not isinstance(ref, str):
        raise UnknownRef(ref)
    if ":" not in ref:
        if ref not in by_id:
            raise UnknownRef(ref)
        return by_id[ref]
    other, _, mid = ref.partition(":")
    layout = layouts.get(other) if qualified and isinstance(layouts, dict) else None
    if not isinstance(layout, dict):
        raise UnknownRef(ref)
    if other not in others:
        others[other] = _resolve_entries(other, layout, by_id, layouts, qualified=False)
    target = next((m for m in others[other] if m["id"] == mid), None)
    if target is None:
        raise UnknownRef(ref)
    return target


def _as_dict(v):
    return v if isinstance(v, dict) else {}


def get_grid():
    return get_config().get("grid", DEFAULT_CONFIG["grid"])


def get_timezone():
    """The configured local timezone name — the single source of truth every
    date-boundary calculation (timeline/calendar sectioning) must use."""
    return get_config().get("timezone") or DEFAULT_TIMEZONE


def resolve_zone(tz_name):
    """A tzinfo for `tz_name`.

    None (naive/system-local) if no name was given — callers that never receive a
    `timezone` value keep their prior behavior unchanged. A bad/unknown name (typo
    in dashboard.json) fails safe to UTC rather than silently reverting to
    host-OS-local time, which is the exact bug this exists to avoid.
    """
    if not tz_name:
        return None
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return timezone.utc
