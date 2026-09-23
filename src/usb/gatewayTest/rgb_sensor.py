# SPDX-License-Identifier: AGPL-3.0-only
# rgb_sensor.py
#
# RGB LED (NeoPixel) output sensor.
#
# Registers a DIR_OUT gateway channel (KIND 2) and accepts COMMAND
# messages carrying exactly 3 bytes (R, G, B). Each accepted command is
# echoed back as a RESPONSE so the host can confirm the applied color.

import machine
import neopixel
import usb_channel_server as ucs


class RGBOutputSensor:
    """Single-pixel NeoPixel sink on a USB gateway channel (KIND 2)."""

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
        """Turn the LED off and unregister the channel."""
        self.rgb = (0, 0, 0)
        self._write()
        self.gateway.unregister_channel(self.channel_id)

    def _handle(self, msg_type, payload):
        """Channel handler: apply a 3-byte COMMAND and respond with the color."""
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
        """Push the current color to the pixel hardware."""
        self.pixel[0] = self.rgb
        self.pixel.write()
