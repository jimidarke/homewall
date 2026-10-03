"""Pure helpers that turn HA history and long-term statistics into detail-panel data.

Nothing here talks to HA; the modules' `detail()` functions fetch through `ha.py` and
shape the answers with these. Everything is plain data in, plain data out, so the time
and DST rules are unit-tested directly (tests/test_history.py).

  statistics rows   -> `runs`: gap-safe stretches over uniform buckets. A chart can't
                       carry nulls (store.prune drops them inside lists and would shift
                       every later point), so a gap is simply where one run ends.
  window math       -> UTC hour floors, local midnights (zoneinfo, DST-safe), x ticks
                       at each local midnight labelled with its weekday.
  y scale           -> a "nice" min/max and labelled ticks ("0", "30 L", "-10°C").
  state history     -> spans: laundry runs (mode running/overtime) and door opens
                       (contact "on"), with unavailable/unknown rows ignored and a span
                       still going at the end of the window left open.
  labels            -> "6:05 PM", "Thu Oct 1 · 6:05 PM", "Thu", "4 PM", "58m", "1h 53m".

Statistics row `start`s arrive as epoch milliseconds (HA 2023.3+) or ISO strings
(older); history rows carry ISO `last_changed`. Both go through `ts_of`.
"""
import math
from datetime import datetime, timedelta

from .store import iso_epoch

HOUR = 3600
DAY = 86400
_DEAD = ("unavailable", "unknown", None, "")
_STEPS = (1, 2, 2.5, 5)
_WHOLE_STEPS = (1, 2, 5)
_EPS = 1e-9


# --- time ---------------------------------------------------------------------
def ts_of(v):
    """Epoch seconds for a statistics/history timestamp, or None.

    A number above 1e11 is epoch milliseconds (HA's websocket statistics), a smaller one
    epoch seconds; a string is ISO-8601.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        if not math.isfinite(v):
            return None
        return int(v / 1000) if abs(v) > 1e11 else int(v)
    return iso_epoch(v)


def floor_hour(t):
    """The start of the UTC hour holding epoch `t`."""
    return int(t) - int(t) % HOUR


def midnight(d, tz):
    """Epoch seconds of local midnight starting date `d` in `tz` (DST-safe)."""
    return int(datetime(d.year, d.month, d.day, tzinfo=tz).timestamp())


def local_date(t, tz):
    return datetime.fromtimestamp(t, tz).date()


def local_midnight(t, tz, days_back=0):
    """Epoch of the local midnight `days_back` days before the local day holding `t`."""
    return midnight(local_date(t, tz) - timedelta(days=days_back), tz)


# --- statistics -> chart ----------------------------------------------------------
def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def runs(rows, key, start, step, count, ndigits=3):
    """Statistics rows -> [{"i": first bucket, "v": [values...]}] over `count` buckets.

    A row lands in bucket (row start - `start`) // `step`; rows outside the window, or
    whose `key` value isn't a finite number, are skipped, and consecutive buckets join
    into one run. Values are rounded to `ndigits` (and -0.0 becomes 0.0).
    """
    vals = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        t, v = ts_of(r.get("start")), r.get(key)
        if t is None or not _number(v):
            continue
        i = (t - start) // step
        if 0 <= i < count:
            vals[int(i)] = round(float(v), ndigits) or 0.0
    return runs_from(vals)


def runs_from(vals):
    """{bucket: value} -> runs: consecutive buckets join, a missing bucket splits."""
    out = []
    for i in sorted(vals):
        if out and out[-1]["i"] + len(out[-1]["v"]) == i:
            out[-1]["v"].append(vals[i])
        else:
            out.append({"i": i, "v": [vals[i]]})
    return out


def splice_point(series_runs, i, v):
    """`series_runs` with bucket `i` set to `v` (a new list; the input is untouched).

    Used to put the live reading on the "now" bucket: it extends the run that ends just
    before it, replaces a value already there, or bridges two runs.
    """
    vals = {k + r["i"]: x for r in series_runs for k, x in enumerate(r["v"])}
    vals[i] = v
    return runs_from(vals)


def run_values(series_runs):
    """Every value in a list of runs (for scaling)."""
    return [v for r in series_runs for v in r["v"]]


def daily(rows, key, tz):
    """Statistics rows with period "day" -> {local date: value} (non-numbers skipped)."""
    out = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        t, v = ts_of(r.get("start")), r.get(key)
        if t is not None and _number(v):
            out[local_date(t, tz)] = float(v)
    return out


def midnight_ticks(start, step, count, tz):
    """[{"i": bucket, "label": "Thu"}] for each local midnight inside the window.

    The tick sits on the bucket holding that midnight and is labelled with the weekday
    the midnight starts. DST days are 23 or 25 buckets long; zoneinfo places them.
    """
    end = start + step * count
    d = local_date(start, tz)
    ticks = []
    while True:
        m = midnight(d, tz)
        if m >= end:
            return ticks
        if m >= start:
            ticks.append({"i": int((m - start) // step), "label": weekday(d)})
        d += timedelta(days=1)


def clock_ticks(start, step, count, tz, every=6, avoid=(), radius=0):
    """[{"i": bucket, "label"}] at every local hour divisible by `every` inside the window.

    Midnight is labelled with the weekday it starts ("Sat"), the rest like "6 AM". It reads
    the local clock bucket by bucket, so a DST day needs no special case. Buckets within
    `radius` of any index in `avoid` get no tick (room for a "Now" label). A zone whose
    buckets don't land on the hour (UTC+5:45) gets none.
    """
    ticks = []
    for i in range(count):
        dt = datetime.fromtimestamp(start + i * step, tz)
        if dt.minute or dt.second or dt.hour % every:
            continue
        if any(abs(i - a) <= radius for a in avoid):
            continue
        ticks.append({"i": i, "label": weekday(dt.date()) if dt.hour == 0 else hour_label(dt)})
    return ticks


def _candidate_steps(raw, steps=_STEPS):
    e = math.floor(math.log10(raw)) - 1
    while True:
        for m in steps:
            yield m * 10 ** e
        e += 1


def y_scale(values, unit, zero=True, max_ticks=6, whole=False):
    """A nice y axis for `values`: {"min", "max", "ticks": [{"v", "label"}]}, or None.

    `zero` keeps 0 inside the range (counters) and labels it a bare "0"; temperatures
    pass zero=False and may go negative ("-10°C"). About four intervals, at most
    `max_ticks` ticks, steps of 1, 2, 2.5 or 5 x 10^n. `whole` keeps every tick a whole
    number (steps of 1, 2 or 5 x 10^n, never below 1): a temperature axis reads -5, 0, 5,
    not -2.5, 2.5.
    """
    vals = [float(v) for v in values if _number(v)]
    if not vals:
        return None
    lo, hi = min(vals), max(vals)
    if zero:
        lo, hi = min(lo, 0.0), max(hi, 0.0)
    if hi - lo < _EPS:
        lo, hi = (lo, lo + 1.0) if zero and lo == 0 else (lo - 1.0, hi + 1.0)
    raw = (hi - lo) / 4
    for step in _candidate_steps(raw, _WHOLE_STEPS if whole else _STEPS):
        if step < raw - _EPS or (whole and step < 1):
            continue
        a = math.floor(lo / step + _EPS) * step
        b = math.ceil(hi / step - _EPS) * step
        n = round((b - a) / step) + 1
        if n <= max_ticks:
            break
    ticks = [_clean(a + k * step) for k in range(n)]
    return {"min": ticks[0], "max": ticks[-1],
            "ticks": [{"v": v, "label": tick_label(v, unit, zero)} for v in ticks]}


def _clean(v):
    """Strip float noise; whole numbers become ints."""
    v = round(v, 6) or 0.0
    return int(v) if float(v).is_integer() else v


def num(v):
    """'30', '2.5', '0.125' (at most 3 decimals, no trailing zeros)."""
    v = _clean(v)
    return str(v) if isinstance(v, int) else f"{v:.3f}".rstrip("0").rstrip(".")


def tick_label(v, unit, bare_zero=True):
    if bare_zero and v == 0:
        return "0"
    sep = "" if unit.startswith("°") else " "
    return f"{num(v)}{sep}{unit}"


# --- state history -> spans ------------------------------------------------------
def _transitions(rows, start, end):
    """[(t, state)] in time order, clamped into [start, end]; dead states dropped."""
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        t, st = iso_epoch(r.get("last_changed")), r.get("state")
        if t is None or st in _DEAD:
            continue
        out.append((min(max(t, start), end), str(st)))
    out.sort(key=lambda p: p[0])   # stable: same-second rows keep HA's order
    return out


def spans(rows, start, end, on_states):
    """Stretches of history where the state is in `on_states`.

    Returns [{"start", "end", "length", "open", "clipped"}] oldest first. An
    unavailable/unknown row neither starts nor ends a span. A span still on at `end` is
    `open` (its `end` is None, its `length` runs to `end`); one already on at `start` is
    `clipped` (it began before the window, so its start and length are the window's).
    """
    out, begin = [], None
    for t, st in _transitions(rows, start, end):
        if st in on_states:
            if begin is None:
                begin = t
        elif begin is not None:
            out.append(_span(begin, t, start, False))
            begin = None
    if begin is not None:
        out.append(_span(begin, end, start, True))
    return out


def _span(begin, stop, start, still_on):
    return {"start": begin, "end": None if still_on else stop, "length": stop - begin,
            "open": still_on, "clipped": begin <= start}


def mode_runs(rows, start, end):
    """Laundry runs from a `sensor.laundry_<m>_mode` history (running or overtime)."""
    return spans(rows, start, end, ("running", "overtime"))


def open_intervals(rows, start, end):
    """Door opens from a binary_sensor contact history (`on` = open)."""
    return spans(rows, start, end, ("on",))


# --- labels ----------------------------------------------------------------------
def clock(t, tz):
    """'6:05 PM'."""
    dt = datetime.fromtimestamp(t, tz)
    return f"{dt.hour % 12 or 12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def hour_label(t, tz=None):
    """'4 PM' for an epoch (with `tz`) or an aware/naive datetime (without)."""
    dt = t if tz is None else datetime.fromtimestamp(t, tz)
    return f"{dt.hour % 12 or 12} {'AM' if dt.hour < 12 else 'PM'}"


def weekday(d):
    """'Thu' for a date."""
    return d.strftime("%a")


def dt_label(t, tz):
    """'Thu Oct 1 · 6:05 PM'."""
    dt = datetime.fromtimestamp(t, tz)
    return f"{dt.strftime('%a')} {dt.strftime('%b')} {dt.day} · {clock(t, tz)}"


def when_label(t, now, tz):
    """'6:05 PM' today, 'Wed 6:05 PM' within the last 6 days, else 'Thu Sep 24'."""
    d, today = local_date(t, tz), local_date(now, tz)
    if d == today:
        return clock(t, tz)
    if timedelta(0) < today - d < timedelta(days=7):
        return f"{weekday(d)} {clock(t, tz)}"
    return f"{weekday(d)} {d.strftime('%b')} {d.day}"


def duration(secs):
    """'<1m', '58m', '1h 53m', '2h' (floored to the minute)."""
    m = max(0, int(secs)) // 60
    if m < 1:
        return "<1m"
    if m < 60:
        return f"{m}m"
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if m else f"{h}h"


def days_back(today, n):
    """The `n` local dates before `today`, oldest first."""
    return [today - timedelta(days=k) for k in range(n, 0, -1)]

