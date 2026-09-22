# boot.py
# M5Stack AtomS3U, MicroPython 1.26.1
#
# Composite USB device:
#   interfaces 0/1: built-in CDC ACM REPL
#   interface 2: vendor-specific binary echo
#   EP 0x03: bulk OUT
#   EP 0x83: bulk IN
#
# The vendor interface is callback-driven. Each host transfer is echoed back.
# Logical transfers may be 1..4096 bytes; USB splits them into 64-byte packets.

import machine

USB = machine.USBDevice
USBD = USB()

VENDOR_INTERFACE = 2
EP_OUT = 0x03
EP_IN = 0x83
BUFFER_SIZE = 4096

_rx_buffer = bytearray(BUFFER_SIZE)
_rx_view = memoryview(_rx_buffer)
_out_armed = False
_in_busy = False
_last_length = 0

# Persistent counters are intentionally simple. Inspect them at the REPL:
#   import boot
#   boot.usb_stats()
_rx_bytes = 0
_tx_bytes = 0
_rx_transfers = 0
_tx_transfers = 0
_errors = 0
_dropped = 0


def _is_success(result):
    # MicroPython 1.26 documentation describes True/False, while newer
    # versions use XFER_SUCCESS == 0. Accept both representations.
    return result is True or result == 0


def _arm_out():
    global _out_armed, _errors
    if _out_armed:
        return True
    try:
        queued = USBD.submit_xfer(EP_OUT, _rx_buffer)
    except Exception:
        _errors += 1
        return False
    _out_armed = bool(queued)
    return _out_armed


def _open_interface(interface_desc):
    # Called for the built-in CDC IAD and for the vendor interface.
    # Arm OUT only when interface 2 is accepted by the host.
    raw = bytes(interface_desc)
    if len(raw) >= 3 and raw[1] == 0x04 and raw[2] == VENDOR_INTERFACE:
        _arm_out()


def _usb_reset():
    global _out_armed, _in_busy
    # Pending transfers are cancelled without completion callbacks.
    _out_armed = False
    _in_busy = False


def _transfer_complete(endpoint, result, transferred):
    global _out_armed, _in_busy, _last_length
    global _rx_bytes, _tx_bytes, _rx_transfers, _tx_transfers
    global _errors, _dropped

    if endpoint == EP_OUT:
        _out_armed = False

        if not _is_success(result):
            _errors += 1
            _arm_out()
            return

        _rx_bytes += transferred
        _rx_transfers += 1
        _last_length = transferred

        if transferred == 0:
            _arm_out()
            return

        # Only one echo may be outstanding. The host benchmark sends one
        # request and waits for its response, so this remains lossless.
        if _in_busy:
            _dropped += 1
            _arm_out()
            return

        try:
            queued = USBD.submit_xfer(EP_IN, _rx_view[:transferred])
        except Exception:
            queued = False

        if queued:
            _in_busy = True
        else:
            _errors += 1
            _arm_out()

    elif endpoint == EP_IN:
        _in_busy = False

        if _is_success(result):
            _tx_bytes += transferred
            _tx_transfers += 1
        else:
            _errors += 1

        # Rearm after the echo is consumed. This gives strict request/reply
        # semantics and avoids overwriting the shared buffer.
        _arm_out()


def usb_stats():
    return {
        "rx_bytes": _rx_bytes,
        "tx_bytes": _tx_bytes,
        "rx_transfers": _rx_transfers,
        "tx_transfers": _tx_transfers,
        "errors": _errors,
        "dropped": _dropped,
        "out_armed": _out_armed,
        "in_busy": _in_busy,
        "last_length": _last_length,
    }


def _configure_usb():
    builtin = USB.BUILTIN_CDC

    USBD.active(False)
    USBD.builtin_driver = builtin

    if builtin.itf_max != VENDOR_INTERFACE or builtin.ep_max != 3:
        raise RuntimeError(
            "Unexpected built-in allocation: itf_max=%d ep_max=%d"
            % (builtin.itf_max, builtin.ep_max)
        )

    vendor_desc = bytes((
        # Interface 2: vendor-specific, two bulk endpoints.
        0x09, 0x04, VENDOR_INTERFACE, 0x00, 0x02,
        0xFF, 0x00, 0x00, 0x00,

        # EP 0x03 OUT, bulk, 64-byte Full-Speed max packet.
        0x07, 0x05, EP_OUT, 0x02, 0x40, 0x00, 0x00,

        # EP 0x83 IN, bulk, 64-byte Full-Speed max packet.
        0x07, 0x05, EP_IN, 0x02, 0x40, 0x00, 0x00,
    ))

    desc_cfg = bytearray(builtin.desc_cfg)
    desc_cfg.extend(vendor_desc)

    total = len(desc_cfg)
    desc_cfg[2] = total & 0xFF
    desc_cfg[3] = (total >> 8) & 0xFF
    desc_cfg[4] = VENDOR_INTERFACE + 1

    # Positional arguments avoid the desc_strs binding issue observed on
    # this MicroPython 1.26.1 build:
    # desc_dev, desc_cfg, desc_strs, open_itf_cb, reset_cb,
    # control_xfer_cb, xfer_cb
    USBD.config(
        builtin.desc_dev,
        desc_cfg,
        {},
        _open_interface,
        _usb_reset,
        None,
        _transfer_complete,
    )
    USBD.active(True)


_configure_usb()
