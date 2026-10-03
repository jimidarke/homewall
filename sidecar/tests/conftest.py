"""Shared fixtures for the sidecar tests — loaded by pytest before any test module.

Puts `sidecar/` on sys.path so `haku_sidecar` imports without being installed,
and holds what more than one test module needs: the FakeHA stand-in for the HA
client, the SECRET_TOKEN that proves the HA token is never serialized, and the
hermetic Flask `client` fixture. Test modules import the plain names with
`from conftest import FakeHA, SECRET_TOKEN`.
"""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from haku_sidecar import config as cfg_module         # noqa: E402
from haku_sidecar.store import CachedJson             # noqa: E402

import pytest                                         # noqa: E402


SECRET_TOKEN = "super-secret-llt-value-do-not-leak"


class FakeHA:
    """Canned stand-in for ha.HAClient.

    `statistics` maps a statistic id, or a (statistic id, period) pair (which wins), to
    its rows; `history` maps an entity id to its rows. Either set to FakeHA.FAIL makes
    that call fail (None, as HAClient returns with nothing cached). Every statistics and
    history call is recorded in `calls` as (method, kwargs).

    `forecast` is a list (served for every type, as before), or {"daily": [...], "hourly":
    [...]} serving each type its own list; a type that is missing, empty or FakeHA.FAIL
    answers [] (what HAClient returns for an empty or failed fetch). Each get_forecast is
    recorded in `forecast_calls` as (entity id, type).
    """
    FAIL = object()

    def __init__(self, states=None, forecast=None, calendars=None, events=None, logbook=None,
                 statistics=None, history=None):
        self._states = states or {}
        self._forecast = forecast if forecast is not None else []
        self._calendars = calendars or []
        self._events = events or {}      # entity_id -> [event, ...]
        self._logbook = logbook or {}    # entity_id -> [row, ...]
        self._statistics = {} if statistics is None else statistics
        self._history = {} if history is None else history
        self.calls = []
        self.forecast_calls = []

    def get_state(self, eid):
        return self._states.get(eid)

    def attr(self, eid, key, default=None):
        st = self._states.get(eid)
        if not st:
            return default
        return st.get("attributes", {}).get(key, default)

    def get_forecast(self, eid, ftype="daily", ttl=600):
        self.forecast_calls.append((eid, ftype))
        if not isinstance(self._forecast, dict):
            return self._forecast
        rows = self._forecast.get(ftype)
        return [] if rows is FakeHA.FAIL or not rows else rows

    def get_calendars(self, ttl=600):
        return self._calendars

    def get_calendar_events(self, eid, lookahead_days=14, ttl=300):
        return self._events.get(eid, [])

    def get_logbook(self, eid, lookback_hours=12, ttl=30):
        return self._logbook.get(eid, [])

    def get_statistics(self, statistic_ids, start, end, period, types, units=None, ttl=600):
        self.calls.append(("get_statistics", {
            "statistic_ids": list(statistic_ids), "start": start, "end": end,
            "period": period, "types": list(types), "units": units}))
        if self._statistics is FakeHA.FAIL:
            return None
        out = {}
        for sid in statistic_ids:
            rows = self._statistics.get((sid, period), self._statistics.get(sid))
            if rows:
                out[sid] = rows
        return out

    def get_history(self, entity_ids, start, end=None, ttl=600):
        self.calls.append(("get_history", {"entity_ids": list(entity_ids), "start": start, "end": end}))
        if self._history is FakeHA.FAIL:
            return None
        return {eid: self._history[eid] for eid in entity_ids if self._history.get(eid)}

    def status(self):
        return {"connected": True, "last_ok_ts": 1, "last_error": None, "entity_count": len(self._states)}


@pytest.fixture()
def client(monkeypatch):
    from haku_sidecar import app as app_module
    # Hermetic config: force DEFAULT_CONFIG (which carries the `background` block)
    # regardless of any /etc/haku/dashboard.json on the host.
    monkeypatch.setattr(
        cfg_module, "_cache",
        CachedJson("/nonexistent/haku/dashboard.json", cfg_module.DEFAULT_CONFIG))
    # Give the shared HA client a token so we can prove it's never serialized.
    monkeypatch.setattr(app_module.ha, "_token", SECRET_TOKEN)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


# --- the tablet detail contract (tablet v3 contract §1) -------------------------
_BLOCK_CAPS = {"stats": ("items", 6), "days": ("items", 8), "forecast": ("days", 5),
               "rows": ("items", 30), "hourly": ("items", 12)}
_STYLES = {"compact"}
_TONES = {"water", "heat", "cool", "washer", "dryer", "sage", "ink", "muted", "amber", "coral"}


def assert_detail_contract(body):
    """Check a /api/detail body against the contract's shapes, caps and no-null rule."""
    import json
    assert "null" not in json.dumps(body), "a key carries null"
    assert body["v"] == 1 and isinstance(body["id"], str) and isinstance(body["title"], str)
    assert isinstance(body["ts"], int) and isinstance(body["blocks"], list)
    if "note" in body:
        assert isinstance(body["note"], str) and body["note"]
    for b in body["blocks"]:
        kind = b["type"]
        assert b.get("col", 0) in (0, 1) and not isinstance(b.get("col"), bool), b
        if kind in _BLOCK_CAPS:
            key, cap = _BLOCK_CAPS[kind]
            assert 0 < len(b[key]) <= cap, (kind, len(b[key]))
            for item in b[key]:
                assert all(isinstance(v, str) for v in item.values()), item
                assert item.get("tone", "ink") in _TONES
        if kind in ("stats", "days", "rows"):
            assert all(isinstance(i["label"], str) and isinstance(i["value"], str) for i in b["items"])
        elif kind == "forecast":
            assert all(d["label"] and d["glyph"] for d in b["days"])
            assert b.get("style", "compact") in _STYLES
        elif kind == "hourly":
            assert all(i["label"] and i["temp"] for i in b["items"])
        elif kind == "now":
            assert b["temp"] and all(isinstance(v, str) for k, v in b.items() if k not in ("type", "col"))
        elif kind == "chart":
            _assert_chart(b)
        else:
            raise AssertionError(f"unknown block type {kind}")


def _assert_chart(b):
    assert b["step"] > 0 and b["count"] > 0 and isinstance(b["start"], int)
    assert 1 <= len(b["series"]) <= 4
    points = 0
    for s in b["series"]:
        assert isinstance(s["label"], str) and s["tone"] in _TONES
        assert s.get("fill", False) in (True, False)
        end = 0
        for r in s["runs"]:
            assert r["i"] >= end, "runs overlap or are out of order"
            assert r["v"] and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in r["v"])
            end = r["i"] + len(r["v"])
            assert end <= b["count"]
            points += len(r["v"])
    assert points <= 2000
    ticks = b.get("x", {}).get("ticks", [])
    assert [t["i"] for t in ticks] == sorted({t["i"] for t in ticks}), "ticks out of order or repeated"
    for t in ticks:
        assert 0 <= t["i"] < b["count"] and isinstance(t["label"], str)
        assert t.get("strong", True) is True
    if points:
        assert "empty" not in b
        y = b["y"]
        assert y["max"] > y["min"]
        assert all(y["min"] <= t["v"] <= y["max"] and isinstance(t["label"], str) for t in y["ticks"])
    else:
        assert isinstance(b["empty"], str) and "y" not in b
