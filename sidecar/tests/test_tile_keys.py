"""Tablet tile keys: `glyph` / `active` / `level` on every value module's `tile`, and
`glyph` on timeline event items.

All additive: the Roku reads tile keys by name and ignores the extras, so its
`hero/sub/detail/severity/icon` output must stay exactly as it was. `active` is always a
real bool (`store.prune` only drops None, so `false` survives); `level` is an int 0-100
using the same scale the Roku `icon` bucket uses, and is None (so pruned) when the reading
is unavailable.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from haku_sidecar import config as cfg_module
from haku_sidecar import glyphs, modules
from haku_sidecar.modules import calendar as cal_mod
from haku_sidecar.modules import climate, energy, gas
from haku_sidecar.modules import timeline as tl_mod
from haku_sidecar.modules import water, weather
from haku_sidecar.store import CachedJson

from conftest import FakeHA


def _state(eid, state, **attrs):
    return {eid: {"entity_id": eid, "state": state, "attributes": attrs}}


def _desc(kind, **entities):
    return {"id": kind, "kind": kind, "feedKey": kind,
            "tile": {"type": "value"}, "entities": entities}


# --- weather ---------------------------------------------------------------
WEATHER_GLYPHS = [
    ("clear-night", "weather-night"),
    ("cloudy", "weather-cloudy"),
    ("exceptional", "alert-circle-outline"),
    ("fog", "weather-fog"),
    ("hail", "weather-hail"),
    ("lightning", "weather-lightning"),
    ("lightning-rainy", "weather-lightning-rainy"),
    ("partlycloudy", "weather-partly-cloudy"),
    ("pouring", "weather-pouring"),
    ("rainy", "weather-rainy"),
    ("snowy", "weather-snowy"),
    ("snowy-rainy", "weather-snowy-rainy"),
    ("sunny", "weather-sunny"),
    ("windy", "weather-windy"),
    ("windy-variant", "weather-windy-variant"),
    ("volcanic-ash", "weather-partly-cloudy"),   # unknown -> the default
    (None, "weather-partly-cloudy"),             # stale -> the default
]


@pytest.mark.parametrize("condition,glyph", WEATHER_GLYPHS)
def test_weather_glyph_map_all_conditions(condition, glyph):
    assert glyphs.weather_glyph(condition) == glyph


def test_weather_glyph_map_covers_every_label_condition():
    # The 15 HA conditions the module already labels are exactly the mapped ones.
    assert set(glyphs.WEATHER_GLYPHS) == set(weather._COND_LABELS)
    assert len(glyphs.WEATHER_GLYPHS) == 15


def test_weather_inactive():
    ha = FakeHA(_state("weather.edmonton_forecast", "sunny", temperature=21.4))
    tile = weather.values(ha, _desc("weather", forecast="weather.edmonton_forecast"))["tile"]
    assert tile["glyph"] == "weather-sunny"
    assert tile["active"] is False
    assert "level" not in tile


def test_weather_stale_gets_default_glyph():
    tile = weather.values(FakeHA(), _desc("weather", forecast="weather.edmonton_forecast"))["tile"]
    assert tile["glyph"] == "weather-partly-cloudy"
    assert tile["active"] is False


# --- energy ----------------------------------------------------------------
def test_energy_flash_level():
    ha = FakeHA(_state("sensor.power", "2412", unit_of_measurement="W"))
    tile = energy.values(ha, _desc("energy", power="sensor.power"))["tile"]
    assert tile["glyph"] == "flash"
    assert tile["active"] is False
    assert tile["level"] == 50 and isinstance(tile["level"], int)   # 2.4 kW / 5.0 kW
    assert tile["level"] == int(tile["icon"])                       # same scale as the Roku icon


def test_energy_level_clamps_and_is_none_when_unavailable():
    ha = FakeHA(_state("sensor.power", "6200", unit_of_measurement="W"))
    assert energy.values(ha, _desc("energy", power="sensor.power"))["tile"]["level"] == 100
    tile = energy.values(FakeHA(), _desc("energy", power="sensor.power"))["tile"]
    assert tile["level"] is None            # prune drops it
    assert tile["glyph"] == "flash" and tile["active"] is False


# --- water -----------------------------------------------------------------
def _water(flow, **extra):
    ha = FakeHA(_state("sensor.flow", flow, unit_of_measurement="L/min"))
    return water.values(ha, {**_desc("water", flow="sensor.flow"), **extra})


def test_water_running_active_glyph_level():
    tile = _water("4.2")["tile"]
    assert tile["glyph"] == "water"
    assert tile["active"] is True
    assert tile["level"] == 40 and isinstance(tile["level"], int)   # 4.2 / 10 default
    assert tile["level"] == int(tile["icon"])


def test_water_level_uses_configured_max_flow():
    assert _water("4.2", maxFlowLpm=12)["tile"]["level"] == 35


def test_water_idle_outline_inactive():
    tile = _water("0")["tile"]
    assert tile["glyph"] == "water-outline"
    assert tile["active"] is False
    assert tile["level"] == 0               # idle but readable: 0, not absent
    assert tile["severity"] == "normal"


def test_water_level_none_when_flow_unavailable():
    ha = FakeHA(_state("sensor.flow", "unavailable"))
    v = water.values(ha, _desc("water", flow="sensor.flow"))
    assert v["tile"]["level"] is None
    assert v["tile"]["glyph"] == "water-outline" and v["tile"]["active"] is False


def test_water_running_severity_override_normal():
    v = _water("4.2", runningSeverity="normal")
    assert v["running"] is True
    assert v["tile"]["severity"] == "normal"
    assert v["tile"]["active"] is True      # still active; only the severity changes


def test_water_running_severity_default_high():
    assert _water("4.2")["tile"]["severity"] == "high"          # the Roku's behaviour
    assert _water("0")["tile"]["severity"] == "normal"          # idle is never escalated
    assert _water("0", runningSeverity="high")["tile"]["severity"] == "normal"


def test_water_running_severity_ignores_invalid_value():
    assert _water("4.2", runningSeverity="loud")["tile"]["severity"] == "high"


# --- gas -------------------------------------------------------------------
def _gas(flow, **extra):
    ha = FakeHA(_state("sensor.gas_flow", flow, unit_of_measurement="m³/h"))
    return gas.values(ha, {**_desc("gas", flow="sensor.gas_flow"), **extra})


def test_gas_flow_fire_active():
    tile = _gas("0.65")["tile"]
    assert tile["glyph"] == "fire"
    assert tile["active"] is True
    assert tile["level"] == 30 and isinstance(tile["level"], int)   # 0.65 / 2.0 default
    assert tile["level"] == int(tile["icon"])
    assert _gas("0.65", maxFlowM3h=1.2)["tile"]["level"] == 55


def test_gas_idle_meter_gas():
    tile = _gas("0")["tile"]
    assert tile["glyph"] == "meter-gas"
    assert tile["active"] is False
    assert tile["level"] == 0


def test_gas_trickle_rounds_to_zero_is_not_running():
    # 0.04 displays as "0.0 m³/h", so it must not read as running or light the card.
    tile = _gas("0.04")["tile"]
    assert tile["hero"] == "0.0 m³/h"
    assert tile["sub"] == ""
    assert tile["active"] is False
    assert tile["glyph"] == "meter-gas"


def test_gas_flow_point_one_is_running():
    tile = _gas("0.1")["tile"]
    assert tile["hero"] == "0.1 m³/h"
    assert tile["sub"] == "running"
    assert tile["active"] is True
    assert tile["glyph"] == "fire"


def test_gas_level_none_when_flow_unavailable():
    ha = FakeHA(_state("sensor.gas_flow", "unavailable"))
    tile = gas.values(ha, _desc("gas", flow="sensor.gas_flow"))["tile"]
    assert tile["level"] is None
    assert tile["glyph"] == "meter-gas" and tile["active"] is False


# --- climate ---------------------------------------------------------------
def _climate(mode, action):
    attrs = {"current_temperature": 21.0, "current_humidity": 48, "preset_mode": "home"}
    if action is not None:
        attrs["hvac_action"] = action
    ha = FakeHA(_state("climate.ecobee", mode, **attrs))
    return climate.values(ha, _desc("climate", thermostat="climate.ecobee"))["tile"]


def test_climate_heating_fire_active():
    tile = _climate("heat", "heating")
    assert (tile["glyph"], tile["active"]) == ("fire", True)


def test_climate_cooling_snowflake():
    tile = _climate("cool", "cooling")
    assert (tile["glyph"], tile["active"]) == ("snowflake", True)


def test_climate_fan_keeps_fan_glyph():
    # Fan-only circulation keeps the fan glyph but is not an activity.
    tile = _climate("heat_cool", "fan")
    assert (tile["glyph"], tile["active"]) == ("fan", False)


def test_climate_fan_sub_is_fan_and_inactive():
    tile = _climate("heat_cool", "fan")
    assert tile["sub"] == "Fan"
    assert tile["active"] is False
    assert tile["glyph"] == "fan"


def test_climate_fan_with_mode_off_reads_off():
    # The Roku has always read "Off" for a thermostat that is off, fan running or not.
    # "Fan" replaces only the old "Idle" fallback.
    tile = _climate("off", "fan")
    assert tile["sub"] == "Off"
    assert (tile["glyph"], tile["active"]) == ("fan", False)


def test_climate_idle_thermostat_inactive():
    for mode, action in (("heat", "idle"), ("off", "off"), ("heat", None)):
        tile = _climate(mode, action)
        assert (tile["glyph"], tile["active"]) == ("thermostat", False), (mode, action)


def test_climate_stale_thermostat_inactive():
    tile = climate.values(FakeHA(), _desc("climate", thermostat="climate.ecobee"))["tile"]
    assert (tile["glyph"], tile["active"]) == ("thermostat", False)


def test_climate_still_has_no_icon_or_level():
    tile = _climate("heat", "heating")
    assert "icon" not in tile and "level" not in tile


# --- calendar / timeline ---------------------------------------------------
def test_calendar_glyph():
    desc = {"id": "calendar", "kind": "calendar", "tile": {"type": "agenda"}, "entities": {}}
    for ha in (FakeHA(), FakeHA(calendars=[{"entity_id": "calendar.family"}], events={
            "calendar.family": [{"start": {"dateTime": "2999-01-01T09:00:00-06:00"}, "summary": "Later"}]})):
        tile = cal_mod.values(ha, desc)["tile"]
        assert tile["glyph"] == "calendar"
        assert tile["active"] is False
        assert "level" not in tile


def test_timeline_tile_glyph_history():
    populated = FakeHA(_tl_states(), logbook={
        "lock.front": [{"when": _iso(30), "state": "locked", "name": "Front lock"}]})
    for ha in (FakeHA(), populated):                             # empty and populated
        tile = tl_mod.values(ha, _TL_DESC)["tile"]
        assert tile["glyph"] == "history"
        assert tile["active"] is False
        assert "level" not in tile


_TL_DESC = {
    "id": "timeline", "kind": "timeline", "feedKey": "timeline",
    "tile": {"type": "agenda"}, "coalesceWindowSec": 300, "lookbackHours": 12,
    "entities": {"watch": [
        "binary_sensor.front_door", "binary_sensor.garage", "binary_sensor.hall_motion",
        "lock.front", "person.jimi", "person.sam", "person.zoe", "switch.kettle"]},
}


def _iso(secs_ago):
    return (datetime.now(timezone.utc) - timedelta(seconds=secs_ago)).isoformat()


def _tl_states():
    """HA states for every entity _TL_DESC watches."""
    states = {}
    states.update(_state("binary_sensor.front_door", "off", device_class="door"))
    states.update(_state("binary_sensor.garage", "on", device_class="garage_door"))
    states.update(_state("binary_sensor.hall_motion", "on", device_class="motion"))
    states.update(_state("lock.front", "locked"))
    states.update(_state("person.jimi", "home"))
    states.update(_state("person.sam", "not_home"))
    states.update(_state("person.zoe", "work"))
    states.update(_state("switch.kettle", "on"))
    return states


def _items(**rows):
    """Run the timeline over one fresh logbook row per entity.

    `rows` maps an entity id (written with `__` for the dot, so it works as a keyword)
    to the state it just changed to. Returns the event items keyed by that same name.
    """
    logbook = {name.replace("__", "."): [{"when": _iso(30), "state": st, "name": name}]
               for name, st in rows.items()}
    v = tl_mod.values(FakeHA(_tl_states(), logbook=logbook), _TL_DESC)
    return {it["title"]: it for it in v["items"] if it["kind"] == "event"}


def test_timeline_item_glyphs():
    items = _items(
        binary_sensor__front_door="off",     # door closed
        binary_sensor__garage="on",          # garage opened
        binary_sensor__hall_motion="on",     # motion
        lock__front="locked",
        person__jimi="home",
        person__sam="not_home",
        person__zoe="work",                  # a named zone still means away from home
        switch__kettle="on",                 # unmapped
    )
    assert items["binary_sensor__front_door"]["glyph"] == "door-closed"
    assert items["binary_sensor__garage"]["glyph"] == "door-open"
    assert items["binary_sensor__hall_motion"]["glyph"] == "motion-sensor"
    assert items["lock__front"]["glyph"] == "lock"
    assert items["person__jimi"]["glyph"] == "home-account"
    assert items["person__sam"]["glyph"] == "account-arrow-right"
    assert items["person__zoe"]["glyph"] == "account-arrow-right"
    assert items["person__zoe"]["sub"] == "→ Work"
    assert "glyph" not in items["switch__kettle"]
    # HA still reports the garage open, so its unclosed opening reads "open now" and is urgent
    assert items["binary_sensor__garage"]["sub"] == "open now"
    assert items["binary_sensor__garage"]["severity"] == "high"


def test_timeline_item_glyphs_other_states():
    assert _items(binary_sensor__garage="on")["binary_sensor__garage"]["glyph"] == "door-open"
    # an opening HA already reports closed (the close is newer than the logbook) shows closed
    assert _items(binary_sensor__front_door="on")["binary_sensor__front_door"]["glyph"] == "door-closed"
    assert _items(lock__front="unlocked")["lock__front"]["glyph"] == "lock-open-variant"
    assert _items(person__sam="away")["person__sam"]["glyph"] == "account-arrow-right"
    # "detected" is a motion edge; the "clear" edge is dropped by the transition policy,
    # so exercise _glyph directly for it.
    assert _items(binary_sensor__hall_motion="detected")["binary_sensor__hall_motion"]["glyph"] == "motion-sensor"
    assert tl_mod._glyph("off", "motion", "binary_sensor.hall_motion") == "motion-sensor-off"
    assert tl_mod._glyph("off", "occupancy", "binary_sensor.x") == "motion-sensor-off"


def test_timeline_item_glyph_omitted_for_unmapped_domains():
    assert tl_mod._glyph("on", "switch", "switch.kettle") is None
    assert tl_mod._glyph("open", "cover", "cover.blind") is None


# --- through the API: pruning keeps `active: false` ------------------------
def test_active_is_real_bool_after_prune(client, monkeypatch):
    from haku_sidecar import app as app_module

    states = {}
    states.update(_state("weather.edmonton_forecast", "sunny", temperature=20))
    states.update(_state("sensor.flow", "0", unit_of_measurement="L/min"))
    states.update(_state("sensor.power", "unavailable"))                 # level -> pruned
    config = {
        "version": 1, "site": "home", "timezone": "America/Edmonton",
        "modules": [
            {"id": "weather", "kind": "weather", "feedKey": "weather",
             "tile": {"type": "value"}, "entities": {"forecast": "weather.edmonton_forecast"}},
            {"id": "water", "kind": "water", "feedKey": "water",
             "tile": {"type": "value"}, "entities": {"flow": "sensor.flow"}},
            {"id": "energy", "kind": "energy", "feedKey": "energy",
             "tile": {"type": "value"}, "entities": {"power": "sensor.power"}},
        ],
    }
    monkeypatch.setattr(cfg_module, "_cache", CachedJson("/nonexistent/haku/dashboard.json", config))
    monkeypatch.setattr(app_module, "ha", FakeHA(states))

    r = client.get("/api/state")
    assert r.status_code == 200
    body = json.loads(r.get_data(as_text=True))
    assert body["weather"]["tile"]["active"] is False       # present, and a bool, not missing
    assert body["water"]["tile"]["active"] is False
    assert body["energy"]["tile"]["active"] is False
    assert '"active": false' in r.get_data(as_text=True) or '"active":false' in r.get_data(as_text=True)
    assert body["water"]["tile"]["level"] == 0              # a real zero survives the prune
    assert "level" not in body["energy"]["tile"]            # None was dropped
    assert "null" not in r.get_data(as_text=True)


def test_compose_state_keeps_agenda_item_glyphs():
    logbook = {"lock.front": [{"when": _iso(30), "state": "locked", "name": "Front lock"}]}
    snap = modules.compose_state(FakeHA(_tl_states(), logbook=logbook), {"modules": [_TL_DESC]})
    event = next(it for it in snap["timeline"]["items"] if it["kind"] == "event")
    assert event["glyph"] == "lock"
    assert snap["timeline"]["tile"]["glyph"] == "history"
