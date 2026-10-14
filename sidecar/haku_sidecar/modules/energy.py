"""Energy module: whole-house power + today's energy + today's cost.

Value tile only (no drill card). Reads three sensors from the descriptor's
`entities` map so the module is portable:
  entities.power         -> instantaneous demand sensor, reported in WATTS
  entities.daily_energy  -> today's cumulative energy, in kWh
  entities.cost          -> today's cumulative cost ($); falls back to
                            entities.cost_fallback if missing/unavailable
The sidecar owns all formatting (W->kW, units, "$", "today"/"so far"). Severity
flips to "high" when demand exceeds _SPIKE_KW, matching HAKU_DESIGN.md's ">5 kW"
energy-spike ambient push.

Optional descriptor field `tileStyle: "rate"` (the tablet layout) words the tile as
"now · today · cost": hero "0.9 kW", sub "32 kWh today", detail "$6.91 today". A
missing today or cost entity leaves that key out. Without the flag the output is
unchanged.

`detail()` serves the tablet's detail panel (GET /api/detail/energy): now / today / this
month stats, an hourly 7-day kWh chart and a 7-day strip with costs, from
`entities.stat_usage` / `stat_cost` long-term statistics plus the `monthly` and
`monthly_cost` live states.
"""

from .. import blocks, charts, icons
from .. import config as cfg

_SPIKE_KW = 5.0
_RATE = "rate"  # descriptor `tileStyle` for the tablet's "now · today · cost" tile
_KWH = {"energy": "kWh"}  # statistics unit conversion for the detail chart


def values(ha, descriptor):
    ents = descriptor.get("entities", {})

    power_w = _reading(ha, ents.get("power"))
    power_kw = round(power_w / 1000.0, 1) if power_w is not None else None
    daily_kwh = _int(_reading(ha, ents.get("daily_energy")))
    cost = _reading(ha, ents.get("cost"))
    if cost is None:
        cost = _reading(ha, ents.get("cost_fallback"))
    cost = round(cost, 2) if cost is not None else None

    stale = power_kw is None  # no instantaneous power = nothing to headline

    out = {"power_kw": power_kw, "daily_kwh": daily_kwh, "cost": cost, "stale": stale}

    spike = power_kw is not None and power_kw > _SPIKE_KW
    out["tile"] = {
        "hero": f"{power_kw:.1f} kW" if power_kw is not None else "-- kW",
        "sub": f"{daily_kwh} kWh today" if daily_kwh is not None else "",
        "detail": f"${cost:.2f} so far" if cost is not None else "",
        "severity": "high" if spike else "normal",
        "icon": str(icons.fill_bucket_pct(power_kw, _SPIKE_KW)) if power_kw is not None else "",
        # Layout keys (pre-0.11 Roku channels ignore them). `level` is the icon's bucket, as an int.
        "glyph": "flash",
        "active": False,
        "level": icons.fill_bucket_pct(power_kw, _SPIKE_KW) if power_kw is not None else None,
    }
    if descriptor.get("tileStyle") == _RATE:
        out["tile"].update(
            sub=f"{daily_kwh} kWh today" if daily_kwh is not None else None,
            detail=f"${cost:.2f} today" if cost is not None else None,
        )
    return out


def detail(ha, descriptor, now):
    """The detail panel's blocks (tablet contract §1)."""
    ents = descriptor.get("entities", {})
    tz = cfg.resolve_zone(descriptor.get("timezone"))
    v = values(ha, descriptor)
    monthly = _reading(ha, ents.get("monthly"))
    month_cost = _reading(ha, ents.get("monthly_cost"))
    return {"blocks": [
        blocks.stats(
            ents.get("power") and blocks.stat("Now", v["tile"]["hero"]),
            ents.get("daily_energy") and blocks.stat("Today", _fmt_kwh(v["daily_kwh"]),
                                                     blocks.money(v["cost"])),
            ents.get("monthly") and blocks.stat("This month", _fmt_kwh(monthly),
                                                blocks.estimate(month_cost)),
        ),
        blocks.chart(ha, [{"stat": ents.get("stat_usage"), "label": "Energy", "tone": "amber",
                           "fill": True}],
                     now, tz, stat_type="change", unit="kWh", units=_KWH),
        blocks.days(ha, ents.get("stat_usage"), ents.get("stat_cost"), now, tz,
                    fmt=_fmt_kwh, today=v["daily_kwh"], today_cost=v["cost"], units=_KWH),
    ]}


def _fmt_kwh(v):
    return None if v is None else f"{round(v)} kWh"


def render_icon(ha, descriptor, w=96, h=96):
    power_w = _reading(ha, descriptor.get("entities", {}).get("power"))
    if power_w is None:
        return None
    power_kw = power_w / 1000.0
    frac = min(1.0, power_kw / _SPIKE_KW)
    color = charts.HIGH if power_kw > _SPIKE_KW else charts.BRAND
    return icons.render_battery(frac, w, h, color=color)


def _reading(ha, entity_id):
    """Numeric state of `entity_id`, or None if unset/unavailable/non-numeric."""
    if not entity_id:
        return None
    st = ha.get_state(entity_id)
    if st is None or st.get("state") in (None, "unavailable", "unknown"):
        return None
    return _num(st.get("state"))


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None
