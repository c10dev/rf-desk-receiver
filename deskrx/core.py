"""Pure logic: observations, group keys, tracker, baseline and watch decision.

This module does no input, no output and no clock reads.
It ports the rules of KoriyoSCAN (SignalGroups.kt, DeviceTracker.kt,
ObservationPeriods.kt, RssiFilter.kt, SignalHints.kt) without "acknowledged".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

BLE, WIFI = "BLE", "WIFI"
ESTABLISHED_S = 30.0
WEAK_DBM = -85
GAP_S = {BLE: 15.0, WIFI: 90.0}  # longer silence starts a new reception period
HIDDEN_WIFI_KEY = "WIFI:hidden"
EMA_ALPHA = 0.25

# Priority of hints = declaration order of the SignalHint enum in SignalHints.kt,
# limited to the hints this program can produce.
HINT_ORDER = ("APPLE_AUDIO", "APPLE_ACTIVE", "WINDOWS", "FAST_PAIR", "FIND_MY", "BEACON", "HOTSPOT", "WIFI_DIRECT")

HINT_LABELS = {
    "APPLE_AUDIO": "Apple·Beats 이어폰",
    "APPLE_ACTIVE": "켜져 있는 Apple 기기",
    "WINDOWS": "Windows 기기",
    "FAST_PAIR": "블루투스 액세서리",
    "FIND_MY": "나의 찾기 신호",
    "BEACON": "고정 비콘",
    "HOTSPOT": "휴대폰 핫스팟 후보",
    "WIFI_DIRECT": "Wi-Fi Direct 기기",
}

APPLE_COMPANY_ID = 0x004C

_HOTSPOT_NAME = re.compile(
    r"iPhone|iPad|Galaxy|AndroidAP|Pixel[ _]|Redmi|Xiaomi|POCO|HUAWEI|OnePlus|hotspot|핫스팟|테더링",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Observation:
    source: str  # BLE | WIFI
    address: str  # stored upper-case
    name: Optional[str]  # advertised name or SSID; None/blank = no name
    rssi: Optional[int]  # dBm
    t: float  # epoch seconds
    company_ids: frozenset = frozenset()
    hint: Optional[str] = None


@dataclass(frozen=True)
class Device:
    source: str
    address: str
    name: Optional[str]
    group: str
    hint: Optional[str]
    ema: Optional[float]
    peak: Optional[int]
    first_seen: float
    last_seen: float
    period_start: float  # start of the current reception period
    count: int
    live: bool  # now - last_seen <= GAP_S[source]


def primary_hint(hints: Iterable[str]) -> Optional[str]:
    """Return the member that comes first in HINT_ORDER."""
    found = set(hints)
    for hint in HINT_ORDER:
        if hint in found:
            return hint
    return None


def group_key(source: str, name: Optional[str], company_ids: Iterable[int], hint: Optional[str]) -> str:
    advertised = name.strip() if name else ""
    ids = sorted(company_ids)
    if advertised:
        return f"{source}:name:{advertised.lower()}"
    if source == WIFI:
        return HIDDEN_WIFI_KEY
    if not ids and not hint:
        return "BLE:unknown"
    return f"BLE:kind:{','.join(str(i) for i in ids)}:{hint or ''}"


def apple_hint(payload: bytes) -> Optional[str]:
    """Read Apple manufacturer data without the 2 company bytes: [type][len][data]..."""
    kinds = {
        0x02: "BEACON",
        0x07: "APPLE_AUDIO",
        0x05: "APPLE_ACTIVE",
        0x0C: "APPLE_ACTIVE",
        0x0E: "APPLE_ACTIVE",
        0x0F: "APPLE_ACTIVE",
        0x10: "APPLE_ACTIVE",
        0x12: "FIND_MY",
    }
    found = set()
    index = 0
    while index + 1 < len(payload):
        kind = kinds.get(payload[index])
        if kind:
            found.add(kind)
        index += 2 + payload[index + 1]
    return primary_hint(found)


def wifi_hint(ssid: Optional[str]) -> Optional[str]:
    if not ssid or not ssid.strip():
        return None
    if ssid.startswith("DIRECT-"):
        return "WIFI_DIRECT"
    if _HOTSPOT_NAME.search(ssid):
        return "HOTSPOT"
    return None


def same_access_point(address: str, baseline_wifi: Iterable[str]) -> bool:
    """One access point uses several addresses that differ in the first or last octet."""
    known_set = set(baseline_wifi)
    candidate = address.upper()
    if candidate in known_set:
        return True
    if len(candidate) != 17:
        return False
    return any(
        len(known) == 17 and (known[3:] == candidate[3:] or known[:-2] == candidate[:-2])
        for known in known_set
    )


def device_label(device: Device) -> str:
    if device.name and device.name.strip():
        return device.name.strip()
    if device.hint:
        return HINT_LABELS.get(device.hint, device.hint)
    if device.source == WIFI:
        return "이름 없는 Wi-Fi " + device.address[-5:]
    return "BLE 기기 " + device.address[-5:]


class _Track:
    def __init__(self, source: str, address: str, t: float) -> None:
        self.source = source
        self.address = address
        self.name: Optional[str] = None
        self.company_ids: set = set()
        self.hints: set = set()
        self.ema: Optional[float] = None
        self.peak: Optional[int] = None
        self.first_seen = t
        self.last_seen = t
        self.period_start = t
        self.count = 0


class Tracker:
    def __init__(self) -> None:
        self._tracks: dict = {}

    def update(self, obs: Observation) -> None:
        address = obs.address.upper()
        track = self._tracks.get(address)
        late = False
        if track is None:
            track = _Track(obs.source, address, obs.t)
            self._tracks[address] = track
        else:
            late = obs.t < track.last_seen
            if not late and obs.t - track.last_seen > GAP_S[track.source]:
                track.period_start = obs.t
                track.ema = None  # EMA restarts with a new reception period
        track.first_seen = min(track.first_seen, obs.t)
        track.last_seen = max(track.last_seen, obs.t)
        track.count += 1
        track.company_ids.update(obs.company_ids)
        if obs.hint:
            track.hints.add(obs.hint)
        if obs.name and obs.name.strip() and (not late or track.name is None):
            track.name = obs.name  # A name, once seen, stays unless a newer name arrives.
        if obs.rssi is not None:
            if not late:
                track.ema = float(obs.rssi) if track.ema is None else track.ema + EMA_ALPHA * (obs.rssi - track.ema)
            track.peak = obs.rssi if track.peak is None else max(track.peak, obs.rssi)

    def _group(self, track: _Track) -> str:
        return group_key(track.source, track.name, track.company_ids, primary_hint(track.hints))

    def group_of(self, address: str) -> Optional[str]:
        track = self._tracks.get(address.upper())
        return self._group(track) if track else None

    def devices(self, now: float) -> list:
        result = []
        for track in self._tracks.values():
            result.append(
                Device(
                    source=track.source,
                    address=track.address,
                    name=track.name,
                    group=self._group(track),
                    hint=primary_hint(track.hints),
                    ema=track.ema,
                    peak=track.peak,
                    first_seen=track.first_seen,
                    last_seen=track.last_seen,
                    period_start=track.period_start,
                    count=track.count,
                    live=now - track.last_seen <= GAP_S[track.source],
                )
            )
        return result


@dataclass(frozen=True)
class Baseline:
    captured_at: float
    groups: dict  # group -> live count at capture, at least 1 for every group seen
    wifi: frozenset  # Wi-Fi addresses seen

    def to_json(self) -> dict:
        return {"captured_at": self.captured_at, "groups": dict(self.groups), "wifi": sorted(self.wifi)}

    @staticmethod
    def from_json(d: dict) -> "Baseline":
        return Baseline(
            captured_at=float(d["captured_at"]),
            groups={str(k): int(v) for k, v in d["groups"].items()},
            wifi=frozenset(str(a).upper() for a in d["wifi"]),
        )


def capture_baseline(devices: list, now: float) -> Baseline:
    groups: dict = {}
    for d in devices:
        groups[d.group] = groups.get(d.group, 0) + (1 if d.live else 0)
    groups = {k: max(v, 1) for k, v in groups.items()}
    wifi = frozenset(d.address.upper() for d in devices if d.source == WIFI)
    return Baseline(captured_at=now, groups=groups, wifi=wifi)


def _strength(device: Device) -> float:
    return device.ema if device.ema is not None else float("-inf")


@dataclass(frozen=True)
class GroupRow:
    key: str
    devices: tuple  # strongest first
    baseline_count: int
    alert: bool

    @property
    def strongest(self) -> Device:
        return self.devices[0]


@dataclass(frozen=True)
class View:
    new: tuple  # not weak
    far: tuple  # strongest ema < WEAK_DBM
    find_my: int  # live BLE devices with hint FIND_MY
    known_live: int  # live devices judged as "was there before"


def watch(devices: list, baseline: Baseline, now: float) -> View:
    live = [d for d in devices if d.live]
    find_my = [d for d in live if d.source == BLE and d.hint == "FIND_MY"]
    others = [d for d in live if not (d.source == BLE and d.hint == "FIND_MY")]
    # A known access point may show another address later, even with a hidden name.
    rest = [d for d in others if not (d.source == WIFI and same_access_point(d.address, baseline.wifi))]
    grouped: dict = {}
    for d in rest:
        grouped.setdefault(d.group, []).append(d)
    flagged = []
    for key, members in grouped.items():
        ordered = sorted(members, key=_strength, reverse=True)
        before = baseline.groups.get(key, 0)
        is_wifi = ordered[0].source == WIFI
        established = sum(1 for m in members if now - m.period_start >= ESTABLISHED_S)
        row = None
        if before == 0:
            # A group missing from the empty room shows at once. A Wi-Fi address does not change, so it alerts at once.
            row = GroupRow(key, tuple(ordered), 0, is_wifi or established > 0)
        elif is_wifi and key == HIDDEN_WIFI_KEY:
            row = GroupRow(key, tuple(ordered), 0, True)
        elif is_wifi:
            row = None  # Same-name Wi-Fi was there before, whatever the address count.
        elif established > before:
            row = GroupRow(key, tuple(ordered), before, True)
        if row is not None:
            flagged.append(row)
    flagged.sort(key=lambda r: _strength(r.strongest), reverse=True)
    far = tuple(r for r in flagged if (r.strongest.ema if r.strongest.ema is not None else -127.0) < WEAK_DBM)
    near = tuple(r for r in flagged if r not in far)
    flagged_devices = sum(len(r.devices) for r in flagged)
    return View(new=near, far=far, find_my=len(find_my), known_live=len(others) - flagged_devices)
