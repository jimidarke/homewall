"""history.py: statistics and state history -> chart runs, ticks, scales, spans, labels.

All pure. Times are pinned to America/Edmonton, so the day boundaries are the house's.
The DST cases use the 2025 fall-back (Nov 2, a 25-hour day) and the 2026 spring-forward
(Mar 8, 23 hours): current tzdata has Alberta on permanent UTC-6 from Nov 1 2026, so no
later fall-back is certain.
"""
from datetime import date, datetime, timedelta, timezone
from itertools import pairwise
from zoneinfo import ZoneInfo

import pytest

from haku_sidecar import history as h

TZ = ZoneInfo("America/Edmonton")
UTC = timezone.utc


def _t(*a, tz=TZ):
    return int(datetime(*a, tzinfo=tz).timestamp())


def _iso(t):
    return datetime.fromtimestamp(t, UTC).isoformat()


# --- ts_of -------------------------------------------------------------------
@pytest.mark.parametrize("v,want", [
    (1790305200000.0, 1790305200),            # epoch ms (HA 2023.3+)
    (1790305200000, 1790305200),
    (1790305200, 1790305200),                 # epoch s
    ("2026-09-24T06:00:00+00:00", _t(2026, 9, 24, 6, tz=UTC)),
    ("2026-09-24T06:00:00Z", _t(2026, 9, 24, 6, tz=UTC)),
    (None, None), ("junk", None), (True, None), (float("nan"), None),
])
def test_ts_of(v, want):
    assert h.ts_of(v) == want


# --- runs -----------------------------------------------------------------------
START = _t(2026, 9, 24, 18, tz=UTC)


def _row(i, v, key="change", ms=True, start=START):
    t = start + i * 3600
    return {"start": t * 1000.0 if ms else _iso(t), "end": (t + 3600) * 1000.0, key: v}


def test_runs_split_at_gaps():
    rows = [_row(0, 1.0), _row(1, 0.0), _row(2, 12.5), _row(41, 3.2), _row(42, 4.0)]
    assert h.runs(rows, "change", START, 3600, 168) == [
        {"i": 0, "v": [1.0, 0.0, 12.5]}, {"i": 41, "v": [3.2, 4.0]}]


def test_runs_accept_iso_starts_and_unordered_rows():
    rows = [_row(5, 2.0, ms=False), _row(3, 1.0, ms=False), _row(4, 1.5)]
    assert h.runs(rows, "change", START, 3600, 168) == [{"i": 3, "v": [1.0, 1.5, 2.0]}]


def test_runs_window_edges():
    rows = [_row(-1, 9.0), _row(0, 1.0), _row(167, 2.0), _row(168, 9.0)]
    out = h.runs(rows, "change", START, 3600, 168)
    assert out == [{"i": 0, "v": [1.0]}, {"i": 167, "v": [2.0]}]
    assert all(r["i"] >= 0 and r["i"] + len(r["v"]) <= 168 for r in out)


def test_runs_skip_non_numbers_as_gaps():
    rows = [_row(0, 1.0), _row(1, None), _row(2, "x"), _row(3, True), _row(4, float("inf")),
            _row(5, 2.0), {"start": None, "change": 3.0}, "junk"]
    assert h.runs(rows, "change", START, 3600, 168) == [{"i": 0, "v": [1.0]}, {"i": 5, "v": [2.0]}]


def test_runs_round_and_no_negative_zero():
    assert h.runs([_row(0, 1.23456), _row(1, -0.0001)], "change", START, 3600, 168) == [
        {"i": 0, "v": [1.235, 0.0]}]
    assert str(h.runs([_row(0, -0.00001)], "change", START, 3600, 168)[0]["v"][0]) == "0.0"


def test_runs_mean_key_and_negative_temps():
    rows = [_row(0, -12.34, key="mean"), _row(1, -11.0, key="mean")]
    assert h.runs(rows, "mean", START, 3600, 168, ndigits=1) == [{"i": 0, "v": [-12.3, -11.0]}]


def test_runs_empty():
    assert h.runs(None, "change", START, 3600, 168) == []
    assert h.runs([], "change", START, 3600, 168) == []


# --- window math and ticks ----------------------------------------------------------
def test_floor_hour():
    assert h.floor_hour(_t(2026, 10, 1, 18, 37, 12)) == _t(2026, 10, 1, 18)


def test_local_midnight_is_the_house_day_not_utc():
    t = _t(2026, 10, 1, 19, 30)                          # 01:30 UTC on Oct 2
    assert h.local_midnight(t, TZ) == _t(2026, 10, 1)
    assert h.local_midnight(t, TZ, 6) == _t(2026, 9, 25)


def test_local_midnight_across_fall_back():
    t = _t(2025, 11, 3, 12)
    assert h.local_midnight(t, TZ) - h.local_midnight(t, TZ, 1) == 25 * 3600
    assert h.local_midnight(t, TZ, 1) == _t(2025, 11, 2, 6, tz=UTC)    # still MDT
    assert h.local_midnight(t, TZ) == _t(2025, 11, 3, 7, tz=UTC)       # now MST


def test_local_midnight_across_spring_forward():
    t = _t(2026, 3, 9, 12)
    assert h.local_midnight(t, TZ) - h.local_midnight(t, TZ, 1) == 23 * 3600


def test_midnight_ticks_label_the_day_they_start():
    start = h.floor_hour(_t(2026, 10, 1, 18, 30)) - 168 * 3600      # Thu Sep 24 18:00
    ticks = h.midnight_ticks(start, 3600, 168, TZ)
    assert [t["label"] for t in ticks] == ["Fri", "Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
    assert [t["i"] for t in ticks] == [6, 30, 54, 78, 102, 126, 150]


def test_midnight_ticks_include_a_midnight_on_the_left_edge_only():
    start = _t(2026, 9, 25)
    ticks = h.midnight_ticks(start, 3600, 48, TZ)
    assert [t["i"] for t in ticks] == [0, 24]                       # Sep 27 00:00 is i=48: out


@pytest.mark.parametrize("day,gap", [((2025, 11, 2), 25), ((2026, 3, 8), 23), ((2026, 10, 1), 24)])
def test_midnight_ticks_dst_days(day, gap):
    start = _t(*day) - 30 * 3600
    ticks = h.midnight_ticks(start, 3600, 96, TZ)
    i = {t["label"]: t["i"] for t in ticks}
    d = date(*day)
    nxt = h.weekday(d + timedelta(days=1))
    assert i[nxt] - i[h.weekday(d)] == gap
    assert all(0 <= t["i"] < 96 for t in ticks)


def test_days_back():
    assert h.days_back(date(2026, 10, 1), 3) == [date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30)]


def test_daily_maps_rows_to_local_dates():
    rows = [{"start": _t(2026, 9, 29) * 1000, "change": 400.0},
            {"start": _iso(_t(2026, 9, 30)), "change": 380.5},
            {"start": _t(2026, 9, 28) * 1000, "change": None}]
    assert h.daily(rows, "change", TZ) == {date(2026, 9, 29): 400.0, date(2026, 9, 30): 380.5}


# --- y scale -----------------------------------------------------------------------
def test_y_scale_counter():
    assert h.y_scale([12.0, 52.0, 0.0], "L") == {"min": 0, "max": 60, "ticks": [
        {"v": 0, "label": "0"}, {"v": 20, "label": "20 L"},
        {"v": 40, "label": "40 L"}, {"v": 60, "label": "60 L"}]}


def test_y_scale_small_decimals():
    y = h.y_scale([0.8, 0.1], "kWh")
    assert (y["min"], y["max"]) == (0, 0.8)
    assert [t["label"] for t in y["ticks"]] == ["0", "0.2 kWh", "0.4 kWh", "0.6 kWh", "0.8 kWh"]


def test_y_scale_temperatures_go_negative():
    y = h.y_scale([-12.4, 23.1, 5.0], "°C", zero=False)
    assert y["min"] <= -12.4 and y["max"] >= 23.1
    assert {"v": 0, "label": "0°C"} in y["ticks"]
    assert y["ticks"][0]["label"] == "-20°C"
    assert len(y["ticks"]) <= 6


def test_y_scale_all_below_zero_without_zero():
    y = h.y_scale([-30.0, -25.0], "°C", zero=False)
    assert -30 >= y["min"] and y["max"] >= -25 and y["max"] < 0


@pytest.mark.parametrize("vals,want", [
    ([-5.0, 5.0], [-5, 0, 5]),                    # a 2.5 step would label -2.5 and 2.5
    ([-1.0, 7.0], [-2, 0, 2, 4, 6, 8]),
    ([0.4, 14.1], [0, 5, 10, 15]),
    ([6.6, 6.6], [5, 6, 7, 8]),                   # flat data: whole-degree steps even for a tiny range
    ([-31.0, 2.0], [-40, -30, -20, -10, 0, 10]),
])
def test_y_scale_whole_steps(vals, want):
    y = h.y_scale(vals, "°", zero=False, whole=True)
    assert [t["v"] for t in y["ticks"]] == want
    assert y["min"] == want[0] and y["max"] == want[-1]


@pytest.mark.parametrize("vals", [[0.0, 0.0], [21.3], [5.0, 5.0]])
def test_y_scale_flat_data_still_has_a_range(vals):
    y = h.y_scale(vals, "°C", zero=False)
    assert y["max"] > y["min"]


def test_y_scale_no_data():
    assert h.y_scale([], "L") is None
    assert h.y_scale([None, "x"], "L") is None


def test_y_scale_ticks_are_evenly_spaced_and_cover_the_data():
    for vals in ([3.7], [1234.0], [0.04], [150.0], [7.5, 99.9], [0.33]):
        y = h.y_scale(vals, "L")
        vs = [t["v"] for t in y["ticks"]]
        steps = {round(b - a, 6) for a, b in pairwise(vs)}
        assert len(steps) == 1 and 3 <= len(vs) <= 6
        assert y["min"] == vs[0] <= min(vals) and y["max"] == vs[-1] >= max(vals)


def test_num_and_tick_label():
    assert [h.num(v) for v in (30, 30.0, 2.5, 0.125, 0.1 + 0.2)] == ["30", "30", "2.5", "0.125", "0.3"]
    assert h.tick_label(30, "L") == "30 L"
    assert h.tick_label(0, "L") == "0"
    assert h.tick_label(0, "°C", bare_zero=False) == "0°C"


# --- spans -------------------------------------------------------------------------
W0, W1 = _t(2026, 9, 25), _t(2026, 10, 1, 18, 30)


def _h(*pairs):
    return [{"state": st, "last_changed": _iso(t)} for st, t in pairs]


def test_mode_runs_running_through_overtime_is_one_run():
    rows = _h(("idle", W0), ("running", _t(2026, 9, 28, 9, 12)), ("overtime", _t(2026, 9, 28, 10, 0)),
              ("done", _t(2026, 9, 28, 10, 10)), ("done_calm", _t(2026, 9, 28, 10, 25)),
              ("idle", _t(2026, 9, 28, 11)))
    run, = h.mode_runs(rows, W0, W1)
    assert run == {"start": _t(2026, 9, 28, 9, 12), "end": _t(2026, 9, 28, 10, 10),
                   "length": 58 * 60, "open": False, "clipped": False}


def test_mode_runs_open_at_the_end_is_running_now():
    rows = _h(("idle", W0), ("running", W1 - 600))
    run, = h.mode_runs(rows, W0, W1)
    assert run["open"] is True and run["end"] is None and run["length"] == 600


def test_mode_runs_ignore_unavailable():
    rows = _h(("idle", W0), ("running", W0 + 3600), ("unavailable", W0 + 4000),
              ("running", W0 + 4100), ("unknown", W0 + 5000), ("done", W0 + 7200))
    run, = h.mode_runs(rows, W0, W1)
    assert (run["start"], run["end"]) == (W0 + 3600, W0 + 7200)


def test_mode_runs_clipped_at_the_window_start():
    rows = _h(("running", W0 - 900), ("done", W0 + 1800), ("running", W0 + 7200), ("done", W0 + 9000))
    first, second = h.mode_runs(rows, W0, W1)
    assert first["clipped"] is True and first["start"] == W0 and first["length"] == 1800
    assert second["clipped"] is False and second["length"] == 1800


def test_mode_runs_unordered_and_bad_rows():
    rows = _h(("done", W0 + 7200), ("running", W0 + 3600)) + [{"state": "running"}, None, "x"]
    assert [(r["start"], r["end"]) for r in h.mode_runs(rows, W0, W1)] == [(W0 + 3600, W0 + 7200)]


def test_open_intervals_for_a_contact():
    rows = _h(("off", W0), ("on", W0 + 100), ("off", W0 + 160), ("unavailable", W0 + 200),
              ("on", W0 + 300), ("on", W0 + 310), ("off", W0 + 3900), ("on", W1 - 60))
    a, b, c = h.open_intervals(rows, W0, W1)
    assert (a["start"], a["length"], a["open"]) == (W0 + 100, 60, False)
    assert (b["start"], b["length"]) == (W0 + 300, 3600)
    assert (c["start"], c["open"], c["length"]) == (W1 - 60, True, 60)


def test_open_intervals_open_all_window():
    a, = h.open_intervals(_h(("on", W0 - 7200)), W0, W1)
    assert a["clipped"] and a["open"] and a["length"] == W1 - W0


def test_spans_empty():
    assert h.open_intervals([], W0, W1) == []
    assert h.mode_runs(None, W0, W1) == []
    assert h.open_intervals(_h(("unavailable", W0), ("off", W0 + 5)), W0, W1) == []


# --- labels ------------------------------------------------------------------------
def test_clock_and_datetime_labels():
    t = _t(2026, 10, 1, 18, 5)
    assert h.clock(t, TZ) == "6:05 PM"
    assert h.clock(_t(2026, 10, 1, 0, 7), TZ) == "12:07 AM"
    assert h.clock(_t(2026, 10, 1, 12, 0), TZ) == "12:00 PM"
    assert h.dt_label(t, TZ) == "Thu Oct 1 · 6:05 PM"
    assert h.weekday(date(2026, 10, 1)) == "Thu"


def test_when_label():
    now = _t(2026, 10, 1, 18, 30)
    assert h.when_label(_t(2026, 10, 1, 6, 5), now, TZ) == "6:05 AM"
    assert h.when_label(_t(2026, 9, 30, 21, 40), now, TZ) == "Wed 9:40 PM"
    assert h.when_label(_t(2026, 9, 24, 8, 0), now, TZ) == "Thu Sep 24"


@pytest.mark.parametrize("secs,label", [
    (0, "<1m"), (59, "<1m"), (60, "1m"), (58 * 60 + 59, "58m"), (3600, "1h"),
    (113 * 60, "1h 53m"), (26 * 3600 + 300, "26h 5m"), (-5, "<1m"),
])
def test_duration(secs, label):
    assert h.duration(secs) == label


# --- weather chart helpers -----------------------------------------------------
@pytest.mark.parametrize("hour,want", [(0, "12 AM"), (1, "1 AM"), (11, "11 AM"), (12, "12 PM"),
                                       (13, "1 PM"), (23, "11 PM")])
def test_hour_label(hour, want):
    assert h.hour_label(_t(2026, 10, 3, hour, 40), TZ) == want


def test_clock_ticks_sit_on_local_hours_divisible_by_the_step():
    start = _t(2026, 10, 2, 14)                     # 14:00 local; 49 buckets run to 14:00 two days on
    ticks = h.clock_ticks(start, h.HOUR, 49, TZ, every=6)
    assert [(t["i"], t["label"]) for t in ticks] == [
        (4, "6 PM"), (10, "Sat"), (16, "6 AM"), (22, "12 PM"), (28, "6 PM"), (34, "Sun"),
        (40, "6 AM"), (46, "12 PM")]
    assert all(a["i"] < b["i"] for a, b in pairwise(ticks))


def test_clock_ticks_midnight_is_labelled_with_the_day_it_starts():
    ticks = h.clock_ticks(_t(2026, 10, 3, 20), h.HOUR, 12, TZ, every=12)
    assert ticks == [{"i": 4, "label": "Sun"}]      # 00:00 Sunday; 12 PM is outside the window


def test_clock_ticks_avoid_a_neighbourhood():
    start = _t(2026, 10, 2, 14)
    ticks = h.clock_ticks(start, h.HOUR, 49, TZ, every=6, avoid=[24], radius=5)
    assert [t["i"] for t in ticks] == [4, 10, 16, 34, 40, 46]   # 22 and 28 are within 5 of 24


def test_clock_ticks_follow_the_local_clock_over_spring_forward():
    """On 2026-03-08 the clock jumps 02:00 -> 03:00: 6 AM is 5 buckets after midnight, not 6."""
    start = _t(2026, 3, 8, 0)
    ticks = h.clock_ticks(start, h.HOUR, 12, TZ, every=6)
    assert [(t["i"], t["label"]) for t in ticks] == [(0, "Sun"), (5, "6 AM"), (11, "12 PM")]


def test_clock_ticks_skip_zones_off_the_hour():
    kathmandu = ZoneInfo("Asia/Kathmandu")           # UTC+5:45: UTC-hour buckets never land on :00
    assert h.clock_ticks(_t(2026, 10, 3, 0, tz=UTC), h.HOUR, 24, kathmandu, every=6) == []


def test_runs_from_joins_adjacent_buckets():
    assert h.runs_from({0: 1.0, 1: 2.0, 3: 4.0}) == [{"i": 0, "v": [1.0, 2.0]}, {"i": 3, "v": [4.0]}]
    assert h.runs_from({}) == []


def test_splice_point_extends_replaces_and_bridges():
    runs = [{"i": 0, "v": [1.0, 2.0]}, {"i": 5, "v": [9.0]}]
    assert h.splice_point(runs, 2, 3.0) == [{"i": 0, "v": [1.0, 2.0, 3.0]}, {"i": 5, "v": [9.0]}]
    assert h.splice_point(runs, 1, 7.5) == [{"i": 0, "v": [1.0, 7.5]}, {"i": 5, "v": [9.0]}]
    assert h.splice_point(runs, 4, 8.0) == [{"i": 0, "v": [1.0, 2.0]}, {"i": 4, "v": [8.0, 9.0]}]
    assert h.splice_point([], 24, 14.1) == [{"i": 24, "v": [14.1]}]
    assert runs == [{"i": 0, "v": [1.0, 2.0]}, {"i": 5, "v": [9.0]}]       # the input is untouched
