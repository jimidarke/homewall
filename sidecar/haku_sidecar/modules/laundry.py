"""Laundry module: the kitchen laundry notifier (esp-laundry) as tablet data.

Layout-only module, defined in the tablet layout (the Roku layout reuses it through a
`tablet:` ref); there is no `render_icon` (each client draws the LED bar itself). All the state logic lives in HA's laundry package;
like the ESPs, this module MIRRORS those sensors and never re-derives them. Per machine
`m` (descriptor `machines[]`: {id, label, color, glyph?, entities?}) it reads, by the
package's naming convention:
  mode              sensor.laundry_<m>_mode                idle|running|overtime|done|done_calm
  leds              sensor.laundry_<m>_leds                0-4 countdown pixels (passed through)
  started           input_datetime.laundry_<m>_started     `timestamp` attr; < 1e9 = never set
  finished          input_datetime.laundry_<m>_finished    (same)
  expected_minutes  input_number.laundry_<m>_expected_minutes
  power             none by default; map it (e.g. sensor.emporia_circuit_7_power)
`machines[].entities` overrides any of these by key.

Per machine it adds minutes (`remaining_min` while running, `over_min` in overtime),
`finished_hm` once done, a display `status` ("34m left", "running 5m long",
"done 9:52 AM", "no data") and a `glyph` (config, else washing-machine / tumble-dryer
by id). A mode sensor that is unavailable, missing or not one of the five modes makes
the machine `stale` ("no data", the LED bar's violet NO DATA); its `mode` reads `idle`
so it stays in the contract's enum.

Tile hero by priority: done > overtime > running > done_calm > idle (done_calm is the
calm after-phase, so a machine mid-cycle outranks it). The other machines go in `sub`.
Severity is `high` only for `done` (the box's loud phase); `active` is any machine
running, overtime or done.

`detail()` serves the tablet's detail panel (GET /api/detail/laundry): a rows block per
machine (status, last started, last finished, last run length, from the input_datetimes)
and "Last 7 days", every run in the mode sensors' history (running or overtime), newest
first. A run that began before the window is left out; one still going is "running now".
"""
import math
from datetime import datetime

from .. import blocks
from .. import config as cfg
from .. import history as hist
from ..store import now_s

_MODES = ("idle", "running", "overtime", "done", "done_calm")
_RANK = {"done": 5, "overtime": 4, "running": 3, "done_calm": 2, "idle": 1}   # stale: 0
_ACTIVE = ("running", "overtime", "done")
_GLYPH_BY_ID = {"washer": "washing-machine", "dryer": "tumble-dryer"}
_DEFAULT_GLYPH = "washing-machine"
_NEVER_SET = 1e9   # an input_datetime timestamp below this was never set


def values(ha, descriptor):
    tz = cfg.resolve_zone(descriptor.get("timezone"))
    now = now_s()
    machines = [_machine(ha, m, tz, now)
                for m in (descriptor.get("machines") or []) if isinstance(m, dict)]
    stale = all(m["stale"] for m in machines)   # also true with no machines
    return {"machines": machines, "stale": stale, "tile": _tile(machines, stale)}


def _entities(mid, overrides):
    ids = {
        "mode": f"sensor.laundry_{mid}_mode",
        "leds": f"sensor.laundry_{mid}_leds",
        "started": f"input_datetime.laundry_{mid}_started",
        "finished": f"input_datetime.laundry_{mid}_finished",
        "expected_minutes": f"input_number.laundry_{mid}_expected_minutes",
        "power": None,
    }
    if isinstance(overrides, dict):
        ids.update(overrides)
    return ids


def _machine(ha, m, tz, now):
    mid = str(m.get("id") or "")
    ents = _entities(mid, m.get("entities"))
    raw_mode = _state(ha, ents["mode"])
    stale = raw_mode not in _MODES
    mode = "idle" if stale else raw_mode

    started = elapsed = expected = remaining = over = finished = finished_hm = None
    if mode in ("running", "overtime"):
        started = _timestamp(ha, ents["started"])
        expected = _int(_state(ha, ents["expected_minutes"]))
        elapsed = max(0, (now - started) // 60) if started is not None else None
        if elapsed is not None and expected is not None:
            if mode == "running":
                remaining = max(0, expected - elapsed)
            else:
                over = max(0, elapsed - expected)
    elif mode in ("done", "done_calm"):
        finished = _timestamp(ha, ents["finished"])
        finished_hm = _hm(finished, tz) if finished is not None else None

    return {
        "id": mid,
        "label": m.get("label") or mid.title(),
        "color": m.get("color"),
        "mode": mode,
        "leds": _int(_state(ha, ents["leds"])) or 0,
        "started": started,
        "elapsed_min": elapsed,
        "expected_min": expected,
        "remaining_min": remaining,
        "over_min": over,
        "finished": finished,
        "finished_hm": finished_hm,
        "power_w": _int(_state(ha, ents["power"])),
        "status": _status(mode, stale, remaining, over, finished_hm),
        "glyph": m.get("glyph") or _GLYPH_BY_ID.get(mid, _DEFAULT_GLYPH),
        "stale": stale,
    }


def _status(mode, stale, remaining, over, finished_hm):
    if stale:
        return "no data"
    if mode == "running":
        return f"{remaining}m left" if remaining is not None else "running"
    if mode == "overtime":
        return f"running {over}m long" if over is not None else "running long"
    if mode == "done_calm" and finished_hm:
        return f"done {finished_hm}"
    if mode in ("done", "done_calm"):
        return "done"
    return "idle"


# --- detail ----------------------------------------------------------------
_TONE_BY_ID = {"washer": "washer", "dryer": "dryer"}
_HISTORY_DAYS = 7
_HISTORY_TTL = 60     # a run that just ended should show while the panel is open
_MAX_ROWS = 30        # the tablet clamps rows to 30


def detail(ha, descriptor, now):
    """The detail panel's blocks (tablet contract §1)."""
    tz = cfg.resolve_zone(descriptor.get("timezone"))
    shown = {m["id"]: m for m in values(ha, descriptor)["machines"]}
    ents = {}
    for m in descriptor.get("machines") or []:
        if isinstance(m, dict):
            mid = str(m.get("id") or "")
            ents[mid] = _entities(mid, m.get("entities"))

    start = hist.local_midnight(now, tz, _HISTORY_DAYS - 1)
    modes = [e["mode"] for e in ents.values() if e.get("mode")]
    history = ha.get_history(modes, start, None, ttl=_HISTORY_TTL) if modes else {}
    runs = {mid: [r for r in hist.mode_runs((history or {}).get(e.get("mode")), start, now)
                  if not r["clipped"]]
            for mid, e in ents.items()}

    out = [_machine_rows(ha, shown[mid], e, runs[mid], tz) for mid, e in ents.items()]
    recent = sorted(((shown[mid], r) for mid, rs in runs.items() for r in rs),
                    key=lambda p: p[1]["start"], reverse=True)[:_MAX_ROWS]
    note = None
    if history is None:
        note = "History unavailable"
    elif recent:
        out.append(blocks.rows("Last 7 days", [
            {"glyph": m["glyph"], "tone": _tone(m), "label": m["label"],
             "value": hist.dt_label(r["start"], tz),
             "sub": "running now" if r["open"] else hist.duration(r["length"])}
            for m, r in recent]))
    else:
        note = "No runs in the last 7 days"
    return {"blocks": out, "note": note}


def _machine_rows(ha, m, ents, runs, tz):
    """Rows for one machine: status, last started / finished, last run length."""
    started, finished = _timestamp(ha, ents["started"]), _timestamp(ha, ents["finished"])
    if started is not None and finished is not None and finished >= started:
        length = finished - started
    else:
        done = [r for r in runs if not r["open"]]
        length = done[-1]["length"] if done else None
    status = m["status"]
    items = [
        {"glyph": m["glyph"], "tone": _tone(m), "label": "Status",
         "value": status[:1].upper() + status[1:]},
        started is not None and {"label": "Last started", "value": hist.dt_label(started, tz)},
        finished is not None and {"label": "Last finished", "value": hist.dt_label(finished, tz)},
        length is not None and {"label": "Last run length", "value": hist.duration(length)},
    ]
    return blocks.rows(m["label"], [i for i in items if i])


def _tone(m):
    return _TONE_BY_ID.get(m["id"], "ink")


# --- tile ------------------------------------------------------------------
def _tile(machines, stale):
    if stale:
        hero, sub = "No data", ""
    elif all(m["mode"] == "idle" and not m["stale"] for m in machines):
        hero, sub = "Laundry idle", ""
    else:
        top = max(machines, key=_rank)               # first of equals: config order
        hero = _line(top)
        sub = " · ".join(_line(m) for m in machines if m is not top)
    return {
        "hero": hero,
        "sub": sub,
        "detail": "",
        "severity": "high" if any(m["mode"] == "done" for m in machines) else "normal",
        # cache-bust token in the Roku's `icon` style; the tablet ignores it
        "icon": "|".join(f"{'stale' if m['stale'] else m['mode']}:{m['leds']}" for m in machines),
        "glyph": "washing-machine",
        "active": any(m["mode"] in _ACTIVE for m in machines),
    }


def _rank(m):
    return 0 if m["stale"] else _RANK[m["mode"]]


def _line(m):
    return f"{m['label']} {m['status']}"                  # "Washer 34m left"


# --- helpers ---------------------------------------------------------------
def _state(ha, eid):
    st = ha.get_state(eid) if eid else None
    return st.get("state") if st else None


def _timestamp(ha, eid):
    ts = _num(ha.attr(eid, "timestamp")) if eid else None
    return int(ts) if ts is not None and ts >= _NEVER_SET else None


def _hm(ts, tz):
    dt = datetime.fromtimestamp(ts, tz)
    return f"{dt.hour % 12 or 12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def _num(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def _int(v):
    n = _num(v)
    return int(round(n)) if n is not None else None
