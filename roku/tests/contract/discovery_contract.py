#!/usr/bin/env python3
"""
Discovery contract test — validates that what the deployed
`haku-discovery.service` returns matches what the Roku channel's
DiscoveryTask + LiveGroup + GridGroup expect.

Catches server↔channel drift before sideload.

Run:
  python3 tests/contract/discovery_contract.py                # hits live server
  HAKU_FIXTURE=1 python3 tests/contract/discovery_contract.py   # offline fixture

Override the URL with HAKU_DISCOVERY_URL.
"""

from __future__ import annotations
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

DEFAULT_URL = os.environ.get(
    "HAKU_DISCOVERY_URL", "http://192.0.2.20:1985/discovery.json"
)
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "discovery.json"

EXPECTED_SCHEMA_VERSION = 2
EXPECTED_KEYS_PER_STREAM = ("hls", "rtsp", "displayName")
EXPECTED_STREAMS = ("mosaic", "front", "front_steps", "yard", "side")
# v2 adds the sidecar pointer (haku-sidecar: module JSON + rendered PNG cards).
EXPECTED_SIDECAR_KEYS = ("base", "config", "state")


class Reporter:
    def __init__(self) -> None:
        self.pass_ = 0
        self.fail = 0
        self.warn = 0

    def ok(self, msg: str) -> None:
        print(f"  ok    {msg}")
        self.pass_ += 1

    def fail_(self, msg: str) -> None:
        print(f"  FAIL  {msg}")
        self.fail += 1

    def warn_(self, msg: str) -> None:
        print(f"  warn  {msg}")
        self.warn += 1


def fetch(url: str) -> dict:
    if os.environ.get("HAKU_FIXTURE") == "1":
        print(f"== using fixture {FIXTURE} ==")
        return json.loads(FIXTURE.read_text())
    print(f"== fetching {url} ==")
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  warn  live fetch failed ({e}); falling back to fixture")
        return json.loads(FIXTURE.read_text())


def probe(url: str, timeout: float = 3.0) -> tuple[int, str]:
    """GET first 256 bytes — server's stdlib BaseHTTPRequestHandler doesn't
    handle HEAD by default. We just want status + a sanity-check on body."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            r.read(256)
            return r.status, ""
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def main() -> int:
    r = Reporter()

    payload = fetch(DEFAULT_URL)

    # --- top-level shape ---
    print("== top-level ==")
    if payload.get("schemaVersion") == EXPECTED_SCHEMA_VERSION:
        r.ok(f"schemaVersion = {EXPECTED_SCHEMA_VERSION}")
    else:
        r.fail_(
            f"schemaVersion got={payload.get('schemaVersion')!r} want={EXPECTED_SCHEMA_VERSION}"
        )

    for k in ("service", "host", "streams", "sidecar"):
        if k in payload:
            r.ok(f"top-level key '{k}' present")
        else:
            r.fail_(f"top-level key '{k}' missing")

    # --- sidecar pointer (schema v2) ---
    print("== sidecar block ==")
    sidecar = payload.get("sidecar")
    if not isinstance(sidecar, dict):
        r.fail_("sidecar block missing or wrong type")
    else:
        for k in EXPECTED_SIDECAR_KEYS:
            if sidecar.get(k):
                r.ok(f"sidecar.{k} present")
            else:
                r.fail_(f"sidecar.{k} missing")
        base = sidecar.get("base", "")
        if base.startswith("http"):
            r.ok(f"sidecar.base is a URL ({base})")
        else:
            r.fail_(f"sidecar.base not a URL: {base!r}")

    streams = payload.get("streams", {})
    if not isinstance(streams, dict) or not streams:
        r.fail_("streams object is empty or wrong type")
        print(f"\nRESULT pass={r.pass_} fail={r.fail} warn={r.warn}")
        return 1 if r.fail else 0

    # --- mosaic must always be present (Phase 1, currently deployed) ---
    print("== mosaic stream ==")
    if "mosaic" in streams:
        r.ok("streams.mosaic present")
        mosaic = streams["mosaic"]
        for k in EXPECTED_KEYS_PER_STREAM:
            if k in mosaic:
                r.ok(f"mosaic.{k} present")
            else:
                r.fail_(f"mosaic.{k} missing")
        # HLS must be reachable
        hls = mosaic.get("hls")
        if hls and os.environ.get("HAKU_FIXTURE") != "1":
            status, err = probe(hls)
            if status == 200:
                r.ok(f"mosaic.hls reachable (GET 200) {hls}")
            else:
                r.fail_(f"mosaic.hls fetch failed status={status} err={err} url={hls}")
        elif hls:
            r.warn_("skipping HLS reachability probe in fixture mode")
    else:
        r.fail_("streams.mosaic missing — channel cannot fall back to mosaic")

    # --- all expected streams must be present (Phase 2 deployed 2026-05-08) ---
    print("== full stream roster (mosaic + per-cam) ==")
    for cam in EXPECTED_STREAMS:
        if cam in streams:
            r.ok(f"streams.{cam} present")
        else:
            r.fail_(f"streams.{cam} MISSING — channel will fall back to mosaic")

    # --- per-stream key consistency + codec sanity ---
    print("== shape consistency across streams ==")
    for name, body in streams.items():
        for k in EXPECTED_KEYS_PER_STREAM:
            if k not in body:
                r.fail_(f"streams.{name}.{k} missing")
        codec = body.get("codec")
        if codec is None:
            r.warn_(f"streams.{name} has no codec metadata")
        elif codec.lower() != "h264":
            r.fail_(
                f"streams.{name} codec={codec!r} — Roku Video node won't reliably decode anything but H.264 over HLS"
            )

    # --- HLS reachability for every stream (live mode only) ---
    if os.environ.get("HAKU_FIXTURE") != "1":
        print("== HLS reachability for every stream ==")
        for name, body in streams.items():
            hls = body.get("hls")
            if not hls:
                continue
            status, err = probe(hls)
            if status == 200:
                r.ok(f"{name}.hls reachable (200)")
            else:
                r.fail_(f"{name}.hls fetch failed status={status} err={err}")

    print(f"\nRESULT pass={r.pass_} fail={r.fail} warn={r.warn}")
    return 1 if r.fail else 0


if __name__ == "__main__":
    sys.exit(main())
