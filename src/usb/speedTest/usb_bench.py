#!/usr/bin/env python3
"""
Linux USB bulk echo benchmark for the M5Stack AtomS3U.

Requirements:
    sudo apt install python3-usb
or:
    python3 -m pip install pyusb

Examples:
    python3 usb_bench.py --duration 10 --size 4096
    python3 usb_bench.py --duration 10 --size 1024 --serial 30eda0c9de440000

The benchmark sends a variable-length binary block to EP 0x03 and reads the
echo from EP 0x83. USB access runs in a worker thread so the main application
remains asyncio-compatible.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass

import usb.core
import usb.util

VID = 0x303A
PID = 0x4001
INTERFACE = 2
EP_OUT = 0x03
EP_IN = 0x83
MAX_TRANSFER = 4096


@dataclass
class Results:
    transfers: int = 0
    payload_bytes: int = 0
    errors: int = 0


def find_device(serial: str | None):
    devices = usb.core.find(find_all=True, idVendor=VID, idProduct=PID)
    for dev in devices:
        if serial is None:
            return dev
        try:
            if usb.util.get_string(dev, dev.iSerialNumber) == serial:
                return dev
        except usb.core.USBError:
            continue
    return None


class AtomS3U:
    def __init__(self, serial: str | None, timeout_ms: int):
        self.dev = find_device(serial)
        if self.dev is None:
            raise RuntimeError(
                f"USB device {VID:04x}:{PID:04x}"
                + (f" serial {serial}" if serial else "")
                + " not found"
            )
        self.timeout_ms = timeout_ms
        self.claimed = False
        self._open()

    def _open(self):
        # Do not detach cdc_acm from interfaces 0/1. Claim only interface 2.
        try:
            self.dev.set_configuration()
        except usb.core.USBError as exc:
            # EBUSY is commonly harmless if the existing configuration is
            # already active and CDC is in use.
            if getattr(exc, "errno", None) not in (16,):
                raise

        if self.dev.is_kernel_driver_active(INTERFACE):
            raise RuntimeError(
                "Kernel driver unexpectedly owns vendor interface 2"
            )

        usb.util.claim_interface(self.dev, INTERFACE)
        self.claimed = True

    def close(self):
        if self.claimed:
            usb.util.release_interface(self.dev, INTERFACE)
            self.claimed = False
        usb.util.dispose_resources(self.dev)

    def exchange(self, payload: bytes) -> bytes:
        written = self.dev.write(
            EP_OUT, payload, timeout=self.timeout_ms
        )
        if written != len(payload):
            raise IOError(f"short USB write: {written}/{len(payload)}")

        received = self.dev.read(
            EP_IN, len(payload), timeout=self.timeout_ms
        )
        return bytes(received)


def make_payload(size: int, sequence: int) -> bytes:
    # Deterministic binary data, including all byte values. The first four
    # bytes change each transfer to catch stale or repeated echoes.
    data = bytearray(size)
    seq = sequence & 0xFFFFFFFF
    if size >= 4:
        data[0:4] = seq.to_bytes(4, "little")
        start = 4
    else:
        start = 0
    for i in range(start, size):
        data[i] = (i * 37 + sequence * 17) & 0xFF
    return bytes(data)


async def run_benchmark(
    device: AtomS3U,
    duration: float,
    size: int,
    report_interval: float,
) -> Results:
    result = Results()
    started = time.monotonic()
    last_report = started
    last_bytes = 0
    sequence = 0

    while True:
        now = time.monotonic()
        if now - started >= duration:
            break

        payload = make_payload(size, sequence)
        try:
            echoed = await asyncio.to_thread(device.exchange, payload)
            if echoed != payload:
                raise IOError(
                    f"data mismatch at transfer {sequence}: "
                    f"sent {len(payload)}, received {len(echoed)}"
                )
        except Exception:
            result.errors += 1
            raise

        result.transfers += 1
        result.payload_bytes += len(payload)
        sequence += 1

        now = time.monotonic()
        if now - last_report >= report_interval:
            interval = now - last_report
            interval_bytes = result.payload_bytes - last_bytes
            one_way_bps = interval_bytes / interval
            print(
                f"{one_way_bps / 1000:9.1f} kB/s one-way, "
                f"{one_way_bps * 8 / 1000:9.1f} kbit/s, "
                f"{result.transfers} transfers",
                flush=True,
            )
            last_report = now
            last_bytes = result.payload_bytes

    elapsed = time.monotonic() - started
    one_way_bps = result.payload_bytes / elapsed
    print()
    print(f"elapsed:             {elapsed:.3f} s")
    print(f"transfer size:       {size} bytes")
    print(f"transfers:           {result.transfers}")
    print(f"verified one-way:    {one_way_bps / 1000:.1f} kB/s")
    print(f"verified one-way:    {one_way_bps * 8 / 1000:.1f} kbit/s")
    print(f"USB round-trip data: {2 * one_way_bps / 1000:.1f} kB/s")
    print(f"errors:              {result.errors}")
    return result


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--size", type=int, default=4096)
    parser.add_argument("--timeout-ms", type=int, default=2000)
    parser.add_argument("--report-interval", type=float, default=1.0)
    parser.add_argument("--serial")
    args = parser.parse_args()

    if not 1 <= args.size <= MAX_TRANSFER:
        parser.error(f"--size must be between 1 and {MAX_TRANSFER}")
    if args.duration <= 0:
        parser.error("--duration must be positive")
    return args


async def async_main() -> int:
    args = parse_args()
    try:
        device = AtomS3U(args.serial, args.timeout_ms)
    except usb.core.USBError as exc:
        print(f"USB open failed: {exc}", file=sys.stderr)
        print(
            "Check the udev rule or run once as root for diagnosis.",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(f"Open failed: {exc}", file=sys.stderr)
        return 2

    try:
        await run_benchmark(
            device,
            duration=args.duration,
            size=args.size,
            report_interval=args.report_interval,
        )
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Benchmark failed: {exc}", file=sys.stderr)
        return 1
    finally:
        device.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
