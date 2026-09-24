# SPDX-License-Identifier: AGPL-3.0-only
# sensor_test_wifi.py
#
# Test-sensor factory for the USB gateway using WiFi AP server.
# This is the MicroPython counterpart of the Linux host application sensor_tui.py.
#
# Creates the three demo channels expected by the TUI:
#   channel 1 : button  (GPIO41 input,  timer driven)
#   channel 2 : rgb     (GPIO35 NeoPixel output)
#   channel 3 : wifi   (WiFi AP server on channel 3, SSID: MPY)
#
# From the REPL:
#   import sensor_test_wifi
#   sensor_test_wifi.run()
#   sensor_test_wifi.stop()
#   sensor_test_wifi.stats()

from button_sensor import DigitalInputSensor
from rgb_sensor import RGBOutputSensor
from wifi_server import WiFiServer

button = None
rgb = None
wifi = None


def run(items = ("button", "rgb", "wifi")):
    """Create and start the requested test sensors.

    Sensors that are already active are left untouched; only the missing
    ones are created, so run() can repair a partially stopped set.
    Button polling is started automatically; on failure all sensors
    created in this call are closed again before re-raising.
    """
    global button, rgb, wifi

    created = []

    try:
        if "button" in items and button is None:
            button = DigitalInputSensor(1, 41, timer_id=1)
            created.append(button)
        if "rgb" in items and rgb is None:
            rgb = RGBOutputSensor(2, 35)
            created.append(rgb)

        if "wifi" in items and wifi is None:
            wifi = WiFiServer(3)
            wifi.start_server()
            created.append(wifi)

        if button is not None:
            button.start()

    except Exception:
        for item in reversed(created):
            try:
                item.close()
            except Exception:
                pass
        button = None
        rgb = None
        wifi = None
        raise


def stop(items = ("button", "rgb", "wifi")):
    """Close the selected test sensors. Collects errors and raises at the end."""
    global button, rgb, wifi

    errors = []

    for item in items:
        if item == "button" and button is not None:
            try:
                button.close()
                button = None
            except Exception as exc:
                errors.append(exc)
        elif item == "rgb" and rgb is not None:
            try:
                rgb.close()
                rgb = None
            except Exception as exc:
                errors.append(exc)
        elif item == "wifi" and wifi is not None:
            try:
                wifi.close()
                wifi = None
            except Exception as exc:
                errors.append(exc)


    if errors:
        raise RuntimeError("sensor shutdown errors: %r" % errors)


def stats():
    """Combined gateway, WiFi and sensor activity report."""
    import usb_channel_server

    return {
        "usb": usb_channel_server.get_gateway().stats(),
        "wifi": None if wifi is None else wifi.stats(),
        "button_active": button is not None,
        "rgb_active": rgb is not None,
    }
