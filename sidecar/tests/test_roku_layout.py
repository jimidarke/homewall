"""The wall Rokus' `layouts.roku` in dashboard.json.example (`?layout=roku`).

A 6x3 grid: the left four columns are the tablet's tiles (qualified `tablet:` refs, so
moving a tablet tile moves the Roku's too), a 2x2 camera square on the right and a 2x1
3-day forecast strip under it. The default view the older channels read is untouched
(test_roku_golden.py).
"""
import json

from haku_sidecar import config as cfg_module
from haku_sidecar.store import CachedJson

from test_roku_golden import EXAMPLE, roku_client  # noqa: F401  (pytest fixture)


def _layout(monkeypatch, name):
    monkeypatch.setattr(cfg_module, "_cache", CachedJson(EXAMPLE, cfg_module.DEFAULT_CONFIG))
    return cfg_module.get_layout(name)[0]


def _cells(tile):
    return {(tile["col"] + c, tile["row"] + r) for c in range(tile["w"]) for r in range(tile["h"])}


def test_roku_layout_tiles_cover_the_grid_exactly_once(monkeypatch):
    roku = _layout(monkeypatch, "roku")
    grid = roku["grid"]
    assert (grid["cols"], grid["rows"]) == (6, 3)
    seen = []
    for m in roku["modules"]:
        seen.extend(_cells(m["tile"]))
    assert sorted(seen) == sorted((c, r) for c in range(6) for r in range(3))


def test_roku_left_columns_are_the_tablets_tiles(monkeypatch):
    tablet = {m["id"]: m for m in _layout(monkeypatch, "tablet")["modules"]}
    roku = {m["id"]: m for m in _layout(monkeypatch, "roku")["modules"]}
    for mid, m in tablet.items():
        assert roku[mid] == m, mid                               # same tile, same keys
    assert set(roku) - set(tablet) == {"cameras", "forecast"}
    assert roku["cameras"]["tile"] == {"type": "camera", "col": 4, "row": 0, "w": 2, "h": 2}
    fc = roku["forecast"]
    assert (fc["kind"], fc["feedKey"], fc["outlook"]) == ("weather", "forecast", True)
    assert fc["tile"] == {"type": "forecast", "col": 4, "row": 2, "w": 2, "h": 1}


def test_roku_layout_never_carries_tablet_only_keys(monkeypatch):
    roku = _layout(monkeypatch, "roku")
    assert "nightDim" not in roku
    assert roku["background"] == {"enabled": True, "intervalMs": 60000}


def test_roku_config_and_state_routes(roku_client):
    conf = roku_client.get("/api/config?layout=roku")
    assert conf.status_code == 200
    assert len(conf.get_data()) < 16 * 1024                      # the Roku's registry slot
    state = roku_client.get("/api/state?layout=roku").get_json()
    assert {"doors", "laundry", "timeline", "calendar", "water", "energy", "weather",
            "gas", "climate", "cameras", "forecast"} <= set(state)
    assert [d["id"] for d in state["doors"]["doors"]] == ["front", "back"]
    assert [m["id"] for m in state["laundry"]["machines"]] == ["washer", "dryer"]
    # The golden FakeHA's forecast has two days after its frozen "today".
    assert [d["label"] for d in state["forecast"]["outlook"]] == ["Fri", "Sat"]
    assert "outlook" not in state["weather"]
    assert json.dumps(state).find("null") == -1
