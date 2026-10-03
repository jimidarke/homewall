"""Sidecar unit tests — run with: python -m pytest sidecar/tests -q

No Home Assistant or network needed: a FakeHA supplies canned states/forecast so we
exercise the value projection, the None-pruning contract, config parsing, and that
the weather card actually renders a PNG.
"""
import json
from datetime import date, datetime, timedelta, timezone

from PIL import Image

from haku_sidecar import charts
from haku_sidecar import config as cfg_module
from haku_sidecar import icons
from haku_sidecar import modules
from haku_sidecar.ha import HAClient
from haku_sidecar.modules import calendar as cal_mod
from haku_sidecar.modules import climate
from haku_sidecar.modules import energy
from haku_sidecar.modules import gas
from haku_sidecar.modules import timeline as tl_mod
from haku_sidecar.modules import water
from haku_sidecar.modules import weather
from haku_sidecar.store import CachedJson, prune

import pytest

from conftest import SECRET_TOKEN, FakeHA


WEATHER_STATE = {
    "weather.edmonton_forecast": {
        "entity_id": "weather.edmonton_forecast",
        "state": "rainy",
        "last_updated": "2026-07-05T13:17:00+00:00",
        "attributes": {"temperature": 12.4, "humidity": 86, "wind_speed": 15.0},
    },
    "weather.my_ecobee": {
        "entity_id": "weather.my_ecobee",
        "state": "cloudy",
        "attributes": {"temperature": 21.5},
    },
}
FORECAST = [
    {"datetime": "2026-07-05T13:00:00+00:00", "temperature": 21.0, "templow": 10.0, "condition": "rainy"},
    {"datetime": "2026-07-06T13:00:00+00:00", "temperature": 24.0, "templow": 12.0, "condition": "sunny"},
    {"datetime": "2026-07-07T13:00:00+00:00", "temperature": 19.0, "templow": 9.0, "condition": "cloudy"},
]

WEATHER_DESC = {
    "id": "weather", "kind": "weather", "feedKey": "weather",
    "tile": {"type": "value"},
    "entities": {"forecast": "weather.edmonton_forecast", "indoor": "weather.my_ecobee"},
}
CAMERAS_DESC = {
    "id": "cameras", "kind": "cameras", "feedKey": "cameras",
    "tile": {"type": "camera", "thumbCam": "front"},
    "streams": ["front", "yard", "side", "backyard"],
}

ENERGY_STATE = {
    "sensor.emporia_total_power": {
        "entity_id": "sensor.emporia_total_power", "state": "2412",
        "attributes": {"unit_of_measurement": "W"},
    },
    "sensor.emporia_total_daily_energy_kwh": {
        "entity_id": "sensor.emporia_total_daily_energy_kwh", "state": "18.23",
        "attributes": {"unit_of_measurement": "kWh"},
    },
    "sensor.electricity_daily_cost": {
        "entity_id": "sensor.electricity_daily_cost", "state": "4.12",
        "attributes": {"unit_of_measurement": "USD"},
    },
}
ENERGY_SPIKE_STATE = dict(ENERGY_STATE)
ENERGY_SPIKE_STATE["sensor.emporia_total_power"] = {
    "entity_id": "sensor.emporia_total_power", "state": "6200",
    "attributes": {"unit_of_measurement": "W"},
}
ENERGY_DESC = {
    "id": "energy", "kind": "energy", "feedKey": "energy",
    "tile": {"type": "value"},
    "entities": {
        "power": "sensor.emporia_total_power",
        "daily_energy": "sensor.emporia_total_daily_energy_kwh",
        "cost": "sensor.electricity_daily_cost",
        "cost_fallback": "sensor.emporia_total_daily_energy_kwh_cost",
    },
}

WATER_STATE = {
    "sensor.water_meter_hourly": {
        "entity_id": "sensor.water_meter_hourly", "state": "12.0",
        "attributes": {"unit_of_measurement": "L"},
    },
    "sensor.water_meter_flow": {
        "entity_id": "sensor.water_meter_flow", "state": "4.2",
        "attributes": {"unit_of_measurement": "L/min"},
    },
    "sensor.water_meter_daily": {
        "entity_id": "sensor.water_meter_daily", "state": "210",
        "attributes": {"unit_of_measurement": "L"},
    },
    "sensor.water_meter_monthly": {
        "entity_id": "sensor.water_meter_monthly", "state": "6100",
        "attributes": {"unit_of_measurement": "L"},
    },
    "sensor.water_meter_total": {
        "entity_id": "sensor.water_meter_total", "state": "812345",
        "attributes": {"unit_of_measurement": "L"},
    },
}
WATER_IDLE_STATE = dict(WATER_STATE)
WATER_IDLE_STATE["sensor.water_meter_flow"] = {
    "entity_id": "sensor.water_meter_flow", "state": "0",
    "attributes": {"unit_of_measurement": "L/min"},
}
WATER_DESC = {
    "id": "water", "kind": "water", "feedKey": "water",
    "tile": {"type": "value"},
    "entities": {
        "hourly": "sensor.water_meter_hourly",
        "flow": "sensor.water_meter_flow",
        "daily": "sensor.water_meter_daily",
        "monthly": "sensor.water_meter_monthly",
        "total": "sensor.water_meter_total",
    },
}

GAS_STATE = {
    "sensor.home_gas_usage": {
        "entity_id": "sensor.home_gas_usage", "state": "0.65",
        "attributes": {"unit_of_measurement": "m³/h"},
    },
    "sensor.gas_meter_gas_meter_direct": {
        "entity_id": "sensor.gas_meter_gas_meter_direct", "state": "17.45",
        "attributes": {"unit_of_measurement": "m³"},
    },
}
GAS_IDLE_STATE = dict(GAS_STATE)
GAS_IDLE_STATE["sensor.home_gas_usage"] = {
    "entity_id": "sensor.home_gas_usage", "state": "0",
    "attributes": {"unit_of_measurement": "m³/h"},
}
GAS_DESC = {
    "id": "gas", "kind": "gas", "feedKey": "gas",
    "tile": {"type": "value"},
    "entities": {
        "flow": "sensor.home_gas_usage",
        "total": "sensor.gas_meter_gas_meter_direct",
    },
}

CLIMATE_STATE = {
    "climate.my_ecobee": {
        "entity_id": "climate.my_ecobee", "state": "heat",
        "attributes": {
            "current_temperature": 23.1, "current_humidity": 56,
            "hvac_action": "heating", "preset_mode": "home",
        },
    },
}
CLIMATE_IDLE_STATE = dict(CLIMATE_STATE)
CLIMATE_IDLE_STATE["climate.my_ecobee"] = {
    "entity_id": "climate.my_ecobee", "state": "heat",
    "attributes": {
        "current_temperature": 21.0, "current_humidity": 48,
        "hvac_action": "idle", "preset_mode": "away",
    },
}
CLIMATE_OFF_STATE = dict(CLIMATE_STATE)
CLIMATE_OFF_STATE["climate.my_ecobee"] = {
    "entity_id": "climate.my_ecobee", "state": "off",
    "attributes": {
        "current_temperature": 19.5, "current_humidity": 52,
        "hvac_action": "off", "preset_mode": "sleep",
    },
}
CLIMATE_DESC = {
    "id": "climate", "kind": "climate", "feedKey": "climate",
    "tile": {"type": "value"},
    "entities": {"thermostat": "climate.my_ecobee"},
}


def test_prune_drops_none_keeps_empty():
    assert prune({"a": 1, "b": None, "c": {"d": None, "e": 2}, "f": []}) == {
        "a": 1, "c": {"e": 2}, "f": []
    }


def test_weather_values_shape():
    ha = FakeHA(WEATHER_STATE, FORECAST)
    v = weather.values(ha, WEATHER_DESC)
    assert v["temp_c"] == 12.4
    assert v["condition"] == "rainy"
    assert v["cond_label"] == "Rainy"
    assert v["humidity"] == 86
    assert v["high_c"] == 21.0 and v["low_c"] == 10.0
    assert v["indoor_c"] == 21.5
    assert v["stale"] is False
    assert v["observed_hm"] == "13:17"
    # display-ready tile projection (sidecar owns formatting)
    assert v["tile"]["hero"] == "12°"
    assert v["tile"]["sub"] == "Rainy"
    assert "H 21°" in v["tile"]["detail"] and "86% RH" in v["tile"]["detail"]


def test_weather_stale_when_missing():
    v = weather.values(FakeHA({}, []), WEATHER_DESC)
    assert v["stale"] is True
    assert v["condition"] is None


def test_weather_tile_icon_reflects_condition():
    v = weather.values(FakeHA(WEATHER_STATE, FORECAST), WEATHER_DESC)
    assert v["tile"]["icon"] == "rainy"


def test_weather_tile_icon_empty_when_stale():
    v = weather.values(FakeHA({}, []), WEATHER_DESC)
    assert v["tile"]["icon"] == ""


def test_weather_render_icon_returns_png():
    png = weather.render_icon(FakeHA(WEATHER_STATE, FORECAST), WEATHER_DESC)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_weather_render_icon_none_when_stale():
    assert weather.render_icon(FakeHA({}, []), WEATHER_DESC) is None


def test_weather_render_icon_falls_back_for_unmapped_condition():
    states = {"weather.edmonton_forecast": {**WEATHER_STATE["weather.edmonton_forecast"],
                                             "state": "some-future-condition"}}
    png = weather.render_icon(FakeHA(states, FORECAST), WEATHER_DESC)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"   # falls back to icons.DEFAULT_GLYPH, still renders


def test_compose_state_pruned_and_keyed():
    ha = FakeHA(WEATHER_STATE, FORECAST)
    config = {"modules": [WEATHER_DESC, CAMERAS_DESC]}
    snap = modules.compose_state(ha, config)
    assert "weather" in snap and "cameras" in snap
    assert snap["cameras"]["count"] == 4
    # None-pruned: a missing indoor temp key must be absent, never null.
    lean = modules.compose_state(FakeHA({}, []), {"modules": [WEATHER_DESC]})
    assert "indoor_c" not in lean["weather"]
    assert json.dumps(snap).find("null") == -1


def test_weather_card_renders_png():
    ha = FakeHA(WEATHER_STATE, FORECAST)
    png = modules.render_card(ha, "weather_forecast", {"modules": [WEATHER_DESC]}, 560, 360)
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic
    assert len(png) > 1000


def test_card_renders_without_forecast():
    ha = FakeHA(WEATHER_STATE, [])  # forecast unavailable path
    png = charts.render_weather_forecast({"temp_c": 12, "cond_label": "Rainy"}, [], 560, 360)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_card_unknown_returns_none():
    assert modules.render_card(FakeHA(), "nope", {"modules": [WEATHER_DESC]}, 560, 360) is None


# --- icons.py: fill_bucket_pct + render dispatch ----------------------------
def test_fill_bucket_pct_rounds_to_nearest_step():
    assert icons.fill_bucket_pct(2.3, 5.0) == 45   # 46% -> nearest 5% step
    assert icons.fill_bucket_pct(0, 5.0) == 0
    assert icons.fill_bucket_pct(5.0, 5.0) == 100


def test_fill_bucket_pct_clamps_past_max():
    assert icons.fill_bucket_pct(9.0, 5.0) == 100


def test_fill_bucket_pct_none_or_zero_max_is_zero():
    assert icons.fill_bucket_pct(None, 5.0) == 0
    assert icons.fill_bucket_pct(3.0, 0) == 0


def test_render_icon_dispatch_returns_pngs_for_supported_modules():
    ha = FakeHA({**WEATHER_STATE, **ENERGY_STATE, **WATER_STATE}, FORECAST)
    config = {"modules": [WEATHER_DESC, ENERGY_DESC, WATER_DESC]}
    for module_id in ("weather", "energy", "water"):
        png = modules.render_icon(ha, module_id, config, 96, 96)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_icon_none_for_kind_without_icon():
    config = {"modules": [CAL_DESC]}
    assert modules.render_icon(FakeHA(), "calendar", config, 96, 96) is None


def test_render_icon_none_for_unknown_module_id():
    assert modules.render_icon(FakeHA(), "nope", {"modules": [WEATHER_DESC]}, 96, 96) is None


def test_energy_values_shape_and_w_to_kw():
    v = energy.values(FakeHA(ENERGY_STATE), ENERGY_DESC)
    assert v["power_kw"] == 2.4          # 2412 W -> 2.4 kW conversion
    assert v["daily_kwh"] == 18
    assert v["cost"] == 4.12
    assert v["stale"] is False
    assert v["tile"]["hero"] == "2.4 kW"
    assert v["tile"]["sub"] == "18 kWh today"
    assert v["tile"]["detail"] == "$4.12 so far"
    assert v["tile"]["severity"] == "normal"


def test_energy_spike_severity():
    v = energy.values(FakeHA(ENERGY_SPIKE_STATE), ENERGY_DESC)
    assert v["power_kw"] == 6.2
    assert v["tile"]["severity"] == "high"   # > _SPIKE_KW


def test_energy_cost_fallback():
    states = dict(ENERGY_STATE)
    del states["sensor.electricity_daily_cost"]
    states["sensor.emporia_total_daily_energy_kwh_cost"] = {
        "entity_id": "sensor.emporia_total_daily_energy_kwh_cost", "state": "3.90",
        "attributes": {"unit_of_measurement": "USD"},
    }
    v = energy.values(FakeHA(states), ENERGY_DESC)
    assert v["cost"] == 3.9
    assert v["tile"]["detail"] == "$3.90 so far"


def test_energy_stale_when_missing():
    v = energy.values(FakeHA({}), ENERGY_DESC)
    assert v["stale"] is True
    assert v["tile"]["hero"] == "-- kW"
    assert "power_kw" not in prune(v)        # None-pruned


def test_energy_tile_icon_bucket_pct_of_spike_kw():
    v = energy.values(FakeHA(ENERGY_STATE), ENERGY_DESC)
    assert v["tile"]["icon"] == "50"   # 2.4kW / 5.0kW -> ~48% -> nearest 5% step


def test_energy_tile_icon_clamps_past_spike():
    v = energy.values(FakeHA(ENERGY_SPIKE_STATE), ENERGY_DESC)
    assert v["tile"]["icon"] == "100"  # 6.2kW clamps to full


def test_energy_tile_icon_empty_when_stale():
    v = energy.values(FakeHA({}), ENERGY_DESC)
    assert v["tile"]["icon"] == ""


def test_energy_render_icon_battery_png():
    png = energy.render_icon(FakeHA(ENERGY_STATE), ENERGY_DESC)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_energy_render_icon_none_when_missing():
    assert energy.render_icon(FakeHA({}), ENERGY_DESC) is None


def test_water_values_shape_and_flow_severity():
    v = water.values(FakeHA(WATER_STATE), WATER_DESC)
    assert v["hourly"] == 12.0
    assert v["flow"] == 4.2
    assert v["running"] is True
    assert v["tile"]["hero"] == "12 L"
    assert v["tile"]["sub"] == "flowing 4.2 L/min"
    assert "24h 210 L" in v["tile"]["detail"]
    assert "30d 6100 L" in v["tile"]["detail"]
    assert v["tile"]["severity"] == "high"   # flow > 0


def test_water_idle_severity_normal():
    v = water.values(FakeHA(WATER_IDLE_STATE), WATER_DESC)
    assert v["running"] is False
    assert v["tile"]["sub"] == "idle"
    assert v["tile"]["severity"] == "normal"


def test_water_missing_period_omits_line():
    states = dict(WATER_STATE)
    del states["sensor.water_meter_monthly"]         # 30d sensor absent
    v = water.values(FakeHA(states), WATER_DESC)
    assert v["monthly"] is None
    assert "30d" not in v["tile"]["detail"]          # line dropped, not broken
    assert "24h 210 L" in v["tile"]["detail"]        # 24h still present
    assert "monthly" not in prune(v)                 # None-pruned from snapshot


def test_water_stale_when_empty():
    v = water.values(FakeHA({}), WATER_DESC)
    assert v["stale"] is True
    assert v["tile"]["hero"] == "-- L"


def test_water_tile_icon_uses_default_max_flow():
    v = water.values(FakeHA(WATER_STATE), WATER_DESC)
    assert v["tile"]["icon"] == "40"   # 4.2 L/min / 10.0 default -> 42% -> nearest 5% step


def test_water_tile_icon_respects_configured_max_flow():
    desc = {**WATER_DESC, "maxFlowLpm": 12}
    v = water.values(FakeHA(WATER_STATE), desc)
    assert v["tile"]["icon"] == "35"   # 4.2 / 12.0 -> 35% -> nearest 5% step


def test_water_tile_icon_zero_when_idle():
    v = water.values(FakeHA(WATER_IDLE_STATE), WATER_DESC)
    assert v["tile"]["icon"] == "0"


def test_water_render_icon_bucket_png():
    png = water.render_icon(FakeHA(WATER_STATE), WATER_DESC)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_water_render_icon_empty_bucket_when_idle():
    png = water.render_icon(FakeHA(WATER_IDLE_STATE), WATER_DESC)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"   # flow=0 still renders (empty bucket), not None


def test_water_render_icon_none_when_sensor_missing():
    assert water.render_icon(FakeHA({}), WATER_DESC) is None


def test_gas_values_shape_and_hero_always_shows_flow():
    v = gas.values(FakeHA(GAS_STATE), GAS_DESC)
    assert v["flow"] == 0.7          # round1(0.65)
    assert v["total"] == 17.4        # round1(17.45)
    assert v["stale"] is False
    assert v["tile"]["hero"] == "0.7 m³/h"
    assert v["tile"]["sub"] == "running"
    assert v["tile"]["detail"] == "17 m³ total"
    assert v["tile"]["severity"] == "normal"


def test_gas_idle_hero_still_shows_zero_flow():
    v = gas.values(FakeHA(GAS_IDLE_STATE), GAS_DESC)
    assert v["tile"]["hero"] == "0.0 m³/h"   # zero flow is the normal state, never hidden
    assert v["tile"]["sub"] == ""
    assert v["tile"]["severity"] == "normal"


def test_gas_stale_when_missing():
    v = gas.values(FakeHA({}), GAS_DESC)
    assert v["stale"] is True
    assert v["tile"]["hero"] == "-- m³/h"
    assert "flow" not in prune(v)


def test_gas_tile_icon_bucket_pct_of_max_flow():
    v = gas.values(FakeHA(GAS_STATE), GAS_DESC)
    assert v["tile"]["icon"] == "30"   # 0.65 / 2.0 default -> nearest 5% step


def test_gas_tile_icon_respects_configured_max_flow():
    desc = {**GAS_DESC, "maxFlowM3h": 1.2}
    v = gas.values(FakeHA(GAS_STATE), desc)
    assert v["tile"]["icon"] == "55"   # 0.65 / 1.2 -> nearest 5% step


def test_gas_tile_icon_empty_when_stale():
    v = gas.values(FakeHA({}), GAS_DESC)
    assert v["tile"]["icon"] == ""


def test_gas_render_icon_bucket_png():
    png = gas.render_icon(FakeHA(GAS_STATE), GAS_DESC)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_gas_render_icon_none_when_missing():
    assert gas.render_icon(FakeHA({}), GAS_DESC) is None


def test_climate_values_heating():
    v = climate.values(FakeHA(CLIMATE_STATE), CLIMATE_DESC)
    assert v["stale"] is False
    assert v["tile"]["hero"] == "23°"
    assert v["tile"]["sub"] == "Heating"
    assert v["tile"]["detail"] == "56% RH   Home mode"
    assert v["tile"]["severity"] == "normal"


def test_climate_values_idle():
    v = climate.values(FakeHA(CLIMATE_IDLE_STATE), CLIMATE_DESC)
    assert v["tile"]["hero"] == "21°"
    assert v["tile"]["sub"] == "Idle"
    assert "Away mode" in v["tile"]["detail"]


def test_climate_values_off():
    v = climate.values(FakeHA(CLIMATE_OFF_STATE), CLIMATE_DESC)
    assert v["tile"]["sub"] == "Off"
    assert "Sleep mode" in v["tile"]["detail"]


def test_climate_stale_when_missing():
    v = climate.values(FakeHA({}), CLIMATE_DESC)
    assert v["stale"] is True
    assert v["tile"]["hero"] == "--°"
    assert "current_temp" not in prune(v)


def test_climate_has_no_render_icon():
    # Deliberate v1 scope decision (see modules/climate.py docstring) -- locks
    # in that calendar/timeline/cameras's "no accent icon" precedent extends
    # to climate too, so a future refactor doesn't add one by accident.
    assert not hasattr(climate, "render_icon")


def test_compose_state_includes_energy_water_no_null():
    ha = FakeHA({**WEATHER_STATE, **ENERGY_STATE, **WATER_STATE}, FORECAST)
    config = {"modules": [WEATHER_DESC, CAMERAS_DESC, ENERGY_DESC, WATER_DESC]}
    snap = modules.compose_state(ha, config)
    assert "energy" in snap and "water" in snap
    assert snap["energy"]["tile"]["hero"] == "2.4 kW"
    assert snap["water"]["tile"]["severity"] == "high"
    assert json.dumps(snap).find("null") == -1       # extends the no-null contract


# --- weather card is a transparent (glass) PNG -----------------------------
def test_weather_card_has_alpha_channel():
    """The dark glass card must save with an alpha channel so it composites."""
    png = charts.render_weather_forecast(
        {"temp_c": 12, "cond_label": "Rainy"}, FORECAST, 560, 360)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    import io as _io
    with Image.open(_io.BytesIO(png)) as im:
        assert im.mode == "RGBA"                      # transparent=True keeps alpha
        assert im.getchannel("A").getextrema()[0] < 255  # some pixels are transparent


# --- HA status never leaks the token ---------------------------------------
def test_ha_status_exposes_url_and_token_present():
    ha = HAClient("http://ha.example:8123", SECRET_TOKEN)
    st = ha.status()
    assert st["url"] == "http://ha.example:8123"
    assert st["token_present"] is True
    # The token STRING must never appear anywhere in the serialized status.
    assert SECRET_TOKEN not in json.dumps(st)


def test_ha_status_token_present_false_when_empty():
    assert HAClient("http://ha.example:8123", "").status()["token_present"] is False
    assert HAClient("http://ha.example:8123", None).status()["token_present"] is False


# --- Flask app: new routes + no-token contract (`client` lives in conftest) --
def test_api_health_reports_token_present_without_token(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.get_json()
    assert "token_present" in body["ha"]
    assert "url" in body["ha"]
    # The token value must never be serialized into any response.
    assert SECRET_TOKEN not in r.get_data(as_text=True)
    assert json.dumps(body).find("null") == -1


def test_api_config_includes_background_block(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.get_json()
    assert body["background"] == {"intervalMs": 20000, "enabled": True}


def test_api_icon_404s_for_unknown_module(client):
    # DEFAULT_CONFIG (forced by the `client` fixture) has no modules configured.
    assert client.get("/api/icon/weather.png").status_code == 404
    assert client.get("/api/icon/nope.png").status_code == 404


def test_api_icon_serves_png_end_to_end(client, monkeypatch):
    from haku_sidecar import app as app_module
    monkeypatch.setattr(
        cfg_module, "_cache",
        CachedJson("/nonexistent/haku/dashboard.json",
                   {**cfg_module.DEFAULT_CONFIG, "modules": [WEATHER_DESC, ENERGY_DESC, WATER_DESC]}))
    monkeypatch.setattr(app_module, "ha", FakeHA({**WEATHER_STATE, **ENERGY_STATE, **WATER_STATE}, FORECAST))
    for module_id in ("weather", "energy", "water"):
        r = client.get(f"/api/icon/{module_id}.png")
        assert r.status_code == 200
        assert r.mimetype == "image/png"
        assert r.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert client.get("/api/icon/calendar.png").status_code == 404


# --- calendar module -------------------------------------------------------
CAL_LIST = [{"entity_id": "calendar.family", "name": "Family Calendar"}]
CAL_DESC = {
    "id": "calendar", "kind": "calendar", "feedKey": "calendar",
    "tile": {"type": "agenda"}, "entities": {"calendars": ["calendar.family"]},
}


def _cal_events():
    today = date.today()
    d0, d1, d2 = [(today + timedelta(days=n)).isoformat() for n in (0, 1, 2)]
    return {"calendar.family": [
        {"start": {"dateTime": f"{d0}T09:00:00-06:00"}, "end": {"dateTime": f"{d0}T09:30:00-06:00"},
         "summary": "Standup", "description": None, "location": None},
        {"start": {"date": d0}, "end": {"date": d1}, "summary": "Trash day"},
        {"start": {"dateTime": f"{d1}T08:00:00-06:00"}, "summary": "Soccer"},
        {"start": {"dateTime": f"{d2}T15:30:00-06:00"}, "summary": None},  # busy / no title
    ]}


def test_calendar_grouping_and_formatting():
    v = cal_mod.values(FakeHA(calendars=CAL_LIST, events=_cal_events()), CAL_DESC)
    assert v["count"] == 4
    items = v["items"]
    assert items[0] == {"kind": "header", "title": "TODAY"}
    # all-day sorts before timed within the same day
    assert items[1]["title"] == "Trash day" and items[1]["time"] == "all day"
    assert items[2]["title"] == "Standup" and items[2]["time"] == "9:00 AM"
    hdrs = [it["title"] for it in items if it["kind"] == "header"]
    assert "TOMORROW" in hdrs
    soccer = next(it for it in items if it.get("title") == "Soccer")
    assert soccer["time"] == "8:00 AM"
    # null summary -> "(busy)"; 24h -> 12h PM
    busy = next(it for it in items if it.get("time") == "3:30 PM")
    assert busy["title"] == "(busy)"
    # a >tomorrow day gets a weekday·month·day header
    assert any("·" in h for h in hdrs)


def test_calendar_tile_projection():
    t = cal_mod.values(FakeHA(calendars=CAL_LIST, events=_cal_events()), CAL_DESC)["tile"]
    assert t["hero"] == "Trash day"               # first upcoming (all-day today)
    assert t["sub"].startswith("then 9:00 AM")
    assert t["detail"] == "2 today"               # Standup + Trash day
    assert t["severity"] == "normal"


def test_calendar_autodiscover_when_unconfigured():
    desc = {"id": "calendar", "kind": "calendar", "tile": {"type": "agenda"}, "entities": {}}
    v = cal_mod.values(FakeHA(calendars=CAL_LIST, events=_cal_events()), desc)
    assert v["count"] == 4                          # merged ALL discovered calendars


def test_calendar_empty_and_12h_edges():
    v = cal_mod.values(FakeHA(calendars=CAL_LIST, events={}), CAL_DESC)
    assert v["count"] == 0 and v["items"] == [] and v["tile"]["hero"] == "—"
    assert cal_mod._to12h("00:00") == "12:00 AM"
    assert cal_mod._to12h("12:00") == "12:00 PM"
    assert cal_mod._to12h("13:05") == "1:05 PM"


# --- timeline module (watched-entities framework) --------------------------
TL_STATES = {
    "binary_sensor.front_door": {"entity_id": "binary_sensor.front_door", "state": "off",
        "attributes": {"device_class": "door", "friendly_name": "Front Door"}},
    "binary_sensor.hall_motion": {"entity_id": "binary_sensor.hall_motion", "state": "on",
        "attributes": {"device_class": "occupancy", "friendly_name": "Hallway"}},
    "person.jimi": {"entity_id": "person.jimi", "state": "home",
        "attributes": {"friendly_name": "Jimi"}},
}
TL_DESC = {
    "id": "timeline", "kind": "timeline", "feedKey": "timeline",
    "tile": {"type": "agenda", "rotate": True},
    "coalesceWindowSec": 300, "lookbackHours": 12,
    "entities": {"watch": ["binary_sensor.front_door", "binary_sensor.hall_motion", "person.jimi"]},
}


def _iso(secs_ago):
    return (datetime.now(timezone.utc) - timedelta(seconds=secs_ago)).isoformat()


def _tl_logbook():
    return {
        "binary_sensor.front_door": [{"when": _iso(130), "state": "on", "name": "Front Door"}],
        "binary_sensor.hall_motion": [                       # flapping motion sensor
            {"when": _iso(8), "state": "on", "name": "Hallway"},
            {"when": _iso(12), "state": "on", "name": "Hallway"},
            {"when": _iso(500), "state": "on", "name": "Hallway"},
            {"when": _iso(505), "state": "off", "name": "Hallway"},
        ],
        "person.jimi": [{"when": _iso(90), "state": "home", "name": "Jimi"}],
    }


def test_timeline_coalesce_and_transition_policy():
    v = tl_mod.values(FakeHA(TL_STATES, logbook=_tl_logbook()), TL_DESC)
    events = [it for it in v["items"] if it["kind"] == "event"]
    # 4 raw hall rows -> 2 bursts (recent + ~8m ago); motion "off" dropped entirely
    assert len([e for e in events if e["title"] == "Hallway"]) == 2
    assert all(e["sub"] != "clear" for e in events)
    assert v["count"] == 4                            # hall(2) + door(1) + jimi(1)
    assert events[0]["title"] == "Hallway" and events[0]["time"] == "now"   # newest first
    # The open has no close in the logbook but HA says the door is shut now: the close is
    # newer than the cached logbook, so it reads "opened" (no duration) and isn't urgent.
    door = next(e for e in events if e["title"] == "Front Door")
    assert door["sub"] == "opened" and door["severity"] == "normal" and door["time"] == "2m"
    assert door["glyph"] == "door-closed"
    jimi = next(e for e in events if e["title"] == "Jimi")
    assert jimi["sub"] == "→ home" and jimi["severity"] == "low" and jimi["time"] == "1m"


def test_timeline_drops_restart_repeats():
    """An HA or Zigbee2MQTT restart replays every contact's and person's state; only real
    changes show (2026-10-01: "Front Door closed 11m" while the door card said 50m)."""
    logbook = {
        "binary_sensor.front_door": [
            {"when": _iso(3600), "state": "on", "name": "Front Door"},
            {"when": _iso(2990), "state": "off", "name": "Front Door"},     # real close
            {"when": _iso(660), "state": "off", "name": "Front Door"},      # restart replay
        ],
        "binary_sensor.hall_motion": [],
        "person.jimi": [
            {"when": _iso(2000), "state": "home", "name": "Jimi"},
            {"when": _iso(1500), "state": "unavailable", "name": "Jimi"},
            {"when": _iso(1490), "state": "not_home", "name": "Jimi"},       # a real change across an outage
            {"when": _iso(660), "state": "not_home", "name": "Jimi"},        # restart replay
        ],
    }
    v = tl_mod.values(FakeHA(TL_STATES, logbook=logbook), TL_DESC)
    events = [(e["title"], e["sub"]) for e in v["items"] if e["kind"] == "event"]
    # the open and its real close pair into one row stamped at the opening; the replay is gone
    assert [s for t, s in events if t == "Front Door"] == ["opened · 10m"]
    assert [s for t, s in events if t == "Jimi"] == ["→ away", "→ home"]
    door = next(e for e in v["items"] if e.get("title") == "Front Door")
    assert door["time"] == "1h"


def test_timeline_sections_and_tile():
    v = tl_mod.values(FakeHA(TL_STATES, logbook=_tl_logbook()), TL_DESC)
    assert v["items"][0] == {"kind": "header", "title": "TODAY"}   # all within today
    assert v["tile"]["hero"] == "Hallway"
    assert v["tile"]["sub"] == "motion · now"
    assert v["tile"]["severity"] == "normal"


def test_timeline_section_uses_ha_timezone_not_system_clock():
    # 2026-07-06T00:15 UTC and 2026-07-05T23:50 UTC fall on different UTC calendar
    # days, but both are the evening of 2026-07-05 in Edmonton (UTC-6 in summer).
    # Sectioning must follow HA's local day, not whatever tz the sidecar host is set to.
    now = int(datetime(2026, 7, 6, 0, 15, tzinfo=timezone.utc).timestamp())
    when = int(datetime(2026, 7, 5, 23, 50, tzinfo=timezone.utc).timestamp())
    assert tl_mod._section(when, now, "America/Edmonton") == "TODAY"


def test_timeline_empty_watch():
    v = tl_mod.values(FakeHA(TL_STATES), {"entities": {"watch": []}})
    assert v["count"] == 0 and v["items"] == [] and v["tile"]["hero"] == "—"


def test_compose_state_agenda_modules_no_null():
    ha = FakeHA(TL_STATES, calendars=CAL_LIST, events=_cal_events(), logbook=_tl_logbook())
    snap = modules.compose_state(ha, {"modules": [TL_DESC, CAL_DESC]})
    assert "timeline" in snap and "calendar" in snap
    assert snap["timeline"]["tile"]["hero"] == "Hallway"
    assert isinstance(snap["calendar"]["items"], list)
    assert json.dumps(snap).find("null") == -1       # extends the no-null contract


# --- config: single-source-of-truth timezone --------------------------------
def test_config_default_timezone_is_edmonton():
    assert cfg_module.DEFAULT_TIMEZONE == "America/Edmonton"


def test_config_get_timezone_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(cfg_module, "_cache", CachedJson("/nonexistent", {}))
    assert cfg_module.get_timezone() == cfg_module.DEFAULT_TIMEZONE


def test_config_get_timezone_reads_configured_value(monkeypatch):
    monkeypatch.setattr(cfg_module, "_cache", CachedJson("/nonexistent", {"timezone": "Europe/Berlin"}))
    assert cfg_module.get_timezone() == "Europe/Berlin"


def test_config_resolve_zone_none_when_no_name_given():
    assert cfg_module.resolve_zone(None) is None
    assert cfg_module.resolve_zone("") is None


def test_config_resolve_zone_valid_name():
    tz = cfg_module.resolve_zone("America/Edmonton")
    # Mid-summer Edmonton is UTC-6 (MDT).
    dt = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc).astimezone(tz)
    assert dt.utcoffset().total_seconds() == -6 * 3600


def test_config_resolve_zone_bad_name_fails_safe_to_utc():
    assert cfg_module.resolve_zone("Not/ARealZone") is timezone.utc


def test_module_values_injects_configured_timezone_when_absent(monkeypatch):
    monkeypatch.setattr(cfg_module, "_cache",
                         CachedJson("/nonexistent", {"timezone": "America/Edmonton"}))
    captured = {}

    class _EchoModule:
        @staticmethod
        def values(ha, descriptor):
            captured["timezone"] = descriptor.get("timezone")
            return {}

    monkeypatch.setitem(modules.MODULES, "echo", _EchoModule)
    modules.module_values(FakeHA(), {"id": "x", "kind": "echo"})
    assert captured["timezone"] == "America/Edmonton"


def test_module_values_respects_explicit_per_module_timezone(monkeypatch):
    monkeypatch.setattr(cfg_module, "_cache",
                         CachedJson("/nonexistent", {"timezone": "America/Edmonton"}))
    captured = {}

    class _EchoModule:
        @staticmethod
        def values(ha, descriptor):
            captured["timezone"] = descriptor.get("timezone")
            return {}

    monkeypatch.setitem(modules.MODULES, "echo", _EchoModule)
    modules.module_values(FakeHA(), {"id": "x", "kind": "echo", "timezone": "Europe/Berlin"})
    assert captured["timezone"] == "Europe/Berlin"
