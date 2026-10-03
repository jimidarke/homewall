"""Small JSON read-model store + prune helpers for the HAku sidecar, plus the
shared time helpers (`rel_age`, `iso_epoch`) the agenda and doors modules format with.

Lifted from sallynet services/sally-api/store.py (mtime-cached reader + atomic
writer, both proven against the same 5 s Roku poll cadence) with `_prune` folded in
from sally-api/app.py. `_prune` is load-bearing: the Roku's `ParseJson` maps JSON
`null` to a value its assocarray round-trip mishandles, so the sidecar must NEVER
emit null — drop the key instead.
"""
import json
import os
import time
from datetime import datetime


def now_s():
    return int(time.time())


def rel_age(age):
    """Compact age for a duration in seconds: "now", "6m", "2h", "3d" (floored).

    The one age format every module shows (timeline rows, door ages).
    """
    age = max(0, int(age))
    if age < 60:
        return "now"
    if age < 3600:
        return f"{age // 60}m"
    if age < 86400:
        return f"{age // 3600}h"
    return f"{age // 86400}d"


def iso_epoch(iso):
    """Epoch seconds for an HA ISO-8601 timestamp (logbook `when`, `last_changed`).

    None when missing or unparseable.
    """
    if not iso:
        return None
    try:
        return int(datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError):
        return None


def read_json(path, default=None):
    """One-shot read; returns `default` on any error (missing / malformed)."""
    try:
        with open(path) as f:
            return json.load(f)
    except (ValueError, OSError):
        return default


def atomic_write_json(path, data, indent=2):
    """Write `data` as JSON to `path` atomically (tmp + os.replace). Creates parents."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=indent, sort_keys=True)
    os.replace(tmp, path)  # atomic on POSIX


def prune(obj):
    """Recursively drop None so JSON we hand the Roku never contains `null`.

    Empty dicts/lists are kept (the Roku tolerates them); only None is removed.
    """
    if isinstance(obj, dict):
        return {k: prune(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, (list, tuple)):
        return [prune(v) for v in obj if v is not None]
    return obj


class CachedJson:
    """Reader that reloads only when the file's mtime changes (cheap per-request).

    Construct one per file at import time; call .get() inside request handlers so an
    edit to dashboard.json is picked up without a restart.
    """

    def __init__(self, path, default):
        self._path = path
        self._default = default
        self._mtime = -1.0
        self._data = default

    def get(self):
        try:
            mtime = os.stat(self._path).st_mtime
        except OSError:
            return self._data
        if mtime != self._mtime:
            loaded = read_json(self._path, None)
            if loaded is not None:
                self._data = loaded
                self._mtime = mtime
        return self._data

    def invalidate(self):
        self._mtime = -1.0
