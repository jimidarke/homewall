"""Server-side card rendering for the HAku sidecar (matplotlib Agg + Pillow).

Roku has no chart primitives and no webview, so history/forecast cards are rendered
to PNG here and shown as Posters on the TV. We use the Agg backend (headless, no
browser dependency — deliberately NOT Plotly/Kaleido which needs Chrome) and the
HAku "Daylight" palette so cards match the on-device look. Each render is cached by
(name, size, rounded inputs) so the shared 30 s poll from N Rokos re-renders at most
once per data change.
"""
import hashlib
import io

import matplotlib
matplotlib.use("Agg")  # headless — must precede pyplot import
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

# --- "Smoked glass" dark palette (mirrors roku/source/Config.brs) --------
# Cards render on a dark, translucent glass panel with light text so they
# composite over the Roku's photo background (PNG saved WITH alpha, transparent
# figure). Accent colours are unchanged from the brand set — they read on dark.
INK = "#F3EFE6"      # primary text (light on glass)
MUTED = "#B9B3A6"    # secondary / muted text
BRAND = "#5B8C7F"
HIGH = "#D4673E"     # live / high temp
LOW = "#6B9080"      # ok / low temp
CARD_BG = "#1A211F"  # dark charcoal glass fill
CARD_ALPHA = 0.72

_cache = {}  # key -> png bytes
_CACHE_MAX = 64


def _key(name, w, h, payload):
    h_ = hashlib.sha1(repr(payload).encode()).hexdigest()[:12]
    return f"{name}:{w}x{h}:{h_}"


def _emit(fig, w, h):
    buf = io.BytesIO()
    # transparent=True → PNG keeps an alpha channel so the dark glass card
    # composites over the Roku's photo background.
    fig.savefig(buf, format="png", dpi=100, transparent=True)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_weather_forecast(current, forecast, w=560, h=360):
    """Render a daily temp band card.

    current: {"temp_c", "condition", "cond_label"}
    forecast: list of {"datetime", "temperature", "templow", "condition", ...}
    Returns PNG bytes sized exactly w x h.
    """
    days = forecast[:6] if forecast else []
    # Round inputs for the cache so poll jitter doesn't force re-renders.
    payload = [(d.get("datetime", "")[:10],
                round(_num(d.get("temperature")), 1),
                round(_num(d.get("templow")), 1)) for d in days]
    ck = _key("weather_forecast", w, h, (round(_num(current.get("temp_c")), 1), payload))
    if ck in _cache:
        return _cache[ck]

    fig = plt.figure(figsize=(w / 100.0, h / 100.0), dpi=100)
    fig.patch.set_alpha(0)  # transparent figure — only the glass card is opaque

    # Dark, semi-transparent rounded "glass" card behind the whole figure.
    card = FancyBboxPatch(
        (0.03, 0.05), 0.94, 0.90,
        boxstyle="round,pad=0,rounding_size=0.035",
        transform=fig.transFigure, clip_on=False,
        facecolor=CARD_BG, edgecolor="none", alpha=CARD_ALPHA, zorder=0,
    )
    fig.add_artist(card)

    ax = fig.add_axes([0.10, 0.16, 0.86, 0.60])  # leave room for header
    ax.set_facecolor("none")

    if days:
        xs = list(range(len(days)))
        highs = [_num(d.get("temperature")) for d in days]
        lows = [_num(d.get("templow"), highs[i] if i < len(highs) else 0)
                for i, d in enumerate(days)]
        labels = [_weekday(d.get("datetime", "")) for d in days]

        ax.fill_between(xs, lows, highs, color=BRAND, alpha=0.18, zorder=1)
        ax.plot(xs, highs, color=HIGH, lw=3, marker="o", ms=6, zorder=3)
        ax.plot(xs, lows, color=LOW, lw=3, marker="o", ms=6, zorder=3)
        for i, (hi, lo) in enumerate(zip(highs, lows)):
            ax.annotate(f"{hi:.0f}°", (i, hi), textcoords="offset points",
                        xytext=(0, 9), ha="center", color=HIGH, fontsize=13, weight="bold")
            ax.annotate(f"{lo:.0f}°", (i, lo), textcoords="offset points",
                        xytext=(0, -16), ha="center", color=LOW, fontsize=13, weight="bold")
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, color=INK, fontsize=13)
        ax.margins(x=0.06, y=0.30)
    else:
        ax.text(0.5, 0.5, "forecast unavailable", ha="center", va="center",
                color=MUTED, fontsize=15, transform=ax.transAxes)
        ax.set_xticks([])

    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)

    # Header
    temp = current.get("temp_c")
    hero = f"{temp:.0f}°" if isinstance(temp, (int, float)) else "--°"
    label = current.get("cond_label") or "Weather"
    fig.text(0.10, 0.86, "WEATHER", color=MUTED, fontsize=13, weight="bold")
    fig.text(0.10, 0.80, f"{hero}  {label}", color=INK, fontsize=22, weight="bold",
             va="top")

    png = _emit(fig, w, h)
    if len(_cache) > _CACHE_MAX:
        _cache.clear()
    _cache[ck] = png
    return png


# --- helpers ---------------------------------------------------------------
def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


_WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _weekday(dt_iso):
    # dt_iso like "2026-07-05T13:17:00+00:00"; derive weekday without dateutil.
    try:
        from datetime import date
        y, m, d = int(dt_iso[0:4]), int(dt_iso[5:7]), int(dt_iso[8:10])
        return _WD[date(y, m, d).weekday()]
    except Exception:
        return dt_iso[5:10]
