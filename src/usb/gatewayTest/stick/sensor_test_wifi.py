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
from channel_defs import CHANNEL_WIFI
import time

button = None
rgb = None
wifi = None
_debug = False


def run(items=("button", "rgb", "wifi"), debug=False):
    """Create and start the requested test sensors.

    Sensors that are already active are left untouched; only the missing
    ones are created, so run() can repair a partially stopped set.
    Button polling is started automatically; on failure all sensors
    created in this call are closed again before re-raising.
    """
    global button, rgb, wifi, _debug
    _debug = debug

    created = []

    try:
        if "button" in items and button is None:
            print("sensor_test_wifi: Creating button sensor on channel 1, GPIO41")
            button = DigitalInputSensor(1, 41, timer_id=1)
            created.append(button)
        if "rgb" in items and rgb is None:
            print("sensor_test_wifi: Creating RGB sensor on channel 2, GPIO35")
            rgb = RGBOutputSensor(2, 35)
            created.append(rgb)

        if "wifi" in items and wifi is None:
            print("sensor_test_wifi: Creating WiFi server on channel %d" % CHANNEL_WIFI)
            wifi = WiFiServer(CHANNEL_WIFI, debug=debug)
            print("sensor_test_wifi: WiFi server created, starting server...")
            wifi.start_server()
            created.append(wifi)
            
            # Print initial stats
            print("sensor_test_wifi: WiFi stats after start:")
            s = wifi.stats()
            print("  IP: %s" % s["wifi"]["ip"])
            print("  SSID: %s" % s["wifi"]["ssid"])
            print("  Channel: %s" % s["wifi"]["channel"])
            print("  MAC: %s" % s["wifi"]["mac"])
            print("  Server port: %s" % s["server"]["port"])
            print("  Listening: %s" % s["server"]["listening"])

        if button is not None:
            button.start()
            print("sensor_test_wifi: Button polling started")

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


def stop(items=("button", "rgb", "wifi")):
    """Close the selected test sensors. Collects errors and raises at the end."""
    global button, rgb, wifi

    errors = []

    for item in items:
        if item == "button" and button is not None:
            try:
                print("sensor_test_wifi: Stopping button sensor")
                button.close()
                button = None
            except Exception as exc:
                errors.append(exc)
        elif item == "rgb" and rgb is not None:
            try:
                print("sensor_test_wifi: Stopping RGB sensor")
                rgb.close()
                rgb = None
            except Exception as exc:
                errors.append(exc)
        elif item == "wifi" and wifi is not None:
            try:
                print("sensor_test_wifi: Stopping WiFi server")
                wifi.close()
                wifi = None
            except Exception as exc:
                errors.append(exc)


    if errors:
        raise RuntimeError("sensor shutdown errors: %r" % errors)


def poll():
    """Poll WiFi server for new connections and data. Call periodically."""
    global wifi
    if wifi is not None:
        wifi._poll()


def stats():
    """Combined gateway, WiFi and sensor activity report."""
    import usb_channel_server

    result = {
        "usb": usb_channel_server.get_gateway().stats(),
        "wifi": None if wifi is None else wifi.stats(),
        "button_active": button is not None,
        "rgb_active": rgb is not None,
    }
    
    # Print formatted
    print("\n=== sensor_test_wifi Stats ===")
    print("Button active:", result["button_active"])
    print("RGB active:", result["rgb_active"])
    
    if result["wifi"]:
        w = result["wifi"]
        print("\nWiFi:")
        print("  SSID: %s" % w["wifi"]["ssid"])
        print("  Channel: %s" % w["wifi"]["channel"])
        print("  IP: %s" % w["wifi"]["ip"])
        print("  MAC: %s" % w["wifi"]["mac"])
        print("  Server port: %s" % w["server"]["port"])
        print("  Listening: %s" % w["server"]["listening"])
        print("  Clients: %s" % w["clients"])
        print("  Authorized MACs: %s" % w["authorized_macs"])
        print("  Connected: %s" % w["stats"]["connected"])
        print("  Disconnected: %s" % w["stats"]["disconnected"])
        print("  Received: %s" % w["stats"]["received"])
        print("  Rejected: %s" % w["stats"]["rejected"])
        print("  Sent: %s" % w["stats"]["sent"])
        print("  TX errors: %s" % w["stats"]["tx_errors"])
        print("  RX errors: %s" % w["stats"]["rx_errors"])
        print("  Forward dropped: %s" % w["stats"]["forward_dropped"])
    
    if result["usb"]:
        u = result["usb"]
        print("\nUSB:")
        print("  RX bytes: %s" % u["rx_bytes"])
        print("  TX bytes: %s" % u["tx_bytes"])
        print("  RX frames: %s" % u["rx_frames"])
        print("  TX frames: %s" % u["tx_frames"])
        print("  Parse errors: %s" % u["parse_errors"])
        print("  USB errors: %s" % u["usb_errors"])
        print("  TX dropped: %s" % u["tx_dropped"])
    
    print("============================\n")
    
    return result
