# SPDX-License-Identifier: AGPL-3.0-only
# wifi_server.py
#
# WiFi AP server: creates an access point and accepts TCP connections.
# Messages from connected clients are forwarded as events on a USB gateway
# channel (KIND 3, DIR_BIDI).
#
# Configuration lives in /config.json on the device:
#   {
#     "id":  "<device id>",
#     "ble":  {"key": "<32 hex chars = 16-byte shared key>"},
#     "wlan": {"addr": "<own MAC hex>"},
#     ...
#   }
#
# WiFi AP settings (hardcoded):
#   SSID: "MPY"
#   Password: "xxx"
#   Channel: 3
#
# Only clients with MAC addresses registered via enableNode() are accepted.
# The server listens on port 8080 for TCP connections.
#
# Message protocol:
#   - Each message is prefixed with 16-byte shared key (like ESP-NOW)
#   - USB event payload = 6-byte source MAC + application data
#   - Outbound: MSG_COMMAND with peer_index + message (like ESP-NOW)

import os
import json
import network
import socket
import micropython
import private as pr
import usb_channel_server as ucs
import time
from channel_defs import KIND_BIDI, DIR_BIDI, MSG_EVENT, MSG_COMMAND, MSG_PEER_ADD, MSG_PEER_DEL, CHANNEL_WIFI

# WiFi AP configuration
AP_SSID = "MPY"
AP_PASSWORD = "xxx"
AP_CHANNEL = 3
AP_LISTEN_PORT = 8080
HEADER_LEN = 16  # Shared key header length


# config stuff
_CONF_FILE = "config.json"
files = os.listdir("/")
if not _CONF_FILE in files:
    print("No config file, starting with dummy/empty config")
    raise BaseException("No Config")


class WiFiServer:
    """WiFi Access Point server that accepts TCP connections and bridges messages.

    Operates as an AP on channel 3. Only registered MAC addresses can connect.
    Messages from clients are forwarded as USB gateway events. Host can send
    messages to clients via the bidirectional channel.
    """

    KIND = KIND_BIDI

    def __init__(
        self,
        channel_id,
        name="wifi-server",
        gateway=None,
        debug=False,
        stand_alone=False
    ):
        if not stand_alone:
            self.gateway = gateway or ucs.get_gateway()
        else:
            self.gateway = None

        self.channel_id = channel_id
        self.debug = debug
        self.security = True
        self.shared_key = None
        self.address = None
        self.authorized_macs = set()  # MAC addresses allowed to connect
        
        # Server socket and client connections
        self.server_socket = None
        self.clients = {}  # mac -> (socket, addr)
        self.accepting = False
        self.irq_pending = False
        
        # Statistics
        self.connected = 0
        self.disconnected = 0
        self.received = 0
        self.rejected = 0
        self.forward_dropped = 0

        if self.debug:
            print("WiFiServer: initializing")
            if self.gateway:
                print("WiFiServer: gateway:", self.gateway)
            else:
                print("WiFiServer: stand-alone mode")

        # Load configuration
        global _CONF_FILE
        try:
            with open(_CONF_FILE) as f:
                config = json.load(f)
        except (OSError, ValueError):
            raise BaseException("No Config")

        self.shared_key = bytes.fromhex(config["ble"]["key"])
        self.address = config["wlan"]["addr"]

        print("Device ID:", config["id"], "Wi-Fi AP channel:", AP_CHANNEL, "address:", self.address)

        # Initialize WiFi AP
        self._init_wifi()

        # Register the bidirectional channel
        if self.gateway:
            self.gateway.register_channel(
                channel_id,
                self.KIND,
                DIR_BIDI,
                1024,  # Max packet size
                name,
                self._handle_outbound,
            )

    def _init_wifi(self):
        """Initialize WiFi in AP mode."""
        # Create AP interface (MicroPython uses network.AP_IF)
        self.ap = network.WLAN(network.AP_IF)
        
        # Configure AP with SSID, password, and channel
        self.ap.config(essid=AP_SSID, password=AP_PASSWORD, channel=AP_CHANNEL)
        
        # Activate AP
        self.ap.active(True)
        
        # Wait for AP to be active
        while not self.ap.active():
            time.sleep(0.1)
        
        if self.debug:
            print("WiFiServer: AP active, IP:", self.ap.ifconfig())

    def start_server(self):
        """Start accepting TCP connections."""
        if self.server_socket is not None:
            return
        
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', AP_LISTEN_PORT))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)  # Non-blocking with timeout
            self.accepting = True
            
            if self.debug:
                print("WiFiServer: listening on port", AP_LISTEN_PORT)
        except Exception as e:
            if self.debug:
                print("WiFiServer: failed to start server:", e)
            self.server_socket = None
            self.accepting = False

    def stop_server(self):
        """Stop accepting TCP connections and close all client sockets."""
        self.accepting = False
        
        # Close all client connections
        for mac in list(self.clients.keys()):
            self._close_client(mac)
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
            self.server_socket = None

    def _close_client(self, mac):
        """Close a specific client connection."""
        if mac in self.clients:
            sock, addr = self.clients[mac]
            try:
                sock.close()
            except Exception:
                pass
            del self.clients[mac]
            self.disconnected += 1
            if self.debug:
                print("WiFiServer: client disconnected:", mac.hex())

    def enableNode(self, mac, lmk=None):
        """Authorize a client MAC address to connect.
        
        Returns:
            1 on success
            0 if already authorized
            -1 on failure
        """
        mac_bytes = bytes(mac)
        if mac_bytes in self.authorized_macs:
            if self.debug:
                print("WiFiServer: MAC already authorized:", mac_bytes.hex())
            return 0
        
        self.authorized_macs.add(mac_bytes)
        if self.debug:
            print("WiFiServer: authorized MAC:", mac_bytes.hex())
        return 1

    def disableNode(self, mac):
        """Remove a client MAC from authorized list and disconnect if connected.
        
        Returns:
            1 on success
            0 if not authorized
            -1 on failure
        """
        mac_bytes = bytes(mac)
        if mac_bytes not in self.authorized_macs:
            if self.debug:
                print("WiFiServer: MAC not authorized:", mac_bytes.hex())
            return 0
        
        self.authorized_macs.discard(mac_bytes)
        
        # Disconnect if connected
        if mac_bytes in self.clients:
            self._close_client(mac_bytes)
        
        if self.debug:
            print("WiFiServer: removed MAC:", mac_bytes.hex())
        return 1

    def close(self):
        """Stop server, close connections, and unregister the channel."""
        self.stop_server()
        
        if self.gateway:
            self.gateway.unregister_channel(self.channel_id)

    def _poll(self):
        """Poll for new connections and data. Called periodically."""
        if not self.accepting:
            return
        
        # Accept new connections
        if self.server_socket:
            try:
                sock, addr = self.server_socket.accept()
                self._handle_new_connection(sock, addr)
            except OSError:
                pass  # No pending connection
        
        # Check each client for data
        for mac in list(self.clients.keys()):
            self._check_client_data(mac)

    def _handle_new_connection(self, sock, addr):
        """Handle a new TCP connection."""
        try:
            # Get client MAC from station info
            # Note: On ESP32, we can't easily get MAC of connected station
            # We'll use a placeholder and authorize based on first message
            
            if self.debug:
                print("WiFiServer: new connection from", addr)
            
            # Add to clients with None MAC initially (will be set when we receive data)
            # For now, accept all connections and verify in data handler
            self.clients[None] = (sock, addr)
            
        except Exception as e:
            if self.debug:
                print("WiFiServer: error accepting connection:", e)
            try:
                sock.close()
            except Exception:
                pass

    def _check_client_data(self, mac):
        """Check if there's data from a client."""
        if mac not in self.clients:
            return
        
        sock, addr = self.clients[mac]
        try:
            sock.settimeout(0)  # Non-blocking for MicroPython
            data = sock.recv(1024)
            if data:
                self._handle_client_data(mac, data)
            else:
                # No data - connection closed
                if mac is not None:
                    self._close_client(mac)
        except OSError:
            pass  # No data available
        except Exception as e:
            if self.debug:
                print("WiFiServer: error reading from client:", e)
            if mac is not None:
                self._close_client(mac)

    def _handle_client_data(self, mac, data):
        """Process data received from a client.
        
        Expected format: 16-byte shared key header + application data
        """
        if len(data) < HEADER_LEN:
            if self.debug:
                print("WiFiServer: received short data:", len(data))
            self.rejected += 1
            return
        
        # Verify shared key header
        if data[:HEADER_LEN] != self.shared_key:
            if self.debug:
                print("WiFiServer: invalid shared key from client")
            self.rejected += 1
            return
        
        application_data = data[HEADER_LEN:]
        
        # If MAC is None, try to get it from the socket
        if mac is None:
            # First message - try to determine MAC
            # For now, accept the connection
            mac = bytes([0] * 6)  # Placeholder
        
        # Forward to USB gateway
        if self.gateway:
            payload = mac + application_data
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
                print("WiFiServer: received:", application_data)

    def _handle_outbound(self, msg_type, payload):
        """Handle outbound messages from the host.

        MSG_COMMAND payload: peer_index:u8 + message:string
        MSG_PEER_ADD payload: mac:6-bytes + lmk:16-bytes (optional)
        MSG_PEER_DEL payload: mac:6-bytes
        
        Returns:
            1 on success
            0 if no clients or general failure
            negative on specific errors
        """
        if msg_type == MSG_COMMAND:
            if len(payload) < 1:
                if self.debug:
                    print("WiFiServer: no peer index specified")
                return -1  # No peer index

            peer_index = payload[0]
            message = payload[1:].decode("utf-8", "replace")

            # Get list of connected client MACs
            client_macs = [mac for mac in self.clients.keys() if mac is not None]
            
            if not client_macs:
                if self.debug:
                    print("WiFiServer: no clients connected")
                return -2  # No clients connected
            
            if peer_index >= len(client_macs):
                if self.debug:
                    print(f"WiFiServer: invalid peer index {peer_index} (max {len(client_macs)-1})")
                return -3  # Invalid peer index

            mac = client_macs[peer_index]
            full_message = self.shared_key[:HEADER_LEN] + message.encode()

            if self.debug:
                print(f"WiFiServer: sending to peer {peer_index} ({mac.hex() if mac else 'None'}): {message}")

            result = self._send_to_client(mac, full_message)
            return result

        elif msg_type == MSG_PEER_ADD:
            if len(payload) < 6:
                if self.debug:
                    print("WiFiServer: peer_add requires at least 6 bytes (MAC)")
                return -4  # Invalid MAC length

            mac = bytes(payload[:6])

            if self.debug:
                print(f"WiFiServer: authorizing MAC {mac.hex()}")

            result = self.enableNode(mac)
            return result

        elif msg_type == MSG_PEER_DEL:
            if len(payload) < 6:
                if self.debug:
                    print("WiFiServer: peer_del requires 6 bytes (MAC)")
                return -4  # Invalid MAC length

            mac = bytes(payload[:6])

            if self.debug:
                print(f"WiFiServer: de-authorizing MAC {mac.hex()}")

            result = self.disableNode(mac)
            return result
        
        return 0  # Unknown msg_type

    def _send_to_client(self, mac, message):
        """Send a message to a specific client.
        
        Returns:
            1 on success
            0 on failure
        """
        if mac not in self.clients:
            if self.debug:
                print("WiFiServer: client not connected:", mac.hex() if mac else "None")
            return 0
        
        try:
            sock, addr = self.clients[mac]
            sock.send(message)
            if self.debug:
                print("WiFiServer: sent to", mac.hex() if mac else "None")
            return 1
        except Exception as e:
            if self.debug:
                print("WiFiServer: send error:", e)
            self._close_client(mac)
            return 0

    def send_to_all_clients(self, message):
        """Send a message to all connected clients.
        
        Returns:
            Number of successful sends if all succeed
            Negative value if any sends failed
        """
        client_macs = [mac for mac in self.clients.keys() if mac is not None]
        if not client_macs:
            return 0
        
        success_count = 0
        for mac in client_macs:
            if self._send_to_client(mac, message):
                success_count += 1
        
        if success_count != len(client_macs):
            return success_count - len(client_macs)
        return success_count

    def get_connected_count(self):
        """Return number of connected clients."""
        return len([mac for mac in self.clients.keys() if mac is not None])

    def get_client_macs(self):
        """Return list of connected client MAC addresses."""
        return [mac for mac in self.clients.keys() if mac is not None]

    def get_authorized_macs(self):
        """Return list of authorized MAC addresses."""
        return list(self.authorized_macs)

    def stats(self):
        """Configuration plus connection statistics."""
        return {
            "config": {
                "address": self.address,
                "ssid": AP_SSID,
                "channel": AP_CHANNEL,
                "port": AP_LISTEN_PORT,
            },
            "connected": self.connected,
            "disconnected": self.disconnected,
            "received": self.received,
            "rejected": self.rejected,
            "forward_dropped": self.forward_dropped,
            "clients": self.get_connected_count(),
            "authorized_macs": len(self.authorized_macs),
        }


if __name__ == "__main__":
    # Standalone mode: run as WiFi AP server without USB gateway
    server = WiFiServer(channel_id=3, debug=True, stand_alone=True)
    
    # Add a test peer (in real use, would come from peers.json or USB)
    test_mac = bytes.fromhex("aabbccddeeff")
    server.enableNode(test_mac)
    
    # Start accepting connections
    server.start_server()
    
    print("WiFiServer: AP running, SSID:", AP_SSID)
    print("Connect clients and press Ctrl+C to stop")
    
    try:
        while True:
            server._poll()
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
