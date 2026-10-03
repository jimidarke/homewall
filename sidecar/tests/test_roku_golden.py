"""Roku golden guard: the default (no `?layout=`) /api/config and /api/state, byte for byte.

The Rokus read the default view, and v3's tablet work (rate tiles, details, the stale
truth fix) must not change a byte of it. The goldens in `tests/golden/` were captured
before any v3 behaviour change, from `dashboard.json.example`'s top-level modules, a
FakeHA where every entity is valid (so the stale fix has nothing to correct) and a frozen
clock (2026-10-01 18:30 in America/Edmonton, which is already 2026-10-02 in UTC).

The files are pretty-printed for review; the test re-serializes them the way Flask's
default JSON provider does (sorted keys, compact, ASCII, trailing newline) and compares
the response bytes, so an int turning into a float or a key changing order also fails.

Regenerate only on purpose, after confirming the Roku should see the change:
    HAKU_UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/test_roku_golden.py
"""
import json
import os
import types
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from conftest import FakeHA

from haku_sidecar import config as cfg_module
from haku_sidecar import store
from haku_sidecar.modules import calendar as cal_mod
from haku_sidecar.modules import cameras as cam_mod
from haku_sidecar.modules import timeline as tl_mod
from haku_sidecar.store import CachedJson

HERE = os.path.dirname(__file__)
GOLDEN_DIR = os.path.join(HERE, "golden")
EXAMPLE = os.path.abspath(os.path.join(HERE, "..", "dashboard.json.example"))
SIDECAR_BASE = "http://192.0.2.20:1986"

TZ = ZoneInfo("America/Edmonton")
FROZEN = int(datetime(2026, 10, 1, 18, 30, tzinfo=TZ).timestamp())   # 2026-10-02T00:30Z


def _iso(secs_ago):
    return datetime.fromtimestamp(FROZEN - secs_ago, timezone.utc).isoformat()


def _st(eid, state, last_changed=None, **attrs):
    row = {"entity_id": eid, "state": state, "attributes": attrs}
    if last_changed is not None:
        row["last_changed"] = last_changed
    return {eid: row}


STATES = {
    **_st("weather.edmonton_forecast", "rainy", temperature=12.4, humidity=86, wind_speed=15.0),
    **_st("weather.my_ecobee", "cloudy", temperature=21.5),
    **_st("sensor.emporia_total_power", "2412", unit_of_measurement="W"),
    **_st("sensor.emporia_total_daily_energy_kwh", "18.23", unit_of_measurement="kWh"),
    **_st("sensor.electricity_daily_cost", "4.12", unit_of_measurement="CAD"),
    **_st("sensor.water_hourly_usage", "12.0", unit_of_measurement="L"),
    **_st("sensor.water_flow_lpm", "4.2", unit_of_measurement="L/min"),
    **_st("sensor.water_daily_usage", "210", unit_of_measurement="L"),
    **_st("sensor.water_monthly_usage", "6100", unit_of_measurement="L"),
    **_st("sensor.water_meter_total", "812345", unit_of_measurement="L"),
    **_st("binary_sensor.front_motion_occupancy", "on", _iso(90), device_class="occupancy"),
    **_st("binary_sensor.backyard_motion_occupancy", "off", _iso(3600), device_class="occupancy"),
    **_st("binary_sensor.front_doorcontact_contact", "off", _iso(600), device_class="door"),
    **_st("binary_sensor.back_doorcontact_contact", "off", _iso(7200), device_class="door"),
    **_st("binary_sensor.bathroom_door_contact", "on", _iso(120), device_class="door"),
    **_st("binary_sensor.my_ecobee_occupancy", "on", _iso(300), device_class="occupancy"),
    **_st("binary_sensor.shed_motion_occupancy", "off", _iso(9000), device_class="motion"),
    **_st("binary_sensor.water_in_tier_2", "off", _iso(86400), device_class="moisture"),
    **_st("person.jimi", "home", _iso(1800)),
    **_st("person.alex", "not_home", _iso(5400)),
    **_st("person.robin", "school", _iso(30000)),
    **_st("sensor.home_gas_usage", "0.65", unit_of_measurement="m³/h"),
    **_st("sensor.gas_meter_gas_meter_direct", "17639.9", unit_of_measurement="m³"),
    **_st("climate.my_ecobee", "heat", current_temperature=21.3, current_humidity=48,
          hvac_action="heating", preset_mode="home"),
}
# Forecast `datetime`s are UTC noon-ish, as HA's met/environment_canada entities send them.
FORECAST = [
    {"datetime": "2026-10-01T18:00:00+00:00", "temperature": 14.0, "templow": 3.0,
     "condition": "rainy", "precipitation_probability": 60},
    {"datetime": "2026-10-02T18:00:00+00:00", "temperature": 11.0, "templow": 1.0,
     "condition": "cloudy", "precipitation_probability": 20},
    {"datetime": "2026-10-03T18:00:00+00:00", "temperature": 16.0, "templow": 4.0,
     "condition": "sunny"},
]


def _row(name, state, secs_ago):
    return {"when": _iso(secs_ago), "state": state, "name": name}


LOGBOOK = {
    "binary_sensor.front_doorcontact_contact": [
        _row("Front Door", "on", 700), _row("Front Door", "off", 600)],
    "binary_sensor.back_doorcontact_contact": [
        _row("Back Door", "on", 7300), _row("Back Door", "off", 7200)],
    "binary_sensor.bathroom_door_contact": [_row("Bathroom Door", "on", 120)],
    "binary_sensor.front_motion_occupancy": [
        _row("Front Motion", "on", 90), _row("Front Motion", "off", 400),
        _row("Front Motion", "on", 500)],
    "binary_sensor.backyard_motion_occupancy": [
        _row("Backyard Motion", "on", 3700), _row("Backyard Motion", "off", 3600)],
    "binary_sensor.shed_motion_occupancy": [_row("Shed Motion", "on", 9100)],
    "person.jimi": [_row("Jimi", "home", 1800)],
    "person.alex": [_row("Alex", "not_home", 5400)],
    # 21:40 the previous local evening: a YESTERDAY section header.
    "person.robin": [_row("Robin", "school", 30000), _row("Robin", "home", 75600)],
}
CALENDARS = [{"entity_id": "calendar.family", "name": "Family"}]
EVENTS = {"calendar.family": [
    {"start": {"date": "2026-10-01"}, "end": {"date": "2026-10-02"}, "summary": "Recycling day"},
    {"start": {"dateTime": "2026-10-01T19:00:00-06:00"},
     "end": {"dateTime": "2026-10-01T20:00:00-06:00"}, "summary": "Practice"},
    {"start": {"dateTime": "2026-10-02T08:15:00-06:00"}, "summary": "Appointment"},
    {"start": {"dateTime": "2026-10-04T15:30:00-06:00"}, "summary": None},
]}


class _FrozenDatetime(datetime):
    """`datetime` with `now()` pinned to FROZEN (calendar and timeline call it)."""

    @classmethod
    def now(cls, tz=None):
        return datetime.fromtimestamp(FROZEN, tz)


@pytest.fixture()
def roku_client(client, monkeypatch):
    """The shared `client` over dashboard.json.example, a rich FakeHA and a frozen clock."""
    from haku_sidecar import app as app_module
    monkeypatch.setattr(cfg_module, "_cache", CachedJson(EXAMPLE, cfg_module.DEFAULT_CONFIG))
    monkeypatch.setattr(app_module, "ha", FakeHA(STATES, FORECAST, calendars=CALENDARS,
                                                 events=EVENTS, logbook=LOGBOOK))
    monkeypatch.setattr(app_module, "SIDECAR_BASE", SIDECAR_BASE)
    frozen_time = types.SimpleNamespace(time=lambda: float(FROZEN))
    monkeypatch.setattr(store, "time", frozen_time)
    monkeypatch.setattr(cam_mod, "time", frozen_time)
    monkeypatch.setattr(cal_mod, "datetime", _FrozenDatetime)
    monkeypatch.setattr(tl_mod, "datetime", _FrozenDatetime)
    return client


def _flask_bytes(obj):
    """What Flask's default JSON provider sends for `obj` outside debug mode."""
    return (json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _check(name, body):
    path = os.path.join(GOLDEN_DIR, name)
    if os.environ.get("HAKU_UPDATE_GOLDEN"):
        os.makedirs(GOLDEN_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(json.loads(body), f, indent=2, sort_keys=True, ensure_ascii=False)
            f.write("\n")
    with open(path, encoding="utf-8") as f:
        golden = json.load(f)
    assert json.loads(body) == golden
    assert body == _flask_bytes(golden)


def test_roku_config_matches_golden(roku_client):
    r = roku_client.get("/api/config")
    assert r.status_code == 200
    _check("roku_config.json", r.get_data())


def test_roku_state_matches_golden(roku_client):
    r = roku_client.get("/api/state")
    assert r.status_code == 200
    _check("roku_state.json", r.get_data())


def test_golden_fixture_is_rich():
    """Every value module in the golden has a real hero, so the stale fix can't touch it."""
    with open(os.path.join(GOLDEN_DIR, "roku_state.json"), encoding="utf-8") as f:
        state = json.load(f)
    for key in ("weather", "energy", "water", "gas", "climate"):
        assert state[key]["stale"] is False, key
        assert not state[key]["tile"]["hero"].startswith("--"), key
    assert state["timeline"]["count"] > 0 and state["calendar"]["count"] > 0
    assert "cams" in state["cameras"]
    assert state["ts"] == FROZEN
