#!/usr/bin/env python3
"""
Layout contract test — validates that the sidecar's `?layout=roku` config and
state carry what the 0.11+ glass home reads (HomeGroup, ModuleTile and the
*Body components).

Run:
  python3 tests/contract/layout_contract.py                # hits the live sidecar
  HAKU_FIXTURE=1 python3 tests/contract/layout_contract.py   # offline fixtures

Override the sidecar with HAKU_SIDECAR_URL. A live sidecar without the layout
(404 "unknown layout") is a WARN, not a FAIL: the channel then falls back to the
default view, but the wall won't look right until /etc/haku/dashboard.json
carries `layouts.roku`.
"""

from __future__ import annotations
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("HAKU_SIDECAR_URL", "http://192.0.2.20:1986").rstrip("/")
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
LAYOUT = "roku"
GRID_KEYS = ("cols", "rows", "cellW", "cellH", "originX", "originY", "gap")
TILE_KEYS = ("type", "col", "row", "w", "h")
DOOR_KEYS = ("id", "label", "state", "age")
MACHINE_KEYS = ("id", "label", "mode", "leds", "status", "color")
DAY_KEYS = ("label", "glyph", "hi", "lo")


class Reporter:
    def __init__(self) -> None:
        self.pass_ = self.fail = self.warn = 0

    def ok(self, msg: str) -> None:
        self.pass_ += 1
        print(f"  ok    {msg}")

    def bad(self, msg: str) -> None:
        self.fail += 1
        print(f"  FAIL  {msg}")

    def note(self, msg: str) -> None:
        self.warn += 1
        print(f"  WARN  {msg}")

    def check(self, cond: bool, msg: str) -> None:
        self.ok(msg) if cond else self.bad(msg)


def fetch(path: str):
    """(status, body) for a live GET; body is parsed JSON or None."""
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, None


def load():
    if os.environ.get("HAKU_FIXTURE"):
        print(f"(fixtures: {FIXTURES})")
        return (json.loads((FIXTURES / "config_roku.json").read_text()),
                json.loads((FIXTURES / "state_roku.json").read_text()))
    print(f"(live: {BASE})")
    st, cfg = fetch(f"/api/config?layout={LAYOUT}")
    if st == 404 and isinstance(cfg, dict) and cfg.get("error") == "unknown layout":
        return None, None
    if st != 200:
        raise SystemExit(f"config fetch failed: HTTP {st}")
    st, state = fetch(f"/api/state?layout={LAYOUT}")
    if st != 200:
        raise SystemExit(f"state fetch failed: HTTP {st}")
    return cfg, state


def card_kind(m: dict, values) -> str:
    """ModuleTile's hkCardKind (Config.brs)."""
    t = m.get("tile", {}).get("type", "")
    if m.get("kind") == "doors" and isinstance(values, dict) and values.get("doors"):
        return "doors"
    if m.get("kind") == "laundry" and isinstance(values, dict) and values.get("machines"):
        return "laundry"
    return t if t in ("agenda", "camera", "forecast") else "value"


def check_config(r: Reporter, cfg: dict) -> None:
    grid = cfg.get("grid", {})
    for k in GRID_KEYS:
        r.check(isinstance(grid.get(k), int), f"grid.{k} is an int")
    cells = set()
    for m in cfg.get("modules", []):
        mid = m.get("id", "?")
        tile = m.get("tile", {})
        if not all(isinstance(tile.get(k), (int, str)) for k in TILE_KEYS):
            r.bad(f"{mid}: tile has {', '.join(TILE_KEYS)}")
            continue
        span = {(tile["col"] + c, tile["row"] + w) for c in range(tile["w"]) for w in range(tile["h"])}
        inside = all(0 <= c < grid.get("cols", 0) and 0 <= w < grid.get("rows", 0) for c, w in span)
        r.check(inside, f"{mid}: tile inside the grid")
        r.check(not (span & cells), f"{mid}: tile overlaps no other")
        cells |= span
    r.check(len(json.dumps(cfg)) < 16 * 1024, "config fits the registry slot")


def check_state(r: Reporter, cfg: dict, state: dict) -> None:
    for m in cfg.get("modules", []):
        key = m.get("feedKey") or m.get("id")
        values = state.get(key)
        if not isinstance(values, dict):
            r.bad(f"{key}: state has a values object")
            continue
        kind = card_kind(m, values)
        if kind == "value":
            r.check(isinstance(values.get("tile", {}).get("hero"), str), f"{key}: tile.hero")
        elif kind == "doors":
            r.check(all(all(k in d for k in DOOR_KEYS) for d in values["doors"]),
                    f"{key}: doors[] carry {', '.join(DOOR_KEYS)}")
        elif kind == "laundry":
            r.check(all(all(k in mc for k in MACHINE_KEYS) for mc in values["machines"]),
                    f"{key}: machines[] carry {', '.join(MACHINE_KEYS)}")
        elif kind == "agenda":
            r.check(isinstance(values.get("items"), list), f"{key}: items[]")
        elif kind == "forecast":
            days = values.get("outlook")
            if days is None:
                r.note(f"{key}: no outlook (no forecast from HA right now?)")
            else:
                r.check(all(all(k in d for k in DAY_KEYS) for d in days), f"{key}: outlook[] carry {', '.join(DAY_KEYS)}")
        else:
            r.ok(f"{key}: {kind} card needs no values")


def main() -> int:
    r = Reporter()
    cfg, state = load()
    if cfg is None:
        r.note(f"sidecar has no `layouts.{LAYOUT}`: the channel falls back to the default view")
    else:
        check_config(r, cfg)
        check_state(r, cfg, state)
    print(f"RESULT pass={r.pass_} fail={r.fail} warn={r.warn}")
    return 1 if r.fail else 0


if __name__ == "__main__":
    sys.exit(main())
