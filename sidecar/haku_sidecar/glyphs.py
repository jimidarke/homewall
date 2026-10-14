"""Material Design Icons (MDI) glyph names for the tablet's tile `glyph` keys.

The sidecar only names the glyph; the tablet draws it (it ships the path data for the
set listed in the tablet contract; the Roku channel draws the same set). Only layout views
carry `glyph`, so none of this touches the default view's output. Per-module glyph rules live in each module next to the tile they describe;
what is shared lives here: the HA weather-condition map and the fallback.
"""

# HA `weather.*` state -> MDI glyph. Keys are exactly the conditions weather.py labels.
WEATHER_GLYPHS = {
    "clear-night": "weather-night",
    "cloudy": "weather-cloudy",
    "exceptional": "alert-circle-outline",
    "fog": "weather-fog",
    "hail": "weather-hail",
    "lightning": "weather-lightning",
    "lightning-rainy": "weather-lightning-rainy",
    "partlycloudy": "weather-partly-cloudy",
    "pouring": "weather-pouring",
    "rainy": "weather-rainy",
    "snowy": "weather-snowy",
    "snowy-rainy": "weather-snowy-rainy",
    "sunny": "weather-sunny",
    "windy": "weather-windy",
    "windy-variant": "weather-windy-variant",
}
DEFAULT_WEATHER_GLYPH = "weather-partly-cloudy"


def weather_glyph(condition):
    """MDI glyph for an HA weather condition; the default for unknown or missing (stale)."""
    return WEATHER_GLYPHS.get(condition, DEFAULT_WEATHER_GLYPH)
