"""History of new signals (start and end) and its JSONL record."""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .core import View, device_label


@dataclass
class Event:
    key: str
    label: str
    source: str
    started: float
    last_seen: float
    ended: Optional[float]
    peak: Optional[int]


@dataclass(frozen=True)
class EventSummary:
    key: str
    label: str
    source: str
    count: int  # closed events with this key
    first_started: float
    last_ended: float
    peak: Optional[int]  # strongest peak over those events


def _ended(ev: Event) -> float:
    return ev.ended if ev.ended is not None else ev.last_seen


def summarize(closed: list) -> list:
    """One summary per key. Label and source come from the newest event of the key."""
    by_key: dict = {}
    for ev in closed:
        by_key.setdefault(ev.key, []).append(ev)
    result = []
    for key, events in by_key.items():
        newest = max(events, key=_ended)
        peaks = [e.peak for e in events if e.peak is not None]
        result.append(
            EventSummary(
                key=key,
                label=newest.label,
                source=newest.source,
                count=len(events),
                first_started=min(e.started for e in events),
                last_ended=_ended(newest),
                peak=max(peaks) if peaks else None,
            )
        )
    result.sort(key=lambda x: x.last_ended, reverse=True)
    return result


def iso_local(t: Optional[float]) -> Optional[str]:
    return None if t is None else datetime.fromtimestamp(t).isoformat(timespec="seconds")


class EventLog:
    def __init__(self, path: Optional[pathlib.Path]) -> None:
        self._path = pathlib.Path(path) if path else None
        self._file = None
        self._open: dict = {}
        self._closed: list = []

    def _write(self, kind: str, ev: Event) -> None:
        if self._path is None:
            return
        if self._file is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(self._path, "a", encoding="utf-8")
        line = {
            "type": kind,
            "key": ev.key,
            "label": ev.label,
            "source": ev.source,
            "started": iso_local(ev.started),
            "last_seen": iso_local(ev.last_seen),
            "ended": iso_local(ev.ended),
            "peak": ev.peak,
        }
        self._file.write(json.dumps(line, ensure_ascii=False) + "\n")
        self._file.flush()

    def update(self, view: View, now: float) -> None:
        present = {row.key: row for row in view.new + view.far}
        for key, row in present.items():
            peaks = [d.peak for d in row.devices if d.peak is not None]
            peak = max(peaks) if peaks else None
            first_packet = min(d.period_start for d in row.devices)
            last_packet = max(d.last_seen for d in row.devices)
            ev = self._open.get(key)
            if ev is None:
                ev = Event(key, device_label(row.strongest), row.strongest.source, first_packet, last_packet, None, peak)
                self._open[key] = ev
                self._write("start", ev)
            else:
                ev.last_seen = last_packet
                if peak is not None and (ev.peak is None or peak > ev.peak):
                    ev.peak = peak
        for key in [k for k in self._open if k not in present]:
            ev = self._open.pop(key)
            ev.ended = now
            self._closed.insert(0, ev)
            self._write("end", ev)

    @property
    def open(self) -> list:
        return list(self._open.values())

    @property
    def closed(self) -> list:
        return list(self._closed)

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
