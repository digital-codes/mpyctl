# SPDX-License-Identifier: AGPL-3.0-only
# usb_channel_server.py
# Generic USB framed channel server. No sensor imports.
#
# Wire format (little-endian):
#   channel   u8    0 = control, 1..254 application, 255 invalid
#   msg type  u8    MSG_* (see below)
#   length    u16   payload length in bytes
#   payload   bytes <= max_payload
#
# Channels are registered dynamically with a kind, direction (host view),
# maximum packet size, name and an optional inbound handler.
#
# The control channel (0) answers PING with PONG ("AS3U" + version byte),
# serves channel list requests, and handles CTRL_* commands wrapped in
# MSG_COMMAND (debug switch, status readout, debug log clear).
#
# TX path note: submit_xfer() may complete synchronously on current
# ESP32-S3 MicroPython builds, so an IN transfer is marked busy BEFORE it
# is submitted. See the README "Important implementation detail" section.

import time

MSG_DATA = 0x01
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

KIND_CONTROL = 0

DIR_IN = 1
DIR_OUT = 2
DIR_BIDI = 3

CHANNEL_CONTROL = 0

CTRL_SET_DEBUG = 0x01
CTRL_GET_STATUS = 0x02
CTRL_CLEAR_DEBUG = 0x03

_default_gateway = None


class USBGatewayError(Exception):
    pass


class USBProtocolError(USBGatewayError):
    pass


class USBQueueFull(USBGatewayError):
    pass


def set_default_gateway(gateway):
    """Publish the gateway singleton used by sensor modules via get_gateway()."""
    global _default_gateway
    _default_gateway = gateway


def get_gateway():
    """Return the process-wide gateway. Raises if boot.py has not run."""
    if _default_gateway is None:
        raise RuntimeError("USB gateway is not initialized")
    return _default_gateway


def _u16(value):
    return bytes((value & 0xFF, (value >> 8) & 0xFF))


def _u32(value):
    return bytes((
        value & 0xFF,
        (value >> 8) & 0xFF,
        (value >> 16) & 0xFF,
        (value >> 24) & 0xFF,
    ))


class USBChannelServer:
    """Framed multi-channel transport over one bulk endpoint pair.

    Owns RX framing/dispatch and a single-flight TX queue, tracks USB
    interface state through the callbacks installed by boot.py, and
    offers a runtime debug log. Channel 0 (control) is always present.
    """

    def __init__(
        self,
        usbd,
        interface,
        ep_out,
        ep_in,
        rx_size=4096,
        max_payload=1024,
        tx_queue_depth=32,
        debug_limit=64,
    ):
        self.usbd = usbd
        self.interface = interface
        self.ep_out = ep_out
        self.ep_in = ep_in

        self.rx_buffer = bytearray(rx_size)
        self.rx_view = memoryview(self.rx_buffer)
        self.rx_pending = bytearray()

        self.max_payload = max_payload
        self.tx_queue_depth = tx_queue_depth
        self.tx_queue = []
        self.tx_active = None
        self.tx_offset = 0
        # submit_xfer() receives a persistent mutable buffer. Some ESP32
        # MicroPython builds can leave IN transfers pending when passed a
        # temporary or immutable object.
        self.tx_buffer = bytearray(max_payload + 4)
        self.tx_view = memoryview(self.tx_buffer)
        self.tx_length = 0

        self.channels = {}
        self.interface_open = False
        self.out_armed = False
        self.tx_busy = False

        self.rx_bytes = 0
        self.tx_bytes = 0
        self.rx_frames = 0
        self.tx_frames = 0
        self.parse_errors = 0
        self.usb_errors = 0
        self.tx_dropped = 0
        self.resets = 0

        self.debug_enabled = False
        self.debug_limit = debug_limit
        self.debug_log = []

        self.register_channel(
            CHANNEL_CONTROL,
            KIND_CONTROL,
            DIR_BIDI,
            self.max_payload,
            "control",
            self._handle_control,
            announce=False,
        )

    def _debug(self, event, **fields):
        if not self.debug_enabled:
            return
        entry = {"ms": time.ticks_ms(), "event": event}
        entry.update(fields)
        self.debug_log.append(entry)
        if len(self.debug_log) > self.debug_limit:
            del self.debug_log[0]

    def set_debug(self, enabled):
        """Enable/disable the debug ring buffer. Disabling clears it."""
        self.debug_enabled = bool(enabled)
        if not self.debug_enabled:
            self.debug_log = []

    def dump_debug(self):
        """Print the debug log to the REPL."""
        for entry in self.debug_log:
            print(entry)

    def clear_debug(self):
        """Empty the debug log."""
        self.debug_log = []

    def register_channel(
        self,
        channel_id,
        kind,
        direction,
        max_packet,
        name,
        handler=None,
        announce=True,
    ):
        """Register a channel and announce it to the host if the interface is open.

        handler(msg_type, payload) receives inbound frames; with
        handler=None the channel is read-only for the host (an error
        frame is returned instead).
        """
        if not 0 <= channel_id <= 254:
            raise ValueError("channel id must be 0..254")
        if channel_id in self.channels:
            raise ValueError("duplicate channel id %d" % channel_id)
        if not 0 <= max_packet <= self.max_payload:
            raise ValueError("invalid max_packet")

        name_bytes = name.encode("utf-8")
        if len(name_bytes) > 63:
            raise ValueError("channel name too long")

        channel = {
            "id": channel_id,
            "kind": kind,
            "direction": direction,
            "max_packet": max_packet,
            "name": name,
            "name_bytes": name_bytes,
            "handler": handler,
        }
        self.channels[channel_id] = channel
        self._debug("channel_registered", channel=channel_id)

        if announce and self.interface_open:
            self.send(
                CHANNEL_CONTROL,
                MSG_CHANNEL_ADDED,
                self._encode_channel(channel),
                raise_on_full=False,
            )

    def unregister_channel(self, channel_id):
        """Remove an application channel and notify the host. Channel 0 is fixed."""
        if channel_id == CHANNEL_CONTROL:
            raise ValueError("control channel cannot be removed")
        if channel_id not in self.channels:
            raise KeyError(channel_id)

        del self.channels[channel_id]
        self._debug("channel_unregistered", channel=channel_id)

        if self.interface_open:
            self.send(
                CHANNEL_CONTROL,
                MSG_CHANNEL_REMOVED,
                bytes((channel_id,)),
                raise_on_full=False,
            )

    def on_interface_open(self):
        """Notify that the host opened the vendor interface. Arms RX and starts TX."""
        self.interface_open = True
        self._debug("interface_open")
        self._arm_out()
        self._start_next_in()

    def on_usb_reset(self):
        """Notify a bus reset. Drops all transfer state; queued frames survive."""
        self.resets += 1
        self.interface_open = False
        self.out_armed = False
        self.tx_busy = False
        self.tx_active = None
        self.tx_length = 0
        self.tx_offset = 0
        self._debug("usb_reset", resets=self.resets)

    @staticmethod
    def _success(result):
        return result is True or result == 0

    def _arm_out(self):
        if self.out_armed or not self.interface_open:
            return

        try:
            self.out_armed = bool(
                self.usbd.submit_xfer(self.ep_out, self.rx_buffer)
            )
            self._debug("arm_out", queued=self.out_armed)
        except Exception as exc:
            self.usb_errors += 1
            self.out_armed = False
            self._debug("arm_out_error", error=repr(exc))

    def _start_next_in(self):
        if self.tx_busy or not self.interface_open:
            return

        if self.tx_active is None:
            if not self.tx_queue:
                return

            frame = self.tx_queue.pop(0)
            frame_length = len(frame)
            self.tx_buffer[:frame_length] = frame
            self.tx_active = self.tx_buffer
            self.tx_length = frame_length
            self.tx_offset = 0

        remaining_length = self.tx_length - self.tx_offset
        if remaining_length <= 0:
            self.tx_frames += 1
            self.tx_active = None
            self.tx_length = 0
            self.tx_offset = 0
            self._start_next_in()
            return

        remaining = self.tx_view[
            self.tx_offset:self.tx_offset + remaining_length
        ]

        # submit_xfer() may invoke the completion callback synchronously on
        # this MicroPython build. Mark the transfer busy before calling it.
        self.tx_busy = True
        self._debug(
            "submit_in_begin",
            length=remaining_length,
            offset=self.tx_offset,
            queue_depth=len(self.tx_queue),
        )

        try:
            queued = bool(self.usbd.submit_xfer(self.ep_in, remaining))
        except Exception as exc:
            self.usb_errors += 1
            self.tx_busy = False
            self.tx_active = None
            self.tx_length = 0
            self.tx_offset = 0
            self._debug("submit_in_error", error=repr(exc))
            return

        self._debug(
            "submit_in_return",
            queued=queued,
            tx_busy=self.tx_busy,
            offset=self.tx_offset,
            queue_depth=len(self.tx_queue),
        )

        # If the callback completed synchronously, it already cleared
        # tx_busy and advanced or completed the active frame.
        if not queued and self.tx_busy:
            self.tx_busy = False
            self.usb_errors += 1
            self._debug("submit_in_rejected")

    def on_transfer_complete(self, endpoint, result, transferred):
        """Transfer completion callback for both bulk endpoints."""
        self._debug(
            "xfer_complete",
            endpoint=endpoint,
            result=result,
            transferred=transferred,
        )

        if endpoint == self.ep_out:
            self.out_armed = False

            if self._success(result):
                self.rx_bytes += transferred
                try:
                    self._consume(bytes(self.rx_view[:transferred]))
                except Exception as exc:
                    self.parse_errors += 1
                    self._debug("consume_error", error=repr(exc))
            else:
                self.usb_errors += 1

            self._arm_out()
            return

        if endpoint == self.ep_in:
            if self.tx_busy and self.tx_active is not None:
                if self._success(result):
                    self.tx_bytes += transferred
                    self.tx_offset += transferred

                    if self.tx_offset >= self.tx_length:
                        self.tx_frames += 1
                        self.tx_active = None
                        self.tx_length = 0
                        self.tx_offset = 0
                else:
                    self.usb_errors += 1
                    self.tx_active = None
                    self.tx_length = 0
                    self.tx_offset = 0

            self.tx_busy = False
            self._start_next_in()

    def _consume(self, data):
        if not data:
            return

        self._debug(
            "out_data",
            length=len(data),
            raw=bytes(data[:32]),
        )
        self.rx_pending.extend(data)

        # Without a magic word, complete recovery is impossible. For robustness,
        # discard one byte at a time until a plausible header is found.
        while len(self.rx_pending) >= 4:
            channel_id = self.rx_pending[0]
            msg_type = self.rx_pending[1]
            length = self.rx_pending[2] | (self.rx_pending[3] << 8)

            plausible = (
                channel_id != 255
                and 1 <= msg_type <= MSG_STATUS
                and length <= self.max_payload
            )
            if not plausible:
                self.parse_errors += 1
                self._debug(
                    "bad_header",
                    raw=bytes(self.rx_pending[:4]),
                    channel=channel_id,
                    msg_type=msg_type,
                    length=length,
                )
                self.rx_pending = self.rx_pending[1:]
                continue

            frame_length = 4 + length
            if len(self.rx_pending) < frame_length:
                return

            payload = bytes(self.rx_pending[4:frame_length])
            self.rx_pending = self.rx_pending[frame_length:]

            self.rx_frames += 1
            self._debug(
                "frame_rx",
                channel=channel_id,
                msg_type=msg_type,
                length=length,
            )
            self._dispatch(channel_id, msg_type, payload)

    def _dispatch(self, channel_id, msg_type, payload):
        channel = self.channels.get(channel_id)
        if channel is None:
            self.send_error(channel_id, 2, "unknown channel")
            return

        if len(payload) > channel["max_packet"]:
            self.send_error(channel_id, 3, "packet too large")
            return

        handler = channel["handler"]
        if handler is None:
            self.send_error(channel_id, 4, "channel is not writable")
            return

        try:
            handler(msg_type, payload)
        except Exception as exc:
            self.send_error(channel_id, 5, repr(exc))

    def send(
        self,
        channel_id,
        msg_type,
        payload=b"",
        raise_on_full=True,
    ):
        """Queue one frame for transmission.

        Returns True when queued, False when the TX queue is full and
        raise_on_full is False (event-style traffic). Raises USBQueueFull
        when the queue is full and raise_on_full is True.
        """
        if channel_id not in self.channels:
            raise KeyError(channel_id)
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise TypeError("payload must support the buffer protocol")

        length = len(payload)
        if length > self.max_payload:
            raise ValueError("payload too large")

        if len(self.tx_queue) >= self.tx_queue_depth:
            self.tx_dropped += 1
            if raise_on_full:
                raise USBQueueFull("USB transmit queue is full")
            return False

        frame = (
            bytes((channel_id, msg_type))
            + _u16(length)
            + bytes(payload)
        )
        self.tx_queue.append(frame)
        self._debug(
            "frame_queued",
            channel=channel_id,
            msg_type=msg_type,
            length=length,
            queue_depth=len(self.tx_queue),
        )
        self._start_next_in()
        return True

    def send_error(self, related_channel, code, text):
        """Report a protocol/handler problem on the control channel (never raises)."""
        raw = text.encode("utf-8")[:120]
        self.send(
            CHANNEL_CONTROL,
            MSG_ERROR,
            bytes((related_channel & 0xFF, code & 0xFF)) + raw,
            raise_on_full=False,
        )

    def _handle_control(self, msg_type, payload):
        if msg_type == MSG_PING:
            self.send(CHANNEL_CONTROL, MSG_PONG, b"AS3U\x01")
            return

        if msg_type == MSG_CHANNEL_LIST_REQUEST:
            self.send(
                CHANNEL_CONTROL,
                MSG_CHANNEL_LIST_RESPONSE,
                self._encode_channel_list(),
            )
            return

        if msg_type == MSG_COMMAND:
            self._handle_control_command(payload)
            return

        self.send_error(CHANNEL_CONTROL, 6, "unsupported control message")

    def _handle_control_command(self, payload):
        if not payload:
            self.send_error(CHANNEL_CONTROL, 7, "empty control command")
            return

        command = payload[0]

        if command == CTRL_SET_DEBUG:
            if len(payload) != 2:
                self.send_error(CHANNEL_CONTROL, 8, "SET_DEBUG requires 1 byte")
                return
            self.set_debug(payload[1] != 0)
            self.send(CHANNEL_CONTROL, MSG_STATUS, self._encode_status())
            return

        if command == CTRL_GET_STATUS:
            self.send(CHANNEL_CONTROL, MSG_STATUS, self._encode_status())
            return

        if command == CTRL_CLEAR_DEBUG:
            self.clear_debug()
            self.send(CHANNEL_CONTROL, MSG_STATUS, self._encode_status())
            return

        self.send_error(CHANNEL_CONTROL, 9, "unknown control command")

    def _encode_status(self):
        # debug:u8, interface_open:u8, tx_busy:u8, out_armed:u8,
        # rx_frames:u32, tx_frames:u32, parse_errors:u32,
        # usb_errors:u32, tx_dropped:u32, queued:u16, debug_entries:u16
        return (
            bytes((
                1 if self.debug_enabled else 0,
                1 if self.interface_open else 0,
                1 if self.tx_busy else 0,
                1 if self.out_armed else 0,
            ))
            + _u32(self.rx_frames)
            + _u32(self.tx_frames)
            + _u32(self.parse_errors)
            + _u32(self.usb_errors)
            + _u32(self.tx_dropped)
            + _u16(len(self.tx_queue) + (1 if self.tx_active is not None else 0))
            + _u16(len(self.debug_log))
        )

    def _encode_channel(self, channel):
        return (
            bytes((
                channel["id"],
                channel["kind"],
                channel["direction"],
                channel["max_packet"] & 0xFF,
                (channel["max_packet"] >> 8) & 0xFF,
                len(channel["name_bytes"]),
            ))
            + channel["name_bytes"]
        )

    def _encode_channel_list(self):
        result = bytearray((len(self.channels),))
        for channel_id in sorted(self.channels):
            result.extend(self._encode_channel(self.channels[channel_id]))
        return bytes(result)

    def stats(self):
        """Snapshot of all transport counters and transfer state."""
        return {
            "interface_open": self.interface_open,
            "channels": len(self.channels),
            "rx_bytes": self.rx_bytes,
            "tx_bytes": self.tx_bytes,
            "rx_frames": self.rx_frames,
            "tx_frames": self.tx_frames,
            "parse_errors": self.parse_errors,
            "usb_errors": self.usb_errors,
            "tx_dropped": self.tx_dropped,
            "resets": self.resets,
            "queued": len(self.tx_queue) + (1 if self.tx_active is not None else 0),
            "tx_busy": self.tx_busy,
            "tx_offset": self.tx_offset,
            "out_armed": self.out_armed,
            "debug_enabled": self.debug_enabled,
            "debug_entries": len(self.debug_log),
        }
