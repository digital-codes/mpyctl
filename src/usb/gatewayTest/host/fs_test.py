#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Filesystem operations tool for the AtomS3U USB sensor gateway.

Host counterpart of the MicroPython filesystem handlers. Talks to the device's
vendor-specific bulk interface (interface 2, EP 0x03 OUT / EP 0x83 IN) using
the 4-byte framing defined by usb_channel_server.py.

Commands:
  ls [path]     - List directory contents (like mpremote ls)
  cat <path>    - Read file contents (like mpremote cat)
  put <src> [dst] - Write local file to device (like mpremote cp)
  rm <path>     - Delete file from device
  exists <path> - Check if file exists on device

Requires pyusb. Optional --serial selects among several attached boards.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import usb.core
import usb.util

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from channel_defs import (
    MSG_COMMAND,
    MSG_RESPONSE,
    MSG_ERROR,
    MSG_PING,
    MSG_PONG,
    MSG_FS_LIST,
    MSG_FS_READ,
    MSG_FS_WRITE,
    MSG_FS_DELETE,
    MSG_FS_EXISTS,
    MSG_FS_RESPONSE,
    CHANNEL_CONTROL,
    CTRL_FS_LIST,
    CTRL_FS_READ,
    CTRL_FS_WRITE,
    CTRL_FS_DELETE,
    CTRL_FS_EXISTS,
)

VID = 0x303A
PID = 0x4001
INTERFACE = 2
EP_OUT = 0x03
EP_IN = 0x83


class ProtocolError(Exception):
    pass


class USBDisconnected(Exception):
    pass


class FrameParser:
    """Incremental parser for the 4-byte framed protocol."""

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
    """PyUSB transport for filesystem operations."""

    def __init__(self, serial=None, timeout_ms=100):
        self.serial = serial
        self.timeout_ms = timeout_ms
        self.dev = None
        self.claimed = False
        self.parser = FrameParser()
        self.write_lock = None
        self.response_event = None
        self.last_response = None
        self.last_error = None

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
        """Locate the device and claim the vendor interface."""
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
        self.write_lock = __import__("threading").Lock()

    def close(self):
        """Release the interface and dispose USB resources."""
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
        except usb.core.USBError as exc:
            raise USBDisconnected(str(exc)) from exc

    def read_response(self, timeout_ms=5000):
        """Read a response from the device."""
        if self.dev is None:
            raise USBDisconnected("device is not open")

        start_time = time.time()
        while (time.time() - start_time) * 1000 < timeout_ms:
            try:
                data = bytes(
                    self.dev.read(
                        EP_IN,
                        4096,
                        timeout=self.timeout_ms,
                    )
                )
                for frame in self.parser.feed(data):
                    channel, msg_type, payload = frame
                    if channel == CHANNEL_CONTROL:
                        if msg_type == MSG_FS_RESPONSE:
                            return payload
                        elif msg_type == MSG_ERROR:
                            related = payload[0] if len(payload) > 0 else -1
                            code = payload[1] if len(payload) > 1 else -1
                            text = payload[2:].decode("utf-8", "replace")
                            raise ProtocolError(
                                "device error ch=%d code=%d: %s"
                                % (related, code, text)
                            )
            except usb.core.USBTimeoutError:
                continue

        raise ProtocolError("timeout waiting for response")

    def ping(self):
        """Send ping and wait for pong."""
        self.send(CHANNEL_CONTROL, MSG_PING)
        start_time = time.time()
        while (time.time() - start_time) * 1000 < 5000:
            try:
                data = bytes(
                    self.dev.read(
                        EP_IN,
                        4096,
                        timeout=100,
                    )
                )
                for frame in self.parser.feed(data):
                    channel, msg_type, payload = frame
                    if channel == CHANNEL_CONTROL and msg_type == MSG_PONG:
                        return True
            except usb.core.USBTimeoutError:
                continue
        return False


def fs_list(gateway, path="/"):
    """List directory contents on the device."""
    payload = bytes((CTRL_FS_LIST,)) + path.encode("utf-8")
    gateway.send(CHANNEL_CONTROL, MSG_COMMAND, payload)
    response = gateway.read_response()

    if not response:
        return []

    entries = []
    offset = 0
    while offset < len(response):
        if offset + 2 > len(response):
            break
        name_len = response[offset]
        offset += 1
        if offset + name_len + 2 > len(response):
            break
        name = response[offset:offset + name_len].decode("utf-8")
        offset += name_len
        is_dir = response[offset] != 0
        offset += 1
        if offset + 4 > len(response):
            break
        size = int.from_bytes(response[offset:offset + 4], "little")
        offset += 4
        entries.append({"name": name, "is_dir": is_dir, "size": size})

    return entries


MAX_CHUNK_SIZE = 960


def _u32(value):
    return bytes((value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF, (value >> 24) & 0xFF))


def fs_read(gateway, path, max_size=None):
    """Read file contents from the device, handling large files in chunks."""
    path_bytes = path.encode("utf-8")
    offset = 0
    result = bytearray()

    while True:
        size = MAX_CHUNK_SIZE
        if max_size is not None:
            remaining = max_size - offset
            if remaining <= 0:
                break
            size = min(size, remaining)

        extra = _u32(offset) + _u32(size)
        payload = bytes((CTRL_FS_READ,)) + path_bytes + b"\0" + extra
        gateway.send(CHANNEL_CONTROL, MSG_COMMAND, payload)
        data = gateway.read_response()

        if not data:
            break
        result.extend(data)

        if len(data) < size:
            break
        offset += len(data)

    return bytes(result)


def fs_write(gateway, path, data):
    """Write data to a file on the device, chunking if necessary."""
    path_bytes = path.encode("utf-8")
    total_written = 0
    offset = 0

    while offset < len(data):
        chunk = data[offset:offset + MAX_CHUNK_SIZE]
        offset_bytes = _u32(offset)
        payload = bytes((CTRL_FS_WRITE,)) + path_bytes + b"\0" + offset_bytes + chunk
        gateway.send(CHANNEL_CONTROL, MSG_COMMAND, payload)
        response = gateway.read_response()
        if len(response) >= 4:
            written = int.from_bytes(response[:4], "little")
            total_written += written
        offset += len(chunk)

    return total_written


def fs_delete(gateway, path):
    """Delete a file from the device."""
    payload = bytes((CTRL_FS_DELETE,)) + path.encode("utf-8")
    gateway.send(CHANNEL_CONTROL, MSG_COMMAND, payload)
    response = gateway.read_response()
    return len(response) > 0 and response[0] == 1


def fs_exists(gateway, path):
    """Check if a file exists on the device."""
    payload = bytes((CTRL_FS_EXISTS,)) + path.encode("utf-8")
    gateway.send(CHANNEL_CONTROL, MSG_COMMAND, payload)
    response = gateway.read_response()
    return len(response) > 0 and response[0] == 1


def cmd_ls(args):
    """Execute ls command."""
    gateway = USBGateway(serial=args.device_serial)
    try:
        gateway.open()
        if not gateway.ping():
            print("Error: device not responding to ping")
            return 1

        entries = fs_list(gateway, args.path)
        for entry in entries:
            if entry["is_dir"]:
                print("%s/" % entry["name"])
            else:
                print("%s  %d" % (entry["name"], entry["size"]))
        return 0
    except Exception as e:
        print("Error: %s" % e)
        return 1
    finally:
        gateway.close()


def cmd_cat(args):
    """Execute cat command."""
    gateway = USBGateway(serial=args.device_serial)
    try:
        gateway.open()
        if not gateway.ping():
            print("Error: device not responding to ping")
            return 1

        data = fs_read(gateway, args.path)
        sys.stdout.buffer.write(data)
        return 0
    except Exception as e:
        print("Error: %s" % e)
        return 1
    finally:
        gateway.close()


def cmd_put(args):
    """Execute put command (write local file to device)."""
    dest = args.dest if args.dest else os.path.basename(args.src)

    gateway = USBGateway(serial=args.device_serial)
    try:
        gateway.open()
        if not gateway.ping():
            print("Error: device not responding to ping")
            return 1

        with open(args.src, "rb") as f:
            data = f.read()

        size = fs_write(gateway, dest, data)
        print("Wrote %d bytes to %s" % (size, dest))
        return 0
    except Exception as e:
        print("Error: %s" % e)
        return 1
    finally:
        gateway.close()


def cmd_rm(args):
    """Execute rm command (delete file from device)."""
    gateway = USBGateway(serial=args.device_serial)
    try:
        gateway.open()
        if not gateway.ping():
            print("Error: device not responding to ping")
            return 1

        if fs_delete(gateway, args.path):
            print("Deleted %s" % args.path)
            return 0
        else:
            print("Failed to delete %s" % args.path)
            return 1
    except Exception as e:
        print("Error: %s" % e)
        return 1
    finally:
        gateway.close()


def cmd_exists(args):
    """Execute exists command."""
    gateway = USBGateway(serial=args.device_serial)
    try:
        gateway.open()
        if not gateway.ping():
            print("Error: device not responding to ping")
            return 1

        if fs_exists(gateway, args.path):
            print("%s exists" % args.path)
            return 0
        else:
            print("%s does not exist" % args.path)
            return 1
    except Exception as e:
        print("Error: %s" % e)
        return 1
    finally:
        gateway.close()


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Filesystem operations for AtomS3U device",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ls /                - List root directory
  %(prog)s ls /flash           - List flash filesystem
  %(prog)s cat /main.py        - Read file contents
  %(prog)s put local.py /main.py - Write file to device
  %(prog)s rm /test.py         - Delete file from device
  %(prog)s exists /boot.py     - Check if file exists
        """,
    )
    parser.add_argument(
        "--device-serial",
        help="Device serial number from USB descriptor (if multiple devices)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    ls_parser = subparsers.add_parser("ls", help="List directory")
    ls_parser.add_argument("path", nargs="?", default="/", help="Directory path")

    cat_parser = subparsers.add_parser("cat", help="Read file")
    cat_parser.add_argument("path", help="File path")

    put_parser = subparsers.add_parser("put", help="Write file")
    put_parser.add_argument("src", help="Local source file")
    put_parser.add_argument("dest", nargs="?", help="Remote destination path")

    rm_parser = subparsers.add_parser("rm", help="Delete file")
    rm_parser.add_argument("path", help="File path")

    exists_parser = subparsers.add_parser("exists", help="Check file exists")
    exists_parser.add_argument("path", help="File path")

    args = parser.parse_args()

    if args.command == "ls":
        return cmd_ls(args)
    elif args.command == "cat":
        return cmd_cat(args)
    elif args.command == "put":
        return cmd_put(args)
    elif args.command == "rm":
        return cmd_rm(args)
    elif args.command == "exists":
        return cmd_exists(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
