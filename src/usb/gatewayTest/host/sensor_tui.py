#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Fedora terminal UI for the AtomS3U USB sensor gateway.

Host counterpart of the MicroPython application sensor_test.py. Talks to
the device's vendor-specific bulk interface (interface 2, EP 0x03 OUT /
EP 0x83 IN) using the 4-byte framing defined by usb_channel_server.py:
channel:u8, msg_type:u8, length:u16 le, payload.

A background reader thread parses frames into an event queue; the curses
main loop drains it and redraws. Fixed channel map expected from the
device: 0 control, 1 button, 2 rgb, 3 espnow.

Keys: r/g/b/w/y set the LED colour, 0 turns it off, p ping, c channel
list, d toggle device debug, s request gateway status, x clear the
device debug log, q (or ESC) quit.

Requires pyusb. Optional --serial selects among several attached boards.
"""

from __future__ import annotations

import argparse
import curses
import queue
import signal
import threading
import time
from dataclasses import dataclass
from typing import Optional

import usb.core
import usb.util

VID = 0x303A
PID = 0x4001
INTERFACE = 2
EP_OUT = 0x03
EP_IN = 0x83

MSG_COMMAND = 0x02
MSG_RESPONSE = 0x03
MSG_EVENT = 0x04
MSG_CHANNEL_LIST_REQUEST = 0x05
MSG_CHANNEL_LIST_RESPONSE = 0x06
MSG_CHANNEL_ADDED = 0x07
MSG_CHANNEL_REMOVED = 0x08
MSG_ERROR = 0x09
MSG_PING = 0x0A
MSG_PONG = 0x0B
MSG_STATUS = 0x0C

CTRL_SET_DEBUG = 0x01
CTRL_GET_STATUS = 0x02
CTRL_CLEAR_DEBUG = 0x03

CHANNEL_CONTROL = 0
CHANNEL_BUTTON = 1
CHANNEL_RGB = 2
CHANNEL_ESPNOW = 3


@dataclass
class ChannelInfo:
    channel_id: int
    kind: int
    direction: int
    max_packet: int
    name: str


class ProtocolError(Exception):
    pass


class USBDisconnected(Exception):
    pass


class FrameParser:
    """Incremental parser for the 4-byte framed protocol. Invalid headers abort the buffer."""

    def __init__(self, max_payload=4096):
        self.buffer = bytearray()
        self.max_payload = max_payload

    def feed(self, data):
        self.buffer.extend(data)
        frames = []

        while len(self.buffer) >= 4:
            channel = self.buffer[0]
            msg_type = self.buffer[1]
            length = self.buffer[2] | (self.buffer[3] << 8)

            if channel == 255 or length > self.max_payload:
                self.buffer.clear()
                raise ProtocolError(
                    "invalid header channel=%d length=%d"
                    % (channel, length)
                )

            total = 4 + length
            if len(self.buffer) < total:
                break

            payload = bytes(self.buffer[4:total])
            del self.buffer[:total]
            frames.append((channel, msg_type, payload))

        return frames


class USBGateway:
    """PyUSB transport. Reader thread delivers (kind, data) tuples on .events.

    kind is "frame" with (channel, msg_type, payload) or "error" with a
    text description. The event queue drops its oldest entry when full so
    the device is never blocked by a slow consumer.
    """

    def __init__(self, serial=None, timeout_ms=100):
        self.serial = serial
        self.timeout_ms = timeout_ms
        self.dev = None
        self.claimed = False
        self.stop_event = threading.Event()
        self.reader_thread = None
        self.write_lock = threading.Lock()
        self.events = queue.Queue(maxsize=256)
        self.parser = FrameParser()
        self.rx_bytes = 0
        self.tx_bytes = 0
        self.errors = 0
        self.reader_alive = False
        self.reader_last_error = ""

    def _find(self):
        devices = usb.core.find(
            find_all=True,
            idVendor=VID,
            idProduct=PID,
        )
        for dev in devices:
            if self.serial is None:
                return dev
            try:
                if usb.util.get_string(dev, dev.iSerialNumber) == self.serial:
                    return dev
            except usb.core.USBError:
                continue
        return None

    def open(self):
        """Locate the device, claim the vendor interface and start the reader thread."""
        dev = self._find()
        if dev is None:
            raise USBDisconnected("device not found")

        try:
            dev.set_configuration()
        except usb.core.USBError as exc:
            if getattr(exc, "errno", None) != 16:
                raise

        if dev.is_kernel_driver_active(INTERFACE):
            raise RuntimeError("kernel driver owns interface 2")

        usb.util.claim_interface(dev, INTERFACE)
        self.dev = dev
        self.claimed = True
        self.stop_event.clear()
        self.reader_thread = threading.Thread(
            target=self._reader,
            daemon=True,
        )
        self.reader_thread.start()

    def close(self):
        """Stop the reader, release the interface and dispose USB resources."""
        self.stop_event.set()

        if self.reader_thread is not None:
            self.reader_thread.join(timeout=1.0)
            self.reader_thread = None

        dev = self.dev
        self.dev = None

        if dev is not None:
            try:
                if self.claimed:
                    usb.util.release_interface(dev, INTERFACE)
            finally:
                self.claimed = False
                usb.util.dispose_resources(dev)

    def send(self, channel, msg_type, payload=b""):
        """Send one frame. Raises USBDisconnected on device loss or short write."""
        if self.dev is None:
            raise USBDisconnected("device is not open")

        frame = (
            bytes((
                channel,
                msg_type,
                len(payload) & 0xFF,
                (len(payload) >> 8) & 0xFF,
            ))
            + payload
        )

        try:
            with self.write_lock:
                written = self.dev.write(
                    EP_OUT,
                    frame,
                    timeout=1000,
                )
            if written != len(frame):
                raise USBDisconnected(
                    "short write %d/%d" % (written, len(frame))
                )
            self.tx_bytes += written
        except usb.core.USBError as exc:
            self.errors += 1
            raise USBDisconnected(str(exc)) from exc

    def _put_event(self, event):
        try:
            self.events.put_nowait(event)
        except queue.Full:
            try:
                self.events.get_nowait()
            except queue.Empty:
                pass
            self.events.put_nowait(event)

    def _reader(self):
        """Reader thread: read bursts from EP_IN, parse and enqueue frames."""
        self.reader_alive = True
        try:
            while not self.stop_event.is_set():
                try:
                    data = bytes(
                        self.dev.read(
                            EP_IN,
                            4096,
                            timeout=self.timeout_ms,
                        )
                    )
                    self.rx_bytes += len(data)
                    for frame in self.parser.feed(data):
                        self._put_event(("frame", frame))
                except usb.core.USBTimeoutError:
                    continue
                except ProtocolError as exc:
                    self.errors += 1
                    if not self.stop_event.is_set():
                        self._put_event(("error", "protocol: " + str(exc)))
                    continue
                except usb.core.USBError as exc:
                    self.errors += 1
                    if not self.stop_event.is_set():
                        self._put_event(("error", "usb: " + str(exc)))
                    return
        except Exception as exc:
            self.errors += 1
            self.reader_last_error = "%s: %s" % (type(exc).__name__, exc)
            if not self.stop_event.is_set():
                self._put_event(("error", "reader stopped: " + self.reader_last_error))
        finally:
            self.reader_alive = False



def parse_channels(payload):
    """Decode a channel-list payload into {channel_id: ChannelInfo}."""
    if not payload:
        raise ProtocolError("empty channel list")

    count = payload[0]
    offset = 1
    channels = {}

    for _ in range(count):
        if offset + 6 > len(payload):
            raise ProtocolError("truncated channel descriptor")

        channel_id = payload[offset]
        kind = payload[offset + 1]
        direction = payload[offset + 2]
        max_packet = payload[offset + 3] | (payload[offset + 4] << 8)
        name_length = payload[offset + 5]
        offset += 6

        if offset + name_length > len(payload):
            raise ProtocolError("truncated channel name")

        name = payload[offset:offset + name_length].decode(
            "utf-8",
            "replace",
        )
        offset += name_length

        channels[channel_id] = ChannelInfo(
            channel_id,
            kind,
            direction,
            max_packet,
            name,
        )

    return channels


def parse_status(payload):
    """Decode the fixed 28-byte gateway status payload into a dict."""
    if len(payload) != 28:
        raise ProtocolError(
            "unexpected status length %d" % len(payload)
        )

    def u32(offset):
        return int.from_bytes(payload[offset:offset + 4], "little")

    return {
        "debug": bool(payload[0]),
        "interface_open": bool(payload[1]),
        "tx_busy": bool(payload[2]),
        "out_armed": bool(payload[3]),
        "rx_frames": u32(4),
        "tx_frames": u32(8),
        "parse_errors": u32(12),
        "usb_errors": u32(16),
        "tx_dropped": u32(20),
        "queued": int.from_bytes(payload[24:26], "little"),
        "debug_entries": int.from_bytes(payload[26:28], "little"),
    }


class TUI:
    """Curses front end: tracks gateway/sensor state and renders it."""

    COLORS = {
        ord("0"): (0, 0, 0),
        ord("r"): (255, 0, 0),
        ord("g"): (0, 255, 0),
        ord("b"): (0, 0, 255),
        ord("w"): (255, 255, 255),
        ord("y"): (255, 255, 0),
    }

    def __init__(self, gateway):
        self.gateway = gateway
        self.shutdown = threading.Event()
        self.channels = {}
        self.button = "unknown"
        self.rgb = (0, 0, 0)
        self.status = "starting"
        self.last_error = ""
        self.esp_messages = []
        self.gateway_status = None
        self.debug_requested = False

    def send_control(self, command, argument=None):
        """Send a CTRL_* command on the control channel."""
        payload = bytes((command,))
        if argument is not None:
            payload += bytes((argument,))
        self.gateway.send(CHANNEL_CONTROL, MSG_COMMAND, payload)

    def request_initial_state(self):
        """Ping, fetch the channel list and the gateway status."""
        self.gateway.send(CHANNEL_CONTROL, MSG_PING)
        self.gateway.send(
            CHANNEL_CONTROL,
            MSG_CHANNEL_LIST_REQUEST,
        )
        self.send_control(CTRL_GET_STATUS)

    def handle_frame(self, channel, msg_type, payload):
        """Update TUI state from one device frame."""
        if channel == CHANNEL_CONTROL:
            if msg_type == MSG_PONG:
                self.status = "controller online"
            elif msg_type == MSG_CHANNEL_LIST_RESPONSE:
                self.channels = parse_channels(payload)
            elif msg_type == MSG_CHANNEL_ADDED:
                descriptor = bytes((1,)) + payload
                self.channels.update(parse_channels(descriptor))
            elif msg_type == MSG_CHANNEL_REMOVED and payload:
                self.channels.pop(payload[0], None)
            elif msg_type == MSG_STATUS:
                self.gateway_status = parse_status(payload)
                self.debug_requested = self.gateway_status["debug"]
            elif msg_type == MSG_ERROR:
                related = payload[0] if len(payload) > 0 else -1
                code = payload[1] if len(payload) > 1 else -1
                text = payload[2:].decode("utf-8", "replace")
                self.last_error = (
                    "device error ch=%d code=%d: %s"
                    % (related, code, text)
                )
            return

        if channel == CHANNEL_BUTTON and msg_type == MSG_EVENT:
            if payload:
                self.button = "PRESSED" if payload[0] else "released"
            return

        if channel == CHANNEL_RGB and msg_type == MSG_RESPONSE:
            if len(payload) == 3:
                self.rgb = tuple(payload)
            return

        if channel == CHANNEL_ESPNOW and msg_type == MSG_EVENT:
            if len(payload) >= 7:
                mac = ":".join("%02x" % b for b in payload[:6])
                raw_rssi = payload[6]
                rssi = raw_rssi - 256 if raw_rssi >= 128 else raw_rssi
                data = payload[7:]
                try:
                    display = data.decode("utf-8")
                except UnicodeDecodeError:
                    display = data.hex(" ")
                self.esp_messages.append(
                    "%s %s RSSI %d: %s"
                    % (
                        time.strftime("%H:%M:%S"),
                        mac,
                        rssi,
                        display,
                    )
                )
                self.esp_messages = self.esp_messages[-8:]

    def drain_events(self):
        """Apply all pending reader-thread events to the TUI state."""
        while True:
            try:
                kind, data = self.gateway.events.get_nowait()
            except queue.Empty:
                return

            if kind == "frame":
                self.handle_frame(*data)
            else:
                self.last_error = data

    def draw(self, screen):
        """Redraw the whole (single-page) status screen."""
        screen.erase()
        rows, columns = screen.getmaxyx()

        def line(row, text):
            if row < rows:
                screen.addnstr(row, 0, text, max(0, columns - 1))

        line(0, "AtomS3U Sensor Gateway")
        line(1, "=" * min(72, columns - 1))
        line(3, "Status: " + self.status)
        line(4, "Button GPIO41: " + self.button)
        line(5, "RGB GPIO35: %r" % (self.rgb,))
        line(
            6,
            "Host USB RX/TX: %d/%d bytes; reader=%s"
            % (
                self.gateway.rx_bytes,
                self.gateway.tx_bytes,
                "alive" if self.gateway.reader_alive else "stopped",
            ),
        )

        if self.gateway_status:
            status = self.gateway_status
            line(
                7,
                "Gateway debug=%s open=%s out=%s tx_busy=%s queue=%d"
                % (
                    status["debug"],
                    status["interface_open"],
                    status["out_armed"],
                    status["tx_busy"],
                    status["queued"],
                ),
            )
            line(
                8,
                "Frames RX/TX=%d/%d parse=%d usb=%d dropped=%d log=%d"
                % (
                    status["rx_frames"],
                    status["tx_frames"],
                    status["parse_errors"],
                    status["usb_errors"],
                    status["tx_dropped"],
                    status["debug_entries"],
                ),
            )

        line(10, "Channels:")
        row = 11
        for channel_id in sorted(self.channels):
            channel = self.channels[channel_id]
            line(
                row,
                "  %3d %-18s kind=%d dir=%d max=%d"
                % (
                    channel.channel_id,
                    channel.name,
                    channel.kind,
                    channel.direction,
                    channel.max_packet,
                ),
            )
            row += 1

        row += 1
        line(row, "ESP-NOW messages:")
        row += 1
        # show only the last two messages to avoid cluttering the screen
        for message in self.esp_messages[-2:]:
            line(row, "  " + message)
            row += 1

        footer = max(row + 1, rows - 4)
        line(
            footer,
            "Keys: r/g/b/w/y LED, 0 off, p ping, c channels, "
            "d debug, s status, x clear log, q quit",
        )
        if self.last_error:
            line(footer + 1, "Error: " + self.last_error)

        screen.refresh()

    def run(self, screen):
        """Curses main loop: drain events, redraw, dispatch key presses."""
        curses.curs_set(0)
        screen.nodelay(True)
        screen.timeout(100)

        self.request_initial_state()

        while not self.shutdown.is_set():
            self.drain_events()
            self.draw(screen)

            key = screen.getch()
            if key == -1:
                continue

            try:
                if key in (ord("q"), 27):
                    self.shutdown.set()
                elif key in self.COLORS:
                    self.gateway.send(
                        CHANNEL_RGB,
                        MSG_COMMAND,
                        bytes(self.COLORS[key]),
                    )
                elif key == ord("p"):
                    self.gateway.send(CHANNEL_CONTROL, MSG_PING)
                elif key == ord("c"):
                    self.gateway.send(
                        CHANNEL_CONTROL,
                        MSG_CHANNEL_LIST_REQUEST,
                    )
                elif key == ord("d"):
                    self.send_control(
                        CTRL_SET_DEBUG,
                        0 if self.debug_requested else 1,
                    )
                elif key == ord("s"):
                    self.send_control(CTRL_GET_STATUS)
                elif key == ord("x"):
                    self.send_control(CTRL_CLEAR_DEBUG)
            except Exception as exc:
                self.last_error = str(exc)


def main():
    """Entry point: open the gateway and run the TUI until quit or signal."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial")
    args = parser.parse_args()

    gateway = USBGateway(serial=args.serial)
    tui = TUI(gateway)

    def shutdown_handler(signum, frame):
        tui.shutdown.set()

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        gateway.open()
        curses.wrapper(tui.run)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        raise SystemExit("fatal: %s" % exc) from exc
    finally:
        gateway.close()


if __name__ == "__main__":
    main()
