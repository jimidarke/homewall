"""Recent Activity module: a coalesced HA-logbook timeline of *watched* entities.

The watched-entities framework. ``entities.watch`` is a curated list of entity ids
(doors, motion, presence, ...). HA's REST logbook filter is single-entity, so we
fetch each watched entity's logbook, merge, sort newest-first, and — critically —
COALESCE consecutive rows of the same entity within ``coalesceWindowSec``. Motion
sensors flap on/off every few seconds (the whole-house logbook is ~4000 rows / 8h),
so without coalescing + a per-class transition policy the card is unreadable.

Doors and windows don't go through the newest-wins coalescing: each opening is paired
with its close and shown as one row stamped at the opening ("opened · <1m", "open now"),
and openings within ``coalesceWindowSec`` of each other merge ("opened 3×"). Without
this a quick in-and-out read as "closed" (2026-10-03 audit: 90% of front-door openings).

Logbook rows here are minimal (``{state, entity_id, name, when}``), so the human
phrase is composed from the entity's ``device_class`` (read from the states cache)
+ the new state. The native agenda tile ROLLS through the most recent events; the
drill shows the full list grouped by section (TODAY / YESTERDAY / weekday-date).

All curation is config — no code change:
  watch[]            curated entity ids (empty => whole-house, discouraged/noisy)
  lookbackHours      history window (12)
  coalesceWindowSec  collapse same-entity bursts within N seconds (300)
  drillCap           max rows in the drill (50)
  labels{eid:name}   friendly-name overrides
  states{eid:[...]}  surface only these new states for that entity (e.g. a laundry
                     mode sensor -> ["done"]); other edges are dropped
  glyphs{eid:name}   tablet glyph overrides
  openAlertSec       a door/window open longer than this (or still open) is `high` (300)
"""
from datetime import datetime, timezone

from .. import config as cfg
from .. import history as hist
from ..store import iso_epoch, rel_age

_DEFAULT_LOOKBACK = 12
_DEFAULT_COALESCE = 300
_DEFAULT_DRILL_CAP = 50
_DEFAULT_OPEN_ALERT = 300

# device_class values that flap and should surface only their "active" edge.
_MOTIONISH = ("motion", "occupancy", "presence", "moving", "vibration", "sound")
_OPENABLE = ("door", "garage_door", "window", "opening")
_DEAD_STATES = ("unavailable", "unknown", "none", "")


def values(ha, descriptor):
    ents = descriptor.get("entities", {}) or {}
    watch = ents.get("watch") or []
    labels = ents.get("labels", {}) or {}
    only = ents.get("states", {}) or {}
    glyphs = ents.get("glyphs", {}) or {}
    lookback = _int(descriptor.get("lookbackHours"), _DEFAULT_LOOKBACK)
    coalesce_win = _int(descriptor.get("coalesceWindowSec"), _DEFAULT_COALESCE)
    cap = _int(descriptor.get("drillCap"), _DEFAULT_DRILL_CAP)
    alert = _int(descriptor.get("openAlertSec"), _DEFAULT_OPEN_ALERT)

    rows = []
    for eid in watch:
        dclass = ha.attr(eid, "device_class") or _domain(eid)
        for r in (ha.get_logbook(eid, lookback) or []):
            when = iso_epoch(r.get("when"))
            if when is None:
                continue
            rows.append({
                "eid": eid,
                "when": when,
                "state": str(r.get("state") or "").lower(),
                "name": labels.get(eid) or r.get("name") or _pretty(eid),
                "dclass": dclass,
            })

    rows = _drop_repeats(rows)                         # HA/Zigbee restarts replay the same state
    openable = [r for r in rows if r["dclass"] in _OPENABLE]
    rows = [r for r in rows if r["dclass"] not in _OPENABLE]
    rows.sort(key=lambda x: x["when"], reverse=True)   # newest first
    rows = [r for r in rows if _keep(r, only)]         # transition policy
    rows = _coalesce(rows, coalesce_win)               # collapse flapping bursts
    rows += _openings(openable, ha, coalesce_win, alert)
    rows.sort(key=lambda x: x["when"], reverse=True)

    now = _now_epoch()
    events = [_to_item(r, now, glyphs) for r in rows][:cap]
    return {
        "items": _sectioned(events, now, descriptor.get("timezone")),
        "count": len(events),
        "tile": _tile(events),
    }


# --- noise control ---------------------------------------------------------
def _keep(r, only=None):
    """Transition policy: which state changes are worth surfacing."""
    st = r["state"]
    if st in _DEAD_STATES:
        return False
    if only and r["eid"] in only:
        return st in only[r["eid"]]
    if r["dclass"] in _MOTIONISH:
        return st in ("on", "detected", "home")        # drop the "off"/"clear" edge
    return True


def _drop_repeats(rows):
    """Drop rows that only repeat their entity's last real state.

    When HA or Zigbee2MQTT restarts, every contact, sensor and person goes unavailable
    and comes back in the state it had. The logbook leaves the dead state out, so the
    return reads as a fresh "Front Door closed" (2026-10-01: three at every restart).
    A row is kept only if its state differs from the entity's previous non-dead state,
    so a real change across an outage (open, unavailable, closed) still shows. The first
    row of each entity in the window has nothing to compare with and is kept. Motion-like
    sensors are left alone: only their "on" edge shows, and `_coalesce` already merges
    their bursts.
    """
    last = {}
    kept = []
    for r in sorted(rows, key=lambda x: x["when"]):    # stable: same-second rows keep HA's order
        st = r["state"]
        if st in _DEAD_STATES or r["dclass"] in _MOTIONISH:
            kept.append(r)                             # _keep and _coalesce handle these
            continue
        if last.get(r["eid"]) == st:
            continue
        last[r["eid"]] = st
        kept.append(r)
    return kept


def _coalesce(rows, win):
    """Drop older same-entity rows within `win` s of a newer kept one (rows are desc)."""
    kept = []
    last_when = {}
    for r in rows:
        lw = last_when.get(r["eid"])
        if lw is not None and (lw - r["when"]) <= win:
            continue
        kept.append(r)
        last_when[r["eid"]] = r["when"]
    return kept


def _openings(rows, ha, win, alert):
    """Door/window rows -> one row per opening (or burst of openings), stamped at the open.

    Rows are already repeat-free. Per entity, oldest first: `on` starts an opening, the
    next `off` ends it; dead states in between don't end it. An `off` with no opening in
    the window (opened before it) stays a plain "closed" row. An opening with no close is
    "open now" only if HA still says `on`; otherwise the close is newer than the cached
    logbook, so it reads "opened" with no duration. Openings that start within `win` s of
    the previous one's close merge into one row at the newest opening.
    """
    by_eid = {}
    for r in sorted(rows, key=lambda x: x["when"]):
        by_eid.setdefault(r["eid"], []).append(r)

    out = []
    for eid, rs in by_eid.items():
        is_open = ((ha.get_state(eid) or {}).get("state") == "on")
        spans, start = [], None            # spans: [open_row, close_when | None]
        for r in rs:
            if r["state"] == "on" and start is None:
                start = r
            elif r["state"] == "off":
                if start is not None:
                    spans.append([start, r["when"]])
                    start = None
                else:
                    out.append(dict(r, sub="closed", severity="normal", glyph="door-closed"))
        if start is not None:
            spans.append([start, None])

        groups = []
        for sp in spans:
            prev = groups[-1][-1] if groups else None
            if prev is not None and prev[1] is not None and sp[0]["when"] - prev[1] <= win:
                groups[-1].append(sp)
            else:
                groups.append([sp])
        for g in groups:
            out.append(_opening_row(g, is_open, alert))
    return out


def _opening_row(group, is_open, alert):
    newest, close = group[-1]
    still_open = close is None and is_open
    long_open = any(c is not None and c - o["when"] > alert for o, c in group)
    if len(group) > 1:
        sub = f"opened {len(group)}×" + (" · open now" if still_open else "")
    elif still_open:
        sub = "open now"
    elif close is not None:
        sub = f"opened · {hist.duration(close - newest['when'])}"
    else:
        sub = "opened"
    return dict(newest, sub=sub, severity="high" if still_open or long_open else "normal",
                glyph="door-open" if still_open else "door-closed")


# --- item shaping ----------------------------------------------------------
def _to_item(r, now, glyphs=None):
    item = {
        "kind": "event",
        "time": rel_age(now - r["when"]),
        "title": r["name"],
        "sub": r.get("sub") or _phrase(r["state"], r["dclass"], r["eid"]),
        "severity": r.get("severity") or _sev(r["state"], r["dclass"], r["eid"]),
        "when": r["when"],
    }
    glyph = ((glyphs or {}).get(r["eid"]) or r.get("glyph")
             or _glyph(r["state"], r["dclass"], r["eid"]))
    if glyph:                                       # tablet-only; no mapping => key omitted
        item["glyph"] = glyph
    return item


def _phrase(state, dclass, eid):
    if dclass in _OPENABLE:
        return "opened" if state == "on" else "closed"
    if dclass in _MOTIONISH:
        return "motion" if state in ("on", "detected") else "clear"
    if dclass == "lock":
        return "unlocked" if state == "unlocked" else "locked"
    if _domain(eid) == "person":
        return "→ " + _loc(state)                  # "→ home"
    if state in ("on", "off"):
        return state
    return state.replace("_", " ")


def _sev(state, dclass, eid):
    if dclass in _OPENABLE:
        return "high" if state == "on" else "normal"   # a door opening wants attention
    if _domain(eid) == "person":
        return "low" if state == "home" else "normal"  # arrival = ok/green
    return "normal"


def _glyph(state, dclass, eid):
    """MDI glyph for an event, or None. Branches mirror `_phrase` so glyph and phrase agree."""
    if dclass in _OPENABLE:
        return "door-open" if state == "on" else "door-closed"
    if dclass in _MOTIONISH:
        return "motion-sensor" if state in ("on", "detected") else "motion-sensor-off"
    if dclass == "lock":
        return "lock-open-variant" if state == "unlocked" else "lock"
    if _domain(eid) == "person":
        # Only "home" is home; not_home, away and any named zone ("work") all mean away.
        return "home-account" if state == "home" else "account-arrow-right"
    return None


def _loc(state):
    if state == "home":
        return "home"
    if state in ("not_home", "away"):
        return "away"
    return state.replace("_", " ").title()


# --- drill sectioning ------------------------------------------------------
def _sectioned(events, now, tz_name):
    items = []
    last = None
    for it in events:
        sec = _section(it["when"], now, tz_name)
        if sec != last:
            items.append({"kind": "header", "title": sec})
            last = sec
        items.append(it)
    return items


def _section(when, now, tz_name):
    # Day boundaries follow the configured local timezone, not the sidecar
    # host's OS clock — the two commonly differ (host runs UTC, home doesn't).
    tz = cfg.resolve_zone(tz_name)
    d = datetime.fromtimestamp(when, tz).date()
    today = datetime.fromtimestamp(now, tz).date()
    delta = (today - d).days
    if delta <= 0:
        return "TODAY"
    if delta == 1:
        return "YESTERDAY"
    return f"{d.strftime('%a').upper()} · {d.strftime('%b').upper()} {d.day}"


def _tile(events):
    if not events:
        return {"hero": "—", "sub": "No recent activity", "detail": "", "severity": "normal",
                "glyph": "history", "active": False}
    top = events[0]
    detail = f"{events[1]['title']} · {events[1]['time']}" if len(events) > 1 else ""
    return {
        "hero": top["title"],
        "sub": f"{top['sub']} · {top['time']}",
        "detail": detail,
        "severity": top["severity"],
        "glyph": "history",
        "active": False,
    }


# --- helpers ---------------------------------------------------------------
def _domain(eid):
    return eid.split(".", 1)[0] if "." in eid else ""


def _pretty(eid):
    return eid.split(".", 1)[-1].replace("_", " ").title()


def _now_epoch():
    return int(datetime.now(timezone.utc).timestamp())


def _int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default
