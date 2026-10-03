"""Cameras module: minimal glance feed for the home-page camera tile.

The camera tile's thumbnail comes from go2rtc's JPEG snapshot endpoint (no sidecar
data, no decoder cost) and its drill-down delegates to the existing LiveGroup, so the
sidecar only needs to surface roster + optional motion state. Motion is read from
HA occupancy binary_sensors when the descriptor maps them (entities.motion is a
{stream: binary_sensor_entity} map); absent → the tile simply shows the thumbnail.
"""
import time


def _age_s(iso):
    # last_changed ISO -> seconds since, best-effort.
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return max(0, int(time.time() - dt.timestamp()))
    except Exception:
        return None


def values(ha, descriptor):
    streams = descriptor.get("streams", [])
    motion_map = descriptor.get("entities", {}).get("motion", {}) or {}

    out = {
        "streams": list(streams),
        "count": len(streams),
        "thumbCam": descriptor.get("tile", {}).get("thumbCam"),
    }
    if motion_map:
        cams = {}
        for stream, ent in motion_map.items():
            st = ha.get_state(ent)
            if not st:
                continue
            active = st.get("state") == "on"
            cams[stream] = {
                "motion": active,
                "motion_age_s": _age_s(st.get("last_changed", "")),
            }
        if cams:
            out["cams"] = cams
    return out


CARDS = {}
