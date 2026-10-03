"""GET /api/detail/<id> (tablet v3 contract §1): routing, 404s, no nulls, Roku untouched.

Runs over dashboard.json.example (its tablet layout carries the full entity maps) and
the Roku golden's rich FakeHA plus canned statistics/history, with the golden's frozen
clock. The default (Roku) /api/config and /api/state must still match their goldens
after every detail call.
"""
import json
import types

import pytest
from conftest import SECRET_TOKEN, FakeHA, assert_detail_contract
from test_roku_golden import (  # noqa: F401  (fixture)
    FROZEN,
    STATES,
    _check,
    roku_client,
)

from haku_sidecar import config as cfg_module
from haku_sidecar import store
from haku_sidecar.modules import water
from haku_sidecar.store import CachedJson

DETAIL_IDS = ["water", "energy", "gas", "climate", "weather", "laundry", "doors"]
END = FROZEN - FROZEN % 3600
START = END - 168 * 3600


def _hourly(key, value):
    return [{"start": (START + i * 3600) * 1000.0, key: value(i)} for i in range(168) if i % 50 != 7]


STATISTICS = {
    ("sensor.water_meter_total", "hour"): _hourly("change", lambda i: (i % 6) * 7.5),
    ("sensor.emporia_total_daily_energy_kwh", "hour"): _hourly("change", lambda i: 0.3 + (i % 4) * 0.2),
    ("sensor.gas_meter_gas_meter_direct", "hour"): _hourly("change", lambda i: (i % 3) * 0.1),
    "sensor.my_ecobee_temperature": _hourly("mean", lambda i: 21.0 + (i % 5) * 0.1),
    "sensor.edmonton_weather_temperature": _hourly("mean", lambda i: -5.0 + (i % 24) * 0.5),
}
EXTRA_STATES = {
    "sensor.water_cost_today": {"state": "0.88", "attributes": {}},
    "sensor.edmonton_weather_temperature": {"state": "6.5", "attributes": {}},
    "sensor.laundry_washer_mode": {"state": "running", "attributes": {}},
    "sensor.laundry_dryer_mode": {"state": "idle", "attributes": {}},
    "input_datetime.laundry_washer_started": {"state": "x", "attributes": {"timestamp": FROZEN - 900.0}},
}


@pytest.fixture()
def tablet(roku_client, monkeypatch):  # noqa: F811  (the imported fixture)
    """`roku_client` (example config, rich FakeHA, frozen clock) plus statistics/history."""
    from haku_sidecar import app as app_module
    base = app_module.ha
    ha = FakeHA({**STATES, **EXTRA_STATES}, base._forecast, calendars=base._calendars,
                events=base._events, logbook=base._logbook, statistics=STATISTICS,
                history={"binary_sensor.front_doorcontact_contact": [
                    {"state": "off", "last_changed": "2026-10-01T06:00:00+00:00"},
                    {"state": "on", "last_changed": "2026-10-01T23:10:00+00:00"},
                    {"state": "off", "last_changed": "2026-10-01T23:12:00+00:00"}],
                    "sensor.laundry_washer_mode": [
                    {"state": "idle", "last_changed": "2026-09-25T06:00:00+00:00"},
                    {"state": "running", "last_changed": "2026-10-02T00:15:00+00:00"}]})
    monkeypatch.setattr(app_module, "ha", ha)
    return roku_client


@pytest.mark.parametrize("mid", DETAIL_IDS)
def test_every_tablet_detail_is_200_and_on_contract(tablet, mid):
    r = tablet.get(f"/api/detail/{mid}?layout=tablet")
    assert r.status_code == 200, r.get_json()
    text = r.get_data(as_text=True)
    assert "null" not in text and SECRET_TOKEN not in text
    body = r.get_json()
    assert_detail_contract(body)
    assert (body["id"], body["ts"]) == (mid, FROZEN)
    assert body["blocks"], mid


def test_tablet_details_carry_charts_and_strips(tablet):
    kinds = {mid: [b["type"] for b in tablet.get(f"/api/detail/{mid}?layout=tablet").get_json()["blocks"]]
             for mid in DETAIL_IDS}
    assert kinds == {
        "water": ["stats", "chart", "days"], "energy": ["stats", "chart", "days"],
        "gas": ["stats", "chart", "days"], "climate": ["stats", "chart"],
        "weather": ["now", "rows", "forecast", "hourly", "chart"], "laundry": ["rows", "rows", "rows"], "doors": ["rows", "rows"],
    }
    climate = tablet.get("/api/detail/climate?layout=tablet").get_json()
    assert [s["label"] for s in climate["blocks"][1]["series"]] == ["Indoor", "Outdoor"]
    assert climate["title"] == "Thermostat"


@pytest.mark.parametrize("path,error", [
    ("/api/detail/nope?layout=tablet", "unknown module"),
    ("/api/detail/cameras?layout=tablet", "unknown module"),       # not in the tablet layout
    ("/api/detail/calendar?layout=tablet", "no detail"),
    ("/api/detail/timeline?layout=tablet", "no detail"),
    ("/api/detail/cameras", "no detail"),
    ("/api/detail/water?layout=kiosk", "unknown layout"),
])
def test_404s(tablet, path, error):
    r = tablet.get(path)
    assert r.status_code == 404
    assert r.get_json()["error"] == error
    assert "null" not in r.get_data(as_text=True)


def test_unknown_ref_is_404(client, monkeypatch):
    config = {**cfg_module.DEFAULT_CONFIG, "layouts": {"tablet": {"modules": [{"ref": "ghost"}]}}}
    monkeypatch.setattr(cfg_module, "_cache", CachedJson("/nonexistent", config))
    r = client.get("/api/detail/ghost?layout=tablet")
    assert r.status_code == 404 and r.get_json() == {"error": "unknown ref", "ref": "ghost"}


def test_without_layout_serves_the_default_module(tablet):
    """Like /api/module: no ?layout= reads the top-level (Roku) descriptor, which has no
    statistics keys, so only the live stats block comes back."""
    body = tablet.get("/api/detail/water").get_json()
    assert_detail_contract(body)
    assert [b["type"] for b in body["blocks"]] == ["stats"]


def test_history_outage_is_never_a_500(tablet, monkeypatch):
    from haku_sidecar import app as app_module
    monkeypatch.setattr(app_module, "ha", FakeHA(STATES, statistics=FakeHA.FAIL, history=FakeHA.FAIL))
    for mid in DETAIL_IDS:
        r = tablet.get(f"/api/detail/{mid}?layout=tablet")
        assert r.status_code == 200, mid
        body = r.get_json()
        assert_detail_contract(body)
        charts = [b for b in body["blocks"] if b["type"] == "chart"]
        assert all(c["empty"] == "History unavailable" for c in charts)
        if mid in ("laundry", "doors"):
            assert body["note"] == "History unavailable"


def test_empty_ha_is_never_a_500(tablet, monkeypatch):
    from haku_sidecar import app as app_module
    monkeypatch.setattr(app_module, "ha", FakeHA())
    for mid in DETAIL_IDS:
        r = tablet.get(f"/api/detail/{mid}?layout=tablet")
        assert r.status_code == 200, mid
        assert_detail_contract(r.get_json())


def test_a_crashing_detail_answers_with_a_note(tablet, monkeypatch):
    monkeypatch.setattr(water, "detail", lambda ha, d, now: 1 / 0)
    r = tablet.get("/api/detail/water?layout=tablet")
    assert r.status_code == 200
    assert r.get_json() == {"v": 1, "id": "water", "title": "Water", "ts": FROZEN,
                            "note": "Detail unavailable", "blocks": []}


def test_roku_routes_untouched_by_detail_calls(tablet):
    for mid in DETAIL_IDS:
        tablet.get(f"/api/detail/{mid}?layout=tablet")
        tablet.get(f"/api/detail/{mid}")
    _check("roku_config.json", tablet.get("/api/config").get_data())
    _check("roku_state.json", tablet.get("/api/state").get_data())
    assert "/api/detail" not in json.dumps(tablet.get("/api/config").get_json())


def test_detail_ts_is_build_time(tablet, monkeypatch):
    monkeypatch.setattr(store, "time", types.SimpleNamespace(time=lambda: float(FROZEN + 61)))
    assert tablet.get("/api/detail/water?layout=tablet").get_json()["ts"] == FROZEN + 61
