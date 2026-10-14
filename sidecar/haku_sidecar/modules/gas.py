"""Gas module: instantaneous flow rate headline + lifetime meter total.

Value tile only (no drill card). Two sensors, wired via the descriptor's
`entities` map so the module stays portable (no hardcoded HA entity ids):
  entities.flow   -> instantaneous flow rate  (sensor.home_gas_usage, m3/h)
  entities.total  -> lifetime meter total     (sensor.gas_meter_..., m3)
Units pass through from unit_of_measurement with a fallback, same as
water.py's _reading() -- unlike energy.py, nothing here hardcodes W/kWh.
No cost: HA exposes sensor.home_gas_volume_cost but it's `unavailable`
(restored-only) on this install, so unlike energy's cost this module simply
never reads a cost entity -- no fallback/omission dance needed.

Severity is always "normal": unlike water (flow>0 can mean a leak) or energy
(a >5kW draw is a load spike), gas flow has no abnormal threshold worth
alerting on -- the furnace/water heater cycling on is the routine, expected
reason flow is ever nonzero, so escalating severity here would just be noise.

Optional descriptor field `maxFlowM3h` sets the "full" scale for the
home-tile icon's fill level (default 2.0 m3/h if unset).

Optional descriptor field `tileStyle: "rate"` (the tablet layout) words the tile as
"now · today · cost": hero "0.8 m³/h" ("0 m³/h" when idle, i.e. not running), sub
"3.1 m³ today" from `entities.daily`, detail "$1.05 today" from `entities.cost_today`
(a gas price in HA is optional, so this is often left out). A missing sub or detail
entity leaves that key out. Without the flag the output is unchanged.

`detail()` serves the tablet's detail panel (GET /api/detail/gas): now / today / this
month stats (costs when HA knows a gas price), an hourly 7-day m³ chart and a 7-day strip,
from `entities.stat_usage` / `stat_cost` long-term statistics plus the `daily`,
`cost_today`, `monthly` and `monthly_cost` live states.
"""

from .. import blocks, charts, icons
from .. import config as cfg

_UNIT_FALLBACK = "m³/h"
_TOTAL_UNIT_FALLBACK = "m³"
_DEFAULT_MAX_FLOW_M3H = 2.0  # "full" scale when descriptor.maxFlowM3h is unset
_RATE = "rate"  # descriptor `tileStyle` for the tablet's "now · today · cost" tile
_CUBIC = {"volume": "m³"}  # statistics unit conversion for the detail chart


def _max_flow(descriptor):
    v = descriptor.get("maxFlowM3h")
    n = _num(v)
    return n if n and n > 0 else _DEFAULT_MAX_FLOW_M3H


def values(ha, descriptor):
    ents = descriptor.get("entities", {})

    flow, flow_u = _reading(ha, ents.get("flow"), _UNIT_FALLBACK)
    total, total_u = _reading(ha, ents.get("total"), _TOTAL_UNIT_FALLBACK)

    stale = flow is None  # the hero is the flow, so no flow = a placeholder hero
    # "Running" is judged on the displayed rate: a 0.04 trickle shows "0.0" so it is not running.
    running = flow is not None and round(flow, 1) > 0

    out = {"flow": _round1(flow), "total": _round1(total), "stale": stale}

    out["tile"] = {
        "hero": f"{flow:.1f} {flow_u}" if flow is not None else "-- " + _UNIT_FALLBACK,
        "sub": "running" if running else "",
        "detail": _fmt_total(total, total_u) or "",
        "severity": "normal",
        "icon": str(icons.fill_bucket_pct(flow, _max_flow(descriptor))) if flow is not None else "",
        # Layout keys (pre-0.11 Roku channels ignore them). `level` is the icon's bucket, as an int.
        "glyph": "fire" if running else "meter-gas",
        "active": running,
        "level": icons.fill_bucket_pct(flow, _max_flow(descriptor)) if flow is not None else None,
    }
    if descriptor.get("tileStyle") == _RATE:
        daily, daily_u = _reading(ha, ents.get("daily"), _TOTAL_UNIT_FALLBACK)
        cost = _cost(ha, ents.get("cost_today"))
        out["daily"] = _round1(daily)
        out["cost_today"] = cost
        out["tile"].update(
            hero=_rate(flow, flow_u, running),
            sub=f"{daily:.1f} {daily_u} today" if daily is not None else None,
            detail=f"${cost:.2f} today" if cost is not None else None,
        )
    return out


def detail(ha, descriptor, now):
    """The detail panel's blocks (tablet contract §1)."""
    ents = descriptor.get("entities", {})
    tz = cfg.resolve_zone(descriptor.get("timezone"))
    flow, flow_u = _reading(ha, ents.get("flow"), _UNIT_FALLBACK)
    running = flow is not None and round(flow, 1) > 0
    daily, _du = _reading(ha, ents.get("daily"), _TOTAL_UNIT_FALLBACK)
    monthly, _mu = _reading(ha, ents.get("monthly"), _TOTAL_UNIT_FALLBACK)
    cost_today = _cost(ha, ents.get("cost_today"))
    month_cost = _cost(ha, ents.get("monthly_cost"))
    return {"blocks": [
        blocks.stats(
            ents.get("flow") and blocks.stat("Now", _rate(flow, flow_u, running)),
            ents.get("daily") and blocks.stat("Today", _fmt_m3(daily), blocks.money(cost_today)),
            ents.get("monthly") and blocks.stat("This month", _fmt_m3(monthly),
                                                blocks.estimate(month_cost)),
        ),
        blocks.chart(ha, [{"stat": ents.get("stat_usage"), "label": "Gas", "tone": "heat",
                           "fill": True}],
                     now, tz, stat_type="change", unit="m³", units=_CUBIC),
        blocks.days(ha, ents.get("stat_usage"), ents.get("stat_cost"), now, tz,
                    fmt=_fmt_m3, today=daily, today_cost=cost_today, units=_CUBIC),
    ]}


def _fmt_m3(v):
    return None if v is None else f"{v:.1f} m³"


def _cost(ha, entity_id):
    """Cost to the cent, or None when the entity is unset or unavailable (no gas price)."""
    v, _u = _reading(ha, entity_id, "")
    return None if v is None else round(v, 2)


def render_icon(ha, descriptor, w=96, h=96):
    flow, _u = _reading(ha, descriptor.get("entities", {}).get("flow"), _UNIT_FALLBACK)
    if flow is None:
        return None
    frac = min(1.0, flow / _max_flow(descriptor)) if flow > 0 else 0.0
    # Bucket (not battery): gas's flow+total shape mirrors water's, and a fill
    # gauge reads more naturally for a metered volumetric flow than energy's
    # battery, which implies stored charge rather than throughput.
    color = charts.BRAND if flow > 0 else charts.MUTED
    return icons.render_bucket(frac, w, h, color=color)


def _rate(flow, unit, running):
    """Rate hero: '0.8 m³/h', '0 m³/h' when not running, '-- m³/h' when missing."""
    if flow is None:
        return "-- " + _UNIT_FALLBACK
    return f"{flow:.1f} {unit}" if running else f"0 {unit}"


def _reading(ha, entity_id, unit_default):
    """(value, unit) for `entity_id`; (None, unit_default) if unset/unavailable."""
    if not entity_id:
        return None, unit_default
    st = ha.get_state(entity_id)
    if st is None or st.get("state") in (None, "unavailable", "unknown"):
        return None, unit_default
    unit = (st.get("attributes", {}) or {}).get("unit_of_measurement") or unit_default
    return _num(st.get("state")), unit


def _fmt_total(val, unit):
    """'17 m³ total'; None when val is missing."""
    if val is None:
        return None
    return f"{int(round(val))} {unit} total"


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _round1(v):
    return None if v is None else round(v, 1)
