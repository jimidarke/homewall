"""Calendar module: a merged Google-calendar agenda (daily / upcoming).

Auto-discovers every calendar.* entity (or a configured subset) and merges their
events into a day-grouped agenda. Timed events show a local ``h:mm AM/PM`` (the HA
``start.dateTime`` already carries the home's UTC offset, so the wall-clock in the
string IS local — no tz conversion needed, same trick as weather._hhmm); all-day
events show ``all day``. The native agenda tile shows the next few upcoming events
(static); the drill renders the full grouped list with TODAY / TOMORROW /
weekday-date ``header`` rows.

Portable: bind calendars via the descriptor's ``entities.calendars`` (omit the key
to merge ALL discovered calendars); per-calendar dot colour via ``entities.colors``.
Tunables: ``lookaheadDays`` (14), ``drillCap`` (40).
"""
from datetime import date, datetime

from .. import config as cfg

_BRAND_DOT = "0x5B8C7FFF"       # HK_BRAND — the default agenda dot
_DEFAULT_LOOKAHEAD = 14
_DRILL_CAP = 40


def values(ha, descriptor):
    ents = descriptor.get("entities", {}) or {}
    ids = _calendar_ids(ha, ents)
    lookahead = _int(descriptor.get("lookaheadDays"), _DEFAULT_LOOKAHEAD)
    cap = _int(descriptor.get("drillCap"), _DRILL_CAP)
    colors = ents.get("colors", {}) or {}

    events = []
    for cid in ids:
        for ev in (ha.get_calendar_events(cid, lookahead) or []):
            date_str, tm, sortk = _event_start(ev)
            if not date_str:
                continue
            events.append({
                "date": date_str,
                "time": tm,                                  # None => all-day
                "sort": sortk,
                "summary": (ev.get("summary") or "(busy)"),
                "dot": colors.get(cid, _BRAND_DOT),
            })
    # All-day events first within a day, then chronological.
    events.sort(key=lambda e: (e["date"], e["time"] is not None, e["sort"]))

    # Day boundaries follow the configured local timezone, not the sidecar host's
    # OS clock — the two commonly differ (host runs UTC, home doesn't).
    today = datetime.now(cfg.resolve_zone(descriptor.get("timezone"))).date()
    items = _grouped_items(events, today)[:cap]
    ev_rows = [it for it in items if it.get("kind") == "event"]

    return {
        "items": items,
        "count": len(events),
        "tile": _tile(ev_rows, events, today),
    }


# --- calendar resolution ---------------------------------------------------
def _calendar_ids(ha, ents):
    configured = ents.get("calendars")
    if configured:                                          # explicit filter
        return [c for c in configured if c]
    return [c.get("entity_id") for c in (ha.get_calendars() or [])
            if c.get("entity_id")]                          # merge-all


# --- event shaping ---------------------------------------------------------
def _event_start(ev):
    """Return (date 'YYYY-MM-DD', time 'h:mm AM/PM' | None all-day, sort_key)."""
    s = ev.get("start") or {}
    dt = s.get("dateTime")
    if dt:
        return dt[:10], _to12h(dt[11:16]), dt                # "2026-07-07T16:00:00-06:00"
    d = (s.get("date") or "")[:10]                           # all-day: {"date": "2026-07-07"}
    return d, None, d


def _to12h(hm):
    try:
        h, mn = int(hm[:2]), hm[3:5]
        ampm = "AM" if h < 12 else "PM"
        return f"{h % 12 or 12}:{mn} {ampm}"
    except (ValueError, IndexError):
        return hm or None


def _grouped_items(events, today):
    items = []
    last_date = None
    for e in events:
        if e["date"] != last_date:
            items.append({"kind": "header", "title": _day_label(e["date"], today)})
            last_date = e["date"]
        items.append({
            "kind": "event",
            "time": e["time"] or "all day",
            "title": e["summary"],
            "severity": "normal",
            "dot": e["dot"],
        })
    return items


def _day_label(date_str, today):
    d = _parse_date(date_str)
    if d is None:
        return date_str
    delta = (d - today).days
    if delta <= 0:
        return "TODAY"
    if delta == 1:
        return "TOMORROW"
    return f"{d.strftime('%a').upper()} · {d.strftime('%b').upper()} {d.day}"


def _tile(ev_rows, events, today):
    if not ev_rows:
        return {"hero": "—", "sub": "No upcoming events", "detail": "", "severity": "normal",
                "glyph": "calendar", "active": False}
    first = ev_rows[0]
    hero = first["title"] if first["time"] == "all day" else f"{first['time']}  {first['title']}"
    sub = ""
    if len(ev_rows) > 1:
        nxt = ev_rows[1]
        sub = ("then " + nxt["title"]) if nxt["time"] == "all day" \
            else f"then {nxt['time']}  {nxt['title']}"
    todays = sum(1 for e in events if e["date"] == today.isoformat())
    detail = f"{todays} today" if todays else "none left today"
    return {"hero": hero, "sub": sub, "detail": detail, "severity": "normal",
            "glyph": "calendar", "active": False}


# --- helpers ---------------------------------------------------------------
def _parse_date(date_str):
    try:
        return date(int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10]))
    except (ValueError, TypeError, IndexError):
        return None


def _int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default
