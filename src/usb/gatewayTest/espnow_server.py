# SPDX-License-Identifier: AGPL-3.0-only
# espnow_server.py

import os
import json
import micropython
import network
import espnow
import usb_channel_server as ucs
import time
    
CHAN = 5

# config stuff
_CONF_FILE = "config.json"
files = os.listdir("/")
if not _CONF_FILE in files:
    print("No config file, starting with dummy/empty config")
    raise BaseException("No Config")


class ESPNowIngressSensor:
    KIND = 3

    def __init__(
        self,
        channel_id,
        name="espnow-ingress",
        gateway=None,
        debug = False,
        stand_alone=False
    ):
        if not stand_alone:
            self.gateway = gateway or ucs.get_gateway()
        else:
            self.gateway = None

        self.channel_id = channel_id
        self.irq_pending = False
        self.received = 0
        self.rejected = 0
        self.forward_dropped = 0
        self.debug = debug

        if self.debug:
            print("ESPNowIngressSensor: initializing")
            if self.gateway:
                print("ESPNowIngressSensor: gateway:", self.gateway)
            else:
                print("ESPNowIngressSensor: stand-alone mode")

        # disconnect from any existing wifi connection, if any
        try:
            network.WLAN().disconnect() # disconnect from any existing wifi connection
        except OSError:
            pass

        # Wi-Fi must be active before ESP-NOW is created or activated.
        self.wlan = network.WLAN(network.WLAN.IF_STA)
        self.wlan.active(True)
        while not self.wlan.active():
            time.sleep(1)

        global _CONF_FILE
        try:
            with open(_CONF_FILE) as f:
                config = json.load(f)
        except (OSError, ValueError):
            raise BaseException("No Config")

        self.shared_key = bytes.fromhex(config["ble"]["key"])
        self.wifi_channel = CHAN
        self.address = config["wlan"]["addr"]
        
        print("Device ID:", config["id"], "Wi-Fi channel:", ", address: ", self.address, self.wifi_channel, "Shared key:", self.shared_key)

        try:
            self.wlan.config(pm=self.wlan.PM_NONE)
        except Exception:
            pass

        try:
            self.wlan.config(channel=self.wifi_channel)
        except Exception:
            pass

        if self.debug:
            print("ESPNowIngressSensor: wlan config:", self.wlan.config("channel"), self.wlan.config("mac"))

        self.radio = espnow.ESPNow()
        # ESP-NOW must be initialized before config() and set_pmk().
        self.radio.active(True)
        self.radio.config(rxbuf=4096, timeout_ms=0)
        self.radio.set_pmk(self.shared_key[:16])

        if self.gateway:
            self.gateway.register_channel(
                channel_id,
                self.KIND,
                ucs.DIR_IN,
                250,
                name,
                None,
            )


        self.radio.irq(self._irq)

    def close(self):
        try:
            self.radio.irq(None)
        except Exception:
            pass
        self.radio.active(False)
        if self.gateway:
            self.gateway.unregister_channel(self.channel_id)

    def _irq(self, radio):
        if self.irq_pending:
            return

        self.irq_pending = True
        try:
            micropython.schedule(self._drain, 0)
        except RuntimeError:
            self.irq_pending = False

    def _drain(self, ignored):
        self.irq_pending = False

        while True:
            mac, message = self.radio.irecv(0)
            if mac is None:
                return

            if self.debug:
                print("Received message from", mac, "Data:", message)

            if len(message) < 16 or message[:16] != self.shared_key:
                self.rejected += 1
                continue

            application_data = message[16:]
            peer_data = self.radio.peers_table.get(mac)
            rssi = -128 if peer_data is None else peer_data[0]

            payload = (
                bytes(mac)
                + bytes(((rssi + 256) & 0xFF,))
                + application_data
            )

            if self.gateway:
                if self.gateway.send(
                    self.channel_id,
                    ucs.MSG_EVENT,
                    payload,
                    raise_on_full=False,
                ):
                    self.received += 1
                else:
                    self.forward_dropped += 1
            else:
                self.received += 1
                if self.debug:
                    print("Received message from", mac, "RSSI:", rssi, "Data:", application_data)

    def stats(self):
        return {
            "config": {
                "address": self.address,
                "shared_key": self.shared_key,
                "wifi_channel": self.wifi_channel,
            },
            "received": self.received,
            "rejected": self.rejected,
            "forward_dropped": self.forward_dropped,
            "espnow": self.radio.stats(),
        }


if __name__ == "__main__":
    sensor = ESPNowIngressSensor(channel_id=CHAN,debug=True, stand_alone=True)
    try:
        while True:
            time.sleep(10)
            print(sensor.stats())
    except KeyboardInterrupt:
        pass
    finally:
        sensor.close()
        