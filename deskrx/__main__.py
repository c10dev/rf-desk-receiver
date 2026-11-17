"""CLI: collect an empty-room record, then watch for new signals."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import pathlib
import sys
import time
from datetime import datetime
from typing import Optional

from .core import Baseline, Observation, Tracker, capture_baseline, watch
from .events import EventLog
from .sim import sim_observations
from .ui import render
from .wifi import WifiUnavailable, scan_once

WIFI_INTERVAL_S = 30.0
BLE_RETRY_S = 10.0
CLEAR = "\x1b[2J\x1b[H"


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="deskrx", description="교탁 수신 프로그램")
    p.add_argument("--collect-seconds", type=float, default=120.0, help="빈 교실 수집 시간(초)")
    p.add_argument("--records", type=pathlib.Path, default=pathlib.Path("records"), help="기록 폴더")
    p.add_argument("--no-ble", action="store_true", help="BLE 수신을 끈다")
    p.add_argument("--no-wifi", action="store_true", help="와이파이 수신을 끈다")
    p.add_argument("--use-saved", action="store_true", help="저장된 빈 교실 기록으로 바로 감시한다")
    p.add_argument("--raw-log", action="store_true", help="모든 관측을 CSV로 남긴다")
    p.add_argument("--sim", action="store_true", help="가상 전파 시나리오를 쓴다")
    p.add_argument("--auto-baseline", action="store_true", help="수집이 끝나면 Enter 없이 감시한다")
    p.add_argument("--duration", type=float, default=None, help="감시 시간(초). 지나면 종료 코드 0으로 끝낸다")
    return p.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    loop = asyncio.get_running_loop()
    records: pathlib.Path = args.records
    records.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    baseline_path = records / "baseline.json"
    events = EventLog(records / f"events-{stamp}.jsonl")
    tracker = Tracker()

    raw_file = None
    raw_writer = None
    if args.raw_log:
        raw_file = open(records / f"obs-{stamp}.csv", "w", newline="", encoding="utf-8")
        raw_writer = csv.writer(raw_file)
        raw_writer.writerow(["time", "source", "address", "name", "rssi", "group"])

    ble_on = not args.no_ble and not args.sim
    wifi_on = not args.no_wifi and not args.sim
    if args.sim:
        ble_on = wifi_on = True
    health = {"ble_age": None, "ble_error": None, "wifi_age": None, "wifi_error": None, "ble_on": ble_on, "wifi_on": wifi_on}
    last = {"ble": None, "wifi": None}

    def on_obs(obs: Observation) -> None:
        tracker.update(obs)
        key = "ble" if obs.source == "BLE" else "wifi"
        last[key] = obs.t
        if key == "ble":
            health["ble_error"] = None
        if raw_writer is not None:
            raw_writer.writerow([
                datetime.fromtimestamp(obs.t).isoformat(timespec="seconds"), obs.source, obs.address,
                obs.name or "", "" if obs.rssi is None else obs.rssi, tracker.group_of(obs.address),
            ])
            raw_file.flush()

    async def ble_task() -> None:
        from .ble import run_ble
        while True:
            try:
                await run_ble(on_obs)
                health["ble_error"] = "BLE 수신이 멈췄습니다"
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # bleak raises many kinds of errors
                health["ble_error"] = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(BLE_RETRY_S)

    async def wifi_task() -> None:
        while True:
            try:
                for obs in await scan_once(time.time()):
                    on_obs(obs)
                health["wifi_error"] = None
                last["wifi"] = time.time()
            except WifiUnavailable as exc:
                health["wifi_error"] = str(exc)
            await asyncio.sleep(WIFI_INTERVAL_S)

    tasks = []
    if ble_on and not args.sim:
        tasks.append(asyncio.create_task(ble_task()))
    if wifi_on and not args.sim:
        tasks.append(asyncio.create_task(wifi_task()))

    started = time.time()
    phase = "collect"
    baseline: Optional[Baseline] = None
    watch_start = 0.0
    stdin_task = None
    tty = sys.stdout.isatty()
    if tty and os.name == "nt":
        os.system("")  # turn on ANSI escape codes in the Windows console

    def begin_watch(now: float) -> None:
        nonlocal phase, watch_start, baseline
        if baseline is None:
            baseline = capture_baseline(tracker.devices(now), now)
            baseline_path.write_text(json.dumps(baseline.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
        phase = "watch"
        watch_start = now

    if args.use_saved:
        if not baseline_path.exists():
            print(f"저장된 빈 교실 기록이 없습니다: {baseline_path}", file=sys.stderr)
            return 2
        baseline = Baseline.from_json(json.loads(baseline_path.read_text(encoding="utf-8")))
        begin_watch(started)

    tick = 0
    try:
        while True:
            now = time.time()
            if args.sim:
                for obs in sim_observations(started, now, args.collect_seconds):
                    on_obs(obs)
                last["ble"] = last["wifi"] = now
            health["ble_age"] = None if last["ble"] is None else now - last["ble"]
            health["wifi_age"] = None if last["wifi"] is None else now - last["wifi"]

            collect_left = max(0.0, args.collect_seconds - (now - started))
            if phase == "collect" and collect_left <= 0 and tracker.devices(now):
                if args.auto_baseline:
                    begin_watch(now)
                else:
                    phase = "ready"
                    stdin_task = loop.run_in_executor(None, sys.stdin.readline)
            if phase == "ready" and stdin_task.done():
                stdin_task = None
                begin_watch(now)

            view = None
            if phase == "watch":
                view = watch(tracker.devices(now), baseline, now)
                events.update(view, now)
            text = render(phase, now, started, view, events, health, collect_left)
            if tty:
                sys.stdout.write(CLEAR + text + "\n")
                sys.stdout.flush()
            elif tick % 5 == 0:
                print("=" * 60)
                print(text, flush=True)
            tick += 1

            if phase == "watch" and args.duration is not None and now - watch_start >= args.duration:
                return 0
            await asyncio.sleep(1.0)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        events.close()
        if raw_file is not None:
            raw_file.close()
        if stdin_task is not None and not stdin_task.done():
            sys.stdout.flush()
            os._exit(0)  # A blocked stdin read cannot be cancelled.


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
