# SPDX-License-Identifier: AGPL-3.0-only

import usb_channel_server
gateway = usb_channel_server.get_gateway()
gateway.set_debug(True)
gateway.clear_debug()
gateway.stats()
from button_sensor import DigitalInputSensor
button = None
button = DigitalInputSensor(1, 41, timer_id=1)
button.start()
gateway.stats()
gateway.dump_debug()
gateway.clear_debug()
from rgb_sensor import RGBOutputSensor
rgb = RGBOutputSensor(2, 35)
gateway.dump_debug()
gateway.stats()
import os
os.remove("boot.py")


