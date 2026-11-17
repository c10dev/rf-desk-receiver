from deskrx.core import Device, GroupRow, View
from deskrx.events import EventLog
from deskrx.ui import render

OK = {"ble_age": 1.0, "ble_error": None, "wifi_age": 5.0, "wifi_error": None, "ble_on": True, "wifi_on": True}
EMPTY = View((), (), 0, 0)


def row():
    d = Device("BLE", "AA:00:00:00:00:09", "Galaxy Buds2", "BLE:name:galaxy buds2", None, -50.0, -50, 0, 0, 0, 3, True)
    return GroupRow(d.group, (d,), 0, True)


def text(view, health, phase="watch"):
    return render(phase, 1000.0, 0.0, view, EventLog(None), health, 0.0)


def test_no_new_signal():
    out = text(EMPTY, OK)
    assert "새 전파 없음" in out and "감시가 완전하지 않습니다" not in out


def test_new_signal_count_and_name():
    out = text(View((row(),), (), 0, 0), OK)
    assert "새 전파 1개" in out and "Galaxy Buds2" in out


def test_lost_ble_reception_warns():
    out = text(EMPTY, dict(OK, ble_age=45.0))
    assert "감시가 완전하지 않습니다" in out and "새 전파 없음" not in out


def test_warning_shown_with_new_signals_after_count_line():
    out = text(View((row(),), (), 0, 0), dict(OK, wifi_error="nmcli 명령을 찾을 수 없습니다."))
    assert out.index("새 전파 1개") < out.index("감시가 완전하지 않습니다")
    assert "nmcli" in out


def test_no_reception_record_is_incomplete_but_off_source_is_not():
    assert "감시가 완전하지 않습니다" in text(EMPTY, dict(OK, ble_age=None))
    assert "감시가 완전하지 않습니다" not in text(EMPTY, dict(OK, ble_on=False, ble_age=None))
    assert "감시가 완전하지 않습니다" in text(EMPTY, dict(OK, wifi_age=121.0))


def test_collect_and_ready_phases():
    assert "수집" in render("collect", 1.0, 0.0, None, EventLog(None), OK, 42.0)
    assert "Enter" in render("ready", 1.0, 0.0, None, EventLog(None), OK, 0.0)


def _log(events):
    log = EventLog(None)
    log._closed = list(events)
    return log


def _ev(key, label, peak, n, t0=1000.0):
    from deskrx.events import Event

    return [Event(key, label, "BLE", t0 + i * 30, t0 + i * 30 + 5, t0 + i * 30 + 20, peak) for i in range(n)]


def test_only_weak_history_is_folded():
    closed = _ev("a", "BLE 기기 FC:4C", -93, 5) + _ev("b", "BLE 기기 AA:01", -90, 4) + _ev("c", "BLE 기기 BB:02", -89, 3)
    out = render("watch", 2000.0, 0.0, EMPTY, _log(closed), OK, 0.0)
    section = out.split("사라진 새 전파(최근 10종)")[1]
    assert section.lstrip("\n").startswith("  없음")
    assert "멀리서 약하게 잡혔다 사라진 것 3종 12번" in out
    assert "  BLE 기기 FC:4C  5번  최고 -93 dBm" in out


def test_strong_history_listed_among_weak():
    closed = _ev("s", "Galaxy Buds2", -50, 1) + _ev("w", "BLE 기기 FC:4C", -93, 6)
    out = render("watch", 2000.0, 0.0, EMPTY, _log(closed), OK, 0.0)
    strong_part = out.split("사라진 새 전파(최근 10종)")[1].split("멀리서 약하게 잡혔다 사라진 것")[0]
    assert "Galaxy Buds2  최고 -50 dBm" in strong_part and "번  최고" not in strong_part
    assert "멀리서 약하게 잡혔다 사라진 것 1종 6번" in out


def test_repeated_strong_history_shows_count_and_no_weak_line_when_none():
    out = render("watch", 2000.0, 0.0, EMPTY, _log(_ev("s", "Galaxy Buds2", -50, 3)), OK, 0.0)
    assert "Galaxy Buds2  3번  최고 -50 dBm" in out
    assert "멀리서 약하게 잡혔다 사라진 것" not in out
