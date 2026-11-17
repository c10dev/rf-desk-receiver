"""BLE reception with bleak."""
from __future__ import annotations

import asyncio
import time
from typing import Callable

from .core import APPLE_COMPANY_ID, BLE, HINT_ORDER, Observation, apple_hint

MICROSOFT_COMPANY_ID = 0x0006
FAST_PAIR_UUID_PREFIX = "0000fe2c-"


def hint_from_advertisement(manufacturer_data: dict, service_data: dict, service_uuids: list):
    """Return the hint that comes first in HINT_ORDER, or None."""
    found = set()
    apple = manufacturer_data.get(APPLE_COMPANY_ID)
    if apple is not None:
        hint = apple_hint(bytes(apple))
        if hint:
            found.add(hint)
    microsoft = manufacturer_data.get(MICROSOFT_COMPANY_ID)
    if microsoft is not None and len(microsoft) > 0 and microsoft[0] == 0x01:
        found.add("WINDOWS")
    uuids = list(service_data.keys()) + list(service_uuids)
    if any(str(u).lower().startswith(FAST_PAIR_UUID_PREFIX) for u in uuids):
        found.add("FAST_PAIR")
    for hint in HINT_ORDER:
        if hint in found:
            return hint
    return None


async def run_ble(on_obs: Callable[[Observation], None]) -> None:
    from bleak import BleakScanner  # Import here so the rest of the program runs without bleak.

    def callback(device, adv) -> None:
        manufacturer = dict(adv.manufacturer_data or {})
        on_obs(
            Observation(
                source=BLE,
                address=device.address.upper(),
                name=adv.local_name,
                rssi=adv.rssi,
                t=time.time(),
                company_ids=frozenset(manufacturer.keys()),
                hint=hint_from_advertisement(manufacturer, dict(adv.service_data or {}), list(adv.service_uuids or [])),
            )
        )

    scanner = BleakScanner(detection_callback=callback, scanning_mode="active")
    await scanner.start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await scanner.stop()
