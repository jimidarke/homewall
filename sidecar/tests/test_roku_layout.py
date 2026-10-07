"""The wall Rokus' `layouts.roku` in dashboard.json.example (`?layout=roku`).

A 6x4 grid (0.12): the tablet's modules through qualified `tablet:` refs, each with its
own `tile` (the ref merge is shallow, so the Roku's tiles no longer follow tablet moves),
a live front camera square top right and the 2x2 Forecast card (3-day strip plus the
`weather_chart` card) under it. The default view the older channels read is untouched
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
    assert grid == {"cols": 6, "rows": 4, "cellW": 289, "cellH": 220, "originX": 52, "originY": 116, "gap": 16}
    seen = []
    for m in roku["modules"]:
        seen.extend(_cells(m["tile"]))
    assert sorted(seen) == sorted((c, r) for c in range(6) for r in range(4))


_VALUE = {"type": "value", "w": 1, "h": 1}
ROKU_TILES = {
    "doors": {**_VALUE, "col": 0, "row": 0, "w": 2},
    "laundry": {**_VALUE, "col": 0, "row": 1}, "water": {**_VALUE, "col": 1, "row": 1},
    "energy": {**_VALUE, "col": 0, "row": 2}, "gas": {**_VALUE, "col": 1, "row": 2},
    "weather": {**_VALUE, "col": 0, "row": 3}, "climate": {**_VALUE, "col": 1, "row": 3},
    "calendar": {"type": "agenda", "col": 2, "row": 0, "w": 2, "h": 2, "dropHeaders": False},
    "timeline": {"type": "agenda", "col": 2, "row": 2, "w": 2, "h": 2, "dropHeaders": True},
    "cameras": {"type": "camera", "col": 4, "row": 0, "w": 2, "h": 2, "cam": "front"},
    "forecast": {"type": "forecast", "col": 4, "row": 2, "w": 2, "h": 2, "card": "/api/card/weather_chart.png"},
}


def test_roku_tiles_are_the_planned_6x4_wall(monkeypatch):
    roku = {m["id"]: m for m in _layout(monkeypatch, "roku")["modules"]}
    assert {mid: m["tile"] for mid, m in roku.items()} == ROKU_TILES
    assert roku["cameras"]["title"] == "Front"
    fc = roku["forecast"]
    assert (fc["kind"], fc["feedKey"], fc["title"], fc["outlook"]) == ("weather", "forecast", "Forecast", True)


def test_roku_tablet_refs_still_resolve_to_the_tablets_modules(monkeypatch):
    """Only `tile` differs: kind, feedKey, entities and the rest come from the tablet's entry."""
    tablet = {m["id"]: m for m in _layout(monkeypatch, "tablet")["modules"]}
    roku = {m["id"]: m for m in _layout(monkeypatch, "roku")["modules"]}
    assert set(roku) - set(tablet) == {"cameras", "forecast"}
    for mid, m in tablet.items():
        assert {k: v for k, v in roku[mid].items() if k != "tile"} == \
            {k: v for k, v in m.items() if k != "tile"}, mid
        assert (roku[mid]["kind"], roku[mid]["feedKey"]) == (m["kind"], m["feedKey"]), mid
    fc = roku["forecast"]
    assert (fc["entities"], fc["refreshMs"]) == (tablet["weather"]["entities"], tablet["weather"]["refreshMs"])


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
