"""Doors module: open/closed per door contact, with how long it has been that way.

Layout-only module, defined in the tablet layout; the Roku layout reuses it through a
`tablet:` ref. Descriptor:
  entities.doors[]  {id, entity, label}: one binary_sensor contact per door
  openAlertSec      a door open longer than this is `high` (300)
  lookbackHours     logbook window for "since" (12, the timeline's, so the
                    `entity:hours` logbook cache entry is shared)
  camera            optional door camera takeover (the tablet's):
                    {door: <door id>, cam: <stream>, sec: 60, label: <door's label>}

Camera takeover: when `camera.door` opened less than `sec` ago, the values carry
`takeover: {cam, hls, label, until}` (`until` = opening epoch + sec), and no key at all
otherwise. The opening time is the HA client's `last_on` (an off->on edge between two
of its snapshots), so it survives the door closing again and needs the 1 s poll to
catch a quick open. `hls` is `<base>/<cam>.m3u8`, base from `net.stream_hls_base()`
($HAKU_HLS_BASE, else the stream server on the sidecar's host).

State: `on` -> open, `off` -> closed, anything else (unavailable/unknown/missing) -> unknown.

"Since" comes from the logbook, not `last_changed`: the contacts are Zigbee2MQTT
entities and HA re-stamps `last_changed` on restart. The newest logbook row that is a
real open/close wins. Two kinds of row are skipped:
  - rows out of `unavailable`/`unknown` (Z2M reconnects);
  - a row repeating the previous row's state. Logbook rows always differ from their old
    state, so a repeat means an unlogged dead state in between: HA's logbook drops the
    restart's first row (it has no old state), leaving `off, off`.
If that row's state differs from the current state, the 30 s logbook cache hasn't seen
the change yet, so `last_changed` is used (still exact). With no usable row in the
window, `last_changed` is used: exact if it is at most 60 s old (a change newer than the
cache), else `since_exact: false` with the age "> 12h" (older than the window).
Known limitation: when the restart row is the only row in the window (the door hasn't
changed in more than `lookbackHours`), it is accepted, so "since" reads as an exact time
at the restart.

Severity: open longer than `openAlertSec`, or open with an inexact "since" (open since
before the window) -> high; a brief opening stays normal. Unknown -> low.

Glyphs: door-open / door-closed per door, `door` when unknown; the tile glyph is
door-open if any door is open, else door-closed, and `active` is any door open.

`detail()` serves the tablet's detail panel (GET /api/detail/doors): "Now", each door's
state and since (the same restart-proof logic as the tile), and "Today", every opening
since local midnight from the contacts' state history, newest first, with how long it
stayed open ("open now" while it still is).
"""

from .. import blocks
from .. import config as cfg
from .. import history as hist
from ..net import stream_hls_base
from ..store import iso_epoch, now_s, rel_age

_DEFAULT_OPEN_ALERT_SEC = 300
_DEFAULT_LOOKBACK_HOURS = 12
_STATES = {"on": "open", "off": "closed"}
_GLYPHS = {"open": "door-open", "closed": "door-closed", "unknown": "door"}
_DEAD = ("unavailable", "unknown")
_FRESH_SEC = 60    # a last_changed this recent is newer than the 30 s logbook cache
_DEFAULT_CAMERA_SEC = 60


def values(ha, descriptor):
    ents = descriptor.get("entities", {}) or {}
    alert_sec = _int(descriptor.get("openAlertSec"), _DEFAULT_OPEN_ALERT_SEC)
    lookback = _int(descriptor.get("lookbackHours"), _DEFAULT_LOOKBACK_HOURS)
    now = now_s()

    configured = [d for d in (ents.get("doors") or []) if isinstance(d, dict)]
    doors = [_door(ha, d, alert_sec, lookback, now) for d in configured]
    open_count = sum(1 for d in doors if d["state"] == "open")
    stale = all(d["state"] == "unknown" for d in doors)   # also true with no doors

    out = {
        "doors": doors,
        "open_count": open_count,
        "stale": stale,
        "tile": _tile(doors, open_count, stale),
    }
    takeover = _takeover(ha, descriptor.get("camera"), configured, doors, now)
    if takeover:
        out["takeover"] = takeover
    return out


def _takeover(ha, cam, configured, doors, now):
    """The camera takeover for a door opened in the last `sec`, or None."""
    if not isinstance(cam, dict) or not cam.get("cam") or not hasattr(ha, "last_on"):
        return None
    for conf, door in zip(configured, doors):
        if door["id"] == cam.get("door") and conf.get("entity"):
            opened = ha.last_on(conf["entity"])
            sec = _int(cam.get("sec"), _DEFAULT_CAMERA_SEC)
            if opened is None or not (0 <= now - opened < sec):
                return None
            base = stream_hls_base()
            return {"cam": cam["cam"], "hls": f"{base}/{cam['cam']}.m3u8",
                    "label": cam.get("label") or door["label"], "until": opened + sec}
    return None


def _door(ha, d, alert_sec, lookback, now):
    eid = d.get("entity")
    st = (ha.get_state(eid) if eid else None) or {}
    raw = st.get("state")
    state = _STATES.get(raw, "unknown")

    rows = ha.get_logbook(eid, lookback) if eid else []
    since, exact = _since(rows, raw, iso_epoch(st.get("last_changed")), now)
    if since is None:
        age = None
    elif exact:
        age = rel_age(now - since)
    else:
        age = f"> {lookback}h"

    if state == "unknown":
        severity = "low"
    elif state == "open" and (not exact or (since is not None and now - since > alert_sec)):
        severity = "high"                      # inexact: open since before the window
    else:
        severity = "normal"

    return {
        "id": d.get("id"),
        "label": d.get("label") or str(d.get("id") or "").title(),
        "state": state,
        "since": since,
        "since_exact": exact,
        "age": age,
        "severity": severity,
        "glyph": _GLYPHS[state],
    }


def _since(rows, current, last_changed, now):
    """(since epoch, exact) from the logbook rows, the current raw state and last_changed."""
    row = _last_real_change(rows)
    if row is None:                            # no real change in the window...
        fresh = last_changed is not None and now - last_changed <= _FRESH_SEC
        return last_changed, fresh             # ...unless it's newer than the cache
    when, state = row
    if state != current:
        return last_changed, True              # a fresh change the cached logbook hasn't seen
    return when, True                          # survives an HA restart's re-stamp


def _last_real_change(rows):
    """(when, state) of the newest real open/close row, or None.

    Skips rows out of unavailable/unknown and rows repeating the previous row's state.
    """
    parsed = []
    for r in rows or []:
        when = iso_epoch(r.get("when")) if isinstance(r, dict) else None
        if when is not None:
            parsed.append((when, str(r.get("state") or "").lower()))
    parsed.sort(key=lambda p: p[0])            # stable: same-second rows keep HA's order

    best, prev = None, None
    for when, state in parsed:
        if state in _STATES and prev not in _DEAD and state != prev:
            best = (when, state)
        prev = state
    return best


# --- detail ----------------------------------------------------------------
_HISTORY_TTL = 60     # today's openings should keep up while the panel is open
_MAX_ROWS = 30        # the tablet clamps rows to 30
_STATE_LABELS = {"open": "Open", "closed": "Closed", "unknown": "Unknown"}


def detail(ha, descriptor, now):
    """The detail panel's blocks (tablet contract §1)."""
    tz = cfg.resolve_zone(descriptor.get("timezone"))
    configured = [d for d in ((descriptor.get("entities") or {}).get("doors") or [])
                  if isinstance(d, dict)]
    doors = values(ha, descriptor)["doors"]          # same order as `configured`
    out = [blocks.rows("Now", [_now_row(d, now, tz) for d in doors])] if doors else []

    midnight = hist.local_midnight(now, tz)
    ids = [d.get("entity") for d in configured if d.get("entity")]
    history = ha.get_history(ids, midnight, None, ttl=_HISTORY_TTL) if ids else {}
    spans = []
    for door, conf in zip(doors, configured, strict=True):
        rows = (history or {}).get(conf.get("entity"))
        spans += [(door, span) for span in hist.open_intervals(rows, midnight, now)]
    opens = sorted(spans, key=lambda p: p[1]["start"], reverse=True)[:_MAX_ROWS]
    note = None
    if history is None:
        note = "History unavailable"
    elif opens:
        out.append(blocks.rows("Today", [
            {"glyph": "door-open", "tone": "amber", "label": door["label"],
             "value": (f"before {hist.clock(midnight, tz)}" if span["clipped"]
                       else hist.clock(span["start"], tz)),
             "sub": "open now" if span["open"] else hist.duration(span["length"])}
            for door, span in opens]))
    else:
        note = "No doors opened today"
    return {"blocks": out, "note": note}


def _now_row(d, now, tz):
    if d["state"] == "unknown":
        sub = None
    elif d["since"] is not None and d["since_exact"]:
        sub = f"since {hist.when_label(d['since'], now, tz)} · {d['age']}"
    else:
        sub = d["age"]                                  # "> 12h": older than the logbook window
    return {"glyph": d["glyph"], "tone": _now_tone(d), "label": d["label"],
            "value": _STATE_LABELS[d["state"]], "sub": sub}


def _now_tone(d):
    if d["state"] == "open":
        return "coral" if d["severity"] == "high" else "amber"
    return "sage" if d["state"] == "closed" else "muted"


# --- tile ------------------------------------------------------------------
def _tile(doors, open_count, stale):
    opened = [d for d in doors if d["state"] == "open"]
    unknown = [d for d in doors if d["state"] == "unknown"]
    if stale:
        hero, featured = "No data", []
    elif opened:
        hero = f"{opened[0]['label']} open" if len(opened) == 1 else f"{len(opened)} open"
        featured = opened
    elif unknown:
        hero = f"{unknown[0]['label']} unknown" if len(unknown) == 1 else f"{len(unknown)} unknown"
        featured = unknown
    else:
        hero, featured = "All closed", []

    if len(featured) == 1:
        sub = featured[0]["age"] or ""                                    # "6m"
    else:
        sub = " · ".join(_join(d["label"], d["age"]) for d in featured)  # "Front 1m · Back 2m"

    if stale:
        detail = ""
    elif featured:                                                        # "Front closed · 12m"
        detail = "   ".join(_join(f"{d['label']} {d['state']}", d["age"], " · ")
                            for d in doors if d not in featured)
    else:
        detail = " · ".join(_join(d["label"], d["age"]) for d in doors)  # "Front 3h · Back 5h"

    return {
        "hero": hero,
        "sub": sub,
        "detail": detail,
        "severity": "high" if any(d["severity"] == "high" for d in doors) else "normal",
        "icon": "open" if open_count else ("unknown" if stale else "closed"),
        "glyph": "door-open" if open_count else "door-closed",
        "active": open_count > 0,
    }


def _join(text, age, sep=" "):
    return f"{text}{sep}{age}" if age else text


def _int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default
