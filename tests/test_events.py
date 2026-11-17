import json

from deskrx.core import Baseline, Device, GroupRow, Observation, Tracker, View, watch
from deskrx.events import EventLog, iso_local


def dev(address="AA:00:00:00:00:09", name="Galaxy Buds2", peak=-50, t=0.0):
    return Device("BLE", address, name, "BLE:name:galaxy buds2", None, -50.0, peak, t, t, t, 1, True)


def view_with(alert=True, peak=-50, t=0.0):
    row = GroupRow("BLE:name:galaxy buds2", (dev(peak=peak, t=t),), 0, alert)
    return View(new=(row,), far=(), find_my=0, known_live=0)


EMPTY = View(new=(), far=(), find_my=0, known_live=0)


def test_start_and_end_lines_are_written(tmp_path):
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    log.update(view_with(), 1000.0)
    log.update(view_with(peak=-40), 1010.0)
    log.update(EMPTY, 1020.0)
    log.close()
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert [x["type"] for x in lines] == ["start", "end"]
    assert set(lines[0]) == {"type", "key", "label", "source", "started", "last_seen", "ended", "peak"}
    assert lines[0]["label"] == "Galaxy Buds2" and lines[0]["ended"] is None
    assert lines[1]["peak"] == -40 and lines[1]["ended"] is not None
    assert len(lines[1]["started"]) == 19  # ISO local time with seconds


def test_returning_signal_opens_new_event():
    log = EventLog(None)
    log.update(view_with(), 1.0)
    log.update(EMPTY, 2.0)
    log.update(view_with(t=3.0), 3.0)
    assert len(log.open) == 1 and len(log.closed) == 1
    log.update(EMPTY, 4.0)
    assert len(log.closed) == 2 and log.closed[0].started == 3.0  # newest first


def test_non_alert_group_opens_event():
    log = EventLog(None)
    log.update(view_with(alert=False), 1.0)
    assert len(log.open) == 1 and log.closed == []


def test_short_ble_signal_leaves_start_and_end_lines(tmp_path):
    base = 1_800_000_000.0
    tracker = Tracker()
    baseline = Baseline(base - 100, {}, frozenset())
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    for sec in range(0, 11):  # new BLE name seen for 10 s
        tracker.update(Observation("BLE", "AA:00:00:00:00:09", "Short Buds", -50, base + sec))
        now = base + sec
        log.update(watch(tracker.devices(now), baseline, now), now)
    for sec in range(11, 40):  # then gone (15 s gap)
        now = base + sec
        log.update(watch(tracker.devices(now), baseline, now), now)
    log.close()
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert [x["type"] for x in lines] == ["start", "end"]
    assert lines[0]["started"] == iso_local(base)  # first packet time
    assert lines[1]["started"] == iso_local(base)
    assert lines[1]["last_seen"] == iso_local(base + 10)


def test_summarize_merges_same_key():
    from deskrx.events import Event, summarize

    closed = [  # newest first, as EventLog.closed
        Event("k", "New Label", "BLE", 300.0, 320.0, 330.0, -60),
        Event("k", "Old", "BLE", 200.0, 210.0, 220.0, -50),
        Event("k", "Older", "BLE", 100.0, 110.0, 120.0, -70),
        Event("other", "Other", "WIFI", 10.0, 20.0, 400.0, None),
    ]
    out = summarize(closed)
    assert [x.key for x in out] == ["other", "k"]  # newest last_ended first
    k = out[1]
    assert (k.count, k.first_started, k.last_ended, k.peak) == (3, 100.0, 330.0, -50)
    assert k.label == "New Label" and k.source == "BLE"
