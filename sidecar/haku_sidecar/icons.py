"""Module-tile accent icons for the HAku sidecar (Pillow only — no matplotlib).

Small PNGs shown as a corner accent on home-tile "value" cards: a Font Awesome
glyph for the weather module, and hand-drawn gauge shapes (battery / bucket)
for energy / water whose fill level is proportional to a live reading. Kept
separate from charts.py's matplotlib pipeline on purpose — these are simple
flat-color shapes re-rendered on every poll from every Roku, and a matplotlib
Figure/Axes per icon would be needless overhead for that.

Font Awesome Free "solid" font (assets/fontawesome-solid.otf, SIL OFL 1.1 —
see assets/FONT_AWESOME_LICENSE.txt) supplies the weather glyphs. Codepoints
below were read from that release's own metadata/icons.json and confirmed
free-tier ("solid") — see HAKU_DESIGN.md / the icon-enrichment plan for the
verification note.
"""
import hashlib
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import charts

_ASSET_DIR = Path(__file__).parent / "assets"
_FA_SOLID_PATH = _ASSET_DIR / "fontawesome-solid.otf"

_GLYPHS = {
    "sun": "", "moon": "", "cloud": "", "cloud-sun": "",
    "cloud-rain": "", "cloud-showers-heavy": "", "bolt": "",
    "cloud-bolt": "", "snowflake": "", "smog": "", "wind": "",
    "circle": "",
}
DEFAULT_GLYPH = "circle"

_font_cache = {}  # size -> ImageFont (font loading from disk is the expensive part)


def _font(size):
    f = _font_cache.get(size)
    if f is None:
        f = ImageFont.truetype(str(_FA_SOLID_PATH), size)
        _font_cache[size] = f
    return f


def _rgba(hex_color, alpha=255):
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


_cache = {}  # key -> png bytes, mirrors charts.py's render cache
_CACHE_MAX = 64


def _key(name, w, h, payload):
    h_ = hashlib.sha1(repr(payload).encode()).hexdigest()[:12]
    return f"{name}:{w}x{h}:{h_}"


def _emit(im):
    buf = io.BytesIO()
    im.save(buf, format="png")
    return buf.getvalue()


def _cached(name, w, h, payload, build):
    ck = _key(name, w, h, payload)
    png = _cache.get(ck)
    if png is not None:
        return png
    png = _emit(build())
    if len(_cache) > _CACHE_MAX:
        _cache.clear()
    _cache[ck] = png
    return png


def fill_bucket_pct(value, max_value, step=5):
    """Round value/max_value into a 0-100 step-of-`step` percentage bucket.

    Used both as the icon URL's cache-bust token and the actual render
    fraction, so the Roku only re-fetches when the rendered PNG would
    actually look different, and near-identical readings share one cache
    entry server-side.
    """
    if value is None or not max_value:
        return 0
    frac = max(0.0, min(1.0, value / max_value))
    pct = round(frac * 100 / step) * step
    return max(0, min(100, int(pct)))


def render_glyph(glyph_name, w=96, h=96, color=charts.INK):
    """A single centered Font Awesome glyph on a transparent canvas."""
    name = glyph_name if glyph_name in _GLYPHS else DEFAULT_GLYPH

    def build():
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)
        size = int(min(w, h) * 0.72)
        draw.text((w / 2, h / 2), _GLYPHS[name], font=_font(size),
                  fill=_rgba(color), anchor="mm")
        return im
    return _cached(f"glyph:{name}", w, h, name, build)


def render_battery(fill_frac, w=96, h=96, color=charts.BRAND):
    """Landscape battery outline with a continuously-sized inner fill."""
    frac = max(0.0, min(1.0, fill_frac))

    def build():
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)
        outline = _rgba(color)
        stroke = max(2, int(h * 0.05))

        pad = w * 0.12
        nub_w = max(3, w * 0.07)
        body = (pad, h * 0.28, w - pad - nub_w, h * 0.72)
        nub = (w - pad - nub_w, h * 0.40, w - pad, h * 0.60)
        draw.rounded_rectangle(body, radius=h * 0.07, outline=outline, width=stroke)
        draw.rounded_rectangle(nub, radius=h * 0.02, fill=outline)

        inset = stroke + 2
        inner = (body[0] + inset, body[1] + inset, body[2] - inset, body[3] - inset)
        fill_w = (inner[2] - inner[0]) * frac
        if fill_w > 0:
            draw.rectangle((inner[0], inner[1], inner[0] + fill_w, inner[3]), fill=outline)
        return im
    return _cached("battery", w, h, round(frac, 2), build)


def render_bucket(fill_frac, w=96, h=96, color=charts.BRAND):
    """Bucket silhouette (tapered trapezoid + handle) with a rising fill."""
    frac = max(0.0, min(1.0, fill_frac))

    def build():
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)
        outline = _rgba(color)
        stroke = max(2, int(h * 0.045))

        top_y, bot_y = h * 0.24, h * 0.86
        top_l, top_r = w * 0.18, w * 0.82
        bot_l, bot_r = w * 0.30, w * 0.70

        def edge_x(y):
            t = (y - top_y) / (bot_y - top_y)
            return top_l + (bot_l - top_l) * t, top_r + (bot_r - top_r) * t

        if frac > 0:
            fill_y = bot_y - (bot_y - top_y) * frac
            fl, fr = edge_x(fill_y)
            bl, br = edge_x(bot_y)
            draw.polygon([(fl, fill_y), (fr, fill_y), (br, bot_y), (bl, bot_y)], fill=outline)

        bucket = [(top_l, top_y), (top_r, top_y), (bot_r, bot_y), (bot_l, bot_y), (top_l, top_y)]
        draw.line(bucket, fill=outline, width=stroke)
        draw.arc((w * 0.30, h * 0.04, w * 0.70, h * 0.32), start=200, end=340,
                  fill=outline, width=max(2, int(h * 0.03)))
        return im
    return _cached("bucket", w, h, round(frac, 2), build)
