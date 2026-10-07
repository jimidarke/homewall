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
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless — must precede pyplot import
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

# Barlow (SIL OFL 1.1, assets/OFL-Barlow.txt), the same two cuts the Roku channel
# ships in roku/fonts/, so a rendered card's type matches the native labels beside it.
# A missing file (a deploy that forgot assets/) falls back to matplotlib's default
# face rather than taking the whole sidecar down at import.
_ASSET_DIR = Path(__file__).parent / "assets"
BARLOW = _ASSET_DIR / "barlow_medium.ttf"
BARLOW_SEMI = _ASSET_DIR / "barlow_semi_condensed_semibold.ttf"
for _f in (BARLOW, BARLOW_SEMI):
    if _f.exists():
        font_manager.fontManager.addfont(str(_f))

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


# --- the Roku wall's temperature chart (`weather_chart`) ------------------------
# Tokens from roku/source/Config.brs (HK_INK, HK_INK_MUTED, HK_INK_FAINT, HK_COOL):
# the card body is the channel's own smoked-glass panel, so this image is fully
# transparent and only draws lines and type, at sizes read from across a room.
TV_INK = "#FAF6EE"
TV_COOL = "#7CCBF2"
_TONES = {"ink": TV_INK, "cool": TV_COOL}
_MUTED_A, _FAINT_A = 0.78, 0.48      # ink alphas of HK_INK_MUTED / HK_INK_FAINT
_GRID_A, _TICK_A, _NOW_A = 0.16, 0.08, 0.40
_LABEL_PX, _EMPTY_PX = 21, 24
_LINE_PX, _DOT_PX = 3, 9
_PAD_X = 4                           # x label inset from its tick, like the tablet's


def _pt(px):
    """Pixels -> points at the 100 dpi the cards render at (fonts and widths are in points)."""
    return px * 72.0 / 100.0


def _font(path, px):
    if not path.exists():
        return font_manager.FontProperties(size=_pt(px))
    return font_manager.FontProperties(fname=str(path), size=_pt(px))


def render_temp_chart(chart, w=554, h=208):
    """Draw a weather `_chart_block` dict (the tablet's chart block) as a w x h RGBA PNG.

    Each series' runs are separate lines (a gap in the data is a gap in the line), in
    their tone: observed in ink, the forecast in cool. Faint gridlines carry the
    y ticks' labels on the left; the x ticks' labels sit along the bottom, each just
    right of its bucket, and the strong one ("Now") gets a firmer vertical line and
    full-ink type. No title or legend: the card's header names it, and the two lines
    meet at Now. With `empty` (or nothing to plot) the text is centred instead.
    The background is fully transparent; renders are cached on the whole dict (it
    carries `start` and the live reading) plus the size.
    """
    ck = _key("weather_chart", w, h, chart)
    if ck in _cache:
        return _cache[ck]

    fig = plt.figure(figsize=(w / 100.0, h / 100.0), dpi=100)
    fig.patch.set_alpha(0)
    series = [s for s in chart.get("series") or [] if s.get("runs")]
    y = chart.get("y")
    if chart.get("empty") or not series or not y:
        fig.text(0.5, 0.5, chart.get("empty") or "No data", ha="center", va="center",
                 color=TV_INK, alpha=_MUTED_A, fontproperties=_font(BARLOW, _EMPTY_PX))
    else:
        _draw_temp_chart(fig, chart, series, y, w, h)

    png = _emit(fig, w, h)
    if len(_cache) > _CACHE_MAX:
        _cache.clear()
    _cache[ck] = png
    return png


def _draw_temp_chart(fig, chart, series, y, w, h):
    label, strong = _font(BARLOW, _LABEL_PX), _font(BARLOW_SEMI, _LABEL_PX)
    renderer = fig.canvas.get_renderer()

    # Margins in pixels: the widest y label plus a gap on the left, one label line
    # at the bottom, and half a label at the top so the top tick's text isn't cut.
    y_labels = [fig.text(0, 0, t["label"], fontproperties=label) for t in y.get("ticks", [])]
    widest = max((t.get_window_extent(renderer).width for t in y_labels), default=0)
    for t in y_labels:
        t.remove()
    left = int(widest) + 10
    bottom, top, right = _LABEL_PX + 10, _LABEL_PX // 2 + 2, 6
    ax = fig.add_axes([left / w, bottom / h, (w - left - right) / w, (h - bottom - top) / h])
    ax.set_facecolor("none")
    ax.set_axis_off()
    count = chart.get("count") or 1
    ax.set_xlim(0, count - 1)
    ax.set_ylim(y["min"], y["max"])

    for t in y.get("ticks", []):
        ax.axhline(t["v"], color=TV_INK, alpha=_GRID_A, lw=_pt(1), zorder=1)
        ax.annotate(t["label"], (0, t["v"]), xycoords=("axes fraction", "data"),
                    xytext=(-_pt(10), 0), textcoords="offset points", ha="right", va="center",
                    color=TV_INK, alpha=_MUTED_A, fontproperties=label, annotation_clip=False)

    # x labels: left-aligned just past their tick, clamped inside the image; a label
    # that would collide with an already placed one is dropped, "Now" placed first.
    ticks = sorted(chart.get("x", {}).get("ticks", []), key=lambda t: not t.get("strong"))
    placed = []
    plot_w = w - left - right
    for t in ticks:
        is_strong = bool(t.get("strong"))
        ax.axvline(t["i"], color=TV_INK, alpha=_NOW_A if is_strong else _TICK_A,
                   lw=_pt(2 if is_strong else 1), zorder=1)
        fp = strong if is_strong else label
        probe = fig.text(0, 0, t["label"], fontproperties=fp)
        tw = probe.get_window_extent(renderer).width
        probe.remove()
        x = min(left + t["i"] * plot_w / max(count - 1, 1) + _PAD_X, w - right - tw)
        if any(x < px + pw + 8 and px < x + tw + 8 for px, pw in placed):
            continue
        placed.append((x, tw))
        fig.text(x / w, (bottom - 6) / h, t["label"], ha="left", va="top", fontproperties=fp,
                 color=TV_INK, alpha=1.0 if is_strong else _MUTED_A)

    for s in series:
        color = _TONES.get(s.get("tone"), TV_INK)
        for r in s["runs"]:
            xs = list(range(r["i"], r["i"] + len(r["v"])))
            if len(xs) == 1:
                ax.plot(xs, r["v"], "o", color=color, ms=_pt(_DOT_PX), zorder=3, clip_on=False)
            else:
                ax.plot(xs, r["v"], color=color, lw=_pt(_LINE_PX), solid_capstyle="round",
                        solid_joinstyle="round", zorder=3, clip_on=False)

    # A dot on the live reading, where the lines meet at Now.
    now_i = next((t["i"] for t in ticks if t.get("strong")), None)
    for s in series:
        v = next((r["v"][now_i - r["i"]] for r in s["runs"]
                  if now_i is not None and r["i"] <= now_i < r["i"] + len(r["v"])), None)
        if v is not None:
            ax.plot([now_i], [v], "o", color=_TONES.get(s.get("tone"), TV_INK), ms=_pt(_DOT_PX),
                    zorder=4, clip_on=False)
            break


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
