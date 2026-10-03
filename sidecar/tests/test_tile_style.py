"""Rate tiles: `"tileStyle": "rate"` on water, energy and gas (tablet contract §2).

With the flag the tile reads "now · today · cost": hero = the rate now, sub = "<today>
today", detail = "$x.xx today". A missing or unavailable today/cost entity leaves that key
out, and `stale` is exactly "the rate source is missing". `active`, `level`, `glyph` and
`severity` keep their rules. Without the flag (or with any other value) the output is
what it was, which `test_roku_golden.py` also guards byte for byte.
"""
import json
import os

import pytest
from conftest import FakeHA

from haku_sidecar import config as cfg_module
from haku_sidecar.modules import energy, gas, water
from haku_sidecar.store import CachedJson, prune

EXAMPLE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard.json.example"))


def _st(eid, state, **attrs):
    return {eid: {"entity_id": eid, "state": state, "attributes": attrs}}


def _without(states, *eids):
    return {k: v for k, v in states.items() if k not in eids}


def _with(states, eid, state):
    return {**states, eid: {**states[eid], "state": state}}


def _tile(mod, states, desc):
    return prune(mod.values(FakeHA(states), desc))["tile"]


# --- water -------------------------------------------------------------------
WATER_STATES = {
    **_st("sensor.water_hourly_usage", "12.0", unit_of_measurement="L"),
    **_st("sensor.water_flow_lpm", "4.2", unit_of_measurement="L/min"),
    **_st("sensor.water_daily_usage", "412.4", unit_of_measurement="L"),
    **_st("sensor.water_cost_today", "1.2449", unit_of_measurement="CAD"),
    **_st("sensor.water_monthly_usage", "6100", unit_of_measurement="L"),
}
WATER_ENTS = {"hourly": "sensor.water_hourly_usage", "flow": "sensor.water_flow_lpm",
              "daily": "sensor.water_daily_usage", "cost_today": "sensor.water_cost_today",
              "monthly": "sensor.water_monthly_usage"}
WATER_RATE = {"id": "water", "kind": "water", "tile": {"type": "value"}, "tileStyle": "rate",
              "runningSeverity": "normal", "entities": WATER_ENTS}


def test_water_rate_tile():
    v = water.values(FakeHA(WATER_STATES), WATER_RATE)
    t = v["tile"]
    assert (t["hero"], t["sub"], t["detail"]) == ("4.2 L/min", "412 L today", "$1.24 today")
    assert v["stale"] is False and v["cost_today"] == 1.24
    # unchanged rules
    assert (t["glyph"], t["active"], t["level"], t["severity"]) == ("water", True, 40, "normal")


def test_water_rate_idle_shows_a_bare_zero():
    t = _tile(water, _with(WATER_STATES, "sensor.water_flow_lpm", "0.0"), WATER_RATE)
    assert t["hero"] == "0 L/min"
    assert (t["glyph"], t["active"], t["level"]) == ("water-outline", False, 0)


@pytest.mark.parametrize("flow,hero", [("4", "4.0 L/min"), ("0.04", "0.0 L/min"), ("12.36", "12.4 L/min")])
def test_water_rate_one_decimal(flow, hero):
    assert _tile(water, _with(WATER_STATES, "sensor.water_flow_lpm", flow), WATER_RATE)["hero"] == hero


def test_water_rate_integer_litres():
    t = _tile(water, _with(WATER_STATES, "sensor.water_daily_usage", "87.6"), WATER_RATE)
    assert t["sub"] == "88 L today"


@pytest.mark.parametrize("states", [
    _without(WATER_STATES, "sensor.water_cost_today"),
    _with(WATER_STATES, "sensor.water_cost_today", "unavailable"),
    _with(WATER_STATES, "sensor.water_cost_today", "unknown"),
])
def test_water_rate_no_cost_leaves_detail_out(states):
    t = _tile(water, states, WATER_RATE)
    assert "detail" not in t
    assert t["sub"] == "412 L today"


def test_water_rate_no_cost_entity_configured():
    desc = {**WATER_RATE, "entities": {k: v for k, v in WATER_ENTS.items() if k != "cost_today"}}
    assert "detail" not in _tile(water, WATER_STATES, desc)


def test_water_rate_no_daily_leaves_sub_out():
    t = _tile(water, _with(WATER_STATES, "sensor.water_daily_usage", "unavailable"), WATER_RATE)
    assert "sub" not in t
    assert t["detail"] == "$1.24 today"


def test_water_rate_stale_exactly_when_flow_is_missing():
    v = water.values(FakeHA(_without(WATER_STATES, "sensor.water_flow_lpm")), WATER_RATE)
    assert v["stale"] is True and v["tile"]["hero"] == "-- L/min"
    # the hourly total is not the rate tile's hero, so its absence is not stale
    v = water.values(FakeHA(_without(WATER_STATES, "sensor.water_hourly_usage")), WATER_RATE)
    assert v["stale"] is False and v["tile"]["hero"] == "4.2 L/min"


def test_water_rate_running_severity_still_applies():
    desc = {**WATER_RATE, "runningSeverity": "high"}
    assert _tile(water, WATER_STATES, desc)["severity"] == "high"


# --- energy ------------------------------------------------------------------
ENERGY_STATES = {
    **_st("sensor.emporia_total_power", "912", unit_of_measurement="W"),
    **_st("sensor.emporia_total_daily_energy_kwh", "31.6", unit_of_measurement="kWh"),
    **_st("sensor.electricity_daily_cost", "6.912"),
}
ENERGY_RATE = {"id": "energy", "kind": "energy", "tile": {"type": "value"}, "tileStyle": "rate",
               "entities": {"power": "sensor.emporia_total_power",
                            "daily_energy": "sensor.emporia_total_daily_energy_kwh",
                            "cost": "sensor.electricity_daily_cost",
                            "cost_fallback": "sensor.emporia_total_daily_energy_kwh_cost"}}


def test_energy_rate_tile():
    v = energy.values(FakeHA(ENERGY_STATES), ENERGY_RATE)
    t = v["tile"]
    assert (t["hero"], t["sub"], t["detail"]) == ("0.9 kW", "32 kWh today", "$6.91 today")
    assert v["stale"] is False
    assert (t["glyph"], t["active"], t["level"], t["severity"]) == ("flash", False, 20, "normal")


def test_energy_rate_cost_falls_back_then_leaves_detail_out():
    states = {**_without(ENERGY_STATES, "sensor.electricity_daily_cost"),
              **_st("sensor.emporia_total_daily_energy_kwh_cost", "3.9")}
    assert _tile(energy, states, ENERGY_RATE)["detail"] == "$3.90 today"
    t = _tile(energy, _with(ENERGY_STATES, "sensor.electricity_daily_cost", "unavailable"), ENERGY_RATE)
    assert "detail" not in t and t["sub"] == "32 kWh today"


def test_energy_rate_no_daily_leaves_sub_out():
    assert "sub" not in _tile(energy, _without(ENERGY_STATES, "sensor.emporia_total_daily_energy_kwh"),
                              ENERGY_RATE)


def test_energy_rate_stale_exactly_when_power_is_missing():
    v = energy.values(FakeHA(_without(ENERGY_STATES, "sensor.emporia_total_power")), ENERGY_RATE)
    assert v["stale"] is True and v["tile"]["hero"] == "-- kW"
    assert energy.values(FakeHA(ENERGY_STATES), ENERGY_RATE)["stale"] is False


# --- gas ---------------------------------------------------------------------
GAS_STATES = {
    **_st("sensor.home_gas_usage", "0.84", unit_of_measurement="m³/h"),
    **_st("sensor.gas_meter_gas_meter_direct", "17639.9", unit_of_measurement="m³"),
    **_st("sensor.gas_daily_usage", "3.14", unit_of_measurement="m³"),
    **_st("sensor.gas_cost_today", "1.049"),
}
GAS_RATE = {"id": "gas", "kind": "gas", "tile": {"type": "value"}, "tileStyle": "rate",
            "entities": {"flow": "sensor.home_gas_usage", "total": "sensor.gas_meter_gas_meter_direct",
                         "daily": "sensor.gas_daily_usage", "cost_today": "sensor.gas_cost_today"}}


def test_gas_rate_tile():
    v = gas.values(FakeHA(GAS_STATES), GAS_RATE)
    t = v["tile"]
    assert (t["hero"], t["sub"], t["detail"]) == ("0.8 m³/h", "3.1 m³ today", "$1.05 today")
    assert v["stale"] is False and v["daily"] == 3.1 and v["cost_today"] == 1.05
    assert (t["glyph"], t["active"], t["level"], t["severity"]) == ("fire", True, 40, "normal")


@pytest.mark.parametrize("flow", ["0", "0.0", "0.04"])
def test_gas_rate_idle_shows_a_bare_zero(flow):
    """Idle is the module's "not running": a trickle that displays as 0.0 is idle too."""
    t = _tile(gas, _with(GAS_STATES, "sensor.home_gas_usage", flow), GAS_RATE)
    assert t["hero"] == "0 m³/h"
    assert (t["glyph"], t["active"]) == ("meter-gas", False)


@pytest.mark.parametrize("states", [
    _without(GAS_STATES, "sensor.gas_cost_today"),
    _with(GAS_STATES, "sensor.gas_cost_today", "unavailable"),
])
def test_gas_rate_no_price_leaves_detail_out(states):
    t = _tile(gas, states, GAS_RATE)
    assert "detail" not in t and t["sub"] == "3.1 m³ today"


def test_gas_rate_no_daily_leaves_sub_out():
    assert "sub" not in _tile(gas, _without(GAS_STATES, "sensor.gas_daily_usage"), GAS_RATE)


def test_gas_rate_stale_exactly_when_flow_is_missing():
    v = gas.values(FakeHA(_without(GAS_STATES, "sensor.home_gas_usage")), GAS_RATE)
    assert v["stale"] is True and v["tile"]["hero"] == "-- m³/h"


# --- without the flag nothing changes ----------------------------------------
@pytest.mark.parametrize("mod,desc,states", [
    (water, WATER_RATE, WATER_STATES), (energy, ENERGY_RATE, ENERGY_STATES), (gas, GAS_RATE, GAS_STATES),
])
@pytest.mark.parametrize("style", [None, "fixed", "RATE", ""])
def test_other_styles_are_the_default_output(mod, desc, states, style):
    base = {k: v for k, v in desc.items() if k != "tileStyle"}
    flagged = base if style is None else {**base, "tileStyle": style}
    assert mod.values(FakeHA(states), flagged) == mod.values(FakeHA(states), base)
    assert mod.values(FakeHA(states), base) != mod.values(FakeHA(states), desc)


def test_default_wording_is_the_pre_v3_wording():
    assert _tile(water, WATER_STATES, {**WATER_RATE, "tileStyle": None})["hero"] == "12 L"
    assert _tile(energy, ENERGY_STATES, {**ENERGY_RATE, "tileStyle": None})["detail"] == "$6.91 so far"
    assert _tile(gas, GAS_STATES, {**GAS_RATE, "tileStyle": None})["detail"] == "17640 m³ total"


# --- the example config's tablet layout ----------------------------------------
def test_example_tablet_layout_uses_rate_tiles_with_full_entity_maps(monkeypatch):
    monkeypatch.setattr(cfg_module, "_cache", CachedJson(EXAMPLE, cfg_module.DEFAULT_CONFIG))
    mods = {m["id"]: m for m in cfg_module.get_layout("tablet")[0]["modules"]}
    for mid in ("water", "energy", "gas"):
        assert mods[mid]["tileStyle"] == "rate"
    # a ref's `entities` replaces the whole map, so each one repeats the top-level keys
    top = {m["id"]: m for m in cfg_module.get_modules()}
    for mid in ("water", "energy", "gas", "climate", "weather"):
        assert set(top[mid]["entities"]) <= set(mods[mid]["entities"]), mid
        assert "tileStyle" not in top[mid]
    assert mods["water"]["entities"]["cost_today"] == "sensor.water_cost_today"
    assert mods["gas"]["entities"]["daily"] == "sensor.gas_daily_usage"
    assert mods["climate"]["entities"]["outdoor_temp"] == "sensor.edmonton_weather_temperature"


def test_example_tablet_state_has_rate_wording(client, monkeypatch):
    from haku_sidecar import app as app_module
    monkeypatch.setattr(cfg_module, "_cache", CachedJson(EXAMPLE, cfg_module.DEFAULT_CONFIG))
    states = {**WATER_STATES, **ENERGY_STATES, **GAS_STATES,
              **_st("sensor.water_flow_lpm", "0", unit_of_measurement="L/min")}
    monkeypatch.setattr(app_module, "ha", FakeHA(states))
    body = client.get("/api/state?layout=tablet").get_json()
    assert body["water"]["tile"]["hero"] == "0 L/min"
    assert body["water"]["tile"]["sub"] == "412 L today"
    assert body["energy"]["tile"]["detail"] == "$6.91 today"
    assert body["gas"]["tile"]["sub"] == "3.1 m³ today"
    assert "null" not in json.dumps(body)
