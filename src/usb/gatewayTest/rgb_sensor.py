# SPDX-License-Identifier: AGPL-3.0-only
# rgb_sensor.py

import machine
import neopixel
import usb_channel_server as ucs


class RGBOutputSensor:
    KIND = 2

    def __init__(
        self,
        channel_id,
        pin_number,
        name="rgb-led",
        gateway=None,
    ):
        self.gateway = gateway or ucs.get_gateway()
        self.channel_id = channel_id
        self.pixel = neopixel.NeoPixel(
            machine.Pin(pin_number, machine.Pin.OUT),
            1,
        )
        self.rgb = (0, 0, 0)

        self.gateway.register_channel(
            channel_id,
            self.KIND,
            ucs.DIR_OUT,
            3,
            name,
            self._handle,
        )
        self._write()

    def close(self):
        self.rgb = (0, 0, 0)
        self._write()
        self.gateway.unregister_channel(self.channel_id)

    def _handle(self, msg_type, payload):
        if msg_type != ucs.MSG_COMMAND:
            raise ValueError("RGB channel accepts COMMAND only")
        if len(payload) != 3:
            raise ValueError("RGB payload must be exactly 3 bytes")

        self.rgb = (payload[0], payload[1], payload[2])
        self._write()

        self.gateway.send(
            self.channel_id,
            ucs.MSG_RESPONSE,
            bytes(self.rgb),
        )

    def _write(self):
        self.pixel[0] = self.rgb
        self.pixel.write()
