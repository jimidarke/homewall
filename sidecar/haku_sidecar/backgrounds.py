"""Rotating background images for the HAku sidecar.

The Roku's "smoked glass" theme composites its dark glass cards over a full-screen
photo background. The sidecar owns that photo roster: it serves a deterministic,
sorted list of image names (the Roku rotates through them on a config interval) and
serves each one as an exact w x h JPEG so a client only ever fetches a correctly-sized
image (no on-device scaling).

Two fits: `contain` (the default, what the Roku uses) letterboxes onto black; `cover`
(the kitchen tablet) fills w x h and centre-crops. `blur` softens the photo.

BG_DIR is resolved AT REQUEST TIME from HAKU_BG_DIR (default /etc/haku/backgrounds)
so tests can monkeypatch the env var without re-importing the module. A display layout
can name its own directory (`layouts.<name>.background.dir`); the routes pass that as
`d`, and `d=None` means the default directory above.

Dotfiles are never listed (a Mac leaves AppleDouble `._*` files on a share), and a file
Pillow can't decode raises Undecodable, which the route turns into a 422.
"""
import io
import os

from PIL import Image, ImageFilter, ImageOps

ALLOWED = {".jpg", ".jpeg", ".png", ".webp"}
FITS = ("contain", "cover")
BLUR_MAX = 40

_EXIF_ORIENTATION = 0x0112
_SIDEWAYS = (5, 6, 7, 8)  # orientations that swap width and height when upright

_cache = {}  # (d, name, mtime, w, h, fit, blur) -> jpeg bytes
_CACHE_MAX = 32
_listings = {}  # d -> (dir mtime, tuple of names); the dir mtime changes when files come or go


class Undecodable(Exception):
    """A listed background that Pillow can't read: corrupt, truncated, or a decompression bomb."""

    def __init__(self, name):
        super().__init__(name)
        self.name = name


def bg_dir():
    """Backgrounds directory, resolved fresh each call (env may change under tests)."""
    return os.environ.get("HAKU_BG_DIR", "/etc/haku/backgrounds")


def list_names(d=None):
    """Sorted basenames of image files in `d` (default: bg_dir()), the rotation order.

    Names starting with `.` are skipped. The scan is cached against the directory's
    mtime, so a call costs one stat until a file is added or removed. Returns [] if the
    directory is missing/unreadable.
    """
    d = bg_dir() if d is None else d
    try:
        mtime = os.stat(d).st_mtime_ns  # before the scan: a change mid-scan re-scans next call
    except OSError:
        _listings.pop(d, None)
        return []
    hit = _listings.get(d)
    if hit is not None and hit[0] == mtime:
        return list(hit[1])
    try:
        entries = os.listdir(d)
    except OSError:
        _listings.pop(d, None)
        return []
    names = tuple(sorted(
        n for n in entries
        if not n.startswith(".")
        and os.path.splitext(n)[1].lower() in ALLOWED
        and os.path.isfile(os.path.join(d, n))
    ))
    _listings[d] = (mtime, names)
    return list(names)


def _decode(im, w, h):
    """`im` as an upright RGB image, decoded no smaller than w x h where JPEG allows.

    `draft` lets the JPEG decoder skip down to a 1/2, 1/4 or 1/8 scale, which is most of
    the cost of a 12 MP photo. A sideways-stored photo (EXIF orientation 5-8) is upright
    only after the transpose, so it has to hold w x h that way round, not as stored.
    """
    if im.getexif().get(_EXIF_ORIENTATION, 1) in _SIDEWAYS:
        w, h = h, w
    im.draft("RGB", (w, h))  # no-op for PNG/WebP
    return ImageOps.exif_transpose(im).convert("RGB")


def serve(name, w=1920, h=1080, fit="contain", blur=0, d=None):
    """Return JPEG bytes of `name` rendered to exactly w x h.

    fit="contain" scales the photo to fit inside w x h and letterboxes it onto black.
    fit="cover" scales by max(w/src_w, h/src_h) and centre-crops. `blur` (clamped to
    0..BLUR_MAX) is a Gaussian radius applied to the photo after it is resized. `d` is
    the directory to read (default: bg_dir()).

    Raises ValueError for any other `fit` (the route checks `fit` first and answers 400).
    Validates `name` is a bare basename that is a known background (defends against path
    traversal); raises FileNotFoundError otherwise (the route maps that to 404). Raises
    Undecodable when Pillow can't read the file (the route maps that to 422).
    """
    if fit not in FITS:
        raise ValueError(f"unknown fit {fit!r}")
    blur = max(0, min(BLUR_MAX, blur))
    d = bg_dir() if d is None else d
    if os.path.basename(name) != name or name not in list_names(d):
        raise FileNotFoundError(name)

    path = os.path.join(d, name)
    try:
        mtime = os.stat(path).st_mtime_ns
    except OSError as e:
        raise FileNotFoundError(name) from e

    ck = (d, name, mtime, w, h, fit, blur)
    hit = _cache.get(ck)
    if hit is not None:
        return hit

    try:
        with Image.open(path) as im:
            src = _decode(im, w, h)  # loads every pixel, so all file reads happen here
    except FileNotFoundError:
        raise  # removed since the listing: still a 404
    except (OSError, ValueError, Image.DecompressionBombError) as e:
        raise Undecodable(name) from e
    if fit == "cover":
        photo = ImageOps.fit(src, (w, h), Image.LANCZOS)
    else:
        scale = min(w / src.width, h / src.height)
        photo = src.resize((max(1, int(round(src.width * scale))),
                            max(1, int(round(src.height * scale)))), Image.LANCZOS)
    if blur > 0:
        photo = photo.filter(ImageFilter.GaussianBlur(blur))

    if photo.size == (w, h):
        canvas = photo
    else:
        canvas = Image.new("RGB", (w, h), (0, 0, 0))
        canvas.paste(photo, ((w - photo.width) // 2, (h - photo.height) // 2))

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=85, progressive=True)
    body = buf.getvalue()

    if len(_cache) > _CACHE_MAX:
        _cache.clear()
    _cache[ck] = body
    return body
