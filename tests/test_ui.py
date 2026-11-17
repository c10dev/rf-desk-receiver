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
