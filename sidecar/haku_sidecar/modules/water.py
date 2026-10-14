"""Water module: last-hour usage headline + flow / 24h / 30d detail.

Value tile only (no drill card). "Last hour / 24h / 30d" are PERIOD totals and
the sidecar does NOT fetch HA history -- so each period must already be the
CURRENT state of a utility_meter / statistics sensor, wired via the descriptor's
`entities` map (all optional; the module renders whatever exists):
  entities.hourly   -> usage so far this hour   (utility_meter, cycle hourly)
  entities.flow     -> instantaneous flow rate  (sensor.water_meter_flow)
  entities.daily    -> usage last 24h / today   (utility_meter, cycle daily)
  entities.monthly  -> usage last 30d / month   (utility_meter, cycle monthly)
  entities.total    -> lifetime meter total     (sensor.water_meter_total)
Missing/unavailable period sensors are omitted (None -> pruned, line skipped).
Units pass through from unit_of_measurement with a fallback. Severity flips to
"high" when flow > 0 (water running); see `runningSeverity` below.

Optional descriptor field `maxFlowLpm` sets the "full bucket" scale for the
home-tile icon's fill level (default 10 L/min if unset).

Optional descriptor field `runningSeverity` (low|normal|high, default "high") is the
severity reported while water is running. The default view keeps "high"; the tablet layout
(and the Roku layout, through its `tablet:` refs) sets "normal" so a shower or a washing machine doesn't paint the water card as an alert.

Optional descriptor field `tileStyle: "rate"` (the tablet layout) re-words the tile as
"now · today · cost": hero = the flow ("4.2 L/min", "0 L/min" idle), sub = "412 L today"
from `entities.daily`, detail = "$1.24 today" from `entities.cost_today`. A missing sub or
detail entity leaves that key out; `stale` is exactly "no flow". Without the flag the
output is unchanged.

`detail()` serves the tablet's detail panel (GET /api/detail/water): now / today / this
month stats, an hourly 7-day chart in litres and a 7-day strip with costs, from
`entities.stat_usage` / `stat_cost` long-term statistics (HA converts to L) plus
`cost_today`, `monthly` and `monthly_cost` live states.
"""

from .. import blocks, charts, icons
from .. import config as cfg

_UNIT_FALLBACK = "L"
_FLOW_UNIT_FALLBACK = "L/min"
_DEFAULT_MAX_FLOW_LPM = 10.0  # "full bucket" scale when descriptor.maxFlowLpm is unset
_SEVERITIES = ("low", "normal", "high")
_DEFAULT_RUNNING_SEVERITY = "high"  # the Roku's behaviour: water flowing wants attention
_RATE = "rate"  # descriptor `tileStyle` for the tablet's "now · today · cost" tile
_LITRES = {"volume": "L"}  # statistics unit conversion: the detail charts water in litres


def _max_flow(descriptor):
    v = descriptor.get("maxFlowLpm")
    n = _num(v)
    return n if n and n > 0 else _DEFAULT_MAX_FLOW_LPM


def _running_severity(descriptor):
    v = descriptor.get("runningSeverity")
    return v if v in _SEVERITIES else _DEFAULT_RUNNING_SEVERITY


def values(ha, descriptor):
    ents = descriptor.get("entities", {})

    hourly, hourly_u = _reading(ha, ents.get("hourly"))
    flow, flow_u = _reading(ha, ents.get("flow"), _FLOW_UNIT_FALLBACK)
    daily, daily_u = _reading(ha, ents.get("daily"))
    monthly, monthly_u = _reading(ha, ents.get("monthly"))
    total, total_u = _reading(ha, ents.get("total"))

    running = flow is not None and flow > 0
    stale = hourly is None  # the hero is the hourly total, so no hourly = a placeholder hero

    out = {
        "hourly": _round1(hourly), "flow": _round1(flow), "daily": _round1(daily),
        "monthly": _round1(monthly), "total": _round1(total),
        "running": running, "stale": stale,
    }

    hero = _fmt(hourly, hourly_u)
    out["tile"] = {
        "hero": hero if hero is not None else "-- " + _UNIT_FALLBACK,
        "sub": _sub(running, flow, flow_u),
        "detail": _detail(daily, daily_u, monthly, monthly_u),
        "severity": _running_severity(descriptor) if running else "normal",
        "icon": str(icons.fill_bucket_pct(flow, _max_flow(descriptor))) if flow is not None else "",
        # Layout keys (pre-0.11 Roku channels ignore them). `level` is the icon's bucket, as an int.
        "glyph": "water" if running else "water-outline",
        "active": running,
        "level": icons.fill_bucket_pct(flow, _max_flow(descriptor)) if flow is not None else None,
    }
    if descriptor.get("tileStyle") == _RATE:
        cost = _cost(ha, ents.get("cost_today"))
        out["cost_today"] = cost
        out["stale"] = flow is None
        out["tile"].update(
            hero=_rate(flow, flow_u),
            sub=f"{round(daily)} {daily_u} today" if daily is not None else None,
            detail=f"${cost:.2f} today" if cost is not None else None,
        )
    return out


def detail(ha, descriptor, now):
    """The detail panel's blocks (tablet contract §1)."""
    ents = descriptor.get("entities", {})
    tz = cfg.resolve_zone(descriptor.get("timezone"))
    flow, flow_u = _reading(ha, ents.get("flow"), _FLOW_UNIT_FALLBACK)
    daily = _litres(*_reading(ha, ents.get("daily")))
    monthly, monthly_u = _reading(ha, ents.get("monthly"))
    cost_today = _cost(ha, ents.get("cost_today"))
    month_cost = _cost(ha, ents.get("monthly_cost"))
    return {"blocks": [
        blocks.stats(
            ents.get("flow") and blocks.stat("Now", _rate(flow, flow_u)),
            ents.get("daily") and blocks.stat("Today", _fmt_litres(daily), blocks.money(cost_today)),
            ents.get("monthly") and blocks.stat("This month", _fmt_cubic(monthly, monthly_u),
                                                blocks.estimate(month_cost)),
        ),
        blocks.chart(ha, [{"stat": ents.get("stat_usage"), "label": "Water", "tone": "water",
                           "fill": True}],
                     now, tz, stat_type="change", unit="L", units=_LITRES, ndigits=1),
        blocks.days(ha, ents.get("stat_usage"), ents.get("stat_cost"), now, tz,
                    fmt=_fmt_litres, today=daily, today_cost=cost_today, units=_LITRES),
    ]}


def render_icon(ha, descriptor, w=96, h=96):
    flow, _u = _reading(ha, descriptor.get("entities", {}).get("flow"), _FLOW_UNIT_FALLBACK)
    if flow is None:
        return None
    frac = min(1.0, flow / _max_flow(descriptor)) if flow > 0 else 0.0
    color = charts.BRAND if flow > 0 else charts.MUTED
    return icons.render_bucket(frac, w, h, color=color)


def _sub(running, flow, flow_u):
    if running:
        return "flowing " + _fmt(flow, flow_u)
    if flow is not None:
        return "idle"
    return ""


def _detail(daily, daily_u, monthly, monthly_u):
    parts = []
    d = _fmt(daily, daily_u)
    if d is not None:
        parts.append("24h " + d)
    mo = _fmt(monthly, monthly_u)
    if mo is not None:
        parts.append("30d " + mo)
    return "   ".join(parts)


def _rate(flow, unit):
    """Rate hero: '4.2 L/min', '0 L/min' for an exact 0, '-- L/min' when missing."""
    if flow is None:
        return "-- " + _FLOW_UNIT_FALLBACK
    return f"0 {unit}" if flow == 0 else f"{flow:.1f} {unit}"


def _litres(val, unit):
    """A volume in litres (m³ readings are converted), or None."""
    if val is None:
        return None
    return val * 1000 if unit in ("m³", "m3") else val


def _fmt_litres(v):
    return None if v is None else f"{round(v)} L"


def _fmt_cubic(val, unit):
    """'6.1 m³' from a litre or m³ reading, or None."""
    if val is None:
        return None
    return f"{(val if unit in ('m³', 'm3') else val / 1000):.1f} m³"


def _cost(ha, entity_id):
    """Cost to the cent, or None when the entity is unset or unavailable (no price)."""
    v, _u = _reading(ha, entity_id)
    return None if v is None else round(v, 2)


def _reading(ha, entity_id, unit_default=_UNIT_FALLBACK):
    """(value, unit) for `entity_id`; (None, unit_default) if unset/unavailable."""
    if not entity_id:
        return None, unit_default
    st = ha.get_state(entity_id)
    if st is None or st.get("state") in (None, "unavailable", "unknown"):
        return None, unit_default
    unit = (st.get("attributes", {}) or {}).get("unit_of_measurement") or unit_default
    return _num(st.get("state")), unit


def _fmt(val, unit):
    """'12 L' / '4.2 L/min'; None (drops the line) when val is missing."""
    if val is None:
        return None
    n = int(val) if float(val).is_integer() else round(val, 1)
    return f"{n} {unit}"


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _round1(v):
    return None if v is None else round(v, 1)
