"""Background images: the listing, the exact-size JPEG renderer, and their routes.

The Roku asks for letterboxed `contain` images from the default dir (HAKU_BG_DIR); the
kitchen tablet asks `?layout=tablet` for `fit=cover` (optionally blurred) images from
that layout's own `background.dir`. Images here are generated with Pillow in tmp_path.
`client` lives in conftest.
"""
import io
import json
import os
import threading

from PIL import Image, ImageDraw

from haku_sidecar import backgrounds
from haku_sidecar import config as cfg_module
from haku_sidecar.store import CachedJson

import pytest

from conftest import FakeHA

SEEDS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backgrounds"))


def _write_png(path, color=(10, 20, 30), size=(8, 8)):
    Image.new("RGB", size, color).save(str(path), format="PNG")


def test_backgrounds_list_names_sorted(tmp_path, monkeypatch):
    monkeypatch.setenv("HAKU_BG_DIR", str(tmp_path))
    _write_png(tmp_path / "b_two.png")
    _write_png(tmp_path / "a_one.png")
    _write_png(tmp_path / "notes.txt")               # non-image ignored
    (tmp_path / "notes.txt").write_text("nope")
    assert backgrounds.list_names() == ["a_one.png", "b_two.png"]


def test_backgrounds_missing_dir_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HAKU_BG_DIR", str(tmp_path / "does-not-exist"))
    assert backgrounds.list_names() == []


def test_backgrounds_serve_returns_letterboxed_jpeg(tmp_path, monkeypatch):
    monkeypatch.setenv("HAKU_BG_DIR", str(tmp_path))
    _write_png(tmp_path / "a_one.png", size=(100, 40))
    body = backgrounds.serve("a_one.png", 320, 240)
    assert body[:3] == b"\xff\xd8\xff"               # JPEG magic
    import io as _io
    with Image.open(_io.BytesIO(body)) as im:
        assert im.format == "JPEG"
        assert im.size == (320, 240)                  # exact letterboxed size


def test_backgrounds_serve_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("HAKU_BG_DIR", str(tmp_path))
    _write_png(tmp_path / "a_one.png")
    with pytest.raises((FileNotFoundError, ValueError)):
        backgrounds.serve("../etc/passwd")
    with pytest.raises((FileNotFoundError, ValueError)):
        backgrounds.serve("a/b.png")
    with pytest.raises((FileNotFoundError, ValueError)):
        backgrounds.serve("missing.png")             # unknown name



def test_api_backgrounds_returns_image_list(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HAKU_BG_DIR", str(tmp_path))
    _write_png(tmp_path / "one.png")
    _write_png(tmp_path / "two.png")
    r = client.get("/api/backgrounds")
    assert r.status_code == 200
    body = r.get_json()
    assert isinstance(body["images"], list)
    names = [img["name"] for img in body["images"]]
    assert names == ["one.png", "two.png"]
    for img in body["images"]:
        assert img["url"].endswith("/api/background/" + img["name"])
    assert json.dumps(body).find("null") == -1        # no-null contract


def test_api_background_serves_and_404s(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HAKU_BG_DIR", str(tmp_path))
    _write_png(tmp_path / "one.png", size=(60, 60))
    ok = client.get("/api/background/one.png?w=200&h=150")
    assert ok.status_code == 200
    assert ok.mimetype == "image/jpeg"
    assert ok.data[:3] == b"\xff\xd8\xff"
    assert client.get("/api/background/nope.png").status_code == 404
    assert client.get("/api/background/..%2f..%2fetc%2fpasswd").status_code == 404


# --- helpers for the fit / blur / layout tests --------------------------------
def _open(body):
    return Image.open(io.BytesIO(body)).convert("RGB")


def _near(px, want, tol=40):
    return all(abs(a - b) <= tol for a, b in zip(px, want))


RED, GREEN, BLUE, BLACK = (200, 30, 30), (30, 200, 30), (30, 30, 200), (0, 0, 0)


def _use_layout_dir(monkeypatch, layout_dir, **layout):
    """Config whose `tablet` layout reads backgrounds from `layout_dir`."""
    config = {**cfg_module.DEFAULT_CONFIG, "layouts": {"tablet": {
        "modules": [], "background": {"intervalMs": 180000, "dir": str(layout_dir)}, **layout}}}
    monkeypatch.setattr(cfg_module, "_cache", CachedJson("/nonexistent/haku/dashboard.json", config))


# --- fit=cover / fit=contain --------------------------------------------------
def test_cover_exact_size_and_crop(tmp_path):
    # 400x300 -> 200x100 scales by 0.5 to 200x150, then crops 25 px off the top and
    # bottom. Green bands in the top/bottom 20 source rows must be cropped away.
    src = Image.new("RGB", (400, 300), RED)
    draw = ImageDraw.Draw(src)
    draw.rectangle((0, 0, 399, 19), fill=GREEN)
    draw.rectangle((0, 280, 399, 299), fill=GREEN)
    draw.rectangle((140, 105, 259, 194), fill=BLUE)            # centre block
    src.save(str(tmp_path / "wide.png"))

    out = _open(backgrounds.serve("wide.png", 200, 100, fit="cover", d=str(tmp_path)))
    assert out.size == (200, 100)
    assert _near(out.getpixel((100, 50)), BLUE)                # centre preserved
    assert _near(out.getpixel((100, 1)), RED)                  # top band cropped, not squashed in
    assert _near(out.getpixel((100, 98)), RED)
    assert _near(out.getpixel((1, 1)), RED)                    # no letterbox bars


def test_contain_still_letterboxes(tmp_path):
    Image.new("RGB", (100, 40), BLUE).save(str(tmp_path / "wide.png"))
    d = str(tmp_path)
    for kwargs in ({}, {"fit": "contain"}):                    # contain is the default
        out = _open(backgrounds.serve("wide.png", 320, 240, d=d, **kwargs))
        assert out.size == (320, 240)
        assert _near(out.getpixel((160, 120)), BLUE)           # photo: 320x128, centred
        assert _near(out.getpixel((160, 10)), BLACK)           # bars above and below
        assert _near(out.getpixel((160, 230)), BLACK)


def test_bad_fit_400(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HAKU_BG_DIR", str(tmp_path))
    _write_png(tmp_path / "one.png")
    with pytest.raises(ValueError):
        backgrounds.serve("one.png", 64, 64, fit="stretch", d=str(tmp_path))
    r = client.get("/api/background/one.png?w=64&h=64&fit=stretch")
    assert r.status_code == 400
    assert client.get("/api/background/one.png?w=64&h=64&fit=cover").status_code == 200
    # a missing image is still a 404, whatever the fit
    assert client.get("/api/background/nope.png?fit=cover").status_code == 404


def test_cover_via_route_is_exact_size(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HAKU_BG_DIR", str(tmp_path))
    _write_png(tmp_path / "one.png", color=RED, size=(60, 20))
    r = client.get("/api/background/one.png?w=100&h=200&fit=cover")
    assert r.status_code == 200
    out = _open(r.data)
    assert out.size == (100, 200)
    assert _near(out.getpixel((50, 3)), RED)                   # filled to the edge, no bars


# --- blur ---------------------------------------------------------------------
def _half_and_half(path):
    src = Image.new("RGB", (200, 100), RED)
    ImageDraw.Draw(src).rectangle((100, 0, 199, 99), fill=BLUE)
    src.save(str(path))


def test_blur_changes_pixels_and_keeps_size(tmp_path):
    _half_and_half(tmp_path / "split.png")
    d = str(tmp_path)
    sharp = backgrounds.serve("split.png", 200, 100, fit="cover", d=d)
    soft = backgrounds.serve("split.png", 200, 100, fit="cover", blur=8, d=d)
    assert soft != sharp
    assert _open(soft).size == (200, 100)
    # beside the red/blue edge the sharp image is still red; the blurred one has bled blue in
    sharp_blue = _open(sharp).getpixel((96, 50))[2]
    soft_blue = _open(soft).getpixel((96, 50))[2]
    assert sharp_blue < 50
    assert soft_blue > sharp_blue + 40


def test_blur_clamped_40(client, tmp_path, monkeypatch):
    _half_and_half(tmp_path / "split.png")
    d = str(tmp_path)

    def at(blur):
        return backgrounds.serve("split.png", 200, 100, fit="cover", blur=blur, d=d)

    assert at(1000) == at(40)
    assert at(40) != at(0)
    assert at(-5) == at(0)                                     # negative: no blur
    monkeypatch.setenv("HAKU_BG_DIR", str(tmp_path))
    r = client.get("/api/background/split.png?w=200&h=100&fit=cover&blur=999")
    assert r.status_code == 200 and r.data == at(40)
    # an unparsable or non-finite blur is the default (none), not an error
    for junk in ("abc", "nan", "inf"):
        r = client.get(f"/api/background/split.png?w=200&h=100&fit=cover&blur={junk}")
        assert r.status_code == 200 and r.data == at(0), junk


# --- decoding: EXIF orientation, MPO ------------------------------------------
def _exif_orientation(n):
    exif = Image.Exif()
    exif[0x0112] = n
    return exif


def test_exif_rotated_source_is_upright(tmp_path):
    # Stored landscape 400x200 with orientation 6 (rotate 90 CW to display): upright it
    # is 200x400 portrait, and the green block at the stored top-left lands top-right.
    src = Image.new("RGB", (400, 200), RED)
    ImageDraw.Draw(src).rectangle((0, 0, 79, 79), fill=GREEN)
    src.save(str(tmp_path / "drone.jpg"), quality=95, exif=_exif_orientation(6))

    out = _open(backgrounds.serve("drone.jpg", 300, 300, d=str(tmp_path)))
    assert out.size == (300, 300)
    # contain: a portrait photo is 150x300, so bars at the sides rather than the top
    assert _near(out.getpixel((20, 150)), BLACK)
    assert _near(out.getpixel((150, 5)), RED, tol=60)
    assert _near(out.getpixel((195, 30)), GREEN)               # marker moved to the top-right
    assert _near(out.getpixel((105, 30)), RED)

    portrait = _open(backgrounds.serve("drone.jpg", 100, 200, fit="cover", d=str(tmp_path)))
    assert _near(portrait.getpixel((85, 15)), GREEN)
    assert _near(portrait.getpixel((15, 15)), RED)


def test_mpo_source_is_served(tmp_path):
    # The drone's JPEGs are sometimes MPO (multi-picture) files: the main frame plus a thumbnail.
    main, thumb = Image.new("RGB", (120, 80), BLUE), Image.new("RGB", (60, 40), RED)
    main.save(str(tmp_path / "drone.jpg"), format="MPO", save_all=True, append_images=[thumb])
    with Image.open(str(tmp_path / "drone.jpg")) as im:
        assert im.format == "MPO"
    out = _open(backgrounds.serve("drone.jpg", 60, 60, fit="cover", d=str(tmp_path)))
    assert out.size == (60, 60)
    assert _near(out.getpixel((30, 30)), BLUE)


# --- listing: explicit dir, mtime cache ---------------------------------------
def test_missing_dir_empty_list(client, tmp_path, monkeypatch):
    gone = tmp_path / "unmounted"
    assert backgrounds.list_names(str(gone)) == []
    _use_layout_dir(monkeypatch, gone)
    r = client.get("/api/backgrounds?layout=tablet")
    assert (r.status_code, r.get_json()) == (200, {"images": []})


def test_listing_cache_invalidates_on_new_file(tmp_path):
    d = str(tmp_path)
    _write_png(tmp_path / "a.png")
    assert backgrounds.list_names(d) == ["a.png"]
    _write_png(tmp_path / "b.png")
    st = os.stat(d)
    os.utime(d, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))   # bump the dir mtime
    assert backgrounds.list_names(d) == ["a.png", "b.png"]
    (tmp_path / "a.png").unlink()
    os.utime(d, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))
    assert backgrounds.list_names(d) == ["b.png"]


def test_listing_is_cached_while_dir_unchanged(tmp_path, monkeypatch):
    d = str(tmp_path)
    _write_png(tmp_path / "a.png")
    calls = []
    real = os.listdir
    monkeypatch.setattr(os, "listdir", lambda p: calls.append(p) or real(p))
    first = backgrounds.list_names(d)
    first.append("mutated")                                    # callers cannot poison the cache
    assert backgrounds.list_names(d) == ["a.png"]
    assert backgrounds.list_names(d) == ["a.png"]
    assert calls == [d]                                        # one scan, two cache hits


def test_serve_cache_is_per_directory(tmp_path):
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir(), two.mkdir()
    Image.new("RGB", (64, 64), RED).save(str(one / "same.png"))
    Image.new("RGB", (64, 64), BLUE).save(str(two / "same.png"))
    a = _open(backgrounds.serve("same.png", 64, 64, d=str(one)))
    b = _open(backgrounds.serve("same.png", 64, 64, d=str(two)))
    assert _near(a.getpixel((32, 32)), RED)
    assert _near(b.getpixel((32, 32)), BLUE)


# --- routes: ?layout=, traversal, Roku default --------------------------------
def test_layout_dir_used(client, tmp_path, monkeypatch):
    default_dir, tablet_dir = tmp_path / "default", tmp_path / "tablet"
    default_dir.mkdir(), tablet_dir.mkdir()
    _write_png(default_dir / "roku.png")
    _write_png(tablet_dir / "t_one.png", size=(40, 20))
    _write_png(tablet_dir / "t_two.png")
    monkeypatch.setenv("HAKU_BG_DIR", str(default_dir))
    _use_layout_dir(monkeypatch, tablet_dir)

    r = client.get("/api/backgrounds?layout=tablet")
    assert r.status_code == 200
    images = r.get_json()["images"]
    assert [i["name"] for i in images] == ["t_one.png", "t_two.png"]
    for i in images:
        assert i["url"].endswith(f"/api/background/{i['name']}?layout=tablet")

    # the listed URL really serves from that dir (roku.png is not in it)
    ok = client.get("/api/background/t_one.png?layout=tablet&w=100&h=100&fit=cover")
    assert ok.status_code == 200 and _open(ok.data).size == (100, 100)
    assert client.get("/api/background/roku.png?layout=tablet").status_code == 404
    assert tmp_path.as_posix() not in json.dumps(client.get("/api/config?layout=tablet").get_json())


def test_unknown_layout_404(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HAKU_BG_DIR", str(tmp_path))
    _write_png(tmp_path / "one.png")
    for path in ("/api/backgrounds", "/api/background/one.png"):
        r = client.get(f"{path}?layout=nope")
        assert r.status_code == 404, path
        assert r.get_json() == {"error": "unknown layout", "layout": "nope"}, path


def test_path_traversal_404(client, tmp_path, monkeypatch):
    layout_dir = tmp_path / "tablet"
    layout_dir.mkdir()
    _write_png(layout_dir / "ok.png")
    _write_png(tmp_path / "secret.png")                        # next to the dir, not in it
    _use_layout_dir(monkeypatch, layout_dir)
    for bad in ("../secret.png", "..", "a/../secret.png", str(tmp_path / "secret.png")):
        with pytest.raises(FileNotFoundError):
            backgrounds.serve(bad, 64, 64, d=str(layout_dir))
    for url in ("/api/background/..%2fsecret.png", "/api/background/%2e%2e%2fsecret.png",
                "/api/background/..%2f..%2fetc%2fpasswd"):
        assert client.get(url + "?layout=tablet").status_code == 404, url
    assert client.get("/api/background/ok.png?layout=tablet").status_code == 200


def test_default_route_unchanged_for_roku(client, tmp_path, monkeypatch):
    roku_dir, tablet_dir = tmp_path / "roku", tmp_path / "tablet"
    roku_dir.mkdir(), tablet_dir.mkdir()
    _write_png(roku_dir / "wide.png", color=BLUE, size=(100, 40))
    _write_png(tablet_dir / "t.png")
    monkeypatch.setenv("HAKU_BG_DIR", str(roku_dir))
    _use_layout_dir(monkeypatch, tablet_dir)                   # a tablet layout exists, unused here

    body = client.get("/api/backgrounds").get_json()
    base = body["images"][0]["url"].rsplit("/api/background/", 1)[0]
    assert body == {"images": [{"name": "wide.png", "url": f"{base}/api/background/wide.png"}]}

    r = client.get("/api/background/wide.png?w=320&h=240")     # no layout, fit or blur
    assert r.status_code == 200 and r.mimetype == "image/jpeg"
    assert r.headers["Cache-Control"] == "public, max-age=3600"
    out = _open(r.data)
    assert out.size == (320, 240)
    assert _near(out.getpixel((160, 120)), BLUE)
    assert _near(out.getpixel((160, 10)), BLACK)               # still letterboxed (contain)
    assert r.data == _prebranch_letterbox(roku_dir / "wide.png", 320, 240)


def _prebranch_letterbox(path, w, h):
    """The Roku's background exactly as serve() rendered it before the tablet work (4851c46).

    Kept inline, not imported, so a change to the default route's bytes fails here.
    """
    with Image.open(str(path)) as im:
        im = im.convert("RGB")
        src_w, src_h = im.size
        scale = min(w / src_w, h / src_h)
        new_w = max(1, int(round(src_w * scale)))
        new_h = max(1, int(round(src_h * scale)))
        resized = im.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new("RGB", (w, h), (0, 0, 0))
        canvas.paste(resized, ((w - new_w) // 2, (h - new_h) // 2))
        buf = io.BytesIO()
        canvas.save(buf, format="JPEG", quality=85, progressive=True)
        return buf.getvalue()


@pytest.mark.parametrize("seed", ["bg_01.jpg", "bg_04.jpg"])
def test_roku_seed_bytes_match_pre_branch_render(client, monkeypatch, seed):
    monkeypatch.setenv("HAKU_BG_DIR", SEEDS)
    r = client.get(f"/api/background/{seed}?w=1920&h=1080")   # the Roku's BackgroundListTask size
    assert r.status_code == 200
    assert r.data == _prebranch_letterbox(os.path.join(SEEDS, seed), 1920, 1080)


# --- unreadable images, bad fit, dotfiles --------------------------------------
UNDECODABLE = {"error": "undecodable background"}


def test_corrupt_image_is_422_json(client, tmp_path, monkeypatch):
    roku_dir, nas = tmp_path / "roku", tmp_path / "nas"
    roku_dir.mkdir(), nas.mkdir()
    good = io.BytesIO()
    Image.new("RGB", (64, 48), RED).save(good, format="JPEG")
    for d in (roku_dir, nas):
        (d / "junk.jpg").write_bytes(b"not an image " * 8)
        (d / "cut.jpg").write_bytes(good.getvalue()[: len(good.getvalue()) // 2])   # truncated
    monkeypatch.setenv("HAKU_BG_DIR", str(roku_dir))
    _use_layout_dir(monkeypatch, nas)
    for name in ("junk.jpg", "cut.jpg"):
        for query in ("", "?layout=tablet&fit=cover"):
            r = client.get(f"/api/background/{name}{query}")
            assert r.status_code == 422, (name, query)
            assert r.get_json() == {**UNDECODABLE, "name": name}, (name, query)


@pytest.mark.parametrize("exc, status", [
    (OSError("broken data stream"), 422),
    (ValueError("decoder error"), 422),
    (Image.DecompressionBombError("too many pixels"), 422),
    (FileNotFoundError("removed after the listing"), 404),
])
def test_decode_errors_map_to_json(client, tmp_path, monkeypatch, exc, status):
    monkeypatch.setenv("HAKU_BG_DIR", str(tmp_path))
    _write_png(tmp_path / "one.png")

    def fail(*args, **kwargs):
        raise exc

    monkeypatch.setattr(backgrounds, "_decode", fail)
    r = client.get("/api/background/one.png")
    assert r.status_code == status
    assert r.get_json()["name"] == "one.png"


def test_decompression_bomb_is_422(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HAKU_BG_DIR", str(tmp_path))
    _write_png(tmp_path / "huge.png", size=(64, 64))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)       # 4096 px is over 2x: Pillow raises
    r = client.get("/api/background/huge.png")
    assert (r.status_code, r.get_json()) == (422, {**UNDECODABLE, "name": "huge.png"})


def test_bad_fit_400_before_reading_the_file(client, tmp_path, monkeypatch):
    nas = tmp_path / "nas"
    nas.mkdir()
    _write_png(nas / "one.png")
    monkeypatch.setenv("HAKU_BG_DIR", str(nas))
    _use_layout_dir(monkeypatch, nas)
    reads = []
    monkeypatch.setattr(backgrounds, "serve", lambda *a, **kw: reads.append(a) or b"")
    for query in ("fit=stretch", "fit=stretch&layout=tablet", "fit="):
        r = client.get(f"/api/background/one.png?{query}")
        fit = query.split("&")[0].split("=")[1]
        assert (r.status_code, r.get_json()) == (400, {"error": "unknown fit", "fit": fit}), query
    assert reads == []


def test_dotfiles_not_listed(client, tmp_path, monkeypatch):
    _write_png(tmp_path / "a.png")
    (tmp_path / "._a.jpg").write_bytes(b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X")  # AppleDouble
    _write_png(tmp_path / ".hidden.jpg")
    assert backgrounds.list_names(str(tmp_path)) == ["a.png"]
    monkeypatch.setenv("HAKU_BG_DIR", str(tmp_path))
    assert [i["name"] for i in client.get("/api/backgrounds").get_json()["images"]] == ["a.png"]
    for name in ("._a.jpg", ".hidden.jpg"):
        assert client.get(f"/api/background/{name}").status_code == 404, name


# --- a hung NAS mount must not take the Roku down -----------------------------
def _get_within(app, url, seconds):
    """GET `url` on its own thread and test client; the response, or None if still blocked."""
    out = []
    t = threading.Thread(target=lambda: out.append(app.test_client().get(url)), daemon=True)
    t.start()
    t.join(seconds)
    return out[0] if out else None


def test_hung_layout_dir_caps_requests_and_spares_roku(client, tmp_path, monkeypatch):
    # nserver mounts the NAS `hard`: when it drops, stat() blocks in the kernel and never
    # returns. Layout background requests get two slots; a third is a fast 503 that never
    # touches the mount, and the Roku's default routes keep answering.
    from haku_sidecar import app as app_module
    monkeypatch.setattr(app_module, "ha", FakeHA())
    roku_dir, nas = tmp_path / "roku", tmp_path / "nas"
    roku_dir.mkdir(), nas.mkdir()
    _write_png(roku_dir / "r.png")
    _write_png(nas / "n.png")
    monkeypatch.setenv("HAKU_BG_DIR", str(roku_dir))
    _use_layout_dir(monkeypatch, nas)

    nas_back, stuck = threading.Event(), threading.Semaphore(0)
    real_stat = os.stat

    def hung_stat(path, *args, **kwargs):
        if isinstance(path, str) and path.startswith(str(nas)):
            stuck.release()
            nas_back.wait(10)             # a real hung mount never returns; 10 s bounds a failing test
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", hung_stat)
    app, results, threads = client.application, {}, []

    def fetch(key, url):
        results[key] = app.test_client().get(url)

    try:
        for key, url in (("list", "/api/backgrounds?layout=tablet"),
                         ("image", "/api/background/n.png?layout=tablet&fit=cover")):
            threads.append(threading.Thread(target=fetch, args=(key, url), daemon=True))
            threads[-1].start()
        assert stuck.acquire(timeout=5) and stuck.acquire(timeout=5)   # both blocked in stat()

        for url in ("/api/backgrounds?layout=tablet", "/api/background/n.png?layout=tablet"):
            r = _get_within(app, url, 2)
            assert r is not None, f"{url} blocked on the hung mount"
            assert (r.status_code, r.get_json()) == (503, {"error": "backgrounds busy"}), url
        assert not stuck.acquire(blocking=False)                       # the 503s never touched it

        for url in ("/api/config", "/api/state", "/api/backgrounds", "/api/background/r.png?w=64&h=64"):
            r = _get_within(app, url, 2)
            assert r is not None and r.status_code == 200, url
    finally:
        nas_back.set()
        for t in threads:
            t.join(5)

    assert results["list"].status_code == 200 and results["image"].status_code == 200
    assert client.get("/api/backgrounds?layout=tablet").status_code == 200   # slots are free again


def test_layout_bg_slots_released_on_every_outcome(client, tmp_path, monkeypatch):
    from haku_sidecar import app as app_module
    nas = tmp_path / "nas"
    nas.mkdir()
    _write_png(nas / "ok.png")
    (nas / "bad.jpg").write_bytes(b"junk")
    _use_layout_dir(monkeypatch, nas)
    for _ in range(3):                                         # more requests than slots
        for url, status in (("/api/backgrounds?layout=tablet", 200),
                            ("/api/background/ok.png?layout=tablet", 200),
                            ("/api/background/nope.png?layout=tablet", 404),
                            ("/api/background/bad.jpg?layout=tablet", 422),
                            ("/api/background/ok.png?layout=tablet&fit=stretch", 400)):
            assert client.get(url).status_code == status, url

    def boom(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(backgrounds, "serve", boom)
    with pytest.raises(RuntimeError):                          # TESTING propagates the 500
        client.get("/api/background/ok.png?layout=tablet")
    slots = app_module._LAYOUT_BG_SLOTS
    assert slots.acquire(blocking=False) and slots.acquire(blocking=False)
    slots.release(), slots.release()
