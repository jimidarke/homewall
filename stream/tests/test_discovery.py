"""Unit tests for haku-discovery.py: the capability document, SSDP and the HTTP listener.

Run from the repo root: python3 -m pytest stream/tests -q (stdlib + pytest only).
"""

import importlib.util
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "haku-discovery.py"
_spec = importlib.util.spec_from_file_location("haku_discovery", _SRC)
hd = importlib.util.module_from_spec(_spec)
sys.modules["haku_discovery"] = hd  # dataclasses resolve annotations through sys.modules
_spec.loader.exec_module(hd)

HOST = "192.0.2.20"


@pytest.fixture
def settings(tmp_path):
    return hd.Settings(host=HOST, bind_ip="127.0.0.1", http_port=1985, hls_dir=str(tmp_path),
                       sidecar_base=f"http://{HOST}:1986")


def test_settings_from_env_defaults_the_sidecar_to_the_advertised_host():
    s = hd.Settings.from_env({"HAKU_DISCOVERY_HOST": HOST})
    assert (s.host, s.bind_ip, s.http_port) == (HOST, HOST, 1985)
    assert s.sidecar_base == f"http://{HOST}:1986"
    assert s.location == f"http://{HOST}:1985/discovery.json"
    assert s.usn == "uuid:haku-192-0-2-20::urn:haku:service:dashboard:1"


def test_settings_without_a_host_detects_one():
    s = hd.Settings.from_env({})
    assert s.host.count(".") == 3


def test_payload_matches_schema_2(settings):
    doc = hd.build_payload(["mosaic", "front", "unknown_cam"], settings)
    assert doc["service"] == "haku" and doc["schemaVersion"] == 2 and doc["host"] == HOST
    assert doc["sidecar"] == {"base": f"http://{HOST}:1986", "config": "/api/config",
                              "state": "/api/state"}
    front = doc["streams"]["front"]
    assert front["hls"] == f"http://{HOST}:1985/hls/front.m3u8"
    assert front["rtsp"] == f"rtsp://{HOST}:8554/front"
    assert front["mjpeg"].endswith("/api/stream.mjpeg?src=front")
    assert front["snapshot"].endswith("/api/frame.jpeg?src=front")
    assert front["displayName"] == "Front Door"
    assert "displayName" not in doc["streams"]["unknown_cam"]  # no metadata, URLs only


def test_catalog_falls_back_to_the_static_roster(settings):
    cat = hd.Catalog(settings, list_streams=lambda _url: None)
    doc = cat.rebuild()
    assert set(doc["streams"]) == set(hd.STREAM_METADATA)
    assert json.loads(cat.body()) == doc


def test_catalog_lists_what_go2rtc_serves(settings):
    cat = hd.Catalog(settings, list_streams=lambda _url: ["mosaic", "side"])
    assert set(cat.rebuild()["streams"]) == {"mosaic", "side"}


@pytest.mark.parametrize("st, answered", [
    ("urn:haku:service:dashboard:1", True),
    ("ssdp:all", True),
    ("urn:dial-multiscreen-org:service:dial:1", False),
])
def test_ssdp_answers_only_our_search(settings, st, answered):
    msg = (f'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\n'
           f"MX: 2\r\nST: {st}\r\n\r\n").encode()
    reply = hd.ssdp_reply(hd.parse_msearch(msg), settings)
    if not answered:
        assert reply is None
        return
    text = reply.decode()
    assert text.startswith("HTTP/1.1 200 OK\r\n") and text.endswith("\r\n\r\n")
    assert f"LOCATION: http://{HOST}:1985/discovery.json\r\n" in text
    assert "ST: urn:haku:service:dashboard:1\r\n" in text


def test_notify_packets_are_ignored():
    assert hd.parse_msearch(b"NOTIFY * HTTP/1.1\r\nNT: upnp:rootdevice\r\n\r\n") is None


@pytest.fixture
def server(settings, tmp_path):
    (tmp_path / "front.m3u8").write_text("#EXTM3U\n")
    (tmp_path / "front_seg_00001.ts").write_bytes(b"\x47" * 188)
    cat = hd.Catalog(settings, list_streams=lambda _url: ["front"])
    cat.rebuild()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), hd.make_handler(cat, settings))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, b""


def test_http_serves_the_document(server):
    status, headers, body = _get(server + "/discovery.json")
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    assert list(json.loads(body)["streams"]) == ["front"]


def test_http_serves_playlists_and_segments(server):
    status, headers, body = _get(server + "/hls/front.m3u8?_=1")
    assert (status, body) == (200, b"#EXTM3U\n")
    assert headers["Content-Type"] == "application/vnd.apple.mpegurl"
    assert headers["Cache-Control"] == "no-cache, no-store"
    status, headers, body = _get(server + "/hls/front_seg_00001.ts")
    assert (status, len(body), headers["Content-Type"]) == (200, 188, "video/mp2t")


@pytest.mark.parametrize("path, status", [
    ("/hls/missing.m3u8", 404),
    ("/hls/..%2f..%2fetc%2fpasswd", 403),
    ("/hls/../front.m3u8", 403),
    ("/hls/notes.txt", 403),
    ("/elsewhere", 404),
])
def test_http_refuses_everything_else(server, path, status):
    assert _get(server + path)[0] == status
