# SPDX-License-Identifier: AGPL-3.0-only
# button_sensor.py

import time
import machine
import micropython
import usb_channel_server as ucs


class DigitalInputSensor:
    KIND = 1

    def __init__(
        self,
        channel_id,
        pin_number,
        name="button",
        timer_id=1,
        pull=machine.Pin.PULL_UP,
        active_low=True,
        debounce_ms=30,
        poll_ms=10,
        gateway=None,
    ):
        self.gateway = gateway or ucs.get_gateway()
        self.channel_id = channel_id
        self.pin = machine.Pin(pin_number, machine.Pin.IN, pull)
        self.active_low = active_low
        self.debounce_ms = debounce_ms
        self.poll_ms = poll_ms

        self.raw = self.pin.value()
        self.stable = self.raw
        self.changed_at = time.ticks_ms()
        self.timer = machine.Timer(timer_id)
        self.running = False

        self.gateway.register_channel(
            channel_id,
            self.KIND,
            ucs.DIR_IN,
            1,
            name,
            None,
        )

    def start(self):
        if self.running:
            return
        self.timer.init(
            period=self.poll_ms,
            mode=machine.Timer.PERIODIC,
            callback=self._poll,
        )
        self.running = True
        self._emit()

    def stop(self):
        if not self.running:
            return
        self.timer.deinit()
        self.running = False

    def close(self):
        self.stop()
        self.gateway.unregister_channel(self.channel_id)

    def _poll(self, timer):
        now = time.ticks_ms()
        raw = self.pin.value()

        if raw != self.raw:
            self.raw = raw
            self.changed_at = now
            return

        if (
            raw != self.stable
            and time.ticks_diff(now, self.changed_at) >= self.debounce_ms
        ):
            self.stable = raw
            try:
                micropython.schedule(self._scheduled_emit, 0)
            except RuntimeError:
                pass

    def _scheduled_emit(self, ignored):
        self._emit()

    def _emit(self):
        pressed = (
            self.stable == 0
            if self.active_low
            else self.stable != 0
        )
        self.gateway.send(
            self.channel_id,
            ucs.MSG_EVENT,
            bytes((1 if pressed else 0,)),
            raise_on_full=False,
        )
