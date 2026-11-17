"""Build screen text. Pure functions."""
from __future__ import annotations

from datetime import datetime

from .core import HINT_LABELS, GroupRow, View, device_label
from .events import EventLog

BLE_STALE_S = 30
WIFI_STALE_S = 120
RULE = "-" * 60


def _clock(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%H:%M:%S")


def _mmss(seconds: float) -> str:
    s = int(max(0, seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def incomplete_reasons(health: dict) -> list:
    reasons = []
    if health.get("ble_on"):
        if health.get("ble_error"):
            reasons.append(f"BLE 수신 오류: {health['ble_error']}")
        elif health.get("ble_age") is None:
            reasons.append("BLE 수신 기록이 아직 없습니다")
        elif health["ble_age"] > BLE_STALE_S:
            reasons.append(f"BLE 마지막 수신이 {int(health['ble_age'])}초 전입니다")
    if health.get("wifi_on"):
        if health.get("wifi_error"):
            reasons.append(f"와이파이 수신 오류: {health['wifi_error']}")
        elif health.get("wifi_age") is None:
            reasons.append("와이파이 수신 기록이 아직 없습니다")
        elif health["wifi_age"] > WIFI_STALE_S:
            reasons.append(f"와이파이 마지막 수신이 {int(health['wifi_age'])}초 전입니다")
    return reasons


def _row_line(row: GroupRow) -> str:
    d = row.strongest
    ema = "?" if d.ema is None else f"{d.ema:.0f}"
    kind = "BLE" if d.source == "BLE" else "Wi-Fi"
    state = "알림" if row.alert else "확인 중"
    hint = f" · {HINT_LABELS.get(d.hint, d.hint)}" if d.hint and d.name else ""
    return f"  [{state}] {device_label(d)}{hint} ({kind}) {len(row.devices)}대, 평균 {ema} dBm"


def _health_lines(health: dict) -> list:
    lines = []
    if health.get("ble_on"):
        age = health.get("ble_age")
        lines.append("BLE: " + ("기록 없음" if age is None else f"마지막 수신 {int(age)}초 전"))
    else:
        lines.append("BLE: 꺼짐")
    if health.get("wifi_on"):
        age = health.get("wifi_age")
        lines.append("와이파이: " + ("기록 없음" if age is None else f"마지막 수신 {int(age)}초 전"))
    else:
        lines.append("와이파이: 꺼짐")
    return lines


def render(phase: str, now: float, started: float, view, events: EventLog, health: dict, collect_left: float) -> str:
    out = [f"deskrx 교탁 수신기  {_clock(now)}  (실행 {_mmss(now - started)})"]
    if phase == "collect":
        out.append(f"빈 교실 전파를 수집 중입니다. 남은 시간 {int(max(0, collect_left))}초")
        out.extend(_health_lines(health))
        return "\n".join(out)
    if phase == "ready":
        out.append("수집이 끝났습니다. 교실이 비어 있으면 Enter를 눌러 감시를 시작하세요.")
        out.extend(_health_lines(health))
        return "\n".join(out)

    reasons = incomplete_reasons(health)
    new_count = 0 if view is None else len(view.new)
    far = () if view is None else view.far
    if new_count:
        out.append(f"새 전파 {new_count}개")
    elif not reasons:
        out.append("새 전파 없음")
    if reasons:
        out.append("감시가 완전하지 않습니다: " + "; ".join(reasons))
    out.append(RULE)
    out.append("새 전파(지금)")
    if view is not None and view.new:
        out.extend(_row_line(r) for r in view.new)
    else:
        out.append("  없음")
    out.append("멀리서 약하게 잡히는 것")
    if far:
        out.extend(_row_line(r) for r in far)
    else:
        out.append("  없음")
    find_my = 0 if view is None else view.find_my
    out.append(f"꺼 둔 아이폰·에어태그 신호 {find_my}개")
    out.append("사라진 새 전파(최근 10건)")
    closed = events.closed[:10]
    if closed:
        for ev in closed:
            peak = "?" if ev.peak is None else str(ev.peak)
            end = _clock(ev.ended if ev.ended is not None else ev.last_seen)
            out.append(f"  {_clock(ev.started)}–{end}  {ev.label}  최고 {peak} dBm")
    else:
        out.append("  없음")
    out.append(RULE)
    out.extend(_health_lines(health))
    return "\n".join(out)
