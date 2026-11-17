"""Read the Wi-Fi list with the OS tool and parse it."""
from __future__ import annotations

import asyncio
import locale
import re
import sys
from typing import List, Optional

from .core import WIFI, Observation, wifi_hint

SCAN_TIMEOUT_S = 20.0


class WifiUnavailable(Exception):
    pass


def _dbm(percent: int) -> int:
    return int(round(percent / 2 - 100))


def _observation(address: str, ssid: str, percent: Optional[int], now: float) -> Observation:
    name = ssid.strip() or None
    return Observation(
        source=WIFI,
        address=address.upper(),
        name=name,
        rssi=None if percent is None else _dbm(percent),
        t=now,
        hint=wifi_hint(name),
    )


_SSID = re.compile(r"^SSID \d+ : (.*)$")
_BSSID = re.compile(r"^\s+BSSID \d+\s*: ([0-9A-Fa-f:]{17})")
_PERCENT = re.compile(r"(\d+)%")


def parse_netsh(text: str, now: float) -> List[Observation]:
    """Parse `netsh wlan show networks mode=bssid`. The output is localized, so match only the layout."""
    result: List[Observation] = []
    ssid = ""
    pending: Optional[str] = None  # BSSID that still waits for its signal line

    def flush(percent: Optional[int]) -> None:
        nonlocal pending
        if pending is not None:
            result.append(_observation(pending, ssid, percent, now))
            pending = None

    for raw in text.splitlines():
        line = raw.rstrip("\r\n")
        m = _SSID.match(line)
        if m:
            flush(None)
            ssid = m.group(1).strip()
            continue
        m = _BSSID.match(line)
        if m:
            flush(None)
            pending = m.group(1)
            continue
        if pending is not None:
            p = _PERCENT.search(line)
            if p:
                flush(int(p.group(1)))
    flush(None)
    return result


def _split_nmcli(line: str) -> List[str]:
    fields: List[str] = []
    current: List[str] = []
    i = 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            current.append(line[i + 1])
            i += 2
            continue
        if c == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(c)
        i += 1
    fields.append("".join(current))
    return fields


def parse_nmcli(text: str, now: float) -> List[Observation]:
    """Parse `nmcli -t -f BSSID,SSID,SIGNAL dev wifi list`."""
    result: List[Observation] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = _split_nmcli(line)
        if len(fields) != 3:
            continue
        bssid, ssid, signal = fields
        if not re.fullmatch(r"[0-9A-Fa-f:]{17}", bssid):
            continue
        if ssid == "--":
            ssid = ""
        percent = int(signal) if signal.strip().isdigit() else None
        result.append(_observation(bssid, ssid, percent, now))
    return result


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(locale.getpreferredencoding(False) or "utf-8", errors="replace")


async def scan_once(now: float) -> List[Observation]:
    if sys.platform.startswith("win"):
        cmd = ["netsh", "wlan", "show", "networks", "mode=bssid"]
        parse = parse_netsh
    elif sys.platform.startswith("linux"):
        cmd = ["nmcli", "-t", "-f", "BSSID,SSID,SIGNAL", "dev", "wifi", "list", "--rescan", "yes"]
        parse = parse_nmcli
    else:
        raise WifiUnavailable("이 운영체제에서는 와이파이 목록을 읽을 수 없습니다.")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except (FileNotFoundError, PermissionError):
        raise WifiUnavailable(f"{cmd[0]} 명령을 찾을 수 없습니다.")
    try:
        out, _err = await asyncio.wait_for(proc.communicate(), timeout=SCAN_TIMEOUT_S)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()
        raise WifiUnavailable(f"{cmd[0]} 명령이 {int(SCAN_TIMEOUT_S)}초 안에 끝나지 않았습니다.")
    if proc.returncode != 0:
        raise WifiUnavailable(f"{cmd[0]} 명령이 오류로 끝났습니다(종료 코드 {proc.returncode}).")
    return parse(_decode(out), now)
