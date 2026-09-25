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
# Uses UDP broadcast on port 8081 to discover server IP automatically.
#
# Configuration:
#   private.py   : WIFI_SSID, WIFI_PASSWORD, WIFI_CHANNEL
#                  WIFI_KEY (hex, its first 16 bytes become the message header)
#   config.json  : ble.key (hex) used as the shared key for messages

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
SERVER_PORT = 8080
SHARED_KEY = bytes.fromhex(pr.WIFI_KEY[:32])

print("WiFi Client starting...")
print("SSID:", WIFI_SSID)
print("Server port:", SERVER_PORT)
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
wlan.active(False) # Reset WiFi
time.sleep(1)
wlan.active(True)

while not wlan.active():
    print("Activating WiFi...")
    time.sleep(1)

# Configure channel before connecting
try:
    wlan.config(channel=WIFI_CHANNEL)
except Exception:
    pass

try:
    wlan.config(pm=wlan.PM_NONE)
except Exception:
    pass

# Wait for connection
print("Connecting to WiFi...")
wlan.connect(WIFI_SSID, WIFI_PASSWORD)
while not wlan.isconnected():
    print("Connecting to WiFi...")
    for _ in range(10):
        if wlan.isconnected():
            break
        time.sleep(1)

print("Connected! IP:", wlan.ifconfig()[0])
SERVER_IP = wlan.ifconfig()[2]  # gateway
print("Using server:", SERVER_IP)

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

# Peer index for this client (assign manually or from config)
MY_PEER_INDEX = 0


def send_message(message):
    """Send a message to the server with peer index (no shared key - WPA security)."""
    global sock
    if sock is None:
        return False

    try:
        payload = bytes([MY_PEER_INDEX]) + message.encode()
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
            # WiFi: message is peer_index(1) + data
            if len(data) >= 1:
                peer_index = data[0]
                message = data[1:]
                print("\n*** Received from server ***")
                print("    Peer index:", peer_index)
                print("    Data:", message.decode('utf-8', errors='replace'))
                received_count += 1
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
