# SPDX-License-Identifier: AGPL-3.0-only
# button_sensor.py
#
# Debounced digital input (push button) sensor.
#
# Publishes button state changes on a DIR_IN gateway channel (KIND 1).
# Payload is a single byte: 0x01 pressed, 0x00 released.
#
# The pin is sampled periodically from a hardware timer; a level change
# is only emitted after it has been stable for debounce_ms. The emission
# itself runs outside the timer IRQ via micropython.schedule().

import time
import machine
import micropython
import usb_channel_server as ucs
from channel_defs import KIND_INPUT, DIR_IN, MSG_EVENT


class DigitalInputSensor:
    """Debounced GPIO input published on a USB gateway channel.

    Registers a DIR_IN channel on construction. Call start() to begin
    polling and emitting events, stop() to pause, close() to tear down
    and unregister the channel.
    """

    KIND = KIND_INPUT

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
            DIR_IN,
            1,
            name,
            None,
        )

    def start(self):
        """Start periodic polling and emit the current state once."""
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
        """Stop polling. The channel stays registered; call close() to remove it."""
        if not self.running:
            return
        self.timer.deinit()
        self.running = False

    def close(self):
        """Stop polling and unregister the channel."""
        self.stop()
        self.gateway.unregister_channel(self.channel_id)

    def _poll(self, timer):
        """Timer IRQ. Track raw edges; schedule an emit once the level is stable."""
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
        """Deferred emit target run outside the timer IRQ by the scheduler."""
        self._emit()

    def _emit(self):
        """Send the debounced state as a one-byte event. Queue-full is not fatal."""
        pressed = (
            self.stable == 0
            if self.active_low
            else self.stable != 0
        )
        self.gateway.send(
            self.channel_id,
            MSG_EVENT,
            bytes((1 if pressed else 0,)),
            raise_on_full=False,
        )
