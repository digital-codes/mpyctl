# SPDX-License-Identifier: AGPL-3.0-only
# boot.py
# AtomS3U USB enumeration only.
#
# This file:
#   1. configures the composite USB device,
#   2. activates it,
#   3. waits briefly for re-enumeration,
#   4. loads usb_channel_server and attaches it to the configured USB device.
#
# It contains no sensor-specific code.
#
# USB layout:
#   interface 0/1 : MicroPython CDC REPL
#   interface 2   : vendor-specific bulk interface (EP 0x03 OUT, EP 0x83 IN)
#
# All callbacks registered with USBD.config() are static proxies that
# forward to the USBChannelServer object once it exists; this keeps the
# callbacks valid across the re-enumeration delay below.

import time
import machine

USB = machine.USBDevice
USBD = USB()

VENDOR_INTERFACE = 2
EP_OUT = 0x03
EP_IN = 0x83

_server = None
_interface_open = False


def _open_interface(descriptor):
    """Host SET_INTERFACE callback. Track when the vendor interface is opened."""
    global _interface_open
    raw = bytes(descriptor)

    if (
        len(raw) >= 3
        and raw[1] == 0x04
        and raw[2] == VENDOR_INTERFACE
    ):
        _interface_open = True
        if _server is not None:
            _server.on_interface_open()


def _usb_reset():
    """USB bus reset callback. Forget interface state and notify the server."""
    global _interface_open
    _interface_open = False
    if _server is not None:
        _server.on_usb_reset()


def _transfer_complete(endpoint, result, transferred):
    """Transfer completion callback shared by both bulk endpoints."""
    if _server is not None:
        _server.on_transfer_complete(endpoint, result, transferred)


def _configure_usb():
    """Build the composite configuration and activate the USB device."""
    builtin = USB.BUILTIN_CDC

    USBD.active(False)
    USBD.builtin_driver = builtin

    if builtin.itf_max != VENDOR_INTERFACE or builtin.ep_max != 3:
        raise RuntimeError(
            "unexpected USB allocation: itf_max=%d ep_max=%d"
            % (builtin.itf_max, builtin.ep_max)
        )

    vendor_descriptor = bytes((
        # Vendor interface 2, two bulk endpoints.
        0x09, 0x04, VENDOR_INTERFACE, 0x00, 0x02,
        0xFF, 0x00, 0x00, 0x00,

        # EP 0x03 OUT, bulk, 64 bytes.
        0x07, 0x05, EP_OUT, 0x02, 0x40, 0x00, 0x00,

        # EP 0x83 IN, bulk, 64 bytes.
        0x07, 0x05, EP_IN, 0x02, 0x40, 0x00, 0x00,
    ))

    descriptor = bytearray(builtin.desc_cfg)
    descriptor.extend(vendor_descriptor)

    total_length = len(descriptor)
    descriptor[2] = total_length & 0xFF
    descriptor[3] = (total_length >> 8) & 0xFF
    descriptor[4] = VENDOR_INTERFACE + 1

    USBD.config(
        builtin.desc_dev,
        descriptor,
        {},
        _open_interface,
        _usb_reset,
        None,
        _transfer_complete,
    )
    USBD.active(True)


_configure_usb()

# Let the host observe the new composite configuration before importing the
# protocol implementation. The callback proxies above remain valid during
# this interval.
time.sleep_ms(250)

import usb_channel_server

_server = usb_channel_server.USBChannelServer(
    USBD,
    interface=VENDOR_INTERFACE,
    ep_out=EP_OUT,
    ep_in=EP_IN,
)
usb_channel_server.set_default_gateway(_server)

# Enumeration may have completed before the server object was created.
if _interface_open:
    _server.on_interface_open()
