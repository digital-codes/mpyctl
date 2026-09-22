# SPDX-License-Identifier: AGPL-3.0-only
# sensor_test.py
#
# From the REPL:
#   import sensor_test
#   sensor_test.run()
#   sensor_test.stop()
#   sensor_test.stats()

from button_sensor import DigitalInputSensor
from rgb_sensor import RGBOutputSensor
from espnow_server import ESPNowIngressSensor

button = None
rgb = None
espnow = None


def run(items = ("button", "rgb", "espnow")):
    global button, rgb, espnow

    enabled = set()
    if "button" in items:
        enabled.add(button)
    if "rgb" in items:
        enabled.add(rgb)
    if "espnow" in items:
        enabled.add(espnow)

    if any(item is not None for item in enabled):
        return

    created = []

    try:
        if "button" in items and button is None:
                button = DigitalInputSensor(1, 41, timer_id=1)
                created.append(button)
        if "rgb" in items and rgb is None:
            rgb = RGBOutputSensor(2, 35)
            created.append(rgb)

        if "espnow" in items and espnow is None:
            espnow = ESPNowIngressSensor(3)
            created.append(espnow)

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
        espnow = None
        raise


def stop(items = ("button", "rgb", "espnow")):
    global button, rgb, espnow

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
        elif item == "espnow" and espnow is not None:
            try:
                espnow.close()
                espnow = None
            except Exception as exc:
                errors.append(exc)


    if errors:
        raise RuntimeError("sensor shutdown errors: %r" % errors)


def stats():
    import usb_channel_server

    return {
        "usb": usb_channel_server.get_gateway().stats(),
        "espnow": None if espnow is None else espnow.stats(),
        "button_active": button is not None,
        "rgb_active": rgb is not None,
    }
