"""Climate module: thermostat headline (current temp + hvac action + mode).

Value tile only (no drill card, no accent icon — see render_icon note below).
One multi-attribute HA `climate.*` entity, wired via the descriptor's
`entities` map so the module stays portable:
  entities.thermostat -> the climate entity (e.g. climate.my_ecobee)

HA's climate domain has two related-but-distinct mode signals read straight
off the entity, no lookup table needed:
  state (aka hvac_mode)   -> the mode the thermostat is SET to (off/heat/cool/…)
  attributes.hvac_action  -> what the equipment is ACTUALLY doing right now
                             (idle/heating/cooling/fan/off)
`attributes.preset_mode` (home/away/sleep/wakeup/away_indefinitely, …) is a
free-form, integration-specific string; the sidecar title-cases it rather
than maintaining a label table like weather.py's _COND_LABELS, since a
thermostat's preset roster isn't a fixed enum the way HA's weather
condition is.

Severity is always "normal": informational card, not anomaly-driven -- there
is no "bad" hvac_action/preset_mode the way water's flow>0 or energy's >5kW
draw are, so a severity escalation here would have nothing to key off.

No render_icon: unlike energy/water's live-fill gauges, there's no existing
single-glyph accent for "thermostat" without adding a new Font Awesome glyph
to icons.py (out of scope here — see icons.py's _GLYPHS table). The module
simply has no `render_icon` attribute, same as calendar/timeline/cameras
today; modules/__init__.render_icon()'s `getattr(mod, "render_icon", None)`
already handles that gracefully (404 -> Roku hides the icon Poster).

Tablet-only tile keys: `glyph` (fire / snowflake / fan by hvac_action, else a thermostat)
and `active` (heating or cooling; fan-only circulation is not an activity). There is still
no `tile.icon`.

`detail()` serves the tablet's detail panel (GET /api/detail/climate): indoor, outdoor,
humidity, mode/action and set-point stats, and a 7-day chart of hourly mean temperature,
indoor (`entities.indoor_temp`, tone heat) against outdoor (`entities.outdoor_temp`,
tone cool), from long-term statistics in °C.
"""
from .. import blocks
from .. import config as cfg

# hvac_action -> MDI glyph. Fan keeps its glyph but is not "active" (see _ACTIVE_ACTIONS).
_ACTION_GLYPHS = {"heating": "fire", "cooling": "snowflake", "fan": "fan"}
_ACTIVE_ACTIONS = ("heating", "cooling")
_IDLE_GLYPH = "thermostat"


def values(ha, descriptor):
    ents = descriptor.get("entities", {})
    entity_id = ents.get("thermostat")
    st = ha.get_state(entity_id) if entity_id else None

    dead = st is None or st.get("state") in (None, "unavailable", "unknown")
    hvac_mode = None if dead else st.get("state")
    a = (st or {}).get("attributes", {})

    current_temp = _num(a.get("current_temperature"))
    stale = dead or current_temp is None  # a "--°" hero is always stale
    humidity = _int(a.get("current_humidity"))
    hvac_action = a.get("hvac_action")
    preset_mode = a.get("preset_mode")

    out = {
        "current_temp": current_temp, "humidity": humidity,
        "hvac_mode": hvac_mode, "hvac_action": hvac_action,
        "preset_mode": preset_mode, "stale": stale,
    }

    out["tile"] = {
        "hero": f"{_int(current_temp)}°" if current_temp is not None else "--°",
        "sub": _sub(hvac_action, hvac_mode),
        "detail": _detail(humidity, preset_mode),
        "severity": "normal",
        "glyph": _ACTION_GLYPHS.get(hvac_action, _IDLE_GLYPH),
        "active": hvac_action in _ACTIVE_ACTIONS,
    }
    return out


_MODE_LABELS = {"heat_cool": "Heat/Cool", "fan_only": "Fan only", "dry": "Dry"}
_CELSIUS = {"temperature": "°C"}


def detail(ha, descriptor, now):
    """The detail panel's blocks (tablet contract §1)."""
    ents = descriptor.get("entities", {})
    tz = cfg.resolve_zone(descriptor.get("timezone"))
    v = values(ha, descriptor)
    st = ha.get_state(ents.get("thermostat")) if ents.get("thermostat") else None
    a = (st or {}).get("attributes", {}) or {}
    indoor = v["current_temp"]
    if indoor is None:
        indoor, _u = blocks.state_num(ha, ents.get("indoor_temp"))
    outdoor, _u = blocks.state_num(ha, ents.get("outdoor_temp"))
    mode, action = v["hvac_mode"], _sub(v["hvac_action"], v["hvac_mode"])
    mode_label = _MODE_LABELS.get(mode, (mode or "").replace("_", " ").title()) or None
    return {"blocks": [
        blocks.stats(
            blocks.stat("Indoor", blocks.deg(indoor)),
            ents.get("outdoor_temp") and blocks.stat("Outdoor", blocks.deg(outdoor)),
            blocks.stat("Humidity", blocks.pct(v["humidity"])),
            blocks.stat("Mode", mode_label, None if mode is None or action == mode_label else action),
            _setpoint(a, mode),
        ),
        blocks.chart(ha, [
            {"stat": ents.get("indoor_temp"), "label": "Indoor", "tone": "heat"},
            {"stat": ents.get("outdoor_temp"), "label": "Outdoor", "tone": "cool"},
        ], now, tz, stat_type="mean", unit="°C", units=_CELSIUS, zero=False, ndigits=1),
    ]}


def _setpoint(attrs, mode):
    """'Set to' stat: one target, or a low–high range; None when off or unset."""
    if mode in (None, "off"):
        return None
    t = _num(attrs.get("temperature"))
    lo, hi = _num(attrs.get("target_temp_low")), _num(attrs.get("target_temp_high"))
    if t is not None:
        return blocks.stat("Set to", blocks.deg(t))
    if lo is not None and hi is not None:
        return blocks.stat("Set to", f"{blocks.deg(lo).rstrip('°')}–{blocks.deg(hi)}")
    return None


def _sub(hvac_action, hvac_mode):
    if hvac_action == "heating":
        return "Heating"
    if hvac_action == "cooling":
        return "Cooling"
    if hvac_mode == "off":
        return "Off"  # before "fan": an off thermostat reads "Off" on the Roku, fan or not
    if hvac_action == "fan":
        return "Fan"  # replaces only the old "Idle" fallback
    return "Idle"


def _detail(humidity, preset_mode):
    parts = []
    if humidity is not None:
        parts.append(f"{humidity}% RH")
    if preset_mode:
        parts.append(f"{preset_mode.replace('_', ' ').title()} mode")
    return "   ".join(parts)


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
