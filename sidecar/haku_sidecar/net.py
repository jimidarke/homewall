"""LAN addressing helpers: where this host is, without hard-coding the network."""

import os
import socket
from urllib.parse import urlsplit

_FALLBACK_PROBE = "239.255.255.250"  # SSDP group: routed out of the LAN interface


def lan_ip(probe_host=None):
    """This host's address on the interface that routes to `probe_host` (default: the
    Home Assistant host from $HAKU_HA_URL). A UDP connect sends no packets."""
    targets = [probe_host or urlsplit(os.environ.get("HAKU_HA_URL", "")).hostname,
               _FALLBACK_PROBE]
    for target in targets:
        if not target:
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((target, 80))
                return s.getsockname()[0]
        except OSError:
            continue
    return "127.0.0.1"


def stream_hls_base():
    """Base URL of the HLS files: $HAKU_HLS_BASE, else the stream server (:1985) on
    the sidecar's own host ($HAKU_SIDECAR_BASE's host, else this host's LAN address)."""
    base = os.environ.get("HAKU_HLS_BASE")
    if not base:
        host = urlsplit(os.environ.get("HAKU_SIDECAR_BASE", "")).hostname or lan_ip()
        base = f"http://{host}:1985/hls"
    return base.rstrip("/")
