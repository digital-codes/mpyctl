# SPDX-License-Identifier: AGPL-3.0-only
# wifi_client_example.py
#
# WiFi TCP client. Runs on a SECOND ESP32 board (not the gateway).
#
# Connects to the WiFi AP (SSID: MPY, password: xxx) and sends TCP messages
# to the server on port 8080 every 5 seconds:
#   payload = 16-byte shared key header + "sensor message <n>"
#
# Also receives messages from the server and prints them.
#
# Configuration:
#   private.py   : WIFI_SSID, WIFI_PASSWORD, WIFI_CHANNEL
#                  WIFI_SERVER_IP (server IP address)
#                  WIFI_KEY (hex, its first 16 bytes become the message header)
#   config.json  : ble.key (hex) used as the shared key for messages
#
# The server must have this board registered via enableNode()/peers.json
# with the matching MAC address.

import time
import json
import network
import socket
import micropython

# get configuration from private.py
import private as pr
WIFI_SSID = pr.WIFI_SSID
WIFI_PASSWORD = pr.WIFI_PASSWORD
WIFI_CHANNEL = pr.WIFI_CHANNEL
SERVER_IP = pr.WIFI_SERVER_IP
SERVER_PORT = 8080
SHARED_KEY = bytes.fromhex(pr.WIFI_KEY[:32])

print("WiFi Client starting...")
print("SSID:", WIFI_SSID)
print("Server:", SERVER_IP, "port:", SERVER_PORT)
print("Shared key:", SHARED_KEY.hex())

try:
    with open("config.json", "r") as f:
        config = json.load(f)
        print("Config:", config)
except Exception as e:
    print("Failed to load config.json:", e)
    config = {}

# Connect to WiFi
wlan = network.WLAN(network.STA_IF)
wlan.active(True)

# Configure channel before connecting
try:
    wlan.config(channel=WIFI_CHANNEL)
except Exception:
    pass

try:
    wlan.config(pm=wlan.PM_NONE)
except Exception:
    pass

print("Connecting to WiFi...")
wlan.connect(WIFI_SSID, WIFI_PASSWORD)

# Wait for connection
max_wait = 20
while max_wait > 0:
    if wlan.status() < 0 or wlan.status() >= 3:
        break
    max_wait -= 1
    time.sleep(0.5)

if wlan.status() != 3:
    print("Failed to connect to WiFi, status:", wlan.status())
else:
    print("Connected! IP:", wlan.ifconfig()[0])

# Receive state
irq_pending = False
received_count = 0

# Server socket
sock = None

def connect_to_server():
    """Connect to the TCP server."""
    global sock
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((SERVER_IP, SERVER_PORT))
        sock.settimeout(0)  # Non-blocking
        print("Connected to server")
        return True
    except Exception as e:
        print("Failed to connect to server:", e)
        return False

def send_message(message):
    """Send a message to the server with shared key header."""
    global sock
    if sock is None:
        return False
    
    try:
        payload = SHARED_KEY[:16] + message
        sock.send(payload)
        return True
    except Exception as e:
        print("Send error:", e)
        return False

def receive_messages():
    """Check for and receive messages from server."""
    global received_count
    if sock is None:
        return
    
    try:
        sock.setblocking(False)
        data = sock.recv(1024)
        if data:
            # Check for shared key header
            if len(data) >= 16 and data[:16] == SHARED_KEY:
                application_data = data[16:]
                print("\n*** Received from server ***")
                print("    Data:", application_data.decode())
                received_count += 1
            else:
                print("\n*** Received from server (no valid header) ***")
                print("    Data:", data)
    except OSError:
        pass  # No data available
    except Exception as e:
        print("Receive error:", e)

# Connect to server
connect_to_server()

counter = 0
while True:
    # Check for incoming messages
    receive_messages()
    
    # Send a message every 5 seconds
    message = "sensor message %d" % counter
    print("Sending message %d: %s" % (counter, message))
    
    if send_message(message):
        print("Send result: OK")
    else:
        print("Send result: FAIL")
        # Try to reconnect
        try:
            if sock:
                sock.close()
        except Exception:
            pass
        sock = None
        connect_to_server()
    
    counter += 1
    
    # Sleep in small increments to allow receiving
    for _ in range(50):
        time.sleep(0.1)
        receive_messages()
