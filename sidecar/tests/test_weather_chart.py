"""The Roku wall's `weather_chart` card: the weather panel's temperature chart as a PNG.

It reuses test_detail_modules.py's weather fixtures (and its clock, frozen at Thu
2026-10-01 18:30 in America/Edmonton), so the chart drawn here is the very block the
tablet's detail panel serves.
"""
import io

import pytest
from conftest import FakeHA
from PIL import Image

from haku_sidecar import charts, modules
from haku_sidecar import config as cfg_module

from test_detail_modules import DAILY, FORECASTS, WEATHER_ENTS, WEATHER_STATES, WEATHER_STATS, _block, _weather
from test_detail_modules import frozen  # noqa: F401  (autouse: the frozen clock)
from test_roku_golden import roku_client  # noqa: F401  (pytest fixture)

W, H = 554, 208
DESC = {"id": "forecast", "kind": "weather", "title": "Forecast", "outlook": True,
        "tile": {"type": "forecast", "card": "/api/card/weather_chart.png"}, "entities": WEATHER_ENTS}
EDMONTON_TICKS = ["6 PM", "Thu", "6 AM", "12 PM", "Now", "Fri", "6 AM", "12 PM", "6 PM"]


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(charts, "_cache", {})


def _ha(states=None, forecast=None, statistics=None):
    return FakeHA(WEATHER_STATES if states is None else states, FORECASTS if forecast is None else forecast,
                  statistics=WEATHER_STATS if statistics is None else statistics)


def _image(png):
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    im = Image.open(io.BytesIO(png))
    im.load()
    return im


def _captured(monkeypatch):
    seen = []
    monkeypatch.setattr(charts, "render_temp_chart", lambda chart, w, h: seen.append((chart, w, h)) or b"png")
    return seen


def _zone(monkeypatch, name):
    monkeypatch.setattr(cfg_module, "get_timezone", lambda: name)


def test_weather_chart_card_is_a_transparent_png_of_the_asked_size(monkeypatch):
    _zone(monkeypatch, "America/Edmonton")
    im = _image(modules.render_card(_ha(), "weather_chart", {"modules": [DESC]}, W, H))
    assert (im.size, im.mode) == ((W, H), "RGBA")
    alpha = im.getchannel("A")
    assert alpha.getextrema() == (0, 255)                    # a see-through background, solid lines
    assert alpha.getpixel((W // 2, 2)) == 0 and alpha.getpixel((W - 1, H // 2)) == 0


def test_weather_chart_card_draws_the_detail_panels_chart_block(monkeypatch):
    _zone(monkeypatch, "America/Edmonton")
    seen = _captured(monkeypatch)
    assert modules.render_card(_ha(), "weather_chart", {"modules": [DESC]}, W, H) == b"png"
    (chart, w, h), = seen
    assert (w, h) == (W, H)
    panel = _block(_weather()[0], "chart")
    assert chart == {k: v for k, v in panel.items() if k != "col"}         # the panel's, minus its column


def test_weather_chart_card_labels_hours_on_the_configured_clock(monkeypatch):
    """nserver runs on UTC: without the configured zone, '6 PM' Edmonton would read '12 AM'."""
    seen = _captured(monkeypatch)
    _zone(monkeypatch, "America/Edmonton")
    modules.render_card(_ha(), "weather_chart", {"modules": [DESC]}, W, H)
    _zone(monkeypatch, "UTC")
    modules.render_card(_ha(), "weather_chart", {"modules": [DESC]}, W, H)
    modules.render_card(_ha(), "weather_chart", {"modules": [{**DESC, "timezone": "America/Edmonton"}]}, W, H)
    edmonton, utc, own = ([t["label"] for t in chart["x"]["ticks"]] for chart, _w, _h in seen)
    assert edmonton == own == EDMONTON_TICKS                 # a module's own zone wins over the config's
    assert utc == ["Thu", "6 AM", "12 PM", "6 PM", "Now", "6 AM", "12 PM", "6 PM", "Sat"]


def test_weather_chart_card_shares_the_detail_panels_ha_reads(monkeypatch):
    """Same statistics and hourly-forecast arguments as the panel, so HA's caches serve both."""
    _zone(monkeypatch, "America/Edmonton")
    _captured(monkeypatch)
    ha = _ha()
    modules.render_card(ha, "weather_chart", {"modules": [DESC]}, W, H)
    _body, panel = _weather()
    assert ha.calls == panel.calls
    assert ha.forecast_calls == [("weather.edmonton_forecast", "hourly")]     # no daily: the card has no use for it
    assert set(ha.forecast_calls) < set(panel.forecast_calls)


def test_weather_chart_card_with_nothing_to_draw_still_renders(monkeypatch):
    _zone(monkeypatch, "America/Edmonton")
    ha = _ha(forecast={"daily": DAILY}, statistics=FakeHA.FAIL)
    im = _image(modules.render_card(ha, "weather_chart", {"modules": [DESC]}, W, H))
    assert (im.size, im.mode) == ((W, H), "RGBA")
    assert im.getchannel("A").getextrema()[1] > 0             # the "History unavailable" text
    seen = _captured(monkeypatch)
    modules.render_card(_ha({}, {"daily": [], "hourly": []}, {}), "weather_chart", {"modules": [DESC]}, W, H)
    assert seen[0][0]["empty"] == "No history yet"


def test_temp_chart_renders_one_line_per_run_and_caches():
    chart = {"type": "chart", "start": 0, "step": 3600, "count": 5,
             "x": {"ticks": [{"i": 0, "label": "6 PM"}, {"i": 2, "label": "Now", "strong": True}]},
             "series": [{"label": "Observed", "tone": "ink", "runs": [{"i": 0, "v": [1.0]}, {"i": 1, "v": [2, 3]}]},
                        {"label": "Forecast", "tone": "cool", "runs": [{"i": 2, "v": [3, 4, 2]}]}],
             "y": {"min": 0, "max": 5, "ticks": [{"v": 0, "label": "0°"}, {"v": 5, "label": "5°"}]}}
    png = charts.render_temp_chart(chart, 300, 120)
    assert _image(png).size == (300, 120)
    assert charts.render_temp_chart(dict(chart), 300, 120) is png             # same data: no re-render
    assert charts.render_temp_chart(chart, 301, 120) is not png


def test_unknown_card_is_still_none_and_a_404(roku_client):
    assert modules.render_card(_ha(), "nope", {"modules": [DESC]}, W, H) is None
    r = roku_client.get("/api/card/nope.png?layout=roku")
    assert (r.status_code, r.get_json()) == (404, {"error": "unknown card", "name": "nope"})


def test_weather_chart_route_on_the_roku_layout(roku_client):
    r = roku_client.get(f"/api/card/weather_chart.png?layout=roku&w={W}&h={H}")
    assert (r.status_code, r.mimetype) == (200, "image/png")
    assert _image(r.get_data()).size == (W, H)
