#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Fedora terminal UI for the AtomS3U USB sensor gateway.

Host counterpart of the MicroPython application sensor_test.py. Talks to
the device's vendor-specific bulk interface (interface 2, EP 0x03 OUT /
EP 0x83 IN) using the 4-byte framing defined by usb_channel_server.py:
channel:u8, msg_type:u8, length:u16 le, payload.

A background reader thread parses frames into an event queue; the curses
main loop drains it and redraws. Fixed channel map expected from the
device: 0 control, 1 button, 2 rgb, 3 espnow/wifi.

Keys: r/g/b/w/y set the LED colour, 0 turns it off, p ping, c channel
list, d toggle device debug, s request gateway status, x clear the
device debug log, Enter send message, q (or ESC) quit.

Requires pyusb. Optional --serial selects among several attached boards.
Use -e for ESP-NOW mode or -w for WiFi mode.
"""

from __future__ import annotations

import argparse
import curses
import json
import os
import queue
import signal
import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional

import usb.core
import usb.util

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from channel_defs import (
    MSG_COMMAND,
    MSG_RESPONSE,
    MSG_EVENT,
    MSG_CHANNEL_LIST_REQUEST,
    MSG_CHANNEL_LIST_RESPONSE,
    MSG_CHANNEL_ADDED,
    MSG_CHANNEL_REMOVED,
    MSG_ERROR,
    MSG_PING,
    MSG_PONG,
    MSG_STATUS,
    MSG_PEER_ADD,
    MSG_PEER_DEL,
    CTRL_SET_DEBUG,
    CTRL_GET_STATUS,
    CTRL_CLEAR_DEBUG,
    CHANNEL_CONTROL,
    CHANNEL_BUTTON,
    CHANNEL_RGB,
    CHANNEL_ESPNOW,
)

VID = 0x303A
PID = 0x4001
INTERFACE = 2
EP_OUT = 0x03
EP_IN = 0x83


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

    # Path to stick directory for peers.json
    PEERS_PATH = os.path.join(os.path.dirname(__file__), "..", "stick", "peers.json")

    def __init__(self, gateway, use_wifi=False, use_espnow=False):
        self.gateway = gateway
        self.use_wifi = use_wifi
        self.use_espnow = use_espnow
        # Determine which channel to use for messaging
        # WiFi and ESP-NOW both use channel 3
        self.wireless_channel = CHANNEL_ESPNOW if (use_wifi or use_espnow) else None
        self.shutdown = threading.Event()
        self.channels = {}
        self.button = "unknown"
        self.rgb = (0, 0, 0)
        self.status = "starting"
        self.last_error = ""
        self.esp_messages = []
        self.wifi_clients = []  # Seen WiFi client IPs
        self.gateway_status = None
        self.debug_requested = False
        self.peers = []
        self.input_text = ""
        self.input_peer = 0
        self.input_mode = False
        self.last_action = ""
        # Only load peers for ESP-NOW mode (WiFi doesn't use MAC-based peers)
        if not use_wifi:
            self._load_peers_from_file()

    def _load_peers_from_file(self):
        """Load peers from peers.json (but don't send to device yet)."""
        try:
            peers_path = os.path.normpath(self.PEERS_PATH)
            if os.path.exists(peers_path):
                with open(peers_path, "r") as f:
                    self.peers = json.load(f)
                print(f"Loaded {len(self.peers)} peers from {peers_path}")
            else:
                print(f"Peers file not found: {peers_path}")
        except Exception as e:
            print(f"Failed to load peers: {e}")
            self.peers = []

    def _send_peers_to_device(self):
        """Send all peers to the ESP-NOW server via peer_add messages."""
        if self.gateway is None:
            return
        for peer in self.peers:
            try:
                mac_hex = peer.get("mac", "")
                lmk_hex = peer.get("lmk", "")
                mac = bytes.fromhex(mac_hex)
                lmk = bytes.fromhex(lmk_hex) if lmk_hex else None

                payload = mac
                if lmk:
                    payload += lmk

                self.gateway.send(CHANNEL_ESPNOW, MSG_PEER_ADD, payload)
                print(f"Sent peer_add for {mac_hex}")
            except Exception as e:
                print(f"Failed to send peer_add for {peer.get('mac')}: {e}")

    def _save_and_clear_log(self):
        """Save ESP-NOW messages and status to sensor_test.log and clear them."""
        try:
            with open("sensor_test.log", "a") as f:
                f.write(f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                if self.gateway_status:
                    f.write(f"Status: RX={self.gateway_status['rx_frames']} TX={self.gateway_status['tx_frames']} "
                            f"parse={self.gateway_status['parse_errors']} usb={self.gateway_status['usb_errors']}\n")
                if self.esp_messages:
                    mode = "WiFi" if self.use_wifi else "ESP-NOW"
                    f.write(f"{mode} messages:\n")
                    for msg in self.esp_messages:
                        f.write(f"  {msg}\n")
                f.write("\n")
        except Exception as e:
            self.last_error = f"Failed to save log: {e}"
        self.esp_messages = []
        self.send_control(CTRL_CLEAR_DEBUG)

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
        # Only send peers for ESP-NOW mode
        if not self.use_wifi:
            self._send_peers_to_device()

    def send_espnow_message(self, peer_index, message):
        """Send a message to a specific peer via wireless channel (ESP-NOW or WiFi).

        Payload format: peer_index:u8 + message:string
        """
        if self.wireless_channel is None:
            self.last_error = "No wireless channel configured (use -e or -w)"
            return False

        # Use appropriate client list based on mode
        if self.use_wifi:
            client_list = self.wifi_clients
        else:
            client_list = self.peers

        if peer_index >= len(client_list):
            self.last_error = f"Invalid peer index {peer_index}"
            return False

        payload = bytes([peer_index]) + message.encode()
        try:
            print(f"DEBUG: Sending to channel {self.wireless_channel}, payload={payload.hex()}")
            self.gateway.send(self.wireless_channel, MSG_COMMAND, payload)
            mode = "WiFi" if self.use_wifi else "ESP-NOW"
            self.last_action = f"sent via {mode} to peer {peer_index}: {message[:20]}"
            return True
        except Exception as e:
            self.last_error = f"Send failed: {e}"
            return False

    def handle_frame(self, channel, msg_type, payload):
        """Update TUI state from one device frame."""
        if channel == CHANNEL_CONTROL:
            if msg_type == MSG_PONG:
                self.status = "controller online"
                self.last_action = ""
            elif msg_type == MSG_CHANNEL_LIST_RESPONSE:
                self.channels = parse_channels(payload)
                self.last_action = ""
            elif msg_type == MSG_CHANNEL_ADDED:
                descriptor = bytes((1,)) + payload
                self.channels.update(parse_channels(descriptor))
            elif msg_type == MSG_CHANNEL_REMOVED and payload:
                self.channels.pop(payload[0], None)
            elif msg_type == MSG_STATUS:
                self.gateway_status = parse_status(payload)
                self.last_action = ""
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
            if len(payload) >= 6:
                if self.use_wifi:
                    # WiFi: payload = IP(4) + peer_index(1) + message
                    mac = payload[:4].hex()
                    if len(payload) > 4:
                        data = payload[5:]  # Skip peer_index
                    else:
                        data = b""
                    rssi_str = ""

                    # Show IP instead of MAC for WiFi
                    try:
                        ip_bytes = bytes.fromhex(mac[:8])
                        client_ip = f"{ip_bytes[0]}.{ip_bytes[1]}.{ip_bytes[2]}.{ip_bytes[3]}"
                        peer_label = client_ip

                        # Track unique client IPs
                        if client_ip not in self.wifi_clients:
                            self.wifi_clients.append(client_ip)
                    except Exception:
                        peer_label = mac
                else:
                    # ESP-NOW: payload = MAC(6) + RSSI(1) + data
                    mac = payload[:6].hex()
                    if len(payload) >= 7:
                        raw_rssi = payload[6]
                        rssi = raw_rssi - 256 if raw_rssi >= 128 else raw_rssi
                        rssi_str = f" RSSI {rssi}"
                        data = payload[7:]
                    else:
                        rssi_str = ""
                        data = b""

                    # Find matching peer index
                    peer_label = mac
                    for idx, peer in enumerate(self.peers):
                        if peer.get("mac", "").lower() == mac.lower():
                            peer_label = f"Peer {idx}"
                            break

                try:
                    display = data.decode("utf-8")
                except UnicodeDecodeError:
                    display = data.hex(" ")

                self.esp_messages.append(
                    "%s %s%s: %s"
                    % (
                        time.strftime("%H:%M:%S"),
                        peer_label,
                        rssi_str,
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
        line(1, "Status: %s | Button: %s | RGB: %r%s" % (self.status, self.button, self.rgb, " | " + self.last_action if self.last_action else ""))

        if self.gateway_status:
            status = self.gateway_status
            line(2, "RX=%d TX=%d q=%d | debug=%s open=%s"
                 % (status["rx_frames"], status["tx_frames"], status["queued"],
                    status["debug"], status["interface_open"]))

        line(3, "Channels: " + ", ".join("%d:%s" % (c.channel_id, c.name) for c in sorted(self.channels.values(), key=lambda x: x.channel_id)))

        row = 4
        if self.esp_messages:
            mode = "WiFi" if self.use_wifi else "ESP-NOW"
            line(row, "%s: %s" % (mode, self.esp_messages[-1]))
            row += 1

        if self.input_mode:
            if self.use_wifi:
                # WiFi mode: use seen client IPs
                client_list = self.wifi_clients
            else:
                # ESP-NOW mode: use peers from file
                client_list = self.peers

            if client_list and 0 <= self.input_peer < len(client_list):
                if self.use_wifi:
                    peer_label = client_list[self.input_peer]  # IP string
                else:
                    peer_label = client_list[self.input_peer].get("mac", "unknown")
                line(row, "To peer %d (%s): %s" % (self.input_peer, peer_label, self.input_text))
            else:
                count = len(client_list) if client_list else 0
                line(row, "Peer [0-%d]: %s" % (count - 1 if count > 0 else 0, self.input_text))
            row += 1
            line(row, "Enter=send, Esc=cancel, Up/Down=peer")
        else:
            line(row, "Keys: r/g/b/w/y/0=RGB, p/c/d/s/x/m/q")

        footer = max(row + 2, rows - 2)
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
                if self.input_mode:
                    # Handle input mode
                    if key in (ord("\n"), curses.KEY_ENTER):
                        # Send message
client_list = self.wifi_clients if self.use_wifi else self.peers
                    if self.input_text.strip() and client_list:
                        self.send_espnow_message(self.input_peer, self.input_text.strip())
                        self.input_text = ""
                        self.input_mode = False
                        curses.curs_set(0)
                    elif key == 27:  # Escape
                        self.input_text = ""
                        self.input_mode = False
                        curses.curs_set(0)
                    elif key in (curses.KEY_BACKSPACE, 127, 8):
                        # Backspace
                        self.input_text = self.input_text[:-1]
                    elif key == curses.KEY_UP:
                        # Previous peer
                        client_list = self.wifi_clients if self.use_wifi else self.peers
                        if client_list:
                            self.input_peer = (self.input_peer - 1) % len(client_list)
                    elif key == curses.KEY_DOWN:
                        # Next peer
                        client_list = self.wifi_clients if self.use_wifi else self.peers
                        if client_list:
                            self.input_peer = (self.input_peer + 1) % len(client_list)
                    elif 32 <= key <= 126:
                        # Printable character
                        self.input_text += chr(key)
                elif key in (ord("q"), 27):
                    self.shutdown.set()
                elif key == ord("m"):
                    # Enter message mode
                    client_list = self.wifi_clients if self.use_wifi else self.peers
                    if client_list:
                        self.input_mode = True
                        self.input_text = ""
                        self.input_peer = 0
                        curses.curs_set(1)
                    else:
                        self.last_error = "No peers configured"
                elif key in self.COLORS:
                    self.gateway.send(
                        CHANNEL_RGB,
                        MSG_COMMAND,
                        bytes(self.COLORS[key]),
                    )
                elif key == ord("p"):
                    self.gateway.send(CHANNEL_CONTROL, MSG_PING)
                    self.last_action = "ping sent"
                elif key == ord("c"):
                    self.gateway.send(
                        CHANNEL_CONTROL,
                        MSG_CHANNEL_LIST_REQUEST,
                    )
                    self.last_action = "channels requested"
                elif key == ord("d"):
                    self.send_control(
                        CTRL_SET_DEBUG,
                        0 if self.debug_requested else 1,
                    )
                    self.last_action = "debug toggled"
                elif key == ord("s"):
                    self.send_control(CTRL_GET_STATUS)
                    self.last_action = "status requested"
                elif key == ord("x"):
                    self._save_and_clear_log()
                    self.last_action = "log saved"
            except Exception as exc:
                self.last_error = str(exc)


def main():
    """Entry point: open the gateway and run the TUI until quit or signal."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial")
    parser.add_argument(
        "-e", "--espnow",
        action="store_true",
        help="Use ESP-NOW radio (channel 3)"
    )
    parser.add_argument(
        "-w", "--wifi",
        action="store_true",
        help="Use WiFi server (channel 3)"
    )
    args = parser.parse_args()

    # Validate mutually exclusive options
    if args.espnow and args.wifi:
        raise SystemExit("Error: -e (espnow) and -w (wifi) cannot be used together")

    gateway = USBGateway(serial=args.serial)
    tui = TUI(gateway, use_wifi=args.wifi, use_espnow=args.espnow)

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
