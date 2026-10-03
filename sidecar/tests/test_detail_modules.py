"""Each module's `detail()` (tablet v3 contract §1) over FakeHA's canned statistics/history.

The clock is frozen at Thu 2026-10-01 18:30 in America/Edmonton (00:30 UTC on Oct 2), so
the hourly chart covers Thu Sep 24 18:00 to Thu Oct 1 18:00 local and the days strip is
Fri Sep 25 to Wed Sep 30 plus "Today". Every payload also passes the shared contract
check (conftest.assert_detail_contract): no nulls, caps, gap-safe runs.
"""
import types
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from conftest import FakeHA, assert_detail_contract

from haku_sidecar import modules, store
from haku_sidecar.modules import climate, doors, energy, gas, laundry, water, weather

TZ = ZoneInfo("America/Edmonton")
NOW = int(datetime(2026, 10, 1, 18, 30, tzinfo=TZ).timestamp())
END = int(datetime(2026, 10, 1, 18, 0, tzinfo=TZ).timestamp())
START = END - 168 * 3600
MIDNIGHT = int(datetime(2026, 10, 1, tzinfo=TZ).timestamp())
WEEK_AGO = int(datetime(2026, 9, 25, tzinfo=TZ).timestamp())
PAST = ["Fri", "Sat", "Sun", "Mon", "Tue", "Wed"]


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(store, "time", types.SimpleNamespace(time=lambda: float(NOW)))


def _st(eid, state, **attrs):
    return {eid: {"entity_id": eid, "state": state, "attributes": attrs,
                  "last_changed": _iso(NOW - 600)}}


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def _hourly(key, value, skip=range(40, 45)):
    """168 hourly rows from START (epoch-ms starts, as HA sends), minus the `skip` hours."""
    return [{"start": (START + i * 3600) * 1000.0, "end": (START + (i + 1) * 3600) * 1000.0,
             key: value(i)} for i in range(168) if i not in skip]


def _daily(values):
    """Daily rows for Sep 25.. (one per value, None = no row)."""
    out = []
    for k, v in enumerate(values):
        if v is not None:
            day = int(datetime(2026, 9, 25 + k, tzinfo=TZ).timestamp())
            out.append({"start": day * 1000.0, "end": (day + 86400) * 1000.0, "change": v})
    return out


def _detail(mod, ha, desc):
    body = modules.module_detail(ha, {"id": desc["kind"], "title": desc["kind"].title(),
                                      "tile": {"type": "value"}, "timezone": "America/Edmonton",
                                      **desc}, NOW)
    assert_detail_contract(body)
    assert body["ts"] == NOW
    return body


def _block(body, kind, title=None):
    found = [b for b in body["blocks"] if b["type"] == kind and (title is None or b.get("title") == title)]
    return found[0] if found else None


def _stats(body):
    return {i["label"]: (i["value"], i.get("sub")) for i in _block(body, "stats")["items"]}


def _calls(ha, method):
    return [kw for name, kw in ha.calls if name == method]


# --- water -------------------------------------------------------------------------
WATER_ENTS = {
    "hourly": "sensor.water_hourly_usage", "flow": "sensor.water_flow_lpm",
    "daily": "sensor.water_daily_usage", "cost_today": "sensor.water_cost_today",
    "monthly": "sensor.water_monthly_usage", "monthly_cost": "sensor.water_monthly_estimated_cost",
    "total": "sensor.water_meter_total",
    "stat_usage": "sensor.water_meter_total", "stat_cost": "sensor.water_meter_total_cost",
}
WATER_DESC = {"kind": "water", "tileStyle": "rate", "entities": WATER_ENTS}
WATER_STATES = {
    **_st("sensor.water_flow_lpm", "4.2", unit_of_measurement="L/min"),
    **_st("sensor.water_daily_usage", "87.6", unit_of_measurement="L"),
    **_st("sensor.water_cost_today", "0.27"),
    **_st("sensor.water_monthly_usage", "6100", unit_of_measurement="L"),
    **_st("sensor.water_monthly_estimated_cost", "18.4"),
}
WATER_STATS = {
    ("sensor.water_meter_total", "hour"): _hourly("change", lambda i: float(i % 5) * 10.25),
    ("sensor.water_meter_total", "day"): _daily([400.0, 380.4, None, 512.0, 0.0, 255.5]),
    ("sensor.water_meter_total_cost", "day"): _daily([1.2, 1.14, None, None, 0.0, 0.77]),
}


def test_water_detail():
    ha = FakeHA(WATER_STATES, statistics=WATER_STATS)
    body = _detail(water, ha, WATER_DESC)
    assert body["id"] == "water" and "note" not in body
    assert _stats(body) == {"Now": ("4.2 L/min", None), "Today": ("88 L", "$0.27"),
                            "This month": ("6.1 m³", "$18.40 est.")}

    chart = _block(body, "chart")
    assert (chart["start"], chart["step"], chart["count"]) == (START, 3600, 168)
    assert chart["title"] == "Per hour · last 7 days"
    s, = chart["series"]
    assert (s["label"], s["tone"], s["fill"]) == ("Water", "water", True)
    assert [(r["i"], len(r["v"])) for r in s["runs"]] == [(0, 40), (45, 123)]
    assert s["runs"][0]["v"][:3] == [0.0, 10.2, 20.5]
    assert [t["label"] for t in chart["x"]["ticks"]] == PAST + ["Thu"]
    assert chart["x"]["ticks"][0]["i"] == 6
    assert chart["y"]["min"] == 0 and chart["y"]["max"] >= 41
    assert chart["y"]["ticks"][1]["label"].endswith(" L")

    strip = _block(body, "days")["items"]
    assert [d["label"] for d in strip] == [*PAST, "Today"]
    assert [d["value"] for d in strip] == ["400 L", "380 L", "--", "512 L", "0 L", "256 L", "88 L"]
    assert [d.get("sub") for d in strip] == ["$1.20", "$1.14", None, None, "$0.00", "$0.77", "$0.27"]


def test_water_statistics_requests():
    ha = FakeHA(WATER_STATES, statistics=WATER_STATS)
    _detail(water, ha, WATER_DESC)
    hourly, days = _calls(ha, "get_statistics")
    assert hourly == {"statistic_ids": ["sensor.water_meter_total"], "start": START, "end": END,
                      "period": "hour", "types": ["change"], "units": {"volume": "L"}}
    assert days == {"statistic_ids": ["sensor.water_meter_total", "sensor.water_meter_total_cost"],
                    "start": WEEK_AGO, "end": MIDNIGHT, "period": "day", "types": ["change"],
                    "units": {"volume": "L"}}


def test_water_detail_when_statistics_fail():
    body = _detail(water, FakeHA(WATER_STATES, statistics=FakeHA.FAIL), WATER_DESC)
    chart = _block(body, "chart")
    assert chart["empty"] == "History unavailable"
    assert chart["series"][0]["runs"] == [] and "y" not in chart
    strip = _block(body, "days")["items"]
    assert [d["value"] for d in strip] == ["--"] * 6 + ["88 L"]


def test_water_detail_with_no_history_yet():
    body = _detail(water, FakeHA(WATER_STATES), WATER_DESC)
    assert _block(body, "chart")["empty"] == "No history yet"


def test_water_detail_with_the_meter_down():
    """The ESP outage: every live water entity unavailable. Placeholders, no crash."""
    states = {eid: {**row, "state": "unavailable"} for eid, row in WATER_STATES.items()}
    body = _detail(water, FakeHA(states, statistics=WATER_STATS), WATER_DESC)
    assert _stats(body) == {"Now": ("-- L/min", None), "Today": ("--", None),
                            "This month": ("--", None)}
    assert _block(body, "days")["items"][-1] == {"label": "Today", "value": "--"}
    assert _block(body, "chart")["series"][0]["runs"]          # history still shows


def test_water_detail_without_statistics_entities_leaves_chart_and_days_out():
    ents = {k: v for k, v in WATER_ENTS.items() if not k.startswith("stat_")}
    ha = FakeHA(WATER_STATES, statistics=WATER_STATS)
    body = _detail(water, ha, {"kind": "water", "entities": ents})
    assert [b["type"] for b in body["blocks"]] == ["stats"]
    assert _calls(ha, "get_statistics") == []


def test_water_detail_monthly_in_cubic_metres_and_unconfigured_stats():
    states = {**WATER_STATES, **_st("sensor.water_monthly_usage", "6.25", unit_of_measurement="m³")}
    ents = {"flow": "sensor.water_flow_lpm", "monthly": "sensor.water_monthly_usage"}
    body = _detail(water, FakeHA(states), {"kind": "water", "entities": ents})
    assert _stats(body) == {"Now": ("4.2 L/min", None), "This month": ("6.2 m³", None)}


# --- energy ------------------------------------------------------------------------
ENERGY_ENTS = {
    "power": "sensor.emporia_total_power", "daily_energy": "sensor.emporia_total_daily_energy_kwh",
    "cost": "sensor.electricity_daily_cost", "monthly": "sensor.electricity_monthly_usage",
    "monthly_cost": "sensor.electricity_monthly_estimated_cost",
    "stat_usage": "sensor.emporia_total_daily_energy_kwh",
    "stat_cost": "sensor.emporia_total_daily_energy_kwh_cost",
}
ENERGY_STATES = {
    **_st("sensor.emporia_total_power", "912", unit_of_measurement="W"),
    **_st("sensor.emporia_total_daily_energy_kwh", "31.6", unit_of_measurement="kWh"),
    **_st("sensor.electricity_daily_cost", "6.91"),
    **_st("sensor.electricity_monthly_usage", "412.4", unit_of_measurement="kWh"),
    **_st("sensor.electricity_monthly_estimated_cost", "58.2"),
}
ENERGY_STATS = {
    ("sensor.emporia_total_daily_energy_kwh", "hour"): _hourly("change", lambda i: 0.4 + (i % 3) * 0.1234, skip=()),
    ("sensor.emporia_total_daily_energy_kwh", "day"): _daily([30.2, 28.7, 33.5, 29.0, 31.4, 27.6]),
    ("sensor.emporia_total_daily_energy_kwh_cost", "day"): _daily([6.6, 6.3, 7.4, 6.4, 6.9, 6.1]),
}


def test_energy_detail():
    ha = FakeHA(ENERGY_STATES, statistics=ENERGY_STATS)
    body = _detail(energy, ha, {"kind": "energy", "entities": ENERGY_ENTS})
    assert _stats(body) == {"Now": ("0.9 kW", None), "Today": ("32 kWh", "$6.91"),
                            "This month": ("412 kWh", "$58.20 est.")}
    s, = _block(body, "chart")["series"]
    assert (s["label"], s["tone"], s["fill"]) == ("Energy", "amber", True)
    assert s["runs"] == [{"i": 0, "v": [round(0.4 + (i % 3) * 0.1234, 3) for i in range(168)]}]
    assert _block(body, "chart")["y"]["ticks"][-1]["label"].endswith(" kWh")
    strip = _block(body, "days")["items"]
    assert [d["value"] for d in strip] == ["30 kWh", "29 kWh", "34 kWh", "29 kWh", "31 kWh", "28 kWh", "32 kWh"]
    assert strip[0]["sub"] == "$6.60" and strip[-1]["sub"] == "$6.91"
    assert {c["units"]["energy"] for c in _calls(ha, "get_statistics")} == {"kWh"}


def test_energy_detail_power_down():
    states = {k: v for k, v in ENERGY_STATES.items() if k != "sensor.emporia_total_power"}
    body = _detail(energy, FakeHA(states, statistics=ENERGY_STATS), {"kind": "energy", "entities": ENERGY_ENTS})
    assert _stats(body)["Now"] == ("-- kW", None)


# --- gas ---------------------------------------------------------------------------
GAS_ENTS = {
    "flow": "sensor.home_gas_usage", "total": "sensor.gas_meter_gas_meter_direct",
    "daily": "sensor.gas_daily_usage", "cost_today": "sensor.gas_cost_today",
    "monthly": "sensor.gas_monthly_usage", "monthly_cost": "sensor.gas_monthly_cost",
    "stat_usage": "sensor.gas_meter_gas_meter_direct", "stat_cost": "sensor.gas_meter_gas_meter_direct_cost",
}
GAS_STATES = {
    **_st("sensor.home_gas_usage", "0.02", unit_of_measurement="m³/h"),
    **_st("sensor.gas_daily_usage", "3.14", unit_of_measurement="m³"),
    **_st("sensor.gas_cost_today", "unavailable"),           # no gas price yet
    **_st("sensor.gas_monthly_usage", "41.25", unit_of_measurement="m³"),
}
GAS_STATS = {
    # Gas statistics only started on Oct 1: the chart and strip fill in over a week.
    ("sensor.gas_meter_gas_meter_direct", "hour"): _hourly("change", lambda i: 0.125, skip=range(150)),
    ("sensor.gas_meter_gas_meter_direct", "day"): [],
}


def test_gas_detail_without_a_price_and_young_statistics():
    ha = FakeHA(GAS_STATES, statistics=GAS_STATS)
    body = _detail(gas, ha, {"kind": "gas", "entities": GAS_ENTS})
    assert _stats(body) == {"Now": ("0 m³/h", None), "Today": ("3.1 m³", None),
                            "This month": ("41.2 m³", None)}
    s, = _block(body, "chart")["series"]
    assert (s["tone"], s["runs"]) == ("heat", [{"i": 150, "v": [0.125] * 18}])
    strip = _block(body, "days")["items"]
    assert [d["value"] for d in strip] == ["--"] * 6 + ["3.1 m³"]
    assert all("sub" not in d for d in strip)
    assert {c["units"]["volume"] for c in _calls(ha, "get_statistics")} == {"m³"}


def test_gas_detail_with_a_price():
    states = {**GAS_STATES, **_st("sensor.home_gas_usage", "0.84"), **_st("sensor.gas_cost_today", "1.049"),
              **_st("sensor.gas_monthly_cost", "14.5")}
    stats = {**GAS_STATS, ("sensor.gas_meter_gas_meter_direct", "day"): _daily([None] * 5 + [2.95]),
             ("sensor.gas_meter_gas_meter_direct_cost", "day"): _daily([None] * 5 + [0.99])}
    body = _detail(gas, FakeHA(states, statistics=stats), {"kind": "gas", "entities": GAS_ENTS})
    assert _stats(body) == {"Now": ("0.8 m³/h", None), "Today": ("3.1 m³", "$1.05"),
                            "This month": ("41.2 m³", "$14.50 est.")}
    assert _block(body, "days")["items"][-2:] == [{"label": "Wed", "value": "3.0 m³", "sub": "$0.99"},
                                                 {"label": "Today", "value": "3.1 m³", "sub": "$1.05"}]


# --- climate -----------------------------------------------------------------------
CLIMATE_ENTS = {"thermostat": "climate.my_ecobee", "indoor_temp": "sensor.my_ecobee_temperature",
                "outdoor_temp": "sensor.edmonton_weather_temperature"}
CLIMATE_STATS = {
    "sensor.my_ecobee_temperature": _hourly("mean", lambda i: 21.0 + (i % 4) * 0.25, skip=()),
    "sensor.edmonton_weather_temperature": _hourly("mean", lambda i: -12.34 + i * 0.2, skip=range(60, 70)),
}


def _thermostat(state="heat", **attrs):
    base = {"current_temperature": 21.3, "current_humidity": 48, "hvac_action": "heating", "temperature": 21.5}
    return _st("climate.my_ecobee", state, **{**base, **attrs})


def test_climate_detail():
    states = {**_thermostat(), **_st("sensor.edmonton_weather_temperature", "6.5")}
    ha = FakeHA(states, statistics=CLIMATE_STATS)
    body = _detail(climate, ha, {"kind": "climate", "entities": CLIMATE_ENTS})
    assert _stats(body) == {"Indoor": ("21.3°", None), "Outdoor": ("6.5°", None),
                            "Humidity": ("48%", None), "Mode": ("Heat", "Heating"), "Set to": ("21.5°", None)}
    chart = _block(body, "chart")
    indoor, outdoor = chart["series"]
    assert (indoor["label"], indoor["tone"], outdoor["label"], outdoor["tone"]) == ("Indoor", "heat", "Outdoor", "cool")
    assert "fill" not in indoor and "fill" not in outdoor
    assert [(r["i"], len(r["v"])) for r in outdoor["runs"]] == [(0, 60), (70, 98)]
    assert outdoor["runs"][0]["v"][0] == -12.3
    assert chart["y"]["min"] <= -12.3 and any(t["label"].startswith("-") and t["label"].endswith("°C")
                                               for t in chart["y"]["ticks"])
    call, = _calls(ha, "get_statistics")
    assert (call["types"], call["units"], call["period"]) == (["mean"], {"temperature": "°C"}, "hour")


@pytest.mark.parametrize("attrs,mode,setpoint", [
    ({"hvac_action": "idle"}, ("Heat", "Idle"), ("21.5°", None)),
    ({"temperature": None, "target_temp_low": 20, "target_temp_high": 24, "hvac_action": "cooling"},
     ("Heat/Cool", "Cooling"), ("20–24°", None)),
])
def test_climate_modes(attrs, mode, setpoint):
    state = "heat_cool" if "target_temp_low" in attrs else "heat"
    body = _detail(climate, FakeHA(_thermostat(state, **attrs)), {"kind": "climate", "entities": CLIMATE_ENTS})
    assert _stats(body)["Mode"] == mode and _stats(body)["Set to"] == setpoint


def test_climate_off_has_no_setpoint_and_no_echo():
    body = _detail(climate, FakeHA(_thermostat("off", hvac_action="off")), {"kind": "climate", "entities": CLIMATE_ENTS})
    assert _stats(body)["Mode"] == ("Off", None)
    assert "Set to" not in _stats(body)


def test_climate_thermostat_down():
    body = _detail(climate, FakeHA({}, statistics=FakeHA.FAIL), {"kind": "climate", "entities": CLIMATE_ENTS})
    assert _stats(body) == {"Indoor": ("--", None), "Outdoor": ("--", None), "Humidity": ("--", None),
                            "Mode": ("--", None)}
    assert _block(body, "chart")["empty"] == "History unavailable"


def test_climate_indoor_falls_back_to_the_temperature_sensor():
    states = {**_thermostat(current_temperature=None), **_st("sensor.my_ecobee_temperature", "20.94")}
    body = _detail(climate, FakeHA(states), {"kind": "climate", "entities": CLIMATE_ENTS})
    assert _stats(body)["Indoor"] == ("20.9°", None)


# --- weather -----------------------------------------------------------------------
WEATHER_ENTS = {"forecast": "weather.edmonton_forecast", "indoor": "weather.my_ecobee",
                "wind_chill": "sensor.edmonton_weather_wind_chill",
                "precip": "sensor.edmonton_weather_chance_of_precipitation"}   # precip: no longer read
OUTDOOR = "sensor.edmonton_weather_temperature"
ATTRIBUTION = "Data provided by Environment Canada"
W_START = END - 24 * 3600          # chart bucket 0 (24 h before the current hour); Now is bucket 24


def _fc(days_ahead, hour=18, **kw):
    """A daily forecast entry `days_ahead` local days from NOW (environment_canada style)."""
    t = datetime(2026, 10, 1 + days_ahead, hour, 30, tzinfo=TZ).isoformat()
    return {"datetime": t, **kw}


def _hr(k, **kw):
    """An hourly forecast entry `k` hours after the current hour (END = 18:00 local)."""
    return {"datetime": _iso(END + k * 3600), **kw}


DAILY = [
    _fc(0, temperature=11.6, templow=3, condition="rainy", precipitation_probability=60),   # today
    _fc(1, temperature=12.4, templow=4, condition="rainy", precipitation_probability=40),
    _fc(2, temperature=9, templow=-1.6, condition="snowy-rainy"),
    _fc(3, temperature=15, templow=2, condition="volcanic-ash", precipitation_probability=0),
    _fc(4, temperature=16, templow=3, condition="sunny"),
]
EVENING = [{**DAILY[0], "temperature": None}, *DAILY[1:]]       # EnvCan: tonight has no high
# k = 0 is the current hour (never shown: the strip starts at the next one). Temps fall 1 deg every 3 h
# from 7; the chance is 10k % except hour 2, which reports 0.
HOURLY = [_hr(k, temperature=7 - k // 3, condition="rainy" if k < 10 else "cloudy",
              precipitation_probability=0 if k == 2 else 10 * k) for k in range(25)]
FORECASTS = {"daily": DAILY, "hourly": HOURLY}


def _obs(i):
    return round(1.0 + i * 0.2, 1)


# Hourly means for buckets 0..23 of the chart, minus bucket 10 (a gap).
OBSERVED = [{"start": (W_START + i * 3600) * 1000.0, "mean": _obs(i)} for i in range(24) if i != 10]
WEATHER_STATES = {
    **_st("weather.edmonton_forecast", "rainy", temperature=6.6, humidity=58, wind_speed=14.6,
          wind_bearing=300, wind_speed_unit="km/h", pressure=101.3, pressure_unit="kPa",
          attribution=ATTRIBUTION),
    **_st("sensor.edmonton_weather_wind_chill", "3.2"),
    **_st(OUTDOOR, "6.6", unit_of_measurement="°C"),
    **_st("sun.sun", "above_horizon", next_setting=_iso(NOW + 11 * 60),
          next_rising=_iso(int(datetime(2026, 10, 2, 7, 30, tzinfo=TZ).timestamp()))),
}
WEATHER_STATS = {OUTDOOR: OBSERVED}


def _weather(states=None, forecast=None, statistics=None, now=NOW):
    ha = FakeHA(WEATHER_STATES if states is None else states, FORECASTS if forecast is None else forecast,
                statistics=WEATHER_STATS if statistics is None else statistics)
    body = modules.module_detail(ha, {"id": "weather", "title": "Weather", "kind": "weather",
                                      "tile": {"type": "value"}, "timezone": "America/Edmonton",
                                      "entities": WEATHER_ENTS}, now)
    assert_detail_contract(body)
    return body, ha


def _types(body):
    return [(b["type"], b.get("col", 0)) for b in body["blocks"]]


def _kinds(body):
    return [b["type"] for b in body["blocks"]]


def test_weather_detail_blocks_and_columns():
    body, _ = _weather()
    assert _types(body) == [("now", 0), ("rows", 0), ("forecast", 0), ("hourly", 1), ("chart", 1)]
    assert body["note"] == ATTRIBUTION


def test_weather_without_an_attribution_has_no_note():
    states = {**WEATHER_STATES, **_st("weather.edmonton_forecast", "rainy", temperature=6.6)}
    assert "note" not in _weather(states)[0]


def test_weather_now_block():
    now = _block(_weather()[0], "now")
    assert now == {"type": "now", "col": 0, "glyph": "weather-rainy", "temp": "7°", "cond": "Rainy",
                   "hilo": "H 12°  L 3°", "sub": "Updated 6:20 PM"}     # the state changed at NOW - 600


def test_weather_now_block_in_the_evening_has_only_the_low():
    """EnvCan's first daily item is 'Tonight' with no high: the block says only 'L 3°'."""
    now = _block(_weather(forecast={**FORECASTS, "daily": EVENING})[0], "now")
    assert now["hilo"] == "L 3°"


def test_weather_now_block_without_a_daily_forecast_has_no_hilo():
    now = _block(_weather(forecast={"hourly": HOURLY})[0], "now")
    assert "hilo" not in now and now["temp"] == "7°"


def test_weather_facts_rows():
    rows = _block(_weather()[0], "rows")
    assert [(i["label"], i["value"]) for i in rows["items"]] == [
        ("Feels like", "3°"), ("Humidity", "58%"), ("Wind", "15 km/h NW"), ("Pressure", "101.3 kPa"),
        ("Sunset", "6:41 PM"), ("Sunrise", "Fri 7:30 AM")]
    assert "title" not in rows


@pytest.mark.parametrize("attr,sensor,want", [
    (14.6, None, "15 km/h NW"),        # the entity's own speed
    (None, "14", "14 km/h NW"),        # EnvCan leaves it empty when calm or unreported: the sensor has it
    (None, "0", "Calm"),               # no speed to speak of: no bearing either
    (0.3, None, "Calm"),
    (None, "unknown", None),           # nobody knows: no row, not a "--"
    (None, None, None),
])
def test_weather_wind_row(attr, sensor, want):
    states = {**WEATHER_STATES, **_st("weather.edmonton_forecast", "rainy", temperature=6.6, wind_speed=attr,
                                      wind_bearing=300, wind_speed_unit="km/h")}
    if sensor is not None:
        states.update(_st("sensor.edmonton_weather_wind_speed", sensor, unit_of_measurement="km/h"))
    items = _block(_weather(states)[0], "rows")["items"]
    assert [i["value"] for i in items if i["label"] == "Wind"] == ([want] if want else [])


def test_weather_facts_omit_what_has_no_source():
    bare = _st("weather.edmonton_forecast", "rainy", temperature=6.6, humidity=58, wind_speed=14.6)
    rows = _block(_weather({**bare, **_st(OUTDOOR, "6.6")})[0], "rows")
    assert [(i["label"], i["value"]) for i in rows["items"]] == [("Humidity", "58%"), ("Wind", "15 km/h")]


@pytest.mark.parametrize("unit,value,want", [("hPa", 1013.25, "1013 hPa"), ("inHg", 29.9213, "29.92 inHg"),
                                             ("kPa", 101.25, "101.2 kPa")])
def test_weather_pressure_formats_by_unit(unit, value, want):
    states = {**WEATHER_STATES, **_st("weather.edmonton_forecast", "rainy", temperature=6.6,
                                      pressure=value, pressure_unit=unit)}
    items = _block(_weather(states)[0], "rows")["items"]
    assert [i["value"] for i in items if i["label"] == "Pressure"] == [want]


def test_weather_sun_rows_are_in_time_order_and_say_the_day_when_not_today():
    sun = _st("sun.sun", "below_horizon", next_rising=_iso(NOW + 3600), next_setting=_iso(NOW + 86400 + 60))
    items = _block(_weather({**WEATHER_STATES, **sun})[0], "rows")["items"]
    assert [(i["label"], i["value"]) for i in items[-2:]] == [("Sunrise", "7:30 PM"), ("Sunset", "Fri 6:31 PM")]


def test_weather_outlook_is_the_next_three_days_in_compact_rows():
    block = _block(_weather()[0], "forecast")
    assert block["style"] == "compact"
    assert block["days"] == [
        {"label": "Fri", "glyph": "weather-rainy", "cond": "Rainy", "hi": "12°", "lo": "4°", "sub": "40%"},
        {"label": "Sat", "glyph": "weather-snowy-rainy", "cond": "Wet Snow", "hi": "9°", "lo": "-2°"},
        {"label": "Sun", "glyph": "weather-partly-cloudy", "cond": "Volcanic Ash", "hi": "15°", "lo": "2°"},
    ]       # a zero rain chance is no news: EnvCan reports a missing one as 0 too


def test_weather_outlook_day_zero_in_utc_tomorrow_is_still_today():
    """Day 0 stamped 23:30 local is already tomorrow in UTC; the local date decides."""
    daily = [_fc(0, hour=23, temperature=14, condition="sunny"), *DAILY[1:]]
    days = _block(_weather(forecast={**FORECASTS, "daily": daily})[0], "forecast")["days"]
    assert [d["label"] for d in days] == ["Fri", "Sat", "Sun"]


def test_weather_hourly_strip_is_the_next_eight_hours_across_midnight():
    items = _block(_weather()[0], "hourly")["items"]
    assert items == [
        {"label": "7 PM", "glyph": "weather-rainy", "temp": "7°", "sub": "10%"},
        {"label": "8 PM", "glyph": "weather-rainy", "temp": "7°"},                 # 0% is left out
        {"label": "9 PM", "glyph": "weather-rainy", "temp": "6°", "sub": "30%"},
        {"label": "10 PM", "glyph": "weather-rainy", "temp": "6°", "sub": "40%"},
        {"label": "11 PM", "glyph": "weather-rainy", "temp": "6°", "sub": "50%"},
        {"label": "12 AM", "glyph": "weather-rainy", "temp": "5°", "sub": "60%"},
        {"label": "1 AM", "glyph": "weather-rainy", "temp": "5°", "sub": "70%"},
        {"label": "2 AM", "glyph": "weather-rainy", "temp": "5°", "sub": "80%"},
    ]


def test_weather_hourly_strip_skips_unusable_rows():
    hourly = [_hr(1, temperature=5, condition="cloudy", precipitation_probability=0),
              {"datetime": "junk", "temperature": 1}, "junk", {"condition": "sunny"},
              _hr(2, condition="sunny"),                      # no temperature: no cell
              _hr(3, temperature=-0.2, condition="volcanic-ash", precipitation_probability=5)]
    items = _block(_weather(forecast={**FORECASTS, "hourly": hourly})[0], "hourly")["items"]
    assert items == [{"label": "7 PM", "glyph": "weather-cloudy", "temp": "5°"},
                     {"label": "9 PM", "glyph": "weather-partly-cloudy", "temp": "0°", "sub": "5%"}]


def test_weather_hourly_strip_never_shows_the_current_or_past_hours():
    hourly = [_hr(-2, temperature=1), _hr(-1, temperature=2), _hr(0, temperature=3), _hr(1, temperature=4)]
    items = _block(_weather(forecast={**FORECASTS, "hourly": hourly})[0], "hourly")["items"]
    assert [(i["label"], i["temp"]) for i in items] == [("7 PM", "4°")]


def test_weather_chart_joins_observed_and_forecast_at_now():
    chart = _block(_weather()[0], "chart")
    assert (chart["start"], chart["step"], chart["count"]) == (W_START, 3600, 49)
    assert chart["title"] == "Outdoor · last 24 h and next 24 h"
    obs, fc = chart["series"]
    assert (obs["label"], obs["tone"], fc["label"], fc["tone"]) == ("Observed", "ink", "Forecast", "cool")
    assert obs["runs"] == [{"i": 0, "v": [_obs(i) for i in range(10)]},                 # bucket 10 is a gap
                           {"i": 11, "v": [_obs(i) for i in range(11, 24)] + [6.6]}]    # + the live reading
    assert fc["runs"] == [{"i": 24, "v": [6.6] + [float(7 - k // 3) for k in range(1, 25)]}]


def test_weather_chart_axes():
    chart = _block(_weather()[0], "chart")
    assert chart["x"]["ticks"] == [
        {"i": 0, "label": "6 PM"}, {"i": 6, "label": "Thu"}, {"i": 12, "label": "6 AM"},
        {"i": 18, "label": "12 PM"}, {"i": 24, "label": "Now", "strong": True}, {"i": 30, "label": "Fri"},
        {"i": 36, "label": "6 AM"}, {"i": 42, "label": "12 PM"}, {"i": 48, "label": "6 PM"}]
    y = chart["y"]
    assert y["min"] <= -1 and y["max"] >= 7 and all(t["label"].endswith("°") for t in y["ticks"])
    assert all(float(t["v"]).is_integer() for t in y["ticks"])      # whole degrees: -5, 0, 5, not -2.5


def test_weather_chart_without_forecast_is_observed_only():
    body, _ = _weather(forecast={"daily": DAILY})
    assert [s["label"] for s in _block(body, "chart")["series"]] == ["Observed"]
    assert _block(body, "hourly") is None


def test_weather_chart_without_history_has_only_the_live_dot_for_observed():
    body, _ = _weather(statistics=FakeHA.FAIL)
    chart = _block(body, "chart")
    assert [s["label"] for s in chart["series"]] == ["Observed", "Forecast"]
    assert chart["series"][0]["runs"] == [{"i": 24, "v": [6.6]}]
    assert _kinds(body) == ["now", "rows", "forecast", "hourly", "chart"]


def test_weather_chart_without_a_live_reading_starts_the_forecast_after_now():
    bare = _st("weather.edmonton_forecast", "rainy", humidity=58)             # no temperature, no sensor
    chart = _block(_weather(bare)[0], "chart")
    obs, fc = chart["series"]
    assert obs["runs"][-1]["i"] + len(obs["runs"][-1]["v"]) == 24             # history stops before Now
    assert fc["runs"][0]["i"] == 25                                           # the current hour's row is not drawn


def test_weather_chart_with_nothing_says_why():
    body, _ = _weather(statistics=FakeHA.FAIL, forecast={"daily": DAILY})
    chart = _block(body, "chart")
    assert chart["empty"] == "History unavailable" and "y" not in chart
    assert _block(body, "now") and _block(body, "forecast")
    body, _ = _weather(statistics={}, forecast={"daily": DAILY})
    assert _block(body, "chart")["empty"] == "No history yet"


def test_weather_forecast_with_a_hole_at_the_start_is_not_drawn_from_now():
    """A line from the live reading to a point 5 hours out would claim hours nobody forecast."""
    late = [_hr(k, temperature=4, condition="cloudy") for k in range(5, 20)]
    chart = _block(_weather(forecast={**FORECASTS, "hourly": late})[0], "chart")
    assert [s["label"] for s in chart["series"]] == ["Observed"]


def test_weather_each_source_fails_alone():
    body, _ = _weather(forecast={"daily": FakeHA.FAIL, "hourly": HOURLY})
    assert _kinds(body) == ["now", "rows", "hourly", "chart"]
    body, _ = _weather(forecast={"daily": DAILY, "hourly": FakeHA.FAIL})
    assert _kinds(body) == ["now", "rows", "forecast", "chart"]
    assert [s["label"] for s in _block(body, "chart")["series"]] == ["Observed"]


def test_weather_a_builder_that_raises_costs_only_its_block(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("bad row")
    monkeypatch.setattr(weather, "_facts_block", boom)
    assert _kinds(_weather()[0]) == ["now", "forecast", "hourly", "chart"]


def test_weather_junk_forecast_rows_are_ignored():
    junk = [{"datetime": "junk", "temperature": 3}, {"condition": "sunny"}, "junk", None]
    body, _ = _weather(forecast={"daily": junk, "hourly": junk})
    assert _kinds(body) == ["now", "rows", "chart"]


def test_weather_entity_down_still_answers_without_forecast_fetches():
    states = {k: v for k, v in WEATHER_STATES.items() if not k.startswith("weather.")}
    body, ha = _weather(states)
    now = _block(body, "now")
    assert now["temp"] == "7°" and "cond" not in now and "glyph" not in now   # the sensor still has a value
    assert ha.forecast_calls == []
    body, ha = _weather({})
    assert _block(body, "now") == {"type": "now", "col": 0, "temp": "--°"}
    assert [s["label"] for s in _block(body, "chart")["series"]] == ["Observed"]    # history alone


def test_weather_detail_asks_for_daily_and_hourly_once_each():
    _body, ha = _weather()
    assert sorted(ha.forecast_calls) == [("weather.edmonton_forecast", "daily"),
                                         ("weather.edmonton_forecast", "hourly")]
    stat_calls = [kw for name, kw in ha.calls if name == "get_statistics"]
    assert len(stat_calls) == 1
    kw = stat_calls[0]
    assert (kw["statistic_ids"], kw["period"], kw["types"]) == ([OUTDOOR], "hour", ["mean"])
    assert (kw["start"], kw["end"], kw["units"]) == (W_START, END, {"temperature": "°C"})


def test_weather_the_tile_still_asks_only_for_the_daily_forecast():
    ha = FakeHA(WEATHER_STATES, FORECASTS)
    weather.values(ha, {"kind": "weather", "entities": WEATHER_ENTS})
    assert ha.forecast_calls == [("weather.edmonton_forecast", "daily")]


def test_weather_chart_over_spring_forward_keeps_ticks_on_the_local_clock():
    """On 2026-03-08 clocks jump 02:00 -> 03:00, so the buckets after Now are one local hour short."""
    now = int(datetime(2026, 3, 8, 0, 30, tzinfo=TZ).timestamp())
    body, _ = _weather(forecast={"daily": []}, statistics={}, now=now)
    ticks = [(t["i"], t["label"]) for t in _block(body, "chart")["x"]["ticks"]]
    assert ticks == [(0, "Sat"), (6, "6 AM"), (12, "12 PM"), (18, "6 PM"), (24, "Now"),
                     (35, "12 PM"), (41, "6 PM"), (47, "Mon")]


# --- laundry -----------------------------------------------------------------------
LAUNDRY_DESC = {"kind": "laundry", "machines": [
    {"id": "washer", "label": "Washer", "color": "#00AAFF"},
    {"id": "dryer", "label": "Dryer", "color": "#FF6900"}]}


def _machine(mid, mode, started=None, finished=None):
    return {**_st(f"sensor.laundry_{mid}_mode", mode),
            **_st(f"input_datetime.laundry_{mid}_started", "x", timestamp=float(started or 0)),
            **_st(f"input_datetime.laundry_{mid}_finished", "x", timestamp=float(finished or 0)),
            **_st(f"input_number.laundry_{mid}_expected_minutes", "55")}


def _rows(*pairs):
    return [{"state": st, "last_changed": _iso(t)} for st, t in pairs]


LAUNDRY_HISTORY = {
    "sensor.laundry_washer_mode": _rows(
        ("running", WEEK_AGO), ("done", WEEK_AGO + 1800),                     # clipped at the window: dropped
        ("running", NOW - 2 * 86400), ("overtime", NOW - 2 * 86400 + 3300), ("done", NOW - 2 * 86400 + 3480),
        ("idle", NOW - 2 * 86400 + 4000), ("unavailable", NOW - 86400), ("idle", NOW - 86000),
        ("running", NOW - 9000), ("done", NOW - 9000 + 6780)),
    "sensor.laundry_dryer_mode": _rows(("idle", WEEK_AGO), ("running", NOW - 1500)),
}


def test_laundry_detail():
    states = {**_machine("washer", "done_calm", NOW - 9000, NOW - 9000 + 6780),
              **_machine("dryer", "running", NOW - 1500, NOW - 5 * 86400)}
    ha = FakeHA(states, history=LAUNDRY_HISTORY)
    body = _detail(laundry, ha, LAUNDRY_DESC)
    assert "note" not in body
    washer = _block(body, "rows", "Washer")["items"]
    assert washer == [
        {"glyph": "washing-machine", "tone": "washer", "label": "Status", "value": "Done 5:53 PM"},
        {"label": "Last started", "value": "Thu Oct 1 · 4:00 PM"},
        {"label": "Last finished", "value": "Thu Oct 1 · 5:53 PM"},
        {"label": "Last run length", "value": "1h 53m"},
    ]
    dryer = _block(body, "rows", "Dryer")["items"]
    assert dryer[0] == {"glyph": "tumble-dryer", "tone": "dryer", "label": "Status", "value": "30m left"}
    assert {"label": "Last run length", "value": "58m"} not in dryer   # no closed dryer run to fall back on
    assert [i["label"] for i in dryer] == ["Status", "Last started", "Last finished"]
    recent = _block(body, "rows", "Last 7 days")["items"]
    assert recent == [
        {"glyph": "tumble-dryer", "tone": "dryer", "label": "Dryer", "value": "Thu Oct 1 · 6:05 PM",
         "sub": "running now"},
        {"glyph": "washing-machine", "tone": "washer", "label": "Washer", "value": "Thu Oct 1 · 4:00 PM",
         "sub": "1h 53m"},
        {"glyph": "washing-machine", "tone": "washer", "label": "Washer", "value": "Tue Sep 29 · 6:30 PM",
         "sub": "58m"},
    ]
    call, = _calls(ha, "get_history")
    assert call == {"entity_ids": ["sensor.laundry_washer_mode", "sensor.laundry_dryer_mode"],
                    "start": WEEK_AGO, "end": None}


def test_laundry_run_length_falls_back_to_history_while_running():
    """Mid-run, `started` is newer than `finished`; the last closed run gives the length."""
    states = {**_machine("washer", "running", NOW - 600, NOW - 9000 + 6780), **_machine("dryer", "idle")}
    body = _detail(laundry, FakeHA(states, history=LAUNDRY_HISTORY), LAUNDRY_DESC)
    assert _block(body, "rows", "Washer")["items"][-1] == {"label": "Last run length", "value": "1h 53m"}


def test_laundry_never_set_timestamps_are_left_out():
    states = {**_machine("washer", "idle"), **_machine("dryer", "idle")}
    body = _detail(laundry, FakeHA(states, history={}), LAUNDRY_DESC)
    assert _block(body, "rows", "Washer")["items"] == [
        {"glyph": "washing-machine", "tone": "washer", "label": "Status", "value": "Idle"}]
    assert body["note"] == "No runs in the last 7 days"
    assert _block(body, "rows", "Last 7 days") is None


def test_laundry_history_failure_is_a_note():
    states = {**_machine("washer", "idle"), **_machine("dryer", "idle")}
    body = _detail(laundry, FakeHA(states, history=FakeHA.FAIL), LAUNDRY_DESC)
    assert body["note"] == "History unavailable"
    assert [b["title"] for b in body["blocks"]] == ["Washer", "Dryer"]


def test_laundry_stale_machine():
    body = _detail(laundry, FakeHA({}, history={}), LAUNDRY_DESC)
    assert _block(body, "rows", "Washer")["items"][0]["value"] == "No data"


# --- doors -------------------------------------------------------------------------
FRONT, BACK = "binary_sensor.front_doorcontact_contact", "binary_sensor.back_doorcontact_contact"
DOORS_DESC = {"kind": "doors", "openAlertSec": 300, "entities": {"doors": [
    {"id": "front", "entity": FRONT, "label": "Front"},
    {"id": "back", "entity": BACK, "label": "Back"}]}}


def _door(eid, state, changed):
    return {eid: {"entity_id": eid, "state": state, "last_changed": _iso(changed),
                  "attributes": {"device_class": "door"}}}


def test_doors_detail():
    states = {**_door(FRONT, "off", NOW - 1140), **_door(BACK, "on", NOW - 180)}
    logbook = {FRONT: [{"when": _iso(NOW - 1140), "state": "off"}],
               BACK: [{"when": _iso(NOW - 180), "state": "on"}]}
    history = {
        FRONT: _rows(("on", MIDNIGHT - 3600), ("off", MIDNIGHT + 1200),          # open overnight
                     ("on", NOW - 1200), ("unavailable", NOW - 1180), ("off", NOW - 1140)),
        BACK: _rows(("off", MIDNIGHT), ("on", MIDNIGHT + 8 * 3600 + 300), ("off", MIDNIGHT + 8 * 3600 + 345),
                    ("on", NOW - 180)),
    }
    ha = FakeHA(states, logbook=logbook, history=history)
    body = _detail(doors, ha, DOORS_DESC)
    assert _block(body, "rows", "Now")["items"] == [
        {"glyph": "door-closed", "tone": "sage", "label": "Front", "value": "Closed", "sub": "since 6:11 PM · 19m"},
        {"glyph": "door-open", "tone": "amber", "label": "Back", "value": "Open", "sub": "since 6:27 PM · 3m"},
    ]
    assert _block(body, "rows", "Today")["items"] == [
        {"glyph": "door-open", "tone": "amber", "label": "Back", "value": "6:27 PM", "sub": "open now"},
        {"glyph": "door-open", "tone": "amber", "label": "Front", "value": "6:10 PM", "sub": "1m"},
        {"glyph": "door-open", "tone": "amber", "label": "Back", "value": "8:05 AM", "sub": "<1m"},
        {"glyph": "door-open", "tone": "amber", "label": "Front", "value": "before 12:00 AM", "sub": "20m"},
    ]
    call, = _calls(ha, "get_history")
    assert call == {"entity_ids": [FRONT, BACK], "start": MIDNIGHT, "end": None}


def test_doors_now_rows_long_open_unknown_and_inexact():
    states = {**_door(FRONT, "on", NOW - 7200), **_door(BACK, "unavailable", NOW - 60)}
    body = _detail(doors, FakeHA(states, history={}), DOORS_DESC)
    front, back = _block(body, "rows", "Now")["items"]
    assert (front["tone"], front["value"], front["sub"]) == ("coral", "Open", "> 12h")   # no logbook row: inexact
    assert back == {"glyph": "door", "tone": "muted", "label": "Back", "value": "Unknown"}
    assert body["note"] == "No doors opened today"


def test_doors_since_yesterday_names_the_day():
    states = {**_door(FRONT, "off", NOW - 86400), **_door(BACK, "off", NOW - 3600)}
    logbook = {FRONT: [{"when": _iso(NOW - 86400), "state": "off"}]}
    body = _detail(doors, FakeHA(states, logbook=logbook, history={}), {**DOORS_DESC, "lookbackHours": 48})
    assert _block(body, "rows", "Now")["items"][0]["sub"] == "since Wed 6:30 PM · 1d"


def test_doors_history_failure_is_a_note():
    states = {**_door(FRONT, "off", NOW - 60), **_door(BACK, "off", NOW - 60)}
    body = _detail(doors, FakeHA(states, history=FakeHA.FAIL), DOORS_DESC)
    assert body["note"] == "History unavailable"
    assert [b["title"] for b in body["blocks"]] == ["Now"]


def test_doors_with_none_configured():
    body = _detail(doors, FakeHA(), {"kind": "doors", "entities": {}})
    assert body["blocks"] == [] and body["note"] == "No doors opened today"
    body = _detail(laundry, FakeHA(), {"kind": "laundry"})
    assert body["blocks"] == [] and body["note"] == "No runs in the last 7 days"


# --- dispatch ----------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["calendar", "timeline", "cameras", "nope"])
def test_kinds_without_detail(kind):
    assert modules.module_detail(FakeHA(), {"id": kind, "kind": kind, "tile": {"type": "value"}}) is None


def test_a_detail_that_raises_is_a_note(monkeypatch):
    def boom(ha, desc, now):
        raise KeyError("x")
    monkeypatch.setattr(water, "detail", boom)
    body = modules.module_detail(FakeHA(), {"id": "water", "kind": "water", "tile": {"type": "value"}}, NOW)
    assert body == {"v": 1, "id": "water", "title": "Water", "ts": NOW, "note": "Detail unavailable", "blocks": []}


def test_detail_gets_the_configured_timezone(monkeypatch):
    seen = {}
    monkeypatch.setattr(water, "detail", lambda ha, d, now: seen.update(tz=d.get("timezone")) or {"blocks": []})
    modules.module_detail(FakeHA(), {"id": "water", "kind": "water", "tile": {"type": "value"}})
    assert seen["tz"]
