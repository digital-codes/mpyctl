# SPDX-License-Identifier: AGPL-3.0-only
# espnow_server.py
#
# ESP-NOW radio sensor: receive ESP-NOW packets and forward them as
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
from channel_defs import KIND_BIDI, DIR_BIDI, MSG_EVENT, MSG_COMMAND, MSG_PEER_ADD, MSG_PEER_DEL
    
# config stuff
_CONF_FILE = "config.json"
files = os.listdir("/")
if not _CONF_FILE in files:
    print("No config file, starting with dummy/empty config")
    raise BaseException("No Config")


class ESPNowRadio:
    """ESP-NOW receiver bridging peer messages onto a USB gateway channel.

    channel_id is the USB gateway channel number only (KIND 3, DIR_IN);
    the radio operates on private.py ENOW_CHANNEL regardless of it.
    In gateway mode every authenticated message is forwarded as one
    MSG_EVENT. In stand-alone mode (gateway=None) messages are only
    counted and optionally printed.
    """

    KIND = KIND_BIDI

    def __init__(
        self,
        channel_id,
        name="espnow-radio",
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
            print("ESPNowRadio: initializing")
            if self.gateway:
                print("ESPNowRadio: gateway:", self.gateway)
            else:
                print("ESPNowRadio: stand-alone mode")

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
            print("ESPNowRadio: wlan config:", self.wlan.config("channel"), self.wlan.config("mac"))

        self.radio = espnow.ESPNow()
        # add some espnow defs to instance
        self._radio_datalen = espnow.MAX_DATA_LEN
        self._radio_crypt_peers = espnow.MAX_ENCRYPT_PEER_NUM
        self._radio_total_peers = espnow.MAX_TOTAL_PEER_NUM 
        # ESP-NOW must be initialized before config() and set_pmk().
        self.radio.active(True)
        self.radio.config(rxbuf=4096, timeout_ms=0)
        self.radio.set_pmk(self.shared_key[:16])

        if self.gateway:
            self.gateway.register_channel(
                channel_id,
                self.KIND,
                DIR_BIDI,
                self._radio_datalen,
                name,
                self._handle_outbound,
            )


        self.radio.irq(self._irq)

    def setDebug(self, debug):
        """Toggle verbose print output for received/rejected traffic."""
        self.debug = debug

    def setSecurity(self, security):
        """If security is True, only registered peers are accepted."""
        self.security = security

    def enableNode(self, mac, lmk=None):
        """Enable a node with the given MAC address and optional LMK.
        
        Returns:
            1 on success
            0 if peer already exists (not an error)
            negative on failure
        """
        try:
            existing = self.radio.get_peer(mac)
            if existing is not None:
                if self.debug:
                    print("Peer already exists:", mac.hex())
                return 0  # Already exists, not an error
        except Exception:
            pass
        try:
            if lmk is not None:
                self.radio.add_peer(mac, lmk, channel=self.wifi_channel)
            else:
                self.radio.add_peer(mac, channel=self.wifi_channel)
            if self.debug:
                print("Enabled peer:", mac, "LMK:", lmk)
            return 1
        except OSError as e:
            if self.debug:
                print("Failed to enable peer:", mac.hex(), "Error:", e)
            return -1


    def disableNode(self, mac):
        """Remove a previously enabled peer. Encrypted traffic from it is dropped.
        
        Returns:
            1 on success
            0 if peer didn't exist
            negative on failure
        """
        try:
            self.radio.del_peer(mac)
            if self.debug:
                print("Disabled peer:", mac.hex())
            return 1
        except Exception as e:
            if self.debug:
                print("Failed to disable peer:", mac.hex(), "Error:", e)
            return -1
        

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
                    MSG_EVENT,
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

    def _handle_outbound(self, msg_type, payload):
        """Handle outbound messages from the host.

        MSG_COMMAND payload: peer_index:u8 + message:string
        MSG_PEER_ADD payload: mac:6-bytes + lmk:16-bytes (optional)
        MSG_PEER_DEL payload: mac:6-bytes
        
        Returns:
            1 on success
            0 if no peers or general failure
            negative on specific errors
        """
        if msg_type == MSG_COMMAND:
            if len(payload) < 1:
                if self.debug:
                    print("Outbound: no peer index specified")
                return -1  # No peer index

            peer_index = payload[0]
            message = payload[1:].decode("utf-8", "replace")

            peer_macs = self.get_peer_macs()
            if not peer_macs:
                if self.debug:
                    print("Outbound: no peers registered")
                return -2  # No peers
            
            if peer_index >= len(peer_macs):
                if self.debug:
                    print(f"Outbound: invalid peer index {peer_index} (max {len(peer_macs)-1})")
                return -3  # Invalid peer index

            mac = peer_macs[peer_index]
            full_payload = self.shared_key[:16] + message.encode()

            if self.debug:
                print(f"Outbound to peer {peer_index} ({mac.hex()}): {message}")

            result = self.send_to_peer(mac, full_payload)
            return result  # 1 for success, 0 for failure

        elif msg_type == MSG_PEER_ADD:
            if len(payload) < 6:
                if self.debug:
                    print("Outbound: peer_add requires at least 6 bytes (MAC)")
                return -4  # Invalid MAC length

            mac = bytes(payload[:6])
            lmk = bytes(payload[6:22]) if len(payload) >= 22 else None

            if self.debug:
                print(f"Outbound: adding peer {mac.hex()} with LMK: {lmk.hex() if lmk else 'None'}")

            result = self.enableNode(mac, lmk)
            return result  # 1=success, 0=already exists, -1=failed

        elif msg_type == MSG_PEER_DEL:
            if len(payload) < 6:
                if self.debug:
                    print("Outbound: peer_del requires 6 bytes (MAC)")
                return -4  # Invalid MAC length

            mac = bytes(payload[:6])

            if self.debug:
                print(f"Outbound: removing peer {mac.hex()}")

            result = self.disableNode(mac)
            return result  # 1=success, 0=didn't exist, -1=failed
        
        return 0  # Unknown msg_type

    def send_to_peer(self, mac, message):
        """Send a message to a specific peer. Returns 1 on success, 0 on failure."""
        if self.debug:
            print("Sending to", mac, "Message:", message)
        try:
            result = self.radio.send(mac, message)
            if self.debug:
                print("Send result:", result)
            return 1 if result else 0
        except Exception as e:
            if self.debug:
                print("Send error:", e)
            return 0

    def send_to_all_peers(self, message):
        """Send a message to all registered peers.
        
        Returns:
            Number of successful sends if all succeed
            Negative value if any sends failed (peer_count - success_count)
        """
        try:
            peers = self.radio.peers_table
            peer_count = len(peers)
            success_count = 0
            for mac in peers:
                success_count += self.send_to_peer(mac, message)
            
            if success_count != peer_count:
                # Return negative difference to indicate partial failure
                return success_count - peer_count  # e.g., -1 if 1 peer failed
            return success_count
        except Exception as e:
            if self.debug:
                print("Error sending to all peers:", e)
            return -1

    def get_peer_count(self):
        """Return the number of registered peers."""
        try:
            return len(self.radio.peers_table)
        except Exception:
            return 0

    def get_peer_macs(self):
        """Return a list of registered peer MAC addresses."""
        try:
            return list(self.radio.peers_table.keys())
        except Exception:
            return []

    def stats(self):
        """Configuration plus receive/reject/drop counters and radio stats."""
        return {
            "config": {
                "address": self.address,
                "shared_key": self.shared_key,
                "wifi_channel": self.wifi_channel,
                "radio_datalen": self._radio_datalen,
                "radio_crypt_peers": self._radio_crypt_peers,
                "radio_total_peers": self._radio_total_peers
            },
            "received": self.received,
            "rejected": self.rejected,
            "forward_dropped": self.forward_dropped,
            "radio": self.radio.stats(),
        }


if __name__ == "__main__":
    # channel_id is the USB channel number and unused without a gateway;
    # the Wi-Fi channel comes from private.py ENOW_CHANNEL (see above).
    sensor = ESPNowRadio(channel_id=3, debug=True, stand_alone=True)
    
    # add peer with LMK from private.py
    with open("peers.json", "r") as f:
        peers = json.load(f)
        for peer in peers:
            mac = peer["mac"]
            lmk = peer["lmk"]
            print("Enabling peer:", mac, "LMK:", lmk)
            sensor.enableNode(bytes.fromhex(mac), bytes.fromhex(lmk))
    
    send_counter = 0
    try:
        while True:
            # Send a message to each enabled peer
            peer_macs = sensor.get_peer_macs()
            if peer_macs:
                print(f"\n--- Sending to {len(peer_macs)} peers (counter={send_counter}) ---")
                for idx, mac in enumerate(peer_macs):
                    # Create message with peer index and message count
                    msg = f"server msg {idx} {send_counter}".encode()
                    # Prepend shared key header for consistency with protocol
                    payload = sensor.shared_key[:16] + msg
                    r = sensor.send_to_peer(mac, payload)
                    print(f"Sending to peer {idx} ({mac.hex()}): {msg.decode()} - Result: {'OK' if r == 1 else 'FAIL'}")
            else:
                print("No peers registered, skipping send")
            
            send_counter += 1
            time.sleep(10)
            print(sensor.stats())
    except KeyboardInterrupt:
        pass
    finally:
        sensor.close()
        
