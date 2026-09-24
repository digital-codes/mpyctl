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
# WiFi AP settings (from private.py):
#   SSID, Password, Channel, IP
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
import usb_channel_server as ucs
import time
from channel_defs import KIND_BIDI, DIR_BIDI, MSG_EVENT, MSG_COMMAND, MSG_PEER_ADD, MSG_PEER_DEL, CHANNEL_WIFI

# WiFi AP configuration - read from private.py with defaults
try:
    import private as pr
    AP_SSID = getattr(pr, 'WIFI_SSID', 'MPY')
    AP_PASSWORD = getattr(pr, 'WIFI_PASSWORD', 'xxx')
    AP_CHANNEL = getattr(pr, 'WIFI_CHANNEL', 3)
except Exception:
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
        self.clients = {}  # addr -> (socket, mac)
        self.accepting = False
        self.irq_pending = False
        
        # Statistics
        self.connected = 0
        self.disconnected = 0
        self.received = 0
        self.rejected = 0
        self.forward_dropped = 0
        self.sent = 0
        self.tx_errors = 0
        self.rx_errors = 0

        # Select poll for async I/O
        import select
        self.poller = select.poll()
        self.poll_timeout = 250  # ms

        # Timer to call _poll
        import machine
        self.timer = None
        self.timer_id = 3

        # Get AP settings
        global AP_SSID, AP_PASSWORD, AP_CHANNEL
        self.ssid = AP_SSID
        self.password = AP_PASSWORD
        self.wifi_channel = AP_CHANNEL

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

        print("WiFiServer: Device ID:", config["id"])
        print("WiFiServer: SSID:", self.ssid)
        print("WiFiServer: Password:", self.password)
        print("WiFiServer: WiFi channel:", self.wifi_channel)

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
        print("WiFiServer: Initializing WiFi AP...")
        
        # Create AP interface (MicroPython uses network.AP_IF)
        self.ap = network.WLAN(network.AP_IF)
        
        # Get MAC address
        self.mac = self.ap.config('mac')
        print("WiFiServer: AP MAC:", self.mac.hex())
        
        # Configure AP with SSID, password, and channel
        print("WiFiServer: Configuring AP with ssid='%s', password='%s', channel=%d" % 
              (self.ssid, self.password, self.wifi_channel))
        self.ap.config(essid=self.ssid, password=self.password, channel=self.wifi_channel, authmode=3)
        
        # Activate AP
        self.ap.active(True)
        
        # Wait for AP to be active
        print("WiFiServer: Waiting for AP to activate...")
        while not self.ap.active():
            time.sleep(0.1)
        
        # Get IP configuration
        self.ap_ip = self.ap.ifconfig()
        print("WiFiServer: AP IP config:", self.ap_ip)
        self.server_ip = self.ap_ip[0]  # Use the actual IP from ifconfig
        
        # Bind socket to the actual IP
        print("WiFiServer: Server will bind to IP:", self.server_ip)

    def start_server(self):
        """Start accepting TCP connections."""
        if self.server_socket is not None:
            return

        print("WiFiServer: Starting TCP server on %s:%d..." % (self.server_ip, AP_LISTEN_PORT))

        # Start TCP server - bind to the actual IP address
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.server_ip, AP_LISTEN_PORT))
            self.server_socket.listen(5)
            self.server_socket.settimeout(0)  # Non-blocking
            self.accepting = True

            # Register server socket for accept
            import select
            self.poller.register(self.server_socket, select.POLLIN)

            # Start timer to call _poll
            import machine
            self.timer = machine.Timer(self.timer_id)
            self.timer.init(period=100, mode=machine.Timer.PERIODIC, callback=self._timer_callback)

            print("WiFiServer: TCP server listening on %s:%d" % (self.server_ip, AP_LISTEN_PORT))
        except Exception as e:
            print("WiFiServer: ERROR - failed to start TCP server:", e)
            self.server_socket = None
            self.accepting = False

    def stop_server(self):
        """Stop accepting TCP connections and close all client sockets."""
        self.accepting = False

        # Close all client connections
        for addr in list(self.clients.keys()):
            self._close_client(addr)

        # Close server socket
        if self.server_socket:
            try:
                self.poller.unregister(self.server_socket)
                self.server_socket.close()
            except Exception:
                pass
            self.server_socket = None

        # Stop timer
        if self.timer:
            self.timer.deinit()
            self.timer = None

    def _close_client(self, addr):
        """Close a specific client connection."""
        if addr in self.clients:
            sock, mac = self.clients[addr]
            try:
                self.poller.unregister(sock)
                sock.close()
            except Exception:
                pass
            del self.clients[addr]
            self.disconnected += 1
            if self.debug:
                print("WiFiServer: Client disconnected: %s (mac: %s)" %
                      (str(addr), mac.hex() if mac else "unknown"))

    def enableNode(self, mac, lmk=None):
        """Authorize a client MAC address to connect.
        
        Returns:
            1 on success
            0 if already authorized
            -1 on failure
        """
        mac_bytes = bytes(mac)
        if mac_bytes in self.authorized_macs:
            print("WiFiServer: MAC already authorized:", mac_bytes.hex())
            return 0
        
        self.authorized_macs.add(mac_bytes)
        print("WiFiServer: Authorized MAC:", mac_bytes.hex())
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
            print("WiFiServer: MAC not authorized:", mac_bytes.hex())
            return 0
        
        self.authorized_macs.discard(mac_bytes)
        
        # Disconnect if connected - find by MAC
        for addr, (sock, m) in list(self.clients.items()):
            if m == mac_bytes:
                self._close_client(addr)
        
        print("WiFiServer: Removed MAC:", mac_bytes.hex())
        return 1

    def close(self):
        """Stop server, close connections, and unregister the channel."""
        print("WiFiServer: Closing...")
        self.stop_server()
        
        if self.gateway:
            self.gateway.unregister_channel(self.channel_id)

    def _timer_callback(self, t):
        """Timer callback to poll for connections and data."""
        micropython.schedule(self._poll, None)

    def _poll(self, t=None):
        """Poll for new connections and data using select.poll()."""
        if not self.accepting:
            return

        import select

        # Re-register server socket and all client sockets
        self.poller.register(self.server_socket, select.POLLIN)
        for addr, (sock, mac) in self.clients.items():
            self.poller.register(sock, select.POLLIN)

        # Wait for events
        events = self.poller.poll(self.poll_timeout)
        if not events:
            return

        # Handle events
        for sock, event in events:
            if event & (select.POLLHUP | select.POLLERR):
                # Find and close the socket
                for addr, (client_sock, mac) in list(self.clients.items()):
                    if client_sock is sock:
                        if self.debug:
                            print("WiFiServer: Socket error/hup for %s" % str(addr))
                        self._close_client(addr)
                        break
                continue

            if sock is self.server_socket:
                # Server socket ready for accept
                try:
                    client_sock, addr = self.server_socket.accept()
                    self._handle_new_connection(client_sock, addr)
                except OSError:
                    pass
                except Exception as e:
                    if self.debug:
                        print("WiFiServer: ERROR - accept:", e)
            else:
                # Client socket has data
                for addr, (client_sock, mac) in list(self.clients.items()):
                    if client_sock is sock:
                        self._check_client_data(addr)
                        break

    def _handle_new_connection(self, sock, addr):
        """Handle a new TCP connection."""
        if self.debug:
            print("WiFiServer: New connection from %s" % str(addr))

        # Accept all connections initially, verify MAC on first data
        self.clients[addr] = (sock, None)
        self.connected += 1

        # Register client socket for reading
        import select
        self.poller.register(sock, select.POLLIN)

    def _check_client_data(self, addr):
        """Check if there's data from a client."""
        if addr not in self.clients:
            return

        sock, client_mac = self.clients[addr]
        try:
            sock.settimeout(0)  # Non-blocking for MicroPython
            data = sock.recv(1024)
            if data:
                self._handle_client_data(addr, data)
            else:
                # No data - connection closed
                if self.debug:
                    print("WiFiServer: Connection closed by client %s" % str(addr))
                self._close_client(addr)
        except OSError:
            pass  # No data available
        except Exception as e:
            if self.debug:
                print("WiFiServer: ERROR - reading from %s: %s" % (str(addr), e))
            self.rx_errors += 1
            self._close_client(addr)

    def _handle_client_data(self, addr, data):
        """Process data received from a client.

        Expected format: 16-byte shared key header + application data
        """
        if self.debug:
            print("WiFiServer: ============================================")
            print("WiFiServer: RECEIVED from %s" % str(addr))
            print("WiFiServer: Raw bytes:", data)
            print("WiFiServer: Raw hex:", data.hex())
            print("WiFiServer: Length:", len(data))

        if len(data) < HEADER_LEN:
            if self.debug:
                print("WiFiServer: ERROR - short data: %d bytes" % len(data))
            self.rejected += 1
            return

        # Verify shared key header
        header = data[:HEADER_LEN]
        if header != self.shared_key:
            print("WiFiServer: ERROR - invalid shared key from %s" % str(addr))
            print("WiFiServer: Expected: %s" % self.shared_key.hex())
            print("WiFiServer: Got:      %s" % header.hex())
            self.rejected += 1
            return

        if self.debug:
            print("WiFiServer: Header: %s" % header.hex())

        # Extract peer_index and message from payload
        # Format: peer_index(1) + message
        if len(data) > HEADER_LEN:
            peer_index = data[HEADER_LEN]
            message = data[HEADER_LEN + 1:]
        else:
            peer_index = 0
            message = b""

        if self.debug:
            print("WiFiServer: Peer index: %d" % peer_index)
            print("WiFiServer: Message:", message)
            try:
                print("WiFiServer: Message decode:", message.decode('utf-8'))
            except Exception as e:
                print("WiFiServer: Message decode error:", e)

        # If MAC is None, use IP as identifier (4 bytes)
        sock, client_mac = self.clients[addr]
        if client_mac is None:
            # Encode client IP as 4-byte identifier
            ip_parts = addr[0].split('.')
            client_mac = bytes([int(x) for x in ip_parts])

        if self.debug:
            print("WiFiServer: Data from %s: %s" % (str(addr), message))
        
        # Forward to USB gateway
        if self.gateway:
            payload = client_mac + message
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
            print("WiFiServer: No gateway, data logged locally")

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
        print("WiFiServer: Outbound msg_type=%d, payload_len=%d" % (msg_type, len(payload)))
        
        if msg_type == MSG_COMMAND:
            if len(payload) < 1:
                print("WiFiServer: ERROR - no peer index")
                return -1

            peer_index = payload[0]
            message = payload[1:].decode("utf-8", "replace")

            # Get list of connected client addresses
            client_addrs = list(self.clients.keys())
            
            if not client_addrs:
                print("WiFiServer: ERROR - no clients connected")
                return -2
            
            if peer_index >= len(client_addrs):
                print("WiFiServer: ERROR - invalid peer index %d (max %d)" % 
                      (peer_index, len(client_addrs) - 1))
                return -3

            addr = client_addrs[peer_index]
            full_message = self.shared_key[:HEADER_LEN] + message.encode()

            print("WiFiServer: Sending to peer %d (%s): %s" % (peer_index, str(addr), message))

            result = self._send_to_client(addr, full_message)
            return result

        elif msg_type == MSG_PEER_ADD:
            if len(payload) < 6:
                print("WiFiServer: ERROR - peer_add requires 6 bytes")
                return -4

            mac = bytes(payload[:6])
            print("WiFiServer: Authorizing MAC %s" % mac.hex())

            result = self.enableNode(mac)
            return result

        elif msg_type == MSG_PEER_DEL:
            if len(payload) < 6:
                print("WiFiServer: ERROR - peer_del requires 6 bytes")
                return -4

            mac = bytes(payload[:6])
            print("WiFiServer: De-authorizing MAC %s" % mac.hex())

            result = self.disableNode(mac)
            return result
        
        print("WiFiServer: ERROR - unknown msg_type %d" % msg_type)
        return 0

    def _send_to_client(self, addr, message):
        """Send a message to a specific client.
        
        Returns:
            1 on success
            0 on failure
        """
        if addr not in self.clients:
            print("WiFiServer: ERROR - client not connected: %s" % str(addr))
            return 0

        if self.debug:
            print("WiFiServer: Sending to %s:" % str(addr))
            print("  Raw bytes:", message)
            print("  Raw hex:", message.hex())
            print("  Length:", len(message))

        try:
            sock, mac = self.clients[addr]
            sent = sock.send(message)
            if sent == len(message):
                self.sent += 1
                if self.debug:
                    print("WiFiServer: Sent %d bytes to %s" % (sent, str(addr)))
                return 1
            else:
                if self.debug:
                    print("WiFiServer: ERROR - partial send to %s: %d/%d" %
                          (str(addr), sent, len(message)))
                self.tx_errors += 1
                return 0
        except Exception as e:
            print("WiFiServer: ERROR - send to %s: %s" % (str(addr), e))
            self.tx_errors += 1
            self._close_client(addr)
            return 0

    def send_to_all_clients(self, message):
        """Send a message to all connected clients.
        
        Returns:
            Number of successful sends if all succeed
            Negative value if any sends failed
        """
        client_addrs = list(self.clients.keys())
        if not client_addrs:
            return 0
        
        success_count = 0
        for addr in client_addrs:
            if self._send_to_client(addr, message):
                success_count += 1
        
        if success_count != len(client_addrs):
            return success_count - len(client_addrs)
        return success_count

    def get_connected_count(self):
        """Return number of connected clients."""
        return len(self.clients)

    def get_client_list(self):
        """Return list of connected clients as strings."""
        result = []
        for addr, (sock, mac) in self.clients.items():
            result.append({"addr": str(addr), "mac": mac.hex() if mac else "unknown"})
        return result

    def get_authorized_macs(self):
        """Return list of authorized MAC addresses."""
        return [m.hex() for m in self.authorized_macs]

    def stats(self):
        """Configuration plus connection statistics."""
        return {
            "wifi": {
                "ssid": self.ssid,
                "channel": self.wifi_channel,
                "ip": self.server_ip,
                "mac": self.mac.hex() if self.mac else "unknown",
            },
            "server": {
                "port": AP_LISTEN_PORT,
                "listening": self.accepting,
            },
            "stats": {
                "connected": self.connected,
                "disconnected": self.disconnected,
                "received": self.received,
                "rejected": self.rejected,
                "sent": self.sent,
                "tx_errors": self.tx_errors,
                "rx_errors": self.rx_errors,
                "forward_dropped": self.forward_dropped,
            },
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
    
    print("WiFiServer: AP running, SSID:", server.ssid)
    print("WiFiServer: Server IP:", server.server_ip)
    print("WiFiServer: Connect clients and press Ctrl+C to stop")
    
    try:
        while True:
            server._poll()
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
