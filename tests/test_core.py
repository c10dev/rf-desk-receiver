from deskrx.core import (
    BLE, WIFI, HIDDEN_WIFI_KEY, Baseline, Observation, Tracker, apple_hint, capture_baseline,
    group_key, primary_hint, same_access_point, watch, wifi_hint,
)

APPLE = frozenset({76})


def ble(tracker, address, t, rssi=-60, name=None, ids=APPLE, hint="APPLE_ACTIVE"):
    tracker.update(Observation(BLE, address, name, rssi, t, ids, hint))


def wifi(tracker, address, name=None, rssi=-60, t=0):
    tracker.update(Observation(WIFI, address, name, rssi, t, hint=wifi_hint(name)))


def view_at(tracker, baseline, now):
    return watch(tracker.devices(now), baseline, now)


def test_group_key_four_branches():
    assert group_key(BLE, "  Galaxy Buds2 ", frozenset(), None) == "BLE:name:galaxy buds2"
    assert group_key(WIFI, "School-AP", frozenset(), None) == "WIFI:name:school-ap"
    assert group_key(WIFI, "  ", frozenset(), None) == HIDDEN_WIFI_KEY
    assert group_key(WIFI, None, frozenset(), None) == HIDDEN_WIFI_KEY
    assert group_key(BLE, None, frozenset(), None) == "BLE:unknown"
    assert group_key(BLE, "", frozenset({76, 6}), "APPLE_ACTIVE") == "BLE:kind:6,76:APPLE_ACTIVE"
    assert group_key(BLE, None, frozenset({76}), None) == "BLE:kind:76:"
    assert group_key(BLE, None, frozenset(), "FAST_PAIR") == "BLE:kind::FAST_PAIR"


def test_same_access_point():
    known = {"10:00:00:00:00:01"}
    assert same_access_point("10:00:00:00:00:01", known)
    assert same_access_point("10:00:00:00:00:99", known)  # last octet differs
    assert same_access_point("AA:00:00:00:00:01", known)  # first octet differs
    assert not same_access_point("DE:AD:BE:EF:00:01", known)
    assert not same_access_point("10:00:00", known)
    assert same_access_point("10:00:00:00:00:99".lower(), known)


def test_apple_hint_priority_and_walk():
    assert apple_hint(bytes([0x12, 0x00])) == "FIND_MY"
    assert apple_hint(bytes([0x02, 0x00])) == "BEACON"
    assert apple_hint(bytes([0x0C, 0x01, 0xAA])) == "APPLE_ACTIVE"
    # Audio beats active, active beats find-my, find-my beats beacon.
    both = bytes([0x12, 0x01, 0xAA, 0x02, 0x00, 0x05, 0x00, 0x07, 0x00])
    assert apple_hint(both) == "APPLE_AUDIO"
    assert apple_hint(bytes([0x12, 0x00, 0x05, 0x00])) == "APPLE_ACTIVE"
    assert apple_hint(bytes([0x12, 0x00, 0x02, 0x00])) == "FIND_MY"
    assert apple_hint(bytes([0x99, 0x00])) is None
    assert apple_hint(b"") is None


def test_primary_hint_follows_hint_order():
    assert primary_hint({"FAST_PAIR", "WINDOWS"}) == "WINDOWS"
    assert primary_hint({"FIND_MY", "FAST_PAIR"}) == "FAST_PAIR"
    assert primary_hint(set()) is None


def test_wifi_hint():
    assert wifi_hint("DIRECT-ab-Printer") == "WIFI_DIRECT"
    assert wifi_hint("My iPhone") == "HOTSPOT"
    assert wifi_hint("AndroidAP_1234") == "HOTSPOT"
    assert wifi_hint("내 핫스팟") == "HOTSPOT"
    assert wifi_hint("School-AP") is None
    assert wifi_hint(None) is None
    assert wifi_hint("  ") is None


def test_tracker_accumulates_hints_as_set():
    t = Tracker()
    ble(t, "AA:00:00:00:00:01", 0, hint="FAST_PAIR", ids=frozenset())
    ble(t, "AA:00:00:00:00:01", 1, hint="WINDOWS", ids=frozenset({6}))
    d = t.devices(1)[0]
    assert d.hint == "WINDOWS"
    assert d.group == "BLE:kind:6:WINDOWS"


def test_tracker_name_stays_peak_never_drops_ema_restarts():
    t = Tracker()
    ble(t, "aa:00:00:00:00:01", 0, rssi=-40, name="Buds")
    ble(t, "AA:00:00:00:00:01", 1, rssi=-80, name=None)
    d = t.devices(1)[0]
    assert d.name == "Buds" and d.peak == -40 and d.address == "AA:00:00:00:00:01"
    assert d.ema == -50.0  # -40 + 0.25 * (-80 + 40)
    ble(t, "AA:00:00:00:00:01", 100, rssi=-90)  # silence above 15 s starts a new period
    d = t.devices(100)[0]
    assert d.ema == -90.0 and d.period_start == 100 and d.peak == -40


def test_changed_address_is_not_counted_again():
    t = Tracker()
    ble(t, "AA:00:00:00:00:01", 0)
    ble(t, "AA:00:00:00:00:02", 0)
    baseline = capture_baseline(t.devices(1), 1)
    assert baseline.groups == {"BLE:kind:76:APPLE_ACTIVE": 2}
    later = 900
    ble(t, "AA:00:00:00:00:01", later)
    ble(t, "AA:00:00:00:00:02", later - 5)
    ble(t, "AA:00:00:00:00:03", later)
    assert view_at(t, baseline, later + 1).new == ()
    ble(t, "AA:00:00:00:00:01", later + 40)
    ble(t, "AA:00:00:00:00:03", later + 40)
    assert view_at(t, baseline, later + 41).new == ()


def test_one_more_of_same_kind_alerts_after_thirty_seconds():
    t = Tracker()
    ble(t, "AA:00:00:00:00:01", 0)
    ble(t, "AA:00:00:00:00:02", 0)
    baseline = capture_baseline(t.devices(1), 1)
    later = 600
    for step in (0, 10, 20, 30, 40):
        ble(t, "AA:00:00:00:00:01", later + step)
        ble(t, "AA:00:00:00:00:02", later + step)
        ble(t, "AA:00:00:00:00:09", later + step, rssi=-50)
    assert view_at(t, baseline, later + 20).new == ()  # still under 30 s
    row = view_at(t, baseline, later + 41).new[0]
    assert row.baseline_count == 2 and len(row.devices) == 3
    assert row.strongest.address == "AA:00:00:00:00:09"
    assert row.alert


def test_hidden_wifi_alerts_at_once_but_known_access_point_address_does_not():
    t = Tracker()
    wifi(t, "10:00:00:00:00:01", "School-AP")
    wifi(t, "10:00:00:00:00:02", None)
    baseline = capture_baseline(t.devices(1), 1)
    assert baseline.wifi == frozenset({"10:00:00:00:00:01", "10:00:00:00:00:02"})
    assert view_at(t, baseline, 2).new == ()
    wifi(t, "10:00:00:00:00:99", None, rssi=-40)  # same access point, other address
    assert view_at(t, baseline, 3).new == ()
    wifi(t, "DE:AD:BE:EF:00:01", None, rssi=-45)
    row = view_at(t, baseline, 3).new[0]
    assert row.key == HIDDEN_WIFI_KEY and row.alert
    assert [d.address for d in row.devices] == ["DE:AD:BE:EF:00:01"]


def test_same_name_wifi_is_known():
    t = Tracker()
    wifi(t, "10:00:00:00:00:01", "School-AP")
    baseline = capture_baseline(t.devices(1), 1)
    wifi(t, "77:77:77:77:77:77", "School-AP")
    assert view_at(t, baseline, 2).new == ()


def test_find_my_counted_only_in_find_my():
    t = Tracker()
    baseline = Baseline(0, {}, frozenset())
    ble(t, "AA:00:00:00:00:01", 0, hint="FIND_MY")
    ble(t, "AA:00:00:00:00:02", 0, hint="FIND_MY")
    v = view_at(t, baseline, 1)
    assert v.find_my == 2 and v.new == () and v.far == ()


def test_weak_signal_goes_to_far():
    t = Tracker()
    baseline = Baseline(0, {}, frozenset())
    wifi(t, "DE:AD:BE:EF:00:01", "Neighbor", rssi=-90)
    wifi(t, "DE:AD:BE:EF:00:02", "Near", rssi=-60)
    v = view_at(t, baseline, 1)
    assert [r.strongest.name for r in v.far] == ["Neighbor"]
    assert [r.strongest.name for r in v.new] == ["Near"]


def test_known_live_and_baseline_json_roundtrip():
    t = Tracker()
    ble(t, "AA:00:00:00:00:01", 0, name="Teacher Watch", ids=frozenset(), hint=None)
    baseline = capture_baseline(t.devices(1), 1)
    again = Baseline.from_json(baseline.to_json())
    assert again == baseline
    v = view_at(t, again, 2)
    assert v.known_live == 1 and v.new == ()


def test_baseline_counts_at_least_one_for_vanished_group():
    t = Tracker()
    ble(t, "AA:00:00:00:00:01", 0, name="Gone")
    baseline = capture_baseline(t.devices(500), 500)  # device is no longer live
    assert baseline.groups == {"BLE:name:gone": 1}
