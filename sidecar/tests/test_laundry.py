"""Laundry module (tablet layout): mirrors HA's laundry package, never re-derives it.

Per machine `m`, HA owns `sensor.laundry_<m>_mode` / `_leds` and the cycle helpers
(`input_datetime.laundry_<m>_started` / `_finished`, `input_number.laundry_<m>_expected_minutes`).
The sidecar passes mode and leds through, adds minutes and a display `status`, and
picks the tile hero by priority: done > overtime > running > done_calm > idle.
"""
import json
import time
from datetime import datetime, timezone

import pytest

from haku_sidecar import modules
from haku_sidecar.modules import laundry

from conftest import FakeHA

# 2026-09-30 15:52 UTC = 9:52 AM in America/Edmonton (MDT)
FINISHED = int(datetime(2026, 9, 30, 15, 52, tzinfo=timezone.utc).timestamp())
POWER = "sensor.emporia_circuit_7_power"


def _machine(mid, mode, leds=0, started_min_ago=None, finished=FINISHED, expected="55.0",
             started_ts=None):
    """HA states for one machine. `started_ts` overrides the computed start (e.g. never set)."""
    if started_ts is None:
        started_ts = time.time() - started_min_ago * 60 if started_min_ago is not None else 0.0
    return {
        f"sensor.laundry_{mid}_mode": {"state": mode, "attributes": {}},
        f"sensor.laundry_{mid}_leds": {"state": str(leds), "attributes": {}},
        f"input_datetime.laundry_{mid}_started": {"state": "x", "attributes": {"timestamp": started_ts}},
        f"input_datetime.laundry_{mid}_finished": {"state": "x", "attributes": {"timestamp": float(finished)}},
        f"input_number.laundry_{mid}_expected_minutes": {"state": expected, "attributes": {}},
    }


def _desc(machines=None, tz="UTC"):
    return {"id": "laundry", "kind": "laundry", "feedKey": "laundry", "tile": {"type": "value"},
            "timezone": tz,
            "machines": machines or [
                {"id": "washer", "label": "Washer", "color": "#00AAFF", "entities": {"power": POWER}},
                {"id": "dryer", "label": "Dryer", "color": "#FF6900"}]}


def _run(washer, dryer=None, tz="UTC", extra=None):
    """`washer` / `dryer` are kwargs dicts for `_machine` (dryer defaults to idle)."""
    states = {**_machine("washer", **washer), **_machine("dryer", **(dryer or {"mode": "idle"})),
              **(extra or {})}
    return laundry.values(FakeHA(states), _desc(tz=tz))


def _m(v, mid):
    return next(m for m in v["machines"] if m["id"] == mid)


# --- per-machine -------------------------------------------------------------
@pytest.mark.parametrize("mode,started_min_ago,status", [
    ("idle", None, "idle"),
    ("running", 21, "34m left"),
    ("overtime", 70, "running 15m long"),
    ("done", None, "done"),
    ("done_calm", None, "done 3:52 PM"),
])
def test_each_mode_status_text(mode, started_min_ago, status):
    v = _run({"mode": mode, "started_min_ago": started_min_ago})
    w = _m(v, "washer")
    assert w["mode"] == mode
    assert w["status"] == status
    assert w["stale"] is False
    assert (w["label"], w["color"]) == ("Washer", "#00AAFF")
    assert _m(v, "dryer")["status"] == "idle"


def test_done_calm_finished_hm_uses_the_configured_timezone():
    v = _run({"mode": "done_calm"}, tz="America/Edmonton")
    w = _m(v, "washer")
    assert (w["finished"], w["finished_hm"], w["status"]) == (FINISHED, "9:52 AM", "done 9:52 AM")


def test_leds_passthrough():
    for leds in (0, 3, 4):
        assert _m(_run({"mode": "running", "leds": leds, "started_min_ago": 10}), "washer")["leds"] == leds
    # leds is mirrored in every mode, not just running
    assert _m(_run({"mode": "done", "leds": 2}), "washer")["leds"] == 2
    # an unavailable leds sensor reads as 0
    v = _run({"mode": "running", "started_min_ago": 10},
             extra={"sensor.laundry_washer_leds": {"state": "unavailable", "attributes": {}}})
    assert _m(v, "washer")["leds"] == 0
    # power is passed through when the descriptor maps it
    v = _run({"mode": "running", "started_min_ago": 10},
             extra={POWER: {"state": "186.4", "attributes": {"unit_of_measurement": "W"}}})
    assert _m(v, "washer")["power_w"] == 186
    assert _m(v, "dryer").get("power_w") is None   # no power entity mapped


def test_remaining_and_overtime_minutes():
    w = _m(_run({"mode": "running", "started_min_ago": 21}), "washer")
    assert (w["elapsed_min"], w["expected_min"], w["remaining_min"]) == (21, 55, 34)
    assert w.get("over_min") is None
    assert w["started"] == pytest.approx(time.time() - 21 * 60, abs=2)

    # past the expected time but HA hasn't flipped to overtime yet: clamped at 0
    w = _m(_run({"mode": "running", "started_min_ago": 60}), "washer")
    assert (w["remaining_min"], w["status"]) == (0, "0m left")

    w = _m(_run({"mode": "overtime", "started_min_ago": 70}), "washer")
    assert (w["elapsed_min"], w["over_min"]) == (70, 15)
    assert w.get("remaining_min") is None

    # finished/started are only reported where they mean something
    w = _m(_run({"mode": "done"}), "washer")
    assert w["finished"] == FINISHED and w.get("started") is None and w.get("remaining_min") is None
    w = _m(_run({"mode": "idle"}), "washer")
    for key in ("started", "elapsed_min", "remaining_min", "over_min", "finished", "finished_hm"):
        assert w.get(key) is None, key


def test_started_never_set():
    for ts in (0.0, 25200.0):                     # epoch-ish values HA gives an unset helper
        w = _m(_run({"mode": "running", "started_ts": ts}), "washer")
        assert w.get("started") is None
        assert w.get("elapsed_min") is None and w.get("remaining_min") is None
        assert w["status"] == "running"
    w = _m(_run({"mode": "overtime", "started_ts": 0.0}), "washer")
    assert w["status"] == "running long"
    assert _run({"mode": "running", "started_ts": 0.0})["tile"]["hero"] == "Washer running"
    # a never-set finish time drops finished_hm, and done_calm says just "done"
    w = _m(_run({"mode": "done_calm", "finished": 0}), "washer")
    assert w.get("finished_hm") is None and w["status"] == "done"


def test_mode_unavailable_stale_status_no_data():
    v = _run({"mode": "unavailable", "leds": 0})
    w = _m(v, "washer")
    assert (w["stale"], w["status"]) == (True, "no data")
    assert w["mode"] == "idle"                    # mode stays in the contract's enum
    assert v["stale"] is False                    # the dryer still reports
    assert (v["tile"]["hero"], v["tile"]["sub"]) == ("Dryer idle", "Washer no data")
    assert v["tile"]["active"] is False

    # an unrecognised mode is the same "no data" as unavailable
    assert _m(_run({"mode": "paused"}), "washer")["stale"] is True

    # nothing in HA at all: every machine stale, the module stale, and no `null` once composed
    snap = modules.compose_state(FakeHA(), {"modules": [_desc()]})
    lv = snap["laundry"]
    assert lv["stale"] is True
    assert [m["status"] for m in lv["machines"]] == ["no data", "no data"]
    assert lv["tile"]["hero"] == "No data"
    assert "null" not in json.dumps(snap)


# --- tile ------------------------------------------------------------------
def test_hero_priority_done_over_overtime_over_running():
    cases = [
        # (washer, dryer, hero, sub, severity)
        ({"mode": "running", "started_min_ago": 21}, {"mode": "done"},
         "Dryer done", "Washer 34m left", "high"),
        ({"mode": "overtime", "started_min_ago": 70}, {"mode": "done"},
         "Dryer done", "Washer running 15m long", "high"),
        ({"mode": "running", "started_min_ago": 21}, {"mode": "overtime", "started_min_ago": 50,
                                                       "expected": "45.0"},
         "Dryer running 5m long", "Washer 34m left", "normal"),
        # done_calm is the calm after-phase: an active cycle outranks it (Contract §1.2 example)
        ({"mode": "running", "started_min_ago": 21}, {"mode": "done_calm"},
         "Washer 34m left", "Dryer done 3:52 PM", "normal"),
        ({"mode": "idle"}, {"mode": "done_calm"}, "Dryer done 3:52 PM", "Washer idle", "normal"),
        ({"mode": "done"}, {"mode": "idle"}, "Washer done", "Dryer idle", "high"),
        # same rank: config order wins
        ({"mode": "running", "started_min_ago": 21}, {"mode": "running", "started_min_ago": 5,
                                                       "expected": "45.0"},
         "Washer 34m left", "Dryer 40m left", "normal"),
        ({"mode": "idle"}, {"mode": "idle"}, "Laundry idle", "", "normal"),
    ]
    for washer, dryer, hero, sub, severity in cases:
        tile = _run(washer, dryer)["tile"]
        assert (tile["hero"], tile["sub"], tile["severity"]) == (hero, sub, severity), (washer, dryer)
        assert tile["detail"] == ""


def test_tile_active_rules():
    expect = {"running": True, "overtime": True, "done": True, "done_calm": False, "idle": False,
              "unavailable": False}
    for mode, active in expect.items():
        tile = _run({"mode": mode, "started_min_ago": 10})["tile"]
        assert tile["active"] is active, mode
        assert tile["glyph"] == "washing-machine", mode
    # the Roku-style cache-bust token tracks mode and leds
    assert _run({"mode": "running", "leds": 3, "started_min_ago": 10})["tile"]["icon"] == "running:3|idle:0"


def test_glyph_defaults_by_id():
    machines = [
        {"id": "washer", "label": "Washer", "color": "#00AAFF"},
        {"id": "dryer", "label": "Dryer", "color": "#FF6900"},
        {"id": "garage", "label": "Garage"},
        {"id": "dryer2", "label": "Dryer 2", "glyph": "tumble-dryer"},
        {"id": "dryer", "label": "Dryer", "glyph": "washing-machine"},       # config wins
    ]
    v = laundry.values(FakeHA(), _desc(machines=machines))
    assert [m["glyph"] for m in v["machines"]] == [
        "washing-machine", "tumble-dryer", "washing-machine", "tumble-dryer", "washing-machine"]
    assert v["machines"][2].get("color") is None
