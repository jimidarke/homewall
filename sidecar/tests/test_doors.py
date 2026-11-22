"""Doors module (tablet layout): door contacts with a restart-proof "since".

HA re-stamps `last_changed` when it restarts, so "since" comes from the newest logbook
row that is a real open/close (not a Zigbee2MQTT reconnect out of `unavailable`). A
change the 30 s logbook cache hasn't seen yet shows up as a state mismatch and uses
`last_changed`; with no usable row the door falls back to `last_changed`, inexact.
"""
import json
from datetime import datetime, timedelta, timezone

from haku_sidecar import modules
from haku_sidecar.modules import doors

from conftest import FakeHA

FRONT = "binary_sensor.front_doorcontact_contact"
BACK = "binary_sensor.back_doorcontact_contact"


def _iso(secs_ago):
    return (datetime.now(timezone.utc) - timedelta(seconds=secs_ago)).isoformat()


def _epoch(iso):
    return int(datetime.fromisoformat(iso).timestamp())


def _state(eid, state, changed):
    """An HA state row; `changed` is the ISO `last_changed`."""
    return {eid: {"entity_id": eid, "state": state, "last_changed": changed,
                  "attributes": {"device_class": "door"}}}


def _row(eid, state, when):
    return {"when": when, "state": state, "entity_id": eid, "name": eid}


def _desc(**extra):
    return {"id": "doors", "kind": "doors", "feedKey": "doors", "tile": {"type": "value"},
            "openAlertSec": 300,
            "entities": {"doors": [
                {"id": "front", "entity": FRONT, "label": "Front"},
                {"id": "back", "entity": BACK, "label": "Back"}]},
            **extra}


def _ha(front=("off", 3 * 3600), back=("off", 5 * 3600)):
    """FakeHA from each door's (state, secs since its last real change).

    Each door gets a matching `last_changed` and logbook row, so "since" is exact.
    """
    states, logbook = {}, {}
    for eid, (st, ago) in ((FRONT, front), (BACK, back)):
        when = _iso(ago)
        states.update(_state(eid, st, when))
        logbook[eid] = [_row(eid, st, when)]
    return FakeHA(states, logbook=logbook)


def _doors(front=("off", 3 * 3600), back=("off", 5 * 3600), **extra):
    return doors.values(_ha(front, back), _desc(**extra))


def _by_id(v):
    return {d["id"]: d for d in v["doors"]}


class RecordingHA(FakeHA):
    """FakeHA that remembers the lookback hours each logbook fetch asked for."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.lookbacks = []

    def get_logbook(self, eid, lookback_hours=12, ttl=30):
        self.lookbacks.append((eid, lookback_hours))
        return super().get_logbook(eid, lookback_hours, ttl)


# --- states, severity, glyphs ----------------------------------------------
def test_all_closed():
    v = _doors()
    d = _by_id(v)
    assert [x["id"] for x in v["doors"]] == ["front", "back"]          # config order
    assert d["front"]["label"] == "Front"
    for door in d.values():
        assert door["state"] == "closed"
        assert door["glyph"] == "door-closed"
        assert door["severity"] == "normal"
        assert door["since_exact"] is True
    assert (d["front"]["age"], d["back"]["age"]) == ("3h", "5h")
    assert v["open_count"] == 0
    assert v["stale"] is False
    assert v["tile"] == {
        "hero": "All closed", "sub": "", "detail": "Front 3h · Back 5h",
        "severity": "normal", "icon": "closed", "glyph": "door-closed", "active": False,
    }


def test_one_open_under_alert_threshold_normal_active():
    v = _doors(back=("on", 120))
    back = _by_id(v)["back"]
    assert (back["state"], back["glyph"], back["age"]) == ("open", "door-open", "2m")
    assert back["severity"] == "normal"                 # a brief opening isn't an alert
    assert v["open_count"] == 1
    tile = v["tile"]
    assert (tile["hero"], tile["sub"], tile["detail"]) == ("Back open", "2m", "Front closed · 3h")
    assert tile["severity"] == "normal"
    assert (tile["glyph"], tile["active"], tile["icon"]) == ("door-open", True, "open")


def test_one_open_over_threshold_high():
    v = _doors(back=("on", 600))
    assert _by_id(v)["back"]["severity"] == "high"
    assert _by_id(v)["back"]["age"] == "10m"
    assert v["tile"]["severity"] == "high"
    assert v["tile"]["hero"] == "Back open"
    # the threshold is configurable
    assert _by_id(_doors(back=("on", 600), openAlertSec=900))["back"]["severity"] == "normal"
    # default threshold (300 s) when the descriptor omits it
    desc = _desc()
    del desc["openAlertSec"]
    assert _by_id(doors.values(_ha(back=("on", 600)), desc))["back"]["severity"] == "high"
    assert _by_id(doors.values(_ha(back=("on", 240)), desc))["back"]["severity"] == "normal"


def test_unavailable_is_unknown_low_glyph_door():
    for raw in ("unavailable", "unknown"):
        v = _doors(back=(raw, 600))
        back = _by_id(v)["back"]
        assert (back["state"], back["severity"], back["glyph"]) == ("unknown", "low", "door")
        assert v["open_count"] == 0
        assert v["stale"] is False                      # the front door still reports
        assert v["tile"]["hero"] == "Back unknown"
        assert v["tile"]["severity"] == "normal"        # unknown never escalates the tile
        assert v["tile"]["active"] is False

    # An entity HA doesn't have at all: unknown, and no `null` once composed.
    states = _state(FRONT, "off", _iso(3600))
    snap = modules.compose_state(FakeHA(states), {"modules": [_desc()]})
    back = {d["id"]: d for d in snap["doors"]["doors"]}["back"]
    assert (back["state"], back["glyph"]) == ("unknown", "door")
    assert "since" not in back and "age" not in back     # None was pruned
    assert "null" not in json.dumps(snap)


# --- "since" ----------------------------------------------------------------
def test_logbook_empty_uses_last_changed_inexact():
    changed = _iso(120)                                 # e.g. HA restarted 2 min ago
    states = {**_state(FRONT, "off", changed), **_state(BACK, "on", changed)}
    ha = RecordingHA(states)
    v = doors.values(ha, _desc())
    front, back = _by_id(v)["front"], _by_id(v)["back"]
    assert front["since"] == _epoch(changed)
    assert front["since_exact"] is False
    assert front["age"] == "> 12h"
    assert back["age"] == "> 12h"
    # lookbackHours defaults to 12, so the logbook cache entry is the timeline's
    assert ha.lookbacks == [(FRONT, 12), (BACK, 12)]

    ha = RecordingHA(states)
    v = doors.values(ha, _desc(lookbackHours=24))
    assert _by_id(v)["front"]["age"] == "> 24h"
    assert ha.lookbacks == [(FRONT, 24), (BACK, 24)]


def test_ha_restart_logbook_wins():
    row_when = _iso(2 * 3600)
    states = {**_state(FRONT, "off", _iso(60)), **_state(BACK, "off", _iso(60))}  # restart re-stamp
    logbook = {FRONT: [_row(FRONT, "off", row_when)], BACK: [_row(BACK, "off", row_when)]}
    front = _by_id(doors.values(FakeHA(states, logbook=logbook), _desc()))["front"]
    assert front["since"] == _epoch(row_when)
    assert front["since_exact"] is True
    assert front["age"] == "2h"


def test_fresh_change_uses_last_changed():
    changed = _iso(30)
    states = {**_state(FRONT, "off", _iso(3600)), **_state(BACK, "on", changed)}
    logbook = {FRONT: [_row(FRONT, "off", _iso(3600))],
               BACK: [_row(BACK, "off", _iso(2 * 3600))]}  # cache hasn't seen the opening
    back = _by_id(doors.values(FakeHA(states, logbook=logbook), _desc()))["back"]
    assert back["state"] == "open"
    assert back["since"] == _epoch(changed)
    assert back["since_exact"] is True
    assert back["age"] == "now"
    assert back["severity"] == "normal"


def test_skips_transitions_from_unavailable():
    real = _iso(3 * 3600)
    reconnect = _iso(55 * 60)
    rows = [  # newest first, deliberately: the module sorts by `when` itself
        _row(FRONT, "off", reconnect),           # Zigbee2MQTT reconnect: not a real change
        _row(FRONT, "unavailable", _iso(3600)),
        _row(FRONT, "off", real),                # the real close
    ]
    states = {**_state(FRONT, "off", reconnect), **_state(BACK, "off", _iso(3600))}
    logbook = {FRONT: rows, BACK: [_row(BACK, "off", _iso(3600))]}
    front = _by_id(doors.values(FakeHA(states, logbook=logbook), _desc()))["front"]
    assert front["since"] == _epoch(real)
    assert (front["since_exact"], front["age"]) == (True, "3h")

    # Only a reconnect (out of `unknown`) in the window: no usable row -> inexact fallback.
    rows = [_row(FRONT, "unknown", _iso(2 * 3600)), _row(FRONT, "off", reconnect)]
    front = _by_id(doors.values(FakeHA(states, logbook={FRONT: rows}), _desc()))["front"]
    assert front["since"] == _epoch(reconnect)
    assert (front["since_exact"], front["age"]) == (False, "> 12h")


def test_restart_row_same_state_is_skipped():
    # HA's logbook drops the restart's unknown row (it has no old state), so the
    # restart shows up only as a repeat of the state before it.
    real, restart = _iso(8 * 3600), _iso(3 * 3600)
    states = {**_state(FRONT, "off", restart), **_state(BACK, "off", restart)}
    logbook = {FRONT: [_row(FRONT, "off", real), _row(FRONT, "off", restart)]}
    front = _by_id(doors.values(FakeHA(states, logbook=logbook), _desc()))["front"]
    assert front["since"] == _epoch(real)
    assert (front["since_exact"], front["age"]) == (True, "8h")


def test_same_second_rows_keep_logbook_order():
    # Ties within one second keep HA's chronological order (`when` is floored to seconds).
    t = (datetime.now(timezone.utc) - timedelta(hours=3)).replace(microsecond=0)
    early = _iso(8 * 3600)
    unknown_at = (t + timedelta(milliseconds=200)).isoformat()
    off_at = (t + timedelta(milliseconds=700)).isoformat()
    states = {**_state(FRONT, "off", off_at), **_state(BACK, "off", off_at)}

    rows = [_row(FRONT, "off", early), _row(FRONT, "unknown", unknown_at), _row(FRONT, "off", off_at)]
    front = _by_id(doors.values(FakeHA(states, logbook={FRONT: rows}), _desc()))["front"]
    assert (front["since"], front["since_exact"]) == (_epoch(early), True)

    # Just the reconnect pair: the `off` is out of `unknown`, so there is no usable row.
    rows = [_row(FRONT, "unknown", unknown_at), _row(FRONT, "off", off_at)]
    front = _by_id(doors.values(FakeHA(states, logbook={FRONT: rows}), _desc()))["front"]
    assert (front["since_exact"], front["age"]) == (False, "> 12h")


def test_inexact_open_door_is_high():
    # No usable row and an old last_changed: open since before the lookback window.
    states = {**_state(FRONT, "off", _iso(120)), **_state(BACK, "on", _iso(120))}
    v = doors.values(FakeHA(states), _desc(openAlertSec=900))
    back = _by_id(v)["back"]
    assert (back["since_exact"], back["age"]) == (False, "> 12h")
    assert back["severity"] == "high"
    assert v["tile"]["severity"] == "high"
    assert _by_id(v)["front"]["severity"] == "normal"   # a closed door never escalates


def test_inexact_open_recent_last_changed_is_fresh():
    # No usable row but last_changed within 60 s: the change is newer than the 30 s
    # logbook cache, so "since" is exact and severity is measured normally.
    changed = _iso(20)
    states = {**_state(FRONT, "off", changed), **_state(BACK, "on", changed)}
    v = doors.values(FakeHA(states), _desc())
    back, front = _by_id(v)["back"], _by_id(v)["front"]
    assert (back["since"], back["since_exact"], back["age"]) == (_epoch(changed), True, "now")
    assert back["severity"] == "normal"
    assert (front["since_exact"], front["age"]) == (True, "now")   # the rule isn't door-state specific


# --- tile -------------------------------------------------------------------
def test_hero_texts():
    assert _doors()["tile"]["hero"] == "All closed"
    assert _doors(back=("on", 120))["tile"]["hero"] == "Back open"
    assert _doors(front=("on", 60))["tile"]["hero"] == "Front open"

    both = _doors(front=("on", 60), back=("on", 120))
    assert both["open_count"] == 2
    assert both["tile"]["hero"] == "2 open"
    assert both["tile"]["sub"] == "Front 1m · Back 2m"
    assert both["tile"]["detail"] == ""

    gone = _doors(front=("unavailable", 60), back=("unavailable", 60))
    assert gone["stale"] is True
    assert gone["open_count"] == 0
    assert gone["tile"]["hero"] == "No data"
    assert (gone["tile"]["glyph"], gone["tile"]["active"]) == ("door-closed", False)

    # Nothing configured is stale too, not "All closed".
    empty = doors.values(FakeHA(), {"id": "doors", "kind": "doors", "entities": {}})
    assert (empty["doors"], empty["stale"], empty["tile"]["hero"]) == ([], True, "No data")


# --- door camera takeover (tablet) ------------------------------------------------
CAMERA = {"door": "front", "cam": "front_steps", "sec": 60, "label": "Front Steps"}


def _cam_doors(front=("on", 10), opened_ago=10, **extra):
    ha = _ha(front=front)
    if opened_ago is not None:
        ha._rising = {FRONT: doors.now_s() - opened_ago}
    return doors.values(ha, _desc(**extra)), ha


def test_takeover_while_inside_the_window(monkeypatch):
    monkeypatch.delenv("HAKU_HLS_BASE", raising=False)
    monkeypatch.setenv("HAKU_SIDECAR_BASE", "http://192.0.2.20:1986")  # HLS on the same host
    v, ha = _cam_doors(camera=CAMERA)
    t = ha.last_on(FRONT)
    assert v["takeover"] == {"cam": "front_steps", "label": "Front Steps", "until": t + 60,
                             "hls": "http://192.0.2.20:1985/hls/front_steps.m3u8"}


def test_takeover_holds_after_the_door_closes_again():
    v, _ = _cam_doors(front=("off", 5), opened_ago=8, camera=CAMERA)
    assert "takeover" in v


def test_no_takeover_after_the_window():
    v, _ = _cam_doors(opened_ago=61, camera=CAMERA)
    assert "takeover" not in v


def test_no_takeover_without_an_opening_or_a_camera_key():
    assert "takeover" not in _cam_doors(opened_ago=None, camera=CAMERA)[0]
    assert "takeover" not in _cam_doors()[0]                       # no camera key
    assert "takeover" not in _cam_doors(camera={**CAMERA, "door": "garage"})[0]
    assert "takeover" not in _cam_doors(camera={"door": "front"})[0]  # no cam


def test_takeover_hls_base_from_env(monkeypatch):
    monkeypatch.setenv("HAKU_HLS_BASE", "http://cams.lan:9000/hls/")
    v, _ = _cam_doors(camera={"door": "front", "cam": "front_steps"})
    assert v["takeover"]["hls"] == "http://cams.lan:9000/hls/front_steps.m3u8"
    assert v["takeover"]["label"] == "Front"                        # the door's label
    assert v["takeover"]["until"] - doors.now_s() in (49, 50, 51)   # sec defaults to 60
