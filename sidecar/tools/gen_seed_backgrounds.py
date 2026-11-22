#!/usr/bin/env python3
"""Generate the seed backgrounds sidecar/backgrounds/bg_01.jpg .. bg_05.jpg.

Original abstract art (soft colour fields, no photos), so the repo ships no third-party
images. The live displays rotate a photo folder synced from the NAS instead
(haku-bg-sync, see ../README.md § Backgrounds); these only fill a fresh install.
Deterministic: the same script always writes the same pixels.

Run from sidecar/: .venv/bin/python tools/gen_seed_backgrounds.py
"""
import math
from pathlib import Path

from PIL import Image, ImageFilter

W, H = 1920, 1080
OUT = Path(__file__).resolve().parents[1] / "backgrounds"

# (top-left colour, bottom-right colour, [(x, y, radius, colour), ...] glows), as fractions of W/H.
PALETTES = [
    ((18, 32, 48), (52, 86, 96), [(0.25, 0.30, 0.45, (88, 140, 150)), (0.80, 0.75, 0.40, (30, 60, 80))]),
    ((40, 28, 52), (120, 70, 80), [(0.70, 0.25, 0.50, (190, 110, 90)), (0.20, 0.80, 0.35, (70, 50, 100))]),
    ((20, 40, 30), (90, 110, 70), [(0.30, 0.65, 0.45, (130, 150, 90)), (0.85, 0.20, 0.30, (40, 80, 70))]),
    ((60, 40, 20), (30, 30, 50), [(0.50, 0.40, 0.55, (210, 140, 70)), (0.10, 0.10, 0.30, (110, 60, 40))]),
    ((24, 24, 30), (70, 80, 110), [(0.60, 0.60, 0.50, (120, 130, 180)), (0.20, 0.30, 0.30, (60, 70, 90))]),
]


def render(top_left, bottom_right, glows):
    # Low-res field, then an upscale and blur: smooth gradients with no banding steps.
    w, h = W // 8, H // 8
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = (x / w + y / h) / 2
            c = [a + (b - a) * t for a, b in zip(top_left, bottom_right)]
            for gx, gy, r, gc in glows:
                d = math.hypot(x / w - gx, (y / h - gy) * H / W)
                k = max(0.0, 1 - d / r) ** 2
                c = [v + (g - v) * k for v, g in zip(c, gc)]
            px[x, y] = tuple(int(round(v)) for v in c)
    return img.resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(12))


def main():
    for i, (tl, br, glows) in enumerate(PALETTES, start=1):
        path = OUT / f"bg_{i:02d}.jpg"
        render(tl, br, glows).save(path, "JPEG", quality=90, optimize=True)
        print(path.name)


if __name__ == "__main__":
    main()
