#!/usr/bin/env python3
"""
HAku brand-asset pipeline.

Single source of truth for shipped image assets. Reads source artwork from
../../docs/brand/ and emits Roku-spec variants into ../images/ plus
one default background card into ../../sidecar/backgrounds/.

Sources (docs/brand/, NOT shipped in the .pkg):
  docs/brand/logo_icon.png        4:3 transparent PNG, icon-only glyph — app icon
  docs/brand/logo_wordmark.png    Transparent PNG, full icon+wordmark lockup —
                               splash, reconnect wordmark, background card

Outputs (roku/images/, referenced by manifest):
  icon_focus_sd.png           248x186  (legacy, paletted)
  icon_focus_hd.png           290x218  (paletted)
  icon_focus_fhd.png          540x405  (paletted)
  splash_sd.jpg               720x480  (progressive q88)
  splash_hd.jpg               1280x720 (progressive q88)
  splash_fhd.jpg              1920x1080 (progressive q90)
  haku_wordmark.png      500x100  (transparent, used by reconnect overlay)
  bg_fallback.jpg              1920x1080 (dark gradient + centered wordmark,
                                          cold-boot background before the
                                          sidecar's list arrives)

Output (sidecar/backgrounds/, seed set copied to HAKU_BG_DIR at deploy):
  bg_00_haku_logo.jpg         1920x1080 (wordmark centered on cream) — sorts
                               first in rotation (filename-sorted playlist).

Brand:
  splash_color  #F7F1E3 (cream) — also fills any letterbox seam on splashes
                                  and the 4:3 padding around square icons.

Run: python3 scripts/generate_brand_assets.py
"""

from __future__ import annotations
import os
from pathlib import Path
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "docs" / "brand"
OUT = REPO / "roku" / "images"
OUT_BG = REPO / "sidecar" / "backgrounds"

# Palette mirrors source/Config.brs (HW_BG_*, HW_TEXT_*). Keep in sync.
CREAM_RGB = (0xF7, 0xF1, 0xE3)
CREAM_RGBA = CREAM_RGB + (0xFF,)
SCRIM_RGB  = (0x2B, 0x2A, 0x26)              # bg.scrim base colour
INK_RGB    = (0x2B, 0x2A, 0x26)              # text.ink (also hairline border)


def autocrop(img: Image.Image, pad_frac: float = 0.04) -> Image.Image:
    """Trim transparent margin down to the visible content + a small pad.

    Source art often ships with generous transparent canvas around the mark
    (for arbitrary-aspect flexibility); left uncropped, every downstream
    composite (icon tile, background card) inherits that padding and reads
    as "zoomed out" no matter how large `inset` is set.
    """
    bbox = img.getbbox()
    if bbox is None:
        return img
    l, t, r, b = bbox
    pad_x = int((r - l) * pad_frac)
    pad_y = int((b - t) * pad_frac)
    l = max(0, l - pad_x)
    t = max(0, t - pad_y)
    r = min(img.width, r + pad_x)
    b = min(img.height, b + pad_y)
    return img.crop((l, t, r, b))


def fit_letterbox(src: Image.Image, w: int, h: int) -> Image.Image:
    canvas = Image.new("RGB", (w, h), CREAM_RGB)
    sw, sh = src.size
    scale = min(w / sw, h / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    r = src.resize((nw, nh), Image.LANCZOS)
    canvas.paste(r, ((w - nw) // 2, (h - nh) // 2), r if r.mode == "RGBA" else None)
    return canvas


def make_icon(logo: Image.Image, w: int, h: int, inset: float = 0.94) -> Image.Image:
    canvas = Image.new("RGBA", (w, h), CREAM_RGBA)
    target = int(min(w, h) * inset)
    sw, sh = logo.size
    scale = target / max(sw, sh)
    nw, nh = int(sw * scale), int(sh * scale)
    r = logo.resize((nw, nh), Image.LANCZOS)
    canvas.paste(r, ((w - nw) // 2, (h - nh) // 2), r)
    return canvas.convert("RGB").quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE)


def make_wordmark(logo: Image.Image, w: int = 500, h: int = 100) -> Image.Image:
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    target_h = int(h * 0.92)
    sw, sh = logo.size
    scale = target_h / sh
    nw, nh = int(sw * scale), int(sh * scale)
    r = logo.resize((nw, nh), Image.LANCZOS)
    canvas.paste(r, ((w - nw) // 2, (h - nh) // 2), r)
    return canvas


def make_bg_card(logo: Image.Image, w: int = 1920, h: int = 1080,
                 bg_rgb: tuple = CREAM_RGB, inset: float = 0.68) -> Image.Image:
    """Full-bleed background-rotation card: logo centered on a solid fill.

    Same paste-on-solid-color pattern as make_icon, just full-bleed instead
    of composited into a small tile.
    """
    canvas = Image.new("RGB", (w, h), bg_rgb)
    target = int(min(w, h) * inset)
    sw, sh = logo.size
    scale = target / max(sw, sh)
    nw, nh = int(sw * scale), int(sh * scale)
    r = logo.resize((nw, nh), Image.LANCZOS)
    canvas.paste(r, ((w - nw) // 2, (h - nh) // 2), r)
    return canvas


def make_rounded_card(w: int, h: int, fill_rgba: tuple, radius: int,
                      border_rgba: tuple | None = None, border_w: int = 0) -> Image.Image:
    """Solid rounded-rect card with optional 1-px hairline border.

    Used for overlay backgrounds — Roku's Rectangle node has no cornerRadius,
    so we bake the corners into a Poster.
    """
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=fill_rgba)
    if border_rgba is not None and border_w > 0:
        draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius,
                               outline=border_rgba, width=border_w)
    return canvas


def make_pip_frame(w: int = 480, h: int = 302, header: int = 32,
                   border_w: int = 4, radius: int = 12) -> Image.Image:
    """PIP frame: scrim header strip + transparent video well + warn-tint border.

    The JPEG snapshot Poster sits in the transparent well at offset
    (border_w, header) with size (w - 2*border_w, h - header - border_w).
    """
    warn = (0xD9, 0xA4, 0x41, 0xFF)           # accent.warn
    scrim_solid = SCRIM_RGB + (0xE6,)         # 90% alpha — header sits over video
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    # Outer rounded rect = warn border (drawn as fill, then we punch the well).
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=warn)
    # Header strip (top, scrim).
    draw.rectangle((border_w, border_w, w - border_w - 1, header - 1),
                   fill=scrim_solid)
    # Video well — transparent hole. ImageDraw doesn't punch holes, so we draw
    # the well as fully-transparent on a fresh layer and alpha-composite.
    well = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    well_draw = ImageDraw.Draw(well)
    well_draw.rectangle((border_w, header, w - border_w - 1, h - border_w - 1),
                        fill=(0, 0, 0, 0))
    # The "transparent hole" trick: paste the well with alpha=0 over the canvas
    # by using putpixel-style overwrite. PIL's paste with mask=well doesn't
    # actually clear pixels, so we just leave the well area filled with warn,
    # then layer the JPEG Poster over it at runtime — the Poster covers the
    # warn fill in the inner area and only the border + header remain visible.
    # (No need to punch a hole; Poster on top renders opaquely.)
    return canvas


def make_chevron(direction: str = "left", w: int = 56, h: int = 84,
                 color: tuple = (0xFA, 0xF6, 0xEE, 0xFF)) -> Image.Image:
    """Solid triangle chevron. Roku's system font has no geometric-shape glyphs
    (◀/▶ render as tofu boxes), so the live carousel affordances are baked PNGs.
    """
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if direction == "left":
        d.polygon([(w - 1, 0), (w - 1, h - 1), (0, h // 2)], fill=color)
    else:
        d.polygon([(0, 0), (0, h - 1), (w - 1, h // 2)], fill=color)
    return img


def make_background_fallback(logo: Image.Image | None = None,
                             w: int = 1920, h: int = 1080) -> Image.Image:
    """Dark vertical gradient used as the rotating-background fallback.

    Shown by BackgroundGallery on cold boot and whenever the sidecar image list
    is unavailable/empty, so the smoked-glass home screen always has a dark,
    on-theme backdrop. Built as a 1-px column then stretched (fast, seam-free).
    If `logo` is given, it's centered on top so even the very first frame
    before any network call is on-brand.
    """
    top = (0x12, 0x16, 0x14)
    bot = (0x05, 0x07, 0x09)
    col = Image.new("RGB", (1, h))
    cpx = col.load()
    for y in range(h):
        t = y / max(1, h - 1)
        cpx[0, y] = (
            int(top[0] + (bot[0] - top[0]) * t),
            int(top[1] + (bot[1] - top[1]) * t),
            int(top[2] + (bot[2] - top[2]) * t),
        )
    canvas = col.resize((w, h))
    if logo is not None:
        target = int(min(w, h) * 0.3)
        sw, sh = logo.size
        scale = target / max(sw, sh)
        nw, nh = int(sw * scale), int(sh * scale)
        r = logo.resize((nw, nh), Image.LANCZOS)
        canvas.paste(r, ((w - nw) // 2, (h - nh) // 2), r)
    return canvas


def make_top_fade(w: int = 1920, h: int = 220) -> Image.Image:
    """Vertical gradient: scrim 80% alpha at top -> 0 alpha at bottom.

    Drawn in alpha only so it tints whatever is underneath. Used behind the
    chip stack to keep small text legible over busy frames.
    """
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = canvas.load()
    top_alpha = 0xCC                          # 80% — matches HW_BG_SCRIM
    for y in range(h):
        t = y / max(1, h - 1)
        a = int(top_alpha * (1.0 - t))
        for x in range(w):
            px[x, y] = SCRIM_RGB + (a,)
    return canvas


def emit_overlay_assets(logo: Image.Image) -> list[tuple[str, str]]:
    """Bake the v0.5 overlay surfaces. Returns (name, size-bytes) for each."""
    out: list[tuple[str, str]] = []

    # Scrim card — door banner + text banner. 80% alpha matches HW_BG_SCRIM.
    scrim_card = make_rounded_card(720, 120, SCRIM_RGB + (0xCC,), radius=16)
    p = OUT / "overlay_card_scrim.png"
    scrim_card.save(p, "PNG", optimize=True)
    out.append((p.name, str(os.path.getsize(p))))

    # Cream chip — weather + sensor. 92% alpha + hairline ink border.
    cream_chip = make_rounded_card(360, 96, CREAM_RGB + (0xEB,), radius=14,
                                   border_rgba=INK_RGB + (0x66,), border_w=1)
    p = OUT / "overlay_card_cream.png"
    cream_chip.save(p, "PNG", optimize=True)
    out.append((p.name, str(os.path.getsize(p))))

    # PIP frame.
    pip = make_pip_frame()
    p = OUT / "overlay_pip_frame.png"
    pip.save(p, "PNG", optimize=True)
    out.append((p.name, str(os.path.getsize(p))))

    # Top-fade gradient.
    fade = make_top_fade()
    p = OUT / "overlay_gradient_topfade.png"
    fade.save(p, "PNG", optimize=True)
    out.append((p.name, str(os.path.getsize(p))))

    # Rotating-background fallback (dark gradient JPEG + centered wordmark).
    p = OUT / "bg_fallback.jpg"
    make_background_fallback(logo).save(p, "JPEG", quality=85, optimize=True, progressive=True)
    out.append((p.name, str(os.path.getsize(p))))

    # Live-carousel chevrons (font has no ◀/▶ glyphs).
    for direction in ("left", "right"):
        p = OUT / f"chevron_{direction}.png"
        make_chevron(direction).save(p, "PNG", optimize=True)
        out.append((p.name, str(os.path.getsize(p))))

    return out


def main() -> None:
    logo_icon = autocrop(Image.open(SRC / "logo_icon.png").convert("RGBA"))
    logo_wordmark = autocrop(Image.open(SRC / "logo_wordmark.png").convert("RGBA"))

    OUT.mkdir(parents=True, exist_ok=True)
    OUT_BG.mkdir(parents=True, exist_ok=True)

    icon_specs = [
        ("icon_focus_sd.png",  248, 186),
        ("icon_focus_hd.png",  290, 218),
        ("icon_focus_fhd.png", 540, 405),
    ]
    for name, w, h in icon_specs:
        make_icon(logo_icon, w, h).save(OUT / name, "PNG", optimize=True)

    splash_specs = [
        ("splash_sd.jpg",   720,  480, 88),
        ("splash_hd.jpg",  1280,  720, 88),
        ("splash_fhd.jpg", 1920, 1080, 90),
    ]
    for name, w, h, q in splash_specs:
        fit_letterbox(logo_wordmark, w, h).save(OUT / name, "JPEG", quality=q, optimize=True, progressive=True)

    make_wordmark(logo_wordmark).save(OUT / "haku_wordmark.png", "PNG", optimize=True)

    bg_card_path = OUT_BG / "bg_00_haku_logo.jpg"
    make_bg_card(logo_wordmark).save(bg_card_path, "JPEG", quality=90, optimize=True, progressive=True)

    overlay_emitted = emit_overlay_assets(logo_wordmark)

    print(f"{'asset':<32} {'size':>10}")
    print("-" * 44)
    for name, *_ in icon_specs + splash_specs + [("haku_wordmark.png",)]:
        p = OUT / name
        print(f"{name:<32} {os.path.getsize(p):>10}")
    for name, size in overlay_emitted:
        print(f"{name:<32} {size:>10}")
    print(f"{'sidecar/backgrounds/' + bg_card_path.name:<32} {os.path.getsize(bg_card_path):>10}")


if __name__ == "__main__":
    main()
