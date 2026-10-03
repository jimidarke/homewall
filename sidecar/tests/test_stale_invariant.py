"""Stale truth (all layouts): a value tile whose hero is a placeholder is always `stale`.

A placeholder hero starts with "--" ("-- L", "-- kW", "--°"). Before v3, water could send
"-- L" with `stale: false` (flow present, hourly missing), and climate/weather could do
the same with the entity up but its temperature attribute missing. The tablet greys a
stale card and holds its last good value, so the flag must tell the truth. The Roku
never reads `stale`.

Each module runs over the empty state and every partial state built from its full one:
each entity alone, each entity removed, each entity `unavailable`, and each attribute the
module reads removed.
"""
import pytest
from conftest import FakeHA

from haku_sidecar.modules import climate, energy, gas, water, weather


def _st(eid, state, **attrs):
    return {eid: {"entity_id": eid, "state": state, "attributes": attrs}}


WATER = ({"entities": {
    "hourly": "sensor.water_hourly_usage", "flow": "sensor.water_flow_lpm",
    "daily": "sensor.water_daily_usage", "monthly": "sensor.water_monthly_usage",
    "total": "sensor.water_meter_total"}}, {
    **_st("sensor.water_hourly_usage", "12.0", unit_of_measurement="L"),
    **_st("sensor.water_flow_lpm", "4.2", unit_of_measurement="L/min"),
    **_st("sensor.water_daily_usage", "210", unit_of_measurement="L"),
    **_st("sensor.water_monthly_usage", "6100", unit_of_measurement="L"),
    **_st("sensor.water_meter_total", "812345", unit_of_measurement="L")})
ENERGY = ({"entities": {
    "power": "sensor.emporia_total_power", "daily_energy": "sensor.emporia_total_daily_energy_kwh",
    "cost": "sensor.electricity_daily_cost"}}, {
    **_st("sensor.emporia_total_power", "2412", unit_of_measurement="W"),
    **_st("sensor.emporia_total_daily_energy_kwh", "18.2", unit_of_measurement="kWh"),
    **_st("sensor.electricity_daily_cost", "4.12")})
GAS = ({"entities": {"flow": "sensor.home_gas_usage", "total": "sensor.gas_meter_gas_meter_direct"}}, {
    **_st("sensor.home_gas_usage", "0.65", unit_of_measurement="m³/h"),
    **_st("sensor.gas_meter_gas_meter_direct", "17.45", unit_of_measurement="m³")})
CLIMATE = ({"entities": {"thermostat": "climate.my_ecobee"}}, {
    **_st("climate.my_ecobee", "heat", current_temperature=21.3, current_humidity=48,
          hvac_action="heating", preset_mode="home")})
WEATHER = ({"entities": {"forecast": "weather.edmonton_forecast", "indoor": "weather.my_ecobee"}}, {
    **_st("weather.edmonton_forecast", "rainy", temperature=12.4, humidity=86, wind_speed=15.0),
    **_st("weather.my_ecobee", "cloudy", temperature=21.5)})

WATER_RATE = ({"tileStyle": "rate", "entities": {
    **WATER[0]["entities"], "cost_today": "sensor.water_cost_today"}}, {
    **WATER[1], **_st("sensor.water_cost_today", "1.24")})
ENERGY_RATE = ({**ENERGY[0], "tileStyle": "rate"}, ENERGY[1])
GAS_RATE = ({"tileStyle": "rate", "entities": {
    **GAS[0]["entities"], "daily": "sensor.gas_daily_usage", "cost_today": "sensor.gas_cost_today"}}, {
    **GAS[1], **_st("sensor.gas_daily_usage", "3.1", unit_of_measurement="m³"),
    **_st("sensor.gas_cost_today", "1.05")})

CASES = {
    "water": (water, *WATER),
    "energy": (energy, *ENERGY),
    "gas": (gas, *GAS),
    "climate": (climate, *CLIMATE),
    "weather": (weather, *WEATHER),
    "water-rate": (water, *WATER_RATE),
    "energy-rate": (energy, *ENERGY_RATE),
    "gas-rate": (gas, *GAS_RATE),
}


def _partials(full):
    """(label, states) for the empty state and every partial state of `full`."""
    yield "empty", {}
    for eid, row in full.items():
        yield f"only {eid}", {eid: row}
        yield f"without {eid}", {k: v for k, v in full.items() if k != eid}
        yield f"{eid} unavailable", {**full, eid: {**row, "state": "unavailable", "attributes": {}}}
        for attr in row["attributes"]:
            attrs = {k: v for k, v in row["attributes"].items() if k != attr}
            yield f"{eid} without {attr}", {**full, eid: {**row, "attributes": attrs}}


PARAMS = [pytest.param(kind, states, id=f"{kind}: {label}")
          for kind, (_mod, _desc, full) in CASES.items()
          for label, states in _partials(full)]


@pytest.mark.parametrize("kind,states", PARAMS)
def test_placeholder_hero_is_stale(kind, states):
    mod, desc, _full = CASES[kind]
    v = mod.values(FakeHA(states), {"id": kind, "kind": kind, "tile": {"type": "value"}, **desc})
    if v["tile"]["hero"].startswith("--"):
        assert v["stale"] is True, v["tile"]["hero"]


@pytest.mark.parametrize("kind", list(CASES))
def test_full_state_is_not_stale(kind):
    mod, desc, full = CASES[kind]
    v = mod.values(FakeHA(full), {"id": kind, "kind": kind, "tile": {"type": "value"}, **desc})
    assert v["stale"] is False
    assert not v["tile"]["hero"].startswith("--")


@pytest.mark.parametrize("kind,states,hero", [
    ("water", {**_st("sensor.water_flow_lpm", "4.2", unit_of_measurement="L/min")}, "-- L"),
    ("gas", {**_st("sensor.gas_meter_gas_meter_direct", "17.45")}, "-- m³/h"),
    ("climate", {**_st("climate.my_ecobee", "heat", current_humidity=48)}, "--°"),
    ("weather", {**_st("weather.edmonton_forecast", "rainy", humidity=86)}, "--°"),
])
def test_the_pre_v3_lies_are_fixed(kind, states, hero):
    """The exact cases that used to send a placeholder hero with `stale: false`."""
    mod, desc, _full = CASES[kind]
    v = mod.values(FakeHA(states), {"id": kind, "kind": kind, "tile": {"type": "value"}, **desc})
    assert v["tile"]["hero"] == hero
    assert v["stale"] is True


def test_weather_entity_up_without_temperature_keeps_its_condition():
    """Stale from a missing temperature doesn't blank the condition the tile still shows."""
    states = _st("weather.edmonton_forecast", "rainy", humidity=86)
    v = weather.values(FakeHA(states), {"entities": {"forecast": "weather.edmonton_forecast"}})
    assert v["stale"] is True
    assert v["condition"] == "rainy" and v["tile"]["sub"] == "Rainy"


def test_climate_entity_up_without_temperature_keeps_its_mode():
    states = _st("climate.my_ecobee", "heat", hvac_action="heating")
    v = climate.values(FakeHA(states), {"entities": {"thermostat": "climate.my_ecobee"}})
    assert v["stale"] is True
    assert v["hvac_mode"] == "heat" and v["tile"]["sub"] == "Heating"
