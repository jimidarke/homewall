"""HAClient's on-demand reads: history, long-term statistics and the forecast cache.

No HA and no network: `_request` is patched for REST, and a fake `websocket` module
(standing in for websocket-client) scripts the websocket exchange. These cover URL
building and encoding, response parsing, cache keys, keep-last-good and that the token
never reaches an error string.
"""
import json
import os
import subprocess
import sys
import types
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from conftest import SECRET_TOKEN

from haku_sidecar import ha as ha_mod
from haku_sidecar.ha import HAClient

T0 = int(datetime(2026, 9, 24, 6, 0, tzinfo=timezone.utc).timestamp())
T1 = int(datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc).timestamp())


def _client(url="http://ha.example:8123"):
    return HAClient(url, SECRET_TOKEN)


class _Rest:
    """Patches `_request`: records (method, endpoint, body) and answers from a queue."""

    def __init__(self, monkeypatch, client, *answers):
        self.calls = []
        self.answers = list(answers)
        monkeypatch.setattr(client, "_request", self)

    def __call__(self, method, endpoint, body=None):
        self.calls.append((method, endpoint, body))
        return self.answers.pop(0) if self.answers else None


# --- history -------------------------------------------------------------------
HISTORY = [
    [{"entity_id": "sensor.laundry_washer_mode", "state": "idle",
      "last_changed": "2026-09-24T06:00:00+00:00", "last_updated": "2026-09-24T06:00:00+00:00"},
     {"state": "running", "last_changed": "2026-09-25T15:00:00+00:00"},
     {"state": "done", "last_changed": "2026-09-25T16:00:00+00:00"}],
    [{"entity_id": "sensor.laundry_dryer_mode", "state": "idle",
      "last_changed": "2026-09-24T06:00:00+00:00"}],
]


def test_history_url_encodes_the_window_and_filter(monkeypatch):
    c = _client()
    rest = _Rest(monkeypatch, c, HISTORY)
    c.get_history(["sensor.laundry_washer_mode", "sensor.laundry_dryer_mode"], T0, T1)
    method, endpoint, body = rest.calls[0]
    assert method == "GET" and body is None
    path, query = endpoint.split("?", 1)
    assert path == "/api/history/period/2026-09-24T06%3A00%3A00%2B00%3A00"
    assert unquote(path.rsplit("/", 1)[1]) == "2026-09-24T06:00:00+00:00"
    q = parse_qs(query, keep_blank_values=True)
    assert q["filter_entity_id"] == ["sensor.laundry_washer_mode,sensor.laundry_dryer_mode"]
    assert q["end_time"] == ["2026-10-01T06:00:00+00:00"]
    assert "minimal_response" in q and "no_attributes" in q
    assert "+" not in query.split("end_time=", 1)[1].split("&", 1)[0]   # '+' is encoded


def test_history_groups_minimal_rows_by_list():
    out = ha_mod._group_history(HISTORY, ("sensor.laundry_washer_mode", "sensor.laundry_dryer_mode"))
    assert list(out) == ["sensor.laundry_washer_mode", "sensor.laundry_dryer_mode"]
    assert out["sensor.laundry_washer_mode"] == [
        {"state": "idle", "last_changed": "2026-09-24T06:00:00+00:00"},
        {"state": "running", "last_changed": "2026-09-25T15:00:00+00:00"},
        {"state": "done", "last_changed": "2026-09-25T16:00:00+00:00"}]


def test_history_groups_by_the_entity_id_not_the_request_order():
    out = ha_mod._group_history(list(reversed(HISTORY)), ("sensor.laundry_washer_mode", "sensor.laundry_dryer_mode"))
    assert out["sensor.laundry_washer_mode"][1]["state"] == "running"
    assert len(out["sensor.laundry_dryer_mode"]) == 1


def test_history_list_without_entity_id_takes_its_position():
    data = [[{"state": "on", "last_changed": "2026-10-01T01:00:00+00:00"}], []]
    assert ha_mod._group_history(data, ("binary_sensor.a", "binary_sensor.b")) == {
        "binary_sensor.a": [{"state": "on", "last_changed": "2026-10-01T01:00:00+00:00"}]}


@pytest.mark.parametrize("bad", [None, {}, "x", 3])
def test_history_failure_is_none(bad):
    assert ha_mod._group_history(bad, ("a",)) is None


def test_history_open_end_uses_now_and_a_stable_key(monkeypatch):
    c = _client()
    rest = _Rest(monkeypatch, c, HISTORY, HISTORY)
    before = datetime.now(timezone.utc)
    first = c.get_history(["sensor.laundry_washer_mode"], T0)
    end = parse_qs(rest.calls[0][1].split("?", 1)[1])["end_time"][0]
    assert datetime.fromisoformat(end) >= before.replace(microsecond=0)
    assert c.get_history(["sensor.laundry_washer_mode"], T0) is first   # cached
    assert len(rest.calls) == 1


def test_history_keeps_last_good_on_failure(monkeypatch):
    c = _client()
    rest = _Rest(monkeypatch, c, HISTORY, None)
    good = c.get_history(["sensor.laundry_washer_mode"], T0, T1)
    assert c.get_history(["sensor.laundry_washer_mode"], T0, T1, ttl=0) == good   # refetch failed
    assert len(rest.calls) == 2


def test_history_failure_with_nothing_cached_is_none(monkeypatch):
    c = _client()
    _Rest(monkeypatch, c, None)
    assert c.get_history(["binary_sensor.front"], T0, T1) is None


def test_history_accepts_datetimes():
    assert ha_mod._when(datetime(2026, 10, 1, 6, tzinfo=timezone.utc)) == "2026-10-01T06:00:00+00:00"
    naive = datetime(2026, 10, 1, 6)  # noqa: DTZ001 - the naive case under test
    assert ha_mod._when(naive) == "2026-10-01T06:00:00+00:00"   # naive = UTC
    assert ha_mod._when(T1) == "2026-10-01T06:00:00+00:00"


def test_history_cache_evicts_old_windows(monkeypatch):
    c = _client()
    _Rest(monkeypatch, c, HISTORY, HISTORY)
    c.get_history(["a"], T0, T1)
    (key, (ts, val)), = c._history_cache.items()
    c._history_cache[key] = (ts - ha_mod._WINDOW_CACHE_MAX_AGE - 1, val)
    c.get_history(["a"], T0 + 3600, T1 + 3600)
    assert key not in c._history_cache and len(c._history_cache) == 1
    assert not any(str(key) in k for k in c._cache_locks)


# --- statistics over the websocket ---------------------------------------------------
class _FakeWS:
    def __init__(self, url, timeout, script):
        self.url, self.timeout = url, timeout
        self.script = list(script)
        self.sent = []
        self.closed = False

    def recv(self):
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, str) else json.dumps(item)

    def send(self, data):
        self.sent.append(json.loads(data))

    def close(self):
        self.closed = True


class _WSModule(types.ModuleType):
    """A stand-in `websocket` module; each create_connection pops the next script."""

    class WebSocketException(Exception):
        pass

    def __init__(self, *scripts):
        super().__init__("websocket")
        self.scripts = list(scripts)
        self.sockets = []

    def create_connection(self, url, timeout=None):
        script = self.scripts.pop(0)
        if isinstance(script, Exception):
            raise script
        ws = _FakeWS(url, timeout, script)
        self.sockets.append(ws)
        return ws


ROWS = {"sensor.water_meter_total": [
    {"start": 1790305200000.0, "end": 1790308800000.0, "change": 12.5},
    {"start": 1790308800000.0, "end": 1790312400000.0, "change": 0.0}]}


def _ok(result=ROWS, msg_id=1):
    return [{"type": "auth_required", "ha_version": "2026.8.3"},
            {"type": "auth_ok", "ha_version": "2026.8.3"},
            {"id": msg_id, "type": "result", "success": True, "result": result}]


def _ws(monkeypatch, *scripts):
    mod = _WSModule(*scripts)
    monkeypatch.setitem(sys.modules, "websocket", mod)
    return mod


def test_statistics_protocol(monkeypatch):
    ws = _ws(monkeypatch, _ok())
    c = _client()
    out = c.get_statistics(["sensor.water_meter_total"], T0, T1, "hour", ["change"], units={"volume": "L"})
    assert out == ROWS
    sock, = ws.sockets
    assert sock.url == "ws://ha.example:8123/api/websocket"
    assert sock.timeout == c.timeout and sock.closed
    auth, cmd = sock.sent
    assert auth == {"type": "auth", "access_token": SECRET_TOKEN}
    assert cmd == {
        "id": 1, "type": "recorder/statistics_during_period",
        "start_time": "2026-09-24T06:00:00+00:00", "end_time": "2026-10-01T06:00:00+00:00",
        "statistic_ids": ["sensor.water_meter_total"], "period": "hour", "types": ["change"],
        "units": {"volume": "L"}}


def test_statistics_omits_units_when_none(monkeypatch):
    ws = _ws(monkeypatch, _ok())
    _client().get_statistics(["sensor.x"], T0, T1, "day", ["mean"])
    assert "units" not in ws.sockets[0].sent[1]


@pytest.mark.parametrize("base,url", [
    ("https://ha.example", "wss://ha.example/api/websocket"),
    ("http://192.0.2.10:8123/", "ws://192.0.2.10:8123/api/websocket"),
])
def test_statistics_websocket_url(monkeypatch, base, url):
    ws = _ws(monkeypatch, _ok())
    HAClient(base, SECRET_TOKEN).get_statistics(["sensor.x"], T0, T1, "hour", ["change"])
    assert ws.sockets[0].url == url


def test_statistics_skips_frames_that_are_not_its_result(monkeypatch):
    script = _ok()
    script.insert(2, {"id": 7, "type": "event", "event": {}})
    _ws(monkeypatch, script)
    assert _client().get_statistics(["sensor.x"], T0, T1, "hour", ["change"]) == ROWS


def test_statistics_cached_and_keyed_on_every_argument(monkeypatch):
    ws = _ws(monkeypatch, _ok(), _ok(), _ok(), _ok(), _ok())
    c = _client()
    args = (["sensor.x"], T0, T1, "hour", ["change"])
    c.get_statistics(*args, units={"volume": "L"})
    c.get_statistics(*args, units={"volume": "L"})          # hit
    assert len(ws.sockets) == 1
    c.get_statistics(*args, units={"volume": "m³"})        # other units
    c.get_statistics(["sensor.x"], T0, T1, "day", ["change"], units={"volume": "L"})
    c.get_statistics(["sensor.x"], T0, T1, "hour", ["mean"], units={"volume": "L"})
    c.get_statistics(["sensor.x"], T0, T1 + 3600, "hour", ["change"], units={"volume": "L"})
    assert len(ws.sockets) == 5


@pytest.mark.parametrize("script,error", [
    ([{"type": "auth_required"}, {"type": "auth_invalid", "message": "Invalid access token"}],
     "websocket auth failed"),
    ([{"type": "hello"}], "websocket handshake failed"),
    ([{"type": "auth_required"}, {"type": "auth_ok"},
      {"id": 1, "type": "result", "success": False, "error": {"code": "unauthorized"}}],
     "websocket unauthorized"),
    ([{"type": "auth_required"}, "not json"], "JSONDecodeError"),
    ([{"type": "auth_required"}, {"type": "auth_ok"}, OSError("reset")], "OSError"),
])
def test_statistics_failures_are_none_with_an_error(monkeypatch, script, error):
    ws = _ws(monkeypatch, script)
    c = _client()
    assert c.get_statistics(["sensor.x"], T0, T1, "hour", ["change"]) is None
    assert error in c.status()["last_error"]
    assert SECRET_TOKEN not in json.dumps(c.status())
    assert ws.sockets[0].closed


def test_statistics_connect_failure(monkeypatch):
    _ws(monkeypatch, ConnectionRefusedError("refused"))
    c = _client()
    assert c.get_statistics(["sensor.x"], T0, T1, "hour", ["change"]) is None
    assert c.status()["last_error"] == "ConnectionRefusedError on recorder/statistics_during_period"


def test_statistics_keeps_last_good(monkeypatch):
    _ws(monkeypatch, _ok(), [{"type": "auth_required"}, {"type": "auth_invalid"}])
    c = _client()
    good = c.get_statistics(["sensor.x"], T0, T1, "hour", ["change"])
    assert c.get_statistics(["sensor.x"], T0, T1, "hour", ["change"], ttl=0) == good


def test_statistics_without_websocket_client(monkeypatch):
    monkeypatch.setitem(sys.modules, "websocket", None)   # makes `import websocket` fail
    c = _client()
    assert c.get_statistics(["sensor.x"], T0, T1, "hour", ["change"]) is None
    assert "websocket-client" in c.status()["last_error"]


def test_statistics_gives_up_at_the_deadline(monkeypatch):
    chatter = [{"type": "auth_required"}, {"type": "auth_ok"}] + [{"id": 9, "type": "event"}] * 50
    _ws(monkeypatch, chatter)
    c = _client()
    clock = iter(range(0, 1000, 5))
    monkeypatch.setattr(ha_mod.time, "monotonic", lambda: next(clock))
    assert c.get_statistics(["sensor.x"], T0, T1, "hour", ["change"]) is None
    assert c.status()["last_error"].startswith("TimeoutError")


def test_sidecar_imports_without_websocket_client():
    """Only _ws_command imports websocket-client, so the modules load without it."""
    code = ("import sys; sys.modules['websocket'] = None; "
            "import haku_sidecar.ha, haku_sidecar.modules, haku_sidecar.history; print('ok')")
    sidecar = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out = subprocess.run([sys.executable, "-c", code], cwd=sidecar, capture_output=True,
                         text=True, timeout=60, check=False)
    assert out.stdout.strip() == "ok", out.stderr
    assert "websocket" not in vars(ha_mod)


# --- forecast cache ---------------------------------------------------------------
def _forecast(eid, kind):
    return {"service_response": {eid: {"forecast": [{"datetime": "2026-10-02", "kind": kind}]}}}


def test_forecast_cached_per_entity_and_type(monkeypatch):
    c = _client()
    rest = _Rest(monkeypatch, c, _forecast("weather.home", "daily"), _forecast("weather.home", "hourly"))
    daily = c.get_forecast("weather.home", "daily")
    hourly = c.get_forecast("weather.home", "hourly")
    assert daily[0]["kind"] == "daily" and hourly[0]["kind"] == "hourly"
    assert c.get_forecast("weather.home", "daily") == daily        # cache hit, not the hourly list
    assert [call[2]["type"] for call in rest.calls] == ["daily", "hourly"]
    assert rest.calls[0][:2] == ("POST", "/api/services/weather/get_forecasts?return_response")
    assert rest.calls[0][2] == {"entity_id": "weather.home", "type": "daily"}


def test_forecast_keeps_last_good_and_never_caches_empty(monkeypatch):
    c = _client()
    clock = [1_792_000_000.0]
    monkeypatch.setattr(ha_mod.time, "time", lambda: clock[0])
    rest = _Rest(monkeypatch, c, {"service_response": {"weather.home": {"forecast": []}}},
                 _forecast("weather.home", "daily"), None)
    assert c.get_forecast("weather.home") == []
    clock[0] += ha_mod._FAIL_BACKOFF_S + 1          # an empty answer counts as a failure
    good = c.get_forecast("weather.home")
    assert good[0]["kind"] == "daily"
    assert c.get_forecast("weather.home", ttl=0) == good           # failed refetch
    assert len(rest.calls) == 3


def test_service_response_shapes(monkeypatch):
    c = _client()
    _Rest(monkeypatch, c, {"service_response": {"a": 1}}, {"other": 1}, None, {"service_response": []})
    assert c._service_response("x", "y", {}) == {"a": 1}
    assert c._service_response("x", "y", {}) is None
    assert c._service_response("x", "y", {}) is None
    assert c._service_response("x", "y", {}) is None


def test_existing_request_path_unchanged(monkeypatch):
    """The REST helper still builds the same URL and auth header (no regressions)."""
    seen = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"[]"

    def fake_urlopen(req, timeout):
        seen["url"], seen["auth"], seen["timeout"] = req.full_url, req.get_header("Authorization"), timeout
        return _Resp()

    monkeypatch.setattr(ha_mod.urllib.request, "urlopen", fake_urlopen)
    c = _client()
    assert c._get("/api/history/period/x?filter_entity_id=a") == []
    assert seen == {"url": "http://ha.example:8123/api/history/period/x?filter_entity_id=a",
                    "auth": f"Bearer {SECRET_TOKEN}", "timeout": c.timeout}
    assert urlsplit(seen["url"]).netloc == "ha.example:8123"


# --- the poller: rising edges, failure backoff ---------------------------------------
DOOR = "binary_sensor.front_doorcontact_contact"


def _snap(state, changed="2026-10-14T23:21:03+00:00"):
    return [{"entity_id": DOOR, "state": state, "last_changed": changed}]


def test_poll_records_the_rising_edge_at_has_last_changed(monkeypatch):
    c = _client()
    _Rest(monkeypatch, c, _snap("off"), _snap("on"), _snap("on"), _snap("off", "2026-10-14T23:21:06+00:00"))
    c._poll_once()
    assert c.last_on(DOOR) is None
    c._poll_once()
    opened = int(datetime(2026, 10, 14, 23, 21, 3, tzinfo=timezone.utc).timestamp())
    assert c.last_on(DOOR) == opened
    c._poll_once()
    c._poll_once()                                   # closed again: the opening is kept
    assert c.last_on(DOOR) == opened


def test_first_poll_records_no_edge(monkeypatch):
    c = _client()
    _Rest(monkeypatch, c, _snap("on"))
    c._poll_once()
    assert c.last_on(DOOR) is None                   # open before the sidecar started


def test_edge_from_unavailable_counts_and_bad_last_changed_uses_now(monkeypatch):
    c = _client()
    monkeypatch.setattr(ha_mod.time, "time", lambda: 1_792_000_000.0)
    _Rest(monkeypatch, c, _snap("unavailable"), _snap("on", "garbage"))
    c._poll_once()
    c._poll_once()
    assert c.last_on(DOOR) == 1_792_000_000


def test_failed_fetch_is_not_retried_inside_the_backoff(monkeypatch):
    c = _client()
    clock = [1_792_000_000.0]
    monkeypatch.setattr(ha_mod.time, "time", lambda: clock[0])
    rest = _Rest(monkeypatch, c, None, [{"when": "x", "state": "on"}])
    assert c.get_logbook(DOOR) == []                 # failed, nothing cached
    assert c.get_logbook(DOOR) == []                 # inside the backoff: no new request
    assert len(rest.calls) == 1
    clock[0] += ha_mod._FAIL_BACKOFF_S + 1
    assert c.get_logbook(DOOR) == [{"when": "x", "state": "on"}]
    assert len(rest.calls) == 2


def test_poll_interval_floor_is_one_second():
    assert HAClient("http://x", "t", poll_interval=1).poll_interval == 1
    assert HAClient("http://x", "t", poll_interval=0).poll_interval == 1
