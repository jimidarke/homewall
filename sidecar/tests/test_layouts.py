"""Per-display layouts (`layouts` in dashboard.json, `?layout=` on the API).

The Roku caches /api/config in a ~16 KB registry slot, so the default responses must
stay byte-for-byte what they were before layouts existed; `?layout=<name>` serves a
display its own resolved module set (the kitchen tablet: no cameras, extra tiles).
"""
import copy
import json
import logging

import pytest
from PIL import Image

from haku_sidecar import config as cfg_module
from haku_sidecar.store import CachedJson

from conftest import FakeHA


WEATHER = {
    "id": "weather", "kind": "weather", "title": "Weather", "feedKey": "weather",
    "tile": {"type": "value", "col": 0, "row": 0, "w": 1, "h": 1},
    "drill": {"type": "chart", "card": "/api/card/weather_forecast.png"},
    "entities": {"forecast": "weather.edmonton_forecast", "indoor": "weather.my_ecobee"},
}
ENERGY = {
    "id": "energy", "kind": "energy", "title": "Energy", "feedKey": "energy",
    "tile": {"type": "value", "col": 1, "row": 0, "w": 1, "h": 1},
    "entities": {"power": "sensor.emporia_total_power"},
}
WATER = {
    "id": "water", "kind": "water", "title": "Water", "feedKey": "water", "maxFlowLpm": 10,
    "tile": {"type": "value", "col": 0, "row": 1, "w": 1, "h": 1},
    "entities": {"flow": "sensor.water_flow_lpm", "daily": "sensor.water_daily_usage"},
}
CAMERAS = {
    "id": "cameras", "kind": "cameras", "title": "Cameras", "feedKey": "cameras",
    "tile": {"type": "camera", "col": 2, "row": 0, "w": 1, "h": 1, "thumbCam": "mosaic"},
    "streams": ["front", "yard", "mosaic"],
}

BASE_CFG = {
    "version": 1, "site": "home", "timezone": "America/Edmonton",
    "grid": {"cols": 4, "rows": 2, "cellW": 432, "cellH": 440, "originX": 60, "originY": 160, "gap": 24},
    "background": {"intervalMs": 20000, "enabled": True},
    "modules": [WEATHER, ENERGY, WATER, CAMERAS],
}

TABLET_BG_DIR = "/srv/haku/backgrounds-tablet"
WATER_TABLET_TILE = {"type": "value", "col": 1, "row": 1, "w": 1, "h": 1}
DOORS = {
    "id": "doors", "kind": "doors", "title": "Doors", "feedKey": "doors",
    "tile": {"type": "value", "col": 0, "row": 0, "w": 1, "h": 1},
    "entities": {"doors": [
        {"id": "front", "entity": "binary_sensor.front_doorcontact_contact", "label": "Front"}]},
}
LAYOUTS = {
    "tablet": {
        "grid": {"cols": 4, "rows": 3},
        "nightDim": {"start": "22:00", "end": "06:30", "brightness": 0.15},
        "background": {"intervalMs": 180000, "dir": TABLET_BG_DIR},
        "modules": [
            DOORS,
            {"ref": "water", "runningSeverity": "normal", "tile": WATER_TABLET_TILE},
            {"ref": "weather", "tile": {"type": "value", "col": 0, "row": 2, "w": 1, "h": 1}},
            {"ref": "energy", "tile": {"type": "value", "col": 1, "row": 2, "w": 1, "h": 1}},
        ],
    },
}

STATES = {
    "weather.edmonton_forecast": {
        "entity_id": "weather.edmonton_forecast", "state": "rainy",
        "attributes": {"temperature": 12.4, "humidity": 86, "wind_speed": 15.0},
    },
    "sensor.water_flow_lpm": {
        "entity_id": "sensor.water_flow_lpm", "state": "5.7",
        "attributes": {"unit_of_measurement": "L/min"},
    },
}


def _use_config(monkeypatch, config):
    monkeypatch.setattr(cfg_module, "_cache", CachedJson("/nonexistent/haku/dashboard.json", config))


def _use_fake_ha(monkeypatch):
    from haku_sidecar import app as app_module
    monkeypatch.setattr(app_module, "ha", FakeHA(STATES))


def _ids(public):
    return [m["id"] for m in public["modules"]]


@pytest.fixture()
def tablet_client(client, monkeypatch):
    """The shared `client`, over BASE_CFG + LAYOUTS, with a FakeHA for the live poller."""
    _use_config(monkeypatch, {**BASE_CFG, "layouts": LAYOUTS})
    _use_fake_ha(monkeypatch)
    return client


# --- default (Roku) output is unchanged --------------------------------------
def test_default_config_has_no_layouts_key(tablet_client):
    body = tablet_client.get("/api/config").get_json()
    assert "layouts" not in body
    assert body["modules"] == BASE_CFG["modules"]
    assert "layouts" not in cfg_module.public_config()


def test_default_output_identical_with_and_without_layouts_block(client, monkeypatch):
    _use_fake_ha(monkeypatch)

    def snapshot(config):
        _use_config(monkeypatch, config)
        conf = client.get("/api/config").get_data()
        state = client.get("/api/state").get_json()
        state.pop("ts")
        return conf, state

    assert snapshot(BASE_CFG) == snapshot({**BASE_CFG, "layouts": LAYOUTS})


# --- get_layout resolution ---------------------------------------------------
def test_get_layout_resolves_ref_and_overrides_tile(monkeypatch):
    _use_config(monkeypatch, {**BASE_CFG, "layouts": LAYOUTS})
    public, _ = cfg_module.get_layout("tablet")
    water = next(m for m in public["modules"] if m["id"] == "water")
    assert water == {**WATER, "runningSeverity": "normal", "tile": WATER_TABLET_TILE}
    assert "ref" not in water


def test_ref_override_is_shallow(monkeypatch):
    layouts = {"tablet": {"modules": [
        {"ref": "weather", "tile": {"col": 2}},
        {"ref": "water", "entities": {"flow": "sensor.other_flow"}},
    ]}}
    _use_config(monkeypatch, {**BASE_CFG, "layouts": layouts})
    weather, water = cfg_module.get_layout("tablet")[0]["modules"]
    assert weather["tile"] == {"col": 2}                       # replaced, not deep-merged
    assert weather["entities"] == WEATHER["entities"]          # untouched keys come from the base
    assert water["entities"] == {"flow": "sensor.other_flow"}
    assert water["tile"] == WATER["tile"]


def test_layout_only_module_included(monkeypatch):
    _use_config(monkeypatch, {**BASE_CFG, "layouts": LAYOUTS})
    public, _ = cfg_module.get_layout("tablet")
    assert _ids(public) == ["doors", "water", "weather", "energy"]   # layout order, no cameras
    assert public["modules"][0] == DOORS


def test_get_layout_does_not_mutate_cache(monkeypatch):
    _use_config(monkeypatch, {**BASE_CFG, "layouts": LAYOUTS})
    before = copy.deepcopy(cfg_module.get_config())
    public, _ = cfg_module.get_layout("tablet")
    # Scribble over everything handed back: none of it may alias the cached config.
    for m in public["modules"]:
        m["tile"]["col"] = 99
        m.setdefault("entities", {})["scribble"] = "x"
    public["grid"]["cols"] = 1
    public["background"]["enabled"] = False
    public["nightDim"]["brightness"] = 1.0
    cfg_module.get_layout("tablet")
    assert cfg_module.get_config() == before


def test_get_layout_top_level_shape_and_fallbacks(monkeypatch):
    layouts = {**LAYOUTS, "plain": {"modules": [{"ref": "weather"}]}}
    _use_config(monkeypatch, {**BASE_CFG, "layouts": layouts})

    tablet, _ = cfg_module.get_layout("tablet")
    assert set(tablet) == {"version", "site", "timezone", "grid", "nightDim", "background", "modules"}
    assert (tablet["version"], tablet["site"], tablet["timezone"]) == (1, "home", "America/Edmonton")
    assert tablet["grid"] == {"cols": 4, "rows": 3}
    assert tablet["nightDim"] == LAYOUTS["tablet"]["nightDim"]

    plain, bg_dir = cfg_module.get_layout("plain")
    assert set(plain) == {"version", "site", "timezone", "grid", "background", "modules"}
    assert plain["grid"] == BASE_CFG["grid"]                    # falls back to the top-level grid
    assert plain["background"] == BASE_CFG["background"]
    assert bg_dir is None                                       # None -> HAKU_BG_DIR as today


def test_get_layout_drops_invalid_module_and_logs(monkeypatch, caplog):
    layouts = {"tablet": {"modules": [
        {"id": "notile", "kind": "doors", "feedKey": "notile"},  # no tile
        "junk",
        {"ref": "weather", "tile": "not-a-dict"},                # the override breaks it
        {"ref": "water"},
    ]}}
    _use_config(monkeypatch, {**BASE_CFG, "layouts": layouts})
    with caplog.at_level(logging.WARNING, logger="haku_sidecar.config"):
        public, _ = cfg_module.get_layout("tablet")
    assert _ids(public) == ["water"]
    assert "notile" in caplog.text
    assert "weather" in caplog.text


def test_layout_background_merges_over_global(monkeypatch):
    _use_config(monkeypatch, {**BASE_CFG, "layouts": LAYOUTS})
    public, bg_dir = cfg_module.get_layout("tablet")
    assert public["background"] == {"intervalMs": 180000, "enabled": True}
    assert bg_dir == TABLET_BG_DIR


# --- malformed layout config: never a 500 ------------------------------------
@pytest.mark.parametrize("modules", [5, True, "doors", {"ref": "water"}])
def test_layout_modules_not_a_list_serves_no_modules(client, monkeypatch, caplog, modules):
    _use_config(monkeypatch, {**BASE_CFG, "layouts": {"tablet": {"modules": modules}}})
    _use_fake_ha(monkeypatch)
    with caplog.at_level(logging.WARNING, logger="haku_sidecar.config"):
        public, _ = cfg_module.get_layout("tablet")
        conf = client.get("/api/config?layout=tablet")
        state = client.get("/api/state?layout=tablet")
    assert public["modules"] == []
    assert "modules is not a list" in caplog.text
    assert conf.status_code == 200 and conf.get_json()["modules"] == []
    assert state.status_code == 200


@pytest.mark.parametrize("bad_dir", [["/srv/photos"], {"path": "/srv/photos"}, 5, True, ""])
def test_layout_background_dir_not_a_string_is_ignored(client, tmp_path, monkeypatch, caplog, bad_dir):
    Image.new("RGB", (8, 8)).save(str(tmp_path / "roku.png"))
    monkeypatch.setenv("HAKU_BG_DIR", str(tmp_path))
    layouts = {"tablet": {"modules": [], "background": {"intervalMs": 180000, "dir": bad_dir}}}
    _use_config(monkeypatch, {**BASE_CFG, "layouts": layouts})
    with caplog.at_level(logging.WARNING, logger="haku_sidecar.config"):
        public, bg_dir = cfg_module.get_layout("tablet")
        r = client.get("/api/backgrounds?layout=tablet")
    assert bg_dir is None                                       # HAKU_BG_DIR, as with no dir
    assert public["background"] == {"intervalMs": 180000, "enabled": True}
    assert "background.dir" in caplog.text
    assert r.status_code == 200
    assert [i["name"] for i in r.get_json()["images"]] == ["roku.png"]


# --- routes ------------------------------------------------------------------
def test_unknown_layout_404(tablet_client, monkeypatch):
    for path in ("/api/config", "/api/state", "/api/module/water",
                 "/api/icon/weather.png", "/api/card/weather_forecast.png"):
        r = tablet_client.get(f"{path}?layout=nope")
        assert r.status_code == 404, path
        assert r.get_json() == {"error": "unknown layout", "layout": "nope"}, path
    r = tablet_client.get("/api/config?layout=")                # an empty name is not "no layout"
    assert (r.status_code, r.get_json()) == (404, {"error": "unknown layout", "layout": ""})
    with pytest.raises(cfg_module.UnknownLayout):
        cfg_module.get_layout("nope")

    _use_config(monkeypatch, BASE_CFG)                          # no `layouts` block at all
    assert tablet_client.get("/api/config?layout=tablet").status_code == 404


def test_unknown_ref_404(client, monkeypatch):
    layouts = {"tablet": {"modules": [
        {"ref": "water", "tile": WATER_TABLET_TILE},
        {"ref": "ghost", "tile": {"type": "value", "col": 0, "row": 0, "w": 1, "h": 1}},
    ]}}
    _use_config(monkeypatch, {**BASE_CFG, "layouts": layouts})
    _use_fake_ha(monkeypatch)
    for path in ("/api/config", "/api/state", "/api/module/water"):
        r = client.get(f"{path}?layout=tablet")
        assert r.status_code == 404, path
        assert r.get_json() == {"error": "unknown ref", "ref": "ghost"}, path
    with pytest.raises(cfg_module.UnknownRef) as exc:
        cfg_module.get_layout("tablet")
    assert exc.value.ref == "ghost"


def test_layout_config_route(tablet_client):
    r = tablet_client.get("/api/config?layout=tablet")
    assert r.status_code == 200
    body = r.get_json()
    assert _ids(body) == ["doors", "water", "weather", "energy"]
    assert body["grid"] == {"cols": 4, "rows": 3}
    assert set(body["sidecar"]) == {"base", "config", "state"}
    assert "layouts" not in body
    assert json.dumps(body).find("null") == -1


def test_bg_dir_never_serialized(tablet_client):
    r = tablet_client.get("/api/config?layout=tablet")
    assert r.status_code == 200
    text = r.get_data(as_text=True)
    assert '"dir"' not in text
    assert TABLET_BG_DIR not in text


def test_state_with_layout_only_resolved_feed_keys(tablet_client):
    r = tablet_client.get("/api/state?layout=tablet")
    assert r.status_code == 200
    body = r.get_json()
    assert set(body) == {"v", "ts", "doors", "water", "weather", "energy"}   # no cameras
    assert json.dumps(body).find("null") == -1


def test_module_route_finds_layout_only_module_with_param(tablet_client):
    assert tablet_client.get("/api/module/doors?layout=tablet").status_code == 200
    r = tablet_client.get("/api/module/doors")                  # default (Roku) set: unchanged
    assert (r.status_code, r.get_json()) == (404, {"error": "unknown module", "id": "doors"})
    assert tablet_client.get("/api/module/water?layout=tablet").get_json()["tile"]
    assert tablet_client.get("/api/module/cameras?layout=tablet").status_code == 404


def test_icon_and_card_routes_resolve_through_layout(client, monkeypatch):
    layouts = {
        "renamed": {"modules": [{"ref": "weather", "id": "outside"}]},
        "nowx": {"modules": [{"ref": "water"}]},
    }
    _use_config(monkeypatch, {**BASE_CFG, "layouts": layouts})
    _use_fake_ha(monkeypatch)
    r = client.get("/api/icon/outside.png?layout=renamed")      # id exists only in the layout
    assert (r.status_code, r.mimetype) == (200, "image/png")
    assert client.get("/api/icon/outside.png").status_code == 404
    r = client.get("/api/card/weather_forecast.png?layout=nowx")  # no weather module there
    assert (r.status_code, r.get_json()) == (404, {"error": "unknown card", "name": "weather_forecast"})


# --- qualified refs ("<layout>:<id>") ------------------------------------------
def _with_wall(monkeypatch, wall_modules):
    layouts = {**LAYOUTS, "wall": {"grid": {"cols": 6, "rows": 3}, "modules": wall_modules}}
    _use_config(monkeypatch, {**BASE_CFG, "layouts": layouts})


def test_qualified_ref_resolves_through_the_other_layout(monkeypatch):
    _with_wall(monkeypatch, [{"ref": "tablet:water"}, {"ref": "tablet:doors"}, {"ref": "cameras"}])
    public, _ = cfg_module.get_layout("wall")
    water, doors, cameras = public["modules"]
    # The tablet's resolved entry: top-level module + the tablet's own overrides.
    assert water == {**WATER, "runningSeverity": "normal", "tile": WATER_TABLET_TILE}
    assert doors == DOORS                                       # a tablet layout-only module
    assert cameras == CAMERAS                                   # bare refs still mean top-level
    assert public["grid"] == {"cols": 6, "rows": 3}


def test_qualified_ref_overrides_merge_over_the_resolved_entry(monkeypatch):
    tile = {"type": "forecast", "col": 4, "row": 2, "w": 2, "h": 1}
    _with_wall(monkeypatch, [{"ref": "tablet:weather", "id": "forecast", "outlook": True, "tile": tile}])
    (fc,) = cfg_module.get_layout("wall")[0]["modules"]
    assert fc["id"] == "forecast" and fc["outlook"] is True and fc["tile"] == tile
    assert fc["entities"] == WEATHER["entities"] and fc["kind"] == "weather"
    assert "ref" not in fc


@pytest.mark.parametrize("ref", ["tablet:ghost", "nope:water", ":water", "tablet:"])
def test_qualified_ref_unknown_404_only_for_that_layout(client, monkeypatch, ref):
    _with_wall(monkeypatch, [{"ref": "tablet:water"}, {"ref": ref}])
    _use_fake_ha(monkeypatch)
    r = client.get("/api/config?layout=wall")
    assert (r.status_code, r.get_json()) == (404, {"error": "unknown ref", "ref": ref})
    assert client.get("/api/config?layout=tablet").status_code == 200
    assert client.get("/api/config").status_code == 200


def test_qualified_ref_cannot_chain(monkeypatch):
    layouts = {
        **LAYOUTS,
        "wall": {"modules": [{"ref": "tablet:water"}]},
        "hall": {"modules": [{"ref": "wall:water"}]},           # wall's entry is itself qualified
    }
    _use_config(monkeypatch, {**BASE_CFG, "layouts": layouts})
    assert _ids(cfg_module.get_layout("wall")[0]) == ["water"]
    with pytest.raises(cfg_module.UnknownRef) as exc:
        cfg_module.get_layout("hall")
    assert exc.value.ref == "tablet:water"


def test_qualified_ref_does_not_mutate_cache(monkeypatch):
    _with_wall(monkeypatch, [{"ref": "tablet:water"}, {"ref": "tablet:doors"}])
    before = copy.deepcopy(cfg_module.get_config())
    public, _ = cfg_module.get_layout("wall")
    for m in public["modules"]:
        m["tile"]["col"] = 99
        m.setdefault("entities", {})["scribble"] = "x"
    assert cfg_module.get_config() == before
