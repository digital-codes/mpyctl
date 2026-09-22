# boot.py — AtomS3U USB composite enumeration test with persistent logging
#
# Keeps the built-in CDC REPL and appends:
#   interface 2: vendor-specific
#   endpoint 0x03: bulk OUT, 64 bytes
#   endpoint 0x83: bulk IN, 64 bytes
#
# No transfers are submitted. Diagnostics are written to /usb_boot.log.

import sys
import machine

LOG_PATH = "/usb_boot.log"


def _log(message):
    # Open/close for every entry so earlier diagnostics survive a later failure.
    try:
        with open(LOG_PATH, "a") as f:
            f.write(str(message))
            f.write("\n")
            f.flush()
    except Exception:
        # Logging must not hide the original USB problem.
        pass


def _log_exception(exc):
    try:
        with open(LOG_PATH, "a") as f:
            f.write("EXCEPTION:\n")
            sys.print_exception(exc, f)
            f.flush()
    except Exception:
        pass


# Start a new log on every hard boot.
try:
    with open(LOG_PATH, "w") as f:
        f.write("AtomS3U USB enumeration test\n")
        f.write("MicroPython: %s\n" % (sys.version,))
        f.flush()
except Exception:
    pass

try:
    USB = machine.USBDevice
    usbd = USB()
    builtin = USB.BUILTIN_CDC

    _log("USBDevice object created")
    _log("initial active=%r" % (usbd.active(),))
    _log(
        "BUILTIN_CDC: itf_max=%d ep_max=%d str_max=%d"
        % (builtin.itf_max, builtin.ep_max, builtin.str_max)
    )
    _log("built-in device descriptor length=%d" % len(builtin.desc_dev))
    _log("built-in config descriptor length=%d" % len(builtin.desc_cfg))
    _log("built-in config header=%r" % (builtin.desc_cfg[:9],))

    # Required before assigning builtin_driver.
    usbd.active(False)
    _log("after active(False): active=%r" % (usbd.active(),))

    usbd.builtin_driver = builtin
    _log("builtin_driver assigned to BUILTIN_CDC")
    _log(
        "selected builtin: itf_max=%d ep_max=%d str_max=%d"
        % (
            usbd.builtin_driver.itf_max,
            usbd.builtin_driver.ep_max,
            usbd.builtin_driver.str_max,
        )
    )

    itf_vendor = builtin.itf_max
    ep_out = builtin.ep_max
    ep_in = 0x80 | ep_out

    if itf_vendor != 2 or ep_out != 3:
        raise RuntimeError(
            "Unexpected allocation: itf_max=%d ep_max=%d"
            % (itf_vendor, ep_out)
        )

    vendor_desc = bytes((
        # Interface 2: vendor-specific, two endpoints.
        0x09, 0x04, itf_vendor, 0x00, 0x02, 0xFF, 0x00, 0x00, 0x00,

        # Endpoint 0x03: bulk OUT, max packet 64.
        0x07, 0x05, ep_out, 0x02, 0x40, 0x00, 0x00,

        # Endpoint 0x83: bulk IN, max packet 64.
        0x07, 0x05, ep_in, 0x02, 0x40, 0x00, 0x00,
    ))

    desc_cfg = bytearray(builtin.desc_cfg)
    desc_cfg.extend(vendor_desc)

    total_length = len(desc_cfg)
    desc_cfg[2] = total_length & 0xFF
    desc_cfg[3] = (total_length >> 8) & 0xFF
    desc_cfg[4] = itf_vendor + 1

    _log("vendor descriptor length=%d" % len(vendor_desc))
    _log("combined descriptor length=%d" % total_length)
    _log("combined config header=%r" % (bytes(desc_cfg[:9]),))
    _log(
        "new interface=%d endpoints=0x%02x/0x%02x"
        % (itf_vendor, ep_out, ep_in)
    )

    # open_itf_cb records whether the host accepts each interface/IAD.
    def _open_itf_cb(desc):
        try:
            raw = bytes(desc)
            dtype = raw[1] if len(raw) > 1 else -1
            number = raw[2] if len(raw) > 2 else -1
            _log(
                "open_itf_cb: type=%d number/first=%d length=%d raw=%r"
                % (dtype, number, len(raw), raw)
            )
        except Exception as exc:
            _log("open_itf_cb logging failed: %r" % (exc,))

    def _reset_cb():
        _log("reset_cb: USB bus reset")

    _log("calling config()")
    # This ESP32 build requires desc_strs to be supplied explicitly.
    # An empty dict makes all built-in string indices fall back to the
    # compiled-in CDC strings, while defining no runtime strings.
    desc_strs = {}
    _log("desc_strs supplied explicitly as empty dict")

    # Pass the first five parameters positionally for compatibility with
    # this firmware's native argument binding:
    #   desc_dev, desc_cfg, desc_strs, open_itf_cb, reset_cb
    usbd.config(
        builtin.desc_dev,
        desc_cfg,
        desc_strs,
        _open_itf_cb,
        _reset_cb,
    )
    _log("config() returned successfully")

    usbd.active(True)
    _log("after active(True): active=%r" % (usbd.active(),))
    _log("boot.py USB setup completed")

except Exception as exc:
    _log_exception(exc)
    _log("USB setup failed; built-in CDC may fall back after boot")
