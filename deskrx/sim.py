"""Fixed simulated radio scenario."""
from __future__ import annotations

from .core import BLE, WIFI, Observation


def sim_observations(start: float, now: float, collect_s: float) -> list:
    w = start + collect_s  # The watch phase begins here.
    result = [
        Observation(WIFI, "10:00:00:00:00:01", "School-AP", -55, now),
        Observation(WIFI, "10:00:00:00:00:02", None, -70, now),
        Observation(BLE, "BB:00:00:00:00:01", "Teacher Watch", -60, now),
    ]
    if w + 5 <= now < w + 45:
        result.append(Observation(BLE, "AA:00:00:00:00:09", "Galaxy Buds2", -50, now))
    if now >= w + 10:
        result.append(Observation(WIFI, "DE:AD:BE:EF:00:01", None, -45, now))
    return result
