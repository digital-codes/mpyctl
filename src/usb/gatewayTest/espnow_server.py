# SPDX-License-Identifier: AGPL-3.0-only
# espnow_server.py
#
# ESP-NOW ingress sensor: receive ESP-NOW packets and forward them as
# events on a USB gateway channel (KIND 3, DIR_IN).
#
# Configuration lives in /config.json on the device:
#   {
#     "id":  "<device id>",
#     "ble":  {"key": "<32 hex chars = 16-byte shared key>"},
#     "wlan": {"addr": "<own mac hex>"},
#     ...
#   }
#
# Message contract with espnow_client_example.py:
#   on-air payload  = 16-byte shared key + application data
#   USB event payload = 6-byte source MAC + 1-byte RSSI (offset by 256)
#                       + application data
#
# Wi-Fi STA is activated before ESP-NOW is created (required on ESP32).
# channel_id is only the USB gateway channel number; the Wi-Fi channel
# is always taken from private.py ENOW_CHANNEL (private.py is required):
#   ENOW_CHANNEL = <Wi-Fi channel>
#
# Stand-alone mode (run as __main__): no USB gateway, peers loaded from
# peers.json (list of {"mac": "<hex>", "lmk": "<hex>"}).

import os
import json
import micropython
import network
import espnow
import private as pr
import usb_channel_server as ucs
import time
    
# config stuff
_CONF_FILE = "config.json"
files = os.listdir("/")
if not _CONF_FILE in files:
    print("No config file, starting with dummy/empty config")
    raise BaseException("No Config")


class ESPNowIngressSensor:
    """ESP-NOW receiver bridging peer messages onto a USB gateway channel.

    channel_id is the USB gateway channel number only (KIND 3, DIR_IN);
    the radio operates on private.py ENOW_CHANNEL regardless of it.
    In gateway mode every authenticated message is forwarded as one
    MSG_EVENT. In stand-alone mode (gateway=None) messages are only
    counted and optionally printed.
    """

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
        self.security = True

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
        self.wifi_channel = pr.ENOW_CHANNEL
        self.address = config["wlan"]["addr"]

        print("Device ID:", config["id"], "Wi-Fi channel:", self.wifi_channel, "address:", self.address, "Shared key:", self.shared_key)

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

    def setDebug(self, debug):
        """Toggle verbose print output for received/rejected traffic."""
        self.debug = debug

    def setSecurity(self, security):
        """If security is True, only registered peers are accepted."""
        self.security = security

    def enableNode(self, mac, lmk=None):
        """Enable a node with the given MAC address and optional LMK. Use LMK from individual device config BLE key.
        so server send as receives with LMK as node BLE key.
        """
        if lmk is not None:
            self.radio.add_peer(mac, lmk, channel=self.wifi_channel)
        else:
            self.radio.add_peer(mac, channel=self.wifi_channel) 
        if self.debug:
            print("Enabled peer:", mac, "LMK:", lmk)


    def disableNode(self, mac):
        """Remove a previously enabled peer. Encrypted traffic from it is dropped."""
        self.radio.del_peer(mac)
        

    def close(self):
        """Detach the IRQ, deactivate the radio and unregister the channel."""
        try:
            self.radio.irq(None)
        except Exception:
            pass
        self.radio.active(False)
        if self.gateway:
            self.gateway.unregister_channel(self.channel_id)

    def _irq(self, radio):
        """ESP-NOW IRQ. Schedule a drain; never block in interrupt context."""
        if self.irq_pending:
            return

        self.irq_pending = True
        try:
            micropython.schedule(self._drain, 0)
        except RuntimeError:
            self.irq_pending = False

    def _drain(self, ignored):
        """Drain the ESP-NOW receive buffer and forward valid messages.

        A message is accepted only from a registered peer (when security
        is on) and only if it starts with the 16-byte shared key header.
        """
        self.irq_pending = False

        while True:
            mac, message = self.radio.irecv(0)
            if mac is None:
                return

            if self.security:
                try:
                    self.radio.get_peer(mac)
                except Exception:
                    if self.debug:
                        print("Rejected message from unknown peer:", mac)
                    continue

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
        """Configuration plus receive/reject/drop counters and radio stats."""
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
    # channel_id is the USB channel number and unused without a gateway;
    # the Wi-Fi channel comes from private.py ENOW_CHANNEL (see above).
    sensor = ESPNowIngressSensor(channel_id=3, debug=True, stand_alone=True)
    
    # add peer with LMK from private.py
    with open("peers.json", "r") as f:
        peers = json.load(f)
        for peer in peers:
            mac = peer["mac"]
            lmk = peer["lmk"]
            print("Enabling peer:", mac, "LMK:", lmk)
            sensor.enableNode(bytes.fromhex(mac), bytes.fromhex(lmk))
    
    try:
        while True:
            time.sleep(10)
            print(sensor.stats())
    except KeyboardInterrupt:
        pass
    finally:
        sensor.close()
        