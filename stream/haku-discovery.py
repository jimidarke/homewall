#!/usr/bin/env python3
"""haku-discovery: tells HAku clients where the streams and the sidecar are.

One stdlib-only process with two listeners:

* **SSDP** (UDP multicast 239.255.255.250:1900). A client sends an M-SEARCH for
  ``urn:haku:service:dashboard:1``; we answer with a ``LOCATION`` header that points
  at the HTTP listener below. Clients never hard-code the media host's address.
* **HTTP** (``:1985`` by default)::

      GET /discovery.json   the capability document (schema below)
      GET /hls/<file>       playlists and segments the haku-hls units write to tmpfs

The capability document is rebuilt every ``HAKU_DISCOVERY_REFRESH`` seconds from
go2rtc's ``/api/streams``, so a stream added to ``go2rtc.yaml`` shows up without a
restart. If go2rtc is down, the static ``STREAM_METADATA`` roster stands in.

Schema 2 (the Roku's ``discovery_contract.py`` pins it)::

    {"service": "haku", "version": "...", "schemaVersion": 2, "host": "<ip>",
     "sidecar": {"base": "http://<ip>:1986", "config": "/api/config", "state": "/api/state"},
     "streams": {"<name>": {"hls", "rtsp", "mjpeg", "snapshot", ...metadata}}}

Configuration is environment only (see ``Settings.from_env``). ``HAKU_DISCOVERY_HOST``
is optional: without it the address of the interface that routes to the SSDP group
is advertised. Deployed as ``haku-discovery.service``; see ``README.md`` § Deploy.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import socket
import struct
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Iterable, Mapping

SERVICE_TYPE = "urn:haku:service:dashboard:1"
SCHEMA_VERSION = 2  # 2 added the `sidecar` block; the streams block is unchanged from 1
SERVICE_VERSION = "1.1.0"

SSDP_GROUP = "239.255.255.250"
SSDP_PORT = 1900

log = logging.getLogger("haku-discovery")

# Per-stream facts that go2rtc can't report (they mirror the encode settings in
# go2rtc.yaml). Keys must match go2rtc's stream names.
STREAM_METADATA: dict[str, dict] = {
    "mosaic": {
        "displayName": "NVR 4-up Mosaic",
        "codec": "h264", "profile": "main", "level": "4.0",
        "resolution": "1920x1080", "framerate": 20, "bitrate_kbps": 2500,
        "audio": False,
    },
    "front": {
        "displayName": "Front Door",
        "vendor": "Genbolt", "ptz": True,
        "codec": "h264", "resolution": "1280x720", "audio": False,
        "note": "PTZ lens (/21) transcoded HEVC -> H.264 720p for Roku compat.",
    },
    "front_steps": {
        "displayName": "Front Steps",
        "vendor": "Genbolt", "ptz": False,
        "codec": "h264", "resolution": "1280x720", "audio": False,
        "note": "Fixed lens (/11) on the front steps, transcoded HEVC -> H.264 720p. "
                "Shown in the Rokus' home square on front motion (homeCam=front_steps).",
    },
    "yard": {
        "displayName": "Yard",
        "vendor": "Reolink", "ptz": True,
        "codec": "h264", "resolution": "640x480", "audio": True,
        "note": "Sub-stream used for Roku H.264 compat; main is HEVC 4K.",
    },
    "side": {
        "displayName": "Side Gate",
        "vendor": "Amcrest", "ptz": True,
        "codec": "h264", "resolution": "1920x1080", "audio": True,
    },
    # "backyard" is retired while its camera is offline (go2rtc.yaml has it commented out).
}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def detect_lan_ip() -> str:
    """The local address the kernel would use to reach the SSDP group (no packet is sent)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((SSDP_GROUP, SSDP_PORT))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


@dataclass(frozen=True)
class Settings:
    host: str                 # address advertised to clients (LOCATION, stream URLs)
    bind_ip: str              # address the HTTP listener binds and SSDP replies leave from
    http_port: int = 1985
    go2rtc_api: str = "http://127.0.0.1:1984/api/streams"
    refresh_s: int = 60
    hls_dir: str = "/run/haku-hls"
    sidecar_base: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        host = env.get("HAKU_DISCOVERY_HOST") or detect_lan_ip()
        return cls(
            host=host,
            bind_ip=env.get("HAKU_DISCOVERY_BIND_IP") or host,
            http_port=int(env.get("HAKU_DISCOVERY_HTTP_PORT", "1985")),
            go2rtc_api=env.get("HAKU_GO2RTC_API", cls.go2rtc_api),
            refresh_s=int(env.get("HAKU_DISCOVERY_REFRESH", "60")),
            hls_dir=env.get("HAKU_HLS_DIR", cls.hls_dir),
            sidecar_base=env.get("HAKU_SIDECAR_BASE") or f"http://{host}:1986",
        )

    @property
    def location(self) -> str:
        return f"http://{self.host}:{self.http_port}/discovery.json"

    @property
    def usn(self) -> str:
        return f"uuid:haku-{self.host.replace('.', '-')}::{SERVICE_TYPE}"


# ---------------------------------------------------------------------------
# Capability document
# ---------------------------------------------------------------------------

def stream_entry(name: str, s: Settings) -> dict:
    """URLs for one stream. HLS comes from our own listener: go2rtc's built-in HLS keeps
    about a second of media, too little for a Roku (see AlexxIT/go2rtc#1699)."""
    entry = dict(STREAM_METADATA.get(name, {}))
    entry.update({
        "rtsp": f"rtsp://{s.host}:8554/{name}",
        "hls": f"http://{s.host}:{s.http_port}/hls/{name}.m3u8",
        "mjpeg": f"http://{s.host}:1984/api/stream.mjpeg?src={name}",
        "snapshot": f"http://{s.host}:1984/api/frame.jpeg?src={name}",
    })
    return entry


def build_payload(stream_names: Iterable[str], s: Settings) -> dict:
    return {
        "service": "haku",
        "version": SERVICE_VERSION,
        "schemaVersion": SCHEMA_VERSION,
        "host": s.host,
        "sidecar": {"base": s.sidecar_base, "config": "/api/config", "state": "/api/state"},
        "streams": {name: stream_entry(name, s) for name in stream_names},
    }


def go2rtc_stream_names(api_url: str, timeout: float = 2.0) -> list[str] | None:
    """Stream names go2rtc is serving, or None when its API can't be read."""
    try:
        with urllib.request.urlopen(api_url, timeout=timeout) as resp:
            return list(json.load(resp))
    except (OSError, ValueError) as exc:
        log.warning("go2rtc API unreachable (%s); advertising the static roster", exc)
        return None


class Catalog:
    """The current capability document, rebuilt on a timer and read by every HTTP thread."""

    def __init__(self, settings: Settings,
                 list_streams: Callable[[str], list[str] | None] = go2rtc_stream_names):
        self._settings = settings
        self._list_streams = list_streams
        self._lock = threading.Lock()
        self._body = b"{}"

    def rebuild(self) -> dict:
        names = self._list_streams(self._settings.go2rtc_api)
        if names is None:
            names = list(STREAM_METADATA)
        doc = build_payload(names, self._settings)
        body = json.dumps(doc, indent=2).encode("utf-8")
        with self._lock:
            self._body = body
        return doc

    def body(self) -> bytes:
        with self._lock:
            return self._body

    def keep_fresh(self) -> None:
        while True:
            time.sleep(self._settings.refresh_s)
            try:
                self.rebuild()
            except Exception:  # keep serving the last good document
                log.exception("catalog rebuild failed")


# ---------------------------------------------------------------------------
# SSDP
# ---------------------------------------------------------------------------

def parse_msearch(datagram: bytes) -> dict[str, str] | None:
    """Headers of an M-SEARCH request (lower-cased names), or None for anything else."""
    text = datagram.decode("utf-8", errors="replace")
    lines = text.split("\r\n") if "\r\n" in text else text.split("\n")
    if not lines or not lines[0].upper().startswith("M-SEARCH"):
        return None
    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if sep:
            headers[name.strip().lower()] = value.strip()
    return headers


def ssdp_reply(headers: Mapping[str, str], s: Settings) -> bytes | None:
    """The unicast answer to a search for our service type (or ssdp:all), else None."""
    if headers.get("st") not in (SERVICE_TYPE, "ssdp:all"):
        return None
    fields = [
        "HTTP/1.1 200 OK",
        "CACHE-CONTROL: max-age=900",
        f"DATE: {formatdate(usegmt=True)}",
        "EXT:",
        f"LOCATION: {s.location}",
        f"SERVER: {sys.platform}/UPnP/1.1 HAku/{SERVICE_VERSION}",
        f"ST: {SERVICE_TYPE}",
        f"USN: {s.usn}",
    ]
    return ("\r\n".join(fields) + "\r\n\r\n").encode("ascii")


def open_ssdp_socket(s: Settings) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    # Linux only hands multicast datagrams to a socket bound to the wildcard address;
    # the group membership below is what ties us to the LAN interface.
    sock.bind(("", SSDP_PORT))
    group = socket.inet_aton(SSDP_GROUP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                        group + socket.inet_aton(s.bind_ip))
    except OSError as exc:
        log.warning("joining %s on %s failed (%s); joining on the default interface",
                    SSDP_GROUP, s.bind_ip, exc)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                        struct.pack("4sl", group, socket.INADDR_ANY))
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(s.bind_ip))
    return sock


def answer_searches(sock: socket.socket, s: Settings) -> None:
    log.info("SSDP: answering %s from %s", SERVICE_TYPE, s.bind_ip)
    while True:
        datagram, sender = sock.recvfrom(4096)
        headers = parse_msearch(datagram)
        reply = ssdp_reply(headers, s) if headers is not None else None
        if reply is None:
            continue
        sock.sendto(reply, sender)
        log.info("SSDP: answered %s:%d", *sender)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

HLS_NAME = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*\.(m3u8|ts|m4s|mp4)$")
HLS_TYPES = {
    "m3u8": "application/vnd.apple.mpegurl",
    "ts": "video/mp2t",
    "m4s": "video/iso.segment",
    "mp4": "video/mp4",
}


def make_handler(catalog: Catalog, s: Settings) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = f"HAku/{SERVICE_VERSION}"

        def do_GET(self) -> None:  # noqa: N802 (http.server naming)
            path = self.path.split("?", 1)[0]
            try:
                if path.rstrip("/") == "/discovery.json":
                    self._send(200, "application/json; charset=utf-8", catalog.body(),
                               cache="no-cache, must-revalidate")
                elif path.startswith("/hls/"):
                    self._send_hls(path[len("/hls/"):])
                else:
                    self.send_error(404)
            except (BrokenPipeError, ConnectionResetError):
                # Players routinely hang up mid-transfer between segments.
                self.close_connection = True

        def _send(self, status: int, ctype: str, body: bytes, cache: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _send_hls(self, name: str) -> None:
            match = HLS_NAME.match(name)
            if not match:
                self.send_error(403)
                return
            full = os.path.join(s.hls_dir, name)
            try:
                f = open(full, "rb")
            except FileNotFoundError:
                self.send_error(404)
                return
            with f:
                size = os.fstat(f.fileno()).st_size
                ext = match.group(1)
                self.send_response(200)
                self.send_header("Content-Type", HLS_TYPES[ext])
                self.send_header("Content-Length", str(size))
                # The playlist changes every segment; segments never change.
                self.send_header("Cache-Control",
                                 "no-cache, no-store" if ext == "m3u8" else "max-age=10")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                shutil.copyfileobj(f, self.wfile, 64 * 1024)

        def log_message(self, fmt: str, *args) -> None:
            log.debug("http %s %s", self.address_string(), fmt % args)

    return Handler


def serve_http(catalog: Catalog, s: Settings) -> None:
    # If the listener can't run, SSDP would keep pointing clients at a dead URL:
    # take the whole process down and let systemd restart it.
    try:
        server = ThreadingHTTPServer((s.bind_ip, s.http_port), make_handler(catalog, s))
        log.info("HTTP: %s", s.location)
        server.serve_forever()
    except BaseException:
        log.exception("HTTP listener stopped; exiting for a restart")
    os._exit(1)


def main() -> int:
    logging.basicConfig(level=os.environ.get("HAKU_DISCOVERY_LOG", "INFO"),
                        format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    catalog = Catalog(settings)
    doc = catalog.rebuild()
    log.info("advertising %s with streams %s", settings.host, ", ".join(doc["streams"]))
    threading.Thread(target=catalog.keep_fresh, name="catalog", daemon=True).start()
    threading.Thread(target=serve_http, args=(catalog, settings), name="http", daemon=True).start()
    try:
        answer_searches(open_ssdp_socket(settings), settings)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
