"""Home Assistant client for the HAku sidecar.

Holds a background REST poller that refreshes a full entity snapshot on an interval
(default 10 s) into an in-memory cache, so every Roku-facing request is served from
RAM and HA sees at most one /api/states call per interval regardless of how many
Rokus poll the sidecar. Forecast data (which HA no longer exposes as a `forecast`
attribute) is fetched on demand via the weather.get_forecasts service and cached.

REST is stdlib-only (urllib), matching console-calendar's proven client against this
same HA. The tablet's detail panels add two on-demand reads, both cached about 10 min
with keep-last-good:
  get_history     REST /api/history/period (laundry runs, door opens)
  get_statistics  long-term statistics over the websocket command
                  `recorder/statistics_during_period` (the Energy dashboard's call; any
                  user may make it, unlike the admin-only `recorder.get_statistics`
                  service). It needs `websocket-client`, imported lazily so nothing
                  else in the sidecar (or its tests) depends on it.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .store import iso_epoch

_WS_PATH = "/api/websocket"
_WINDOW_CACHE_MAX_AGE = 6 * 3600   # drop history/statistics windows not fetched for this long
_FAIL_BACKOFF_S = 15               # a failed on-demand fetch isn't retried for this long


def _q(s):
    """URL-encode a path/query fragment (ISO timestamps carry '+', ':' offsets)."""
    return urllib.parse.quote(str(s), safe="")


def _when(t):
    """ISO-8601 for an epoch-seconds number or a datetime (a naive datetime is UTC)."""
    if isinstance(t, datetime):
        return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).isoformat()
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def _group_history(data, entity_ids):
    """REST history (a list per entity) -> {entity_id: [{state, last_changed}, ...]}.

    With `minimal_response` only each list's first item carries `entity_id`, so the rows
    are grouped by list. A list whose first item has no `entity_id` takes the requested id
    at its position. None (a failed call) stays None.
    """
    if not isinstance(data, list):
        return None
    out = {}
    for pos, rows in enumerate(data):
        if not isinstance(rows, list) or not rows:
            continue
        first = rows[0] if isinstance(rows[0], dict) else {}
        eid = first.get("entity_id") or (entity_ids[pos] if pos < len(entity_ids) else None)
        if not eid:
            continue
        out[eid] = [{"state": r.get("state"), "last_changed": r.get("last_changed")}
                    for r in rows if isinstance(r, dict)]
    return out


class HAClient:
    def __init__(self, base_url, token, poll_interval=10, timeout=10):
        self.base_url = (base_url or "").rstrip("/")
        self._token = token or ""
        self.poll_interval = max(1, int(poll_interval))
        self.timeout = timeout

        self._lock = threading.Lock()
        self._states = {}          # entity_id -> state dict
        self._connected = False
        self._last_ok_ts = 0
        self._last_error = None
        self._forecast_cache = {}  # (entity_id, type) -> (ts, list)
        # On-demand caches for the agenda modules (calendar / timeline). Each is
        # keyed and TTL-guarded like _forecast_cache; a per-key lock (double-checked)
        # collapses the thundering herd when N Rokos poll simultaneously after expiry.
        self._calendars_cache = {}  # "calendars" -> (ts, list)
        self._events_cache = {}     # "entity:days" -> (ts, list)
        self._logbook_cache = {}    # "entity:hours" -> (ts, list)
        self._history_cache = {}    # (ids, start, end|None) -> (ts, {entity_id: rows})
        self._stats_cache = {}      # (ids, start, end, period, types, units) -> (ts, {id: rows})
        self._cache_locks = {}      # namespaced key -> Lock
        self._cache_locks_guard = threading.Lock()
        self._failed_at = {}        # namespaced cache key -> epoch of its last failed fetch
        self._last_on = {}          # entity_id -> epoch of its last off->on edge (see _poll_once)
        self._stop = threading.Event()
        self._thread = None

    # ---- lifecycle --------------------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="ha-poller", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        # Prime immediately, then on a fixed cadence: the fetch's own time counts toward
        # the interval, so 1 s means about one poll a second, not one every 1 s + fetch.
        while not self._stop.is_set():
            started = time.monotonic()
            self._poll_once()
            self._stop.wait(max(0.0, self.poll_interval - (time.monotonic() - started)))

    def _poll_once(self):
        data = self._get("/api/states")
        if data is None:
            with self._lock:
                self._connected = False
            return
        by_id = {e["entity_id"]: e for e in data if isinstance(e, dict) and "entity_id" in e}
        with self._lock:
            self._note_rising_edges(self._states, by_id)
            self._states = by_id
            self._connected = True
            self._last_ok_ts = int(time.time())
            self._last_error = None

    def _note_rising_edges(self, before, after):
        """Remember when each entity last went to `on` (a door opening, say).

        Only a change seen between two snapshots counts, so the first poll after a start
        records nothing. HA's `last_changed` dates the edge; the time of the poll stands
        in when it is missing or unparseable. A door that opens and closes between two
        polls is missed, so the interval must stay short (1 s on nserver).
        """
        if not before:
            return
        for eid, st in after.items():
            if st.get("state") != "on":
                continue
            prev = before.get(eid)
            if prev is not None and prev.get("state") != "on":
                when = iso_epoch(st.get("last_changed"))
                self._last_on[eid] = when if when is not None else int(time.time())

    def last_on(self, entity_id):
        """Epoch of the entity's last off->on edge since the sidecar started, or None."""
        with self._lock:
            return self._last_on.get(entity_id)

    # ---- low-level HTTP ---------------------------------------------------
    def _request(self, method, endpoint, body=None):
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            self._last_error = f"HTTP {e.code} on {endpoint}"
            return None
        except (urllib.error.URLError, ValueError, OSError) as e:
            self._last_error = f"{type(e).__name__} on {endpoint}"
            return None

    def _get(self, endpoint):
        return self._request("GET", endpoint)

    # ---- read API ---------------------------------------------------------
    def get_state(self, entity_id):
        with self._lock:
            return self._states.get(entity_id)

    def get_states(self):
        with self._lock:
            return dict(self._states)

    def attr(self, entity_id, key, default=None):
        st = self.get_state(entity_id)
        if not st:
            return default
        return st.get("attributes", {}).get(key, default)

    def _service_response(self, domain, service, data):
        """POST a service call with `?return_response`; its `service_response` dict or None."""
        resp = self._request("POST", f"/api/services/{domain}/{service}?return_response", data)
        out = resp.get("service_response") if isinstance(resp, dict) else None
        return out if isinstance(out, dict) else None

    def get_forecast(self, entity_id, ftype="daily", ttl=600):
        """Return the daily/hourly forecast list via weather.get_forecasts (cached).

        Cached per (entity_id, type), so a daily and an hourly forecast never stand in for
        each other. An empty or failed answer keeps the last good list.
        """
        def fetch():
            resp = self._service_response(
                "weather", "get_forecasts", {"entity_id": entity_id, "type": ftype})
            ent = (resp or {}).get(entity_id)
            forecast = ent.get("forecast") if isinstance(ent, dict) else None
            return forecast if isinstance(forecast, list) and forecast else None

        return self._cached(self._forecast_cache, (entity_id, ftype), ttl, fetch) or []

    # ---- agenda fetches (calendar / logbook) ------------------------------
    def _key_lock(self, ns, key):
        """Return a stable per-(cache, key) lock so only one thread refetches it."""
        lk = f"{ns}:{key}"
        with self._cache_locks_guard:
            lock = self._cache_locks.get(lk)
            if lock is None:
                lock = threading.Lock()
                self._cache_locks[lk] = lock
            return lock

    def _cached(self, cache, key, ttl, fetch):
        """TTL cache with double-checked per-key locking and keep-last-good.

        `fetch` returns fresh data or None on failure; None is never cached, and a
        stale-but-good previous value is returned instead of failing hard.
        """
        hit = cache.get(key)
        if hit and (time.time() - hit[0]) < ttl:
            return hit[1]
        with self._key_lock(id(cache), key):
            hit = cache.get(key)  # re-check: another thread may have just filled it
            if hit and (time.time() - hit[0]) < ttl:
                return hit[1]
            fk = (id(cache), key)
            failed = self._failed_at.get(fk)
            if failed is not None and time.time() - failed < _FAIL_BACKOFF_S:
                return hit[1] if hit else None     # failed just now: don't hammer HA
            val = fetch()
            if val is not None:
                cache[key] = (time.time(), val)
                self._failed_at.pop(fk, None)
                return val
            self._failed_at[fk] = time.time()
            return hit[1] if hit else None

    def get_calendars(self, ttl=600):
        """List available calendar.* entities: [{entity_id, name}, ...]. Cached."""
        return self._cached(self._calendars_cache, "calendars", ttl,
                            lambda: self._get("/api/calendars")) or []

    def get_calendar_events(self, entity_id, lookahead_days=14, ttl=300):
        """Events for one calendar.* entity over [now, now+lookahead_days], cached.

        The window is derived here (not passed in) so the cache key is stable across
        the sub-second drift of repeated /api/state polls.
        """
        now = datetime.now(timezone.utc).astimezone()
        start = _q(now.isoformat())
        end = _q((now + timedelta(days=lookahead_days)).isoformat())
        key = f"{entity_id}:{lookahead_days}"
        path = f"/api/calendars/{entity_id}?start={start}&end={end}"
        return self._cached(self._events_cache, key, ttl, lambda: self._get(path)) or []

    def get_logbook(self, entity_id, lookback_hours=12, ttl=30):
        """Logbook rows for one entity over the last lookback_hours, cached.

        HA's REST logbook filter (`entity=`) is single-entity, so a watched-list
        module calls this once per entity and merges. Window derived here for a
        stable cache key.
        """
        now = datetime.now(timezone.utc)
        start = _q((now - timedelta(hours=lookback_hours)).isoformat())
        end = _q(now.isoformat())
        key = f"{entity_id}:{lookback_hours}"
        path = f"/api/logbook/{start}?entity={_q(entity_id)}&end_time={end}"
        return self._cached(self._logbook_cache, key, ttl, lambda: self._get(path)) or []

    # ---- detail-panel reads (history, long-term statistics) --------------
    def _evict(self, cache, max_age=_WINDOW_CACHE_MAX_AGE):
        """Drop entries (and their locks) not refreshed for `max_age` s.

        History and statistics keys carry their time window, which moves on every hour or
        day, so without this those caches would grow forever.
        """
        cutoff = time.time() - max_age
        for key, (ts, _val) in list(cache.items()):
            if ts < cutoff:
                cache.pop(key, None)
                with self._cache_locks_guard:
                    self._cache_locks.pop(f"{id(cache)}:{key}", None)

    def get_history(self, entity_ids, start, end=None, ttl=600):
        """State history for `entity_ids` over [start, end], cached.

        `start`/`end` are epoch seconds or datetimes. `end=None` means "up to now": the
        cache key then holds only `start`, so a repeat call within `ttl` is a hit and a
        failed refresh keeps the last good answer. Returns {entity_id: [{state,
        last_changed}, ...]} in time order (HA includes each entity's state as of `start`
        first; an entity with no rows is absent), or None on a failure with nothing cached.
        """
        ids = tuple(entity_ids)
        start_iso = _when(start)
        end_iso = None if end is None else _when(end)
        key = (ids, start_iso, end_iso)

        def fetch():
            until = end_iso or datetime.now(timezone.utc).isoformat()
            path = (f"/api/history/period/{_q(start_iso)}"
                    f"?filter_entity_id={','.join(_q(i) for i in ids)}"
                    f"&end_time={_q(until)}&minimal_response&no_attributes")
            return _group_history(self._get(path), ids)

        self._evict(self._history_cache)
        return self._cached(self._history_cache, key, ttl, fetch)

    def get_statistics(self, statistic_ids, start, end, period, types, units=None, ttl=600):
        """Long-term statistics via the websocket `recorder/statistics_during_period`, cached.

        `start`/`end` are epoch seconds or datetimes, `period` is "5minute", "hour", "day",
        "week" or "month", `types` a list like ["change"] or ["mean"], and `units` an
        optional unit-class map such as {"volume": "L"} (HA converts). The cache key holds
        every argument. Returns HA's result, {statistic_id: [{"start", "end", <types>},
        ...]} where `start`/`end` are epoch milliseconds (older HA: ISO strings), or None
        on a failure with nothing cached. A statistic with no rows is absent.
        """
        ids = tuple(statistic_ids)
        msg = {
            "id": 1,
            "type": "recorder/statistics_during_period",
            "start_time": _when(start),
            "end_time": _when(end),
            "statistic_ids": list(ids),
            "period": period,
            "types": list(types),
        }
        if units is not None:
            msg["units"] = dict(units)
        key = (ids, msg["start_time"], msg["end_time"], period, tuple(types),
               tuple(sorted((units or {}).items())))
        self._evict(self._stats_cache)
        return self._cached(self._stats_cache, key, ttl, lambda: self._ws_command(msg))

    def _ws_url(self):
        parts = urllib.parse.urlsplit(self.base_url)
        scheme = "wss" if parts.scheme == "https" else "ws"
        return urllib.parse.urlunsplit((scheme, parts.netloc, parts.path + _WS_PATH, "", ""))

    def _ws_command(self, msg):
        """One websocket command: connect, authenticate, send `msg`, read its result, close.

        Returns the result dict, or None (with `_last_error` set) on any failure. The
        whole exchange gets `self.timeout` seconds.
        """
        what = msg.get("type")
        try:
            import websocket  # websocket-client; lazy so the rest of the sidecar never needs it
        except ImportError:
            self._last_error = f"websocket-client missing for {what}"
            return None
        deadline = time.monotonic() + self.timeout
        ws = None
        try:
            ws = websocket.create_connection(self._ws_url(), timeout=self.timeout)
            if _ws_recv(ws).get("type") != "auth_required":
                self._last_error = f"websocket handshake failed for {what}"
                return None
            ws.send(json.dumps({"type": "auth", "access_token": self._token}))
            if _ws_recv(ws).get("type") != "auth_ok":
                self._last_error = f"websocket auth failed for {what}"
                return None
            ws.send(json.dumps(msg))
            while True:   # skip anything that isn't our result (HA sends nothing else here)
                if time.monotonic() > deadline:
                    raise TimeoutError
                reply = _ws_recv(ws)
                if reply.get("id") == msg["id"] and reply.get("type") == "result":
                    break
            if not reply.get("success"):
                code = (reply.get("error") or {}).get("code") or "error"
                self._last_error = f"websocket {code} on {what}"
                return None
            result = reply.get("result")
            return result if isinstance(result, dict) else None
        except (websocket.WebSocketException, OSError, ValueError) as e:
            self._last_error = f"{type(e).__name__} on {what}"
            return None
        finally:
            if ws is not None:
                try:
                    ws.close()
                except (websocket.WebSocketException, OSError):
                    pass

    # ---- status -----------------------------------------------------------
    def status(self):
        with self._lock:
            return {
                "connected": self._connected,
                "url": self.base_url,
                "token_present": bool(self._token),
                "last_ok_ts": self._last_ok_ts,
                "last_error": self._last_error,
                "entity_count": len(self._states),
            }


def _ws_recv(ws):
    """The next websocket frame as a dict ({} for anything else); raises on bad JSON."""
    msg = json.loads(ws.recv())
    return msg if isinstance(msg, dict) else {}
