"""Weather module: current conditions + today's high/low + a forecast card.

Values feed the native SceneGraph value tile; the forecast card is a server-rendered
PNG (charts.render_weather_forecast). Entities are read from the descriptor so the
module is portable — `entities.forecast` (a weather.* entity) and optional
`entities.indoor` (a second weather/climate entity for the inside temperature).

`detail()` serves the tablet's detail panel (GET /api/detail/weather) as two columns:
  left   `now` (glyph, temperature, condition, today's high/low, "Updated 2:05 PM"),
         the facts `rows` (feels-like from `entities.wind_chill`, humidity, wind (`entities.wind_speed`
         when the entity has none), pressure,
         sunrise/sunset from `entities.sun`) and the next 3 days as a compact `forecast`
  right  an `hourly` strip (the next 8 hours) over a `chart` of the outdoor temperature
         (`entities.outdoor_temp`): 24 h observed from long-term statistics, then the
         hourly forecast, meeting at a "Now" tick
Each block comes from its own source and fails alone: a forecast error costs the blocks
that need it, never the panel. The note carries the weather entity's attribution.
"""
import logging
from concurrent.futures import ThreadPoolExecutor

from .. import blocks, charts, glyphs, icons
from .. import config as cfg
from .. import history as hist
from ..store import iso_epoch

log = logging.getLogger(__name__)

_COND_LABELS = {
    "clear-night": "Clear", "cloudy": "Cloudy", "exceptional": "Severe",
    "fog": "Fog", "hail": "Hail", "lightning": "Thunder",
    "lightning-rainy": "Thunderstorms", "partlycloudy": "Partly Cloudy",
    "pouring": "Heavy Rain", "rainy": "Rainy", "snowy": "Snow",
    "snowy-rainy": "Wet Snow", "sunny": "Sunny", "windy": "Windy",
    "windy-variant": "Windy",
}

# Font Awesome Free "solid" glyph per HA condition — see icons.py/_GLYPHS.
_COND_ICONS = {
    "clear-night": "moon", "cloudy": "cloud", "exceptional": "circle",
    "fog": "smog", "hail": "cloud-showers-heavy", "lightning": "bolt",
    "lightning-rainy": "cloud-bolt", "partlycloudy": "cloud-sun",
    "pouring": "cloud-showers-heavy", "rainy": "cloud-rain", "snowy": "snowflake",
    "snowy-rainy": "snowflake", "sunny": "sun", "windy": "wind",
    "windy-variant": "wind",
}


def _label(condition):
    if not condition:
        return "Weather"
    return _COND_LABELS.get(condition, condition.replace("-", " ").title())


def _hhmm(iso):
    # "2026-07-05T13:17:00.123+00:00" -> "13:17" (best-effort, no tz conversion).
    try:
        t = iso.split("T", 1)[1]
        return t[:5]
    except Exception:
        return None


def values(ha, descriptor):
    ents = descriptor.get("entities", {})
    fc_entity = ents.get("forecast", "weather.edmonton_forecast")
    st = ha.get_state(fc_entity)

    dead = st is None or st.get("state") in (None, "unavailable", "unknown")
    condition = None if dead else st.get("state")
    a = (st or {}).get("attributes", {})

    forecast = ha.get_forecast(fc_entity) if not dead else []
    today = forecast[0] if forecast else {}

    temp_c = _round(a.get("temperature"))
    out = {
        "temp_c": temp_c,
        "condition": condition,
        "cond_label": _label(condition),
        "humidity": _round(a.get("humidity"), 0),
        "wind_kmh": _round(a.get("wind_speed"), 0),
        "high_c": _round(today.get("temperature")),
        "low_c": _round(today.get("templow")),
        "observed_hm": _hhmm((st or {}).get("last_updated", "")),
        "stale": dead or temp_c is None,   # a "--°" hero is always stale
    }

    indoor = ents.get("indoor")
    if indoor:
        ist = ha.get_state(indoor)
        if ist:
            out["indoor_c"] = _round(ist.get("attributes", {}).get("temperature"))

    # Display-ready projection for the native value tile — the sidecar owns
    # formatting (degree symbol, units) so the Roku tile stays generic/portable.
    out["tile"] = {
        "hero": f"{_int(out['temp_c'])}°" if out["temp_c"] is not None else "--°",
        "sub": out["cond_label"],
        "detail": _tile_detail(out),
        "severity": "normal",
        "icon": condition or "",
        "glyph": glyphs.weather_glyph(condition),    # tablet-only; the Roku ignores it
        "active": False,
    }
    return out


def _tile_detail(v):
    parts = []
    if v.get("high_c") is not None and v.get("low_c") is not None:
        parts.append(f"H {_int(v['high_c'])}°  L {_int(v['low_c'])}°")
    if v.get("humidity") is not None:
        parts.append(f"{v['humidity']}% RH")
    if v.get("indoor_c") is not None:
        parts.append(f"in {_int(v['indoor_c'])}°")
    return "   ".join(parts)


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return v


_FORECAST_DAYS = 3
_HOURLY_CELLS = 8
_COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
_FC_ENTITY = "weather.edmonton_forecast"
_OUTDOOR = "sensor.edmonton_weather_temperature"
_SUN = "sun.sun"
_WIND_SPEED = "sensor.edmonton_weather_wind_speed"
_BACK = _AHEAD = 24                        # chart hours either side of Now
_CHART_COUNT = _BACK + 1 + _AHEAD          # 49 hourly buckets; bucket _BACK is the current hour
_TICK_EVERY = 6                            # a labelled tick every 6 local hours
_NOW_ROOM = 5                              # ...but none this close to the "Now" label
_FIRST_FORECAST = 2                        # a forecast must start within this many buckets of Now
_CHART_TITLE = "Outdoor · last 24 h and next 24 h"
_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="weather-detail")


def detail(ha, descriptor, now):
    """The detail panel's blocks (tablet contract §1 + the weather panel spec)."""
    ents = descriptor.get("entities", {}) or {}
    tz = cfg.resolve_zone(descriptor.get("timezone"))
    fc_entity = ents.get("forecast", _FC_ENTITY)
    outdoor = ents.get("outdoor_temp", _OUTDOOR)
    st = ha.get_state(fc_entity)
    dead = st is None or st.get("state") in (None, "unavailable", "unknown")
    a = (st or {}).get("attributes", {}) or {}
    condition = None if dead else st.get("state")

    # The three slow reads run side by side. A dead entity gets no forecast calls.
    now_hour = hist.floor_hour(now)
    daily = None if dead else _POOL.submit(_isolated, ha.get_forecast, fc_entity, "daily")
    hourly = None if dead else _POOL.submit(_isolated, ha.get_forecast, fc_entity, "hourly")
    stats = _POOL.submit(_isolated, ha.get_statistics, [outdoor], now_hour - _BACK * hist.HOUR,
                         now_hour, "hour", ["mean"], units={"temperature": "°C"}, ttl=300)
    daily, hourly, stats = (f.result() if f else None for f in (daily, hourly, stats))
    daily, hourly = daily or [], hourly or []

    temp = blocks.num(a.get("temperature"))
    if temp is None:
        temp = blocks.state_num(ha, outdoor)[0]
    updated = iso_epoch((st or {}).get("last_updated") or (st or {}).get("last_changed"))
    left = [
        _isolated(_now_block, condition, temp, _today(daily, now, tz), updated, tz),
        _isolated(_facts_block, ha, a, ents, now, tz),
        _isolated(_outlook_block, daily, now, tz),
    ]
    right = [
        _isolated(_hourly_block, hourly, now, tz),
        _isolated(_chart_block, stats, outdoor, hourly, temp, now, tz),
    ]
    attribution = a.get("attribution")
    return {"note": attribution if isinstance(attribution, str) and attribution else None,
            "blocks": [b for b in [*(blocks.col(x, 0) for x in left),
                                   *(blocks.col(x, 1) for x in right)] if b]}


def _isolated(fn, *args, **kw):
    """`fn(...)`, or None (logged) when it raises: one bad source never blanks the panel."""
    try:
        return fn(*args, **kw)
    except Exception:
        log.exception("weather detail: %s failed", getattr(fn, "__name__", fn))
        return None


def _t(v):
    """'7°' (whole degrees, rounded like the tile hero), or None."""
    return None if v is None else f"{int(round(v))}°"


def _points(forecast):
    """[(epoch, row)] of the forecast rows that have a usable datetime, in time order."""
    out = []
    for f in forecast or []:
        t = iso_epoch(f.get("datetime")) if isinstance(f, dict) else None
        if t is not None:
            out.append((t, f))
    out.sort(key=lambda p: p[0])
    return out


def _today(daily, now, tz):
    """The daily row for today's local date (in the evening it is 'Tonight', with no high)."""
    today = hist.local_date(now, tz)
    return next((f for t, f in _points(daily) if hist.local_date(t, tz) == today), None)


def _now_block(condition, temp, today, updated, tz):
    hi, lo = (blocks.num(today.get(k)) for k in ("temperature", "templow")) if today else (None, None)
    hilo = "  ".join(p for p in (hi is not None and f"H {_t(hi)}", lo is not None and f"L {_t(lo)}") if p)
    return blocks.current(
        glyph=glyphs.weather_glyph(condition) if condition else None,
        temp=_t(temp) or "--°",
        cond=_label(condition) if condition else None,
        hilo=hilo or None,
        sub=f"Updated {hist.clock(updated, tz)}" if updated is not None else None)


def _row(label, value):
    return {"label": label, "value": value} if value else None


def _facts_block(ha, a, ents, now, tz):
    """Feels-like, humidity, wind, pressure, then the sun times: each only if it has a source."""
    chill, _u = blocks.state_num(ha, ents.get("wind_chill"))
    items = [
        _row("Feels like", _t(chill)),
        _row("Humidity", blocks.pct(blocks.num(a.get("humidity")))),
        _row("Wind", _wind_text(ha, a, ents)),
        _row("Pressure", _pressure(blocks.num(a.get("pressure")), a.get("pressure_unit"))),
        *_sun_rows(ha, ents.get("sun", _SUN), now, tz),
    ]
    items = [i for i in items if i]
    return blocks.rows(None, items) if items else None


def _wind_text(ha, a, ents):
    """'15 km/h NW', 'Calm', or None when nothing knows the speed.

    EnvCan leaves the weather entity's `wind_speed` empty when the wind is calm, and its
    own wind-speed sensor (`entities.wind_speed`) reads 0, so the entity is asked first and
    the sensor second. A speed that rounds to 0 is "Calm", with no bearing.
    """
    speed, unit = blocks.num(a.get("wind_speed")), a.get("wind_speed_unit")
    if speed is None:
        speed, sensor_unit = blocks.state_num(ha, ents.get("wind_speed", _WIND_SPEED))
        unit = sensor_unit or unit
    if speed is None:
        return None
    if round(speed) == 0:
        return "Calm"
    wind, compass = _wind(speed, unit), _compass(a.get("wind_bearing"))
    return f"{wind} {compass}" if compass else wind


def _pressure(v, unit):
    """'101.3 kPa', '1013 hPa', '29.92 inHg', or None."""
    if v is None:
        return None
    unit = unit or "kPa"
    if unit == "kPa":
        return f"{v:.1f} kPa"
    if unit == "inHg":
        return f"{v:.2f} inHg"
    return f"{round(v)} {unit}"


def _sun_rows(ha, entity, now, tz):
    """'Sunset 6:41 PM' / 'Sunrise Fri 7:30 AM' from sun.sun's next events, soonest first."""
    a = ((ha.get_state(entity) or {}).get("attributes") or {}) if entity else {}
    events = sorted((t, name) for t, name in ((iso_epoch(a.get("next_rising")), "Sunrise"),
                                              (iso_epoch(a.get("next_setting")), "Sunset"))
                    if t is not None)
    today = hist.local_date(now, tz)
    return [_row(name, hist.clock(t, tz) if hist.local_date(t, tz) == today
                 else f"{hist.weekday(hist.local_date(t, tz))} {hist.clock(t, tz)}")
            for t, name in events]


def _outlook_block(daily, now, tz):
    """The next 3 days after today's local date, as compact rows; None with no forecast."""
    today = hist.local_date(now, tz)
    days = []
    for t, f in _points(daily):
        if hist.local_date(t, tz) <= today:
            continue
        cond = f.get("condition")
        pop = blocks.num(f.get("precipitation_probability"))
        days.append({
            "label": hist.weekday(hist.local_date(t, tz)),
            "glyph": glyphs.weather_glyph(cond),
            "cond": _label(cond) if cond else None,
            "hi": _t(blocks.num(f.get("temperature"))),
            "lo": _t(blocks.num(f.get("templow"))),
            "sub": blocks.pct(pop) if pop else None,    # EnvCan reports a missing chance as 0
        })
        if len(days) == _FORECAST_DAYS:
            break
    return {"type": "forecast", "style": "compact", "days": days} if days else None


def _hourly_block(hourly, now, tz):
    """The next 8 hours starting at the next full hour, across midnight if need be."""
    first = hist.floor_hour(now) + hist.HOUR
    items, seen = [], set()
    for t, f in _points(hourly):
        temp = blocks.num(f.get("temperature"))
        if t < first or temp is None or hist.floor_hour(t) in seen:
            continue
        seen.add(hist.floor_hour(t))
        cond = f.get("condition")
        pop = blocks.num(f.get("precipitation_probability"))
        items.append({"label": hist.hour_label(t, tz), "glyph": glyphs.weather_glyph(cond) if cond else None,
                      "temp": _t(temp), "sub": blocks.pct(pop) if pop else None})
        if len(items) == _HOURLY_CELLS:
            break
    return blocks.hourly(items)


def _chart_block(stats, outdoor, hourly, temp, now, tz):
    """Outdoor temperature: 24 h observed + 24 h forecast on one hourly grid, joined at Now.

    Bucket `_BACK` is the current hour. Observed fills 0.._BACK-1 from hourly means, then
    takes the live reading as its last point; the forecast starts from that same point, so
    the lines meet. With fewer than two points the chart says why instead.
    """
    start = hist.floor_hour(now) - _BACK * hist.HOUR
    live = None if temp is None else round(temp, 1)
    observed = hist.runs((stats or {}).get(outdoor), "mean", start, hist.HOUR, _BACK, 1)
    if live is not None:
        observed = hist.splice_point(observed, _BACK, live)
    ahead = {}
    for t, f in _points(hourly):
        i, v = (t - start) // hist.HOUR, blocks.num(f.get("temperature"))
        if _BACK < i < _CHART_COUNT and v is not None:
            ahead[int(i)] = round(v, 1)
    forecast = []
    if ahead and min(ahead) <= _BACK + _FIRST_FORECAST:     # not a line across a hole in the forecast
        if live is not None:
            ahead[_BACK] = live
        forecast = hist.runs_from(ahead)
    series = [s for s in ({"label": "Observed", "tone": "ink", "runs": observed},
                          {"label": "Forecast", "tone": "cool", "runs": forecast}) if s["runs"]]
    values = [v for s in series for v in hist.run_values(s["runs"])]
    ticks = hist.clock_ticks(start, hist.HOUR, _CHART_COUNT, tz, every=_TICK_EVERY,
                             avoid=[_BACK], radius=_NOW_ROOM)
    ticks = sorted([*ticks, {"i": _BACK, "label": "Now", "strong": True}], key=lambda t: t["i"])
    chart = {"type": "chart", "title": _CHART_TITLE, "start": start, "step": hist.HOUR,
             "count": _CHART_COUNT, "x": {"ticks": ticks}}
    if len(values) >= 2:
        chart["series"] = series
        chart["y"] = hist.y_scale(values, "°", zero=False, whole=True)
    else:
        chart["series"] = [{"label": "Observed", "tone": "ink", "runs": []}]
        chart["empty"] = blocks.HISTORY_DOWN if stats is None and not forecast else blocks.NO_HISTORY
    return chart


def _wind(speed, unit):
    """'15 km/h', or None."""
    return None if speed is None else f"{round(speed)} {unit or 'km/h'}"


def _compass(bearing):
    """'NW' from a bearing in degrees (or a compass string passed through), else None."""
    b = blocks.num(bearing)
    if b is None:
        return bearing if isinstance(bearing, str) and bearing.isalpha() else None
    return _COMPASS[round(b / 45) % 8]


def _render_forecast(ha, descriptor, w, h):
    ents = descriptor.get("entities", {})
    fc_entity = ents.get("forecast", "weather.edmonton_forecast")
    st = ha.get_state(fc_entity)
    cond = (st or {}).get("state")
    current = {
        "temp_c": _round((st or {}).get("attributes", {}).get("temperature")),
        "condition": cond,
        "cond_label": _label(cond),
    }
    forecast = ha.get_forecast(fc_entity)
    return charts.render_weather_forecast(current, forecast, w, h)


CARDS = {"weather_forecast": _render_forecast}


def render_icon(ha, descriptor, w=96, h=96):
    ents = descriptor.get("entities", {})
    fc_entity = ents.get("forecast", "weather.edmonton_forecast")
    st = ha.get_state(fc_entity)
    condition = (st or {}).get("state")
    if not condition or condition in ("unavailable", "unknown"):
        return None  # stale -> 404 -> Roku hides the icon Poster gracefully
    glyph = _COND_ICONS.get(condition, icons.DEFAULT_GLYPH)
    return icons.render_glyph(glyph, w, h, color=charts.INK)


def _round(v, ndigits=1):
    try:
        f = round(float(v), ndigits)
        return int(f) if ndigits == 0 else f
    except (TypeError, ValueError):
        return None
