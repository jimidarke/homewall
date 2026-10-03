"""Detail-panel blocks for GET /api/detail/<id> (the tablet v3 contract, §1).

A detail payload is a list of typed blocks the tablet renders without knowing which
module sent them: `stats`, `chart`, `days`, `forecast`, `rows`, and the weather panel's
`now` and `hourly`. Any block may carry `col` (0 left, 1 right): with blocks in both
columns the tablet draws two, otherwise it stacks them. The modules' `detail()`
functions build them with the helpers here; `modules.module_detail` wraps them in the
envelope ({v, id, title, ts, note?, blocks}) and prunes None, so an optional key is
simply left as None here and never reaches the wire.

Every string is display-ready; only chart geometry (bucket indices and raw floats) is
left for the tablet to scale. HA calls fail soft: a failed statistics read gives a chart
with `empty: "History unavailable"`, never an exception.

Windows:
  chart  168 hourly buckets ending at the start of the current UTC hour
  days   the 6 previous local days from long-term statistics (period "day"), then a
         "Today" item from live states
"""
import math

from . import history as hist

CHART_HOURS = 168
PAST_DAYS = 6
CHART_TITLE = "Per hour · last 7 days"
NO_HISTORY = "No history yet"
HISTORY_DOWN = "History unavailable"
PLACEHOLDER = "--"


# --- values -------------------------------------------------------------------------
def money(v):
    """'$1.24', or None."""
    return None if v is None else f"${v:.2f}"


def estimate(v):
    """'$18.40 est.' (a month-to-date projection), or None."""
    return None if v is None else f"{money(v)} est."


def deg(v):
    """'21.3°', '21°' (one decimal at most), or None."""
    if v is None:
        return None
    r = round(float(v), 1) or 0.0
    return f"{int(r)}°" if r.is_integer() else f"{r}°"


def pct(v):
    """'48%', or None."""
    return None if v is None else f"{round(float(v))}%"


def num(v):
    """A float from an HA state or attribute, or None (unavailable, junk, inf/nan)."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def state_num(ha, entity_id):
    """(number, unit) of an entity's state; (None, None) when unset or unavailable."""
    st = ha.get_state(entity_id) if entity_id else None
    if not st or st.get("state") in (None, "unavailable", "unknown"):
        return None, None
    return num(st.get("state")), (st.get("attributes") or {}).get("unit_of_measurement")


# --- blocks -------------------------------------------------------------------------
def stat(label, value, sub=None):
    """One stats item; a None value shows the placeholder."""
    return {"label": label, "value": PLACEHOLDER if value is None else value, "sub": sub}


def stats(*items):
    """A `stats` block from items, skipping falsy ones.

    So `ents.get("monthly") and stat(...)` leaves out a stat whose entity isn't configured.
    """
    return {"type": "stats", "items": [i for i in items if i]}


def rows(title, items):
    return {"type": "rows", "title": title, "items": items}


def current(glyph, temp, cond=None, hilo=None, sub=None):
    """The weather panel's `now` hero: glyph, the big temperature, condition, "H 12°  L 3°"."""
    return {"type": "now", "glyph": glyph, "temp": temp, "cond": cond, "hilo": hilo, "sub": sub}


def hourly(items):
    """A strip of hour cells [{"label", "glyph"?, "temp", "sub"?}]; None (left out) when empty."""
    return {"type": "hourly", "items": items} if items else None


def col(block, n):
    """`block` placed in tablet column `n` (0 left, 1 right); None stays None."""
    if block is not None:
        block["col"] = n
    return block


def hour_window(now):
    """(start, end) of the 168-bucket hourly chart ending at the current hour's start."""
    end = hist.floor_hour(now)
    return end - CHART_HOURS * hist.HOUR, end


def chart(ha, series, now, tz, *, stat_type, unit, units=None, zero=True, ndigits=3,
          title=CHART_TITLE):
    """An hourly `chart` block over the last 168 hours from long-term statistics.

    `series` is [{"stat", "label", "tone", "fill"?}]; those without a `stat` are dropped,
    and with none left the block is None (left out). One websocket read covers all series.
    """
    series = [s for s in series if s.get("stat")]
    if not series:
        return None
    start, end = hour_window(now)
    result = ha.get_statistics([s["stat"] for s in series], start, end, "hour", [stat_type],
                               units=units)
    out = []
    for s in series:
        r = hist.runs((result or {}).get(s["stat"]), stat_type, start, hist.HOUR, CHART_HOURS,
                      ndigits)
        out.append({"label": s["label"], "tone": s["tone"], "fill": s.get("fill"), "runs": r})
    values = [v for s in out for v in hist.run_values(s["runs"])]
    return {
        "type": "chart",
        "title": title,
        "start": start,
        "step": hist.HOUR,
        "count": CHART_HOURS,
        "series": out,
        "x": {"ticks": hist.midnight_ticks(start, hist.HOUR, CHART_HOURS, tz)},
        "y": hist.y_scale(values, unit, zero=zero),
        "empty": None if values else (HISTORY_DOWN if result is None else NO_HISTORY),
    }


def days(ha, usage_stat, cost_stat, now, tz, *, fmt, today, today_cost, units=None):
    """A `days` strip: the 6 previous local days from statistics, then "Today" from live.

    `fmt` formats a usage value ("412 L"); a day with no statistic shows the placeholder,
    and a cost sub appears only where the cost statistic has that day. None (left out)
    when `usage_stat` isn't configured.
    """
    if not usage_stat:
        return None
    ids = [i for i in (usage_stat, cost_stat) if i]
    result = ha.get_statistics(ids, hist.local_midnight(now, tz, PAST_DAYS),
                               hist.local_midnight(now, tz), "day", ["change"], units=units) or {}
    use = hist.daily(result.get(usage_stat), "change", tz)
    cost = hist.daily(result.get(cost_stat), "change", tz) if cost_stat else {}
    items = [{"label": hist.weekday(d), "value": _fmt_or_placeholder(fmt, use.get(d)),
              "sub": money(cost.get(d))}
             for d in hist.days_back(hist.local_date(now, tz), PAST_DAYS)]
    items.append({"label": "Today", "value": _fmt_or_placeholder(fmt, today),
                  "sub": money(today_cost)})
    return {"type": "days", "items": items}


def _fmt_or_placeholder(fmt, v):
    return PLACEHOLDER if v is None else fmt(v)
