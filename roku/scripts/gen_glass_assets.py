#!/usr/bin/env python3
"""The home screen's glass pieces (the tablet's v3 GlassCard, without the frost).

Roku's Rectangle has no corner radius, so every rounded shape is a PNG: the card
outline pieces are 9-patches (Android convention: a 1 px border whose opaque black
pixels on the top and left edges mark the stretchable columns and rows) that one
Poster stretches to any tile size. Shapes are drawn 4x and downsampled, so edges are
anti-aliased. Pieces that the channel tints (fill, rim, chip, dot, glow) are pure
white; Poster.blendColor colours them and Poster.opacity sets their strength, so the
palette lives in Config.brs, not here.

Writes roku/images/glass/:
  fill.9.png    card body, r=RADIUS (tinted night)
  edge.9.png    1 px ink rim at 8% + the top highlight (12% fading to 0 by y=RADIUS); untinted
  rim.9.png     2 px ring for the lit state (tinted accent or coral)
  seg.9.png     a laundry LED segment, r=SEG_R (tinted the bar's colour)
  chip.png      the glyph chip, CHIP px, r=CHIP_R
  dot.png       a disc (status dot, agenda marks, calendar dots)
  glow.png      the lit card's radial glow, pre-masked to a 1x1 card with the chip at its centre
  scrim.png     4x1080 vertical night gradient stretched over the photo

Run: python3 roku/scripts/gen_glass_assets.py   (Pillow only; any Python with Pillow)
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "roku" / "images" / "glass"

SS = 4                       # supersampling factor
RADIUS = 28                  # card corner (tablet 20 dp x 1.375)
CHIP, CHIP_R = 60, 18        # glyph chip (tablet 48 dp, r 14)
SEG_R = 4                    # LED segment corner (tablet 3 dp)
INK = (0xFA, 0xF6, 0xEE)     # Config.brs HK_INK
NIGHT = (0x0C, 0x12, 0x11)   # Config.brs HK_NIGHT
CELL = (286, 292)            # a 1x1 tile in layouts.roku (glow is drawn for this size)
PAD = 20                     # card inset; the chip sits at (w - PAD - CHIP, PAD)


def rounded_mask(w, h, r, inset=0.0):
    """An L-mode anti-aliased rounded-rect mask of w x h, shrunk by `inset` px."""
    big = Image.new("L", (w * SS, h * SS), 0)
    i = round(inset * SS)
    ImageDraw.Draw(big).rounded_rectangle(
        (i, i, w * SS - 1 - i, h * SS - 1 - i), radius=max(0, (r - inset) * SS), fill=255)
    return big.resize((w, h), Image.LANCZOS)


def ring_mask(w, h, r, width):
    """The outline band `width` px thick just inside a w x h rounded rect."""
    return ImageChops.subtract(rounded_mask(w, h, r), rounded_mask(w, h, r, inset=width))


def nine_patch(img, r=RADIUS):
    """Wrap `img` in the 9-patch border: stretch the middle columns and rows past `r`."""
    w, h = img.size
    out = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0))
    out.paste(img, (1, 1))
    black = (0, 0, 0, 255)
    for x in range(1 + r, 1 + w - r):
        out.putpixel((x, 0), black)
    for y in range(1 + r, 1 + h - r):
        out.putpixel((0, y), black)
    return out


def solid(mask, rgb=(255, 255, 255), alpha=1.0):
    img = Image.new("RGBA", mask.size, rgb + (0,))
    img.putalpha(mask.point(lambda a: round(a * alpha)))
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    side = 2 * RADIUS + 2        # two stretchable pixels between the corners

    nine_patch(solid(rounded_mask(side, side, RADIUS))).save(OUT / "fill.9.png")
    nine_patch(solid(ring_mask(side, side, RADIUS, 2))).save(OUT / "rim.9.png")

    # Edge: the 8% ink rim everywhere, lifted to 12% along the top and fading back to the
    # rim by y = RADIUS (the tablet's top highlight). It lives in the fixed top rows, so
    # stretching never smears it.
    ring = ring_mask(side, side, RADIUS, 1)
    lift = Image.new("L", (side, side), 0)
    for y in range(RADIUS):
        a = 0.08 + 0.04 * (1 - y / RADIUS)
        lift.paste(round(255 * a), (0, y, side, y + 1))
    base = Image.new("L", (side, side), round(255 * 0.08))
    for y in range(RADIUS):
        base.paste(lift.getpixel((0, y)), (0, y, side, y + 1))
    edge_alpha = ImageChops.multiply(ring, base)
    edge = Image.new("RGBA", (side, side), INK + (0,))
    edge.putalpha(edge_alpha)
    nine_patch(edge).save(OUT / "edge.9.png")

    seg = 2 * SEG_R + 2
    nine_patch(solid(rounded_mask(seg, seg, SEG_R)), SEG_R).save(OUT / "seg.9.png")

    solid(rounded_mask(CHIP, CHIP, CHIP_R)).save(OUT / "chip.png")

    big = Image.new("L", (32 * SS, 32 * SS), 0)
    ImageDraw.Draw(big).ellipse((0, 0, 32 * SS - 1, 32 * SS - 1), fill=255)
    solid(big.resize((32, 32), Image.LANCZOS)).save(OUT / "dot.png")

    # Glow: radial from the chip centre, radius 0.7 x card width, smooth falloff, clipped
    # to the card. Its strength is Poster.opacity (0.18 lit).
    w, h = CELL
    cx, cy, rad = w - PAD - CHIP / 2, PAD + CHIP / 2, 0.7 * w
    glow = Image.new("L", (w, h), 0)
    px = glow.load()
    for y in range(h):
        for x in range(w):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / rad
            px[x, y] = round(255 * max(0.0, 1 - d) ** 2)
    glow = ImageChops.multiply(glow, rounded_mask(w, h, RADIUS))
    solid(glow).save(OUT / "glow.png")

    # Scrim: night at 0.60 under the header, easing to 0.35 at the bottom.
    scrim = Image.new("RGBA", (4, 1080), NIGHT + (0,))
    for y in range(1080):
        a = 0.60 - 0.25 * (y / 1079) ** 0.8
        scrim.paste(NIGHT + (round(255 * a),), (0, y, 4, y + 1))
    scrim.save(OUT / "scrim.png")
    print(f"glass assets -> {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
